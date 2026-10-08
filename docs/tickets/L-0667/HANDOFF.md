# Cloud handoff: L-0667

**T-0067 child 2: `/crew:graph` - one command for graph status, the sanctioned refresh and queries**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

**Blocked: do not start before T-0064 has merged.** It adds the checker this command calls and edits the same function in `crew_refresh_check.py`.

- **Role:** child, split from T-0067, slice 2 of 3 (the family is T-0067, L-0666, L-0667, L-0668).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0667-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0667/direction.md`, `docs/tickets/L-0667/spec.md`
- **Size:** about 250 production lines (`crew_graph.py` about 170, `commands/graph.md` about 60, `crew_refresh_check.py` about 12, the rest about 8). No harness path. If `crew_graph.py` passes 200 lines at plan, the hint rename (the `runs` field) is cut to a follow-up rather than growing the PR past 300.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0064 | approved, draft PR open, not merged | Must be merged first: `crew_graph_ignore.coverage` and its edit to `_graph` in `crew_refresh_check.py`. |
| T-0008 | merged | The refresh check. |

This ticket does not depend on its parent T-0067 or on L-0666. All three edit `commands/autopilot.md`, so whichever lands later merges main in.

Related, no ordering: T-0063 (approved; edits `crew_refresh_check.py` too, whichever lands second re-reads).

This ticket blocks nothing.

Family order:

1. **T-0067**: the `reviewPolicy` key and the `fix` phase.
2. **L-0666**: the stop-message contract. After T-0067.
3. **L-0668**: sabotage mutations for 1 and 2. After both.
4. **L-0667** (this ticket): `/crew:graph`. Independent of 1 to 3; after T-0064.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`, except the T-0064 lines, which were read on its open branch. Main has moved since (this branch starts at `ce235468`). Re-read every anchor on the main that contains T-0064; its final shape may differ.
- There is no plan.md and none is published. The implementing session writes the plan.
- The line `    command = ("graphify update ." if info["reportTracked"]` in `crew_refresh_check.py` must stay byte-identical and present exactly once: a sabotage mutation anchors it and a feature PR may not edit a sabotage file. If that cannot hold, stop: the hint rename moves to a tooling follow-up and this ticket ships without it.
- The script never installs anything, never commits, pushes or stages, and never writes `.graphifyignore`.
- The pair check compares the report's Summary line with `len(graph["nodes"])` and `len(graph["links"])`. The key is `links`, not `edges`; a graph with `edges` and no `links` is could-not-tell (exit 2), never zero links.
- Adding a command moves the command count from 36 to 37 in every place the spec's Evidence lists, including both install scripts (a matched pair: same text, same place). Registration must be whole in one commit.
- After this merges, the root README's install URLs are re-pinned to the new commit SHA (a promotion step no script enforces).
- Tests use a fake `graphify` on PATH. None runs the real tool or touches this repo's `graphify-out/`.
- The spec's Unknowns give the grep that checks whether anything executes the artifact's `command` string as a shell line. If a script does, it reads `runs` instead and joins Touch by amendment.

## Open questions for the owner (recommended option taken)

1. `/crew:graph --refresh` waits for T-0064 to merge. Alternative: ship first with a refusal that names T-0064.
2. `/crew:graph --refresh` never commits; the phase that called it commits, like every other refresh. Alternative: it commits the pair itself.
3. The refresh hint names `/crew:graph --refresh`, with the raw command in a new `runs` field. Alternative: keep naming the raw command, and the command is only an entry point for people.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0667/` in the final PR unless the owner wants it kept.
