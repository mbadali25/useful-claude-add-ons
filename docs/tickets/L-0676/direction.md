# L-0676 direction: sabotage mutations for crew's recall project argument          status: direction   risk: low
Split from T-0083 on 2026-10-04. Filed as L-0676.

## Ask
L-0675 changes `plugin/crew/hooks/scripts/crew_recall.py` and adds tests for it. The repo requires that a guard's tests are proven by sabotage: put the bug back and see the named test go red. crew's sabotage tables live in `plugin/crew/tests/sabotage*.py`, which is review and gate harness (scripts/check-tooling-pr.py:78). A harness change lands alone, with no feature work in the same PR (owner rule 2026-09-28, T-0087). So the mutations for L-0675 need their own tooling-only PR.

## Options
1. **Recommended: a tooling-only PR after L-0675 merges, adding the mutations to `sabotage_context.py`.** This is the standing "feature PR, then tooling PR" order.
2. Record hand-run sabotage in L-0675's PR body and add nothing to the table. Rejected: the table is what keeps the proof repeatable; a hand-run note is not re-run when the code moves.

## Approval
Status `direction`. Option 1 taken as the default on 2026-10-04 with the owner unavailable.
