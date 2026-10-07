# L-0514 plan

Written by the implementing session (rush/h3-review, on top of L-0528).

Unknowns read at plan:
- Timeout share of tool INCOMPLETEs: the ledgers are on the owner's host, not in this container;
  not measured here. The default (no in-process retry on a timeout) stands.
- Metrics: `finish` appends one `review_metrics` row per round, so a retry adds its own row.
- Pre-review record: `review_checks.bind_record` removes the staged record when it binds round N, so
  the retry copies round N's bound record and binds it to round N+1 (`_carry_record`).

Steps (test-first, each test named in the spec's acceptance list, in test_review_refund.py):
1. Fake reviewer: a comma-separated FAKE_REVIEWER_MODE runs one mode per call (counter in
   FAKE_REVIEWER_STATE), and a `limit` mode emits Codex's usage-limit stream. `run_review` runs
   review_run with RETRY_BACKOFF_SECONDS patched to 0 (`review_fixtures.NO_BACKOFF`).
2. review_run.py: RETRY_LIMIT, RETRY_BACKOFF_SECONDS, RETRY_KEPT, RETRY_OPTIONS; `run`'s launch
   becomes `_launch_round` in a loop; `_retry_reason` (limit, timeout, class, refund, limit count),
   `_retry_blocked` (preflight, bundle re-hash) after the sleep; `_keep_round_files`;
   `_carry_record`; docstring RETRY section.
3. Existing refund tests that ran a non-timeout tool failure now see the retry: their assertions
   count the retry's round.
4. Sabotage: the spec's six plus "the bundle is not re-hashed before the retry".
5. review.md (line count unchanged), README, both guides (+ rebuild), code map, CHANGELOG.
