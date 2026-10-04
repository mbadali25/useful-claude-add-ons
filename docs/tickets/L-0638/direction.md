# Cross-session messaging: sabotage mutations for the bridge script (tooling PR)

Split from T-0032 (L-0638), 2026-10-04.

## Problem
`crew_bridge.py` (T-0032 and its children L-0636 and L-0637) is fail-closed code: a doorbell parser, a pending state and a lane refusal. This repo's rule is that such checks are sabotage-tested: reintroduce the bug and confirm a named test goes red. The sabotage files are harness paths (`plugin/crew/tests/sabotage*.py`, `scripts/check-tooling-pr.py:79`), and a harness change lands alone with no production code (owner rule, 2026-09-28). So the mutations cannot ride in the feature PRs.

## Options
- A (recommended, taken): one tooling ticket after the three feature tickets, adding `sabotage_bridge.py` and its registration, tests only.
- B: one tooling ticket per feature ticket. Rejected: three harness PRs, each running the golden replay and the canary review, for about ten mutations in total.
- C: no sabotage. Rejected by the repo rule.

## Open questions
- `plugin/crew/tests/sabotage.py` is at `.pylintrc`'s `max-module-lines` limit, so a registration line does not fit. Taken: register the way the newest per-area module does at implementation time; if every route needs a new line in `sabotage.py`, remove a line in the same change or stop for the owner.
