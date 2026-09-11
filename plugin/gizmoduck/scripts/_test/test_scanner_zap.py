"""Tests for the ZAP adapter's parser.

ZAP is not installed in this environment (no zap.bat/zap.sh on PATH), so the
structural diff between the Automation Framework `report` job's
traditional-json output and the standalone `-J` add-on output (spec 13.11
open item) could not be run here - see the task report. This fixture and
parser are built directly from the documented traditional-json schema
(site[] -> alerts[] -> instances[]), which both delivery paths are documented
to share via the same Report Generation add-on template name.
"""
from scanners import zap


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


def test_missing_report_file_returns_empty_list_not_a_crash(tmp_path):
    assert zap.parse(tmp_path / "does-not-exist.json", "site-a") == []


def test_malformed_json_returns_empty_list_not_a_crash(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json")
    assert zap.parse(bad, "site-a") == []
