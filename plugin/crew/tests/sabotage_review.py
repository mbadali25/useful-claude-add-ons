"""The crew 1.0 T1 review-fix mutations, appended to `sabotage.py`'s
MUTATIONS. Kept apart only because `sabotage.py` sits at `.pylintrc`'s
max-module-lines; the runner, its restore guarantees and its reporting are
all `sabotage.py`'s. Run that file, not this one.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REVIEW_DOC = os.path.join(CREW, "commands", "review.md")
REVIEW_VERDICT = os.path.join(CREW, "hooks", "scripts", "review_verdict.py")
REVIEW_LEDGER = os.path.join(CREW, "hooks", "scripts", "review_ledger.py")
REVIEW_RUN = os.path.join(CREW, "hooks", "scripts", "review_run.py")
REVIEW_PATCH = os.path.join(CREW, "hooks", "scripts", "review_patch.py")
REVIEW_PROMPT = os.path.join(CREW, "hooks", "scripts", "review_prompt.py")
MERGED_MAIN = os.path.join(CREW, "hooks", "scripts", "merged_main.py")
REVIEW_GATE = os.path.join(CREW, "hooks", "scripts", "review_gate.py")
REVIEW_METRICS = os.path.join(CREW, "hooks", "scripts", "review_metrics.py")

REVIEW_FIX_MUTATIONS = (
    # The T1 review-fix round. Each was also run by hand against the tracked
    # file, restored from a scratch copy with `cp` and confirmed with `diff`.
    (
        # The exclude pathspec back on `git add`: exit 1 in every repo that
        # gitignores `.work/`, this one included -- no bundle can be built.
        "the bundle stages with a .work exclude pathspec again",
        REVIEW_PATCH,
        '        _run(root, ["add", "-A", "--", "."], env=env)\n',
        '        _run(root, ["add", "-A", "--", "."] + _EXCLUDE_SPEC, env=env)\n',
        ("tests/test_review_patch.py::"
         "test_gitignored_work_dir_still_builds_a_bundle"),
    ),
    (
        # The patch diff reads .work again: entries already in the copied
        # index, or committed at the base, reach the bundle and its hash.
        "the bundle diff no longer excludes .work",
        REVIEW_PATCH,
        '        patch = _run_raw(root, ["diff"] + _DIFF_FLAGS + [tree, working_tree] + only)\n',
        '        patch = _run_raw(root, ["diff"] + _DIFF_FLAGS + [tree, working_tree])\n',
        ("tests/test_review_patch.py::"
         "test_work_entries_already_in_the_index_stay_out_of_the_bundle"),
    ),
    # T-0092 (crew 1.0.54): generated graphify-out/ leaves the bundle. Each
    # was run by hand against the tracked file, restored with `git checkout`.
    (
        # The diffs read graphify-out/ again: a reviewer is handed ~120 parts
        # of generated JSON and the Claude fallback comes back INCOMPLETE.
        "the bundle diff no longer excludes graphify-out",
        REVIEW_PATCH,
        '_EXCLUDE_SPEC = [":(exclude).work", ":(exclude)graphify-out", '
        '":(exclude).crew/metrics.md"]\n',
        '_EXCLUDE_SPEC = [":(exclude).work", ":(exclude).crew/metrics.md"]\n',
        ("tests/test_review_patch.py::"
         "test_generated_graph_dir_is_excluded_and_says_so"),
    ),
    (
        # The manifest stops naming graphify-out/: a reviewer reads a bundle
        # with the graph left out and nothing records that it was.
        "the manifest stops saying graphify-out is excluded",
        REVIEW_PATCH,
        'EXCLUDED = (".work/", "graphify-out/", ".crew/metrics.md")\n',
        'EXCLUDED = (".work/", ".crew/metrics.md")\n',
        ("tests/test_review_patch.py::"
         "test_generated_graph_dir_is_excluded_and_says_so"),
    ),
    (
        # The prompt stops naming the excluded paths: a reviewer can report
        # CLEAN on a bundle without knowing anything was left out of it.
        "the review prompt stops naming the excluded paths",
        REVIEW_PROMPT,
        ('    if isinstance(excluded, list) and all(isinstance(p, str) and p.strip() for p in excluded):\n'
         '        out.append("  excluded (never in the bundle): "\n'
         '                   + (", ".join(excluded) if excluded else "none"))\n'
         '    else:\n'
         '        out.append("  excluded: not recorded by this manifest (unknown)")\n'),
        "    pass\n",
        ("tests/test_review_prompt.py::"
         "test_build_names_the_excluded_paths"),
    ),
    (
        # T-0099: an empty exclusion list collapses into the unknown line, so a
        # manifest that says "nothing was left out" reads as one that cannot say.
        "an empty exclusion list prints as unknown",
        REVIEW_PROMPT,
        "    if isinstance(excluded, list) and all(isinstance(p, str) and p.strip() for p in excluded):\n",
        "    if excluded and isinstance(excluded, list) and all(isinstance(p, str) and p.strip() for p in excluded):\n",
        ("tests/test_review_prompt.py::"
         "test_an_empty_exclusion_list_is_not_reported_as_unknown"),
    ),
    (
        # T-0099 rounds 1-2: a blank entry passes as a path, so `[""]` or
        # `[" "]` prints a blank known list instead of the unknown line.
        "a blank exclusion entry reads as a known list",
        REVIEW_PROMPT,
        "    if isinstance(excluded, list) and all(isinstance(p, str) and p.strip() for p in excluded):\n",
        "    if isinstance(excluded, list) and all(isinstance(p, str) for p in excluded):\n",
        ("tests/test_review_prompt.py::"
         "test_a_malformed_exclusion_value_reads_as_unknown"),
    ),
    (
        # An older round's result lands after a later round was reserved.
        "the ledger records a result for a round that is not the latest",
        REVIEW_LEDGER,
        "        if row is not rounds[-1]:\n",
        "        if False:\n",
        ("tests/test_review_ledger.py::"
         "test_record_an_older_round_while_a_later_one_is_reserved_is_refused"),
    ),
    (
        # A result moves the ledger off NEEDS_REPLAN.
        "the ledger lets a result change NEEDS_REPLAN",
        REVIEW_LEDGER,
        "        if data.get(\"state\") == NEEDS_REPLAN:\n"
        "            raise LedgerError(f\"{ticket} is {NEEDS_REPLAN}; no review result",
        "        if False:\n"
        "            raise LedgerError(f\"{ticket} is {NEEDS_REPLAN}; no review result",
        ("tests/test_review_ledger.py::"
         "test_record_after_needs_replan_is_refused_even_for_the_latest_round"),
    ),
    (
        # A Claude result completes a Codex reservation.
        "the ledger records a result from an unreserved reviewer",
        REVIEW_LEDGER,
        "        if recording != reserved_for:\n",
        "        if False:\n",
        ("tests/test_review_ledger.py::"
         "test_claude_result_cannot_complete_a_codex_reservation"),
    ),
    (
        # Parts are never checked: an emptied part still reads CLEAN and the
        # receipt binds the untouched tree hash.
        "the review round no longer checks the bundle parts",
        REVIEW_RUN,
        "    extra_reasons = list(extra_reasons) + bundle_problems(manifest)\n",
        "    extra_reasons = list(extra_reasons)\n",
        ("tests/test_review_receipt.py::"
         "test_truncated_bundle_parts_are_incomplete_and_mint_no_receipt"),
    ),
    (
        # Unreadable Codex event lines are skipped again.
        "an unparseable Codex event line is ignored",
        REVIEW_VERDICT,
        "            if error is None:\n"
        "                error = f\"unparseable Codex event line",
        "            if False:\n"
        "                error = f\"unparseable Codex event line",
        ("tests/test_review_verdict.py::"
         "test_codex_final_message_an_unparseable_event_line_is_an_error"),
    ),
    (
        # The pre-fix finding regex: empty fields read as a finding.
        "a finding with empty fields is FINDINGS again",
        REVIEW_VERDICT,
        "_FINDING = re.compile(rf\"^(BLOCK|FIX|NIT)\\|{_FIELD}\\|{_FIELD}\\|.*\\S.*$\")\n",
        "_FINDING = re.compile(r\"^(BLOCK|FIX|NIT)\\|[^|]+\\|.+$\")\n",
        ("tests/test_review_verdict.py::"
         "test_parse_a_finding_with_an_empty_or_missing_field_is_incomplete"),
    ),
    (
        # Code fences tolerated again.
        "a code fence in reviewer output is skipped",
        REVIEW_VERDICT,
        "        if not line:\n            continue\n        if line == CLEAN:\n",
        "        if not line or line.startswith(\"```\"):\n            continue\n"
        "        if line == CLEAN:\n",
        ("tests/test_review_verdict.py::"
         "test_parse_a_code_fence_is_incomplete"),
    ),
    (
        # The bundle base back to the default-branch merge-base.
        "review.md bundles from the merge-base instead of the ticket start",
        REVIEW_DOC,
        "BASE=$(python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/scope_base.py --root . "
        "--base \"$TICKET\"); SB_RC=$?\n",
        "BASE=$(git merge-base HEAD main); SB_RC=$?\n",
        ("tests/test_review_base.py::"
         "test_review_base_comes_from_scope_base_first"),
    ),
    (
        # Codex round-2 BLOCK, the whole pre-fix acceptance restored: the
        # latest COMPLETED round is accepted, whatever the state.
        "--accept takes an older round and leaves NEEDS_REPLAN",
        REVIEW_LEDGER,
        "        if data.get(\"state\") == NEEDS_REPLAN:\n"
        "            raise LedgerError(f\"{ticket} is {NEEDS_REPLAN}; no acceptance changes that \"\n"
        "                              \"state, only an approved successor plan continues\")\n"
        "        rounds = data.get(\"rounds\", [])\n"
        "        if not rounds:\n"
        "            raise LedgerError(\"no review round to accept\")\n"
        "        row = rounds[-1]\n"
        "        if row.get(\"status\") != \"completed\":\n",
        "        rounds = [r for r in data.get(\"rounds\", []) if r.get(\"status\") == "
        "\"completed\"]\n"
        "        row = rounds[-1]\n"
        "        if False:\n",
        ("tests/test_review_receipt.py::"
         "test_accept_an_older_round_after_needs_replan_is_refused"),
    ),
    (
        # Only the NEEDS_REPLAN refusal gone: round 2's FINDINGS is the most
        # recent completed round, so nothing else stops it.
        "--accept ignores NEEDS_REPLAN",
        REVIEW_LEDGER,
        "        if data.get(\"state\") == NEEDS_REPLAN:\n"
        "            raise LedgerError(f\"{ticket} is {NEEDS_REPLAN}; no acceptance",
        "        if False:\n"
        "            raise LedgerError(f\"{ticket} is {NEEDS_REPLAN}; no acceptance",
        ("tests/test_review_receipt.py::"
         "test_accept_the_latest_findings_round_once_it_is_needs_replan_is_refused"),
    ),
    (
        # Only the most-recent rule gone: round 1 accepted under a reserved
        # round 2, with the state still IN_REVIEW.
        "--accept takes the latest completed round, not the latest round",
        REVIEW_LEDGER,
        "        row = rounds[-1]\n        if row.get(\"status\") != \"completed\":\n",
        "        row = [r for r in rounds if r.get(\"status\") == \"completed\"][-1]\n"
        "        if False:\n",
        ("tests/test_review_receipt.py::"
         "test_accept_an_older_round_while_a_later_one_is_reserved_is_refused"),
    ),
    (
        # Codex round-2 BLOCK, the pre-fix result restored: a manifest with
        # no parts reports no problems. (Disabling the guard alone stays
        # green -- the whole-bundle hash then catches it -- so the mutation
        # returns the empty list the pre-fix loop did.)
        "a manifest with no parts is checked by nothing",
        REVIEW_RUN,
        "        return [\"the manifest lists no bundle parts",
        "        return [] and [\"the manifest lists no bundle parts",
        ("tests/test_review_receipt.py::"
         "test_empty_parts_manifest_is_incomplete_and_mints_no_receipt"),
    ),
    (
        # A dropped part with bundle_sha256 rewritten to match what is left.
        "the part byte total is not compared with patch_bytes",
        REVIEW_RUN,
        "    if not problems and total != manifest.get(\"patch_bytes\"):\n",
        "    if False:\n",
        ("tests/test_review_receipt.py::"
         "test_dropped_part_with_a_rewritten_bundle_hash_is_incomplete"),
    ),
    (
        # 0.20.18: the 1a16af5f rule back -- round 2's FINDINGS set
        # NEEDS_REPLAN on record, so the owner can never accept them.
        "round-2 FINDINGS set NEEDS_REPLAN again",
        REVIEW_LEDGER,
        "        else:\n            data[\"state\"] = REVIEWED\n",
        "        elif number >= BUDGET:\n            data[\"state\"] = NEEDS_REPLAN\n"
        "        else:\n            data[\"state\"] = REVIEWED\n",
        ("tests/test_review_receipt.py::"
         "test_accept_round_two_findings_writes_a_receipt"),
    ),
    (
        # --accept a second time on the same round rewrites who and when.
        "--accept takes the same round twice",
        REVIEW_LEDGER,
        "        if receipt.get(\"round\") == row[\"round\"]:\n",
        "        if False:\n",
        ("tests/test_review_receipt.py::"
         "test_accept_the_same_round_twice_is_refused"),
    ),
    (
        # --reject moves an ACCEPTED or NEEDS_REPLAN ticket.
        "--reject changes an ACCEPTED or NEEDS_REPLAN ticket",
        REVIEW_LEDGER,
        "        if data.get(\"state\") in (NEEDS_REPLAN, ACCEPTED):\n",
        "        if False:\n",
        ("tests/test_review_receipt.py::"
         "test_reject_is_refused_and_changes_nothing"),
    ),
    (
        # T2 fix round: every refused reservation after NEEDS_REPLAN writes
        # another `refused` entry again.
        "a reservation after NEEDS_REPLAN writes the ledger",
        REVIEW_LEDGER,
        "        if data.get(\"state\") == NEEDS_REPLAN:\n            return None, exhausted\n",
        "",
        ("tests/test_review_ledger.py::"
         "test_reserve_after_needs_replan_is_refused_without_writing"),
    ),
    (
        # An older round's receipt outlives a later round's verdict.
        "--check-receipt ignores rounds after the receipt's",
        REVIEW_LEDGER,
        "    if not isinstance(latest, dict) or latest.get(\"round\") != receipt.get(\"round\"):\n",
        "    if False:\n",
        ("tests/test_review_receipt.py::"
         "test_check_receipt_fails_when_a_later_round_exists"),
    ),
    (
        # A receipt stands on a NEEDS_REPLAN ticket.
        "--check-receipt ignores NEEDS_REPLAN",
        REVIEW_LEDGER,
        "        return False, f\"{ticket} is {NEEDS_REPLAN}; no receipt stands\"\n",
        "        pass\n",
        ("tests/test_review_receipt.py::"
         "test_check_receipt_fails_once_needs_replan_even_on_the_latest_clean_round"),
    ),
    (
        # The latest round's verdict is not read (L-0510: through receipt_stands).
        "--check-receipt does not read the latest round's verdict",
        REVIEW_LEDGER,
        "    if not receipt_stands(receipt, latest, root, ticket):\n",
        "    if False:\n",
        ("tests/test_review_receipt.py::"
         "test_check_receipt_fails_when_the_latest_round_is_not_clean_or_accepted"),
    ),
    (
        # `launch`'s timeout-cleanup killpgs an already-exited leader again:
        # the `proc.poll() is None` gate removed, so the bare-pid signal
        # fires whether or not that pid could have been recycled.
        "review_run.launch killpgs an already-exited leader again",
        REVIEW_RUN,
        "        escaped = False\n"
        "        if proc.poll() is None:\n",
        "        escaped = False\n"
        "        if True:\n",
        ("tests/test_review_run_launch.py::"
         "test_killpg_is_skipped_once_the_leader_has_already_exited"),
    ),
    (
        # The follow-up `communicate()` after a kill loses its bound again:
        # a descendant that escaped the kill can block it indefinitely.
        "review_run.launch's post-kill communicate() loses its timeout bound",
        REVIEW_RUN,
        "            stdout, stderr = proc.communicate(timeout=POST_KILL_TIMEOUT)\n",
        "            stdout, stderr = proc.communicate()\n",
        ("tests/test_review_run_launch.py::"
         "test_post_kill_communicate_is_bounded_and_keeps_the_partial_output"),
    ),
    (
        # 1.0.21: the discard-and-close-the-pipes shape this ticket removed,
        # restored -- a second TimeoutExpired throws away whatever partial
        # output CPython's own exception already carried instead of decoding
        # and keeping it.
        "review_run.launch discards partial output on a second timeout again",
        REVIEW_RUN,
        "        except subprocess.TimeoutExpired as exc:\n"
        "            escaped = True\n"
        "            stdout = _decode_partial(exc.output)\n"
        "            stderr = _decode_partial(exc.stderr)\n",
        "        except subprocess.TimeoutExpired:\n"
        "            escaped = True\n"
        "            stdout, stderr = \"\", \"\"\n",
        ("tests/test_review_run_launch.py::"
         "test_post_kill_communicate_is_bounded_and_keeps_the_partial_output"),
    ),
    # T-0079: a READ line counts for a part when it is the part's path as
    # listed, or its bare file name -- and for nothing else. Each rule below
    # has its own proof.
    (
        # Exact comparison against the listed path gone: only bare names count,
        # so a reviewer echoing the listed path is INCOMPLETE (T-0009 round 4).
        "the READ parser compares bare names only again",
        REVIEW_VERDICT,
        "    if token == listed:\n        return True\n",
        "    if False:\n        return True\n",
        ("tests/test_review_verdict.py::"
         "test_parse_a_full_path_read_counts_for_its_listed_part"),
    ),
    (
        # A file name alone is not an identity: part-002 of another bundle
        # would cover this bundle's part-002.
        "any READ token is reduced to its basename",
        REVIEW_VERDICT,
        "    return \"/\" not in token and token == posixpath.basename(listed)\n",
        "    return posixpath.basename(token) == posixpath.basename(listed)\n",
        ("tests/test_review_verdict.py::"
         "test_parse_a_same_basename_in_another_directory_counts_for_nothing"),
    ),
    (
        # The loosest rule: any READ line at all covers every part, so a path
        # outside the bundle stands in for a part nobody claimed to read.
        "any READ line counts for any part",
        REVIEW_VERDICT,
        "    return \"/\" not in token and token == posixpath.basename(listed)\n",
        "    return True\n",
        ("tests/test_review_verdict.py::"
         "test_parse_a_read_of_a_path_outside_the_bundle_counts_for_nothing"),
    ),
    (
        # A Windows reviewer writing C:/... for a listed C:\... is INCOMPLETE.
        "READ paths are no longer separator-normalised",
        REVIEW_VERDICT,
        "    return posixpath.normpath(path.strip().replace(\"\\\\\", \"/\"))\n",
        "    return posixpath.normpath(path.strip())\n",
        ("tests/test_review_verdict.py::"
         "test_parse_a_differently_spelled_listed_path_counts"),
    ),
    (
        # A listed path under a directory with a space cannot be acknowledged.
        "a READ path containing a space is unparseable again",
        REVIEW_VERDICT,
        "_READ = re.compile(r\"^READ\\|(.*\\S.*)$\")\n",
        "_READ = re.compile(r\"^READ\\|(\\S+)$\")\n",
        ("tests/test_review_verdict.py::"
         "test_parse_a_listed_path_with_a_space_counts"),
    ),
    (
        # The parser handed bare names while the prompt lists full paths.
        "review_run expects bare part names again",
        REVIEW_RUN,
        "    parts = [p.get(\"path\") or p[\"name\"] for p in manifest.get(\"parts\") or []]\n",
        "    parts = [p[\"name\"] for p in manifest.get(\"parts\") or []]\n",
        ("tests/test_webtest_guard.py::"
         "test_review_reads_written_as_the_listed_paths_are_clean"),
    ),
    (
        # The overflow file's READ must match the full path the prompt printed.
        "review_run expects the webtest overflow file by bare name again",
        REVIEW_RUN,
        "        parts.append(os.path.join(args.scratch, review_prompt.WEBTEST_FINDINGS_FILE))\n",
        "        parts.append(review_prompt.WEBTEST_FINDINGS_FILE)\n",
        ("tests/test_webtest_guard.py::"
         "test_review_the_overflow_file_needs_its_own_read"),
    ),
    (
        # The prompt asking for a form the parser does not state is the defect.
        "the bundle prompt asks for READ|<its file name> again",
        REVIEW_PROMPT,
        "           f\"{review_verdict.READ_FORM} on its own line. A READ line for a path in any\",\n",
        "           \"READ|<its file name> on its own line. A READ line for a path in any\",\n",
        ("tests/test_review_prompt.py::"
         "test_build_states_the_read_form_the_parser_accepts"),
    ),
    (
        # The webtest overflow line asking for the bare name again. The bundle
        # block states READ_FORM too, so the test reads the overflow line alone.
        "the webtest overflow line asks for a bare READ name again",
        REVIEW_PROMPT,
        "                   f\"and output {review_verdict.READ_FORM} for that file on its own line. \"\n",
        "                   f\"and output READ|{WEBTEST_FINDINGS_FILE} on its own line. \"\n",
        ("tests/test_webtest_guard.py::"
         "test_review_prompt_hands_over_every_row_through_a_file_past_the_inline_limit"),
    ),
    (
        # splitlines() also breaks at U+2028 and the C0 separators, cutting a
        # verdict line in two (T-0079 amendment).
        "the verdict parser splits reviewer output with splitlines again",
        REVIEW_VERDICT,
        '    for raw in (text or "").split("\\n"):\n',
        '    for raw in (text or "").splitlines():\n',
        ("tests/test_review_verdict.py::"
         "test_parse_a_verdict_line_holding_a_unicode_line_break_is_one_line"),
    ),
    (
        # A raw U+2028 inside a Codex event's JSON cut it mid-object and scored
        # T-0072 round 4 INCOMPLETE.
        "the Codex event reader splits with splitlines again",
        REVIEW_VERDICT,
        '    for line in (jsonl or "").split("\\n"):\n',
        '    for line in (jsonl or "").splitlines():\n',
        ("tests/test_review_verdict.py::"
         "test_codex_final_message_an_event_holding_a_unicode_line_break_parses_intact"),
    ),
    # T-0100: paths identical to merged main leave the bundle, and the reviewer
    # and the receipt check are told. Each run by hand against the tracked
    # file, restored with `git checkout`.
    (
        "the bundle diffs from the ticket start instead of the synthetic base",
        REVIEW_PATCH,
        '        patch = _run_raw(root, ["diff"] + _DIFF_FLAGS + [tree, working_tree] + only)\n',
        '        patch = _run_raw(root, ["diff"] + _DIFF_FLAGS + [base_sha, working_tree] + only)\n',
        "tests/test_review_patch.py::test_merged_main_paths_leave_the_bundle",
    ),
    (
        "the manifest entries read the ticket start instead of the synthetic base",
        REVIEW_PATCH,
        "        entries = _entries(root, tree, working_tree)\n",
        "        entries = _entries(root, base_sha, working_tree)\n",
        "tests/test_review_patch.py::test_merged_main_paths_leave_the_bundle",
    ),
    (
        "the reviewer is not told what merged main left out",
        REVIEW_PROMPT,
        '    out.append(_merged_main_line(manifest.get("merged_main")))\n',
        "",
        "tests/test_review_prompt.py::test_build_names_the_merged_main_line[could-not-tell]",
    ),
    (
        "a stale receipt hides a could-not-tell merge of main",
        REVIEW_LEDGER,
        '                       f"{_merged_note(merged, stale=True)}")\n',
        '                       "")\n',
        "tests/test_review_receipt.py::test_check_receipt_stale_message_says_could_not_tell",
    ),
    # T-0100 review round 1: every merged-main bundle and receipt check gets a
    # mutation. Each run by hand in the foreground against the tracked file,
    # restored with `git checkout --`; output in .work/tickets/T-0100/sabotage-r1.txt.
    (
        "a path main also changed is diffed from the start",
        REVIEW_PATCH,
        '    against = sorted((by_main[p] for p in kept if p in by_main), key=lambda e: e["path"])\n',
        "    against = []\n",
        "tests/test_review_patch.py::test_a_ticket_edit_on_top_of_merged_mains_edit_stays_in_the_bundle",
    ),
    (
        "main's changes are read from the start instead of the fork",
        REVIEW_PATCH,
        '                _parse_raw(_run_raw(root, raw + [fork, merged["commit"]] + only))}\n',
        '                _parse_raw(_run_raw(root, raw + [base_sha, merged["commit"]] + only))}\n',
        "tests/test_review_patch.py::"
        "test_a_start_after_the_fork_diffs_only_mains_paths_from_the_merged_commit",
    ),
    (
        "the reviewer is not told which paths are diffed from merged main",
        REVIEW_PROMPT,
        '                   f"lines there are context: {\', \'.join(against)}" if against else "")\n',
        '                   f"lines there are context: {\', \'.join(against)}" if False else "")\n',
        "tests/test_review_prompt.py::test_build_names_the_merged_main_line"
        "[applies-diffed-from-merged]",
    ),
    (
        "a detached HEAD bundles as though a merge applied",
        MERGED_MAIN,
        '    if not branch:\n        return {"ref": ref, "commit": None,',
        '    if False:\n        return {"ref": ref, "commit": None,',
        "tests/test_review_patch.py::test_could_not_tell_bundles_everything_and_says_so",
    ),
    (
        "the summary line reads could-not-tell as none",
        REVIEW_PATCH,
        '    return " merged-main=could-not-tell" if merged["commit"] is None else " merged-main=none"\n',
        '    return " merged-main=none"\n',
        "tests/test_review_patch.py::test_could_not_tell_bundles_everything_and_says_so",
    ),
    (
        "nothing-to-review after a merge says the base matches",
        REVIEW_PATCH,
        '    if code == EXIT_NOTHING_TO_REVIEW and merged["dropped"]:\n',
        "    if False:\n",
        "tests/test_review_patch.py::test_everything_merged_and_nothing_else_is_nothing_to_review",
    ),
    (
        "the bundle never leaves out what merged main already holds",
        REVIEW_PATCH,
        '    if not merged["applies"]:\n        return base_tree, merged, [], []\n',
        '    if True:\n        return base_tree, merged, [], []\n',
        "tests/test_review_receipt.py::"
        "test_check_receipt_survives_a_merge_of_main_that_touches_no_reviewed_path",
    ),
    (
        "a stale receipt does not name the merged commit",
        REVIEW_LEDGER,
        '        return (f"; merged main: {merged[\'commit\'][:12]} ({count} path(s) identical to it "\n'
        '                f"left out){fork}")\n',
        '        return ""\n',
        "tests/test_review_receipt.py::"
        "test_check_receipt_is_stale_when_a_merge_of_main_changes_a_reviewed_path",
    ),
    # T-0100 successor (review round 2): a failed fork lookup is could-not-tell in
    # every line derived from it -- manifest, stderr, prompt, receipt note.
    (
        "a failed fork lookup leaves no fork_reason in the manifest",
        REVIEW_PATCH,
        '    if not fork:\n        # The more-inclusive bundle stays',
        '    if False:\n        # The more-inclusive bundle stays',
        "tests/test_review_patch.py::test_a_failed_fork_lookup_is_could_not_tell",
    ),
    (
        "review-patch's stderr prints a count when the fork lookup failed",
        REVIEW_PATCH,
        '        against = ("could-not-tell" if merged.get("fork", "") is None\n',
        '        against = ("could-not-tell" if False\n',
        "tests/test_review_patch.py::test_a_failed_fork_lookup_is_could_not_tell",
    ),
    (
        "the reviewer is not told the fork lookup failed",
        REVIEW_PROMPT,
        '                + _fork_clause(merged))\n',
        '                + "")\n',
        "tests/test_review_prompt.py::test_build_names_the_merged_main_line"
        "[applies-fork-could-not-tell]",
    ),
    (
        "the receipt note is silent on a failed fork lookup",
        REVIEW_LEDGER,
        '    fork = "; fork: could not tell" if merged.get("fork", "") is None else ""\n',
        '    fork = ""\n',
        "tests/test_review_receipt.py::"
        "test_check_receipt_says_could_not_tell_when_the_fork_lookup_fails",
    ),
    # crew 1.0.65: gate first, and no second round on an unchanged CLEAN
    # bundle. Each was run by hand against the tracked file and confirmed RED.
    (
        # The preflight is skipped: a round is spent on a tree the gate has
        # not passed, which is the whole cost this exists to avoid.
        "review_run reserves a round without asking the gate",
        REVIEW_RUN,
        "    short = preflight(args)\n    if short is not None:\n        return short\n",
        "    short = None\n",
        ("tests/test_review_gate.py::"
         "test_an_unverified_tree_is_refused_with_exit_5_and_no_round_spent"),
    ),
    (
        # "Could not tell" reviews as though it were "passed".
        "an UNKNOWN gate state is let through to a review",
        REVIEW_RUN,
        "    if state in (review_gate.UNVERIFIED, review_gate.UNKNOWN):\n        if args.allow_unverified:\n",
        "    if state in (review_gate.UNVERIFIED,):\n        if args.allow_unverified:\n",
        ("tests/test_review_gate.py::"
         "test_an_unknown_gate_state_is_refused_like_an_unverified_one"),
    ),
    (
        # An unreadable repository collapses into VERIFIED.
        "gate_state reads an unreadable repository as VERIFIED",
        REVIEW_GATE,
        "        return UNKNOWN, str(exc)\n",
        "        return VERIFIED, str(exc)\n",
        "tests/test_review_gate.py::test_git_failing_is_unknown_not_verified",
    ),
    (
        # The digest is never compared: any edit after a pass still reads
        # as verified.
        "gate_state stops comparing the fingerprint",
        REVIEW_GATE,
        "    if current != recorded:\n",
        "    if False:\n",
        "tests/test_review_gate.py::test_any_change_after_the_pass_is_unverified[content]",
    ),
    (
        # A new untracked file is invisible to the changed set, so it is
        # neither hashed nor noticed.
        "gate_state's changed set drops untracked files",
        REVIEW_GATE,
        ('    text = _git(root, "diff", "--name-only", "HEAD") + "\\n" + \\\n'
         '        _git(root, "ls-files", "--others", "--exclude-standard")\n'),
        '    text = _git(root, "diff", "--name-only", "HEAD")\n',
        "tests/test_review_gate.py::test_any_change_after_the_pass_is_unverified[new-untracked]",
    ),
    (
        # Commits after the last pass are waved through.
        "gate_state stops checking the marker against HEAD",
        REVIEW_GATE,
        "        if marker != head:\n",
        "        if False:\n",
        "tests/test_review_gate.py::test_a_marker_behind_head_is_unverified",
    ),
    (
        # Must-allow: the gate's own marker counts as a change, so a clean
        # tree the gate just passed is refused forever.
        "gate_state counts the gate's own markers as material",
        REVIEW_GATE,
        "        if not verify_fingerprint._material(changed):  # pylint: disable=protected-access\n",
        "        if not changed:\n",
        "tests/test_review_gate.py::test_after_the_real_gate_passes_the_tree_is_verified[clean-tree]",
    ),
    (
        # A person's acceptance of one round's FINDINGS stands in for a
        # clean review of the tree.
        "an owner-accepted receipt short-circuits a review",
        REVIEW_RUN,
        '    if ok and (data.get("receipt") or {}).get("kind") == "clean":\n',
        "    if ok:\n",
        "tests/test_review_gate.py::test_owner_accepted_findings_do_not_short_circuit",
    ),
    # L-0510: the auto-accept guard. Each was run by hand against the tracked
    # file, seen red, and restored with `git checkout --`.
    (
        # A final round with a BLOCK is auto-accepted.
        "auto-accept stops refusing a BLOCK count",
        REVIEW_LEDGER,
        '    if counts["BLOCK"] != 0:\n',
        "    if False:\n",
        "tests/test_review_auto_accept.py::test_auto_accept_refuses[block-1-count-only]",
    ),
    (
        # An INCOMPLETE round -- the reviewer never finished reading -- is
        # auto-accepted.
        "auto-accept stops refusing a non-FINDINGS verdict",
        REVIEW_LEDGER,
        '    if row.get("verdict") != "FINDINGS":\n        failure = ',
        "    if False:\n        failure = ",
        "tests/test_review_auto_accept.py::test_auto_accept_refuses[incomplete-reviewer]",
    ),
    (
        # Round 1 of 2 is auto-accepted: the lane never fixes and reruns.
        "auto-accept stops requiring the final round",
        REVIEW_LEDGER,
        "    if _charged(data) < BUDGET:\n",
        "    if False:\n",
        "tests/test_review_auto_accept.py::test_auto_accept_refuses[round-1-of-2]",
    ),
    (
        # An open healer skip is auto-accepted.
        "auto-accept stops reading the webtest state",
        REVIEW_LEDGER,
        "    if not ((type(webtest) is int and webtest == 0) or webtest == WEBTEST_NA):",
        "    if False:",
        "tests/test_review_auto_accept.py::test_auto_accept_refuses[webtest-open-1]",
    ),
    (
        # A membership test: `False in (0, WEBTEST_NA)` is true, so a webtest
        # state of `false` passes as 0.
        "auto-accept's webtest check lets a bool through",
        REVIEW_LEDGER,
        "    if not ((type(webtest) is int and webtest == 0) or webtest == WEBTEST_NA):",
        "    if webtest not in (0, WEBTEST_NA):",
        "tests/test_review_auto_accept.py::test_auto_accept_refuses[webtest-open-false]",
    ),
    (
        # Finding lines that disagree with the counts are taken as read.
        "auto-accept stops checking lines against counts",
        REVIEW_LEDGER,
        ('    if not findings or (fixes, len(findings) - fixes) != (counts["FIX"], '
         'counts["NIT"]):\n'),
        "    if False:\n",
        "tests/test_review_auto_accept.py::test_auto_accept_refuses[findings-disagree]",
    ),
    # L-0510 fix round. Each was run by hand against the tracked file, seen
    # red, and restored with `git checkout --`.
    (
        # Only the total is compared: one NIT line under counts FIX=1, NIT=0
        # is auto-accepted.
        "auto-accept compares only the total of FIX and NIT lines",
        REVIEW_LEDGER,
        ('    if not findings or (fixes, len(findings) - fixes) != (counts["FIX"], '
         'counts["NIT"]):\n'),
        '    if not findings or len(findings) != counts["FIX"] + counts["NIT"]:\n',
        "tests/test_review_auto_accept.py::test_auto_accept_refuses[findings-fix-count-nit-line]",
    ),
    (
        # A line that is neither FIX| nor NIT| is taken as a finding.
        "auto-accept stops refusing a line of no known severity",
        REVIEW_LEDGER,
        "    if other:\n",
        "    if False:\n",
        "tests/test_review_auto_accept.py::test_auto_accept_refuses[findings-unknown-severity]",
    ),
    (
        # A receipt of an unknown kind reads as "not applicable".
        "--check-follow-up passes a receipt of an unknown kind",
        REVIEW_LEDGER,
        '        return False, (f"the receipt\'s kind is',
        '        return True, (f"the receipt\'s kind is',
        ("tests/test_review_auto_accept.py::"
         "test_check_follow_up_unknown_kind_is_could_not_tell[garbage]"),
    ),
    (
        # A CLEAN round stands under a receipt of any kind.
        "receipt_stands stops reading a CLEAN receipt's kind",
        REVIEW_LEDGER,
        '        return receipt.get("kind") == "clean"\n',
        "        return True\n",
        ("tests/test_review_auto_accept.py::"
         "test_check_receipt_refuses_a_clean_round_with_an_unknown_kind"),
    ),
    (
        # A follow-up that is not UTF-8 crashes with a traceback.
        "--check-follow-up stops catching a decode error",
        REVIEW_LEDGER,
        "    except UnicodeDecodeError as exc:\n",
        "    except KeyError as exc:\n",
        "tests/test_review_auto_accept.py::test_check_follow_up_refuses_by_name[not-utf8]",
    ),
    (
        # The follow-up's lines are stripped: an indented copy passes.
        "--check-follow-up strips the follow-up's lines",
        REVIEW_LEDGER,
        '                line[:-1] if line.endswith("\\r") else line for line in fh.read().split("\\n"))\n',
        '                line.strip() for line in fh.read().split("\\n"))\n',
        "tests/test_review_auto_accept.py::test_check_follow_up_refuses_by_name[indented-line]",
    ),
    (
        # A line the receipt carries twice is satisfied by one copy.
        "--check-follow-up stops counting duplicate lines",
        REVIEW_LEDGER,
        "    missing = list((collections.Counter(lines) - have).elements())\n",
        "    missing = [line for line in lines if line not in have]\n",
        "tests/test_review_auto_accept.py::test_check_follow_up_counts_duplicate_lines[one-copy]",
    ),
    (
        # The owner path forges the auto receipt's string.
        "--accept stops reserving the auto: prefix",
        REVIEW_LEDGER,
        "    if _is_auto_name(by):\n",
        "    if False:\n",
        "tests/test_review_auto_accept.py::test_owner_accept_refuses_the_auto_prefix",
    ),
    (
        # An auto receipt keeps standing after its row is edited to a BLOCK.
        "receipt_stands stops re-checking the auto row",
        REVIEW_LEDGER,
        "            and _auto_row_problem(latest) is None\n",
        "            and True\n",
        "tests/test_review_auto_accept.py::test_check_receipt_requires_the_auto_rows_guard[row-block-1]",
    ),
    (
        # The lines the follow-up must quote are never recorded.
        "finish stops recording the finding lines",
        REVIEW_RUN,
        '        "findings": result["findings"], "webtest_open"',
        '        "webtest_open"',
        "tests/test_review_auto_accept.py::test_finish_records_findings_and_webtest_state",
    ),
    # L-0510, owner decision 2026-10-01 #3: the family rule. Run by hand
    # against the tracked file, seen red, restored with `git checkout --`.
    (
        # The family check is removed: a Claude-fallback (same-family) round
        # auto-accepts.
        "auto-accept stops checking the reviewer's family",
        REVIEW_LEDGER,
        "    problem = _family_problem(row)\n    if problem:\n        return problem\n",
        "",
        "tests/test_review_auto_accept.py::test_auto_accept_refuses[same-family-claude]",
    ),
    (
        # Review round 3 FIX 2: the receipt's provider and family are never
        # compared with the row's, so a receipt naming claude still stands.
        "auto receipt stops naming the row's reviewer",
        REVIEW_LEDGER,
        "            and _receipt_names_the_reviewer(receipt, latest)\n",
        "",
        "tests/test_review_auto_accept.py::test_check_receipt_requires_the_auto_rows_guard"
        "[receipt-family-claude]",
    ),
    # Review round 4 (owner decision 2026-10-01 #5). Each run by hand against
    # the tracked file, seen red, restored with `git checkout --`.
    (
        # A FIX prefix hides a BLOCK-form line after an embedded newline.
        "auto-accept stops refusing a finding with a line break",
        REVIEW_LEDGER,
        "    if broken:\n",
        "    if False:  # pylint: disable=using-constant-test\n",
        "tests/test_review_auto_accept.py::test_auto_accept_refuses[finding-embedded-newline]",
    ),
    (
        # splitlines() back: U+2028 inside a quoted finding splits the line.
        "the follow-up check splits on U+2028 again",
        REVIEW_LEDGER,
        '                line[:-1] if line.endswith("\\r") else line for line in fh.read().split("\\n"))\n',
        '                line[:-1] if line.endswith("\\r") else line for line in fh.read().splitlines())\n',
        "tests/test_review_auto_accept.py::test_check_follow_up_keeps_a_u2028_finding_on_one_line",
    ),
    # Owner decision 2026-10-01 #6: recovered verdicts never auto-accept. Run
    # by hand against the tracked file, seen red, restored.
    (
        # A row recorded before L-0576 reads as 0 stray lines, so an unread
        # count passes as "not recovered".
        "auto-accept defaults a missing ignored_lines to 0",
        REVIEW_LEDGER,
        '    ignored = row.get("ignored_lines")\n',
        '    ignored = row.get("ignored_lines", 0)\n',
        "tests/test_review_auto_accept.py::test_auto_accept_refuses[ignored-lines-missing]",
    ),
    (
        # Review round 5 BLOCK: review.json's count is not checked for shape,
        # so an empty list (or any falsy value) reads as 0 stray lines.
        "auto-accept reads any falsy review.json ignored_lines as 0",
        REVIEW_LEDGER,
        "    if not _is_count(count):\n",
        "    if count and not _is_count(count):\n",
        "tests/test_review_auto_accept.py::test_auto_accept_refuses[review-json-ignored-list]",
    ),
    # win-repo-2 at 75bd0aea: a cp1252 console. Each run by hand, seen red.
    (
        # The ledger CLI prints finding lines in the console's code page again.
        "the ledger CLI stops writing UTF-8",
        REVIEW_LEDGER,
        "def main(argv):\n    utf8_stdio()\n",
        "def main(argv):\n",
        "tests/test_review_auto_accept.py::"
        "test_auto_accept_prints_a_non_cp1252_finding_on_a_cp1252_console",
    ),
    (
        "review_run stops switching its streams to UTF-8",
        REVIEW_RUN,
        "    review_ledger.utf8_stdio()\n",
        "",
        "tests/test_review_auto_accept.py::test_review_run_main_switches_its_streams_to_utf8_first",
    ),
    (
        "crew_autopilot stops switching its streams to UTF-8",
        os.path.join(CREW, "hooks", "scripts", "crew_autopilot.py"),
        "    review_ledger.utf8_stdio()\n",
        "",
        "tests/test_review_auto_accept.py::test_autopilot_main_switches_its_streams_to_utf8_first",
    ),
    # Review round 6 (owner decision 2026-10-02 #10). Each run by hand, seen red.
    (
        # BLOCK 1: the auto receipt stops re-checking the review.json it read.
        "receipt_stands stops re-checking review.json",
        REVIEW_LEDGER,
        "            and _receipt_binds_review_json(receipt, latest, root, ticket))\n",
        "            and True)\n",
        "tests/test_review_auto_accept.py::"
        "test_auto_receipt_does_not_stand_once_review_json_moves[recovered]",
    ),
    (
        # BLOCK 1 neighbour: the count is compared but the bytes are not.
        "receipt_stands compares review.json's count but not its hash",
        REVIEW_LEDGER,
        "    return problem is None and now == digest\n",
        "    return problem is None\n",
        "tests/test_review_auto_accept.py::"
        "test_auto_receipt_does_not_stand_once_review_json_moves[reformatted]",
    ),
    (
        # BLOCK 2: json keeps the last of two duplicate keys again.
        "review.json is parsed with duplicate keys allowed",
        REVIEW_LEDGER,
        "        review = json.loads(raw.decode(\"utf-8\"), object_pairs_hook=_refuse_duplicate_keys)\n",
        "        review = json.loads(raw.decode(\"utf-8\"))\n",
        "tests/test_review_auto_accept.py::"
        "test_auto_accept_refuses_duplicate_keys_in_review_json[top-level]",
    ),
    (
        # BLOCK 2 neighbour: review.json is followed through a link.
        "review.json is read through a link",
        REVIEW_LEDGER,
        "        if os.path.islink(path):\n            return None, None, (f\"{path} is a link;",
        "        if False:\n            return None, None, (f\"{path} is a link;",
        "tests/test_review_auto_accept.py::test_auto_accept_refuses_a_symlinked_review_json",
    ),
    (
        # Neighbour: a review.json written for another bundle is taken as the witness.
        "review.json's bundle is not compared with the round's",
        REVIEW_LEDGER,
        "    if review.get(\"bundle_sha256\") != row.get(\"bundle_sha256\"):\n",
        "    if False:\n",
        "tests/test_review_auto_accept.py::test_auto_accept_refuses_a_review_json_for_another_bundle",
    ),
    (
        # Neighbour found before round 7: `True == 1` lets a bool round in
        # review.json pass as round 1.
        "review.json's round is compared without its type",
        REVIEW_LEDGER,
        "isinstance(got, bool) or got != row.get(\"round\"):\n",
        "got != row.get(\"round\"):\n",
        "tests/test_review_auto_accept.py::test_auto_accept_refuses_a_bool_round_in_review_json",
    ),
    (
        # FIX 5: the step-3 auto-accept command splits on a spaced plugin path.
        "review.md's step-3 auto-accept command leaves the plugin root unquoted",
        REVIEW_DOC,
        '`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/review_ledger.py" --ticket "$TICKET" --auto-accept',
        '`python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/review_ledger.py --ticket "$TICKET" --auto-accept',
        "tests/test_review_auto_accept.py::test_step3_closure_commands_quote_the_plugin_root",
    ),
    (
        # FIX 4: universal newlines fold a bare CR into a line break again.
        "direction.md is read with universal newlines",
        REVIEW_LEDGER,
        '        with open(path, encoding="utf-8", newline="") as fh:\n',
        '        with open(path, encoding="utf-8") as fh:\n',
        "tests/test_review_auto_accept.py::"
        "test_check_follow_up_splits_direction_md_on_newline_only[bare-cr]",
    ),
    # L-0576: harmless stray lines beside findings are recovered; CLEAN stays
    # exact and anything that might be a contract line stays INCOMPLETE.
    (
        # The pre-L-0576 strictness: any stray line burns the round.
        "a stray prose line beside findings is INCOMPLETE again",
        REVIEW_VERDICT,
        "        if (findings and not reasons\n",
        "        if (False and findings and not reasons\n",
        ("tests/test_review_verdict.py::"
         "test_parse_harmless_stray_lines_beside_findings_are_recovered"),
    ),
    (
        # Recovery reaches CLEAN: a CLEAN wrapped in prose or a fence passes.
        "stray lines beside a CLEAN are recovered",
        REVIEW_VERDICT,
        "        if (findings and not reasons\n",
        "        if ((findings or clean_lines) and not reasons\n",
        ("tests/test_review_verdict.py::"
         "test_parse_clean_with_any_stray_line_is_incomplete"),
    ),
    (
        # A decorated or malformed finding is ignored as prose: a BLOCK the
        # parser could not read is dropped while the round reads FINDINGS.
        "contract-like stray lines are recovered as prose",
        REVIEW_VERDICT,
        "                and not any(contract_like(line) for line in unparseable)):\n",
        "                and True):\n",
        ("tests/test_review_verdict.py::"
         "test_parse_a_contract_like_stray_line_is_incomplete"),
    ),
    (
        # Markdown decoration hides the keyword: `- FIX|...` reads as prose.
        "contract-like check stops stripping markdown decoration",
        REVIEW_VERDICT,
        '    bare = "" if _FENCE.match(line) else _DECORATION.sub("", line)\n',
        '    bare = "" if _FENCE.match(line) else line\n',
        ("tests/test_review_verdict.py::"
         "test_parse_a_contract_like_stray_line_is_incomplete"),
    ),
    (
        # A reviewer that admits in prose it fell short is ignored as prose.
        "a stray line admitting a shortfall is recovered as prose",
        REVIEW_VERDICT,
        "_ON_LINE = (re.compile(r\"\\|.*\\|.*\\|\"),) + tuple(\n"
        "    re.compile(p, re.IGNORECASE) for p in _SHORTFALL)\n",
        "_ON_LINE = (re.compile(r\"\\|.*\\|.*\\|\"),)\n",
        ("tests/test_review_verdict.py::"
         "test_parse_a_contract_like_stray_line_is_incomplete"),
    ),
    (
        # A lower-case keyword reads as prose: `block a.py:1 ...` is ignored.
        "contract keywords are matched in capitals only",
        REVIEW_VERDICT,
        '_ON_BARE = (re.compile(rf"^(?:{_KEYWORD})\\b", re.IGNORECASE),)\n',
        '_ON_BARE = (re.compile(rf"^(?:{_KEYWORD})\\b"),)\n',
        ("tests/test_review_verdict.py::"
         "test_parse_a_contract_like_stray_line_is_incomplete"),
    ),
    (
        # finish's own tree/stream reasons are added after the parse again,
        # so a stray line is recovered on a round they make INCOMPLETE.
        "finish adds its outside reasons after recovery",
        REVIEW_RUN,
        "                                  prior_reasons=extra_reasons)\n",
        "                                  prior_reasons=())\n",
        "tests/test_review_refund.py::test_finish_recovers_nothing_when_the_bundle_changed",
    ),
    (
        # The ledger forgets that a round was recovered.
        "the ledger row drops the ignored-line count",
        REVIEW_LEDGER,
        '            "ignored_lines": _ignored_count(review.get("ignored_lines")),\n',
        '            "ignored_lines": 0,\n',
        "tests/test_review_refund.py::test_ledger_row_counts_the_ignored_lines",
    ),
    (
        # Recovery runs despite a missing READ, a bad exit or a timeout, so
        # the stray-line reason disappears from an INCOMPLETE round.
        "recovery ignores the round's other reasons",
        REVIEW_VERDICT,
        "        if (findings and not reasons\n",
        "        if (findings\n",
        ("tests/test_review_verdict.py::"
         "test_parse_recovery_never_masks_another_reason"),
    ),
    (
        # The ignored lines vanish from review.json.
        "review.json drops the ignored lines",
        REVIEW_RUN,
        '        "ignored_lines": len(result["ignored"]), "ignored_text": result["ignored"],\n',
        '        "ignored_lines": 0, "ignored_text": [],\n',
        "tests/test_review_refund.py::test_finish_reports_ignored_lines",
    ),
    (
        # The ignored lines are never named on a `review:` line.
        "review_run stops printing the ignored lines",
        REVIEW_RUN,
        '    if result["ignored"]:\n        print(f"review: {result[\'verdict\']} kept; ',
        '    if False:\n        print(f"review: {result[\'verdict\']} kept; ',
        "tests/test_review_refund.py::test_finish_reports_ignored_lines",
    ),
    (
        # Review round 1 FIX: a fence's info string (```FIX) read as a
        # keyword, so a fenced, well-formed finding burned the round.
        "a code fence's info string is read as a contract keyword",
        REVIEW_VERDICT,
        '    bare = "" if _FENCE.match(line) else _DECORATION.sub("", line)\n',
        '    bare = _DECORATION.sub("", line)\n',
        ("tests/test_review_verdict.py::"
         "test_parse_harmless_stray_lines_beside_findings_are_recovered"),
    ),
    (
        # Review round 1 FIX: ignored lines stored stripped, not as written.
        "ignored lines are stored stripped",
        REVIEW_VERDICT,
        '        unparseable.append(raw[:-1] if raw.endswith("\\r") else raw)\n',
        "        unparseable.append(line)\n",
        "tests/test_review_verdict.py::test_parse_ignored_lines_are_kept_verbatim",
    ),
    (
        # Review round 2 FIX: a fence with a space before its info string
        # ("``` FIX") was not a fence, so its info word read as a keyword.
        "a fence with a space before its info string is not a fence",
        REVIEW_VERDICT,
        '_FENCE = re.compile(r"^(?:`{3,}|~{3,})[ \\t]*[\\w.+#-]*$")\n',
        '_FENCE = re.compile(r"^(?:`{3,}|~{3,})[\\w.+#-]*$")\n',
        ("tests/test_review_verdict.py::"
         "test_parse_harmless_stray_lines_beside_findings_are_recovered"),
    ),
    (
        # L-0510 lane: an unknown ignored-line count read as 0 ("none").
        "the ledger records an unknown ignored-line count as 0",
        REVIEW_LEDGER,
        "        return value\n    return None\n",
        "        return value\n    return 0\n",
        ("tests/test_review_refund.py::"
         "test_ledger_row_records_an_unknown_ignored_count_as_null_never_0"),
    ),
    (
        # L-0578: the metrics row goes back to depending on prose step 6,
        # which lanes skipped for 118 of 162 rounds.
        "a recorded round writes no metrics row",
        REVIEW_RUN,
        "    metrics_line = review_metrics.record(args.root, args.ticket, number, review,\n",
        '    metrics_line = "review: no row"; _unused = (\n',
        "tests/test_review_metrics.py::test_codex_findings_round_appends_one_scored_row",
    ),
    (
        # L-0578: the row the round writes changes the bundle, so a CLEAN
        # receipt in a repo that does not gitignore .crew/ stops checking.
        "the metrics row is reviewed as part of the bundle",
        REVIEW_PATCH,
        '_EXCLUDE_SPEC = [":(exclude).work", ":(exclude)graphify-out", '
        '":(exclude).crew/metrics.md"]\n',
        '_EXCLUDE_SPEC = [":(exclude).work", ":(exclude)graphify-out"]\n',
        "tests/test_review_patch.py::"
        "test_metrics_row_stays_out_of_the_bundle_and_the_rest_of_crew_stays_in",
    ),
    (
        # L-0578 review r1 BLOCK: a symlinked .crew directory is followed and
        # the row lands in a file outside the checkout.
        "the metrics writer follows a symlinked .crew directory",
        REVIEW_METRICS,
        "    if is_link_or_junction(parent):\n"
        "        raise NotARegularFile(f\"{parent} is a link or junction; not following it\")\n"
        "    try:\n",
        "    if False:\n"
        "        raise NotARegularFile(f\"{parent} is a link or junction; not following it\")\n"
        "    try:\n",
        "tests/test_review_metrics.py::test_a_junction_parent_is_refused",
    ),
    (
        # L-0578 review r2 BLOCK: the open follows a .crew symlink swapped in
        # after the pre-check (check-then-open race).
        "the metrics open follows the .crew directory",
        REVIEW_METRICS,
        "    if nofollow and directory and os.open in os.supports_dir_fd:\n",
        "    if False:\n",
        "tests/test_review_metrics.py::"
        "test_the_open_itself_refuses_a_crew_symlink_swapped_in_after_the_check",
    ),
    (
        # L-0578 review r2 FIX: a marker naming another provider passes for a
        # Codex limit.
        "a limit marker of any provider claims a codex limit",
        REVIEW_METRICS,
        '    if not isinstance(previous, int) or isinstance(previous, bool) or provider != "codex" \\\n',
        "    if not isinstance(previous, int) or isinstance(previous, bool) \\\n",
        "tests/test_review_metrics.py::test_a_malformed_limit_marker_is_unreadable_not_a_limit",
    ),
    (
        # L-0578 review r2 FIX: a malformed config reads as config provenance.
        "an unreadable config is reported as config provenance",
        REVIEW_METRICS,
        '    if source == "config" and config_unreadable(root):\n',
        "    if False:\n",
        "tests/test_review_metrics.py::test_a_malformed_config_is_not_reported_as_config_provenance",
    ),
    (
        # L-0578 review r2 FIX: the row takes a reservation record for
        # another round.
        "a reservation token for another round is used",
        REVIEW_METRICS,
        "                or kept.get(\"round\") != number or isinstance(kept.get(\"round\"), bool):\n",
        "                or isinstance(kept.get(\"round\"), bool):\n",
        "tests/test_review_metrics.py::test_a_reservation_record_for_another_round_is_not_used",
    ),
    # --- H1 harness bundle (T-0098, T-0109, T-0101) -------------------------
    # T-0098: --correct-acceptance. Each red on its named test through this
    # runner's own main(), with MUTATIONS filtered to the entry.
    (
        # (a) An auto-accepted receipt's fixed accepter is "corrected", so
        # receipt_stands stops standing it.
        "a correction takes an auto-accepted receipt",
        REVIEW_LEDGER,
        '        if not isinstance(receipt, dict) or receipt.get("kind") != "owner-accepted":\n',
        '        if not isinstance(receipt, dict) or receipt.get("kind") not in '
        '("owner-accepted", AUTO_KIND):\n',
        "tests/test_review_correct_acceptance.py::test_correction_refused",
    ),
    (
        # (b) A correction writes an `auto:` name without auto_accept's guard.
        "a correction takes an auto: name",
        REVIEW_LEDGER,
        "    if _is_auto_name(new):\n",
        "    if False:\n",
        "tests/test_review_correct_acceptance.py::test_correction_refused",
    ),
    (
        # (c) The history row overwrites the list instead of appending.
        "a correction overwrites the correction history",
        REVIEW_LEDGER,
        '        data["acceptance_corrections"] = history + [row]\n',
        '        data["acceptance_corrections"] = [row]\n',
        ("tests/test_review_correct_acceptance.py::"
         "test_second_correction_appends_and_keeps_the_first_row"),
    ),
    (
        # (d) The correction refreshes accepted_at as well as the name.
        "a correction refreshes accepted_at",
        REVIEW_LEDGER,
        '        receipt["accepted_by"] = new\n',
        '        receipt["accepted_by"] = new\n        receipt["accepted_at"] = _now()\n',
        ("tests/test_review_correct_acceptance.py::"
         "test_correction_changes_only_the_name_and_the_history"),
    ),
    (
        # (e) A malformed history is extended instead of refused.
        "a correction extends a malformed correction history",
        REVIEW_LEDGER,
        "        if not _is_dict_list(history):\n"
        "            raise LedgerError(f\"{ticket}'s `acceptance_corrections` is not a list of \"\n",
        "        if False:\n"
        "            raise LedgerError(f\"{ticket}'s `acceptance_corrections` is not a list of \"\n",
        "tests/test_review_correct_acceptance.py::test_correction_refused",
    ),
    (
        # (f) --reason may carry a line break into the ledger and the status.
        "a correction reason may carry a line break",
        REVIEW_LEDGER,
        '    why = _one_line_arg(reason, "--reason")\n',
        '    why = (reason.strip() if isinstance(reason, str) and reason.strip()\n'
        '           else _one_line_arg(reason, "--reason"))\n',
        "tests/test_review_correct_acceptance.py::test_correction_refused",
    ),
    # T-0109: --reject --by <who> --supersede-accepted.
    (
        # (a) Plain --reject voids an accepted receipt.
        "plain --reject supersedes an ACCEPTED ticket without the flag",
        REVIEW_LEDGER,
        "        if supersede_accepted:\n",
        "        if supersede_accepted or data.get(\"state\") == ACCEPTED:\n",
        ("tests/test_review_reject_accepted.py::"
         "test_supersede_is_refused_and_changes_nothing"),
    ),
    (
        # (b) An unattended `auto:` name supersedes an acceptance.
        "--supersede-accepted takes an auto: name",
        REVIEW_LEDGER,
        "    if supersede_accepted and _is_auto_name(by):\n",
        "    if False:\n",
        ("tests/test_review_reject_accepted.py::"
         "test_supersede_is_refused_and_changes_nothing"),
    ),
    (
        # (c) The flag acts on a REVIEWED ticket, recording a supersession
        # that never happened.
        "--supersede-accepted takes a REVIEWED ticket",
        REVIEW_LEDGER,
        "    if data.get(\"state\") != ACCEPTED:\n",
        "    if data.get(\"state\") not in (ACCEPTED, REVIEWED):\n",
        ("tests/test_review_reject_accepted.py::"
         "test_supersede_is_refused_and_changes_nothing"),
    ),
    (
        # (d) A receipt of a kind nobody knows is superseded as if read.
        "--supersede-accepted takes any receipt kind",
        REVIEW_LEDGER,
        "    if not isinstance(receipt, dict) or receipt.get(\"kind\") not in SUPERSEDABLE:\n",
        "    if not isinstance(receipt, dict):\n",
        ("tests/test_review_reject_accepted.py::"
         "test_supersede_is_refused_and_changes_nothing"),
    ),
    (
        # (e) A receipt for an older round than the latest is superseded.
        "--supersede-accepted drops the latest-round check",
        REVIEW_LEDGER,
        "    if (not isinstance(latest, dict) or latest.get(\"status\") != \"completed\"\n"
        "            or latest.get(\"round\") != number):\n",
        "    if False:\n",
        ("tests/test_review_reject_accepted.py::"
         "test_supersede_is_refused_and_changes_nothing"),
    ),
    (
        # (f) The replaced receipt is lost instead of kept.
        "--supersede-accepted does not keep the old receipt",
        REVIEW_LEDGER,
        "    data[\"superseded\"] = history + [{\"receipt\": receipt, \"by\": by, \"at\": at}]\n",
        "    data[\"superseded\"] = history\n",
        ("tests/test_review_reject_accepted.py::"
         "test_supersede_moves_an_owner_accepted_ticket_to_needs_replan"),
    ),
    (
        # (g) A second supersession overwrites the first row.
        "--supersede-accepted replaces the superseded history",
        REVIEW_LEDGER,
        "    data[\"superseded\"] = history + [{\"receipt\": receipt, \"by\": by, \"at\": at}]\n",
        "    data[\"superseded\"] = [{\"receipt\": receipt, \"by\": by, \"at\": at}]\n",
        ("tests/test_review_reject_accepted.py::"
         "test_supersede_survives_a_successor_and_appends"),
    ),
    (
        # (h) The receipt stays in place under NEEDS_REPLAN.
        "--supersede-accepted leaves the receipt in place",
        REVIEW_LEDGER,
        "    data[\"rejected\"] = {\"by\": by, \"at\": at, \"round\": number, "
        "\"superseded\": receipt[\"kind\"]}\n    data[\"receipt\"] = None\n",
        "    data[\"rejected\"] = {\"by\": by, \"at\": at, \"round\": number, "
        "\"superseded\": receipt[\"kind\"]}\n",
        ("tests/test_review_reject_accepted.py::"
         "test_supersede_moves_an_owner_accepted_ticket_to_needs_replan"),
    ),
    # T-0101: the override line in the receipts block.
    (
        # (a) The line is no longer printed on a tree the gate does not accept.
        "the receipts block drops the recorded-override line",
        REVIEW_PROMPT,
        "                out.append(OVERRIDE_LINE)\n",
        "",
        "tests/test_review_prompt.py::test_an_unverified_tree_names_the_recorded_override",
    ),
    (
        # (b) The line is printed on every tree, accepted ones included.
        "the receipts block prints the override line on an accepted gate",
        REVIEW_PROMPT,
        '    out = ["== Test receipts (verify gate) =="]\n',
        '    out = ["== Test receipts (verify gate) ==", OVERRIDE_LINE]\n',
        "tests/test_review_prompt.py::test_an_accepted_gate_never_carries_the_override_line",
    ),
    # Review of 24cb235c (#418): FIX1, FIX2, N1, N2, N3.
    (
        # FIX2: a receipt round of `true` passes as round 1 (True == 1).
        "--supersede-accepted takes a bool receipt round",
        REVIEW_LEDGER,
        "    if not isinstance(number, int) or isinstance(number, bool):\n",
        "    if not isinstance(number, int):\n",
        ("tests/test_review_reject_accepted.py::"
         "test_supersede_is_refused_and_changes_nothing"),
    ),
    (
        # FIX2: a latest row round of 1.0 or true passes as round 1.
        "--supersede-accepted drops the latest round's type check",
        REVIEW_LEDGER,
        "    if not isinstance(latest_round, int) or isinstance(latest_round, bool):\n",
        "    if False:\n",
        ("tests/test_review_reject_accepted.py::"
         "test_supersede_is_refused_and_changes_nothing"),
    ),
    (
        # FIX1: --supersede-accepted's --by skips the one-line / UTF-8 check,
        # so a lone surrogate is written and the success line then crashes.
        "--reject writes a --by it cannot print",
        REVIEW_LEDGER,
        '    by = _one_line_arg(by, "--by", "--reject")\n',
        '    if not isinstance(by, str) or not by.strip():\n'
        '        raise LedgerError("--reject needs --by <who is rejecting>")\n',
        ("tests/test_review_reject_accepted.py::"
         "test_supersede_is_refused_and_changes_nothing"),
    ),
    (
        # FIX1: plain --accept writes a --by it cannot print or that spans lines.
        "--accept writes a --by it cannot print",
        REVIEW_LEDGER,
        '    by = _one_line_arg(by, "--by", "--accept")\n',
        '    if not isinstance(by, str) or not by.strip():\n'
        '        raise LedgerError("--accept needs --by <who is accepting>")\n',
        ("tests/test_review_reject_accepted.py::"
         "test_plain_reject_and_accept_refuse_a_name_they_cannot_write"),
    ),
    (
        # N1: a fullwidth or zero-width lookalike passes the reserved prefix.
        "the auto: prefix test stops folding lookalikes",
        REVIEW_LEDGER,
        '    folded = unicodedata.normalize("NFKC", name).casefold()\n',
        "    folded = name.lower()\n",
        "tests/test_review_correct_acceptance.py::test_correction_refused",
    ),
    (
        # N2: only \n and \r count as line breaks again.
        "a one-line argument may carry a Unicode line break",
        REVIEW_LEDGER,
        "    if any(ch in _LINE_BREAKS for ch in value):\n",
        '    if "\\n" in value or "\\r" in value:\n',
        "tests/test_review_correct_acceptance.py::test_correction_refused",
    ),
    (
        # N3: argparse prefix matching lets `--super` reach the flag.
        "review_ledger.py accepts abbreviated flags",
        REVIEW_LEDGER,
        "    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0], "
        "allow_abbrev=False)\n",
        "    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])\n",
        ("tests/test_review_correct_acceptance.py::"
         "test_an_abbreviated_flag_is_a_usage_error"),
    ),
    (
        # Review of 1b9ce429, FIX2: a receipt the round's verdict cannot carry
        # is superseded as if it were readable.
        "--supersede-accepted takes a receipt the verdict cannot carry",
        REVIEW_LEDGER,
        '    if receipt.get("kind") not in wanted:\n',
        "    if False:\n",
        ("tests/test_review_reject_accepted.py::"
         "test_supersede_is_refused_and_changes_nothing"),
    ),
    (
        # FIX2: a receipt naming no bundle is superseded.
        "--supersede-accepted takes a receipt with no bundle",
        REVIEW_LEDGER,
        '    if not isinstance(receipt.get("bundle_sha256"), str) or not receipt["bundle_sha256"]:\n',
        "    if False:\n",
        ("tests/test_review_reject_accepted.py::"
         "test_supersede_is_refused_and_changes_nothing"),
    ),
    (
        # Review of 1b9ce429, FIX1: --correct-acceptance on a ticket that is
        # no longer ACCEPTED.
        "--correct-acceptance ignores the state",
        REVIEW_LEDGER,
        "        if current != ACCEPTED:\n",
        "        if False:\n",
        "tests/test_review_correct_acceptance.py::test_correction_refused",
    ),
    (
        # FIX1: --correct-acceptance on a receipt for an older round.
        "--correct-acceptance takes a receipt for an older round",
        REVIEW_LEDGER,
        '                or latest.get("verdict") != "FINDINGS" or latest.get("round") != number\n',
        '                or latest.get("verdict") != "FINDINGS"\n',
        "tests/test_review_correct_acceptance.py::test_correction_refused",
    ),
    (
        # Review of 1b9ce429, FIX3: --status shows a null history as empty.
        "--status shows a malformed history as empty",
        REVIEW_LEDGER,
        '            "superseded": data.get("superseded", []),\n',
        '            "superseded": data.get("superseded") or [],\n',
        ("tests/test_review_reject_accepted.py::"
         "test_status_shows_a_malformed_history_as_it_is"),
    ),
    (
        # Review of 7351594b: a float latest round passes as the receipt's.
        "--correct-acceptance takes a float latest round",
        REVIEW_LEDGER,
        '                or type(latest.get("round")) is not int):'
        '  # pylint: disable=unidiomatic-typecheck\n',
        '                or False):\n',
        "tests/test_review_correct_acceptance.py::test_correction_refused",
    ),
    (
        # Review of 7351594b: an old accepter it cannot print is corrected.
        "--correct-acceptance takes an old accepter it cannot print",
        REVIEW_LEDGER,
        '            _one_line_arg(was, "accepted_by")\n',
        "            pass\n",
        "tests/test_review_correct_acceptance.py::test_correction_refused",
    ),
)
