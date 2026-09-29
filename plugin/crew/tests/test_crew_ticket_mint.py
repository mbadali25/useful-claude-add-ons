"""T-0019: `crew_ticket.mint`, the one way code creates a ticket.

    python3 -m pytest plugin/crew/tests/test_crew_ticket_mint.py -q

`mint` takes one past the highest `T-` number over `.work/tickets/` folders
and `.work/INDEX.md` rows, claims it with an exclusive `os.mkdir`, writes the
direction complete or not at all, and only then asks `crew_tracker.create`
for the INDEX row (and, under `obsidian`, the note and card). Every repository
and vault is built under tmp_path; nothing touches the real one, a real vault
or ~/.claude. `sabotage_autopilot.py`'s ASSIGN_MUTATIONS prove these can fail.
"""
import json
import os
import pathlib
import re
import subprocess
import sys

import context  # noqa: F401  pylint: disable=unused-import
import crew_ticket
import crew_tracker
import pytest
from crew_fixtures import make_repo
from test_crew_tracker import _lane_of, _make_vault

SCRIPTS = os.path.dirname(os.path.abspath(crew_ticket.__file__))
SCRIPT = os.path.join(SCRIPTS, "crew_ticket.py")
ROW_RE = re.compile(r"^T-[0-9]{4} \| ready \| - \| [^|]+ \| title [0-9]+$")


def _files_repo(tmp_path, rows=None):
    root = make_repo(tmp_path)
    (root / ".crew" / "config.json").write_text(json.dumps({"tracker": "files"}),
                                                encoding="utf-8")
    if rows is not None:
        (root / ".work" / "INDEX.md").write_bytes(rows.encode("utf-8"))
    return root


def _index(root):
    path = root / ".work" / "INDEX.md"
    return path.read_bytes() if path.exists() else None


def _tickets(root):
    folder = root / ".work" / "tickets"
    return sorted(os.listdir(folder)) if folder.is_dir() else []


def _report(state, reason, backend="files"):
    return {"kind": "files", "source": "config.json",
            "results": [{"backend": backend, "state": state, "reason": reason,
                         "command": None}]}


def _spy_create(monkeypatch):
    calls = []
    real = crew_tracker.create

    def spy(root, ticket, title):
        calls.append(ticket)
        return real(root, ticket, title)

    monkeypatch.setattr(crew_tracker, "create", spy)
    return calls


def _no_temp(root):
    return [p for p in (root / ".work").rglob("*") if p.name.endswith(".tmp")]


# --- must-block ----------------------------------------------------------------

_MINT_ONE = ("import sys; sys.path.insert(0, sys.argv[1]); import crew_ticket; "
             "print(crew_ticket.mint(sys.argv[2], 'title ' + sys.argv[3], "
             "direction='body ' + sys.argv[3])['ticket'])")


