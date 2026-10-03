"""crew_tracker.py: one tracker interface behind every lifecycle transition (T-0021).

    python3 -m pytest plugin/crew/tests/test_crew_tracker.py -q

Every vault here is a throwaway fixture under `tmp_path`. Nothing in this file
may read or write a real Obsidian vault: the Obsidian backend writes outside
the repository, which is exactly why its must-block cases assert that the
vault AND the repo are byte-identical after a refusal.
"""
import json
import os
import pathlib
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_status
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
    """Same vault and boardDir, so only the whole-block comparison can see it."""
    root = make_repo(tmp_path)
    _crew_json(root, {"kind": "obsidian", "obsidian": {"vaultPath": "/a", "board": "One.md"}})
    _config_json(root, "obsidian", obsidian={"vaultPath": "/a", "board": "Two.md"})

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
    """Once: the second create finds the id held and refuses it (round 3)."""
    root = _files_repo(tmp_path, "T-0001 | done | low | repo | first\n")

    first = crew_tracker.create(str(root), "T-0002", "second")
    again = crew_tracker.create(str(root), "T-0002", "second")

    assert ([r["state"] for r in first["results"] + again["results"]], _index(root)) == (
        ["updated", "could not update"],
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

    def racing(path, dir_fd=None):
        calls.append(path)
        if len(calls) == 2:
            with open(index, "a", encoding="utf-8", newline="\n") as handle:
                handle.write("T-0002 | direction | - | repo | other session\n")
        return real(path, dir_fd=dir_fd)

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

    def always_racing(path, dir_fd=None):
        calls.append(path)
        if len(calls) % 2 == 0:
            with open(index, "a", encoding="utf-8", newline="\n") as handle:
                handle.write(f"T-10{len(calls)} | direction | - | repo | noise\n")
        return real(path, dir_fd=dir_fd)

    monkeypatch.setattr(crew_tracker, "_read_bytes", always_racing)

    got = crew_tracker.move(str(root), "T-0001", "planned")

    assert (got["results"][0]["reason"], "planned" in _index(root)) == (
        ".work/INDEX.md changed during write", False)


def test_cli_rejects_a_malformed_ticket_id(tmp_path):
    root = _files_repo(tmp_path)

    done = _cli(root, "move", "--ticket", "../etc", "--to", "spec")

    assert done.returncode == 2


# --- the Kanban board: parse and edit without disturbing it --------------------

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tracker_fixtures")
COLUMNS = dict(crew_tracker.DEFAULT_COLUMNS)
RENAMED = {"backlog": "Icebox", "ready": "Todo", "inProgress": "Doing",
           "review": "QA", "done": "Shipped"}


def _fixture(name):
    # LF by intent; a CRLF checkout of the fixture must not change what is tested.
    with open(os.path.join(FIXTURES, name), "rb") as handle:
        return handle.read().decode("utf-8").replace("\r\n", "\n")


def _board(name, columns=None):
    board, problem = crew_tracker.parse_board(_fixture(name), columns or COLUMNS)
    assert problem is None, problem
    return board


def _lane_of(text, ticket, columns=None):
    board, problem = crew_tracker.parse_board(text, columns or COLUMNS)
    assert problem is None, problem
    card, problem = crew_tracker.find_card(board, ticket)
    assert problem is None, problem
    return card["lane"]


def test_parse_0_20_board():
    board = _board("board_0_20.md")

    card, problem = crew_tracker.find_card(board, "T-0042")

    assert (card["lane"], problem) == ("Ready", None)


def test_move_changes_only_the_card():
    old = _fixture("board_with_archive.md")
    card = "- [ ] [[T-0042]] Fix token refresh on 401\n"
    expected = old.replace(card, "", 1).replace(
        "## In Progress\n\n", "## In Progress\n\n" + card, 1)

    new, moved_from, problem = crew_tracker.move_card(_board("board_with_archive.md"), "T-0042", "inProgress")

    assert (new, moved_from, problem) == (expected, "Ready", None)


def test_move_carries_continuation_lines():
    old = _fixture("board_with_archive.md")
    card = ("- [ ] [[T-0051]] a card with a body\n"
            "\tcontinuation line one\n\tcontinuation line two\n")
    expected = old.replace(card, "", 1).replace("## Review\n\n", "## Review\n\n" + card, 1)

    new, _, _ = crew_tracker.move_card(_board("board_with_archive.md"), "T-0051", "review")

    assert new == expected


def test_move_to_done_checks_and_sits_below_complete():
    old = _fixture("board_0_20.md")
    expected = old.replace("- [ ] [[T-0042]] Fix token refresh on 401\n", "", 1).replace(
        "**Complete**\n\n", "**Complete**\n\n- [x] [[T-0042]] Fix token refresh on 401\n", 1)

    new, _, _ = crew_tracker.move_card(_board("board_0_20.md"), "T-0042", "done")

    assert new == expected


def test_leaving_done_unchecks_the_card():
    new, moved_from, _ = crew_tracker.move_card(_board("board_0_20.md"), "T-0039", "review")

    assert (moved_from, "## Review\n\n- [ ] [[T-0039]] Bump pinned deps\n" in new,
            "[x] [[T-0039]]" in new) == ("Done", True, False)


def test_move_to_the_lane_it_is_in_is_unchanged():
    old = _fixture("board_0_20.md")

    new, moved_from, problem = crew_tracker.move_card(_board("board_0_20.md"), "T-0042", "ready")

    assert (new, moved_from, problem) == (old, "Ready", None)


def test_archive_untouched():
    old = _fixture("board_with_archive.md")
    cut = old.index("***\n")

    new, _, problem = crew_tracker.move_card(_board("board_with_archive.md"), "T-0042", "done")

    assert (problem, new[new.index("***\n"):]) == (None, old[cut:])


def test_card_identity_is_its_first_id():
    """T-0043's card mentions T-0042 as a dependency; that is not a second T-0042 card."""
    board = _board("board_with_archive.md")

    card, problem = crew_tracker.find_card(board, "T-0042")

    assert (card["lane"], problem) == ("Ready", None)


def test_bare_id_card_is_found_but_a_longer_id_is_not():
    text = _fixture("board_0_20.md").replace("[[T-0042]]", "T-0042")
    board, _ = crew_tracker.parse_board(text, COLUMNS)

    found, _ = crew_tracker.find_card(board, "T-0042")
    longer, problem = crew_tracker.find_card(board, "T-004")

    assert (found["lane"], longer, problem) == ("Ready", None, "no card for T-004 on the board")


def test_renamed_lanes_from_columns():
    board = _board("board_renamed_lanes.md", RENAMED)

    new, moved_from, _ = crew_tracker.move_card(board, "T-0042", "inProgress")

    assert (moved_from, _lane_of(new, "T-0042", RENAMED)) == ("Todo", "Doing")


def test_default_columns_on_a_renamed_board_refused():
    _, problem = crew_tracker.parse_board(_fixture("board_renamed_lanes.md"), COLUMNS)

    assert problem == "lane 'Backlog' (obsidian.columns.backlog) is not on the board"


def test_missing_frontmatter_refused():
    _, problem = crew_tracker.parse_board(_fixture("board_no_frontmatter.md"), COLUMNS)

    assert problem == "not a Kanban board: no 'kanban-plugin: board' in its frontmatter"


def test_duplicate_lane_refused():
    _, problem = crew_tracker.parse_board(_fixture("board_duplicate_lane.md"), COLUMNS)

    assert problem == "lane 'Ready' appears 2 times on the board"


def test_settings_block_not_last_refused():
    text = _fixture("board_0_20.md") + "\n## Stray\n"

    _, problem = crew_tracker.parse_board(text, COLUMNS)

    assert problem == "the %% kanban:settings block is not the last thing on the board"


def test_two_cards_same_id_refused():
    text = _fixture("board_0_20.md").replace(
        "## Review\n", "## Review\n\n- [ ] [[T-0042]] a copy\n", 1)
    board, _ = crew_tracker.parse_board(text, COLUMNS)

    card, problem = crew_tracker.find_card(board, "T-0042")

    assert (card, problem) == (None, "2 cards for T-0042 on the board (Ready, Review)")


def test_add_card_is_the_first_backlog_item():
    old = _fixture("board_with_archive.md")
    expected = old.replace("## Backlog\n\n", "## Backlog\n\n- [ ] [[T-0060]] new work\n", 1)

    new, problem = crew_tracker.add_card(_board("board_with_archive.md"), "T-0060", "new work", "backlog")

    assert (new, problem) == (expected, None)


def test_add_card_into_an_empty_lane():
    old = _fixture("board_0_20.md")
    expected = old.replace("## Backlog\n\n", "## Backlog\n\n- [ ] [[T-0060]] new work\n", 1)

    new, _ = crew_tracker.add_card(_board("board_0_20.md"), "T-0060", "new work", "backlog")

    assert new == expected


def test_add_card_already_present_is_unchanged():
    old = _fixture("board_0_20.md")

    new, problem = crew_tracker.add_card(_board("board_0_20.md"), "T-0042", "again", "backlog")

    assert (new, problem) == (old, None)


def test_crlf_board_keeps_its_line_endings():
    old = _fixture("board_0_20.md").replace("\n", "\r\n")
    board, _ = crew_tracker.parse_board(old, COLUMNS)

    new, _, _ = crew_tracker.move_card(board, "T-0042", "review")

    assert (new.count("\r\n"), new.count("\n")) == (old.count("\r\n"), old.count("\n"))


# --- the Obsidian backend: confinement and atomic replace -----------------------

CARD = "T-0042"
ROW = "T-0042 | spec | low | repo | Fix token refresh on 401\n"


def _make_vault(where, board="board_0_20.md", board_dir="Boards/repo", dot_obsidian=True):
    (where / board_dir).mkdir(parents=True)
    if dot_obsidian:
        (where / ".obsidian").mkdir()
    (where / board_dir / "Board.md").write_text(_fixture(board), encoding="utf-8", newline="\n")
    return where


def _own(root, folder, ticket=CARD):
    """The note that makes `ticket`'s card this repo's: `repo-id:` is the only
    evidence of ownership a shared board carries (review round 3)."""
    (folder / f"{ticket}.md").write_text(
        f"# {ticket}\n\n- repo-id: {crew_tracker.repo_id(str(root))}\n", encoding="utf-8", newline="\n")


def _obsidian_repo(tmp_path, vault_path, own=True, **settings):
    """A repo on `vault_path`'s board whose T-0042 card is its own (`own`) --
    unless there is no board directory yet to hold the note."""
    root = make_repo(tmp_path)
    obsidian = {"vaultPath": str(vault_path), "boardDir": "Boards/repo", "board": "Board.md"}
    obsidian.update(settings)
    _crew_json(root, {"kind": "obsidian", "obsidian": obsidian})
    (root / ".work" / "INDEX.md").write_text(ROW, encoding="utf-8", newline="\n")
    board_dir = obsidian["boardDir"]
    inside = isinstance(board_dir, str) and not os.path.isabs(board_dir) and ".." not in board_dir
    folder = pathlib.Path(vault_path) / (board_dir if inside else "")
    if own and inside and folder.is_dir():
        _own(root, folder)
    return root


def _symlink(link, target, is_dir=False):
    try:
        link.symlink_to(target, target_is_directory=is_dir)
    except OSError as exc:
        pytest.skip(f"cannot create a symlink here: {exc}")


def _snapshot(*dirs):
    """Every file and link under `dirs` (a repo's .git excluded), as bytes or link target."""
    seen = {}
    for top in dirs:
        for base, subdirs, files in os.walk(top):
            subdirs[:] = [d for d in subdirs if d != ".git"]
            for name in subdirs + files:
                path = os.path.join(base, name)
                if os.path.islink(path):
                    seen[path] = ("link", os.readlink(path))
                elif os.path.isfile(path):
                    with open(path, "rb") as handle:
                        seen[path] = handle.read()
    return seen


def _refused(tmp_path, root, action=("move", "--ticket", CARD, "--to", "in-progress")):
    before = _snapshot(tmp_path)
    done = _cli(root, *action)
    return done, _snapshot(tmp_path) == before


def test_vault_missing(tmp_path):
    root = _obsidian_repo(tmp_path, tmp_path / "no-such-vault")

    done, untouched = _refused(tmp_path, root)

    assert (done.returncode, untouched, done.stdout) == (
        1, True, f"obsidian: could not update: vault missing: {tmp_path / 'no-such-vault'}\n")


def test_vault_without_dot_obsidian(tmp_path):
    vault = _make_vault(tmp_path / "vault", dot_obsidian=False)
    root = _obsidian_repo(tmp_path, vault)

    done, untouched = _refused(tmp_path, root)

    assert (done.returncode, untouched, "has no .obsidian/" in done.stdout) == (1, True, True)


@pytest.mark.parametrize("board_dir", ["../outside", "Boards/../Boards/repo"])
def test_board_dir_dotdot(tmp_path, board_dir):
    vault = _make_vault(tmp_path / "vault")
    _make_vault(tmp_path / "outside", board_dir=".")
    root = _obsidian_repo(tmp_path, vault, boardDir=board_dir)

    done, untouched = _refused(tmp_path, root)

    assert (done.returncode, untouched, done.stdout) == (
        1, True, f"obsidian: could not update: obsidian.boardDir {board_dir!r} may not contain '..'\n")


def test_board_dir_absolute(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault, boardDir=str(vault / "Boards" / "repo"))

    done, untouched = _refused(tmp_path, root)

    assert (done.returncode, untouched, "must be relative to the vault" in done.stdout) == (1, True, True)


def test_board_name_with_separator(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault, boardDir="Boards", board="repo/Board.md")

    done, untouched = _refused(tmp_path, root)

    assert (done.returncode, untouched, "must be a bare file name" in done.stdout) == (1, True, True)


def test_board_symlink_outside_vault(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    outside = _make_vault(tmp_path / "outside", board_dir=".")
    board = vault / "Boards" / "repo" / "Board.md"
    board.unlink()
    _symlink(board, outside / "Board.md")
    root = _obsidian_repo(tmp_path, vault)

    done, untouched = _refused(tmp_path, root)

    assert (done.returncode, untouched, "resolves outside the vault" in done.stdout) == (1, True, True)


def test_note_symlink_outside_vault(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    _symlink(vault / "Boards" / "repo" / "T-0060.md", tmp_path / "outside-note.md")
    root = _obsidian_repo(tmp_path, vault)

    done, untouched = _refused(tmp_path, root, ("create", "--ticket", "T-0060", "--title", "new"))

    assert (done.returncode, untouched, "resolves outside the vault" in done.stdout) == (1, True, True)


def test_vault_in_worktree_not_ignored(tmp_path):
    root = make_repo(tmp_path)
    vault = _make_vault(root / "vault")
    _crew_json(root, {"kind": "obsidian", "obsidian": {"vaultPath": str(vault), "boardDir": "Boards/repo"}})
    (root / ".work" / "INDEX.md").write_text(ROW, encoding="utf-8", newline="\n")

    done, untouched = _refused(tmp_path, root)

    assert (done.returncode, untouched, "would enter the review bundle" in done.stdout) == (1, True, True)


def test_kind_could_not_tell_writes_nothing(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)
    _config_json(root, "files")

    done, untouched = _refused(tmp_path, root)

    assert (done.returncode, untouched, done.stdout.startswith(
        "tracker: could not update: tracker kind could not tell: ")) == (1, True, True)


@pytest.mark.parametrize("board,settings,reason", [
    ("board_no_frontmatter.md", {}, "not a Kanban board"),
    ("board_duplicate_lane.md", {}, "appears 2 times"),
    ("board_renamed_lanes.md", {}, "is not on the board"),
])
def test_unusable_board_writes_nothing(tmp_path, board, settings, reason):
    vault = _make_vault(tmp_path / "vault", board=board)
    root = _obsidian_repo(tmp_path, vault, **settings)

    done, untouched = _refused(tmp_path, root)

    assert (done.returncode, untouched, reason in done.stdout) == (1, True, True)


def test_board_file_missing_writes_nothing(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    (vault / "Boards" / "repo" / "Board.md").unlink()
    root = _obsidian_repo(tmp_path, vault)

    done, untouched = _refused(tmp_path, root)

    assert (done.returncode, untouched, "no board at Boards/repo/Board.md" in done.stdout) == (1, True, True)


def test_obsidian_move_updates_index_and_board(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)

    done = _cli(root, "move", "--ticket", CARD, "--to", "in-progress")
    board = (vault / "Boards" / "repo" / "Board.md").read_text(encoding="utf-8")

    assert (done.returncode, done.stdout, _index(root), _lane_of(board, CARD)) == (
        0,
        "files: updated: .work/INDEX.md spec -> in-progress\n"
        "obsidian: updated: Boards/repo/Board.md Ready -> In Progress\n",
        ROW.replace("spec", "in-progress"), "In Progress")


def test_obsidian_move_leaves_no_temp_file(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)

    _cli(root, "move", "--ticket", CARD, "--to", "review")

    assert sorted(os.listdir(vault / "Boards" / "repo")) == ["Board.md", "T-0042.md"]


def test_board_failure_keeps_the_files_half(tmp_path, monkeypatch):
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)
    board = vault / "Boards" / "repo" / "Board.md"
    real = crew_tracker._read_bytes  # pylint: disable=protected-access
    calls = {"n": 0}

    def racing(path, dir_fd=None):
        """Every re-read of the board sees different bytes: Obsidian keeps saving."""
        if os.path.basename(path) == board.name:
            calls["n"] += 1
            if calls["n"] % 2 == 0:
                return real(path, dir_fd=dir_fd) + b"\n"
        return real(path, dir_fd=dir_fd)

    monkeypatch.setattr(crew_tracker, "_read_bytes", racing)

    got = crew_tracker.move(str(root), CARD, "review")

    assert ([r["state"] for r in got["results"]], _index(root), crew_tracker.exit_code(got)) == (
        ["updated", "could not update"], ROW.replace("spec", "review"), 1)


def test_nested_board_dir(tmp_path):
    vault = _make_vault(tmp_path / "vault", board_dir="Boards/a/b/c")
    root = _obsidian_repo(tmp_path, vault, boardDir="Boards/a/b/c")

    done = _cli(root, "move", "--ticket", CARD, "--to", "review")

    assert (done.returncode, _lane_of((vault / "Boards/a/b/c/Board.md").read_text(encoding="utf-8"), CARD)) == (
        0, "Review")


def test_vault_path_with_spaces(tmp_path):
    vault = _make_vault(tmp_path / "my vault")
    root = _obsidian_repo(tmp_path, vault)

    done = _cli(root, "move", "--ticket", CARD, "--to", "review")

    assert (done.returncode, _lane_of((vault / "Boards/repo/Board.md").read_text(encoding="utf-8"), CARD)) == (
        0, "Review")


def test_vault_is_symlink(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    _symlink(tmp_path / "vault-link", vault, is_dir=True)
    root = _obsidian_repo(tmp_path, tmp_path / "vault-link")

    done = _cli(root, "move", "--ticket", CARD, "--to", "review")

    assert (done.returncode, _lane_of((vault / "Boards/repo/Board.md").read_text(encoding="utf-8"), CARD)) == (
        0, "Review")


def test_vault_in_worktree_ignored(tmp_path):
    root = make_repo(tmp_path)
    vault = _make_vault(root / "vault")
    (root / ".gitignore").write_text("vault/\n", encoding="utf-8")
    _crew_json(root, {"kind": "obsidian", "obsidian": {"vaultPath": str(vault), "boardDir": "Boards/repo"}})
    (root / ".work" / "INDEX.md").write_text(ROW, encoding="utf-8", newline="\n")
    _own(root, vault / "Boards" / "repo")

    done = _cli(root, "move", "--ticket", CARD, "--to", "review")

    assert (done.returncode, _lane_of((vault / "Boards/repo/Board.md").read_text(encoding="utf-8"), CARD)) == (
        0, "Review")


def test_obsidian_create_adds_row_card_and_note(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)

    done = _cli(root, "create", "--ticket", "T-0060", "--title", "new work")
    board = (vault / "Boards" / "repo" / "Board.md").read_text(encoding="utf-8")
    note = (vault / "Boards" / "repo" / "T-0060.md").read_text(encoding="utf-8")

    assert (done.returncode, _lane_of(board, "T-0060"), note.startswith('---\ntitle: "new work"\ncreated: '),
            (root / ".work" / "tickets" / "T-0060").as_uri() in note) == (0, "Backlog", True, True)


def test_note_created_once_never_overwritten(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)
    _cli(root, "create", "--ticket", "T-0060", "--title", "new work")
    note = vault / "Boards" / "repo" / "T-0060.md"
    edited = note.read_text(encoding="utf-8") + "a human edited this\n"
    note.write_text(edited, encoding="utf-8")
    (root / ".work" / "INDEX.md").write_text(ROW, encoding="utf-8", newline="\n")

    done = _cli(root, "create", "--ticket", "T-0060", "--title", "new work")

    assert (done.returncode, note.read_text(encoding="utf-8"), done.stdout.splitlines()[1:]) == (
        0, edited, ["obsidian: unchanged: Boards/repo/Board.md already has T-0060",
                    "obsidian-note: unchanged: Boards/repo/T-0060.md exists; never rewritten"])


def test_read_reports_disagreement(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)
    board = vault / "Boards" / "repo" / "Board.md"
    text = board.read_text(encoding="utf-8")
    moved, _, _ = crew_tracker.move_card(crew_tracker.parse_board(text, COLUMNS)[0], CARD, "inProgress")
    board.write_text(moved, encoding="utf-8", newline="\n")

    got = crew_tracker.read(str(root), CARD)

    assert [(r["backend"], r.get("status") or r.get("lane"), r.get("disagree")) for r in got["results"]] == [
        ("files", "spec", None), ("obsidian", "In Progress", True)]


def test_read_reports_agreement(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)

    got = crew_tracker.read(str(root), CARD)

    assert got["results"][1]["disagree"] is False


def test_jira_move_is_delegated_and_writes_nothing(tmp_path):
    root = make_repo(tmp_path)
    _crew_json(root, {"kind": "jira", "jira": {"project": "ABC"}})
    before = _snapshot(tmp_path)

    done = _cli(root, "move", "--ticket", "ABC-12", "--to", "in-progress")

    assert (done.returncode, done.stdout, _snapshot(tmp_path) == before) == (
        3, "jira: delegated: run /crew:jira-sync ABC-12 --push --to in-progress\n", True)


def test_sdp_move_is_delegated(tmp_path):
    root = make_repo(tmp_path)
    _config_json(root, "sdp")

    done = _cli(root, "move", "--ticket", "SDP-40219", "--to", "done")

    assert (done.returncode, done.stdout) == (3, "sdp: delegated: run /crew:sdp-sync SDP-40219 --push --to done\n")


def test_jira_create_is_delegated_to_mcp(tmp_path):
    root = make_repo(tmp_path)
    _config_json(root, "jira")

    done = _cli(root, "create", "--ticket", "ABC-12", "--title", "t")

    assert (done.returncode, done.stdout) == (
        3, "jira: delegated: create the tracker item through MCP, as brainstorm.md step 1 says\n")


# --- /crew:status reads the tracker through resolve ------------------------------

def test_status_tracker_could_not_tell(tmp_path):
    root = make_repo(tmp_path)
    _crew_json(root, {"kind": "files"})
    _config_json(root, "obsidian")

    lines = crew_status.collect(str(root))

    assert [line for line in lines if line.startswith("tracker")] == [
        "tracker  could not tell - .crew/crew.json says tracker.kind 'files', "
        ".crew/config.json says tracker 'obsidian'"]


def test_status_tracker_names_its_source(tmp_path):
    root = make_repo(tmp_path)
    _config_json(root, "obsidian")

    lines = crew_status.collect(str(root))

    assert [line for line in lines if line.startswith("tracker")] == [
        "tracker  obsidian (from .crew/config.json)"]


# --- guard branches the sabotage table names -----------------------------------

def test_board_that_is_a_directory_is_refused(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    board = vault / "Boards" / "repo" / "Board.md"
    board.unlink()
    board.mkdir()
    root = _obsidian_repo(tmp_path, vault)

    done, untouched = _refused(tmp_path, root)

    assert (done.returncode, untouched, "is not a regular file" in done.stdout) == (1, True, True)


def test_frontmatter_without_the_kanban_key_refused():
    text = _fixture("board_0_20.md").replace("kanban-plugin: board\n", "type: meta\n", 1)

    _, problem = crew_tracker.parse_board(text, COLUMNS)

    assert problem == "not a Kanban board: no 'kanban-plugin: board' in its frontmatter"


def test_vault_in_worktree_git_cannot_say_is_refused(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    vault = _make_vault(root / "vault")
    _crew_json(root, {"kind": "obsidian", "obsidian": {"vaultPath": str(vault), "boardDir": "Boards/repo"}})
    (root / ".work" / "INDEX.md").write_text(ROW, encoding="utf-8", newline="\n")
    monkeypatch.setattr(crew_tracker, "_git_ignored", lambda repo, path: None)
    before = _snapshot(tmp_path)

    got = crew_tracker.move(str(root), CARD, "review")

    assert (got["results"][0]["reason"], _snapshot(tmp_path) == before) == (
        "could not tell whether git ignores Boards/repo/Board.md in this worktree", True)


def test_files_move_refuses_two_rows_for_one_ticket(tmp_path):
    rows = "T-0001 | spec | low | repo | t\nT-0001 | planned | low | repo | t again\n"
    root = _files_repo(tmp_path, rows)

    got = crew_tracker.move(str(root), "T-0001", "review")

    assert (got["results"][0]["reason"], _index(root)) == (".work/INDEX.md has 2 rows for T-0001", rows)


def test_obsidian_move_without_a_card_writes_nothing(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)
    (root / ".work" / "INDEX.md").write_text(ROW + ROW.replace("T-0042", "T-0077"), encoding="utf-8")

    done, untouched = _refused(tmp_path, root, ("move", "--ticket", "T-0077", "--to", "review"))

    assert (done.returncode, untouched, done.stdout) == (
        1, True, "obsidian: could not update: no card for T-0077 on the board\n")


def test_every_tracker_sabotage_anchor_is_present_exactly_once():
    """An edit that moves a line a mutation aims at would otherwise leave that
    mutation testing nothing until somebody paid for a full sabotage run."""
    import sabotage_tracker  # pylint: disable=import-outside-toplevel

    lost = []
    for label, target, find, _replace, _test in sabotage_tracker.TRACKER_MUTATIONS:
        with open(target, encoding="utf-8", newline="") as handle:
            if handle.read().count(find) != 1:
                lost.append(label)

    assert not lost, lost


def test_an_unreadable_index_is_could_not_update_not_a_traceback(tmp_path):
    root = _files_repo(tmp_path)
    (root / ".work" / "INDEX.md").mkdir()

    done = _cli(root, "move", "--ticket", "T-0001", "--to", "spec")

    assert (done.returncode, done.stdout.startswith("files: could not update: .work/INDEX.md: "),
            done.stderr) == (1, True, "")


# --- review round 1 (T-0021): each test is a reviewer repro, run first ---------

def _needs_root():
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        pytest.skip("giving a file to another uid needs root")


def test_planted_temp_symlink_is_never_followed(tmp_path):
    """The round-1 BLOCK, verbatim: a link sitting at the temp name the old code
    used must not receive the board, and Board.md must stay a regular file."""
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)
    victim = tmp_path / "outside" / "victim.txt"
    victim.parent.mkdir()
    victim.write_text("victim\n", encoding="utf-8")
    board = vault / "Boards" / "repo" / "Board.md"
    _symlink(vault / "Boards" / "repo" / f".Board.md.crew-{os.getpid()}.tmp", victim)

    got = crew_tracker.move(str(root), CARD, "review")

    assert (got["results"][1]["state"], victim.read_text(encoding="utf-8"), board.is_symlink(),
            _lane_of(board.read_text(encoding="utf-8"), CARD)) == ("updated", "victim\n", False, "Review")


def test_temp_name_collision_never_follows_a_link(tmp_path, monkeypatch):
    """Exclusive create is the guard, not an unguessable name: even when every
    temp name tried is a planted link, nothing is written through it."""
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)
    victim = tmp_path / "victim.txt"
    victim.write_text("victim\n", encoding="utf-8")
    board = vault / "Boards" / "repo" / "Board.md"
    before = board.read_bytes()
    _symlink(vault / "Boards" / "repo" / ".planted.tmp", victim)
    monkeypatch.setattr(crew_tracker, "_temp_name", lambda name: ".planted.tmp")

    got = crew_tracker.move(str(root), CARD, "review")

    assert (got["results"][1]["state"], victim.read_text(encoding="utf-8"), board.is_symlink(),
            board.read_bytes() == before) == ("could not update", "victim\n", False, True)


@pytest.mark.skipif(os.name == "nt", reason="Windows has no group/other mode bits: chmod only sets read-only, "
                    "so 0o664 reads back as 0o666 and there is no mode to keep")
def test_board_keeps_its_mode(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)
    board = vault / "Boards" / "repo" / "Board.md"
    os.chmod(board, 0o664)

    crew_tracker.move(str(root), CARD, "review")

    assert (oct(board.stat().st_mode & 0o7777), _lane_of(board.read_text(encoding="utf-8"), CARD)) == (
        "0o664", "Review")


def test_board_keeps_its_owner(tmp_path):
    _needs_root()
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)
    board = vault / "Boards" / "repo" / "Board.md"
    os.chown(board, 12345, 12346)

    crew_tracker.move(str(root), CARD, "review")

    assert (board.stat().st_uid, board.stat().st_gid, _lane_of(board.read_text(encoding="utf-8"), CARD)) == (
        12345, 12346, "Review")


def test_new_note_takes_its_directory_owner_when_root(tmp_path):
    _needs_root()
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)
    folder = vault / "Boards" / "repo"
    os.chown(folder, 12345, 12346)
    os.chown(folder / "Board.md", 12345, 12346)

    crew_tracker.create(str(root), "T-0060", "new work")
    note = folder / "T-0060.md"

    assert (note.stat().st_uid, note.stat().st_gid, (folder / "Board.md").stat().st_uid) == (12345, 12346, 12345)


def _vault_around_repo(tmp_path, board_dir, ignore=None):
    """A vault at tmp_path that CONTAINS the repo at tmp_path/repo."""
    root = make_repo(tmp_path)
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / board_dir).mkdir(parents=True)
    (tmp_path / board_dir / "Board.md").write_text(_fixture("board_0_20.md"), encoding="utf-8", newline="\n")
    if ignore:
        (root / ".gitignore").write_text(ignore, encoding="utf-8")
    _crew_json(root, {"kind": "obsidian", "obsidian": {"vaultPath": str(tmp_path), "boardDir": board_dir}})
    (root / ".work" / "INDEX.md").write_text(ROW, encoding="utf-8", newline="\n")
    _own(root, tmp_path / board_dir)
    return root


def test_board_inside_worktree_of_a_vault_that_contains_it_is_refused(tmp_path):
    root = _vault_around_repo(tmp_path, "repo/boards")

    done, untouched = _refused(tmp_path, root)

    assert (done.returncode, untouched, "would enter the review bundle" in done.stdout) == (1, True, True)


def test_board_inside_worktree_that_git_ignores_is_allowed(tmp_path):
    root = _vault_around_repo(tmp_path, "repo/boards", ignore="boards/\n")

    done = _cli(root, "move", "--ticket", CARD, "--to", "review")

    assert (done.returncode, _lane_of((tmp_path / "repo/boards/Board.md").read_text(encoding="utf-8"), CARD)) == (
        0, "Review")


def test_board_outside_worktree_of_a_vault_that_contains_it_is_allowed(tmp_path):
    root = _vault_around_repo(tmp_path, "Boards/repo")

    done = _cli(root, "move", "--ticket", CARD, "--to", "review")

    assert (done.returncode, _lane_of((tmp_path / "Boards/repo/Board.md").read_text(encoding="utf-8"), CARD)) == (
        0, "Review")


@pytest.mark.parametrize("sep", ["\u2028", "\u2029", "\x85", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e"])
def test_title_with_a_line_separator_is_refused(tmp_path, sep):
    root = _files_repo(tmp_path, "T-0001 | done | low | repo | first\n")

    got = crew_tracker.create(str(root), "T-0002", f"split{sep}tail")

    assert (got["results"][0]["state"], _index(root)) == (
        "could not update", "T-0001 | done | low | repo | first\n")


def test_a_human_card_holding_a_line_separator_moves_whole():
    """Obsidian keeps U+2028 inside a line; str.splitlines does not. Splitting
    the board there would move half a card and strand the rest."""
    text = _fixture("board_0_20.md").replace("Fix token refresh on 401", "Fix token\u2028refresh on 401", 1)
    board, problem = crew_tracker.parse_board(text, COLUMNS)
    assert problem is None, problem

    moved, _, why = crew_tracker.move_card(board, CARD, "review")

    assert (why, moved.count("\u2028"), "- [ ] [[T-0042]] Fix token\u2028refresh on 401\n" in moved,
            _lane_of(moved, CARD)) == (None, 1, True, "Review")


def _named_repo(tmp_path, name, vault, rows=""):
    """A repo whose git name is `name`, sharing `vault`'s top-level board."""
    made = make_repo(tmp_path / name)
    root = tmp_path / name / name
    os.rename(made, root)
    _crew_json(root, {"kind": "obsidian", "obsidian": {"vaultPath": str(vault)}})
    (root / ".work" / "INDEX.md").write_text(rows, encoding="utf-8", newline="\n")
    return root


def test_create_refuses_a_card_on_a_shared_board_no_note_claims(tmp_path):
    """The round-1 repro: repo A's T-0042 sits on the default (shared) board with
    no note; repo B minting its own T-0042 must not adopt A's card."""
    vault = _make_vault(tmp_path / "vault", board_dir=".")
    other = _named_repo(tmp_path, "beta", vault)

    done, untouched = _refused(tmp_path, other, ("create", "--ticket", CARD, "--title", "B's work"))

    assert (done.returncode, untouched, "could not tell whose" in done.stdout) == (1, True, True)


def test_create_refuses_a_ticket_another_repo_owns(tmp_path):
    vault = _make_vault(tmp_path / "vault", board_dir=".")
    first = _named_repo(tmp_path, "alpha", vault)
    other = _named_repo(tmp_path, "beta", vault)
    assert _cli(first, "create", "--ticket", "T-0060", "--title", "A's work").returncode == 0

    done, untouched = _refused(tmp_path, other, ("create", "--ticket", "T-0060", "--title", "B's work"))

    assert (done.returncode, untouched, "belongs to another repo" in done.stdout) == (1, True, True)


def test_move_refuses_a_card_another_repo_owns(tmp_path):
    vault = _make_vault(tmp_path / "vault", board_dir=".")
    first = _named_repo(tmp_path, "alpha", vault)
    other = _named_repo(tmp_path, "beta", vault, rows="T-0060 | direction | - | beta | B's work\n")
    assert _cli(first, "create", "--ticket", "T-0060", "--title", "A's work").returncode == 0

    done, untouched = _refused(tmp_path, other, ("move", "--ticket", "T-0060", "--to", "done"))

    assert (done.returncode, untouched, "belongs to another repo" in done.stdout) == (1, True, True)


def test_move_without_this_repos_index_row_writes_nothing(tmp_path):
    vault = _make_vault(tmp_path / "vault", board_dir=".")
    other = _named_repo(tmp_path, "beta", vault)

    done, untouched = _refused(tmp_path, other, ("move", "--ticket", CARD, "--to", "done"))

    assert (done.returncode, untouched, done.stdout) == (
        1, True, "obsidian: could not update: no .work/INDEX.md row for T-0042 in this repo\n")


def test_read_refuses_a_card_another_repo_owns(tmp_path):
    vault = _make_vault(tmp_path / "vault", board_dir=".")
    first = _named_repo(tmp_path, "alpha", vault)
    other = _named_repo(tmp_path, "beta", vault, rows="T-0060 | direction | - | beta | B's work\n")
    assert _cli(first, "create", "--ticket", "T-0060", "--title", "A's work").returncode == 0

    got = crew_tracker.read(str(other), "T-0060")

    assert (got["results"][1]["state"], "belongs to another repo" in got["results"][1]["reason"]) == (
        "could not read", True)


def test_ready_status_maps_to_the_backlog_lane(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)
    _cli(root, "create", "--ticket", "T-0060", "--title", "new work")

    done = _cli(root, "move", "--ticket", "T-0060", "--to", "ready")
    board = (vault / "Boards" / "repo" / "Board.md").read_text(encoding="utf-8")

    assert (done.returncode, "T-0060 | ready |" in _index(root), _lane_of(board, "T-0060")) == (0, True, "Backlog")


@pytest.mark.parametrize("row", ["| T-0001\n", "T-0001 |\n", "| T-0001 |\n"])
def test_index_row_without_a_status_cell_is_could_not_update(tmp_path, row):
    root = _files_repo(tmp_path, row)

    done = _cli(root, "move", "--ticket", "T-0001", "--to", "spec")

    assert (done.returncode, done.stdout, done.stderr, _index(root)) == (
        1, "files: could not update: .work/INDEX.md row for T-0001 has no status cell\n", "", row)


def test_read_of_a_row_without_a_status_cell_is_could_not_read(tmp_path):
    root = _files_repo(tmp_path, "| T-0001\n")

    got = crew_tracker.read(str(root), "T-0001")

    assert got["results"][0] == {"backend": "files", "state": "could not read",
                                 "reason": ".work/INDEX.md row for T-0001 has no status cell", "command": None}


def test_create_with_work_a_file_is_could_not_update(tmp_path):
    root = _files_repo(tmp_path)
    (root / ".work").rmdir()
    (root / ".work").write_text("", encoding="utf-8")

    done = _cli(root, "create", "--ticket", "T-0001", "--title", "x")

    assert (done.returncode, done.stdout.startswith("files: could not update: .work: "), done.stderr) == (1, True, "")


@pytest.mark.parametrize("board", [5, ["Board.md"], None])
def test_non_string_board_name_is_refused(tmp_path, board):
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault, board=board)

    done, untouched = _refused(tmp_path, root)

    assert (done.returncode, untouched, "must be a bare file name" in done.stdout, done.stderr) == (1, True, True, "")


def test_read_says_when_no_note_names_the_cards_repo(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault, own=False)

    done = _cli(root, "read", "--ticket", CARD)

    assert (done.returncode, done.stdout.splitlines()[1]) == (
        0, "obsidian: Ready (whose card could not tell: no Boards/repo/T-0042.md note names its repo-id)")


# --- review round 2 (T-0021): each test is a reviewer repro, run first ---------

def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, stdin=subprocess.DEVNULL)


def _repo_at(tmp_path, where, vault, rows="", origin=None):
    """A repo at tmp_path/<where> (e.g. `a/app`) on `vault`'s top-level board."""
    parent, name = os.path.split(where)
    made = make_repo(tmp_path / parent)
    root = tmp_path / parent / name
    os.rename(made, root)
    if origin:
        _git(root, "remote", "add", "origin", origin)
    _crew_json(root, {"kind": "obsidian", "obsidian": {"vaultPath": str(vault)}})
    (root / ".work" / "INDEX.md").write_text(rows, encoding="utf-8", newline="\n")
    return root


@pytest.mark.parametrize("origins", [
    ("https://example.invalid/a/app.git", "https://example.invalid/b/app.git"),
    (None, None),
])
def test_same_repo_name_is_not_the_same_repo(tmp_path, origins):
    """Round 2 FIX (:830): `a/app` and `b/app` share a basename, not an identity."""
    vault = _make_vault(tmp_path / "vault", board_dir=".")
    first = _repo_at(tmp_path, "a/app", vault, origin=origins[0])
    other = _repo_at(tmp_path, "b/app", vault, rows="T-0060 | direction | - | app | B work\n", origin=origins[1])
    assert _cli(first, "create", "--ticket", "T-0060", "--title", "A work").returncode == 0

    done, untouched = _refused(tmp_path, other, ("move", "--ticket", "T-0060", "--to", "done"))

    assert (done.returncode, untouched, "belongs to another repo" in done.stdout) == (1, True, True)


@pytest.mark.parametrize("origin", [None, "https://example.invalid/team/repo.git"])
def test_two_worktrees_of_one_repo_move_the_same_card(tmp_path, origin):
    vault = _make_vault(tmp_path / "vault", board_dir=".")
    first = _repo_at(tmp_path, "main/repo", vault, origin=origin)
    assert _cli(first, "create", "--ticket", "T-0060", "--title", "A work").returncode == 0
    second = tmp_path / "wt"
    _git(first, "worktree", "add", "-q", "-b", "wt", str(second))
    (second / ".crew").mkdir()
    (second / ".work").mkdir()
    (second / ".crew" / "crew.json").write_bytes((first / ".crew" / "crew.json").read_bytes())
    (second / ".work" / "INDEX.md").write_bytes((first / ".work" / "INDEX.md").read_bytes())

    done = _cli(second, "move", "--ticket", "T-0060", "--to", "review")

    assert (done.returncode, _lane_of((vault / "Board.md").read_text(encoding="utf-8"), "T-0060")) == (0, "Review")


@pytest.mark.parametrize("url,expected", [
    ("https://User:s3cret@Example.invalid/Owner/Repo.git", "https://example.invalid/owner/repo"),
    ("https://example.invalid/owner/repo/", "https://example.invalid/owner/repo"),
    ("ssh://git@Example.invalid:22/Owner/Repo.git", "ssh://git@example.invalid:22/owner/repo"),
    ("git@GitHub.com:Owner/Repo.git", "git@github.com:owner/repo"),
])
def test_repo_id_normalises_the_origin_url(tmp_path, url, expected):
    root = make_repo(tmp_path)
    _git(root, "remote", "add", "origin", url)

    assert crew_tracker.repo_id(str(root)) == expected


def test_note_records_repo_id_without_credentials(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)
    _git(root, "remote", "add", "origin", "https://user:s3cret@example.invalid/Team/Repo.git")

    _cli(root, "create", "--ticket", "T-0060", "--title", "new work")
    note = (vault / "Boards" / "repo" / "T-0060.md").read_text(encoding="utf-8")

    assert ("- repo-id: https://example.invalid/team/repo\n" in note, "s3cret" in note) == (True, False)


def test_move_refuses_a_card_no_note_claims(tmp_path):
    """Round 2 FIX (:876): the review repro -- another repo's no-note T-0042."""
    vault = _make_vault(tmp_path / "vault", board_dir=".")
    other = _repo_at(tmp_path, "x/other", vault, rows="T-0042 | spec | - | other | mine\n")

    done, untouched = _refused(tmp_path, other, ("move", "--ticket", CARD, "--to", "done"))

    assert (done.returncode, untouched, "could not tell whose card T-0042 is" in done.stdout,
            "repo-id: " in done.stdout) == (1, True, True, True)


def test_move_refuses_a_card_whose_note_names_no_repo_id(tmp_path):
    """An existing note is never rewritten, so an exact title cannot claim it."""
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)
    (vault / "Boards" / "repo" / "T-0042.md").write_text("# T-0042\n\nhand-written\n", encoding="utf-8")

    done, untouched = _refused(tmp_path, root)

    assert (done.returncode, untouched, "could not tell whose card T-0042 is" in done.stdout) == (1, True, True)


