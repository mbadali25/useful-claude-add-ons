#!/usr/bin/env python3
"""gizmoduck - run Nuclei, or the whole scanner routine from a manifest, and turn the
output into a report or SDP tickets.
Cross-platform (Windows + Linux/WSL), stdlib only - except `routine`, which imports
routine.py (and so PyYAML) lazily, inside that command alone.

Only scan assets you own or have explicit written permission to test.

Usage:
  gizmoduck.py scan    <target|targets.txt> [--severity critical,high,medium] [--out findings.jsonl] [--extra "..."]
  gizmoduck.py routine <manifest.yaml> [--out DIR | --scan-root MODULE_DIR [--date YYYY-MM-DD]]
                       [--replace] [--confirm-active] [--title "..."] [--min-severity medium]
                       # every scanner the manifest resolves (checkov, trivy, dependency-check,
                       # semgrep, ZAP, testssl, nmap, nikto; sqlmap only on a target whose
                       # options.sqlmap is true AND with --confirm-active named),
                       # then findings.jsonl, run-manifest.json, report.md/.html(/.pdf) and
                       # scan-meta.json in DIR (default routine-out/) or in
                       # MODULE_DIR/docs/security-scans/YYYY-MM-DD/. A directory already
                       # holding a scan-meta.json is refused unless --replace is named.
                       # Exit 0: every cell ran. Exit 4: every output was written but some
                       # cell did not run - NOT a clean result; the last stdout line is
                       # GIZMODUCK_ROUTINE_INCOMPLETE. Exit 2: usage or manifest error,
                       # nothing written. scan-meta.json and report.* are written
                       # complete-then-renamed; routine.py's own findings.jsonl,
                       # run-manifest.json and each tool's native output are not.
  gizmoduck.py summary <findings.jsonl>
  gizmoduck.py parse   <findings.jsonl> [--min-severity info|low|medium|high|critical]
  gizmoduck.py report  <findings.jsonl> [--min-severity medium] [--format md|html|pdf] [--out FILE] [--title "..."]
                       [--run-manifest run-manifest.json]
                       # --run-manifest: a routine run's manifest, so the report carries its
                       # coverage table; ignored for plain Nuclei findings.
                       # itemises Critical/High/Medium; Low and Info are counted only.
                       # --min-severity raises that floor, never lowers it.
  gizmoduck.py tickets <findings.jsonl> [--min-severity high] [--yes DIGEST]
                       # without --yes: prints a human-readable preview of the tickets that
                       # WOULD be created, a digest over that exact batch, and the rerun
                       # command carrying it; exits 3 without emitting ticket records.
                       # with --yes DIGEST: emits the ticket records (JSON) for creation,
                       # but only if DIGEST matches the batch as recomputed right now -
                       # a stale or wrong digest (a different findings file, a different
                       # --min-severity) is refused rather than silently widened.
  gizmoduck.py diff    <baseline.jsonl> <current.jsonl> [--min-severity high]   # what's new since last scan
  gizmoduck.py update                                                            # update nuclei + templates
  gizmoduck.py doctor                                                            # check the local toolchain

A "target" is a URL (https://site) or a host/IP; a targets file has one per line.
"""
import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

SEV_NUM = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0, "unknown": 0}
SEV_NAME = {4: "Critical", 3: "High", 2: "Medium", 1: "Low", 0: "Info"}
SEV_COLOR = {4: "#7a1616", 3: "#b3541e", 2: "#b59a00", 1: "#3a7a3a", 0: "#666"}
ORDER = [4, 3, 2, 1, 0]

# Reports itemise Critical, High and Medium only. Low and Info are counted in
# the severity table and then deliberately dropped, because nobody works that
# queue: a signature scanner's low/info output is inventory - version banners,
# DNS records, "a form exists" - and listing it buries the findings somebody is
# actually expected to fix. `--min-severity` can raise this floor (report only
# High and above, say) but never lower it; a request for `info` still gets
# counts rather than pages of noise.
REPORT_DETAIL_FLOOR = 2  # Medium

# Combined-report grouping (Task 16 / spec 7, 12.3): findings are grouped by
# target then by category, not by tool - so `deps` (trivy + depcheck) and
# `iac` (checkov + trivy) each render as one section per target even though
# two tools feed them. A finding carries `tool` and `target` but not the
# target's own `kind`, so category is derived from the reporting tool here.
# trivy is the one adapter that serves two categories from one binary
# (scanners/trivy.py); it is disambiguated by the `type` field its own
# adapter already sets ("vulnerability" -> deps, "misconfiguration" -> iac)
# rather than by a second lookup, since that field is the one piece of
# category-bearing data trivy's finding shape already carries.
#
# nuclei/nmap/testssl also run against `host`-kind targets (KIND_DEFAULTS'
# `host` list is a strict subset of `web`'s), but nothing in the finding shape
# distinguishes a host-kind run from a web-kind one at report time, so those
# land under `web` here. Widening this precisely would mean normalize.py
# growing a `kind`/`category` field on every finding - out of scope for this
# task and not this file's to add.
# All ten tools (nuclei, zap, nikto, nmap, testssl, trivy, depcheck, checkov,
# sqlmap, semgrep) must resolve to a real category here.
# sqlmap only ever runs against a `web`-kind target (a concrete injection
# point - scanners/sqlmap.py), same as nuclei/zap/nikto/nmap/testssl, so it
# joins them rather than getting a category of its own. Missing an entry
# here used to mean the finding fell through to "other", which the renderer
# then never visited at all - a confirmed finding (e.g. a proven SQL
# injection) existed in the data and never appeared anywhere in the report.
_TOOL_CATEGORY = {
    "nuclei": "web", "zap": "web", "nikto": "web", "nmap": "web", "testssl": "web",
    "sqlmap": "web",
    "depcheck": "deps",
    "checkov": "iac",
    # semgrep reads source, which no other tool here does, so it gets its own
    # category rather than being folded into one of the existing three. Without
    # an entry it would fall through to "other" - the exact path by which
    # sqlmap's findings once existed in the data and appeared nowhere in the
    # report.
    "semgrep": "code",
}
CATEGORY_ORDER = ["web", "deps", "iac", "code"]
CATEGORY_LABEL = {"web": "Web", "deps": "Dependencies", "iac": "Infrastructure as Code",
                  "code": "Source Code", "other": "Other"}


def category_of(f):
    tool = f.get("tool")
    if tool == "trivy":
        return "iac" if f.get("type") == "misconfiguration" else "deps"
    return _TOOL_CATEGORY.get(tool, "other")


def _categories_for(findings):
    """CATEGORY_ORDER, extended with any category `category_of` returns that
    isn't already in that fixed list. A finding that exists must never be
    silently absent from the report just because its tool isn't one of the
    ones this module knows how to name a section for (HIGH defect: this is
    exactly how sqlmap's findings went missing before it was added to
    `_TOOL_CATEGORY` above) - a future/unmapped tool now gets its own
    "Other"-labelled section instead of vanishing. Extra categories are
    sorted for a stable order and appended after the fixed three, so
    today's output (only web/deps/iac ever appear) is unaffected."""
    extra = sorted({category_of(f) for f in findings} - set(CATEGORY_ORDER))
    return CATEGORY_ORDER + extra


def find_nuclei():
    for name in ("nuclei", "nuclei.exe"):
        p = shutil.which(name)
        if p:
            return p
    # common go install location
    cand = os.path.expanduser("~/go/bin/nuclei")
    return cand if os.path.exists(cand) else None


