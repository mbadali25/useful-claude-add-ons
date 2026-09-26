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
_TESTS = "tests/test_crew_tracker.py::"

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
        "tracker accepts a title that breaks the INDEX row",
        TRACKER,
        '    return bool(title) and not any(ch in title for ch in "|\\r\\n")\n',
        "    return True\n",
        _TESTS + "test_files_create_refuses_a_pipe_in_the_title",
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
        "    if _inside(repo, vault):\n",
        "    if False:\n",
        _TESTS + "test_vault_in_worktree_not_ignored",
    ),
    (
        "tracker reads git failing as 'not ignored' instead of 'could not tell'",
        TRACKER,
        "            if ignored is None:\n",
        "            if False:\n",
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
)
