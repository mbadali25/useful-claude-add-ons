# install-scripts
anchor: useful-claude-add-ons@7b0d8f3a
verified: 2026-09-12
re-verified, not re-derived: every claim below was re-read against the files it
cites at this anchor and its citation re-pointed where the code had moved. The
claims themselves are the previous pass's, not a fresh derivation.

## Does
`scripts/install-prerequisites.sh` (bash) and `scripts/install-prerequisites.ps1` (PowerShell) are
the same interactive installer for two operating systems: a checkbox picker over prerequisites, the
Claude CLI, MCP servers, and this repo's own skills and plugins. DERIVED. The delivery mechanism
differs per row and is *not* uniformly `claude plugin install`: plugins and skills go through
`claude plugin install` (`scripts/install-prerequisites.sh:383`), MCP servers through
`claude mcp add` (`scripts/install-prerequisites.sh:558`), and the standalone tools through their
own package managers (see **Calls out to**). DERIVED.

## Entry points
- `scripts/install-prerequisites.sh:720-727` - `MENU_KEYS`, the top-level picker's ordered key
  list, now **24** keys; `MENU_DEFAULT` is the parallel tick list at `:728`. DERIVED. Run directly by a user on Linux,
  macOS or Git Bash.
- `scripts/install-prerequisites.ps1:750-775` - `$script:Catalog`, the Windows equivalent,
  carrying `Key` and `Default` on one line per row. Same 24 keys in the same order. DERIVED.
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
  `scripts/install-prerequisites.sh:2429`, with `uv` itself bootstrapped via `pip3`/`pip` just
  above. DERIVED. (`:2307` was cited here previously; that line is the *idempotence* skip, not the
  install - and it is now `:2412`.)
- `https://knowledge-mcp.global.api.aws/mcp` and `https://learn.microsoft.com/api/mcp` — registered, not called by the installer. Both were probed live before being added and answered a real MCP `initialize`.
- `uvx awslabs.aws-pricing-mcp-server@latest`, recorded by `claude mcp add` rather than executed, which is why the `uv` check above has to happen first.

## Landmines
- **Matched pair, and confirmed in sync at this anchor - by mechanical diff, not by eye.**
  Skill catalogs: `scripts/install-prerequisites.sh:807-878` (`SKILL_KEYS` at `:807-842`,
  `SKILL_NAME` at `:843-878`) against `scripts/install-prerequisites.ps1:808-843`
  (`$script:SkillCatalog`) - **34** keys, same order, and the 34 description strings diff
  byte-identical. Plugin catalogs: `scripts/install-prerequisites.sh:892-903` (`PLUGIN_KEYS` at
  `:892-897`, `PLUGIN_NAME` at `:898-903`) against `scripts/install-prerequisites.ps1:855-858` (the
  four entries; `$script:PluginCatalog = @(` is `:854`, closing paren `:859`) - same four keys
  (`crew`, `gizmoduck`, `localgpu`, `obsidian-vault`), same order, descriptions diff identical.
  DERIVED. (The previous range `ps1:842-844` claimed to show four keys and spanned two of them.)
  Top-level menu: the 24 `MENU_KEYS` and the 24 `$script:Catalog` keys match in order, and
  `MENU_DEFAULT` (`scripts/install-prerequisites.sh:728`, eight `1`s then sixteen `0`s) matches the
  `Default` column entry-for-entry. DERIVED - all 24 diffed, not just `repo-plugins`.
  The counts 21 -> 24 and 25 -> 34 are the re-verification's own finding: the previous pass
  recorded 21 menu rows and 25 skills, and both lists have since grown. The *claim* - that the two
  sides agree entry-for-entry - still holds at the new sizes.
  Top-level *names* legitimately differ where the platform differs: the `prereqs` row names apt
  packages and sudo on the `.sh` (`:730`) and Chocolatey and Administrator on the `.ps1` (`:751`).
  DERIVED. Do not "fix" that into agreement.

