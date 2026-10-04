# Cloud handoff: T-0057

**Plain-text routing for the autopilot commands the router knows (status, assign, goal, goal resume, focus)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** parent of a four-ticket family. Children: L-0661, L-0662, L-0663. This ticket is slice 1 of 4 (the availability gate, the soft "not available yet" line, and five rows).
- **INDEX status:** ready (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `T-0057-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0057/direction.md`, `docs/tickets/T-0057/spec.md`
- **Size:** about 120 production lines, all in `plugin/crew/hooks/scripts/crew_route.py`. No harness path: the sabotage mutations are split out to L-0661 because `plugin/crew/tests/sabotage*.py` is harness and lands alone.

## Dependencies and work order

Must land first (all already on main):

| Ticket | State | Why |
|---|---|---|
| T-0023 | merged | The `PHRASES` table, the UserPromptSubmit route line and the route/ask/none outcomes this ticket extends. |
| T-0018 | merged | `crew_autopilot.route`, `SUBCOMMANDS` and `AVAILABLE`, which the new availability gate reads. |
| T-0004 | merged | `/crew:autopilot` itself. |
| T-0024 | merged | Owns plain-text approval; the reason no approve row is added. |
| T-0087 | merged | The tooling-PR rule that forces the sabotage mutations into their own PRs. |

Nothing unmerged blocks this ticket. It can be worked at any time.

Not blocking (a row asks softly until each lands, then routes with no change here):

| Ticket | State | Row it makes live |
|---|---|---|
| T-0019, and its follow-up L-0611 | in-progress; direction | `assign` |
| T-0012, and its split L-0541 | approved; direction | `goal` and `--goal` |
| T-0020 | approved | `focus` |
| T-0056 | ready | The goal slug resolver for "pick the goal back up"; until then that phrase always asks. |

This ticket blocks: L-0661, L-0662 and (through them) L-0663. T-0054 (ready), whose autopilot guide lists every plain-text phrase. T-0025 (approved) reads `PHRASES` for `/crew:help`; it is not hard-blocked but should plan against the new rule names.

Family order:

1. **T-0057** (this ticket): gate and five rows. Feature PR.
2. **L-0661**: sabotage mutations for step 1. Tooling-only PR. After T-0057.
3. **L-0662**: rows for wave, split, sleep, wake. Feature PR. After T-0057; independent of L-0661.
4. **L-0663**: sabotage mutations for step 3. Tooling-only PR. After L-0662 and L-0661 (same file).

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (this branch starts at `ce235468`); re-check each anchor.
- There is no plan.md and none is published. The implementing session writes the plan.
- "Has the command landed?" is read from `crew_autopilot.route` at decide time. The table holds no second copy of that fact.
- `sabotage_route.py` anchors exact strings in `crew_route.py`, and each must stay present exactly once. Three are easy to duplicate by accident; the spec's "Anchor constraint" paragraph names them. New rows go after the `status` row without rewrapping it.
- No edit to `plugin/crew/tests/sabotage*.py`, `crew_autopilot.py`, `crew_context.py`, `commands/autopilot.md` or `hooks.json` in this PR.
- If T-0019 lands first, re-read `autopilot.md` section 0 before planning (spec, Unknowns).
- direction.md carries two owner decisions from 2026-09-30 (catch up with main by merge, never rebase; run the suites under the heavy-run wrapper with 4 workers). The wrapper path is local and is redacted as `<local-tmp>/`; use whatever the cloud environment provides.
- Nothing was run when the spec was written: no pytest, sabotage or gate. Evidence lines were read only.

## Open questions for the owner (recommended option taken)

1. Free-text rows before their command lands: a soft "not available yet" line. Alternative: no line at all until T-0019 / T-0012 land. The soft line fires on every short "handle ..." or "take care of ..." prompt while `route.enabled` is true.
2. `assign` and `goal` phrases do not need the word "autopilot"; a bare pronoun as the work ("handle it") never routes. Alternative: require "have autopilot handle ...".
3. The 80-character prompt cap stays for assign and goal phrases. Alternative: raise it.
4. Bare "this is too big" is not a split phrase (L-0662). Alternative: make it a row.
5. "morning" and "I'm back" stay as wake phrases (L-0662); they produce nothing until T-0053 lands.
6. `sleep` by phrase without a configured schedule is allowed; T-0053 decides the behaviour.
7. The two autopilot status questions accept a trailing `?`, which no T-0023 row does. Allowed because status is read-only.
8. `focus` needs an explicit id; "focus on this" does not route. This differs slightly from T-0023's it/this convention.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/T-0057/` in the final PR unless the owner wants it kept.
