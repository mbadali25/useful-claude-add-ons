"""The crew 1.0 T6 context-hook mutations, appended to `sabotage.py`'s
MUTATIONS. Kept apart because `sabotage.py` sits at `.pylintrc`'s
max-module-lines; the runner and its restore guarantees are `sabotage.py`'s.

Each was also run through `sabotage.py`'s own apply/run/restore helpers
before it was committed, and went red on its named test.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(CREW, "hooks", "scripts")
CONTEXT = os.path.join(SCRIPTS, "crew_context.py")
RECALL = os.path.join(SCRIPTS, "crew_recall.py")
INSTRUCTIONS = os.path.join(SCRIPTS, "crew_instructions.py")
_FIXES = "tests/test_crew_context_fixes.py::"
_WRAP = "tests/test_crew_context_wrappers.py::"
_INSTR = "tests/test_crew_instructions.py::"
_OFF = "  # pylint: disable=using-constant-test\n"

# The T6 review round: one per finding that changed code.
REVIEW_FIX_CONTEXT_MUTATIONS = (
    ("a failed session-state write is reported as saved",
     CONTEXT,
     "    except (OSError, TypeError, ValueError):\n        return False\n    return True\n",
     "    except (OSError, TypeError, ValueError):\n        return True\n    return True\n",
     _FIXES + "test_an_unsaved_state_emits_nothing_for_a_prompt_and_logs_why"),
    ("the emission log never rotates",
     CONTEXT,
     "            if os.path.getsize(path) >= LOG_MAX_BYTES:\n",
     "            if False:" + _OFF,
     _FIXES + "test_the_log_rotates_into_one_file_at_the_size_bound"),
    ("stats reads the whole emission log again",
     CONTEXT,
     "            handle.seek(max(0, size - limit))\n",
     "            handle.seek(0)\n",
     _FIXES + "test_stats_reads_only_the_bounded_tail_of_an_oversized_log"),
    ("parallel same-type subagents take the first unconsumed call again",
     CONTEXT,
     "        if len(open_calls) == 1:\n",
     "        if open_calls:\n",
     _FIXES + "test_parallel_same_type_subagents_without_an_id_get_no_task_recall"),
    ("the session state is read and written without the lock",
     CONTEXT,
     "    if not acquire_lock(lock):\n",
     "    if False:" + _OFF,
     _FIXES + "test_a_held_session_lock_means_nothing_is_emitted"),
    ("a snippet can close the vault-recall block",
     CONTEXT,
     "        lines += [_RECALL_DELIM_RE.sub(r\"&lt;\\1\", i[\"text\"]) for i in kept]\n",
     "        lines += [i[\"text\"] for i in kept]\n",
     _FIXES + "test_recalled_text_sits_inside_one_data_block_it_cannot_close"),
    ("a vault or note name carrying a line break is injected",
     RECALL,
     "        if _CONTROL_RE.search(vault) or _CONTROL_RE.search(note) or vault not in priority:\n",
     "        if vault not in priority:\n",
     _FIXES + "test_a_vault_or_note_name_with_a_line_break_is_dropped"),
    ("a snippet from a vault the repo did not ask for is injected",
     RECALL,
     "        if _CONTROL_RE.search(vault) or _CONTROL_RE.search(note) or vault not in priority:\n",
     "        if _CONTROL_RE.search(vault) or _CONTROL_RE.search(note):\n",
     _FIXES + "test_a_snippet_from_a_vault_not_asked_for_is_dropped"),
    ("codex overwrites a hand-written .codex/hooks.json",
     INSTRUCTIONS,
     "        ours = _codex_hooks_generated(current) if path.endswith(\".json\") else MARKER in (current or \"\")\n",
     "        ours = True if path.endswith(\".json\") else MARKER in (current or \"\")\n",
     _INSTR + "test_codex_never_overwrites_a_hand_written_hooks_json"),
    ("--check passes over a hand-written file at a generated path",
     INSTRUCTIONS,
     "    drift = [p for p in problems if not p.startswith(\"hand-written, left alone\")]\n",
     "    drift = [p for p in problems if not p.startswith(\"hand-written\")]\n",
     _INSTR + "test_rules_check_fails_on_a_hand_written_file_at_a_generated_path"),
    ("the rule source hash ignores paths, anchor, filename and name",
     INSTRUCTIONS,
     "    return _sha(json.dumps([sub[\"name\"], sub[\"file\"], list(sub[\"paths\"]), sub[\"anchor\"],\n",
     "    return _sha(json.dumps([\n",
     _INSTR + "test_the_recorded_source_hash_moves_with_every_rendered_input"),
    ("a rule with many scoped paths is no longer cut to 30 lines",
     INSTRUCTIONS,
     "    if len(paths) > room_paths:\n",
     "    if False:" + _OFF,
     _INSTR + "test_a_rule_with_24_scoped_paths_still_fits_30_lines"),
)

CONTEXT_MUTATIONS = (
    (
        # The hard cap raised past Codex's ~2,500-token context limit.
        "the context hook's hard cap is raised to 60,000 chars",
        CONTEXT,
        "HARD_CAP = 6000\n",
        "HARD_CAP = 60000\n",
        ("tests/test_crew_context.py::"
         "test_fit_never_exceeds_the_6000_char_hard_cap_whatever_the_budget"),
    ),
    (
        # A recall line that no longer says which vault it came from.
        "recall snippets are injected without their vault label",
        RECALL,
        "    return f\"- [vault:{snippet['vault']}] {snippet['note']}: {snippet['text']}\"\n",
        "    return f\"- {snippet['note']}: {snippet['text']}\"\n",
        ("tests/test_crew_context.py::"
         "test_every_recall_snippet_names_its_vault_and_unlabelled_items_are_dropped"),
    ),
    (
        # An item the CLI returned with no vault is let through. Since the
        # T6 review the vault allow-list below the first check drops an empty
        # vault too, so deleting the first check alone went STILL GREEN:
        # the mutation now exempts the empty vault from both.
        "unlabelled recall items are no longer dropped",
        RECALL,
        ("        if not vault or not note or not text:\n"
         "            dropped += 1\n"
         "            continue\n"
         "        if _CONTROL_RE.search(vault) or _CONTROL_RE.search(note) or vault not in priority:\n"),
        ("        if not note or not text:\n"
         "            dropped += 1\n"
         "            continue\n"
         "        if _CONTROL_RE.search(vault) or _CONTROL_RE.search(note) or (vault and vault not in priority):\n"),
        ("tests/test_crew_context.py::"
         "test_every_recall_snippet_names_its_vault_and_unlabelled_items_are_dropped"),
    ),
    (
        # Dedup dropped: the same slice on every touch of the subsystem.
        "the context hook no longer deduplicates per subsystem and epoch",
        CONTEXT,
        "        if item.get(\"id\") and item[\"id\"] in seen:\n",
        "        if False:  # pylint: disable=using-constant-test\n",
        "tests/test_crew_context.py::test_a_subsystem_slice_is_injected_once_per_epoch",
    ),
    (
        # The compaction epoch never advances: a slice lost with the
        # compacted context is never re-injected.
        "a compaction no longer starts a new dedup epoch",
        CONTEXT,
        "            state[\"epoch\"] += 1\n",
        "            state[\"epoch\"] += 0\n",
        ("tests/test_crew_context.py::"
         "test_a_compaction_starts_a_new_epoch_and_the_slice_returns"),
    ),
    (
        # T-0076: without the pin, Windows' text-mode stdout writes CRLF and
        # the route hook's byte-identical tests fail on sh and ps1.
        "the context hook inherits the platform's line ending",
        CONTEXT,
        '            sys.stdout.reconfigure(newline="\\n")\n',
        "            pass\n",
        ("tests/test_crew_context.py::"
         "test_emit_writes_lf_even_through_a_crlf_translating_stdout"),
    ),
) + REVIEW_FIX_CONTEXT_MUTATIONS

# L-0676: L-0675's `--project` for the recall CLI. Each puts one bug back that
# the project tests were written against.
_PROJECT = "tests/test_crew_recall_project.py::"

RECALL_PROJECT_MUTATIONS = (
    ("recall: the project is never sent", RECALL,
     '    tries = [argv + ["--project=" + ",".join(names)], argv] if names else [argv]\n',
     "    tries = [argv]\n",
     _PROJECT + "test_the_main_checkout_name_is_sent_as_the_project"),
    ("recall: the project is the worktree's own directory name", RECALL,
     "    name = _main_checkout_name(root)\n",
     "    name = os.path.basename(os.path.abspath(root))\n",
     _PROJECT + "test_a_linked_worktree_sends_the_main_checkout_name"),
    ("recall: an exit 2 is not retried without the project", RECALL,
     "        if done.returncode != 2 or deadline - _clock() < RETRY_MIN_SECONDS:\n",
     "        if True:\n",
     _PROJECT + "test_an_older_cli_is_asked_again_without_the_project"),
    ("recall: every non-zero exit is retried", RECALL,
     "        if done.returncode != 2 or deadline - _clock() < RETRY_MIN_SECONDS:\n",
     "        if done.returncode == 0 or deadline - _clock() < RETRY_MIN_SECONDS:\n",
     _PROJECT + "test_only_exit_2_is_retried"),
    # The spec named test_the_retry_shares_one_time_budget for this one; that
    # test holds the no-retry-once-spent gate below, and stays green here.
    ("recall: the retry gets a fresh time budget", RECALL,
     "        left = CLI_TIMEOUT_SECONDS if answered_by == 0 else deadline - _clock()\n",
     "        left = CLI_TIMEOUT_SECONDS\n",
     _PROJECT + "test_the_retry_gets_only_the_time_left"),
    ("recall: an exit 2 is retried after the shared deadline is spent", RECALL,
     "        if done.returncode != 2 or deadline - _clock() < RETRY_MIN_SECONDS:\n",
     "        if done.returncode != 2:\n",
     _PROJECT + "test_the_retry_shares_one_time_budget"),
    ("recall: the retry's answer is reported as projectUsed true", RECALL,
     '        result["projectUsed"] = answered_by == 0\n',
     '        result["projectUsed"] = True\n',
     _PROJECT + "test_an_older_cli_is_asked_again_without_the_project"),
)

CONTEXT_MUTATIONS += RECALL_PROJECT_MUTATIONS

# L-0679: crew_memory.py's fail-closed rules (T-0084, L-0677, L-0678): the
# pointer grammar, vault resolution, `save`'s write order and `migrate`/`restore`.
MEMORY = os.path.join(SCRIPTS, "crew_memory.py")
_MEM = "tests/test_crew_memory.py::"
_SAVE = "tests/test_crew_memory_save.py::"
_MIG = "tests/test_crew_memory_migrate.py::"

MEMORY_MUTATIONS = (
    # A leading `/` is also an empty first segment, so with the absolute rule
    # gone the path is still refused, by the segment rule: only the reason the
    # refusal names shows the absolute rule is there.
    ("memory (a): the absolute-path rule is gone (refused only as an empty segment)", MEMORY,
     '    if path.startswith("/"):\n',
     "    if False:\n",
     _MEM + "test_an_absolute_note_path_is_refused_as_absolute"),
    ("memory (b): the note path grammar accepts a backslash", MEMORY,
     '    if "\\\\" in path or "|" in path:\n',
     '    if "|" in path:\n',
     _MEM + "test_pointer_grammar_refuses"),
    ("memory (b): the note path grammar accepts a drive prefix", MEMORY,
     '    if ":" in path:\n        return "the note path holds',
     '    if False:\n        return "the note path holds',
     _MEM + "test_pointer_grammar_refuses"),
    ("memory (c): the .. segment check is dropped", MEMORY,
     '        if segment in ("", ".", ".."):\n',
     '        if segment in ("", "."):\n',
     _MEM + "test_pointer_grammar_refuses"),
    ("memory (d): a vault: line that fails the grammar reads as full text", MEMORY,
     "    if not _attempt(lines):\n",
     '    if not _attempt(lines) or _grammar(lines)[0] == "malformed":\n',
     _MEM + "test_pointer_grammar_refuses"),
    ("memory (e): an unavailable named vault falls through to another", MEMORY,
     "    if entry is not None:\n",
     '    if entry is not None and os.path.isdir(str(entry.get("path"))):\n',
     _MEM + "test_unavailable_vault_is_not_substituted"),
    ("memory (f): an unparseable Obsidian config reads as no vaults", MEMORY,
     '    if problem:\n        return None, "no-vault-config", problem\n',
     "    if problem:\n        data, present = {}, False\n",
     _MEM + "test_unparseable_config_is_not_no_vaults"),
    ("memory (g): the symlink-component check is dropped", MEMORY,
     "        if stat.S_ISLNK(mode):\n"
     '            return None, "outside-vault", f"{note}: a symlink inside the vault',
     "        if False:\n"
     '            return None, "outside-vault", f"{note}: a symlink inside the vault',
     _MEM + "test_symlinked_component_is_outside_vault"),
    ("memory (h): save writes the pointer before the note", MEMORY,
     "    try:\n        apply_note(plan)\n",
     "    try:\n        apply_pointer(plan)\n    except (OSError, ValueError):\n        pass\n"
     "    try:\n        apply_note(plan)\n",
     _SAVE + "test_note_link_failure_leaves_native_unchanged_and_no_temp"),
    ("memory (i): save skips the read-back's resolve check before the pointer", MEMORY,
     '    if not same or state != "resolved":\n',
     "    if not same:\n",
     _SAVE + "test_read_back_failure_writes_no_pointer"),
    ("memory (i): save skips the read-back's byte comparison before the pointer", MEMORY,
     '        same = _read_bytes(plan["note_path"]) == want\n',
     "        same = True\n",
     _SAVE + "test_read_back_content_mismatch_writes_no_pointer"),
    ("memory (j): the no-hard-link create truncates a note that appeared", MEMORY,
     '    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)\n',
     '    flags = os.O_CREAT | os.O_TRUNC | os.O_WRONLY | getattr(os, "O_BINARY", 0)\n',
     _SAVE + "test_no_hard_links_and_a_note_appearing_is_refused"),
    ("memory (k): save ignores memory_id when a note exists", MEMORY,
     "    if found != memory_id:\n",
     "    if False:\n",
     _SAVE + "test_existing_note_of_another_memory_is_a_collision"),
    ("memory (l): the writer takes another vault when the primary is unavailable", MEMORY,
     "    path, _state, reason = vault_path(name, root)\n    if path is None:\n",
     "    path, _state, reason = vault_path(name, root)\n"
     "    if path is None and vaults:\n"
     "        name = next(n for n in vaults if n != name)\n"
     "        path, _state, reason = vault_path(name, root)\n"
     "    if path is None:\n",
     _SAVE + "test_primary_not_on_disk_never_falls_back_to_recall"),
    ("memory (m): save keeps the memory's CR line breaks in the note", MEMORY,
     '    body = _LINE_BREAK.sub("\\n", body).strip("\\n")\n    if not body.strip():\n',
     '    body = body.strip("\\n")\n    if not body.strip():\n',
     _SAVE + "test_outputs_are_lf_only"),
    ("memory (n): migrate --apply stops at the first failed file", MEMORY,
     "            if args.apply:\n                _migrate_apply(row, plan)\n",
     '            if args.apply and "failed" not in counts:\n                _migrate_apply(row, plan)\n',
     _MIG + "test_migrate_continues_past_a_failed_file"),
    ("memory (o): migrate converts a memory with no name: line", MEMORY,
     '    if not title:\n        return "refuse: no name: line", "no name: line in the memory"\n',
     '    if not title:\n        title = "untitled"\n',
     _MIG + "test_migrate_apply_matches_the_preview"),
    ("memory (p): restore exits 0 on a pointer that does not resolve", MEMORY,
     '    if row["state"] != "resolved":\n        return dict(row, exit=0 if row["state"] == "full-text" else 1)\n',
     '    if row["state"] != "resolved":\n        return dict(row, exit=0)\n',
     _MIG + "test_restore_refuses_what_does_not_resolve"),
)

CONTEXT_MUTATIONS += MEMORY_MUTATIONS
