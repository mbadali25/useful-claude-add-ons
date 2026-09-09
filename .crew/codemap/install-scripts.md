# install-scripts
anchor: useful-claude-add-ons@d61342c3
verified: 2026-09-06

## Does
`scripts/install-prerequisites.sh` (bash) and `scripts/install-prerequisites.ps1` (PowerShell) are
the same interactive installer for two operating systems: a checkbox picker over prerequisites, the
Claude CLI, MCP servers, and this repo's own skills and plugins. DERIVED. The delivery mechanism
differs per row and is *not* uniformly `claude plugin install`: plugins and skills go through
`claude plugin install` (`scripts/install-prerequisites.sh:383`), MCP servers through
`claude mcp add` (`scripts/install-prerequisites.sh:558`), and the standalone tools through their
own package managers (see **Calls out to**). DERIVED.

## Entry points
- `scripts/install-prerequisites.sh:720` - `MENU_KEYS`, the top-level picker's ordered key list;
  `MENU_DEFAULT` is the parallel tick list at `:727`. DERIVED. Run directly by a user on Linux,
  macOS or Git Bash.
- `scripts/install-prerequisites.ps1:750` - `$script:Catalog`, the Windows equivalent, carrying
  `Key` and `Default` on one line per row. Same 21 keys in the same order. DERIVED.
- `scripts/_test/drift-detection.sh:21` - sets `SCRIPT` to the real `.sh`; `:82` lifts
  `install_plugin` out of it with an `eval "$(awk ...)"` over the function body, so the
  update-detection path can be exercised without running the installer. DERIVED.
  (Previously cited as `:20`. Line 20 sets `REPO`, not `SCRIPT`.)

## Owns data

- Nothing of its own. It shells out to `claude plugin marketplace add` / `install` / `update`.
- Installed-plugin state is read **once** into `PLUGINS_CACHE` by `load_plugins`, whose
  `claude plugin list --json` call is at `scripts/install-prerequisites.sh:242` (PowerShell
  equivalent at `scripts/install-prerequisites.ps1:253`). DERIVED. `plugin_version`
  (`scripts/install-prerequisites.sh:258`) reads only that cache, never the CLI.
  (This was previously cited as `:626`, which is a `skip` call inside `install_plugin` and reaches
  no CLI at all.)
- The re-run fast path deliberately avoids the CLI: `install_plugin` compares the marketplace HEAD
  sha against the sha recorded for the installed copy (`scripts/install-prerequisites.sh:636-643`),
  two file reads instead of a process launch. DERIVED.
- The `claude-code-plugins` marketplace is no longer registered by either script. It carried only `frontend-design`, now sourced from `claude-plugins-official`.

## Calls out to

- The `claude` CLI: `claude plugin list --json` at `scripts/install-prerequisites.sh:242`,
  `claude plugin install` at `:383`, `claude plugin update` at `:666`, `claude mcp add` at `:558`.
  DERIVED.
- The tools it provisions - Playwright CLI, skillui, strix, graphify, Obsidian - each through its
  own package manager. For graphify that is `uv tool install graphifyy` at
  `scripts/install-prerequisites.sh:2324`, with `uv` itself bootstrapped via `pip3`/`pip` just
  above. DERIVED. (`:2307` was cited here previously; that line is the *idempotence* skip, not the
  install.)
- `https://knowledge-mcp.global.api.aws/mcp` and `https://learn.microsoft.com/api/mcp` — registered, not called by the installer. Both were probed live before being added and answered a real MCP `initialize`.
- `uvx awslabs.aws-pricing-mcp-server@latest`, recorded by `claude mcp add` rather than executed, which is why the `uv` check above has to happen first.

## Landmines
- **Matched pair, and confirmed in sync at this anchor - by mechanical diff, not by eye.**
  Skill catalogs: `scripts/install-prerequisites.sh:803-838` (`SKILL_KEYS` at `:803-811`,
  `SKILL_NAME` at `:812-838`) against `scripts/install-prerequisites.ps1:805-830`
  (`$script:SkillCatalog`) - 25 keys, same order, and the 25 description strings diff
  byte-identical. Plugin catalogs: `scripts/install-prerequisites.sh:852-863` (`PLUGIN_KEYS` at
  `:852-857`, `PLUGIN_NAME` at `:858-863`) against `scripts/install-prerequisites.ps1:843-846` (the
  four entries; `$script:PluginCatalog = @(` is `:842`, closing paren `:847`) - same four keys
  (`crew`, `gizmoduck`, `localgpu`, `obsidian-vault`), same order, descriptions diff identical.
  DERIVED. (The previous range `ps1:842-844` claimed to show four keys and spanned two of them.)
  Top-level menu: the 21 `MENU_KEYS` and the 21 `$script:Catalog` keys match in order, and
  `MENU_DEFAULT` (`sh:727`, eight `1`s then thirteen `0`s) matches the `Default` column
  entry-for-entry. DERIVED - all 21 diffed, not just `repo-plugins`.
  Top-level *names* legitimately differ where the platform differs: the `prereqs` row names apt
  packages and sudo on the `.sh` (`:729`) and Chocolatey and Administrator on the `.ps1` (`:751`).
  DERIVED. Do not "fix" that into agreement.