def test_move_refuses_when_this_repos_identity_cannot_be_told(tmp_path, monkeypatch):
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)
    assert crew_tracker.create(str(root), "T-0060", "new work")["results"][0]["state"] == "updated"
    monkeypatch.setattr(crew_tracker, "repo_id", lambda root: None)
    before = _snapshot(tmp_path)

    got = crew_tracker.move(str(root), "T-0060", "spec")

    assert (got["results"][0]["reason"].startswith("could not tell this repo's identity"),
            _snapshot(tmp_path) == before) == (True, True)


def _two_vaults(tmp_path):
    first = _make_vault(tmp_path / "v1", board_dir="B")
    second = _make_vault(tmp_path / "v2")
    return first, second


def test_resolve_compares_the_effective_vault(tmp_path):
    """Round 2 FIX (:181): the review repro -- crew.json falls back to the
    memory vault while config.json names another."""
    first, second = _two_vaults(tmp_path)
    root = make_repo(tmp_path)
    _write_json(root / ".crew" / "crew.json",
                {"schema": 1, "tracker": {"kind": "obsidian"}, "memory": {"vaultPath": str(second)}})
    _config_json(root, "obsidian", obsidian={"vaultPath": str(first), "boardDir": "B"})
    (root / ".work" / "INDEX.md").write_text(ROW, encoding="utf-8", newline="\n")

    got = crew_tracker.resolve(str(root))
    done, untouched = _refused(tmp_path, root)

    # The problem quotes each path with repr, which doubles a Windows backslash.
    assert (got["kind"], repr(str(first)) in got["problems"][0], repr(str(second)) in got["problems"][0],
            done.returncode, untouched) == ("could not tell", True, True, 1, True)


