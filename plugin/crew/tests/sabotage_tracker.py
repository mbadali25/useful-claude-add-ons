"""The T-0021 mutations for `crew_tracker.py`, appended to `sabotage.py`'s
MUTATIONS. Kept apart for the reason every `sabotage_*.py` sibling is:
`sabotage.py` sits at `.pylintrc`'s max-module-lines. Run that file, not this.

`crew_tracker.py` is the only crew code that writes outside the repository,
so every guard branch it has gets one mutation here, each aimed at the one
test that can see that branch alone. Two pairs of guards are layered on
purpose and are mutated separately for that reason: the `..` segment check and
the vault confinement check (`Boards/../Boards/repo` stays inside the vault, so
only the segment check catches it; a board symlink leaves the vault with no
`..` in sight, so only the confinement check does).
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACKER = os.path.join(CREW, "hooks", "scripts", "crew_tracker.py")
BRAINSTORM = os.path.join(CREW, "commands", "brainstorm.md")
_TESTS = "tests/test_crew_tracker.py::"
_LIFECYCLE = "tests/test_lifecycle_commands.py::"

TRACKER_MUTATIONS = (
    (
        # The unknown-collapses-to-safe bug: crew.json's kind wins silently.
        "tracker resolve picks crew.json's kind when the two files disagree",
        TRACKER,
        '        if first["kind"] != second["kind"]:\n',
        "        if False:\n",
        _TESTS + "test_resolve_both_disagree_is_could_not_tell",
    ),
    (
        "tracker resolve ignores disagreeing settings under an agreeing kind",
        TRACKER,
        '            if (kind in first["blocks"] and kind in second["blocks"]\n',
        '            if (False and kind in first["blocks"] and kind in second["blocks"]\n',
        _TESTS + "test_resolve_both_disagree_on_the_kinds_settings_is_could_not_tell",
    ),
    (
        "tracker resolve accepts a kind crew does not know",
        TRACKER,
        "    if kind not in KINDS:\n",
        "    if False:\n",
        _TESTS + "test_resolve_unknown_kind",
    ),
    (
        "tracker writes run on kind 'could not tell'",
        TRACKER,
        '    if kind == COULD_NOT_TELL:\n        return _result("tracker", FAILED,',
        '    if False:\n        return _result("tracker", FAILED,',
        _TESTS + "test_kind_could_not_tell_writes_nothing",
    ),
    (
        "tracker move accepts a status that maps to no lane",
        TRACKER,
        "    if status not in LANE_FOR_STATUS:\n",
        "    if False:\n",
        _TESTS + "test_files_move_unknown_status_writes_nothing",
    ),
    (
        # A concurrent INDEX append is overwritten by a stale recompute.
        "tracker replaces without re-reading the target first",
        TRACKER,
        "            if _read_bytes(path) != before:\n",
        "            if False:\n",
        _TESTS + "test_files_move_retries_when_index_changes",
    ),
    (
        "tracker files move rewrites the first of two rows for one ticket",
        TRACKER,
        "        if len(found) > 1:\n",
        "        if False:\n",
        _TESTS + "test_files_move_refuses_two_rows_for_one_ticket",
    ),
    (
        "tracker accepts a '|' in a title, breaking the INDEX row",
        TRACKER,
        '    return bool(title) and "|" not in title and title.splitlines() == [title]\n',
        "    return bool(title) and title.splitlines() == [title]\n",
        _TESTS + "test_files_create_refuses_a_pipe_in_the_title",
    ),
    (
        # Round 1 FIX: U+2028 and kin split the card on the next parse.
        "tracker accepts a title holding a line separator splitlines splits on",
        TRACKER,
        '    return bool(title) and "|" not in title and title.splitlines() == [title]\n',
        '    return bool(title) and "|" not in title and not any(ch in title for ch in "\\r\\n")\n',
        _TESTS + "test_title_with_a_line_separator_is_refused",
    ),
    (
        "tracker splits a board where Obsidian does not, cutting a card in two",
        TRACKER,
        "    lines = _board_lines(text)\n",
        "    lines = text.splitlines(keepends=True)\n",
        _TESTS + "test_a_human_card_holding_a_line_separator_moves_whole",
    ),
    (
        "tracker writes a vault with no .obsidian/",
        TRACKER,
        '    if not os.path.isdir(os.path.join(vault, ".obsidian")):\n',
        "    if False:\n",
        _TESTS + "test_vault_without_dot_obsidian",
    ),
    (
        "tracker accepts an absolute boardDir",
        TRACKER,
        '    if os.path.isabs(board_dir) or ntpath.isabs(board_dir) or board_dir.startswith(("/", "\\\\")):\n',
        "    if False:\n",
        _TESTS + "test_board_dir_absolute",
    ),
    (
        "tracker accepts a '..' segment in boardDir",
        TRACKER,
        '    if ".." in re.split(r"[\\\\/]", board_dir):\n',
        "    if False:\n",
        _TESTS + "test_board_dir_dotdot",
    ),
    (
        "tracker accepts a board name with a path separator",
        TRACKER,
        '        if not name or name in (".", "..") or any(sep in name for sep in "/\\\\"):\n',
        "        if False:\n",
        _TESTS + "test_board_name_with_separator",
    ),
    (
        # The confinement check itself: a board symlink out of the vault.
        "tracker writes a board that resolves outside the vault",
        TRACKER,
        "        if not _inside(vault, real):\n",
        "        if False:\n",
        _TESTS + "test_board_symlink_outside_vault",
    ),
    (
        "tracker creates a note that resolves outside the vault",
        TRACKER,
        "        if not _inside(vault, real):\n",
        "        if False:\n",
        _TESTS + "test_note_symlink_outside_vault",
    ),
    (
        "tracker writes a board that is not a regular file",
        TRACKER,
        "        if os.path.lexists(real) and not os.path.isfile(real):\n",
        "        if False:\n",
        _TESTS + "test_board_that_is_a_directory_is_refused",
    ),
    (
        # The board would be staged into the review bundle.
        "tracker writes an in-worktree vault git does not ignore",
        TRACKER,
        "        if not ignored:\n",
        "        if False:\n",
        _TESTS + "test_vault_in_worktree_not_ignored",
    ),
    (
        # Round 1 FIX: the neighbour -- a vault that CONTAINS the repo.
        "tracker checks only the vault against the worktree, not the board",
        TRACKER,
        "        if not _inside(repo, found[label]):\n",
        "        if not _inside(repo, vault):\n",
        _TESTS + "test_board_inside_worktree_of_a_vault_that_contains_it_is_refused",
    ),
    (
        "tracker reads git failing as 'not ignored' instead of 'could not tell'",
        TRACKER,
        "        if ignored is None:\n",
        "        if False:\n",
        _TESTS + "test_vault_in_worktree_git_cannot_say_is_refused",
    ),
    (
        # The INDEX half is written before the board says it has no card.
        "tracker move skips the card lookup before writing anything",
        TRACKER,
        "    if not problem:\n        _, _, problem = move_card(board, ticket, key)\n",
        "",
        _TESTS + "test_obsidian_move_without_a_card_writes_nothing",
    ),
    (
        "tracker rewrites an existing ticket note",
        TRACKER,
        '        with open(paths["note"], "xb") as handle:\n',
        '        with open(paths["note"], "wb") as handle:\n',
        _TESTS + "test_note_created_once_never_overwritten",
    ),
    (
        "tracker edits a board with no kanban-plugin key",
        TRACKER,
        "            if any(_KANBAN_KEY.match(_bare(line)) for line in lines[1:index]):\n",
        "            if True:\n",
        _TESTS + "test_frontmatter_without_the_kanban_key_refused",
    ),
    (
        "tracker edits a board missing a configured lane",
        TRACKER,
        "        if count == 0:\n",
        "        if False:\n",
        _TESTS + "test_default_columns_on_a_renamed_board_refused",
    ),
    (
        "tracker edits a board with a duplicated lane",
        TRACKER,
        "        if count > 1:\n",
        "        if False:\n",
        _TESTS + "test_duplicate_lane_refused",
    ),
    (
        "tracker edits a board whose settings block is not last",
        TRACKER,
        "        if close is None or any(_bare(line).strip() for line in lines[close + 1:]):\n",
        "        if False:\n",
        _TESTS + "test_settings_block_not_last_refused",
    ),
    (
        "tracker moves the first of two cards for one ticket",
        TRACKER,
        "    if len(matches) > 1:\n",
        "    if False:\n",
        _TESTS + "test_two_cards_same_id_refused",
    ),
    (
        # Round 1 BLOCK: the temp opened through a planted symlink.
        "tracker opens its temp file without exclusive create",
        TRACKER,
        "_TEMP_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW | _BINARY\n",
        "_TEMP_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | _BINARY\n",
        _TESTS + "test_temp_name_collision_never_follows_a_link",
    ),
    (
        "tracker replaces a board without keeping its mode",
        TRACKER,
        "        os.fchmod(fd, mode)\n",
        "        pass\n",
        _TESTS + "test_board_keeps_its_mode",
    ),
    (
        # RED only as root: the test skips, by name, without root.
        "tracker replaces a board without keeping its owner",
        TRACKER,
        "                os.fchown(fd, uid, gid)\n",
        "                pass\n",
        _TESTS + "test_board_keeps_its_owner",
    ),
    (
        # RED only as root, as above.
        "tracker creates a note as root instead of its directory's owner",
        TRACKER,
        '    if hasattr(os, "fchown") and (replaces or _is_root()):\n',
        '    if hasattr(os, "fchown") and replaces:\n',
        _TESTS + "test_new_note_takes_its_directory_owner_when_root",
    ),
    (
        # Round 1 FIX: another repo's card on a shared board.
        "tracker moves a card whose note names another repo",
        TRACKER,
        "    if owner is not None and owner != here:\n",
        "    if False:\n",
        _TESTS + "test_move_refuses_a_card_another_repo_owns",
    ),
    (
        "tracker create adopts a card no note claims as 'unchanged'",
        TRACKER,
        "        if owner is None:\n",
        "        if False:\n",
        _TESTS + "test_create_refuses_a_card_on_a_shared_board_no_note_claims",
    ),
    (
        "tracker move writes the board for a ticket this repo never minted",
        TRACKER,
        '    if not problem and _files_read(root, ticket)["state"] != READ:\n',
        "    if False:\n",
        _TESTS + "test_move_without_this_repos_index_row_writes_nothing",
    ),
    (
        # 'could not tell' must survive onto the line, not read as ours.
        "tracker move drops 'could not tell whose card' from its line",
        TRACKER,
        '    caveat = f" (whose card could not tell: {unknown})" if unknown else ""\n',
        '    caveat = ""\n',
        _TESTS + "test_move_says_when_no_note_names_the_cards_repo",
    ),
    (
        "tracker move indexes a status cell an INDEX row does not have",
        TRACKER,
        "        if len(cells) < 2:\n            return None, _result(backend, FAILED, _no_status_cell(ticket))\n",
        "        if False:\n            return None, _result(backend, FAILED, _no_status_cell(ticket))\n",
        _TESTS + "test_index_row_without_a_status_cell_is_could_not_update",
    ),
    (
        "tracker read indexes a status cell an INDEX row does not have",
        TRACKER,
        '    if len(cells) < 2:\n        return _result("files", UNREADABLE, _no_status_cell(ticket))\n',
        '    if False:\n        return _result("files", UNREADABLE, _no_status_cell(ticket))\n',
        _TESTS + "test_read_of_a_row_without_a_status_cell_is_could_not_read",
    ),
    (
        "tracker create lets a failed .work mkdir escape as a traceback",
        TRACKER,
        '    except OSError as exc:\n        return _result(backend, FAILED, f".work: {exc.strerror or exc}")\n',
        '    except KeyError as exc:\n        return _result(backend, FAILED, f".work: {exc.strerror or exc}")\n',
        _TESTS + "test_create_with_work_a_file_is_could_not_update",
    ),
    (
        "tracker takes a non-string obsidian.board as a file name",
        TRACKER,
        "        if not isinstance(name, str):\n",
        "        if False:\n",
        _TESTS + "test_non_string_board_name_is_refused",
    ),
    (
        # Round 1 FIX: brainstorm's approval status had no lane.
        "tracker maps brainstorm's 'ready' status to no lane",
        TRACKER,
        '    "ready": "backlog",\n',
        "",
        _TESTS + "test_ready_status_maps_to_the_backlog_lane",
    ),
    (
        "brainstorm hand-edits INDEX on approval instead of moving the tracker",
        BRAINSTORM,
        "crew_tracker.py move --root . --ticket <id> --to ready",
        "crew_tracker.py (no move on approval)",
        _LIFECYCLE + "test_every_transition_calls_the_tracker",
    ),
    (
        "tracker read drops 'could not tell whose card' from its line",
        TRACKER,
        '    notes += [f"whose card could not tell: {unknown}"] if unknown else []\n',
        "",
        _TESTS + "test_read_says_when_no_note_names_the_cards_repo",
    ),
)
