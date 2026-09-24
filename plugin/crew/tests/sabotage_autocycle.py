"""Mutations for the auto wrap-up / auto-clear / auto-resume cycle.

Same tuple shape as `sabotage.py`'s MUTATIONS -- (label, target, find,
replace, pytest target) -- but kept in a module of its own and run by its own
runner, so running these never runs (or edits) `sabotage.py`.

The runner restores by scratch copy rather than `.bak`: before each mutation
the target is copied to a scratch directory, the mutation is applied, the
named test is run, the scratch copy is copied back, and the restored bytes are
compared with the copy. A mismatch stops the run at once.

    python3 tests/sabotage_autocycle.py [--scratch DIR]

Exit 0 only when every mutation turns its named test red with a real test
failure (pytest exit 1), not a collection error.

Two rules are guarded twice in the bash flavour, so no single mutation there
can show them: stop_hook_active (a cheap string match, then python's parsed
value) and once-per-crossing (the marker check, then a noclobber claim). The
single-guard .ps1 twin carries the stop_hook_active mutation, and the
once-per-crossing mutations aim at the re-arm condition instead -- re-arming
on a reading that never dropped is the way that rule actually breaks.
"""
import argparse
import filecmp
import os
import shutil
import subprocess
import sys
import tempfile

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(CREW, "hooks", "scripts")
WATCH_SH = os.path.join(SCRIPTS, "context-watch.sh")
WATCH_PS1 = os.path.join(SCRIPTS, "context-watch.ps1")
CLEAR_PS1 = os.path.join(SCRIPTS, "auto-clear.ps1")
READ_SH = os.path.join(SCRIPTS, "handoff-read.sh")
READ_PS1 = os.path.join(SCRIPTS, "handoff-read.ps1")
CYCLE = os.path.join(SCRIPTS, "crew_autocycle.py")
CONTEXT = os.path.join(SCRIPTS, "crew_context.py")
_T = "tests/test_auto_cycle.py::"
_OFF = "  # pylint: disable=using-constant-test\n"

