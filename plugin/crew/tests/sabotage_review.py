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
REVIEW_GATE = os.path.join(CREW, "hooks", "scripts", "review_gate.py")

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
        '        patch = _run_raw(root, ["diff"] + _DIFF_FLAGS + [base_sha, working_tree] + only)\n',
        '        patch = _run_raw(root, ["diff"] + _DIFF_FLAGS + [base_sha, working_tree])\n',
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
        '_EXCLUDE_SPEC = [":(exclude).work", ":(exclude)graphify-out"]\n',
        '_EXCLUDE_SPEC = [":(exclude).work"]\n',
        ("tests/test_review_patch.py::"
         "test_generated_graph_dir_is_excluded_and_says_so"),
    ),
    (
        # The manifest stops naming graphify-out/: a reviewer reads a bundle
        # with the graph left out and nothing records that it was.
        "the manifest stops saying graphify-out is excluded",
        REVIEW_PATCH,
        'EXCLUDED = (".work/", "graphify-out/")\n',
        'EXCLUDED = (".work/",)\n',
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
        "--base \"$TICKET\")\n",
        "BASE=$(git merge-base HEAD main)\n",
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
        # The latest round's verdict is not read.
        "--check-receipt does not read the latest round's verdict",
        REVIEW_LEDGER,
        "    if latest.get(\"status\") != \"completed\" or not accepted:\n",
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
)
