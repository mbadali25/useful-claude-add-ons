# L-0669: sabotage mutations for the T-0071 tracker fixes (tooling PR)          status: direction   risk: med
Split from T-0071 on 2026-10-04. Filed as L-0669.

## Ask
T-0071 fixes six accepted findings in `plugin/crew/hooks/scripts/crew_tracker.py` and `plugin/crew/commands/fix.md`, each with a test. Every guard branch in `crew_tracker.py` has one mutation in `plugin/crew/tests/sabotage_tracker.py` that proves its test can fail (that file's own header states the rule). The new branches have none, because `sabotage*.py` is a `HARNESS` path (`scripts/check-tooling-pr.py:78`) and a harness change may not ride with feature work (owner rule, T-0087). This ticket adds those mutations, alone.

## Direction check 2026-10-04
Checked against origin/main `155fe6d8` (crew 1.0.322). The problem does not exist yet: it starts when T-0071 merges. Precedent for the shape: L-0531 (merged), "Sabotage entries for L-0529 (tooling PR split from L-0529)".

## Options
1. **One tooling-only PR after T-0071 merges, one mutation per new branch, each aimed at the one test that sees it (recommended, taken).**
2. Put the mutations in T-0071's PR. Not possible: `check-tooling-pr.py` exits 1.
3. Skip the mutations. Rejected: the repo's rule for the one module that writes outside the repository is that a test without a mutation is not counted as coverage.

## Recommendation
Option 1.

## Open questions for the owner
- None that block. If T-0071's review changes a fix's shape, the mutation list in spec.md follows the merged code, not this list.
