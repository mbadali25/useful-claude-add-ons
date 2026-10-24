"""The L-0710 mutations: the Stop gate fits its budget. Same tuple shape as
`sabotage.py`'s MUTATIONS -- (label, target, find, replace, test) -- and
appended to it there. Run `sabotage.py`, not this file.

Each one puts back a way the Stop gate used to fail its budget contract:
a deferral that blocks the turn, a turn that ran nothing recorded as
verified, a real failure let through because something else was deferred,
and the diff baseline that replaced the quiet-turn marker not being kept or
not being read (the guard's own fix, re-reviewed as hard as the guard).
Every target is a case in `test_verify_gate_stop_fits_budget.py`, and each
label names the first assertion its mutation trips.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SH = os.path.join(CREW, "hooks", "scripts", "verify-gate.sh")
RECORD = os.path.join(CREW, "hooks", "scripts", "verify_record.py")
_T = "tests/test_verify_gate_stop_fits_budget.py::"

STOP_BUDGET_MUTATIONS = (
    ("a deferral at Stop exits 2 again (acceptance 6a)", SH,
     "      printf '%s\\n' \"$NOTICE_LINE\" >&2\n    fi\n  done <<< \"$NOTICES\"\nfi\n",
     "      printf '%s\\n' \"$NOTICE_LINE\" >&2\n    fi\n  done <<< \"$NOTICES\"\n  exit 2\nfi\n",
     _T + "test_a_chronic_rule_is_named_as_ci_and_exits_0[sh]"),
    ("an empty changed set advances the verified marker again (acceptance 6b)", SH,
     '  if [ "$BASE_FROM_MARKER" -eq 0 ]; then\n    record_base || refuse_base_write\n  fi\n  exit 0\n',
     "  record_verified\n  exit 0\n",
     _T + "test_zero_rules_ran_does_not_advance_an_existing_marker[sh]"),
    ("a turn that selected no command writes the verified marker (acceptance 6b)", SH,
     "    record_base || refuse_base_write\n  fi\nelif",
     "    record_verified\n  fi\nelif",
     _T + "test_a_changed_file_matching_nothing_runnable_says_0_rules_ran[sh]"),
    ("an in-budget failure passes when the budget deferred something (acceptance 6c)", SH,
     '\n[ "$FAILED" -eq 0 ] || exit 2\n\n# --ci never advances',
     '\n[ "$FAILED" -eq 0 ] || [ -n "$NOTICES" ] || exit 2\n\n# --ci never advances',
     _T + "test_an_in_budget_failure_beside_a_chronic_rule_exits_2[sh]"),
    ("the diff baseline is never read, so a commit on main is out of scope", SH,
     'if [ -z "$BASE" ] && [ -e "$BASE_AT" ] \\\n',
     'if false && [ -e "$BASE_AT" ] \\\n',
     _T + "test_a_commit_on_the_default_branch_after_a_quiet_turn_is_in_scope[sh]"),
    ("a quiet turn records no diff baseline, so a commit on main is out of scope", SH,
     '    record_base || refuse_base_write\n  fi\n  exit 0\n',
     "    :\n  fi\n  exit 0\n",
     _T + "test_a_commit_on_the_default_branch_after_a_quiet_turn_is_in_scope[sh]"),
    # Review round 1 (Codex): the baseline's own guards, each both flavours.
    ("a baseline left on another branch is trusted", SH,
     '      BASE=$(git merge-base "$CAND" HEAD 2>/dev/null) || BASE=""\n',
     '      BASE="$CAND"\n',
     _T + "test_a_baseline_left_on_another_branch_is_not_used[sh]"),
    ("a zero-command turn moves the baseline past a committed change", SH,
     '     && git diff --quiet "$BASE" HEAD -- 2>/dev/null; then\n',
     "     && true; then\n",
     _T + "test_a_zero_command_turn_with_a_committed_change_keeps_the_baseline[sh]"),
    ("a baseline write that fails is a quiet success", SH,
     "    record_base || refuse_base_write\n  fi\n  exit 0\n",
     "    record_base || true\n  fi\n  exit 0\n",
     _T + "test_a_baseline_that_cannot_be_written_refuses_the_turn[sh]"),
    ("an unmapped failure that ran nothing does not say 0 rules ran", SH,
     'if [ "$FAILED" -ne 0 ] && [ "$CI_MODE" -eq 0 ] && ! printf',
     'if false && [ "$FAILED" -ne 0 ] && [ "$CI_MODE" -eq 0 ] && ! printf',
     _T + "test_an_unmapped_failure_with_no_command_still_says_0_rules_ran[sh]"),
    ("an old chronic record keeps its pre-CI reason", RECORD,
     "            and reason.endswith(_OLD_CHRONIC_TAIL)):\n",
     "            and reason.endswith(_OLD_CHRONIC_TAIL) and False):\n",
     _T + "test_an_old_chronic_record_is_reported_as_deferred_to_ci"),
    # Review round 2 (Codex): an unreadable or corrupt baseline is refused.
    ("a baseline that names no commit falls back to merge-base = HEAD", SH,
     'Run /crew:verify --all, then remove that file." >&2\n    exit 2\n',
     'Run /crew:verify --all, then remove that file." >&2\n',
     _T + "test_a_baseline_that_names_no_commit_refuses_the_turn[sh-not-a-sha\\n]"),
    # Review round 3 (Codex): a baseline that is a FIFO hung Stop in `head`.
    ("a FIFO baseline is read and Stop hangs waiting for a writer", SH,
     '  if [ -f "$BASE_AT" ]; then\n    CAND=$(head',
     '  if [ -e "$BASE_AT" ]; then\n    CAND=$(head',
     _T + "test_a_baseline_that_is_a_fifo_refuses_the_turn_without_hanging[sh]"),
    # L-0905: the pricing floor, the sync payload and the dead producer.
    ("a cached zero prices a declared rule (the positive floor is dropped)", SH,
     "                            and cached > 0):\n"
     "                        rule_secs[ri] = cached\n"
     "                        if cached < secs:\n",
     "                            and cached >= 0):\n"
     "                        rule_secs[ri] = cached\n"
     "                        if cached < secs:\n",
     "tests/test_verify_gate_stop_budget.py::test_an_unusable_measurement_leaves_the_declared_price[0-sh]"),
    ("the sync payload rides on argv again", SH,
     'with open(sys.argv[1], encoding="utf-8") as fh:\n    extras = json.loads(fh.read())\n',
     "extras = json.loads(sys.argv[1])\n",
     "tests/test_verify_gate_sync_payload.py::test_a_payload_over_the_argv_limit_reaches_the_record[sh]"),
    ("the sync payload rides on argv again (call site)", SH,
     "' \"$EXTRAS_FILE\" \"$SYNC_SHA\"",
     "' \"$EXTRAS\" \"$SYNC_SHA\"",
     "tests/test_verify_gate_sync_payload.py::test_a_payload_over_the_argv_limit_reaches_the_record[sh]"),
    ("only the last pipeline stage decides the sync status", SH,
     'if [ "$SYNC_STATUS" -eq 0 ] && { [ "${SYNC_PIPE[0]}"',
     'if false && { [ "${SYNC_PIPE[0]}"',
     "tests/test_verify_gate_sync_payload.py::test_a_failed_sync_producer_does_not_advance_the_marker[sh]"),
    ("an empty sync payload is accepted", RECORD,
     "    if not raw.strip():\n",
     "    if False:\n",
     "tests/test_verify_gate_sync_payload.py::test_an_empty_sync_payload_is_refused"),
    ("a rule child inherits the hook's stdin", SH,
     '>"$RULE_OUT_FILE" 2>&1 </dev/null 4>&- &',
     '>"$RULE_OUT_FILE" 2>&1 4>&- &',
     "tests/test_verify_gate_sync_payload.py::test_the_rule_child_redirects_stdin_from_devnull_in_the_run_line"),
    ("a cached true prices a rule with no declared seconds", SH,
     "                    if (isinstance(cached, int) and not isinstance(cached, bool)\n"
     "                            and cached > 0):\n"
     "                        rule_secs[ri] = cached\n"
     "                        measured_used[ri] = True\n",
     "                    if (isinstance(cached, int)\n"
     "                            and cached > 0):\n"
     "                        rule_secs[ri] = cached\n"
     "                        measured_used[ri] = True\n",
     "tests/test_verify_gate_reprice.py::"
     "test_an_unusable_measurement_does_not_price_a_rule_with_no_declared_seconds[True-sh]"),
)
