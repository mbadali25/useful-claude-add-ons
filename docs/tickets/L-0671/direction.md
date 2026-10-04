# L-0671 direction: sabotage entries for autopilot's auto-replan guards, and review.md names the policy

status: proposed 2026-10-04 (split from T-0074; filed as L-0671)
risk: high

Split from T-0074.

## Request
T-0074 and L-0670 add two guards to `crew_autopilot.py`: the policy that decides whether autopilot may reject a review itself, and the check that a successor plan quotes the findings. Neither ticket may add sabotage entries, because `plugin/crew/tests/sabotage*.py` is a review/gate harness path and a harness change lands alone (owner rule 2026-09-28, T-0087). Until the entries exist, nobody has shown that the new tests fail when a guard is broken. `plugin/crew/commands/review.md` step 3 also still says any BLOCK stops for the owner, with no word about the policy; it is a harness path too.

## What exists (origin/main 155fe6d8)
- plugin/crew/tests/sabotage_autopilot.py holds `AUTOPILOT_MUTATIONS` as (label, target, find, replace, test) tuples, appended to `sabotage.MUTATIONS`; plugin/crew/tests/test_crew_autopilot.py holds every anchor to exactly one match.
- scripts/check-tooling-pr.py:79 and :83 list `plugin/crew/tests/sabotage*.py` and `plugin/crew/commands/review.md` in `HARNESS`; `plugin/crew/tests/**`, docs and version files ride along (:99-118).

## Recommendation
One tooling-only PR: a mutation per way each guard could let autopilot past a person, each tied to a test that goes red, plus one sentence in `review.md` step 3. No production code.

## Options considered
1. One tooling PR after both feature slices (recommended).
2. Two tooling PRs, one per guard: more review rounds for the same lines.
3. Put the mutations in a non-`sabotage*` file to ride with the feature: defeats the owner rule.

## Depends on / order
T-0074 and L-0670, both merged. If L-0670 is delayed, this may land with T-0074's mutations only and L-0670's follow in their own tooling PR.
