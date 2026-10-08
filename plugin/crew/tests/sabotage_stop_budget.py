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
     '  [ "$BASE_FROM_MARKER" -eq 1 ] || record_base\n',
     "  record_verified\n",
     _T + "test_zero_rules_ran_does_not_advance_an_existing_marker[sh]"),
    ("the PowerShell gate advances the marker on an empty changed set", PS1,
     "  if (-not $baseFromMarker) { Write-CrewBase }\n  exit 0\n",
     "  Write-CrewVerified\n  exit 0\n",
     _T + "test_zero_rules_ran_does_not_advance_an_existing_marker[ps1]"),
    ("a turn that selected no command writes the verified marker (acceptance 6b)", SH,
     "    record_base\n  fi\nelif",
     "    record_verified\n  fi\nelif",
     _T + "test_a_changed_file_matching_nothing_runnable_says_0_rules_ran[sh]"),
    ("the PowerShell gate writes the marker when no command was selected", PS1,
     "  if ($fullyVerified -and -not $baseFromMarker) { Write-CrewBase }\n} elseif",
     "  if ($fullyVerified -and -not $baseFromMarker) { Write-CrewVerified }\n} elseif",
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
     '  [ "$BASE_FROM_MARKER" -eq 1 ] || record_base\n',
     "  :\n",
     _T + "test_a_commit_on_the_default_branch_after_a_quiet_turn_is_in_scope[sh]"),
)
