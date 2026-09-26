"""Mutations for auto-clear's session binding (T-0016).

Same tuple shape as `sabotage.py`'s MUTATIONS -- (label, target, find,
replace, pytest target) -- registered there, and runnable on their own:

    python3 tests/sabotage_autoclear_binding.py [--scratch DIR]

The runner is `sabotage_autocycle`'s: each target is copied to a scratch
directory, mutated, its named test run, copied back, and the restored bytes
compared with the copy; a mismatch stops the run at once. A target test that
skips on this host (the ps1 cases need pwsh) is reported SKIPPED, never
counted as caught. Exit 0 only when every mutation turns its named test red
with a real test failure (pytest exit 1).

Every mutation removes one link of the proof that the target is THIS
session's -- the record lookup, its kind, its entrypoint, its pid's start
time and ancestry, the tty equality, "could not tell" staying a refusal, the
walk origin and its reach above the owner, the window being no other live
session's, the relocated CLAUDE_CONFIG_DIR, the ssh/WSL boundary -- and the
named test is the one that must notice. `test_every_binding_sabotage_anchor_is_present_exactly_once` holds
each `find` to exactly one occurrence, so a drifted anchor fails the suite
instead of silently testing nothing.
"""
import argparse
import filecmp
import os
import shutil
import sys
import tempfile

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(CREW, "hooks", "scripts")
CYCLE = os.path.join(SCRIPTS, "crew_autocycle.py")
CLEAR_SH = os.path.join(SCRIPTS, "auto-clear.sh")
CLEAR_PS1 = os.path.join(SCRIPTS, "auto-clear.ps1")
_T = "tests/test_autoclear_binding.py::"

