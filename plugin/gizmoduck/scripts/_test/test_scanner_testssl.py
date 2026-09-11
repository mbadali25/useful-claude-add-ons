"""testssl adapter tests.

The fixture (fixtures/testssl.json) carries one entry per real testssl.sh
severity value plus one with a missing severity, so every handling path in
the adapter gets exercised:

  INFO, OK           -> info findings (OK is a clean pass, not a fallback)
  LOW, MEDIUM        -> low / medium findings
  HIGH, CRITICAL     -> high / critical findings, both carrying a CVE
  WARN, FATAL        -> tool errors, NEVER findings about the target
  null severity      -> falls back to info, tagged severity-assigned

The WARN/FATAL split is the one that matters most: testssl mixes per-check
scan errors into the same jsonfile array as real findings, and mapping WARN
or FATAL as if they were severities would make a broken scan (e.g. a stale
CRL fetch, a refused connection) read as a vulnerability in the target.
"""
from scanners import base, testssl


def _load(fixture):
    return testssl.parse(fixture("testssl.json"), target="site-a")


def test_finding_count_excludes_warn_and_fatal(fixture):
    findings = _load(fixture)
    # 9 fixture entries - 2 (WARN, FATAL) = 7 real findings
    assert len(findings) == 7


def test_ok_and_info_map_to_info_and_are_recognized(fixture):
    findings = _load(fixture)
    by_id = {f["template_id"]: f for f in findings}
    scan_time = by_id["testssl:scanTime"]
    heartbleed = by_id["testssl:heartbleed"]
    assert scan_time["severity"] == 0 and scan_time["severity_name"] == "info"
    assert heartbleed["severity"] == 0 and heartbleed["severity_name"] == "info"
    # OK is a confident, documented mapping - not a fallback - so neither
    # finding should be flagged as a heuristic severity assignment.
    assert "severity-assigned" not in scan_time["tags"]
    assert "severity-assigned" not in heartbleed["tags"]


def test_low_and_medium_map_correctly(fixture):
    findings = _load(fixture)
    by_id = {f["template_id"]: f for f in findings}
    assert by_id["testssl:cert_expiration"]["severity"] == 1
    assert by_id["testssl:POODLE_SSL"]["severity"] == 2


def test_high_and_critical_carry_their_cve(fixture):
    findings = _load(fixture)
    by_id = {f["template_id"]: f for f in findings}
    robot = by_id["testssl:ROBOT"]
    breach = by_id["testssl:BREACH"]
    assert robot["severity"] == 3 and robot["severity_name"] == "high"
    assert robot["cve"] == ["CVE-2017-13099"]
    assert breach["severity"] == 4 and breach["severity_name"] == "critical"
    assert breach["cve"] == ["CVE-2013-3587"]


def test_null_severity_falls_back_to_info_and_is_flagged(fixture):
    findings = _load(fixture)
    by_id = {f["template_id"]: f for f in findings}
    unknown = by_id["testssl:cert_random_check"]
    assert unknown["severity"] == 0
    assert "severity-assigned" in unknown["tags"]


def test_template_id_is_namespaced_by_tool(fixture):
    findings = _load(fixture)
    assert all(f["template_id"].startswith("testssl:") for f in findings)


def test_target_is_set_from_the_argument(fixture):
    findings = _load(fixture)
    assert all(f["target"] == "site-a" for f in findings)


def test_warn_and_fatal_never_appear_as_findings(fixture):
    findings = _load(fixture)
    ids = {f["template_id"] for f in findings}
    assert "testssl:cert_chain_of_trust" not in ids
    assert "testssl:connection" not in ids


def test_warn_and_fatal_are_surfaced_as_tool_errors(fixture):
    """The one test that matters most in this task.

    routine (Task 15) needs a way to record these in the run manifest instead
    of silently dropping them - parse() alone throws them away by design, so
    the adapter must expose a second, additive entry point routine can call.
    """
    errors = testssl.parse_errors(fixture("testssl.json"), target="site-a")
    assert len(errors) == 2
    by_id = {e["id"]: e for e in errors}

    warn = by_id["cert_chain_of_trust"]
    assert warn["severity"] == "WARN"
    assert warn["target"] == "site-a"
    assert warn["tool"] == "testssl"
    assert "revocation" in warn["message"]

    fatal = by_id["connection"]
    assert fatal["severity"] == "FATAL"
    assert "Connection refused" in fatal["message"]

    # Errors are not findings: none of the 14+ finding keys leak in, and in
    # particular there is no `severity_name`/int severity band to confuse a
    # report renderer that expects the finding shape.
    assert "severity_name" not in warn
    assert "template_id" not in warn


def test_run_returns_none_path_and_a_toolresult_when_binary_missing(monkeypatch, tmp_path):
    """run() must satisfy the team-standardized (raw_path, ToolResult)
    contract even when testssl.sh isn't installed - there is no subprocess
    in that case, but routine still needs a ToolResult to record the cell
    as an error rather than treating it as a run that produced nothing."""
    monkeypatch.setattr(base, "which", lambda name: None)
    raw_path, result = testssl.run("example.com", str(tmp_path), {})
    assert raw_path is None
    assert isinstance(result, base.ToolResult)
    assert result.returncode != 0
    assert result.timed_out is False


def test_run_returns_the_jsonfile_path_and_toolresult_on_success(monkeypatch, tmp_path, fixture):
    """A stand-in binary that copies the fixture into place, exercising the
    real argv-building and success path without needing testssl.sh itself."""
    import shutil as _shutil

    fake_bin = tmp_path / "fake-testssl.sh"
    fake_bin.write_text("stand-in, never executed directly in this test")
    monkeypatch.setattr(base, "which", lambda name: str(fake_bin))

    def fake_run_tool(argv, timeout, cwd=None):
        # argv[2] is the --jsonfile path per the command this adapter builds
        assert argv[1] == "--jsonfile"
        _shutil.copy(fixture("testssl.json"), argv[2])
        return base.ToolResult(0, "", "", False)

    monkeypatch.setattr(base, "run_tool", fake_run_tool)

    raw_path, result = testssl.run("example.com", str(tmp_path), {})
    assert raw_path == tmp_path / "testssl.json"
    assert result.returncode == 0 and result.timed_out is False
    assert testssl.parse(raw_path, target="site-a")  # the file is really usable
