# Cloud handoff: T-0067

**Autopilot fixes round-1 review findings itself: `autopilot.reviewPolicy` and the single-ticket fix phase**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** parent of a four-ticket family. Children: L-0666, L-0667, L-0668. This ticket is narrowed to the first slice (the `reviewPolicy` key and a fail-closed `fix` phase).
- **INDEX status:** ready, priority high (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `T-0067-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0067/direction.md`, `docs/tickets/T-0067/spec.md`
- **Size:** about 150 production lines (`crew_autopilot.py` about 110, `commands/autopilot.md` about 30, four config surfaces about 6). No harness path. `crew_autopilot.py` and `commands/autopilot.md` are seam paths, which count as feature work here; the sabotage mutations are split out to L-0668.

## Dependencies and work order

Must land first (all already on main):

| Ticket | State | Why |
|---|---|---|
| T-0004 | merged | `/crew:autopilot` and `crew_autopilot.py next`, which this extends. |
| T-0010 | merged | The policy pattern: could-not-tell reads `unknown` and never acts. |
| T-0018 | merged | `status` and the `WAITING` phase map, which gains the `fix` phase. |
| T-0008 | merged | The refresh check `_toward_review` uses after the fix. |
| L-0510 | done | Round rows carry the findings list; `check_follow_up`'s whole-line rule is reused; the final-round auto-accept stays as is. |
| T-0087 | merged | The tooling-PR rule that forces the sabotage mutations into their own PR. |

Nothing unmerged blocks this ticket. It can be worked at any time.

Where the INDEX title and the spec disagree, the spec wins: the INDEX title still says "depends on T-0029, T-0064". The spec says neither blocks this narrowed ticket.

| Ticket | State | Why it no longer blocks |
|---|---|---|
| T-0029 | in-progress, far behind main | It was to add `autopilot.reviewPolicy`. This ticket adds the key itself, with T-0029's name, values and default. T-0029 must read the key instead of adding it when it catches up. |
| T-0064 | approved, draft PR open | Needed only by L-0667 (`/crew:graph`). |

Related, same files, no order forced: T-0063 (approved), T-0070 (spec; should list `reviewPolicy`), L-0522 (in-progress), T-0074 (acts only at zero rounds left), T-0043 (rewords the same FINDINGS stop; whichever lands second re-reads it).

This ticket blocks: L-0666 (edits the same function), L-0668 (sabotage for this change), T-0073 (direction; names T-0067 as a dependency and should be re-read against L-0510 before it is specced), and T-0029 (its lane prompt should reuse this phase's fixes.md rule).

Family order:

1. **T-0067** (this ticket): the key and the `fix` phase. Feature PR.
2. **L-0666**: the stop-message contract. Feature PR. After T-0067.
3. **L-0668**: sabotage mutations for 1 and 2. Tooling-only PR. After T-0067 and L-0666.
4. **L-0667**: `/crew:graph`. Feature PR. Independent of 1 to 3; waits for T-0064 to merge.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (this branch starts at `ce235468`); re-check each anchor.
- There is no plan.md and none is published. The implementing session writes the plan.
- The default stays `stop`: autonomy is opt-in. `stop` and `clean-only` must behave exactly as main does today in a single-ticket run.
- Fail closed. The spec lists every condition that must return the existing `accept-review` stop. A config that cannot be read reads `unknown`, which never fixes.
- "INCOMPLETE twice" from the original direction is dropped: main carries a must-block sabotage rule against rerunning an INCOMPLETE round unattended. That branch stays as it is.
- The lines existing sabotage mutations anchor stay byte-identical. The spec's Exclusions name them. No edit to any harness path in this PR.
- CONFIG.md's leaf counts move by one. Re-measure them; do not edit the number by hand.
- Two Unknowns are resolved at plan time by a grep the spec gives (`status` under `policy=False`, and whether `crew_status.py` renders phases from a closed list). If the second is true, that file joins Touch by amendment before any edit.
- direction.md carries two owner decisions from 2026-09-30 (catch up with main by merge, never rebase; run the suites under the heavy-run wrapper with 4 workers). The wrapper path is local and is redacted as `<local-tmp>/`.
- Nothing was run when the spec was written: no pytest, gate or tracker command. Evidence is from reading origin/main.

## Open questions for the owner (recommended option taken)

1. `autopilot.reviewPolicy` is added by this ticket. Alternative: wait for T-0029 to add it.
2. An unrefunded INCOMPLETE round keeps stopping, as main's sabotage rule demands. Alternative: rerun it once under `fix-and-rereview`, as the original direction said.
3. Under `fix-and-rereview`, a round-1 BLOCK is fixed unattended like a FIX (round 2 still judges it). Alternative: a BLOCK always stops.
4. When the auto-accept guard passes but no receipt was written, the stop names only the owner's accept (L-0666). Alternative: autopilot finishes the auto-accept itself (would belong with T-0073).
5. `/crew:graph --refresh` waits for T-0064 to merge (L-0667). Alternative: ship first with a refusal naming T-0064.
6. `/crew:graph --refresh` never commits; the calling phase commits (L-0667). Alternative: it commits the pair itself.
7. Refresh hints name `/crew:graph --refresh`, with the raw command in a new `runs` field (L-0667). Alternative: keep naming the raw command.
8. direction.md was edited beyond an append: four mentions of another repository (its tag, a ticket id, and a line about what its graph build scanned) were made generic because these files are published. The owner's quoted words were otherwise kept. The owner is asked to confirm that is acceptable. A local wrapper path in the older owner-decision note is redacted in this published copy.
9. T-0073's direction predates L-0510's auto-accept and should be re-read against it before it is specced.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/T-0067/` in the final PR unless the owner wants it kept.
