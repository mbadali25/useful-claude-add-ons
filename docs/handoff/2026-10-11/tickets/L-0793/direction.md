# L-0793: two timing-fragile tests failed main's scheduled CI run on a slow runner

Title: [bug] timing-fragile tests: the 6.0s heartbeat bound and the promote-gate slow-python deadline case fail on a slow runner

Type: bug (tests; test_promote_gate_review.py belongs to the review/gate harness, so that half lands under the T-0087 tooling rule)
Priority: -
Status: direction. Not a lane yet. NOT to be implemented from this file alone.
Filed by: the crew coordinator (ac5b48330c1347c0d), 2026-10-11 14:50 CDT, on the owner's decision.
Related: L-0768 (#597, promote-gate), L-0777 (#600, where a third promote-gate observation appeared in CI), W-0131 (python resolver; detail in the ticket).

## Owner decision this ticket carries

Matthew, 2026-10-11, through AskUserQuestion, relayed by the lead to the coordinator: main's red scheduled run of
2026-10-11 does NOT reset the "main green for 7 days" count of the crew feature freeze, and the two tests that
failed in it are ticketed as timing-fragile. This is that ticket. Recorded as relayed; the coordinator did not
hear the answer first-hand.

## What was seen

Scheduled run 38145816635 of pytest-crew.yml on main `987ea4fb8`, created 2026-10-11 14:06:05Z. Three failing jobs
of 16, two real test failures. Read by the L-0789 lane, read-only; nothing was re-run.

1. Job 114488803048, crew-shell-matrix (ubuntu-latest), Python 3.13.16:

   ```
   FAILED plugin/crew/tests/test_promote_gate_review.py::test_a_slow_python_plus_a_hung_check_still_ends_inside_the_hook_timeout[sh] - AssertionError: the hung git was never reached: the case proves nothing
   >       assert pids.exists(), "the hung git was never reached: the case proves nothing"
   E       AssertionError: the hung git was never reached: the case proves nothing
   =========== 1 failed, 2955 passed, 22 skipped in 1252.41s (0:20:52) ============
   ```

   The `[ps1]` case passed in the same job. The earlier asserts in the test (`code == 2`, `took < 20`) passed.

2. Job 114489607838, crew-windows-default (2/6), Python 3.13.15:

   ```
   FAILED plugin/crew/tests/test_crew_coord.py::test_heartbeat_process_exits_after_pid_gone - assert (673.9087791 - 667.2050376) < (0.5 + 5.0)
   >       assert time.monotonic() - started < 0.5 + 5.0
   plugin\crew\tests\test_crew_coord.py:1063: AssertionError
   ========== 1 failed, 3214 passed, 116 skipped in 1136.07s (0:18:56) ===========
   ```

   That is 6.70s measured against 6.0s allowed.

3. Job 114499507198, crew-shell-matrix (windows-latest): no failing test of its own. It is red only as the
   roll-up of job 2 (`DEFAULT_RESULT: failure`, `SLOW_RESULT: success`, `WALLCLOCK_RESULT: success`).

The push run on the same sha, 38144717433, passed all three jobs and both tests
(`2956 passed, 22 skipped in 1031.14s`; `3215 passed, 116 skipped in 694.68s`). There was no code change between
the two runs. The two earlier scheduled runs (38057058915 on 2026-10-10, 37943907325 on 2026-10-09) were green.
Schedule: `cron: '17 7 * * *'`; in practice the runs start around 14:00Z.

Evidence kept: the failed extract and the full job logs are in the session scratchpad,
`/tmp/claude-0/-repos-personal-useful-claude-add-ons/41f532c6-dbbb-4861-9178-6bb4373d64e7/scratchpad/main-scheduled-38145816635-failed.log`
and `job-<id>.log` beside it. The scratchpad is session-scoped: copy them into this ticket's folder before the
session ends if this ticket is to be worked.

## Readings (the lanes', not proven)

- Heartbeat test: a plain elapsed-time bound on a slow runner. The same shard took 1136s here against 695s in the
  push run, with setup durations of 154.81s and 123.50s. The test is not marked `wallclock` (inferred from a grep
  for the marker in test_crew_coord.py: no hits).
- Slow-python test: the gate hit its own 16s deadline before reaching the hung git. The test's docstring budgets
  seven 1.8s interpreter starts, "about 11.5s before the search starts", against that 16s. On a slower run the
  margin goes. This is read from the test body, not from a timing line in the log. The test is marked `slow`, not
  `wallclock`.
- Neither is a disagreement between the sh and ps1 flavours.

## Related observations from the same day (cross-references, each with its own record)

1. #600 (L-0777) CI, head 46d015a35, run 38162614845, job 114538511973, `Pytest / test (3.12)`:
   `test_promote_gate_literal_match.py::test_both_flavours_pick_the_same_environment[map0]` failed with
   `'deploy target=prod': promote-gate.sh chose qa,production, promote-gate.ps1 chose BLOCKED qa,production`.
   A parity disagreement, seen once; `test (3.11)` and `test (3.13)` passed on the same sha. Saved log:
   `.work/tickets/L-0777/evidence/ci-run38162614845-job114538511973-attempt1.log`. Lane B1's reading: the ps1 gate
   matched the same environments and then exited 2 at one of three sites (promote-gate.ps1 :652 Stop-Promotion,
   :1090 Deny-ReviewUnknown, :1172 final verdict; line numbers on origin/main 987ea4fb); the test helper `_chosen`
   drops stderr, so the log cannot say which. Best-supported cause: the single 16s whole-gate deadline, measured
   from the pwsh process start (promote-gate.ps1:30-33), or a python-probe timeout. Not proven.
2. [redacted: b], Git Bash on a real Windows box, 2026-10-11: on old head 9d45c697a of #597 at 47 to 100% CPU, four
   promote-gate cases failed with "the gate's deadline passed before the review check could finish"; on main
   987ea4fb at 100% CPU one case took 14.80s against the 16s deadline and passed. Record:
   `.work/tickets/L-0768/done-waiver.md`.
3. Lane B1's timings on this host, 2026-10-11, load average 10 to 14: the gate for parity map0 takes about 0.35s
   (sh) and about 1.6s (ps1) on main and on #597's head, the difference below run-to-run noise. #597 adds a net
   3 git starts and 0 interpreter starts per matched deploy that passes the tree checks. Idle and loaded cells
   are still owed. Record: `.work/tickets/L-0768/done-waiver.md`, section "FOR A REVIEWER OF #597".

## Unknowns

- Whether the three promote-gate observations share one cause (a 16s whole-gate deadline that a slow or loaded
  box exhausts). Nothing proves it yet.
- Which of the three ps1 sites fired in the #600 CI failure.
- Whether the heartbeat bound has any relation to the promote-gate cases beyond both being time bounds.
- How slow the scheduled runner was relative to a normal one, beyond the shard's total time.

## Acceptance (draft)

- The parity assert in test_promote_gate_literal_match.py prints the gate's stderr when the flavours disagree, so
  the next occurrence names the site. (First step; it is cheap and settles observation 1.)
- The heartbeat test and the slow-python test either measure what they mean without a wall-clock bound that a
  slow runner can miss, or are marked and run where wall-clock bounds are honoured (`wallclock`), with the reason
  stated. A bound is not simply raised without saying what it protects.
- Each change is sabotage-tested: the behaviour the test protects is broken and the test goes red.
- The scheduled run on main is green on the runner class that failed.
