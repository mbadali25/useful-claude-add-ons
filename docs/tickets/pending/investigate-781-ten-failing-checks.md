# #781 (per-run review base override): find out why 10 checks fail

Priority: unassigned (owner to set).
Status: needs ticket (no T-/L-/C- id yet). Recorded 2026-11-17 from the owner's open-item list.

## Problem

#781 ("feat(crew): per-run review base override") has 10 failing checks and nobody has read them. Until they are read it is unknown whether the PR's change breaks them or whether main is already red.

## What the PR is

VERIFIED by `gh pr view 781` on 2026-11-17: open, NOT draft, head `3e6136af4`, branch `feat/review-base-override`, base `main`, `mergeStateStatus` BEHIND, last update 2026-11-16T02:12Z. Body: adds `review_run.py --prepare --base-branch REF` and a `CREW_BASE_BRANCH` env fallback so PRs targeting `qa` are measured against `qa`; env wins over `tickets.baseBranch`; unset keeps today's behaviour; an invalid ref stops the run (exit 3); tests `plugin/crew/tests/test_scope_base_override.py` (8, red before the change). `review_run.py` is a review-harness path (see `HARNESS` in `scripts/check-tooling-pr.py`), so the harness-alone rule may apply: INFERRED, not checked.

## Evidence

VERIFIED (rollup): 10 FAILURE, 20 SUCCESS. Failing: `check`, `build (3.12)`, `test (3.12)`, `crew-windows-default (1/6)` through `(6/6)`, `crew-shell-matrix (windows-latest)`.

Partly read (job logs, run 43790703175 and 43790703218):
- `check` (job 133048217312): ends with "1 problem(s):" then exit code 1. The problem text was not read.
- `build (3.12)` (job 133048217488): the step exits with code 16. Cause not read (the log mentions a comment about failing "on code nobody touched").
- The other 8 jobs were not opened. All six Windows default shards failing at once suggests a shared cause (a collection or import error, or a stale base): INFERRED only.

The PR is BEHIND main, so the failures may be cured by a merge of main, or may be inherited from main at that time: UNKNOWN.

## Recommended next step

Open each failing job's log (`gh run view --job <id> --log-failed`) and record the first error per job. Then merge or rebase onto current main and re-run to separate inherited failures from the PR's own. Do not fix anything under this ticket until the cause is known.

## Acceptance criteria

- One line per failing check with its first error, VERIFIED from the log, and whether it reproduces on current main.
- A decision: fix in #781, fix on main, or close #781 as superseded.
- If `review_run.py` is a harness path, the PR is confirmed to land alone.

## Owner questions

1. Is the per-run review base override still wanted (the `qa` environment now exists on main, PR #730)?
2. Who owns #781 (its session id differs from the guards-master PRs)?

## Out of scope

Merging; reviewing the feature design.

## Related

#781; `plugin/crew/hooks/scripts/review_run.py`, `plugin/crew/tests/test_scope_base_override.py` (named in the PR body, not opened).