def _concurrent(root, count=8):
    # Started together and waited on below: a `with` per process would run them one at a time.
    procs = [subprocess.Popen(  # pylint: disable=consider-using-with
        [sys.executable, "-c", _MINT_ONE, SCRIPTS, str(root), str(n)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, stdin=subprocess.DEVNULL)
        for n in range(count)]
    return [(p.communicate(timeout=120), p.returncode) for p in procs]


def test_concurrent_mints_distinct(tmp_path):
    root = _files_repo(tmp_path)

    runs = _concurrent(root)
    ids = [out.strip() for (out, _err), _code in runs]
    with_direction = [t for t in _tickets(root)
                      if (root / ".work" / "tickets" / t / "direction.md").is_file()]

    assert ([code for _out, code in runs], len(set(ids)), sorted(ids) == with_direction,
            len(with_direction)) == ([0] * 8, 8, True, 8), [err for (_o, err), _c in runs]


def test_index_rows_intact_after_concurrent_mints(tmp_path):
    root = _files_repo(tmp_path)

    _concurrent(root)
    lines = _index(root).decode("utf-8").splitlines()

    assert (len(lines), [line for line in lines if not ROW_RE.match(line)],
            len({line.split(" | ")[0] for line in lines})) == (8, [], 8)


def test_mint_never_takes_an_index_only_id(tmp_path):
    root = _files_repo(tmp_path, rows="T-0050 | spec | - | r | elsewhere\n")

    got = crew_ticket.mint(str(root), "new work")

    assert got["ticket"] == "T-0051"


def test_mint_moves_on_when_the_tracker_says_id_taken(tmp_path, monkeypatch):
    root = _files_repo(tmp_path)
    real, seen = crew_tracker.create, []

    def create(where, ticket, title):
        seen.append(ticket)
        if len(seen) == 1:
            return _report(crew_tracker.FAILED, f'{crew_tracker.TAKEN}: {ticket} is already '
                                                'spec "theirs"')
        return real(where, ticket, title)

    monkeypatch.setattr(crew_tracker, "create", create)

    got = crew_ticket.mint(str(root), "new work", direction="go")

    assert (seen, got["ticket"], _tickets(root)) == (["T-0001", "T-0002"], "T-0002", ["T-0002"])


def test_mint_skips_existing_folder(tmp_path, monkeypatch):
    root = _files_repo(tmp_path)
    theirs = root / ".work" / "tickets" / "T-0001"
    theirs.mkdir(parents=True)
    (theirs / "note.txt").write_text("someone else's\n", encoding="utf-8")
    # The folder appeared after the scan: only the exclusive mkdir sees it.
    monkeypatch.setattr(crew_ticket, "_mint_taken", lambda top: set())

    got = crew_ticket.mint(str(root), "new work", direction="go")

    assert (got["ticket"], sorted(os.listdir(theirs))) == ("T-0002", ["note.txt"])


def test_mint_half_written_direction_leaves_no_ticket(tmp_path, monkeypatch):
    root = _files_repo(tmp_path, rows="T-0003 | spec | - | r | old\n")
    before = _index(root)
    calls = _spy_create(monkeypatch)

    def boom(src, dst):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(crew_ticket.os, "replace", boom)

    with pytest.raises(OSError):
        crew_ticket.mint(str(root), "new work", direction="go")

    assert (_tickets(root), _no_temp(root), _index(root) == before, calls) == (
        [], [], True, [])


def test_mint_failed_tracker_create_leaves_no_ticket(tmp_path, monkeypatch):
    root = _files_repo(tmp_path, rows="T-0003 | spec | - | r | old\n")
    before, calls = _index(root), []

    def create(where, ticket, title):
        calls.append(ticket)
        return _report(crew_tracker.FAILED, ".work/INDEX.md changed during write")

    monkeypatch.setattr(crew_tracker, "create", create)
    monkeypatch.setattr(crew_ticket, "_MINT_RETRY_PAUSE", 0)

    with pytest.raises(crew_ticket.TicketError) as err:
        crew_ticket.mint(str(root), "new work", direction="go")

    assert (_tickets(root), _index(root) == before, len(calls),
            "files: could not update: .work/INDEX.md changed during write" in str(err.value)) == (
        [], True, crew_ticket.MINT_ATTEMPTS, True)


@pytest.mark.parametrize("title", ["a|b", "a\nb", "a\rb", "", " ", "x" * 121],
                         ids=["a|b", "newline", "cr", "empty", "space", "long"])
def test_mint_rejects_bad_title(tmp_path, monkeypatch, title):
    root = _files_repo(tmp_path)
    calls = _spy_create(monkeypatch)

    with pytest.raises(crew_ticket.TicketError):
        crew_ticket.mint(str(root), title)

    assert (_tickets(root), _index(root), calls) == ([], None, [])


def test_mint_rejects_unknown_status(tmp_path):
    root = _files_repo(tmp_path)

    with pytest.raises(crew_ticket.TicketError):
        crew_ticket.mint(str(root), "new work", status="spec")

    assert (_tickets(root), _index(root)) == ([], None)


def test_mint_gives_up_after_max_attempts(tmp_path, monkeypatch):
    root = _files_repo(tmp_path, rows="T-0003 | spec | - | r | old\n")
    (root / ".work" / "tickets").mkdir()
    before, tried = _index(root), []

    def taken(path, *args, **kwargs):
        if os.path.basename(path).startswith("T-"):
            tried.append(os.path.basename(path))
        raise FileExistsError(17, "File exists", path)

    monkeypatch.setattr(crew_ticket.os, "mkdir", taken)

    with pytest.raises(crew_ticket.TicketError):
        crew_ticket.mint(str(root), "new work")

    assert (len(tried), tried[0], _index(root) == before) == (
        crew_ticket.MINT_ATTEMPTS, "T-0004", True)


def test_mint_unreadable_index_refuses(tmp_path, monkeypatch):
    root = _files_repo(tmp_path)
    (root / ".work" / "INDEX.md").mkdir()
    calls = _spy_create(monkeypatch)

    with pytest.raises(crew_ticket.TicketError) as err:
        crew_ticket.mint(str(root), "new work")

    assert (_tickets(root), calls, "INDEX.md" in str(err.value)) == ([], [], True)


def _tracker_config(root, which):
    crew = root / ".crew"
    (crew / "config.json").unlink()
    if which in ("jira", "sdp"):
        (crew / "config.json").write_text(json.dumps({"tracker": which}), encoding="utf-8")
    elif which == "disagree":
        (crew / "config.json").write_text(json.dumps({"tracker": "files"}), encoding="utf-8")
        (crew / "crew.json").write_text(json.dumps({"tracker": {"kind": "jira"}}),
                                        encoding="utf-8")


@pytest.mark.parametrize("which", ["jira", "sdp", "none", "disagree"])
def test_mint_refuses_under_a_delegated_or_unknown_tracker(tmp_path, monkeypatch, which):
    root = _files_repo(tmp_path)
    _tracker_config(root, which)
    calls = _spy_create(monkeypatch)

    with pytest.raises(crew_ticket.TicketError) as err:
        crew_ticket.mint(str(root), "new work")

    assert (_tickets(root), calls, "brainstorm.md" in str(err.value)) == ([], [], True)


# --- must-allow ----------------------------------------------------------------

def test_mint_takes_max_plus_one(tmp_path):
    root = _files_repo(tmp_path, rows="T-0007 | spec | - | r | a\nT-0002 | done | - | r | b\n")
    (root / ".work" / "tickets" / "T-0005").mkdir(parents=True)
    (root / ".work" / "tickets" / "T-0009").mkdir(parents=True)

    got = crew_ticket.mint(str(root), "new work")

    assert (got["ticket"], got["status"], got["warnings"]) == ("T-0010", "ready", [])


def test_mint_writes_direction_then_row(tmp_path, monkeypatch):
    root = _files_repo(tmp_path)
    real, seen = crew_tracker.create, []

    def create(where, ticket, title):
        seen.append(os.path.isfile(os.path.join(where, ".work", "tickets", ticket,
                                                "direction.md")))
        return real(where, ticket, title)

    monkeypatch.setattr(crew_tracker, "create", create)

    got = crew_ticket.mint(str(root), "new work", direction="## Ask\nthe work\n")
    text = (root / ".work" / "tickets" / "T-0001" / "direction.md").read_text(encoding="utf-8")

    assert (got["ticket"], seen, text, _index(root).decode("utf-8").splitlines()[0]) == (
        "T-0001", [True], "# T-0001 direction\n## Ask\nthe work\n",
        f"T-0001 | ready | - | {crew_tracker.repo_name(str(root))} | new work")


def test_mint_row_on_its_own_line_without_trailing_newline(tmp_path):
    root = _files_repo(tmp_path, rows="T-0004 | spec | - | r | old")

    crew_ticket.mint(str(root), "new work")

    assert _index(root).decode("utf-8").splitlines()[1].startswith("T-0005 | ready | - |")


def test_mint_under_obsidian_adds_note_and_card(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    root = make_repo(tmp_path)
    (root / ".crew" / "crew.json").write_text(json.dumps({"tracker": {
        "kind": "obsidian", "obsidian": {"vaultPath": str(vault), "boardDir": "Boards/repo",
                                         "board": "Board.md"}}}), encoding="utf-8")
    (root / ".work" / "INDEX.md").write_text("T-0059 | spec | - | r | old\n", encoding="utf-8")

    got = crew_ticket.mint(str(root), "new work", direction="go")
    board = (vault / "Boards" / "repo" / "Board.md").read_text(encoding="utf-8")

    assert (got["ticket"], got["status"], (vault / "Boards" / "repo" / "T-0060.md").is_file(),
            _lane_of(board, "T-0060"), "T-0060 | ready |" in _index(root).decode("utf-8")) == (
        "T-0060", "ready", True, "Backlog", True), got["warnings"]


def test_mint_ready_move_failure_leaves_direction_row_and_warns(tmp_path, monkeypatch):
    root = _files_repo(tmp_path)
    monkeypatch.setattr(crew_tracker, "move", lambda where, ticket, status, reopen=False:
                        _report(crew_tracker.FAILED, ".work/INDEX.md changed during write"))

    got = crew_ticket.mint(str(root), "new work", direction="go")

    assert (got["status"], got["warnings"],
            (root / ".work" / "tickets" / "T-0001" / "direction.md").is_file(),
            "T-0001 | direction |" in _index(root).decode("utf-8")) == (
        "direction", ["tracker: files: could not update: .work/INDEX.md changed during write"],
        True, True)


def test_mint_direction_status_writes_no_move(tmp_path, monkeypatch):
    root = _files_repo(tmp_path)
    moves = []
    monkeypatch.setattr(crew_tracker, "move", lambda *a, **k: moves.append(a))

    got = crew_ticket.mint(str(root), "new work", status="direction")

    assert (got["status"], moves, "T-0001 | direction |" in _index(root).decode("utf-8")) == (
        "direction", [], True)


def _cli(root, *args):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True,
                          check=False, cwd=str(root), stdin=subprocess.DEVNULL)


def test_mint_cli_prints_ticket(tmp_path):
    root = _files_repo(tmp_path)
    body = pathlib.Path(tmp_path / "direction-body.md")
    body.write_text("## Ask\nfrom a file\n", encoding="utf-8")

    done = _cli(root, "mint", "--root", ".", "--title", "new work", "--direction-file",
                str(body))

    assert (done.returncode, done.stdout, (root / ".work" / "tickets" / "T-0001" /
                                           "direction.md").read_text(encoding="utf-8")) == (
        0, "ticket=T-0001\n", "# T-0001 direction\n## Ask\nfrom a file\n"), done.stderr


def test_mint_cli_refusal_exits_1(tmp_path):
    root = _files_repo(tmp_path)

    done = _cli(root, "mint", "--root", ".", "--title", "a|b")

    assert (done.returncode, done.stdout.startswith("refused: "), _tickets(root)) == (1, True, [])
