# Upgrade report
status: upgraded
to schema: 3
graph anchor: abe639c

Nothing below was applied automatically. Conflicts are the map and
the graph disagreeing, and either can be wrong: the graph misses
generated call sites, reflection, and dynamic dispatch.

## Config
- roles added: security, smoke-author, dba, browser-tester, analyst, infrastructure-architect, scribe, researcher
- tier: 2 (unchanged)
- roles are added only up to the tier this config already declares. Moving UP a tier is `/crew:scale`; removing a role is `/crew:pm offboard`, which still stops for an explicit yes.
- schema 2 -> 3, which added the per-role provider table and a declared fallback: qa.fallback, qa.roles, dev.fallback, dev.roles. Both arrive NEUTRAL — `qa.roles` and `dev.roles` are empty, so every role still runs on its block's own `provider`, and `fallback` only fires when a pinned model has been retired, which used to be a plain error. This repo dispatches exactly as it did before the upgrade. To pin a model per role, run `/crew:model` — nothing here chose one for you.

## Contradictions — kept in the map, verify by hand
- none

## Added by the graph
- none

## Anchors left stale on purpose
- none

