# T-0506 the repo's own pwsh gate launches run on a private startup-profile cache          status: spec   risk: med

Anchored to origin/main `155fe6d8` (crew 1.0.322). Direction: `.work/tickets/T-0506/direction.md`,
"Direction check 2026-10-04" (option 1, taken as the default; the owner was not available).

## Written 2026-10-04

First spec for this ticket; there was no earlier spec or plan to refresh. The direction's scope
shrank because L-0557 (merged) already covers every test suite and L-0559 owns crew's `.ps1` hooks.
What is left is the four non-test launch sites named under Evidence.

## Intent

Every pwsh that this repo's own gate scripts start runs with a private, throwaway `XDG_CACHE_HOME`,
so no two of them share PowerShell's startup profile and an already-corrupt shared profile cannot
fail them. One launcher, `scripts/pwsh-isolated.sh`, does it, and the verify rule for `.ps1` files,
`_verify/smoke.sh`, `_verify/run-all.sh` and the gate runner's `check-powershell` step all start
pwsh through it. When pwsh ends on a signal, the launcher says on stderr that the tool died (not
that a `.ps1` failed its check) and passes the exit status on unchanged.

### Launcher contract (`scripts/pwsh-isolated.sh`, POSIX sh, LF, called as `sh scripts/pwsh-isolated.sh <pwsh args>`)

1. **Resolve pwsh.** `$PWSH` when it is set and non-empty (the override the suites already use,
   `scripts/_test/check-powershell.sh:51-55`); otherwise the same candidates in the same order as
   today's rule at `.crew/verify.json:251`: `pwsh`, `pwsh.exe`, then the four known Windows
   locations. Nothing resolves, or `$PWSH` is not runnable: print the existing
   `TOOL MISSING: pwsh ...` line on stderr and exit 77. pwsh is not started.
2. **Private cache.** Create a directory with `mktemp -d` and **assign** `XDG_CACHE_HOME` to a path
   inside it (assigned, not defaulted: an ambient value is the shared one). If the directory cannot
   be created, pwsh is **not** started on the shared cache: print a `TOOL BROKEN:` line naming the
   failure and exit 1.
3. **Run.** Start pwsh with the arguments exactly as given (count, order and content, including
   arguments with spaces). stdout and stderr pass through. stdin is `/dev/null`: no call site feeds
   pwsh stdin, and `smoke.sh` calls it inside a `while read` loop whose input pwsh must not consume.
4. **Signals.** A TERM or INT delivered to the launcher ends the pwsh child as well. `run-all.sh`
   wraps the call in `timeout`, which signals only its direct child, so a launcher that merely
   waited would turn a timeout into a hang.
5. **Clean up and exit.** The directory is removed on every exit path (normal, non-zero, signal).
   The launcher exits with pwsh's own status.
6. **Label a tool death.** When pwsh's status is 128 or above, print one stderr line starting
   `TOOL BROKEN: pwsh` that gives the status, the signal number (status minus 128), and that the run
   used a private empty cache, so the shared startup profile is ruled out. The status is still
   passed on unchanged. No retry and no second attempt.
7. **Windows.** The variable is set and has no effect there (the profile is under `LOCALAPPDATA`).
   The header comment says so. Nothing else is done for Windows.

## Exclusions

- No retry, and no change of exit status based on a crash signature. Item 6 only adds a line.
- No probe run before the real one (it would double every pwsh start).
- No crew production code: not `plugin/crew/hooks/hooks.json`, not any hook `.sh`/`.ps1`/`.py`, and
  not the verify gate itself (`plugin/crew/hooks/scripts/verify-gate.*`, `verify_record.py`). Those
  are harness paths (`scripts/check-tooling-pr.py:58-87`) and crew's hooks are L-0559. Because no
  file under `plugin/crew/` changes, there is no crew version bump and the crew doc set in the repo
  CLAUDE.md does not apply. The PR body says `Docs: none for crew - no plugin/crew file changes`.
