# L-0514 direction - INCOMPLETE review rounds retry automatically after T-0087's tool-failure refund, capped, instead of stopping the lane

Status: approved 2026-10-05 for cloud hand-off by the orchestrator under the owner's standing self-approve authority (open questions take the recommended option, recorded below as "default taken").

Improvement 6. OVERLAP CHECKED: T-0087 (#260, in review) already refunds a tool-caused INCOMPLETE round (failure_class 'tool', REFUND_LIMIT constant) but does not retry, and never refunds a reviewer-class INCOMPLETE. This ticket is the retry on top of T-0087's refund: bounded retries, then stop with options. Starts after T-0087 lands. Measured: INCOMPLETE 14% of rounds (Codex 24%).

Source: owner decisions 2026-09-30 ("All recommended", relayed by crew-chat) on a measured CI/review/QA review of 2026-09-28..30; raw data at /tmp/claude-0/.../ci-review/, copied to .work/ci-review-2026-09-30/ (every number there carries its source; copy what you cite into this folder, the scratchpad is not durable).

## Ask

When a review round comes back INCOMPLETE because the TOOL lost it (T-0087's `failure_class: tool`,
refunded), `/crew:review` retries it automatically, a bounded number of times, instead of stopping the
lane. When the retries run out, or the round is not one a retry can fix, it stops and names the options.

## What origin/main `a555ff37` (crew 1.1.0) already does

- **Refund: done (T-0087, #281).** `review_ledger.REFUND_LIMIT = 2` per plan
  (`plugin/crew/hooks/scripts/review_ledger.py:137`); a `tool` INCOMPLETE row gets `refunded: true`
  (`:403-406`); `review_run.py` prints whether it was refunded (`review_run.py:626-632`) and still exits 3.
- **Autopilot already reruns a refunded round.** T-0087's round-1 fix (`bbe68e85`, 2026-09-28) added
  `refunded_rerun` (`plugin/crew/hooks/scripts/crew_autopilot.py:1278-1285`, `next_phase` `:1350-1364`):
  autopilot routes back to `/crew:review`, bounded by `REFUND_LIMIT` and `autopilot.maxPhases`. So the seed's
  "does not retry" is true only OUTSIDE autopilot.
- **Outside autopilot nothing retries.** `/crew:review` says "its rerun is a new round"
  (`plugin/crew/commands/review.md:486`) and stops; a lane or a human calling `review_run.py` gets exit 3.
  This is the gap. `review_run.run` reserves, launches and finishes one round (`review_run.py:832-908`).
- **Reviewer-class INCOMPLETE** is never refunded (`review_ledger.py:24-33`) and L-0576 (crew 1.0.128) already
  recovered most of them (stray prose beside findings now parses FINDINGS; CHANGELOG "harmless stray lines").
- **Usage limits** are already routed to the Claude reviewer (T-0088, `review_limit.py:1-30`, `review_run.py:884-905`).

## Options

1. **A bounded in-process retry in `review_run.py run` (recommended).** After `finish` records a round
   INCOMPLETE with `failure_class: tool` AND `refunded: true`, and the failure is not a usage limit and not
   a timeout, `run` waits `RETRY_BACKOFF_SECONDS`, re-runs `preflight` (a tree that changed, or a receipt
   that now stands, stops the retry), reserves a fresh round and relaunches, at most `RETRY_LIMIT = 1` time
   per invocation. The ledger's `REFUND_LIMIT` still caps the plan. When the retry is not taken it prints one
   `review: retry: not retried - <why>` line and a `review: options:` line. Exit code is the last round's.
   Tradeoff: a harness change (`review_run.py`, `review.md`), so a tooling-only PR with must-block/must-allow
   tests; one more Codex call per tool failure.
2. **Prose in `review.md`: on exit 3 with a refunded line, rerun the review block once.** No code. Tradeoff:
   lanes and phase agents must read and obey it, and the Claude fallback path differs; nothing enforces the
   cap. Rejected (Lessons: put the check where the evidence is).
3. **Also retry reviewer-class INCOMPLETE.** Tradeoff: each retry spends a budget round (two per plan); a
   reviewer that did not finish reading tends to repeat. Rejected; it stays a stop with options.

## Recommendation

Option 1, as one tooling-only PR. The Claude fallback (`--reserve-only` then `--round N --output`) records
rounds in two calls, so it gets no in-process retry: `review.md` step 2c says to re-dispatch once on a
refunded `tool` round, inside the same 551-line budget.

## Open questions (default taken)

1. **How many retries per invocation?** (A, taken) one: `RETRY_LIMIT = 1`, a constant, never config. With
   `REFUND_LIMIT = 2` per plan this bounds the plan to two refunded rounds whatever the caller does. (B) two.
2. **Timeouts.** (A, taken) a timed-out round is not retried in-process: `DEFAULT_TIMEOUT` is 1800s
   (`review_run.py:169`), so a retry could double a 30-minute wait; it stops with options. (B) retry all tool failures.
3. **Backoff.** (A, taken) fixed 30s, a module constant the tests patch to 0. (B) none. (C) exponential.
4. **Does autopilot's own rerun stay?** (A, taken) yes, unchanged: after the in-process retry also fails,
   autopilot's `refunded_rerun` may route to review again, still bounded by `REFUND_LIMIT` (the second
   refused refund counts and ends it). (B) drop autopilot's rerun.
