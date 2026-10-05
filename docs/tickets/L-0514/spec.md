# L-0514: a refunded tool-failure review round retries automatically, once, then stops with options          status: spec   risk: medium
Improvement 6 of the owner's 2026-09-30 CI/review/QA decisions ("All recommended"). Builds on T-0087 (#281,
merged). Written against origin/main `a555ff37` (crew 1.1.0). **Tooling-only PR**: every production path here is
a review harness path (`HARNESS` in `scripts/check-tooling-pr.py:58-87`).

## Intent
`review_run.py run` retries a round the TOOL lost, without a human. After `finish` records a round INCOMPLETE
with `failure_class: tool` and the ledger refunded it, and the failure was neither a usage limit (T-0088 routes
those to the Claude reviewer) nor a timeout, `run` waits `RETRY_BACKOFF_SECONDS`, re-runs `preflight`, reserves
a fresh round and relaunches the same provider, model and effort. It does this at most `RETRY_LIMIT = 1` time
per invocation. The ledger's `REFUND_LIMIT = 2` per plan still bounds the plan. Every other INCOMPLETE is not
retried: reviewer, tree, a refund the ledger refused, a usage limit, a timeout, a tree or receipt that changed
before the retry. For those, `run` prints one `review: retry: not retried - <reason>` line and one
`review: options:` line (rerun `/crew:review`, spending a round when not refunded; switch provider; replan) and
exits 3 as today. The exit code is always the last round's verdict. `/crew:review` step 2c (the Claude fallback,
two calls) re-dispatches once on a refunded `tool` round under the same rule, in prose, inside the 551-line
budget.

## Exclusions
- No change to the refund rule, `REFUND_LIMIT`, `failure_class` or `review_verdict.parse`
  (`review_ledger.py`, `review_verdict.py`). No retry spends a budget round: only refunded rounds retry.
- No retry of reviewer-class or tree-class INCOMPLETE, FINDINGS or CLEAN rounds.
- No config key: `RETRY_LIMIT` and `RETRY_BACKOFF_SECONDS` are module constants (tests patch the backoff).
- No change to `crew_autopilot.py`'s `refunded_rerun` (`crew_autopilot.py:1278-1285`, a SEAM path): it stays,
  and is still bounded by `REFUND_LIMIT`. No change to `/crew:autopilot`.
- No change to the probe (`--probe`), the usage-limit marker (`review_limit.py`) or the provider walk.
- No feature code rides along: this is a tooling-only PR (CLAUDE.md, T-0087 rule). Tests, docs, version files,
  the code map and the graph may.
- Kimi (`--provider kimi`) is not on main (L-0527). If it lands first it is in `LAUNCHED` and gets the same
  retry. If not, nothing here names it.

## Evidence
origin/main `a555ff37`:
- Refund: `REFUND_LIMIT = 2` `plugin/crew/hooks/scripts/review_ledger.py:137`; docstring `:24-33`; `refunded` /
  `refund_refused` set in `record` `:403-406`; `status` exposes `refund_limit` `:956`.
- Failure class: `failure_class` `plugin/crew/hooks/scripts/review_verdict.py:240-246`
  (`TOOL, REVIEWER, TREE` `:95`).
- One round per `run`: `run` `plugin/crew/hooks/scripts/review_run.py:832-908` (`preflight` `:846`, reserve
  `:863`, launch `:875`, `finish` `:893`, usage-limit marker `:894-905`); `finish` `:534-638` (refund lines
  `:626-632`, exit mapping `:637-638`); `preflight` `:672`; `LAUNCHED = ("codex", "copilot")` `:181`; exit codes
  `:167-168`; `DEFAULT_TIMEOUT = 1800` `:169`; docstring "FAILURE CLASS AND REFUNDS" `:92-98` ("A refunded round
  still exits 3").
- Usage limit judged only on a failed call: `review_run.py:884-889`, `review_limit.limit_line`
  (`plugin/crew/hooks/scripts/review_limit.py:1-30`).
- `/crew:review`: Step 2a/2b call `plugin/crew/commands/review.md:436-440`; Step 2c Claude fallback
  `:452-475`; "Only a `tool` INCOMPLETE (no intact answer) is refunded, up to two per plan ...; its rerun is a
  new round." `:486`. File is 548 lines, allowance 551 (`plugin/crew/.budget-allowance.json`,
  "plugin/crew/commands/review.md").
