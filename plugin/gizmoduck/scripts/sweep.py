"""Scan every site a repository declares, in one command.

"Run a security scan on all the sites in this repo" is a routine request, and
answering it with a script written fresh each time is how the conventions drift:
one run writes reports somewhere else, another forgets the PDF, a third skips
the modules whose DNS does not resolve and never says so.

The convention this implements:

  <module>/public-endpoint.md          declares url / status / kind
  <module>/docs/security-scans/<date>/ receives findings.jsonl + report.{md,html,pdf}

For each declared site: the endpoint tools run against its `url`, and the source
tools run against that module's own directory. Everything merges into one
findings file and one Medium-and-above report per module.

Three behaviours worth knowing, each learned from a real run:

1. **A module whose endpoint does not resolve is still scanned.** Dependencies,
   Terraform and source code do not care whether the endpoint is reachable, so
   skipping the module drops real coverage. The endpoint is recorded as
   unreachable and the source tools run anyway.

2. **A clean module still gets HTML and PDF.** "Nothing found" is a result
   somebody needs to open and file. Generating reports only when findings exist
   leaves the clean modules with nothing readable.

3. **One module's failure never kills the sweep.** `cmd_scan` exits the process
   when nuclei fails, which is right for a single scan and wrong for a sweep of
   eighteen. That exit is caught per module and recorded.
"""
import io
import json
import os
import re
import socket
import sys
import time
from datetime import date

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

DEFAULT_DECLARATION = "public-endpoint.md"
DEFAULT_SCAN_DIR = os.path.join("docs", "security-scans")

# Directories that never hold a module worth scanning.
PRUNE = {"node_modules", ".git", ".venv", "venv", "__pycache__", "dist",
         "build", ".terraform", "graphify-out"}


def _field(lines, name):
    """Pull one scalar out of a declaration's front matter.

    Deliberately not a YAML parse: the declaration files carry long prose
    values with colons and em-dashes in them, and a strict parser fails on
    files a human wrote correctly. Only three scalars are needed.
    """
    pat = re.compile(rf'^{name}\s*:\s*(.*)$')
    for ln in lines:
        m = pat.match(ln)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    return ""


