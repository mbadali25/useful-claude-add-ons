"""One tool lookup rule for every gizmoduck adapter (L-0684).

Order: the tool's own override variable, then the tool home
(GIZMODUCK_HOME, default ~/.local/share/gizmoduck off Windows), then PATH,
then %LOCALAPPDATA%. A set override that does not resolve disables the tool;
it never falls through to another install. Every tool here is an empty
executable file under tmp_path; nothing is installed or run, and the autouse
conftest fixture keeps the real tool home out of reach.
"""
import os
import sys
from pathlib import Path

import pytest

import gizmoduck
from scanners import base, nikto, testssl, zap

POSIX_ONLY = pytest.mark.skipif(os.name == "nt", reason="os.access X_OK is true for any file on Windows")


def _exe(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(0o755)
    return path


@pytest.fixture
def path_dir(tmp_path, monkeypatch):
    """An empty directory that is the whole of PATH."""
    d = tmp_path / "pathbin"
    d.mkdir()
    monkeypatch.setenv("PATH", str(d))
    return d


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A fresh tool home, set through GIZMODUCK_HOME."""
    h = tmp_path / "toolhome"
    h.mkdir()
    monkeypatch.setenv("GIZMODUCK_HOME", str(h))
    return h


@pytest.fixture
def no_localappdata(monkeypatch):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)


# ---- tool_home and which ------------------------------------------------------

def test_tool_home_uses_gizmoduck_home_when_set(monkeypatch, tmp_path):
    monkeypatch.setenv("GIZMODUCK_HOME", str(tmp_path / "gh"))
    assert base.tool_home() == tmp_path / "gh"


@pytest.mark.parametrize("xdg", [True, False])
def test_tool_home_defaults_under_xdg_data_home_then_local_share(monkeypatch, tmp_path, xdg):
    monkeypatch.setattr(base.os, "name", "posix")
    monkeypatch.delenv("GIZMODUCK_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    if xdg:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
        assert base.tool_home() == tmp_path / "xdg" / "gizmoduck"
    else:
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.setattr(base.Path, "home", classmethod(lambda cls: tmp_path / "h"))
        assert base.tool_home() == tmp_path / "h" / ".local" / "share" / "gizmoduck"


def test_tool_home_is_none_on_windows_without_gizmoduck_home(monkeypatch):
    monkeypatch.setattr(base.os, "name", "nt")
    monkeypatch.delenv("GIZMODUCK_HOME", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", "/somewhere")
    assert base.tool_home() is None


def test_tool_home_is_read_at_call_time(monkeypatch, tmp_path):
    monkeypatch.setenv("GIZMODUCK_HOME", str(tmp_path / "first"))
    assert base.tool_home() == tmp_path / "first"
    monkeypatch.setenv("GIZMODUCK_HOME", str(tmp_path / "second"))
    assert base.tool_home() == tmp_path / "second"


def test_which_prefers_tool_home_bin_over_path(home, path_dir):
    _exe(path_dir / "trivy")
    mine = _exe(home / "bin" / "trivy")
    assert base.which("trivy") == str(mine)


def test_which_falls_back_to_path(home, path_dir):
    on_path = _exe(path_dir / "trivy")
    assert Path(base.which("trivy")) == on_path


@POSIX_ONLY
def test_which_ignores_a_non_executable_file_in_tool_home_bin(home, path_dir):
    on_path = _exe(path_dir / "trivy")
    stray = home / "bin" / "trivy"
    stray.parent.mkdir(parents=True)
    stray.write_text("not executable")
    stray.chmod(0o644)
    assert Path(base.which("trivy")) == on_path


def test_which_tries_windows_extensions_in_tool_home(home, path_dir, monkeypatch):
    bat = _exe(home / "bin" / "dependency-check.bat")
    monkeypatch.setattr(base, "_windows", lambda: True)
    monkeypatch.setenv("PATHEXT", os.pathsep.join([".COM", ".EXE", ".BAT", ".CMD"]))
    assert base.which("dependency-check") == str(bat)


def test_empty_override_disables_the_tool(monkeypatch, path_dir):
    _exe(path_dir / "nikto")
    _exe(path_dir / "perl")
    monkeypatch.setenv("GIZMODUCK_NIKTO_PL", "")
    assert nikto.is_available() is False


def test_windows_tool_home_does_not_run_a_shell_script_directly(home, path_dir, monkeypatch):
    _exe(home / "bin" / "testssl.sh")
    bash = _exe(path_dir / "bash")
    monkeypatch.setattr(base, "_windows", lambda: True)
    monkeypatch.setenv("PATHEXT", os.pathsep.join([".COM", ".EXE", ".BAT", ".CMD"]))
    assert base.which("testssl.sh") is None or not base.which("testssl.sh").startswith(str(home))
    script = _exe(home / "testssl.sh" / "testssl.sh")
    assert testssl._resolve_command() == [str(bash), str(script)]


@POSIX_ONLY
def test_zap_non_executable_wrapper_is_not_a_route(monkeypatch, tmp_path, path_dir):
    java = _exe(path_dir / "java")
    zdir = tmp_path / "myzap"
    zdir.mkdir()
    for name in ("zap.sh", "zap.bat"):
        (zdir / name).write_text("not runnable")
        (zdir / name).chmod(0o644)
    jar = zdir / "zap-2.17.0.jar"
    jar.write_text("jar")
    monkeypatch.setenv("GIZMODUCK_ZAP_HOME", str(zdir))
    assert zap._resolve_zap_command() == [str(java), "-jar", str(jar)]


def test_testssl_puts_tool_home_hexdump_on_its_path(home, path_dir):
    _exe(home / "bin" / "hexdump")
    assert testssl._hexdump_dir() == str(home / "bin")
    _exe(path_dir / "hexdump")
    _exe(home / "bin" / "hexdump")
    assert testssl._hexdump_dir() == str(home / "bin")  # tool home wins, still not on PATH


def test_testssl_hexdump_already_on_path_needs_no_prepend(path_dir):
    _exe(path_dir / "hexdump")
    assert testssl._hexdump_dir() is None


def test_override_states_unset_ok_broken(monkeypatch, tmp_path):
    monkeypatch.delenv("GIZMODUCK_X", raising=False)
    assert base.override("GIZMODUCK_X", base.existing_file).state == base.UNSET
    monkeypatch.setenv("GIZMODUCK_X", "")
    assert base.override("GIZMODUCK_X", base.existing_file).state == base.BROKEN
    real = tmp_path / "x.pl"
    real.write_text("x")
    monkeypatch.setenv("GIZMODUCK_X", str(real))
    ok = base.override("GIZMODUCK_X", base.existing_file)
    assert (ok.state, ok.found) == (base.OK, str(real))
    monkeypatch.setenv("GIZMODUCK_X", str(tmp_path / "gone.pl"))
    broken = base.override("GIZMODUCK_X", base.existing_file)
    assert (broken.state, broken.value, broken.found) == (base.BROKEN, str(tmp_path / "gone.pl"), None)


def test_override_that_cannot_be_checked_is_broken_not_unset(monkeypatch):
    def boom(_path):
        raise PermissionError("denied")
    monkeypatch.setenv("GIZMODUCK_X", "/somewhere")
    assert base.override("GIZMODUCK_X", boom).state == base.BROKEN


# ---- ZAP ----------------------------------------------------------------------

def test_zap_override_beats_path(monkeypatch, tmp_path, path_dir):
    _exe(path_dir / "zap.sh")
    _exe(path_dir / "zap.bat")
    mine = _exe(tmp_path / "myzap" / "zap.sh")
    _exe(tmp_path / "myzap" / "zap.bat")
    monkeypatch.setenv("GIZMODUCK_ZAP_HOME", str(tmp_path / "myzap"))
    assert zap._resolve_zap_command()[0] in (str(mine), str(tmp_path / "myzap" / "zap.bat"))
    assert Path(zap._resolve_zap_command()[0]).parent == tmp_path / "myzap"


def test_zap_override_finds_wrapper_not_only_jar(monkeypatch, tmp_path, path_dir):
    _exe(tmp_path / "myzap" / "ZAP_2.17.0" / "zap.sh")
    _exe(tmp_path / "myzap" / "ZAP_2.17.0" / "zap.bat")
    monkeypatch.setenv("GIZMODUCK_ZAP_HOME", str(tmp_path / "myzap"))
    command = zap._resolve_zap_command()
    assert command is not None and len(command) == 1
    assert Path(command[0]).parent == tmp_path / "myzap" / "ZAP_2.17.0"


def test_zap_override_jar_runs_with_java(monkeypatch, tmp_path, path_dir):
    java = _exe(path_dir / "java")
    jar = tmp_path / "myzap" / "zap-2.17.0.jar"
    jar.parent.mkdir()
    jar.write_text("jar")
    monkeypatch.setenv("GIZMODUCK_ZAP_HOME", str(tmp_path / "myzap"))
    assert zap._resolve_zap_command() == [str(java), "-jar", str(jar)]


def test_zap_broken_override_is_unavailable_and_does_not_fall_through(monkeypatch, tmp_path, path_dir):
    _exe(path_dir / "zap.sh")
    _exe(path_dir / "zap.bat")
    (tmp_path / "empty").mkdir()
    monkeypatch.setenv("GIZMODUCK_ZAP_HOME", str(tmp_path / "empty"))
    assert zap.is_available() is False
    assert zap.zap_override().state == base.BROKEN


def test_zap_tool_home_beats_path(home, path_dir):
    _exe(path_dir / "zap.sh")
    _exe(path_dir / "zap.bat")
    _exe(home / "zap" / "zap.sh")
    _exe(home / "zap" / "zap.bat")
    assert Path(zap._resolve_zap_command()[0]).parent == home / "zap"


# ---- nikto --------------------------------------------------------------------

def test_nikto_override_beats_path(monkeypatch, tmp_path, path_dir):
    _exe(path_dir / "nikto")
    perl = _exe(path_dir / "perl")
    pl = _exe(tmp_path / "mynikto" / "nikto.pl")
    monkeypatch.setenv("GIZMODUCK_NIKTO_PL", str(pl))
    assert nikto._resolve_prefix() == [str(perl), str(pl)]


def test_nikto_broken_override_is_unavailable_and_does_not_fall_through(monkeypatch, tmp_path, path_dir):
    _exe(path_dir / "nikto")
    _exe(path_dir / "perl")
    monkeypatch.setenv("GIZMODUCK_NIKTO_PL", str(tmp_path / "gone" / "nikto.pl"))
    assert nikto.is_available() is False
    assert nikto._resolve_argv("https://example.test", str(tmp_path / "o.csv")) is None


def test_nikto_tool_home_script_is_found_with_perl(home, path_dir):
    _exe(path_dir / "nikto")
    perl = _exe(path_dir / "perl")
    pl = _exe(home / "nikto" / "program" / "nikto.pl")
    assert nikto._resolve_prefix() == [str(perl), str(pl)]


def test_nikto_reads_the_override_at_call_time(monkeypatch, tmp_path, path_dir):
    # The module was imported long before this test set the variable.
    perl = _exe(path_dir / "perl")
    pl = _exe(tmp_path / "late" / "nikto.pl")
    assert nikto.is_available() is False
    monkeypatch.setenv("GIZMODUCK_NIKTO_PL", str(pl))
    assert nikto._resolve_prefix() == [str(perl), str(pl)]


@pytest.mark.parametrize("step", ["override", "tool_home", "path", "localappdata", "none"])
def test_nikto_is_available_agrees_with_resolve_argv(monkeypatch, tmp_path, path_dir, home, step):
    _exe(path_dir / "perl")
    if step == "override":
        monkeypatch.setenv("GIZMODUCK_NIKTO_PL", str(_exe(tmp_path / "o" / "nikto.pl")))
    elif step == "tool_home":
        _exe(home / "nikto" / "program" / "nikto.pl")
    elif step == "path":
        _exe(path_dir / "nikto")
    elif step == "localappdata":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "lad"))
        _exe(tmp_path / "lad" / "Programs" / "nikto" / "program" / "nikto.pl")
    argv = nikto._resolve_argv("https://example.test", str(tmp_path / "o.csv"))
    assert nikto.is_available() is (argv is not None)
    assert (argv is None) is (step == "none")


# ---- testssl ------------------------------------------------------------------

def test_testssl_override_beats_path(monkeypatch, tmp_path, path_dir):
    _exe(path_dir / "testssl.sh")
    bash = _exe(path_dir / "bash")
    script = _exe(tmp_path / "mine" / "testssl.sh")
    monkeypatch.setenv("GIZMODUCK_TESTSSL_SH", str(script))
    assert testssl._resolve_command() == [str(bash), str(script)]


def test_testssl_broken_override_is_unavailable_and_does_not_fall_through(monkeypatch, tmp_path, path_dir):
    _exe(path_dir / "testssl.sh")
    _exe(path_dir / "bash")
    monkeypatch.setenv("GIZMODUCK_TESTSSL_SH", str(tmp_path / "gone.sh"))
    assert testssl.is_available() is False


def test_testssl_tool_home_script_is_found_with_bash(home, path_dir):
    _exe(path_dir / "testssl.sh")
    bash = _exe(path_dir / "bash")
    script = _exe(home / "testssl.sh" / "testssl.sh")
    assert testssl._resolve_command() == [str(bash), str(script)]


# ---- nuclei -------------------------------------------------------------------

def test_find_nuclei_prefers_tool_home_bin(home, path_dir):
    _exe(path_dir / "nuclei")
    mine = _exe(home / "bin" / "nuclei")
    assert gizmoduck.find_nuclei() == str(mine)


# ---- the last step ------------------------------------------------------------

@pytest.mark.parametrize("tool", ["zap", "nikto", "testssl"])
def test_localappdata_is_still_the_last_step(monkeypatch, tmp_path, path_dir, tool):
    lad = tmp_path / "lad"
    monkeypatch.setenv("LOCALAPPDATA", str(lad))
    interp = {"zap": "java", "nikto": "perl", "testssl": "bash"}[tool]
    interp_path = _exe(path_dir / interp)
    if tool == "zap":
        jar = lad / "Programs" / "zap" / "ZAP_2.17.0" / "zap-2.17.0.jar"
        jar.parent.mkdir(parents=True)
        jar.write_text("jar")
        assert zap._resolve_zap_command() == [str(interp_path), "-jar", str(jar)]
    elif tool == "nikto":
        pl = _exe(lad / "Programs" / "nikto" / "program" / "nikto.pl")
        assert nikto._resolve_prefix() == [str(interp_path), str(pl)]
    else:
        script = _exe(lad / "Programs" / "testssl.sh" / "testssl.sh")
        assert testssl._resolve_command() == [str(interp_path), str(script)]


def test_suite_never_sees_the_real_tool_home():
    # The autouse fixture in conftest.py: an empty GIZMODUCK_HOME, no overrides.
    home = base.tool_home()
    assert home is not None and not any(home.iterdir())
    for var in ("GIZMODUCK_ZAP_HOME", "GIZMODUCK_NIKTO_PL", "GIZMODUCK_TESTSSL_SH", "XDG_DATA_HOME"):
        assert var not in os.environ


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
