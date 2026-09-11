import pytest

from scanners import base, sqlmap


# --- gating: the confirm token and the injection-point check --------------
#
# Cross-adapter contract: run() -> (raw_path | None, ToolResult) always, even
# on a declined gate. A decline is signalled via result.returncode is None -
# never an int - so routine.py can tell "we chose not to fire" (skipped-
# active) apart from a real failure (a real int returncode, or the -1
# sentinel base.run_tool uses for a timeout/missing binary).

def test_run_refuses_without_confirm_token(monkeypatch, fixture):
    called = []
    monkeypatch.setattr(base, "run_tool", lambda *a, **k: called.append(1))

    raw_path, result = sqlmap.run(
        "http://example.test/page?id=1", str(fixture("sqlmap-session/confirmed")), {})

    # The refusal must happen before any subprocess is built - sqlmap sends
    # real attack traffic, so an absent token must send zero bytes, not just
    # get flagged after the fact.
    assert called == []
    assert raw_path is None
    assert result.returncode is None
    assert isinstance(result, base.ToolResult)


def test_run_refuses_falsy_confirm_token(monkeypatch, fixture):
    called = []
    monkeypatch.setattr(base, "run_tool", lambda *a, **k: called.append(1))

    raw_path, result = sqlmap.run(
        "http://example.test/page?id=1",
        str(fixture("sqlmap-session/confirmed")), {"confirm": False})

    assert called == []
    assert raw_path is None
    assert result.returncode is None


def test_run_refuses_a_target_with_no_injection_point(monkeypatch):
    called = []
    monkeypatch.setattr(base, "run_tool", lambda *a, **k: called.append(1))

    raw_path, result = sqlmap.run(
        "http://example.test/page", "/tmp/out", {"confirm": "APPROVED-BY-ME"})

    assert called == []
    assert raw_path is None
    assert result.returncode is None


def test_declined_result_is_distinguishable_from_a_real_error(monkeypatch):
    # A real failure (e.g. the binary missing) still gets an int returncode
    # from base.run_tool (its own -1 sentinel) - only a declined gate ever
    # produces returncode is None. The two must never be confused.
    monkeypatch.setattr(
        base, "run_tool",
        lambda *a, **k: base.ToolResult(-1, "", "sqlmap: command not found", False))

    _, declined = sqlmap.run("http://example.test/page?id=1", "/tmp/out", {})
    _, real_error = sqlmap.run(
        "http://example.test/page?id=1", "/tmp/out", {"confirm": "APPROVED-BY-ME"})

    assert declined.returncode is None
    assert real_error.returncode == -1
    assert declined.returncode is not real_error.returncode


def test_run_builds_the_expected_argv_when_confirmed(monkeypatch, tmp_path):
    captured = {}

    def fake_run_tool(argv, timeout, cwd=None):
        captured["argv"] = argv
        captured["timeout"] = timeout
        (tmp_path / "log").write_text("no injection point found\n")
        return base.ToolResult(0, "", "", False)

    monkeypatch.setattr(base, "run_tool", fake_run_tool)

    raw_path, result = sqlmap.run("http://example.test/page?id=1", str(tmp_path),
                                  {"confirm": "APPROVED-BY-ME", "time_limit": 120})

    assert result.returncode == 0
    assert raw_path == str(tmp_path)
    argv = captured["argv"]
    assert argv[0] == "sqlmap"
    assert "-u" in argv and "http://example.test/page?id=1" in argv
    assert "--batch" in argv
    assert "--time-limit=120" in argv
    assert "--output-dir=%s" % tmp_path in argv


def test_run_returns_none_path_when_timed_out(monkeypatch, tmp_path):
    monkeypatch.setattr(
        base, "run_tool",
        lambda *a, **k: base.ToolResult(-1, "", "", True))

    raw_path, result = sqlmap.run("http://example.test/page?id=1", str(tmp_path),
                                  {"confirm": "APPROVED-BY-ME"})

    assert raw_path is None
    assert result.timed_out is True


def test_run_returns_none_path_when_no_session_artifacts_were_written(monkeypatch, tmp_path):
    # sqlmap can exit 0 having written nothing (spec 13.9) - success is
    # decided by whether a session actually landed on disk, not the exit code.
    monkeypatch.setattr(base, "run_tool", lambda *a, **k: base.ToolResult(0, "", "", False))

    raw_path, result = sqlmap.run("http://example.test/page?id=1", str(tmp_path),
                                  {"confirm": "APPROVED-BY-ME"})

    assert raw_path is None
    assert result.returncode == 0


# --- CRITICAL defect: run() and parse() must agree on usable evidence -----
#
# run() previously accepted `log` OR `session.sqlite` as proof a session
# landed, while parse() only ever reads `log`. That let a session sqlmap
# interrupted before it wrote its log (e.g. --time-limit firing mid-request)
# come back as returncode 0, a non-null raw_path, and parse() silently
# returning [] - a scan that was cut short presented as a clean target. The
# fix must turn that combination into an error, never an empty list.

