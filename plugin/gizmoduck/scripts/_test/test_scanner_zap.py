"""Tests for the ZAP adapter's parser.

ZAP is not installed in this environment (no zap.bat/zap.sh on PATH), so the
structural diff between the Automation Framework `report` job's
traditional-json output and the standalone `-J` add-on output (spec 13.11
open item) could not be run here - see the task report. This fixture and
parser are built directly from the documented traditional-json schema
(site[] -> alerts[] -> instances[]), which both delivery paths are documented
to share via the same Report Generation add-on template name.
"""
import pytest

from scanners import base, zap


def test_module_declares_baseline_default_and_active_opt_in():
    # Baseline (spider + passive scan) sends no attack traffic and runs by
    # default; only the active scan option turns on attack traffic, so ACTIVE
    # itself must stay False and the opt-in must be explicit (Global
    # Constraints, plan; spec 13.3).
    assert zap.ACTIVE is False
    assert zap.ACTIVE_OPTS == ["zap_active"]


def test_finding_count_matches_instance_fan_out(fixture):
    findings = zap.parse(fixture("zap.json"), "site-a")
    # 3 instances (XSS) + 1 (CSP) + 1 (unknown riskcode) = 5.
    assert len(findings) == 5


def test_template_id_is_namespaced_by_tool(fixture):
    findings = zap.parse(fixture("zap.json"), "site-a")
    assert all(f["template_id"].startswith("zap:") for f in findings)
    assert {f["template_id"] for f in findings} == {
        "zap:40012", "zap:10038", "zap:99999",
    }


def test_target_is_set_from_the_argument(fixture):
    findings = zap.parse(fixture("zap.json"), "site-a")
    assert all(f["target"] == "site-a" for f in findings)
    other = zap.parse(fixture("zap.json"), "site-b")
    assert all(f["target"] == "site-b" for f in other)


def test_one_alert_with_three_instances_yields_three_matched_at(fixture):
    findings = zap.parse(fixture("zap.json"), "site-a")
    xss = [f for f in findings if f["template_id"] == "zap:40012"]
    assert len(xss) == 3
    assert {f["matched_at"] for f in xss} == {
        "https://example.test/search?q=1",
        "https://example.test/search?q=2",
        "https://example.test/comments?q=3",
    }
    # riskcode 3 -> high, and it's a documented value so no assignment tag.
    assert all(f["severity"] == 3 for f in xss)
    assert all("severity-assigned" not in f["tags"] for f in xss)


def test_low_risk_alert_maps_to_low(fixture):
    findings = zap.parse(fixture("zap.json"), "site-a")
    csp = [f for f in findings if f["template_id"] == "zap:10038"][0]
    assert csp["severity"] == 1
    assert csp["severity_name"] == "low"
    assert "severity-assigned" not in csp["tags"]


def test_riskcode_outside_0_3_lands_info_and_is_flagged(fixture):
    # riskcode 9 is not a documented ZAP value (0-3 is a high-confidence
    # inference, not a documented fact - spec 13.3). Must never be guessed
    # into a real severity band.
    findings = zap.parse(fixture("zap.json"), "site-a")
    odd = [f for f in findings if f["template_id"] == "zap:99999"][0]
    assert odd["severity"] == 0
    assert odd["severity_name"] == "info"
    assert "severity-assigned" in odd["tags"]


def test_missing_report_file_raises_parse_error(tmp_path):
    # DEFECT 2 regression guard: a missing report used to come back as `[]`,
    # indistinguishable from "scan ran, found nothing." It must now surface
    # as base.ParseError so routine records error:parse:<detail>, not `ran`
    # with zero findings.
    with pytest.raises(base.ParseError):
        zap.parse(tmp_path / "does-not-exist.json", "site-a")


