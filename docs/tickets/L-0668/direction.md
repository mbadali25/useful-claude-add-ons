# L-0668: sabotage mutations for the review policy, the fix phase and the stop contract (tooling-only PR)

Split from T-0067 on 2026-10-04. Status: direction, recommended option taken (owner not available). Risk: high (review and gate harness).

## Ask
T-0067 and L-0666 add a fail-closed decision (when autopilot may fix findings itself) and a contract (what a stop may ask the owner). The repo rule for a guard is that its tests are sabotage-tested: reintroduce the bug and confirm the suite goes red. The mutations live in `plugin/crew/tests/sabotage_autopilot.py`, which is a harness path, and a harness change lands alone (owner rule 2026-09-28, T-0087). So they cannot ride in either feature PR.

## Measured (origin/main `155fe6d8`)
- `scripts/check-tooling-pr.py:58-87`: `plugin/crew/tests/sabotage*.py` is in `HARNESS`. `:99-118`: tests, docs, version files, the code map and the graph may ride along; production code may not.
- `plugin/crew/tests/sabotage_autopilot.py` is 1118 lines (`.pylintrc:140` allows 3400) and already holds the autopilot mutation tuples that `sabotage.py` imports. `sabotage.py` itself is at the limit and is not edited.
- `plugin/crew/tests/test_sabotage_harness.py:371` checks every anchor is present exactly once.

## Options
1. **One tooling-only PR after both feature PRs (recommended).** Mutations for the policy, the fix decision and the contract, each naming the test it must turn red.
2. **Two tooling PRs, one per feature PR.** Tighter coupling in time, twice the harness-rule overhead (golden replay, seam contracts, canary review) for about a dozen tuples each.
3. **No mutations.** Rejected: two of crew's guard bugs were caught only by sabotage.

## Recommendation
Option 1. If L-0666 is delayed, land the policy mutations alone and file the rest as a follow-up.

## Depends on
T-0067 and L-0666 merged.
