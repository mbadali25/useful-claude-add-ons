# install-scripts
anchor: useful-claude-add-ons@314fb065
verified: 2026-09-27

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

- **`README.md`'s install-URL pin is STALE again at this anchor, by one
  line per script.** `README.md:12` and `:18` still read
  `6c497a14fc06612732241d2b13eee4fea41996f5` (re-read at `07ca3972`), but
  `git log --oneline 6c497a14..07ca3972 -- scripts/install-prerequisites.sh
  scripts/install-prerequisites.ps1` now returns `ecf69e43` (crew 1.0.41,
  T-0004), and `git diff --stat` over the same range is 1 line in each script:
  the crew `PLUGIN_NAME` / `PluginCatalog` label, `34 commands` -> `35
  commands`. So a `curl | bash` taken from the README runs scripts that
  differ from the ones this note describes only in that menu label. DERIVED.
  This is not merged to `main` at this anchor (branch `T-0004-autopilot`), so
  the re-pin is due after that merge, per CLAUDE.md's promotion step. It was
  current at `f2bb919b` (re-pinned by #226, `86931b29`, "README: re-pin
  install URLs to crew 1.0 merge (6c497a14)"). At `6c497a14` this bullet recorded the pin as STALE at
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
  merely re-synced.** All of the following read **4 agents, 35 commands** (34
  until `ecf69e43` added `/crew:autopilot`; re-read at `07ca3972`) (or
  the plugin-level 29 skills / 34 hook entries across 8 events figures that go
  with them), checked directly rather than cross-quoted from one another:
  `.claude-plugin/marketplace.json`'s `crew` description (parsed with
  `json.load`); `plugin/PLUGINS.md:17`; `plugin/README.md:414`'s crew row;
  `plugin/crew/README.md`; `PLUGIN_NAME`'s crew row in both install scripts
  (`scripts/install-prerequisites.sh:1391`,
  `scripts/install-prerequisites.ps1:1174`). Independently re-derived from the
  filesystem rather than trusted: `ls plugin/crew/agents/*.md` = 4 (explorer,
  researcher, reviewer, security — no PM, no scribe: the roster cut this
  repo's own memory already names), `ls plugin/crew/commands/*.md` = 35,
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
Re-verified per-path from `8d447a7d` to `6d35ef8c` for T-0006 (`8d447a7d` is T-0008's pre-rebase
commit, tree-identical to `origin/main` `768a747a` for these paths): of the cited paths
`.claude-plugin/marketplace.json` (crew `version` `:218`, now 1.0.40; `:217` unchanged),
`plugin/PLUGINS.md` (`:14` version; `:17` Registers row unchanged), `plugin/crew/BUDGETS.md` (marker
still `:10`; the `:11` figure is now 17,959 lines across 120 files, and
`git ls-files 'plugin/crew/*.md' | xargs cat | wc -l` returns 17959), `plugin/crew/README.md` (28
lines of auto-resume prose added above the command table, so the `34 commands` claim moved
`:2178` -> `:2206` and `4 agents` `:2189` -> `:2217`; both re-read and still hold,
`ls plugin/crew/commands/*.md` is 34 and `ls plugin/crew/agents/*.md` is 4) and `TODO.md`
changed. Both install scripts, `README.md` and `scripts/check-marketplace.py` did not, so their
citations stand.

Re-verified per-path from `6d35ef8c` to `2bb92f32` for T-0006's review round 3: of the cited
paths only `plugin/crew/BUDGETS.md` (marker still `:10`; the `:11` figure is now 17,967 lines
across 120 files, and `git ls-files 'plugin/crew/*.md' | xargs cat | wc -l` returns 17967) and
`plugin/crew/README.md` (one line added in the auto-resume prose, so the `34 commands` claim moved
`:2206` -> `:2207` and `4 agents` `:2217` -> `:2218`; both re-read and still hold,
`ls plugin/crew/commands/*.md` is 34 and `ls plugin/crew/agents/*.md` is 4) changed.
`.claude-plugin/marketplace.json` and `plugin/PLUGINS.md` were stepped to 1.0.37 and back, so
they end byte-identical to `6d35ef8c`. Both install scripts, `README.md`, `TODO.md` and
`scripts/check-marketplace.py` did not change, so their citations stand.

Re-verified per-path to `a0c0847e` for T-0006's landing (`a0c0847e` is the crew 1.0.40 bump on top of
`1cec9572`, the merge of T-0006 `cb125d51` into main `d3844c76`, joining this note's `8ebbdedc`
and `2bb92f32` lines): of the cited paths `.claude-plugin/marketplace.json` (crew `version`
`:218`, 1.0.40; `:217` unchanged), `plugin/PLUGINS.md` (`:14` version; `:17` Registers row
unchanged), `plugin/crew/BUDGETS.md` (marker still `:10`; `:11` now reads 17,973 lines across 120
files, recomputed from the merged tree and matching `check-marketplace.py`), `plugin/crew/README.md`
(both sides' additions, so the `34 commands` claim is at `:2209` and `4 agents` at `:2220`,
re-grepped, both still true: `ls plugin/crew/commands/*.md` is 34, `ls plugin/crew/agents/*.md`
is 4) and `TODO.md` changed. Both install scripts, `README.md` and
`scripts/check-marketplace.py` did not, so their citations stand. Neither install script was
executed.

