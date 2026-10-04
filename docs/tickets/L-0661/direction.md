# L-0661: sabotage mutations for the autopilot routing rows (tooling-only PR)

Split from T-0057. Status: direction. Risk: med.

## Ask
T-0057 adds five autopilot rows and an availability gate to `crew_route.py`. Its tests pin the must-not-route cases, but nothing proves those tests would go red if the guard were removed. T-0023 shipped with that proof (`plugin/crew/tests/sabotage_route.py`); the new rows need the same.

## Why it is its own ticket
`plugin/crew/tests/sabotage*.py` is review/gate harness (`HARNESS`, scripts/check-tooling-pr.py:79 at origin/main `155fe6d8`). A harness change lands alone, with no feature work in the same PR. `crew_route.py` is feature code, so the mutations cannot ride with T-0057.

## Options
1. **Add the mutations to `sabotage_route.py` in a tooling-only PR after T-0057 merges (recommended).** One file, the existing tuple shape, registered already through `ROUTE_MUTATIONS`.
2. A new `sabotage_route_autopilot.py`. It needs an import and a concatenation in `sabotage.py`, which is at the pylint line limit (3400 of 3400). Rejected.
3. No sabotage. Rejected: the dangerous cases here are false routes, and two guard bugs in this repo were caught only by sabotage.

## Recommendation
Option 1.

## Depends on
T-0057 (the code the mutations target must be on main).

## Approval
Split written 2026-10-04 under the owner's standing authorization; not yet approved as a ticket.
