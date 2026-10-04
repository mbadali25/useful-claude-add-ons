# Cloud handoff: T-0074

**Autopilot auto-rejects an out-of-rounds review that has a BLOCK and continues with a successor plan, capped**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** parent of a three-ticket family. Children: L-0670, L-0671. This ticket is narrowed to the first slice (the opt-in key, the policy, the `auto-reject` subcommand, the routing in `next`, and the docs).
- **INDEX status:** direction, priority high (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session). The facts recorded for this hand-off note "Has open questions for the owner".
- **Branch:** `T-0074-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0074/direction.md`, `docs/tickets/T-0074/spec.md`
- **Size:** about 150 production lines (`crew_autopilot.py` about 145, `crew_state.py` 2, `config.template.json` 1). No harness path. `crew_autopilot.py` and `commands/autopilot.md` are seam paths, which count as feature work here; the sabotage entries and the `review.md` sentence are split out to L-0671.

## Dependencies and work order

Must land first (all already on main):

| Ticket | State | Why |
|---|---|---|
| T-0010 | merged (PR #261) | The approval policy and `crew_autopilot.py approve`, which approves the successor plan and moves NEEDS_REPLAN to IN_REVIEW. |
| L-0510 | done, on main | Round rows carry `findings`, `provider` and `model_family`; a 0-BLOCK final round already auto-accepts, so this ticket covers only rounds with a BLOCK. |
| T-0004 | merged | `crew_autopilot.py next`, which this extends. |
| T-0018 | merged | The subcommand router and `status` (the `WAITING` map gains the new phase). |

Nothing unmerged blocks this ticket. It can be worked at any time.

Where the INDEX title and the spec disagree, the spec wins: the INDEX title still says "depends on T-0010, T-0073". The spec says T-0073 is no longer required.

| Ticket | State | Why it does not block |
|---|---|---|
| T-0073 | direction | Its `reviewAcceptance` key was never built, and its fix-only half shipped as L-0510. This ticket owns its own opt-in key. |
| T-0067 | ready | Fix-and-rereview while a round is left. This ticket acts only at zero rounds left. |
| T-0029 | in-progress | Its subagent never-list is not on main. If it lands first, re-read `scope_guard.py` before planning. |
| T-0109, T-0098 | direction | `reject` and `accepted_by` corrections in the ledger. Independent. |
| T-0037 | ready | A derived `needs-replan` ticket status. Independent. |

This ticket blocks: L-0670 and L-0671. T-0053 (ready, sleep mode) and T-0060 (spec, out-of-rounds pings) read better once this lands, but neither is blocked by it.

Family order:

1. **T-0074** (this ticket): key, policy, `auto-reject`, routing, docs. Feature PR.
2. **L-0670**: the check that a successor plan quotes every BLOCK and FIX line. Feature PR. After T-0074.
3. **L-0671**: sabotage entries for both guards and the `review.md` sentence. Tooling-only PR. After T-0074 and L-0670; it may land after T-0074 alone, with only this ticket's mutations, if L-0670 is delayed.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (this branch starts at `ce235468`); re-check each anchor.
- There is no plan.md and none is published. The implementing session writes the plan.
- The default is `0`: off, today's behaviour, byte for byte. Nothing reads as permission by default; anything that raises or has the wrong type is a refusal that says "could not tell".
- Autopilot never accepts a round with a BLOCK, at any setting. `review_ledger.py --accept` stays the owner's.
- No edit to any harness path: `review_ledger.py`, `crew_ticket.py`, `scope_guard.py`, `commands/review.md`, `plugin/crew/tests/sabotage*.py`. The cap counts successor rows already on the ledger so that no ledger field is needed.
- `auto-reject` becomes the module's second writing subcommand. The test that pins "approve is the only writer" is replaced by one naming exactly two writers.
- The reviewer-family check in `review_ledger` is private. The spec's Unknowns give the two ways to handle that without editing the ledger; a test holds the two in step.
- Two accepted risks to carry into the PR body: the check-then-write gap before `reject` takes the ledger lock, and that the fixed reject name can be typed by hand.
- Docs are in Touch: README, CONFIG.md, PLUGINS.md, three guide sources with rebuilt HTML, DOCX and PDF, the lifecycle review diagram, and the code map.
- direction.md carries two owner decisions from 2026-09-30 (catch up with main by merge, never rebase; run the suites under the heavy-run wrapper with 4 workers). The wrapper path is local and is redacted as `<local-tmp>/`.
- Nothing was run when the spec was written: no tests, gates or git writes.

## Open questions for the owner (recommended option taken)

1. Opt-in key: `autopilot.maxAutoReplans` with default `0`. Alternative: wait for T-0073's `reviewAcceptance: all`.
2. Cap value when turned on: the owner sets it; the direction recommends 2. Alternatives: 1, or no upper bound.
3. On the cap: stop for the owner with the history. Alternative: park the ticket and move on.
4. Exclusions: rely on `autopilot.approval`, so the reject is allowed only where the successor plan could be self-approved. Alternative: a path-glob exclusion list for guard and production-authority tickets.
5. Successor plan author: `/crew:plan` as configured; the owner picks the planner model with `/crew:model`. Alternative: force a different model family or tier (the direction's original recommendation).
6. The cap counts every successor plan on the ledger, owner-approved ones included. Alternative: only those after an automatic reject, which needs a rejection history in `review_ledger.py`, a harness change.
7. T-0073: keep it open for the `reviewAcceptance` key, or close it as superseded by L-0510 plus T-0074. Not decided here.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/T-0074/` in the final PR unless the owner wants it kept.
