# Sabotage mutations for cross-session contracts and dependencies (tooling PR)

Split from T-0031 (2026-10-04 size check). Filed as L-0635.

Status: direction inherited from the parent, plus the owner's standing rule of 2026-09-28 (T-0087) that a change to the review/gate harness lands alone, and the standing instruction of 2026-09-30 that a `check-tooling-pr.py` refusal means "feature PR, then tooling PR".

## Scope
T-0031, L-0633 and L-0634 each add fail-closed behaviour with must-block tests. This ticket proves those tests can fail: one mutation per guard in a new `sabotage_contract.py`, registered in `sabotage.py`, each turning a named test red. It adds no production code.

## Why it is a separate ticket
`plugin/crew/tests/sabotage*.py` is in `HARNESS` in `scripts/check-tooling-pr.py`. A PR that changes a harness path may carry tests, docs and version files, but no production code, so the mutations cannot ride with the three feature PRs.

## Options
- A (recommended, taken). One tooling PR after all three feature PRs.
- B. One tooling PR after each feature PR. Three more PRs and three more version bumps for the same mutations; worth it only if the owner wants each guard sabotage-proven before the next slice starts.

## Question answered with the recommended option (owner not available 2026-10-04)
- A or B above. Taken: A.
