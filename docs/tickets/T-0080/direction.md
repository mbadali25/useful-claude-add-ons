# T-0080 direction          status: direction   risk: med
## Ask
Filed 2026-09-27 ~20:45 CDT from the session crashes of 18:36 and 19:08 CDT. Two sabotage entries in `plugin/crew/tests/sabotage_cloud.py` turn a bounded read into an unbounded one, so an uncapped full `sabotage.py` run grows a single python3 to ~20 GB and the global OOM killer takes the orchestrating Claude session with it:
- `:544` "cloud guard r1: a FIFO or device is opened as a plan" (`[plan-dev-zero]`, reads /dev/zero; measured: both OOM dumps, 19.6 and 20.1 GB RSS).
- `:564` "cloud guard r1: azureProfile.json opened whatever it is" (reported by the T-0075 Implement agent as also stopping every full run at the 6G heavy-run cap; not independently measured yet).
Host-side mitigation in place since 2026-09-27: `<local-tmp>/heavy-run` wraps each run in a 6G cgroup. The suite itself has no bound, so it is only safe behind that wrapper - on CI and on other machines it is not.

Direction to settle at brainstorm: bound the harness, not the mutation - run each sabotaged test child under an RLIMIT_AS / job-object memory cap (and a wall-clock timeout) so a runaway mutation goes RED by being stopped at a small ceiling, reported as RED-by-limit rather than a crash. Keep the two entries: they are correct mutations. Neighbouring case: every sabotage entry whose target reads a path the test controls.
## Options
none yet - to be settled at /crew:brainstorm.
## Approval
Status `direction`. No priority set by the owner.

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
Checked against origin/main `155fe6d8` (crew 1.0.322). Owner go 2026-10-04; the owner was not available for questions, so each choice below is the recommended default and is repeated under "Open questions for the owner".

Still true:
- The harness has no bound of its own. `plugin/crew/tests/sabotage.py:3088-3112` (`run_test`) is a bare `subprocess.run` with no timeout, no memory limit and no process group. `git grep -nE "setrlimit|RLIMIT|killpg|start_new_session" origin/main -- 'plugin/crew/tests/sabotage*.py'` prints nothing. No commit on origin/main since the ticket was filed touches this (`git log origin/main -- plugin/crew/tests/sabotage_cloud.py` ends at `2b18f7ab`, crew 1.0.42).
- Both entries are still on main: `plugin/crew/tests/sabotage_cloud.py:544` (`[plan-dev-zero]`) and `:565` (azureProfile.json; the ticket said `:564`).
- The only bound is host-side: `scripts/gate-runner.py:225` runs `sabotage.py` in its solo phase inside the heavy-run wrapper's memory cgroup when that wrapper exists, and says `heavy_run: absent (uncapped)` when it does not. CI does not run `sabotage.py` at all (`scripts/gate-runner.py:74`). L-0525's log shows the full run still dies at the azureProfile entry (exit 143) even inside the wrapper.

What changed, or was wrong in the 2026-09-27 note:
- The two entries are not alike. Read at origin/main:
  - `:565` replaces the bounded `_read_small` with `json.load(handle)` (`plugin/crew/hooks/scripts/cloud_guard.py:2471-2472`). On a symlink to `/dev/zero` that reads to an end that never comes, so memory grows until the test's own 30-second ceiling (`plugin/crew/tests/test_cloud_guard_environments.py:1186-1199`). This is the unbounded read. L-0525 and T-0087's row both name this entry as the one that stops the run.
  - `:544` makes `_is_regular` return True (`cloud_guard.py:1726-1727`). The plan is then hashed in 1 MiB blocks (`cloud_guard.py:1848-1850`): endless, but constant memory, and the same 30-second ceiling fails the test. By the code, this entry should not grow. The 19.6 and 20.1 GB dumps attributed to it were not re-measured here (no pytest or sabotage runs on this host for this hand-off), so the attribution is an Unknown in the spec, to be measured first.
- `sabotage.py` is at the pylint module limit: 3400 of 3400 lines (`.pylintrc:140`). New harness code cannot go into that file.
- The tooling-PR rule (T-0087, merged) now applies: `plugin/crew/tests/sabotage*.py` is in `HARNESS` (`scripts/check-tooling-pr.py:79`), so this lands as a tooling-only PR. Tests, docs, version files, the code map and `.crew/verify.json` ride along (`:99-118`).
- The gate runner (L-0513, done) already treats a timed-out or signal-killed step as COULD-NOT-TELL and kills the whole process group. That is the outer layer. This ticket is the inner one, per entry.
- Measured on the Linux host 2026-10-04 (pwsh 7.6.5, python3 3.14.4): under `ulimit -v 4194304` (4 GiB) `pwsh -NoProfile -Command '"ok"'` exits 0 and node starts; under `ulimit -v 2097152` (2 GiB) pwsh dies with "Out of memory" (exit 134). So an address-space cap is workable at 4 GiB, and the margin for pwsh-driven test targets is not wide.

Options:
1. **Recommended: cap each entry's test process in the harness.** `run_test` starts the pytest child in its own process group with `RLIMIT_AS` (default 4096 MiB, inherited by the guard the test spawns) and a wall-clock limit (default 600 s). Over the memory cap, the reading process gets `MemoryError`; the guard's own handler turns that into an "internal error" refusal (`cloud_guard.py:3357-3366`), the azureProfile test's `assert "unknown" in reason` fails, pytest exits 1 and the entry is `RED (good)` by a real assertion. A timeout kills the group and is reported `RED BUT UNPROVEN -- timed out`, which fails the suite: could-not-tell stays could-not-tell. No output parsing, no new outcome that counts as a pass. The run prints the bound once, and prints `absent` where the platform does not enforce one (Windows, macOS).
2. A watchdog that polls the child tree's resident memory and kills it at a ceiling, reported as a new `RED BY LIMIT` outcome that counts as a pass (the 2026-09-27 wording). Rejected as the default: a kill is not evidence that the named test caught the mutation, and a passing outcome that is not a test failure is the collapse `sabotage.py:3073-3085` (finding 13) was written to stop. It also needs a `/proc` walker, which is a second mechanism.
3. Put the cap only in the test's `_run_bounded`. Smallest change, but it bounds two tests and leaves every later mutation of a read path unbounded. Rejected: the direction is to bound the harness.

Risk the recommended option carries: the cap could make an unmutated test fail (pwsh needs more than 2 GiB of address space to start), and a cap-induced failure would read as `RED (good)` for a vacuous test. The spec closes that with a one-time measured check (the crew suite, slow cases included, passes under the same `ulimit -v`) and keeps the cap configurable.

Open questions for the owner (defaults taken):
1. Is "RED by a real assertion under the cap" acceptable in place of a separate `RED BY LIMIT` outcome? Default: yes (option 1).
2. Default cap 4096 MiB and 600 s per entry? Default: yes; both overridable by environment variable, an unreadable value refuses to run.
3. Windows and macOS get the timeout only, with the memory cap reported `absent`. A Windows job object is left out. Default: yes; a follow-up ticket if a Windows sabotage run is ever wanted.
