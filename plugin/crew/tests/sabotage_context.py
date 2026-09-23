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
PM_BRIEF = os.path.join(SCRIPTS, "pm_brief.py")
CONTEXT_PS1 = os.path.join(SCRIPTS, "crew-context.ps1")
HANDOFF_SH = os.path.join(SCRIPTS, "handoff-read.sh")
HANDOFF_PS1 = os.path.join(SCRIPTS, "handoff-read.ps1")
_FIXES = "tests/test_crew_context_fixes.py::"
_WRAP = "tests/test_crew_context_wrappers.py::"
_INSTR = "tests/test_crew_instructions.py::"
_OFF = "  # pylint: disable=using-constant-test\n"

# The T6 review round: one per finding that changed code. The .ps1 ones need
# pwsh; on a host without it their tests SKIP (exit 0) and these read as
# STILL GREEN, which is the honest answer there -- nothing was tested.
REVIEW_FIX_CONTEXT_MUTATIONS = (
    ("pm-brief speaks although memory.inject hands SessionStart to the context hook",
     PM_BRIEF,
     "        if crew_context.inject_enabled(crew_context.find_root(root)):\n",
     "        if False:" + _OFF,
     _FIXES + "test_pm_brief_stands_down_exactly_when_memory_inject_is_true"),
    ("handoff-read.sh prints the handoff although memory.inject is true",
     HANDOFF_SH,
     "\"$DIR\" \"$PWD\" 2>/dev/null && exit 0\n",
     "\"$DIR\" \"$PWD\" 2>/dev/null && :\n",
     _FIXES + "test_handoff_read_sh_stands_down_exactly_when_memory_inject_is_true"),
    ("handoff-read.ps1 prints the handoff although memory.inject is true",
     HANDOFF_PS1,
     "if ($LASTEXITCODE -eq 0) { exit 0 }\n",
     "if ($false) { exit 0 }\n",
     _WRAP + "test_handoff_read_ps1_stands_down_exactly_when_memory_inject_is_true"),
    ("the .ps1 flavour hands python its stdin plus a newline, so both flavours emit",
     CONTEXT_PS1,
     "  $proc.StandardInput.BaseStream.Write($stdinBytes, 0, $stdinBytes.Length)\n",
     "  $proc.StandardInput.BaseStream.Write($stdinBytes + [byte[]](10), 0, $stdinBytes.Length + 1)\n",
     _WRAP + "test_both_flavours_claim_the_same_event_so_only_one_emits"),
    ("the .ps1 python probe waits on a hung candidate",
     CONTEXT_PS1,
     "      if (-not $proc.WaitForExit(3000)) {\n",
     "      if (-not $proc.WaitForExit(600000)) {\n",
     _WRAP + "test_a_hung_python_candidate_is_abandoned_not_waited_on"),
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
    ("slice-for-subagent emits vault context with memory.inject unset",
     CONTEXT,
     ("    gate as the hook, so no path emits vault context the repo did not ask for.\"\"\"\n"
      "    cfg = load_crew_config(root)\n"
      "    if dict_or_empty(cfg.get(\"memory\")).get(\"inject\") is not True:\n"),
     ("    gate as the hook, so no path emits vault context the repo did not ask for.\"\"\"\n"
      "    cfg = load_crew_config(root)\n"
      "    if dict_or_empty(cfg.get(\"memory\")).get(\"inject\") is False:\n"),
     _FIXES + "test_slice_for_subagent_emits_and_logs_nothing_unless_inject_is_true"),
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
        # The repo's vault priority is ignored in favour of the CLI's order.
        "recall ignores the repo's vault priority order",
        RECALL,
        "    snippets.sort(key=lambda s: (priority.get(s[\"vault\"], len(priority)), s[\"rank\"]))\n",
        "    snippets.sort(key=lambda s: s[\"rank\"])\n",
        ("tests/test_crew_context.py::"
         "test_snippets_follow_the_repo_vault_priority_not_the_cli_order"),
    ),
    (
        # Back to default-on: 0.20.x would inject beside pm-brief and
        # handoff-read, twice the same state per session.
        "the context hook injects with no memory.inject in the config",
        CONTEXT,
        # Anchored on the comment line above it: slice_for_subagent carries
        # the same `if` since the T6 review, so the bare line is not unique.
        ("    # cut, in the same change that unregisters those two -- not before.\n"
         "    if dict_or_empty(cfg.get(\"memory\")).get(\"inject\") is not True:\n"),
        ("    # cut, in the same change that unregisters those two -- not before.\n"
         "    if dict_or_empty(cfg.get(\"memory\")).get(\"inject\") is False:\n"),
        ("tests/test_crew_context_wrappers.py::"
         "test_bash_flavour_emits_and_logs_nothing_unless_inject_is_true"),
    ),
) + REVIEW_FIX_CONTEXT_MUTATIONS
