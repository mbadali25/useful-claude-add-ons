---
paths:
  - "scripts/**"
  - "plugin/PLUGINS.md"
---
<!-- crew:generated source=.crew/codemap/marketplace-registration.md sha256=9b7e13eca098064c -- do not hand-edit; regenerate with crew_instructions.py rules -->
# marketplace-registration
Code map anchor `5d1fc5fd`; if it is behind HEAD, re-check with `git diff --name-only 5d1fc5fd..HEAD -- <cited paths>`.
Covers: The marketplace itself: what registers a skill vs. a plugin, the two install scripts, and the two separate version-check paths (check-marketplace.py vs. _verify/smoke.sh).
## Entry points
- `.claude-plugin/marketplace.json` — 36 skills and 5 plugins, 41 entries (re-counts unchanged in this range).
- `scripts/check-marketplace.py:301` — `check_catalogs` (unchanged position since `84976536`), which requires `SKILL_KEYS` (.sh) and `$script:SkillCatalog` (.ps1) to match marketplace.json in the same ORDER, not merely...
- `scripts/check-marketplace.py:383` — `check_group_parity` (unchanged position), which hardcodes exactly four sub-picker groups.
- `scripts/check-marketplace.py:472` — `version_set_at` (unchanged position), the git walk that makes the version rule history-based, and therefore un-runnable against an uncommitted change.
- `scripts/check-marketplace.py:649` (moved from `:579` at `84976536`) — `check_self_claims`, body `:649-830`; `count_plugin_skills` (`:563-577`, moved from `:562-576`) is its counting helper, and `count_plugin_commands...
- `scripts/check-marketplace.py:867` and `:1030` — new at this anchor, absent at `84976536`: `check_description_claims` (table `DESCRIPTION_CLAIMS` at `:853-855`) and `check_catalog_claims` (table `CATALOG_CLAIMS` at `:...
- `scripts/check-marketplace.py:1321` (moved from `:929`) — `check_crew_ignore_policy`, added by `0a9d8937` #161: asserts the `.crew/` ignore un-ignore list is one set stated consistently across `.gitignore` and five ot...
- Four checks were new at the `84976536` pass: `check_argument_hint_frontmatter` (`:176`, unchanged), `check_license_consistency` (`:268`, unchanged), `check_command_backtick_spans` (moved `:1094` -> `:1486`) and `check...
- `scripts/check-marketplace.py:1588` (moved from `:1196`) — `main()`, body `:1588-1623` (was `:1196-1229`), calling all sixteen checks (was fourteen) at `:1597-1612` (was `:1205-1218`).
- `.crew/verify.json:50`, `:67` and `:75` — still three invocations of `python3 scripts/check-marketplace.py` from the tracked verification map; position unchanged in this range (the file's two-line diff in this range i...
Full note: `.crew/codemap/marketplace-registration.md`.