def discover(root, declaration=DEFAULT_DECLARATION):
    """Every module under `root` that declares a public endpoint."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in PRUNE and not d.startswith(".")]
        if declaration in filenames:
            path = os.path.join(dirpath, declaration)
            try:
                lines = io.open(path, encoding="utf-8").read().splitlines()
            except OSError:
                continue
            found.append({
                "module": os.path.basename(dirpath),
                "dir": dirpath,
                "declaration": path,
                "url": _field(lines, "url"),
                "status": _field(lines, "status"),
                "kind": _field(lines, "kind"),
            })
    return sorted(found, key=lambda s: s["module"])


def _host_of(url):
    host = url.split("://")[-1].split("/")[0]
    return host.split(":")[0]


def _resolves(host):
    try:
        socket.getaddrinfo(host, None)
        return True
    except (socket.gaierror, UnicodeError):
        return False


def run(root, with_zap=False, with_checkov=False, declaration=DEFAULT_DECLARATION,
        scan_dir=DEFAULT_SCAN_DIR, semgrep_config="p/security-audit",
        extra="", severity="", run_date=None, min_sev=None, resume=False):
    """Scan every declared site. Returns a list of per-module result dicts.

    `min_sev` is the report's itemisation floor as an INT, not a name, and
    defaults to REPORT_DETAIL_FLOOR (Medium). detail_floor() clamps it upward
    anyway, so a caller cannot lower the floor below Medium here.
    """
    import gizmoduck as gz

    if min_sev is None:
        min_sev = gz.REPORT_DETAIL_FLOOR

    sites = discover(root, declaration)
    stamp = run_date or date.today().isoformat()
    gz.safe_print(f"# sweep: {len(sites)} declared site(s) under {root}")
    gz.safe_print(f"# writing to <module>/{scan_dir}/{stamp}/")
    if not sites:
        gz.safe_print(f"!! no {declaration} found. Nothing to scan.")
        return []

    results = []
    for i, site in enumerate(sites, 1):
        mod, url = site["module"], site["url"]
        gz.safe_print("")
        gz.safe_print(f"[{i}/{len(sites)}] {mod}  status={site['status'] or '?'}  {url or '(no url)'}")
        if not url:
            gz.safe_print("  !! declaration carries no url - skipped")
            results.append({**site, "scanned": False, "note": "no url", "findings": 0})
            continue

        out_dir = os.path.join(site["dir"], scan_dir, stamp)
        os.makedirs(out_dir, exist_ok=True)
        jsonl = os.path.join(out_dir, "findings.jsonl")
        marker = os.path.join(out_dir, "scan-meta.json")

        # A repo-wide sweep is a long job - eight minutes a module, so hours for
        # a real estate - and it WILL be interrupted: a lost connection, a
        # reboot, or the OS killing it under memory pressure. Without --resume
        # the only options are rescan everything or hand-pick the remainder,
        # and the second is how modules get silently missed.
        #
        # The marker is what proves completion, not the presence of
        # findings.jsonl: a module that legitimately came back clean writes an
        # empty findings file, and an interrupted one can leave a partial file
        # that looks just like it.
        if resume and os.path.exists(marker):
            try:
                prev = json.loads(io.open(marker, encoding="utf-8").read())
                done_n = prev.get("findings", "?")
            except (OSError, ValueError):
                done_n = "?"
            gz.safe_print(f"  already scanned this date ({done_n} findings) - skipped")
            results.append({**site, "scanned": True, "skipped": True,
                            "findings": prev.get("findings", 0) if isinstance(done_n, int) else 0,
                            "note": "", "out_dir": out_dir})
            continue

        reachable = _resolves(_host_of(url))
        if not reachable:
            # Not a skip. The source tools have real work to do regardless.
            gz.safe_print(f"  !! DNS does not resolve for {_host_of(url)} - "
                          f"endpoint tools will fail; source tools still run")

        started = time.time()
        note = ""
        try:
            gz.cmd_scan(url, jsonl, severity, extra, source=site["dir"],
                        with_zap=with_zap, with_checkov=with_checkov,
                        semgrep_config=semgrep_config)
        except SystemExit as exc:
            # cmd_scan exits the process when nuclei fails - correct for one
            # scan, fatal for a sweep. Record it and keep going.
            note = f"scan aborted: {exc}"
            gz.safe_print(f"  !! {note}")
        except Exception as exc:                      # noqa: BLE001
            note = f"{type(exc).__name__}: {exc}"
            gz.safe_print(f"  !! {note}")

        if not os.path.exists(jsonl):
            io.open(jsonl, "w", encoding="utf-8").close()

        count = sum(1 for ln in io.open(jsonl, encoding="utf-8") if ln.strip())
        gz.safe_print(f"  {count} finding(s) in {(time.time() - started) / 60:.1f} min")

        # Human-readable copies, always - including for a clean module.
        title = f"{mod} - {url}"
        findings = gz.load(jsonl)
        for fmt in ("md", "html", "pdf"):
            dest = os.path.join(out_dir, f"report.{fmt}")
            try:
                if fmt == "md":
                    gz.write_text(dest, gz.cmd_report(findings, min_sev, title))
                elif fmt == "html":
                    gz.write_text(dest, gz.render_html(findings, min_sev, title))
                else:
                    gz.html_to_pdf(gz.render_html(findings, min_sev, title), dest)
            except Exception as exc:                  # noqa: BLE001
                gz.safe_print(f"  !! report.{fmt} failed: {type(exc).__name__}: {exc}")

        # Written LAST, and only on a module that got all the way through, so
        # --resume can trust it. An interrupted module leaves no marker and is
        # rescanned.
        if not note:
            gz.write_text(marker, json.dumps({
                "module": mod, "url": url, "date": stamp,
                "findings": count, "reachable": reachable,
                "with_zap": with_zap, "with_checkov": with_checkov,
                "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }, indent=2))

        results.append({**site, "scanned": True, "reachable": reachable,
                        "findings": count, "note": note, "out_dir": out_dir})

    _summary(results)
    return results


def _summary(results):
    import gizmoduck as gz

    gz.safe_print("")
    gz.safe_print("=" * 64)
    gz.safe_print(f"{'module':<32} {'findings':>9}  note")
    gz.safe_print("-" * 64)
    for r in sorted(results, key=lambda x: -x.get("findings", 0)):
        note = r.get("note") or ("" if r.get("reachable", True) else "endpoint unreachable")
        gz.safe_print(f"{r['module']:<32} {r.get('findings', 0):>9}  {note}")
    gz.safe_print("-" * 64)
    total = sum(r.get("findings", 0) for r in results)
    problems = [r for r in results if r.get("note")]
    gz.safe_print(f"{'TOTAL':<32} {total:>9}")
    if problems:
        gz.safe_print("")
        gz.safe_print(f"!! {len(problems)} module(s) did not scan cleanly - "
                      f"those reports are INCOMPLETE, not clean:")
        for r in problems:
            gz.safe_print(f"   {r['module']}: {r['note']}")
