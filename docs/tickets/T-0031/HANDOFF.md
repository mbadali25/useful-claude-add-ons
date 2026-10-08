# Cloud handoff: T-0031

**Cross-session versioned contracts on the coordination record, frozen once built against**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

**Blocked: implementation cannot start until T-0030 is merged to main.** T-0030's code (`crew_coord.py`) is only on a local branch that is not on the shared remote, and origin/main `ce235468` has no `crew_coord.py`, `crew_wave.py` or `crew_contract.py`.

- **Role:** parent ticket. Its children are L-0633, L-0634 and L-0635. An earlier split (2026-09-30) moved research findings to L-0546, which is a separate ticket.
- **INDEX status:** ready (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `T-0031-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0031/direction.md`, `docs/tickets/T-0031/spec.md`
- **Size:** about 260 production lines, all in a new `plugin/crew/hooks/scripts/crew_contract.py`. No harness path: `crew_ticket.py` is a harness path and is imported and called, never edited. The sabotage mutations for this code are L-0635, a tooling-only PR.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0030 | in-progress, not on main, not in this hand-off | Provides `crew_coord.py` (`Channel`, claims, the `coord` config block) and the `crew-coord/<channel>` branch. Hard blocker. |
| T-0010 | merged | The approval and questions policies that `crew_ticket.accepted` honours; `build-against` reads that approval state. |

The facts recorded for this hand-off also list T-0029 (in-progress, the autopilot wave) because the INDEX row names it. The spec says that after the split this slice does not touch the wave, so T-0029 is a dependency of L-0633 and L-0634 only. The spec wins: T-0029 does not have to land before this ticket.

This ticket blocks: L-0634 (reads this ticket's records and bindings), L-0635 (sabotage for this module), T-0032 (ordering; messaging announces "contract vN is up"), and L-0546 (only where a finding is filed against a contract version). L-0633 does not need this ticket's code, but its spec asks for T-0031 to land first to keep the version order simple.

Order of the whole family:

1. T-0030 and T-0029 land on main (neither is part of this hand-off).
2. T-0031 (this ticket): the contract record and its freeze rule. Needs T-0030 only.
3. L-0633: `<channel>:<id>` dependencies in the wave. Needs T-0029 and T-0030.
4. L-0634: the wave refuses a built-against hash mismatch. Needs T-0031, T-0029, T-0030, and L-0633 first because both edit the same function in `crew_wave.py`.
5. L-0635: the sabotage mutations for all three, as a tooling-only PR. Last.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (this branch's base is `ce235468`); re-check each anchor.
- Every `crew_coord.py` anchor in the spec is from the unmerged branch `T-0030-coord` at `ec9a28a2`, not from main. That branch is not on the shared remote, so a cloud session cannot read it. Re-find each name by content once T-0030 is on main. A helper that was renamed is followed; a helper that was removed is a stop for the owner.
- No plan.md is published (the spec says none exists). The implementing session writes the plan, after T-0030 lands.
- Prefer `crew_coord.py`'s public names. If the private `_setup` is the only route to the channel, ask the owner before widening `crew_coord.py`. No edit to `crew_coord.py` beyond what T-0030 lands.
- No force push, `--force-with-lease` or `+` refspec, no checkout of the channel branch. The only local file written is `.work/tickets/<id>/contracts.json`.
- No edit to any `HARNESS` path of `scripts/check-tooling-pr.py`. No `sabotage*.py` file in this PR.
- direction.md refers to `.work/tickets/T-0030/direction.md` as the approved direction. That file is not published here.
- direction.md mentions a host-local `heavy-run` wrapper. Whether the cloud session has an equivalent: could not tell.

## Open questions for the owner (recommended option taken)

1. Is tying "owner-approved" to the ticket's approval receipt (`crew_ticket.accepted`) enough, or should a new contract version also need an owner-only signal like T-0030's `--break`? Taken: the receipt is enough.
2. Is the local binding in `.work/tickets/<id>/contracts.json` acceptable, given `.work/` is per worktree and ignored? Taken: yes, with the channel's `built_by` as the shared copy.
3. Should a contract body be limited to text formats? Taken: opaque bytes, 1 MiB limit.
4. One sabotage PR for all three slices (L-0635), or one per slice? Taken: one.
5. The INDEX row was already split once (L-0546, findings only). Is a second split into three children acceptable, or should the dependency form and the wave refusal stay in this ticket as one PR of about 470 production lines? Taken: split.

The children's own questions are in their hand-off notes (L-0633, L-0634, L-0635).

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/T-0031/` in the final PR unless the owner wants it kept.