- **The parity checker guards keys, not text - so agreeing descriptions can be jointly wrong.**
  `check_group_parity` (`scripts/check-marketplace.py:233`) compares `SKILL_KEYS` / `TEAM_KEYS` /
  `COMMUNITY_KEYS` / `PLUGIN_KEYS` against their `.ps1` catalogs on **keys only**; the `Name`
  strings are never read. `check_menu_parity` (`scripts/check-marketplace.py:194`) compares
  `MENU_KEYS` against `$script:Catalog` keys and `MENU_DEFAULT` against the `Default` flags - again
  no descriptive text. DERIVED.
  Live consequence: both scripts advertise `crew - Virtual dev team: 11 agents, 21 commands` at
  `scripts/install-prerequisites.sh:899` / `scripts/install-prerequisites.ps1:855`; the counts on
  disk are **54 agents and 24 commands**. They agree with each other, so the matched-pair rule
  passes and `check-marketplace.py` stays green on a figure that is wrong on both sides. Tracked in
  `TODO.md:564-580`. DERIVED.
  Re-verification finding: that TODO entry records the gap as `29 agents, 24 commands`, which was
  true when it was written and is not true now - `ls plugin/crew/agents/*.md` counts 54. So the
  *correction* has itself gone stale while the thing it corrects has not moved at all. The
  advertised `11 agents` has been wrong continuously; only the size of the error changed.
  JUDGEMENT: "the pair is in sync" is a weaker statement than it reads. Sync is enforced;
  correctness of the description text is enforced by nothing.

- **Nothing may bypass `pick_fit` / `Format-PickerLine`** - `scripts/install-prerequisites.sh:1268`
  and `scripts/install-prerequisites.ps1:1076`. Clipping is degradation; a line that *wraps* throws
  off the cursor-up redraw count and smears the menu over what was above it. Every title, label and
  hint in `picker_draw` (`scripts/install-prerequisites.sh:1280`) and `Invoke-Picker`
  (`scripts/install-prerequisites.ps1:1085`) routes through one of the two - re-checked line by
  line, not taken from the comment. DERIVED.
  One line in each does **not** route through the clipper: the scroll indicator `showing N-M of T`
  (`scripts/install-prerequisites.sh:1316-1317`, `scripts/install-prerequisites.ps1:1154-1155`).
  Its content is bounded to roughly 22 characters and both scripts floor the window at 40 columns
  (`term_cols` at `scripts/install-prerequisites.sh:1195`, `if ($winW -lt 40) { $winW = 40 }` at
  `scripts/install-prerequisites.ps1:1119`), so it cannot wrap today. DERIVED.
  JUDGEMENT: route it anyway if that string ever grows - the bound is incidental, not enforced.
  The two clippers are **not** interchangeable: bash appends a one-character ellipsis and reserves
  1 (`scripts/install-prerequisites.sh:1274`); PowerShell appends three dots, reserves 3, and pads
  the result out to `Width` (`scripts/install-prerequisites.ps1:1081-1082`). The `.ps1` carries a
  comment recording that reserving 1 there returned `Width + 2`. Porting a change between them
  without accounting for that is the wrap this pair exists to prevent. DERIVED.

- **Idempotent on both sides, and both sides re-checked.** `install_plugin` reports
  `SKIP | already current` at `scripts/install-prerequisites.sh:643` when the marketplace sha
  matches the installed sha, and `SKIP | already installed` at `:626` on the separate `--no-update`
  branch. DERIVED - two different messages on two different branches, and
  `scripts/_test/drift-detection.sh` asserts both by name (`already current` at `:137` and `:157`,
  `already installed` at `:190`). The previous note cited `:626` for "already current"; that is the
  wrong branch, and the distinction is the whole point of the drift suite.
  Per-tool "already installed" branches, all repo-relative because `sh:`/`ps1:` shorthand cannot
  be pasted into `git diff` and this note cites four different `.sh` files:
  playwright-cli `scripts/install-prerequisites.sh:2194` / `scripts/install-prerequisites.ps1:1994`,
  skillui `scripts/install-prerequisites.sh:2238` / `scripts/install-prerequisites.ps1:2040`,
  strix `scripts/install-prerequisites.sh:2277` / `scripts/install-prerequisites.ps1:2082`,
  graphify `scripts/install-prerequisites.sh:2412` / `scripts/install-prerequisites.ps1:2247`,
  and the PowerShell `Install-ClaudePlugin` mirror at `scripts/install-prerequisites.ps1:648`,
  `:667`, `:676`. DERIVED - the `.ps1` citations are new; the previous note claimed "both sides"
  while citing only `.sh` lines.

