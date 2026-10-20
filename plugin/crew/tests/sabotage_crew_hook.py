"""The L-0727 mutations: the hook dispatcher and its launchers. Same tuple shape as
`sabotage.py`'s MUTATIONS -- (label, target, find, replace, test) -- and appended to
it there. Run `sabotage.py`, not this file.

`crew_hook.py` and the two launchers sit between Claude Code and every guard, so a
slip there turns a guard off without any guard's own suite noticing. Each one puts
back a way that could happen: a dropped row, an exit 2 lost through the extra
process layer, a deny lost in the merge, stdin bytes lost, a launcher that reads a
dispatcher crash as an allow, a guard timeout read as an allow, an "armed" answer
that fails open, a no-python list that forgets a script. Every target is a case in
the suites named below, and each label says what its mutation trips.

The last entry is the A3 freeze: a same-line-count behavioural edit to
`crew_autopilot_paste.py`, which a line count alone would let through.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(CREW, "hooks", "scripts")
HOOK = os.path.join(SCRIPTS, "crew_hook.py")
SH = os.path.join(SCRIPTS, "crew-hook.sh")
PS1 = os.path.join(SCRIPTS, "crew-hook.ps1")
PASTE = os.path.join(SCRIPTS, "crew_autopilot_paste.py")
CI = os.path.join(SCRIPTS, "crew_instructions.py")
_P = "tests/test_crew_hook_parity.py::"
_M = "tests/test_crew_hook_merge.py::"
_F = "tests/test_crew_hook_faults.py::"
_S = "tests/test_hooks_json_shape.py::"
_W = "tests/test_crew_hook_windows.py::"

CREW_HOOK_MUTATIONS = (
    ("a PreToolUse row (cloud-guard) is dropped from TABLE", HOOK,
     '    _row("PreToolUse", "Bash|PowerShell", "cloud-guard.sh", 15, guard=True, twin="cloud-guard.ps1"),\n',
     "",
     _P + "test_launcher_matches_the_golden_result[PreToolUse/bash-cloud-blocked.armed-sh]"),
    ("the dispatcher swallows a child's exit 2", HOOK,
     '    blockers = [r for r in results if r.get("exit") == 2]\n',
     '    blockers = [r for r in results if r.get("exit") == 99]\n',
     _M + "test_exit_2_from_any_child_wins_and_carries_every_blockers_stderr_in_order"),
    ("the dispatcher swallows exit 2 end to end (a restricted role is allowed)", HOOK,
     '    blockers = [r for r in results if r.get("exit") == 2]\n',
     '    blockers = [r for r in results if r.get("exit") == 99]\n',
     _P + "test_launcher_matches_the_golden_result[PreToolUse/write-restricted-role.armed-sh]"),
    ("a deny permissionDecision is dropped in the merge", HOOK,
     '_RANK = {"deny": 3, "ask": 2, "allow": 1}\n',
     '_RANK = {"deny": 0, "ask": 2, "allow": 1}\n',
     _M + "test_permission_decision_is_deny_over_ask_over_allow[decisions0-deny]"),
    ("plain text is dropped from the merge when another child emitted JSON", HOOK,
     "    if plain:\n        contexts.extend(plain)\n",
     "    if plain:\n        pass\n",
     _M + "test_plain_text_is_folded_into_additional_context_when_another_child_emitted_json"),
    ("stdin is forwarded without its first 3 bytes", HOOK,
     "            proc.stdin.write(raw)\n",
     "            proc.stdin.write(raw[3:])\n",
     _F + "test_run_child_forwards_stdin_bytes_exactly"),
    ("stdin without its first 3 bytes breaks a real guard payload", HOOK,
     "            proc.stdin.write(raw)\n",
     "            proc.stdin.write(raw[3:])\n",
     _P + "test_launcher_matches_the_golden_result[PreToolUse/write-in-touch.armed-sh]"),
    ("the sh launcher exits 0 on a dispatcher crash", SH,
     '_fail "crew_hook.py failed (exit $STATUS)"\n',
     "exit 0\n",
     _F + "test_a_fault_in_an_armed_repo_is_exit_2_naming_the_cause[syntax-error-before-main-own-sh]"),
    ("the sh launcher exits 0 when the dispatcher is killed at the deadline", SH,
     '    *) _fail "crew_hook.py failed (exit $STATUS)" ;;\n',
     "    *) exit 0 ;;\n",
     _F + "test_a_fault_in_an_armed_repo_is_exit_2_naming_the_cause[dispatcher-hangs-before-main-own-sh]"),
    ("the ps1 launcher exits 0 on a dispatcher crash", PS1,
     'Exit-Fault "crew_hook.py failed (exit $crewCode)"\n',
     "exit 0\n",
     _F + "test_a_fault_in_an_armed_repo_is_exit_2_naming_the_cause[syntax-error-before-main-own-ps1]"),
    ("a guard timeout is read as an allow", HOOK,
     "            if row.guard and event in BLOCKING_EVENTS:\n",
     "            if False and row.guard and event in BLOCKING_EVENTS:\n",
     _F + "test_a_fault_in_an_armed_repo_is_exit_2_naming_the_cause[guard-past-its-timeout-own-sh]"),
    ("a failed armed() resolution reads as unarmed", HOOK,
     "    except Exception:  # noqa: BLE001  pylint: disable=broad-exception-caught\n        return True\n",
     "    except Exception:  # noqa: BLE001  pylint: disable=broad-exception-caught\n        return False\n",
     _F + "test_armed_is_true_when_the_resolution_fails_or_cannot_tell"),
    ("the sh launcher's armed check ignores the machine-global config", SH,
     '              "$HOME/.claude/crew/config.json"; do\n',
     "              /nonexistent-home/.claude/crew/config.json; do\n",
     _F + "test_the_launcher_check_calls_armed_every_case_armed_calls_armed[sh]"),
    ("the sh launcher's no-python list forgets a script", SH,
     "    UserPromptSubmit) printf '%s\\n' 'crew-context.sh;;' 'approval-hook.sh;;' ;;\n",
     "    UserPromptSubmit) printf '%s\\n' 'crew-context.sh;;' ;;\n",
     _S + "test_the_no_python_list_in_crew_hook_sh_equals_the_table[UserPromptSubmit-claude]"),
    ("a PowerShell call on a POSIX host selects a twin", HOOK,
     "            twin_ok = bool(row.twin) and windows and tool == \"PowerShell\"",
     "            twin_ok = bool(row.twin) and tool == \"PowerShell\"",
     _W + "test_a_power_shell_call_off_windows_never_selects_a_twin"),
    ("an armed repo with no Git Bash is allowed on UserPromptSubmit", HOOK,
     "    if event in BLOCKING_EVENTS and armed_fn(root):\n        return 2, b\"\", (message",
     "    if False and event in BLOCKING_EVENTS and armed_fn(root):\n        return 2, b\"\", (message",
     _W + "test_armed_with_no_git_bash_the_blocking_events_exit_2_naming_git_for_windows[UserPromptSubmit]"),
    # Security pass (L-0850): BLOCK 1 (an environment variable stood every guard down) and BLOCK 2
    # (a crashed guard came back as exit 1 and was retried with an empty payload), and what they touched.
    ("a child's odd exit comes back from the merge as exit 1 again (the launcher then retries)", HOOK,
     "    code = 0\n    parsed = ",
     "    failed = [r for r in results if r.get(\"exit\") not in (0, 2, None)]\n"
     "    code = 1 if failed and not live else 0\n    parsed = ",
     _M + "test_the_merge_only_ever_says_0_or_2_whatever_the_children_exited"),
    ("a guard that exits 1 without a decision is read as an allow", HOOK,
     'undecided = not res["error"] and not res["timed_out"] and res["exit"] not in (0, 2)',
     'undecided = not res["error"] and not res["timed_out"] and res["exit"] not in (0, 1, 2)',
     _F + "test_a_guard_that_exits_without_a_decision_is_a_fault_when_armed[1-own-sh]"),
    ("the sh launcher stands down on OS=Windows_NT whatever uname says", SH,
     "  Linux|Darwin|FreeBSD|OpenBSD|NetBSD|DragonFly|SunOS|AIX) ;;\n",
     "",
     _W + "test_an_os_variable_cannot_stand_the_guards_down_on_a_posix_host"),
    ("the sh launcher's armed check does not treat an unset HOME as armed", SH,
     '  [ -n "${HOME:-}" ] || return 0\n',
     "",
     _F + "test_the_sh_launcher_check_is_armed_when_home_is_unset"),
    ("the no-python path waits on a wedged guard with no deadline", SH,
     '  _watchdog "$((left + 2))" $pids\n',
     '  _watchdog 600 $pids\n',
     _F + "test_with_no_python_a_wedged_guard_is_a_fault_at_the_deadline[own-True]"),
    ("the no-python path ignores a guard that crashed", SH,
     '      *) script="${names[$((i - 1))]}"; fault="$fault $script exited $rc without a decision;" ;;\n',
     "      *) ;;\n",
     _F + "test_with_no_python_the_approval_hook_crashing_is_a_fault_on_user_prompt_submit[own-True]"),
    ("CREW_HOOK_TRACE_FILE is honoured for any path", HOOK,
     '    if not path or not path.endswith(TRACE_SUFFIX):\n',
     '    if not path:\n',
     _F + "test_a_trace_path_without_the_suffix_is_never_written[trace.txt]"),
    ("the ps1 launcher trusts only the OS environment variable", PS1,
     "[System.PlatformID]::Win32NT) { $env:OS = 'Windows_NT' })",
     "[System.PlatformID]::Unix) { $env:OS = 'Windows_NT' })",
     _S + "test_the_ps1_flavour_guard_trusts_the_platform_not_only_the_environment"),
    # Review round (Kimi, 2026-10-20): the Codex rows must come from TABLE, and a matcher the no-python
    # path cannot judge must run its row.
    ("the Codex hook rows are a copy that leaves a TABLE row out", CI,
     "    for row in crew_hook.TABLE if row.codex is not None)\n",
     "    for row in crew_hook.TABLE if row.codex is not None and row.event != \"SubagentStart\")\n",
     _S + "test_instruction_generator_codex_rows_are_derived_from_the_table_not_copied"),
    ("the no-python matcher skips a row whose matcher it cannot judge", SH,
     "    *[!A-Za-z0-9_\\|]*) return 0 ;;\n",
     "",
     _S + "test_the_no_python_tool_matcher_runs_a_row_it_cannot_judge[mcp__.*(x|y)-Read-True]"),
    ("a same-line-count behavioural edit to a frozen autopilot module", PASTE,
     '"\\\\u0020" * len(run.group())',
     '"\\\\u0021" * len(run.group())',
     "tests/test_autopilot_frozen.py::test_no_autopilot_module_has_changed"),
)
