# Cloud handoff: L-0674

**T-0082 child 2: the verify gate ends a hung rule itself and reports it FAILED (could not tell)**

**ON HOLD: needs the owner's go before it is planned or built.** It is also blocked until T-0082 has merged.

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** child ticket, split from T-0082, slice 2 of 2 (the other is L-0673).
- **INDEX status:** direction, HOLD (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session, only after the owner's go)
- **Branch:** `L-0674-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0674/direction.md`, `docs/tickets/L-0674/spec.md`
- **Size:** about 180 production lines (`verify-gate.sh` about 70, `verify-gate.ps1` about 110).
- **Harness:** yes. Both gate scripts and `plugin/crew/tests/sabotage_tooling.py` are harness paths, so this lands alone as a tooling-only PR.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| Owner decision | open | Whether to build this at all. It reopens ground closed in crew 1.0.21, where per-rule process kill was descoped after five review rounds. |
| T-0082 | direction, spec ready, not built | Must merge first. This ticket adds one reason to its decision table and reuses its lines. |
| T-0087 | merged | Tooling PRs land alone. |

The ticket facts and the spec agree. The parent's other prerequisites (L-0513, L-0572, T-0076, T-0077, L-0555) have all landed. L-0513 is related: it already bounds `--all` runs from outside.

This ticket blocks nothing.

Family order:
1. T-0082 (parent, tooling-only PR)
2. L-0673, after T-0082 has merged
3. L-0674 (this ticket), after T-0082 has merged AND the owner's go. No order between L-0673 and L-0674.

## Read before writing code

- Do not start without the owner's go. The recommended option (a whole-run deadline in Stop mode only, no group kill) is recorded but held.
- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`), and T-0082 will move it again; re-read every line number after T-0082 merges.
- A stale plan.md is not published. The implementing session writes the plan.
- The design must not bring back process-group tracking or a kill of anything but the gate's own direct wrapper child. What a rule leaves running stays the documented limitation.
- Three unknowns are resolved before or at plan, not at implement: how the host ends a hook at its timeout, the deadline value (default 540 seconds), and how bash gets a bounded wait. The spec calls the last one the part most likely to cost review rounds.
- The spec asks for a check on a Windows machine (whether TERM ends a wrapper started from Git Bash) before review, and a native Windows run of the new test file. Whether a cloud session can get that: could not tell.
- No deadline under `--all` or `--ci`, no config key, no change to `hooks.json`.

## Open questions for the owner (recommended option taken)

1. Build this at all? Option 1 (whole-run deadline in Stop mode, direct child only) against option 3 (do nothing, rely on the marker not advancing). Taken: hold until the owner decides. This is the parent's open question 4.
2. If built: a fixed deadline derived from the hook timeout (recommended) or a per-rule timeout from config (option 2)?

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0674/` in the final PR unless the owner wants it kept.
