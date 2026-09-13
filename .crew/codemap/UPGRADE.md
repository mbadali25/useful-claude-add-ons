# Upgrade report
status: upgraded
to schema: 5
graph build compared against: 0a21d21
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
- removed, not migrated: graph.obsidian. The code graph lives on the filesystem as `graph.json`; the Obsidian export was withdrawn in 0.16.13 because exporting one note per node made vaults unusably slow. Nothing to re-enable, and no setting was silently switched off.
- schema 3 -> 5, which added `install.policy`: what crew may do when a skill it needs is not installed. It arrives as `manual`, which is what crew already did — name the missing skill and the command, and run nothing. **Your machine did not start installing anything because you upgraded.** `ask` lets crew offer; `auto` lets it install without asking. Under every policy crew can only run a command from its own source, never one from a repo config or a skill file. Set it with `/crew:config` — nothing here chose anything but the floor for you.

## Contradictions — kept in the map, verify by hand
- none

## Added by the graph
- none

## Anchors left stale on purpose
- none