- No change to `plugin/crew/tests/test_pwsh_cache_isolation.py`, `conftest.py` or any existing suite
  (L-0557 is merged; its accepted findings are L-0567).
- No `DOTNET_MultiCoreJitMinNumCpus` or any other runtime knob (direction option 2; L-0559 decides).
- No Windows-specific isolation and no claim that the race does or does not exist on Windows.
- `scripts/install-prerequisites.sh:3496-3501` is not changed. It is an interactive, one-at-a-time
  installer, and it is half of a matched pair with the `.ps1`.
- `.github/workflows/marketplace.yml:178-180` (`shell: pwsh`, one pwsh per hosted job) keeps its
  direct launch. Only a new step for the new suite is added.
- `plugin/crew/tests/test_crew_shell.py:22-40` is not edited. Its `VERIFY_MAP_BASH` is a frozen copy
  of the map "at 6387ab49", not a live read.
- No parallel-crash reproduction test. The cause was measured under L-0557; the race shows about once
  in 20-50 heavy runs, which is not a regression test.
- No sabotage-file entry (`plugin/crew/tests/sabotage*.py` is a harness path and this is not crew).
  The sabotage is done by hand and recorded in the PR (see Acceptance).

## Evidence

All at origin/main `155fe6d8`, read on 2026-10-04.

Cause, already measured:
- `CHANGELOG.md:1241-1259` - L-0557's entry: the profile file, the race, the two crash shapes, and
  "Hooks and production scripts are unchanged (L-0559)".
- `plugin/crew/README.md:2914-2923` - the same, and "Windows pwsh keeps the profile under
  `LOCALAPPDATA`, so the variable changes nothing there".
- `.work/tickets/L-0557/spec.md` Evidence - snap pwsh (classic confinement) honours
  `XDG_CACHE_HOME`; the PowerShell source lines that set the profile root.
- `.work/tickets/L-0559/direction.md` - a corrupt profile fails every pwsh, run alone, until the file
  is removed; a clean `XDG_CACHE_HOME` gives rc 0 on the same machine.

Launch sites still on the shared cache:
- `.crew/verify.json:249-254` - rule for `**/*.ps1`, `**/*.psm1`. `:251` is an `sh -c` loop that
  `exec`s the first pwsh found on `-NoProfile -File ./scripts/check-powershell.ps1` and otherwise
  prints TOOL MISSING and exits 77.
- `_verify/smoke.sh:68-69` resolves `PWSH`; `:122` skips (return 2) when it is empty; `:130` and
  `:138` launch it on `check-powershell.ps1` (`:138` inside a `while read` loop fed by a heredoc);
  `:187` launches it for the Windows registry probe.
- `_verify/run-all.sh:23-24` resolves `PWSH`; `:125` and `:133` launch it under `run`, which wraps
  the command in `timeout` (`:27-38`); `:136` skips when pwsh is absent.
- `scripts/gate-runner.py:174-175` - `Step("check-powershell", "cheap", ("pwsh", "-NoProfile",
  "-File", "scripts/check-powershell.ps1"), needs=("pwsh",), ci=(("marketplace.yml",
  "./scripts/check-powershell.ps1"),))`. `:416-425` `spawn_and_wait` passes `env=None` (the call at
  `:792` gives no env), so the step inherits the caller's cache.

What already exists and is reused:
- `scripts/_test/check-powershell.sh:51-61` - the suite convention: `$PWSH` override, `mktemp -d`,
  `trap ... EXIT`, `export XDG_CACHE_HOME="$TMP/xdg-cache"`.
- `scripts/gate-runner.py:107-110,507-510` - exits 129-143 already report as COULD-NOT-TELL
  ("killed by SIGABRT"), and 77 as SKIP. So the gate runner already does not call a pwsh crash a
  failed check; it only lacks the isolation.