- Autopilot's rerun: `plugin/crew/hooks/scripts/crew_autopilot.py:1278-1285`, `next_phase` docstring
  `:1350-1357`; tests `plugin/crew/tests/test_crew_autopilot.py:1419`, `:1446`; README row
  `plugin/crew/README.md:909`.
- Tests to extend: `plugin/crew/tests/test_review_refund.py` (`test_turn_failed_round_is_refunded` `:223`,
  `test_timed_out_round_is_refunded` `:227`, `test_contract_broken_round_is_not_refunded` `:235`,
  `test_tree_changed_round_is_not_refunded` `:243`); sabotage list `REVIEW_FIX_MUTATIONS`
  `plugin/crew/tests/sabotage_review.py:19` (1156 lines); `plugin/crew/tests/sabotage.py` is 3381 of the
  3400-line module limit, so no entry goes there.
- Verify rules naming these files: `.crew/verify.json:456`, `:473`, `:483`, `:518-524` (the harness rule with
  golden replay, contracts and canary).
- Measured: INCOMPLETE 14% of rounds, Codex 24% (seed `direction.md`, from `.work/ci-review-2026-09-30/`,
  gitignored). L-0576 (crew 1.0.128, CHANGELOG "harmless stray lines") since moved most reviewer-class
  INCOMPLETEs to FINDINGS, so re-measure the tool share before quoting it.

## Unknowns
- **The share of tool INCOMPLETEs that are timeouts**: measured at plan from the ledgers on the host
  (`reasons` of `failure_class: tool` rows). If timeouts are most of them, the PR body says the retry covers
  only the rest. The default (no in-process retry on timeout) stays.
- **Scratch files across the retry**: `out.txt`, `stderr.txt`, `codex-events.jsonl` and `review.json` are
  per-round today. Default taken: the failed round's files are kept as `<name>.round<N>` before the retry
  writes its own, so `/crew:review` step 3 reads the last round and the earlier one stays inspectable.
- **Prompt and bundle reuse**: the retry reuses `prompt.txt` and the bundle unchanged. `preflight` plus the
  bundle hash check in `finish` (`bundle_problems`) prove the tree did not move. A changed tree is
  `not retried - the tree changed`.
- **Metrics row**: whether `review_metrics` appends one row per round (expected) or per invocation. Read at plan.
- Next free crew patch version set at land (main is 1.1.0 at `a555ff37`).

## Size and split
About 60 production lines in `review_run.py` (`_retry_reason`, the loop in `run`, two constants, docstring),
about 3 net lines in `review.md` (text replaced, budget 551). About 10 tests and 6 sabotage entries. One PR,
tooling-only. No split: the retry and its must-block cases are one behaviour.

