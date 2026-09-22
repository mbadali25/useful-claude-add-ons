# install-scripts
anchor: useful-claude-add-ons@2b337296
verified: 2026-09-22

**Re-derived, not re-pointed, on 2026-09-22.** The two scripts grew by roughly
880 lines between `ea8a014` and this anchor and no uniform offset exists, so
every citation below was relocated by finding its construct again rather than by
adding a number to the old one. See `## Re-anchor provenance` at the bottom for
what that pass did and did not read.

## History, from the `0a9d8937` pass

The previous two passes were *re-verifications*: every claim re-read against the
file it cited, citations re-pointed by a uniform offset (+2 lines in the `.sh`,
+1 in the `.ps1`) caused by a single mid-array skill insertion. That technique
does not apply at this anchor and was not used - four new subsystems landed in
both scripts, in four different places, and the offset between any two
citations is different.

## Does
`scripts/install-prerequisites.sh` (bash) and `scripts/install-prerequisites.ps1` (PowerShell) are
the same interactive installer for two operating systems: a checkbox picker over prerequisites, the
Claude CLI, MCP servers, and this repo's own skills and plugins. DERIVED. The delivery mechanism
differs per row and is *not* uniformly `claude plugin install`: plugins and skills go through
`claude plugin install` (`scripts/install-prerequisites.sh:1121`), MCP servers through
`claude mcp add` (`scripts/install-prerequisites.sh:961`, and `:963` for the `--env` form), and the
standalone tools through their own package managers (see **Calls out to**). DERIVED.

## Entry points

- `scripts/install-prerequisites.sh:1137-1144` - `MENU_KEYS`, the top-level picker's ordered key
  list, **25** keys; `MENU_DEFAULT` is the parallel tick list at `:1145`, also 25 (eight `1`s then
  seventeen `0`s). DERIVED, by parsing both. Run directly by a user on Linux, macOS or Git Bash.
- `scripts/install-prerequisites.ps1:981-1007` - `$script:Catalog`, the Windows equivalent, carrying
  `Key`, `Default` and `Name` on one line per row (`:982-1006`). Same 25 keys in the same order,
  same 25 defaults. DERIVED.
- `scripts/install-prerequisites.sh:361` - `ensure_uv`, and `:371` `ensure_uv_once`. **New at this
  anchor** and now a prerequisite of two menu rows; see the uv landmine below.
- `scripts/install-prerequisites.sh:923` - `mcp_launcher_resolves`, the guard that decides whether
  an MCP row may be registered at all. **New at this anchor.** PowerShell equivalent is inline in
  `Add-McpServer` (`scripts/install-prerequisites.ps1:489`, the check at `:523-529`).
- `scripts/install-prerequisites.sh:2398` - `run_skill_preflights`, report-only skill dependency
  checks. **New at this anchor.** PowerShell twin `Invoke-SkillPreflights` at
  `scripts/install-prerequisites.ps1:2018`.
- `scripts/_test/drift-detection.sh:21` - sets `SCRIPT` to the real `.sh`; `:82` lifts
  `install_plugin` out of it with an `eval "$(awk ...)"` over the function body, so the
  update-detection path can be exercised without running the installer. DERIVED, and closed by the
  per-path check: that file has not changed since the previous anchor.
- `scripts/_test/self-claims.py:307` — module entry point (`main()`), from the graph

## Owns data

- Nothing of its own. It shells out to `claude plugin marketplace add` / `install` / `update`.
- Installed-plugin state is read **once** into `PLUGINS_CACHE` by `load_plugins`
  (`scripts/install-prerequisites.sh:567`), whose `claude plugin list --json` call is at
  `scripts/install-prerequisites.sh:571` (PowerShell equivalent `Get-ClaudePlugins` at
  `scripts/install-prerequisites.ps1:418`). DERIVED. `plugin_version`
  (`scripts/install-prerequisites.sh:598`) reads only that cache, never the CLI.
- Registered-MCP-server state is read once into `MCP_CACHE` by `load_mcp_servers`
  (`scripts/install-prerequisites.sh:900`), by taking the name off the front of each
  `claude mcp list` line - **there is no `--json` for that subcommand** (`:901-902`). DERIVED, and
  load-bearing for the MCP landmine below: the cache holds names and nothing else, so no code path
  here ever reads a Connected/Failed status back out.
- The re-run fast path deliberately avoids the CLI: `install_plugin`
  (`scripts/install-prerequisites.sh:1024`) compares the marketplace HEAD sha against the sha
  recorded for the installed copy, two file reads instead of a process launch. DERIVED.
- The `claude-code-plugins` marketplace is no longer registered by either script. It carried only `frontend-design`, now sourced from `claude-plugins-official`.

## Calls out to

- The `claude` CLI: `claude plugin list --json` at `scripts/install-prerequisites.sh:571`,
  `claude plugin install` at `:1121`, `claude plugin update` at `:1083`, `claude mcp add` at `:961`,
  `claude mcp list` at `:905`. DERIVED.