- `scripts/gate-runner.py:142-146` `_bash_suite` and `:166` - how a `scripts/_test/*.sh` suite is
  listed. `:1273` `ci_drift` compares the table with the workflows' `run` commands, so a suite added
  to `marketplace.yml` needs a table step and the reverse.
- `.github/workflows/marketplace.yml:116-117` - how a shell suite is run in CI (`bash <path>`, not
  `./<path>`, because a new `.sh` is recorded 100644).
- `.crew/verify.json:107-120` - the `scripts/**` rule whose `run` list is "marketplace.yml's own step
  list for scripts/".
- `.crew/verify.json:499-506` - L-0557's guard rule; its paths include `scripts/_test/*.sh`, so a new
  shell suite there is scanned by `plugin/crew/tests/test_pwsh_cache_isolation.py`.
- `plugin/crew/hooks/scripts/crew_shell.py:43` - `sh` is in `SHELL_WORDS`, so a run entry beginning
  `sh scripts/...` still classifies as a bash job on Windows.
- `.gitattributes` - `*.sh text eol=lf`.
- `scripts/check-tooling-pr.py:58-87,99-118` - `HARNESS` and `ALONGSIDE`. None of this spec's Touch
  paths is in `HARNESS`; `.crew/verify.json` is in `ALONGSIDE`.
- `docs/handoff/cloud/T-0506.md:75-79` and `docs/handoff/cloud/README.md:26` - the note and its row
  must be deleted in the PR that lands this ticket.

## Unknowns

1. **Does L-0557's static guard accept the new suite?** The suite starts a stub named pwsh and, in
   one optional case, a real one. Resolve at implement: run
   `python3 -m pytest plugin/crew/tests/test_pwsh_cache_isolation.py -q -p no:cacheprovider`. If it
   flags the suite, the suite exports its own `XDG_CACHE_HOME` under its `mktemp` directory before
   the first launch, as `scripts/_test/check-powershell.sh:61` does. The guard is not edited.
