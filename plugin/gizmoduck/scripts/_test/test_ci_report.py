"""ci_report / `gizmoduck_ci.py scan-report` - security-scan-report.md from an
endpoint scan's output, attributed to the fixtures/monorepo inventory.

The scan output is built here: targets.json as the prod-refusal guard writes
it, a run manifest with one coverage cell per target and tool, and normalised
findings carrying their target's name. Every host is on a reserved .test
domain.
"""
import json
import subprocess
import sys
from pathlib import Path

import ci_gate
import ci_inventory
import ci_report
import pytest

_CLI = Path(__file__).resolve().parent.parent / "gizmoduck_ci.py"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "monorepo"
ORDERS = "https://orders.staging.example.test"
BILLING = "https://billing.staging.example.test"
META = {"date": "2026-09-20", "commit": "0123456789abcdef0123456789abcdef01234567", "branch": "release/2.4",
        "tier": "full", "run_url": "https://ci.example.test/runs/42", "artifacts": ["report.html", "report.pdf"]}

TARGETS = {"allowed": [
    {"name": "staging", "url": ORDERS, "kind": "base"},
    {"name": "endpoint-ep-0001-1", "url": f"{ORDERS}/api/orders", "kind": "endpoint"},
    {"name": "endpoint-billing-2", "url": BILLING, "kind": "endpoint"},
], "refused": [], "skipped": []}


def cell(target, tool, status="ran"):
    return {"target": target, "tool": tool, "status": status}


MANIFEST = {"cells": [
    cell("staging", "nuclei"), cell("staging", "zap", "ran(baseline)"), cell("staging", "testssl"),
    cell("endpoint-ep-0001-1", "nuclei"), cell("endpoint-ep-0001-1", "zap", "ran(baseline)"),
    cell("endpoint-billing-2", "nuclei"), cell("endpoint-billing-2", "zap", "error:timeout"),
]}


def finding(tid, sev, target, url):
    names = {4: "critical", 3: "high", 2: "medium", 1: "low", 0: "info"}
    return {"template_id": tid, "name": tid, "severity": sev, "severity_name": names[sev], "target": target,
            "matched_at": url, "host": url, "tool": "nuclei"}


FINDINGS = [
    finding("nuclei:sqli", 4, "endpoint-ep-0001-1", f"{ORDERS}/api/orders?id=1"),
    finding("nuclei:missing-hsts", 2, "staging", ORDERS),
    finding("nuclei:old-tls", 3, "endpoint-billing-2", BILLING),
    finding("nuclei:banner", 1, "endpoint-billing-2", BILLING),
    finding("nuclei:stray", 3, "someone-else", "https://unrelated.example.test/x"),
]
BASELINE = [FINDINGS[1]]     # the Medium was already known


def parsed(records):
    return [ci_gate.parse_line(json.dumps(r)) for r in records]


_DEFAULT = object()


def build(findings=_DEFAULT, baseline=_DEFAULT, manifest=_DEFAULT):
    findings = FINDINGS if findings is _DEFAULT else findings
    baseline = BASELINE if baseline is _DEFAULT else baseline
    manifest = MANIFEST if manifest is _DEFAULT else manifest
    modules = ci_inventory.build(str(FIXTURE), ci_inventory.settings(None))
    return ci_report.build(modules, TARGETS, manifest,
                           None if findings is None else parsed(findings),
                           None if baseline is None else parsed(baseline))


def rows(report):
    return {(m["path"], (r["endpoint"]["method"] + " " + r["endpoint"]["endpoint"]).strip()): r
            for m in report["modules"] for r in m["rows"]}


def test_counts_are_attributed_per_module_and_endpoint():
    r = rows(build())
    get = r[("orders-api", "GET /api/orders")]
    assert get["status"] == "scanned" and get["counts"] == {"critical": 1, "high": 0, "medium": 0, "new": 1}
    main = r[("billing-portal", "https://billing.example.test")]
    assert main["status"] == "partial" and main["missing"] == ["zap=error:timeout"]
    assert main["counts"] == {"critical": 0, "high": 1, "medium": 0, "new": 1}


def test_an_endpoint_nothing_scanned_is_unverified_not_zero():
    r = rows(build())
    row = r[("billing-portal", "https://api.billing.example.test/v1")]
    assert row["status"] == "UNVERIFIED" and row["counts"] is None
    text = ci_report.render(build(), META)
    assert "| `https://api.billing.example.test/v1` | UNVERIFIED (no scanned target matches this endpoint) | " \
           "- | - | - | - |" in text