- The tools it provisions - Playwright CLI, skillui, strix, graphify, Obsidian - each through its
  own package manager. For graphify that is `uv tool install graphifyy` at
  `scripts/install-prerequisites.sh:2998`, inside `install_graphify` (`:2985`), and it is now
  gated on `ensure_uv` (`:2989`) rather than on a bare `pip3` line. The idempotence skip is `:2987`,
  not the install - a distinction three earlier passes got wrong in both directions.
- `https://knowledge-mcp.global.api.aws/mcp` and `https://learn.microsoft.com/api/mcp` — registered, not called by the installer. Both were probed live before being added and answered a real MCP `initialize`.
- `uvx awslabs.aws-pricing-mcp-server@latest`, recorded by `claude mcp add` rather than executed,
  which is why the `uv` check above has to happen first - and, since this anchor, why the
  `mcp_launcher_resolves` check exists at all.

## Landmines

- **Matched pair, and confirmed in sync at this anchor - by mechanical diff, not by eye.**
  Skill catalogs: `scripts/install-prerequisites.sh:1225-1300` (`SKILL_KEYS` at `:1225-1262`,
  `SKILL_NAME` at `:1263-1300`) against `scripts/install-prerequisites.ps1:1040-1077`
  (`$script:SkillCatalog`, rows at `:1041-1076`) - **36** keys, same order, and the 36 description
  strings compare equal element-for-element. Plugin catalogs:
  `scripts/install-prerequisites.sh:1314-1327` (`PLUGIN_KEYS` at `:1314-1320`, `PLUGIN_NAME` at
  `:1321-1327`) against `scripts/install-prerequisites.ps1:1088-1094` (`$script:PluginCatalog`, the
  five rows at `:1089-1093`) - **five** keys, same order (`crew`, `gizmoduck`, `localgpu`,
  `obsidian-vault`, `rule-of-two`), descriptions equal element-for-element. Team catalogs:
  `scripts/install-prerequisites.sh:1353` (`TEAM_KEYS`, one line) against
  `scripts/install-prerequisites.ps1:1103-1114` - **four**. Community catalogs:
  `scripts/install-prerequisites.sh:1379-1382` against
  `scripts/install-prerequisites.ps1:1120-1135` - **eight**. Top-level menu: 25 and 25, keys equal
  in order and `MENU_DEFAULT` equal to the `Default` column entry-for-entry. DERIVED by parsing
  both files and comparing lists, not by reading them.
  **Two counts moved at this anchor, and neither is the one the previous pass tracked.** `github`
  joined the **team** catalog (`scripts/install-prerequisites.ps1:1113`,
  `scripts/install-prerequisites.sh:1364`), 3 -> 4, sourced from `claude-plugins-official`; `eli5`
  joined the **community** catalog (`scripts/install-prerequisites.ps1:1134`,
  `scripts/install-prerequisites.sh:1401`), 7 -> 8. The own-skills, menu and plugin counts did not
  move between `ea8a014` and this anchor.
  **The marketplace's local name is `claude-community`, not `claude-plugins-community`** - the
  GitHub source is `anthropics/claude-plugins-community` but the repo publishes itself under the
  shorter name, and the spec must use it. Both scripts carry that warning in a comment
  (`scripts/install-prerequisites.sh:1371-1372`,
  `scripts/install-prerequisites.ps1:1128-1129`). DERIVED. Getting it wrong produces a spec that
  installs nothing and reports no error.
  **`github` is in TWO catalogs and they are different plugins** - this repo's own `github` skill
  in `SKILL_KEYS`, and Anthropic's GitHub MCP server as `github@claude-plugins-official` in the
  team catalog. `install_plugin` detects on the bare name, so adding the second to a machine that
  already has the first used to print "plugin 'github' already installed" and install nothing; the
  comment recording that is at `scripts/install-prerequisites.sh:1035-1037` and
  `scripts/install-prerequisites.ps1:869`, and the marketplace is now carried through detection
  (`scripts/install-prerequisites.sh:617`, `:581`). DERIVED.
  Top-level *names* legitimately differ where the platform differs: the `prereqs` row names apt
  packages and sudo on the `.sh` (`:1147`) and Chocolatey and Administrator on the `.ps1` (`:982`).
  DERIVED. Do not "fix" that into agreement.

