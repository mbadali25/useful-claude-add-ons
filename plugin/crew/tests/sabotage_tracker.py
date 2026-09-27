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
FIX = os.path.join(CREW, "commands", "fix.md")
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
        '            elif first["blocks"].get(kind) != second["blocks"].get(kind):\n',
        "            elif False:\n",
        _TESTS + "test_resolve_both_disagree_on_jira_settings_is_could_not_tell",
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
        "            if _read_bytes(path, dir_fd=dir_fd) != before:\n",
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
        "        _, problem = find_card(board, ticket)\n",
        "        _ = find_card(board, ticket)[0]\n",
        _TESTS + "test_obsidian_move_without_a_card_writes_nothing",
    ),
    (
        "tracker rewrites an existing ticket note",
        TRACKER,
        "_NOTE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW | _BINARY\n",
        "_NOTE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | _BINARY\n",
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
        "        if owner == FOREIGN:\n            problem = _foreign(paths, ticket, detail, here)\n"
        "        elif owner == UNKNOWN:\n",
        "        if False:\n            problem = _foreign(paths, ticket, detail, here)\n"
        "        elif owner == UNKNOWN:\n",
        _TESTS + "test_move_refuses_a_card_another_repo_owns",
    ),
    (
        "tracker create adopts a card no note claims as 'unchanged'",
        TRACKER,
        '        elif owner == UNKNOWN and (note or any(card["id"] == ticket for card in _cards(board))):\n',
        "        elif False:\n",
        _TESTS + "test_create_refuses_a_card_on_a_shared_board_no_note_claims",
    ),
    (
        "tracker move writes the board for a ticket this repo never minted",
        TRACKER,
        '    if not problem and row["state"] != READ:\n'
        '        problem = f"no {INDEX_REL} row for {ticket} in this repo"\n',
        "",
        _TESTS + "test_move_without_this_repos_index_row_writes_nothing",
    ),
    (
        # Round 2 FIX (:876): 'could not tell' must refuse, not move with a caveat.
        "tracker moves a card whose owner it could not tell",
        TRACKER,
        "        elif owner == UNKNOWN:\n            problem = _unclaimed(paths, ticket, detail, here)\n",
        "        elif owner == UNKNOWN:\n            problem = None\n",
        _TESTS + "test_move_refuses_a_card_no_note_claims",
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
        '    notes += [f"whose card could not tell: {detail}"] if owner == UNKNOWN else []\n',
        "",
        _TESTS + "test_read_says_when_no_note_names_the_cards_repo",
    ),
    (
        # Round 2 FIX (:830): ownership by basename -- a/app is b/app.
        "tracker owns a card by the origin's basename, not the origin",
        TRACKER,
        "        return normal_url(url)\n",
        "        return os.path.basename(normal_url(url))\n",
        _TESTS + "test_same_repo_name_is_not_the_same_repo",
    ),
    (
        "tracker owns a card by the repo directory's name when there is no origin",
        TRACKER,
        "    if code == 2:\n        return os.path.realpath(common)\n",
        "    if code == 2:\n        return os.path.basename(os.path.dirname(os.path.realpath(common)))\n",
        _TESTS + "test_same_repo_name_is_not_the_same_repo",
    ),
    (
        # The identity is written into a note a human reads: no credentials.
        "tracker keeps the origin URL's userinfo in the repo-id",
        TRACKER,
        "        url = f\"{scheme}://{keep}{host.rpartition('@')[2]}{slash}{path}\"\n",
        "        url = f\"{scheme}://{host}{slash}{path}\"\n",
        _TESTS + "test_note_records_repo_id_without_credentials",
    ),
    (
        "tracker moves when git cannot say which repo this is",
        TRACKER,
        "    if not problem and here is None:\n        problem = _no_identity(root)\n"
        "    board, problem = (None, problem) if problem else _load_board(paths, columns)\n"
        "    if not problem:\n        _, problem = find_card(board, ticket)\n",
        "    board, problem = (None, problem) if problem else _load_board(paths, columns)\n"
        "    if not problem:\n        _, problem = find_card(board, ticket)\n",
        _TESTS + "test_move_refuses_when_this_repos_identity_cannot_be_told",
    ),
    (
        # Round 2 FIX (:181): the memory-vault fallback against a named vault.
        "tracker resolve ignores a disagreement in the effective vault or boardDir",
        TRACKER,
        "        if one != two:\n",
        "        if False:\n",
        _TESTS + "test_resolve_compares_the_effective_vault",
    ),
    (
        "tracker resolve reads an unset boardDir as no value, not the vault root",
        TRACKER,
        '    elif board_dir is None and vault is not None:\n        board_dir = ""\n',
        "",
        _TESTS + "test_resolve_accepts_an_explicit_vault_root_board_dir_beside_an_unset_one",
    ),
    (
        # Round 2 FIX (:422): another session's id, silently taken over.
        "tracker create answers 'unchanged' for an id INDEX holds under another title",
        TRACKER,
        "        if held:\n            return None, _result(backend, FAILED, _held(ticket, held))\n",
        "        if False:\n            return None, _result(backend, FAILED, _held(ticket, held))\n",
        _TESTS + "test_create_refuses_an_id_another_session_holds",
    ),
    (
        "tracker create writes the card after the INDEX half refused",
        TRACKER,
        # INDEX is read before the vault too (review round 4), so only a row
        # appended after that read reaches this refusal.
        '    files = _files_create(root, ticket, title)\n    if files["state"] == FAILED:\n        return [files, claim]\n',
        "    files = _files_create(root, ticket, title)\n",
        _TESTS + "test_obsidian_create_writes_no_card_when_index_refuses_late",
    ),
    (
        # Round 2 FIX (:911): five pushes per ticket, none naming a target.
        "tracker pushes Jira/SDP on every move",
        TRACKER,
        "    if status in _PUSH_AT:\n",
        "    if True:\n",
        _TESTS + "test_jira_and_sdp_push_at_boundaries_only",
    ),
    (
        "tracker's delegated push drops the target status",
        TRACKER,
        '    command = f"{_SYNC[kind]} {ticket}" + (f" --push --to {to}" if to else "")\n',
        '    command = f"{_SYNC[kind]} {ticket}" + (" --push" if to else "")\n',
        _TESTS + "test_jira_and_sdp_push_at_boundaries_only",
    ),
    (
        # Round 2 FIX (:727): the write re-walks a path a link was planted in.
        "tracker follows a link in the board's directory path when it writes",
        TRACKER,
        "            inner = os.open(part, _DIR_FLAGS, dir_fd=fd)\n",
        "            inner = os.open(part, os.O_RDONLY, dir_fd=fd)\n",
        _TESTS + "test_board_dir_swapped_for_a_link_after_the_checks_writes_nothing_outside",
    ),
    (
        "tracker writes into whatever directory now sits at the vault's path",
        TRACKER,
        '        if (seen.st_dev, seen.st_ino) != paths["vaultId"]:\n',
        "        if False:\n",
        _TESTS + "test_vault_replaced_after_the_checks_writes_nothing",
    ),
    (
        # The Windows branch, run on POSIX by switching dir_fd support off.
        "tracker's no-dir_fd branch writes without re-checking the directory",
        TRACKER,
        "        yield paths[label], None, _parent_check(paths, label)\n",
        "        yield paths[label], None, None\n",
        _TESTS + "test_board_dir_swapped_for_a_link_after_the_checks_writes_nothing_outside",
    ),
    (
        # Round 2 NIT (:72): STATUS_ORDER was defined and never read.
        "tracker moves a ticket backwards without --reopen",
        TRACKER,
        "    if STATUS_ORDER.index(status) < STATUS_ORDER.index(current):\n",
        "    if False:\n",
        _TESTS + "test_backwards_move_is_refused",
    ),
    (
        "tracker moves from a status it does not know as if forward",
        TRACKER,
        "    if current not in STATUS_ORDER:\n",
        "    if current not in STATUS_ORDER:\n        return None\n    if False:\n",
        _TESTS + "test_move_from_a_status_crew_does_not_know_is_could_not_tell",
    ),
    (
        "tracker ignores --reopen",
        TRACKER,
        "        backwards = None if reopen else _backwards(ticket, current, status)\n",
        "        backwards = _backwards(ticket, current, status)\n",
        _TESTS + "test_backwards_move_with_reopen_goes_ahead",
    ),
    (
        # Round 2 NIT (fix.md:84): a bare call is "command not found".
        "fix.md calls crew_tracker.py without the plugin-root prefix",
        FIX,
        "`python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_tracker.py move --root . --ticket <id> --to review`",
        "`crew_tracker.py move --root . --ticket <id> --to review`",
        _LIFECYCLE + "test_every_tracker_call_in_commands_carries_the_prefix",
    ),
    # --- review round 3 ----------------------------------------------------------
    (
        # Round 3 BLOCK (:973): the pinned fd follows its directory out of the vault.
        "tracker writes through a pinned directory without re-walking to it",
        TRACKER,
        "        yield os.path.basename(paths[label]), fd, _pinned_check(paths, label, fd)\n",
        "        yield os.path.basename(paths[label]), fd, lambda: None\n",
        _TESTS + "test_board_dir_moved_out_of_the_vault_after_pinning_writes_nothing_there",
    ),
    (
        "tracker takes a different directory at the pinned one's path as the same",
        TRACKER,
        "        if (seen.st_dev, seen.st_ino) != (held.st_dev, held.st_ino):\n",
        "        if False:\n",
        _TESTS + "test_board_dir_moved_out_of_the_vault_after_pinning_writes_nothing_there[replaced]",
    ),
    (
        "tracker writes the note before checking its directory is still in the vault",
        TRACKER,
        '            moved = check()\n            if moved:\n                return _result("obsidian-note", FAILED, moved)\n',
        "",
        _TESTS + "test_note_dir_moved_out_of_the_vault_after_pinning_leaves_no_note_there",
    ),
    (
        "tracker leaves a note it wrote into a directory that left the vault",
        TRACKER,
        "                _discard(name, fd)\n",
        "",
        _TESTS + "test_note_dir_moved_out_after_the_note_is_written_removes_it_there",
    ),
    (
        # Round 3 FIX (:503): `../origin/app.git` is one string, two repositories.
        "tracker takes a relative local origin as the repo's identity",
        TRACKER,
        "        if os.path.isabs(local) or ntpath.isabs(local):\n            return os.path.realpath(local)\n"
        "        return os.path.realpath(common)\n",
        "        return normal_url(url)\n",
        _TESTS + "test_relative_local_origins_are_not_one_repo",
    ),
    (
        "tracker reads an scp-style origin as a local path",
        TRACKER,
        '    if ":" in head and not ntpath.splitdrive(url)[0]:\n        return None\n',
        "",
        _TESTS + "test_repo_id_normalises_the_origin_url",
    ),
    (
        # Round 3 FIX (:1138): a matching title is not an owner.
        "tracker moves another repo's no-note card when the titles match",
        TRACKER,
        "        elif owner == UNKNOWN:\n            problem = _unclaimed(paths, ticket, detail, here)\n",
        "        elif owner == UNKNOWN:\n            problem = None\n",
        _TESTS + "test_move_refuses_another_repos_unclaimed_card_with_the_same_title",
    ),
    (
        # Round 3 FIX (:565): the same title is still another session's id.
        "tracker create answers 'unchanged' for a held id under the same title",
        TRACKER,
        "        held = [_cells(lines[i]) for i in _rows(lines, ticket)]\n        if held:\n",
        "        held = [_cells(lines[i]) for i in _rows(lines, ticket)]\n"
        "        if len(held) == 1 and len(held[0]) > 4 and held[0][4] == title:\n"
        '            return None, _result(backend, UNCHANGED, "already")\n'
        "        if held:\n",
        _TESTS + "test_create_refuses_a_held_id_under_the_same_title",
    ),
    (
        "tracker create does not say 'id taken' for another repo's card",
        TRACKER,
        '            problem = f"{TAKEN}: " + _foreign(paths, ticket, detail, here)\n',
        "            problem = _foreign(paths, ticket, detail, here)\n",
        _TESTS + "test_create_on_an_id_the_board_holds_says_id_taken[foreign]",
    ),
    (
        "tracker create does not say 'id taken' for a card whose owner it cannot tell",
        TRACKER,
        '            problem = f"{TAKEN}: " + _unclaimed(paths, ticket, detail, here)\n',
        "            problem = _unclaimed(paths, ticket, detail, here)\n",
        _TESTS + "test_create_on_an_id_the_board_holds_says_id_taken[unknown]",
    ),
    (
        # Round 3 FIX (brainstorm.md:35, fix.md:29): a refused mint carried on.
        "brainstorm carries on under an id create said is taken",
        BRAINSTORM,
        "If a line says `id taken`, that id is not yours",
        "If a line says anything, carry on",
        _LIFECYCLE + "test_a_taken_id_is_never_written_under[brainstorm.md]",
    ),
    (
        "fix carries on under an id create said is taken",
        FIX,
        "If a line says `id taken`, that id is not yours",
        "If a line says anything, carry on",
        _LIFECYCLE + "test_a_taken_id_is_never_written_under[fix.md]",
    ),
    (
        # Round 3 FIX (:222): only one file carried the block.
        "tracker resolve compares only the vault and boardDir each file yields",
        TRACKER,
        '    for field in ("vaultPath", "boardDir", "board", "columns"):\n',
        '    for field in ("vaultPath", "boardDir"):\n',
        _TESTS + "test_resolve_compares_every_effective_obsidian_setting",
    ),
    (
        "tracker resolve takes a value one file yields and the other does not",
        TRACKER,
        "        if one != two:\n",
        "        if one is not None and two is not None and one != two:\n",
        _TESTS + "test_resolve_refuses_one_file_naming_a_vault_the_other_does_not",
    ),
    (
        "tracker resolve takes the Jira/SDP block only one file carries",
        TRACKER,
        '            elif first["blocks"].get(kind) != second["blocks"].get(kind):\n',
        '            elif (kind in first["blocks"] and kind in second["blocks"]\n'
        '                  and first["blocks"][kind] != second["blocks"][kind]):\n',
        _TESTS + "test_resolve_refuses_a_block_only_one_file_carries",
    ),
    (
        # Round 3 FIX (:1158): the board moved after the INDEX half refused.
        "tracker moves the board after the INDEX half refused the move",
        TRACKER,
        '    files = _files_move(root, ticket, status, reopen)\n    if files["state"] == FAILED:\n        return [files]\n',
        "    files = _files_move(root, ticket, status, reopen)\n",
        _TESTS + "test_board_is_not_moved_when_the_index_half_refuses",
    ),
    (
        # The same gate now stops a backwards move's board half (round 2 NIT).
        "tracker moves the board back after the INDEX half refused a backwards move",
        TRACKER,
        '    files = _files_move(root, ticket, status, reopen)\n    if files["state"] == FAILED:\n        return [files]\n',
        "    files = _files_move(root, ticket, status, reopen)\n",
        _TESTS + "test_obsidian_backwards_move_leaves_the_board_alone",
    ),
    (
        # Round 3 FIX (:797): a card already in Done skipped its repair.
        "tracker leaves a card in its lane with the wrong checkbox",
        TRACKER,
        '        fixed[card["start"]] = _checkbox(lines[card["start"]], key)\n',
        '        fixed[card["start"]] = lines[card["start"]]\n',
        _TESTS + "test_move_to_done_rechecks_a_card_already_in_done",
    ),
    (
        "tracker leaves a card above **Complete** in Done",
        TRACKER,
        '    if card["lane"] == target and (key != "done" or card["start"] > _complete_markers(board)[0]):\n',
        '    if card["lane"] == target:\n',
        _TESTS + "test_move_to_done_puts_a_card_above_complete_below_it",
    ),
    (
        "tracker reports a card repaired in its lane as unchanged",
        TRACKER,
        '        if moved_from == columns[key] and new == "".join(current["lines"]):\n',
        "        if moved_from == columns[key]:\n",
        _TESTS + "test_backend_repairs_an_unchecked_card_already_in_done",
    ),
    (
        # Round 3 FIX (:765): a Done lane with no marker took a checked card.
        "tracker accepts a Done lane with no **Complete** marker",
        TRACKER,
        "    if markers != 1:\n",
        "    if markers > 1:\n",
        _TESTS + "test_done_lane_without_complete_writes_nothing",
    ),
    (
        "tracker accepts a Done lane with two **Complete** markers",
        TRACKER,
        "    if markers != 1:\n",
        "    if markers == 0:\n",
        _TESTS + "test_done_lane_needs_exactly_one_complete_marker",
    ),
)
