#!/usr/bin/env python3
"""gizmoduck - run Nuclei and turn its JSONL output into a report or SDP tickets.
Cross-platform (Windows + Linux/WSL), stdlib only.

Only scan assets you own or have explicit written permission to test.

Usage:
  gizmoduck.py scan    <target|targets.txt> [--severity critical,high,medium] [--out findings.jsonl] [--extra "..."]
  gizmoduck.py summary <findings.jsonl>
  gizmoduck.py parse   <findings.jsonl> [--min-severity info|low|medium|high|critical]
  gizmoduck.py report  <findings.jsonl> [--min-severity medium] [--format md|html|pdf] [--out FILE] [--title "..."]
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
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict

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


def find_nuclei():
    for name in ("nuclei", "nuclei.exe"):
        p = shutil.which(name)
        if p:
            return p
    # common go install location
    cand = os.path.expanduser("~/go/bin/nuclei")
    return cand if os.path.exists(cand) else None


def cmd_scan(target, out, severity, extra, source=None, with_zap=False,
             with_checkov=False, semgrep_config="p/security-audit"):
    """Run the scanner suite and write ONE findings file.

    Nuclei runs here because it owns the failed-scan-is-not-a-clean-scan rule
    below. Every other tool runs through scanners.run_suite and is normalised
    into Nuclei's record shape, so load()/dedupe()/cmd_report merge the lot
    into a single report at the existing Medium-and-above floor without
    growing a per-tool branch.

    A tool that is missing or failed is reported as such on stderr and in the
    returned status list. It is never allowed to look like a clean result -
    four silent failures next to one clean Nuclei run would read as a clean
    bill of health, which is the exact failure the Nuclei guard below exists
    to prevent."""
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
    # Nuclei is in. Now the rest of the suite. Imported by path rather than by
    # name: gizmoduck.py is invoked as an absolute path from other directories,
    # so the script's own directory is not reliably on sys.path.
    _here = os.path.dirname(os.path.abspath(__file__))
    if _here not in sys.path:
        sys.path.insert(0, _here)
    from scanners import run_suite

    extra_findings, runs = run_suite(
        target, source=source, with_zap=with_zap, with_checkov=with_checkov,
        semgrep_config=semgrep_config)

    safe_print(f"  nuclei        ok       {len(lines)} finding(s)")
    for r in runs:
        note = f"  - {r.detail}" if r.detail else ""
        safe_print(f"  {r.tool:<13} {r.status:<8} {len(r.findings)} finding(s){note}")

    failed = [r.tool for r in runs if r.status in ("missing", "failed")]
    if failed:
        safe_print(f"!! {len(failed)} tool(s) did not run: {', '.join(failed)}. "
                   f"This scan is INCOMPLETE - treat a clean report accordingly.")

    with open(out, "w", encoding="utf-8") as fh:
        for ln in lines:
            fh.write(ln + "\n")
        for rec in extra_findings:
            fh.write(json.dumps(rec) + "\n")

    total = len(lines) + len(extra_findings)
    safe_print(f"wrote {total} findings to {out}")
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


def load(path):
    findings = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
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
        g = groups.setdefault(f["template_id"], {**f, "affected": [], "raw_count": 0})
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


def cmd_report(findings, min_sev, title):
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


def render_html(findings, min_sev, title):
    """Presentation lives in report_template.py; this stays the data prep.

    dedupe() and cmd_summary() own what a finding *is*; the template module owns
    only how it looks, and is handed the severity vocabulary rather than
    redefining it.
    """
    uniq = sorted(dedupe(findings), key=lambda f: (-f["severity"], f["name"]))
    return _template_module().render_report(
        uniq=uniq,
        summary=cmd_summary(findings),
        min_sev=min_sev,
        title=title,
        sev_name=SEV_NAME,
        order=ORDER,
        findings=findings,
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

    # The rest of the suite. Each is reported individually: a scan is only as
    # complete as the tools that actually ran, and "gizmoduck is set up" has to
    # mean all of them, not just the one that gave this plugin its name.
    safe_print("")
    safe_print("-- scanner suite --")
    for label, names, why in (
        ("sslyze (TLS)", ("sslyze",),
         "TLS protocol/cert posture; nuclei only fingerprints"),
        ("trivy (deps, secrets, IaC)", ("trivy", "trivy.exe"),
         "dependency CVEs, committed secrets, Terraform misconfiguration"),
        ("semgrep (SAST)", ("semgrep", "semgrep.exe"),
         "source analysis; the only tool here that sees a missing auth gate"),
    ):
        p = shutil.which(names[0]) or (shutil.which(names[1]) if len(names) > 1 else None)
        if not p and names[0] == "sslyze":
            try:
                import sslyze  # noqa: F401
                p = f"{sys.executable} -m sslyze"
            except ImportError:
                p = None
        line(label, p or f"NOT FOUND — {why}", good=bool(p))

    safe_print("")
    safe_print("-- optional, opt-in --")
    for label, names, flag in (
        ("OWASP ZAP", ("zap.sh", "zap.bat", "zap"), "--with-zap"),
        ("checkov", ("checkov", "checkov.exe", "checkov.cmd"), "--with-checkov"),
    ):
        p = next((shutil.which(n) for n in names if shutil.which(n)), None)
        # Optional tools never fail the doctor: absent is a valid state for them.
        safe_print(f"{'OK ' if p else '-- '}{label}: "
                   f"{p or f'not installed (enable with {flag} once present)'}")

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
    p = argparse.ArgumentParser(description="Gizmoduck: run Nuclei and process its output.",
                                 allow_abbrev=False)
    p.add_argument("command",
                   choices=["scan", "sweep", "summary", "parse", "report", "tickets",
                            "diff", "doctor", "update"])
    p.add_argument("target", nargs="?", help="target/host/URL/file, or findings.jsonl")
    p.add_argument("baseline2", nargs="?", help="for diff: the newer findings.jsonl")
    # No default here. It is resolved per command below, because one default
    # cannot be right for both: `parse`/`summary` want everything, while
    # `report` and `tickets` are documented as High and above - and a `tickets`
    # run that quietly defaulted to Info would open a ticket per informational
    # finding, which is how the queue stops being read.
    p.add_argument("--min-severity", default=None, choices=list(SEV_NUM))
    p.add_argument("--severity", default="", help="nuclei -severity filter for scan (e.g. critical,high)")
    p.add_argument("--extra", default="", help="extra args passed through to nuclei")
    # The source tools (trivy, semgrep, checkov) need a directory, not a URL.
    # Without this they are reported as SKIPPED rather than silently omitted -
    # a scan missing three of five tools must not read as a clean scan.
    p.add_argument("--source", default=None, metavar="DIR",
                   help="scan: source tree for trivy/semgrep/checkov. Omit and those "
                        "tools report as skipped, not clean.")
    p.add_argument("--with-zap", action="store_true",
                   help="scan: also run OWASP ZAP (crawler-driven DAST; minutes per "
                        "target). Off by default.")
    p.add_argument("--with-checkov", action="store_true",
                   help="scan: also run checkov for IaC breadth. Off by default - "
                        "checkov OSS returns no severity, so its findings are floored "
                        "at Low and will not appear in a Medium-and-above report.")
    p.add_argument("--semgrep-config", default="p/security-audit",
                   help="scan: semgrep ruleset (default: p/security-audit)")
    p.add_argument("--declaration", default="public-endpoint.md", metavar="FILE",
                   help="sweep: per-module file declaring the endpoint "
                        "(default: public-endpoint.md)")
    p.add_argument("--scan-dir", default=os.path.join("docs", "security-scans"),
                   metavar="DIR",
                   help="sweep: path under each module for results "
                        "(default: docs/security-scans)")
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
    a = p.parse_args()

    # `command` is positional and `target`/`baseline2` are not, so argparse
    # accepts `scan` with no target and the failure surfaces later as a
    # TypeError or a confusing open() error on None. Say what is missing.
    if a.command not in ("doctor", "update") and not a.target:
        p.error(f"{a.command} needs a "
                f"{'target (URL, host, or a file of targets)' if a.command == 'scan' else 'findings.jsonl path'}")
    if a.command == "diff" and not a.baseline2:
        p.error("diff needs two findings files: <baseline.jsonl> <current.jsonl>")
    # `--yes` is a top-level flag (argparse has no per-subcommand parsers here),
    # so nothing stops `gizmoduck.py scan --yes` from parsing - it would just be
    # silently ignored. Say so rather than letting a typo look like it did
    # something, since --yes is the one flag in this tool that changes behaviour.
    if a.yes and a.command != "tickets":
        p.error(f"--yes only applies to the 'tickets' command, not '{a.command}'")

    # Per command, matching what each command file passes, because one default
    # cannot be right for all of them. `report` and `tickets` are High and above
    # - a `tickets` run defaulting to Info would open a ticket per informational
    # finding. `diff` is Low, because "what is new since last quarter" is the one
    # question where a Medium appearing for the first time is the answer.
    # `summary` and `parse` are the machine-readable dumps and take everything.
    # `report` defaults to medium so the report itemises Critical/High/Medium -
    # see REPORT_DETAIL_FLOOR. `tickets` stays at high on purpose: a Medium is
    # worth reading in a report without being worth a ticket of its own.
    # `sweep` is listed explicitly even though detail_floor() would clamp an
    # unlisted command's `info` default up to Medium anyway: a reader checking
    # what a repo-wide sweep reports should find the answer here rather than
    # having to trace it through the clamp.
    _FLOORS = {"report": "medium", "sweep": "medium", "tickets": "high",
               "diff": "low"}
    min_sev = SEV_NUM[a.min_severity or _FLOORS.get(a.command, "info")]

    if a.command == "doctor":
        cmd_doctor()
        return
    if a.command == "update":
        cmd_update()
        return
    if a.command == "scan":
        cmd_scan(a.target, a.out or "findings.jsonl", a.severity, a.extra,
                 source=a.source, with_zap=a.with_zap, with_checkov=a.with_checkov,
                 semgrep_config=a.semgrep_config)
        return
    if a.command == "sweep":
        _here = os.path.dirname(os.path.abspath(__file__))
        if _here not in sys.path:
            sys.path.insert(0, _here)
        import sweep as _sweep
        results = _sweep.run(a.target, with_zap=a.with_zap,
                             with_checkov=a.with_checkov,
                             declaration=a.declaration, scan_dir=a.scan_dir,
                             semgrep_config=a.semgrep_config, extra=a.extra,
                             severity=a.severity, min_sev=min_sev)
        # A sweep where some module failed to scan must not exit 0: a caller
        # that treats exit 0 as "the estate is clean" would be wrong, and the
        # per-module reports it is about to read are incomplete, not clean.
        sys.exit(1 if any(r.get("note") for r in results) else 0)
    if a.command == "diff":
        title = a.title if a.title != "Nuclei Vulnerability Report" else "Scan Diff"
        safe_print(cmd_diff(a.target, a.baseline2, min_sev, title))
        return

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
        if a.format == "md":
            md = cmd_report(findings, min_sev, a.title)
            if a.out:
                write_text(a.out, md)
                safe_print(f"wrote {a.out}")
            else:
                safe_print(md)
        elif a.format == "html":
            out = a.out or "nuclei-report.html"
            write_text(out, render_html(findings, min_sev, a.title))
            safe_print(f"wrote {out}")
        elif a.format == "pdf":
            out = a.out or "nuclei-report.pdf"
            doc = render_html(findings, min_sev, a.title)
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
