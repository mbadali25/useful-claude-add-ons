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
     '              "${HOME:-/nonexistent-home}/.claude/crew/config.json"; do\n',
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
    ("a same-line-count behavioural edit to a frozen autopilot module", PASTE,
     '"\\\\u0020" * len(run.group())',
     '"\\\\u0021" * len(run.group())',
     "tests/test_autopilot_frozen.py::test_no_autopilot_module_has_changed"),
)