## Touch
- `plugin/crew/hooks/scripts/review_run.py`
- `plugin/crew/commands/review.md`
- `plugin/crew/tests/test_review_refund.py`
- `plugin/crew/tests/test_review_run_launch.py` (only if the launch fake lives there)
- `plugin/crew/tests/sabotage_review.py`
- `plugin/crew/README.md` (review budget paragraph near `:764`, and the autopilot row `:909` if its wording names "rerun")
- `docs/guides/crew/src/working-with-codex.md`, `docs/guides/crew/src/troubleshooting.md` (where they describe an INCOMPLETE round)
- `docs/guides/crew/**` - HTML, DOCX and PDF rebuilt by `docs/guides/crew/src/build.py`
- `.crew/codemap/crew.md`, `.crew/codemap/verification-harness.md`, `.crew/codemap/INDEX.md`
- `.crew/verify.json` (only a `why` text naming the new tests, if a rule's suite list changes)
- `CHANGELOG.md`, `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `plugin/PLUGINS.md`
- `docs/tickets/L-0514/` (removed in the final PR)

Not in Touch: `review_ledger.py`, `review_verdict.py`, `review_limit.py`, `crew_autopilot.py`,
`plugin/crew/CONFIG.md` (no key: PR body says `Docs: none - CONFIG.md, no config key`), `docs/diagrams/`
(no new box; say so in the PR if unchanged).

## Acceptance checks
Commands from the repo root; pytest through the heavy-run wrapper on a memory-bound host. `R` is
`plugin/crew/tests/test_review_refund.py`; run as `python3 plugin/crew/tests/pytest_rule.py R -q -k <name>`.
- [ ] Must-allow: a fake Codex whose first call ends in a turn-failed stream error and whose second returns
  CLEAN: one invocation records two rounds (round 1 `refunded: true`, round 2 CLEAN), prints
  `review: retry: round 1 was a tool failure; retrying once`, and exits 0. `-k test_refunded_tool_round_retries_once_and_clean_wins`
- [ ] The retry is capped: two tool failures in a row record two rounds, the second is not retried
  (`not retried - retry limit 1 per invocation`), exit 3 with the `review: options:` line. `-k test_retry_limit_is_one_per_invocation`
- [ ] Must-block, one test each, nothing reserved after the first round: a reviewer-class INCOMPLETE; a
  tree-class INCOMPLETE; a refund the ledger refused (`REFUND_LIMIT` reached); a usage-limit failure (the
  Claude-reviewer line still prints); a timeout; a tree changed between the rounds (`preflight` or the bundle
  hash says so). Each prints its own `not retried - <reason>`.
  `-k "test_no_retry_for_reviewer_class or test_no_retry_for_tree_class or test_no_retry_when_refund_refused or test_no_retry_on_usage_limit or test_no_retry_on_timeout or test_no_retry_when_tree_changed"`
- [ ] A FINDINGS or CLEAN first round is never retried, and the exit code is unchanged.
  `-k test_clean_and_findings_rounds_are_not_retried`
- [ ] The backoff runs before the retry reservation (patched sleep records the call before `reserve`).
  `-k test_backoff_precedes_the_retry_reservation`
- [ ] The failed round's scratch files survive as `*.round<N>`; `review.json` is the last round's.
  `-k test_failed_round_files_are_kept`
- [ ] The Claude fallback path (`--reserve-only`, `--round N --output`) never retries in-process.
  `-k test_claude_fallback_never_retries_in_process`
- [ ] `review.md` step 2c says to re-dispatch once on a refunded `tool` round and :486's sentence names the
  in-process retry; the file stays at or under 551 lines.
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_lifecycle_commands.py -q` and `python3 scripts/check-marketplace.py`
- [ ] Sabotage (`sabotage_review.py`): retry a reviewer-class round; retry when the refund was refused; retry
  on a usage limit; retry on a timeout; drop the `RETRY_LIMIT` check; skip `preflight` before the retry. Each
  turns its named test red under `python3 plugin/crew/tests/sabotage.py` (no single-entry flag on
  `a555ff37`; run the whole suite through the heavy-run wrapper, and quote each new entry's RED line in the PR).
- [ ] The harness rule's suites pass: `python3 scripts/check-tooling-pr.py` (reports harness-only),
  `python3 scripts/_test/tooling-pr.py`, and the golden replay, seam contracts and canary named in
  `.crew/verify.json:518-524`.
- [ ] Autopilot's refunded rerun is unchanged:
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot.py -q -k refunded_rerun`

## Dependencies
- T-0087 (merged, #281): refunds and `failure_class`. Required, present.
- T-0088 (merged): usage-limit routing. Present.
- L-0576 (merged, crew 1.0.128): reviewer-class recovery. Disjoint.
- L-0510 (merged): auto-accept never takes an INCOMPLETE. Disjoint (CHANGELOG "Boundary with L-0514").
- L-0526 (planned): `review_run.py` takes the merge train before a gate round. It touches `run`'s preamble.
  Whichever lands second merges the other. The retry must re-check the train hold if L-0526 is on main.
- L-0527 (direction): Kimi review launch. If it lands first, `LAUNCHED` gains `kimi` and the retry covers it.
- Blocks nothing.

## Approval
Direction and spec approved for cloud hand-off by the orchestrator under the owner's standing self-approve authority, 2026-10-05. Plan: to be written by the implementing session.