def cmd_scan(target, out, severity, extra):
    exe = find_nuclei()
    if not exe:
        sys.exit("nuclei not found on PATH. Run bootstrap.sh (Linux/WSL) or bootstrap.ps1 (Windows) first.")
    cmd = [exe, "-jsonl", "-silent", "-nc"]
    cmd += ["-l", target] if os.path.isfile(target) else ["-u", target]
    if severity:
        cmd += ["-severity", severity]
    if extra:
        cmd += extra.split()
    print(f"# running: {' '.join(cmd)}", file=sys.stderr)
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip().startswith("{")]
    # Do NOT write an output file for a failed scan. One that died - bad target,
    # missing templates, no network - produces no stdout, and writing that as an
    # empty findings file is indistinguishable from a clean result: the report
    # says nothing was found, the diff says nothing is new, and the baseline the
    # next scan compares against is a lie.
    #
    # Exit 1 is the ambiguous one: with `-ec` nuclei uses it to mean "findings
    # exist", but it is also a plain failure code. Findings on stdout settle it.
    # Exit 1 with nothing on stdout is a failure, not a clean run.
    if proc.returncode != 0 and not (proc.returncode == 1 and lines):
        sys.stderr.write(proc.stderr)
        sys.exit(f"nuclei exited {proc.returncode} with no findings on stdout; "
                 f"no findings file written (a failed scan is not a clean scan)")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + ("\n" if lines else ""))
    safe_print(f"wrote {len(lines)} findings to {out}")
    return out


def write_text(path, text):
    """Write `text` to `path` as UTF-8, closing the handle on the way out."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def safe_print(s=""):
    """print() that cannot raise UnicodeEncodeError. Nuclei template names are
    attacker-influenced free text; on Windows Git Bash's python3, sys.stdout.encoding
    is cp1252, so a non-ASCII name (accented characters, an emoji) would otherwise
    crash mid-preview with a generic exit 1 - hiding the gated command's exit 3
    marker and inviting a caller to rerun with --yes without ever seeing a preview.

    Every stdout path that can carry finding-derived text (report/diff output,
    not just the tickets preview) goes through this, not print() directly.

    errors="backslashreplace", not "replace": "replace" collapses every
    unencodable character to the same "?", so an operator approving what the
    preview shows is approving a string ("Caf? ? TLS ?") that is strictly
    lossy versus the record actually filed ("Café — TLS ⚠") - two different
    inputs could render identically. backslashreplace keeps each codepoint
    distinguishable (\\u26a0 etc.), so the preview and the payload differ only
    in how a character is spelled, never in what was approved."""
    enc = sys.stdout.encoding or "utf-8"
    print(s.encode(enc, errors="backslashreplace").decode(enc))


def _records_digest(records):
    """Short digest over the exact ticket records a preview showed.

    Binds a `--yes` rerun to that batch: the value must match what
    re-deriving `cmd_tickets` from the same findings file and --min-severity
    produces right now, or the rerun is refused (see the gate in main()).
    Not a cryptographic approval - both preview and rerun compute it from the
    same untrusted input - it only catches the batch having silently changed
    shape between the two: a wider or narrower --min-severity, a different
    findings file passed by mistake, or findings edited in between. Without
    it, nothing bound --yes to what was actually shown - a preview at
    --min-severity critical (one ticket) followed by a bare --yes at the
    tool's default floor emitted every High as well.

    sort_keys + compact separators + ensure_ascii so the same records always
    hash the same regardless of dict insertion order or which platform ran
    json.dumps.
    """
    canon = json.dumps(records, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:12]


def _is_raw_nuclei_record(r):
    """True for a raw `nuclei -jsonl` line: a top-level `template-id`
    (hyphen) alongside a nested `info` object holding name/severity/etc.
    Both are present on every real Nuclei line and neither ever appears on
    an already-normalized finding (normalize.make_finding uses `template_id`
    with an underscore and never nests an `info` dict), so checking both
    together can't misfire on the normalized shape."""
    return "template-id" in r and isinstance(r.get("info"), dict)


def _is_normalized_record(r):
    """True for an already-normalized finding (normalize.make_finding's
    shape, which is what `routine` writes to findings.jsonl - routine.py
    ~422). `template_id` (underscore) plus `severity_name` are both always
    present on that shape and neither ever appears at the top level of raw
    Nuclei output (Nuclei's equivalents are `template-id` and the nested
    `info.severity`), so the pair can't misfire on a raw record either."""
    return "template_id" in r and "severity_name" in r


def load(path):
    """Parse a findings.jsonl file. Two, and only two, line shapes are
    recognized:

    - raw `nuclei -jsonl` output, re-derived into this module's finding
      dict from `template-id`/`info`/... as it always has been;
    - an already-normalized finding (normalize.make_finding's shape - what
      `routine` writes), passed through UNCHANGED.

    Passing normalized records through raw-Nuclei re-derivation was the
    CRITICAL defect this guards against: a normalized record has no
    `info` object, so every field the raw path reads from `info` (name,
    severity, description, remediation, reference, tags) came back blank,
    severity silently defaulted to Info, and `tool`/`target`/`matched_at`
    were dropped outright - which made `gizmoduck report <routine's own
    findings.jsonl>` print "No action required" over a real finding. A
    line matching neither shape is rejected rather than treated as raw
    Nuclei with everything blank."""
    findings = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if _is_normalized_record(r):
                findings.append(r)
                continue
            if not _is_raw_nuclei_record(r):
                raise ValueError(
                    f"{path}: line matches neither raw Nuclei JSONL (`template-id` + "
                    "`info`) nor an already-normalized finding (`template_id` + "
                    f"`severity_name`): {line!r:.200}"
                )
            info = r.get("info", {})
            cls = info.get("classification") or {}
            sev = SEV_NUM.get((info.get("severity") or "unknown").lower(), 0)
            findings.append({
                "template_id": r.get("template-id", ""),
                "name": info.get("name", r.get("template-id", "")),
                "severity": sev,
                "severity_name": SEV_NAME[sev],
                "type": r.get("type", ""),
                # Carried so a report regenerated later still names the date the
                # scan ran, rather than the date it was printed.
                "timestamp": r.get("timestamp", ""),
                "host": r.get("host", ""),
                "matched_at": r.get("matched-at", r.get("matched", "")),
                "cve": cls.get("cve-id") or [],
                "cvss": cls.get("cvss-score", ""),
                "description": info.get("description", "") or "",
                "remediation": info.get("remediation", "") or "",
                "reference": info.get("reference") or [],
                "tags": info.get("tags") or [],
            })
    return findings


def dedupe(findings):
    groups = {}
    for f in findings:
        # Key on (target, template_id), not template_id alone. A combined
        # routine run holds many targets in one findings list, and keying on
        # the template alone collapsed the same template across every site -
        # which also made the per-target report grouping impossible. Plain
        # Nuclei findings carry no `target`, so they key on (None, id) and
        # group exactly as they always have.
        key = (f.get("target"), f["template_id"])
        g = groups.get(key)
        if g is None:
            groups[key] = g = {**f, "affected": [], "raw_count": 0}
        else:
            # A group must reflect the HIGHEST severity any member carries,
            # and must retain the severity-assigned marker if ANY member
            # has it. `setdefault()` used to keep only the FIRST record's
            # severity and tags - later records in the same group
            # contributed only location/count - so a known-severity finding
            # merged with a later null-severity one silently lost its
            # severity-assigned marker, and reversing the arrival order of a
            # low and a critical record for the same group changed the
            # reported severity. Order must never matter here.
            if f["severity"] > g["severity"]:
                g["severity"] = f["severity"]
                g["severity_name"] = f["severity_name"]
            if "severity-assigned" in (f.get("tags") or []):
                if "severity-assigned" not in (g.get("tags") or []):
                    g["tags"] = list(g.get("tags") or []) + ["severity-assigned"]
        g["affected"].append(f["matched_at"] or f["host"])
        g["raw_count"] += 1
    for g in groups.values():
        g["affected"] = sorted(set(a for a in g["affected"] if a))
        # `instances` counts distinct locations, not findings: one template can
        # fire many times against a single URL (http-missing-security-headers
        # fires once per absent header). Both numbers are kept because reporting
        # only `instances` makes the per-severity totals look wrong - a summary
        # saying 42 Info next to rows summing to 20 reads as a bug.
        g["instances"] = len(g["affected"])
    return list(groups.values())


