"""Tests for scanners/nmap.py.

nmap is not installed in this environment (confirmed: `which nmap` finds
nothing on this machine). fixtures/nmap.xml was therefore hand-built against
the documented XML / vulns.lua shape (spec 13.11), not captured from a real
scan - these tests validate the parser against that documented shape, not
against verified real-world nmap output. See the fixture's own header
comment and nmap.py's module docstring for the same caveat.
"""
import pytest

from scanners import nmap
from scanners import base
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
    # 6 open ports -> 6 info findings, plus 4 port-level script tables that
    # are not "not vulnerable" (CVE-2014-3566 high, CVE-2017-5638 critical,
    # XYZ-UNKNOWN medium/assigned, GENERIC-ID-1 medium/likely-vulnerable),
    # plus 1 host-level script table (CVE-2021-99999 high, under
    # <hostscript>) -> 11 total.
    findings = _findings(fixture)
    assert len(findings) == 11


def test_hostscript_vulnerability_is_not_dropped(fixture):
    """DEFECT 1 regression guard: many --script vuln NSE scripts (e.g.
    clock-skew or whole-host SMB checks) report under host/hostscript/script
    rather than under any <port>. A parser that only walks port-level
    <script> elements silently drops these - the target reads as clean even
    though vulns.lua reported a confirmed VULNERABLE state."""
    findings = _findings(fixture)
    host_vuln = [f for f in findings if f["template_id"] == "nmap:CVE-2021-99999"]
    assert len(host_vuln) == 1
    finding = host_vuln[0]
    assert finding["severity_name"] == "high"
    assert finding["type"] == "vuln"
    # No port applies to a host-level script - matched_at/host must still be
    # a sensible locator (the bare host), not a stale/empty/port-shaped value.
    assert finding["host"] == "203.0.113.10"
    assert finding["matched_at"] == "203.0.113.10"


def test_cve_is_populated_from_the_ids_table(fixture):
    findings = _findings(fixture)
    poodle = [f for f in findings if f["template_id"] == "nmap:CVE-2014-3566"][0]
    assert poodle["cve"] == ["CVE-2014-3566"]


def test_cvss_is_populated_from_the_scores_table(fixture):
    findings = _findings(fixture)
    poodle = [f for f in findings if f["template_id"] == "nmap:CVE-2014-3566"][0]
    assert poodle["cvss"] == 3.4
    struts = [f for f in findings if f["template_id"] == "nmap:CVE-2017-5638"][0]
    assert struts["cvss"] == 10.0


def test_references_are_populated_from_the_references_table(fixture):
    findings = _findings(fixture)
    poodle = [f for f in findings if f["template_id"] == "nmap:CVE-2014-3566"][0]
    assert poodle["reference"] == [
        "https://www.openssl.org/~bodo/ssl-poodle.pdf",
        "https://nvd.nist.gov/vuln/detail/CVE-2014-3566",
    ]
    # struts has no <table key="references"> at all - must come back empty,
    # not raise and not inherit poodle's list.
    struts = [f for f in findings if f["template_id"] == "nmap:CVE-2017-5638"][0]
    assert struts["reference"] == []


def test_missing_ids_table_leaves_cve_empty_rather_than_falling_back_to_the_key(fixture):
    """The regression this whole enrichment guards against: before, nothing
    populated `cve` at all, and template_id/rule_id happening to look like a
    CVE (e.g. "nmap:CVE-2014-3566") could be mistaken for cve being derived
    from the outer <table key=...> attribute. XYZ-UNKNOWN's outer key is not
    even CVE-shaped and it carries no <table key="ids"> - cve must be []."""
    findings = _findings(fixture)
    unknown = [f for f in findings if f["template_id"] == "nmap:XYZ-UNKNOWN"][0]
    assert unknown["cve"] == []
    assert unknown["cvss"] == ""
    assert unknown["reference"] == []


def test_cve_never_falls_back_to_a_non_cve_shaped_outer_key(fixture):
    """Proves cve is read from the ids table independent of the outer
    <table key=...> attribute, in both directions: GENERIC-ID-1 is not
    CVE-shaped, yet its ids table supplies a real CVE that must surface."""
    findings = _findings(fixture)
    generic = [f for f in findings if f["template_id"] == "nmap:GENERIC-ID-1"][0]
    assert generic["cve"] == ["CVE-2099-0001"]
    assert generic["cvss"] == ""