- **The parity checker guards keys, not text - so agreeing descriptions can be jointly wrong.**
  `check_group_parity` (`scripts/check-marketplace.py:383`) compares `SKILL_KEYS` / `TEAM_KEYS` /
  `COMMUNITY_KEYS` / `PLUGIN_KEYS` against their `.ps1` catalogs on **keys only** (`:388-393` is the
  group list, `:404` the comparison); the `Name` strings are never read. `check_menu_parity`
  (`scripts/check-marketplace.py:329`) compares `MENU_KEYS` against `$script:Catalog` keys and
  `MENU_DEFAULT` against the `Default` flags - again no descriptive text. DERIVED, re-read at this
  anchor rather than closed by the per-path check: `check-marketplace.py` gained +193 lines and
  three new checks since the previous anchor (`check_argument_hint_frontmatter` at `:176`,
  `check_license_consistency` at `:268`, `check_command_backtick_spans` at `:1094`), but neither of
  these two functions' bodies changed - only their position, and not by a uniform amount.

  **The example this bullet carries was live at this anchor, and is now fixed - uncommitted,
  on branch `post-207-checklist`, not yet part of this file's own `2b337296` history.**
  `plugin/crew/commands/` holds **28** `.md` files, `plugin/crew/agents/` holds **54**, and
  `plugin/crew/skills/` holds **20** subdirectories (DERIVED, directory counts at this anchor,
  unchanged since - only the prose describing them moved). At `2b337296` it was a three-way
  disagreement:
  - both install scripts read `crew                    - Virtual dev team: 54 agents, 26 commands, safety hooks`
    (`scripts/install-prerequisites.sh:1322`, `scripts/install-prerequisites.ps1:1089`) - agents
    right, commands wrong by two;
  - `.claude-plugin/marketplace.json`'s `crew` description said `27 slash commands, 19 bundled
    skills` - wrong by one in each direction, and wrong differently from the scripts;
  - `README.md` said `54 subagents, 28 slash commands, 20 bundled skills` - correct;
  - two more sites carried the SAME wrong number, in files no version of this note previously
    named: `plugin/crew/skills/crew-best-practices/SKILL.md:29` said `26 commands` and
    `plugin/crew/README.md:2097` said `27 commands`, both against 28 on disk.

  **All five are now fixed in the uncommitted diff**, and the mechanism changed along with the
  numbers: `scripts/check-marketplace.py` gained `check_description_claims` (an explicit
  `DESCRIPTION_CLAIMS` table naming `.claude-plugin/marketplace.json`'s own JSON `description`
  string, which cannot carry an HTML comment) and `check_catalog_claims` (the same idea, an
  explicit `CATALOG_CLAIMS` table, for the two install scripts' own catalog labels - scoped to
  each plugin's own row via `_catalog_name_text`, not a whole-file scan). The two newly-found
  `.md` sites are ordinary `<!-- claim: plugin-commands:crew -->` markers, the same mechanism
  `plugin-skills:crew` already used - `check_self_claims` gained a `plugin-commands:` branch
  alongside `plugin-skills:` for exactly this. So the two scripts now agree with each other, the
  marketplace, `README.md`, and both newly-marked sites, and `python3 scripts/check-marketplace.py`
  now fails loudly if any one of the five drifts again - confirmed by sabotage (setting either
  `.md` site back to 26 reproduces the failure, restored). None of this is committed as of this
  anchor: `git diff --name-only 2b337296..HEAD` for these paths still returns empty until it is,
  so re-derive this passage rather than trusting it once that lands. **Not fixed here**: this
  note's scope is the map, and an edit to a shipped install script still requires the README
  install URLs to be re-pinned (see the next landmine) once committed.

  JUDGEMENT, unchanged and now three-times-evidenced at this anchor, **narrower since the
  uncommitted fix above**: "the pair is in sync" is a weaker statement than it reads. Sync is
  enforced; correctness of the description text was enforced by nothing at `2b337296`, and a wrong
  description survived every gate this repo had. `check_description_claims` and
  `check_catalog_claims` now enforce correctness too, but only for the exact (file, plugin, kind)
  triples explicitly listed in `DESCRIPTION_CLAIMS`/`CATALOG_CLAIMS` - crew's commands and agents
  counts in these two scripts and in `marketplace.json`'s description, and nothing else. Any other
  plugin's catalog label, or any other stated number, is still unenforced prose - the opt-in design
  this repo insists on (CLAUDE.md: "a checker that guesses which number describes what" is
  rejected) means coverage grows one explicit table row at a time, not by inference. The previous
  pass recorded a cosmetic
  instance of the same class - `rule-of-two`'s `PLUGIN_NAME` row pads its key to 25 characters
  before the ` - ` separator where the other four pad to 24, so its description column sits one
  character right in the rendered picker. **Still true at this anchor**, still identical in both
  scripts, still invisible to every check. DERIVED by measuring the padding of all five rows.

- **The README's install URLs are now CURRENT — re-pinned since this note's own anchor, and this
  bullet previously said the opposite.** Previously: "pinned to a commit that predates this anchor's
  script changes," citing `0a2d49b069bd178092e75a8cfd1a1c9df6690cd3` and a non-empty
  `git diff --name-only` over both scripts. Re-verified at this anchor: `README.md:12` and `:18` now
  pin `d541ee5708481fbf18c3a5fda050c9e40a40a2d9` (re-pinned by `2cc73a1e`, "README: re-pin install
  URLs to d541ee57 after PR #205 changed both install scripts (#206)"), and
  `git diff --name-only d541ee57..HEAD -- scripts/install-prerequisites.sh scripts/install-prerequisites.ps1`
  is **empty** — both re-verified directly at this pass. DERIVED. So a `curl | bash` taken from the
  README today runs the same script this note describes, including the four subsystems below it.
  The reversal is the interesting fact, not the current state alone: the previous anchor's finding
  was accurate on its own day and rotted within the same PR cycle that produced this note, which is
  the ordinary lifespan of a pin claim, not a special failure.
  **Not the same as "every pin in the repo is current."** `repo-docs.md` (2026-09-22 pass) found
  `docs/guides/Running-a-Mailbox-Job.json:18` still pins the *older* `0a2d49b0` SHA, one commit
  behind `d541ee57` — that file was not part of the `2cc73a1e` re-pin. Not fixed here; that file is
  outside this note's write scope.

- **`claude mcp add` writes config and never invokes the command, so six rows reported success for
  servers that could not start.** This is the defect `mcp_launcher_resolves`
  (`scripts/install-prerequisites.sh:923`) was added to close, and its comment at `:924-932` states
  the mechanism. DERIVED. The shape is CLAUDE.md's named recurring bug: registration succeeded,
  nothing read a status back (`load_mcp_servers` takes only the name, `:905`), so "could not tell"
  wore the label of a check that happened.
  Three points that are easy to get backwards:
  - **The check runs BEFORE the already-registered skip, not after** (`:954`, with the reasoning at
    `:949-953`; PowerShell at `scripts/install-prerequisites.ps1:523-529`, ahead of
    `Test-McpServerRegistered` at `:530`). A blind registration made on an earlier run is exactly as
    broken as one made now, and skipping it would print "already registered" over a server that
    cannot start - the same false reassurance, in the idempotent path.
  - **Only the launcher is checked, never the package behind it** (`:934-936`). `npx -y @scope/pkg`
    resolves its package at first launch; asking here would mean a network call. "npx is absent" is
    knowable now, "the package publishes" is not.
  - **The HTTP rows get no such check and that is deliberate** - `add_mcp_http_server`
    (`scripts/install-prerequisites.sh:970`) registers an endpoint, so there is no executable whose
    absence could be detected, and the equivalent check would make the installer's success depend
    on the network being up at install time. The `.ps1` states this explicitly at
    `scripts/install-prerequisites.ps1:519-522`. DERIVED.
  The failure is reported on **stderr** (`mcp_warn`, `scripts/install-prerequisites.sh:921`) for the
  same reason `uv_warn` is: the consequence is invisible at the point it is made and surfaces much
  later, inside a session, as a server that will not start.

- **`ensure_uv` is a chain of rungs, it is memoised, and the two scripts' middle rungs are NOT the
  same.** Six unchecked `pip3 install --user uv` calls were replaced at this anchor. DERIVED.
  - Memoised in `UV_ENSURED` (`scripts/install-prerequisites.sh:360`, read at `:362-365`) because
    three rows need uv: running the chain per row repeated the whole failure block three times, and
    where uv was already present moved `COUNT_SKIPPED` by 3 for one tool. The comment recording
    that is at `:355-359`.
  - `.sh` rungs: pipx (`:389`), Astral's pinned standalone installer (`:405`), then pip (`:456`).
  - `.ps1` rungs: pipx (`scripts/install-prerequisites.ps1:264`), **winget** (`:283`), then pip
    (`:305`). The middle rung differs by platform on purpose and is not a parity defect.
  - **The `.sh` middle rung is unreachable as shipped, deliberately, and says so.**
    `UV_INSTALLER_VERSION` and `UV_INSTALLER_SHA256` are both empty string
    (`scripts/install-prerequisites.sh:288-289`), `uv_installer_pinned` (`:292`) therefore returns
    false, and the rung is skipped with the reason recorded in `$attempted` (`:417-419`). The
    comment at `:275-287` makes recording the pin an explicit human step and refuses to fetch an
    unpinned installer, on the grounds that this repo already pins its own install URLs by sha.
    DERIVED. So the bash chain is effectively pipx -> pip today, and **that is a designed state,
    not a defect to fix by deleting the guard.**
  - Every label appended to `$attempted` is distinct, because that string is the whole of what the
    final failure message tells the operator (`:481`). The comment at `:413-416` records that
    `astral.sh-installer` used to be appended *before* the download, so a run in which curl was
    never invoked still reported the installer as tried - an unknown collapsing into the
    safe-looking value, caught and closed.
  - PEP 668 is probed rather than assumed: `pep668_enforced`
    (`scripts/install-prerequisites.sh:249`) returns three states, and the third - "could not tell,
    no python to ask" - survives into its own warning at `:465` and into an attempt-and-check rather
    than either assumption. DERIVED, and the correct shape per CLAUDE.md.
  - It refuses to install at all when running as root with a `HOME` root does not own
    (`uv_home_is_safe`, `:210`, refusal at `:373-377`), because every rung installs into
    `$HOME/.local/bin` and then puts that on PATH.

- **The skill preflights are REPORT-ONLY and must stay that way.** `run_skill_preflights`
  (`scripts/install-prerequisites.sh:2398`; PowerShell `Invoke-SkillPreflights` at
  `scripts/install-prerequisites.ps1:2018`) runs each selected skill's own `scripts/preflight.py`
  with no `--install` and no `--venv`. The reasoning is at
  `scripts/install-prerequisites.sh:2342-2368` and `scripts/install-prerequisites.ps1:1959-2000`.
  DERIVED. Three things worth not re-deriving:
  - **`</dev/null` is load-bearing** (`scripts/install-prerequisites.sh:2417`, and the `.ps1` passes
    an empty file as stdin at `:2037-2038`): `preflight.py` offers to install what is missing, and
    an inherited console would turn a report into a prompt mid-run.
  - **A missing interpreter is reported as UNCHECKED, not as absent** (`:2412`, and the `.ps1` at
    `:2073`). "None of python3, python or py is on PATH, so this skill's dependencies are
    UNCHECKED - not absent, unchecked." That is the distinction CLAUDE.md says has to survive into
    every derived line, and it does here.
  - It runs **after** the install, never before (`scripts/install-prerequisites.ps1:2122-2124`) -
    a preflight reads the copy that landed.
  - It found that **neither script had ever run a skill's `requirements.txt` or its preflight**
    before this anchor (`scripts/install-prerequisites.sh:2342-2345`, which records the grep that
    returned zero hits). DERIVED from the comment, not re-measured here.

- **Nothing may bypass `pick_fit` / `Format-PickerLine`** - `scripts/install-prerequisites.sh:1715-1725`
  and `scripts/install-prerequisites.ps1:1325-1333`. Clipping is degradation; a line that *wraps* throws
  off the cursor-up redraw count and smears the menu over what was above it. Every title, label and
  hint in `picker_draw` (`scripts/install-prerequisites.sh:1727`) and `Invoke-Picker`
  (`scripts/install-prerequisites.ps1:1334`) routes through one of the two - re-checked line by
  line, not taken from the comment. DERIVED.
  One line in each does **not** route through the clipper: the scroll indicator `showing N-M of T`
  (`scripts/install-prerequisites.sh:1763`, `scripts/install-prerequisites.ps1:1403`).
  Its content is bounded to roughly 22 characters and both scripts floor the window at 40 columns
  (`term_cols` at `scripts/install-prerequisites.sh:1637-1644`, the floor itself at `:1642`;
  `if ($winW -lt 40) { $winW = 40 }` at `scripts/install-prerequisites.ps1:1368`), so it cannot wrap
  today. DERIVED.
  JUDGEMENT: route it anyway if that string ever grows - the bound is incidental, not enforced.
  The two clippers are **not** interchangeable: bash appends a one-character ellipsis and reserves
  1 (`scripts/install-prerequisites.sh:1721`); PowerShell appends three dots, reserves 3, and pads
  the result out to `Width` (`scripts/install-prerequisites.ps1:1330-1331`). The `.ps1` carries a
  comment at `:1326-1328` recording that reserving 1 there returned `Width + 2`. Porting a change
  between them without accounting for that is the wrap this pair exists to prevent. DERIVED.
  **New at this anchor:** the three console touches are now funnelled through `Get-PickerConsole`
  (`scripts/install-prerequisites.ps1:1305`), `Set-PickerCursor` (`:1313`) and `Read-PickerKey`
  (`:1321`), so the draw loop can be exercised with no console attached - a test dot-sources the
  script and replaces them - and a host that throws on one fails in a single identifiable place
  rather than halfway through a repaint. The comment stating that is at `:1301-1304`. DERIVED from
  the source; **the test that does the dot-sourcing was not located or run at this pass.**

- **Idempotent on both sides, and both sides re-checked.** `install_plugin` reports
  `SKIP | already current` at `scripts/install-prerequisites.sh:1060`, `:1071` and `:1116` - three
  branches, not one - and `SKIP | already installed` at `:1043` on the separate `--no-update`
  branch (`:1042`). DERIVED. `scripts/_test/drift-detection.sh` asserts both by name
  (`already current` at `:128`, `:129`, `:137`, `:147`, `:148`, `:157`, `:162`, `:163`;
  `already installed` at `:190`). That file is **unchanged since the previous anchor**
  (`git diff --name-only ea8a014..HEAD -- scripts/_test/drift-detection.sh` is empty), so those
  citations are closed by the per-path check rather than re-read.
  A fourth branch is new and is not a skip: when a plugin's marketplace content changed but its
  declared version did not, it warns that the installed copy is stale and names `--force-refresh`
  (`scripts/install-prerequisites.sh:1113`). That is the "content change with no version bump"
  landmine CLAUDE.md opens with, detected from the installer's side. DERIVED.
  Per-tool "already installed" branches, all repo-relative because `sh:`/`ps1:` shorthand cannot
  be pasted into `git diff` and this note cites four different `.sh` files:
  playwright-cli `scripts/install-prerequisites.sh:2769` / `scripts/install-prerequisites.ps1:2395`,
  skillui `scripts/install-prerequisites.sh:2813` / `scripts/install-prerequisites.ps1:2441`,
  strix `scripts/install-prerequisites.sh:2852` / `scripts/install-prerequisites.ps1:2483`,
  graphify `scripts/install-prerequisites.sh:2987` / `scripts/install-prerequisites.ps1:2648`,
  and the PowerShell `Install-ClaudePlugin` mirror at `scripts/install-prerequisites.ps1:879`,
  `:898`, `:907`, `:959`. `uv` itself now has one too
  (`scripts/install-prerequisites.sh:382-384`), which is what makes `ensure_uv` safe to call from
  three rows.

- **The `repo-plugins` menu row defaults to OFF; the five plugins inside it are pre-ticked.**
  `MENU_DEFAULT` index 18 is `0` at `scripts/install-prerequisites.sh:1145` against
  `Default = $false` at `scripts/install-prerequisites.ps1:1000`, each carrying the same reasoning
  in a comment (`scripts/install-prerequisites.sh:1309-1313`,
  `scripts/install-prerequisites.ps1:1083-1087`) - a hook runs whether or not Claude agrees with it,
  so it is opted into explicitly. DERIVED. Index 18 was re-derived by finding `repo-plugins` in the
  parsed `MENU_KEYS` list rather than counting by eye; it is still index 18, now at 25 keys rather
  than 24, so **the index survived the menu growing** - which is luck, not design, and is exactly
  why it is re-parsed each pass instead of carried.
  Precision that matters: the gate is the single outer row, which covers all five plugins - and by
  the scripts' own descriptions `gizmoduck`, `localgpu` and `rule-of-two` register no hooks
  (`scripts/install-prerequisites.sh:1323-1324`, `:1326`). So the rule as implemented is "the row
  carrying plugins is off", not "hook-registering plugins are off".
  `PLUGIN_STATE` is declared empty at `scripts/install-prerequisites.sh:1335` and filled to all-`1`
  by the loop at `:1336`. Every `Selected` is `$true`
  (`scripts/install-prerequisites.ps1:1089-1093`), so the inner rows are pre-ticked and take effect
  only once the outer row is turned on. DERIVED.

- **`json_query` resolves `jq` then `python3` and nothing else, with stderr discarded.**
  `scripts/install-prerequisites.sh:493-506` (the `jq` branch at `:499-500`, `python3` at
  `:501-502`, `return 1` at `:504`). No `python` or `py` fallback, no warning when both
  back ends are missing, and both invocations carry `2>/dev/null`. DERIVED, re-read at this anchor
  - the function moved and also grew a CRLF strip (`:494-498` explains it: both back ends emit CRLF
  under Git Bash / WSL interop, leaving a stray `\r` on the last tab-separated field). CLAUDE.md's
  "Git Bash ships without `python3`" landmine still lands squarely here: with neither `jq` nor
  `python3`, `json_query` returns 1, `PLUGINS_CACHE` stays empty, `plugin_version` returns 1 for
  every name (`:598-604`), and `install_plugin` takes the fresh-install path for everything.
  DERIVED.
  JUDGEMENT: the failure direction is reinstall-everything rather than silently-skip, so it is loud
  and slow rather than wrong - but it is still an unknown collapsing into a value, and the user is
  told nothing. **This is now the odd one out.** Three paths added at this anchor -
  `run_skill_preflights` (`:2412`), `pep668_enforced` (`:249`) and `mcp_launcher_resolves` (`:938`)
  - all resolve `python3`/`python`/`py` or report "could not tell" as its own value, and
  `setup_notify` (`scripts/install-prerequisites.sh:2089`) tries `python3` then `python` and warns
  on neither (`:2094-2098`). `json_query` is the one remaining silent collapse, and the gap between
  it and its four newer neighbours is wider than it was. JUDGEMENT.

- **The `pwsh`-not-on-PATH landmine does not live here.** Neither script invokes `pwsh` or
  `powershell` as a subprocess; the four occurrences of either word in the `.sh` are comments
  (`:1504`, `:2342`, `:2435`) and one hook description printed to the user (`:2947`), and the `.ps1`
  has no such invocation at all (`grep -c` returns 0). DERIVED, re-measured at this anchor. That
  landmine belongs to hook `command` configuration elsewhere in the repo, and attributing it to
  these files sends you looking in the wrong place.

## Corrected at this anchor

**The two counts this note carried were already wrong at its own anchor, not drifted into.** The
note said `MENU_KEYS` held **24** keys and the skill catalogs **35**. Measured at `ea8a014` - the
sha this file itself named - `MENU_KEYS` held **25** and `SKILL_KEYS` **36**, and neither has moved
since. So both figures were stale before the previous pass re-anchored, and the re-anchor carried
them forward unread; the header said so in as many words ("Every claim below carries forward from
`0a9d8937` unread, re-anchored only"), which is the honest form of the error but not a harmless
one.

`INDEX.md` already records this exact failure for this exact file - that its citations "never
matched its own anchor (they match `0131d0f0`, three days earlier)". That finding was about line
numbers. This is the same defect in the counts, one pass later, and it survived a pass that
explicitly checked and corrected a count (34 -> 35). **A re-anchor that advances the sha without
re-reading turns every claim in the file into a claim about an unstated earlier commit**, and
nothing in the file distinguishes the claims that were checked from the ones that were carried.

**The PowerShell picker DOES have a pre-flight**, and a version of this note two passes ago said it
did not. `Test-PickerSupported` (`scripts/install-prerequisites.ps1:1286-1299`) is the direct
equivalent of bash's `picker_supported` (`scripts/install-prerequisites.sh:1646-1655`), and it
refuses more cases than bash does. Re-read line by line at this anchor:

| Refuses | `.ps1` | `.sh` |
|---|---|---|
| redirected input or output | `:1288` | `:1649` (`NO_TTY`), `:1652` (`stty -g`) |
| no raw UI / no `stty` | `:1289` | `:1650` |
| the PowerShell ISE, where `ReadKey` throws | `:1291` | n/a |
| `TERM=dumb` | n/a | `:1651` |
| fewer than 10 lines | `:1292` | `:1653` |
| **fewer than 40 columns** | `:1292` | not checked here - `term_cols` (`:1642`) floors the value instead |
| `ReadKey` unreachable | `:1294`, inside the `try` | n/a |

The `CursorVisible` swallow is still there (`scripts/install-prerequisites.ps1:1361`, restored at
`:1439` and `:1516`) and is still deliberate - hiding the cursor is cosmetic - but it is a fallback
*inside* a path the pre-flight has already approved, not a substitute for one.

## Unverified
- `scripts/_test/drift-detection.sh` was confirmed byte-unchanged since the previous anchor by the
  per-path diff and was **not re-read and not executed** (it drives the real `claude` CLI, which
  CLAUDE.md records as the reason CI cannot run it). CI's own skip behaviour was not inspected.
- **Neither install script was executed, in whole or in part, at this pass.** Every claim above is
  a reading of source. In particular: the `ensure_uv` chain was read rung by rung and never run, so
  which rung succeeds on any given machine is unknown here; `mcp_launcher_resolves` was read and
  never exercised; and no picker was drawn.
- **The eleven files under `scripts/_test/` were not run.** Five of them are new since the previous
  anchor (`check-powershell.sh`, `license-consistency.py`, `mcp-preflight-catalog.sh`,
  `menu-groups.sh`, `ps-install-keys.sh`, `uv-install.sh`) and at least three appear from their
  names to pin behaviour this note now describes. Their existence is a directory listing; what they
  assert is unread. That is the largest unexamined thing in this note.
- Picker behaviour under redirected output is still reasoned about rather than executed. Both
  pre-flights are read and tabulated above, but whether `[Console]::WindowWidth`
  (`Get-PickerConsole`, `scripts/install-prerequisites.ps1:1305-1312`, the width read at `:1308`)
  throws inside a redirected host was not tested - `Test-PickerSupported` should have returned
  false before reaching it, and that ordering was read, not run.
- `scripts/check-marketplace.py` was read for `check_menu_parity` (`:329`) and `check_group_parity`
  (`:383`) only. The three checks added since the previous anchor
  (`check_argument_hint_frontmatter` `:176`, `check_license_consistency` `:268`,
  `check_command_backtick_spans` `:1094`) were located by name and **not read**; nor were
  `check_registration`, `check_skill_manifests`, `check_plugin_manifests`, `check_catalogs`,
  `check_docs`, `check_hook_commands`, `check_versions`, `check_self_claims` or
  `check_crew_ignore_policy`. See `marketplace-registration.md` and `verification-harness.md`.
- The `ms-mcp` and `obsidian-mcp` install paths were not read; nothing in this note depends on them.
- `skill_preflight_path` / `Get-SkillPreflightPath`
  (`scripts/install-prerequisites.sh:2382`, `scripts/install-prerequisites.ps1:2001`) locate a
  skill's `preflight.py` under a versioned install directory by recursive search. The search itself
  was read; **no installed skill directory was inspected**, so whether the path shape it assumes
  matches a real install on either platform is unverified.

## Re-anchor provenance - ea8a014 -> 84976536, 2026-09-22

**Full re-derivation of both install scripts. Not a re-point.**

The per-path check over this note's cited paths:

```
git diff --name-only ea8a014..HEAD -- .claude-plugin/marketplace.json INSTALLATION.md \
  plugin/PLUGINS.md plugin/README.md README.md scripts/check-marketplace.py \
  scripts/install-prerequisites.ps1 scripts/install-prerequisites.sh \
  scripts/_test/drift-detection.sh scripts/_test/self-claims.py TODO.md
