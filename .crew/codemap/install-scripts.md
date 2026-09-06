# install-scripts
anchor: useful-claude-add-ons@a02331ee
verified: 2026-09-06

## Does
`scripts/install-prerequisites.sh` (bash) and `scripts/install-prerequisites.ps1` (PowerShell) are
the same interactive installer for two operating systems: a checkbox picker over prerequisites, the
Claude CLI, MCP servers, and this repo's own skills and plugins, each installed or skipped through
`claude plugin install`.

## Entry points
- `scripts/install-prerequisites.sh:720` - `MENU_KEYS` / `MENU_DEFAULT` drive the top-level picker.
  Run directly by a user on Linux, macOS or Git Bash.
- `scripts/install-prerequisites.ps1:750` - `$script:Catalog`, the Windows equivalent, same keys in
  the same order.
- `scripts/_test/drift-detection.sh:20` - lifts `install_plugin` out of the real `.sh` via
  `eval "$(awk ...)"` (`:82`) so the update-detection path can be tested in isolation.

## Owns data
- Nothing of its own. It shells out to `claude plugin marketplace add` / `install` / `update` and
  reads `claude plugin list --json` before deciding to install, skip or update
  (`scripts/install-prerequisites.sh:626`).

## Calls out to
- The `claude` CLI, at `scripts/install-prerequisites.sh:626`.
- The tools it provisions - Playwright CLI, skillui, strix, graphify, Obsidian - each through its
  own package manager, e.g. `scripts/install-prerequisites.sh:2307` for graphify.

## Landmines
- **Matched pair, and confirmed in sync at this anchor.** Skill catalogs:
  `scripts/install-prerequisites.sh:803-838` (`SKILL_KEYS` / `SKILL_NAME`) against
  `scripts/install-prerequisites.ps1:805-830` (`$script:SkillCatalog`) - same keys, same order,
  same description text. Plugin catalogs: `scripts/install-prerequisites.sh:852-863` against
  `scripts/install-prerequisites.ps1:842-844` - same four keys (`crew`, `gizmoduck`, `localgpu`,
  `obsidian-vault`), same order, same text. Changing one without the other is the failure this
  pairing exists to prevent.
- **Nothing may bypass `pick_fit` / `Format-PickerLine`** - `scripts/install-prerequisites.sh:1223`
  and `scripts/install-prerequisites.ps1:1062`. Clipping is degradation; a line that *wraps* throws
  off the cursor-up redraw count and smears the menu over what was above it. Every title, label and
  hint in `picker_draw` (`scripts/install-prerequisites.sh:1235`) and `Invoke-Picker`
  (`scripts/install-prerequisites.ps1:1071`) was confirmed to route through one of the two - checked,
  not taken from the comment.
- **Idempotent on both sides.** `install_plugin` reports `SKIP | already current` rather than
  reinstalling (`scripts/install-prerequisites.sh:626`), and the same "already installed" branch
  repeats for playwright-cli (`:2089`), skillui (`:2133`), strix (`:2172`) and graphify (`:2307`).
- **Plugins registering a hook default to OFF**, on both sides: `MENU_DEFAULT[18]=0` at
  `scripts/install-prerequisites.sh:727` against `Default = $false` at
  `scripts/install-prerequisites.ps1:769`, each carrying the same reasoning in a comment
  (`sh:849-850`, `ps1:838-840`). The inner plugin rows are pre-ticked, which only takes effect once
  that outer row is turned on.
- **The `pwsh`-not-on-PATH landmine does not live here.** Neither script invokes `pwsh` or
  `powershell` as a subprocess. That one belongs to hook `command` configuration elsewhere in the
  repo, and attributing it to these files sends you looking in the wrong place.

## Unverified
- `term_cols()` / `Get-PickerConsole`, the width sources `pick_fit` and `Format-PickerLine` consume,
  were not traced for redirected output or very narrow terminals.
- All 21 `MENU_DEFAULT` values were not diffed entry-by-entry against `$script:Catalog`'s `Default`
  fields; only the `repo-plugins` row was checked.
- `check_menu_parity` / `check_group_parity` in `scripts/check-marketplace.py` - the automated check
  that would catch future drift between these catalogs - were read but not traced line by line.
- `scripts/_test/drift-detection.sh` was confirmed to drive the real `claude` CLI (`:62-64`, `:134`,
  `:154`, `:188`) and to self-skip when `claude` is absent (`:28`), so "CI cannot run it" is
  plausible - but CI's own skip behaviour was not inspected.
