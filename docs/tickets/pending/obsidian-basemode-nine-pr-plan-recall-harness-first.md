# Obsidian and Base Mode plan: nine small PRs, recall test harness first (land #757, then the rest in order)

Priority: unassigned (owner to set).
Status: needs ticket (no T-/L-/C- id yet). Recorded 2026-11-17 from the owner's open-item list.

## Problem

The owner approved an Obsidian and Base Mode plan of nine small PRs, with the recall evaluation harness first. Only the harness exists, as draft PR #757. The other eight have no PR.

## Evidence

Plan file (named by the owner, NOT read by this ticket's author, it lives in another repo): `dashboards/crew-artifacts/obsidian-basemode-proposal.md` on branch `dashboards/crew-artifacts-20261117` of the `abs-claude-development` repo, section E, lines 143 to 155. Approved order: `.work/HANDOFF.md` line 25 (same repo, not read).

VERIFIED by `gh pr view 757` on 2026-11-17: draft, head `09c407465`, branch `feat/obsidian-recall-eval-harness`, base `main`, `mergeStateStatus` BEHIND, 19 checks SUCCESS and 3 SKIPPED, 0 failing, last update 2026-11-11. Its body: "Item 1 of the approved recall order: an evaluation harness, no recall behaviour change", `scripts/recall-eval.py`, a fixture builder, a 16-case golden set (13 gated, 3 gap cases), a 12-test suite, registered in `scripts/gate-runner.py`, `.github/workflows/marketplace.yml` and the `scripts-checks` rule in `.crew/verify.json`; baseline measured on main `170d4c4b2`. The PR touches no plugin file, so no version bump. Its "Not in this PR" list: held-back titles, recall speed, superseded ranking, `files:` recall.

Owner's observation, to be confirmed against the plan file: PRs 2, 4, 6, 8 and 9 have no slot in the approved order, and "recall speed" maps to no numbered PR. UNVERIFIED here.

## Recommended next step

1. Bring #757 up to date with main (it is BEHIND), re-run its gates, review it, and land it first.
2. Reconcile the nine-PR list in section E with the approved order in HANDOFF.md: assign a slot to PRs 2, 4, 6, 8, 9 or drop them, and say which numbered PR "recall speed" is.
3. Open the remaining PRs one at a time, in the approved order, each flipping a `gap` case or a baseline number in the harness (the harness removes a `gap` marker when its PR closes the gap).

## Acceptance criteria

- #757 merged, with its baseline numbers re-measured on the current main.
- A table of all nine PRs: number, title, slot in the approved order, PR link or "not started".
- Each later PR states which golden case or baseline number it moves.

## Owner questions

1. Which slots do PRs 2, 4, 6, 8, 9 take, or are they dropped?
2. Which PR carries "recall speed"?
3. Does the 3000-note baseline (walk deadline hit on every run) set the speed target?

## Out of scope

Doing PRs 1 to 4 and 6 to 9; changing recall behaviour inside #757.

## Related

#757; `scripts/recall-eval.py`, `scripts/recall_eval_fixture.py`, `scripts/_test/recall-eval/golden.json`; `plugin/obsidian-vault/` recall scripts (named by the PR, not opened).