Re-verified per-path from `a0c0847e` to `07ca3972` for T-0004 (`/crew:autopilot`, crew 1.0.41):
of the cited paths `.claude-plugin/marketplace.json` (crew `version` `:218`, now 1.0.41; the `:217`
description now reads `35 slash commands`), `plugin/PLUGINS.md` (`:14` version; the `:17` Registers
row now reads `35 commands`), `plugin/README.md` (`:414` crew row, `34` -> `35 commands`, in place),
`README.md` (`:168` and `:874`, `34` -> `35`, in place; `:12`/`:18` pins and `:736` did not move),
`plugin/crew/BUDGETS.md` (marker still `:10`; `:11` now reads 18,176 lines across 121 files, and
`git ls-files 'plugin/crew/*.md' | xargs cat | wc -l` returns 18176), `plugin/crew/README.md` (the
`35 commands` claim is now at `:2255` and `4 agents` at `:2266`, re-grepped),
`plugin/crew/commands/` (`autopilot.md` added, `migrate.md` edited; `ls plugin/crew/commands/*.md`
is 35, `ls plugin/crew/agents/*.md` is 4, `ls -d plugin/crew/skills/*/` is 29, `hooks.json` still 34
entries across 8 events), `TODO.md`, and **both install scripts** changed. Each script's change is a
single in-place line, the crew label at `scripts/install-prerequisites.sh:1391` and
`scripts/install-prerequisites.ps1:1174` (`34` -> `35 commands`), so no other line number in either
script moved and every other install-script citation stands. That same change makes the README pin
stale (Landmines). `scripts/check-marketplace.py`, `scripts/_test/self-claims.py`,
`scripts/_test/drift-detection.sh` and `INSTALLATION.md` did not change. Neither install script was
executed, and `check-marketplace.py` was not run at this pass.

Re-verified per-path from `8d447a7d` to `fc54def6` for T-0005 (`8d447a7d` is T-0008's pre-rebase
commit; T-0008 landed as `95120430`/`768a747a`): of the cited paths only
`.claude-plugin/marketplace.json` (crew `version` `:218`, now 1.0.41; the `:217` description is
unchanged), `plugin/PLUGINS.md` (`:14` version; `:17` Registers row unchanged),
`plugin/crew/BUDGETS.md` (marker still `:10`; the `:11` figure re-measured, now 18,006 lines, 120
files), `plugin/crew/README.md` (the cloud-guard environments section added above the command
table; the `34 commands` claim moved `:2178` -> `:2217` and `4 agents` `:2189` -> `:2228`, both
re-read and still true) and `TODO.md` changed. Both install scripts, `README.md` and
`scripts/check-marketplace.py` did not change, so their citations stand.

## Re-anchor provenance - `fc54def6` -> `2170d72e`, 2026-09-26 (T-0005 review round 2)

`git diff --name-only fc54def6 2170d72e -- <the paths this note cites>` returns only what round 2
changed: `plugin/crew/README.md` (one table row rewritten in place at `:971`, no line added or
removed, so `:2217` and `:2228` hold; re-read) and `plugin/crew/BUDGETS.md` (the `:11`
figure re-measured, now 18,009 lines, 120 files). The install scripts, `README.md` and
`scripts/check-marketplace.py` did not change.

## Re-anchor provenance - `2170d72e` -> `3a57b2d2`, 2026-09-26 (T-0005 rounds 3-4 and Step 8)

`git diff --name-only 2170d72e 3a57b2d2 -- <the paths this note cites>` returns only
`plugin/crew/README.md` (the cloud-guard section gained the allowlist paragraph, 21 lines above
the command table, so the `34 commands` claim moved `:2217` -> `:2238` and `4 agents` `:2228` ->
`:2249`; both re-read and still true) and `plugin/crew/BUDGETS.md` (marker still `:10`; the `:11`
figure re-measured, now 18,050 lines, 120 files). The version files are byte-identical to
`2170d72e` (crew 1.0.41 was stepped back and re-set). The install scripts, `README.md` and
`scripts/check-marketplace.py` did not change.

## Re-anchor provenance - `3a57b2d2` -> `1e210476`, 2026-09-26 (T-0005 Step 9)

`git diff --name-only 3a57b2d2 1e210476 -- <the paths this note cites>` returns
`plugin/crew/README.md` (the cloud-guard allowlist paragraph gained seven lines above the command
table, so the `34 commands` claim moved `:2238` -> `:2245` and `4 agents` `:2249` -> `:2256`; both
re-read and still true) and `plugin/crew/BUDGETS.md` (marker still `:10`; the `:11` figure
re-measured, now 18,061 lines, 120 files, which `check-marketplace.py` verifies). The version files
are byte-identical to `3a57b2d2` (crew stepped back to 1.0.37 and re-set to 1.0.41). The install
scripts, `README.md` and `scripts/check-marketplace.py` did not change.

## Re-anchor provenance - `1e210476` -> `aa7f9841`, 2026-09-26 (T-0005 review round 5)

`git diff --name-only 1e210476 aa7f9841 -- <the paths this note cites>` returns
`plugin/crew/README.md` (a round-5 paragraph of fifteen lines added to the cloud-guard section, so
the `34 commands` claim moved `:2245` -> `:2260` and `4 agents` `:2256` -> `:2271`; both re-read
and byte-identical to the old lines; `:12`, `:414` and `:736` are above the hunk and hold) and
`plugin/crew/BUDGETS.md` (marker still `:10`; the `:11` figure re-measured, now 18,082 lines, 120
files, which `check-marketplace.py` verifies). The version files are byte-identical to `1e210476`
(crew stepped back to 1.0.37 and re-set to 1.0.41). The install scripts and
`scripts/check-marketplace.py` did not change.

## Re-anchor provenance - `aa7f9841` -> `a26ad8c0`, 2026-09-26 (T-0005 Step 10)