def test_resolve_compares_the_effective_board_dir(tmp_path):
    vault = _make_vault(tmp_path / "vault", board_dir="B")
    root = make_repo(tmp_path)
    _write_json(root / ".crew" / "crew.json",
                {"schema": 1, "tracker": {"kind": "obsidian"}, "memory": {"vaultPath": str(vault)}})
    _config_json(root, "obsidian", obsidian={"vaultPath": str(vault), "boardDir": "B"})

    got = crew_tracker.resolve(str(root))

    assert (got["kind"], "boardDir" in got["problems"][0]) == ("could not tell", True)


def test_resolve_accepts_one_vault_reached_two_ways(tmp_path):
    vault = _make_vault(tmp_path / "vault", board_dir=".")
    root = make_repo(tmp_path)
    _write_json(root / ".crew" / "crew.json",
                {"schema": 1, "tracker": {"kind": "obsidian"}, "memory": {"vaultPath": str(vault)}})
    _config_json(root, "obsidian", obsidian={"vaultPath": str(vault) + os.sep})

    got = crew_tracker.resolve(str(root))

    assert (got["kind"], got["problems"]) == ("obsidian", [])


def test_create_refuses_an_id_another_session_holds(tmp_path):
    """Round 2 FIX (:422): the review repro, verbatim."""
    row = "T-0050 | in-progress | high | r | another session's auth rewrite\n"
    root = _files_repo(tmp_path, row)

    done = _cli(root, "create", "--ticket", "T-0050", "--title", "my new idea")

    assert (done.returncode, done.stdout, _index(root)) == (
        1, "files: could not update: id taken: T-0050 is already in-progress \"another session's auth rewrite\"\n",
        row)


