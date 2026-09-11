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
import os
import shutil

import pytest

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


# ---------------------------------------------------------------------------
# DEFECT 1 (CRITICAL): stale artifact must never be returned as this run's
# evidence.
# ---------------------------------------------------------------------------

def test_stale_jsonfile_is_not_returned_when_the_run_writes_nothing(monkeypatch, tmp_path):
    stale = tmp_path / "testssl.json"
    stale.write_text("[]")  # old clean report from a prior run

    monkeypatch.setattr(base, "which", lambda name: "/usr/bin/testssl.sh")

    def fake_run_tool(argv, timeout, cwd=None):
        return base.ToolResult(1, "", "boom", False)

    monkeypatch.setattr(base, "run_tool", fake_run_tool)

    raw_path, result = testssl.run("example.com", str(tmp_path), {})
    assert raw_path is None
    assert result.returncode == 1


# ---------------------------------------------------------------------------
# DEFECT 2: parse()/parse_errors() must never convert a parse failure into
# an empty list, and must never let JSONDecodeError/TypeError escape
# uncaught.
# ---------------------------------------------------------------------------

def test_empty_file_raises_parse_error(tmp_path):
    empty = tmp_path / "empty.json"
    empty.write_text("")
    with pytest.raises(base.ParseError):
        testssl.parse(empty, target="site-a")


