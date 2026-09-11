"""Tests for scanners/nmap.py.

nmap is not installed in this environment (confirmed: `which nmap` finds
nothing on this machine). fixtures/nmap.xml was therefore hand-built against
the documented XML / vulns.lua shape (spec 13.11), not captured from a real
scan - these tests validate the parser against that documented shape, not
against verified real-world nmap output. See the fixture's own header
comment and nmap.py's module docstring for the same caveat.
"""
from scanners import nmap
from scanners.base import ToolResult


def _findings(fixture):
    return nmap.parse(fixture("nmap.xml"), target="site-a")


def test_open_port_without_script_yields_exactly_one_info_finding(fixture):
    findings = _findings(fixture)
    port80 = [f for f in findings if f["matched_at"].endswith(":80")]
    assert len(port80) == 1
    assert port80[0]["severity_name"] == "info"
    assert port80[0]["template_id"] == "nmap:open-port/tcp/80"


def test_port_with_script_table_yields_its_own_separate_finding(fixture):
    """The edge case the plan calls out by name: an open port with a script
    carrying a structured <table> must yield the info finding for the port
    PLUS a separate finding at the mapped severity - not one or the other."""
    findings = _findings(fixture)
    port443 = [f for f in findings if f["matched_at"].endswith(":443")]
    assert len(port443) == 2
    by_sev = {f["severity_name"] for f in port443}
    assert by_sev == {"info", "high"}
    vuln = [f for f in port443 if f["severity_name"] == "high"][0]
    assert vuln["template_id"] == "nmap:CVE-2014-3566"
    assert vuln["type"] == "vuln"


def test_vulnerable_exploitable_state_maps_to_critical(fixture):
    findings = _findings(fixture)
    vuln = [f for f in findings if f["template_id"] == "nmap:CVE-2017-5638"][0]
    assert vuln["severity_name"] == "critical"
    assert vuln["severity"] == 4


def test_not_vulnerable_state_produces_no_finding(fixture):
    """NOT VULNERABLE is not a finding at all (spec 13.11) - only the port's
    own info finding should appear for that port."""
    findings = _findings(fixture)
    port9090 = [f for f in findings if f["matched_at"].endswith(":9090")]
    assert len(port9090) == 1
    assert port9090[0]["severity_name"] == "info"
    assert not any(f["template_id"] == "nmap:ABC-000" for f in findings)


def test_unrecognized_state_lands_medium_and_is_flagged(fixture):
    """A malformed/absent-severity entry: an unrecognized state value must
    still surface as a finding (never silently dropped) at a conservative
    default, tagged so a report reader can tell it apart from a real
    assessment."""
    findings = _findings(fixture)
    vuln = [f for f in findings if f["template_id"] == "nmap:XYZ-UNKNOWN"][0]
    assert vuln["severity_name"] == "medium"
    assert "severity-assigned" in vuln["tags"]


def test_target_is_set_from_the_argument(fixture):
    findings = _findings(fixture)
    assert findings
    assert all(f["target"] == "site-a" for f in findings)


def test_every_template_id_is_namespaced_by_tool(fixture):
    findings = _findings(fixture)
    assert findings
    assert all(f["template_id"].startswith("nmap:") for f in findings)


def test_total_finding_count(fixture):
    # 5 open ports -> 5 info findings, plus 3 script tables that are not
    # "not vulnerable" (CVE-2014-3566 high, CVE-2017-5638 critical,
    # XYZ-UNKNOWN medium/assigned) -> 8 total.
    findings = _findings(fixture)
    assert len(findings) == 8


def test_is_available_reflects_which(monkeypatch):
    monkeypatch.setattr(nmap.base, "which", lambda binary: "/usr/bin/nmap")
    assert nmap.is_available() is True
    monkeypatch.setattr(nmap.base, "which", lambda binary: None)
    assert nmap.is_available() is False


def test_run_builds_safe_mode_argv_without_vuln_script(monkeypatch, tmp_path):
    calls = {}

    def fake_run_tool(argv, timeout, cwd=None):
        calls["argv"] = argv
        calls["timeout"] = timeout
        return ToolResult(0, "", "", False)

    monkeypatch.setattr(nmap.base, "run_tool", fake_run_tool)
    raw_path, result = nmap.run("example.com", str(tmp_path), {})

    assert raw_path == str(tmp_path / "nmap.xml") or raw_path.endswith("nmap.xml")
    assert "--script" not in calls["argv"]
    assert calls["argv"][0] == "nmap"
    assert calls["argv"][-1] == "example.com"
    assert result.returncode == 0


def test_run_adds_vuln_script_only_when_opted_in(monkeypatch, tmp_path):
    calls = {}

    def fake_run_tool(argv, timeout, cwd=None):
        calls["argv"] = argv
        return ToolResult(0, "", "", False)

    monkeypatch.setattr(nmap.base, "run_tool", fake_run_tool)
    nmap.run("example.com", str(tmp_path), {"nmap_vuln": True})

    assert "--script" in calls["argv"]
    idx = calls["argv"].index("--script")
    assert calls["argv"][idx + 1] == "vuln"


def test_run_resolves_host_from_url_when_no_host_attribute(monkeypatch, tmp_path):
    class FakeTarget:
        url = "https://site-a.example:8443/path"

    calls = {}

    def fake_run_tool(argv, timeout, cwd=None):
        calls["argv"] = argv
        return ToolResult(0, "", "", False)

    monkeypatch.setattr(nmap.base, "run_tool", fake_run_tool)
    nmap.run(FakeTarget(), str(tmp_path), {})

    assert calls["argv"][-1] == "site-a.example"


def test_active_opts_marks_only_the_vuln_mode_active():
    assert nmap.ACTIVE is False
    assert nmap.ACTIVE_OPTS == ["nmap_vuln"]
    assert nmap.DEFAULT_ENABLED is True