- **The parity checker guards keys, not text - so agreeing descriptions can be jointly wrong.**
  `check_group_parity` (`scripts/check-marketplace.py:233`) compares `SKILL_KEYS` / `TEAM_KEYS` /
  `COMMUNITY_KEYS` / `PLUGIN_KEYS` against their `.ps1` catalogs on **keys only**; the `Name`
  strings are never read. `check_menu_parity` (`scripts/check-marketplace.py:194`) compares
  `MENU_KEYS` against `$script:Catalog` keys and `MENU_DEFAULT` against the `Default` flags - again
  no descriptive text. DERIVED.
  Live consequence: both scripts advertise `crew - Virtual dev team: 11 agents, 21 commands` at
  `scripts/install-prerequisites.sh:859` / `scripts/install-prerequisites.ps1:843`; the counts on
  disk are 29 agents and 24 commands. They agree with each other, so the matched-pair rule passes
  and `check-marketplace.py` stays green on a figure that is wrong on both sides. Tracked in
  `TODO.md:381-392`. DERIVED.
  JUDGEMENT: "the pair is in sync" is a weaker statement than it reads. Sync is enforced;
  correctness of the description text is enforced by nothing.

- **Nothing may bypass `pick_fit` / `Format-PickerLine`** - `scripts/install-prerequisites.sh:1223`
  and `scripts/install-prerequisites.ps1:1062`. Clipping is degradation; a line that *wraps* throws
  off the cursor-up redraw count and smears the menu over what was above it. Every title, label and
  hint in `picker_draw` (`scripts/install-prerequisites.sh:1235`) and `Invoke-Picker`
  (`scripts/install-prerequisites.ps1:1071`) routes through one of the two - re-checked line by
  line, not taken from the comment. DERIVED.
  One line in each does **not** route through the clipper: the scroll indicator `showing N-M of T`
  (`scripts/install-prerequisites.sh:1271-1272`, `scripts/install-prerequisites.ps1:1140-1141`).
  Its content is bounded to roughly 22 characters and both scripts floor the window at 40 columns
  (`term_cols` at `scripts/install-prerequisites.sh:1150`, `if ($winW -lt 40) { $winW = 40 }` at
  `scripts/install-prerequisites.ps1:1105`), so it cannot wrap today. DERIVED.
  JUDGEMENT: route it anyway if that string ever grows - the bound is incidental, not enforced.
  The two clippers are **not** interchangeable: bash appends a one-character ellipsis and reserves
  1 (`scripts/install-prerequisites.sh:1229`); PowerShell appends three dots, reserves 3, and pads
  the result out to `Width` (`scripts/install-prerequisites.ps1:1067-1068`). The `.ps1` carries a
  comment recording that reserving 1 there returned `Width + 2`. Porting a change between them
  without accounting for that is the wrap this pair exists to prevent. DERIVED.

- **Idempotent on both sides, and both sides re-checked.** `install_plugin` reports
  `SKIP | already current` at `scripts/install-prerequisites.sh:643` when the marketplace sha
  matches the installed sha, and `SKIP | already installed` at `:626` on the separate `--no-update`
  branch. DERIVED - two different messages on two different branches, and
  `scripts/_test/drift-detection.sh` asserts both by name (`already current` at `:137` and `:157`,
  `already installed` at `:190`). The previous note cited `:626` for "already current"; that is the
  wrong branch, and the distinction is the whole point of the drift suite.
  Per-tool "already installed" branches: playwright-cli `sh:2089` / `ps1:1926`, skillui `sh:2133` /
  `ps1:1972`, strix `sh:2172` / `ps1:2014`, graphify `sh:2307` / `ps1:2179`, and the PowerShell
  `Install-ClaudePlugin` mirror at `ps1:648`, `:667`, `:676`. DERIVED - the `.ps1` citations are
  new; the previous note claimed "both sides" while citing only `.sh` lines.

