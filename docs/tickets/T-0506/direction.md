# T-0506 direction - concurrent pwsh runs corrupt the shared startup profile cache

Status: seed (not yet approved).

## Ask (owner the owner, 2026-09-29 ~12:20 CDT, verbatim)
"file a ticket for the pwsh cache race"

## What happened (Linux box, 2026-09-29, measured)
- The crew Stop hook (verify-gate.sh, crew 1.0.59) failed the PowerShell rule, and `_verify/smoke.sh` failed its powershell check. Both printed `Stack overflow.` and then `Aborted (core dumped)` from `"$PWSH" -NoProfile -File scripts/check-powershell.ps1`.
- `/snap/bin/pwsh` (snap powershell 7.6.5, rev 405, unchanged since 2026-09-22) crashed the same way on a bare `-NoProfile -Command '1+1'`, and `ulimit -s 8192` did not help.
- Isolation: `XDG_CACHE_HOME=<empty dir>` fixed it and `XDG_DATA_HOME=<empty dir>` did not. A copy of `~/.cache/powershell` minus `StartupProfileData-NonInteractive` ran clean, and a copy minus `ModuleAnalysisCache-31468CF5` still crashed. So the corrupt file was `StartupProfileData-NonInteractive`, the .NET multicore-JIT startup profile. It was last written 2026-09-29 12:06:46 CDT.
- Repair: the file was moved to the session scratchpad as `StartupProfileData-NonInteractive.corrupt` (still there to inspect). pwsh regenerated it on the next run, and `check-powershell.ps1` then passed: "44 PowerShell file(s) checked, all clean", rc 0.

## Hypothesis (JUDGEMENT, not measured)
12:06 is right after 8 workflows were relaunched at ~12:05, several lanes running verify rules and suites at once. Every pwsh on the box writes the same per-user profile file with no lock, and a torn write leaves a profile that crashes every later start. Reproduction under N parallel `pwsh -NoProfile -Command 1` is the first Brainstorm step. Until it reproduces, "race" is the leading explanation, not the established one.

## Where pwsh is launched concurrently (origin/main 8ab733d7; re-verify)
- `.crew/verify.json:206`: the verify rule that execs pwsh on check-powershell.ps1.
- `_verify/smoke.sh:126`, `:134`, `:183`, and `_verify/run-all.sh:125`, `:133`.
- `scripts/_test/check-powershell.sh:76`, `:98`, `:123`, `scripts/_test/lsp-stack-tools.sh:638`, `scripts/_test/mcp-preflight-catalog.sh:755`, `:765`.
- Crew hooks that dispatch to a `.ps1` twin (`crew_tool_dispatch`) - check whether any runs pwsh on Linux.

## Scope for Brainstorm
1. Reproduce: N parallel pwsh starts against one cache dir, and confirm the corrupt-profile crash.
2. Fix at the launch sites: give each run its own cache so no two pwsh processes share the profile. Options: a per-process `XDG_CACHE_HOME` under the run's temp dir, or turning the startup profile off for these non-interactive runs, if the runtime has a supported switch (research it; do not guess an env var name). Keep it in one shared helper, so the .sh/.ps1 pairs and every `_test` suite resolve pwsh the same way.
3. Classification: a pwsh that dies with `Stack overflow.` before running any script is "the tool could not run", not "the .ps1 is bad". Consider reporting it as TOOL BROKEN (like the rc 77 TOOL MISSING path) with the cache path and the repair, per the repo lesson "A failing gate names the failure, not the cause".
4. Windows: check whether Windows PowerShell 7 shares a per-user profile the same way (`%LOCALAPPDATA%\Microsoft\PowerShell`) and whether the fix must cover it too.
5. Regression test that breaks the fix on purpose: sabotage the per-run cache (point it back at a shared dir) and show the parallel repro goes red.

## Unknowns
- Whether the lanes' own worktrees saw the same crash between 12:06 and 12:17 and recorded it as a failed .ps1 check (check lane journals / gate logs).
- Whether snap confinement changes where the profile is written for other users.