def test_hostscript_finding_also_gets_the_enriched_fields(fixture):
    """Host-level findings go through the same _append_vuln_findings helper
    as port-level ones (defect 1's fix), so scores/ids/references must be
    read there too, not just for scripts nested under a <port>."""
    findings = _findings(fixture)
    host_vuln = [f for f in findings if f["template_id"] == "nmap:CVE-2021-99999"][0]
    assert host_vuln["cvss"] == 7.5


def test_description_is_read_from_the_nested_description_table(fixture):
    """description lives in a nested <table key="description"> holding an
    anonymous <elem>, the same nesting shape as ids/scores/references - not
    a direct <elem key="description"> child of the vuln table. A lookup
    written for the wrong shape silently returned "" for every finding;
    combined with the empty cve fixed earlier, an nmap vuln rendered in the
    report as a bare title with no explanation of what it was."""
    findings = _findings(fixture)
    poodle = [f for f in findings if f["template_id"] == "nmap:CVE-2014-3566"][0]
    assert poodle["description"] == (
        "The SSL protocol 3.0 uses nondeterministic CBC padding, which allows\n"
        "man-in-the-middle attackers to obtain cleartext data via a padding-oracle\n"
        "attack (CVE-2014-3566), aka the POODLE issue."
    )


def test_missing_description_table_yields_empty_string_not_a_raise(fixture):
    """XYZ-UNKNOWN has no <table key="description"> at all - must come back
    "" rather than raising or fabricating text."""
    findings = _findings(fixture)
    unknown = [f for f in findings if f["template_id"] == "nmap:XYZ-UNKNOWN"][0]
    assert unknown["description"] == ""


def test_finding_name_comes_from_the_title_elem(fixture):
    """title (the finding's `name`) is a direct <elem key="title"> child of
    the vuln table - unlike ids/scores/references/description, which nest
    inside their own <table>. Confirmed correct per the fixture's
    documented shape, but nothing previously asserted its content directly;
    a finding's name is the one field it cannot do without, so this closes
    that gap explicitly rather than leaving it unverified."""
    findings = _findings(fixture)
    poodle = [f for f in findings if f["template_id"] == "nmap:CVE-2014-3566"][0]
    assert poodle["name"] == "SSL POODLE information leak"
    struts = [f for f in findings if f["template_id"] == "nmap:CVE-2017-5638"][0]
    assert struts["name"] == "Apache Struts Jakarta Multipart Parser Remote Code Execution"


def test_malformed_xml_raises_base_parse_error_not_a_bare_exception(tmp_path):
    """DEFECT 2 regression guard: nmap.py must never let
    xml.etree.ElementTree.ParseError escape uncaught. That fails the whole
    routine run instead of just this one cell - base.ParseError is what
    routine catches to record error:parse:<detail> for that cell alone. An
    empty finding list must mean only "nmap ran and found nothing", never
    "the output was unreadable"."""
    bad = tmp_path / "truncated.xml"
    bad.write_text("<?xml version=\"1.0\"?><nmaprun><host><ports>")

    with pytest.raises(base.ParseError):
        nmap.parse(str(bad), target="site-a")


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


def test_run_returns_none_path_on_nonzero_exit(monkeypatch, tmp_path):
    """Per the pinned adapter contract (spec 13.14), a failed run withholds
    raw_path but still returns the ToolResult, so routine can record
    error:<message> without ever handing parse() a file that may not exist
    or may not parse."""
    def fake_run_tool(argv, timeout, cwd=None):
        return ToolResult(1, "", "nmap: command line error", False)

    monkeypatch.setattr(nmap.base, "run_tool", fake_run_tool)
    raw_path, result = nmap.run("example.com", str(tmp_path), {})

    assert raw_path is None
    assert result.returncode == 1


def test_run_returns_none_path_on_timeout(monkeypatch, tmp_path):
    def fake_run_tool(argv, timeout, cwd=None):
        return ToolResult(-1, "", "", True)

    monkeypatch.setattr(nmap.base, "run_tool", fake_run_tool)
    raw_path, result = nmap.run("example.com", str(tmp_path), {})

    assert raw_path is None
    assert result.timed_out is True


def test_active_opts_marks_only_the_vuln_mode_active():
    assert nmap.ACTIVE is False
    assert nmap.ACTIVE_OPTS == ["nmap_vuln"]
    assert nmap.DEFAULT_ENABLED is True
