# install-scripts
anchor: useful-claude-add-ons@f9bb78a6
verified: 2026-09-14
Re-anchor only, no content change: `f9bb78a6` (#169, the crew skill-count
sweep prompting this pass) did not touch either install script — confirmed
by `git show f9bb78a6 --stat`, which lists only `README.md`,
`INSTALLATION.md`, `plugin/PLUGINS.md`, `plugin/README.md`,
`scripts/check-marketplace.py` and `scripts/_test/self-claims.py`. This
note's two citations into `scripts/check-marketplace.py`
(`check_group_parity` at `:234`, `check_menu_parity` at `:195`) are also
unaffected: `f9bb78a6`'s edits all land at or after old line 405, inside and
after `check_versions`/`check_self_claims` (confirmed by reading the diff's
hunk headers), well below both cited lines. Every claim below carries
forward from `0a9d8937` unread, re-anchored only.

## History, from the `0a9d8937` pass

re-verified, not re-derived: every claim below was re-read against the files it
cites at this anchor and its citation re-pointed where the code had moved. One
new skill (`github`) was inserted mid-array in both scripts, shifting every
citation below it by a uniform +2 lines in the `.sh` and +1 line in the `.ps1`
(confirmed at five widely-separated points - `term_cols`/`picker_supported`/
`pick_fit`/`picker_draw` in the `.sh`, `Test-PickerSupported`/
`Get-PickerConsole`/`Format-PickerLine`/`CursorVisible` in the `.ps1` - before
applying it to the rest). No claim about picker *behaviour* changed; this pass
is a citation re-point plus one count correction (34 skills -> 35).

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
  `scripts/install-prerequisites.sh:2434`, with `uv` itself bootstrapped via `pip3`/`pip` just
  above. DERIVED. The idempotence skip is `:2417`, not the install - a distinction two earlier
  passes got wrong in both directions; both line numbers moved by the uniform +2 offset at this
  anchor.
- `https://knowledge-mcp.global.api.aws/mcp` and `https://learn.microsoft.com/api/mcp` — registered, not called by the installer. Both were probed live before being added and answered a real MCP `initialize`.
- `uvx awslabs.aws-pricing-mcp-server@latest`, recorded by `claude mcp add` rather than executed, which is why the `uv` check above has to happen first.

## Landmines
- **Matched pair, and confirmed in sync at this anchor - by mechanical diff, not by eye.**
  Skill catalogs: `scripts/install-prerequisites.sh:807-880` (`SKILL_KEYS` at `:807-843`,
  `SKILL_NAME` at `:844-880`) against `scripts/install-prerequisites.ps1:808-854`
  (`$script:SkillCatalog`) - **35** keys, same order, and the 35 description strings compare
  equal element-for-element. Plugin catalogs: `scripts/install-prerequisites.sh:894-907`
  (`PLUGIN_KEYS` at `:894-900`, `PLUGIN_NAME` at `:901-907`) against
  `scripts/install-prerequisites.ps1:855-861` (`$script:PluginCatalog`, the five entries at
  `:856-860`) - **five** keys, same order (`crew`, `gizmoduck`, `localgpu`, `obsidian-vault`,
  `rule-of-two`), descriptions equal element-for-element. DERIVED by parsing both files and
  comparing lists, not by reading them.
  **The skill count moved at this anchor: 34 -> 35.** `github` was inserted between
  `find-skills` and `i-have-adhd` in both scripts' `SKILL_KEYS`/`SKILL_NAME` (`.sh`) and
  `$script:SkillCatalog` (`.ps1`) - a mid-array insertion, not an append, which is why every
  citation below it in both files moved (see the anchor note above).
  Top-level menu: the 24 `MENU_KEYS` and the 24 `$script:Catalog` keys match in order, and
  `MENU_DEFAULT` (`scripts/install-prerequisites.sh:728`, eight `1`s then sixteen `0`s) matches the
  `Default` column entry-for-entry - all 24 compared, not just `repo-plugins`. DERIVED. The menu
  count (24) did not move - `github` joins the `own-skills` sub-picker, not the top-level menu.
  The plugin count stayed at five; no plugin was added or removed at this anchor.
  Top-level *names* legitimately differ where the platform differs: the `prereqs` row names apt
  packages and sudo on the `.sh` (`:730`) and Chocolatey and Administrator on the `.ps1` (`:751`).
  DERIVED. Do not "fix" that into agreement.

