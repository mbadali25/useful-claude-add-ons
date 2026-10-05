# Cloud handoff: L-0530

**crew_tracker names an INDEX status crew does not know (and the crew word for a retired one) instead of reporting `expects None`**

Handed to a cloud session on 2026-10-05 by the orchestrator under the owner's standing self-approve authority.

**Reshaped.** The seed asked to map `merged`/`approved`/`new`/`land-blocked` to board lanes. The owner rule of 2026-10-05 (INDEX statuses are crew-known only; never `approved`, `merged`, `closed`, `new`, `parked`) rules that out, and the INDEX data was rewritten to crew words the same day (344 rows, all crew-known). What is left is the diagnostic: `read` still says `INDEX status X expects None` for a foreign word, and nothing names the crew word to use.

- **Role:** standalone ticket.
- **INDEX status:** spec (direction and spec approved for hand-off 2026-10-05; plan to be written by the implementing session)
- **Branch:** `L-0530-build`, new from origin/main `a555ff37`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0530/direction.md`, `docs/tickets/L-0530/spec.md`
- **Size:** about 20 production lines in `plugin/crew/hooks/scripts/crew_tracker.py`, about 8 tests, four doc files plus rebuilt guides.
- **Harness:** no. `crew_tracker.py` is in neither `HARNESS` nor `SEAM`. The sabotage entries the seed asked for touch `plugin/crew/tests/sabotage*.py` (harness), so they are a separate tooling-only follow-up.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0037 | merged (#394) | The ten-word vocabulary and the unknown-current `move` refusal this extends. |
| (follow-up, unminted) | - | Tooling-only sabotage entries for the new read branch and the text-only hint. Not blocking. |

This ticket blocks nothing.

## Read before writing code

- Hints are text only. `RETIRED_STATUSES` (approved -> spec, merged -> done, closed -> done, new -> direction, parked -> needs-owner) never adds a lane, a write or an exit code. `LANE_FOR_STATUS` is unchanged, and so is `test_the_new_words_are_table_rows`.
- `land-blocked` gets no hint: no owner decision maps it.
- An unknown INDEX status makes `read`'s `disagree` the string `"could not tell"`, not `True`. Say so in the CHANGELOG, because `--json` consumers see the field change type.
- `plugin/crew/` change: update every doc that describes the tracker vocabulary (obsidian-sync.md, README Ticket statuses, the memory-and-obsidian guide plus rebuilt outputs, `.crew/codemap/crew.md`) in the same PR, and bump the version files.
- Evidence anchors were checked at origin/main `a555ff37`; re-find by content if main has moved.
- No plan.md is published. The implementing session writes the plan.

## Open questions for the owner (recommended option taken)

The reshape itself: name the foreign word, don't map it. The alternatives were the seed's mapping (contradicts the 2026-10-05 rule) and closing as superseded (data is clean, but the misleading `expects None` stays). Smaller defaults are in direction.md: `disagree` becomes a could-not-tell string, the hint table sits beside `LANE_FOR_STATUS`, sabotage goes to a follow-up tooling PR, and jira/sdp are left alone.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0530/` in the final PR unless the owner wants it kept.
