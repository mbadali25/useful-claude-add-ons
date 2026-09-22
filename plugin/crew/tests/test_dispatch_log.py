"""The general dispatch LOG (`--log-dispatch`) and its one consumer.

`crew_state.py`'s own comment on `DISPATCH_KINDS` warns against exactly the
failure this file exists to rule out: "a `--record-dispatch qa` flag whose
output no code ever consults is state written to nowhere". `--log-dispatch`
widens dispatch evidence past the single `dev` slot to every role the PM
sends work to, and `pm_pulse._dispatch_gap_note` is the consumer -- this
tests both the store (`log_dispatch` / `read_dispatch_log`) and the reader
(`_last_pulse_time` / `_dispatch_gap_note` / `render`) that make the log a
real check rather than an inert flag.

This is the regression suite the team lead's brief asked for: must-block
(`test_render_appends_the_gap_note_...`) and must-allow
(`test_render_omits_the_note_...`) cases. Sabotage-tested by hand against
this commit: flipping the `if entries: return None` guard in
`pm_pulse._dispatch_gap_note` to `if not entries: return None` (inverting
which state is "quiet") turned every must-allow case in this file red while
leaving the must-block cases green -- proving the tests actually exercise
the "logged this pass" condition rather than passing regardless of it.
Separately, changing `_last_pulse_time`'s `since` computation to always
return `None` (as if no prior pulse ever existed) turned
`test_last_pulse_time_ignores_the_stood_down_marker_and_older_pulses` red.
Both were restored with `git checkout --` and reverified byte-identical
before this file was committed. Re-run that by hand rather than trusting
this paragraph; it is a fact about one commit.

The dev-slot store (`DISPATCH_DIR`/`DISPATCH_PATH`, `record_dispatch`,
`read_dispatch`) is untouched by any of this and is NOT exercised here --
see `test_crew_state.py` / `sabotage.py` for that store's own coverage.
"""
import io
import json
import os
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
import crew_state
import pm_pulse

HEALTHY = {
    "isCrew": True, "schema": 2, "tier": 1,
    "roles": ["explorer", "qa-reviewer"], "tracker": "files",
    "pm": {"enabled": True, "mode": "adaptive", "quietLines": 8,
           "maxLines": 40, "authority": "act"},
    "health": {"tickets": 10, "findings": 8, "rate": 0.8,
               "verdict": "healthy"},
    "work": {"ticket": "T-0042", "handoffPending": False},
    "knowledge": {"subsystems": 6, "behind": [],
                  "graph": {"present": True, "current": True}},
    "triggers": [],
}


def _triggered(**over):
    """A state with one real (non-quiet) trigger -- the condition under
    which `render` fires at all, per `should_pulse`."""
    state = dict(HEALTHY, triggers=["knowledgeBehind"])
    state.update(over)
    return state


# --- crew_state.log_dispatch / read_dispatch_log ----------------------


