"""T-0044 on native Windows: `crew_unattended.py` refuses at its platform
check, before anything is read or sealed, and its start-up sweep of stale
sealed directories sends no signal there -- `os.kill(pid, 0)` on Windows is
CTRL_C_EVENT to the console group (the G2 landing's Windows CI was
interrupted by exactly that). These cases run on every platform: they set
`_os_name` to "nt" rather than needing a Windows host.
"""
import os

import context  # noqa: F401  pylint: disable=unused-import
import crew_unattended as cu


def _no_kill(monkeypatch):
    killed = []
    monkeypatch.setattr(cu.os, "kill", lambda *a: killed.append(a))
    return killed


def test_windows_sweep_sends_no_signal_and_removes_nothing(tmp_path, monkeypatch):
    killed = _no_kill(monkeypatch)
    monkeypatch.setattr(cu, "_os_name", lambda: "nt")
    stale = tmp_path / "crew-sealed-999999-x"
    stale.mkdir()

    assert (cu.sweep_stale_sealed(str(tmp_path)), killed, stale.is_dir()) == ([], [], True)


def test_windows_check_refuses_at_platform_and_runs_nothing_else(tmp_path, monkeypatch, capsys):
    killed = _no_kill(monkeypatch)
    monkeypatch.setattr(cu, "_os_name", lambda: "nt")
    monkeypatch.setattr(cu, "_run", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("a Windows check ran a process")))

    rows, launch = cu.run_checks(str(tmp_path), None)

    assert (launch, rows[0]["check"], rows[0]["state"], killed) == (
        None, "platform", cu.UNKNOWN, [])
    assert "native Windows" in rows[0]["why"]
    assert all(r["state"] == "not run" for r in rows[1:] if r["check"] != "note")


def test_windows_check_cli_exits_1(tmp_path, monkeypatch, capsys):
    _no_kill(monkeypatch)
    monkeypatch.setattr(cu, "_os_name", lambda: "nt")

    code = cu.main(["check", "--root", str(tmp_path)])

    assert (code, "native Windows" in capsys.readouterr().out) == (1, True)
    assert os.listdir(str(tmp_path)) == []
