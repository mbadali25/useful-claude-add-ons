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


def _obsidian_repo(tmp_path, vault_path, **settings):
    root = make_repo(tmp_path)
    obsidian = {"vaultPath": str(vault_path), "boardDir": "Boards/repo", "board": "Board.md"}
    obsidian.update(settings)
    _crew_json(root, {"kind": "obsidian", "obsidian": obsidian})
    (root / ".work" / "INDEX.md").write_text(ROW, encoding="utf-8", newline="\n")
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
        "obsidian: updated: Boards/repo/Board.md Ready -> In Progress\n"
        "obsidian-note: updated: Boards/repo/T-0042.md created "
        "(its card's text is this repo's INDEX title, so the card is this repo's)\n",
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
        ["updated", "could not update", "updated"], ROW.replace("spec", "review"), 1)


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

    done = _cli(root, "create", "--ticket", "T-0060", "--title", "new work")

    assert (done.returncode, note.read_text(encoding="utf-8"), done.stdout.count("unchanged")) == (
        0, edited, 3)


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


@pytest.mark.parametrize("sep", [" ", " ", "\x85", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e"])
def test_title_with_a_line_separator_is_refused(tmp_path, sep):
    root = _files_repo(tmp_path, "T-0001 | done | low | repo | first\n")

    got = crew_tracker.create(str(root), "T-0002", f"split{sep}tail")

    assert (got["results"][0]["state"], _index(root)) == (
        "could not update", "T-0001 | done | low | repo | first\n")


def test_a_human_card_holding_a_line_separator_moves_whole():
    """Obsidian keeps U+2028 inside a line; str.splitlines does not. Splitting
    the board there would move half a card and strand the rest."""
    text = _fixture("board_0_20.md").replace("Fix token refresh on 401", "Fix token refresh on 401", 1)
    board, problem = crew_tracker.parse_board(text, COLUMNS)
    assert problem is None, problem

    moved, _, why = crew_tracker.move_card(board, CARD, "review")

    assert (why, moved.count(" "), "- [ ] [[T-0042]] Fix token refresh on 401\n" in moved,
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
    root = _obsidian_repo(tmp_path, vault)

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
    ("ssh://git@Example.invalid:22/Owner/Repo.git", "ssh://example.invalid:22/owner/repo"),
    ("git@GitHub.com:Owner/Repo.git", "github.com:owner/repo"),
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


def test_move_claims_an_exact_title_card_and_records_repo_id(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)
    note = vault / "Boards" / "repo" / "T-0042.md"

    done = _cli(root, "move", "--ticket", CARD, "--to", "review")

    assert (done.returncode, f"- repo-id: {crew_tracker.repo_id(str(root))}\n" in note.read_text(encoding="utf-8"),
            _lane_of((vault / "Boards/repo/Board.md").read_text(encoding="utf-8"), CARD)) == (0, True, "Review")


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

    assert (got["kind"], str(first) in got["problems"][0], str(second) in got["problems"][0],
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
        1, "files: could not update: T-0050 is already in-progress \"another session's auth rewrite\"\n", row)


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
    root = _obsidian_repo(tmp_path, vault, boardDir="B")
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
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)
    (root / ".work" / "INDEX.md").write_text(ROW.replace("spec", "review"), encoding="utf-8", newline="\n")

    done, untouched = _refused(tmp_path, root, ("move", "--ticket", CARD, "--to", "spec"))

    assert (done.returncode, untouched, "needs --reopen" in done.stdout) == (1, True, True)


def test_move_refuses_a_multi_line_card_when_index_has_no_title(tmp_path):
    """The claim's neighbour: no card text and no INDEX title are not a match."""
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)
    board = vault / "Boards" / "repo" / "Board.md"
    board.write_text(board.read_text(encoding="utf-8").replace(
        "Fix token refresh on 401\n", "Fix token refresh on 401\n\tsecond line\n", 1), encoding="utf-8", newline="\n")
    (root / ".work" / "INDEX.md").write_text("T-0042 | spec\n", encoding="utf-8", newline="\n")

    done, untouched = _refused(tmp_path, root)

    assert (done.returncode, untouched, "could not tell whose card T-0042 is" in done.stdout) == (1, True, True)
