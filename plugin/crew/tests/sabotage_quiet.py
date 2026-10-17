"""The L-0796 mutations: the quiet Stop gate must not hide a failure or an unknown.
Same tuple shape as `sabotage.py`'s MUTATIONS -- (label, target, find, replace,
test) -- and appended to it there. Run `sabotage.py`, not this file.

verify-gate.sh now prints a verdict line and only the lines it cannot prove are
informational. Each mutation reintroduces one way that could go wrong: the
classifier demoting what it should show, a failure body dropped, the repeat
line returning a pass, a missing state read as "unchanged", a not-run rule
counted as passed, an unwritable log reading as silence, and the session key
ignored. Every target is a case in `test_verify_gate_quiet.py`.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SH = os.path.join(CREW, "hooks", "scripts", "verify-gate.sh")
PS1 = os.path.join(CREW, "hooks", "scripts", "verify-gate.ps1")
_TP = "tests/test_verify_gate_quiet_ps1.py::"
_T = "tests/test_verify_gate_quiet.py::"
_CREDITED = (
    "    \"verify-gate: \"*\" command(s) passed on this exact tree in an earlier run "
    "and are credited\"*) return 0 ;;\n")

QUIET_MUTATIONS = (
    ("quiet gate: the classifier demotes a notice it does not know (S1)", SH,
     _CREDITED + "  esac\n  return 1\n",
     _CREDITED + "  esac\n  return 0\n",
     _T + "test_unknown_notice_line_still_prints"),
    ("quiet gate: a failing rule's header is demoted to the log (S1)", SH,
     "    echo \"VERIFY FAILED: $c\" >&2\n    echo \"$OUT\" | tail -25 >&2\n    FAILED=1\n    CMD_STATUS=\"fail\"\n",
     "    gate_detail \"VERIFY FAILED: $c\"\n    echo \"$OUT\" | tail -25 >&2\n    FAILED=1\n    CMD_STATUS=\"fail\"\n",
     _T + "test_failure_span_identical_to_verbose"),
    ("quiet gate: every line the gate printed is treated as detail (S1)", SH,
     "  LC_ALL=C grep -a -v \"^$CREW_GATE_NONCE\" \"$_buf\" > \"$_plain\" 2>/dev/null\n",
     "  : > \"$_plain\"\n",
     _T + "test_rule_output_resembling_info_line_is_not_demoted"),
    ("quiet gate: the tail -25 body is dropped in quiet mode (S2)", SH,
     "    echo \"VERIFY FAILED: $c\" >&2\n    echo \"$OUT\" | tail -25 >&2\n    FAILED=1\n    CMD_STATUS=\"fail\"\n",
     "    echo \"VERIFY FAILED: $c\" >&2\n    [ \"${CREW_GATE_QUIET:-0}\" -eq 1 ] || echo \"$OUT\" | tail -25 >&2\n"
     "    FAILED=1\n    CMD_STATUS=\"fail\"\n",
     _T + "test_failure_span_identical_to_verbose"),
    ("quiet gate: the unchanged line exits 0 (S3)", SH,
     "\"$_nfail\" \"$_nvtxt\" \"$_first\" \"$_detail\" >&2\n",
     "\"$_nfail\" \"$_nvtxt\" \"$_first\" \"$_detail\" >&2\n    exit 0\n",
     _T + "test_unchanged_same_session_prints_one_line_exit_2"),
    ("quiet gate: an unchanged repeat ignores an unwritable log", SH,
     "  [ \"$_log_ok\" -eq 1 ] || _unchanged=0\n", "",
     _T + "test_unchanged_repeat_with_unwritable_log_prints_failure_in_full"),
    ("quiet gate: a missing state file is read as unchanged (S4)", SH,
     "  if [ \"$_unchanged\" -eq 1 ]; then\n",
     "  if [ \"$_unchanged\" -eq 1 ] || [ ! -f \"$_state\" ]; then\n",
     _T + "test_unchanged_same_session_prints_one_line_exit_2"),
    ("quiet gate: a not-run skipped rule is counted into PASSED (S5)", SH,
     "  G_NV=$((G_REACH + G_OVER + G_DIRTY + G_DEFER + G_SKIP + G_OTHER))\n",
     "  G_NV=$((G_REACH + G_OVER + G_DIRTY + G_DEFER + G_SKIP + G_OTHER))\n  G_PASS=$((G_PASS + G_SKIP))\n",
     _T + "test_not_verified_never_counted_as_passed"),
    ("quiet gate: an unwritable log prints nothing instead of the full text (S6)", SH,
     "  local _detail=\"unavailable\" _body=\"$_full\"\n",
     "  local _detail=\"unavailable\" _body=\"/dev/null\"\n",
     _T + "test_unwritable_log_degrades_to_full_output"),
    ("quiet gate: the session id is ignored by the repeat check (S7)", SH,
     "    if [ \"$_st_sid\" = \"$CREW_GATE_SESSION\" ] && [ \"$_st_hash\" = \"$_hash\" ]; then\n",
     "    if [ \"$_st_hash\" = \"$_hash\" ]; then\n",
     _T + "test_new_session_or_missing_state_prints_full_block"),
    ("quiet gate: the rule subshell inherits the hook's saved stderr pipe (fd 4)", SH,
     "</dev/null 4>&- &\n", "</dev/null &\n",
     _T + "test_rule_that_backgrounds_a_process_does_not_hold_the_hook_open"),
    ("quiet gate: the unchanged line drops the detail-log pointer", SH,
     " | detail: %s | /crew:verify --all runs every rule\\n' \"$_nfail\" \"$_nvtxt\" \"$_first\" \"$_detail\"",
     "\\n' \"$_nfail\" \"$_nvtxt\" \"$_first\"",
     _T + "test_unchanged_same_session_prints_one_line_exit_2"),
    ("quiet gate: the verdict drops its units", SH,
     "NOT VERIFIED $G_NVTXT item(s) (reach", "NOT VERIFIED $G_NVTXT (reach",
     _T + "test_verdict_names_its_units"),
    ("quiet gate (ps1): every notice reads as informational", PS1,
     "if ($Line -cmatch $pattern) { return $true } }\n  return $false",
     "if ($Line -cmatch $pattern) { return $true } }\n  return $true",
     _TP + "test_ps1_unknown_notice_line_still_prints"),
    ("quiet gate (ps1): an unwritable log prints nothing instead of the full text", PS1,
     "$body = if ($logOk) { $plainLines } else { $fullLines }",
     "$body = if ($logOk) { $plainLines } else { @() }",
     _TP + "test_ps1_unwritable_log_degrades_to_full_output"),
    ("quiet gate (ps1): an unchanged repeat ignores an unwritable log", PS1,
     "  if (-not $logOk) { $unchanged = $false }\n", "",
     _TP + "test_ps1_unchanged_repeat_with_unwritable_log_prints_failure_in_full"),
    ("quiet gate (ps1): the session id is ignored by the repeat check", PS1,
     "$stateParts[0] -ceq $script:CrewSession -and ", "",
     _TP + "test_ps1_other_session_prints_full_block_and_unchanged_names_the_log"),
    ("quiet gate (ps1): the unchanged line drops the detail-log pointer", PS1,
     " | detail: $detail | /crew:verify --all runs every rule\")", "\")",
     _TP + "test_ps1_other_session_prints_full_block_and_unchanged_names_the_log"),
    ("quiet gate: a backed-off run may replace the lock holder's detail log", SH,
     "[ \"$CREW_GATE_MAY_LOG\" -eq 1 ] && [ -s \"$_buf\" ]", "[ -s \"$_buf\" ]",
     _T + "test_backed_off_run_leaves_the_lock_holders_log_alone"),
    ("quiet gate: reach-excluded always/default commands are left out of NOT VERIFIED", SH,
     "    G_REACH=$((G_REACH + ${G_FB:-0}))\n", "",
     _T + "test_reach_excluded_always_command_counts_as_not_verified"),
    ("quiet gate: the repeat check hashes counts but not which rules were not run", SH,
     "\"$G_OTHER\" \"$G_FAIL\" \"$G_NVD\"; }", "\"$G_OTHER\" \"$G_FAIL\" \"\"; }",
     _T + "test_repeat_check_follows_which_rules_were_not_run"),
    ("quiet gate: a payload with two session ids picks one", SH,
     "| wc -l | tr -d '[:space:]')\" = 1 ]; then\n", "| wc -l | tr -d '[:space:]')\" -ge 1 ]; then\n",
     _T + "test_ambiguous_session_id_prints_the_full_block_every_time"),
    ("quiet gate (ps1): a backed-off run may replace the lock holder's detail log", PS1,
     "  if ($script:CrewMayLog -and $fullLines.Count -gt 0", "  if ($fullLines.Count -gt 0",
     _TP + "test_ps1_backed_off_run_leaves_the_lock_holders_log_alone"),
    ("quiet gate (ps1): reach-excluded always/default commands are left out of NOT VERIFIED", PS1,
     "  $reach += $(if ($null -ne $fallbackNotices) { $fallbackNotices.Count } else { 0 })\n", "",
     _TP + "test_ps1_reach_excluded_always_command_counts_as_not_verified"),
    ("quiet gate (ps1): the repeat check hashes counts but not which rules were not run", PS1,
     "$other $fail $nvDigest`n", "$other $fail`n",
     _TP + "test_ps1_repeat_check_follows_which_rules_were_not_run"),
    ("quiet gate: a failed split of the stderr buffer is trusted", SH,
     "  if [ \"$_split_ok\" -eq 0 ]; then _plain=\"$_buf\"; _full=\"$_buf\"; fi\n", "",
     _T + "test_failed_split_of_the_buffer_prints_everything"),
    ("quiet gate: an exit-0 Stop leaves the repeat state in place", SH,
     "  if [ \"$_rc\" -eq 0 ] && [ \"$CREW_GATE_BACKED_OFF\" -eq 0 ]; then\n"
     "    rm -f \".crew/.verify-gate.last-stop\" 2>/dev/null\n  fi\n", "",
     _T + "test_exit_zero_stop_clears_the_repeat_state"),
    ("quiet gate: a nested session id is taken as the session", SH,
     "    if [ $((_qi_o - _qi_c)) -eq 1 ] && [ \"$_qi_ao\" = \"$_qi_ac\" ]; then\n",
     "    if true; then\n",
     _T + "test_a_session_id_that_is_not_a_top_level_string_prints_the_full_block"),
    ("quiet gate (ps1): an exit-0 Stop leaves the repeat state in place", PS1,
     "  if ($rc -eq 0 -and -not $script:CrewBackedOff) {\n"
     "    Remove-Item -LiteralPath \".crew/.verify-gate.last-stop\" -Force -ErrorAction SilentlyContinue\n  }\n", "",
     _TP + "test_ps1_exit_zero_stop_clears_the_repeat_state"),
    ("quiet gate (ps1): a nested session id is taken as the session", PS1,
     "  if ($braces -ne 1 -or $brackets -ne 0) { return \"\" }\n", "",
     _TP + "test_ps1_a_session_id_that_is_not_a_top_level_string_prints_the_full_block"),
)
