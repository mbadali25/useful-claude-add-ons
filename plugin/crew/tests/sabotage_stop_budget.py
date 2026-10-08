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
PS1 = os.path.join(CREW, "hooks", "scripts", "verify-gate.ps1")
RECORD = os.path.join(CREW, "hooks", "scripts", "verify_record.py")
_T = "tests/test_verify_gate_stop_fits_budget.py::"

STOP_BUDGET_MUTATIONS = (
    ("a deferral at Stop exits 2 again (acceptance 6a)", SH,
     "if [ -n \"$NOTICES\" ]; then\n  printf '%s\\n' \"$NOTICES\" >&2\nfi\n",
     "if [ -n \"$NOTICES\" ]; then\n  printf '%s\\n' \"$NOTICES\" >&2\n  exit 2\nfi\n",
     _T + "test_a_chronic_rule_is_named_as_ci_and_exits_0[sh]"),
    ("the PowerShell gate exits 2 on a deferral again", PS1,
     "foreach ($n in $notices) { [Console]::Error.WriteLine($n) }\n",
     "foreach ($n in $notices) { [Console]::Error.WriteLine($n) }\n"
     "if ($notices.Count -gt 0) { exit 2 }\n",
     _T + "test_a_chronic_rule_is_named_as_ci_and_exits_0[ps1]"),
    ("an empty changed set advances the verified marker again (acceptance 6b)", SH,
     '  if [ "$BASE_FROM_MARKER" -eq 0 ]; then\n    record_base || refuse_base_write\n  fi\n  exit 0\n',
     "  record_verified\n  exit 0\n",
     _T + "test_zero_rules_ran_does_not_advance_an_existing_marker[sh]"),
    ("the PowerShell gate advances the marker on an empty changed set", PS1,
     "  if (-not $baseFromMarker) { Write-CrewBase }\n  exit 0\n",
     "  Write-CrewVerified\n  exit 0\n",
     _T + "test_zero_rules_ran_does_not_advance_an_existing_marker[ps1]"),
    ("a turn that selected no command writes the verified marker (acceptance 6b)", SH,
     "    record_base || refuse_base_write\n  fi\nelif",
     "    record_verified\n  fi\nelif",
     _T + "test_a_changed_file_matching_nothing_runnable_says_0_rules_ran[sh]"),
    ("the PowerShell gate writes the marker when no command was selected", PS1,
     "    if ($LASTEXITCODE -eq 0) { Write-CrewBase }\n  }\n} elseif",
     "    if ($LASTEXITCODE -eq 0) { Write-CrewVerified }\n  }\n} elseif",
     _T + "test_a_changed_file_matching_nothing_runnable_says_0_rules_ran[ps1]"),
    ("an in-budget failure passes when the budget deferred something (acceptance 6c)", SH,
     '\n[ "$FAILED" -eq 0 ] || exit 2\n\n# --ci never advances',
     '\n[ "$FAILED" -eq 0 ] || [ -n "$NOTICES" ] || exit 2\n\n# --ci never advances',
     _T + "test_an_in_budget_failure_beside_a_chronic_rule_exits_2[sh]"),
    ("the PowerShell gate lets a failure through beside a deferral", PS1,
     "\nif ($failed) { exit 2 }\n",
     "\nif ($failed -and $notices.Count -eq 0) { exit 2 }\n",
     _T + "test_an_in_budget_failure_beside_a_chronic_rule_exits_2[ps1]"),
    ("the diff baseline is never read, so a commit on main is out of scope", SH,
     'if [ -z "$BASE" ] && [ -f "$BASE_AT" ]; then\n',
     "if false; then\n",
     _T + "test_a_commit_on_the_default_branch_after_a_quiet_turn_is_in_scope[sh]"),
    ("the PowerShell gate never reads the diff baseline", PS1,
     "if (-not $base -and (Test-Path $baseAt)) {\n",
     "if ($false) {\n",
     _T + "test_a_commit_on_the_default_branch_after_a_quiet_turn_is_in_scope[ps1]"),
    ("a quiet turn records no diff baseline, so a commit on main is out of scope", SH,
     '    record_base || refuse_base_write\n  fi\n  exit 0\n',
     "    :\n  fi\n  exit 0\n",
     _T + "test_a_commit_on_the_default_branch_after_a_quiet_turn_is_in_scope[sh]"),
    # Review round 1 (Codex): the baseline's own guards, each both flavours.
    ("a baseline left on another branch is trusted", SH,
     '     && git merge-base --is-ancestor "$CAND" HEAD 2>/dev/null; then\n',
     "     && true; then\n",
     _T + "test_a_baseline_left_on_another_branch_is_not_used[sh]"),
    ("the PowerShell gate trusts a baseline left on another branch", PS1,
     "      $null | git merge-base --is-ancestor $cand HEAD 2>$null\n",
     "      $null | git cat-file -e \"$cand^{commit}\" 2>$null\n",
     _T + "test_a_baseline_left_on_another_branch_is_not_used[ps1]"),
    ("a zero-command turn moves the baseline past a committed change", SH,
     '     && git diff --quiet "$BASE" HEAD -- 2>/dev/null; then\n',
     "     && true; then\n",
     _T + "test_a_zero_command_turn_with_a_committed_change_keeps_the_baseline[sh]"),
    ("the PowerShell gate moves the baseline past a committed change", PS1,
     "    $null | git diff --quiet $base HEAD -- 2>$null\n",
     "    $null | git rev-parse HEAD 2>$null | Out-Null\n",
     _T + "test_a_zero_command_turn_with_a_committed_change_keeps_the_baseline[ps1]"),
    ("a baseline write that fails is a quiet success", SH,
     "    record_base || refuse_base_write\n  fi\n  exit 0\n",
     "    record_base || true\n  fi\n  exit 0\n",
     _T + "test_a_baseline_that_cannot_be_written_refuses_the_turn[sh]"),
    ("the PowerShell gate exits 0 when the baseline write fails", PS1,
     "      exit 2\n    }\n  }\n}\n\n# The twin of zero_rules_line",
     "    }\n  }\n}\n\n# The twin of zero_rules_line",
     _T + "test_a_baseline_that_cannot_be_written_refuses_the_turn[ps1]"),
    ("an unmapped failure that ran nothing does not say 0 rules ran", SH,
     'if [ "$FAILED" -ne 0 ] && [ "$CI_MODE" -eq 0 ] && ! printf',
     'if false && [ "$FAILED" -ne 0 ] && [ "$CI_MODE" -eq 0 ] && ! printf',
     _T + "test_an_unmapped_failure_with_no_command_still_says_0_rules_ran[sh]"),
    ("the PowerShell gate drops the 0-rules line on an unmapped failure", PS1,
     "if ($failed -and -not $Ci -and $cmds.Count -eq 0) { Write-ZeroRulesLine }\n",
     "",
     _T + "test_an_unmapped_failure_with_no_command_still_says_0_rules_ran[ps1]"),
    ("an old chronic record keeps its pre-CI reason", RECORD,
     "            and reason.endswith(_OLD_CHRONIC_TAIL)):\n",
     "            and reason.endswith(_OLD_CHRONIC_TAIL) and False):\n",
     _T + "test_an_old_chronic_record_is_reported_as_deferred_to_ci"),
)
