# L-0643 direction: sabotage mutations for T-0043's autopilot fixes and the fence parser (tooling PR)
Split from T-0043 on 2026-10-04. Checked against origin/main `155fe6d8` (crew 1.0.322).

## Problem
T-0043 and L-0642 change code that decides whether autopilot stops for a person. The repo's rule for such code is a committed, sabotage-tested regression: reintroduce the bug, and a named test goes red. The mutation table for autopilot is `plugin/crew/tests/sabotage_autopilot.py`, and since T-0087 every `plugin/crew/tests/sabotage*.py` file is review/gate harness (`scripts/check-tooling-pr.py:79`): a change to it lands alone, with no feature work in the same PR. So the two feature PRs cannot carry their own mutations, and until this ticket lands their sabotage evidence is hand-run and lives only in PR bodies.

## Recommendation (taken, owner unavailable)
One tooling PR after both feature PRs are on main. It adds the mutations to `sabotage_autopilot.py`, touches no production file, and runs the harness rule (`.crew/verify.json:457-473`). Tests, the changelog, version files and refresh artifacts ride along, as the rule allows.

## Options not taken
- One tooling PR per feature PR: two runs of the harness rule (golden replay, seam contracts, canary review) for about a dozen table rows in one file.
- Declaring `crew_autopilot.py` as a seam and landing everything together: the `Tooling-seam:` trailer is for a consumer that must move with a harness format change, not for carrying a feature.
- Not committing the mutations: the hand-run evidence is not repeatable, and two autopilot guard bugs were caught only by this suite.

## Open questions for the owner
- [x] If L-0642 is delayed, this ticket waits with it. Taken: wait. The alternative is to land T-0043's three mutations first and file the fence mutations as a further tooling ticket.
