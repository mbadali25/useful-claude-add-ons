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
MERGED_MAIN = os.path.join(_S, "merged_main.py")
# T-0061: the ticket base branch (`tickets.baseBranch`).
SCOPE_BASE_PY = os.path.join(_S, "scope_base.py")

_SG = "tests/test_scope_guard.py::"
_CA = "tests/test_completion_audit.py::"
_CT = "tests/test_crew_ticket.py::"
_AH = "tests/test_approval_hook.py::"
_AD = "tests/test_approval_digest.py::"
_MM = "tests/test_merged_main.py::"

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
     "        names = [p for p in fields[i + 1:i + 1 + width] if p]\n",
     "        names = [p for p in fields[i + width:i + 1 + width] if p]\n",
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
     _CA + "test_a_crashed_python_fails_closed_only_where_scope_is_armed[block-2-2-sh-scope-guard]"),
    ("the PowerShell guard fails open when python crashes", GUARD_PS1,
     "(exit $exitCode); failing closed because .crew/config.json does not provably set "
     "scope.mode off.\")\n  exit 2\n",
     "(exit $exitCode); failing closed because .crew/config.json does not provably set "
     "scope.mode off.\")\n  exit 0\n",
     _CA + "test_a_crashed_python_fails_closed_only_where_scope_is_armed[block-2-2-ps1-scope-guard]"),
    ("the bash audit fails open when python crashes", AUDIT_SH,
     '  _block_once "completion_audit.py did not run to a verdict (exit $status); nothing was '
     'audited."\n',
     "  exit 0\n",
     _CA + "test_a_crashed_python_fails_closed_only_where_scope_is_armed"
     "[block-2-2-sh-completion-audit]"),
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
    ("the PowerShell no-python reader accepts any mode as off", GUARD_PS1,
     "      return ($mode.GetString() -ceq 'off')\n",
     "      return $true\n",
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
     "    bundle, and never a write to the index.\"\"\"\n",
     "    bundle, and never a write to the index.\"\"\"\n"
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
    # --- the T3 fail-closed round (0.20.26) --------------------------------------
    ("the bash guard reads a present config as off without python", GUARD_SH,
     '  [ -e "$cfg" ] || [ -L "$cfg" ] || return 0\n  return 1\n',
     '  [ -e "$cfg" ] || [ -L "$cfg" ] || return 0\n  return 0\n',
     _CA + "test_no_python_fails_closed_unless_scope_is_provably_off"
     "[trailing-comma-sh-scope-guard]"),
    ("the bash audit reads a present config as off without python", AUDIT_SH,
     '  [ -e "$cfg" ] || [ -L "$cfg" ] || return 0\n  return 1\n',
     '  [ -e "$cfg" ] || [ -L "$cfg" ] || return 0\n  return 0\n',
     _CA + "test_no_python_fails_closed_unless_scope_is_provably_off"
     "[trailing-comma-sh-completion-audit]"),
    ("the PowerShell guard parses the config leniently", GUARD_PS1,
     "    $doc = [System.Text.Json.JsonDocument]::Parse($text)\n",
     "    $doc = [System.Text.Json.JsonDocument]::Parse($text, "
     "[System.Text.Json.JsonDocumentOptions]@{ AllowTrailingCommas = $true })\n",
     _CA + "test_no_python_fails_closed_unless_scope_is_provably_off"
     "[trailing-comma-ps1-scope-guard]"),
    ("the PowerShell audit parses the config leniently", AUDIT_PS1,
     "    $doc = [System.Text.Json.JsonDocument]::Parse($text)\n",
     "    $doc = [System.Text.Json.JsonDocument]::Parse($text, "
     "[System.Text.Json.JsonDocumentOptions]@{ AllowTrailingCommas = $true })\n",
     _CA + "test_no_python_fails_closed_unless_scope_is_provably_off"
     "[trailing-comma-ps1-completion-audit]"),
    ("the PowerShell reader takes the first of two scope keys", GUARD_PS1,
     "      if ($scopes.Count -ne 1) { return $false }\n",
     "      if ($scopes.Count -lt 1) { return $false }\n",
     _CA + "test_no_python_fails_closed_unless_scope_is_provably_off"
     "[escaped-duplicate-scope-ps1-scope-guard]"),
    ("a cli receipt continues a NEEDS_REPLAN ledger", LEDGER,
     "    result = crew_ticket.accepted(root, ticket)\n",
     "    result = crew_ticket.status(root, ticket)\n",
     _CT + "test_a_cli_approval_does_not_continue_needs_replan_without_allow_cli"),
    ("a malformed /crew:approve payload passes as an unrelated prompt", HOOK,
     "        if data is None and COMMAND.encode() in raw:\n",
     "        if False:\n",
     _AH + "test_a_malformed_payload_naming_the_command_is_refused[truncated-module]"),
    ("the bash approval hook lets an unrecorded approval through", HOOK_SH,
     "no usable python to validate the plan.\" >&2\n  exit 2\n",
     "no usable python to validate the plan.\" >&2\n  exit 0\n",
     _AH + "test_without_python_only_an_approve_prompt_is_blocked[/crew:approve T-1-2-sh]"),
    # --- T-0026: the approval digest normalises the header's status value only ---
    ("APPROVAL DIGEST: the whole first line is normalised", TICKET,
     "    return head[:start] + _STATUS_PLACEHOLDER + head[end:] + rest, True\n",
     "    return _STATUS_PLACEHOLDER + rest, True\n",
     _AD + "test_risk_change_stales_approval"),
    ("APPROVAL DIGEST: every line's status value is normalised", TICKET,
     "    return head[:start] + _STATUS_PLACEHOLDER + head[end:] + rest, True\n",
     ('    return re.sub(rb"(?m)((?<=[ \\t])status:[ \\t]+)(?:" + _STATUS_ALTERNATION\n'
      '                  + rb")(?=[ \\t\\r]|$)", rb"\\1<status>", data), True\n'),
     _AD + "test_second_status_line_in_body_stales_approval[value-changed]"),
    ("APPROVAL DIGEST: the bytes after line 1 are dropped", TICKET,
     "    return head[:start] + _STATUS_PLACEHOLDER + head[end:] + rest, True\n",
     "    return head[:start] + _STATUS_PLACEHOLDER + head[end:], True\n",
     _AD + "test_body_line_change_stales_approval"),
    ("APPROVAL DIGEST: line endings are normalised", TICKET,
     '    cut = _line_one_end(data)\n',
     '    data = data.replace(b"\\r\\n", b"\\n")\n    cut = _line_one_end(data)\n',
     _AD + "test_crlf_to_lf_stales_approval"),
    ("APPROVAL DIGEST: leading blank lines are skipped to find the header", TICKET,
     ('    cut = _line_one_end(data)\n'
      '    head, rest = (data, b"") if cut < 0 else (data[:cut], data[cut:])\n'),
     ('    lead = len(data) - len(data.lstrip(b"\\n"))\n'
      '    cut = data.find(b"\\n", lead)\n'
      '    head, rest = (data[lead:], b"") if cut < 0 else (data[lead:cut], data[cut:])\n'),
     _AD + "test_header_not_on_line_one_is_not_normalised[blank-first-line]"),
    ("APPROVAL DIGEST: any value is normalised, not the closed list", TICKET,
     '(" + _STATUS_ALTERNATION + rb")',
     '(" + rb"\\S+" + rb")',
     _AD + "test_status_value_outside_vocabulary_stales_approval[unknown-value]"),
    ("APPROVAL DIGEST: the value needs no boundary after it", TICKET,
     'rb")(?=[ \\t]|\\Z)")',
     'rb")")',
     _AD + "test_status_value_outside_vocabulary_stales_approval[suffixed-value]"),
    ("APPROVAL DIGEST: the token needs no boundary before it", TICKET,
     'rb"(?<=[ \\t])status:',
     'rb"status:',
     _AD + "test_status_token_glued_to_a_word_is_not_normalised"),
    ("APPROVAL DIGEST: line 1 need not be a # header", TICKET,
     '    if not body.startswith(b"# "):\n',
     "    if False:\n",
     _AD + "test_header_not_on_line_one_is_not_normalised[no-hash]"),
    ("APPROVAL DIGEST: a header with two status tokens is normalised", TICKET,
     '    if head.lower().count(b"status:") != 1:\n',
     "    if False:\n",
     _AD + "test_second_status_token_in_header_stales_approval[present-at-approval]"),
    ("APPROVAL DIGEST: the preimage drops the normalised/raw flag", TICKET,
     '    flag = b"normalised" if normalised else b"raw"\n',
     '    flag = b"raw"\n',
     _AD + "test_placeholder_literal_does_not_match_normalised"),
    ("APPROVAL DIGEST: a receipt with no digest is read as /2", TICKET,
     '    scheme = receipt.get("digest", _V1)\n',
     '    scheme = receipt.get("digest", DIGEST_SCHEME)\n',
     _AD + "test_receipt_without_digest_verifies_unchanged_files"),
    ("APPROVAL DIGEST: an unknown digest scheme is read as /2", TICKET,
     "    elif scheme == DIGEST_SCHEME:\n",
     "    elif True:\n",
     _AD + "test_unknown_digest_scheme_is_stale[crew-approval/9]"),
    ("APPROVAL DIGEST: a /2 receipt missing a digest falls back to raw", TICKET,
     ('            return {"status": "stale", "receipt": receipt, "touch": [],\n'
      '                    "why": (f"the approval receipt has no usable {\' or \'.join(unusable)}; "\n'
      '                            "approve again")}\n'),
     '            measure, keys = _sha, ("plan_sha256", "spec_sha256")\n',
     _AD + "test_a_v2_receipt_without_a_usable_digest_is_stale_not_raw[missing]"),
    # --- T-0026 review round 2 ---------------------------------------------------
    ("APPROVAL DIGEST: nothing is normalised", TICKET,
     '    cut = _line_one_end(data)\n',
     '    return data, False\n    cut = _line_one_end(data)\n',
     _AD + "test_metrics_reads_approval_after_status_done"),
    ("APPROVAL DIGEST: approve digests a later read of plan.md than it validated", TICKET,
     'approval_digest(contract["plan.md"])',
     'approval_digest(read_contract(top, ticket)["plan.md"])',
     _AD + "test_approve_digests_the_bytes_it_validated_not_a_later_version"),
    ("APPROVAL DIGEST: approve digests a later read of spec.md than it validated", TICKET,
     'approval_digest(contract["spec.md"])',
     'approval_digest(read_contract(top, ticket)["spec.md"])',
     _AD + "test_approve_digests_the_bytes_it_validated_not_a_later_version"),
    # --- T-0026 review round 3 ---------------------------------------------------
    ("APPROVAL DIGEST: line 1 split only on \\n", TICKET,
     '    cut = _line_one_end(data)\n',
     '    cut = data.find(b"\\n")\n',
     _AD + "test_body_status_line_after_a_non_lf_break_stales_approval"
     "[bare-cr-trailing-space]"),
    # --- T-0100: paths identical to merged main (merged_main.py, the audit) ----
    # Each run by hand against the tracked file, restored with `git checkout`.
    ("MERGED MAIN: a merge older than the ticket start still applies", MERGED_MAIN,
     "    if before:\n",
     "    if before and False:\n",
     _MM + "test_no_merge_past_the_start_changes_nothing"),
    ("MERGED MAIN: no integration ref falls through to merge-base HEAD HEAD", MERGED_MAIN,
     '    if not ref:\n        return {"ref": None,',
     '    ref = ref or "HEAD"\n    if False:\n        return {"ref": None,',
     _MM + "test_could_not_tell_drops_nothing[no-ref]"),
    ("MERGED MAIN: HEAD on the integration branch still applies", MERGED_MAIN,
     '    if branch in (ref, ref.removeprefix("origin/")):\n',
     "    if False:\n",
     _MM + "test_head_on_the_integration_branch_never_applies"),
    ("MERGED MAIN: keep drops nothing", MERGED_MAIN,
     "    return sorted(set(since_base) & set(since_merged))\n",
     "    return sorted(set(since_base))\n",
     _CA + "test_paths_identical_to_merged_main_are_not_out_of_scope[module]"),
    ("MERGED MAIN: keep drops what differs from merged main instead", MERGED_MAIN,
     "    return sorted(set(since_base) & set(since_merged))\n",
     "    return sorted(set(since_base) - set(since_merged))\n",
     _CA + "test_a_ticket_edit_on_top_of_merged_mains_edit_stays_flagged[module]"),
    ("the audit drops an untracked file after a merge of main", AUDIT,
     '    since_merged = worktree_changes(top, merged["commit"], _ONLY[1:]) | untracked\n',
     '    since_merged = worktree_changes(top, merged["commit"], _ONLY[1:])\n',
     _CA + "test_an_untracked_out_of_touch_file_after_a_merge_of_main_still_blocks"),
    ("the audit never passes the merged commit on", AUDIT,
     "        paths = changed_paths(top, base, merged)\n",
     "        paths = changed_paths(top, base, None)\n",
     _CA + "test_paths_identical_to_merged_main_are_not_out_of_scope[module]"),
    # --- T-0100 review round 1: every merged-main check gets a mutation --------
    # Each run by hand in the foreground against the tracked file, restored with
    # `git checkout --`; the output is in .work/tickets/T-0100/sabotage-r1.txt.
    ("MERGED MAIN: an ancestry check with no answer applies", MERGED_MAIN,
     "    if before is None:\n",
     "    if False:\n",
     _MM + "test_could_not_tell_drops_nothing[is-ancestor-fails]"),
    ("MERGED MAIN: a detached HEAD is read as a branch", MERGED_MAIN,
     '    if not branch:\n        return {"ref": ref, "commit": None,',
     '    if False:\n        return {"ref": ref, "commit": None,',
     _MM + "test_could_not_tell_drops_nothing[detached-head]"),
    ("MERGED MAIN: a merge-base with no answer falls through to HEAD", MERGED_MAIN,
     "    if not commit:\n",
     '    commit = commit or "HEAD"\n    if False:\n',
     _MM + "test_could_not_tell_drops_nothing[merge-base-fails]"),
    # On T-0061's base branch: a configured `tickets.baseBranch` naming no
    # commit must stay could-not-tell, never fall back to origin/main.
    ("MERGED MAIN: a base branch naming no commit falls back to origin/main", MERGED_MAIN,
     "    ref, problem = scope_base.base_branch(root)\n",
     '    ref, problem = (scope_base.base_branch(root)[0] or "origin/main"), None\n',
     _MM + "test_could_not_tell_drops_nothing[base-branch-names-no-commit]"),
    ("MERGED MAIN: the base branch's problem is not named", MERGED_MAIN,
     '                "reason": f"{UNKNOWN}: {problem}; nothing dropped"}\n',
     '                "reason": f"{UNKNOWN}: no integration ref names a commit; nothing dropped"}\n',
     _MM + "test_could_not_tell_names_t0061s_reason_for_a_configured_base_branch"),
    ("MERGED MAIN: HEAD at the merged commit reads as no merge", MERGED_MAIN,
     "    before = _is_ancestor(root, commit, base_sha)\n",
     "    before = _is_ancestor(root, commit, base_sha) or (\n"
     '        commit == crew_common.git_out(root, "rev-parse", "HEAD"))\n',
     _CA + "test_a_fast_forward_to_main_drops_everything_committed_and_keeps_dirty_edits"),
    ("the audit's verdict leaves out the merged commit and its count", AUDIT,
     '    if merged["applies"]:\n        return [(f"  merged main {merged',
     '    if merged["applies"]:\n        return []\n        return [(f"  merged main {merged',
     _CA + "test_check_names_the_merged_commit_and_what_it_did_not_count"),
    ("the audit's pass is silent on could-not-tell", AUDIT,
     '    passed = extra if (merged["applies"] and dropped) or merged["commit"] is None else []\n',
     '    passed = extra if merged["applies"] and dropped else []\n',
     _CA + "test_a_passing_check_states_the_merged_main_answer[could-not-tell]"),
    ("the audit counts a merged-in path taken out of the index", AUDIT,
     '    return merged_main.keep(paths, since_merged - _as_merged(top, merged["commit"], '
     "untracked))\n",
     "    return merged_main.keep(paths, since_merged)\n",
     _MM + "test_the_bundle_and_the_audit_agree_on_a_merged_in_path_removed_from_the_index"
     "[identical-to-merged]"),
    ("the audit drops every untracked merged-in path, edited or not", AUDIT,
     "    return {p for p, oid in zip(names, hashes)\n",
     "    return set(names) or {p for p, oid in zip(names, hashes)\n",
     _MM + "test_the_bundle_and_the_audit_agree_on_a_merged_in_path_removed_from_the_index"
     "[edited]"),
    # --- T-0100 successor (round 2): the mode half, and core.fileMode ------------
    ("the audit judges an untracked merged-in path by its blob id alone", AUDIT,
     "            if (oid, _disk_mode(top, p, file_mode)) == (entries[p][1], entries[p][0])}\n",
     "            if oid == entries[p][1]}\n",
     _CA + "test_an_untracked_merged_in_path_is_judged_by_the_mode_git_add_records"
     "[module-exec-filemode-true]"),
    ("the audit reads the execute bit whatever core.fileMode says", AUDIT,
     "    file_mode = _file_mode(top)\n",
     "    file_mode = True\n",
     _CA + "test_an_untracked_merged_in_path_is_judged_by_the_mode_git_add_records"
     "[module-exec-filemode-false]"),
    ("MERGED MAIN: keep drops nothing, through the bash audit", MERGED_MAIN,
     "    return sorted(set(since_base) & set(since_merged))\n",
     "    return sorted(set(since_base))\n",
     _CA + "test_paths_identical_to_merged_main_are_not_out_of_scope[sh]"),
    ("MERGED MAIN: keep drops nothing, through the PowerShell audit", MERGED_MAIN,
     "    return sorted(set(since_base) & set(since_merged))\n",
     "    return sorted(set(since_base))\n",
     _CA + "test_paths_identical_to_merged_main_are_not_out_of_scope[ps1]"),
    ("MERGED MAIN: keep widened, a ticket edit on top, bash audit", MERGED_MAIN,
     "    return sorted(set(since_base) & set(since_merged))\n",
     "    return sorted(set(since_base) - set(since_merged))\n",
     _CA + "test_a_ticket_edit_on_top_of_merged_mains_edit_stays_flagged[sh]"),
    ("MERGED MAIN: keep widened, a ticket edit on top, PowerShell audit", MERGED_MAIN,
     "    return sorted(set(since_base) & set(since_merged))\n",
     "    return sorted(set(since_base) - set(since_merged))\n",
     _CA + "test_a_ticket_edit_on_top_of_merged_mains_edit_stays_flagged[ps1]"),
    ("MERGED MAIN: keep widened, an edit after the merge, bash audit", MERGED_MAIN,
     "    return sorted(set(since_base) & set(since_merged))\n",
     "    return sorted(set(since_base) - set(since_merged))\n",
     _CA + "test_an_out_of_touch_edit_after_a_merge_of_main_stays_flagged[sh]"),
    ("MERGED MAIN: keep widened, an edit after the merge, PowerShell audit", MERGED_MAIN,
     "    return sorted(set(since_base) & set(since_merged))\n",
     "    return sorted(set(since_base) - set(since_merged))\n",
     _CA + "test_an_out_of_touch_edit_after_a_merge_of_main_stays_flagged[ps1]"),
    # --- T-0097 ------------------------------------------------------------------
    ("PROBE: a silent candidate's null answer is piped into ConvertFrom-Json", AUDIT_PS1,
     "          $probe = if ($line) { $line | ConvertFrom-Json } else { $null }\n",
     "          $probe = $line | ConvertFrom-Json\n",
     "tests/test_ps1_python_probe.py::"
     "test_a_silent_candidate_is_rejected_without_writing_to_stderr"),
    # T-0061: the ticket base branch. Each entry names the one test that
    # sees it; the neighbour cases stay green on purpose.
    (
        # The key is read and thrown away: every repo measures against
        # origin/HEAD again, and TSS-510's 492-file bundle comes back.
        "tickets.baseBranch is ignored",
        SCOPE_BASE_PY,
        '    path = crew_common.repo_config_file(root, "config.json")\n',
        "    return None, None\n",
        ("tests/test_scope_base_branch.py::"
         "test_a_branch_cut_from_the_configured_base_records_exact"),
    ),
    (
        # A configured branch that names no commit falls through to the old
        # chain -- the unknown collapsing into the reassuring answer.
        "a missing configured branch falls back to origin/HEAD",
        SCOPE_BASE_PY,
        '        return None, (f"tickets.baseBranch {value!r} names no commit here "\n',
        '        _lost = (f"tickets.baseBranch {value!r} names no commit here "\n',
        ("tests/test_scope_base_branch.py::"
         "test_could_not_tell_never_falls_back_to_origin_head"),
    ),
    (
        # `--base` answers HEAD and exit 0 on could-not-tell, so review.md
        # step 1a bundles the working tree alone as if it were the ticket.
        "--base prints HEAD when it could not tell",
        SCOPE_BASE_PY,
        '        sys.stderr.write(f"scope-base: {reason}\\n")\n'
        "        return 3\n",
        '        sys.stdout.write("HEAD\\n")\n'
        "        return 0\n",
        ("tests/test_scope_base_branch.py::"
         "test_a_configured_base_that_names_no_commit_could_not_tell"),
    ),
    (
        # The re-derivation loses its fallback-only condition, so a known
        # start is moved by a config change -- the defect the record exists
        # to prevent.
        "an exact record is re-derived",
        SCOPE_BASE_PY,
        "    if not _is_fallback_entry(entry):\n"
        "        return None\n"
        "    ref, problem = base_branch(root)\n",
        "    ref, problem = base_branch(root)\n",
        ("tests/test_scope_base_branch.py::"
         "test_an_exact_record_is_never_rederived"),
    ),
    (
        # activate sets the pointer and records nothing, so the first
        # `--record` lands after commits exist and is a fallback again.
        "activate does not record",
        TICKET,
        "        sha, status = scope_base.record(top, ticket)\n",
        "        sha, status = None, None\n",
        ("tests/test_scope_base_branch.py::"
         "test_activate_records_the_scope_base"),
    ),
    (
        # The not-ancestor reason reads like an ordinary fallback again; the
        # base is still the merge-base, so only the reason's prefix sees it.
        "the not-ancestor reason loses could-not-tell",
        SCOPE_BASE_PY,
        '_REASON_NOT_ANCESTOR = ("could not tell where {ticket} started: start commit "\n',
        '_REASON_NOT_ANCESTOR = ("start commit "\n',
        ("tests/test_scope_base_branch.py::"
         "test_a_not_ancestor_record_says_could_not_tell_and_shows_more"),
    ),
    (
        # QA F1 restored: a base branch that resolves with an empty
        # merge-base (orphan, shallow) reads as "no base branch", so --base
        # prints HEAD and --record writes an EXACT entry that is never moved.
        "an empty merge-base falls to HEAD",
        SCOPE_BASE_PY,
        "    if base:\n"
        "        return ref, base, None\n",
        "    if True:\n"
        "        return (ref, base, None) if base else (None, None, None)\n",
        ("tests/test_scope_base_branch.py::"
         "test_an_orphan_branch_with_the_key_could_not_tell"),
    ),
    # --- T-0068: crew's own bookkeeping ---------------------------------------------
    ("the audit judges bookkeeping", AUDIT,
     '_ONLY = ["--", ".", ":(exclude).work"] + crew_ticket.bookkeeping_excludes()\n',
     '_ONLY = ["--", ".", ":(exclude).work"]\n',
     _CA + "test_bookkeeping_is_never_out_of_touch"),
    ("the unapproved audit lists bookkeeping", AUDIT,
     '_ONLY = ["--", ".", ":(exclude).work"] + crew_ticket.bookkeeping_excludes()\n',
     '_ONLY = ["--", ".", ":(exclude).work"]\n',
     _CA + "test_unapproved_touch_still_fails_but_lists_no_bookkeeping"),
    ("the audit drops every .crew path", AUDIT,
     '_ONLY = ["--", ".", ":(exclude).work"] + crew_ticket.bookkeeping_excludes()\n',
     '_ONLY = ["--", ".", ":(exclude).work", ":(exclude).crew"]\n',
     _CA + "test_an_out_of_touch_file_beside_bookkeeping_still_fails"),
    ("bookkeeping is judged against Touch", GUARD,
     '    if real_rel is not None and all(crew_ticket.is_crew_write_allowed(r) for r in checks):\n'
     '        return True, "crew bookkeeping"\n',
     "",
     _SG + "test_an_edit_to_bookkeeping_is_allowed_outside_touch[.crew/metrics.md-approved]"),
    ("bookkeeping is refused without an approval", GUARD,
     '    if real_rel is not None and all(crew_ticket.is_crew_write_allowed(r) for r in checks):\n'
     '        return True, "crew bookkeeping"\n',
     "",
     _SG + "test_an_edit_to_bookkeeping_is_allowed_outside_touch[.crew/metrics.md-no-approval]"),
    ("the scope base is writable as bookkeeping", GUARD,
     "        if rel is not None and os.path.normcase(rel) == os.path.normcase(SCOPE_BASE):\n"
     "            return True\n"
     "        if rel is not None and crew_ticket.is_crew_write_refused(rel):\n",
     "        if rel is not None and crew_ticket.is_crew_write_refused(rel) \\\n"
     "                and os.path.normcase(rel) != os.path.normcase(SCOPE_BASE):\n",
     _SG + "test_scope_base_stays_refused_though_it_is_bookkeeping[Edit-block]"),
    ("one side of a link decides", GUARD,
     "    if real_rel is not None and all(crew_ticket.is_crew_write_allowed(r) for r in checks):\n",
     "    if real_rel is not None and any(crew_ticket.is_crew_write_allowed(r) for r in checks):\n",
     _SG + "test_one_side_of_a_link_being_bookkeeping_does_not_decide"),
    ("a bookkeeping name linked out of the worktree is bookkeeping", GUARD,
     "    if real_rel is not None and all(crew_ticket.is_crew_write_allowed(r) for r in checks):\n",
     "    if all(crew_ticket.is_crew_write_allowed(r) for r in checks):\n",
     _SG + "test_a_bookkeeping_name_linked_outside_the_worktree_is_not_bookkeeping"),
    # --- review of 514ca132: two lists, not one ---------------------------------------
    # FIX 1: rule 5a opens the whole bookkeeping list again, or a trust input
    # crew READS (a tfplan summary, an incident, the deploy marker) is put on
    # the write-allowed list.
    ("rule 5a opens every bookkeeping path", GUARD,
     "    if real_rel is not None and all(crew_ticket.is_crew_write_allowed(r) for r in checks):\n",
     "    if real_rel is not None and all(crew_ticket.is_crew_bookkeeping(r) or "
     "crew_ticket.is_crew_state(r) for r in checks):\n",
     _SG + "test_a_trust_input_crew_writes_is_judged_against_touch[.crew/tfplan/x.json-approved]"),
    ("a tfplan summary is write-allowed", TICKET,
     'CREW_WRITE_ALLOWED_PATHS = (\n    ".crew/metrics.md",\n)\n',
     'CREW_WRITE_ALLOWED_PATHS = (\n    ".crew/metrics.md",\n    ".crew/tfplan/**",\n)\n',
     _SG + "test_a_trust_input_crew_writes_is_judged_against_touch[.crew/tfplan/x.json-no-approval]"),
    ("the incident file is write-allowed", TICKET,
     'CREW_WRITE_ALLOWED_PATHS = (\n    ".crew/metrics.md",\n)\n',
     'CREW_WRITE_ALLOWED_PATHS = (\n    ".crew/metrics.md",\n    ".crew/incident.json",\n)\n',
     _SG + "test_a_trust_input_crew_writes_is_judged_against_touch[.crew/incident.json-approved]"),
    ("the deploy marker is write-allowed", TICKET,
     'CREW_WRITE_ALLOWED_PATHS = (\n    ".crew/metrics.md",\n)\n',
     'CREW_WRITE_ALLOWED_PATHS = (\n    ".crew/metrics.md",\n    ".crew/.deploy-in-flight",\n)\n',
     _SG + "test_a_trust_input_crew_writes_is_judged_against_touch[.crew/.deploy-in-flight-approved]"),
    # FIX 2: the gate's records, out of review, become Write/Edit-able --
    # rule 2 stops refusing them, or they join the write-allowed list.
    ("rule 2 stops refusing the gate's records", GUARD,
     "        if rel is not None and crew_ticket.is_crew_write_refused(rel):\n"
     "            return True\n",
     "",
     _SG + "test_the_gates_records_are_refused_even_inside_touch[.crew/.verify-gate.record.json-Write]"),
    ("rule 2 stops refusing the gate's marker with no ticket", GUARD,
     "        if rel is not None and crew_ticket.is_crew_write_refused(rel):\n"
     "            return True\n",
     "",
     _SG + "test_the_gates_marker_is_refused_with_no_ticket_in_every_mode[report]"),
    ("the gate's fingerprint is write-allowed", TICKET,
     'CREW_WRITE_ALLOWED_PATHS = (\n    ".crew/metrics.md",\n)\n',
     'CREW_WRITE_ALLOWED_PATHS = (\n    ".crew/metrics.md",\n    ".crew/.verify-gate.*",\n)\n',
     _SG + "test_the_gates_records_are_refused_even_inside_touch[.crew/.verify-gate.fingerprint-Edit]"),
    ("the gate's marker is write-allowed", TICKET,
     'CREW_WRITE_ALLOWED_PATHS = (\n    ".crew/metrics.md",\n)\n',
     'CREW_WRITE_ALLOWED_PATHS = (\n    ".crew/metrics.md",\n    ".crew/.verify-verified-at",\n)\n',
     _SG + "test_the_gates_records_are_refused_even_inside_touch[.crew/.verify-verified-at-Write]"),
    # Round-2 review of 1292b863: guard.log, appended on every scope decision,
    # goes back to judged state (the TSS-510 deadlock after any refusal) or
    # becomes Write/Edit-able while out of the audit (a forged or erased row).
    ("guard.log deadlocks the audit again", TICKET,
     '    ".crew/guard.log",                    # scope_guard.py:126, crew_guards.py:346\n',
     "",
     _CA + "test_a_guard_log_row_never_deadlocks_the_audit"),
    ("guard.log is judged state, editable in report mode", TICKET,
     '    ".crew/guard.log",                    # scope_guard.py:126, crew_guards.py:346\n',
     "",
     _SG + "test_a_log_left_out_of_the_audit_is_refused_to_write"
     "[.crew/guard.log-Write-report-approved]"),
    ("guard.log is write-allowed", TICKET,
     'CREW_WRITE_ALLOWED_PATHS = (\n    ".crew/metrics.md",\n)\n',
     'CREW_WRITE_ALLOWED_PATHS = (\n    ".crew/metrics.md",\n    ".crew/guard.log",\n)\n',
     _SG + "test_a_log_left_out_of_the_audit_is_refused_to_write"
     "[.crew/guard.log-Edit-block-approved]"),
    # FIX 3: a trust input crew writes is left out of the audit again.
    ("the audit drops a committed incident file", TICKET,
     '    ".crew/metrics.jsonl",                # crew_metrics.py:139 (`/crew:done` step 2)\n',
     '    ".crew/metrics.jsonl",                # crew_metrics.py:139 (`/crew:done` step 2)\n'
     '    ".crew/incident.json",\n',
     _CA + "test_a_committed_crew_trust_input_is_out_of_touch[.crew/incident.json]"),
    ("the audit drops a committed tfplan summary", TICKET,
     '    ".crew/metrics.jsonl",                # crew_metrics.py:139 (`/crew:done` step 2)\n',
     '    ".crew/metrics.jsonl",                # crew_metrics.py:139 (`/crew:done` step 2)\n'
     '    ".crew/tfplan/**",\n',
     _CA + "test_a_committed_crew_trust_input_is_out_of_touch[.crew/tfplan/x.json]"),
    ("the audit drops a committed handoff", TICKET,
     '    ".crew/metrics.jsonl",                # crew_metrics.py:139 (`/crew:done` step 2)\n',
     '    ".crew/metrics.jsonl",                # crew_metrics.py:139 (`/crew:done` step 2)\n'
     '    ".crew/handoffs/**",\n',
     _CA + "test_a_committed_crew_trust_input_is_out_of_touch[.crew/handoffs/x.md]"),
)
