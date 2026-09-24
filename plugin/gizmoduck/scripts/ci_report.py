"""ci_report.py - `security-scan-report.md`, written after every endpoint scan.

`build(...)` joins four things the endpoint stage already leaves in its output
directory with the endpoints inventory (ci_inventory.build):

  targets.json        what the prod-refusal guard allowed (name -> URL)
  run-manifest.json   one coverage cell per target and tool
  findings.jsonl      normalised findings, each carrying its target's name
  a baseline          the previous trusted run's findings, when one exists

and `render(...)` turns the result into Markdown. Both are pure: the scan date,
commit and artifact links are arguments, so the same inputs give the same bytes.

Attribution. An inventory endpoint is matched to a scanned target when the
target's URL equals the endpoint's staging scan URL; failing that, when the
endpoint's staging URL is undetermined and exactly one target has the same
path. A target no endpoint claims (the bare staging base URL, say) is listed
under "Other scanned targets", so every finding is counted exactly once.

Status per endpoint:
  scanned      a target covers it and every coverage cell for that target ran
  partial      a target covers it and some cell did not run (named)
  UNVERIFIED   nothing scanned it - no target matched, or no cell ran. Zero
               findings on an UNVERIFIED row is not a clean result.

New since baseline uses ci_gate's finding identity (template id + matched
URL). With no baseline, nothing can be called new, and the report says so
rather than printing zeros.

Only counts, statuses and redacted URLs are written - never a finding's body,
request or response - so the file is safe to commit.
"""
import json
import os
import urllib.parse

import ci_gate
import ci_guard

DEFAULT_OUTPUT = "security-scan-report.md"
ARTIFACT_FILES = ("report.html", "report.pdf", "report.md", "diff.md", "findings.jsonl", "gate.json")
_SEV = {4: "critical", 3: "high", 2: "medium"}


def _norm(url):
    return ci_guard.redact_url(str(url or "")).rstrip("/")


def _path_of(url):
    try:
        return urllib.parse.urlsplit(url).path.rstrip("/") or "/"
    except ValueError:
        return ""


def load_jsonl(path):
    """Findings from a JSONL file, or None when the file is absent."""
    if not path or not os.path.exists(path):
        return None
    return ci_gate.load_findings(path)


def load_json(path):
    if not path or not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _counts(findings, base_keys):
    c = {"critical": 0, "high": 0, "medium": 0, "new": 0 if base_keys is not None else None}
    for f in findings:
        label = _SEV.get(f.severity)
        if label:
            c[label] += 1
        if base_keys is not None and f.key not in base_keys and f.severity >= 2:
            c["new"] += 1
    return c


def build(modules, targets_doc, manifest, findings, baseline):
    """The report as data. `findings` None means the scan left no findings
    file (every target UNVERIFIED); `baseline` None means no baseline."""
    targets = [t for t in (targets_doc or {}).get("allowed") or [] if isinstance(t, dict) and t.get("name")]
    by_name = {t["name"]: _norm(t.get("url")) for t in targets}
    cells = [c for c in (manifest or {}).get("cells") or [] if isinstance(c, dict)]
    base_keys = {f.key for f in baseline} if baseline is not None else None

    per_target = {name: [] for name in by_name}
    unattributed = []
    for f in findings or []:
        name = f.record.get("target")
        if name not in per_target:
            where = _norm(f.record.get("matched_at") or f.record.get("matched-at") or f.record.get("host"))
            hits = sorted((u for u in by_name.values() if u and (where == u or where.startswith(u + "/"))),
                          key=len, reverse=True)
            name = next((n for n, u in sorted(by_name.items()) if hits and u == hits[0]), None)
        (per_target[name] if name in per_target else unattributed).append(f)

    def coverage(name):
        mine = [c for c in cells if c.get("target") == name]
        ran = [c for c in mine if ci_gate._cell_complete(c)]
        missing = sorted(f"{c.get('tool')}={c.get('status')}" for c in mine if not ci_gate._cell_complete(c))
        if findings is None or not ran:
            return "UNVERIFIED", missing or ["no coverage cell ran"]
        return ("scanned", []) if not missing else ("partial", missing)

    claimed = set()
    out_modules = []
    for m in modules:
        rows = []
        for r in m["rows"]:
            scan_url = _norm(r.get("scan_url"))
            name = next((n for n, u in sorted(by_name.items()) if scan_url and u == scan_url), None)
            if name is None and r["staging_url"] == "undetermined" and r["endpoint"].startswith("/"):
                path = r["endpoint"].split("{", 1)[0].rstrip("/") or "/"
                same = sorted(n for n, u in by_name.items() if _path_of(u) == path)
                name = same[0] if len(same) == 1 else None
            if name is None:
                rows.append({"endpoint": r, "target": None, "status": "UNVERIFIED",
                             "missing": ["no scanned target matches this endpoint"], "counts": None})
                continue
            claimed.add(name)
            status, missing = coverage(name)
            rows.append({"endpoint": r, "target": name, "status": status, "missing": missing,
                         "counts": _counts(per_target[name], base_keys) if status != "UNVERIFIED" else None})
        out_modules.append({"path": m["path"], "mode": m["mode"], "rows": rows})
    others = []
    for name in sorted(set(by_name) - claimed):
        status, missing = coverage(name)
        others.append({"target": name, "url": by_name[name], "status": status, "missing": missing,
                       "counts": _counts(per_target[name], base_keys) if status != "UNVERIFIED" else None})
    every = [f for fs in per_target.values() for f in fs] + unattributed
    return {"modules": out_modules, "others": others, "totals": _counts(every, base_keys),
            "unattributed": len(unattributed), "baseline": base_keys is not None,
            "findings_present": findings is not None, "targets": len(by_name)}


