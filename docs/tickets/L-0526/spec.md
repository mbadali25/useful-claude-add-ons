# L-0526 Merge train slice 1b (tooling): review_run takes the train before a gate round (exit 6), the reviewer's rerere block, /crew:review exit 6, sabotage S1-S19          status: spec   risk: high

Split from L-0520 by the owner (2026-09-30, "Split into 2 PRs"). Base: origin/main after L-0520's
PR 1 merges (crew 1.0.77 or later). Source of the work: `b7fe895a`.

## Intent

Make the merge train binding at the gate round. Once a clone is armed (`crew_train.py arm`),
`review_run.py`'s `preflight` ends in `train_gate`: after the CLEAN-receipt short-circuit and the
verify gate, before the standards self-check and `review_ledger.reserve`, it calls
`crew_train.acquire`; holding goes on, anything else (waiting behind an overlapping ticket, `merge
<base> first`, an unreadable train, any exception) is the new exit 6 with no round reserved and the
reason on stderr. An unarmed clone reviews byte-for-byte as before. `review_prompt.py` adds a
`== Catch-up merges (rerere) ==` block from `crew_train.read_merge_log` so a reviewer sees every
rerere-replayed resolution as a change. `/crew:review` names exit 6. Sabotage rows S1-S19 prove
L-0520's acceptance (a)-(f), its hardening (S13-S15) and its PYTHON-set fixes (S16-S19, drafted at
`/root/crew-tmp/l-0520/tools/s16_s19.py` and run RED on L-0520's tree before its review) go red when
broken.

## Exclusions

- No change to `plugin/crew/hooks/scripts/crew_train.py` (L-0520 shipped it; `check-tooling-pr.py`
  would refuse it here as feature work). A defect found in it is reported and filed, not fixed here.
- No delta gate (L-0522), no scheduling (L-0523), no accepted-limits section (L-0524).
- No hook registration, no config key, no new command, skill or agent.
- The Claude fallback's second `review_run.py` call (`--round N --output`) records a round
  reserved under the lock and is not re-checked.
- The machine-local lane scripts are not in the repo and not changed.

## Evidence

- `b7fe895a:plugin/crew/hooks/scripts/review_run.py` (`preflight`, `_receipt_and_gate`,
  `train_gate`, `EXIT_TRAIN = 6`, docstring questions 1-4 and exit codes), resolved against T-0087's
  "FAILURE CLASS AND REFUNDS" docstring in the L-0520 merge `fab062af`.
- `b7fe895a:plugin/crew/hooks/scripts/review_prompt.py` (`_catch_up_block`, the `build` tuple).
- `b7fe895a:plugin/crew/tests/sabotage_train.py` (S1-S15), `sabotage.py` (`TRAIN_MUTATIONS`
  registered after `TOOLING_MUTATIONS`/`STANDARDS_MUTATIONS`), `test_review_run_train.py`,
  `test_review_prompt.py` (three catch-up cases), `test_lifecycle_commands.py`
  (`test_review_names_the_train_exit`).
- `scripts/check-tooling-pr.py` `HARNESS`/`ALONGSIDE`: every Touch path below is one or the other.
- L-0520's pre-split runs at `90d0d0e9`: S1-S15 all RED, full suite green.

## Unknowns

- Main may move `review_run.py`, `review_prompt.py`, `review.md` or `sabotage.py` between
  `b7fe895a` and the cut; each is re-read on the new main, never copied blind. Resolved at Step 1.
- A reviewer finding in `crew_train.py` cannot be fixed in this PR (Exclusions); it becomes a
  follow-up ticket and the owner decides whether it blocks. Accepted as risk.
- The full sabotage run was killed twice by an external SIGTERM on the cloud-guard r1 rows
  (L-0525 tracks that suite's state); runs are chunked when that happens and said so.

## Touch

- `plugin/crew/hooks/scripts/review_run.py`
- `plugin/crew/hooks/scripts/review_prompt.py`
- `plugin/crew/commands/review.md`
- `plugin/crew/tests/sabotage.py`
- `plugin/crew/tests/sabotage_train.py`
- `plugin/crew/tests/test_review_run_train.py`
- `plugin/crew/tests/test_review_prompt.py`
- `plugin/crew/tests/test_lifecycle_commands.py`
- `plugin/crew/tests/test_crew_train.py`
- `plugin/crew/README.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
- `CHANGELOG.md`
- `TODO.md`
- `.crew/verify.json`
- `docs/guides/crew/src/working-with-codex.md`
- `docs/guides/crew/src/daily-workflow.md`
- `docs/guides/crew/src/troubleshooting.md`
- `docs/guides/crew/crew-1.0-working-with-codex.html`
- `docs/guides/crew/crew-1.0-working-with-codex.docx`
- `docs/guides/crew/crew-1.0-working-with-codex.pdf`
- `docs/guides/crew/crew-1.0-daily-workflow.html`
- `docs/guides/crew/crew-1.0-daily-workflow.docx`
- `docs/guides/crew/crew-1.0-daily-workflow.pdf`
- `docs/guides/crew/crew-1.0-troubleshooting.html`
- `docs/guides/crew/crew-1.0-troubleshooting.docx`
- `docs/guides/crew/crew-1.0-troubleshooting.pdf`
- `.crew/codemap/*.md`
- `.claude/rules/*.md`
- `docs/diagrams/*.mmd`
- `graphify-out/graph.json`
- `graphify-out/GRAPH_REPORT.md`

## Acceptance checks

- [ ] (a)/(e) review_run half: with T-1 holding, an overlapping T-2's `review_run.py` exits 6 with
      `train: waiting behind T-1`, the ledger byte-identical; after T-1's release T-2 reserves
      (`test_review_run_train.py::test_second_overlapping_gate_round_is_refused_unspent`, S6).
- [ ] Unarmed clone reviews as before (`::test_unarmed_clone_reviews_as_before`); unreadable train
      is exit 6 (`::test_unreadable_train_refuses_the_round`); a crash in the step refuses and
      reserves nothing (`::test_train_crash_refuses_never_reserves`); the CLEAN receipt and an
      unverified gate still answer first (`::test_train_step_follows_the_clean_receipt_and_the_verify_gate`).
- [ ] Review brief: `test_review_prompt.py::test_prompt_lists_rerere_replayed_files`,
      `::test_prompt_has_no_catch_up_block_without_a_log`, `::test_prompt_marks_an_unreadable_merge_log`.
- [ ] `test_crew_train.py::test_only_the_review_path_imports_the_train` asserts equality again
      (both callers import it).
- [ ] `review.md` names exit 6 and stays 551 lines (`test_lifecycle_commands.py::test_review_names_the_train_exit`,
      `scripts/check_instructions.py`).
- [ ] Every S1-S19 row RED through `plugin/crew/tests/sabotage.py` under heavy-run, quoted.
- [ ] `python3 scripts/check-tooling-pr.py` exit 0; `python3 scripts/check-marketplace.py` exit 0;
      full suite, wallclock, pylint, ruff-no-new, verify gate green under heavy-run.
- [ ] Docs: README (exit 6, the rerere prompt block), `review.md`, working-with-codex /
      daily-workflow / troubleshooting sources and nine outputs rebuilt; CHANGELOG; version one patch
      past origin/main at push; `.crew/verify.json` rules name L-0526 and the train rule runs
      `test_review_run_train.py`; refresh artifacts fresh.
