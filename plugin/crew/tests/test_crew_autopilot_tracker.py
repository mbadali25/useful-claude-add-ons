"""T-0022 step 4: autopilot's tracker step, and proof it cannot stale a receipt.

    python3 -m pytest plugin/crew/tests/test_crew_autopilot_tracker.py -q

`crew_autopilot.tracker_step` derives the ticket's status from disk and moves
the tracker through T-0021's `crew_tracker.move`. The bundle tests measure,
with `review_patch.compute`'s own `bundle_sha256`, that a move made after a
review receipt changes nothing the receipt covers -- for the files kind, an
Obsidian vault outside the worktree, and one inside it that git ignores --
and that T-0021 refuses a vault inside the worktree that git does not ignore.
Every repository and vault is a throwaway under tmp_path.
"""
import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autopilot
import crew_tracker
import review_patch
import scope_base
from review_fixtures import git
from scope_fixtures import make_repo, make_ticket

_ROOT = context._ROOT  # pylint: disable=protected-access
_SCRIPT = os.path.join(_ROOT, "hooks", "scripts", "crew_autopilot.py")
_BOARD = os.path.join(_ROOT, "tests", "tracker_fixtures", "board_0_20.md")
T = "T-0042"


def _write(path, text):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _crew_json(root, tracker):
    _write(root / ".crew" / "crew.json", json.dumps({"schema": 1, "tracker": tracker}))


def _index(root, status):
    _write(root / ".work" / "INDEX.md", f"{T} | {status} | high | r | title\n")


def _index_status(root):
    with open(str(root / ".work" / "INDEX.md"), encoding="utf-8") as handle:
        return handle.read().split("|")[1].strip()


def _repo(tmp_path, status="ready", tracker=None, started=False):
    root = make_repo(tmp_path, mode="off")
    make_ticket(root, T)
    _index(root, status)
    _crew_json(root, tracker or {"kind": "files"})
    if started:
        scope_base.record(str(root), T)
    return root


def _vault(where):
    with open(_BOARD, encoding="utf-8") as handle:
        board = handle.read().replace("\r\n", "\n")
    _write(where / "Boards" / "repo" / "Board.md", board)
    os.makedirs(str(where / ".obsidian"), exist_ok=True)
    return where


def _own(root, vault):
    _write(vault / "Boards" / "repo" / f"{T}.md",
           f"# {T}\n\n- repo-id: {crew_tracker.repo_id(str(root))}\n")


def _obsidian(root, vault):
    _crew_json(root, {"kind": "obsidian", "obsidian": {
        "vaultPath": str(vault), "boardDir": "Boards/repo", "board": "Board.md"}})


# --- disk_status ------------------------------------------------------------------

def test_disk_status_spec_then_in_progress(tmp_path):
    root = _repo(tmp_path)
    assert crew_autopilot.disk_status(str(root), T) == "spec"
    scope_base.record(str(root), T)
    assert crew_autopilot.disk_status(str(root), T) == "in-progress"


@pytest.mark.parametrize("header", ["done", "review"])
def test_disk_status_reads_the_spec_header(tmp_path, header):
    root = _repo(tmp_path, started=True)
    spec = root / ".work" / "tickets" / T / "spec.md"
    with open(str(spec), encoding="utf-8") as handle:
        text = handle.read()
    _write(spec, text.replace(f"# {T}\n", f"# {T} title   status: {header}   risk: low\n", 1))

    assert crew_autopilot.disk_status(str(root), T) == header


def test_disk_status_direction_only(tmp_path):
    root = _repo(tmp_path)
    for name in ("spec.md", "plan.md"):
        os.remove(str(root / ".work" / "tickets" / T / name))

    assert crew_autopilot.disk_status(str(root), T) == "direction"


# --- the tracker step ---------------------------------------------------------------

def test_tracker_step_updates_then_is_unchanged(tmp_path):
    root = _repo(tmp_path, status="ready")

    first = crew_autopilot.tracker_step(str(root), T)
    second = crew_autopilot.tracker_step(str(root), T)

    assert (first["state"], first["stop"], _index_status(root)) == ("updated", False, "spec")
    assert (second["state"], second["stop"]) == ("unchanged", False)


def test_tracker_step_unchanged_when_agreeing(tmp_path):
    root = _repo(tmp_path, status="spec")
    before = _index_status(root)

    got = crew_autopilot.tracker_step(str(root), T)

    assert (got["state"], got["stop"], got["status"], _index_status(root)) == (
        "unchanged", False, "spec", before)