def test_obsidian_create_on_a_held_id_writes_no_card(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)
    (root / ".work" / "INDEX.md").write_text(ROW + "T-0061 | spec | - | repo | someone's\n", encoding="utf-8")

    done, untouched = _refused(tmp_path, root, ("create", "--ticket", "T-0061", "--title", "mine"))

    assert (done.returncode, untouched, 'T-0061 is already spec "someone\'s"' in done.stdout) == (1, True, True)


_BOUNDARY = "tracker: {kind} syncs at boundaries only (in-progress, done); nothing to push\n"


@pytest.mark.parametrize("kind,key,status,code,line", [
    ("jira", "ABC-12", "direction", 0, _BOUNDARY.format(kind="jira")),
    ("jira", "ABC-12", "spec", 0, _BOUNDARY.format(kind="jira")),
    ("jira", "ABC-12", "planned", 0, _BOUNDARY.format(kind="jira")),
    ("jira", "ABC-12", "in-progress", 3, "jira: delegated: run /crew:jira-sync ABC-12 --push --to in-progress\n"),
    ("jira", "ABC-12", "review", 0, _BOUNDARY.format(kind="jira")),
    ("jira", "ABC-12", "done", 3, "jira: delegated: run /crew:jira-sync ABC-12 --push --to done\n"),
    ("sdp", "SDP-40219", "spec", 0, _BOUNDARY.format(kind="sdp")),
    ("sdp", "SDP-40219", "in-progress", 3, "sdp: delegated: run /crew:sdp-sync SDP-40219 --push --to in-progress\n"),
    ("sdp", "SDP-40219", "done", 3, "sdp: delegated: run /crew:sdp-sync SDP-40219 --push --to done\n"),
])
def test_jira_and_sdp_push_at_boundaries_only(tmp_path, kind, key, status, code, line):
    """Round 2 FIX (:911): the push names its target, and only boundaries push."""
    root = make_repo(tmp_path)
    _config_json(root, kind)
    before = _snapshot(tmp_path)

    done = _cli(root, "move", "--ticket", key, "--to", status)

    assert (done.returncode, done.stdout, _snapshot(tmp_path) == before) == (code, line, True)


