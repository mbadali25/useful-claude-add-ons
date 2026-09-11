from scanners import nikto


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
