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
)
