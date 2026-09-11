"""HTML/PDF report grouping and the coverage table (plan Task 17).

Mirrors test_report_grouping.py for the render_report()/render_html() path.
The two things that matter most here are not testable by pytest at all:

1. Qt WebKit 4.8 (wkhtmltopdf) silently ignores flexbox, CSS grid and custom
   properties - a layout using any of them looks right in a browser and wrong
   in the actual PDF, with no error from wkhtmltopdf either way. The
   automated tests below only check the HTML *string*; this file's markup
   uses <table> only, and a real PDF must still be rendered and opened by
   hand before this task is done (see the plan's Task 17 step 4).
2. ACTION_THRESHOLD (Medium) must still floor detail in the grouped path -
   this is the second of the two places the detail floor is enforced
   (Global Constraints: REPORT_DETAIL_FLOOR in gizmoduck.py is the other).
"""
import importlib.util
import json

import pytest


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
    findings = gz.load(str(fixture("nuclei.jsonl")))
    out = gz.render_html(findings, 0, "Flat Regression Report")
    golden = fixture("flat-report-golden.html").read_text(encoding="utf-8")
    assert out == golden


def test_plain_nuclei_input_ignores_a_run_manifest_too(gz, fixture, run_manifest):
    findings = gz.load(str(fixture("nuclei.jsonl")))
    out = gz.render_html(findings, 0, "Flat Regression Report", run_manifest=run_manifest)
    golden = fixture("flat-report-golden.html").read_text(encoding="utf-8")
    assert out == golden


def test_coverage_table_appears_in_the_html(gz, combined_findings, run_manifest):
    out = gz.render_html(combined_findings, 0, "Combined Report", run_manifest=run_manifest)
    assert "Coverage" in out
    assert "site-a" in out and "repo-b" in out and "infra-c" in out
    for tool in ("nuclei", "zap", "nikto", "nmap", "testssl", "trivy", "depcheck", "checkov", "sqlmap"):
        assert tool in out


def test_coverage_table_is_a_real_table_element(gz, combined_findings, run_manifest):
    """Qt WebKit 4.8 has no flexbox/grid/custom-properties - the coverage
    table must be built from <table> markup, not a div-based layout that
    would render fine in a browser and break in the PDF."""
    out = gz.render_html(combined_findings, 0, "Combined Report", run_manifest=run_manifest)
    assert "<table" in out
    # No CSS custom properties (var(--x)) or flex/grid layout anywhere new.
    assert "var(--" not in out
    assert "display:flex" not in out and "display: flex" not in out
    assert "display:grid" not in out and "display: grid" not in out


def test_ran_zero_findings_is_visually_distinct_from_skipped_and_error(gz, combined_findings, run_manifest):
    out = gz.render_html(combined_findings, 0, "Combined Report", run_manifest=run_manifest)
    assert "skipped-missing" in out
    assert "skipped-active" in out
    assert "error:timeout" in out
    assert "ran(safe)" in out


def test_sections_grouped_by_category_not_by_tool(gz, combined_findings, run_manifest):
    out = gz.render_html(combined_findings, 0, "Combined Report", run_manifest=run_manifest)
    assert "Dependencies" in out
    assert "Infrastructure as Code" in out
    assert "lodash" in out and "jackson-databind" in out


def test_action_threshold_still_floors_detail_for_combined_input(gz, combined_findings, run_manifest):
    """The nmap info-level open-port finding on site-a must not be itemised -
    ACTION_THRESHOLD (Medium) applies in the grouped path exactly as it does
    in the flat one."""
    out = gz.render_html(combined_findings, 0, "Combined Report", run_manifest=run_manifest)
    assert "Open port 443/tcp" not in out


def test_ran_cell_with_scan_errors_is_flagged_in_html(gz, combined_findings, run_manifest):
    """Mirrors the Markdown test: site-a/testssl is `ran`, count 0, but
    carries one FATAL parse_errors() entry - that must render differently
    from a genuinely clean `ran - 0 findings` cell, or a real per-target
    failure disappears into "no findings"."""
    out = gz.render_html(combined_findings, 0, "Combined Report", run_manifest=run_manifest)
    assert "scan error" in out.lower()


def test_authorized_by_is_restated_in_html(gz, combined_findings, run_manifest):
    out = gz.render_html(combined_findings, 0, "Combined Report", run_manifest=run_manifest)
    assert "jane@example.com" in out


def test_empty_findings_with_a_manifest_still_renders_combined_mode_html(gz):
    """HTML mirror of the Markdown defect-2 fix: a manifest whose only cell
    is an error must still show the coverage table and must not fall back
    to the "Nothing at or above Medium" clean-scan message, which would
    hide the fact that every tool failed."""
    manifest = {
        "cells": [{"target": "prod", "tool": "nuclei", "status": "error:timeout",
                   "mode": None, "error": "timeout", "duration_s": 30.0,
                   "count": 0, "errors": []}],
    }
    out = gz.render_html([], 2, "Review", run_manifest=manifest)
    assert "Coverage" in out
    assert "error:timeout" in out
    assert "Nothing at or above" not in out
