# L-0528: review_run.py: EXIT_UNVERIFIED and EXIT_PROBE_LIMITED are both 5          status: spec   risk: low
Written against origin/main `a555ff37` (2026-10-05).

## Intent
`review_run.py` returns a different number for every outcome. `EXIT_UNVERIFIED` moves from 5 to 9. That is
the refusal with nothing spent: the verify gate has not passed, or the pre-review checks found a new finding
or could not check. The probe's codes stay 5 (limited), 6 (failed) and 7 (unknown), so a Codex usage limit is
the only meaning of 5. A test asserts that every `EXIT_*` constant in the module is distinct, and a sabotage
entry that brings back the collision goes RED. Every caller and doc that reads 5 as "unverified" is updated in
the same PR. **Breaking:** an out-of-repo script that branches on review exit 5 for a red gate must read 9.

## Exclusions
- No change to the probe's codes or outcomes, to `review_metrics.PROBE_LIMITED_NOTE` (`codex-probe=5`), or to
  `plugin/crew/skills/crew-providers/SKILL.md` (it describes the probe codes, which do not move, and it is not in
  `ALONGSIDE`).
- No split of the refusal into one code per reason (gate, new finding, could not check). Their stderr text
  is unchanged.
- No Kimi work. L-0527 owns `EXIT_PROBE_CHANGED = 8`, which is why 8 is skipped.
- No production code outside the harness.

## Evidence
origin/main `a555ff37`:
- `plugin/crew/hooks/scripts/review_run.py:167` `EXIT_CLEAN, EXIT_FINDINGS, EXIT_USAGE, EXIT_INCOMPLETE, EXIT_REFUSED = 0, 1, 2, 3, 4`;
  `:168` `EXIT_UNVERIFIED = 5`; `:185` `EXIT_PROBE_LIMITED, EXIT_PROBE_FAILED, EXIT_PROBE_UNKNOWN = 5, 6, 7`.
- Returned at `:694` (`preflight`, the gate is unverified or unknown) and `:787` (`prereview_gate`). The probe
  map is at `:985-987`, reached only under `--probe` (`:976`).
- The module docstring states the codes: `:26-27` (probe) and `:111`, `:117`, `:121` (exit 5 for the gate and
  the pre-review checks). The `--note` help text is at `:965` ("5 means a Codex limit"), which stays.