def test_unclaimed_targets_are_listed_and_every_finding_counted_once():
    rep = build()
    assert [o["target"] for o in rep["others"]] == ["staging"]
    assert rep["others"][0]["counts"] == {"critical": 0, "high": 0, "medium": 1, "new": 0}
    assert rep["totals"] == {"critical": 1, "high": 2, "medium": 1, "new": 3}
    assert rep["unattributed"] == 1


def test_no_baseline_means_new_is_not_applicable():
    rep = build(baseline=None)
    assert rep["totals"]["new"] is None
    text = ci_report.render(rep, META)
    assert "none - nothing can be called new" in text and "| n/a |" in text


def test_no_findings_file_makes_every_row_unverified():
    rep = build(findings=None)
    assert {r["status"] for m in rep["modules"] for r in m["rows"]} == {"UNVERIFIED"}
    assert "the scan produced no findings file" in ci_report.render(rep, META)


def test_a_target_whose_tools_never_ran_is_unverified():
    manifest = {"cells": [c for c in MANIFEST["cells"] if c["target"] != "endpoint-ep-0001-1"]}
    assert rows(build(manifest=manifest))[("orders-api", "GET /api/orders")]["status"] == "UNVERIFIED"


def test_header_carries_date_commit_and_artifact_links():
    text = ci_report.render(build(), META)
    assert text.startswith("# Security scan report\n")
    assert "- Scan date: 2026-09-20" in text
    assert "- Commit: `0123456789abcdef0123456789abcdef01234567`" in text
    assert "`report.html`, `report.pdf` in [this run's artifacts](https://ci.example.test/runs/42)" in text
    assert "do not edit" in text


def test_render_is_pure():
    assert ci_report.render(build(), META) == ci_report.render(build(), dict(META))
    assert "\r" not in ci_report.render(build(), META)


def test_nothing_but_counts_and_redacted_urls_is_written():
    records = [dict(FINDINGS[0], description="SECRET-BODY", request="GET /?token=abc")]
    text = ci_report.render(build(findings=records), META)
    assert "SECRET-BODY" not in text and "token=abc" not in text


def _scan_out(tmp_path, findings=True):
    out = tmp_path / "out"
    out.mkdir()
    (out / "targets.json").write_text(json.dumps(TARGETS), encoding="utf-8")
    (out / "run-manifest.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
    if findings:
        (out / "findings.jsonl").write_text("".join(json.dumps(f) + "\n" for f in FINDINGS), encoding="utf-8")
    (out / "report.html").write_text("<html></html>", encoding="utf-8")
    base = tmp_path / "baseline.jsonl"
    base.write_text("".join(json.dumps(f) + "\n" for f in BASELINE), encoding="utf-8")
    return out, base


@pytest.mark.parametrize("findings", [True, False])
def test_cli_writes_the_report_into_the_scan_output(tmp_path, findings):
    out, base = _scan_out(tmp_path, findings)
    summary = tmp_path / "summary.md"

    p = subprocess.run([sys.executable, str(_CLI), "scan-report", "--repo", str(FIXTURE), "--out", str(out),
                        "--commit", "abc123", "--date", "2026-09-20", "--baseline", str(base),
                        "--run-url", "https://ci.example.test/runs/7", "--summary", str(summary)],
                       capture_output=True, text=True, check=False)

    assert p.returncode == 0, p.stderr
    text = (out / ci_report.DEFAULT_OUTPUT).read_text(encoding="utf-8")
    assert "- Full reports: `report.html`" in text and "[this run's artifacts](https://ci.example.test/runs/7)" in text
    assert summary.read_text(encoding="utf-8") == text
    assert ("the scan produced no findings file" in text) is (not findings)


def test_cli_fails_loudly_on_an_unreadable_findings_file(tmp_path):
    out, _ = _scan_out(tmp_path)
    (out / "findings.jsonl").write_text("not json\n", encoding="utf-8")
    p = subprocess.run([sys.executable, str(_CLI), "scan-report", "--repo", str(FIXTURE), "--out", str(out),
                        "--commit", "abc123"], capture_output=True, text=True, check=False)
    assert p.returncode == 2 and "GIZMODUCK_REPORT_FAILED" in p.stderr