def test_truncated_json_raises_parse_error(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("[{")
    with pytest.raises(base.ParseError):
        testssl.parse(bad, target="site-a")


def test_non_array_top_level_raises_parse_error(tmp_path):
    bad = tmp_path / "obj-top.json"
    bad.write_text('{"not": "an array"}')
    with pytest.raises(base.ParseError):
        testssl.parse(bad, target="site-a")


def test_entry_wrong_shape_raises_parse_error_not_typeerror(tmp_path):
    bad = tmp_path / "bad-shape.json"
    bad.write_text("[null]")
    with pytest.raises(base.ParseError):
        testssl.parse(bad, target="site-a")


def test_parse_errors_also_raises_on_malformed_input(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json at all")
    with pytest.raises(base.ParseError):
        testssl.parse_errors(bad, target="site-a")


def test_non_string_severity_raises_parse_error_not_attributeerror(tmp_path):
    """DEFECT 2 (MEDIUM): `severity` present but not a string (here an int)
    used to reach `.strip()` on it and raise a raw AttributeError -
    routine's handler would then record error:AttributeError instead of
    naming the real problem."""
    bad = tmp_path / "bad-severity.json"
    bad.write_text('[{"severity":1}]')
    with pytest.raises(base.ParseError):
        testssl.parse(bad, target="site-a")


def test_non_string_severity_raises_in_parse_errors_too(tmp_path):
    bad = tmp_path / "bad-severity.json"
    bad.write_text('[{"severity":1}]')
    with pytest.raises(base.ParseError):
        testssl.parse_errors(bad, target="site-a")


# ---------------------------------------------------------------------------
# MEDIUM defect (installed-toolchain): testssl.sh hard-requires `hexdump`
# ("You need to install hexdump for this program to work.") and fails before
# doing anything else without it. Git for Windows' bundled Git Bash - the
# bash this adapter actually runs testssl.sh under on an operator's machine -
# ships xxd/od but not hexdump; a sibling MSYS2 install commonly does. This
# must be fixed in the adapter's invocation, never by patching the vendored
# testssl.sh script itself.
# ---------------------------------------------------------------------------

def test_hexdump_dir_is_none_when_hexdump_already_resolvable(monkeypatch):
    monkeypatch.setattr(base, "which", lambda name: "/usr/bin/hexdump" if name == "hexdump" else None)
    assert testssl._hexdump_dir() is None


def test_hexdump_dir_finds_an_msys2_style_candidate(monkeypatch, tmp_path):
    msys_bin = tmp_path / "msys64" / "usr" / "bin"
    msys_bin.mkdir(parents=True)
    (msys_bin / "hexdump.exe").write_text("stand-in")

    monkeypatch.setattr(base, "which", lambda name: None)
    monkeypatch.setattr(testssl, "_MSYS2_HEXDUMP_CANDIDATES", (str(msys_bin),))

    assert testssl._hexdump_dir() == str(msys_bin)


def test_hexdump_dir_is_none_when_no_candidate_actually_has_it(monkeypatch, tmp_path):
    empty_bin = tmp_path / "no-hexdump-here"
    empty_bin.mkdir()

    monkeypatch.setattr(base, "which", lambda name: None)
    monkeypatch.setattr(testssl, "_MSYS2_HEXDUMP_CANDIDATES", (str(empty_bin),))

    assert testssl._hexdump_dir() is None


def test_run_prepends_the_hexdump_dir_to_path_for_the_subprocess(monkeypatch, tmp_path, fixture):
    msys_bin = tmp_path / "msys64" / "usr" / "bin"
    msys_bin.mkdir(parents=True)
    (msys_bin / "hexdump.exe").write_text("stand-in")

    monkeypatch.setattr(base, "which",
                         lambda name: "/usr/bin/bash" if name in ("testssl.sh", "testssl") else None)
    monkeypatch.setattr(testssl, "_MSYS2_HEXDUMP_CANDIDATES", (str(msys_bin),))

    original_path = os.environ.get("PATH", "")
    captured = {}

    def fake_run_tool(argv, timeout, cwd=None):
        captured["path_during_run"] = os.environ.get("PATH", "")
        shutil.copy(fixture("testssl.json"), argv[2])
        return base.ToolResult(0, "", "", False)

    monkeypatch.setattr(base, "run_tool", fake_run_tool)

    raw_path, result = testssl.run("example.com", str(tmp_path), {})

    assert raw_path is not None
    assert captured["path_during_run"].startswith(str(msys_bin) + os.pathsep)
    # PATH must be restored afterward - this must never leak into later runs.
    assert os.environ.get("PATH", "") == original_path


def test_run_does_not_touch_path_when_hexdump_is_already_resolvable(monkeypatch, tmp_path, fixture):
    monkeypatch.setattr(
        base, "which",
        lambda name: {"testssl.sh": "/usr/bin/testssl.sh", "hexdump": "/usr/bin/hexdump"}.get(name))

    original_path = os.environ.get("PATH", "")
    captured = {}

    def fake_run_tool(argv, timeout, cwd=None):
        captured["path_during_run"] = os.environ.get("PATH", "")
        shutil.copy(fixture("testssl.json"), argv[2])
        return base.ToolResult(0, "", "", False)

    monkeypatch.setattr(base, "run_tool", fake_run_tool)

    testssl.run("example.com", str(tmp_path), {})

    assert captured["path_during_run"] == original_path


# ---------------------------------------------------------------------------
# CORRECTION (installed-toolchain, second verification pass): bootstrap.ps1
# only ever git-clones testssl.sh on Windows - nothing puts a directly
# executable testssl.sh/testssl on PATH there (unlike bootstrap.sh's
# `ln -sf .../testssl.sh /usr/local/bin/testssl.sh` on Linux). The verified
# working Windows invocation explicitly runs it through bash
# (`bash testssl.sh ...`, with the MSYS2 hexdump dir prepended to PATH) -
# this adapter must build that same argv shape when no directly-executable
# binary is on PATH, and must degrade with a clear, actionable message when
# `hexdump` cannot be found anywhere, rather than ever invoking testssl.sh
# and letting its own bare "You need to install hexdump..." reach an
# operator with no idea what to do about it on Windows.
# ---------------------------------------------------------------------------

def test_resolve_command_prefers_a_native_binary_when_present(monkeypatch):
    monkeypatch.setattr(base, "which",
                         lambda name: "/usr/bin/testssl.sh" if name == "testssl.sh" else None)
    assert testssl._resolve_command() == ["/usr/bin/testssl.sh"]


def test_resolve_command_falls_back_to_bash_plus_the_cloned_script(monkeypatch, tmp_path):
    script = tmp_path / "testssl.sh"
    script.write_text("#!/usr/bin/env bash\n# stand-in")

    monkeypatch.setattr(testssl, "_TESTSSL_SCRIPT_CANDIDATES", (str(script),))
    monkeypatch.setattr(base, "which", lambda name: "/usr/bin/bash" if name == "bash" else None)

    assert testssl._resolve_command() == ["/usr/bin/bash", str(script)]


def test_resolve_command_is_none_when_script_found_but_no_bash(monkeypatch, tmp_path):
    script = tmp_path / "testssl.sh"
    script.write_text("stand-in")

    monkeypatch.setattr(testssl, "_TESTSSL_SCRIPT_CANDIDATES", (str(script),))
    monkeypatch.setattr(base, "which", lambda name: None)

    assert testssl._resolve_command() is None


def test_resolve_command_is_none_when_nothing_is_found(monkeypatch):
    monkeypatch.setattr(testssl, "_TESTSSL_SCRIPT_CANDIDATES", ())
    monkeypatch.setattr(base, "which", lambda name: None)

    assert testssl._resolve_command() is None


def test_is_available_true_via_bash_and_the_cloned_script(monkeypatch, tmp_path):
    script = tmp_path / "testssl.sh"
    script.write_text("stand-in")

    monkeypatch.setattr(testssl, "_TESTSSL_SCRIPT_CANDIDATES", (str(script),))
    monkeypatch.setattr(base, "which", lambda name: "/usr/bin/bash" if name == "bash" else None)

    assert testssl.is_available() is True


def test_run_uses_bash_and_script_argv_when_no_native_binary_is_found(monkeypatch, tmp_path, fixture):
    script = tmp_path / "testssl.sh"
    script.write_text("stand-in")

    monkeypatch.setattr(testssl, "_TESTSSL_SCRIPT_CANDIDATES", (str(script),))
    monkeypatch.setattr(
        base, "which",
        lambda name: {"bash": "/usr/bin/bash", "hexdump": "/usr/bin/hexdump"}.get(name))

    captured = {}

    def fake_run_tool(argv, timeout, cwd=None):
        captured["argv"] = argv
        assert argv[2] == "--jsonfile"
        shutil.copy(fixture("testssl.json"), argv[3])
        return base.ToolResult(0, "", "", False)

    monkeypatch.setattr(base, "run_tool", fake_run_tool)

    raw_path, result = testssl.run("example.com", str(tmp_path), {})

    assert raw_path == tmp_path / "testssl.json"
    assert captured["argv"][0] == "/usr/bin/bash"
    assert captured["argv"][1] == str(script)


def test_run_declines_with_a_clear_message_when_hexdump_is_missing_everywhere(monkeypatch, tmp_path):
    monkeypatch.setattr(base, "which",
                         lambda name: "/usr/bin/testssl.sh" if name == "testssl.sh" else None)
    monkeypatch.setattr(testssl, "_MSYS2_HEXDUMP_CANDIDATES", ())

    called = []
    monkeypatch.setattr(base, "run_tool", lambda *a, **k: called.append(1))

    raw_path, result = testssl.run("example.com", str(tmp_path), {})

    # testssl.sh must never even be invoked - its own bare error message
    # tells a Windows operator nothing about what to do.
    assert called == []
    assert raw_path is None
    assert "hexdump" in result.stderr.lower()