```
```
.claude-plugin/marketplace.json
INSTALLATION.md
README.md
TODO.md
plugin/PLUGINS.md
plugin/README.md
scripts/check-marketplace.py
scripts/install-prerequisites.ps1
scripts/install-prerequisites.sh
```

Nine of eleven moved. Two did not - `scripts/_test/drift-detection.sh` and
`scripts/_test/self-claims.py` - and their citations are closed by that result rather than re-read.

**The uniform-offset technique the previous two passes used does not apply and was not attempted.**
`git diff --stat` over the range: `scripts/install-prerequisites.sh` +664/-140 net 2610 -> 3134
lines, `scripts/install-prerequisites.ps1` +437/-84 net 2453 -> 2806, `scripts/check-marketplace.py`
+193 net 1040 -> 1233. Four new subsystems landed in four different places in each script, so the
offset between any two citations differs.

Method, stated because the result depends on it: every `` `path:line` `` token in the previous
version of this note was extracted mechanically, resolved against both `ea8a014` and HEAD, and
compared byte-for-byte. Of the citations into the two install scripts and `check-marketplace.py`,
**all but one came back changed.** Each was then relocated by finding its construct again -
`grep -n` for the function name, `awk` over the array declaration, and an AST-free parse of the
four catalogs in each script compared element-for-element - never by adding a number.

**One citation came back byte-identical and was still wrong, which is the trap worth recording.**
`scripts/install-prerequisites.sh:164-177` compared equal at both commits, so a content-equality
check passes it. At `ea8a014` that range was the body of `json_query`; at HEAD it is `as_root`, and
`json_query` has moved to `:493`. Two unrelated fourteen-line regions happened to match. A
same-text test is evidence that a citation *may* still be good, not that it is - the construct has
to be named and found. This note's `json_query` bullet is re-pointed on that basis.

Counts re-measured mechanically at this anchor rather than carried: menu 25/25, own-skills 36/36,
team 4/4, community 8/8, repo-plugins 5/5, keys equal in order on all five and every description
string equal element-for-element between the two scripts. `MENU_DEFAULT` equal to the `Default`
column entry-for-entry. Two of those counts were found to have been wrong at the previous anchor;
see `## Corrected at this anchor`.

