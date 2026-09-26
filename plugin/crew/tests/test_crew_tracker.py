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
