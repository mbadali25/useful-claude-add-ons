"""T-0049: `crew_autopilot.py next` leaves a ticket another runner holds alone.

On the fixture `test_crew_autopilot.py` uses; markers are written through
`crew_inflight` itself, never by hand, except the one test that needs an
unreadable marker. The beat loop is never started (`_start_loop` replaced).
"""
import datetime
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autopilot
import crew_holder
import crew_inflight
from review_fixtures import git
from test_crew_autopilot import T, _approved, _ledger, _round, _ticket

T0 = crew_holder.parse_stamp("2026-09-30T10:00:00+00:00")


@pytest.fixture(autouse=True)
def _private_tmp(tmp_path, monkeypatch):
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    monkeypatch.setenv("TMPDIR", str(tmp))
    monkeypatch.setattr(crew_holder.tempfile, "tempdir", None)
    monkeypatch.setattr(crew_inflight, "_start_loop", lambda *a, **k: None)


@pytest.fixture(name="live_pid")
def _live_pid():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"],  # pylint: disable=consider-using-with
                            stdin=subprocess.DEVNULL)
    yield proc.pid
    proc.kill()
    proc.wait()


@pytest.fixture(autouse=True)
def _me(monkeypatch, live_pid):
    _session(monkeypatch, "sess-a", live_pid)


def _session(monkeypatch, sid, pid):
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", sid)
    monkeypatch.setenv("CLAUDE_PID", str(pid))


def _as(monkeypatch, sid, pid, root, *argv):
    """Run crew_inflight as session `sid`, then switch back to sess-a."""
    _session(monkeypatch, sid, pid)
    code = crew_inflight.main([argv[0], "--root", str(root)] + list(argv[1:]))
    _session(monkeypatch, "sess-a", pid)
    return code


def _held(monkeypatch, root, pid, runner="workflow:lane-b"):
    assert _as(monkeypatch, "sess-b", pid, root, "begin", "--ticket", T, "--runner", runner) == 0


def _next(root, **kwargs):
    return crew_autopilot.next_phase(str(root), T, **kwargs)


def _assert_in_flight(got, *names):
    assert (got["phase"], got["stop"]) == ("in-flight", True), got
    for name in names:
        assert name in got["reason"], got["reason"]


# --- must stop -----------------------------------------------------------------

def test_next_stops_on_live_marker(tmp_path, monkeypatch, live_pid):
    root = _approved(tmp_path)
    _held(monkeypatch, root, live_pid)

    got = _next(root)

    _assert_in_flight(got, "workflow:lane-b", "since", T)


def test_next_stops_on_stale_marker_with_clear_command(tmp_path, monkeypatch, live_pid):
    root = _approved(tmp_path)
    monkeypatch.setattr(crew_inflight, "_now", lambda: T0)
    _held(monkeypatch, root, live_pid)
    monkeypatch.setattr(crew_inflight, "_now", lambda: T0 + datetime.timedelta(hours=1))

    got = _next(root)

    _assert_in_flight(got, "stale", "workflow:lane-b")
    assert "crew_inflight.py clear" in got["command"]


def test_next_stops_on_unreadable_marker(tmp_path):
    root = _approved(tmp_path)
    path = crew_inflight.marker_path(str(root), T)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("{")

    got = _next(root)

    _assert_in_flight(got, "unknown")


def test_next_stops_on_reserved_round(tmp_path):
    root = _approved(tmp_path)
    _ledger(root, [_round(1, status="reserved")])

    got = _next(root)

    _assert_in_flight(got, "round 1 reserved with no result")


def test_next_stops_on_dirty_worktree_live_pid(tmp_path):
    if not sys.platform.startswith("linux"):
        pytest.skip("process working directories are read on Linux only; NOT tested here")
    root = _approved(tmp_path)
    other = tmp_path / "lane"
    git(root, "worktree", "add", "-q", "-b", f"{T}-build", str(other))
    (other / "src" / "app.py").write_text("x = 2\n", encoding="utf-8")
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],  # pylint: disable=consider-using-with
                             cwd=str(other), stdin=subprocess.DEVNULL)
    try:
        got = _next(root)
    finally:
        child.kill()
        child.wait()

    _assert_in_flight(got, "uncommitted changes", str(os.path.realpath(other)))