def _cell(text):
    return str(text).replace("\r", " ").replace("\n", " ").replace("|", "\\|")


def _n(counts, key):
    if counts is None:
        return "-"
    v = counts[key]
    return "n/a" if v is None else str(v)


def render(report, meta):
    """`meta`: date, commit, and optionally branch, tier, run_url, artifacts
    (the artifact file names present)."""
    t = report["totals"]
    unverified = sum(1 for m in report["modules"] for r in m["rows"] if r["status"] == "UNVERIFIED") + \
        sum(1 for o in report["others"] if o["status"] == "UNVERIFIED")
    lines = [
        "# Security scan report",
        "",
        "<!-- gizmoduck security-scan-report. Generated - do not edit. -->",
        "",
        "> **Generated by gizmoduck after an endpoint scan - do not edit.** Counts only; the full",
        "> findings are in the run's artifacts. UNVERIFIED means nothing scanned that endpoint, so",
        "> its zero findings are not a clean result.",
        "",
        f"- Scan date: {_cell(meta['date'])}",
        f"- Commit: `{_cell(meta['commit'])}`",
    ]
    if meta.get("branch"):
        lines.append(f"- Branch: `{_cell(meta['branch'])}`")
    if meta.get("tier"):
        lines.append(f"- Tier: {_cell(meta['tier'])}")
    lines.append("- Baseline: " + ("present - \"new\" counts findings (Medium and above) absent from it"
                                   if report["baseline"] else
                                   "none - nothing can be called new (n/a below)"))
    arts = [a for a in meta.get("artifacts") or [] if a in ARTIFACT_FILES]
    run_url = meta.get("run_url")
    if run_url:
        names = ", ".join(f"`{a}`" for a in arts) or "the scan output"
        lines.append(f"- Full reports: {names} in [this run's artifacts]({_cell(ci_guard.redact_url(run_url))})")
    elif arts:
        lines.append("- Full reports: " + ", ".join(f"`{a}`" for a in arts) + " (run artifacts)")
    else:
        lines.append("- Full reports: none were produced by this run")
    if not report["findings_present"]:
        lines += ["", "**UNVERIFIED:** the scan produced no findings file - every endpoint below is "
                      "unscanned, whatever its counts would have been."]
    lines += [
        "",
        "## Summary",
        "",
        "| Critical | High | Medium | New since baseline | Targets scanned | UNVERIFIED rows |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| {t['critical']} | {t['high']} | {t['medium']} | {_n(t, 'new')} | {report['targets']} | {unverified} |",
        "",
    ]
    if report["unattributed"]:
        lines += [f"{report['unattributed']} finding(s) matched no scanned target; they are in the totals above "
                  "and in the full report.", ""]
    for m in report["modules"]:
        lines += [f"## {m['path']}", ""]
        if not m["rows"]:
            lines += ["**UNVERIFIED** - the inventory lists no endpoint for this module.", ""]
            continue
        lines += ["| Endpoint | Status | Critical | High | Medium | New |", "| --- | --- | ---: | ---: | ---: | ---: |"]
        for r in m["rows"]:
            e = r["endpoint"]
            what = (e["method"] + " " if e["method"] else "") + e["endpoint"]
            status = r["status"] + (f" ({'; '.join(r['missing'])})" if r["missing"] else "")
            c = r["counts"]
            lines.append(f"| `{_cell(what)}` | {_cell(status)} | {_n(c, 'critical')} | {_n(c, 'high')} | "
                         f"{_n(c, 'medium')} | {_n(c, 'new')} |")
        lines.append("")
    if report["others"]:
        lines += ["## Other scanned targets", "",
                  "Targets the guard allowed that no inventory endpoint claims (the staging base URL, say).", "",
                  "| Target | URL | Status | Critical | High | Medium | New |",
                  "| --- | --- | --- | ---: | ---: | ---: | ---: |"]
        for o in report["others"]:
            status = o["status"] + (f" ({'; '.join(o['missing'])})" if o["missing"] else "")
            c = o["counts"]
            lines.append(f"| `{_cell(o['target'])}` | `{_cell(o['url'])}` | {_cell(status)} | {_n(c, 'critical')} | "
                         f"{_n(c, 'high')} | {_n(c, 'medium')} | {_n(c, 'new')} |")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"
