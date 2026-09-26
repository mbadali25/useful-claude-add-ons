"""crew_tracker.py: one tracker interface behind every lifecycle transition (T-0021).

    python3 -m pytest plugin/crew/tests/test_crew_tracker.py -q

Every vault here is a throwaway fixture under `tmp_path`. Nothing in this file
may read or write a real Obsidian vault: the Obsidian backend writes outside
the repository, which is exactly why its must-block cases assert that the
vault AND the repo are byte-identical after a refusal.
"""
import json
import os
import subprocess
import sys

import context  # noqa: F401  pylint: disable=unused-import
import crew_tracker
from crew_fixtures import make_repo

SCRIPT = os.path.join(os.path.dirname(crew_tracker.__file__), "crew_tracker.py")


def _write_json(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def _crew_json(root, tracker):
    _write_json(root / ".crew" / "crew.json", {"schema": 1, "tracker": tracker})


def _config_json(root, tracker, **blocks):
    _write_json(root / ".crew" / "config.json", dict({"schema": 7, "tracker": tracker}, **blocks))


def _cli(root, *args):
    return subprocess.run([sys.executable, SCRIPT, *args, "--root", str(root)],
                          capture_output=True, text=True, check=False,
                          stdin=subprocess.DEVNULL)


def _index(root):
    return (root / ".work" / "INDEX.md").read_text(encoding="utf-8")


def _files_repo(tmp_path, rows=""):
    root = make_repo(tmp_path)
    _crew_json(root, {"kind": "files"})
    if rows:
        (root / ".work" / "INDEX.md").write_text(rows, encoding="utf-8")
    return root


# --- resolve -----------------------------------------------------------------

def test_resolve_crew_json_only(tmp_path):
    root = make_repo(tmp_path)
    _crew_json(root, {"kind": "obsidian", "obsidian": {"vaultPath": "/v", "boardDir": "B"}})

    got = crew_tracker.resolve(str(root))

    assert (got["kind"], got["source"], got["settings"]["boardDir"]) == ("obsidian", "crew.json", "B")


def test_resolve_config_json_only(tmp_path):
    root = make_repo(tmp_path)
    _config_json(root, "obsidian", obsidian={"vaultPath": "/v", "boardDir": "B"})

    got = crew_tracker.resolve(str(root))

    assert (got["kind"], got["source"], got["settings"]["boardDir"]) == ("obsidian", "config.json", "B")


def test_resolve_both_agree(tmp_path):
    root = make_repo(tmp_path)
    _crew_json(root, {"kind": "files"})
    _config_json(root, "files")

    got = crew_tracker.resolve(str(root))

    assert (got["kind"], got["problems"]) == ("files", [])


def test_resolve_both_disagree_is_could_not_tell(tmp_path):
    root = make_repo(tmp_path)
    _crew_json(root, {"kind": "files"})
    _config_json(root, "obsidian")

    got = crew_tracker.resolve(str(root))

    assert (got["kind"], got["problems"]) == (
        "could not tell",
        [".crew/crew.json says tracker.kind 'files', .crew/config.json says tracker 'obsidian'"])


def test_resolve_both_disagree_on_the_kinds_settings_is_could_not_tell(tmp_path):
    root = make_repo(tmp_path)
    _crew_json(root, {"kind": "obsidian", "obsidian": {"vaultPath": "/a"}})
    _config_json(root, "obsidian", obsidian={"vaultPath": "/b"})

    got = crew_tracker.resolve(str(root))

    assert got["kind"] == "could not tell"


def test_resolve_unknown_kind(tmp_path):
    root = make_repo(tmp_path)
    _crew_json(root, {"kind": "trello"})

    got = crew_tracker.resolve(str(root))

    assert (got["kind"], got["problems"]) == (
        "could not tell", [".crew/crew.json names tracker kind 'trello', which crew does not know"])


def test_resolve_neither_file_is_not_configured(tmp_path):
    root = make_repo(tmp_path)

    got = crew_tracker.resolve(str(root))

    assert (got["kind"], got["source"]) == ("not configured", None)


def test_resolve_corrupt_config_is_could_not_tell(tmp_path):
    root = make_repo(tmp_path)
    (root / ".crew" / "config.json").write_text("{nope", encoding="utf-8")

    got = crew_tracker.resolve(str(root))

    assert got["kind"] == "could not tell"


def test_resolve_cli_json_names_source(tmp_path):
    root = make_repo(tmp_path)
    _config_json(root, "files")

    done = _cli(root, "resolve", "--json")

    assert (done.returncode, json.loads(done.stdout)["source"]) == (0, "config.json")


# --- files backend -----------------------------------------------------------

def test_files_create_appends_once(tmp_path):
    root = _files_repo(tmp_path, "T-0001 | done | low | repo | first\n")

    first = crew_tracker.create(str(root), "T-0002", "second")
    again = crew_tracker.create(str(root), "T-0002", "second")

    assert ([r["state"] for r in first["results"] + again["results"]], _index(root)) == (
        ["updated", "unchanged"],
        "T-0001 | done | low | repo | first\nT-0002 | direction | - | repo | second\n")


def test_files_create_refuses_a_pipe_in_the_title(tmp_path):
    root = _files_repo(tmp_path, "T-0001 | done | low | repo | first\n")

    got = crew_tracker.create(str(root), "T-0002", "a | b")

    assert (got["results"][0]["state"], _index(root)) == (
        "could not update", "T-0001 | done | low | repo | first\n")


def test_files_move_rewrites_only_status_cell(tmp_path):
    rows = ("| T-0001 |  spec  | low | repo | T-0001 spec review |\n"
            "T-00011 | spec | low | repo | not this one\n")
    root = _files_repo(tmp_path, rows)

    got = crew_tracker.move(str(root), "T-0001", "planned")

    assert (got["results"][0]["state"], _index(root)) == (
        "updated",
        "| T-0001 |  planned  | low | repo | T-0001 spec review |\n"
        "T-00011 | spec | low | repo | not this one\n")


def test_files_move_same_status_is_unchanged(tmp_path):
    root = _files_repo(tmp_path, "T-0001 | spec | low | repo | t\n")

    got = crew_tracker.move(str(root), "T-0001", "spec")

    assert got["results"][0]["state"] == "unchanged"


def test_files_move_unknown_status_writes_nothing(tmp_path):
    root = _files_repo(tmp_path, "T-0001 | spec | low | repo | t\n")

    done = _cli(root, "move", "--ticket", "T-0001", "--to", "shipped-ish")

    assert (done.returncode, done.stdout.strip(), _index(root)) == (
        1, "files: could not update: status shipped-ish maps to no lane",
        "T-0001 | spec | low | repo | t\n")


def test_files_move_without_a_row_is_refused(tmp_path):
    root = _files_repo(tmp_path, "T-0001 | spec | low | repo | t\n")

    got = crew_tracker.move(str(root), "T-0009", "spec")

    assert got["results"][0] == {"backend": "files", "state": "could not update",
                                 "reason": "no .work/INDEX.md row for T-0009", "command": None}


def test_files_read_returns_the_status_cell(tmp_path):
    root = _files_repo(tmp_path, "T-0001 | in-progress | low | repo | t\n")

    got = crew_tracker.read(str(root), "T-0001")

    assert got["results"][0]["status"] == "in-progress"


def test_files_move_retries_when_index_changes(tmp_path, monkeypatch):
    """Another session appends a row between our read and our replace: the
    append must survive and the move must still land."""
    root = _files_repo(tmp_path, "T-0001 | spec | low | repo | t\n")
    index = root / ".work" / "INDEX.md"
    real = crew_tracker._read_bytes  # pylint: disable=protected-access
    calls = []

    def racing(path):
        calls.append(path)
        if len(calls) == 2:
            with open(index, "a", encoding="utf-8", newline="\n") as handle:
                handle.write("T-0002 | direction | - | repo | other session\n")
        return real(path)

    monkeypatch.setattr(crew_tracker, "_read_bytes", racing)

    got = crew_tracker.move(str(root), "T-0001", "planned")

    assert (got["results"][0]["state"], _index(root)) == (
        "updated",
        "T-0001 | planned | low | repo | t\nT-0002 | direction | - | repo | other session\n")


def test_files_move_gives_up_after_three_changed_reads(tmp_path, monkeypatch):
    root = _files_repo(tmp_path, "T-0001 | spec | low | repo | t\n")
    index = root / ".work" / "INDEX.md"
    real = crew_tracker._read_bytes  # pylint: disable=protected-access
    calls = []

    def always_racing(path):
        calls.append(path)
        if len(calls) % 2 == 0:
            with open(index, "a", encoding="utf-8", newline="\n") as handle:
                handle.write(f"T-10{len(calls)} | direction | - | repo | noise\n")
        return real(path)

    monkeypatch.setattr(crew_tracker, "_read_bytes", always_racing)

    got = crew_tracker.move(str(root), "T-0001", "planned")

    assert (got["results"][0]["reason"], "planned" in _index(root)) == (
        ".work/INDEX.md changed during write", False)


def test_cli_rejects_a_malformed_ticket_id(tmp_path):
    root = _files_repo(tmp_path)

    done = _cli(root, "move", "--ticket", "../etc", "--to", "spec")

    assert done.returncode == 2
