"""The crew 1.0 T3 mutations: plan approval, the scope guard and the
completion audit. Same tuple shape as `sabotage.py`'s MUTATIONS --
(label, target, find, replace, test) -- and meant to be appended to it by the
integration step; `sabotage.py` sits at `.pylintrc`'s max-module-lines, so
this list lives apart. Run `sabotage.py`, not this file.

Every entry was also run by hand against the working tree: the target copied
to a scratch file, the mutation applied, the named test run and seen to FAIL,
the scratch copy `cp`'d back and `diff`ed clean.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_S = os.path.join(CREW, "hooks", "scripts")
GUARD = os.path.join(_S, "scope_guard.py")
TICKET = os.path.join(_S, "crew_ticket.py")
AUDIT = os.path.join(_S, "completion_audit.py")
LEDGER = os.path.join(_S, "review_ledger.py")
GUARD_SH = os.path.join(_S, "scope-guard.sh")
GUARD_PS1 = os.path.join(_S, "scope-guard.ps1")
AUDIT_SH = os.path.join(_S, "completion-audit.sh")

_SG = "tests/test_scope_guard.py::"
_CA = "tests/test_completion_audit.py::"
_CT = "tests/test_crew_ticket.py::"

SCOPE_MUTATIONS = (
    ("the scope guard allows an edit with no approved plan", GUARD,
     '    if approval["status"] != "approved":\n        return False, (f"{ticket}: ',
     '    if False:\n        return False, (f"{ticket}: ',
     _SG + "test_edit_with_no_approved_plan_is_blocked[module]"),
    ("an approval stays current after the spec changes", TICKET,
     "    if changed:\n",
     "    if False:\n",
     _SG + "test_edit_after_the_spec_changed_is_blocked_as_stale[module]"),
    ("the scope guard no longer checks Touch", GUARD,
     "    outside = [r for r in checks if not crew_ticket.in_touch(r, touch)]\n",
     "    outside = []\n",
     _SG + "test_a_path_outside_touch_is_blocked_for_every_editing_tool[Write-module]"),
    ("the scope guard judges the named path, not the symlink target", GUARD,
     "    real = role_write_guard._resolve_real_target(absolute)  # pylint: "
     "disable=protected-access\n    named = os.path.normpath(absolute)\n    real_rel,",
     "    real = os.path.normpath(absolute)\n    named = os.path.normpath(absolute)\n"
     "    real_rel,",
     _SG + "test_a_symlink_inside_touch_pointing_out_of_scope_is_blocked[module]"),
    ("the scope guard ignores the named path of a link into scope", GUARD,
     "    checks = [r for r in (real_rel, named_rel) if r is not None]\n",
     "    checks = [r for r in (real_rel,) if r is not None]\n",
     _SG + "test_a_symlink_outside_touch_pointing_into_scope_is_blocked[module]"),
    ("the scope guard collapses '..' before following symlinks", GUARD,
     "    real = role_write_guard._resolve_real_target(absolute)  # pylint: "
     "disable=protected-access\n    named = os.path.normpath(absolute)\n    real_rel,",
     "    real = os.path.realpath(os.path.normpath(absolute))\n"
     "    named = os.path.normpath(absolute)\n    real_rel,",
     _SG + "test_dotdot_through_a_symlink_resolves_where_the_os_does[module]"),
    ("approval and ledger state lose their protection", GUARD,
     "        if state and _under(path, state):\n            return True\n",
     "        if False:\n            return True\n",
     _SG + "test_approval_state_is_blocked_even_in_report_mode[module]"),
    ("the scope base record loses its protection", GUARD,
     "        if rel is not None and os.path.normcase(rel) == os.path.normcase(SCOPE_BASE):\n",
     "        if False:\n",
     _SG + "test_the_scope_base_record_is_blocked[module]"),
    ("the git directory can be put in scope", GUARD,
     "    if common and (_under(real, common) or _under(named, common)):\n",
     "    if False:\n",
     _SG + "test_the_git_directory_is_never_in_scope[module]"),
    ("a payload naming no path is allowed", GUARD,
     '        verdicts = [("-", False, reason)]\n',
     '        verdicts = [("-", True, reason)]\n',
     _SG + "test_a_payload_naming_no_path_is_blocked[module]"),
    ("report mode blocks", GUARD,
     '    if mode == "block":\n        return _deny([f"SCOPE GUARD: refused',
     '    if mode != "off":\n        return _deny([f"SCOPE GUARD: refused',
     _SG + "test_report_mode_allows_logs_and_says_so[module]"),
    ("a corrupt config reads as off", TICKET,
     '        return "block", ".crew/config.json exists but does not parse; failing closed"\n',
     '        return "off", ".crew/config.json exists but does not parse; failing closed"\n',
     _SG + "test_a_corrupt_config_fails_closed[module]"),
    ("auto never ramps to block", TICKET,
     "    if position < RAMP_TICKETS:\n",
     "    if True:\n",
     _SG + "test_auto_reports_for_the_first_ten_tickets_then_blocks[module]"),
    ("validate lets a plan path widen Touch", TICKET,
     "        if touch and not covered_by(entry, touch):\n",
     "        if False:\n",
     _CT + "test_plan_files_outside_touch_fail_validate"),
    ("a '?' in Touch covers a '*' in the plan", TICKET,
     '        star_only = "?" not in glob and "[" not in glob\n',
     "        star_only = True\n",
     _CT + "test_a_plan_glob_is_accepted_only_when_it_cannot_widen_touch[touch4-files4-False]"),
    ("the audit no longer checks Touch", AUDIT,
     "    outside = [p for p in paths if not crew_ticket.in_touch(p, touch)]\n",
     "    outside = []\n",
     _CA + "test_a_shell_made_out_of_scope_file_blocks_the_stop[module]"),
    ("the audit drops the source end of a rename", AUDIT,
     '        if entry.get("status") == "R" and entry.get("old_path") != entry["path"]:\n',
     "        if False:\n",
     _CA + "test_a_rename_from_out_of_scope_into_scope_blocks_too[module]"),
    ("the audit re-blocks a stop_hook_active continuation", AUDIT,
     '    if data.get("stop_hook_active") is True:\n        return 0\n',
     "    if False:\n        return 0\n",
     _CA + "test_stop_hook_active_never_re_blocks[module]"),
    ("the audit trusts an unapproved Touch", AUDIT,
     '    if approval["status"] != "approved":\n        return False, [f"COMPLETION AUDIT',
     '    if False:\n        return False, [f"COMPLETION AUDIT',
     _CA + "test_changes_under_a_stale_approval_block[module]"),
    ("the bash guard fails open when python crashes", GUARD_SH,
     "failing closed because scope.mode is block or auto.\" >&2\n    exit 2\n  fi\n"
     "  echo \"scope-guard: scope_guard.py",
     "failing closed because scope.mode is block or auto.\" >&2\n    exit 0\n  fi\n"
     "  echo \"scope-guard: scope_guard.py",
     _CA + "test_a_crashed_python_fails_closed_only_where_scope_is_armed[block-2-sh-scope-guard]"),
    ("the PowerShell guard fails open when python crashes", GUARD_PS1,
     "(exit $exitCode); failing closed because scope.mode is block or auto.\")\n    exit 2\n",
     "(exit $exitCode); failing closed because scope.mode is block or auto.\")\n    exit 0\n",
     _CA + "test_a_crashed_python_fails_closed_only_where_scope_is_armed[block-2-ps1-scope-guard]"),
    ("the bash audit fails open when python crashes", AUDIT_SH,
     "did not run to a verdict (exit $status); nothing was audited.\" >&2\n    exit 2\n",
     "did not run to a verdict (exit $status); nothing was audited.\" >&2\n    exit 0\n",
     _CA + "test_a_crashed_python_fails_closed_only_where_scope_is_armed"
     "[block-2-sh-completion-audit]"),
    ("the same plan re-approved counts as a successor", LEDGER,
     "    if plan_hash in crew_ticket.earlier_plan_hashes(root, ticket):\n",
     "    if False:\n",
     _CT + "test_reapproving_the_same_plan_is_not_a_successor"),
    ("findings from before the successor can still be accepted", LEDGER,
     '        if len(rounds) - _spent(data) >= row.get("round", 0):\n',
     "        if False:\n",
     _CT + "test_findings_from_before_the_successor_cannot_be_accepted"),
    ("a round from before the successor can still be recorded", LEDGER,
     "        if len(rounds) - _spent(data) >= number:\n",
     "        if False:\n",
     _CT + "test_a_round_from_before_the_successor_cannot_be_recorded"),
)
