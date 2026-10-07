# Cloud handoff: L-0514

**A refunded tool-failure review round retries automatically, once, then stops with options**

Handed to a cloud session on 2026-10-05 by owner instruction. Do not pick up locally.

**Buildable now.** T-0087 (refunds) and T-0088 (usage-limit routing) are on main.

- **Role:** standalone ticket, improvement 6 of the owner's 2026-09-30 CI/review/QA decisions. It builds on T-0087's refund.
- **INDEX status:** spec (direction and spec approved for hand-off 2026-10-05; plan to be written by the implementing session)
- **Branch:** `L-0514-build`, new from origin/main `a555ff37` (crew 1.1.0); docs only, no implementation yet
- **Files here:** `docs/tickets/L-0514/direction.md`, `docs/tickets/L-0514/spec.md`, `docs/tickets/L-0514/HANDOFF.md`
- **Size:** about 60 production lines in `review_run.py` and about 3 net lines in `review.md`, plus about 10 tests and 6 sabotage entries.
- **Harness:** yes. `review_run.py`, `review.md` and `sabotage_review.py` are `HARNESS` paths in `scripts/check-tooling-pr.py`, so this lands alone as a tooling-only PR. Tests, docs, version files, the code map and the graph may ride along. Feature code may not.
- **Risk:** medium.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0087 | merged (#281) | Refunds, `failure_class`, `REFUND_LIMIT = 2`. Required, present. |
| T-0088 | merged | Usage limits go to the Claude reviewer. A limit is never retried here. |
| L-0576 | merged (crew 1.0.128) | Recovered most reviewer-class INCOMPLETEs. Disjoint. |
| L-0526 | planned | Also edits `review_run.run`'s preamble (the merge-train hold). Whichever lands second merges the other, and the retry re-checks the hold. |
| L-0527 | direction | Kimi launch. If it lands first, the retry covers `kimi` too. |

This ticket blocks nothing.

## Read before writing code

- Seed correction: the seed says T-0087 "does not retry". Autopilot already reruns a refunded round (`crew_autopilot.py:1278-1285`, added in T-0087's round-1 fix `bbe68e85`). The gap is outside autopilot: `/crew:review`, lanes and humans calling `review_run.py` stop on exit 3. Leave autopilot's rerun unchanged.
- Re-find every `path:line` in the spec by content. They were checked at origin/main `a555ff37`.
- Only a round the ledger refunded is retried, so a retry never spends a budget round. Reviewer, tree, refused-refund, usage-limit, timeout and changed-tree rounds are not retried. Each gets a must-block test.
- `review.md` is at 548 of its 551-line allowance. Replace text, do not add it.
- No single-entry flag exists in `sabotage.py`. Run the whole suite through heavy-run and quote each new entry's RED line.
- A harness change runs the harness rule's suites: the tooling checker, its suite, the golden replay, the seam contracts and the canary review (`.crew/verify.json:518-524`).

## Open questions for the owner (recommended option taken)

1. One retry per invocation (`RETRY_LIMIT = 1`, a constant). `REFUND_LIMIT = 2` per plan still caps the plan.
2. A timed-out round is not retried in-process, because a retry could double a 30-minute wait. It stops with options instead.
3. The backoff is a fixed 30 seconds, a module constant that tests patch to 0.
4. Autopilot's own refunded rerun stays.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0514/` in the final PR unless the owner wants it kept.