- **The `repo-plugins` menu row defaults to OFF; the four plugins inside it are pre-ticked.**
  `MENU_DEFAULT` index 18 is `0` at `scripts/install-prerequisites.sh:727` against
  `Default = $false` at `scripts/install-prerequisites.ps1:769`, each carrying the same reasoning
  in a comment (`sh:849-850`, `ps1:838-839`) - a hook runs whether or not Claude agrees with it, so
  it is opted into explicitly. DERIVED. (`ps1:840` was inside the previous citation; that line
  documents the `Spec` string format, not the reasoning.)
  Precision that matters: the gate is the single outer row, which covers all four plugins - and by
  the scripts' own descriptions `gizmoduck` and `localgpu` register no hooks
  (`scripts/install-prerequisites.sh:860-861`). So the rule as implemented is "the row carrying
  plugins is off", not "hook-registering plugins are off". `PLUGIN_STATE` is all `1`
  (`scripts/install-prerequisites.sh:870-871`) and every `Selected` is `$true` (`ps1:843-846`), so
  the inner rows are pre-ticked and take effect only once the outer row is turned on. DERIVED.

- **`json_query` resolves `jq` then `python3` and nothing else, with stderr discarded.**
  `scripts/install-prerequisites.sh:164-176`. No `python` or `py` fallback, no warning when both
  back ends are missing, and both invocations carry `2>/dev/null`. DERIVED. CLAUDE.md's "Git Bash
  ships without `python3`" landmine lands squarely here: with neither `jq` nor `python3`,
  `json_query` returns 1, `PLUGINS_CACHE` stays empty (`:248`), `plugin_version` returns 1 for every
  name (`:260`), and `install_plugin` takes the fresh-install path for everything. DERIVED.
  JUDGEMENT: the failure direction is reinstall-everything rather than silently-skip, so it is loud
  and slow rather than wrong - but it is still an unknown collapsing into a value, and the user is
  told nothing. `setup_notify` does better, trying `python3` then `python` and warning on neither
  (`scripts/install-prerequisites.sh:1601-1603`) - still no `py`.

- **The `pwsh`-not-on-PATH landmine does not live here.** Neither script invokes `pwsh` or
  `powershell` as a subprocess - grepped both, zero hits. DERIVED. That one belongs to hook
  `command` configuration elsewhere in the repo, and attributing it to these files sends you looking
  in the wrong place.

## Unverified
- `scripts/_test/drift-detection.sh` was confirmed to drive the real `claude` CLI (`:62-64`, `:134`,
  `:154`, `:188`) and to self-skip when `claude` is absent (`:28`), so "CI cannot run it" is
  plausible - but CI's own skip behaviour was not inspected. Carried forward unchanged; the suite
  was **not executed** in this pass.
- Picker behaviour under redirected output was reasoned about from the width floors, not executed.
  `picker_supported` (`scripts/install-prerequisites.sh:1154`) refuses a non-tty, `TERM=dumb` and a
  window under 10 lines; the PowerShell side has no equivalent pre-flight and instead swallows a
  `CursorVisible` failure (`scripts/install-prerequisites.ps1:1098`). Whether
  `[Console]::WindowWidth` (`Get-PickerConsole`, `scripts/install-prerequisites.ps1:1042`) throws
  before that point in a redirected host was not tested.
- `scripts/check-marketplace.py` was read for `check_catalogs` (`:166`), `check_menu_parity`
  (`:194`) and `check_group_parity` (`:233`) only. The remaining checks in that file were not
  traced.
- The `ms-mcp` and `obsidian-mcp` install paths (`scripts/install-prerequisites.sh:2356` onward)
  were not read; nothing in this note depends on them.

## Re-anchor provenance
The per-path staleness check came back **empty**. `git diff --name-only a02331ee..HEAD` over this
note's cited paths - `scripts/install-prerequisites.sh`, `scripts/install-prerequisites.ps1`,
`scripts/_test/drift-detection.sh`, `scripts/check-marketplace.py` - lists no files, so by the
repo's usual signal this note was current and needed no work.

It was re-read anyway, and the empty diff turned out to be a **false clean bill**. Six citation
defects were present at the previous anchor - wrong when written, not drifted into. The expensive
one was `scripts/install-prerequisites.sh:626`, cited three times for three different claims (the
`claude` CLI call site, the `claude plugin list --json` read, and the `SKIP | already current`
message) and correct for none of them: it is a `skip` call on the `--no-update` branch, and the
message there is `already installed`. `git diff` cannot see a citation that never matched.

Re-read in full for this pass: `scripts/install-prerequisites.sh` lines 160-200, 236-275, 383, 558,
615-646, 715-772, 795-880, 1145-1175, 1223-1290, 1595-1612, 2085-2092, 2130-2136, 2169-2175,
2303-2345; `scripts/install-prerequisites.ps1` lines 745-775, 795-860, 1042-1150, plus the
`already installed` / `already current` branches at 648-728, 1926, 1972, 2014, 2179;
`scripts/_test/drift-detection.sh` lines 15-35, 58-68, 78-88, 130-138, 150-158, 185-192;
`scripts/check-marketplace.py` lines 166-262. Both key lists and both name lists were diffed
mechanically rather than compared by eye. `scripts/_test/drift-detection.sh` was not executed (it
drives the real `claude` CLI). Neither install script was modified.