2. **Signal handling in POSIX sh under Git Bash.** Contract item 4 needs the child run in the
   background with `wait` and a forwarding trap. Resolve at implement on Linux with the timeout case
   below. Git Bash behaviour is not verified by this ticket; say so in the PR ("NOT VERIFIED on
   Windows") rather than implying it.
3. **Does the race exist on Windows?** Not measured by anyone. Accepted as risk here; tracked under
   L-0559's unknown 1.
4. **Cost of a cold profile per run.** L-0559's notes measured no visible difference on Linux
   (about 0.35 s per start either way). Resolve at implement: time the `.ps1` rule's command before
   and after, three runs each, and put both figures in the rule's `why`. A run over the rule's
   `seconds` budget is fixed by re-measuring the budget, not by dropping the isolation.
5. **Any other pin on the rule's old text.** `git grep` at the anchor finds the old `sh -c` string
   only in `.crew/verify.json` and the frozen copy in `test_crew_shell.py`. Resolve at implement:
   `git grep -n 'for c in pwsh pwsh.exe'` after the change, and run the gate.

## Size and split

Estimated production lines added: about 90 (launcher about 70; `smoke.sh` and `run-all.sh` about 12
changed lines; gate runner about 4; the verify rule is one line of configuration). One new script
with one small classification, no parser, no state machine. No path in `HARNESS`. **Not split.**

## Touch

- `scripts/pwsh-isolated.sh` - new, the launcher
- `scripts/_test/pwsh-isolated.sh` - new, its suite
- `.crew/verify.json` - the ps1 rule's run entry and why; the new suite added to the scripts rule's run list
- `_verify/smoke.sh` - the three launches go through the launcher
- `_verify/run-all.sh` - the two launches go through the launcher
- `_verify/README.md` - one paragraph: pwsh checks run on a private cache, and what TOOL BROKEN means
- `scripts/gate-runner.py` - the check-powershell step goes through the launcher; a table step for the new suite
- `scripts/_test/gate-runner.py` - one new case
- `.github/workflows/marketplace.yml` - one step running the new suite
- `CHANGELOG.md`
- `.crew/codemap/verification-harness.md` - refresh, it documents smoke.sh and the rule map
- `.crew/codemap/INDEX.md` - anchor row, if the refresh moves it
- `graphify-out/graph.json` - rebuilt by graphify update
- `graphify-out/GRAPH_REPORT.md` - rebuilt by graphify update
- `docs/handoff/cloud/T-0506.md` - deleted, as the note itself requires
- `docs/handoff/cloud/README.md` - the T-0506 row removed

## Acceptance checks

Suite: `bash scripts/_test/pwsh-isolated.sh`. It builds everything under `mktemp`, puts a stub
`pwsh` (a shell script that records its arguments and environment to a file, then exits with a
status the case chooses) in front, and never reads or writes the real `~/.cache`. It maps to the
`scripts/**` rule (`.crew/verify.json:107`) once added to that rule's run list.

- [ ] `the_stub_sees_a_private_cache`: the recorded `XDG_CACHE_HOME` is non-empty, is not the
      ambient value the case exported, is not `$HOME/.cache`, and named a directory whose parent
      existed while the stub ran.
- [ ] `two_runs_get_two_caches`: two launcher runs record two different `XDG_CACHE_HOME` values.
- [ ] `the_cache_is_removed_afterwards`: after a run with stub status 0, and again with status 1,
      the recorded directory's parent no longer exists.
- [ ] `arguments_arrive_unchanged`: `-NoProfile -File "a b.ps1" -Path "c d"` reaches the stub as
      exactly five arguments with the spaces intact.
- [ ] `status_is_forwarded`: stub statuses 0, 1 and 3 come back as 0, 1 and 3, with no
      `TOOL BROKEN` on stderr.
- [ ] `a_signal_death_is_labelled_and_still_fails`: stub status 134 comes back as 134 and stderr has
      one line starting `TOOL BROKEN: pwsh` that contains `134`; the same for 139.
- [ ] `missing_pwsh_is_77_and_starts_nothing`: with `PWSH` naming a path that does not exist, and
      again with an empty `PATH` and no `PWSH`, the launcher exits 77, stderr contains
      `TOOL MISSING: pwsh`, and the stub's record file was not written.
- [ ] `no_cache_dir_means_no_run`: with `TMPDIR` pointing at a path that cannot hold a directory,
      the launcher exits 1 with `TOOL BROKEN:` on stderr and the stub's record file was not written.
- [ ] `a_timeout_ends_the_child`: with a stub that sleeps 30 s, `timeout 2 sh scripts/pwsh-isolated.sh`
      returns 124 within 10 s, the stub's process is gone, and the cache directory is removed.
- [ ] `stdin_is_not_consumed`: a `while read` loop fed three lines that calls the launcher once per
      line (stub runs `cat >/dev/null`) iterates three times.
- [ ] `no_gate_site_launches_pwsh_directly` (static, same suite): `_verify/smoke.sh` and
      `_verify/run-all.sh` contain no line that runs `"$PWSH"` as a command; every `run` string in
      `.crew/verify.json` that mentions pwsh does so only through `scripts/pwsh-isolated.sh`; and the
      ps1 rule's run entry is exactly
      `sh scripts/pwsh-isolated.sh -NoProfile -File ./scripts/check-powershell.ps1`.
- [ ] `real_pwsh_sees_the_private_cache`: where a real pwsh is present, the launcher running
      `-NoProfile -Command` that prints `$env:XDG_CACHE_HOME` prints a path that is gone afterwards,
      exit 0. Where pwsh is absent the case prints `SKIPPED: pwsh not found` and the suite's summary
      counts it as skipped, not passed.
- [ ] `python3 scripts/_test/gate-runner.py` passes, including the new case
      `case_no_step_launches_pwsh_directly`: no `TABLE` step has `pwsh` as `argv[0]`, the
      `check-powershell` step's argv is `("bash", "scripts/pwsh-isolated.sh", "-NoProfile", "-File",
      "scripts/check-powershell.ps1")` with `needs` naming both `bash` and `pwsh`, and its `ci` entry
      is unchanged. The existing drift cases pass with the new suite listed in both
      `marketplace.yml` and `TABLE` (rule at `.crew/verify.json:488-490`).
- [ ] `python3 -m pytest plugin/crew/tests/test_pwsh_cache_isolation.py -q -p no:cacheprovider`
      passes with the new suite in the tree (rule at `.crew/verify.json:499-506`; Unknown 1).
- [ ] `sh scripts/pwsh-isolated.sh -NoProfile -File ./scripts/check-powershell.ps1` exits 0 on a
      machine with pwsh and prints the checker's usual "all clean" line; `bash _verify/smoke.sh`
      passes with its PowerShell check reported as before (pass with pwsh, NOT VERIFIED without).
- [ ] `python3 scripts/_test/shellcheck-directives.py` passes, and `shellcheck scripts/pwsh-isolated.sh
      scripts/_test/pwsh-isolated.sh` reports nothing where shellcheck is installed.
- [ ] `git ls-files --eol scripts/pwsh-isolated.sh scripts/_test/pwsh-isolated.sh` shows `i/lf w/lf`
      for both.
- [ ] Sabotage, by hand, each applied alone and restored byte-for-byte, results quoted in the PR:
      (a) change the launcher's assignment so `XDG_CACHE_HOME` keeps the ambient value:
      `the_stub_sees_a_private_cache` goes red; (b) remove the clean-up:
      `the_cache_is_removed_afterwards` goes red; (c) remove the signal forwarding:
      `a_timeout_ends_the_child` goes red; (d) put a direct `"$PWSH" -NoProfile ...` launch back in
      `_verify/smoke.sh`: `no_gate_site_launches_pwsh_directly` goes red.
- [ ] Commit, then `python3 scripts/check-marketplace.py` passes (no plugin directory changed, so no
      version bump is expected; if the checker asks for one, that is a STOP, not a bump to add).
- [ ] `python3 scripts/check-tooling-pr.py` passes (no harness path in the diff).
- [ ] `docs/handoff/cloud/T-0506.md` is gone and `docs/handoff/cloud/README.md` has no T-0506 row.
- [ ] The PR body states what was not verified: Windows and Git Bash behaviour of the launcher, and
      `scripts/_test/drift-detection.sh` (skipped by default; this change does not touch the plugin
      update path).

## Dependencies

Must land before this ticket:
- **L-0557** - merged (PR #300, `ffd11270`). Established the cause and the `XDG_CACHE_HOME` mechanism
  this ticket reuses; its guard scans the suite this ticket adds.

Related, not blocking in either direction:
- **L-0559** - direction. Crew's `.ps1` hooks, the Windows question, and the runtime-knob
  alternative. If it adopts the knob, the launcher here is the one place to change.
- **L-0567** - direction. Follow-up findings on L-0557's guard. Touches the guard and `conftest.py`
  only; no shared file with this ticket except `CHANGELOG.md`.

Blocks: none.

## Open questions for the owner

1. Private `XDG_CACHE_HOME` (taken) or the `DOTNET_MultiCoreJitMinNumCpus=1024` knob once L-0559
   settles it.
2. Whether a Windows burn-in is wanted before landing, or "unchanged on Windows, tracked under
   L-0559" is acceptable (taken).
3. Whether crew's verify gate should give every rule it runs a private cache, protecting repos that
   use crew. That edits harness paths, so it would be a separate tooling-only ticket. Not filed.
4. This ticket is marked as handed to the cloud session. The direction check and this spec were
   written locally as preparation; no tracked file changed.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