def _swap_for_link(monkeypatch, real_dir, target_dir):
    """After the board is loaded -- past every check -- `real_dir` becomes a link."""
    real = crew_tracker._load_board  # pylint: disable=protected-access

    def swapping(paths, columns):
        got = real(paths, columns)
        os.rename(real_dir, str(real_dir) + ".moved")
        os.symlink(target_dir, real_dir, target_is_directory=True)
        return got

    monkeypatch.setattr(crew_tracker, "_load_board", swapping)


def _outside_copy(tmp_path, vault):
    import shutil  # pylint: disable=import-outside-toplevel
    outside = tmp_path / "out" / "B"
    shutil.copytree(vault / "B", outside)
    return outside


@pytest.mark.parametrize("dir_fd", [True, False])
def test_board_dir_swapped_for_a_link_after_the_checks_writes_nothing_outside(tmp_path, monkeypatch, dir_fd):
    """Round 2 FIX (:727): confinement is checked on a path, so the write must not
    re-walk that path through a link planted after the check. dir_fd=False is the
    Windows branch, run here by switching the capability off."""
    vault = _make_vault(tmp_path / "vault", board_dir="B")
    root = _obsidian_repo(tmp_path, vault, boardDir="B")
    assert crew_tracker.create(str(root), "T-0060", "new work")["results"][1]["state"] == "updated"
    outside = _outside_copy(tmp_path, vault)
    before = _snapshot(outside)
    if not dir_fd:
        monkeypatch.setattr(crew_tracker, "_DIR_FD", False)
    _swap_for_link(monkeypatch, vault / "B", outside)

    got = crew_tracker.move(str(root), "T-0060", "spec")

    assert (crew_tracker.exit_code(got), _snapshot(outside) == before) == (1, True)


def test_board_dir_swap_repro_with_a_noteless_card(tmp_path, monkeypatch):
    """The reviewer's repro as written: T-0042, no note, boardDir B."""
    vault = _make_vault(tmp_path / "vault", board_dir="B")
    root = _obsidian_repo(tmp_path, vault, own=False, boardDir="B")
    outside = _outside_copy(tmp_path, vault)
    before = _snapshot(outside)
    _swap_for_link(monkeypatch, vault / "B", outside)

    got = crew_tracker.move(str(root), CARD, "done")

    assert (crew_tracker.exit_code(got), _snapshot(outside) == before) == (1, True)


def test_vault_replaced_after_the_checks_writes_nothing(tmp_path, monkeypatch):
    """The walk starts at the vault it checked: a different directory put at the
    vault's path afterwards is refused, not written."""
    vault = _make_vault(tmp_path / "vault", board_dir="B")
    root = _obsidian_repo(tmp_path, vault, boardDir="B")
    assert crew_tracker.create(str(root), "T-0060", "new work")["results"][1]["state"] == "updated"
    import shutil  # pylint: disable=import-outside-toplevel
    impostor = tmp_path / "impostor"
    shutil.copytree(vault, impostor)
    before = _snapshot(impostor)
    real = crew_tracker._load_board  # pylint: disable=protected-access

    def replacing(paths, columns):
        got = real(paths, columns)
        os.rename(vault, str(vault) + ".moved")
        os.rename(impostor, vault)
        return got

    monkeypatch.setattr(crew_tracker, "_load_board", replacing)

    got = crew_tracker.move(str(root), "T-0060", "spec")

    assert (crew_tracker.exit_code(got), _snapshot(vault) == {k.replace(str(impostor), str(vault)): v
                                                              for k, v in before.items()}) == (1, True)


def test_board_dir_that_is_a_link_inside_the_vault_is_allowed(tmp_path):
    vault = _make_vault(tmp_path / "vault", board_dir="Real/B")
    _symlink(vault / "B", vault / "Real" / "B", is_dir=True)
    root = _obsidian_repo(tmp_path, vault, boardDir="B")

    done = _cli(root, "move", "--ticket", CARD, "--to", "review")

    assert (done.returncode, _lane_of((vault / "Real/B/Board.md").read_text(encoding="utf-8"), CARD)) == (0, "Review")


def test_backwards_move_is_refused(tmp_path):
    """Round 2 NIT (:72): STATUS_ORDER guards a move back from done."""
    root = _files_repo(tmp_path, "T-0001 | done | low | repo | t\n")

    done = _cli(root, "move", "--ticket", "T-0001", "--to", "in-progress")

    assert (done.returncode, done.stdout, _index(root)) == (
        1, "files: could not update: T-0001 is done; moving it back to in-progress needs --reopen\n",
        "T-0001 | done | low | repo | t\n")


def test_backwards_move_with_reopen_goes_ahead(tmp_path):
    root = _files_repo(tmp_path, "T-0001 | done | low | repo | t\n")

    done = _cli(root, "move", "--ticket", "T-0001", "--to", "in-progress", "--reopen")

    assert (done.returncode, _index(root)) == (0, "T-0001 | in-progress | low | repo | t\n")


def test_move_from_a_status_crew_does_not_know_is_could_not_tell(tmp_path):
    root = _files_repo(tmp_path, "T-0001 | merged | low | repo | t\n")

    done = _cli(root, "move", "--ticket", "T-0001", "--to", "review")

    assert (done.returncode, "could not tell whether merged -> review goes backwards" in done.stdout,
            _index(root)) == (1, True, "T-0001 | merged | low | repo | t\n")


def test_obsidian_backwards_move_leaves_the_board_alone(tmp_path):
    """The card sits in Review, where INDEX says it is, so a move back to spec
    that reached the board would visibly move it to Ready."""
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)
    board = vault / "Boards" / "repo" / "Board.md"
    board.write_text(crew_tracker.move_card(_board("board_0_20.md"), CARD, "review")[0], encoding="utf-8",
                     newline="\n")
    (root / ".work" / "INDEX.md").write_text(ROW.replace("spec", "review"), encoding="utf-8", newline="\n")

    done, untouched = _refused(tmp_path, root, ("move", "--ticket", CARD, "--to", "spec"))

    assert (done.returncode, untouched, "needs --reopen" in done.stdout) == (1, True, True)


def test_move_refuses_a_multi_line_card_when_index_has_no_title(tmp_path):
    """The claim's neighbour: no card text and no INDEX title are not a match."""
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault, own=False)
    board = vault / "Boards" / "repo" / "Board.md"
    board.write_text(board.read_text(encoding="utf-8").replace(
        "Fix token refresh on 401\n", "Fix token refresh on 401\n\tsecond line\n", 1), encoding="utf-8", newline="\n")
    (root / ".work" / "INDEX.md").write_text("T-0042 | spec\n", encoding="utf-8", newline="\n")

    done, untouched = _refused(tmp_path, root)

    assert (done.returncode, untouched, "could not tell whose card T-0042 is" in done.stdout) == (1, True, True)


# --- review round 3 (T-0021): each test is a reviewer repro, run first ---------

