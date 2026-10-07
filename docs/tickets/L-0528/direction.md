# L-0528 direction - review_run.py: EXIT_UNVERIFIED and EXIT_PROBE_LIMITED are both 5

Status: approved 2026-10-05 for cloud hand-off (orchestrator, owner's standing self-approve authority). Was: seed. Filed by owner decision 2026-09-30 ("File it"), from the T-0028 lane's report.

On origin/main, `plugin/crew/hooks/scripts/review_run.py` defines `EXIT_UNVERIFIED` and `EXIT_PROBE_LIMITED` with the same value, 5 (T-0028 report cited :105 and :118 at 9af34e57; re-verify). A caller cannot tell "the verify gate has not passed" from "the reviewer hit a usage limit". The Codex-limit fallback to a Claude reviewer depends on telling them apart.

Scope: give each condition a distinct exit code. Update every caller and doc that branches on 5 (commands/review.md, lane scripts' documented contract, tests). Add a test that asserts the review_run exit codes are all distinct, plus a sabotage entry that makes two of them collide again. This is a tooling-only change (review harness), so it lands alone. Version bump and docs per repo rules.

## Ask

Give `review_run.py`'s exit codes distinct values, so one number never means two things. Re-measured on
origin/main `a555ff37`: `EXIT_UNVERIFIED = 5` is at `plugin/crew/hooks/scripts/review_run.py:168` and
`EXIT_PROBE_LIMITED, EXIT_PROBE_FAILED, EXIT_PROBE_UNKNOWN = 5, 6, 7` is at `:185`. The collision is real but
narrower than the seed says. The probe codes come back only from a `--probe` call (`:976-987`). The 5 that
means "unverified" comes back only from a reviewing call, which happens in three places: the verify gate
(`:694`) and the pre-review checks (`:787`, both NEW finding and COULD NOT CHECK). `commands/review.md`
already keeps them apart by variable (`:449`: "Exit 5 (`$REVIEW_STATUS`, not the probe's `$PROBE_STATUS` 5)").
Any caller that reads the code without knowing which mode it ran still cannot tell them apart. That
includes a lane script, a log line, and the Codex-limit fallback reasoning. The `--note codex-probe=5` that
the metrics read (`plugin/crew/hooks/scripts/review_metrics.py:86`) is persisted in metrics rows.

## Options

1. **Move `EXIT_UNVERIFIED` to 9 (recommended).** The probe codes 5/6/7 stay as they are, so the persisted
   `codex-probe=5` notes keep their meaning, and so do `crew-providers/SKILL.md:136` and the guides'
   probe text. SKILL.md is not in `ALONGSIDE`, so a tooling-only PR could not edit it anyway. 8 is left
   for L-0527's `EXIT_PROBE_CHANGED`. Tradeoff: every reviewing-mode reader of 5 changes: review.md,
   README, guides, diagrams, code map, and the tests that assert 5. **Breaking** for any out-of-repo
   script that branches on review exit 5.
2. **Move the probe codes (5/6/7 to 9/10/11).** Tradeoff: old metrics rows with `codex-probe=5` change
   meaning, `review_metrics.PROBE_LIMITED_NOTE` has to change, and `crew-providers/SKILL.md` (outside
   `ALONGSIDE`) would need a separate feature PR. More churn, and history becomes ambiguous.
3. **Keep the values and document the per-mode meaning.** Tradeoff: this does not fix it. The direction
   asks for distinct codes and a test that they stay distinct.

## Recommendation

Option 1, with a test that every `EXIT_*` constant in `review_run` has a distinct value, and a sabotage
entry that puts `EXIT_UNVERIFIED` back to 5. `review_run.py`, `commands/review.md` and
`plugin/crew/tests/sabotage*.py` are all in `HARNESS`, so this is a **tooling-only PR**.

## Open questions (default taken)

- Which value should `EXIT_UNVERIFIED` take? **Default taken:** 9. 8 is reserved for L-0527's
  `EXIT_PROBE_CHANGED` on its source (`git show d4f1e5bc:plugin/crew/hooks/scripts/review_run.py`, `:175`).
- Should L-0528 land before or after L-0527? **Default taken:** either order. Whichever lands second
  re-checks the distinct-values test with the other's constant included.
- Should the three reasons for a refusal (gate, new finding, could not check) get three codes?
  **Default taken:** no. They stay one code, `EXIT_UNVERIFIED`, with the reason on stderr as today. Splitting
  them is a separate ask.
- The breaking change is flagged in the CHANGELOG entry and in the PR body.