def test_tracker_step_could_not_update_stops(tmp_path):
    root = _repo(tmp_path, status="done")

    got = crew_autopilot.tracker_step(str(root), T)

    assert (got["state"], got["stop"], _index_status(root)) == ("stop", True, "done")
    assert "could not update to spec" in got["reason"]
    assert got["command"].endswith(f"crew_tracker.py move --root . --ticket {T} --to spec")


def test_tracker_step_tracker_could_not_tell_stops(tmp_path):
    root = _repo(tmp_path)
    _write(root / ".crew" / "crew.json", json.dumps({"schema": 1, "tracker": {"kind": "trello"}}))

    got = crew_autopilot.tracker_step(str(root), T)

    assert (got["stop"], "could not tell" in got["reason"]) == (True, True)


def test_tracker_step_delegated_returns_command(tmp_path):
    root = _repo(tmp_path, tracker={"kind": "jira"}, started=True)

    got = crew_autopilot.tracker_step(str(root), T)

    assert (got["state"], got["stop"], got["command"]) == (
        "delegated", False, f"/crew:jira-sync {T} --push --to in-progress")


def test_tracker_step_without_t0021_stops(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.setitem(sys.modules, "crew_tracker", None)

    got = crew_autopilot.tracker_step(str(root), T)

    assert (got["state"], got["stop"], got["reason"]) == (
        "stop", True, crew_autopilot.TRACKER_UNAVAILABLE)


def _cli(root, *extra):
    return subprocess.run([sys.executable, _SCRIPT, "tracker", "--root", str(root),
                           "--ticket", T, *extra], capture_output=True, text=True,
                          check=False, stdin=subprocess.DEVNULL)


def test_cli_tracker_prints_one_answer_line_then_the_tracker_lines(tmp_path):
    root = _repo(tmp_path, status="ready")

    done = _cli(root)

    lines = done.stdout.splitlines()
    assert done.returncode == 0
    assert lines[0].startswith("tracker=updated stop=0 status=spec command= reason=")
    assert lines[1].startswith("files: updated")


def test_cli_tracker_after_docs_records_the_attempt(tmp_path):
    root = _repo(tmp_path, status="spec")
    record = root / ".work" / "tickets" / T / crew_autopilot.DOCS_RECORD

    _cli(root, "--after", f"/crew:review {T}")
    _cli(root, "--after", "/crew:docs T-9")  # another ticket's run is not this one's
    assert not record.exists()
    done = _cli(root, "--after", f"/crew:docs {T}")

    with open(str(record), encoding="utf-8") as handle:
        attempts = json.load(handle)["attempts"]
    assert (done.returncode, len(attempts), done.stdout.startswith("tracker=unchanged")) == (
        0, 1, True)


def test_cli_tracker_crash_is_a_stop(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)

    def boom(root, ticket):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(crew_autopilot, "tracker_step", boom)

    code = crew_autopilot.main(["tracker", "--root", str(root), "--ticket", T])

    assert (code, capsys.readouterr().out.startswith("tracker=stop stop=1 ")) == (0, True)


# --- a tracker move after the receipt keeps the bundle --------------------------------

def _bundle(root, base):
    manifest, _patch, _parts = review_patch.compute(str(root), base)
    return manifest["bundle_sha256"]


def _reviewed(tmp_path):
    """A started ticket with a committed change, its bundle taken as a review
    receipt would take it."""
    root = _repo(tmp_path, status="spec", started=True)
    base = git(root, "rev-parse", "HEAD").strip()
    # `.work/` NOT ignored: the bundle's own exclusion is what is measured,
    # not a .gitignore line a repo may not have.
    _write(root / ".gitignore", ".crew/\n")
    _write(root / "src" / "app.py", "x = 2\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "change")
    return root, base


@pytest.mark.parametrize("where", ["files", "obsidian-outside", "obsidian-ignored-inside",
                                   "obsidian-unignored-inside"])
def test_tracker_move_after_receipt_keeps_bundle_hash(tmp_path, where):
    root, base = _reviewed(tmp_path)
    vault = None
    if where == "obsidian-outside":
        vault = _vault(tmp_path / "vault")
    elif where == "obsidian-ignored-inside":
        with open(str(root / ".gitignore"), "a", encoding="utf-8") as handle:
            handle.write("vault/\n")
        vault = _vault(root / "vault")
    elif where == "obsidian-unignored-inside":
        vault = _vault(root / "vault")
    if vault is not None:
        _own(root, vault)
        _obsidian(root, vault)
    before = _bundle(root, base)
    assert before

    got = crew_autopilot.tracker_step(str(root), T)

    if where == "obsidian-unignored-inside":
        assert (got["stop"], "would enter the review bundle" in got["reason"]) == (True, True)
    else:
        assert (got["state"], got["stop"]) == ("updated", False), got
    assert _bundle(root, base) == before
