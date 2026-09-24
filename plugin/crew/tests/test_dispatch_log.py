"""The general dispatch LOG (`--log-dispatch`): the store alone.

`crew_state.py`'s own comment on `DISPATCH_KINDS` warns against "a
`--record-dispatch qa` flag whose output no code ever consults is state
written to nowhere". The log's one consumer, `pm_pulse._dispatch_gap_note`,
was deleted with the PM in crew 1.0, so today the log IS that flag; TODO.md
tracks retiring it. Until then this file keeps the store's own contract
(`log_dispatch` / `read_dispatch_log` and the CLI) covered, so the code that
still ships is still tested.

The dev-slot store (`DISPATCH_DIR`/`DISPATCH_PATH`, `record_dispatch`,
`read_dispatch`) is untouched by any of this and is NOT exercised here --
see `test_crew_state.py` / `sabotage.py` for that store's own coverage.
"""
import json
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
import crew_state


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
