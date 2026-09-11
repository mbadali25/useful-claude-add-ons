"""Markdown report grouping and the coverage table (plan Task 16).

`cmd_report` learns two new things here: when the input carries `target`/
`tool` fields it groups by target then by category (spec 7 / 12.3), and when
handed a run-manifest dict it renders a coverage table above the findings.
Neither is optional plumbing dressed up as a feature - the coverage table is
what stops a `skipped-missing` or `error` cell from reading as a clean scan,
which is the exact failure a previous real run made
(registration.thdmarketplace.com: 0 findings because a WAF blocked the scan,
not because the site was clean).

The regression test (`test_plain_nuclei_input_renders_unchanged`) is the
acceptance bar for every other test in this file: it must stay green through
every step below, checked against a golden captured from the pre-change code
(see `flat-report-golden.md`), because a plain Nuclei JSONL carries no
`target` field and existing callers depend on that output being
byte-for-byte stable (Global Constraints, "Additive only").
"""
import importlib.util
import json

import pytest

import normalize as n


@pytest.fixture(scope="module")
def gz(scripts_dir):
    spec = importlib.util.spec_from_file_location("gz", scripts_dir / "gizmoduck.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture
def combined_findings(fixture):
    with open(fixture("combined-findings.jsonl"), encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


@pytest.fixture
def run_manifest(fixture):
    with open(fixture("run-manifest.json"), encoding="utf-8") as fh:
        return json.load(fh)


def test_plain_nuclei_input_renders_unchanged(gz, fixture):
    """The acceptance bar: no `target` field anywhere means the existing flat
    format, byte-for-byte, exactly as it rendered before this feature existed."""
    findings = gz.load(str(fixture("nuclei.jsonl")))
    out = gz.cmd_report(findings, 0, "Flat Regression Report")
    golden = fixture("flat-report-golden.md").read_text(encoding="utf-8")
    assert out == golden


def test_plain_nuclei_input_ignores_a_run_manifest_too(gz, fixture, run_manifest):
    """Even if a caller mistakenly passes a run_manifest alongside flat
    findings, grouping is keyed on the findings carrying `target`, not on
    whether a manifest was supplied - so this must render identically too."""
    findings = gz.load(str(fixture("nuclei.jsonl")))
    out = gz.cmd_report(findings, 0, "Flat Regression Report", run_manifest=run_manifest)
    golden = fixture("flat-report-golden.md").read_text(encoding="utf-8")
    assert out == golden


def test_one_section_per_target(gz, combined_findings, run_manifest):
    out = gz.cmd_report(combined_findings, 0, "Combined Report", run_manifest=run_manifest)
    for target in ("site-a", "repo-b", "infra-c"):
        assert f"## {target}" in out


def test_categories_not_tools_are_the_section_grouping(gz, combined_findings, run_manifest):
    """deps (trivy + depcheck) and iac (checkov + trivy) each render as ONE
    section per target, not one section per tool - spec 7 / 12.3."""
    out = gz.cmd_report(combined_findings, 0, "Combined Report", run_manifest=run_manifest)
    repo_b_section = out.split("## repo-b", 1)[1].split("## infra-c", 1)[0]
    # trivy and depcheck both feed `deps` - exactly one Dependencies heading.
    assert repo_b_section.count("Dependencies") == 1
    assert "jackson-databind" in repo_b_section
    assert "lodash" in repo_b_section

    infra_c_section = out.split("## infra-c", 1)[1]
    assert infra_c_section.count("Infrastructure as Code") == 1
    assert "S3 bucket allows public read" in infra_c_section
    assert "S3 bucket without default encryption" in infra_c_section


def test_coverage_table_has_one_row_per_target_one_column_per_tool(gz, combined_findings, run_manifest):
    out = gz.cmd_report(combined_findings, 0, "Combined Report", run_manifest=run_manifest)
    assert "## Coverage" in out
    coverage = out.split("## Coverage", 1)[1].split("##", 1)[0]
    for target in ("site-a", "repo-b", "infra-c"):
        assert target in coverage
    for tool in ("nuclei", "zap", "nikto", "nmap", "testssl", "trivy", "depcheck", "checkov", "sqlmap"):
        assert tool in coverage


def test_ran_with_zero_findings_reads_differently_from_skipped_and_error(gz, combined_findings, run_manifest):
    """The whole point of the coverage table: `ran` with nothing found must be
    visibly distinct from `skipped-missing`, `skipped-active` and an `error`
    cell - conflating them is the WAF-false-clean failure this exists to
    prevent."""
    out = gz.cmd_report(combined_findings, 0, "Combined Report", run_manifest=run_manifest)
    coverage = out.split("## Coverage", 1)[1].split("##", 1)[0]
    assert "skipped-missing" in coverage
    assert "skipped-active" in coverage
    assert "error:timeout" in coverage
    # testssl ran clean (0 findings) for site-a - must say so, not just "ran".
    assert "ran" in coverage
    assert "ran(safe)" in coverage  # nmap's mode is recorded, not a bare "ran"


def test_two_mode_tool_records_the_mode_actually_used(gz, combined_findings, run_manifest):
    out = gz.cmd_report(combined_findings, 0, "Combined Report", run_manifest=run_manifest)
    coverage = out.split("## Coverage", 1)[1].split("##", 1)[0]
    assert "ran(safe)" in coverage


def test_authorized_by_is_restated(gz, combined_findings, run_manifest):
    out = gz.cmd_report(combined_findings, 0, "Combined Report", run_manifest=run_manifest)
    assert "jane@example.com" in out


def test_ran_cell_with_scan_errors_is_distinct_from_a_clean_ran(gz, combined_findings, run_manifest):
    """A `ran` cell can still carry a non-empty `errors` list (a tool's own
    parse_errors() - e.g. testssl's WARN/FATAL entries, per routine.py) even
    when its `count` is 0. That is a third way a scan can look clean and not
    be: a real per-target failure that isn't `error:*` at the cell-status
    level because the tool process itself completed. site-a/testssl in the
    fixture is `ran`, count 0, with one FATAL parse error - it must not read
    identically to site-a's genuinely-clean-scan cells."""
    out = gz.cmd_report(combined_findings, 0, "Combined Report", run_manifest=run_manifest)
    coverage = out.split("## Coverage", 1)[1].split("##", 1)[0]
    # Find the testssl column's site-a cell specifically, not just any "ran".
    header = coverage.splitlines()[2]
    testssl_col = header.split("|").index(" testssl ")
    site_a_row = [ln for ln in coverage.splitlines() if ln.strip().startswith("| site-a")][0]
    testssl_cell = site_a_row.split("|")[testssl_col].strip()
    assert testssl_cell != "ran - 0 findings"
    assert "error" in testssl_cell.lower()


def test_detail_floor_still_applies_within_each_category(gz, combined_findings, run_manifest):
    """REPORT_DETAIL_FLOOR (Medium) must still hold inside the grouped path -
    this is one of the two places the floor is enforced (Global Constraints)."""
    out = gz.cmd_report(combined_findings, 0, "Combined Report", run_manifest=run_manifest)
    # The nmap info-level open-port finding on site-a must not be itemised.
    assert "Open port 443/tcp" not in out


# --- CRITICAL defect: load() re-derives an already-normalized record from --
# raw Nuclei field names and silently blanks it (name/template/severity/tool/
# target all lost, severity reported as Info) instead of passing it through.
# `routine` writes NORMALIZED findings to findings.jsonl (routine.py:422-424),
# so `gizmoduck report <that file>` must round-trip them, not re-parse them as
# if they were raw `nuclei -jsonl` output.

def test_load_passes_an_already_normalized_finding_through_unchanged(gz, tmp_path):
    finding = n.make_finding(
        "sqlmap", "prod", "SQLI", "PROVEN_SQL_INJECTION", 3,
        host="prod", matched_at="https://prod/?id=1",
    )
    p = tmp_path / "findings.jsonl"
    p.write_text(json.dumps(finding) + "\n", encoding="utf-8")

    loaded = gz.load(str(p))

    assert len(loaded) == 1
    got = loaded[0]
    # Every field the normalized record carried must survive - not just
    # `severity`. Blank name/template/tool/target/matched_at is exactly the
    # silent-data-loss this defect produces.
    assert got["name"] == "PROVEN_SQL_INJECTION"
    assert got["template_id"] == finding["template_id"]
    assert got["severity"] == 3
    assert got["severity_name"] == "high"
    assert got["tool"] == "sqlmap"
    assert got["target"] == "prod"
    assert got["matched_at"] == "https://prod/?id=1"


def test_load_of_a_normalized_finding_through_the_report_path_shows_the_action(gz, tmp_path):
    """The end-to-end repro from the defect report: a routine findings.jsonl
    fed to `report` must show the finding it actually contains, not
    'No action required'.

    Uses `checkov` rather than `sqlmap` deliberately - `sqlmap` gaining a
    category is a separate defect (see the sqlmap-category tests below);
    this test isolates the load()-blanking defect from that one."""
    finding = n.make_finding(
        "checkov", "prod", "CKV_1", "PROVEN_SQL_INJECTION", 3,
        host="prod", matched_at="https://prod/?id=1",
    )
    p = tmp_path / "findings.jsonl"
    p.write_text(json.dumps(finding) + "\n", encoding="utf-8")

    findings = gz.load(str(p))
    out = gz.cmd_report(findings, 2, "Report")

    assert "No action required" not in out
    assert "PROVEN_SQL_INJECTION" in out
    assert "High" in out


def test_load_still_parses_raw_nuclei_records(gz, fixture):
    """The other half of the discriminator: real `nuclei -jsonl` output
    (`template-id` + nested `info`) must still parse exactly as before."""
    findings = gz.load(str(fixture("nuclei.jsonl")))
    assert findings
    assert all(f.get("template_id") for f in findings)


def test_load_rejects_a_record_that_is_neither_shape(gz, tmp_path):
    """A record with neither raw Nuclei's `template-id`+`info` nor a
    normalized `template_id`+`severity_name` must be rejected outright,
    rather than silently produced as a blank Info finding."""
    p = tmp_path / "findings.jsonl"
    p.write_text(json.dumps({"some": "garbage", "no": "recognizable-shape"}) + "\n",
                 encoding="utf-8")
    with pytest.raises(Exception):
        gz.load(str(p))


# --- CRITICAL defect: an empty finding list discards failed coverage. -----
#
# Combined-mode detection was keyed only on findings carrying `target`, so a
# run where every tool errored (zero findings, but a real run_manifest) fell
# through to the flat path and printed "No action required" - discarding the
# coverage table that is the only evidence distinguishing a failed scan from
# a clean one.

def test_empty_findings_with_a_manifest_still_renders_combined_mode(gz):
    manifest = {
        "cells": [{"target": "prod", "tool": "nuclei", "status": "error:timeout",
                   "mode": None, "error": "timeout", "duration_s": 30.0,
                   "count": 0, "errors": []}],
    }
    out = gz.cmd_report([], 2, "Review", manifest)
    assert "No action required" not in out
    assert "## Coverage" in out
    assert "error:timeout" in out


def test_plain_empty_findings_without_a_manifest_still_says_no_action(gz):
    """No manifest, no findings - the ordinary clean-scan case - must be
    unaffected by the fix above."""
    out = gz.cmd_report([], 2, "Review")
    assert "No action required" in out