- **The `repo-plugins` menu row defaults to OFF; the four plugins inside it are pre-ticked.**
  `MENU_DEFAULT` index 18 is `0` at `scripts/install-prerequisites.sh:728` against
  `Default = $false` at `scripts/install-prerequisites.ps1:769`, each carrying the same reasoning
  in a comment (`scripts/install-prerequisites.sh:889-890`,
  `scripts/install-prerequisites.ps1:851-852`) - a hook runs whether or not Claude agrees with it,
  so it is opted into explicitly. DERIVED. Index 18 was re-counted against the current 24-key
  `MENU_KEYS` rather than carried over, because the list grew: `repo-plugins` is still index 18.
  Precision that matters: the gate is the single outer row, which covers all four plugins - and by
  the scripts' own descriptions `gizmoduck` and `localgpu` register no hooks
  (`scripts/install-prerequisites.sh:900-901`). So the rule as implemented is "the row carrying
  plugins is off", not "hook-registering plugins are off". `PLUGIN_STATE` is all `1`
  (`scripts/install-prerequisites.sh:910-911`) and every `Selected` is `$true`
  (`scripts/install-prerequisites.ps1:855-858`), so
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
  (`scripts/install-prerequisites.sh:1646-1648`) - still no `py`. Note the function at `:1601` is
  `notify_prereqs`; `setup_notify` itself begins at `:1642`.

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
  `picker_supported` (`scripts/install-prerequisites.sh:1199`) refuses a non-tty, `TERM=dumb` and a
  window under 10 lines; the PowerShell side has no equivalent pre-flight and instead swallows a
  `CursorVisible` failure (`scripts/install-prerequisites.ps1:1112`). Whether
  `[Console]::WindowWidth` (`Get-PickerConsole`, `scripts/install-prerequisites.ps1:1056`) throws
  before that point in a redirected host was not tested.
- `scripts/check-marketplace.py` was read for `check_catalogs` (`:166`), `check_menu_parity`
  (`:194`) and `check_group_parity` (`:233`) only. The remaining checks in that file were not
  traced.
- The `ms-mcp` and `obsidian-mcp` install paths (`scripts/install-prerequisites.sh:2461` onward)
  were not read; nothing in this note depends on them.

## Re-anchor provenance

**This pass re-verified; it did not re-derive.** Every claim above is the previous pass's. What
changed is the citations: each was re-read against the file it names, and re-pointed where the code
had moved. Four counts were corrected because the underlying lists grew. No claim was added, and
none was removed.

The previous anchor, `useful-claude-add-ons@d61342c3`, **does not resolve in this repository** -
`git cat-file -e d61342c3^{commit}` fails. So `git diff --name-only <anchor>..HEAD -- <cited paths>`,
which is the entire re-verification mechanism, could not run at all. The anchor was written by
`519754fa` ("crew 0.16.28: fix the codemap anchor writer, and refresh five subsystems (#82)"), a
**squash** merge - and a squash discards the branch commit, so the sha the writer recorded died with
the branch. Fixed for future passes in crew 0.19.13: the writer now records
`git merge-base HEAD origin/main`, a commit that is already on the trunk and survives the squash.

Because the anchor could not be used, the citations were re-pointed mechanically instead: the two
install scripts were aligned between revisions with `difflib`, and every cited line was mapped by
**content** - the text at the old line had to equal the text at the new one, or the citation was
set aside for a full re-read rather than renumbered. Two lines failed that test and were re-read:
`MENU_DEFAULT` (the array grew from 21 entries to 24) and the `.ps1` skill catalog (25 -> 34).

That alignment also settled where these claims actually came from, and the answer is **not** the
recorded anchor. Every citation in this note matches `0131d0f0` (2026-09-05) exactly, and none
matches `519754fa` (2026-09-09), where the same lines already sat 73 (`.sh`) and 62 (`.ps1`) lines
further down. The note's own `verified: 2026-09-06` line was the honest record; the anchor was
three days and two commits ahead of the evidence. This is the tree-moved-under-the-measurement trap
recorded in `TODO.md`, and it is worth naming precisely: the anchor was not merely unresolvable, it
was never the commit the claims were true of. A resolvable-but-wrong anchor would have produced a
confident, empty `git diff` - a clean bill of health for citations that were already off by 73
lines.

Not executed in this pass: `scripts/_test/drift-detection.sh` (it drives the real `claude` CLI).
Neither install script was modified.