def test_log_dispatch_round_trips(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    entry = crew_state.log_dispatch(str(root), "security", "review the diff",
                                    "ok")
    assert entry["role"] == "security"
    assert entry["brief"] == "review the diff"
    assert entry["result"] == "ok"
    assert isinstance(entry["at"], float)

    entries = crew_state.read_dispatch_log(str(root))
    assert len(entries) == 1
    assert entries[0]["role"] == "security"


def test_read_dispatch_log_since_excludes_older_entries(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    crew_state.log_dispatch(str(root), "scribe", "write the ADR", "ok")
    time.sleep(0.05)
    cutoff = time.time()
    time.sleep(0.05)
    crew_state.log_dispatch(str(root), "dba", "review the migration", "ok")

    recent = crew_state.read_dispatch_log(str(root), since=cutoff)
    assert [e["role"] for e in recent] == ["dba"]

    everything = crew_state.read_dispatch_log(str(root), since=None)
    assert {e["role"] for e in everything} == {"scribe", "dba"}


def test_read_dispatch_log_skips_a_malformed_entry(tmp_path):
    """One bad neighbour costs only itself -- the same property the dev-slot
    store's `_dispatch_entries` has, and for the same reason: a hand-edited
    or half-written file must not blind the reader to every other entry."""
    root = crew_fixtures.make_repo(tmp_path)
    crew_state.log_dispatch(str(root), "analyst", "survey tech debt", "ok")
    logdir = root / ".work" / "dispatch-log.d"
    (logdir / "garbage.json").write_text("{not json", encoding="utf-8")

    entries = crew_state.read_dispatch_log(str(root))
    assert len(entries) == 1
    assert entries[0]["role"] == "analyst"


def test_read_dispatch_log_on_a_missing_directory_returns_empty(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    assert crew_state.read_dispatch_log(str(root)) == []


def test_log_dispatch_rejects_an_unknown_result(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    with pytest.raises(ValueError):
        crew_state.log_dispatch(str(root), "dba", "review it", "maybe")


def test_log_dispatch_truncates_a_long_brief(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    entry = crew_state.log_dispatch(str(root), "dba", "x" * 500, "ok")
    assert len(entry["brief"]) == 200


# --- CLI: --log-dispatch ------------------------------------------------


def test_cli_log_dispatch_writes_an_entry(tmp_path, capsys):
    root = crew_fixtures.make_repo(tmp_path)
    rc = crew_state.main(["--root", str(root), "--log-dispatch", "scribe",
                          "--brief", "write the handoff",
                          "--dispatch-result", "ok"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["role"] == "scribe"
    assert out["result"] == "ok"


def test_cli_log_dispatch_needs_brief_and_result(tmp_path, capsys):
    root = crew_fixtures.make_repo(tmp_path)
    rc = crew_state.main(["--root", str(root), "--log-dispatch", "scribe"])
    assert rc == 2
    assert "needs --brief" in capsys.readouterr().err


def test_cli_log_dispatch_rejects_an_unknown_result_choice(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    with pytest.raises(SystemExit):
        crew_state.main(["--root", str(root), "--log-dispatch", "scribe",
                         "--brief", "x", "--dispatch-result", "maybe"])


# --- pm_pulse._last_pulse_time -------------------------------------------


def test_last_pulse_time_with_no_markers_is_none(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    assert pm_pulse._last_pulse_time(str(root), "sess-1") is None  # pylint: disable=protected-access


def test_last_pulse_time_with_no_session_is_none(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    assert pm_pulse._last_pulse_time(str(root), None) is None  # pylint: disable=protected-access


def test_last_pulse_time_ignores_the_stood_down_marker_and_older_pulses(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    crewdir = root / ".crew"
    older = crewdir / ".pm-pulse-sess-1-aaaa"
    newer = crewdir / ".pm-pulse-sess-1-bbbb"
    stood_down = crewdir / ".pm-pulse-sess-1-stood-down"
    older.write_text("", encoding="utf-8")
    os.utime(older, (1_000_000, 1_000_000))
    newer.write_text("", encoding="utf-8")
    os.utime(newer, (2_000_000, 2_000_000))
    stood_down.write_text("", encoding="utf-8")
    os.utime(stood_down, (9_000_000, 9_000_000))  # newest of all; must be ignored

    since = pm_pulse._last_pulse_time(str(root), "sess-1")  # pylint: disable=protected-access
    assert since == 2_000_000.0

    # A different session's markers must not leak in.
    assert pm_pulse._last_pulse_time(str(root), "sess-2") is None  # pylint: disable=protected-access


# --- pm_pulse._dispatch_gap_note -----------------------------------------


def test_dispatch_gap_note_when_the_log_has_never_held_an_entry(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    note = pm_pulse._dispatch_gap_note(str(root), "sess-1")  # pylint: disable=protected-access
    assert note is not None
    assert "has ever been logged" in note


def test_dispatch_gap_note_is_none_once_something_is_logged(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    crew_state.log_dispatch(str(root), "dba", "review the index change", "ok")
    assert pm_pulse._dispatch_gap_note(str(root), "sess-1") is None  # pylint: disable=protected-access


def test_dispatch_gap_note_reappears_once_the_logged_entry_predates_the_pulse(
    tmp_path
):
    """A dispatch logged before the last pulse belongs to the PREVIOUS pass,
    not to the triggers being reported now -- the whole reason `since` is the
    last pulse marker's mtime and not "ever"."""
    root = crew_fixtures.make_repo(tmp_path)
    crew_state.log_dispatch(str(root), "dba", "old pass's dispatch", "ok")
    marker = root / ".crew" / ".pm-pulse-sess-1-aaaa"
    marker.write_text("", encoding="utf-8")
    os.utime(marker, (time.time() + 10, time.time() + 10))

    note = pm_pulse._dispatch_gap_note(str(root), "sess-1")  # pylint: disable=protected-access
    assert note is not None
    assert "has ever been logged" not in note
    assert "since the last check-in" in note


def test_dispatch_gap_note_never_raises_on_an_unreadable_root():
    # No repo at all -- `os.listdir` on a directory that does not exist.
    # Must degrade rather than raise, the same "every failure path stays
    # safe" contract `pm_pulse.main` itself carries. In practice `render`
    # never reaches this with a bogus root -- `should_pulse` already
    # requires `collect(root)` to have found `isCrew` true -- so the only
    # property that matters here is "does not raise"; what it returns for a
    # path that cannot exist is not a decision anything downstream reads.
    note = pm_pulse._dispatch_gap_note("/no/such/path/at/all", "sess-1")  # pylint: disable=protected-access
    assert note is None or isinstance(note, str)


# --- pm_pulse.render, end to end -----------------------------------------


def test_render_appends_the_gap_note_when_triggered_and_unlogged(tmp_path):
    """Must-block (in the sense that matters here: the note must appear)."""
    root = crew_fixtures.make_repo(tmp_path)
    text = pm_pulse.render(_triggered(), str(root), "sess-1")
    assert text is not None
    assert "No dispatch has ever been logged" in text


def test_render_omits_the_note_once_a_dispatch_is_logged(tmp_path):
    """Must-allow: a real dispatch this pass silences the note."""
    root = crew_fixtures.make_repo(tmp_path)
    crew_state.log_dispatch(str(root), "developer", "implement T-0042", "ok")
    text = pm_pulse.render(_triggered(), str(root), "sess-1")
    assert text is not None  # the pulse itself still fires for the trigger
    assert "No dispatch has ever been logged" not in text
    assert "No dispatch has been logged since" not in text


def test_render_without_root_never_looks_at_the_dispatch_log(tmp_path):
    """Backward compatibility: every existing single-argument caller (and
    the whole prior test suite) must keep behaving exactly as before."""
    text = pm_pulse.render(_triggered())
    assert text is not None
    assert "dispatch" not in text.lower() or "No dispatch has" not in text


def test_render_on_a_healthy_state_stays_none_even_with_an_empty_log(tmp_path):
    """The note can never by itself turn a quiet turn into a blocked one --
    it is appended only after `should_pulse` has already said yes."""
    root = crew_fixtures.make_repo(tmp_path)
    assert pm_pulse.render(HEALTHY, str(root), "sess-1") is None


def test_main_end_to_end_includes_the_gap_note_on_stderr(
    tmp_path, monkeypatch, capsys
):
    """`main` itself, not just `render` -- the hook's actual entry point,
    with `collect` stubbed to a known-triggered state so this does not
    depend on which real fixture happens to produce a non-quiet trigger."""
    root = crew_fixtures.make_repo(tmp_path)
    monkeypatch.setattr(pm_pulse.crew_state, "collect",
                        lambda _root: _triggered())
    payload = json.dumps({"cwd": str(root), "session_id": "sess-e2e"})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    rc = pm_pulse.main([])
    assert rc == 2
    err = capsys.readouterr().err
    assert "No dispatch has ever been logged" in err


def test_main_end_to_end_omits_the_note_once_logged(
    tmp_path, monkeypatch, capsys
):
    root = crew_fixtures.make_repo(tmp_path)
    crew_state.log_dispatch(str(root), "developer", "implement T-0042", "ok")
    monkeypatch.setattr(pm_pulse.crew_state, "collect",
                        lambda _root: _triggered())
    payload = json.dumps({"cwd": str(root), "session_id": "sess-e2e-2"})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    rc = pm_pulse.main([])
    assert rc == 2
    err = capsys.readouterr().err
    assert "No dispatch has" not in err