BINDING_MUTATIONS = (
    # --- the record lookup and each field it proves --------------------------
    ("session_owner accepts any session without reading a record", CYCLE,
     '    that owns `session_id`, proven through its session record."""\n',
     '    that owns `session_id`, proven through its session record."""\n'
     '    return {"ok": True, "headless": False, "reason": "", "pid": os.getpid(),\n'
     '            "tty": _tty_of(os.getpid(), env)}\n',
     _T + "test_no_record_tmux_method_refuses"),
    ("a dead owner's record is accepted", CYCLE,
     "    if not _alive(pid):\n",
     "    if False:\n",
     _T + "test_dead_owner_refuses"),
    ("two records naming one session are accepted", CYCLE,
     "    if len(matches) > 1:\n",
     "    if len(matches) > 2:\n",
     _T + "test_two_matching_records_refuse"),
    ("a reused pid's procStart is not compared", CYCLE,
     '    if started is not None and str(record.get("procStart")) != started:\n',
     "    if False:\n",
     _T + "test_proc_start_mismatch_refuses"),
    ("the owner need not be an ancestor of the hook", CYCLE,
     "    if pid not in ancestors():\n",
     "    if False:\n",
     _T + "test_owner_not_ancestor_refuses"),
    ("any kind is accepted as interactive", CYCLE,
     '    if kind != "interactive":\n',
     "    if False:\n",
     _T + "test_non_interactive_kind_refuses"),
    ("an SDK / -p entrypoint is accepted as interactive", CYCLE,
     '    if entrypoint.startswith("sdk"):\n',
     "    if False:\n",
     _T + "test_sdk_entrypoint_refuses"),
    ("an unreadable owner tty reads as a match", CYCLE,
     "    if tty is None:\n",
     "    if tty is None and False:\n",
     _T + "test_xdotool_owner_tty_unreadable_refuses"),
    ("an owner with no controlling tty is not headless", CYCLE,
     '    if tty == "":\n',
     "    if False:\n",
     _T + "test_owner_with_no_controlling_tty_is_headless_and_refuses"),
    # --- each method's check, anchored on the owner ----------------------------
    ("tmux skips the owner-tty == pane-tty check", CYCLE,
     '        if owner["tty"] != pane_tty:\n',
     "        if False:\n",
     _T + "test_child_in_parent_pane_refuses_on_tty_mismatch"),
    ("xdotool walks windows from the hook, not the owner", CYCLE,
     'found = resolve_target(ancestors(owner["pid"]), windows',
     "found = resolve_target(ancestors(), windows",
     _T + "test_xdotool_walks_from_owner"),
    ("xdotool looks only at the owner, never the terminal above it", CYCLE,
     'found = resolve_target(ancestors(owner["pid"]), windows',
     'found = resolve_target([owner["pid"]], windows',
     _T + "test_xdotool_window_of_a_strict_ancestor_of_the_owner_sends[parent]"),
    ("xdotool types into a window another session shares", CYCLE,
     '        if shared:\n            return {"ok": False, "reason": shared}\n',
     '        if False:\n            return {"ok": False, "reason": shared}\n',
     _T + "test_xdotool_walk_through_another_sessions_process_refuses"),
    ("a sibling under the window's owner is not compared", CYCLE,
     "        if window_pid in chain:\n",
     "        if False:\n",
     _T + "test_xdotool_window_shared_with_a_sibling_session_refuses"),
    ("a sibling record with no procStart reads as stale", CYCLE,
     "        if started is not None and recorded is not None and str(recorded) != started:\n",
     "        if started is not None and str(recorded) != started:\n",
     _T + "test_xdotool_sibling_record_without_proc_start_still_refuses"),
    ("a sibling record with no usable pid is skipped", CYCLE,
     "        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 1:\n",
     "        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 1:\n"
     "            continue\n",
     _T + "test_xdotool_sibling_record_with_no_usable_pid_refuses"),
    ("a session under the owner counts as a second holder", CYCLE,
     "        if owner_pid in chain:\n            continue\n",
     "",
     _T + "test_xdotool_session_under_the_owner_does_not_block"),
    ("CLAUDE_CONFIG_DIR's session records are not read", CYCLE,
     '    relocated = (env.get("CLAUDE_CONFIG_DIR") or "").strip()\n',
     '    relocated = ""\n',
     _T + "test_record_under_claude_config_dir_is_found"),
    ("no record under CLAUDE_CONFIG_DIR reads as headless", CYCLE,
     '    if not matches and (env.get("CLAUDE_CONFIG_DIR") or "").strip():\n',
     "    if False:\n",
     _T + "test_no_record_with_claude_config_dir_set_is_could_not_tell"),
    ("an explicit tmux on a headless session becomes a notify", CYCLE,
     '        if cfg["method"] == "auto":\n',
     "        if True:\n",
     _T + "test_no_record_tmux_method_refuses"),
    # --- ssh and WSL ------------------------------------------------------------
    ("ssh lets auto pick xdotool", CYCLE,
     "        elif boundary:\n",
     "        elif False:\n",
     _T + "test_ssh_auto_is_notify_not_xdotool[SSH_CONNECTION]"),
    ("explicit xdotool is allowed across ssh", CYCLE,
     "        if boundary:\n            return {\"ok\": False, \"reason\": (\n"
     "                f\"method xdotool across",
     "        if False:\n            return {\"ok\": False, \"reason\": (\n"
     "                f\"method xdotool across",
     _T + "test_ssh_explicit_xdotool_refuses"),
    ("WSL's environment markers are ignored", CYCLE,
     '    if any(env.get(k) for k in ("WSL_DISTRO_NAME", "WSL_INTEROP")):\n',
     "    if False:\n",
     _T + "test_wsl_auto_is_notify[env-distro]"),
    ("WSL's binfmt interop file is ignored", CYCLE,
     "    if os.path.exists(env.get(WSL_INTEROP_ENV) or _WSL_INTEROP_PATH):\n",
     "    if False:\n",
     _T + "test_wsl_auto_is_notify[interop-file]"),
    ("a headless session with no terminal method gets no recipe", CYCLE,
     '        owner = session_owner(session_id, env)\n        if owner["headless"]:\n',
     '        owner = session_owner(session_id, env)\n        if False:\n',
     _T + "test_headless_with_no_terminal_method_at_all_is_notify"),
    # --- the notify message -----------------------------------------------------
    ("the headless notify drops its reason and recipe", CLEAR_SH,
     '  [ -n "$REASON" ] && MSG="$MSG Why: $REASON."\n',
     "",
     _T + "test_notify_message_carries_the_headless_reason"),
    # --- the ps1 twin -----------------------------------------------------------
    ("ps1 skips the session record lookup", CLEAR_PS1,
     "$owner = Get-CrewSessionOwner $Session $ancestors\n",
     '$owner = @{ Ok = $true; Headless = $false; Reason = ""; Pid = $PID }\n',
     _T + "test_ps1_no_record_declines_to_notify[no-record]"),
    ("ps1 walks windows from $PID, not the owner", CLEAR_PS1,
     "foreach ($ancestor in $ownerChain) {\n",
     "foreach ($ancestor in $ancestors) {\n",
     _T + "test_ps1_walk_starts_at_owner"),
    ("ps1 looks only at the owner, never the terminal above it", CLEAR_PS1,
     "$ownerChain = @($ancestors[$ownerIndex..($ancestors.Count - 1)])\n",
     "$ownerChain = @($owner.Pid)\n",
     _T + "test_ps1_window_of_a_strict_ancestor_of_the_owner_sends[parent]"),
    ("ps1 types into a window another session shares", CLEAR_PS1,
     "$sharedReason = Get-CrewSharedWindowReason $Session $owner.Pid $target\n",
     '$sharedReason = ""\n',
     _T + "test_ps1_walk_through_another_sessions_process_declines"),
    ("ps1 does not compare a sibling to the window's owner", CLEAR_PS1,
     "    if ($holder.Chain -contains $Window.Pid) {\n",
     "    if ($false) {\n",
     _T + "test_ps1_window_shared_with_a_sibling_session_declines"),
    ("ps1 counts a session under the owner as a second holder", CLEAR_PS1,
     "    if ($chain -contains $OwnerPid) { continue }\n",
     "",
     _T + "test_ps1_session_under_the_owner_does_not_block"),
    ("ps1 does not read CLAUDE_CONFIG_DIR's session records", CLEAR_PS1,
     '  $relocated = "$env:CLAUDE_CONFIG_DIR".Trim()\n',
     '  $relocated = ""\n',
     _T + "test_ps1_record_under_claude_config_dir_is_found"),
    ("ps1 reads no record under CLAUDE_CONFIG_DIR as headless", CLEAR_PS1,
     '  if ($matched.Count -eq 0 -and "$env:CLAUDE_CONFIG_DIR".Trim()) {\n',
     "  if ($false) {\n",
     _T + "test_ps1_no_record_with_claude_config_dir_set_refuses"),
    ("ps1 casts a non-integer pid to a match", CLEAR_PS1,
     "  if (-not ($rawPid -is [int] -or $rawPid -is [long])) {\n",
     "  if ($null -eq $rawPid) {\n",
     _T + "test_both_flavours_refuse_a_pid_that_is_not_an_integer[ps1]"),
    ("ps1 accepts a dead owner's record", CLEAR_PS1,
     "  if ($null -eq (Get-Process -Id $ownerPid -ErrorAction SilentlyContinue)) {\n",
     "  if ($false) {\n",
     _T + "test_ps1_dead_owner_refuses"),
    ("ps1 owner need not be an ancestor", CLEAR_PS1,
     "  if ($Chain -notcontains $ownerPid) {\n",
     "  if ($false) {\n",
     _T + "test_ps1_owner_not_ancestor_declines"),
    ("ps1 accepts any kind", CLEAR_PS1,
     '  if ([string]$kind -cne "interactive") {\n',
     "  if ($false) {\n",
     _T + "test_ps1_non_interactive_kind_declines"),
    ("ps1 accepts an SDK / -p entrypoint", CLEAR_PS1,
     '  if ($entrypoint.StartsWith("sdk", [StringComparison]::Ordinal)) {\n',
     "  if ($false) {\n",
     _T + "test_ps1_no_record_declines_to_notify[sdk-entrypoint]"),
)