def test_run_then_parse_on_interrupted_session_is_an_error_not_a_clean_scan(
        monkeypatch, tmp_path):
    # sqlmap wrote its HashDB cache (proof it started) but was cut off
    # before persisting the human-readable `log` sqlmap.parse() reads.
    def fake_run_tool(argv, timeout, cwd=None):
        (tmp_path / "session.sqlite").write_bytes(b"fake-hashdb-zlib-pickle-blob")
        return base.ToolResult(0, "", "", False)

    monkeypatch.setattr(base, "run_tool", fake_run_tool)

    raw_path, result = sqlmap.run("http://example.test/page?id=1", str(tmp_path),
                                  {"confirm": "APPROVED-BY-ME"})

    # run() still reports "a session happened" - that part of the contract
    # doesn't change; it's what parse() does with it that must change.
    assert raw_path is not None
    assert result.returncode == 0

    with pytest.raises(base.ParseError):
        sqlmap.parse(raw_path, "http://example.test/page?id=1")


def test_session_sqlite_without_log_is_a_parse_error(fixture):
    with pytest.raises(base.ParseError):
        sqlmap.parse(fixture("sqlmap-session/interrupted"),
                     "http://example.test/page?id=1")


# --- HIGH defect: the session directory must match the requested host -----
#
# _find_session_dir() previously returned the first alphabetical child under
# an --output-dir root that merely *contained* artifacts, with no check that
# it belonged to the target being parsed. That misattributes findings to a
# host that was never tested, and lets an alphabetically-earlier empty
# session hide a later vulnerable one.

def test_parse_does_not_misattribute_an_unrelated_hosts_session(fixture):
    # sqlmap-session/ holds "confirmed" and "empty" children from other
    # tests - neither is named after this host, so nothing here belongs to
    # it. Picking either one (as the old alphabetical-first logic did) would
    # attribute injection findings to a host that was never scanned.
    findings = sqlmap.parse(fixture("sqlmap-session"), "http://unrelated.example/?id=1")
    assert findings == []


def test_parse_picks_the_matching_host_not_the_alphabetically_first_one(fixture):
    # alpha.example sorts before victim.example and has its own confirmed
    # injection (on a *different* parameter) - if the session directory
    # were still picked alphabetically, we'd get alpha's "user" finding
    # instead of victim's "id" finding, or victim's real vulnerability would
    # never surface at all.
    findings = sqlmap.parse(fixture("sqlmap-session/multi-host"),
                            "http://victim.example/page?id=1")

    assert len(findings) == 1
    assert findings[0]["host"] == "victim.example"
    assert findings[0]["template_id"].startswith("sqlmap:id-get-")


# --- parsing: confirmed session yields findings, empty session yields none -

def test_confirmed_session_yields_two_findings_high_and_critical(fixture):
    findings = sqlmap.parse(fixture("sqlmap-session/confirmed"),
                            "http://example.test/page?id=1")

    assert len(findings) == 2
    severities = sorted(f["severity"] for f in findings)
    assert severities == [3, 4]  # boolean-based blind (high), UNION (critical)

    for f in findings:
        assert f["template_id"].startswith("sqlmap:id-get-")
        assert f["target"] == "http://example.test/page?id=1"
        assert f["tool"] == "sqlmap"
        assert f["host"] == "example.test"

    union_finding = next(f for f in findings if f["severity"] == 4)
    assert "union" in union_finding["template_id"]
    assert union_finding["severity_name"] == "critical"

    blind_finding = next(f for f in findings if f["severity"] == 3)
    assert blind_finding["severity_name"] == "high"


def test_empty_session_yields_zero_findings_not_a_low_severity_entry(fixture):
    # Probed-and-negative parameters are never persisted - a clean run must
    # come back as an empty list, never a synthetic "info: nothing found".
    findings = sqlmap.parse(fixture("sqlmap-session/empty"),
                            "http://example.test/page?id=1")
    assert findings == []


def test_parse_accepts_an_output_dir_root_and_finds_the_host_subfolder(fixture, tmp_path):
    # run() is given the --output-dir root; sqlmap creates the per-host
    # folder underneath it. parse() must be able to take that same root.
    root = tmp_path / "output"
    hostdir = root / "example.test"
    hostdir.mkdir(parents=True)
    (hostdir / "log").write_text((fixture("sqlmap-session/confirmed") / "log").read_text())

    findings = sqlmap.parse(root, "http://example.test/page?id=1")
    assert len(findings) == 2


def test_missing_log_yields_zero_findings(tmp_path):
    # No log at all (session never ran, or nothing survived) is still zero
    # findings, not an error and not a placeholder finding.
    empty_dir = tmp_path / "nothing-here"
    empty_dir.mkdir()
    assert sqlmap.parse(empty_dir, "http://example.test/page?id=1") == []


def test_exit_code_is_not_a_parameter_parse_can_even_consult():
    # parse()'s signature has no returncode slot - the exit-code trap the
    # plan warns about (sqlmap exits 0 whether or not anything was found)
    # cannot leak into the finding count even by accident.
    import inspect
    params = inspect.signature(sqlmap.parse).parameters
    assert "returncode" not in params and "exit_code" not in params


# --- registry protocol conformance -----------------------------------------

def test_module_constants():
    assert sqlmap.NAME == "sqlmap"
    assert sqlmap.KINDS == ["web"]
    assert sqlmap.ACTIVE is True
    assert sqlmap.ACTIVE_OPTS == []
    assert sqlmap.DEFAULT_ENABLED is False