def cmd_summary(findings):
    counts = defaultdict(int)
    hosts = set()
    for f in findings:
        counts[f["severity"]] += 1
        if f["host"]:
            hosts.add(f["host"])
    return {"hosts": len(hosts), "total_instances": len(findings),
            "by_severity": {SEV_NAME[s]: counts[s] for s in ORDER}}


def detail_floor(min_sev):
    """The severity at or above which findings are itemised.

    Never below Medium - see REPORT_DETAIL_FLOOR. A caller asking for `info`
    gets the counts it implies and none of the listing.
    """
    return max(min_sev, REPORT_DETAIL_FLOOR)


def _is_combined(findings, run_manifest=None):
    """True when the input is a `routine` combined run rather than plain
    Nuclei output.

    Primarily decided by the presence of a `target` field on any finding
    (Task 16 step 3: "keyed on the presence of target/tool fields"), never
    merely by whether a run_manifest was supplied - a caller can mistakenly
    pass an unrelated manifest alongside real flat Nuclei findings, and that
    must still render the untouched flat path byte-for-byte (Global
    Constraints, "Additive only";
    test_plain_nuclei_input_ignores_a_run_manifest_too pins this).

    The one exception is an EMPTY findings list together with a real
    run_manifest (CRITICAL defect): `target` can only ever appear on an
    actual finding, so a run where every tool errored or was skipped -
    zero findings, but a manifest full of `error:*`/`skipped-*` cells -
    used to fall through to the flat path and print "No action required",
    discarding the exact evidence (the coverage table) that distinguishes a
    failed scan from a clean one. `run_manifest` is only ever produced by
    `routine`, so its presence is sufficient in this one case, where there
    is no finding to have carried `target` in the first place."""
    if any(f.get("target") for f in findings):
        return True
    return not findings and bool(run_manifest and run_manifest.get("cells"))


def cmd_report(findings, min_sev, title, run_manifest=None):
    if _is_combined(findings, run_manifest):
        return _cmd_report_combined(findings, min_sev, title, run_manifest)
    floor = detail_floor(min_sev)
    uniq = sorted(dedupe(findings), key=lambda f: (-f["severity"], f["name"]))
    s = cmd_summary(findings)
    counts = s["by_severity"]
    shown = [f for f in uniq if f["severity"] >= floor]
    suppressed = sum(counts[SEV_NAME[x]] for x in ORDER if x < floor)

    out = [f"# {title}", ""]
    out += [f"**Hosts with findings:** {s['hosts']}  ",
            f"**Total finding instances:** {s['total_instances']}", ""]

    out += ["| Severity | Count | In this report |", "|---|---:|---|"]
    for x in ORDER:
        state = "itemised" if x >= floor else "count only"
        out.append(f"| {SEV_NAME[x]} | {counts[SEV_NAME[x]]} | {state} |")
    out.append("")

    if suppressed:
        noun = "finding" if suppressed == 1 else "findings"
        out += [f"_{suppressed} {noun} below {SEV_NAME[floor]} were recorded and are "
                f"not itemised. They are inventory - version banners, DNS records, the "
                f"presence of a form - rather than remediation work. The full detail "
                f"remains in the JSONL._", ""]

    if not shown:
        out += ["## No action required", "",
                f"Nothing at or above {SEV_NAME[floor]}. "
                f"Note that this reflects what a signature scanner can match, "
                f"not an absence of vulnerabilities.", ""]
        return "\n".join(out)

    out += [f"## Findings requiring action ({len(shown)})", ""]
    for n, f in enumerate(shown, 1):
        cvss = f["cvss"] or "n/a"
        cves = ", ".join(f["cve"]) if f["cve"] else "-"
        locations = f.get("instances", len(f.get("affected") or []))
        raw = f.get("raw_count", locations)
        hits = (f"{raw}" if raw == locations
                else f"{raw} detections across {locations} location(s)")
        out += [f"### {n}. {f['name']} - {SEV_NAME[f['severity']]}", ""]
        out += ["| | |", "|---|---|",
                f"| Template | `{f['template_id']}` |",
                f"| Type | {f['type'] or '-'} |",
                f"| CVSS | {cvss} |",
                f"| CVE | {cves} |",
                f"| Detections | {hits} |", ""]
        if f["description"]:
            out += ["**Detail**", "", f["description"].strip(), ""]
        if f.get("affected"):
            out += ["**Affected**", ""]
            out += [f"- `{a}`" for a in f["affected"]]
            out.append("")
        if f["remediation"]:
            out += ["**Remediation**", "", f["remediation"].strip(), ""]
        refs = [r for r in (f.get("reference") or []) if r][:4]
        if refs:
            out += ["**References**", ""] + [f"- {r}" for r in refs] + [""]
    return "\n".join(out)


def _cell_text(cell):
    """Render one coverage-table cell. `ran`/`ran(mode)` always carries its
    finding count, so `ran` with zero findings reads as "ran - 0 findings" and
    not merely "ran" - indistinguishable-from-clean is the exact failure this
    table exists to prevent (a WAF blocked a real scan and it read as 0
    findings = clean). `skipped-missing`, `skipped-active` and `error:*`
    render as their bare status, which is already visually distinct from any
    `ran` variant.

    A `ran` cell can still carry a non-empty `errors` list - an adapter's own
    parse_errors() output (routine.py; currently only testssl's WARN/FATAL
    entries), which is not a finding and not a cell-level `error:*` status
    either, because the tool process itself completed. Left unflagged, a
    target testssl couldn't fully reach would read as "ran - 0 findings",
    the exact same text as a target that is genuinely clean - so a non-empty
    `errors` list always appends a scan-error note, however many findings
    were also found.

    `count` missing entirely or explicitly `null` is not the same thing as
    a confirmed zero - `cell.get("count") or 0` used to collapse both into
    "0 findings", manufacturing a definite clean count out of incomplete
    evidence (MEDIUM defect). Only a real int (0 included) renders a count;
    anything else renders an explicit "findings unknown" instead."""
    status = cell.get("status", "")
    if status == "ran" or status.startswith("ran("):
        n = cell.get("count")
        if n is None:
            text = f"{status} - findings unknown"
        else:
            noun = "finding" if n == 1 else "findings"
            text = f"{status} - {n} {noun}"
        errs = cell.get("errors") or []
        if errs:
            enoun = "scan error" if len(errs) == 1 else "scan errors"
            text += f" ({len(errs)} {enoun})"
        return text
    return status


def _coverage_table_md(run_manifest):
    """Rows = targets, columns = tools, cells = status (spec 7). Column order
    follows first appearance in `cells` rather than an alphabetical or fixed
    list, so a manifest naming only the tools it actually used doesn't grow
    columns for tools no target in this run ever touched."""
    cells = run_manifest.get("cells") or []
    if not cells:
        return []
    targets = sorted({c["target"] for c in cells})
    tools = []
    for c in cells:
        if c["tool"] not in tools:
            tools.append(c["tool"])
    by_pair = {(c["target"], c["tool"]): c for c in cells}

    header = "| Target | " + " | ".join(tools) + " |"
    sep = "|---" * (len(tools) + 1) + "|"
    rows = [header, sep]
    for t in targets:
        row = [t]
        for tool in tools:
            c = by_pair.get((t, tool))
            row.append(_cell_text(c) if c is not None else "n/a")
        rows.append("| " + " | ".join(row) + " |")
    return rows


