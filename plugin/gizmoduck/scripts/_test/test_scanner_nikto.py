import pytest

from scanners import base, nikto


def test_parses_both_rows_with_derived_severities(fixture):
    findings = nikto.parse(str(fixture("nikto.csv")), "https://example.test")
    assert len(findings) == 2

    banner, vuln = findings
    assert banner["severity"] == 0
    assert banner["severity_name"] == "info"
    assert vuln["severity"] == 2
    assert vuln["severity_name"] == "medium"


def test_every_finding_carries_severity_assigned(fixture):
    # Nikto has no severity field at all (spec 13.6) - every finding here is
    # a heuristic assignment, and the marker must say so every time.
    findings = nikto.parse(str(fixture("nikto.csv")), "https://example.test")
    assert len(findings) == 2
    for f in findings:
        assert "severity-assigned" in f["tags"]


def test_template_id_is_namespaced_by_tool(fixture):
    findings = nikto.parse(str(fixture("nikto.csv")), "https://example.test")
    ids = {f["template_id"] for f in findings}
    assert ids == {"nikto:000001", "nikto:999100"}


def test_target_is_set_from_argument(fixture):
    findings = nikto.parse(str(fixture("nikto.csv")), "https://example.test")
    for f in findings:
        assert f["target"] == "https://example.test"


def test_parse_missing_file_returns_no_findings(tmp_path):
    assert nikto.parse(str(tmp_path / "absent.csv"), "https://example.test") == []


def test_module_constants_match_the_plan():
    assert nikto.NAME == "nikto"
    assert nikto.KINDS == ["web"]
    assert nikto.ACTIVE is False
    assert nikto.ACTIVE_OPTS == []


# --- parse(): must not manufacture a vulnerability from garbage input ----
#
# MEDIUM defect: any nonempty CSV row - including a truncated row or a
# single diagnostic/garbage line - used to get padded out to the full
# column set and turned into a `medium` finding. That invents a
# vulnerability that was never actually observed. Required columns must
# now be validated, raising base.ParseError instead.

def test_truncated_row_raises_parse_error_instead_of_a_finding(fixture):
    with pytest.raises(base.ParseError):
        nikto.parse(str(fixture("nikto-truncated.csv")), "https://example.test")


def test_garbage_line_raises_parse_error_instead_of_a_finding(fixture):
    with pytest.raises(base.ParseError):
        nikto.parse(str(fixture("nikto-bad-shape.csv")), "https://example.test")


def test_bare_null_line_raises_parse_error_instead_of_a_finding(fixture):
    with pytest.raises(base.ParseError):
        nikto.parse(str(fixture("nikto-null.csv")), "https://example.test")