- `plugin/crew/hooks/scripts/review_metrics.py:86` `PROBE_LIMITED_NOTE = "codex-probe=5"` (unchanged).
- `plugin/crew/commands/review.md:440` (`REVIEW_STATUS=$?   # ... 5 gate red ...`), `:449` (the "Exit 5
  (`$REVIEW_STATUS`, not the probe's `$PROBE_STATUS` 5)" paragraph), and `:472` ("exit 5 above").
- `plugin/crew/README.md:766` (the pre-review paragraph, exit 5 twice), `:3975`, `:3978` (the review diagram labels).
- `docs/guides/crew/src/working-with-codex.md:82`, `:94-97` (unverified exit 5). `:111` and
  `docs/guides/crew/src/troubleshooting.md:170` are the probe's 5 and do not change.
- `docs/diagrams/process-crew-lifecycle-review.mmd:27`, `:40`, `:43`; `docs/diagrams/process-crew-lifecycle.mmd:169`,
  `:201`, `:409`; and the generated `docs/diagrams/README.md:1142` and `docs/diagrams/index.html:587`, `:590`.
- `.crew/codemap/crew.md:1852-1857` (the gate is exit 5, the pre-review checks are exit 5).
- Tests that assert the literal 5 for the gate: `plugin/crew/tests/test_review_gate.py:244-268` (three
  tests, one with `exit_5` in its name); `plugin/crew/tests/test_review_run_standards.py:236`, `:352`; and
  `plugin/crew/tests/test_review_run_prereview.py:157`, `:194`, `:203`, `:213`, `:294`.
  `plugin/crew/tests/test_review_gate_receipt.py:78` already uses the symbol. The probe's 5 is at
  `plugin/crew/tests/test_review_limit.py:213`, `:222`, `:295` and is unchanged.
- Sabotage list without a line-budget problem: `plugin/crew/tests/sabotage_review.py:19` `REVIEW_FIX_MUTATIONS`, 1156 lines.
  `sabotage.py` is at 3381 of 3400 and is not edited.
- Harness: `scripts/check-tooling-pr.py:58-87` (`review_*.py` `:59`, `sabotage*.py` `:79`, `commands/review.md` `:83`).

## Unknowns
- Whether any lane or orchestrator prompt outside the repo branches on review exit 5. A
  `grep -rn "exit 5\|== 5" /root/crew-tmp` sweep on the owner's host is reported in the PR. It is not gated.
- If L-0527 has landed first, `EXIT_PROBE_CHANGED = 8` is in the module, and the distinct-values test covers it unchanged.
- The next free crew patch version is set at implement time.

## Size and split
3 production lines (the constant and two docstring lines in `review_run.py`) and about 6 doc lines in
review.md. About 10 test assertions move from 5 to the symbol, plus 1 new test, 1 sabotage entry, and the doc
and diagram lines above. Harness: **yes, tooling-only PR**. No further split.

## Touch
- `plugin/crew/hooks/scripts/review_run.py`
- `plugin/crew/commands/review.md`
- `plugin/crew/tests/sabotage_review.py`
- `plugin/crew/tests/test_review_gate.py` (assert `review_run.EXIT_UNVERIFIED`, and rename `..._exit_5_...`)
- `plugin/crew/tests/test_review_run_standards.py`
- `plugin/crew/tests/test_review_run_prereview.py`
- `plugin/crew/tests/test_review_run_launch.py` (the new `test_review_run_exit_codes_are_distinct`, or a new `test_review_run_exit_codes.py`)
- `plugin/crew/README.md`
- `docs/guides/crew/src/working-with-codex.md`
- `docs/guides/crew/**` (HTML, DOCX and PDF rebuilt by `docs/guides/crew/src/build.py`)
- `docs/diagrams/process-crew-lifecycle-review.mmd`, `docs/diagrams/process-crew-lifecycle.mmd`, and the regenerated `docs/diagrams/README.md` and `docs/diagrams/index.html`
- `.crew/codemap/crew.md`
- `CHANGELOG.md` (with a **Breaking** line)
- `plugin/crew/BUDGETS.md` (only if `.md` line counts move)
- `plugin/crew/.claude-plugin/plugin.json`
- `plugin/PLUGINS.md`
- `.claude-plugin/marketplace.json`
- `docs/tickets/L-0528/` (removed in the final PR)

Not in Touch: `plugin/crew/skills/crew-providers/SKILL.md`, `docs/guides/crew/src/troubleshooting.md` and
`review_metrics.py` (they describe the probe's 5, which stays); `plugin/crew/CONFIG.md` (no setting);
`.crew/verify.json` (review_run's rule already maps the touched tests).

## Acceptance checks
Commands from the repo root. Run pytest through the heavy-run wrapper on a memory-bound host.
- [ ] Every `EXIT_*` constant in `review_run` has a distinct integer value, found by introspection (not a
  hand list), so a constant added later is covered.
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_review_run_launch.py -q -k exit_codes_are_distinct`
- [ ] `EXIT_UNVERIFIED == 9`, and the probe's codes are still `5, 6, 7`.
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_review_limit.py -q`
- [ ] An unverified or unknown gate, a new pre-review finding, and a pre-review check that could not run each
  exit `review_run.EXIT_UNVERIFIED`, with no round spent.
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_review_gate.py plugin/crew/tests/test_review_run_prereview.py plugin/crew/tests/test_review_run_standards.py plugin/crew/tests/test_review_gate_receipt.py -q`
- [ ] The sabotage entry "review_run's unverified exit collides with the probe's limited exit again" (setting
  `EXIT_UNVERIFIED = 5`) is `RED (good)`. Run that one entry with a scratch driver over `REVIEW_FIX_MUTATIONS`
  and attach its output. `python3 plugin/crew/tests/sabotage.py` runs it in the full suite.
- [ ] No doc says the gate or pre-review refusal is exit 5:
  `grep -rn "exit 5" plugin/crew/README.md plugin/crew/commands/review.md docs/guides/crew/src/working-with-codex.md docs/diagrams/*.mmd .crew/codemap/crew.md`
  lists only probe-limited lines.
- [ ] `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK`, and the harness rule's suites pass
  (`python3 scripts/_test/tooling-pr.py`, the golden replay, seam contracts, and canary review, per `.crew/verify.json`).
- [ ] Guides rebuilt (`python3 docs/guides/crew/src/build.py`) and diagrams regenerated. crew is bumped to
  the next free patch with a CHANGELOG entry that carries a Breaking line, and `python3 scripts/check-marketplace.py`
  passes after the commit.

## Dependencies
- None blocking. Independent of L-0527 in either order (8 is reserved for it). T-0087 (tooling PRs land alone) is merged.
- Helps: the Codex-limit to Claude-reviewer fallback, which reads the probe's 5.

## Approval
Direction and spec approved for cloud hand-off by the orchestrator under the owner's standing self-approve
authority, 2026-10-05. Plan: to be written by the implementing session.
