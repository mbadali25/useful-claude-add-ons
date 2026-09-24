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
CLEAR_SH = os.path.join(SCRIPTS, "auto-clear.sh")
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
    # --- narrowing: onlyRepos / onlySessions --------------------------------
    ("bash arms every repo whatever onlyRepos lists", CYCLE,
     "    repos = _scope(cfg.get(\"onlyRepos\"))\n",
     "    repos = None\n",
     _T + "test_the_machine_can_narrow_auto_clear_to_listed_repos_and_sessions[repo-other-sh]"),
    ("PowerShell arms every repo whatever onlyRepos lists", CLEAR_PS1,
     "$onlyRepos = Get-CrewScopeList $globalAuto \"onlyRepos\"\n",
     "$onlyRepos = $null\n",
     _T + "test_the_machine_can_narrow_auto_clear_to_listed_repos_and_sessions[repo-other-ps1]"),
    ("a repo's own onlyRepos widens the bash flavour", CYCLE,
     "    out[\"onlyRepos\"] = machine.get(\"onlyRepos\")\n",
     "    out[\"onlyRepos\"] = repo.get(\"onlyRepos\", machine.get(\"onlyRepos\"))\n",
     _T + "test_a_repo_config_cannot_widen_the_machines_narrowing[onlyRepos-sh]"),
    ("a repo's own onlySessions widens the PowerShell flavour", CLEAR_PS1,
     "$onlySessions = Get-CrewScopeList $globalAuto \"onlySessions\"\n",
     "$onlySessions = Get-CrewScopeList $repoAuto \"onlySessions\"\n",
     _T + "test_a_repo_config_cannot_widen_the_machines_narrowing[onlySessions-ps1]"),
    # --- backslash/slash collapse on POSIX (review round 1, fix4) -----------
    ("bash normalises a POSIX backslash into a slash again (pre-check)", CYCLE,
     "    text = os.path.expanduser(path)\n"
     "    if windows:\n"
     "        text = text.replace(\"\\\\\", \"/\")\n",
     "    text = os.path.expanduser(path).replace(\"\\\\\", \"/\")\n"
     "    if windows:\n",
     _T + "test_in_scope_does_not_collapse_backslash_and_slash_on_posix"),
    # --- review round 2 (crew-1.0-r3-autocycle): trailing whitespace, POSIX
    # drive-letter, and Unicode casefold ---------------------------------
    ("bash strips whitespace out of onlyRepos entries again", CYCLE,
     "    text = os.path.expanduser(path)\n",
     "    text = os.path.expanduser(path.strip())\n",
     _T + "test_a_trailing_space_in_an_only_repos_entry_does_not_authorise_the_bare_path"),
    ("bash accepts a POSIX-relative drive-letter path as absolute again", CYCLE,
     "    if not (_ABSOLUTE_SLASH.match(candidate) or (windows and _ABSOLUTE_DRIVE.match(candidate))):\n",
     "    if not (_ABSOLUTE_SLASH.match(candidate) or _ABSOLUTE_DRIVE.match(candidate)):\n",
     _T + "test_a_drive_letter_path_is_not_absolute_on_posix"),
    ("bash casefolds onlyRepos comparisons on Windows again", CYCLE,
     "        text = text.lower()\n    return text\n",
     "        text = text.casefold()\n    return text\n",
     _T + "test_windows_repo_matching_does_not_casefold_a_sharp_s"),
    ("bash normalises a POSIX backslash into a slash again (post-realpath)", CYCLE,
     "        text = os.path.realpath(text)\n"
     "        if windows:\n"
     "            text = text.replace(\"\\\\\", \"/\")\n",
     "        text = os.path.realpath(text).replace(\"\\\\\", \"/\")\n",
     _T + "test_in_scope_does_not_collapse_backslash_and_slash_on_posix"),
    # --- chained relative symlink resolves from the wrong parent (fix4) -----
    # Review round 3 (crew-1.0-r4-scope) rewrote Resolve-CrewRealPath's
    # symlink-substitution branch entirely (raw components pushed through the
    # SAME per-component queue as '..', rather than a GetFullPath-collapsed
    # string split once) -- these two mutations are re-anchored onto that new
    # shape, same bug, same target test.
    # Review round 4 (crew-1.0-w2-autoclear, Item 2): the drive-letter/UNC
    # classification that used to live inline was pulled into its own
    # function, Resolve-CrewLinkRoot, so the "relative target, no root at
    # all" case is now `$null -eq $classified` rather than the tail of a
    # `$linkRoot`-truthy if/else. These three anchors are re-pointed at that
    # new shape; the bug and the test each one proves are unchanged.
    ("PowerShell chases a chained relative symlink from the first hop's parent", CLEAR_PS1,
     "    if ($null -eq $classified) {\n"
     "      foreach ($p in (Split-CrewRawComponents $linkNorm)) {\n"
     "        $queue.Insert($insertAt, $p)\n"
     "        $insertAt++\n"
     "      }\n"
     "    } else {\n",
     "    if ($null -eq $classified) {\n"
     "      $resolved.Clear()\n"
     "      foreach ($p in (Split-CrewRawComponents $linkNorm)) {\n"
     "        $queue.Insert($insertAt, $p)\n"
     "        $insertAt++\n"
     "      }\n"
     "    } else {\n",
     _T + "test_a_chained_relative_symlink_in_only_repos_resolves_from_its_own_parent[ps1]"),
    # --- review round 2 (crew-1.0-r3-autocycle): a symlinked component
    # INSIDE a substituted target, and the raised/explicit-fail hop bound --
    ("PowerShell does not re-resolve a symlinked component inside a substituted target", CLEAR_PS1,
     "    if ($null -eq $classified) {\n"
     "      foreach ($p in (Split-CrewRawComponents $linkNorm)) {\n"
     "        $queue.Insert($insertAt, $p)\n"
     "        $insertAt++\n"
     "      }\n"
     "    } else {\n",
     "    if ($null -eq $classified) {\n"
     "    } else {\n",
     _T + "test_a_symlinked_component_inside_a_substituted_target_still_resolves[ps1]"),
    ("PowerShell's symlink hop bound silently keeps a partial path instead of failing closed",
     CLEAR_PS1,
     "    if ($hops -gt $script:_CREW_SYMLINK_HOP_LIMIT) { return $null }\n",
     "\n",
     _T + "test_a_symlink_cycle_in_only_repos_fails_closed[ps1]"),
    # --- review round 3 (crew-1.0-r4-scope): '..' collapsed lexically before
    # a symlinked component inside a substituted target is even looked up --
    ("PowerShell collapses '..' before resolving a symlink inside a substituted target again",
     CLEAR_PS1,
     "    if ($null -eq $classified) {\n"
     "      foreach ($p in (Split-CrewRawComponents $linkNorm)) {\n"
     "        $queue.Insert($insertAt, $p)\n"
     "        $insertAt++\n"
     "      }\n"
     "    } else {\n",
     "    if ($null -eq $classified) {\n"
     "      $targetFull = [System.IO.Path]::GetFullPath((Join-Path (Join-CrewParts $root $resolved) $linkNorm))\n"
     "      foreach ($p in (Split-CrewRawComponents $targetFull.Substring($root.Length))) {\n"
     "        $queue.Insert($insertAt, $p)\n"
     "        $insertAt++\n"
     "      }\n"
     "    } else {\n",
     _T + "test_a_dotdot_after_a_symlinked_component_resolves_before_it_collapses[ps1]"),
    # --- review round 4 (crew-1.0-w2-autoclear, Item 2): a drive-root-
    # relative symlink target ("\repo") used to be taken as fully qualified --
    ("PowerShell treats a drive-root-relative symlink target as fully qualified again",
     CLEAR_PS1,
     "  if ($LinkNorm.StartsWith('/')) {\n"
     "    return @{ Root = $null; Remainder = $LinkNorm.Substring(1); Rootless = $true }\n"
     "  }\n",
     "  if ($LinkNorm.StartsWith('/')) {\n"
     "    return @{ Root = $LinkNorm; Remainder = ''; Rootless = $false }\n"
     "  }\n",
     "tests/test_auto_cycle.py::"
     "test_resolve_crew_link_root_classifies_drive_unc_and_rootless_targets[/repo]"),
    # --- the `.crew/` directory gate reintroducing the OLD `.crew/config.json`
    # requirement: a `.crew/` directory present with no config.json must ARM
    # (state (2) of the six-state matrix, test_auto_clear.py's own comment
    # block), not stand down the way the F3 file-based gate did. OWNER
    # DECISION reversed the gate from the file back to the directory (crew
    # 1.0 F4); these two mutations reintroduce the file check this reversal
    # removed.
    ("auto-clear.sh's .crew/ directory gate reverts to the old config.json check", CLEAR_SH,
     "[ -d .crew ] || exit 0\nLOG=\".crew/.autoclear.log\"\n",
     "[ -f .crew/config.json ] || exit 0\nLOG=\".crew/.autoclear.log\"\n",
     "tests/test_auto_clear.py::"
     "test_a_crew_directory_with_no_config_json_arms_and_reaches_the_session_check_sh"),
    ("auto-clear.ps1's .crew/ directory gate reverts to the old config.json check", CLEAR_PS1,
     "if (-not (Test-Path \".crew\" -PathType Container)) { exit 0 }\n\n$log = \".crew/.autoclear.log\"\n",
     "if (-not (Test-Path \".crew/config.json\" -PathType Leaf)) { exit 0 }\n\n$log = \".crew/.autoclear.log\"\n",
     "tests/test_auto_clear.py::"
     "test_a_crew_directory_with_no_config_json_arms_and_reaches_the_session_check_ps1"),
    # --- `.crew/` created as a side effect of note()/Write-CrewAutoClearNote,
    # WITH the directory gate itself also gone: the never-create rule (state
    # (1) of the same matrix -- no `.crew/` at all) exists because the gate
    # above stands the whole hook down before note() can ever run; reintroduce
    # BOTH the removed gate and the mkdir/New-Item this F4 pass took out of
    # note() and a session with no `.crew/` at all would get one created the
    # moment ANY refusal past that point tried to log (here, "no session
    # id"). Mkdir alone, with the gate left standing, is unreachable dead code
    # and would make this mutation vacuous -- the gate is what has to go too.
    ("auto-clear.sh's directory gate is gone and note() creates .crew/ again", CLEAR_SH,
     "[ -d .crew ] || exit 0\n"
     "LOG=\".crew/.autoclear.log\"\n"
     "\n"
     "note() {  # one line to the log and to stderr; the log is the one anybody reads\n"
     "  # `.crew/` is guaranteed to exist by the gate above, which runs before this\n"
     "  # function is ever called -- no mkdir needed, and none may run here: a\n"
     "  # repo with no `.crew/` must never get one created as a side effect.\n"
     "  printf",
     "LOG=\".crew/.autoclear.log\"\n"
     "\n"
     "note() {  # one line to the log and to stderr; the log is the one anybody reads\n"
     "  mkdir -p .crew 2>/dev/null\n"
     "  printf",
     "tests/test_auto_clear.py::"
     "test_no_crew_directory_at_all_stays_silent_and_creates_nothing_sh"),
    ("auto-clear.ps1's directory gate is gone and Write-CrewAutoClearNote creates .crew/ again", CLEAR_PS1,
     "if (-not (Test-Path \".crew\" -PathType Container)) { exit 0 }\n"
     "\n"
     "$log = \".crew/.autoclear.log\"\n"
     "\n"
     "function Write-CrewAutoClearNote([string]$Message) {\n"
     "  # A Stop hook's stderr is invisible on exit 0, so the log is the only place\n"
     "  # anybody can find out why nothing happened. `.crew` is guaranteed to exist\n"
     "  # by the gate above, which runs before this function is ever called -- no\n"
     "  # New-Item needed, and none may run here.\n"
     "  $stamp",
     "$log = \".crew/.autoclear.log\"\n"
     "\n"
     "function Write-CrewAutoClearNote([string]$Message) {\n"
     "  if (-not (Test-Path \".crew\")) { New-Item -ItemType Directory -Path \".crew\" -Force | Out-Null }\n"
     "  $stamp",
     "tests/test_auto_clear.py::"
     "test_no_crew_directory_at_all_stays_silent_and_creates_nothing_ps1"),
    # --- resume --------------------------------------------------------------
    ("the resume cuts the next action off a long handoff", CONTEXT,
     "                lead = f\"Next action: {action}\\n\" if action else \"\"\n",
     "                lead = \"\"\n",
     _T + "test_write_clear_resume_carries_the_next_action_end_to_end[clear-sh]"),
    # --- order invariant: crew-repo gate -> enabled/narrowing -> only THEN
    # may anything be logged. A not-opted-in run reaching a LATER refusal
    # (no session id, no usable method) before the silent `off`/narrowing
    # exit runs is the exact regression `test_auto_clear_order.py` exists to
    # pin -- see that file's own docstring and CONFIG.md sec 14.
    ("the enabled check no longer runs before anything can log (bash)", CYCLE,
     "    if not cfg[\"enabled\"]:\n",
     "    if False and not cfg[\"enabled\"]:\n",
     "tests/test_auto_clear_order.py::"
     "test_config_present_enabled_false_writes_no_log_sh"),
    ("the enabled check no longer runs before anything can log (PowerShell)", CLEAR_PS1,
     "if (-not $enabled) { exit 0 }\n",
     "if ($false) { exit 0 }\n",
     "tests/test_auto_clear_order.py::"
     "test_config_present_enabled_false_writes_no_log_ps1"),
    ("the onlyRepos/onlySessions narrowing no longer runs before anything can log (bash)",
     CYCLE,
     "    if not in_scope(cfg, root, session_id):\n",
     "    if False and not in_scope(cfg, root, session_id):\n",
     "tests/test_auto_clear_order.py::"
     "test_config_present_only_repos_excludes_writes_no_log_sh"),
    ("the onlyRepos narrowing no longer runs before anything can log (PowerShell)",
     CLEAR_PS1,
     "  if (-not $here -or $listed -notcontains $here) { exit 0 }\n",
     "  if ($false) { exit 0 }\n",
     "tests/test_auto_clear_order.py::"
     "test_config_present_only_repos_excludes_writes_no_log_ps1"),
    # --- Codex review FIXes (gpt-5.6-sol, 485a1b08..3f347d52) ----------------
    ("an unresolvable sendkeys window owner is assumed safe again", CLEAR_PS1,
     "if (-not $ownerKnown -or $ownerProcessName -eq \"WindowsTerminal\") {\n",
     "if ($ownerProcessName -eq \"WindowsTerminal\") {\n",
     "tests/test_auto_clear_review_fixes.py::"
     "test_sendkeys_declines_when_the_window_owner_cannot_be_determined"),
    ("ConvertTo-CrewWin32Arg stops quoting Start-Process's arguments", CLEAR_PS1,
     "  $sb = New-Object System.Text.StringBuilder\n",
     "  return $Arg\n  $sb = New-Object System.Text.StringBuilder\n",
     "tests/test_auto_clear_review_fixes.py::"
     "test_convert_to_crew_win32_arg_round_trips_through_the_real_argv_algorithm[root-with-space]"),
    # --- notify's dry-run delay must never echo a number (Windows relay,
    # 2f7f71f7, item 3): `notify` types nothing, so `delaySeconds` buys it no
    # wait, and echoing the configured number (or a hardcoded 0) reads as a
    # real delay it never takes. ---
    ("auto-clear.sh's notify dry-run echoes the configured delay again", CLEAR_SH,
     '  [ "$RESOLVED" = "notify" ] && DELAY_LINE="delay: n/a (notify sends no keystroke)"\n',
     "",
     _T + "test_notify_dry_run_never_reports_a_delay_number[sh]"),
    ("auto-clear.ps1's notify dry-run hardcodes delay: 0s again", CLEAR_PS1,
     '    Write-Output "  delay: n/a (notify sends no keystroke)"\n',
     '    Write-Output "  delay: 0s"\n',
     _T + "test_notify_dry_run_never_reports_a_delay_number[ps1]"),
    # --- fd 3 leaking into the detached tmux/xdotool sender (Codex FIX, item
    # 4): held context-watch.sh's own stdout pipe open for the whole
    # `sleep $DELAY`, which is what let a slow /clear hit the hook's 20s
    # timeout even though context-watch.sh itself had long since exited. ---
    ("auto-clear.sh's detached sender inherits fd 3 again", CLEAR_SH,
     'setsid bash "$send_script" 3>&- >/dev/null 2>&1 &',
     'setsid bash "$send_script" >/dev/null 2>&1 &',
     _T + "test_context_watch_stdout_reaches_eof_promptly_even_with_a_long_delay"),
    ("context-watch.sh swallows auto-clear's stdout when mktemp fails again", WATCH_SH,
     "  exec 3>&1\n"
     "  err=$(bash \"$(dirname \"${BASH_SOURCE[0]}\")/auto-clear.sh\" --root \"$PWD\" --session \"$SESSION_ID\" 2>&1 1>&3)\n"
     "  rc=$?\n"
     "  exec 3>&-\n",
     "  out_file=$(mktemp 2>/dev/null) || out_file=\"\"\n"
     "  if [ -n \"$out_file\" ]; then\n"
     "    err=$(bash \"$(dirname \"${BASH_SOURCE[0]}\")/auto-clear.sh\" --root \"$PWD\" --session \"$SESSION_ID\" \\\n"
     "          2>&1 1>\"$out_file\")\n"
     "    rc=$?\n"
     "    out=$(cat \"$out_file\" 2>/dev/null)\n"
     "    rm -f \"$out_file\"\n"
     "    [ -n \"$out\" ] && printf '%s\\n' \"$out\"\n"
     "  else\n"
     "    err=$(bash \"$(dirname \"${BASH_SOURCE[0]}\")/auto-clear.sh\" --root \"$PWD\" --session \"$SESSION_ID\" 2>&1 1>/dev/null)\n"
     "    rc=$?\n"
     "  fi\n",
     "tests/test_auto_clear_review_fixes.py::"
     "test_context_watch_forwards_the_notify_json_even_when_mktemp_fails"),
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
