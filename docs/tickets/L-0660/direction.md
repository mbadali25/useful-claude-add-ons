# Sabotage entries for goal resume: writers, handoff validation, discovery (L-0660)

Split from T-0056 on 2026-10-04. Status: seed, written for hand-off; filed as L-0660.

## Why this is its own ticket
T-0056 and its children L-0658 and L-0659 add fail-closed behaviour: "could not tell" never becomes the ticket form,
a stopped goal is never resumed, a ticket handoff keeps its branch check. The repo's rule is that such a
guard is sabotage-tested: put the bug back and confirm a named test goes red. The mutation lists live in
`plugin/crew/tests/sabotage*.py`, which are review/gate harness paths (`scripts/check-tooling-pr.py`
`HARNESS`). A harness change lands alone, with no feature code in the same PR (owner rule, 2026-09-28;
standing instruction 2026-09-30: feature PR first, then the tooling PR).

## Options
1. **One tooling-only PR after the three feature PRs (recommended).** One review round for the harness.
2. One tooling PR after each feature PR. Three harness reviews for about ten mutations.
3. No sabotage entries. Rejected: two of crew's guard bugs were caught only by sabotage.

## Recommendation
Option 1. If L-0658 or L-0659 is delayed, land the mutations for what has merged and say which are left.

## Depends on
T-0056, L-0658, L-0659 (the code the mutations edit and the tests they must turn red).
