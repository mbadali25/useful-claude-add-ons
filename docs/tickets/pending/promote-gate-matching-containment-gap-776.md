# Promote gate: `matching()` containment treats an omitted `environment` input as open (left over from #776)

Priority: unassigned (owner to set).
Status: needs ticket (no T-/L-/C- id yet). Recorded 2026-11-17 from the owner's open-item list.

## Problem

#776 stopped the promote gate from classifying `gh workflow run w.yml -f environment=development` (and qa) as a production dispatch. It deliberately left one question open: how the containment match should treat an `environment` input that a declared dispatch omits. That gap is this ticket.

## Evidence

VERIFIED by `gh pr view 776` on 2026-11-17: state MERGED (head `de6f117d5`, base `main`, all 30 checks SUCCESS, crew 1.3.91 per its body). The body says:
- Root cause: `_promote_dispatch.fits()` allowed any extra input on a dispatch, so a command carrying `-f environment=development` "fitted" a production dispatch whose declaration omitted `environment`.
- Fix: where the command gives `environment` and the declared dispatch omits it, the command now fits only the environment of that name; otherwise the result is could-not-tell.
- "The containment match itself is unchanged; this limit is documented in reference 23 and the crew README paragraph."
- "Open note: guard semantics ... is left open for the owner."

VERIFIED by reading main in this checkout: `matching(envs, strict)` is at `plugin/crew/hooks/scripts/promote-gate.sh:440`. It decides a command matches an environment when any declared `deploy` text is contained in the command (`fold(d) in fcmd`, line 489), with extra flags or a wrapper allowed, "not the reverse (L-0689)". `fits()` is at `plugin/crew/hooks/scripts/_promote_dispatch.py:166`.

The gap, stated precisely: containment accepts extra text around a declared command, so a command that adds an input the declaration omits is still "contained". #776 closed that for the `environment` input in `fits()`; `matching()` is unchanged, and other omitted inputs, spellings or wrappers that change what a dispatch targets are not covered. INFERRED: the owner's "matching() gap" is this; the owner's brief did not name the line, and I did not test any bypass.

## Recommended next step

Decide the intended semantics (owner), then write must-block and must-allow cases for omitted-input dispatches through both `promote-gate.sh` and `promote-gate.ps1` and sabotage-test them. This is the gate itself, so it is a harness change that lands alone.

## Acceptance criteria

- The owner's decision on containment for omitted inputs is recorded.
- Must-block and must-allow suite for it, sabotage-tested (a reintroduced bug turns it red), in sh and ps1.
- Reference 23 and the crew README paragraph are updated in the same PR.

## Owner questions

1. Should a command that supplies any input the declared dispatch omits be could-not-tell, or only `environment`?
2. Is exact-match (no containment) wanted for dispatch commands?

## Out of scope

Reverting #776; production-environment policy (`environments.prodUnattended`).

## Related

#776 (merged); `promote-gate.sh`, `_promote_dispatch.py`; `plugin/crew/tests/promote_tree_mutations.py` (named in the PR body).
