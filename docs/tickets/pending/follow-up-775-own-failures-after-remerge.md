# #775 (guards.enabled key half): own test and CI failures after its re-merge onto #774

Priority: unassigned (owner to set).
Status: needs ticket (no T-/L-/C- id yet). Recorded 2026-11-17 from the owner's open-item list. A fix agent is already working on #775; this ticket tracks the failures so they are not lost. Check the PR for a head newer than the one named here before acting.
Siblings: `codex-re-review-owed-774-775.md`.

## Problem

#775 (draft, base `feat/guards-master-switch-dispatcher`, i.e. stacked on #774) fails its own checks after being re-merged onto #774's newer head. The failures below are the ones the owner listed; none of them is in the PR's own "Results" text.

## Evidence

VERIFIED by `gh pr view 775` on 2026-11-17: head `bdebf07c2`, crew 1.3.134 per the owner (PR body names 1.3.105 to 1.3.124 rounds; the 1.3.134 figure not re-read), state OPEN, draft, `mergeStateStatus` UNSTABLE, last PR update 2026-11-16T22:34Z. Check rollup: 26 SUCCESS, 4 FAILURE. The failing checks are `check-draft (version bump pending at land)`, `test (3.12)`, `crew-windows-default (4/6)`, `crew-shell-matrix (windows-latest)`.

From the owner's list, NOT re-run or re-read by this ticket's author (INFERRED to match the CI failures above, not confirmed to map one to one):

1. `test_cloud_guard.py::test_default_config_ships_the_guard_off`: the shipped default config carries an extra `'enabled': True`.
2. An over-refusal of 72 cells in `test_guards_master_shell.py::test_an_unresolvable_target_in_a_command_that_never_names_the_owner_is_allowed`, plus the read-only/worktree and round-11-extras tests: 5 master-shell failures in all.
3. 12 owner-path-spelling cases in `test_guards_master.py` that return 0 where 2 is expected.
4. `check-draft` exits 77: `origin/feat/guards-master-switch-dispatcher` is not a ref in that CI job.

UNVERIFIED: whether items 1 to 3 are caused by #775's delta or by the merged-in #774 head (the PR body says its delta over #774 touches no HARNESS path and that `test_guards_master*.py` equals #774's, as of its round 8).

## Recommended next step

Read the failing jobs on the newest #775 head (`gh run view <run> --log-failed`), map each failure to the four items above, and decide for each whether the fix belongs in #775 or #774. For item 4, decide whether the `check-draft` job should fetch the base branch or treat a missing base ref as SKIP, not exit 77.

## Acceptance criteria

- Each of the four items has a named cause (VERIFIED by a run or a log line) and a fix or an owner-accepted deferral.
- On the head that carries the fix, `test (3.12)`, `crew-windows-default`, `crew-shell-matrix (windows-latest)` and `check-draft` are green, or each remaining red is named with its reason.
- No test is loosened to pass; a changed expectation says why.

## Owner questions

1. Should a fix for items 2 and 3 land in #774 (the base) so #775 inherits it?
2. Is `check-draft` exit 77 a CI-config defect to fix, or expected for a stacked PR?

## Out of scope

Merging #774 or #775 (owner decision); the Codex re-review (own ticket); the Configuration Guide refresh (see `housekeeping-breach-note-vault-docs-dashboards.md`).

## Related files and PRs

- #775 (`feat/guards-master-switch-key`), #774 (`feat/guards-master-switch-dispatcher`)
- `plugin/crew/tests/test_cloud_guard.py`, `test_guards_master_shell.py`, `test_guards_master.py` (named by the owner; not opened here)
