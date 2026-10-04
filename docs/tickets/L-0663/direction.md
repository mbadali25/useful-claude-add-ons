# L-0663: sabotage mutations for the wave, split, sleep and wake routing rows (tooling-only PR)

Split from T-0057. Status: direction. Risk: low.

## Ask
L-0662 adds four rows whose danger is a false route: "go to sleep mode later" arming sleep, "run the tests in parallel" starting a wave. Its tests pin those cases. This ticket proves the tests bite, the same way L-0661 does for the first five rows.

## Why it is its own ticket
`plugin/crew/tests/sabotage*.py` is review/gate harness (scripts/check-tooling-pr.py:79 at origin/main `155fe6d8`) and lands alone. L-0662 is feature code.

## Options
1. **A second tooling-only PR after L-0662 merges (recommended).**
2. Fold these into L-0661. That would hold L-0661 until L-0662 merges and leave T-0057's own guards unproven for longer. Rejected. If L-0661 has not started when L-0662 merges, the two may be done as one PR; say so in the PR body.

## Recommendation
Option 1.

## Depends on
L-0662 (merged), L-0661 (merged, so the two PRs do not conflict in `sabotage_route.py`).

## Approval
Split written 2026-10-04 under the owner's standing authorization; not yet approved as a ticket.