def _render_finding_block_md(f, n):
    """One itemised finding, grouped-report style. Deliberately not shared
    with the flat path's identical-looking loop in cmd_report above: the flat
    path's output is pinned byte-for-byte (Global Constraints, "Additive
    only") and factoring it out risks a subtle diff neither test would catch
    reliably. The one addition here is the reporting-tool label, since a
    grouped report can show findings from several tools in one category."""
    cvss = f["cvss"] or "n/a"
    cves = ", ".join(f["cve"]) if f["cve"] else "-"
    locations = f.get("instances", len(f.get("affected") or []))
    raw = f.get("raw_count", locations)
    hits = (f"{raw}" if raw == locations
            else f"{raw} detections across {locations} location(s)")
    tools_list = f.get("tools") or ([f["tool"]] if f.get("tool") else [])
    tool_label = "+".join(t for t in tools_list if t) or "-"

    out = [f"#### {n}. {f['name']} - {SEV_NAME[f['severity']]} ({tool_label})", ""]
    out += ["| | |", "|---|---|",
            f"| Template | `{f['template_id']}` |",
            f"| Type | {f['type'] or '-'} |",
            f"| CVSS | {cvss} |",
            f"| CVE | {cves} |",
            f"| Detections | {hits} |", ""]
    if f["description"]:
        out += ["**Detail**", "", f["description"].strip(), ""]
    if f.get("affected"):
        out += ["**Affected**", ""]
        out += [f"- `{a}`" for a in f["affected"]]
        out.append("")
    if f["remediation"]:
        out += ["**Remediation**", "", f["remediation"].strip(), ""]
    refs = [r for r in (f.get("reference") or []) if r][:4]
    if refs:
        out += ["**References**", ""] + [f"- {r}" for r in refs] + [""]
    return out


def _cmd_report_combined(findings, min_sev, title, run_manifest):
    """The `routine` combined-report path: one section per target, findings
    within a target grouped by category (not by tool - spec 7/12.3), and a
    coverage table up top so a `skipped`/`error` cell is never mistaken for a
    clean result. Kept entirely separate from the flat path in cmd_report
    above rather than branching partway through it, so the flat path's
    byte-for-byte output guarantee has nothing new to break it."""
    floor = detail_floor(min_sev)
    s = cmd_summary(findings)
    counts = s["by_severity"]
    suppressed = sum(counts[SEV_NAME[x]] for x in ORDER if x < floor)

    out = [f"# {title}", ""]
    if run_manifest and run_manifest.get("authorized_by"):
        out += [f"**Authorized by:** {run_manifest['authorized_by']}  "]
    out += [f"**Hosts with findings:** {s['hosts']}  ",
            f"**Total finding instances:** {s['total_instances']}", ""]

    if run_manifest:
        out += ["## Coverage", ""]
        out += _coverage_table_md(run_manifest)
        out += ["", "_A `ran` cell states its finding count, including zero. "
                "That is not the same as `skipped-missing` (the tool was not "
                "installed), `skipped-active` (an active-mode tool was not "
                "opted in) or an `error` cell (the tool started and did not "
                "finish) - each of those means no result was produced at all, "
                "which a bare absence of findings must never be confused "
                "with._", ""]

    out += ["| Severity | Count | In this report |", "|---|---:|---|"]
    for x in ORDER:
        state = "itemised" if x >= floor else "count only"
        out.append(f"| {SEV_NAME[x]} | {counts[SEV_NAME[x]]} | {state} |")
    out.append("")

    if suppressed:
        noun = "finding" if suppressed == 1 else "findings"
        out += [f"_{suppressed} {noun} below {SEV_NAME[floor]} were recorded and are "
                f"not itemised. They are inventory - version banners, DNS records, the "
                f"presence of a form - rather than remediation work. The full detail "
                f"remains in the JSONL._", ""]

    targets = sorted({f["target"] for f in findings if f.get("target")})
    for t in targets:
        t_findings = [f for f in findings if f.get("target") == t]
        t_uniq = sorted(dedupe(t_findings), key=lambda f: (-f["severity"], f["name"]))
        out += [f"## {t}", ""]
        for cat in _categories_for(t_uniq):
            cat_findings = [f for f in t_uniq if category_of(f) == cat]
            if not cat_findings:
                continue
            shown = [f for f in cat_findings if f["severity"] >= floor]
            out += [f"### {CATEGORY_LABEL.get(cat, cat)} ({len(cat_findings)})", ""]
            if not shown:
                out += [f"Nothing at or above {SEV_NAME[floor]}.", ""]
                continue
            for n, f in enumerate(shown, 1):
                out += _render_finding_block_md(f, n)
    return "\n".join(out)


