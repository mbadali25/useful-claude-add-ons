#!/usr/bin/env python3
"""gizmoduck - run Nuclei and turn its JSONL output into a report or SDP tickets.
Cross-platform (Windows + Linux/WSL), stdlib only.

Only scan assets you own or have explicit written permission to test.

Usage:
  gizmoduck.py scan    <target|targets.txt> [--severity critical,high,medium] [--out findings.jsonl] [--extra "..."]
  gizmoduck.py summary <findings.jsonl>
  gizmoduck.py parse   <findings.jsonl> [--min-severity info|low|medium|high|critical]
  gizmoduck.py report  <findings.jsonl> [--min-severity high] [--format md|html|pdf] [--out FILE] [--title "..."]
  gizmoduck.py tickets <findings.jsonl> [--min-severity high]
  gizmoduck.py diff    <baseline.jsonl> <current.jsonl> [--min-severity high]   # what's new since last scan
  gizmoduck.py update                                                            # update nuclei + templates
  gizmoduck.py doctor                                                            # check the local toolchain

A "target" is a URL (https://site) or a host/IP; a targets file has one per line.
"""
import argparse
import html
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
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode not in (0, 1):  # nuclei exits 1 when findings exist in some modes
        # Do NOT write an output file here. A scan that died - bad target,
        # missing templates, no network - produces no stdout, and writing that
        # as an empty findings file is indistinguishable from a clean result:
        # the report says nothing was found, the diff says nothing is new, and
        # the baseline the next scan compares against is a lie. Fail loudly.
        sys.stderr.write(proc.stderr)
        sys.exit(f"nuclei exited {proc.returncode}; no findings file written "
                 f"(a failed scan is not a clean scan)")
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip().startswith("{")]
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + ("\n" if lines else ""))
    print(f"wrote {len(lines)} findings to {out}")
    return out


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
        g = groups.setdefault(f["template_id"], {**f, "affected": []})
        g["affected"].append(f["matched_at"] or f["host"])
    for g in groups.values():
        g["affected"] = sorted(set(a for a in g["affected"] if a))
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


def cmd_report(findings, min_sev, title):
    uniq = sorted(dedupe(findings), key=lambda f: (-f["severity"], f["name"]))
    s = cmd_summary(findings)
    out = [f"# {title}\n", f"**Hosts with findings:** {s['hosts']}  ",
           f"**Total finding instances:** {s['total_instances']}\n",
           "| Severity | Count |", "|---|---|"]
    out += [f"| {SEV_NAME[x]} | {s['by_severity'][SEV_NAME[x]]} |" for x in ORDER]
    out.append("")
    shown = [f for f in uniq if f["severity"] >= min_sev]
    if not shown:
        out.append(f"_No findings at or above {SEV_NAME[min_sev]}._")
        return "\n".join(out)
    cur = None
    for f in shown:
        if f["severity"] != cur:
            cur = f["severity"]
            out.append(f"\n## {SEV_NAME[cur]}\n")
        cvss = f["cvss"] or "n/a"
        cves = ", ".join(f["cve"]) if f["cve"] else "—"
        out.append(f"### {f['name']}  \n")
        out.append(f"- **Template:** {f['template_id']}  |  **CVSS:** {cvss}  |  **CVE:** {cves}  |  **Type:** {f['type']}")
        out.append(f"- **Affected ({f['instances']}):** {', '.join(f['affected'])}")
        if f["description"]:
            out.append(f"- **Detail:** {f['description'].strip()}")
        if f["remediation"]:
            out.append(f"- **Remediation:** {f['remediation'].strip()}")
        out.append("")
    return "\n".join(out)


def render_html(findings, min_sev, title):
    uniq = sorted(dedupe(findings), key=lambda f: (-f["severity"], f["name"]))
    s = cmd_summary(findings)
    e = html.escape
    rows = "".join(f"<tr><td style='color:{SEV_COLOR[x]};font-weight:600'>{SEV_NAME[x]}</td>"
                   f"<td>{s['by_severity'][SEV_NAME[x]]}</td></tr>" for x in ORDER)
    body = [f"""<!doctype html><html><head><meta charset="utf-8"><title>{e(title)}</title><style>
body{{font:14px/1.5 -apple-system,Segoe UI,Arial,sans-serif;color:#1a1a1a;max-width:900px;margin:2rem auto;padding:0 1rem}}
h1{{border-bottom:2px solid #ddd;padding-bottom:.3rem}} table{{border-collapse:collapse;margin:1rem 0}}
td,th{{border:1px solid #ddd;padding:.35rem .7rem;text-align:left}}
.finding{{border-left:4px solid #ccc;padding:.4rem 0 .4rem 1rem;margin:1rem 0}}
.meta{{color:#555;font-size:13px}} .rem{{background:#f6f8fa;padding:.5rem .8rem;border-radius:4px}}
</style></head><body><h1>{e(title)}</h1>
<p><b>Hosts with findings:</b> {s['hosts']} &nbsp;|&nbsp; <b>Total instances:</b> {s['total_instances']}</p>
<table><tr><th>Severity</th><th>Count</th></tr>{rows}</table>"""]
    shown = [f for f in uniq if f["severity"] >= min_sev]
    if not shown:
        body.append(f"<p><i>No findings at or above {SEV_NAME[min_sev]}.</i></p>")
    cur = None
    for f in shown:
        if f["severity"] != cur:
            cur = f["severity"]
            body.append(f"<h2 style='color:{SEV_COLOR[cur]}'>{SEV_NAME[cur]}</h2>")
        cvss = e(str(f["cvss"] or "n/a"))
        cves = e(", ".join(f["cve"]) if f["cve"] else "—")
        rem = f"<div class='rem'><b>Remediation:</b> {e(f['remediation'].strip())}</div>" if f["remediation"] else ""
        det = f"<p>{e(f['description'].strip())}</p>" if f["description"] else ""
        body.append(f"<div class='finding' style='border-left-color:{SEV_COLOR[f['severity']]}'>"
                    f"<h3>{e(f['name'])}</h3><p class='meta'>Template {e(f['template_id'])} &nbsp;|&nbsp; "
                    f"CVSS {cvss} &nbsp;|&nbsp; {cves} &nbsp;|&nbsp; {f['instances']} affected</p>"
                    f"<p class='meta'>{e(', '.join(f['affected']))}</p>{det}{rem}</div>")
    body.append("</body></html>")
    return "\n".join(body)


