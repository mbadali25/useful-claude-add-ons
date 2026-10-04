# Cloud handoff: L-0662

**T-0057 child 2: plain-text routing rows for autopilot wave, split, sleep and wake**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** child, split from T-0057, slice 2 of 3 (the family is T-0057, L-0661, L-0662, L-0663).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session). The direction says the split is "not yet approved as a ticket".
- **Branch:** `L-0662-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0662/direction.md`, `docs/tickets/L-0662/spec.md`
- **Size:** about 70 production lines in `plugin/crew/hooks/scripts/crew_route.py`. No harness path.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0057 | ready, not started | Must be merged first: the availability gate, the rule families and the soft ask line these rows use. |
| T-0023 | merged | The table and hook. |
| T-0018 | merged | The autopilot router. |

Blocked until T-0057 is on main. Do not start before then.

Not blocking (each makes one row live; until then the row produces no line at all):

| Ticket | State | Row |
|---|---|---|
| T-0029 | in-progress | `wave` |
| T-0052 and T-0058 | spec | `split` |
| T-0053 | ready | `sleep`, `wake` |

This ticket blocks: L-0663 (sabotage for these rows) and T-0054 (ready), whose guide lists the phrases.

Family order:

1. **T-0057**: gate and five rows. Feature PR.
2. **L-0661**: sabotage mutations for T-0057. Tooling-only PR. Independent of this ticket.
3. **L-0662** (this ticket): four more rows. Feature PR. After T-0057.
4. **L-0663**: sabotage mutations for this ticket. Tooling-only PR. After L-0662 and L-0661.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (this branch starts at `ce235468`); re-check each anchor, and re-read `crew_route.py` on main after T-0057 merges.
- There is no plan.md and none is published. The implementing session writes the plan.
- This ticket does not add `wave`, `split`, `sleep` or `wake` to `crew_autopilot.SUBCOMMANDS`. Each command's own ticket does. On main as it is, every example phrase must decide `none`.
- The `split` row routes to `/crew:autopilot split`, never to `/crew:split` (the Jira split command).
- `sleep` raises how much autopilot does without the owner. The must-not-route cases ("go to sleep mode later", a question about sleep mode, quoted text) are the point of the tests.
- No edit to `plugin/crew/tests/sabotage*.py` or `crew_autopilot.py`. Existing sabotage anchors in `crew_route.py` stay unique.
- The final argument shape of the four commands is not known yet (their tickets are not merged). Whichever lands second amends the row.

## Open questions for the owner (recommended option taken)

1. "morning" and "I'm back" are everyday greetings. Kept as wake phrases, as approved; they produce nothing until T-0053 lands, and the command decides what to do when sleep is not on.
2. Bare "this is too big" is not a split phrase. "this ticket is too big" and "<id> is too big" are.
3. `sleep` by phrase without a configured schedule is allowed; T-0053 decides the behaviour.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0662/` in the final PR unless the owner wants it kept.
