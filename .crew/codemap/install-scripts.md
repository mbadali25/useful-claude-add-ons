# install-scripts
anchor: useful-claude-add-ons@a573ca24
verified: 2026-09-13
re-verified, not re-derived: every claim below was re-read against the files it
cites at this anchor and its citation re-pointed where the code had moved. Three
claims were re-measured and had gone false, and are corrected in place rather
than carried forward.

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
  list, **24** keys; `MENU_DEFAULT` is the parallel tick list at `:728`, also 24. DERIVED. Run
  directly by a user on Linux, macOS or Git Bash.
- `scripts/install-prerequisites.ps1:750-775` - `$script:Catalog`, the Windows equivalent,
  carrying `Key` and `Default` on one line per row. Same 24 keys in the same order. DERIVED.
- `scripts/_test/drift-detection.sh:21` - sets `SCRIPT` to the real `.sh`; `:82` lifts
  `install_plugin` out of it with an `eval "$(awk ...)"` over the function body, so the
  update-detection path can be exercised without running the installer. DERIVED, and closed by the
  per-path check: that file has not changed since the previous anchor.

## Owns data

- Nothing of its own. It shells out to `claude plugin marketplace add` / `install` / `update`.
- Installed-plugin state is read **once** into `PLUGINS_CACHE` by `load_plugins`
  (`scripts/install-prerequisites.sh:238-256`), whose `claude plugin list --json` call is at
  `scripts/install-prerequisites.sh:242` (PowerShell equivalent at
  `scripts/install-prerequisites.ps1:253`). DERIVED. `plugin_version`
  (`scripts/install-prerequisites.sh:258`) reads only that cache, never the CLI.
- The re-run fast path deliberately avoids the CLI: `install_plugin`
  (`scripts/install-prerequisites.sh:615`) compares the marketplace HEAD sha against the sha
  recorded for the installed copy (`scripts/install-prerequisites.sh:636-643`), two file reads
  instead of a process launch. DERIVED.
- The `claude-code-plugins` marketplace is no longer registered by either script. It carried only `frontend-design`, now sourced from `claude-plugins-official`.

## Calls out to

- The `claude` CLI: `claude plugin list --json` at `scripts/install-prerequisites.sh:242`,
  `claude plugin install` at `:383`, `claude plugin update` at `:666`, `claude mcp add` at `:558`.
  DERIVED.
- The tools it provisions - Playwright CLI, skillui, strix, graphify, Obsidian - each through its
  own package manager. For graphify that is `uv tool install graphifyy` at
  `scripts/install-prerequisites.sh:2432`, with `uv` itself bootstrapped via `pip3`/`pip` just
  above. DERIVED. The idempotence skip is `:2415`, not the install - a distinction two earlier
  passes got wrong in both directions, and both line numbers moved by three in this range.
- `https://knowledge-mcp.global.api.aws/mcp` and `https://learn.microsoft.com/api/mcp` — registered, not called by the installer. Both were probed live before being added and answered a real MCP `initialize`.
- `uvx awslabs.aws-pricing-mcp-server@latest`, recorded by `claude mcp add` rather than executed, which is why the `uv` check above has to happen first.