def main(argv=None):
    from sabotage_autocycle import run_test  # pylint: disable=import-outside-toplevel

    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", default=None)
    args = parser.parse_args(argv)
    scratch = args.scratch or tempfile.mkdtemp(prefix="sabotage-binding-")
    os.makedirs(scratch, exist_ok=True)
    ok = True
    for index, (label, target, find, replace, test) in enumerate(BINDING_MUTATIONS):
        with open(target, encoding="utf-8", newline="") as handle:
            text = handle.read()
        if text.count(find) != 1:
            print(f"{'ANCHOR LOST':32} {label}")
            ok = False
            continue
        copy = os.path.join(scratch, f"{index:02d}-{os.path.basename(target)}")
        shutil.copyfile(target, copy)
        mutated = text.replace(find, replace)
        try:
            with open(target, "w", encoding="utf-8", newline="") as handle:
                handle.write(mutated)
            code, skipped, reason = run_test(test)
        finally:
            shutil.copyfile(copy, target)
        if not filecmp.cmp(copy, target, shallow=False):
            print(f"RESTORE FAILED for {target} - the scratch copy is {copy}")
            return 3
        if skipped:
            verdict = f"SKIPPED (not runnable on this host: {reason})"
        else:
            verdict = {0: "STILL GREEN - VACUOUS", 1: "RED (good)"}.get(
                code, f"RED BUT UNPROVEN - exit {code}")
            ok = ok and code == 1
        print(f"{verdict:32} {label}")
    print("\nBINDING SABOTAGE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.exit(main())
