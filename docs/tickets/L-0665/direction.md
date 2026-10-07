# L-0665: promote-gate reads the newest PROMOTIONS.md row for an environment and sha, not the first
Split from T-0062. risk: high (a guard's precondition)

## Problem
`requires` is satisfied by the FIRST row of `.work/PROMOTIONS.md` whose environment and sha match (`plugin/crew/hooks/scripts/promote-gate.sh:397-407`, `promote-gate.ps1:428-438`, origin/main `155fe6d8`). Rows are appended (`plugin/crew/commands/promote.md:292`), so the first row is the oldest. Two wrong answers follow:
- A failed promotion followed by a successful re-run of the same sha stays blocked for good. Found in T-0045 planning, 2026-09-26.
- A pass followed by a later failed run of the same sha still admits the downstream deploy. This is the unsafe direction.

## Recommendation
The last matching row decides, in both flavours. No dependency on T-0009 or on T-0062: it can land now.

## Options considered
1. (Taken) Newest row decides.
2. Any all-pass row admits. Rejected: keeps the unsafe direction.
3. Any failing row blocks. Rejected: a sha could never recover from one bad run.

## Approval
Owner go 2026-10-04 for the T-0062 hand-off; open questions take the recommendation.
