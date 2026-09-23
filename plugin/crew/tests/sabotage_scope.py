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
HOOK = os.path.join(_S, "approval_hook.py")
GUARD_SH = os.path.join(_S, "scope-guard.sh")
GUARD_PS1 = os.path.join(_S, "scope-guard.ps1")
AUDIT_SH = os.path.join(_S, "completion-audit.sh")
AUDIT_PS1 = os.path.join(_S, "completion-audit.ps1")
HOOK_SH = os.path.join(_S, "approval-hook.sh")

_SG = "tests/test_scope_guard.py::"
_CA = "tests/test_completion_audit.py::"
_CT = "tests/test_crew_ticket.py::"
_AH = "tests/test_approval_hook.py::"

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
     '    if mode == "block":\n        return _deny([f"SCOPE GUARD: refused {data.get(',
     '    if mode != "off":\n        return _deny([f"SCOPE GUARD: refused {data.get(',
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
     '    outside = [p for p in paths if not crew_ticket.in_touch(p, approval["touch"])]\n',
     "    outside = []\n",
     _CA + "test_a_shell_made_out_of_scope_file_blocks_the_stop[module]"),
    ("the audit drops the source end of a rename", AUDIT,
     "        paths.update(p for p in fields[i + 1:i + 1 + width] if p)\n",
     "        paths.update(p for p in fields[i + width:i + 1 + width] if p)\n",
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
     "(exit $status); failing closed because .crew/config.json does not provably set "
     "scope.mode off.\" >&2\n  exit 2\n",
     "(exit $status); failing closed because .crew/config.json does not provably set "
     "scope.mode off.\" >&2\n  exit 0\n",
     _CA + "test_a_crashed_python_fails_closed_only_where_scope_is_armed[block-2-sh-scope-guard]"),
    ("the PowerShell guard fails open when python crashes", GUARD_PS1,
     "(exit $exitCode); failing closed because .crew/config.json does not provably set "
     "scope.mode off.\")\n  exit 2\n",
     "(exit $exitCode); failing closed because .crew/config.json does not provably set "
     "scope.mode off.\")\n  exit 0\n",
     _CA + "test_a_crashed_python_fails_closed_only_where_scope_is_armed[block-2-ps1-scope-guard]"),
    ("the bash audit fails open when python crashes", AUDIT_SH,
     '  _block_once "completion_audit.py did not run to a verdict (exit $status); nothing was '
     'audited."\n',
     "  exit 0\n",
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
    # --- the T3 fix round -------------------------------------------------------
    ("approve hashes a later read than the one it validated", TICKET,
     '    plan_sha, spec_sha = _sha(contract["plan.md"]), _sha(contract["spec.md"])\n',
     "    plan_sha, spec_sha = current_hashes(top, ticket)\n",
     _CT + "test_approve_hashes_the_bytes_it_validated_not_a_later_version"),
    ("the guard reads Touch separately from the approval", GUARD,
     '(p,) + classify(top, common, ticket, approval["touch"], approval, p, base)',
     "(p,) + classify(top, common, ticket, crew_ticket.touch_for(top, ticket), approval, p, "
     "base)",
     _SG + "test_touch_is_judged_from_the_bytes_the_approval_hashed[module]"),
    ("a broken active-ticket pointer reads as no ticket", TICKET,
     '        return None, (f"active-ticket names {ticket!r}, which has no .work/tickets/ "\n'
     '                      "directory"), True\n',
     '        return None, (f"active-ticket names {ticket!r}, which has no .work/tickets/ "\n'
     '                      "directory"), False\n',
     _SG + "test_a_pointer_to_a_missing_ticket_is_refused_not_ignored[T-404-module]"),
    ("an unparseable payload under auto past the ramp is allowed", GUARD,
     "    return crew_ticket.effective_mode(root, ticket)[0]\n",
     '    return "report"\n',
     _SG + "test_an_unparseable_payload_under_auto_past_the_ramp_is_refused[module]"),
    ("a cli receipt satisfies the guard", TICKET,
     "    if via == USER_PROMPT or cli_approval_allowed(",
     "    if True or cli_approval_allowed(",
     _SG + "test_a_cli_approval_does_not_open_touch[module]"),
    ("the session may run crew_ticket.py approve", GUARD,
     "    if _APPROVE_RE.search(command):\n",
     "    if False:\n",
     _SG + "test_a_shell_command_forging_approval_state_is_refused"
     "[Bash-python3 hooks/scripts/crew_ticket.py approve --ticket T-1-module]"),
    ("the session may write crew's state through the shell", GUARD,
     "    if names_state and _WRITES_RE.search(command):\n",
     "    if False:\n",
     _SG + "test_a_shell_write_to_the_absolute_state_path_is_refused[module]"),
    ("the bash no-python reader accepts any mode as off", GUARD_SH,
     "grep -Eq '\"mode\"[[:space:]]*:[[:space:]]*\"off\"'",
     "grep -Eq '\"mode\"[[:space:]]*:[[:space:]]*\"[a-z]*\"'",
     _CA + "test_a_crashed_python_fails_closed_unless_scope_is_provably_off[bogus-sh-scope-guard]"),
    ("the PowerShell no-python reader accepts any mode as off", GUARD_PS1,
     "return [bool]($obj -match '\"mode\"\\s*:\\s*\"off\"')",
     "return [bool]($obj -match '\"mode\"\\s*:\\s*\"[a-z]*\"')",
     _CA + "test_a_crashed_python_fails_closed_unless_scope_is_provably_off"
     "[bogus-ps1-scope-guard]"),
    ("the bash audit misses stop_hook_active across a newline", AUDIT_SH,
     "if printf '%s' \"$INPUT\" | tr -d '\\r\\n' \\\n",
     "if printf '%s' \"$INPUT\" \\\n",
     _CA + "test_stop_hook_active_is_seen_in_any_json_whitespace_even_when_python_crashes"
     "[newline-tab-sh]"),
    ("the bash audit blocks every stop while python is broken", AUDIT_SH,
     '  if [ -e "$marker" ]; then\n',
     "  if false; then\n",
     _CA + "test_a_crashed_python_never_blocks_two_stops_in_a_row[sh]"),
    ("the PowerShell audit blocks every stop while python is broken", AUDIT_PS1,
     "  if (Test-Path -LiteralPath $marker) {\n",
     "  if ($false) {\n",
     _CA + "test_a_crashed_python_never_blocks_two_stops_in_a_row[ps1]"),
    ("the successor approval is not rechecked under the lock", LEDGER,
     "        receipt, why = _plan_approval_receipt(root, ticket, plan_hash)\n"
     "        if receipt is None:\n"
     '            return None, (False, f"refused: {why}; {NEEDS_REPLAN} stands")\n',
     "",
     _CT + "test_the_successor_approval_is_rechecked_under_the_ledger_lock"),
    ("the Stop audit builds the whole review bundle", AUDIT,
     "    copy. Names only -- no blob or patch content is read.\"\"\"\n",
     "    copy. Names only -- no blob or patch content is read.\"\"\"\n"
     "    __import__(\"review_patch\").compute(top, base)\n",
     _CA + "test_the_audit_lists_paths_without_building_the_review_bundle"),
    ("a filename's newline reaches the hook message", AUDIT,
     '    return "".join(c if c.isprintable() else\n',
     '    return "".join(c if True else\n',
     _CA + "test_a_filename_with_newlines_cannot_add_lines[module]"),
    ("the six-line cap counts logical lines", AUDIT,
     '    return "\\n".join(lines).splitlines()[:MAX_LINES]\n',
     "    return lines[:MAX_LINES]\n",
     _CA + "test_physical_caps_lines_whatever_they_contain"),
    ("a '*' in Touch crosses '/'", TICKET,
     "    if glob_match(path, glob):\n        return True\n",
     "    if gate_matches(path, glob):\n        return True\n",
     _CT + "test_a_star_never_crosses_a_slash[src/a/b.py-src/*.py-False]"),
    ("a Touch '*' covers a plan '**'", TICKET,
     '        if j == len(names) or (plan and "**" in names[j]):\n',
     "        if j == len(names):\n",
     _CT + "test_a_plan_glob_cannot_widen_touch_through_a_slash[src/**-touch1-False]"),
    ("the approval hook records a mid-sentence mention", HOOK,
     "    raw = _RAW_RE.match(prompt)\n",
     '    raw = re.search(r"/crew:approve(?:\\s+(\\S+))?", prompt)\n',
     _AH + "test_a_prompt_that_is_not_the_command_passes_untouched"
     "[should I run /crew:approve T-1 now?-module]"),
    ("the approval hook writes a cli receipt", HOOK,
     "            root, ticket, via=crew_ticket.USER_PROMPT,",
     "            root, ticket, via=crew_ticket.CLI,",
     _AH + "test_the_users_prompt_records_a_user_prompt_receipt[module]"),
    ("the bash approval hook lets an unrecorded approval through", HOOK_SH,
     "no usable python to validate the plan.\" >&2\n  exit 2\n",
     "no usable python to validate the plan.\" >&2\n  exit 0\n",
     _AH + "test_without_python_only_an_approve_prompt_is_blocked[/crew:approve T-1-2-sh]"),
)
