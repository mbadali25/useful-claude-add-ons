# Cloud handoff: L-0648

**promote-gate reads the `github` entry: the sha input must be the reviewed HEAD**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

Not buildable yet: it needs T-0045 merged, and lands after T-0062 (which is itself blocked on T-0009).

- **Role:** child, split from T-0045, slice 5 of 7 (T-0045 itself is the first landing, so the family has eight).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0648-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0648/direction.md`, `docs/tickets/L-0648/spec.md`
- **Size:** about 120 production lines (`promote-gate.sh` about 60, `promote-gate.ps1` about 60). One guard rule in the two flavours of one gate. No harness path: `promote-gate.*` is not in `HARNESS`.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0045 | direction, handed off (branch `T-0045-build`, draft PR #407), not built | Defines the `github` entry, its canonical prefix and `shaInput`. |
| T-0062 | ready, handed off (branch `T-0062-build`), not built; blocked on T-0009 (PR #336, open on 2026-10-04) | Edits the same two files (`promote-gate.sh`, `promote-gate.ps1`) and owns the `gh api ... /dispatches` form. This ticket lands after it and re-anchors. |
| L-0564 | direction | Ordering only. promote-gate review follow-ups in the same files; whichever lands second merges main. |

The facts file lists T-0045 and T-0062; the direction adds L-0564 as ordering only. The direction words T-0062 as "lands after T-0062 if T-0062 is in flight"; the spec's Unknowns say to re-read both gate files after T-0062 lands, so it is treated as must-land-first. T-0062's PowerShell twin is L-0664 and its first-row fix is L-0665; both touch `promote-gate.ps1` or `promote-gate.sh` too. Whether this ticket must also wait for them: could not tell from the files; if they are in flight, the second to land merges main.

**This ticket blocks:** L-0649.

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
- This is a hook that can block. CLAUDE.md requires a committed regression suite with must-block and must-allow cases, sabotage-tested, and says to re-review the fix to a guard as hard as the guard.
- The spec's Unknowns bullet that starts with a 40-character hex sha "as the sha input value. Decided: blocked as non-literal" does not read as intended: a literal 40-hex value is what the rule accepts. The acceptance check `sha-input-non-literal` names `$(git rev-parse HEAD)`, so the bullet most likely held that substitution and it was expanded when the spec was written. The staged text was left as it is; follow the acceptance check, and ask the owner if in doubt.
- The PowerShell half can only be run on native Windows with pwsh. Elsewhere report it as NOT RUN, never as passed.
- The `gh api ... /actions/workflows/<wf>/dispatches` form is T-0062's. Do not recognise it here, and add no second validator for the entry.
- The three existing promote-gate suites in the run line stay green and unedited.
- `promote.md` is at its 380-line allowance: no net growth.
- Touch names `plugin/crew/skills/crew-verification/github-deploy.md` and `test_promote_gate_github.py`, which L-0647 creates. If this lands before L-0647 those files do not exist yet; which ticket then creates them: could not tell, ask the owner.
- No edit to `plugin/crew/tests/sabotage*.py` (harness). Mutations go in `ghdeploy_mutations.py`.

## Open questions for the owner (recommended option taken)

1. Fold this into T-0062? Taken: keep it separate, land after it.
2. The PowerShell half can only be run on native Windows. Taken: verified on a Windows machine before landing, reported as not run elsewhere.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0648/` in the final PR unless the owner wants it kept.