def test_next_without_session_stops(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID")

    got = _next(root)

    _assert_in_flight(got, "cannot tell who is asking")


def test_next_stops_handover_elsewhere(tmp_path, monkeypatch, live_pid):
    root = _approved(tmp_path)
    other = tmp_path / "lane"
    git(root, "worktree", "add", "-q", "-b", f"{T}-build", str(other))
    assert _as(monkeypatch, "sess-b", live_pid, other, "begin", "--ticket", T, "--runner", "workflow:b") == 0
    assert _as(monkeypatch, "sess-b", live_pid, other, "end", "--ticket", T, "--runner", "workflow:b") == 0

    got = _next(root)

    assert (got["phase"], got["stop"]) == ("handover-elsewhere", True), got
    assert f"cd {os.path.realpath(other)}" in got["reason"]


def test_next_crash_in_holds_stops(tmp_path, monkeypatch):
    root = _approved(tmp_path)

    def boom(*_a, **_k):
        raise RuntimeError("holds exploded")
    monkeypatch.setattr(crew_inflight, "holds", boom)

    got = _next(root)

    _assert_in_flight(got, "RuntimeError")


def test_next_cli_takes_runner(tmp_path, monkeypatch, capsys, live_pid):
    root = _approved(tmp_path)
    assert _as(monkeypatch, "sess-a", live_pid, root, "begin", "--ticket", T, "--runner", "autopilot") == 0
    capsys.readouterr()

    code = crew_autopilot.main(["next", "--root", str(root), "--ticket", T, "--runner", "workflow:other"])
    out = capsys.readouterr().out

    assert code == 0
    assert out.startswith("phase=in-flight stop=1"), out


# --- must allow ------------------------------------------------------------------

def test_next_closed_ticket_is_closed_even_with_marker(tmp_path, monkeypatch, live_pid):
    root = _approved(tmp_path)
    _held(monkeypatch, root, live_pid)
    _ticket(root, status="done")

    got = _next(root)

    assert got["phase"] == "closed"


def test_next_mine_runs_the_phase(tmp_path, monkeypatch, live_pid):
    root = _approved(tmp_path)
    assert _as(monkeypatch, "sess-a", live_pid, root, "begin", "--ticket", T, "--runner", "autopilot") == 0

    got = _next(root)

    assert got["phase"] == "implement"


def test_next_free_runs_the_phase(tmp_path):
    root = _approved(tmp_path)

    got = _next(root)

    assert got["phase"] == "implement"


# --- the stop lists and status ---------------------------------------------------

def test_in_flight_is_an_autonomous_stop_and_handover_a_fixed_one():
    assert "in-flight" in [slug for slug, _text in crew_autopilot.crew_state.AUTONOMOUS_STOPS]
    assert "handover-elsewhere" in [slug for slug, _text in crew_autopilot.FIXED_STOPS]


def test_status_maps_in_flight_to_the_runner(tmp_path, monkeypatch, live_pid):
    root = _approved(tmp_path)
    _held(monkeypatch, root, live_pid)

    got = crew_autopilot.status(str(root), T)

    assert got["phase"] == "in-flight"
    assert got["waiting"].startswith("runner - ") and "workflow:lane-b" in got["waiting"]


def test_status_reserved_round_still_waits_on_reviewer(tmp_path):
    root = _approved(tmp_path)
    _ledger(root, [_round(1, status="reserved")])

    got = crew_autopilot.status(str(root), T)

    assert (got["phase"], got["waiting"].split(" - ", maxsplit=1)[0]) == ("in-flight", "reviewer")
