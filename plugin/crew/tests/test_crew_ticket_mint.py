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
import threading
import time

import context  # noqa: F401  pylint: disable=unused-import
import crew_common
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


def _concurrent(root, count=8, program=_MINT_ONE):
    # Started together and waited on below: a `with` per process would run them one at a time.
    procs = [subprocess.Popen(  # pylint: disable=consider-using-with
        [sys.executable, "-c", program, SCRIPTS, str(root), str(n)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, stdin=subprocess.DEVNULL)
        for n in range(count)]
    return [(p.communicate(timeout=120), p.returncode) for p in procs]


def _stderr(runs):
    """Every process's exit code and stderr in full, as one string: a list in
    the assertion message is truncated by pytest, which hid the one failing
    mint's traceback behind `['', '', ...]` on the Windows runner."""
    return "\n".join(f"--- mint {n} exit {code} ---\n{err}"
                     for n, ((_out, err), code) in enumerate(runs))


def test_concurrent_mints_distinct(tmp_path):
    root = _files_repo(tmp_path)

    runs = _concurrent(root)
    ids = [out.strip() for (out, _err), _code in runs]
    with_direction = [t for t in _tickets(root)
                      if (root / ".work" / "tickets" / t / "direction.md").is_file()]

    assert ([code for _out, code in runs], len(set(ids)), sorted(ids) == with_direction,
            len(with_direction)) == ([0] * 8, 8, True, 8), _stderr(runs)


def test_index_rows_intact_after_concurrent_mints(tmp_path):
    root = _files_repo(tmp_path)

    runs = _concurrent(root)
    lines = _index(root).decode("utf-8").splitlines()

    assert (len(lines), [line for line in lines if not ROW_RE.match(line)],
            len({line.split(" | ")[0] for line in lines})) == (8, [], 8), _stderr(runs)


# The tracker's lost-write window, between its re-read and its replace, held
# open 50 ms by a `_read_bytes` that pauses after reading, so eight unlocked
# mints lose rows every run rather than now and then; the INDEX lock is what
# keeps them. sabotage_autopilot.py removes that lock against this test.
_MINT_SLOW = ("import sys, time; sys.path.insert(0, sys.argv[1]); import crew_tracker, "
              "crew_ticket; real = crew_tracker._read_bytes\n"
              "def slow(*a, **k):\n    got = real(*a, **k); time.sleep(0.05); return got\n"
              "crew_tracker._read_bytes = slow\n"
              "print(crew_ticket.mint(sys.argv[2], 'title ' + sys.argv[3], "
              "direction='body ' + sys.argv[3])['ticket'])")


def test_index_rows_intact_after_concurrent_slow_mints(tmp_path):
    root = _files_repo(tmp_path)

    runs = _concurrent(root, program=_MINT_SLOW)
    lines = _index(root).decode("utf-8").splitlines()

    assert (len(lines), [line for line in lines if not ROW_RE.match(line)],
            len({line.split(" | ")[0] for line in lines})) == (8, [], 8), _stderr(runs)


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


def _lock_held(root):
    return (root / ".work" / "INDEX.md.lock").exists()


def test_mint_ready_move_runs_under_the_index_lock(tmp_path, monkeypatch):
    root = _files_repo(tmp_path)
    real, held = crew_tracker.move, []

    def move(where, ticket, status, reopen=False):
        held.append(_lock_held(root))
        return real(where, ticket, status, reopen=reopen)

    monkeypatch.setattr(crew_tracker, "move", move)

    got = crew_ticket.mint(str(root), "new work", direction="go")

    assert (got["status"], held, _lock_held(root)) == ("ready", [True], False)


def test_mint_create_runs_under_the_index_lock(tmp_path, monkeypatch):
    root = _files_repo(tmp_path)
    real, held = crew_tracker.create, []

    def create(where, ticket, title):
        held.append(_lock_held(root))
        return real(where, ticket, title)

    monkeypatch.setattr(crew_tracker, "create", create)

    got = crew_ticket.mint(str(root), "new work", direction="go")

    assert (got["ticket"], held, _lock_held(root)) == ("T-0001", [True], False)


@pytest.mark.parametrize("raised,expected", [(RuntimeError, crew_ticket.TicketError),
                                             (KeyError, crew_ticket.TicketError),
                                             (KeyboardInterrupt, KeyboardInterrupt)],
                         ids=["RuntimeError", "KeyError", "KeyboardInterrupt"])
def test_mint_create_that_raises_leaves_no_ticket(tmp_path, monkeypatch, raised, expected):
    root = _files_repo(tmp_path, rows="T-0003 | spec | - | r | old\n")
    before = _index(root)

    def create(where, ticket, title):
        raise raised("tracker blew up")

    monkeypatch.setattr(crew_tracker, "create", create)

    with pytest.raises(expected):
        crew_ticket.mint(str(root), "new work", direction="go")

    assert (_tickets(root), _index(root) == before, _lock_held(root)) == ([], True, False)


def test_mint_create_that_raises_after_writing_the_row_keeps_the_ticket(tmp_path, monkeypatch):
    root = _files_repo(tmp_path)
    real = crew_tracker.create

    def create(where, ticket, title):
        real(where, ticket, title)
        raise RuntimeError("the board half blew up")

    monkeypatch.setattr(crew_tracker, "create", create)

    with pytest.raises(crew_ticket.TicketError) as err:
        crew_ticket.mint(str(root), "new work", direction="go")

    assert (_tickets(root), "T-0001 | direction |" in _index(root).decode("utf-8"),
            "kept" in str(err.value)) == (["T-0001"], True, True)


def test_mint_ready_move_that_raises_leaves_direction_row_and_warns(tmp_path, monkeypatch):
    root = _files_repo(tmp_path)

    def move(where, ticket, status, reopen=False):
        raise RuntimeError("board unreadable")

    monkeypatch.setattr(crew_tracker, "move", move)

    got = crew_ticket.mint(str(root), "new work", direction="go")

    assert (got["status"], got["warnings"], _tickets(root), _lock_held(root)) == (
        "direction", ["tracker: move to ready raised RuntimeError: board unreadable"],
        ["T-0001"], False)


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


# L-1510. Windows refuses to open a file while another process `os.replace`s
# it (a sharing violation, PermissionError), and `read_text` answers None.
# `_SHARING` makes every OS behave that way for INDEX.md while `replacing` is
# set, so the race the Windows runner hit now and then happens every run.
_SHARING = "The process cannot access the file because it is being used by another process"


def _index_shared_while(monkeypatch, root, replacing):
    index = os.path.normcase(str(root / ".work" / "INDEX.md"))
    real = open

    def sharing(path, *args, **kwargs):
        if replacing() and os.path.normcase(os.fspath(path)) == index:
            raise PermissionError(13, _SHARING, os.fspath(path))
        return real(path, *args, **kwargs)

    monkeypatch.setattr(crew_common, "open", sharing, raising=False)


def test_mint_never_reads_index_while_another_mint_replaces_it(tmp_path, monkeypatch):
    """Windows CI, runs 37221280492 and 37230021739: a concurrent mint died
    with `.work/INDEX.md exists but could not be read` -- its id scan opened
    INDEX while another mint's `create` was replacing it. The other mint holds
    the INDEX lock across its replace here, and the scan opens INDEX inside
    that window unless it waits for the lock, which it must."""
    import crew_config_files  # pylint: disable=import-outside-toplevel
    root = _files_repo(tmp_path, rows="T-0003 | spec | - | r | old\n")
    replacing, started = threading.Event(), threading.Event()
    _index_shared_while(monkeypatch, root, replacing.is_set)

    def other_mint():
        with crew_config_files.Lock(str(root / ".work" / "INDEX.md"), 30):
            replacing.set()
            started.set()
            time.sleep(0.3)
            crew_tracker.create(str(root), "T-0004", "title other")
            replacing.clear()

    other = threading.Thread(target=other_mint)
    other.start()
    started.wait(10)
    try:
        got = crew_ticket.mint(str(root), "new work", direction="go")
    finally:
        other.join(30)

    lines = _index(root).decode("utf-8").splitlines()
    assert (got["ticket"], [line.split(" | ")[0] for line in lines]) == (
        "T-0005", ["T-0003", "T-0004", "T-0005"]), lines


def test_mint_persistently_unreadable_index_still_refuses(tmp_path, monkeypatch):
    """Must-block beside the race: an INDEX that stays unreadable (the same
    PermissionError, never lifting) is still `could not tell`, never `no ids
    taken`. Nothing is claimed and the tracker is never asked."""
    root = _files_repo(tmp_path, rows="T-0003 | spec | - | r | old\n")
    before = _index(root)
    calls = _spy_create(monkeypatch)
    _index_shared_while(monkeypatch, root, lambda: True)

    with pytest.raises(crew_ticket.TicketError) as err:
        crew_ticket.mint(str(root), "new work", direction="go")

    assert (_tickets(root), calls, _index(root) == before,
            ".work/INDEX.md exists but could not be read" in str(err.value)) == (
        [], [], True, True), str(err.value)


@pytest.mark.parametrize("failure", ["busy", "oserror"])
def test_mint_index_lock_failure_during_the_id_scan_claims_nothing(tmp_path, monkeypatch, failure):
    """The id scan's INDEX lock held past the wait (Busy) or failing to be
    created (an OSError) is a refusal before anything is claimed, naming why."""
    import crew_config_files  # pylint: disable=import-outside-toplevel
    root = _files_repo(tmp_path, rows="T-0003 | spec | - | r | old\n")
    before = _index(root)
    calls = _spy_create(monkeypatch)

    def enter(self):
        if failure == "busy":
            raise crew_config_files.Busy(f"{self.path} is held by pid 4242 (waited 30.0s)")
        raise PermissionError(13, "Permission denied", self.path)

    monkeypatch.setattr(crew_config_files.Lock, "__enter__", enter)

    with pytest.raises(crew_ticket.TicketError) as err:
        crew_ticket.mint(str(root), "new work", direction="go")

    named = "held by pid 4242" if failure == "busy" else "Permission denied"
    assert (_tickets(root), calls, _index(root) == before, named in str(err.value),
            "which ids are taken cannot be told" in str(err.value)) == (
        [], [], True, True, True), str(err.value)


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


@pytest.mark.parametrize("status", ["spec", "READY"])
def test_mint_cli_bad_status_is_refused_exit_1(tmp_path, status):
    root = _files_repo(tmp_path)

    done = _cli(root, "mint", "--root", ".", "--title", "x", "--status", status)

    assert (done.returncode, done.stdout.startswith("refused: status "), _tickets(root)) == (
        1, True, [])


def test_mint_cli_direction_status_is_accepted(tmp_path):
    root = _files_repo(tmp_path)

    done = _cli(root, "mint", "--root", ".", "--title", "x", "--status", "direction")

    assert (done.returncode, done.stdout, "T-0001 | direction |" in _index(root).decode(
        "utf-8")) == (0, "ticket=T-0001\n", True), done.stderr


def test_mint_cli_direction_file_bom_is_not_carried(tmp_path):
    root = _files_repo(tmp_path)
    body = pathlib.Path(tmp_path / "direction-body.md")
    body.write_bytes("\ufeff## Ask\nfrom a file\n".encode("utf-8"))

    done = _cli(root, "mint", "--root", ".", "--title", "new work", "--direction-file",
                str(body))

    assert (done.returncode, (root / ".work" / "tickets" / "T-0001" / "direction.md")
            .read_text(encoding="utf-8")) == (
        0, "# T-0001 direction\n## Ask\nfrom a file\n"), done.stderr


# --- review round 2 (Codex): BLOCK :1225, FIX :1161, :1245, :1255, :1377 ------------

def _obsidian(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    root = make_repo(tmp_path)
    (root / ".crew" / "crew.json").write_text(json.dumps({"tracker": {
        "kind": "obsidian", "obsidian": {"vaultPath": str(vault), "boardDir": "Boards/repo",
                                         "board": "Board.md"}}}), encoding="utf-8")
    return root, vault / "Boards" / "repo"


def _board_fails_during(monkeypatch, which):
    """`crew_tracker._board_write` answers `could not update` while `which`
    (`create` or `move`) runs, and writes for real otherwise."""
    real_write, inside = crew_tracker._board_write, []  # pylint: disable=protected-access

    def wrap(name):
        real = getattr(crew_tracker, name)

        def call(*args, **kwargs):
            inside.append(name)
            try:
                return real(*args, **kwargs)
            finally:
                inside.pop()
        monkeypatch.setattr(crew_tracker, name, call)

    def board_write(paths, columns, edit):
        if which in inside:
            return crew_tracker._result(  # pylint: disable=protected-access
                "obsidian", crew_tracker.FAILED, "Boards/repo/Board.md: vault went away")
        return real_write(paths, columns, edit)

    wrap("create")
    wrap("move")
    monkeypatch.setattr(crew_tracker, "_board_write", board_write)


def _index_status(root, ticket):
    for line in (_index(root) or b"").decode("utf-8").splitlines():
        if line.startswith(ticket + " |"):
            return line.split("|")[1].strip()
    return None


def test_mint_board_failure_on_move_reports_the_rows_status(tmp_path, monkeypatch):
    """BLOCK :1225. The files half of the move to `ready` lands and the board
    half fails: mint promised `direction` (the stop autopilot honours), so the
    row is put back to `direction`, and the reported status is the row's."""
    root, _ = _obsidian(tmp_path)
    _board_fails_during(monkeypatch, "move")

    got = crew_ticket.mint(str(root), "new work", direction="go")

    assert (got["status"], _index_status(root, got["ticket"]),
            any("vault went away" in w for w in got["warnings"])) == (
        "direction", "direction", True), got["warnings"]


def test_mint_board_failure_on_move_whose_revert_fails_says_ready(tmp_path, monkeypatch):
    """The neighbouring case: the row cannot be put back, so mint says what
    INDEX holds (`ready`) and never the `direction` it could not keep."""
    root, _ = _obsidian(tmp_path)
    _board_fails_during(monkeypatch, "move")
    real = crew_tracker.move

    def move(where, ticket, status, reopen=False):
        if status == "direction":
            return _report(crew_tracker.FAILED, ".work/INDEX.md changed during write")
        return real(where, ticket, status, reopen=reopen)

    monkeypatch.setattr(crew_tracker, "move", move)

    got = crew_ticket.mint(str(root), "new work", direction="go")

    assert (got["status"], _index_status(root, got["ticket"])) == ("ready", "ready"), got


def test_mint_board_failure_on_create_is_not_a_successful_mint(tmp_path, monkeypatch):
    """FIX :1161. The INDEX row lands but the card does not: mint refuses
    (naming the board and that the ticket is kept), never moves it to ready."""
    root, _ = _obsidian(tmp_path)
    _board_fails_during(monkeypatch, "create")
    moves = []
    real = crew_tracker.move
    monkeypatch.setattr(crew_tracker, "move",
                        lambda *a, **k: moves.append(a) or real(*a, **k))

    with pytest.raises(crew_ticket.TicketError) as err:
        crew_ticket.mint(str(root), "new work", direction="go")

    assert (moves, _index_status(root, "T-0001"), "vault went away" in str(err.value),
            "T-0001 kept" in str(err.value), _tickets(root)) == (
        [], "direction", True, True, ["T-0001"]), str(err.value)


def test_mint_lock_error_releases_the_claimed_folder(tmp_path, monkeypatch):
    """FIX :1245. Creating `INDEX.md.lock` fails with an OSError (not Busy):
    mint refuses with nothing left behind, no folder and no direction. Only
    the claim's lock fails: the id scan takes the same lock first (L-1510),
    and a failure there claims nothing, which is its own test above."""
    import crew_config_files  # pylint: disable=import-outside-toplevel
    root = _files_repo(tmp_path, rows="T-0003 | spec | - | r | old\n")
    before = _index(root)
    real, claimed = crew_config_files.Lock.__enter__, []

    def enter(self):
        if not _tickets(root):
            return real(self)
        claimed.append(_tickets(root))
        raise PermissionError(13, "Permission denied", self.path)

    monkeypatch.setattr(crew_config_files.Lock, "__enter__", enter)

    with pytest.raises(crew_ticket.TicketError) as err:
        crew_ticket.mint(str(root), "new work", direction="go")

    assert (claimed, _tickets(root), _index(root) == before, _no_temp(root),
            "Permission denied" in str(err.value)) == (
        [["T-0004"]], [], True, [], True), str(err.value)


def test_mint_waits_out_a_delete_pending_index_lock(tmp_path, monkeypatch):
    """Windows CI: one of eight concurrent mints exited 1 with
    `T-0003 claimed but not minted: [Errno 13] Permission denied: ...INDEX.md.lock`.
    The previous holder had just removed the lock and Windows still held the
    name DELETE PENDING, which a create answers with access denied. That is a
    held lock: mint waits it out and mints."""
    import crew_config_files  # pylint: disable=import-outside-toplevel
    root = _files_repo(tmp_path)
    lock = str(root / ".work" / "INDEX.md.lock")
    pathlib.Path(lock).write_bytes(b"4242")
    real, denied = os.open, []

    def pending(path, *args, **kwargs):
        if os.path.normcase(str(path)) == os.path.normcase(lock) and len(denied) < 3:
            denied.append(path)
            if len(denied) == 3:
                os.remove(lock)
            raise PermissionError(13, "Permission denied", path)
        return real(path, *args, **kwargs)

    monkeypatch.setattr(crew_config_files.os, "open", pending)

    got = crew_ticket.mint(str(root), "new work", direction="go")

    assert (got["ticket"], len(denied), _tickets(root), _lock_held(root)) == (
        "T-0001", 3, ["T-0001"], False), got


def test_mint_failed_index_write_under_obsidian_removes_its_note(tmp_path, monkeypatch):
    """FIX :1255. The note is claimed, then the INDEX write fails on every
    attempt: mint refuses, and the note it made goes with the folder."""
    root, folder = _obsidian(tmp_path)
    monkeypatch.setattr(crew_tracker, "_files_create", lambda where, ticket, title:
                        crew_tracker._result(  # pylint: disable=protected-access
                            "files", crew_tracker.FAILED, ".work/INDEX.md changed during write"))
    monkeypatch.setattr(crew_ticket, "_MINT_RETRY_PAUSE", 0)

    with pytest.raises(crew_ticket.TicketError):
        crew_ticket.mint(str(root), "new work", direction="go")

    assert (_tickets(root), sorted(p.name for p in folder.iterdir())) == ([], ["Board.md"])


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFOs on this platform")
def test_mint_cli_direction_file_fifo_is_refused_not_waited_on(tmp_path):
    """FIX :1377's neighbour: `mint --direction-file` naming a FIFO with no
    writer refuses at once instead of blocking on the open."""
    root = _files_repo(tmp_path)
    fifo = tmp_path / "direction-body.md"
    os.mkfifo(fifo)

    try:
        done = subprocess.run([sys.executable, SCRIPT, "mint", "--root", ".", "--title", "x",
                               "--direction-file", str(fifo)], capture_output=True, text=True,
                              check=False, cwd=str(root), stdin=subprocess.DEVNULL, timeout=20)
    except subprocess.TimeoutExpired:
        pytest.fail("mint --direction-file blocked on a FIFO")

    assert (done.returncode, done.stdout.startswith("refused: "),
            "not a regular file" in done.stdout, _tickets(root)) == (1, True, True, []), done.stdout
