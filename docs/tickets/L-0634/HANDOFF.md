# Cloud handoff: L-0634

**The wave refuses a ticket whose built-against contract hash no longer matches**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

**Blocked: implementation cannot start until T-0031, T-0029 and T-0030 are merged to main.** `crew_contract.py` (T-0031) is not written yet, and `crew_wave.py` (T-0029) and `crew_coord.py` (T-0030) exist only on local branches that are not on the shared remote.

- **Role:** child ticket, split from T-0031, slice 2 of 3 (the other children are L-0633 and L-0635).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0634-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0634/direction.md`, `docs/tickets/L-0634/spec.md`
- **Size:** about 110 production lines: `check_bindings` and the `verify` command in `crew_contract.py` (about 80), the call and its two refusal lines in `crew_wave.py` (about 30). No harness path; the sabotage mutations for this guard are L-0635.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0031 | ready (PR in this hand-off) | The contract record and the binding file this check compares. |
| T-0029 | in-progress, not on main, not in this hand-off | The wave, whose `_judge` calls the check. |
| T-0030 | in-progress, not on main, not in this hand-off | The channel. |
| L-0633 | direction (PR in this hand-off) | Not a functional dependency, but it edits the same function in `crew_wave.py`; land it first so the two do not conflict. |

This ticket blocks: L-0635, and T-0032 (as this spec states it; T-0032's own spec names only T-0030 as a hard dependency and T-0031 as ordering).

Order of the whole family:

1. T-0030 and T-0029 land on main (neither is part of this hand-off).
2. T-0031: the contract record and its freeze rule.
3. L-0633: `<channel>:<id>` dependencies in the wave.
4. L-0634 (this ticket): the wave refuses a built-against hash mismatch.
5. L-0635: the sabotage mutations for all three, as a tooling-only PR.

## Read before writing code

- The spec's evidence was checked at origin/main `155fe6d8`. Main has moved since (this branch's base is `ce235468`); re-check each anchor.
- The `crew_wave.py` anchors are from the unmerged branch `T-0029-wave` at `574985ce`, which is not on the shared remote. The record and binding formats are quoted from T-0031's spec, not from code. Re-read both after they land; the landed code wins over this spec's quotes.
- No plan.md is published. The implementing session writes the plan, after the tickets above land.
- The check never repairs anything: it does not rewrite a binding, a record or a body, and never picks the newer version. No write to the channel, no push, no hook, no config key.
- A ticket with no `.work/tickets/<id>/contracts.json` is not checked and causes no fetch. A bindings file that cannot be parsed is `unknown` (exit 3), never "no bindings".
- Order inside `_judge`: the contract check runs after the dependency check, so the cheaper local refusals come first.
- No check at implement, review or done time in this slice; only `verify` and the wave's `plan` / `start`.
- No edit to any `HARNESS` path of `scripts/check-tooling-pr.py`.

## Open questions for the owner (recommended option taken)

1. Should the same check also run at `/crew:done`? Taken: not in this slice; it would touch harness-adjacent commands and belongs in a follow-up if wanted.
2. Is a newer draft version on the channel information only, or should it stop the wave for the owner? Taken: information only.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0634/` in the final PR unless the owner wants it kept.