def test_malformed_json_raises_parse_error(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json")
    with pytest.raises(base.ParseError):
        zap.parse(bad, "site-a")


def test_empty_file_raises_parse_error_not_empty_findings(tmp_path):
    empty = tmp_path / "empty.json"
    empty.write_text("")
    with pytest.raises(base.ParseError):
        zap.parse(empty, "site-a")


def test_null_site_entry_raises_parse_error_not_attributeerror(tmp_path):
    # Shape validation counts: {"site": [null]} must raise ParseError, never
    # let a bare AttributeError escape from `site.get(...)`.
    bad = tmp_path / "bad-shape.json"
    bad.write_text('{"site": [null]}')
    with pytest.raises(base.ParseError):
        zap.parse(bad, "site-a")


def test_non_object_top_level_raises_parse_error(tmp_path):
    bad = tmp_path / "list-top.json"
    bad.write_text("[1, 2, 3]")
    with pytest.raises(base.ParseError):
        zap.parse(bad, "site-a")


def test_empty_object_raises_parse_error_not_empty_findings(tmp_path):
    """DEFECT 1 (CRITICAL): `{}` is syntactically valid JSON but is missing
    the mandatory top-level 'site' container - the traditional-json report
    ZAP actually writes always carries that key (empty list when nothing was
    scanned). A file missing it entirely must never look like a clean scan."""
    bad = tmp_path / "no-site-key.json"
    bad.write_text("{}")
    with pytest.raises(base.ParseError):
        zap.parse(bad, "site-a")


def test_genuine_empty_site_list_still_returns_empty_findings(tmp_path):
    """Guard against trading a false-clean for a false-error: a real ZAP
    report with an explicit, empty `site: []` is a genuine clean scan."""
    ok = tmp_path / "genuine-empty.json"
    ok.write_text('{"site": []}')
    assert zap.parse(ok, "site-a") == []


def test_non_string_reference_raises_parse_error_not_attribute_error(tmp_path):
    """DEFECT 2 (MEDIUM): `alert.reference` present but not a string (here an
    int) used to reach `.splitlines()` and raise a raw AttributeError -
    routine's handler would then record error:AttributeError instead of
    naming the real problem."""
    bad = tmp_path / "bad-reference.json"
    bad.write_text('{"site":[{"alerts":[{"reference":1}]}]}')
    with pytest.raises(base.ParseError):
        zap.parse(bad, "site-a")


def test_fractional_riskcode_is_not_truncated_into_a_real_band(fixture, tmp_path):
    """DEFECT 3: normalize.sev_from_riskcode does int(code), so a riskcode of
    0.9 or 3.9 would truncate to a recognized 0 or 3 instead of being
    rejected as garbage. The adapter must reject a non-integer riskcode
    before it ever reaches sev_from_riskcode.
    """
    import json as _json

    data = _json.loads(fixture("zap.json").read_text())
    data["site"][0]["alerts"][0]["riskcode"] = 3.9
    data["site"][0]["alerts"][1]["riskcode"] = 0.9
    bad = tmp_path / "fractional.json"
    bad.write_text(_json.dumps(data))

    findings = zap.parse(bad, "site-a")
    by_id = {f["template_id"]: f for f in findings if f["template_id"] == "zap:40012"}
    xss = by_id["zap:40012"]
    assert xss["severity"] == 0
    assert xss["severity_name"] == "info"
    assert "severity-assigned" in xss["tags"]

    csp = [f for f in findings if f["template_id"] == "zap:10038"][0]
    assert csp["severity"] == 0
    assert "severity-assigned" in csp["tags"]


def test_stale_report_is_not_returned_when_the_run_writes_nothing(monkeypatch, tmp_path):
    # DEFECT 1 (CRITICAL): an old report left in outdir from a previous run
    # must never be handed back as if it were this run's evidence.
    stale = tmp_path / "zap.json"
    stale.write_text('{"site": []}')

    monkeypatch.setattr(zap, "_zap_binary", lambda: "/usr/bin/zap.sh")

    def fake_run_tool(argv, timeout, cwd=None):
        return base.ToolResult(1, "", "boom", False)

    monkeypatch.setattr(zap.base, "run_tool", fake_run_tool)

    raw_path, result = zap.run("http://example.test", str(tmp_path), {})
    assert raw_path is None
    assert result.returncode == 1
