# Crew outcome eval: results (T-0510, L-0728 slice 3)

Measured 2026-10-24 to 2026-10-25 on one host. This page reports what two tasks showed. It gives **no bucket verdict**: the
selection yielded one task per bucket (owner decision 2026-10-20), and the harness needs at least 2 tasks in a bucket.

| Item | Value |
|---|---|
| Harness (t-0107 rows, after #680) | `scripts/crew-outcome-eval.py` sha256 `700c873b07dc0829...` at main `16ae18675` (crew 1.2.83). The t-0108 rows ran earlier; the preflight of 2026-10-24 recorded harness `dbf8585a...` at `a1a98a21`, crew 1.2.74, and the harness and crew version of the later t-0108 rows were not recorded (unknown) |
| Crew arm change during the run | PR #680 added `graphify-out` to the crew arm's `removePaths` (merged `16ae18675`). Every t-0108 row, both arms, ran before it, and the crew runs before it were exposed to the `refresh` stop; every t-0107 row ran after it |
| Image | t-0107 rows: `crew-outcome-eval:1` rebuilt 2026-10-25 as `sha256:7c9a174cb917...` (the earlier image was gone). t-0108 rows: the earlier image `sha256:db6a863c...`. Claude Code 2.1.303 and Codex 0.162.1 in both |
| Canary | PASS on the rebuilt image, `network=none proxy=unix-socket` (`canary.txt`, 2026-10-25T22:02Z) |
| Author model | claude-sonnet-5-5, medium effort, both arms |
| Reviewer | crew: Codex `gpt-6-sol`; baseline: `/code-review`, same family as the author |
| Cost basis | list price. Both logins are subscriptions, so no cash was billed per run |

## What was compared

Crew: `/crew:autopilot run` on a ticket made from the task statement. Baseline: plain Claude Code, then `/code-review` up to 3 cycles.
Tasks: `t-0108-nuclei-safe-defaults` (bucket M, 10 scored defects) and `t-0107-gizmoduck-routine-cli` (bucket L, 9 scored defects).

## Per-task observations (scored runs only)

| Task | Arm | Scored runs | Cost USD per run | Escaped defects per run | Review cycles | Wall seconds | Ended by |
|---|---|---|---|---|---|---|---|
| t-0108 | crew | 2 | 3.29, 1.74 | 0, 0 | 1, 0 | 547, 302 | stop, resume-cap |
| t-0108 | baseline | 2 | 0.98, 0.84 | 0, 0 | 3, 3 | 249, 242 | stop, stop |
| t-0107 | crew | 3 | 3.59, 3.78, 2.26 | 1, 0, 0 | 2, 2, 0 | 680, 839, 375 | stop, stop, resume-cap |
| t-0107 | baseline | 3 | 1.34, 1.29, 1.43 | 0, 6, 1 | 3, 3, 3 | 351, 354, 381 | stop, stop, stop |

Observations, not verdicts:
- t-0108: neither arm let a scored defect escape in any scored run. Crew cost 1.8 to 3.9 times baseline per run (mean ratio 2.8) and took longer.
- t-0107: crew escaped 1, 0, 0 of 9; baseline escaped 0, 6, 1 (median 1). Crew cost 1.6 to 2.9 times baseline per run (mean ratio 2.4). With 3 runs per arm and one baseline run at 6, this is a hint, not a result.
- Two crew runs ended at the harness resume cap (the arm was still asked for work); they are graded as they stand.
- Regressions (base-passing tests failed): 0 in every scored run.
- Break-even: not computed. The harness computes it only per bucket, and no bucket qualifies.

## Treatment differences (read before comparing arms)

- The crew arm runs without `.crew/codemap` and `graphify-out` (arm file `removePaths`). Both arms start from the same base tree whose `CLAUDE.md` names those maps, so this may favour the baseline.
- Crew has a Codex review available that the baseline does not (two of the five scored crew runs had no completed review cycle); the reviewers are different model families.
- The harness does not digest the arm file into a row, so rows from before #680 are told apart only by the UTC stamp in `runDir`; all t-0108 rows ran under the older arm file.

## Excluded and voided runs

- Contaminated (excluded from the numbers, listed by the harness): t-0108 crew attempt 2 and t-0108 baseline (1), both "hidden test content"; t-0107 crew (3, "hidden test content"; the report lists them once as attempt 1) and t-0107 baseline (1, "reference PR number"). The detector flags 3 distinctive hidden-test lines in one transcript file; whether each flag is a real leak or a correct solution that happens to match was not examined.
- Unscorable: the first t-0108 crew attempt (no CLI JSON, exit 134, 2.56 USD, kept as unscored spend).
- Voided and kept in `/repos/personal/eval-runs/T-0510/`: the pilot row stopped at `split-check-unknown`; a t-0107 crew row with UNKNOWN cost (its transcript did not parse; a full disk was the suspected cause); 8 t-0107 rows that hit the Claude weekly limit (0 USD); `aborted-attempt0-proxy-path-too-long.jsonl` (a zero-spend abort).

## Spend against the cap

Cap 150 USD, stop at 140. Recorded in `results.jsonl`: 41.11 USD (the report total; it already includes the 2.56 USD unscorable attempt, whose cost is also carried into the next row's `costUsd`, so summing that column double counts it). Not in the file: the spike (about 3 USD), the killed pilot baseline (under 1 USD), the voided pilot row (0.49 USD) and the voided t-0107 row (1.12 USD, CLI-reported, a different basis from the list price used elsewhere). All-in roughly 46 USD, give or take the mixed bases.

## Not verified

- No bucket verdict; none can be given from one task per bucket.
- Whether the contamination flags were real leaks.
- Variance: 2 to 3 scored runs per cell cannot separate the arms; the baseline's 6-defect run shows the spread.
- Whether the rebuilt image differs from the first beyond its id (apt and npm transitive packages float; Claude Code and Codex are pinned).
- The crew README one-line-per-bucket entry was not added: every bucket is "could not tell", and a `plugin/crew/` edit needs a version bump.

## Harness report (verbatim)

```
# Outcome eval report

Runs: 17; total cost: 41.11 USD

## Bucket S
could not tell: no tasks in this bucket
could not tell: 0 task(s) with at least 2 known runs per arm (need 2)
Regressions (median base-passing tests failed, beside the verdict, never folded in): crew UNKNOWN, baseline UNKNOWN

## Bucket M
note: 1 crew run(s) were graded at the harness resume cap, not at an autopilot stop (the arm was still asked for work)
could not tell: 1 task(s) with at least 2 known runs per arm (need 2)
Tasks counted: t-0108-nuclei-safe-defaults
Regressions (median base-passing tests failed, beside the verdict, never folded in): crew 0, baseline 0
Contaminated runs (excluded): t-0108-nuclei-safe-defaults/baseline/attempt 1, t-0108-nuclei-safe-defaults/crew/attempt 2

## Bucket L
note: 1 crew run(s) were graded at the harness resume cap, not at an autopilot stop (the arm was still asked for work)
could not tell: 1 task(s) with at least 2 known runs per arm (need 2)
Tasks counted: t-0107-gizmoduck-routine-cli
Regressions (median base-passing tests failed, beside the verdict, never folded in): crew 0, baseline 0
Contaminated runs (excluded): t-0107-gizmoduck-routine-cli/baseline/attempt 1, t-0107-gizmoduck-routine-cli/crew/attempt 1
```