## Landmines
- **Matched pair, and confirmed in sync at this anchor - by mechanical diff, not by eye.**
  Skill catalogs: `scripts/install-prerequisites.sh:807-878` (`SKILL_KEYS` at `:807-842`,
  `SKILL_NAME` at `:843-878`) against `scripts/install-prerequisites.ps1:808-843`
  (`$script:SkillCatalog`) - **34** keys, same order, and the 34 description strings compare
  equal element-for-element. Plugin catalogs: `scripts/install-prerequisites.sh:892-905`
  (`PLUGIN_KEYS` at `:892-898`, `PLUGIN_NAME` at `:899-905`) against
  `scripts/install-prerequisites.ps1:854-860` (`$script:PluginCatalog`, the five entries at
  `:855-859`) - **five** keys now, same order (`crew`, `gizmoduck`, `localgpu`, `obsidian-vault`,
  `rule-of-two`), descriptions equal element-for-element. DERIVED by parsing both files and
  comparing lists, not by reading them.
  Top-level menu: the 24 `MENU_KEYS` and the 24 `$script:Catalog` keys match in order, and
  `MENU_DEFAULT` (`scripts/install-prerequisites.sh:728`, eight `1`s then sixteen `0`s) matches the
  `Default` column entry-for-entry - all 24 compared, not just `repo-plugins`. DERIVED.
  The plugin count 4 -> 5 is this pass's own finding: `rule-of-two` was registered at `9fde7d82`
  (#128) and is in both catalogs with `PLUGIN_STATE`/`Selected` pre-ticked like the other four.
  The skill count (34) and menu count (24) did not move.
  Top-level *names* legitimately differ where the platform differs: the `prereqs` row names apt
  packages and sudo on the `.sh` (`:730`) and Chocolatey and Administrator on the `.ps1` (`:751`).
  DERIVED. Do not "fix" that into agreement.

- **The parity checker guards keys, not text - so agreeing descriptions can be jointly wrong.**
  `check_group_parity` (`scripts/check-marketplace.py:233`) compares `SKILL_KEYS` / `TEAM_KEYS` /
  `COMMUNITY_KEYS` / `PLUGIN_KEYS` against their `.ps1` catalogs on **keys only**; the `Name`
  strings are never read. `check_menu_parity` (`scripts/check-marketplace.py:194`) compares
  `MENU_KEYS` against `$script:Catalog` keys and `MENU_DEFAULT` against the `Default` flags - again
  no descriptive text. DERIVED, and closed by the per-path check: `check-marketplace.py` has not
  changed since the previous anchor.

  **The example this bullet carried has been FIXED, and is replaced by a live one measured here.**
  Both scripts used to advertise `crew - Virtual dev team: 11 agents, 21 commands` while the counts
  on disk were 54 and 24. `5d2e2950` (#124) corrected both sides; at this anchor
  `scripts/install-prerequisites.sh:900` and `scripts/install-prerequisites.ps1:855` both read
  `crew                    - Virtual dev team: 54 agents, 24 commands, safety hooks`, which is
  right. The tracking entry moved with it: it is now `TODO.md:558-681`, headed *"Crew's agent count
  is wrong in seven places and right in none — CLOSED 2026-09-12"*, and the previous citation
  (`TODO.md:564-580`, "29 agents, 24 commands") points into a section that has been rewritten.

  **The replacement is smaller and better, because nothing in this repo can catch it either.**
  DERIVED by measuring the padding of every `PLUGIN_NAME` row: four of the five pad the key out to
  **24** characters before the ` - ` separator (`crew` 4+20, `gizmoduck` 9+15, `localgpu` 8+16,
  `obsidian-vault` 14+10) and `rule-of-two` pads to **25** (11+14), so its description column sits
  one character right of the other four in the rendered picker. The `.ps1` carries the identical
  string, so the two sides agree perfectly — `check_group_parity` passes on keys, a `.sh`-vs-`.ps1`
  description diff passes on equality, and the menu is still visibly misaligned. It is cosmetic and
  it is not being fixed here (a one-character edit to a shipped install script is a separate,
  install-script-touching change that would need the README URLs re-pinned); it is recorded because
  it is the same defect class as the `11 agents` one, found the same way, one week later.

  JUDGEMENT, unchanged and now twice-evidenced: "the pair is in sync" is a weaker statement than it
  reads. Sync is enforced; correctness of the description text is enforced by nothing, and a wrong
  description survives every gate this repo has.

- **Nothing may bypass `pick_fit` / `Format-PickerLine`** - `scripts/install-prerequisites.sh:1271-1281`
  and `scripts/install-prerequisites.ps1:1077-1084`. Clipping is degradation; a line that *wraps* throws
  off the cursor-up redraw count and smears the menu over what was above it. Every title, label and
  hint in `picker_draw` (`scripts/install-prerequisites.sh:1283`) and `Invoke-Picker`
  (`scripts/install-prerequisites.ps1:1086`) routes through one of the two - re-checked line by
  line, not taken from the comment. DERIVED.
  One line in each does **not** route through the clipper: the scroll indicator `showing N-M of T`
  (`scripts/install-prerequisites.sh:1318-1320`, `scripts/install-prerequisites.ps1:1155-1156`).
  Its content is bounded to roughly 22 characters and both scripts floor the window at 40 columns
  (`term_cols` at `scripts/install-prerequisites.sh:1193-1200`, the floor itself at `:1198`;
  `if ($winW -lt 40) { $winW = 40 }` at `scripts/install-prerequisites.ps1:1120`), so it cannot wrap
  today. DERIVED.
  JUDGEMENT: route it anyway if that string ever grows - the bound is incidental, not enforced.
  The two clippers are **not** interchangeable: bash appends a one-character ellipsis and reserves
  1 (`scripts/install-prerequisites.sh:1277`); PowerShell appends three dots, reserves 3, and pads
  the result out to `Width` (`scripts/install-prerequisites.ps1:1082-1083`). The `.ps1` carries a
  comment at `:1078-1080` recording that reserving 1 there returned `Width + 2`. Porting a change
  between them without accounting for that is the wrap this pair exists to prevent. DERIVED.

- **Idempotent on both sides, and both sides re-checked.** `install_plugin` reports
  `SKIP | already current` at `scripts/install-prerequisites.sh:643` when the marketplace sha
  matches the installed sha, and `SKIP | already installed` at `:626` on the separate `--no-update`
  branch. DERIVED - two different messages on two different branches, and
  `scripts/_test/drift-detection.sh` asserts both by name (`already current` at `:128`, `:129`,
  `:137`, `:147`, `:148`, `:157`, `:162`, `:163`; `already installed` at `:190`). That file is
  unchanged since the previous anchor, so those citations are closed by the per-path check rather
  than re-read.
  Per-tool "already installed" branches, all repo-relative because `sh:`/`ps1:` shorthand cannot
  be pasted into `git diff` and this note cites four different `.sh` files:
  playwright-cli `scripts/install-prerequisites.sh:2197` / `scripts/install-prerequisites.ps1:1995`,
  skillui `scripts/install-prerequisites.sh:2241` / `scripts/install-prerequisites.ps1:2041`,
  strix `scripts/install-prerequisites.sh:2280` / `scripts/install-prerequisites.ps1:2083`,
  graphify `scripts/install-prerequisites.sh:2415` / `scripts/install-prerequisites.ps1:2248`,
  and the PowerShell `Install-ClaudePlugin` mirror at `scripts/install-prerequisites.ps1:648`,
  `:667`, `:676`. DERIVED. Every `.sh` citation in this bullet moved by three lines and every
  `.ps1` one by zero or one - which is why they were re-read rather than offset.

- **The `repo-plugins` menu row defaults to OFF; the five plugins inside it are pre-ticked.**
  `MENU_DEFAULT` index 18 is `0` at `scripts/install-prerequisites.sh:728` against
  `Default = $false` at `scripts/install-prerequisites.ps1:769`, each carrying the same reasoning
  in a comment (`scripts/install-prerequisites.sh:888-890`,
  `scripts/install-prerequisites.ps1:850-853`) - a hook runs whether or not Claude agrees with it,
  so it is opted into explicitly. DERIVED. Index 18 was re-derived by finding `repo-plugins` in the
  parsed `MENU_KEYS` list rather than counting by eye; it is still index 18 at 24 keys.
  Precision that matters: the gate is the single outer row, which covers all five plugins - and by
  the scripts' own descriptions `gizmoduck`, `localgpu` and now `rule-of-two` register no hooks
  (`scripts/install-prerequisites.sh:901-902`, `:904`). So the rule as implemented is "the row
  carrying plugins is off", not "hook-registering plugins are off", and adding `rule-of-two`
  widened that gap by one.
  `PLUGIN_STATE` is declared empty at `scripts/install-prerequisites.sh:913` and filled to all-`1`
  by the loop at `:914` - a correction to the previous citation `:910-911`, which now lands inside
  `PLUGIN_SPEC`. Every `Selected` is `$true` (`scripts/install-prerequisites.ps1:855-859`), so
  the inner rows are pre-ticked and take effect only once the outer row is turned on. DERIVED.

- **`json_query` resolves `jq` then `python3` and nothing else, with stderr discarded.**
  `scripts/install-prerequisites.sh:164-177` (the `jq` branch at `:170-171`, `python3` at
  `:172-173`, `return 1` at `:175`). No `python` or `py` fallback, no warning when both
  back ends are missing, and both invocations carry `2>/dev/null`. DERIVED. CLAUDE.md's "Git Bash
  ships without `python3`" landmine lands squarely here: with neither `jq` nor `python3`,
  `json_query` returns 1, `PLUGINS_CACHE` stays empty (`:248`), `plugin_version` returns 1 for every
  name (`:260`), and `install_plugin` takes the fresh-install path for everything. DERIVED.
  JUDGEMENT: the failure direction is reinstall-everything rather than silently-skip, so it is loud
  and slow rather than wrong - but it is still an unknown collapsing into a value, and the user is
  told nothing. `setup_notify` (`scripts/install-prerequisites.sh:1645`) does better, trying
  `python3` then `python` and warning on neither (`:1649-1651`) - still no `py`. Note the function
  at `:1604` is `notify_prereqs`; `setup_notify` itself begins at `:1645`.

- **The `pwsh`-not-on-PATH landmine does not live here.** Neither script invokes `pwsh` or
  `powershell` as a subprocess; the only occurrences of either word in the `.sh` are a comment
  about range syntax (`:1060`) and a hook description printed to the user (`:2375`), and the `.ps1`
  has no such invocation at all. DERIVED at this anchor. That landmine belongs to hook `command`
  configuration elsewhere in the repo, and attributing it to these files sends you looking in the
  wrong place.

## Corrected at this anchor

**The PowerShell picker DOES have a pre-flight, and the previous version of this note said it did
not.** That claim sat under "Unverified" and read: *"the PowerShell side has no equivalent
pre-flight and instead swallows a `CursorVisible` failure."* `Test-PickerSupported`
(`scripts/install-prerequisites.ps1:1038-1051`) is the direct equivalent of bash's
`picker_supported` (`scripts/install-prerequisites.sh:1202-1211`), and it refuses more cases than
bash does:

| Refuses | `.ps1` | `.sh` |
|---|---|---|
| redirected input or output | `:1040` | `:1205` (`NO_TTY`), `:1208` (`stty -g`) |
| no raw UI / no `stty` | `:1041` | `:1206` |
| the PowerShell ISE, where `ReadKey` throws | `:1043` | n/a |
| `TERM=dumb` | n/a | `:1207` |
| fewer than 10 lines | `:1044` | `:1209` |
| **fewer than 40 columns** | `:1044` | not checked here - `term_cols` (`:1198`) floors the value instead |
| `ReadKey` unreachable | `:1046`, inside the `try` | n/a |

The `CursorVisible` swallow is still there (`scripts/install-prerequisites.ps1:1113`) and is still
deliberate - hiding the cursor is cosmetic, and its own comment at `:1110-1112` says so - but it is
a fallback *inside* a path the pre-flight has already approved, not a substitute for one. A reader
acting on the old sentence would have gone to add a check that exists.

The sentence was marked "reasoned about from the width floors, not executed", which is exactly the
label that should have made it cheap to doubt. It was wrong about the *source*, not about the
runtime, so executing it was never the missing step - reading forty lines further up was.

## Unverified
- `scripts/_test/drift-detection.sh` was confirmed to drive the real `claude` CLI (`:62-64`, `:134`,
  `:154`, `:188`) and to self-skip when `claude` is absent (`:28`), so "CI cannot run it" is
  plausible - but CI's own skip behaviour was not inspected. Carried forward unchanged, and the
  file is byte-identical to the previous anchor; the suite was **not executed** in this pass.
- Picker behaviour under redirected output is still reasoned about rather than executed. Both
  pre-flights are now read and tabulated above, but whether `[Console]::WindowWidth`
  (`Get-PickerConsole`, `scripts/install-prerequisites.ps1:1057-1064`, the width read at `:1060`)
  throws inside a redirected host was not tested - `Test-PickerSupported` should have returned
  false before reaching it, and that ordering was read, not run.
- `scripts/check-marketplace.py` was read for `check_catalogs` (`:166`), `check_menu_parity`
  (`:194`) and `check_group_parity` (`:233`) only. The remaining checks in that file were not
  traced. Unchanged since the previous anchor, so this is the same gap rather than a new one.
- The `ms-mcp` and `obsidian-mcp` install paths (`scripts/install-prerequisites.sh:2461` onward)
  were not read; nothing in this note depends on them.

## Re-anchor provenance - 7b0d8f3a -> a573ca24, 2026-09-13

**The previous anchor resolved and the per-path check ran** - the first time for this note, which
has spent two passes working around an unresolvable one. `git diff --name-only 7b0d8f3a..HEAD --
<the four cited paths>` returns **two**: both install scripts. `scripts/_test/drift-detection.sh`
and `scripts/check-marketplace.py` did not change, so every citation into them is current by that
result and was not re-read.

Every citation into the two scripts that did change was re-derived by parsing the file - array
boundaries by matching the array opening and walking to its closing paren, function starts by
matching the definition, the parity verdicts by comparing extracted lists - rather than by
`difflib`-aligning against the previous revision, which is what the last pass had to do when it
had no usable anchor.

Three claims were re-measured and had gone false: the `11 agents, 21 commands` example (fixed by
#124), the four-plugin catalog (`rule-of-two` makes five), and the PowerShell picker pre-flight
(it exists). One new finding was added: the `rule-of-two` row's 25-character pad.

**The byte-identical-line sweep, measured after writing.** Diffing against
`git show a573ca24:.crew/codemap/install-scripts.md`: of **253** lines, **94** survived
byte-identical and **17** of those carry a citation. Only three point into the two unchanged files,
so the per-path result closes almost nothing here - **14** point into the two install scripts,
which did change, and each was resolved independently against HEAD: **0 unresolvable, 0 blank,
0 past EOF.** Each lands on the construct the sentence names (`MENU_KEYS=(` at `sh:720`,
`$script:Catalog = @(` at `ps1:750`, `plugin_version() {` at `sh:258`, the `repo-plugins`
`Default = $false` row at `ps1:769`, and so on).

This note is the case where the sweep earns its keep. Its ratio is the inverse of the other two:
two of four cited files changed, and those two are where nearly every citation points, so the
per-path check hands back almost no free answers and the only thing standing between a carried
citation and a wrong one is resolving it. A pass that reported "the per-path check ran, two files
changed" and stopped there would have covered three citations out of seventeen.

Not executed in this pass: `scripts/_test/drift-detection.sh` (it drives the real `claude` CLI).
Neither install script was modified by this pass.