def _template_module():
    """Load report_template.py, which sits beside this script.

    A plain `import` works when gizmoduck.py is run directly, because its own
    directory heads sys.path. The by-path fallback covers the case where it has
    been imported as a module from elsewhere and that is no longer true.
    """
    try:
        import report_template
        return report_template
    except ImportError:
        import importlib.util
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "report_template.py")
        spec = importlib.util.spec_from_file_location("report_template", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod


def _grouped_sections(findings, floor):
    """Same grouping _cmd_report_combined uses for Markdown (Task 16), built
    once here so the HTML path (Task 17) gets identical target/category
    grouping instead of re-deriving it - report_template.py stays presentation
    -only and never learns what a "category" is.

    Returns [(target, [(category_label, all_findings, shown_findings), ...]), ...]
    """
    groups = []
    targets = sorted({f["target"] for f in findings if f.get("target")})
    for t in targets:
        t_findings = [f for f in findings if f.get("target") == t]
        t_uniq = sorted(dedupe(t_findings), key=lambda f: (-f["severity"], f["name"]))
        cats = []
        for cat in _categories_for(t_uniq):
            cat_findings = [f for f in t_uniq if category_of(f) == cat]
            if not cat_findings:
                continue
            shown = [f for f in cat_findings if f["severity"] >= floor]
            cats.append((CATEGORY_LABEL.get(cat, cat), cat_findings, shown))
        groups.append((t, cats))
    return groups


def render_html(findings, min_sev, title, run_manifest=None):
    """Presentation lives in report_template.py; this stays the data prep.

    dedupe() and cmd_summary() own what a finding *is*; the template module owns
    only how it looks, and is handed the severity vocabulary rather than
    redefining it. Combined-run grouping (Task 17) follows the same rule:
    report_template.py is handed already-grouped data, not the tool/category
    mapping that produced it.
    """
    uniq = sorted(dedupe(findings), key=lambda f: (-f["severity"], f["name"]))
    combined = _is_combined(findings, run_manifest)
    groups = _grouped_sections(findings, detail_floor(min_sev)) if combined else None
    return _template_module().render_report(
        uniq=uniq,
        summary=cmd_summary(findings),
        min_sev=min_sev,
        title=title,
        sev_name=SEV_NAME,
        order=ORDER,
        findings=findings,
        run_manifest=run_manifest if combined else None,
        groups=groups,
    )


def html_to_pdf(html_str, out_path):
    wk = shutil.which("wkhtmltopdf")
    if wk:
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as t:
            t.write(html_str)
            tmp = t.name
        try:
            # check=False and OSError caught: a wkhtmltopdf that is installed
            # but fails - a broken build, a sandboxed temp dir, a binary that
            # will not launch at all - would otherwise raise past the WeasyPrint
            # fallback below and take the whole report command with it, when the
            # fallback would have produced the file.
            if subprocess.run([wk, "-q", "--enable-local-file-access", tmp, out_path],
                              check=False).returncode == 0:
                return True
        except OSError:
            pass
        finally:
            os.unlink(tmp)
    try:
        from weasyprint import HTML  # type: ignore
        HTML(string=html_str).write_pdf(out_path)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# `routine`: the front door to routine.run_routine (T-0107)
# ---------------------------------------------------------------------------

# Exit status of a routine run that wrote every output but where at least one
# (target, tool) cell did not run. Deliberately distinct from 0: a partial
# run is not a clean run, and a scheduler reading only the status must be
# able to tell the two apart without parsing the report.
ROUTINE_INCOMPLETE_EXIT = 4
# The last stdout line of an incomplete run, for callers that read output
# rather than the status (the same shape as GIZMODUCK_CONFIRMATION_REQUIRED).
ROUTINE_MARKER = "GIZMODUCK_ROUTINE_INCOMPLETE"
SCAN_META_SCHEMA = 1
# Every file a routine run owns in its output directory. `--replace` removes
# these, and the per-target subdirectories the earlier scan-meta.json names,
# before rerunning into it - nothing else in the directory.
ROUTINE_FILES = ("scan-meta.json", "findings.jsonl", "run-manifest.json",
                 "report.md", "report.html", "report.pdf")
_ROUTINE_DEFAULT_OUT = "routine-out"


def _atomic_write_text(path, text):
    """Write `text` to a sibling temp file, then os.replace it over `path`.

    `text` must be complete before this is called. A plain
    `with open(path, "w")` truncates `path` at open time, before the payload
    exists, so a write that raises leaves a zero-byte file where the earlier
    run's evidence was (project CLAUDE.md, the `open(p, "w")` landmine).
    Here a failure costs the temp file and nothing else: `path` holds either
    the old bytes or the new ones, never neither."""
    tmp = f"{path}.tmp-{os.getpid()}"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _gizmoduck_version():
    """The plugin version from `.claude-plugin/plugin.json` beside `scripts/`,
    or None when that file is absent or unreadable - a vendored copy of
    `scripts/` alone carries no version, and "could not tell" is recorded as
    null rather than guessed."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                        ".claude-plugin", "plugin.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data.get("version")
    except (OSError, ValueError, AttributeError):
        return None


def _status_family(status):
    """`ran`, `ran(safe)`, `ran(baseline+active)` -> "ran"; `error:<why>` ->
    "error"; `skipped-missing` / `skipped-active` stay themselves."""
    if status.startswith("ran"):
        return "ran"
    if status.startswith("error:"):
        return "error"
    return status


def _coverage_summary(run_manifest):
    """Cell counts by status family, and whether coverage was complete.

    Complete means every cell ran. A run with no cells at all is NOT
    complete: zero tools having run is otherwise indistinguishable from a
    clean scan, which is the exact failure the coverage table exists to
    stop. `ran_with_scan_errors` counts cells that ran but whose adapter
    reported scan errors of its own (testssl's WARN/FATAL entries): those
    cells ran, so they do not make the run incomplete, but a caller that
    wants to treat them as degraded can see how many there were."""
    cells = run_manifest.get("cells") or []
    by_status = {}
    for c in cells:
        fam = _status_family(c.get("status", ""))
        by_status[fam] = by_status.get(fam, 0) + 1
    complete = bool(cells) and all(c.get("status", "").startswith("ran") for c in cells)
    scan_errors = sum(1 for c in cells
                      if c.get("status", "").startswith("ran") and c.get("errors"))
    return {"cells": len(cells), "by_status": by_status, "complete": complete,
            "ran_with_scan_errors": scan_errors}


def _scan_meta_text(*, date_str, started_at, completed_at, manifest, manifest_path,
                    coverage, findings, confirm, files):
    """The complete `scan-meta.json` text (schema 1). Only what gizmoduck
    actually knows: nothing it was not told (reachability, a module URL) is
    invented."""
    import routine
    s = cmd_summary(findings)
    meta = {
        "schema": SCAN_META_SCHEMA,
        "gizmoduck_version": _gizmoduck_version(),
        "date": date_str,
        "started_at": started_at,
        "completed_at": completed_at,
        "authorized_by": manifest.authorized_by,
        "manifest": manifest_path,
        "confirm_active": bool(confirm),
        "targets": [{"name": t.name, "kind": t.kind, "location": routine._location(t)}
                    for t in manifest.targets],
        "coverage": coverage,
        "findings": {"total": s["total_instances"], "by_severity": s["by_severity"]},
        "files": files,
    }
    return json.dumps(meta, indent=2, sort_keys=True) + "\n"


def _load_run_manifest(path):
    """A routine run's `run-manifest.json`, or ValueError/OSError when the
    file is missing, is not JSON, or has no `cells` list (bad input, never TypeError)."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or not isinstance(data.get("cells"), list):
        raise ValueError(f"{path}: not a run manifest (no 'cells' list)")  # noqa: TRY004
    return data


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


def _is_plain_dir_name(name):
    """True for a target name that is safe as `<out>/<name>/`: one path
    component, never `.` or `..`, no separator (`/`, `\\`), no drive colon,
    no NUL, no leading or trailing whitespace. The name becomes a directory
    that `--replace` later removes, so anything that could resolve outside
    the output directory is refused rather than trusted."""
    return (isinstance(name, str) and name.strip() == name
            and name not in ("", ".", "..")
            and not any(c in name for c in "/\\:\0"))


def _check_manifest_shape(path, yaml):
    """Refuse, as ValueError, a manifest whose types load_manifest does not
    check itself: a top-level list, a non-string `authorized_by`, `targets`
    that is not a list, a target that is not a mapping, a target `name` that
    is missing or not a plain directory name, and a `kind`, location, `tools`
    or `options` of the wrong type. Without this those reach load_manifest or
    run_routine as AttributeError / TypeError - exit 1 and a traceback, and
    for a bad name an output directory already created."""
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if data is None:
        return
    if not isinstance(data, dict):
        raise ValueError(f"the manifest must be a mapping with 'authorized_by' and 'targets', "  # noqa: TRY004
                         f"not a {type(data).__name__}")
    auth = data.get("authorized_by")
    if auth is not None and not isinstance(auth, str):
        raise ValueError(f"'authorized_by' must be a string, not {auth!r}")
    targets = data.get("targets")
    if targets is not None and not isinstance(targets, list):
        raise ValueError(f"'targets' must be a list, not a {type(targets).__name__}")
    for i, raw in enumerate(targets or []):
        if not isinstance(raw, dict):
            raise ValueError(f"targets[{i}] must be a mapping (name, kind, location), "  # noqa: TRY004
                             f"not {raw!r}")
        name = raw.get("name")
        if not _is_plain_dir_name(name):
            raise ValueError(f"targets[{i}] needs a 'name' that is a plain directory name "
                             f"(it becomes <out>/<name>/; no '/', '\\' or ':', no "
                             f"leading or trailing space, not '.' or '..'), "
                             f"not {name!r}")
        if not isinstance(raw.get("kind"), str):
            raise ValueError(f"targets[{i}] 'kind' must be a string, "  # noqa: TRY004
                             f"not {raw.get('kind')!r}")
        for key in ("url", "path", "host"):
            if raw.get(key) is not None and not isinstance(raw[key], str):
                raise ValueError(f"targets[{i}] '{key}' must be a string, not {raw[key]!r}")
        tools = raw.get("tools")
        if tools is not None and not (isinstance(tools, list)
                                      and all(isinstance(t, str) for t in tools)):
            raise ValueError(f"targets[{i}] 'tools' must be a list of tool names, "
                             f"not {tools!r}")
        options = raw.get("options")
        if options is not None and not isinstance(options, dict):
            raise ValueError(f"targets[{i}] 'options' must be a mapping, not {options!r}")


def _earlier_run_dirs(outdir, meta_path):
    """The per-target directories the earlier run in `outdir` owns, read from
    its scan-meta.json, or ValueError naming why that cannot be told.

    "Could not tell" is a refusal, never "remove nothing" or "remove every
    directory": the output directory can be one the operator already owns (a
    repo checkout, `--out .`), and only the names the earlier run recorded
    are its to remove. A named directory that is a symlink is refused too -
    removing through it would reach outside `outdir`."""
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"{meta_path} is not readable JSON ({exc})") from exc
    if not isinstance(meta, dict) or meta.get("schema") != SCAN_META_SCHEMA:
        raise ValueError(f"{meta_path} is not a schema-{SCAN_META_SCHEMA} scan-meta.json")
    targets = meta.get("targets")
    if not isinstance(targets, list):
        raise ValueError(f"{meta_path} has no 'targets' list")  # noqa: TRY004
    dirs = []
    for t in targets:
        name = t.get("name") if isinstance(t, dict) else None
        if not _is_plain_dir_name(name):
            raise ValueError(f"{meta_path} names a target {name!r} that is not a plain "
                             f"directory name")
        child = outdir / name
        if child.is_symlink():
            raise ValueError(f"{child} is a symlink; routine removes only real directories "
                             f"it wrote")
        if child.is_dir():
            dirs.append(child)
    return dirs


def _clear_earlier_run(outdir, meta_path, dirs):
    """`--replace`: remove an earlier run's files and the per-target
    directories `_earlier_run_dirs` resolved, and nothing else.

    scan-meta.json goes FIRST. It is the run's completion record, written
    last; once the files it describes start disappearing it must not survive
    them, or a crash or Ctrl-C before the new run finishes leaves the old
    record (`coverage.complete: true`, its findings total) beside a partial
    new run or nothing at all, and the directory reads as a finished clean
    run. With it gone, an interrupted replace looks exactly like an
    interrupted first run: no scan-meta.json."""
    meta_path.unlink()
    for name in ROUTINE_FILES:
        if (outdir / name).exists():
            (outdir / name).unlink()
    for child in dirs:
        shutil.rmtree(child)


def cmd_routine(manifest_path, out, *, scan_root=None, date=None, replace=False,
                confirm=False, title=None, min_sev=REPORT_DETAIL_FLOOR, registry=None):
    """Run every scanner a manifest resolves, then write the report set.

    Returns 0 when every (target, tool) cell ran, ROUTINE_INCOMPLETE_EXIT (4)
    when every output was written but some cell did not run, and 2 when
    nothing was written: PyYAML missing, a refused manifest, an output
    directory that already holds an earlier run's scan-meta.json without
    `replace`, or a `replace` that cannot tell which directories the earlier
    run owns.

    `routine` needs PyYAML, so it is imported here rather than at module top:
    every other command stays stdlib-only, and a missing PyYAML is a usage
    error naming it rather than a traceback. `registry` is run_routine's own
    test seam, passed straight through - no test runs a real scanner.
    sqlmap's two gates stay routine.py's: `options.sqlmap` makes a target a
    candidate, and only `confirm` (the `--confirm-active` flag, by name) lets
    it fire."""
    try:
        import routine
    except ImportError as exc:
        print(f"routine: needs PyYAML, which this interpreter cannot import ({exc}); install "
              f"it with `{sys.executable} -m pip install pyyaml`", file=sys.stderr)
        return 2

    try:
        _check_manifest_shape(manifest_path, routine.yaml)
        manifest = routine.load_manifest(manifest_path, registry=registry)
    except (routine.AuthorizationError, ValueError, OSError, routine.yaml.YAMLError) as exc:
        print(f"routine: manifest refused: {exc}", file=sys.stderr)
        return 2

    date = date or _utc_now().date()
    date_str = date.isoformat()
    if scan_root:
        outdir = Path(scan_root) / "docs" / "security-scans" / date_str
    else:
        outdir = Path(out)

    meta_path = outdir / "scan-meta.json"
    if meta_path.exists():
        if not replace:
            print(f"routine: {meta_path} already exists - this directory holds an earlier "
                  f"run's evidence; pass --replace to overwrite it, or choose another "
                  f"--out/--date", file=sys.stderr)
            return 2
        try:
            dirs = _earlier_run_dirs(outdir, meta_path)
        except ValueError as exc:
            print(f"routine: --replace refused: cannot tell which directories the earlier run "
                  f"owns - {exc}. Nothing was removed; move {outdir} aside or choose another "
                  f"--out/--date", file=sys.stderr)
            return 2
        _clear_earlier_run(outdir, meta_path, dirs)

    started_at = _utc_now().isoformat()
    run_manifest = routine.run_routine(manifest, outdir, registry=registry,
                                       confirm=confirm).to_dict()

    findings = load(str(outdir / "findings.jsonl"))
    title = title or f"Security scan routine {date_str}"
    md = cmd_report(findings, min_sev, title, run_manifest=run_manifest)
    html = render_html(findings, min_sev, title, run_manifest=run_manifest)
    _atomic_write_text(outdir / "report.md", md)
    _atomic_write_text(outdir / "report.html", html)
    pdf_path = outdir / "report.pdf"
    pdf_ok = html_to_pdf(html, str(pdf_path))
    if not pdf_ok:
        print("routine: no PDF renderer (wkhtmltopdf or weasyprint) - report.pdf not "
              "written; report.html is complete", file=sys.stderr)
        if pdf_path.exists():
            pdf_path.unlink()

    coverage = _coverage_summary(run_manifest)
    files = {"findings": "findings.jsonl", "run_manifest": "run-manifest.json",
             "report_md": "report.md", "report_html": "report.html",
             "report_pdf": "report.pdf" if pdf_ok else None}
    text = _scan_meta_text(date_str=date_str, started_at=started_at,
                           completed_at=_utc_now().isoformat(), manifest=manifest,
                           manifest_path=manifest_path, coverage=coverage,
                           findings=findings, confirm=confirm, files=files)
    _atomic_write_text(meta_path, text)

    safe_print(f"wrote {outdir}")
    for fam, n in sorted(coverage["by_status"].items()):
        safe_print(f"  {fam}: {n}")
    if not coverage["complete"]:
        if coverage["cells"]:
            not_ran = sum(n for fam, n in coverage["by_status"].items() if fam != "ran")
            why = (f"{not_ran} of {coverage['cells']} cells did not run - see the Coverage "
                   f"table in report.md")
        else:
            why = "0 of 0 cells ran - the manifest resolved no scanner for any target"
        safe_print(f"{ROUTINE_MARKER}: {why}; this is not a clean result")
        return ROUTINE_INCOMPLETE_EXIT
    return 0


def cmd_tickets(findings, min_sev):
    """Build the SDP-ready ticket records. Does not create anything and does not gate -
    the gate lives in main(), between this and whatever calls the SDP tools."""
    out = []
    for f in sorted(dedupe(findings), key=lambda f: (-f["severity"], f["name"])):
        if f["severity"] < min_sev:
            continue
        cvss = f["cvss"] or "n/a"
        cves = ", ".join(f["cve"]) if f["cve"] else "none"
        subject = f"[Nuclei {f['template_id']}] {f['name']} ({f['instances']} target(s))"
        lines = [f"Severity: {f['severity_name']} | CVSS: {cvss} | CVE: {cves} | Type: {f['type']}",
                 f"Affected: {', '.join(f['affected'])}"]
        if f["description"]:
            lines.append(f"\nDetail: {f['description'].strip()}")
        if f["remediation"]:
            lines.append(f"\nRemediation: {f['remediation'].strip()}")
        out.append({"ref": f"nuclei:{f['template_id']}", "template_id": f["template_id"],
                    "severity": f["severity_name"], "subject": subject,
                    "description": "\n".join(lines)})
    return out


def cmd_diff(baseline, current, min_sev, title):
    """Findings present in `current` but not in `baseline` (per template_id+location)."""
    def key(f):
        return (f["template_id"], f["matched_at"] or f["host"])
    base = load(baseline)
    cur = load(current)
    base_keys = {key(f) for f in base}
    new = [f for f in cur if key(f) not in base_keys and f["severity"] >= min_sev]
    cur_keys = {key(f) for f in cur}
    resolved = [f for f in base if key(f) not in cur_keys and f["severity"] >= min_sev]

    out = [f"# {title}\n",
           f"**New findings:** {len(new)}  |  **Resolved:** {len(resolved)}\n"]
    if new:
        out.append("## New")
        for f in sorted(new, key=lambda f: -f["severity"]):
            loc = f["matched_at"] or f["host"]
            out.append(f"- **[{f['severity_name']}]** {f['name']} — `{f['template_id']}` @ {loc}")
    else:
        out.append("_No new findings at or above the threshold._")
    if resolved:
        out.append("\n## Resolved (were present before, gone now)")
        for f in sorted(resolved, key=lambda f: -f["severity"]):
            loc = f["matched_at"] or f["host"]
            out.append(f"- **[{f['severity_name']}]** {f['name']} — `{f['template_id']}` @ {loc}")
    return "\n".join(out)


def cmd_doctor():
    """Health check for the local toolchain. Exit non-zero if nuclei is missing."""
    ok = True
    def line(label, val, good=True):
        nonlocal ok
        mark = "OK " if good else "!! "
        if not good:
            ok = False
        safe_print(f"{mark}{label}: {val}")

    exe = find_nuclei()
    if exe:
        try:
            v = subprocess.run([exe, "-version"], capture_output=True, text=True,
                               check=False)
            raw = (v.stderr or v.stdout).strip()
            ver = raw.splitlines()[-1] if raw else "unknown"
        except OSError:
            ver = "unknown"
        line("nuclei", f"{exe} ({ver})")
    else:
        line("nuclei", "NOT FOUND — run bootstrap.sh / bootstrap.ps1", good=False)

    tdir = next((d for d in (os.path.expanduser("~/nuclei-templates"),
                             os.path.expanduser("~/.local/nuclei-templates"))
                 if os.path.isdir(d)), None)
    line("templates", tdir or "not found (run: nuclei -update-templates)", good=bool(tdir))

    line("python", sys.version.split()[0])

    wk = shutil.which("wkhtmltopdf")
    line("wkhtmltopdf (PDF)", wk or "not found — HTML reports still work", good=bool(wk))

    # NVD_API_KEY is optional: dependency-check runs fine without it, just
    # rate-limited by NIST (~5 req/30s vs ~50 with a key) on its first NVD
    # sync. Reported directly with safe_print rather than via line(), so an
    # absent key is a visible gap only — it never flips `ok` and never
    # changes doctor's exit code, matching the convention that only nuclei
    # and its templates can fail this check. Never print the key itself, not
    # even partially — presence/absence only.
    if os.environ.get("NVD_API_KEY"):
        safe_print("OK NVD_API_KEY: set")
    else:
        safe_print("!! NVD_API_KEY: not set — dependency-check's first NVD sync will be "
                    "rate-limited to ~5 req/30s; get a free key at "
                    "https://nvd.nist.gov/developers/request-an-api-key")

    # Every registered adapter, asked whether it can actually run. Driven off
    # the registry rather than a hand-written list here, so a tool added to
    # scanners/ can never be missing from doctor - which is the state that
    # makes "gizmoduck is set up" mean one tool is present and the rest are
    # anybody's guess.
    #
    # These never flip `ok` and never change the exit code, matching the
    # existing convention that only nuclei and its templates fail this check:
    # a routine run skips an unavailable tool per target and records it, so a
    # partial toolchain is a degraded scan rather than a broken install.
    safe_print("")
    safe_print("-- scanners --")
    try:
        import scanners as _scanners
    except ImportError as exc:
        safe_print(f"!! scanner registry unavailable: {exc}")
    else:
        missing = []
        for name in sorted(_scanners.ADAPTERS):
            mod = _scanners.ADAPTERS[name]
            kinds = ",".join(getattr(mod, "KINDS", []) or [])
            try:
                present = bool(mod.is_available())
            except Exception as exc:                      # noqa: BLE001
                safe_print(f"!! {name:<10} [{kinds}] check failed: "
                           f"{type(exc).__name__}: {exc}")
                missing.append(name)
                continue
            if present:
                safe_print(f"OK {name:<10} [{kinds}]")
            else:
                safe_print(f"!! {name:<10} [{kinds}] not installed — "
                           f"targets of this kind will scan without it")
                missing.append(name)
        if missing:
            safe_print("")
            safe_print(f"!! {len(missing)} of {len(_scanners.ADAPTERS)} scanners "
                       f"unavailable: {', '.join(missing)}")
            safe_print("!! Run bootstrap.sh / bootstrap.ps1 to install them. A scan "
                       "missing tools is incomplete, not clean.")

    sys.exit(0 if ok else 1)


def cmd_update():
    exe = find_nuclei()
    if not exe:
        sys.exit("nuclei not found. Run bootstrap.sh (Linux/WSL) or bootstrap.ps1 (Windows) first.")
    failures = []
    for label, flag in (("engine", "-update"), ("templates", "-update-templates")):
        safe_print(f">> updating nuclei {label}...")
        if subprocess.run([exe, flag, "-silent"], check=False).returncode != 0:
            failures.append(label)
    if failures:
        # "done." over a failed update is how a scan ends up running last
        # quarter's templates against this quarter's CVEs.
        sys.exit(f"update failed for: {', '.join(failures)}")
    safe_print("done.")


def main():
    # allow_abbrev=False: argparse's default abbreviation matching would let
    # `--y`/`--ye` satisfy `--yes` below, since no other flag starts with `y` -
    # the gate must be asked for by name, not by whatever prefix happens to be
    # unambiguous today.
    p = argparse.ArgumentParser(description="Gizmoduck: run Nuclei, or the whole scanner routine "
                                            "from a manifest, and process the output.",
                                 allow_abbrev=False)
    p.add_argument("command",
                   choices=["scan", "routine", "summary", "parse", "report", "tickets", "diff",
                            "doctor", "update"])
    p.add_argument("target", nargs="?",
                   help="target/host/URL/file, findings.jsonl, or (routine) the manifest YAML")
    p.add_argument("baseline2", nargs="?", help="for diff: the newer findings.jsonl")
    # No default here. It is resolved per command below, because one default
    # cannot be right for both: `parse`/`summary` want everything, while
    # `report` and `tickets` are documented as High and above - and a `tickets`
    # run that quietly defaulted to Info would open a ticket per informational
    # finding, which is how the queue stops being read.
    p.add_argument("--min-severity", default=None, choices=list(SEV_NUM))
    p.add_argument("--severity", default="", help="nuclei -severity filter for scan (e.g. critical,high)")
    p.add_argument("--extra", default="", help="extra args passed through to nuclei")
    p.add_argument("--title", default="Nuclei Vulnerability Report")
    p.add_argument("--format", default="md", choices=["md", "html", "pdf"])
    p.add_argument("--out", default=None)
    # `tickets` files REAL ServiceDesk Plus tickets. Default is gated: without this
    # flag, `tickets` prints a preview of what it WOULD create and stops - see the
    # gate below. Must be asked for by name (allow_abbrev=False above); there is no
    # way to trip it by accident. Its value must also be the digest the preview
    # printed for THIS batch - a bare "yes I approve" is not enough, because
    # nothing then stopped a rerun from silently picking up a wider batch than
    # what was shown (a missing/different --min-severity, a different findings
    # file). Pass it only after a human has approved the exact batch the preview
    # showed - that can be an attended session (the documented flow: preview,
    # show the user, get one go-ahead, rerun with --yes DIGEST) or a truly
    # unattended run that has its own out-of-band approval; it is never the default.
    p.add_argument("--yes", metavar="DIGEST", default=None,
                   help="tickets: emit ticket records for creation. Value must be the "
                        "digest the preview printed for this exact batch (paste the "
                        "rerun command the preview shows, verbatim) - a missing or "
                        "mismatched digest is refused, never treated as a bare "
                        "go-ahead (default is gated; this flag does not mean "
                        "unattended-only)")
    p.add_argument("--run-manifest", metavar="RUN_MANIFEST_JSON", default=None,
                   help="report only: a routine run's run-manifest.json, so the report "
                        "renders its coverage table (which tools ran, were missing, or failed)")
    p.add_argument("--scan-root", metavar="MODULE_DIR", default=None,
                   help="routine only: write into MODULE_DIR/docs/security-scans/YYYY-MM-DD/ "
                        "instead of --out")
    p.add_argument("--date", metavar="YYYY-MM-DD", default=None,
                   help="routine only, with --scan-root: the dated directory's date "
                        "(default: today, UTC)")
    p.add_argument("--replace", action="store_true",
                   help="routine only: overwrite an output directory that already holds an "
                        "earlier run's scan-meta.json (refused without this)")
    # sqlmap sends attack traffic. Asked for by name (allow_abbrev=False
    # above): a manifest's `options.sqlmap: true` only makes a target a
    # candidate, and without this flag that cell records `skipped-active`.
    p.add_argument("--confirm-active", action="store_true",
                   help="routine only: let sqlmap fire on targets whose manifest entry sets "
                        "options.sqlmap true - asked for by name; without it those cells "
                        "record skipped-active")
    a = p.parse_args()

    # `command` is positional and `target`/`baseline2` are not, so argparse
    # accepts `scan` with no target and the failure surfaces later as a
    # TypeError or a confusing open() error on None. Say what is missing.
    if a.command not in ("doctor", "update") and not a.target:
        needs = {"scan": "target (URL, host, or a file of targets)",
                 "routine": "manifest (a targets YAML with authorized_by and targets)"}
        p.error(f"{a.command} needs a {needs.get(a.command, 'findings.jsonl path')}")
    if a.command == "diff" and not a.baseline2:
        p.error("diff needs two findings files: <baseline.jsonl> <current.jsonl>")
    # `--yes` is a top-level flag (argparse has no per-subcommand parsers here),
    # so nothing stops `gizmoduck.py scan --yes` from parsing - it would just be
    # silently ignored. Say so rather than letting a typo look like it did
    # something, since --yes is the one flag in this tool that changes behaviour.
    if a.yes and a.command != "tickets":
        p.error(f"--yes only applies to the 'tickets' command, not '{a.command}'")
    # The same rule for the routine-only flags and report's --run-manifest:
    # a flag silently ignored by the command it was typed on reads as if it
    # did something - and --confirm-active is the one that fires sqlmap.
    for flag, value in (("--scan-root", a.scan_root), ("--date", a.date),
                        ("--replace", a.replace), ("--confirm-active", a.confirm_active)):
        if value and a.command != "routine":
            p.error(f"{flag} only applies to the 'routine' command, not '{a.command}'")
    if a.run_manifest and a.command != "report":
        p.error(f"--run-manifest only applies to the 'report' command, not '{a.command}'")
    routine_date = None
    if a.command == "routine":
        if a.scan_root and a.out:
            p.error("--scan-root and --out name the output directory two ways; pass one")
        if a.date and not a.scan_root:
            p.error("--date only shapes the --scan-root layout; with --out the directory "
                    "is yours to name")
        if a.date:
            try:
                routine_date = datetime.date.fromisoformat(a.date)
            except ValueError:
                p.error(f"--date must be YYYY-MM-DD, not {a.date!r}")

    # Per command, matching what each command file passes, because one default
    # cannot be right for all of them. `report` and `tickets` are High and above
    # - a `tickets` run defaulting to Info would open a ticket per informational
    # finding. `diff` is Low, because "what is new since last quarter" is the one
    # question where a Medium appearing for the first time is the answer.
    # `summary` and `parse` are the machine-readable dumps and take everything.
    # `report` defaults to medium so the report itemises Critical/High/Medium -
    # see REPORT_DETAIL_FLOOR. `tickets` stays at high on purpose: a Medium is
    # worth reading in a report without being worth a ticket of its own.
    _FLOORS = {"report": "medium", "routine": "medium", "tickets": "high", "diff": "low"}
    min_sev = SEV_NUM[a.min_severity or _FLOORS.get(a.command, "info")]

    if a.command == "doctor":
        cmd_doctor()
        return
    if a.command == "update":
        cmd_update()
        return
    if a.command == "scan":
        cmd_scan(a.target, a.out or "findings.jsonl", a.severity, a.extra)
        return
    if a.command == "diff":
        title = a.title if a.title != "Nuclei Vulnerability Report" else "Scan Diff"
        safe_print(cmd_diff(a.target, a.baseline2, min_sev, title))
        return
    if a.command == "routine":
        title = a.title if a.title != "Nuclei Vulnerability Report" else None
        sys.exit(cmd_routine(a.target, a.out or _ROUTINE_DEFAULT_OUT, scan_root=a.scan_root,
                             date=routine_date, replace=a.replace, confirm=a.confirm_active,
                             title=title, min_sev=min_sev))

    findings = load(a.target)

    if a.command == "summary":
        safe_print(json.dumps(cmd_summary(findings), indent=2))
    elif a.command == "parse":
        safe_print(json.dumps([f for f in findings if f["severity"] >= min_sev], indent=2))
    elif a.command == "tickets":
        records = cmd_tickets(findings, min_sev)
        # The gate: `tickets` files REAL SDP tickets, and the caller (a skill
        # following prose) previously had no confirmation step at all. Without
        # --yes, print a human-readable preview - severity + subject, one line
        # each - and stop *without emitting the JSON records a caller would use
        # to actually create anything*. That JSON is what downstream tooling
        # parses, so withholding it is what makes the gate real rather than
        # advisory. --yes must be asked for by name; there is no default that
        # skips this.
        #
        # A name alone is not enough either: nothing bound an earlier bare
        # --yes to the batch a preview actually showed, so a caller who saw a
        # narrow preview (say --min-severity critical, one ticket) and then
        # reran with a wider or missing --min-severity got every record at the
        # tool's default floor instead - four tickets approved as one. The
        # digest closes that: it is computed over the exact record set the
        # preview shows, and --yes must carry the matching value or the rerun
        # is refused, however plausible it looks.
        if records:
            digest = _records_digest(records)
            if a.yes is None:
                safe_print(f"# {len(records)} ticket(s) would be created - confirm with "
                           f"the user before creating any, then rerun with the exact "
                           f"command below (only this batch's digest is accepted):")
                for r in records:
                    safe_print(f"  [{r['severity']}] {r['subject']}")
                rerun = " ".join([sys.executable, *sys.argv, "--yes", digest])
                safe_print(f"  {rerun}")
                safe_print("GIZMODUCK_CONFIRMATION_REQUIRED: no ticket records emitted. "
                           "Get explicit go-ahead for this batch, then rerun the command "
                           "above verbatim.")
                sys.exit(3)
            if a.yes != digest:
                safe_print(f"GIZMODUCK_APPROVAL_MISMATCH: the supplied --yes digest does "
                           f"not match this batch ({len(records)} record(s)). A digest is "
                           f"only valid for the exact findings file and --min-severity it "
                           f"was previewed with - re-run without --yes to see the current "
                           f"batch and its digest.")
                sys.exit(3)
        safe_print(json.dumps(records, indent=2))
    elif a.command == "report":
        run_manifest = None
        if a.run_manifest:
            try:
                run_manifest = _load_run_manifest(a.run_manifest)
            except (OSError, ValueError) as exc:
                p.error(f"--run-manifest: {exc}")
        if a.format == "md":
            md = cmd_report(findings, min_sev, a.title, run_manifest=run_manifest)
            if a.out:
                write_text(a.out, md)
                safe_print(f"wrote {a.out}")
            else:
                safe_print(md)
        elif a.format == "html":
            out = a.out or "nuclei-report.html"
            write_text(out, render_html(findings, min_sev, a.title, run_manifest=run_manifest))
            safe_print(f"wrote {out}")
        elif a.format == "pdf":
            out = a.out or "nuclei-report.pdf"
            doc = render_html(findings, min_sev, a.title, run_manifest=run_manifest)
            if html_to_pdf(doc, out):
                safe_print(f"wrote {out}")
            else:
                fb = os.path.splitext(out)[0] + ".html"
                write_text(fb, doc)
                print(f"No PDF engine found. Wrote {fb} instead — install wkhtmltopdf "
                      f"or open the HTML and Print to PDF.", file=sys.stderr)
                sys.exit(2)


if __name__ == "__main__":
    main()