Newly documented, having no entry in any previous version of this note: the `ensure_uv` chain, the
`mcp_launcher_resolves` guard, the report-only skill preflights, the `github`/`eli5` catalog rows
and the `claude-community` local-name trap, the stale-installed-copy warning branch in
`install_plugin`, and the `Get-PickerConsole`/`Set-PickerCursor`/`Read-PickerKey` indirection.
Newly measured and not previously recorded: the three-way `crew` command-count disagreement, and
the README install URLs being pinned behind the script changes.

Not done at this pass: nothing was installed, executed or run. No suite under `scripts/_test/` was
invoked, `drift-detection.sh` least of all - it drives the real `claude` CLI. Neither install
script was run in any form, on either platform. `python3 scripts/check-marketplace.py` was run and
passes, but that is a check on the repository, not on this note.

## Re-anchor provenance - 84976536 -> 2b337296, 2026-09-22

Per-path check, run rather than skipped:

```
git diff --name-only 84976536..HEAD -- .claude-plugin/marketplace.json INSTALLATION.md \
  plugin/PLUGINS.md plugin/README.md README.md scripts/check-marketplace.py \
  scripts/install-prerequisites.ps1 scripts/install-prerequisites.sh \
  scripts/_test/drift-detection.sh scripts/_test/self-claims.py TODO.md
```
```
.claude-plugin/marketplace.json
README.md
```

Two changed. `.claude-plugin/marketplace.json`'s only change in this range is `doc-builder`'s
version bump `1.5.2` -> `1.5.3`; the `crew` entry this note cites (the three-way command/skill-count
disagreement) is untouched, confirmed by re-diffing the `crew` block specifically. `README.md`'s
change is exactly the install-URL re-pin (`2cc73a1e`, PR #206) this pass re-verified and rewrote the
note's pin bullet for - see that bullet, above, for the corrected claim and the previous wording it
replaces. Both re-verified directly rather than assumed from the diff: `README.md:12` and `:18` now
read `d541ee5708481fbf18c3a5fda050c9e40a40a2d9`, and
`git diff --name-only d541ee57..HEAD -- scripts/install-prerequisites.sh scripts/install-prerequisites.ps1`
is empty.

Nothing else in this note was re-read at this pass; every other citation is closed by the per-path
check returning empty for its file. `python3 scripts/check-marketplace.py` was not re-run at this
pass.
