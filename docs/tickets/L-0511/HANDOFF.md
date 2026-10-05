# Cloud handoff: L-0511

**Version bump and artifact refresh happen once at land, after the final catch-up merge**

Handed to a cloud session on 2026-10-05 by owner instruction. Do not pick up locally.

**PR 1 is buildable now. PR 2 is not buildable until L-0522 PR 2 (the delta gate) has merged.**

- **Role:** standalone ticket, decision 5 of the owner's 2026-09-30 CI/review/QA decisions. Two PRs.
- **INDEX status:** spec (direction and spec approved for hand-off 2026-10-05; plan to be written by the implementing session)
- **Branch:** `L-0511-build`, new from origin/main `a555ff37` (crew 1.1.0); docs only, no implementation yet
- **Files here:** `docs/tickets/L-0511/direction.md`, `docs/tickets/L-0511/spec.md`, `docs/tickets/L-0511/HANDOFF.md`
- **Size:** PR 1 about 40 production lines (`scripts/check-marketplace.py --pending-bump`, the Marketplace workflow, verify rule 0, REPO-03) plus 4-6 `version-drift.py` cases. PR 2 about 80 production lines (`crew_autopilot.py`, `crew_train.py`) plus command and doc text and ~10 tests.
- **Harness:** no. Neither PR touches a `HARNESS` path in `scripts/check-tooling-pr.py`. `crew_autopilot.py` is a SEAM path, which is ordinary feature code here. Sabotage entries are a follow-up tooling-only ticket.
- **Risk:** high. PR 1 changes the severity of the check that stops CLAUDE.md's first stop-and-ask bug (content change, no bump), on draft PRs only.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| L-0522 PR 2 | in progress on `L-0522-tooling` (crew-chat), not merged | The delta gate keeps the receipt across a land-time re-anchor and bump. Without it, a land-time refresh costs a review round. Blocks PR 2 only. |
| L-0520 / L-0558 | merged | `crew_train.py status` (`armed: yes`) is the switch PR 2 routes on. |
| L-0526 | planned | `review_run.py` takes the train. Independent. |
| T-0033 | ready, to close as superseded by L-0522 PR 2 | Not needed. |
| L-0620 | direction | Receipt fast path. Independent. |

Order: PR 1 (repo gate) first, any time. PR 2 (crew) after L-0522 PR 2 merges.

## Read before writing code

- Re-find every `path:line` in the spec by content. They were checked at origin/main `a555ff37`. PR 2's anchors move when L-0522 PR 2 merges.
- PR 1 must keep the stop-and-ask guarantee: a ready PR and every push to `main` run the full `check-marketplace.py`, and `--pending-bump` is ignored on branch `main`. Sabotage both by hand and quote the red output in the PR.
- `scripts/gate-runner.py:153-154` pins the Marketplace CI command string. If the workflow line changes, update its step table, and its suite `scripts/_test/gate-runner.py` must pass.
- Check whether branch protection or a merge queue would let a draft run's green check stand after `gh pr ready`. Use a read-only `gh api .../branches/main/protection`. If it would, the land step re-runs the job.
- PR 2: an unarmed clone must behave byte-for-byte as today. An unreadable train state counts as could-not-tell and keeps today's order.
- `implement.md` is at its 120-line budget and `done.md` is at 115 of 120. Replace text, do not add it.
- PR 2 is a `plugin/crew` change, so every doc in the spec's Touch list updates in the same PR (CLAUDE.md scope rule). That includes the guides rebuilt by `docs/guides/crew/src/build.py`, the code map and the lifecycle diagrams.

## Open questions for the owner (recommended option taken)

1. CI tells a build branch from a land by the PR's draft flag. The land step runs `gh pr ready` after the bump. (Alternatives were a label, or a head version above main's.)
2. An unarmed clone keeps today's order.
3. The graphify rebuild moves to land in both modes. `graphify-out/` is outside the review bundle, so moving it never stales a receipt.
4. `--pending-bump` is ignored on branch `main`.

## Before landing

Merge origin/main and take a crew version above main's from the coordinator (PR 2 only; PR 1 changes no plugin content). Follow the repo's CLAUDE.md: scope discipline, doc updates for `plugin/crew` changes, and the tooling-PR rule. In PR 2's body, list what the machine-local lane scripts must change: no re-bump on catch-up, open PRs as drafts, land through `/crew:done`'s sequence. Remove `docs/tickets/L-0511/` in the final PR unless the owner wants it kept.
