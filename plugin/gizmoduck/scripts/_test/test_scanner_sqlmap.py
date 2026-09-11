import pytest

from scanners import base, sqlmap


# --- gating: the confirm token and the injection-point check --------------

def test_run_refuses_without_confirm_token(monkeypatch, fixture):
    called = []
    monkeypatch.setattr(base, "run_tool", lambda *a, **k: called.append(1))

    with pytest.raises(sqlmap.ConfirmationRequired):
        sqlmap.run("http://example.test/page?id=1", str(fixture("sqlmap-session/confirmed")), {})

    # The refusal must happen before any subprocess is built - sqlmap sends
    # real attack traffic, so an absent token must send zero bytes, not just
    # get flagged after the fact.
    assert called == []


def test_run_refuses_falsy_confirm_token(monkeypatch, fixture):
    called = []
    monkeypatch.setattr(base, "run_tool", lambda *a, **k: called.append(1))

    with pytest.raises(sqlmap.ConfirmationRequired):
        sqlmap.run("http://example.test/page?id=1",
                    str(fixture("sqlmap-session/confirmed")), {"confirm": False})

    assert called == []


def test_run_refuses_a_target_with_no_injection_point(monkeypatch):
    called = []
    monkeypatch.setattr(base, "run_tool", lambda *a, **k: called.append(1))

    with pytest.raises(sqlmap.ConfirmationRequired):
        sqlmap.run("http://example.test/page", "/tmp/out", {"confirm": "APPROVED-BY-ME"})

    assert called == []


def test_run_builds_the_expected_argv_when_confirmed(monkeypatch):
    captured = {}

    def fake_run_tool(argv, timeout, cwd=None):
        captured["argv"] = argv
        captured["timeout"] = timeout
        return base.ToolResult(0, "", "", False)

    monkeypatch.setattr(base, "run_tool", fake_run_tool)

    result = sqlmap.run("http://example.test/page?id=1", "/tmp/out",
                        {"confirm": "APPROVED-BY-ME", "time_limit": 120})

    assert result.returncode == 0
    argv = captured["argv"]
    assert argv[0] == "sqlmap"
    assert "-u" in argv and "http://example.test/page?id=1" in argv
    assert "--batch" in argv
    assert "--time-limit=120" in argv
    assert "--output-dir=/tmp/out" in argv


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