def html_to_pdf(html_str, out_path):
    wk = shutil.which("wkhtmltopdf")
    if wk:
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as t:
            t.write(html_str)
            tmp = t.name
        try:
            # check=False, not check=True: a wkhtmltopdf that is installed but
            # fails (a broken build, a sandboxed temp dir) would otherwise raise
            # past the WeasyPrint fallback below and take the whole report
            # command with it, when the fallback would have produced the file.
            if subprocess.run([wk, "-q", "--enable-local-file-access", tmp, out_path],
                              check=False).returncode == 0:
                return True
        finally:
            os.unlink(tmp)
    try:
        from weasyprint import HTML  # type: ignore
        HTML(string=html_str).write_pdf(out_path)
        return True
    except Exception:
        return False


def cmd_tickets(findings, min_sev):
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
        print(f"{mark}{label}: {val}")

    exe = find_nuclei()
    if exe:
        try:
            v = subprocess.run([exe, "-version"], capture_output=True, text=True)
            ver = (v.stderr or v.stdout).strip().splitlines()[-1] if (v.stderr or v.stdout) else "unknown"
        except Exception:
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

    sys.exit(0 if ok else 1)


def cmd_update():
    exe = find_nuclei()
    if not exe:
        sys.exit("nuclei not found. Run bootstrap.sh (Linux/WSL) or bootstrap.ps1 (Windows) first.")
    failures = []
    for label, flag in (("engine", "-update"), ("templates", "-update-templates")):
        print(f">> updating nuclei {label}...")
        if subprocess.run([exe, flag, "-silent"], check=False).returncode != 0:
            failures.append(label)
    if failures:
        # "done." over a failed update is how a scan ends up running last
        # quarter's templates against this quarter's CVEs.
        sys.exit(f"update failed for: {', '.join(failures)}")
    print("done.")


def main():
    p = argparse.ArgumentParser(description="Gizmoduck: run Nuclei and process its output.")
    p.add_argument("command",
                   choices=["scan", "summary", "parse", "report", "tickets", "diff", "doctor", "update"])
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
    p.add_argument("--title", default="Nuclei Vulnerability Report")
    p.add_argument("--format", default="md", choices=["md", "html", "pdf"])
    p.add_argument("--out", default=None)
    a = p.parse_args()

    # `command` is positional and `target`/`baseline2` are not, so argparse
    # accepts `scan` with no target and the failure surfaces later as a
    # TypeError or a confusing open() error on None. Say what is missing.
    if a.command not in ("doctor", "update") and not a.target:
        p.error(f"{a.command} needs a "
                f"{'target (URL, host, or a file of targets)' if a.command == 'scan' else 'findings.jsonl path'}")
    if a.command == "diff" and not a.baseline2:
        p.error("diff needs two findings files: <baseline.jsonl> <current.jsonl>")

    # High and above for anything a person reads or acts on; everything for the
    # two machine-readable dumps.
    min_sev = SEV_NUM[a.min_severity or
                      ("info" if a.command in ("summary", "parse") else "high")]

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
        print(cmd_diff(a.target, a.baseline2, min_sev, title))
        return

    findings = load(a.target)

    if a.command == "summary":
        print(json.dumps(cmd_summary(findings), indent=2))
    elif a.command == "parse":
        print(json.dumps([f for f in findings if f["severity"] >= min_sev], indent=2))
    elif a.command == "tickets":
        print(json.dumps(cmd_tickets(findings, min_sev), indent=2))
    elif a.command == "report":
        if a.format == "md":
            md = cmd_report(findings, min_sev, a.title)
            (open(a.out, "w", encoding="utf-8").write(md) and print(f"wrote {a.out}")) if a.out else print(md)
        elif a.format == "html":
            out = a.out or "nuclei-report.html"
            open(out, "w", encoding="utf-8").write(render_html(findings, min_sev, a.title))
            print(f"wrote {out}")
        elif a.format == "pdf":
            out = a.out or "nuclei-report.pdf"
            doc = render_html(findings, min_sev, a.title)
            if html_to_pdf(doc, out):
                print(f"wrote {out}")
            else:
                fb = os.path.splitext(out)[0] + ".html"
                open(fb, "w", encoding="utf-8").write(doc)
                print(f"No PDF engine found. Wrote {fb} instead — install wkhtmltopdf "
                      f"or open the HTML and Print to PDF.", file=sys.stderr)
                sys.exit(2)


if __name__ == "__main__":
    main()