# Windows holds every directory from the vault down with a handle that denies
# FILE_SHARE_DELETE (T-0077), so the swaps below are refused by the OS instead of
# happening. There the tests assert that refusal AND where the bytes landed;
# POSIX, which pins by fd and lets the directory move, keeps its assertions.
_HELD_BY_HANDLE = os.name == "nt"


def _rename_or_refused(src, dst, refused):
    """`os.rename`, except that on Windows a held directory's PermissionError is
    recorded in `refused` -- the outcome the pin exists to produce -- not raised."""
    try:
        os.rename(src, dst)
    except PermissionError:
        if not _HELD_BY_HANDLE:
            raise
        refused.append(os.path.basename(src))
        return False
    return True


def _no_temp_anywhere(*dirs):
    return [name for top in dirs if os.path.isdir(top) for name in os.listdir(top) if name.endswith(".tmp")]


def _move_out_when_pinned(monkeypatch, real_dir, outside, label, when="pinned"):
    """Past every check, once a write holds its directory -- as the fd is
    handed back (`pinned`, or `replaced` when a fresh directory then takes its
    place in the vault) or once the temp is written beside the target (`temp`)
    -- `real_dir` is renamed out of the vault. The fd now names a directory
    outside it. Returns the list the Windows refusals land in."""
    refused = []

    def move_out():
        if not os.path.exists(outside) and not refused:
            if _rename_or_refused(real_dir, outside, refused) and when == "replaced":
                os.mkdir(real_dir)

    if when in ("pinned", "replaced"):
        real = crew_tracker._open_pinned  # pylint: disable=protected-access

        def moving(paths, which):
            fd = real(paths, which)
            if which == label:
                move_out()
            return fd
        monkeypatch.setattr(crew_tracker, "_open_pinned", moving)
    else:
        real = crew_tracker._write_temp  # pylint: disable=protected-access

        def moving_after_temp(path, data, ownership, dir_fd=None):
            tmp = real(path, data, ownership, dir_fd)
            if os.path.basename(path) == "Board.md":
                move_out()
            return tmp
        monkeypatch.setattr(crew_tracker, "_write_temp", moving_after_temp)
    return refused


@pytest.mark.parametrize("when", ["pinned", "replaced", "temp"])
def test_board_dir_moved_out_of_the_vault_after_pinning_writes_nothing_there(tmp_path, monkeypatch, when):
    """Round 3 BLOCK (:973): the reviewer's repro -- an owned card's board, its
    directory renamed out of the vault once the fd is held. On Windows the held
    handle refuses the rename, so the write lands in the vault and no temp is
    left anywhere (T-0077)."""
    vault = _make_vault(tmp_path / "vault", board_dir="B")
    root = _obsidian_repo(tmp_path, vault, boardDir="B")
    assert crew_tracker.create(str(root), "T-0060", "new work")["results"][1]["state"] == "updated"
    before = (vault / "B" / "Board.md").read_bytes()
    outside = tmp_path / "out"
    refused = _move_out_when_pinned(monkeypatch, vault / "B", outside, "board", when)

    got = crew_tracker.move(str(root), "T-0060", "spec")

    if _HELD_BY_HANDLE:
        assert (refused, crew_tracker.exit_code(got), outside.exists(),
                (vault / "B" / "Board.md").read_bytes() != before, _no_temp_anywhere(vault / "B")) == (
                    ["B"], 0, False, True, [])
    else:
        assert (crew_tracker.exit_code(got), (outside / "Board.md").read_bytes() == before,
                _no_temp_anywhere(outside)) == (1, True, [])


def _note_result(got):
    """The ticket note's line: the claim runs first (review round 4), so when it
    fails it is the only line, and when it succeeds it is the last."""
    return next(r for r in got["results"] if r["backend"] == "obsidian-note")


def test_note_dir_moved_out_of_the_vault_after_pinning_leaves_no_note_there(tmp_path, monkeypatch):
    """The BLOCK's neighbour: the ticket note is the other vault write."""
    vault = _make_vault(tmp_path / "vault", board_dir="B")
    root = _obsidian_repo(tmp_path, vault, boardDir="B")
    outside = tmp_path / "out"
    refused = _move_out_when_pinned(monkeypatch, vault / "B", outside, "note")

    got = crew_tracker.create(str(root), "T-0060", "new work")

    note = _note_result(got)

    if _HELD_BY_HANDLE:
        assert (refused, note["state"], (vault / "B" / "T-0060.md").exists(), outside.exists()) == (
            ["B"], "updated", True, False)
    else:
        assert (note["state"], note["reason"].endswith("nothing written through it"),
                (outside / "T-0060.md").exists(), _index(root)) == ("could not update", True, False, ROW)


def test_note_dir_moved_out_after_the_note_is_written_removes_it_there(tmp_path, monkeypatch):
    """The check after the write: the note already landed in the moved directory,
    and is removed through the fd that wrote it."""
    vault = _make_vault(tmp_path / "vault", board_dir="B")
    root = _obsidian_repo(tmp_path, vault, boardDir="B")
    outside = tmp_path / "out"
    real = crew_tracker._write_new  # pylint: disable=protected-access
    refused = []

    def moving(path, flags, data, ownership, dir_fd=None):
        real(path, flags, data, ownership, dir_fd)
        if os.path.basename(path) == "T-0060.md":
            _rename_or_refused(vault / "B", outside, refused)

    monkeypatch.setattr(crew_tracker, "_write_new", moving)

    got = crew_tracker.create(str(root), "T-0060", "new work")

    if _HELD_BY_HANDLE:
        assert (refused, _note_result(got)["state"], (vault / "B" / "T-0060.md").exists(), outside.exists()) == (
            ["B"], "updated", True, False)
    else:
        assert (_note_result(got)["state"], (outside / "T-0060.md").exists(), (outside / "Board.md").exists(),
                _index(root)) == ("could not update", False, True, ROW)


# --- T-0077: the Windows handle pin, and the platform with no pin ---------------

def _fake_held(identity=None, attributes=0, at=None):
    """A stand-in for `_win_open_dir` that runs anywhere: the real directory's
    identity, except `identity` (st_dev, st_ino) or `attributes` for the component
    whose basename is `at` (every component when `at` is None)."""
    import types  # pylint: disable=import-outside-toplevel

    def opener(path):
        real = os.stat(path)
        hit = at is None or os.path.basename(path) == at
        dev, ino = identity if (hit and identity is not None) else (real.st_dev, real.st_ino)
        seen = types.SimpleNamespace(st_dev=dev, st_ino=ino, st_mode=real.st_mode,
                                     st_file_attributes=attributes if hit else 0)
        return seen, lambda: None
    return opener


def _held_repo(tmp_path, monkeypatch, opener):
    """An owned card on a vault board, written through the Windows pin branch on
    any OS: dir_fd off, the handle pin on, and `opener` in place of CreateFileW."""
    vault = _make_vault(tmp_path / "vault", board_dir="B")
    root = _obsidian_repo(tmp_path, vault, boardDir="B")
    assert crew_tracker.create(str(root), "T-0060", "new work")["results"][1]["state"] == "updated"
    monkeypatch.setattr(crew_tracker, "_DIR_FD", False)
    monkeypatch.setattr(crew_tracker, "_WIN_PIN", True)
    monkeypatch.setattr(crew_tracker, "_win_open_dir", opener)
    return vault, root, (vault / "B" / "Board.md").read_bytes()


def test_pin_share_mask_never_lets_a_held_directory_be_renamed():
    """The spike (T-0077): FILE_READ_ATTRIBUTES alone did NOT block a rename; a
    handle with data access that denies FILE_SHARE_DELETE does. So the masks are
    a contract, not a detail."""
    assert (crew_tracker._PIN_SHARE & crew_tracker._FILE_SHARE_DELETE,  # pylint: disable=protected-access
            bool(crew_tracker._PIN_ACCESS & crew_tracker._FILE_LIST_DIRECTORY),  # pylint: disable=protected-access
            bool(crew_tracker._PIN_FLAGS & crew_tracker._FILE_FLAG_OPEN_REPARSE_POINT)) == (  # pylint: disable=protected-access
                0, True, True)


def test_the_handle_pin_writes_when_every_directory_is_the_one_checked(tmp_path, monkeypatch):
    vault, root, before = _held_repo(tmp_path, monkeypatch, _fake_held())

    got = crew_tracker.move(str(root), "T-0060", "spec")

    assert (crew_tracker.exit_code(got), (vault / "B" / "Board.md").read_bytes() != before) == (0, True)


def test_the_handle_pin_refuses_a_different_vault(tmp_path, monkeypatch):
    vault, root, before = _held_repo(tmp_path, monkeypatch, _fake_held(identity=(1, 1), at="vault"))

    got = crew_tracker.move(str(root), "T-0060", "spec")

    assert (crew_tracker.exit_code(got), (vault / "B" / "Board.md").read_bytes() == before) == (1, True)


def test_the_handle_pin_refuses_a_zero_file_id_as_could_not_tell(tmp_path, monkeypatch):
    """No file id is no evidence: never read as 'the same directory'."""
    vault, root, before = _held_repo(tmp_path, monkeypatch, _fake_held(identity=(7, 0), at="B"))

    got = crew_tracker.move(str(root), "T-0060", "spec")

    assert (crew_tracker.exit_code(got), "could not tell" in got["results"][-1]["reason"],
            (vault / "B" / "Board.md").read_bytes() == before) == (1, True, True)


def test_the_handle_pin_refuses_a_reparse_point_on_the_walk(tmp_path, monkeypatch):
    vault, root, before = _held_repo(
        tmp_path, monkeypatch, _fake_held(attributes=crew_tracker._REPARSE_POINT, at="B"))  # pylint: disable=protected-access

    got = crew_tracker.move(str(root), "T-0060", "spec")

    assert (crew_tracker.exit_code(got), (vault / "B" / "Board.md").read_bytes() == before) == (1, True)


def test_the_held_check_refuses_when_the_path_no_longer_reaches_the_held_directory(tmp_path, monkeypatch):
    """The re-check beside the handles: with no real handle held (the fake
    opener), the directory CAN move once pinned, and the write must see it."""
    import shutil  # pylint: disable=import-outside-toplevel
    vault, root, before = _held_repo(tmp_path, monkeypatch, _fake_held())
    outside = tmp_path / "out"
    real = crew_tracker._open_pinned  # pylint: disable=protected-access

    def swapped_for_a_copy(paths, which):
        held = real(paths, which)
        if which == "board" and not outside.exists():
            # A byte-identical impostor at the same path: only identity tells.
            os.rename(vault / "B", outside)
            shutil.copytree(outside, vault / "B")
        return held
    monkeypatch.setattr(crew_tracker, "_open_pinned", swapped_for_a_copy)

    got = crew_tracker.move(str(root), "T-0060", "spec")

    assert (crew_tracker.exit_code(got), (vault / "B" / "Board.md").read_bytes() == before,
            (outside / "Board.md").read_bytes() == before, _no_temp_anywhere(outside, vault / "B")) == (
                1, True, True, [])


