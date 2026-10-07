# L-0527 direction - Kimi review launch in the review harness (tooling half of T-0028)

Status: approved 2026-10-05 for cloud hand-off (orchestrator, owner's standing self-approve authority). Was: seed, approved in outline by the owner's split decision.
Filed 2026-09-30 by the T-0028 lane under the owner's decision "Split into 2 PRs", with this
exact number.

## Why it exists
T-0028 (the Kimi Code CLI as a crew provider) changed both feature code and crew's review/gate
harness. Main's `scripts/check-tooling-pr.py` (T-0087, rule 36 of `.crew/verify.json`) refuses a
harness change that carries feature work, so the owner split T-0028 in two:
- PR 1, T-0028 (feature): `kimi_probe.py`, config/state (`kimi` in QA_PROVIDERS/DEV_PROVIDERS,
  family token, default `qa.order`), templates, docs, provider tests. No harness file.
- PR 2, L-0527 (this ticket, tooling only): the review launch.

## Scope (tooling only; every path in check-tooling-pr.py's HARNESS or ALONGSIDE)
- `plugin/crew/hooks/scripts/review_run.py`: `--provider kimi`; probe (via `kimi_probe`) before
  preflight and reserve; the tree fingerprint (REPO-02) with its fixed set-aside tuples and the
  `graph.out` exemption resolved through `crew_common.repo_config_dir`; survivor stop;
  `EXIT_PROBE_CHANGED` = 8; the `prompt_argument(..., exe)` batch-shim path.
- `plugin/crew/hooks/scripts/review_verdict.py`: Kimi stream parsing for the review (reusing
  the parser PR 1 ships in `kimi_probe.py`, not a second copy).
- `plugin/crew/commands/review.md`: the Kimi probe row (pinned kimi hard-fails), step 2e, exit 8,
  the step 1b strike row.
- Tests: `test_review_run_kimi.py`, the Kimi parts of `test_review_verdict.py`,
  `test_worktree_config.py`'s review_run ALLOWED entry and graph_out cases, the review.md
  assertions of `test_kimi_docs.py`; `review_fixtures.py`'s fake-kimi wiring; `sabotage_kimi.py`
  registered in `sabotage.py` (probe mutations included, since sabotage*.py is harness).
- `.crew/verify.json`'s Kimi rule widened to the harness files; docs describing the launch.

## Source
The full implementation, reviewed through T-0028 rounds 1-5 (round 5's eight FIX findings
fixed), is kept on the local branch `L-0527-source` (`d4f1e5bc`). Cut L-0527 from main after
T-0028's PR merges (merge main, never rebase) and carry the harness hunks over.

## Rules from the owner's decision
Own ledger and review budget; own version bump (one past main at land); tooling-only
(`check-tooling-pr.py` must exit 0); full suites, verify gate, re-anchor and self-check stamp
under heavy-run before each review; merge-train protocol with `--match-head-commit`.
Not in scope: the EXIT_UNVERIFIED/EXIT_PROBE_LIMITED collision (L-0528).

## Follow-ups carried from T-0028's TODO (recorded here when the split moved them)
- The working-tree fingerprint for codex and copilot, which are launched without a write check
  beyond their own flags.
- `review_run.py`'s codex path puts a stream error into review.json reasons unredacted
  (`extra.append(f"codex: {error}")`); the kimi path redacts.
- The kimi tree fingerprint does not see a write inside `.git` beyond HEAD and the index.
- Docs to restore from `L-0527-source`: review.md's Kimi rows, the README and crew-providers
  SKILL.md launch/fingerprint paragraphs, alternative-providers' `--provider kimi` pointer,
  test_kimi_docs.py's review.md and fingerprint-fact checks.

## Sabotage entries owed from T-0028 (feature half could not register them)
`sabotage*.py` is harness, so T-0028's PR registered no mutations. L-0527 registers, besides the
entries in `L-0527-source`'s `sabotage_kimi.py`, one per round-6/7 probe fix landed with T-0028:
wrong-shaped api_key/oauth reads not-authenticated again; temp dir inside a repository is allowed
again; non-string default_model reads not-authenticated again; any credentials/ file counts again;
the output cap is removed; config.toml is stat'ed then reopened by path again; and the launch gate
(`crew_config.review_launchable`) admits every QA provider again.

## Ask

Make `/crew:review` able to launch Kimi Code as a reviewer, by carrying the harness half of T-0028 onto
today's main. Re-measured on origin/main `a555ff37` (2026-10-05):

- T-0028's feature half is merged (PR #288, crew 1.0.85). The probe (`kimi_probe.probe`), the stream parser
  (`kimi_probe.final_message`), the read-only agent file and flags, `kimi_env`, `redact`, and the launch gate
  (`crew_config.review_launchable`) are all on main.
- The launch is not on main. `review_run.LAUNCHED = ("codex", "copilot")`
  (`plugin/crew/hooks/scripts/review_run.py:181`), `PROVIDERS = ("codex", "copilot", "claude")` (`:941`), and
  `commands/review.md:298-303` filters `$ELIGIBLE` to codex, copilot and claude.
- The source is **reachable from origin/main**, not only from the local branch. `L-0527-source` is `d4f1e5bc`,
  an ancestor of main. The split commit `524da6a4` removed the harness hunks, so
  `git diff 524da6a4 524da6a4^ -- <harness paths>` is the patch to carry over, and
  `git show d4f1e5bc:<path>` gives each file as reviewed. A cloud session can read both.
- Main has moved under that patch since `524da6a4`. `review_run.py` has 24 commits (+353/-66), review.md 33,
  sabotage.py 18, and review_verdict.py 3. The patch does not apply clean and has to be re-applied by hand,
  hunk by hunk.
- At source time the stream parser was in `review_verdict.py`. On main it is `kimi_probe.final_message`, so
  `review_verdict` imports it rather than carrying a second copy.

## Options

1. **One tooling-only PR with the whole launch, re-applied onto main (recommended).** This is review_run's
   kimi path (probe, tree fingerprint, survivor stop, `EXIT_PROBE_CHANGED = 8`, the batch-shim
   `prompt_argument`), review_verdict's Kimi branch, review.md's rows, the tests, `sabotage_kimi.py`
   registered with the 7 owed round-6/7 entries, and the verify.json rule widened. The docs outside
   `ALONGSIDE` (crew-providers `SKILL.md`, `alternative-providers.md`, and the `kimi_probe.py`/`crew_config.py`
   docstrings that say "lands as L-0527") go in a small follow-up feature PR right after. Tradeoff: those
   lines are stale for the gap between the two merges.
2. **Split the harness half again** (launch and fingerprint first, sabotage entries second). Tradeoff:
   it is two harness rounds instead of one, and the launch would land with no mutation coverage. That is
   the case the sabotage rule exists to prevent.
3. **Docs-first feature PR, then the tooling PR.** Tradeoff: the docs would say Kimi launches before
   anything can launch it. A claim that is not true at the commit is a recurring-findings class.

## Recommendation

Option 1. The scope is what the owner's split decision already fixed. The follow-up docs PR is the
"feature PR alongside a tooling PR" pattern the repo uses, with the order reversed because the docs describe
what the harness does. Every path in this PR is in `HARNESS` or `ALONGSIDE`, so it is a **tooling-only PR**.
`scripts/check-tooling-pr.py` must exit 0.

## Open questions (default taken)

- Should the docs outside `ALONGSIDE` ride along? **Default taken:** no. `check-tooling-pr.py` would refuse
  them. A follow-up feature PR (next L- id, minted by the coordinator, not here) updates crew-providers
  `SKILL.md:366-373`, `alternative-providers.md:10-13`, the `kimi_probe.py` docstrings (`:14`, `:42`, `:109`) and
  `crew_config.py:2104`.
- Which value should `EXIT_PROBE_CHANGED` take? **Default taken:** 8, as on the source. L-0528 moves
  `EXIT_UNVERIFIED` to 9, and either ticket can land first.
- Should the follow-ups carried from T-0028 (a fingerprint for codex/copilot, the unredacted codex stream
  error, `.git` writes beyond HEAD and the index) go in this PR? **Default taken:** no. They stay follow-ups,
  each its own ticket.
- Should `test_kimi_in_qa_order_is_not_eligible_while_review_run_cannot_launch_it`
  (`plugin/crew/tests/test_provider_table.py:2540`) be kept? **Default taken:** it is rewritten. Once `kimi` is
  in `LAUNCHED`, its must-block case becomes "a provider not in `LAUNCHED` is ineligible", and it uses a
  stand-in name.
