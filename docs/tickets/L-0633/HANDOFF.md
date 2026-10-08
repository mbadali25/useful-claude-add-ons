# Cloud handoff: L-0633

**Cross-session dependencies `<channel>:<id>` in the autopilot wave**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

**Blocked: implementation cannot start until T-0029 and T-0030 are both merged to main.** Both exist only on local branches that are not on the shared remote; origin/main `ce235468` has no `crew_wave.py` and no `crew_coord.py`.

- **Role:** child ticket, split from T-0031, slice 1 of 3 (the other children are L-0634 and L-0635).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0633-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0633/direction.md`, `docs/tickets/L-0633/spec.md`
- **Size:** about 140 production lines in `plugin/crew/hooks/scripts/crew_wave.py`. No harness path; the sabotage mutations for this slice are L-0635.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0029 | in-progress, not on main, not in this hand-off | The wave (`crew_wave.py`) and its dependency judgement, which this slice extends. |
| T-0030 | in-progress, not on main, not in this hand-off | The channel and the claim records this slice fetches and reads. |
| T-0031 | ready (PR in this hand-off) | Ordering only: not required by this slice's code, but both edit crew docs and the version files, so the spec asks for T-0031 first. |

This ticket blocks: L-0634 (same function in `crew_wave.py`), L-0635, and T-0032 (as this spec states it; T-0032's own spec names only T-0030 as a hard dependency and T-0031 as ordering).

Order of the whole family:

1. T-0030 and T-0029 land on main (neither is part of this hand-off).
2. T-0031: the contract record and its freeze rule.
3. L-0633 (this ticket): `<channel>:<id>` dependencies in the wave.
4. L-0634: the wave refuses a built-against hash mismatch.
5. L-0635: the sabotage mutations for all three, as a tooling-only PR.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (this branch's base is `ce235468`); re-check each anchor.
- The `crew_wave.py` anchors are from the unmerged branch `T-0029-wave` at `574985ce` and the `crew_coord.py` anchors from `T-0030-coord` at `ec9a28a2`. Neither branch is on the shared remote, so a cloud session cannot read them. Re-find each name by content once both are on main.
- No plan.md is published. The implementing session writes the plan, after T-0029 and T-0030 land.
- A fetch inside `plan`: T-0029's spec requires `plan` to write nothing. Confirm against the landed test. If it also pins `objects/`, the cross-session check moves to `start` only and `plan` reports such a dependency as `unknown (not fetched)`.
- This slice only fetches and reads. No write to the channel, no push, no edit to `crew_coord.py`, no new config key, no new hook.
- No edit to any `HARNESS` path of `scripts/check-tooling-pr.py` (`sabotage*.py`, `crew_ticket.py`, `scope_guard.py`).
- A peer's `done` claim is peer-written data. It decides only whether this side may start, never an approval.
- direction.md refers to `.work/tickets/T-0030/direction.md` as the approved parent direction. That file is not published here.

## Open questions for the owner (recommended option taken)

1. When several repositories on a channel hold the same ticket id, refuse the short form as `unknown` and require `<channel>:<repo>:<id>`, or prefer a claim from another repository over this one? Taken: refuse and require the long form.
2. Does a `released` peer claim close the dependency? Taken: no, only `done`.
3. May `plan` fetch the channel, or only `start`? Taken: `plan` fetches, unless T-0029's landed write-nothing test also pins `objects/`.
4. (From direction.md.) Does a stale `working` claim count as open or unknown? Taken: open, reported with its age.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0633/` in the final PR unless the owner wants it kept.
