# Upgrade report
status: upgraded
to schema: 7
graph build compared against: 0dedb4b
  (not an anchor: this file is a one-time report, not a subsystem map,
   and nothing re-verifies it. The sha records what this run read; it
   may not resolve later, and a squash merge is enough to kill it.)

Nothing below was applied automatically. Conflicts are the map and
the graph disagreeing, and either can be wrong: the graph misses
generated call sites, reflection, and dynamic dispatch.

## Config
- roles added: none
- tier: 2 (unchanged)
- roles are added only up to the tier this config already declares. Moving UP a tier is `/crew:scale`; removing a role is `/crew:pm offboard`, which still stops for an explicit yes.

## Contradictions — kept in the map, verify by hand
- none

## Added by the graph
- none

## Anchors left stale on purpose
- none

