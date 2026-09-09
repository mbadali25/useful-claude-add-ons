# Upgrade report
status: upgraded
to schema: 3
graph anchor: d61342c

Nothing below was applied automatically. Conflicts are the map and
the graph disagreeing, and either can be wrong: the graph misses
generated call sites, reflection, and dynamic dispatch.

## Config
- roles added: smoke-author, dba, browser-tester, analyst, planner, infrastructure-architect, scribe, researcher
- tier: 2 (unchanged)
- roles are added only up to the tier this config already declares. Moving UP a tier is `/crew:scale`; removing a role is `/crew:pm offboard`, which still stops for an explicit yes.
- removed, not migrated: graph.obsidian. The code graph lives on the filesystem as `graph.json`; the Obsidian export was withdrawn in 0.16.13 because exporting one note per node made vaults unusably slow. Nothing to re-enable, and no setting was silently switched off.

## Contradictions — kept in the map, verify by hand
- Entry points: `.sh` is in the map but not in the graph - kept, verify by hand
- Entry points: `Default` is in the map but not in the graph - kept, verify by hand
- Entry points: `Key` is in the map but not in the graph - kept, verify by hand
- Entry points: `MENU_DEFAULT` is in the map but not in the graph - kept, verify by hand
- Entry points: `REPO` is in the map but not in the graph - kept, verify by hand
- Entry points: `SCRIPT` is in the map but not in the graph - kept, verify by hand
- Entry points: `eval "$(awk ...)"` is in the map but not in the graph - kept, verify by hand
- Entry points: `install_plugin` is in the map but not in the graph - kept, verify by hand
- Entry points: `scripts/_test/drift-detection.sh` is in the map but not in the graph - kept, verify by hand
- Owns data: `` is in the map but not in the graph - kept, verify by hand
- Owns data: `PLUGINS_CACHE` is in the map but not in the graph - kept, verify by hand
- Owns data: `claude plugin list --json` is in the map but not in the graph - kept, verify by hand
- Owns data: `claude plugin marketplace add` is in the map but not in the graph - kept, verify by hand
- Owns data: `install` is in the map but not in the graph - kept, verify by hand
- Owns data: `install_plugin` is in the map but not in the graph - kept, verify by hand
- Owns data: `load_plugins` is in the map but not in the graph - kept, verify by hand
- Owns data: `plugin_version` is in the map but not in the graph - kept, verify by hand
- Owns data: `scripts/install-prerequisites.ps1` is in the map but not in the graph - kept, verify by hand
- Owns data: `scripts/install-prerequisites.sh:636-643` is in the map but not in the graph - kept, verify by hand
- Owns data: `skip` is in the map but not in the graph - kept, verify by hand
- Owns data: `update` is in the map but not in the graph - kept, verify by hand
- Calls out to: `` is in the map but not in the graph - kept, verify by hand
- Calls out to: `claude` is in the map but not in the graph - kept, verify by hand
- Calls out to: `claude plugin install` is in the map but not in the graph - kept, verify by hand
- Calls out to: `claude plugin list --json` is in the map but not in the graph - kept, verify by hand
- Calls out to: `claude plugin update` is in the map but not in the graph - kept, verify by hand
- Calls out to: `pip` is in the map but not in the graph - kept, verify by hand
- Calls out to: `pip3` is in the map but not in the graph - kept, verify by hand
- Calls out to: `scripts/install-prerequisites.sh` is in the map but not in the graph - kept, verify by hand
- Calls out to: `uv tool install graphifyy` is in the map but not in the graph - kept, verify by hand
- Entry points: `%% Anchors: <paths>` is in the map but not in the graph - kept, verify by hand
- Entry points: `%% anchor: useful-claude-add-ons@<sha>` is in the map but not in the graph - kept, verify by hand
- Entry points: `/crew:handoff` is in the map but not in the graph - kept, verify by hand
- Entry points: `1f97e51c` is in the map but not in the graph - kept, verify by hand
- Entry points: `check-marketplace.py` is in the map but not in the graph - kept, verify by hand
- Entry points: `data-flow.mmd:1-2` is in the map but not in the graph - kept, verify by hand
- Entry points: `docs/HANDOFF.md:1-5` is in the map but not in the graph - kept, verify by hand
- Entry points: `docs/diagrams/architecture.mmd:1-2` is in the map but not in the graph - kept, verify by hand
- Entry points: `docs/remaining-setup.md:1-6` is in the map but not in the graph - kept, verify by hand
- Entry points: `docs/runbooks/rollback.md:9-14` is in the map but not in the graph - kept, verify by hand
- Entry points: `last verified: 2026-09-05` is in the map but not in the graph - kept, verify by hand
- Entry points: `main` is in the map but not in the graph - kept, verify by hand
- Entry points: `process.mmd:1-2` is in the map but not in the graph - kept, verify by hand
- Entry points: `version` is in the map but not in the graph - kept, verify by hand
- Owns data: `` is in the map but not in the graph - kept, verify by hand
- Owns data: `*.png` is in the map but not in the graph - kept, verify by hand
- Owns data: `.gitignore` is in the map but not in the graph - kept, verify by hand
- Owns data: `.mmd` is in the map but not in the graph - kept, verify by hand
- Owns data: `docs/` is in the map but not in the graph - kept, verify by hand
- Owns data: `docs/diagrams/out/*.svg` is in the map but not in the graph - kept, verify by hand
- Owns data: `docs/superpowers` is in the map but not in the graph - kept, verify by hand
- Owns data: `docs/superpowers/` is in the map but not in the graph - kept, verify by hand
- Owns data: `git ls-files docs/diagrams/` is in the map but not in the graph - kept, verify by hand
- Owns data: `mmdc` is in the map but not in the graph - kept, verify by hand
- Owns data: `out/` is in the map but not in the graph - kept, verify by hand
- Owns data: `plans/` is in the map but not in the graph - kept, verify by hand
- Owns data: `plugin/crew/skills/crew-diagrams/scripts/render.sh` is in the map but not in the graph - kept, verify by hand
- Owns data: `specs/` is in the map but not in the graph - kept, verify by hand
- Calls out to: `` is in the map but not in the graph - kept, verify by hand
- Calls out to: `-s 2` is in the map but not in the graph - kept, verify by hand
- Calls out to: `mmdc` is in the map but not in the graph - kept, verify by hand
- Calls out to: `plugin/crew/skills/crew-diagrams/scripts/render.sh` is in the map but not in the graph - kept, verify by hand

## Added by the graph
- crew: 9 new line(s)
- install-scripts: 3 new line(s)
- marketplace-registration: 5 new line(s)
- repo-docs: 4 new line(s)
- verification-harness: 5 new line(s)

## Anchors left stale on purpose
- none