def test_a_platform_with_no_pin_refuses_as_could_not_tell(tmp_path, monkeypatch):
    """Neither dir_fd nor the handle pin: the write is refused, never made with a
    path-only re-check that a rename-and-replace passes (T-0077)."""
    vault = _make_vault(tmp_path / "vault", board_dir="B")
    root = _obsidian_repo(tmp_path, vault, boardDir="B")
    assert crew_tracker.create(str(root), "T-0060", "new work")["results"][1]["state"] == "updated"
    before = (vault / "B" / "Board.md").read_bytes()
    monkeypatch.setattr(crew_tracker, "_DIR_FD", False)
    monkeypatch.setattr(crew_tracker, "_WIN_PIN", False)

    got = crew_tracker.move(str(root), "T-0060", "spec")

    assert (crew_tracker.exit_code(got), "could not tell" in got["results"][-1]["reason"],
            (vault / "B" / "Board.md").read_bytes() == before) == (1, True, True)


@pytest.mark.skipif(os.name != "nt", reason="the handle pin is Windows-only; POSIX pins by dir_fd")
def test_the_windows_pin_blocks_renames_while_held_and_frees_them_after(tmp_path):
    vault = _make_vault(tmp_path / "vault", board_dir="B")
    seen = os.stat(vault)
    paths = {"vault": str(vault), "vaultId": (seen.st_dev, seen.st_ino),
             "board": str(vault / "B" / "Board.md"), "boardShown": "B/Board.md"}
    refused = []

    held = crew_tracker._open_pinned(paths, "board")  # pylint: disable=protected-access
    try:
        _rename_or_refused(vault / "B", tmp_path / "B.moved", refused)
        _rename_or_refused(vault, tmp_path / "vault.moved", refused)
    finally:
        crew_tracker._release(held)  # pylint: disable=protected-access
    freed = _rename_or_refused(vault / "B", tmp_path / "B.moved", refused)

    assert (refused, freed) == (["B", "vault"], True)


def test_relative_local_origins_are_not_one_repo(tmp_path):
    """Round 3 FIX (:503): `../origin/app.git` from a/app and from b/app are two
    different repositories that normalise to one string."""
    vault = _make_vault(tmp_path / "vault", board_dir=".")
    first = _repo_at(tmp_path, "a/app", vault, origin="../origin/app.git")
    other = _repo_at(tmp_path, "b/app", vault, rows="T-0060 | direction | - | app | B work\n",
                     origin="../origin/app.git")
    assert _cli(first, "create", "--ticket", "T-0060", "--title", "A work").returncode == 0

    done, untouched = _refused(tmp_path, other, ("move", "--ticket", "T-0060", "--to", "done"))

    assert (done.returncode, untouched, "belongs to another repo" in done.stdout) == (1, True, True)


@pytest.mark.parametrize("origin", ["../origin/repo.git", "origin/repo.git", "./repo.git"])
def test_a_relative_origin_is_the_common_dir(tmp_path, origin):
    root = make_repo(tmp_path)
    _git(root, "remote", "add", "origin", origin)
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=root,
                            capture_output=True, text=True, check=True).stdout.strip()

    assert crew_tracker.repo_id(str(root)) == os.path.realpath(common)


def test_worktrees_of_one_repo_with_a_relative_origin_share_its_cards(tmp_path):
    """The neighbour: the fix must not split one repo's worktrees apart."""
    vault = _make_vault(tmp_path / "vault", board_dir=".")
    first = _repo_at(tmp_path, "main/repo", vault, origin="../origin/repo.git")
    assert _cli(first, "create", "--ticket", "T-0060", "--title", "A work").returncode == 0
    second = tmp_path / "wt"
    _git(first, "worktree", "add", "-q", "-b", "wt", str(second))
    (second / ".crew").mkdir()
    (second / ".work").mkdir()
    (second / ".crew" / "crew.json").write_bytes((first / ".crew" / "crew.json").read_bytes())
    (second / ".work" / "INDEX.md").write_bytes((first / ".work" / "INDEX.md").read_bytes())

    done = _cli(second, "move", "--ticket", "T-0060", "--to", "review")

    assert (done.returncode, _lane_of((vault / "Board.md").read_text(encoding="utf-8"), "T-0060")) == (0, "Review")


def test_move_refuses_another_repos_unclaimed_card_with_the_same_title(tmp_path):
    """Round 3 FIX (:1138): a title is not an owner. A's no-note T-0042 and B's
    INDEX row share "Fix token refresh on 401"; B must not claim the card."""
    vault = _make_vault(tmp_path / "vault", board_dir=".")
    other = _repo_at(tmp_path, "x/other", vault, rows="T-0042 | spec | - | other | Fix token refresh on 401\n")

    done, untouched = _refused(tmp_path, other, ("move", "--ticket", CARD, "--to", "done"))

    assert (done.returncode, untouched, "could not tell whose card T-0042 is" in done.stdout) == (1, True, True)


def test_create_refuses_a_held_id_under_the_same_title(tmp_path):
    """Round 3 FIX (:565): the reviewer's repro -- same title, any status."""
    row = "T-0050 | ready | - | r | Fix tests\n"
    root = _files_repo(tmp_path, row)

    done = _cli(root, "create", "--ticket", "T-0050", "--title", "Fix tests")

    assert (done.returncode, done.stdout, _index(root)) == (
        1, 'files: could not update: id taken: T-0050 is already ready "Fix tests"\n', row)


def test_obsidian_create_on_a_held_id_under_the_same_title_writes_nothing(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)
    (root / ".work" / "INDEX.md").write_text(ROW + "T-0061 | direction | - | repo | same\n", encoding="utf-8")

    done, untouched = _refused(tmp_path, root, ("create", "--ticket", "T-0061", "--title", "same"))

    assert (done.returncode, untouched, "id taken: T-0061 is already direction" in done.stdout) == (1, True, True)


@pytest.mark.parametrize("owner", ["foreign", "unknown"])
def test_create_on_an_id_the_board_holds_says_id_taken(tmp_path, owner):
    """The neighbour: an id the shared board holds is as taken as one INDEX holds,
    and the lifecycle prose reads one phrase for both."""
    vault = _make_vault(tmp_path / "vault", board_dir=".")
    if owner == "foreign":
        first = _repo_at(tmp_path, "a/app", vault)
        assert _cli(first, "create", "--ticket", "T-0060", "--title", "A work").returncode == 0
        ticket = "T-0060"
    else:
        ticket = CARD
    other = _repo_at(tmp_path, "b/app", vault)

    done, untouched = _refused(tmp_path, other, ("create", "--ticket", ticket, "--title", "B work"))

    assert (done.returncode, untouched, done.stdout.startswith("obsidian: could not update: id taken: ")) == (
        1, True, True)


@pytest.mark.parametrize("crew_side,config_side,field", [
    ({}, {"vaultPath": "{v}", "board": "Other.md"}, "board"),
    ({}, {"vaultPath": "{v}", "columns": {"done": "Shipped"}}, "columns"),
    ({"vaultPath": "{v}", "board": "Other.md"}, {}, "board"),
])
def test_resolve_compares_every_effective_obsidian_setting(tmp_path, crew_side, config_side, field):
    """Round 3 FIX (:222): the reviewer's repro -- only config.json carries the
    block, both reach one vault, and config.json names another board."""
    vault = str(tmp_path / "V")
    root = make_repo(tmp_path)
    crew = {"schema": 1, "tracker": {"kind": "obsidian"}, "memory": {"vaultPath": vault}}
    if crew_side:
        crew["tracker"]["obsidian"] = {k: v.replace("{v}", vault) if isinstance(v, str) else v
                                       for k, v in crew_side.items()}
    _write_json(root / ".crew" / "crew.json", crew)
    config = {"memory": {"vaultPath": vault}}
    if config_side:
        config["obsidian"] = {k: v.replace("{v}", vault) if isinstance(v, str) else v
                              for k, v in config_side.items()}
    _config_json(root, "obsidian", **config)

    got = crew_tracker.resolve(str(root))

    assert (got["kind"], [p for p in got["problems"] if f"obsidian {field} " in p] != []) == ("could not tell", True)


def test_resolve_refuses_one_file_naming_a_vault_the_other_does_not(tmp_path):
    """The neighbour: a vault one file yields and the other does not is a pick too."""
    root = make_repo(tmp_path)
    _crew_json(root, {"kind": "obsidian"})
    _config_json(root, "obsidian", obsidian={"vaultPath": str(tmp_path / "V")})

    got = crew_tracker.resolve(str(root))

    assert (got["kind"], "obsidian vaultPath None" in got["problems"][0]) == ("could not tell", True)


@pytest.mark.parametrize("kind", ["jira", "sdp"])
def test_resolve_refuses_a_block_only_one_file_carries(tmp_path, kind):
    root = make_repo(tmp_path)
    _crew_json(root, {"kind": kind})
    _config_json(root, kind, **{kind: {"project": "ABC"}})

    got = crew_tracker.resolve(str(root))

    assert got["kind"] == "could not tell"


def test_board_is_not_moved_when_the_index_half_refuses(tmp_path, monkeypatch):
    """Round 3 FIX (:1158): another session completes the ticket after this
    move's first INDEX read; the INDEX half refuses done -> review, and the
    board must not go back to Review either."""
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)
    board = vault / "Boards" / "repo" / "Board.md"
    before = board.read_bytes()
    real = crew_tracker._load_board  # pylint: disable=protected-access

    def completing(paths, columns):
        got = real(paths, columns)
        (root / ".work" / "INDEX.md").write_text(ROW.replace("spec", "done"), encoding="utf-8", newline="\n")
        return got

    monkeypatch.setattr(crew_tracker, "_load_board", completing)

    got = crew_tracker.move(str(root), CARD, "review")

    assert ([r["state"] for r in got["results"]], board.read_bytes() == before) == (["could not update"], True)


_DONE_UNCHECKED = ("- [x] [[T-0039]] Bump pinned deps\n", "- [ ] [[T-0039]] Bump pinned deps\n")
_DONE_ABOVE = ("## Done\n\n**Complete**\n\n- [x] [[T-0039]]",
               "## Done\n\n- [x] [[T-0039]] Bump pinned deps\n**Complete**\n\n- [x] [[T-0039x]]")


def test_move_to_done_rechecks_a_card_already_in_done():
    """Round 3 FIX (:797): the reviewer's repro -- unchecked in Done."""
    old = _fixture("board_0_20.md")
    board, _ = crew_tracker.parse_board(old.replace(*_DONE_UNCHECKED), COLUMNS)

    new, moved_from, problem = crew_tracker.move_card(board, "T-0039", "done")

    assert (new, moved_from, problem) == (old, "Done", None)


def test_move_to_done_puts_a_card_above_complete_below_it():
    old = _fixture("board_0_20.md").replace("- [x] [[T-0039]] Bump pinned deps\n", "")
    above = old.replace("## Done\n\n**Complete**\n", "## Done\n\n- [ ] [[T-0044]] early\n**Complete**\n", 1)
    board, _ = crew_tracker.parse_board(above, COLUMNS)

    new, _, problem = crew_tracker.move_card(board, "T-0044", "done")

    assert (new, problem) == (old.replace("**Complete**\n\n", "**Complete**\n\n- [x] [[T-0044]] early\n", 1), None)