AUTOCYCLE_MUTATIONS = (
    # --- session-keyed markers ---------------------------------------------
    ("two bash sessions share one wrap-up marker again", WATCH_SH,
     "  MARKER=\".crew/.handoff-requested-${SESSION_KEY}\"\n",
     "  MARKER=\".crew/.handoff-requested\"\n",
     _T + "test_two_sessions_in_one_repo_each_get_their_own_wrap_up[sh]"),
    ("two PowerShell sessions share one wrap-up marker again", WATCH_PS1,
     "$marker     = \".crew/.handoff-requested-$sessionKey\"\n",
     "$marker     = \".crew/.handoff-requested\"\n",
     _T + "test_two_sessions_in_one_repo_each_get_their_own_wrap_up[ps1]"),
    ("the bash session key drifts from python's", WATCH_SH,
     "  local key=\"${1//[^A-Za-z0-9_-]/_}\"\n",
     "  local key=\"${1//[^A-Za-z0-9_]/_}\"\n",
     _T + "test_the_session_key_is_the_same_in_every_flavour[sh]"),
    ("one bash SessionStart re-arms every session", READ_SH,
     "rm -f \".crew/.handoff-requested-${KEY}\" \".crew/.autoclear-sent-${KEY}\"\n",
     "rm -f .crew/.handoff-requested-* .crew/.autoclear-sent-*\n",
     _T + "test_one_sessions_start_does_not_rearm_another[sh]"),
    ("one PowerShell SessionStart re-arms every session", READ_PS1,
     "Remove-Item -LiteralPath \".crew/.handoff-requested-$sessionKey\", \".crew/.autoclear-sent-$sessionKey\"",
     "Remove-Item -Path \".crew/.handoff-requested-*\", \".crew/.autoclear-sent-*\"",
     _T + "test_one_sessions_start_does_not_rearm_another[ps1]"),
    # --- once per crossing, stop_hook_active ---------------------------------
    ("bash re-arms without the reading ever dropping", WATCH_SH,
     "  if [ \"${OVER:-0}\" -eq 0 ] && [ \"$SOURCE\" = \"exact\" ]; then\n",
     "  if [ \"$SOURCE\" = \"exact\" ]; then\n",
     _T + "test_wrap_up_blocks_once_per_crossing[sh]"),
    ("PowerShell re-arms without the reading ever dropping", WATCH_PS1,
     "  if ($used -lt $threshold -and $source -eq \"exact\") {\n",
     "  if ($source -eq \"exact\") {\n",
     _T + "test_wrap_up_blocks_once_per_crossing[ps1]"),
    ("PowerShell blocks a stop_hook_active continuation", WATCH_PS1,
     "if ($d.stop_hook_active -eq $true) {\n",
     "if ($false) {\n",
     _T + "test_stop_hook_active_never_blocks_and_claims_nothing[ps1]"),
    ("bash skips auto-clear on the continuation turn again", WATCH_SH,
     "if [ \"$STOP_ACTIVE\" = 1 ]; then\n  if [ -f \"$MARKER\" ]; then\n",
     "if [ \"$STOP_ACTIVE\" = 1 ]; then\n  if false; then\n",
     _T + "test_the_forced_continuation_hands_over_to_auto_clear[sh]"),
    ("PowerShell skips auto-clear on the continuation turn again", WATCH_PS1,
     "if ($d.stop_hook_active -eq $true) {\n  if (Test-Path $marker) {\n",
     "if ($d.stop_hook_active -eq $true) {\n  if ($false) {\n",
     _T + "test_the_forced_continuation_hands_over_to_auto_clear[ps1]"),
    # --- trustworthy readings ------------------------------------------------
    ("bash trusts an estimate", WATCH_SH,
     "trusted = 1 if why == \"measured\" else 0\n",
     "trusted = 1\n",
     _T + "test_the_marker_records_whether_the_reading_can_be_trusted[estimated-estimated-from-transcript-size-sh]"),
    ("PowerShell trusts an estimate", WATCH_PS1,
     "$trusted = ($why -eq \"measured\")\n",
     "$trusted = $true\n",
     _T + "test_the_marker_records_whether_the_reading_can_be_trusted[estimated-estimated-from-transcript-size-ps1]"),
    ("bash trusts a reading from before a compaction", WATCH_SH,
     "elif boundary_at > last_at:\n",
     "elif False:" + _OFF,
     _T + "test_the_marker_records_whether_the_reading_can_be_trusted[stale-stale-reading-before-compaction-sh]"),
    ("PowerShell trusts a reading from before a compaction", WATCH_PS1,
     "elseif ($boundaryAt -gt $lastAt)",
     "elseif ($false)",
     _T + "test_the_marker_records_whether_the_reading_can_be_trusted[stale-stale-reading-before-compaction-ps1]"),
    ("auto-clear.sh clears on an untrusted reading", CYCLE,
     "    if marker.get(\"trusted\") is not True:\n",
     "    if False:" + _OFF,
     _T + "test_no_clear_without_a_verified_handoff_and_a_trusted_reading[untrusted-not trustworthy-sh]"),
    ("auto-clear.ps1 clears on an untrusted reading", CLEAR_PS1,
     "  if (-not (Test-CrewTrue (Get-CrewChild $marker \"trusted\"))) {\n",
     "  if ($false) {\n",
     _T + "test_no_clear_without_a_verified_handoff_and_a_trusted_reading[untrusted-not trustworthy-ps1]"),
    ("auto-clear.ps1 reads a zero-byte marker as a request", CLEAR_PS1,
     "  if ($null -eq $marker) {\n",
     "  if ($false) {\n",
     _T + "test_no_clear_without_a_verified_handoff_and_a_trusted_reading[zero-byte-marker-empty or not JSON-ps1]"),
    # --- verified handoff ----------------------------------------------------
    ("auto-clear.sh accepts a handoff older than the request", CYCLE,
     "    if os.path.getmtime(path) <= requested:\n",
     "    if False:" + _OFF,
     _T + "test_no_clear_without_a_verified_handoff_and_a_trusted_reading[older-handoff-predates-sh]"),
    ("auto-clear.ps1 accepts a handoff older than the request", CLEAR_PS1,
     "  if ($written -le [double]$requested) {",
     "  if ($false) {",
     _T + "test_no_clear_without_a_verified_handoff_and_a_trusted_reading[older-handoff-predates-ps1]"),
    ("auto-clear.sh accepts the PreCompact skeleton", CYCLE,
     "    if SKELETON_MARK in text:\n",
     "    if False:" + _OFF,
     _T + "test_no_clear_without_a_verified_handoff_and_a_trusted_reading[skeleton-skeleton-sh]"),
    ("auto-clear.sh accepts another session's marker", CYCLE,
     "    if marker.get(\"session_id\") != session_id:\n",
     "    if False:" + _OFF,
     _T + "test_no_clear_without_a_verified_handoff_and_a_trusted_reading[other-session-different session-sh]"),
    ("auto-clear.ps1 accepts another session's marker", CLEAR_PS1,
     "  if ([string](Get-CrewChild $marker \"session_id\") -cne $Session) {\n",
     "  if ($false) {\n",
     _T + "test_no_clear_without_a_verified_handoff_and_a_trusted_reading[other-session-different session-ps1]"),
    # --- machine opt-in --------------------------------------------------------
    ("a repo can switch auto-clear on by itself (bash)", CYCLE,
     "    out[\"enabled\"] = machine.get(\"enabled\") is True and repo.get(\"enabled\") is not False\n",
     "    out[\"enabled\"] = machine.get(\"enabled\") is True or repo.get(\"enabled\") is True\n",
     _T + "test_only_the_machine_can_opt_in_and_a_repo_can_only_opt_out[None-True-sh]"),
    ("a repo can switch auto-clear on by itself (PowerShell)", CLEAR_PS1,
     "$enabled = (Test-CrewTrue (Get-CrewChild $globalAuto \"enabled\")) -and\n",
     "$enabled = $true -and\n",
     _T + "test_only_the_machine_can_opt_in_and_a_repo_can_only_opt_out[None-True-ps1]"),
    # --- unique window -------------------------------------------------------
    ("bash takes the first of several title matches", CYCLE,
     "    if len(hits) == 1:\n",
     "    if hits:\n",
     _T + "test_the_window_is_identified_uniquely_or_not_at_all[title-two-sh]"),
    ("bash takes the first of the owner's several windows", CYCLE,
     "        if len(owned) == 1:\n",
     "        if owned:\n",
     _T + "test_the_window_is_identified_uniquely_or_not_at_all[owner-two-sh]"),
    ("PowerShell takes the first of several title matches", CLEAR_PS1,
     "  if ($hits.Count -ne 1) {\n",
     "  if ($hits.Count -eq 0) {\n",
     _T + "test_the_window_is_identified_uniquely_or_not_at_all[title-two-ps1]"),
    ("PowerShell takes the first of the owner's several windows", CLEAR_PS1,
     "  if ($owned.Count -gt 1) {\n",
     "  if ($false) {\n",
     _T + "test_the_window_is_identified_uniquely_or_not_at_all[owner-two-ps1]"),
    ("a tmux pane is trusted without being this session's", CYCLE,
     "        if not pane_pid or pane_pid not in ancestors():\n",
     "        if not pane_pid:\n",
     _T + "test_a_tmux_pane_must_be_the_one_running_this_session[999999-False]"),
    # --- resume --------------------------------------------------------------
    ("the resume cuts the next action off a long handoff", CONTEXT,
     "                lead = f\"Next action: {action}\\n\" if action else \"\"\n",
     "                lead = \"\"\n",
     _T + "test_write_clear_resume_carries_the_next_action_end_to_end[sh]"),
)


def run_test(target):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    # --run-slow: a target naming a bash/pwsh case is deselected by default
    # (conftest.py) and would exit 5, not 1, however the mutation behaved.
    done = subprocess.run([sys.executable, "-m", "pytest", target, "-q", "--no-header", "-x",
                           "-p", "no:cacheprovider", "--run-slow"],
                          cwd=CREW, capture_output=True, text=True, check=False, env=env)
    return done.returncode


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", default=None)
    args = parser.parse_args(argv)
    scratch = args.scratch or tempfile.mkdtemp(prefix="sabotage-autocycle-")
    os.makedirs(scratch, exist_ok=True)
    ok = True
    for index, (label, target, find, replace, test) in enumerate(AUTOCYCLE_MUTATIONS):
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
            code = run_test(test)
        finally:
            shutil.copyfile(copy, target)
        if not filecmp.cmp(copy, target, shallow=False):
            print(f"RESTORE FAILED for {target} - the scratch copy is {copy}")
            return 3
        verdict = {0: "STILL GREEN - VACUOUS", 1: "RED (good)"}.get(code, f"RED BUT UNPROVEN - exit {code}")
        ok = ok and code == 1
        print(f"{verdict:32} {label}")
    print("\nAUTOCYCLE SABOTAGE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
