# L-0563 direction - Sabotage entries for L-0516's deadline polls (tooling PR split from L-0516)

Status: approved (split under the standing tooling-PR rule, owner 2026-09-30: "split, do not ask").

## Why this ticket exists

`scripts/check-tooling-pr.py` refused L-0516's branch with both harness and feature paths:

    tooling-pr: FAIL - a tooling change carries feature work; land these separately:
      plugin/crew/skills/crew-qa-standards/references/harness.md

`plugin/crew/tests/sabotage*.py` is HARNESS, `harness.md` is feature. L-0516 (feature PR) keeps
the poll helpers, the test fixes, the verify rule and the doc; this ticket carries only the four
`sabotage_qa.py` entries that prove them.

## What it carries

The four entries are already written and proven RED on L-0516's branch at `080cea00` (a filtered
`sabotage.py` run printed `RED (good)` four times and `SABOTAGE SUITE: PASS`). They are parked on
branch `L-0563-build`, which points at `080cea00` (stacked on L-0516's commits). After L-0516 lands,
merge origin/main into `L-0563-build` (`git -c rerere.enabled=false merge origin/main`); its diff
against main is then `sabotage_qa.py` plus refresh artifacts, and it takes the next free crew
version at that time.

1. "poll_until probes once and never waits" -> `test_poll_fixtures.py::test_poll_until_returns_once_a_late_child_has_died`
2. "poll_until reports success at the deadline" -> `test_poll_fixtures.py::test_poll_until_reports_a_child_that_never_dies_at_the_deadline`
3. "wait_for_pidfile accepts an existing empty file" -> `test_poll_fixtures.py::test_wait_for_pidfile_waits_past_an_empty_file_for_the_pid`
4. "the ps1 probe kills only the launcher" (`completion-audit.ps1` `Kill($true)` -> `Kill($false)`) -> `test_event_claim_crash_safety.py::test_the_ps1_probe_timeout_kills_the_launchers_child_too`

Depends on: L-0516 merged.

## Update 2026-10-01 (L-0516 Fix phase, review round 1)

L-0516's review round 1 fixes changed `poll_until`'s loop, so entry 1's anchor
(`if done(value) or time.monotonic() >= deadline:`) no longer exists. `L-0563-build` was
fast-forwarded onto L-0516-build `7904a4ba` and commit `32774479` re-adds the four entries with
entry 1 re-anchored to `    while not done(value):` -> `    while False:`, plus two new ones:

5. "poll_until probes once more after the deadline" -> `test_poll_fixtures.py::test_poll_until_never_returns_a_value_first_seen_after_the_deadline`
6. "child cleanup reaps with an unbounded wait" (target `test_poll_fixtures.py`, `proc.wait(timeout=10)` -> `proc.wait()`) -> `test_poll_fixtures.py::test_child_cleanup_reaps_with_a_bounded_wait`

Filtered `sabotage.py` run at `32774479` (heavy-run): six `RED (good)`, `SABOTAGE SUITE: PASS`, rc 0.
`test_sabotage_harness.py`: 17 passed. Still stacked on L-0516; merge origin/main after L-0516 lands.