def test_move_to_a_lane_it_is_in_unchecks_a_checked_card():
    """The neighbour: a checked card outside Done is repaired in place."""
    old = _fixture("board_0_20.md")
    board, _ = crew_tracker.parse_board(old.replace("- [ ] [[T-0042]]", "- [x] [[T-0042]]"), COLUMNS)

    new, moved_from, problem = crew_tracker.move_card(board, "T-0042", "ready")

    assert (new, moved_from, problem) == (old, "Ready", None)


def test_backend_repairs_an_unchecked_card_already_in_done(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)
    board = vault / "Boards" / "repo" / "Board.md"
    board.write_text(_fixture("board_0_20.md").replace("- [ ] [[T-0042]] Fix token refresh on 401\n", "").replace(
        "**Complete**\n\n", "**Complete**\n\n- [ ] [[T-0042]] Fix token refresh on 401\n", 1),
        encoding="utf-8", newline="\n")
    (root / ".work" / "INDEX.md").write_text(ROW.replace("spec", "done"), encoding="utf-8", newline="\n")

    got = crew_tracker.move(str(root), CARD, "done")

    assert ([r["state"] for r in got["results"]], "- [x] [[T-0042]]" in board.read_text(encoding="utf-8")) == (
        ["unchanged", "updated"], True)


@pytest.mark.parametrize("change,reason", [
    (("**Complete**\n\n", ""), "lane 'Done' (obsidian.columns.done) has no **Complete** marker"),
    (("**Complete**\n\n", "**Complete**\n\n**Complete**\n\n"),
     "lane 'Done' (obsidian.columns.done) has 2 **Complete** markers"),
])
def test_done_lane_needs_exactly_one_complete_marker(change, reason):
    """Round 3 FIX (:765): the reviewer's repro, and two markers beside it."""
    board, problem = crew_tracker.parse_board(_fixture("board_0_20.md").replace(*change, 1), COLUMNS)

    assert (board, problem) == (None, reason)


def test_done_lane_without_complete_writes_nothing(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    board = vault / "Boards" / "repo" / "Board.md"
    board.write_text(_fixture("board_0_20.md").replace("**Complete**\n\n", "", 1), encoding="utf-8", newline="\n")
    root = _obsidian_repo(tmp_path, vault)

    done, untouched = _refused(tmp_path, root, ("move", "--ticket", CARD, "--to", "done"))

    assert (done.returncode, untouched, "has no **Complete** marker" in done.stdout) == (1, True, True)


def test_resolve_both_disagree_on_jira_settings_is_could_not_tell(tmp_path):
    """Obsidian's blocks are compared field by field now; Jira and SDP still
    rely on the whole-block comparison when both files carry one."""
    root = make_repo(tmp_path)
    _crew_json(root, {"kind": "jira", "jira": {"project": "ABC"}})
    _config_json(root, "jira", jira={"project": "XYZ"})

    got = crew_tracker.resolve(str(root))

    assert got["kind"] == "could not tell"


@pytest.mark.parametrize("board_dir", ["", "/"])
def test_resolve_accepts_an_explicit_vault_root_board_dir_beside_an_unset_one(tmp_path, board_dir):
    """The comparison's must-allow: an unset boardDir IS the vault root."""
    vault = str(tmp_path / "V")
    root = make_repo(tmp_path)
    _crew_json(root, {"kind": "obsidian", "obsidian": {"vaultPath": vault}})
    _config_json(root, "obsidian", obsidian={"vaultPath": vault, "boardDir": board_dir})

    got = crew_tracker.resolve(str(root))

    assert (got["kind"], got["problems"]) == ("obsidian", [])


# --- review round 4 (T-0021): each test is a reviewer repro, red at 8aa9ccd6 ----

def _bare_with_commit(path):
    """A bare repo at `path` holding one commit; returns that commit."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "--bare", str(path)], check=True, capture_output=True,
                   stdin=subprocess.DEVNULL)
    work = make_repo(path.parent / (path.name + ".work"))
    _git(work, "commit", "-q", "--allow-empty", "-m", path.name)
    _git(work, "push", "-q", str(path), "HEAD:refs/heads/main")
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=work, capture_output=True, text=True,
                          check=True).stdout.strip()


def test_file_url_escapes_are_decoded(tmp_path):
    """Round 4 FIX (:512): git percent-decodes a file:// path, so the id must too."""
    srv = tmp_path / "srv"
    spaced = _bare_with_commit(srv / "a b.git")
    _bare_with_commit(srv / "a%20b.git")
    url = f"file://{srv}/a%20b.git"
    ids = []
    for name, origin in (("r1", url), ("r2", str(srv / "a b.git")), ("r3", str(srv / "a%20b.git"))):
        root = make_repo(tmp_path / name)
        _git(root, "remote", "add", "origin", origin)
        ids.append(crew_tracker.repo_id(str(root)))
    answered = subprocess.run(["git", "ls-remote", url, "main"], capture_output=True, text=True,
                              check=True, stdin=subprocess.DEVNULL).stdout.split()[0]

    assert (answered == spaced, ids[0] == ids[1], ids[0] != ids[2]) == (True, True, True)


@pytest.mark.parametrize("url,expected", [
    ("alice@host:repo.git", "alice@host:repo"),
    ("bob@host:repo.git", "bob@host:repo"),
    ("ssh://alice:pw@host/~/repo", "ssh://alice@host/~/repo"),
    ("https://tok@host/o/r", "https://host/o/r"),
])
def test_repo_id_keeps_an_ssh_username_and_drops_secrets(tmp_path, url, expected):
    """Round 4 FIX (:500): alice's and bob's home-relative repo.git are two repos."""
    root = make_repo(tmp_path)
    _git(root, "remote", "add", "origin", url)

    assert crew_tracker.repo_id(str(root)) == expected


def test_two_users_home_relative_repos_do_not_share_cards(tmp_path):
    vault = _make_vault(tmp_path / "vault", board_dir=".")
    first = _repo_at(tmp_path, "a/app", vault, origin="alice@host:repo.git")
    other = _repo_at(tmp_path, "b/app", vault, rows="T-0060 | direction | - | app | B work\n",
                     origin="bob@host:repo.git")
    assert _cli(first, "create", "--ticket", "T-0060", "--title", "A work").returncode == 0

    done, untouched = _refused(tmp_path, other, ("move", "--ticket", "T-0060", "--to", "done"))

    assert (done.returncode, untouched, "belongs to another repo" in done.stdout) == (1, True, True)


def test_create_loses_the_note_race_says_id_taken(tmp_path, monkeypatch):
    """Round 4 FIX (:1191): B creates T-0060 between A's owner check and A's
    writes. A must refuse, and write no INDEX row and no card."""
    vault = _make_vault(tmp_path / "vault", board_dir=".")
    first = _repo_at(tmp_path, "a/app", vault)
    other = _repo_at(tmp_path, "b/app", vault)
    real = crew_tracker._card_owner  # pylint: disable=protected-access
    raced = []

    def racing(paths, here):
        got = real(paths, here)
        if not raced:
            raced.append(_cli(other, "create", "--ticket", "T-0060", "--title", "B work").returncode)
        return got

    monkeypatch.setattr(crew_tracker, "_card_owner", racing)

    got = crew_tracker.create(str(first), "T-0060", "A work")
    board = (vault / "Board.md").read_text(encoding="utf-8")
    note = (vault / "T-0060.md").read_text(encoding="utf-8")

    assert (raced, crew_tracker.exit_code(got), got["results"][-1]["reason"].startswith("id taken: "),
            _index(first), board.count("[[T-0060]]"), "B work" in board,
            f"repo-id: {crew_tracker.repo_id(str(other))}\n" in note) == (
        [0], 1, True, "", 1, True, True)


def test_create_on_a_held_id_says_id_taken_when_the_vault_is_missing(tmp_path):
    """Round 4 FIX (:1185): a vault failure must not hide a held id -- brainstorm
    and fix go to the next id only on `id taken`."""
    root = _obsidian_repo(tmp_path, tmp_path / "no-such-vault")
    (root / ".work" / "INDEX.md").write_text(ROW + "T-0050 | ready | - | r | Fix tests\n", encoding="utf-8")

    done, untouched = _refused(tmp_path, root, ("create", "--ticket", "T-0050", "--title", "Fix tests"))

    assert (done.returncode, untouched, done.stdout) == (
        1, True, 'files: could not update: id taken: T-0050 is already ready "Fix tests"\n')


def test_obsidian_create_writes_no_card_when_index_refuses_late(tmp_path, monkeypatch):
    """A row appended after the early INDEX read still stops the card."""
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)
    (root / ".work" / "INDEX.md").write_text(ROW + "T-0061 | spec | - | repo | someone's\n", encoding="utf-8")
    monkeypatch.setattr(crew_tracker, "_index_holds", lambda root, ticket: None)
    board = (vault / "Boards" / "repo" / "Board.md").read_bytes()

    got = crew_tracker.create(str(root), "T-0061", "mine")

    assert (crew_tracker.exit_code(got), got["results"][0]["reason"].startswith("id taken: "),
            (vault / "Boards" / "repo" / "Board.md").read_bytes() == board) == (1, True, True)


def _crlf_note(ident, ticket=CARD):
    """Built here, not a tracked fixture: core.autocrlf rewrites a fixture's endings."""
    return f"---\ntitle: \"t\"\n---\n\n# {ticket} t\n\n- repo: repo\n- repo-id: {ident}\n".replace(
        "\n", "\r\n").encode("utf-8")


def test_crlf_note_is_this_repos(tmp_path):
    """Round 4 FIX (:1134): the `\\r` is not part of the id."""
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault, own=False)
    (vault / "Boards" / "repo" / f"{CARD}.md").write_bytes(_crlf_note(crew_tracker.repo_id(str(root))))

    done = _cli(root, "move", "--ticket", CARD, "--to", "in-progress")
    board = (vault / "Boards" / "repo" / "Board.md").read_text(encoding="utf-8")

    assert (done.returncode, _lane_of(board, CARD)) == (0, "In Progress")


def test_crlf_note_naming_another_repo_is_still_foreign(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault, own=False)
    (vault / "Boards" / "repo" / f"{CARD}.md").write_bytes(_crlf_note("https://example.invalid/other"))

    done, untouched = _refused(tmp_path, root)

    assert (done.returncode, untouched, "belongs to another repo (https://example.invalid/other," in done.stdout) == (
        1, True, True)


def _boxless():
    text = _fixture("board_0_20.md").replace("- [ ] [[T-0042]] Fix token refresh on 401", "- T-0042")
    board, problem = crew_tracker.parse_board(text, COLUMNS)
    assert problem is None, problem
    return board


def test_checkboxless_card_is_checked_in_done():
    """Round 4 FIX (:837): a card with no box still reads done in Done."""
    new, _, problem = crew_tracker.move_card(_boxless(), CARD, "done")
    lines = new.splitlines()

    assert (problem, "- [x] T-0042" in lines, "- T-0042" in lines,
            lines.index("- [x] T-0042") > lines.index("**Complete**")) == (None, True, False, True)


def test_checkboxless_card_gets_an_empty_box_elsewhere():
    new, _, problem = crew_tracker.move_card(_boxless(), CARD, "review")
    lines = new.splitlines()

    assert (problem, "- [ ] T-0042" in lines, "- T-0042" in lines) == (None, True, False)
