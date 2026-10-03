# L-0526 direction - merge train slice 1b (tooling): the gate round takes the train

Status: approved 2026-09-30 by the owner's decision "Split into 2 PRs" (relayed by the coordinator),
under standing authority. Split from L-0520 (`.work/tickets/L-0520/direction.md`, Option 1, slice
1), whose approved direction and settled decisions apply unchanged.

T-0087's `scripts/check-tooling-pr.py` (merged `a7524aac`, owner 2026-09-28: "tooling PRs carry no
feature work") refuses a review/gate-harness change carrying feature work. L-0520 therefore lands
as PR 1 (the `crew_train.py` CLI, `/crew:done`'s landing section, docs). This ticket is PR 2, the
harness half, cut from main after L-0520 merges (merge main, never rebase), with its own review
budget and crew version bump:

- `review_run.py` takes the train (`crew_train.acquire`) after the CLEAN-receipt short-circuit and
  the verify gate, before the standards self-check and before reserving a round; waiting, `merge
  <base> first`, an unreadable train or any failure is exit 6, no round spent; unarmed = unchanged.
- `review_prompt.py` lists rerere-replayed files from the ticket's merge log under
  `== Catch-up merges (rerere) ==`.
- `/crew:review` names exit 6; the docs that describe the gate round say so.
- Sabotage rows S1-S15 (`sabotage_train.py`), their registration in `sabotage.py`, and
  `test_review_run_train.py`.

The implementation exists at `b7fe895a` (L-0520's pre-split head, on `origin/L-0520-merge-train`)
and is restored from there onto the new main, re-checked against whatever main holds then.