- **The parity checker guards keys, not text - so agreeing descriptions can be jointly wrong.**
  `check_group_parity` (`scripts/check-marketplace.py:234`) compares `SKILL_KEYS` / `TEAM_KEYS` /
  `COMMUNITY_KEYS` / `PLUGIN_KEYS` against their `.ps1` catalogs on **keys only**; the `Name`
  strings are never read. `check_menu_parity` (`scripts/check-marketplace.py:195`) compares
  `MENU_KEYS` against `$script:Catalog` keys and `MENU_DEFAULT` against the `Default` flags - again
  no descriptive text. DERIVED, and re-read at this anchor rather than closed by the per-path check:
  `check-marketplace.py` changed substantially between the previous anchor and this one (+584/-21
  lines, three commits - `3374e8e0` #139 added `check_self_claims`, `357338cb` #144 fixed the
  version-drift walk across a merge, `0a9d8937` #161 added `check_crew_ignore_policy`), but neither
  of these two functions' bodies changed - only their position, by one line each.

  **The example this bullet carried has been FIXED, and is replaced by a live one measured here.**
  Both scripts used to advertise `crew - Virtual dev team: 11 agents, 21 commands` while the counts
  on disk were 54 and 24. `5d2e2950` (#124) corrected both sides. At this anchor the number has
  moved again, correctly, following a real change on disk: `plugin/crew/commands/` now holds **26**
  `.md` files (was 24), and `scripts/install-prerequisites.sh:902` and
  `scripts/install-prerequisites.ps1:856` both read
  `crew                    - Virtual dev team: 54 agents, 26 commands, safety hooks`, matching
  `.claude-plugin/marketplace.json`'s `crew` entry description at this anchor. The tracking entry
  from the 2026-09-12 fix is `TODO.md:558-681`, headed *"Crew's agent count is wrong in seven places
  and right in none — CLOSED 2026-09-12"* - it covers the *agent* count only, not this later
  *command* count change, which this note found independently while re-verifying.

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

- **Nothing may bypass `pick_fit` / `Format-PickerLine`** - `scripts/install-prerequisites.sh:1273-1283`
  and `scripts/install-prerequisites.ps1:1078-1085`. Clipping is degradation; a line that *wraps* throws
  off the cursor-up redraw count and smears the menu over what was above it. Every title, label and
  hint in `picker_draw` (`scripts/install-prerequisites.sh:1285`) and `Invoke-Picker`
  (`scripts/install-prerequisites.ps1:1087`) routes through one of the two - re-checked line by
  line, not taken from the comment. DERIVED.
  One line in each does **not** route through the clipper: the scroll indicator `showing N-M of T`
  (`scripts/install-prerequisites.sh:1320-1322`, `scripts/install-prerequisites.ps1:1156-1157`).
  Its content is bounded to roughly 22 characters and both scripts floor the window at 40 columns
  (`term_cols` at `scripts/install-prerequisites.sh:1195-1202`, the floor itself at `:1200`;
  `if ($winW -lt 40) { $winW = 40 }` at `scripts/install-prerequisites.ps1:1121`), so it cannot wrap
  today. DERIVED.
  JUDGEMENT: route it anyway if that string ever grows - the bound is incidental, not enforced.
  The two clippers are **not** interchangeable: bash appends a one-character ellipsis and reserves
  1 (`scripts/install-prerequisites.sh:1279`); PowerShell appends three dots, reserves 3, and pads
  the result out to `Width` (`scripts/install-prerequisites.ps1:1083-1084`). The `.ps1` carries a
  comment at `:1079-1081` recording that reserving 1 there returned `Width + 2`. Porting a change
  between them without accounting for that is the wrap this pair exists to prevent. DERIVED. Every
  line number in this bullet shifted by the uniform +2 (`.sh`) / +1 (`.ps1`) offset described at the
  top of this note; none of the picker's behaviour changed.

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
  playwright-cli `scripts/install-prerequisites.sh:2199` / `scripts/install-prerequisites.ps1:1996`,
  skillui `scripts/install-prerequisites.sh:2243` / `scripts/install-prerequisites.ps1:2042`,
  strix `scripts/install-prerequisites.sh:2282` / `scripts/install-prerequisites.ps1:2084`,
  graphify `scripts/install-prerequisites.sh:2417` / `scripts/install-prerequisites.ps1:2249`,
  and the PowerShell `Install-ClaudePlugin` mirror at `scripts/install-prerequisites.ps1:648`,
  `:667`, `:676` - unchanged, because that function sits above the `github` insertion point and the
  uniform offset does not reach it. Every other `.sh` citation in this bullet moved by exactly two
  lines and every other `.ps1` one by exactly one, confirming the uniform offset holds this far into
  the file too.

- **The `repo-plugins` menu row defaults to OFF; the five plugins inside it are pre-ticked.**
  `MENU_DEFAULT` index 18 is `0` at `scripts/install-prerequisites.sh:728` against
  `Default = $false` at `scripts/install-prerequisites.ps1:769`, each carrying the same reasoning
  in a comment (`scripts/install-prerequisites.sh:890-892`,
  `scripts/install-prerequisites.ps1:851-854`) - a hook runs whether or not Claude agrees with it,
  so it is opted into explicitly. DERIVED. Index 18 was re-derived by finding `repo-plugins` in the
  parsed `MENU_KEYS` list rather than counting by eye; it is still index 18 at 24 keys.
  Precision that matters: the gate is the single outer row, which covers all five plugins - and by
  the scripts' own descriptions `gizmoduck`, `localgpu` and now `rule-of-two` register no hooks
  (`scripts/install-prerequisites.sh:903-904`, `:906`). So the rule as implemented is "the row
  carrying plugins is off", not "hook-registering plugins are off", and adding `rule-of-two`
  widened that gap by one.
  `PLUGIN_STATE` is declared empty at `scripts/install-prerequisites.sh:915` and filled to all-`1`
  by the loop at `:916` - moved by two lines from the previous anchor's `:913`/`:914`, which is
  itself a correction to an older citation `:910-911` that had landed inside `PLUGIN_SPEC`. Every
  `Selected` is `$true` (`scripts/install-prerequisites.ps1:856-860`), so
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
  told nothing. `setup_notify` (`scripts/install-prerequisites.sh:1647`) does better, trying
  `python3` then `python` and warning on neither (`:1651-1653`) - still no `py`. Note the function
  at `:1606` is `notify_prereqs`; `setup_notify` itself begins at `:1647` - both shifted by the
  uniform +2 offset from the previous anchor's `:1604`/`:1645`.

- **The `pwsh`-not-on-PATH landmine does not live here.** Neither script invokes `pwsh` or
  `powershell` as a subprocess; the only occurrences of either word in the `.sh` are a comment
  about range syntax (`:1062`) and a hook description printed to the user (`:2377`), and the `.ps1`
  has no such invocation at all. DERIVED at this anchor. That landmine belongs to hook `command`
  configuration elsewhere in the repo, and attributing it to these files sends you looking in the
  wrong place.

## Corrected at this anchor

**The PowerShell picker DOES have a pre-flight, and an earlier version of this note said it did
not.** That claim sat under "Unverified" and read: *"the PowerShell side has no equivalent
pre-flight and instead swallows a `CursorVisible` failure."* `Test-PickerSupported`
(`scripts/install-prerequisites.ps1:1039-1052`) is the direct equivalent of bash's
`picker_supported` (`scripts/install-prerequisites.sh:1204-1213`), and it refuses more cases than
bash does. Re-read line by line at this anchor; every line number below shifted by the uniform
+1 (`.ps1`) / +2 (`.sh`) offset from the previous anchor, none of the behaviour did:

| Refuses | `.ps1` | `.sh` |
|---|---|---|
| redirected input or output | `:1041` | `:1207` (`NO_TTY`), `:1210` (`stty -g`) |
| no raw UI / no `stty` | `:1042` | `:1208` |
| the PowerShell ISE, where `ReadKey` throws | `:1044` | n/a |
| `TERM=dumb` | n/a | `:1209` |
| fewer than 10 lines | `:1045` | `:1211` |
| **fewer than 40 columns** | `:1045` | not checked here - `term_cols` (`:1200`) floors the value instead |
| `ReadKey` unreachable | `:1047`, inside the `try` | n/a |

The `CursorVisible` swallow is still there (`scripts/install-prerequisites.ps1:1114`) and is still
deliberate - hiding the cursor is cosmetic, and its own comment at `:1111-1113` says so - but it is
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
  (`Get-PickerConsole`, `scripts/install-prerequisites.ps1:1058-1065`, the width read at `:1061`)
  throws inside a redirected host was not tested - `Test-PickerSupported` should have returned
  false before reaching it, and that ordering was read, not run.
- `scripts/check-marketplace.py` was read for `check_catalogs` (`:167`), `check_menu_parity`
  (`:195`) and `check_group_parity` (`:234`) only, plus - new at this anchor -
  `check_crew_ignore_policy` (`:727-889`), read in full because it is new. The remaining checks in
  that file (`check_registration`, `check_skill_manifests`, `check_plugin_manifests`, `check_docs`,
  `check_hook_commands`, `check_versions`, `check_self_claims`) were not traced here; see
  `marketplace-registration.md` and `verification-harness.md`, which do trace several of them.
- The `ms-mcp` and `obsidian-mcp` install paths (around `scripts/install-prerequisites.sh:2463`
  onward, +2 from the previous anchor's `:2461`) were not read; nothing in this note depends on
  them.

## Re-anchor provenance - a573ca24 -> 0a9d8937, 2026-09-14

**The per-path check ran over the four cited paths.** `git diff --name-only a573ca24..HEAD --
scripts/check-marketplace.py scripts/install-prerequisites.ps1 scripts/install-prerequisites.sh
scripts/_test/drift-detection.sh` returns **three**: both install scripts and
`scripts/check-marketplace.py`. Only `scripts/_test/drift-detection.sh` did not change, so its
citations (`:21`, `:82`, `:62-64`, `:134`, `:154`, `:188`, `:28`) are closed by that result and were
not re-read.

Both install scripts changed by exactly one insertion each: the `github` skill was added mid-array
in `SKILL_KEYS`/`SKILL_NAME` (`.sh`) and `$script:SkillCatalog` (`.ps1`), and `crew`'s
`PLUGIN_NAME`/`Name` description text changed from `24 commands` to `26 commands` (a real change on
disk - `plugin/crew/commands/` now holds 26 `.md` files - not a drift to correct). Every other
citation into the two scripts was re-pointed by a **uniform offset**: +2 lines in the `.sh` for
anything below the `SKILL_KEYS` insertion point, +1 line in the `.ps1` for anything below the
`$script:SkillCatalog` insertion point. The offset was validated, not assumed: confirmed exact at
five widely-separated constructs (`term_cols`, `picker_supported`, `pick_fit`, `picker_draw` in the
`.sh`; `Test-PickerSupported`, `Get-PickerConsole`, `Format-PickerLine`, `CursorVisible` in the
`.ps1`) before being applied to the rest of this note's ~30 remaining citations into those two
files. One function above the insertion point, `Install-ClaudePlugin`'s marketplace-sha comparison
(`scripts/install-prerequisites.ps1:648`, `:667`, `:676`), did not move, and was confirmed
unchanged rather than assumed so.

`scripts/check-marketplace.py` changed far more than the install scripts (+584/-21 lines across
three commits: `3374e8e0` #139 added `check_self_claims`, `357338cb` #144 fixed the version-drift
walk across a merge, `0a9d8937` #161 added `check_crew_ignore_policy`), but this note only cites
two of its functions (`check_menu_parity`, `check_group_parity`), and both were re-read directly
rather than offset, since check-marketplace.py's internal shifts are not uniform the way the
install scripts' are.

One count changed and is corrected in place: **34 -> 35 skills** (`github` added). No claim in this
note was found to have gone false at this anchor beyond line-number drift; the previous anchor's
corrections (the command-count example, the plugin catalog going to five, the PowerShell pre-flight
existing) all still hold, re-verified rather than re-derived.

Not executed in this pass: `scripts/_test/drift-detection.sh` (it drives the real `claude` CLI).
Neither install script's *behaviour* changed by this pass; only line numbers moved and one
description string was corrected on disk before this note re-read it.