## Owner decision 2026-09-30 - catch up with main by MERGE, never rebase
the owner, 2026-09-30, verbatim choice "Merge main in (Recommended)", after "rebase alot fo these before merge we did 4-5 prs outside of here that merged to main". origin/main has moved (it was a61a6f38 when this note was written: T-0088 #262, the QA fixes #263-#267, crew 1.0.69).
- Before your NEXT Review round and again right before Land: `git fetch origin && git merge origin/main` (a merge commit; mechanical conflicts only - a behavioural conflict is a STOP to the owner). Never `git rebase`, never force-push, never squash.
- After each merge: version one patch past origin/main's, refresh the artifacts until fresh and committed, re-run the suites serially under heavy-run, and state the merged origin/main sha in the phase evidence.
- A review receipt that went stale ONLY because of such a merge follows the existing merge-only rule; anything else needs a new round.

## Owner decision 2026-09-30 - run the suites in parallel (pytest-xdist installed, capped at 4)
the owner, 2026-09-30, verbatim choice "Install + cap at -n 4 (Recommended)". pytest-xdist 3.8.0 is now installed (apt python3-pytest-xdist); <local-tmp>/heavy-run exports PYTEST_XDIST_AUTO_NUM_WORKERS=4, so `-n auto` means 4 workers inside the wrapper.
- Full crew suite, always through heavy-run: `python3 -m pytest plugin/crew/tests/ -q -n 4 -m "not wallclock"`, then `python3 -m pytest plugin/crew/tests/ -q -m wallclock` serially (both must pass). This is main's own .crew/verify.json rule with the worker count pinned. Other pytest suites: same shape.
- pylint as CI runs it: `python3 -m pylint -j 4 $(git ls-files "*.py")`.
- Quote the new timing in the evidence (the serial full suite took ~700-900s here; #263 measured ~230s at -n 4).
- A test that passes serially and fails only under -n 4 is a real finding (shared-state race, as #267's d3cf73c3), not something to paper over: report it, never skip it.

## Direction check 2026-10-04

Checked against origin/main `155fe6d8` (crew 1.0.322). Owner not available; the recommended option
below is taken as the default and the questions are listed at the end.

**What merged work already fixed.**
- The cause is established, no longer a hypothesis. L-0557 (PR #300, merge `ffd11270`) measured it:
  pwsh reads `$XDG_CACHE_HOME/powershell/StartupProfileData-NonInteractive` at start-up and rewrites
  it at exit, concurrent pwsh race on that one file, and a reader that catches it half-written dies
  before running a statement (`CHANGELOG.md:1241-1259`). A later measurement recorded in L-0559's
  direction showed the race can also leave a persistently corrupt profile, which is this ticket's
  original incident. Scope item 1 (reproduce) is therefore done and is not repeated here.
- Every pwsh the **test suites** spawn has its own `XDG_CACHE_HOME`: `plugin/crew/tests/conftest.py:88-106`,
  the ten shell suites (for example `scripts/_test/check-powershell.sh:57-61`), and the static guard
  `plugin/crew/tests/test_pwsh_cache_isolation.py` with its rule at `.crew/verify.json:499-506`. That
  covers this direction's launch-site bullet for `scripts/_test/*`.

**What is still true.** The launch sites that are neither a test suite nor a crew hook still start
pwsh on the shared per-user cache, and they are the ones the original incident went through:
- `.crew/verify.json:251` - the `**/*.ps1` rule execs pwsh directly. The Stop gate runs it in every
  lane, so several worktrees run it at once.
- `_verify/smoke.sh:130`, `:138`, `:187` and `_verify/run-all.sh:125`, `:133`.
- `scripts/gate-runner.py:174` - the `check-powershell` step.
L-0557's guard does not see any of them: it scans `tests`/`_test` suites only. So on a machine with
several lanes, the repo's own gate can still corrupt the shared profile, and once it has, every one
of these sites fails until someone deletes the file.

**What changed in scope.**
- Crew's production `.ps1` hooks are now L-0559 (direction), split from L-0557. They are out of this
  ticket.
- The follow-up findings on L-0557's guard are L-0567 (direction). Out of this ticket.
- Scope item 2's "one shared helper for every `_test` suite" is superseded: the suites each export
  the variable and a guard holds them to it. The helper here serves the non-test sites only.

**Options.**
1. *(Recommended, taken.)* One small launcher, `scripts/pwsh-isolated.sh`, that resolves pwsh, gives
   the run a private throwaway `XDG_CACHE_HOME`, forwards the exit status, removes the directory, and
   labels a signal death as TOOL BROKEN instead of leaving it to read as a failed `.ps1` check. The
   verify rule, `smoke.sh`, `run-all.sh` and the gate-runner step all go through it. Same mechanism
   as the merged L-0557, so one explanation covers tests and gates. A private cache also sidesteps an
   already-corrupt shared profile, which a retry cannot.
2. Set `DOTNET_MultiCoreJitMinNumCpus=1024` at the same sites (L-0559's candidate). No directory and
   no cleanup, and it would cover Windows if it works there. Not taken: it is an undocumented runtime
   knob, untested on Windows, and its race measurement was still pending in L-0559's notes. With one
   launcher the switch is a one-line change if L-0559 adopts it.
3. Do nothing here and rely on host mitigation (a read-only or blocked profile path). Not taken: it
   does not travel to clones of this repo.

**Windows.** pwsh keeps the profile under `LOCALAPPDATA`, so `XDG_CACHE_HOME` changes nothing there
(L-0557's evidence). Whether the race happens on Windows has not been measured by anyone. This
ticket does not change Windows behaviour and says so; the question stays open under L-0559.

**Classification.** Kept, in its smallest form: no probe run and no new exit code. A pwsh that ends
on a signal (exit 128 or above) gets one stderr line saying the tool died, on which signal, and that
it ran on a private empty cache, so the shared profile is ruled out. The exit status is unchanged
and still fails the rule. `scripts/gate-runner.py:507-508` already reports such exits as
COULD-NOT-TELL.

**Regression test.** Deterministic, with a stub pwsh that records its environment; no parallel-crash
loop (the race needs about 20-50 heavy runs to show, which is not a test). The sabotage is the
direction's own: point the launcher back at the shared cache and the suite goes red.

### Open questions for the owner
1. Mechanism: private `XDG_CACHE_HOME` (taken) or the `DOTNET_MultiCoreJitMinNumCpus=1024` knob once
   L-0559 settles it? Default: private cache now; revisit when L-0559 decides.
2. Windows: is a burn-in on a Windows box wanted before this lands, or is "unchanged on Windows,
   tracked under L-0559" acceptable? Default: the latter.
3. Should repos that *use* crew get the same protection for their own `.ps1` verify rules (the gate
   setting a private cache for every rule it runs)? That edits `verify-gate.*`, a harness path, so it
   would be its own tooling-only ticket. Default: not in this ticket; no ticket filed.
4. The ticket is marked "handed to cloud, do not pick up locally". This check and the spec were
   written locally as preparation only; no code was changed.