`git diff --name-only aa7f9841 a26ad8c0 -- <the paths this note cites>` returns
`plugin/crew/README.md` (the cloud-guard section's round-5 paragraph rewritten and a "What the
guard does not catch" subsection added, 44 lines net above the command table, so the `34
commands` claim moved `:2260` -> `:2304` and `4 agents` `:2271` -> `:2315`; both re-read and
byte-identical to the old lines; `:12`, `:414` and `:736` are above the first hunk, at `:1038`,
and hold) and `plugin/crew/BUDGETS.md` (marker still `:10`; the `:11` figure re-measured, now
18,157 lines, 120 files, which `check-marketplace.py` verifies). The version files are
byte-identical to `aa7f9841` (crew stepped back to 1.0.37 and re-set to 1.0.41). The install
scripts and `scripts/check-marketplace.py` did not change.

## Re-anchor provenance - `6f96e627` + `a26ad8c0` -> `2b18f7ab`, 2026-09-26 (T-0005 landing)

`2b18f7ab` is the crew 1.0.42 bump on top of `4ed4b763`, the merge of T-0005 (`4e0abc8f`) into
main at `1e0706ac`. Both lines' provenance is above, side by side. A citation can only be wrong at
the merge when its file changed on both sides, or when a line from one side cites a file the other
side changed; each such citation was re-mapped with a line diff of the cited file and re-read with
`grep -n`/`sed -n` on the merged tree. The bump commit replaced `1.0.41` with `1.0.42` in place in
the version files and in T-0005's own version statements (no line added or removed, except one
line in `CHANGELOG.md`'s T-0005 bump note).

Of the paths this note cites, `.claude-plugin/marketplace.json` (`:218` 1.0.42; `:217` is main's,
35 commands), `plugin/PLUGINS.md` (`:14` 1.0.42; the `:17` Registers row reads 4 agents, 35
commands, 29 skills, matching disk), `plugin/crew/BUDGETS.md` (marker `:10`; 18,494 lines across
121 files, re-measured on the merge), `plugin/crew/README.md` (both sides' additions; the
`35 commands` claim is at `:2381` and `4 agents` at `:2392`, re-grepped) and `TODO.md` changed.
Neither install script changed on T-0005's side, `README.md` and `scripts/check-marketplace.py` did
not change on either, so their citations stand. Neither install script was executed.

## Re-anchor provenance - T-0042's branch line, `6f96e627` -> `068db4ff` -> `07eefac5`, 2026-09-26

Re-verified per-path from `6f96e627` to `068db4ff` for T-0042 (auto-resume round 4, crew 1.0.42).
`6f96e627` is T-0004's landing and `git diff --name-only 6f96e627 1e0706ac` returns refresh
artifacts only. Of the cited paths, `git diff --name-only 1e0706ac 068db4ff` returns
`.claude-plugin/marketplace.json` (crew `version` `:218`, now 1.0.42; the `:217` description is
unchanged), `plugin/PLUGINS.md` (`:14` version only; the `:17` Registers row is unchanged),
`plugin/crew/BUDGETS.md` (marker still `:10`; `:11` now reads 18,253 lines across 121 files, and
`git ls-files -z 'plugin/crew/*.md' | xargs -0 cat | wc -l` returns 18253), `plugin/crew/README.md`
(auto-resume prose added above the claims, so the `35 commands` claim moved `:2255` -> `:2269` and
`4 agents` `:2266` -> `:2280`, re-grepped; `ls plugin/crew/commands/*.md` is 35,
`ls plugin/crew/agents/*.md` is 4, `ls -d plugin/crew/skills/*/` is 29) and `TODO.md` (no live
`TODO.md:<n>` claim here). Both install scripts, `README.md`, `plugin/README.md`, `INSTALLATION.md`,
`hooks.json`, `scripts/check-marketplace.py` and `scripts/_test/self-claims.py` did not change, so
their citations stand; the README pin is exactly as stale as it was at `6f96e627`. Neither install
script was executed; `check-marketplace.py` was run at `068db4ff` and passed.

## Re-anchor provenance - `2b18f7ab` + `068db4ff` -> `53f5482c`, 2026-09-27 (T-0042 merges main)

`53f5482c` is T-0042's rule-26 re-measure on top of the merge of origin/main `502cb137` into its
branch (`b7727a88`) and the crew 1.0.43 bump (`52778dd1`). Of the cited paths,
`git diff --name-only 2b18f7ab 53f5482c` returns `.claude-plugin/marketplace.json` (`:218` 1.0.43;
`:217` unchanged), `plugin/PLUGINS.md` (`:14` 1.0.43; the `:17` Registers row unchanged),
`plugin/crew/BUDGETS.md` (marker `:10`; 18,571 lines across 121 files, re-measured on the merge),
`plugin/crew/README.md` (T-0042's auto-resume prose above the claims, so the `35 commands` claim
moved `:2381` -> `:2395` and `4 agents` `:2392` -> `:2406`, re-grepped) and `TODO.md`. Neither
install script, `README.md`, `scripts/check-marketplace.py` nor `scripts/_test/self-claims.py`
changed on either side since `2b18f7ab`, so their citations stand. Neither install script was
executed.

Re-verified per-path from `8d447a7d` to `7b667587` for T-0021 (T-0034's `c35edda5` in between):
of the cited paths `.claude-plugin/marketplace.json` (crew `version` `:218`, now 1.0.46; `:217`
unchanged), `plugin/PLUGINS.md` (`:14` version; `:17` unchanged), `plugin/crew/BUDGETS.md`
(marker still `:10`; the `:11` figure now 17,989 lines across 125 files), `plugin/crew/README.md`
(section 13c rewritten, +34 lines above the command table, so the `34 commands` claim moved
`:2178` -> `:2212` and `4 agents` `:2189` -> `:2223`; both still hold, `ls plugin/crew/commands/*.md`
is 34), and `TODO.md` changed. Both install scripts, the root `README.md` and
`scripts/check-marketplace.py` did not, so their citations stand.

Re-verified per-path from `7b667587` to `385eadd5` for T-0021's review round 1. `git diff --name-only 7b667587 385eadd5` returns T-0021's refresh (`bc6432b1`), the version step-back (`764c2244`) and review round 1's fix commit (`385eadd5`): `CHANGELOG.md`, `TODO.md`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `brainstorm.md`, `obsidian-sync.md`, `crew_tracker.py` and three test files, plus the refresh's own artifacts. The version files net to no change (1.0.46 stepped back and re-set).
Of the cited paths: `plugin/crew/BUDGETS.md` (marker still `:10`; the `:11` figure now 18,007
lines across 125 files, re-measured with `git ls-files 'plugin/crew/*.md' | xargs cat | wc -l`)
and `plugin/crew/README.md` (the tracker paragraph grew by 7 lines above the command table, so
the `34 commands` claim moved `:2212` -> `:2219` and `4 agents` `:2223` -> `:2230`, re-grepped;
both still hold, `ls plugin/crew/commands/*.md` is 34). `marketplace.json` and `PLUGINS.md` net
to no change. Both install scripts, the root `README.md` and `scripts/check-marketplace.py` did
not change, so their citations stand.

Re-verified per-path from `385eadd5` to `bcb77ce2` for T-0021's review round 2. `git diff --name-only 385eadd5 bcb77ce2` returns the round-1 refresh (`59de6d56`), the version step-back (`f11c72d0`) and review round 2's fix commit (`bcb77ce2`): `CHANGELOG.md`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `fix.md`, `implement.md`, `jira-sync.md`, `sdp-sync.md`, `crew_tracker.py` and three test files, plus the refresh's own artifacts. The version files net to no change (1.0.46 stepped back and re-set).
Of the cited paths: `plugin/crew/BUDGETS.md` (marker still `:10`; the `:11` figure now 18,044
lines across 125 files, re-measured with `git ls-files 'plugin/crew/*.md' | xargs cat | wc -l`)
and `plugin/crew/README.md` (section 13c grew by 25 lines above the command table, so the
`34 commands` claim moved `:2219` -> `:2244` and `4 agents` `:2230` -> `:2255`, re-grepped; both
still hold, `ls plugin/crew/commands/*.md` is 34). Both install scripts, the root `README.md`
and `scripts/check-marketplace.py` did not change, so their citations stand.

## Re-anchor provenance - `2b18f7ab` + `bcb77ce2` -> `c2ae46ab`, 2026-09-27 (T-0021 review round 3 and its merge of main)

The merge `86ea912f` joins main's `2b18f7ab` with T-0021's `bcb77ce2`; review round 3's fix commit
`629fb518` sits under it and the crew 1.0.43 bump `c2ae46ab` on top. `git diff --name-only 2b18f7ab
c2ae46ab` returns only T-0021's files (its code, commands, tests, fixtures, release files,
`.crew/verify.json`, `CHANGELOG.md`, `TODO.md`). Every citation in this note's body into those files
was re-mapped from the side of the merge its line came from (`git blame`: main's lines against
`2b18f7ab`, T-0021's against `bcb77ce2`) with a line diff, and each one whose line moved or changed
was re-read at `c2ae46ab`. Of the cited paths `.claude-plugin/marketplace.json` (crew `version`
`:218`, now 1.0.43; `:217` unchanged), `plugin/PLUGINS.md` (`:14` version; `:17` unchanged),
`plugin/crew/BUDGETS.md` (marker still `:10`; `:11` now 18,713 lines across 126 files) and
`plugin/crew/README.md` changed; both install scripts, the root `README.md` and
`scripts/check-marketplace.py` did not, so their citations stand. No test suite was executed
for this note.

## Re-anchor provenance - `c2ae46ab` -> `d276b268`, 2026-09-27 (T-0021 review round 4)

`git diff --name-only c2ae46ab d276b268` returns T-0021's test-escape and round-4 files:
`crew_tracker.py`, `brainstorm.md`, `fix.md`, three test files, `plugin/crew/README.md`,
`CHANGELOG.md`, `TODO.md` (one follow-up appended at `:5080`), two crew guides with their built
outputs, and the version files (stepped to 1.0.42 and re-set to 1.0.43 twice, net unchanged, so
crew's `version` at `.claude-plugin/marketplace.json:218` and `plugin/PLUGINS.md:14` still read
1.0.43). Of the cited paths only `plugin/crew/README.md` changed: section 13c's "Whose card"
paragraph grew by 9 lines above the command table, so the `35 commands` claim moved `:2457` ->
`:2466` and `4 agents` `:2468` -> `:2477` (re-grepped; `ls plugin/crew/commands/*.md` is 35).
Both install scripts, the root `README.md` and `scripts/check-marketplace.py` did not change, so
their citations stand. No test suite was executed for this note.

## Re-anchor provenance - `f0b12ee6` + `74f52fae` -> `12682e41`, 2026-09-27 (T-0021 lands on T-0042's main)

`6df1231a` merges T-0021's reviewed head `74f52fae` into main `f0b12ee6` (T-0042 landed as crew
1.0.43, PR #242), and `12682e41` bumps crew to 1.0.44. The two sides share no source file: the
paths both changed since `502cb137` are `CHANGELOG.md`, `TODO.md`, `.crew/verify.json`,
`plugin/crew/README.md`, `plugin/crew/CONFIG.md`, `plugin/crew/BUDGETS.md`, the version files and
the refresh artifacts. The conflicting provenance sections keep both sides, T-0042's first. Every
`path:N` citation in the body, and every bare `:N` that follows a path, was mapped from the side
its line came from onto the merged tree with a line diff (`git show <side>:<path>` against the
merge); each one that moved was re-read with `sed -n` on the merge and corrected. Of the cited
paths, `.claude-plugin/marketplace.json` (`:218` 1.0.44; `:217` unchanged), `plugin/PLUGINS.md`
(`:14` 1.0.44; `:17` unchanged), `plugin/crew/BUDGETS.md` (marker `:10`; `:11` 18,800 lines
across 126 files, recomputed on the merge) and `plugin/crew/README.md` changed: the `35
commands` claim is now `:2480` and `4 agents` `:2491` (re-grepped; `ls plugin/crew/commands/*.md`
is 35). Both install scripts, the root `README.md` and `scripts/check-marketplace.py` did not
change on either side, so their citations stand. Neither install script was executed.

## Re-anchor provenance - `6f96e627` -> `eba11657`, 2026-09-26 (T-0023)

Re-verified per-path from `6f96e627` to `eba11657` for T-0023 (plain-text lifecycle routing,
crew 1.0.42); `6f96e627` -> `1e0706ac` touched only refresh artifacts. Of the cited paths,
`git diff --name-only 1e0706ac eba11657` returns `.claude-plugin/marketplace.json` (crew `version`
`:218`, now 1.0.42; the `:217` description is unchanged), `plugin/PLUGINS.md` (`:14` version; the
`:17` Registers row unchanged - no command, agent or skill was added) and `plugin/crew/README.md`
(a 23-line "Plain-text lifecycle" subsection inserted before "Measuring 1.0", so the `35 commands`
claim moved `:2255` -> `:2278` and `4 agents` `:2266` -> `:2289`, re-grepped). Neither install
script, `scripts/check-marketplace.py`, `INSTALLATION.md` nor `plugin/README.md` changed.
`plugin/crew/BUDGETS.md` did not change either, and that is now a defect: its `:11` figure still
reads 18,176 while `git ls-files 'plugin/crew/*.md' | xargs cat | wc -l` returns 18239, so
`check-marketplace.py` fails on it - BUDGETS.md is outside T-0023's Touch and was left for the
owner. Neither install script was executed.

## Re-anchor provenance - `2b18f7ab` + `488053fc` -> `a1acd9b7`, 2026-09-27 (T-0023 merge of main)

`3c968175` merges main at `502cb137` (T-0005 landed, its notes anchored `2b18f7ab`) into T-0023 at
`488053fc` (review round 1's fixes); `f6abe8c1` re-sets crew to 1.0.43 and `a1acd9b7` re-prices
`.crew/verify.json` rule 28 in place. Both lines' provenance is above. A citation can only be
wrong at the merge when its file changed on both sides, or when a line from one side cites a file
the other side changed. Each line of this note was classified by origin (main's text or
T-0023's), its citations into such files re-mapped with a line diff from that side's revision to
the merged tree (`502cb137` or `fa4d8cd5`), and each moved one re-read by content with
`grep -n`/`sed -n`; citations the line diff attributed to the wrong file were discarded, not
applied. Of the paths this note cites, `plugin/crew/README.md` changed on both sides (the `35 commands` claim is at `:2404` and `4 agents` at `:2415`, re-grepped) and the version files moved to 1.0.43 in place. `plugin/crew/BUDGETS.md`'s marked total is re-measured and `check-marketplace.py` passes on it; the defect T-0023's `eba11657` pass recorded above is closed. Neither install script, `scripts/check-marketplace.py` nor `INSTALLATION.md` changed.

## Re-anchor provenance - `db14619c` + `ad74ed35` -> `e463ca53`, 2026-09-27 (T-0023 lands on T-0021's main)

`c68b40bd` merges origin/main `db14619c` (T-0042 landed as crew 1.0.43, PR #242; T-0021 as
1.0.45, PR #243) into T-0023's `ad74ed35`, and `e463ca53` bumps crew to 1.0.46. The files both
sides changed since `502cb137` are `CHANGELOG.md`, `.crew/verify.json`, `plugin/crew/README.md`,
`plugin/crew/CONFIG.md`, `plugin/crew/BUDGETS.md`, `plugin/crew/hooks/scripts/crew_context.py`,
`plugin/crew/tests/sabotage.py`, the version files and the refresh artifacts. The conflicting
provenance sections keep both sides, main's first. Every `path:N` citation in the body, and every
bare `:N` that follows a path, was mapped from the side its line came from onto the merged tree
with a line diff (`git show <side>:<path>` against the merge); each one that moved was re-read
with `sed -n` and corrected, and hits the diff attributed to the wrong file (a bare `:N` after
an unrelated path) were discarded rather than applied. Of the cited
paths, `.claude-plugin/marketplace.json` (`:218` 1.0.46; `:217` unchanged), `plugin/PLUGINS.md`
(`:14` 1.0.46; `:17` unchanged) and `plugin/crew/BUDGETS.md` (marker `:10`; `:11` 18,864 lines
across 126 files, recomputed on the merge) changed. `plugin/crew/README.md` changed on both
sides: its `35 commands` claim is now `:2503` and `4 agents` `:2514` (re-grepped;
`ls plugin/crew/commands/*.md` is 35). Both install scripts, the root `README.md` and
`scripts/check-marketplace.py` did not change on either side, so their citations stand.
Neither install script was executed.

Re-verified per-path from `6f96e627` to `5536c2c8` for T-0018 (`/crew:autopilot status` and the
router, crew 1.0.42): of the cited paths `.claude-plugin/marketplace.json` (crew `version` `:218`,
now 1.0.42; `:217` unchanged), `plugin/PLUGINS.md` (`:14` version; `:17` unchanged),
`plugin/crew/BUDGETS.md` (marker still `:10`; `:11` now reads 18,170 lines across 121 files, and
`git ls-files 'plugin/crew/*.md' | xargs cat | wc -l` returns 18170) and `plugin/crew/README.md`
(14 lines added in the autopilot section above the command table: the `35 commands` claim is now
at `:2269` and `4 agents` at `:2280`, re-grepped) changed. `plugin/crew/commands/` has one file
edited and none added (`ls plugin/crew/commands/*.md` still 35). Both install scripts, `README.md`,
`plugin/README.md`, `INSTALLATION.md` and `scripts/check-marketplace.py` did not change, so their
citations stand. Neither install script was executed; `check-marketplace.py` passed at this pass.

Re-verified per-path from `5536c2c8` to `4ff7e764` (T-0018 review round 1): of the cited paths only
`plugin/crew/README.md` changed, two lines edited in place in the autopilot section, none added or
removed, so the `35 commands` claim at `:2269` and `4 agents` at `:2280` hold (re-grepped), and
`git ls-files 'plugin/crew/*.md' | xargs cat | wc -l` still returns 18170, as `BUDGETS.md:11` says.
Both install scripts, `README.md`, `plugin/README.md`, `INSTALLATION.md` and
`scripts/check-marketplace.py` did not change. `check-marketplace.py` passed at `4ff7e764`.

Re-verified per-path from `2b18f7ab` (main) and `4ff7e764` (the T-0018 branch) to `b1ae1500`, the
T-0018 round-4 fixes, the merge of main `502cb137` (crew 1.0.42) and the crew 1.0.43 bump: of the
cited paths `.claude-plugin/marketplace.json` (crew `version` `:218`, now 1.0.43; `:217`
unchanged), `plugin/PLUGINS.md` (`:14` 1.0.43; the `:17` Registers row still reads 4 agents, 35
commands, 29 skills), `plugin/crew/BUDGETS.md` (marker still `:10`; `:11` now reads 18,489 lines
across 121 files, and `git ls-files 'plugin/crew/*.md' | xargs cat | wc -l` returns 18489 on the
merged index) and `plugin/crew/README.md` (T-0018's 15 autopilot lines above the command table on
top of main's, plus one table row edited in place: the `35 commands` claim is at `:2396` and
`4 agents` at `:2407`, re-grepped) changed. `git diff --name-only 2b18f7ab b1ae1500 -- scripts/
README.md INSTALLATION.md plugin/README.md` is empty, so both install scripts and the other
counting sites stand. Neither install script was executed.

Re-verified per-path from `b1ae1500` to `89f73d79` (T-0018 review round 5, the version step-back
and re-set): of the cited paths only `plugin/crew/README.md` changed, one line in the `status`
paragraph edited in place, none added or removed, so the `35 commands` claim at `:2396` and
`4 agents` at `:2407` hold (re-grepped), and `git ls-files 'plugin/crew/*.md' | xargs cat | wc -l`
still returns 18489, as `BUDGETS.md:11` says. The version files are byte-identical to
`b1ae1500`'s. Both install scripts, `README.md`, `plugin/README.md`, `INSTALLATION.md` and
`scripts/check-marketplace.py` did not change. Neither install script was executed;
`check-marketplace.py` passed at `89f73d79` (`marketplace: 34 skills, 5 plugins`).

## Re-anchor provenance - main's `53f5482c` -> `0c7f6b84`, 2026-09-27 (T-0018, merge of origin/main `f0b12ee6`)

`crew_refresh_check.py --root . --ticket T-0018` named this note after `11e8afe3` merged origin/main
`f0b12ee6` (T-0042, crew 1.0.43) into T-0018-router and `0c7f6b84` set crew 1.0.44 last. The merge
took main's anchor, so the check measured T-0018's own paths against it. The two sides changed no
source file in common. The files both sides changed are `.crew/verify.json`, `plugin/crew/README.md`,
`CHANGELOG.md`, `plugin/crew/BUDGETS.md` and the three version files. Every `path:line` citation into
them in this note was compared with the same line on each side and at `0c7f6b84`:

- `.crew/verify.json` - 28 rules, 306 lines. Against T-0018's side nothing moved (main's rule 26
  `seconds` and `why` changed in place), so rule 27 is still `:293-301`. Against main's side the
  autopilot rule adds one line after `:295`.
- `plugin/crew/README.md` - main added 14 lines at `:1762`, and T-0018 added 15 lines after `:790`.
  The only citation that moved, the runbook-index line, was recomputed in the merge (`:1959`).
- `CHANGELOG.md` - cited by name, apart from one historical citation that was already recorded as
  out of scope. `plugin/crew/BUDGETS.md:11` is 18,566 over 121 files, re-measured in the merge.
- Version files - `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json`
  and `plugin/PLUGINS.md:14` read 1.0.44 at `0c7f6b84`. They were 1.0.43 on both sides of the merge.

No suite was run by this note.

## Re-anchor provenance - `db14619c` + `e6b696fb` -> `fbc27b49`, 2026-09-27 (T-0018 lands on T-0021's main)

`515346b1` merges T-0018's reviewed head `e6b696fb` (review round 6 CLEAN) into main `db14619c`
(T-0021 landed as crew 1.0.44 and 1.0.45, PR #243), and `fbc27b49` bumps crew to 1.0.46. The two
sides share no source file: the paths both changed since `f0b12ee6` are `CHANGELOG.md`,
`.crew/verify.json`, `plugin/crew/README.md`, `plugin/crew/BUDGETS.md`,
`plugin/crew/tests/test_lifecycle_commands.py` (merged cleanly), the version files and the refresh
artifacts. The conflicting provenance sections keep both sides, main's (T-0021's) first. Every
`path:N` citation in the body, and every bare `:N` that follows a path, was mapped from the side
its line came from onto the merged tree with a line diff (`git show <side>:<path>` against the
merge); each one that moved was re-read with `sed -n` on `fbc27b49` and corrected.
Of the cited paths, `.claude-plugin/marketplace.json` (`:218` 1.0.46; `:217` unchanged),
`plugin/PLUGINS.md` (`:14` 1.0.46; `:17` unchanged), `plugin/crew/BUDGETS.md` (`:11` 18,795 lines
across 126 files, recomputed on the merge) and `plugin/crew/README.md` changed: the `35 commands`
claim is now `:2495` and `4 agents` `:2506` (re-grepped). Both install scripts, the root
`README.md` and `scripts/check-marketplace.py` did not change on either side, so their citations
stand. Neither install script was executed.

## Re-anchor provenance - `55f59b04` + `bebbb97f` -> `65bb3330`, 2026-09-27 (T-0018 lands on T-0023's main)

`f458e752` merges main `bebbb97f` (T-0023 landed as crew 1.0.46, PR #244) into T-0018-land,
which had merged T-0018's reviewed head `e6b696fb` into `db14619c` and been refreshed at
`55f59b04`; `65bb3330` re-bumps crew to 1.0.47. The two sides share no source file: T-0023
changed `crew_route.py`, `crew_context.py`, `crew_config.py`, `sabotage.py` and their tests, T-0018
`crew_autopilot.py`, `autopilot.md` and theirs; both changed `CHANGELOG.md`, `.crew/verify.json`
(merged cleanly: 30 rules, 323 lines), `plugin/crew/README.md` (merged cleanly),
`plugin/crew/BUDGETS.md`, the version files and the refresh artifacts. The conflicting provenance
sections keep both sides, main's (T-0023's) first. Every `path:N` citation in the body was mapped
from the side its line came from onto the merged tree with a line diff, and each one that moved was
re-read with `sed -n` on `65bb3330` and corrected.
Of the cited paths, `.claude-plugin/marketplace.json` (`:218` 1.0.47; `:217` unchanged),
`plugin/PLUGINS.md` (`:14` 1.0.47), `plugin/crew/BUDGETS.md` (`:11` 18,859 lines across 126 files,
recomputed on the merge) and `plugin/crew/README.md` changed. Both install scripts, the root
`README.md` and `scripts/check-marketplace.py` did not change on either side, so their citations
stand. Neither install script was executed.

Re-verified per-path from `6f96e627` to `a2802526` for T-0024 (group approval, crew 1.0.42): of the
cited paths `.claude-plugin/marketplace.json` (crew `version` `:218`, now 1.0.42; `:217` unchanged),
`plugin/PLUGINS.md` (`:14` version only), `plugin/crew/BUDGETS.md` (marker still `:10`; `:11` now
reads 18,200 lines across 121 files, re-measured and matching `check-marketplace.py`) and
`plugin/crew/README.md` (the "Scope and approval" section grew, so the `35 commands` claim is now at
`:2263` and `4 agents` at `:2274`, re-grepped; `ls plugin/crew/commands/*.md` is still 35) changed.
Neither install script, `README.md`, `INSTALLATION.md` nor `scripts/check-marketplace.py` changed,
so their citations stand. The README pin landmine still holds: `README.md:12` and `:18` read
`6c497a14`, and `git log 6c497a14..a2802526` over both scripts still returns only `ecf69e43`. T-0004
has since merged to `main` (`1e0706ac`), so the re-pin that bullet calls due after that merge is now
due and was not done by T-0024, whose Touch excludes `README.md`. Neither install script was
executed.

Re-verified per-path from `a2802526` to `f8671fdc` for T-0024's review round 1 and successor step 6
(crew 1.0.43, 1.0.44): of the cited paths `.claude-plugin/marketplace.json` (`:218` 1.0.44; `:217`
unchanged), `plugin/PLUGINS.md` (`:14` only), `plugin/crew/BUDGETS.md` (`:11`, 18,202 lines across
121 files, re-measured) and `plugin/crew/README.md` (group-approval prose only; the `35 commands`
claim `:2263` and `4 agents` `:2274` did not move, re-grepped) changed. Neither install script,
`README.md` nor `INSTALLATION.md` changed; the README pin landmine stands as recorded above.

Re-verified per-path from `f8671fdc` to `45345812` for T-0024's review round 3 (crew 1.0.45): of the
cited paths `.claude-plugin/marketplace.json` (`:218` only), `plugin/PLUGINS.md` (`:14` only) and
`plugin/crew/README.md` (two sentences edited in place; `:2263`/`:2274` hold) changed. Neither
install script, `README.md` nor `BUDGETS.md` changed.

## Re-anchor provenance - `65bb3330` + `474aea8b` -> `8de3c669`, 2026-09-27 (T-0024 lands on T-0018's main)

`affa22a5` merges T-0024's reviewed head `474aea8b` (review round 4 FINDINGS, owner-accepted) into
main `67caa4b8` (T-0018 landed as crew 1.0.47, PR #245), and `8de3c669` bumps crew to 1.0.48.
The two sides share no source file: T-0024 changed `approval_hook.py`, both approval-hook wrappers,
`crew_ticket.py`, `commands/approve.md` and their tests; both sides changed `CHANGELOG.md`,
`.crew/verify.json`, `plugin/crew/README.md` (merged cleanly), `plugin/crew/tests/sabotage.py`,
`plugin/crew/BUDGETS.md`, the version files and the refresh artifacts. The conflicting provenance
sections keep both sides, main's first.
This note cites `.crew/verify.json`, `plugin/crew/README.md` and `sabotage.py` by name only or
in its provenance history; `plugin/PLUGINS.md` `:14` now reads 1.0.48 and `plugin/crew/BUDGETS.md`
`:11` 18,885 lines across 126 files, both changed in place. No body citation moved. Nothing was
executed for this note.

## Re-anchor provenance - `2b18f7ab` -> `b5903601`, 2026-09-27 (T-0009 on 1.0.42)

`b5903601` is the crew 1.0.43 bump on T-0009's branch, after the merge of main `502cb137` (T-0005 landed as 1.0.42) into it at `0c911558`. Main's code is `2b18f7ab` (main's later commit `45109fa1` touched only artifacts), so `git diff {OLD} {NEW}` is T-0009's change plus the bump. Of the paths this note cites, `.claude-plugin/marketplace.json` (`:218` 1.0.43; `:217`
unchanged), `plugin/PLUGINS.md` (`:14` 1.0.43; `:17` unchanged), `plugin/crew/BUDGETS.md` (marker
`:10`; 18,616 lines across 121 files, re-measured in the bump commit) and `plugin/crew/README.md`
(T-0009's rows and paragraph, 42 lines net above the command table, so the `35 commands` claim
moved `:2381` -> `:2423` and `4 agents` `:2392` -> `:2434`, both re-read, same text) changed. The
install scripts, `README.md`, `TODO.md` and `scripts/check-marketplace.py` did not change. Neither
install script was executed.

## Re-anchor provenance - `b5903601` -> `995b5874`, 2026-09-27 (T-0009 review round 1)

`995b5874` re-sets crew 1.0.43 as the last plugin/crew commit after T-0009's review-round-1 fix commit `7efb0f1d` (which stepped the version back to 1.0.42). Of the paths this note cites, `plugin/crew/BUDGETS.md` (marker `:10`; 18,639 lines across
121 files, re-measured in the re-set commit) and `plugin/crew/README.md` (6 lines net above the
command table, so the `35 commands` claim moved `:2423` -> `:2429` and `4 agents` `:2434` -> `:2440`,
both re-read, same text) changed; `.claude-plugin/marketplace.json` and `plugin/PLUGINS.md` read
1.0.43 again, as at `b5903601`. The install scripts, `README.md`, `TODO.md` and
`scripts/check-marketplace.py` did not change.

## Re-anchor provenance - `995b5874` -> `20e9b396`, 2026-09-27 (T-0009 dispatch grammar)

`b5e55fb7` builds T-0009's dispatch grammar (the successor plan after review round 2); `20e9b396` re-sets crew 1.0.43 as the last plugin/crew commit. Of the paths this note cites, `plugin/crew/README.md`
(20 lines net above the command table, so the `35 commands` claim moved `:2429` -> `:2449` and
`4 agents` `:2440` -> `:2460`, both re-read, same text) and `plugin/crew/BUDGETS.md` (marker `:10`;
18,702 lines across 121 files, re-measured in the re-set commit) changed; `.claude-plugin/marketplace.json`
and `plugin/PLUGINS.md` read 1.0.43, as at `995b5874`. The install scripts, `README.md`, `TODO.md` and
`scripts/check-marketplace.py` did not change.

## Re-anchor provenance - `20e9b396` -> `c1f22bc2`, 2026-09-27 (T-0009 review round 3)

`d8d1da86` fixes T-0009 review round 3 (Codex, 4 BLOCK + 1 FIX); `c1f22bc2` re-sets crew 1.0.43 as the last plugin/crew commit. Of the paths this note cites, `plugin/crew/README.md` (+6 lines above the command
table, so the `35 commands` claim moved `:2449` -> `:2455` and `4 agents` `:2460` -> `:2466`, both
re-read, same text) and `plugin/crew/BUDGETS.md` (marker `:10`; 18,720 lines across 121 files,
re-measured in the re-set commit) changed; `.claude-plugin/marketplace.json` and
`plugin/PLUGINS.md` read 1.0.43, as at `20e9b396`. The install scripts, `TODO.md` and
`scripts/check-marketplace.py` did not change.

## Re-anchor provenance - `c1f22bc2` + `e463ca53` -> `657d3d9b`, 2026-09-27 (T-0009 merges main `bebbb97f`)

`638e7ae5` merges origin/main `bebbb97f` (T-0042 landed as crew 1.0.43, T-0021 as 1.0.44 and 1.0.45, T-0023 as 1.0.46; main's notes anchored `e463ca53`) into T-0009 at `bb398e4c` (its notes anchored `c1f22bc2`), and `657d3d9b` sets crew 1.0.47 as the last plugin/crew commit, changing only the version files and T-0009's CHANGELOG entry in place (its line count unchanged). The source files both sides changed since `502cb137` are `CHANGELOG.md`, `.crew/verify.json`, `plugin/crew/CONFIG.md`, `plugin/crew/README.md`, `plugin/crew/BUDGETS.md`, `plugin/crew/hooks/scripts/crew_config.py`, `plugin/crew/skills/crew-setup/SKILL.md`, both config templates, `plugin/crew/tests/test_crew_config.py`, `docs/guides/crew/src/troubleshooting.md` and the version files. The conflicting provenance sections keep both sides, main's first. Every `path:N` citation in the body, and every bare `:N` that follows a path, was mapped from the side its line came from onto the merged tree with a line diff (`git show <side>:<path>` against the merge); each one that moved was re-read with `sed -n` or `grep -n`, and hits the diff attributed to the wrong file (a bare `SKILL.md`, the root `README.md`) were discarded rather than applied. Of the paths this note cites, `plugin/crew/BUDGETS.md` (marker still `:10`; 19,090 lines across 126 files on the merged tree), `plugin/PLUGINS.md` (`:14` 1.0.47; `:17` unchanged) and `.claude-plugin/marketplace.json` (`:218` 1.0.47; `:217` unchanged) changed; no body citation moved. Neither install script changed on either side and neither was executed.

## Re-anchor provenance - `657d3d9b` + `65bb3330` -> `3cf1eea2`, 2026-09-27 (T-0009 merges main `67caa4b8`)

`1f4f9082` merges origin/main `67caa4b8` (T-0018 landed as crew 1.0.47, PR #245; main's notes anchored `65bb3330`) into T-0009 at `055c5fae` (its notes anchored `657d3d9b`), and `3cf1eea2` sets crew 1.0.48 as the last plugin/crew commit, changing only the version files and T-0009's CHANGELOG heading and bump line in place. The two sides share no source file: T-0018 changed `crew_autopilot.py`, `commands/autopilot.md` and their tests, T-0009 the cloud guard, config and docs; both changed `CHANGELOG.md`, `.crew/verify.json` (merged cleanly: 30 rules, 323 lines), `plugin/crew/README.md` (merged cleanly), `plugin/crew/BUDGETS.md` (19,085 lines across 126 files, recomputed on the merged index), `plugin/PLUGINS.md`, the version files and the refresh artifacts. The conflicting provenance sections keep both sides, main's first. Every `path:N` citation in the body, and every bare `:N` that follows a path on the same line, was mapped from the side its line came from onto the merged tree with a line diff (`git show <side>:<path>` against `3cf1eea2`); the only ones that moved are the ones named below, each re-read with `sed -n` or `grep -n`. Of the paths this note cites, `.claude-plugin/marketplace.json` (`:218` 1.0.48; `:217` unchanged), `plugin/PLUGINS.md` (`:14` 1.0.48; `:17` unchanged), `plugin/crew/BUDGETS.md` (marker still `:10`; `:11` 19,085 lines across 126 files) and `plugin/crew/README.md` changed: the `35 commands` claim is now `:2592` and `4 agents` `:2603` (`:2577`/`:2588` at `657d3d9b`, `:2518`/`:2529` at `67caa4b8`; re-grepped, same text). `git diff --name-only` of either side against the merge over `scripts/`, the root `README.md`, `INSTALLATION.md` and `plugin/README.md` is empty, so both install scripts and the other counting sites stand. Neither install script was executed.

## Re-anchor provenance - `3cf1eea2` + `8de3c669` -> `314fb065`, 2026-09-27 (T-0009 review round 4, merges main `d2fbd408`)

`0b9e3a41` builds T-0009's review-round-4 successor (Steps 6-9: the PowerShell launcher rule, the same-command rule, bash alias copies); `e3088f2c` merges origin/main `d2fbd408` (T-0024 landed as crew 1.0.48, PR #246; main's notes anchored `8de3c669`) into it; `314fb065` sets crew 1.0.49 as the last plugin/crew commit, changing only the version files and T-0009's CHANGELOG heading and bump line in place. Source files both sides changed: `CHANGELOG.md`, `.crew/verify.json` (merged cleanly: 31 rules, 332 lines), `plugin/crew/README.md` (merged cleanly), `plugin/crew/BUDGETS.md` (19,147 lines across 126 files, recomputed on the merged index), `plugin/PLUGINS.md` and the version files. The conflicting provenance sections keep both sides, main's first. Every `path:N` citation in the body was mapped from the side its line came from (`8de3c669` for main's lines, `3cf1eea2` for T-0009's) onto `314fb065` with a line diff; a citation whose line the diff could not carry was re-read with `sed -n`/`grep -n`. No body citation moved: both install scripts, the root `README.md` and `scripts/check-marketplace.py` changed on neither side. Nothing was executed for this note.
