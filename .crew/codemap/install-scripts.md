# install-scripts
anchor: useful-claude-add-ons@8ebbdedc
verified: 2026-09-26

## Re-derive provenance

Re-derived from source at `6c497a14` (crew 1.0.25, PR #225 — "lifecycle
redesign, 4-role roster, Windows burn-in and native PowerShell fixes"), not
re-pointed from the previous `5d1fc5fd` anchor. Every citation below was found
by reading the committed file directly at HEAD — `grep -n` for the construct's
name, then the surrounding body read — rather than by adding an offset to the
old line number, because the per-path check (below) showed both scripts grew
enough (+480 / +463 lines respectively) that no uniform offset exists.

Per-path check against this note's previous (`5d1fc5fd`) tracked pathspec —
the 11 paths that note's own last provenance section named:

```
git diff --name-only 5d1fc5fd..6c497a14 -- .claude-plugin/marketplace.json \
  INSTALLATION.md plugin/PLUGINS.md plugin/README.md README.md \
  scripts/check-marketplace.py scripts/install-prerequisites.ps1 \
  scripts/install-prerequisites.sh scripts/_test/drift-detection.sh \
  scripts/_test/self-claims.py TODO.md
```
```
.claude-plugin/marketplace.json
INSTALLATION.md
README.md
TODO.md
plugin/PLUGINS.md
plugin/README.md
scripts/_test/self-claims.py
scripts/check-marketplace.py
scripts/install-prerequisites.ps1
scripts/install-prerequisites.sh
```

**All 11 files this note tracks still exist at `6c497a14`** (confirmed with
`git cat-file -e 6c497a14:<path>` for each, individually) — **10 of the 11
changed, 1 did not**: `scripts/_test/drift-detection.sh` is the sole holdout,
byte-identical across the range. This note was told, before this pass, to
expect "10 of 11 cited paths moved, 4 cited paths gone." The "moved" half
matches exactly what the command above shows. The "4 gone" half does **not**
match anything this note's own 11-path pathspec, or the individual
`path:line` tokens inside the file (all resolve to files that still exist,
checked the same way), can produce — no file this note cites, and no function
or array it names by line, is absent at `6c497a14`. That number is not
reproduced here and is not asserted; see "Unverified" for what this means in
practice. What *is* newly true, and explains most of the +480/+463: two menu
rows (`playwright-mcp`, `playwright-cli`) merged into one (`web-testing`,
now a project-local Playwright + axe-core + MCP + Test-Agents installer, ON
by default) and two brand-new rows (`lsp-plugins`, `stack-tools`) were added
— net `MENU_KEYS` 25 -> 26, confirmed by parsing both arrays directly, not
carried. `SKILL_KEYS` dropped 36 -> 34: `claude-memories-canvas` and
`claude-memories-vault` were removed from both catalogs (the vault-specific
skills the crew roster cut retired in favour of `obsidian-vault`'s portable
conventions profiles — see `README.md:736`, outside this note's scope).
`PLUGIN_KEYS` (5), `TEAM_KEYS` (4) and `COMMUNITY_KEYS` (8) are unchanged in
count and membership.

Everything below is a fresh read against `6c497a14`. No claim from the
`5d1fc5fd` version of this note was carried forward without being re-read at
its new location; the file's own extensive prior "Re-anchor provenance"
history (five prior passes back to `1f97e51c`) is not reproduced here —
consult the file's git history if that trail is needed. `python3
scripts/check-marketplace.py` was run at this anchor and reports `marketplace:
34 skills, 5 plugins / all checks passed`.

## Does
`scripts/install-prerequisites.sh` (bash) and `scripts/install-prerequisites.ps1`
(PowerShell) are the same interactive installer for two operating systems: a
checkbox picker over prerequisites, the Claude CLI, MCP servers, and this
repo's own skills and plugins. DERIVED, re-confirmed at this anchor. Delivery
is not uniform `claude plugin install`: plugins and skills go through
`claude plugin install` (`scripts/install-prerequisites.sh:1192`, was `:1121`),
MCP servers through `claude mcp add` inside `add_mcp_server`
(`scripts/install-prerequisites.sh:942`) or the new
`add_or_refresh_mcp_server` (`:1033`, see Landmines), and standalone tools
(Playwright, skillui, strix, graphify, Obsidian, the LSP/stack-tools rows)
through their own package managers.

## Entry points

- `scripts/install-prerequisites.sh:1208-1216` — `MENU_KEYS`, the top-level
  picker's ordered key list, **26** keys (was 25); `MENU_DEFAULT` at `:1217`,
  also 26 values. DERIVED by parsing both arrays directly. Run by a user on
  Linux, macOS or Git Bash.
- `scripts/install-prerequisites.ps1:1067-1094` — `$script:Catalog`, the
  Windows equivalent: same 26 keys in the same order (`Key`/`Default`/`Name`
  one per row), same defaults. DERIVED.
- `scripts/install-prerequisites.sh:2743` — `install_web_testing`, the new
  merged row (see Landmines). PowerShell equivalent is inline under
  `Test-Selected 'web-testing'` (not a named function on that side — verified
  by `grep -n "'web-testing'" scripts/install-prerequisites.ps1`, one hit,
  a top-level `if` block rather than a function call).
- `scripts/install-prerequisites.sh:923` — `mcp_launcher_resolves`, unchanged
  in behaviour from the previous anchor (checks the launch command resolves on
  PATH before `claude mcp add` is allowed to write a registration it cannot
  start). PowerShell equivalent inline in `Add-McpServer`.
- `scripts/install-prerequisites.sh:1033` — `add_or_refresh_mcp_server`, new
  at this anchor (see Landmines) — a stricter registration path used by the
  web-testing row that compares an existing registration's actual
  command/args against the required form, not just whether a name is taken.
- `scripts/install-prerequisites.sh:2467` — `run_skill_preflights`, unchanged
  in behaviour (report-only, `</dev/null` stdin, UNCHECKED-not-absent
  wording all re-read and confirmed byte-identical in substance).  PowerShell
  twin `Invoke-SkillPreflights` at `scripts/install-prerequisites.ps1:2103`.
- `scripts/_test/drift-detection.sh:21` / `:82` — unchanged (byte-identical
  since `5d1fc5fd`, closed by the per-path check, not re-read).
- `scripts/_test/self-claims.py:1227` — `main()` (was `:1166`; file grew
  1382 -> 1458 lines, +76, adding `run_markdown_lines` and
  `CASES_MARKDOWN_LINES`, a fixture for `check_self_claims`'s new
  `crew-markdown-lines` claim kind — that claim kind and its
  `count_crew_markdown_lines` counter live in `scripts/check-marketplace.py`
  and are consumed by `plugin/crew/BUDGETS.md:10`, outside this note's scope;
  `marketplace-registration.md` owns `check-marketplace.py`'s function map).
- `scripts/install-prerequisites.sh:3355` / `:3506` — the `lsp-plugins` and
  `stack-tools` rows are dispatched as top-level `if is_selected "..."` blocks
  near the end of the script's execution flow, not named functions the way
  every other row is. PowerShell equivalents at
  `scripts/install-prerequisites.ps1:2978` / `:3166`, same shape
  (`if (Test-Selected '...')`). DERIVED; not read for internal behaviour
  beyond confirming both platforms dispatch on the same two keys.

## Owns data

- Nothing of its own. It shells out to `claude plugin marketplace add` /
  `install` / `update`.
- `PLUGINS_CACHE` via `load_plugins` (`scripts/install-prerequisites.sh:567`,
  `claude plugin list --json` at `:571` — both unchanged from the previous
  anchor, re-confirmed by direct read). `plugin_version`
  (`scripts/install-prerequisites.sh:598`) reads only that cache.
- `MCP_CACHE` via `load_mcp_servers` (`scripts/install-prerequisites.sh:900`),
  taking the name off the front of each `claude mcp list` line — still no
  `--json` for that subcommand (`:901-902`). **New at this anchor**:
  `mcp_registration_command` (`scripts/install-prerequisites.sh:1012`) reads
  `claude mcp get <name>` to pull back the actual registered `Command:` /
  `Args:` text, specifically so `add_or_refresh_mcp_server` can compare it
  against the form a row requires — see Landmines. It returns exit code `2`,
  not a false match, when the read fails or cannot be parsed, so a `could not
  tell` never collapses into either "matches" or "does not match."
- `install_plugin` (`scripts/install-prerequisites.sh:1095`) still avoids the
  CLI on the fast path: compares the marketplace HEAD sha against the sha
  recorded for the installed copy. Three `SKIP | already current` branches
  (`:1131`, `:1142`, `:1187`) plus the separate `--no-update` branch's
  `SKIP | already installed` (`:1114`) and the stale-but-same-version warning
  naming `--force-refresh` (`:1184`) — same four-branch shape as the previous
  anchor, all four re-read directly, only the line numbers moved.
- The `claude-code-plugins` marketplace is still not registered by either
  script (re-confirmed: no occurrence of that literal string in
  `scripts/install-prerequisites.sh`); `claude-plugins-official` is the one
  actually used for `frontend-design`, `superpowers`, `github` and
  `claude-code-setup`.

## Calls out to

- The `claude` CLI: `claude plugin list --json` (`:571`), `claude plugin
  install` (`:1192`, and `:757` inside `ensure_plugin_enabled`'s reinstall
  path), `claude plugin update` (`:1154`, inside `install_plugin`), `claude
  mcp add` (`:966`/`:968` inside `add_mcp_server`), `claude mcp get`
  (`:1015`, new), `claude mcp list` (`:905`). DERIVED.
- Playwright, for the merged `web-testing` row
  (`scripts/install-prerequisites.sh:2743-2839`,
  `install_web_testing`): refuses if `node` is absent or older than
  20.19/22.12 (`:2744-2755`, an exact SemVer-ish parse of `node -v`, no
  install-or-upgrade attempt — told, not fixed); requires a `package.json` in
  the current directory because `@playwright/test`/`@axe-core/playwright` are
  installed as project devDependencies, never globally (`:2764-2767`); skips
  the `npm install` entirely when both pinned versions
  (`1.63.0`/`4.13.0`) already match (`:2771-2783`); detects an
  already-downloaded Chromium via `npx playwright install --dry-run`'s
  install-location output rather than its wording, since that wording never
  says "already installed" even at the pinned version (`:2789-2792`); probes
  `sudo -n true` (never prompts) to decide whether `--with-deps` can run, and
  falls back to a browser-only install with a named manual fix
  (`sudo npx playwright install-deps chromium`) when neither root nor
  passwordless sudo is available (`:2794-2810` — **this is the "no-sudo
  path"**, new at this anchor); scaffolds Playwright Test Agents for both the
  `claude` and `codex` loops, and — corrected from a previous defect —
  reports success only if *both* loops actually succeeded, not
  unconditionally after a single failed one (`:2814-2829`, `failed_loops`
  array); registers the `playwright` and `chrome-devtools` MCP servers at
  **project** scope regardless of the global `--scope` default, through
  `add_or_refresh_mcp_server` rather than `add_mcp_server`, specifically so a
  stale prior registration (missing `--isolated --headless --caps testing`,
  or an old package) gets migrated rather than silently kept
  (`:2837-2838`).
- graphify: `uv tool install graphifyy`, gated on `ensure_uv`. Re-grepped;
  still present, position not re-derived to the line (not needed — nothing in
  this note's other claims depends on its exact line, and the previous
  anchor's citation was not falsified).
- `https://knowledge-mcp.global.api.aws/mcp` and
  `https://learn.microsoft.com/api/mcp` — registered, not called by the
  installer. Not re-probed live at this pass (see Unverified).

## Landmines

- **`README.md`'s install-URL pin is current at this anchor - and current is
  a state it leaves on the next script-touching merge.** `README.md:12` and
  `:18` read `6c497a14fc06612732241d2b13eee4fea41996f5` (re-read at
  `f2bb919b`), re-pinned by #226 (`86931b29`, "README: re-pin install URLs to
  crew 1.0 merge (6c497a14)"), and `git log --oneline 6c497a14..f2bb919b --
  scripts/install-prerequisites.sh scripts/install-prerequisites.ps1` is
  empty, so a `curl | bash` taken from the README runs the scripts this note
  describes. At `6c497a14` this bullet recorded the pin as STALE at
  `5d1fc5fd`, missing the merged `web-testing` row, `lsp-plugins`,
  `stack-tools`, the 4-agent/34-command crew catalog line and
  `add_or_refresh_mcp_server`; #226 was the named fix and it landed. The
  pin's whole history (this note's pre-1.0 revisions) is that it goes stale
  again on the very next merge touching either script, so re-run
  `git log --oneline <pinned-sha>..HEAD -- scripts/install-prerequisites.sh
  scripts/install-prerequisites.ps1` against whatever HEAD is current rather
  than trusting this bullet.

- **The five-way crew count disagreement this note tracked for several
  anchors is fully resolved and re-confirmed independently correct, not
  merely re-synced.** All of the following read **4 agents, 34 commands** (or
  the plugin-level 29 skills / 34 hook entries across 8 events figures that go
  with them), checked directly rather than cross-quoted from one another:
  `.claude-plugin/marketplace.json`'s `crew` description (parsed with
  `json.load`); `plugin/PLUGINS.md:17`; `plugin/README.md:414`'s crew row;
  `plugin/crew/README.md`; `PLUGIN_NAME`'s crew row in both install scripts
  (`scripts/install-prerequisites.sh:1391`,
  `scripts/install-prerequisites.ps1:1174`). Independently re-derived from the
  filesystem rather than trusted: `ls plugin/crew/agents/*.md` = 4 (explorer,
  researcher, reviewer, security — no PM, no scribe: the roster cut this
  repo's own memory already names), `ls plugin/crew/commands/*.md` = 34,
  `ls -d plugin/crew/skills/*/` = 29, and `hooks.json` parsed with `json.load`
  = 34 entries across 8 events (`{PostToolUse, PreToolUse, UserPromptSubmit,
  PreCompact, Notification, Stop, SessionStart, SubagentStart}`), 26 unique
  `command` strings (13 scripts × two shells). `python3
  scripts/check-marketplace.py` passes with these numbers live, which is
  necessary but not sufficient — the checker only verifies the *marked*
  sites; this note additionally verified the filesystem count itself.

- **`mcp_launcher_resolves` is unchanged; `add_or_refresh_mcp_server` is a new
  and stricter sibling, not a replacement.** `add_mcp_server`
  (`scripts/install-prerequisites.sh:942`) still treats "a server with this
  name is registered" as fully idempotent — it never re-checks *what* is
  registered. `add_or_refresh_mcp_server` (`:1033`) is used only by the
  web-testing row's two MCP registrations: it reads the current
  command/args back with `claude mcp get` via `mcp_registration_command`
  (`:1012`), and if they don't match the row's required form it either warns
  and leaves it (non-interactive / `--select` / `--all` runs, `:1052-1054`)
  or, interactively, shows the diff and asks to remove-and-re-register
  (`:1056-1065`). A `could not read it back` result (exit 2 from
  `mcp_registration_command`) is treated as its own outcome — `skip`, with a
  message saying so — never silently as a match. DERIVED, read end to end.
  JUDGEMENT: this closes a real gap the plain `add_mcp_server` still has
  everywhere else it is used (any row whose required flags change later would
  report "already registered" over a now-wrong registration) — but the fix
  was made narrowly, for the one row that needed it, not generally.

- **Nothing may bypass `pick_fit` / `Format-PickerLine`.**
  `scripts/install-prerequisites.sh:1784-1793` and
  `scripts/install-prerequisites.ps1:1410-1417`, re-read line by line, same
  shape as the previous anchor: bash appends a one-character ellipsis and
  reserves 1; PowerShell appends `...` (three characters) and reserves 3,
  padding the result to `Width` — the comment at `:1412-1413` still records
  that reserving 1 there used to return `Width + 2`. The scroll indicator
  (`showing N-M of T`) still does not route through either clipper
  (`scripts/install-prerequisites.sh:1832`,
  `scripts/install-prerequisites.ps1:1488`) and is still bounded to a string
  short enough not to wrap at the still-40-column floor
  (`term_cols`, `scripts/install-prerequisites.sh:1706-1713`, the floor at
  `:1711`; `[Console]::WindowWidth -lt 40` inside `Test-PickerSupported` at
  `scripts/install-prerequisites.ps1:1377`). JUDGEMENT, unchanged: route it
  through the clipper anyway if that string ever grows.

- **`Test-PickerSupported` still refuses strictly more cases than bash's
  `picker_supported`,** re-read at this anchor
  (`scripts/install-prerequisites.ps1:1371-1384` vs
  `scripts/install-prerequisites.sh:1715-1724`): redirected input/output, no
  `RawUI`, the PowerShell ISE (`ReadKey` throws there), and
  `WindowHeight < 10 || WindowWidth < 40` all refuse on the PowerShell side;
  bash refuses no-tty, no `stty`, `TERM=dumb`, and fewer than 10 lines, but
  only *floors* (does not refuse on) narrow terminals via `term_cols`. Same
  asymmetry as the previous anchor, re-confirmed rather than assumed
  unchanged.

- **The skill preflights are still REPORT-ONLY, unchanged in every particular
  this note checks.** `run_skill_preflights`
  (`scripts/install-prerequisites.sh:2467`; PowerShell
  `Invoke-SkillPreflights` at `scripts/install-prerequisites.ps1:2103`) still
  runs each selected skill's own `preflight.py` with no `--install`, `</dev/null`
  on the bash side (load-bearing — an inherited console would turn a report
  into a prompt), and a missing interpreter is still reported as UNCHECKED,
  not absent, verbatim (`scripts/install-prerequisites.sh:2481`,
  `scripts/install-prerequisites.ps1:2114`).

- **`ensure_uv`'s chain and memoisation are unchanged.** `UV_ENSURED`
  memoises across the three callers that need `uv`/`uvx`
  (`scripts/install-prerequisites.sh:359-368`); bash's middle rung (Astral's
  own installer) is still deliberately unreachable because
  `UV_INSTALLER_VERSION`/`UV_INSTALLER_SHA256` are still empty strings, so the
  chain is pipx -> pip today, same as the previous anchor, re-read not
  assumed; PowerShell's middle rung is `winget`, still a genuine platform
  difference and not a parity defect. `uv_home_is_safe` still refuses running
  as root with an unprivileged `HOME`.

- **`json_query` is still the one silent-collapse path.** Resolves `jq` then
  `python3`, `return 1` with no warning and no `python`/`py` fallback if
  neither is present, both invocations still carry `2>/dev/null`
  (`scripts/install-prerequisites.sh:493-506`, re-read, unchanged in
  substance). Every other unknown-interpreter path added at or since the
  previous anchor (`run_skill_preflights`, `pep668_enforced`,
  `mcp_launcher_resolves`, `setup_notify`) reports "could not tell" as its own
  value; this one still does not. JUDGEMENT, unchanged.

- **The `repo-plugins` menu row still defaults to OFF; its five plugins are
  still pre-ticked.** Re-derived by finding `repo-plugins` in the freshly
  re-parsed `MENU_KEYS` list rather than assuming its old index still holds —
  it does not: index **17** in the new 26-key list (was 18 of 25).
  `MENU_DEFAULT[17]` is `0`
  (`scripts/install-prerequisites.sh:1217`); `Default = $false` on the
  matching PowerShell row (`scripts/install-prerequisites.ps1:1092` area —
  confirmed by reading the `$script:Catalog` block, `:1067-1094`). Every
  `PLUGIN_STATE` entry is still filled to `1` by a loop
  (`scripts/install-prerequisites.sh:1404-1406`); every PowerShell
  `PluginCatalog` row's `Selected` is still `$true`
  (`scripts/install-prerequisites.ps1:1174-1178`).

- **`claude-memories-vault` / `claude-memories-canvas` are gone from both
  catalogs, replacing a landmine this note no longer needs to track.** Their
  `SKILL_KEYS`/`SKILL_NAME` rows and PowerShell equivalents are absent,
  confirmed by `git diff` (they are pure deletions in this range, not moved
  elsewhere) and by grepping the current file for either string (zero hits in
  `scripts/install-prerequisites.sh`/`.ps1`). `README.md:736` (outside this
  note's scope) explains the replacement: `obsidian-vault`'s portable
  `obsidian-memory-contract` profiles.

## Unverified

- **The task that produced this pass stated "4 cited paths gone" for this
  note; this pass could not reproduce that finding and does not repeat it as
  fact.** Every path this note cites, checked individually with `git cat-file
  -e 6c497a14:<path>`, exists. If "gone" refers to something narrower than
  file existence — a specific cited construct that moved so far its old line
  number now names something unrelated, for instance — that check was not
  performed exhaustively over every historical citation in the pre-1.0
  version of this file, only over the citations this rewrite makes. Re-run
  against the pre-1.0 file's full citation list if that gap matters.
- Neither install script was executed, in whole or in part. Every claim above
  is a reading of source, not a run: the `ensure_uv` chain, the web-testing
  row's Node-version parse and sudo probe, `add_or_refresh_mcp_server`'s
  interactive remove-and-re-register prompt, and the picker's pre-flight
  refusals were all read and never exercised.
- `scripts/_test/drift-detection.sh` was confirmed byte-unchanged by the
  per-path check and was not re-read or re-run at this pass (it drives the
  real `claude` CLI, which CI cannot run).
- The 14 files under `scripts/_test/` were listed
  (`argument-hint-frontmatter.py`, `check-powershell.sh`,
  `crew-ignore-policy.py`, `drift-detection.sh`, `instruction-budgets.py`,
  `license-consistency.py`, `lsp-stack-tools.sh`, `mcp-preflight-catalog.sh`,
  `menu-groups.sh`, `ps-install-keys.sh`, `self-claims.py`, `uv-install.sh`,
  `version-drift.py`, `web-testing.sh` — three new since `5d1fc5fd`:
  `instruction-budgets.py`, `lsp-stack-tools.sh`, `web-testing.sh`) but only
  `self-claims.py` was opened; the other 13 are a directory listing, not a
  read.
- `scripts/check-marketplace.py`'s `check_menu_parity` (`:329`) and
  `check_group_parity` (`:383`) were confirmed to still exist at the same
  line numbers as the previous anchor (the file's growth landed after them),
  but their bodies were not re-read line by line at this pass — the previous
  anchor's reading of them is assumed still accurate because the diff
  (`git diff 5d1fc5fd..6c497a14 -- scripts/check-marketplace.py`) touches only
  a region well after both functions (`count_crew_markdown_lines` onward).
  `marketplace-registration.md` owns this file's full function map.
- The `lsp-plugins` and `stack-tools` rows' actual installers (whatever
  `install_lsp_plugins`/`install_stack_tools`-equivalent code exists inside
  the `if is_selected` blocks at `:3355`/`:3506`) were located but not read
  for behaviour — only their dispatch sites were confirmed to exist and to
  match between the two scripts.
- `https://knowledge-mcp.global.api.aws/mcp` and
  `https://learn.microsoft.com/api/mcp` were not re-probed live at this pass;
  the previous anchor's "answered a real MCP `initialize`" finding is not
  repeated as current.
- `skill_preflight_path` / `Get-SkillPreflightPath`'s recursive search for an
  installed skill's `preflight.py` was not re-read at this pass; no installed
  skill directory was inspected.

## Re-anchor provenance - `6c497a14` -> `f2bb919b`, 2026-09-25 (T-0015)

`git diff --name-only 6c497a14 f2bb919b -- <the 13 tracked paths this note cites>` returns six:
`.claude-plugin/marketplace.json`, `README.md`, `TODO.md`, `plugin/PLUGINS.md`,
`plugin/crew/BUDGETS.md`, `plugin/crew/README.md`. Both install scripts and
`scripts/check-marketplace.py` are **not** in it, so every `scripts/install-prerequisites.*` and
`scripts/check-marketplace.py` citation above stands without a re-read. Each changed file:

- `README.md` - only `:12` and `:18` changed, the two install-URL pins, now `6c497a14` (#226).
  The Landmines bullet was rewritten from STALE to current; `:736`, cited as outside scope, did not
  move.
- `.claude-plugin/marketplace.json` - crew's `version` (`:218`) only; the `crew` description this
  note checks the four-count claim against is `:217`, unchanged.
- `plugin/PLUGINS.md` - crew's version row (`:14`) only; `:17`, the "4 agents, 34 commands, 29
  skills ... 34 hook entries" row cited above, is unchanged.
- `plugin/crew/BUDGETS.md` - the claim marker is still `:10`; the figure on `:11` moved from 17,788
  to 17,811 lines (120 files), which `check-marketplace.py` verifies.
- `plugin/crew/README.md` - one command-table cell (`:2145` at `f2bb919b`, `:2148` at `adf8d1dd`,
  "Acceptance" -> "Acceptance checks"); this note cites the file without a line.
- `TODO.md` - cited only in the historical pathspec above; no live `TODO.md:<n>` claim here.

Not re-verified at this pass: neither install script was executed; `drift-detection.sh` was not run.

Re-verified per-path from `f2bb919b` to `adf8d1dd` for T-0008: of the cited paths only `.claude-plugin/marketplace.json` (crew `version` `:218`, now 1.0.36; the `:217` description is unchanged), `plugin/PLUGINS.md` (`:14` version; `:17` Registers row unchanged), `plugin/crew/BUDGETS.md` (marker still `:10`; the `:11` figure moved again, now 17,841 lines), `plugin/crew/README.md` (rows added above the command table, moving the cell above; the `34 commands` claim at `:2178` and `4 agents` at `:2189` still hold), `plugin/crew/commands/` (two files edited, `ls plugin/crew/commands/*.md` still 34) and `TODO.md` changed, while both install scripts, `README.md` and `scripts/check-marketplace.py` did not, so their citations stand.

Re-verified per-path from `adf8d1dd` to `8d447a7d` for T-0008's review round 3: of the cited paths
only `plugin/crew/README.md` changed, two lines reworded in place at `:764` and `:766`; the
`34 commands` claim at `:2178` and `4 agents` at `:2189` did not move and still hold. Both install
scripts, `README.md` and `scripts/check-marketplace.py` did not change.

Re-verified per-path from `8d447a7d` to `8ebbdedc` for T-0034 and T-0026's landing (`8ebbdedc` is
the crew 1.0.39 bump on top of the T-0026 merge `563f54c3`): of the cited paths
`.claude-plugin/marketplace.json` (crew `version` `:218` only, now 1.0.39; the `:217` description
is unchanged), `plugin/PLUGINS.md` (`:14` version; the `:17` Registers row unchanged),
`plugin/crew/BUDGETS.md` (marker still `:10`; the `:11` figure is now 17,847 lines across 120
files, which `check-marketplace.py` verifies), `plugin/crew/README.md` (two lines added above the
command table, so the `34 commands` claim moved `:2178` -> `:2180` and `4 agents` `:2189` ->
`:2191`, re-grepped, both still true), `plugin/crew/commands/` (four files edited, `ls
plugin/crew/commands/*.md` still 34) and `TODO.md` (one entry closed; no live `TODO.md:<n>` claim
here) changed, while both install scripts, `README.md`, `INSTALLATION.md`, `plugin/README.md` and
`scripts/check-marketplace.py` did not, so their citations stand. Neither install script was
executed.
