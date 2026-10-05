# Cloud handoff: L-0647

**`crew_ghdeploy.py record` and the `/crew:promote` github sequence**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

Not buildable yet: it needs L-0644, L-0645 and L-0646 merged first.

- **Role:** child, split from T-0045, slice 4 of 7 (T-0045 itself is the first landing, so the family has eight).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0647-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0647/direction.md`, `docs/tickets/L-0647/spec.md`
- **Size:** about 130 production lines in `plugin/crew/hooks/scripts/crew_ghdeploy.py`, plus prose in a new `plugin/crew/skills/crew-verification/github-deploy.md` and a pointer in `promote.md`. One writer with one sanitizer. No harness path.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| L-0644 | direction, handed off (branch `L-0644-build`), not built | `prepare` and the state file. |
| L-0645 | direction, handed off (branch `L-0645-build`), not built | `identify` and the run id. |
| L-0646 | direction, handed off (branch `L-0646-build`), not built | `watch` and the verdict that `record` writes down. |

The facts file says "T-0045 child 1, 2, 3", which are L-0644, L-0645 and L-0646. The spec agrees.

**This ticket blocks:** L-0649 (autopilot reads the recorded row).

**Order of the family** (parent T-0045, draft PR #407):

1. T-0045: the `github` entry in `.crew/verify.json` and `crew_ghdeploy.py check`.
2. L-0650: tooling-only PR that wires `ghdeploy_mutations.py` into the sabotage harness. Default is right after T-0045; it lands alone.
3. L-0644 `prepare`: after T-0045 and T-0009.
4. L-0645 `identify`: after L-0644.
5. L-0646 `watch`: after L-0645.
6. L-0647 `record` and the `/crew:promote` sequence: after L-0644, L-0645 and L-0646.
7. L-0648 promote-gate reads the `github` entry: after T-0045 and T-0062. It does not need L-0644 to L-0647.
8. L-0649 autopilot's deploy phase: last. After T-0011, T-0009, and L-0644 to L-0648.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- There is no plan for this ticket. The parent's plan.md (2026-09-26) is stale and is not published; the implementing session writes the plan. The direction's "kept from plan.md 'Design'" refers to text that is not available here. Where a design detail is not in this spec or the parent's files (`docs/tickets/T-0045/` on branch `T-0045-build`): could not tell, ask the owner.
- `promote.md` is at its 380-line allowance. No net growth without an owner decision; the sequence goes in `github-deploy.md`.
- A detail line must hold no pipe character, and every pipe in the log excerpt is shown as a slash, so nothing `record` writes can be read as a pass row. `forged-row-in-excerpt` pins it against the real `promote-gate.sh`.
- Rebuild `.work/PROMOTIONS.md` whole through a temp file and `os.replace`.
- The first-row `passed()` behaviour is T-0062's family (L-0665). Do not change how promote-gate or verify-gate read PROMOTIONS.md here.
- The attended evidence run is not a merge gate. It needs the owner present and a consumer repository with a nonProd workflow, after merge and install. A cloud session cannot do it; say so in the PR body. Its record (`.work/tickets/T-0045/attended-dispatch.md`) is gitignored and must hold no hostname, account name or secret.
- Touch includes `docs/guides/crew/src/troubleshooting.md` and the rebuilt guide outputs (HTML, DOCX, PDF from `docs/guides/crew/src/build.py`). Whether the cloud environment can rebuild DOCX and PDF: could not tell.
- No edit to `plugin/crew/tests/sabotage*.py` (harness), promote-gate or autopilot.
- Every slice from T-0045 to L-0649 adds to `crew_ghdeploy.py`, `test_crew_ghdeploy.py` and `ghdeploy_mutations.py` (where listed in Touch). Build on what the earlier slices merged; do not start a slice on a branch that lacks them.

## Open questions for the owner (recommended option taken)

1. `promote.md` is at its 380-line allowance. Taken: the sequence goes in a new sibling file of the crew-verification skill and promote.md points to it with no net growth. Alternative: raise the allowance.
2. The attended evidence run needs the owner present and a consumer repository with a nonProd workflow. Taken: it is evidence recorded after merge and install, not a merge gate.
3. Carried from the parent: rollback is not automated; the record names the previous good sha and a person chooses.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0647/` in the final PR unless the owner wants it kept.
