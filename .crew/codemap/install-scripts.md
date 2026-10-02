# install-scripts
anchor: useful-claude-add-ons@d6e51bb8
verified: 2026-10-02

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
- `scripts/install-prerequisites.sh:2745` — `install_web_testing`, the new
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
- `scripts/install-prerequisites.sh:2469` — `run_skill_preflights`, unchanged
  in behaviour (report-only, `</dev/null` stdin, UNCHECKED-not-absent
  wording all re-read and confirmed byte-identical in substance).  PowerShell
  twin `Invoke-SkillPreflights` at `scripts/install-prerequisites.ps1:2104`.
- `scripts/_test/drift-detection.sh:21` / `:82` — unchanged (byte-identical
  since `5d1fc5fd`, closed by the per-path check, not re-read).
- `scripts/_test/self-claims.py:1227` — `main()` (was `:1166`; file grew
  1382 -> 1458 lines, +76, adding `run_markdown_lines` and
  `CASES_MARKDOWN_LINES`, a fixture for `check_self_claims`'s new
  `crew-markdown-lines` claim kind — that claim kind and its
  `count_crew_markdown_lines` counter live in `scripts/check-marketplace.py`
  and are consumed by `plugin/crew/BUDGETS.md:10`, outside this note's scope;
  `marketplace-registration.md` owns `check-marketplace.py`'s function map).
- `scripts/install-prerequisites.sh:3357` / `:3506` — the `lsp-plugins` and
  `stack-tools` rows are dispatched as top-level `if is_selected "..."` blocks
  near the end of the script's execution flow, not named functions the way
  every other row is. PowerShell equivalents at
  `scripts/install-prerequisites.ps1:2979` / `:3166`, same shape
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
  (`scripts/install-prerequisites.sh:2745-2841`,
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

- **`README.md`'s install-URL pin is current at this anchor.** `README.md:12`
  and `:18` read `04dde5a228f0c29e5009691a655bcc38b3d9d48d` (re-pinned by `b78d3041` after W-0120
  merged as `04dde5a2`; re-read at `d6e51bb8`), and `git log --oneline 04dde5a2..d6e51bb8 --
  scripts/install-prerequisites.sh scripts/install-prerequisites.ps1` is empty. DERIVED. (Before
  that the pin read `f7caa37d2cfc694330c3cf2b305592ff473e3194`, re-pinned by
  `767fa3ef` after L-0561 merged as `f7caa37d`; re-read at `fe524012`), and
  `git log --oneline f7caa37d..fe524012 -- scripts/install-prerequisites.sh
  scripts/install-prerequisites.ps1` is empty. DERIVED. (At `ea764992` the pin
  read `e878cc31e00a7acb480fc17dd8afdcaf40c91f2d`, re-pinned by `17d057db`.) The history below is
  what the bullet said at earlier anchors: the pin was STALE there, by one
  line per script. `README.md:12` and `:18` still read
  `6c497a14fc06612732241d2b13eee4fea41996f5` (re-read at `07ca3972`), but
  `git log --oneline 6c497a14..e95e5964 -- scripts/install-prerequisites.sh
  scripts/install-prerequisites.ps1` now returns `ecf69e43` (crew 1.0.41,
  T-0004) and `a77a42d6` (T-0075), and `git diff --stat` over the same range
  is still 1 line in each script: the crew `PLUGIN_NAME` / `PluginCatalog`
  label, `34 commands` -> `36 commands` (35 at T-0004, 36 at T-0075). So a
  `curl | bash` taken from the README runs scripts that differ from the ones
  this note describes only in that menu label. DERIVED (re-read at
  `e95e5964`). T-0004 merged without the re-pin, and T-0075 is not merged at
  this anchor (branch `T-0075-build`), so the re-pin is due after that merge,
  per CLAUDE.md's promotion step. It was
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
  merely re-synced.** All of the following read **4 agents, 36 commands** (34
  until `ecf69e43` added `/crew:autopilot`, 35 until T-0075 added
  `/crew:config-setup`; re-read at `e95e5964`) (or
  the plugin-level 31 skills (31 from T-0085's landing merge with #267's `crew-qa-standards`; 29 until T-0085 added `crew-standards`; at
  `22399a9c` `plugin/README.md:414` and `INSTALLATION.md:252` still say 29, outside
  T-0085's Touch, and `scripts/check-marketplace.py` fails on both; both read 30
  from `b82035e6`, the Touch amendment, and the check passes) / 34 hook
  entries across 8 events figures that go with them), checked directly rather than cross-quoted from one another:
  `.claude-plugin/marketplace.json`'s `crew` description (parsed with
  `json.load`); `plugin/PLUGINS.md:17`; `plugin/README.md:414`'s crew row;
  `plugin/crew/README.md`; `PLUGIN_NAME`'s crew row in both install scripts
  (`scripts/install-prerequisites.sh:1393`,
  `scripts/install-prerequisites.ps1:1175`). Independently re-derived from the
  filesystem rather than trusted: `ls plugin/crew/agents/*.md` = 4 (explorer,
  researcher, reviewer, security — no PM, no scribe: the roster cut this
  repo's own memory already names), `ls plugin/crew/commands/*.md` = 36,
  `ls -d plugin/crew/skills/*/` = 30, and `hooks.json` parsed with `json.load`
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
  `scripts/install-prerequisites.sh:1786-1795` and
  `scripts/install-prerequisites.ps1:1411-1418`, re-read line by line, same
  shape as the previous anchor: bash appends a one-character ellipsis and
  reserves 1; PowerShell appends `...` (three characters) and reserves 3,
  padding the result to `Width` — the comment at `:1412-1413` still records
  that reserving 1 there used to return `Width + 2`. The scroll indicator
  (`showing N-M of T`) still does not route through either clipper
  (`scripts/install-prerequisites.sh:1834`,
  `scripts/install-prerequisites.ps1:1489`) and is still bounded to a string
  short enough not to wrap at the still-40-column floor
  (`term_cols`, `scripts/install-prerequisites.sh:1708-1715`, the floor at
  `:1711`; `[Console]::WindowWidth -lt 40` inside `Test-PickerSupported` at
  `scripts/install-prerequisites.ps1:1378`). JUDGEMENT, unchanged: route it
  through the clipper anyway if that string ever grows.

- **`Test-PickerSupported` still refuses strictly more cases than bash's
  `picker_supported`,** re-read at this anchor
  (`scripts/install-prerequisites.ps1:1372-1385` vs
  `scripts/install-prerequisites.sh:1717-1726`): redirected input/output, no
  `RawUI`, the PowerShell ISE (`ReadKey` throws there), and
  `WindowHeight < 10 || WindowWidth < 40` all refuse on the PowerShell side;
  bash refuses no-tty, no `stty`, `TERM=dumb`, and fewer than 10 lines, but
  only *floors* (does not refuse on) narrow terminals via `term_cols`. Same
  asymmetry as the previous anchor, re-confirmed rather than assumed
  unchanged.

- **The skill preflights are still REPORT-ONLY, unchanged in every particular
  this note checks.** `run_skill_preflights`
  (`scripts/install-prerequisites.sh:2469`; PowerShell
  `Invoke-SkillPreflights` at `scripts/install-prerequisites.ps1:2104`) still
  runs each selected skill's own `preflight.py` with no `--install`, `</dev/null`
  on the bash side (load-bearing — an inherited console would turn a report
  into a prompt), and a missing interpreter is still reported as UNCHECKED,
  not absent, verbatim (`scripts/install-prerequisites.sh:2483`,
  `scripts/install-prerequisites.ps1:2115`).

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
  (`scripts/install-prerequisites.sh:1406-1408`); every PowerShell
  `PluginCatalog` row's `Selected` is still `$true`
  (`scripts/install-prerequisites.ps1:1175-1179`).

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

## Re-anchor provenance - T-0010-solo's branch line, `2b18f7ab` -> `50e67586`, 2026-09-27 (crew 1.0.43 on its branch)

T-0010's code commit was cherry-picked off `origin/main` (`502cb137`) as `0fc5b069`, apart from
T-0018 and T-0024, and the version set in `50e67586`. Every `path:line` citation this note makes into
a path T-0010 changed was mapped from the `2b18f7ab` tree with `difflib`; each one that moved
was re-pointed and compared line for line with the anchor tree at `50e67586`.

Of the cited paths only `plugin/crew/README.md` changed: T-0010's three lines sit above the
command table, so the `35 commands` claim moved `:2381` -> `:2384` and `4 agents` `:2392` ->
`:2395` (re-grepped). `plugin/crew/BUDGETS.md` (`:11`, 18,524 lines across 121 files,
re-measured), `plugin/PLUGINS.md:14` and `.claude-plugin/marketplace.json:218` (1.0.43) changed
in place. Neither install script, `README.md`, `INSTALLATION.md` nor
`scripts/check-marketplace.py` changed. `check-marketplace.py`: `all checks passed`.

## Re-anchor provenance - `53f5482c` + `50e67586` -> `89c9ee9a`, 2026-09-27 (T-0010-solo merges main, crew 1.0.44)

`89c9ee9a` is T-0010's crew 1.0.44 version commit on top of `132c1758`, the merge of origin/main
`f0b12ee6` (T-0042 landed at 1.0.43) into T-0010-solo. Both lines' provenance is above. Main-side
citations were mapped through `git diff origin/main 89c9ee9a`, the branch-side ones through
`git diff 708db116 89c9ee9a`, with `difflib` over every repo-relative `path:line` citation, and
every moved or merge-set one re-read with `sed -n` at `89c9ee9a`:

Of the cited paths, `plugin/crew/README.md` changed on both sides: T-0042's auto-resume prose and
T-0010's three lines both sit above the claims, so the `35 commands` claim is `:2398` and
`4 agents` `:2409` (re-grepped). `plugin/crew/BUDGETS.md` (marker `:10`; `:11` reads 18,601 lines
across 121 files, re-measured on the merge), `plugin/PLUGINS.md:14` and
`.claude-plugin/marketplace.json:218` (1.0.44) changed in place. Neither install script,
`README.md`, `INSTALLATION.md`, `scripts/check-marketplace.py` nor `scripts/_test/self-claims.py`
changed on either side. `python3 scripts/check-marketplace.py` at `89c9ee9a`: `all checks passed`.
Neither install script was executed.

## Re-anchor provenance - `89c9ee9a` -> `8314d670`, 2026-09-27 (T-0010 review round 1 fixes)

`8314d670` fixes the four FIX findings of T-0010's review round 1. Its citations were checked
per path through `git diff 89c9ee9a 8314d670`, every moved one re-read with `grep -n`/`sed -n`
at `8314d670`:

`plugin/crew/README.md` changed one line in place (T-0010's policy paragraph), so `:2398` and
`:2409` hold (re-grepped). `plugin/crew/BUDGETS.md` changed in place: marker `:10`, and `:11`
now reads 18,607 lines across 121 files (`check_self_claims` re-measured it). Neither install
script changed. Nothing was executed for this note beyond `scripts/check-marketplace.py`.

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

**Re-anchored `53f5482c` -> `d3a1c77e` on 2026-09-27 (T-0072, crew 1.0.44).** `d3a1c77e` is T-0072's version commit on `T-0072-build`, after it merged origin/main `f0b12ee6` (T-0042's landing) with a merge commit. `git diff --name-only 53f5482c d3a1c77e` over the cited paths returns only T-0072's changes and the version files. T-0072 edited in place, with no line added or removed, `crew_state.py` (`:1084-1090`, the `AUTOPILOT_DEFAULTS` comment and value), `plugin/crew/README.md` (the autopilot Settings paragraph), `plugin/crew/commands/autopilot.md` (`:19-20`), `plugin/crew/BUDGETS.md` (`:11`, now 18,612 lines across 121 files), `plugin/PLUGINS.md` (`:14` 1.0.44, the `/crew:autopilot` row), `.claude-plugin/marketplace.json` (`:218` 1.0.44), `plugin/crew/.claude-plugin/plugin.json` (`:3`) and `.crew/verify.json` (rule 27 `:293-300`, same lines). It added lines to `crew_autopilot.py` (the `deploy-allowed` docstring section and functions, 694 -> 837 lines), `CONFIG.md` (+1 at the leaf paragraph, +1 in the key table, +1 in §20's table, a closing §20 section), `CHANGELOG.md` (+32 at the top) and the autopilot tests. Of the paths this note cites, `plugin/crew/README.md` (in place; the `35 commands`/`4 agents` claims did not move), `plugin/PLUGINS.md` (`:14` 1.0.44; `:17` unchanged), `plugin/crew/BUDGETS.md` (marker `:10`; `git ls-files 'plugin/crew/*.md' | xargs cat | wc -l` returns 18612, matching `:11`) and `.claude-plugin/marketplace.json` (`:218` 1.0.44) changed. Both install scripts did not.

**Re-anchored `d3a1c77e` -> `e30af7f9` on 2026-09-27 (T-0072 review round 1).** `e30af7f9` is T-0072's review-round-1 fix commit on `T-0072-build`. `git diff --name-only d3a1c77e e30af7f9` returns `.crew/verify.json` (rule 27's `why` re-measured in place, still `:293-300`), `CHANGELOG.md` (the 1.0.44 entry, four lines reworded, cited without a line), `plugin/crew/BUDGETS.md` (`:11`, now 18,615 lines across 121 files; `check-marketplace.py` prints `all checks passed`), `plugin/crew/CONFIG.md` (+3 lines in §20's closing section, at `:2317`; nothing cited above it moved, `:2251-2258` holds), `plugin/crew/hooks/scripts/crew_autopilot.py` (+24 lines: the docstring gains a line at `:88`, `_deploy_verdict` moves its `cloud_guard` import below the incident check, `_safe_text` and `_crash_reason` are new), `plugin/crew/tests/sabotage_autopilot.py` (+32: `CLOUD` at `:18`, six mutations) and `plugin/crew/tests/test_crew_autopilot_deploy.py`, plus the refresh artifacts of the previous pass. No crew version change (1.0.44). Of the paths this note cites, only `.crew/verify.json` changed, in place inside rule 27's `why`; every line it cites holds. Nothing else this note cites changed.

**Re-anchored `e463ca53` -> `715a8c2f` on 2026-09-27 (T-0072 merged onto `bebbb97f`, crew 1.0.47).** `715a8c2f` is T-0072's crew 1.0.47 version commit on `T-0072-build`, on top of `e658bb04`, its merge of origin/main `bebbb97f` (T-0021 and T-0023 landed; this note was anchored at T-0023's `e463ca53`). `git diff --name-only e463ca53 715a8c2f` over the cited paths returns only T-0072's changes, the neighbour test T-0072 added after the merge, and the version files. Against main, T-0072 edits in place, with no line added or removed, `crew_state.py` (`:1086-1090`, the `AUTOPILOT_DEFAULTS` comment and value), `plugin/crew/README.md` (`:843`, the autopilot Settings paragraph), `plugin/crew/commands/autopilot.md` (`:19-20`), `plugin/crew/BUDGETS.md` (`:11`, now 18,910 lines across 126 files), `plugin/PLUGINS.md` (`:14` 1.0.47, `:128` the `/crew:autopilot` row), `plugin/crew/skills/crew-setup/SKILL.md` (`:170`), `.claude-plugin/marketplace.json` (`:218` 1.0.47), `plugin/crew/.claude-plugin/plugin.json` (`:3`) and `.crew/verify.json` (rule 27 `:293-300`, same lines). It adds lines to `crew_autopilot.py` (694 -> 861), `CONFIG.md` (+3 at the leaf paragraph `:130`, +1 at `:803`, +1 at `:2282`, and the closing §20 section at `:2297`, 41 lines, with T-0023's §21 after it), `CHANGELOG.md` (+31 at `:7`, T-0072's entry above T-0023's), `config.template.json` (+1 at `:205`), `test_crew_config.py` (+3; the count assertion is `:282`, 123), `test_crew_autopilot.py` (+2), `sabotage_autopilot.py` (+140) and the new `test_crew_autopilot_deploy.py`. Of the paths this note cites, `plugin/crew/README.md` (in place at `:825`; the `35 commands`/`4 agents` claims did not move), `plugin/PLUGINS.md` (`:14` 1.0.47; `:17` holds), `plugin/crew/BUDGETS.md` (marker `:10`; `:11` reads 18,910, which `scripts/check-marketplace.py`'s `count_crew_markdown_lines` returns) and `.claude-plugin/marketplace.json` (`:218` 1.0.47; `:217` unchanged) changed. Neither install script changed. No install script was executed.

**Re-anchored `65bb3330` -> `21429244` on 2026-09-27 (T-0072 merged onto `67caa4b8`, crew 1.0.48).** `21429244` is T-0072's crew 1.0.48 version commit on `T-0072-build`, on top of `80d4073b`, its merge of origin/main `67caa4b8` (T-0018 landed; this note was anchored at T-0018's `65bb3330`, and nothing outside the refresh artifacts changed between `65bb3330` and `67caa4b8`). Main's side of this note was taken in the merge and T-0072's earlier refresh replayed on top (`git apply --3way` of `bebbb97f..b1ec6877`); every citation into a file either side changed was mapped with a line diff (main -> merged for main's text, `b1ec6877` -> merged for T-0072's) and each one that moved was re-read with `sed -n`. `git diff --name-only 65bb3330 21429244`, outside the refresh artifacts, returns only T-0072's files: `crew_autopilot.py` (1063 -> 1230 lines: the `deploy-allowed` docstring section and functions, and its parser at `:1140`), `CONFIG.md` (+56), `CHANGELOG.md` (+31 at the top), `commands/autopilot.md` (the settings sentence rewrapped at `:44-47`, still 100 lines), `crew_state.py` (line-neutral at `:1086-1090`), `config.template.json`, `crew-setup/SKILL.md` (`:170`), `.crew/verify.json` (rule 27 `:293-301`, same lines: `test_crew_autopilot_deploy.py` joins its paths and run), the version files (1.0.48 at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`), `plugin/crew/BUDGETS.md:11` (18,905 lines across 126 files, re-measured on the merge), and the autopilot tests. Of the paths this note cites, only the version files and `plugin/crew/BUDGETS.md:11` changed, in place; both install scripts, the root `README.md`, `plugin/crew/README.md` (T-0072's paragraph is line-neutral, so the command and agent counts it carries hold) and `scripts/check-marketplace.py` did not move. Neither install script was executed.

**Re-anchored `21429244` -> `53855ea5` on 2026-09-27 (T-0072 review round 3).** `53855ea5` is T-0072's review-round-3 fix commit on `T-0072-build`. `git diff --name-only 21429244 53855ea5`, outside the refresh artifacts, returns only T-0072's files: `.crew/verify.json` (rule 27's `seconds` 16 -> 20 and its `why`, in place, still `:293-301`), `CHANGELOG.md` (T-0072's 1.0.48 entry, +4 lines, cited without a line), `plugin/crew/BUDGETS.md` (`:11`, in place: 18,908 lines across 126 files, which `check-marketplace.py` verifies), `plugin/crew/CONFIG.md` (one §20 table row edited in place at `:2309`, +3 lines after `:2327`), `plugin/crew/hooks/scripts/crew_autopilot.py` (1230 -> 1252 lines: +2 in the docstring at `:90-97`, `_cannot_exclude` and `_incident(root)` at `:702-718`, `_cli_value` at `:1132`, the `deploy-allowed` printing at `:1214-1219`), `plugin/crew/tests/sabotage_autopilot.py` (+36 at `:300-335`: eight `DEPLOY_MUTATIONS`; one re-anchored in place at `:256`) and `plugin/crew/tests/test_crew_autopilot_deploy.py`. No crew version change (1.0.48). Of the paths this note cites, only `plugin/crew/BUDGETS.md:11` changed, in place (the marker is still `:10`). Neither install script changed or was executed.

**Re-anchored `8de3c669` -> `80326b1d` on 2026-09-27 (T-0072 merged onto `d2fbd408`, then review round 4's redesign, crew 1.0.49).** `ba7d5c52` merged origin/main `d2fbd408` (T-0024 landed as crew 1.0.48 at `8de3c669`) into `T-0072-build` and took main's side of every code map; T-0072's earlier refresh (`git diff 67caa4b8 2fa75f79 -- .crew/codemap/`) was replayed on top with `git apply --3way`, conflicting provenance sections keeping both sides, main's first. `80326b1d` is T-0072's crew 1.0.49 version commit, after the redesign `35733d76` (one root per answer, a tri-state path probe, a two-stage CLI fallback), its sabotage `fa4c8397`, its docs `8a40dd2c` and the rule-27 re-price `37fa7c97`. `git diff --name-only 8de3c669 80326b1d`, outside the refresh artifacts, returns only T-0072's files: `.claude-plugin/marketplace.json` (`:218` 1.0.49), `.crew/verify.json` (rule 27 in place, `:293-301`, `seconds` 16), `CHANGELOG.md` (T-0072's entry, +45 at the top), `plugin/PLUGINS.md` (`:14` 1.0.49, `:128` the `/crew:autopilot` row in place), `plugin/crew/.claude-plugin/plugin.json` (`:3`), `plugin/crew/BUDGETS.md` (`:11`, 18,939 lines across 126 files, which `check-marketplace.py` verifies), `plugin/crew/CONFIG.md` (2328 -> 2382 lines: the leaf paragraph `:130`, the key table `:803`, the `prodUnattended` row `:1261`, `:2282`, and section 20's closing "Production without asking" block from `:2297`), `plugin/crew/README.md` (`:866` in place), `plugin/crew/commands/autopilot.md` (`:45-48` in place, 100 lines), `crew_autopilot.py` (1312 lines), `crew_state.py` (line-neutral at `:1086-1090`), `crew-setup/SKILL.md` and `config.template.json` (the leaf), `test_crew_config.py` (`:282` asserts 123), `sabotage_autopilot.py`, `test_crew_autopilot.py` and `test_crew_autopilot_deploy.py`. Nothing under `scripts/` changed and neither install script is touched; this note cites the changed files by name or at the version and BUDGETS sites only, which now read 1.0.49 and 18,939 / 126. No citation moved. Nothing was executed for this note.

**Re-anchored `80326b1d` -> `1b5b6560` on 2026-09-27 (T-0072 test fix).** `git diff --name-only 80326b1d 1b5b6560`, outside the refresh artifacts, returns only `plugin/crew/tests/test_crew_autopilot_deploy.py` (the layer_state repro now patches `crew_config.layer_state`, not `crew_state.read_text`, which `test_module_split.py` forbids) and the three version files, stepped back to 1.0.48 and re-set to 1.0.49 so the version stays the last `plugin/crew/` commit (same content as at `80326b1d`). This note cites that test file by name only. No citation moved. Nothing was executed for this note.

**Re-anchored `1b5b6560` -> `a4eb2f55` on 2026-09-28 (T-0072 merged onto `5050ea3b`, crew 1.0.50).** `a4eb2f55` is T-0072's crew 1.0.50 version commit on top of its merge of origin/main `5050ea3b` (T-0077 landed as crew 1.0.49 at `fc289446`; shipstation 1.1.1). The merge was clean. `git diff --name-only 1b5b6560 a4eb2f55`, outside the refresh artifacts, returns main's T-0077 and shipstation files - `crew_tracker.py` (+123: Windows now holds a vault write's directories by handle, `_hold_dirs` / `_held_check` replace `_parent_check`), `crew_autopilot.py` (`_rel` +6 at `:170`, so every later line moves by 6), `sabotage_autopilot.py` (+5 inside `STATUS_MUTATIONS`; the `+=` append moved `:639` -> `:644`), `sabotage_tracker.py` (87 `TRACKER_MUTATIONS`, was 81), `plugin/crew/README.md` (`:1511-1513` in place), `test_crew_tracker.py`, `test_crew_autopilot.py`, `test_crew_autopilot_status.py`, `skills/shipstation/*` - and the version files (1.0.50 at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`) and `CHANGELOG.md` (T-0077's and shipstation's entries under T-0072's). Neither install script changed, and this note cites the changed files by name or at the version sites only. No citation moved. Nothing was executed for this note.

**Re-anchored `a4eb2f55` -> `0f488706` on 2026-09-28 (T-0072 review round 5).** `0f488706` is T-0072's review-round-5 fix commit. `git diff --name-only a4eb2f55 0f488706`, outside the refresh artifacts (`0282cb5c`, `37fa2322`), returns only T-0072's files: `plugin/crew/hooks/scripts/crew_autopilot.py` (`_resolve_root` +4 at `:729`, refusing a root that is not text, so every line after it moves by 4: `_layer_problem` `:744`, `_decide` `:759`, `deploy_allowed` `:836`, `_failure` `:1170`, `_cli_deploy` `:1194`, `main` `:1225`; `--json` dumps without indent, in place; the module docstring re-worded in place, `:87-104`), `plugin/crew/tests/sabotage_autopilot.py` (+30 inside `DEPLOY_MUTATIONS`, 64 entries by `len()`: the `AUTOPILOT_MUTATIONS + DEPLOY_MUTATIONS` append moved `:443` -> `:473`, `STATUS_MUTATIONS`' `:644` -> `:674`), `plugin/crew/tests/test_crew_autopilot_deploy.py`, `plugin/crew/CONFIG.md` (one sentence in section 20 re-worded in place, `:2331-2333`, no line added) and `CHANGELOG.md`. This note cites those files by name or at lines above the change; no citation moved. No suite was executed for this note.

## Re-anchor provenance - `65bb3330` + `8314d670` -> `c817782f`, 2026-09-27 (T-0010-solo merges `67caa4b8`)

`c817782f` is T-0010's crew 1.0.48 version commit on top of `d1e119d2`, T-0010-solo's merge of
origin/main `67caa4b8` (T-0018 landed as 1.0.47; its code maps anchored `65bb3330`), and
`3e2c9962`, the reconciliation under the owner's approve carve-out. Main's side of this note was
mapped from `65bb3330`, T-0010's side from its own anchor (`8314d670`), to `c817782f` with `difflib`
over every cited file, a bare `:N` taken as the last path named in its section; sections headed
provenance (and localgpu's re-derivation record) were left as written. The two mapped texts were
then merged three-way from `f0b12ee6`. Between `65bb3330` and `c817782f` the cited paths that
changed are T-0010's: `crew_autopilot.py`, `crew_ticket.py`, `scope_guard.py`, `crew_state.py`
(four `AUTOPILOT_DEFAULTS` lines at `:1094`, so every later line moved by 4), `commands/autopilot.md`,
the version files, `BUDGETS.md`, README, CONFIG.md, the tests and sabotage modules, and
`.crew/verify.json` (rule 28 inserted at `:302-308`, so rules 29 and 30 moved down by 7).

Neither side moved a citation this note makes: no install script, `README.md`,
`INSTALLATION.md`, `scripts/check-marketplace.py` nor `scripts/_test/self-claims.py` changed.
`plugin/crew/BUDGETS.md:11` reads 18,917 across 126 files, `plugin/PLUGINS.md:14` and
`.claude-plugin/marketplace.json:218` read 1.0.48 (changed in place). Neither install script
was executed.

## Re-anchor provenance - `c817782f` -> `926443d8`, 2026-09-27 (T-0010 review round 3 fixes)

`git diff --name-only c817782f 926443d8` is T-0010's round-3 fix (`caabb005`), the BUDGETS.md
count, the version step-back and re-set, and this refresh. Of the paths this note cites, `plugin/crew/README.md`, `plugin/crew/CONFIG.md` and
`plugin/crew/BUDGETS.md` changed: README two lines rewritten in place (`:792`, `:818`),
CONFIG.md's §20 one-writer paragraph grew six lines, and `BUDGETS.md:11`'s count moved
18,917 -> 18,923 on the same line. No citation this note makes moved (checked with `difflib`
over every cited path). Nothing was executed.

## Re-anchor provenance - `926443d8` + `8de3c669` -> `50a275ea`, 2026-09-28 (T-0010's successor merges `f96e9ec9`)

`ab85880b` merges origin/main `f96e9ec9` (T-0024 landed as crew 1.0.48, its code maps anchored
`8de3c669`; T-0077 as 1.0.49) into T-0010-solo `216ee85f`; `a2f4db76` fixes review round 4's
three FIXes; `3438dc9a` merges `5050ea3b` (shipstation only); `48b2820d` re-measures
`plugin/crew/BUDGETS.md` and `50a275ea` sets crew 1.0.50. The merge took main's side of this
note; it was then re-merged three-way from `67caa4b8`, T-0010's side at `216ee85f` (anchor
`926443d8`) and main's at `f96e9ec9` (anchor `8de3c669`), both sides' provenance kept, main's
first. Every body citation into a file changed since its side's own anchor was mapped with
`difflib` (a bare `:N` taken as the last path named in its section) and each one that moved was
re-read at `50a275ea`.

Of the paths this note cites, `plugin/crew/BUDGETS.md` (`:11`, 18,953 across 126 files),
`plugin/PLUGINS.md` (`:14`, 1.0.50) and `.claude-plugin/marketplace.json` (`:218`, 1.0.50)
changed in place; README and CONFIG.md changed in paragraphs cited by name only. No install
script, `README.md`, `INSTALLATION.md` or `scripts/check-marketplace.py` changed, so no
citation moved. Neither install script was executed.

## Re-anchor provenance - `8de3c669` -> `a6e81869`, 2026-09-27 (T-0079 on its branch)

`T-0079-read` was cut from `67caa4b8`, merged main `d2fbd408` (T-0024 landed; its refresh `fdc54ce9`
changed refresh artifacts only) in `f034ef5c`, and carries T-0079's commits through `a6e81869`
(crew 1.0.49). `git diff --name-only 8de3c669 a6e81869`, refresh artifacts aside, returns T-0079's
files only: `review_verdict.py`, `review_prompt.py`, `review_run.py`, their tests and
`sabotage_review.py`, `agents/reviewer.md`, `plugin/crew/README.md` (line-neutral), `CHANGELOG.md`
and the three version files. Every body citation into those files was compared by script between
`8de3c669` and `a6e81869` at the same line.
Of the cited paths, `.claude-plugin/marketplace.json` (`:218` 1.0.49, in place) and
`plugin/PLUGINS.md` (`:14` 1.0.49, in place) changed; no citation moved. Nothing was executed for
this note.

## Re-anchor provenance - `a6e81869` -> `81685adf`, 2026-09-27 (T-0079 merges main, Step 7, re-bump)

`T-0079-read` gained T-0079's Step 7 (`8f7c62dd`, one `find` string in
`plugin/crew/tests/sabotage_webtest.py`), merged main `f96e9ec9` (T-0077 landed, crew 1.0.49) in
`548ee44e`, and re-bumped crew to 1.0.50 in `81685adf`. `git diff --name-only a6e81869 81685adf`,
refresh artifacts aside, returns that `sabotage_webtest.py`, T-0077's files (`crew_tracker.py`,
`crew_autopilot.py`, `sabotage_tracker.py`, `sabotage_autopilot.py`, `test_crew_tracker.py`,
`test_crew_autopilot.py`, `test_crew_autopilot_status.py`), `plugin/crew/README.md` (line-neutral
on both sides), `CHANGELOG.md` and the three version files. Every body citation of the form
`path:line` into those files was compared by script between `a6e81869` and `81685adf`.
This note cites `plugin/crew/README.md` and the version files by name or at unmoved lines; no
citation moved. Nothing was executed for this note.

**Re-anchored `0f488706` -> `9631c707` on 2026-09-28 (T-0072 landing, crew 1.0.51).** `9631c707` is T-0072's landing bump on `T-0072-land`, after `34af80ef` merged the reviewed `T-0072-build` (`a0978df6`) onto main `e6e10432` (T-0079 landed as crew 1.0.50) and `bf0c513a` re-priced verify rule 27. `git diff --name-only 0f488706 9631c707`, refresh artifacts aside, returns T-0079's files, the three version files, `CHANGELOG.md` and `.crew/verify.json`. The two this note's citations reach changed in place: `.crew/verify.json` `:298` and `:301` (rule 27's `seconds` 16 -> 18 and its `why`, still `:293-301`) and `plugin/crew/README.md` `:738` and `:742` (T-0079's verdict table, line-neutral); no citation moved. The version sentence moves to 1.0.51. No suite was executed for this note.

## Re-anchor provenance - `12682e41` + `d2444be9` -> `e95e5964`, 2026-09-27 (T-0075 merges main)

`e95e5964` is T-0075's crew 1.0.46 bump on top of `e94ce6ce`, the merge of origin/main `db14619c`
(T-0021 landed as 1.0.45) into T-0075's branch; the merge took main's copy of this note and
T-0075's edits were re-applied. Of the cited paths, `git diff --name-only 12682e41 e95e5964`
returns `.claude-plugin/marketplace.json` (`:217` 36 commands, `:218` 1.0.46, both in place),
`plugin/PLUGINS.md` (`:14` 1.0.46; `:17` 36 commands), `plugin/README.md` (`:414`) and `README.md`
(`:168`, `:874`), 35 -> 36 in place (`:12`/`:18` still pin `6c497a14`), `plugin/crew/BUDGETS.md`
(marker `:10`; `:11` 19,061 lines across 128 files, re-measured on the merged index as the checker
counts), `plugin/crew/README.md` (the `36 commands` claim `:2480` -> `:2531` and `4 agents`
`:2491` -> `:2542`, re-grepped) and **both install scripts**, each a single in-place line, the
crew label at `scripts/install-prerequisites.sh:1391` and `scripts/install-prerequisites.ps1:1174`
(`35` -> `36 commands`), so no other line number in either script moved. `ls
plugin/crew/commands/*.md` is 36, agents 4, skills 29. The README pin is stale by that label
(Landmines). Neither install script was executed; `check-marketplace.py` passed at `e95e5964`.

## Re-anchor provenance - `e95e5964` + `e463ca53` -> `f7163410`, 2026-09-27 (T-0075 merges T-0023's main)

`96b7e59c` merges origin/main `bebbb97f` (T-0023 landed as crew 1.0.46, PR #244; its notes anchored
`e463ca53`) into T-0075's branch at `0c6b5ecb` (notes anchored `e95e5964`), and `f7163410` bumps
crew to 1.0.47. The source files both sides changed since `db14619c` are `CHANGELOG.md`,
`.crew/verify.json`, `plugin/PLUGINS.md`, `plugin/crew/README.md`, `plugin/crew/CONFIG.md`,
`plugin/crew/BUDGETS.md`, `plugin/crew/hooks/scripts/crew_config.py`,
`plugin/crew/skills/crew-setup/SKILL.md`, `plugin/crew/tests/sabotage.py`,
`plugin/crew/tests/test_crew_config.py` and the version files. The conflicting provenance sections
keep both sides, main's first. Each body line was classified by origin (in T-0075's copy only, in
main's only, or in both), its `path:N` citations - and bare `:N` after a path in the same
paragraph - into files the other side changed were mapped with a line diff (`git show
<side>:<path>` against the merged tree), each moved one re-read with `sed -n`, and hits the diff
attributed to the wrong file (a bare `:N` after an unrelated path, a same-named file elsewhere)
discarded rather than applied. Of the cited paths, `.claude-plugin/marketplace.json` (`:218` 1.0.47; `:217` 36
commands, in place), `plugin/PLUGINS.md` (`:14` 1.0.47; `:17` 36 commands) and
`plugin/crew/BUDGETS.md` (marker `:10`; `:11` 19,125 lines across 128 files, measured with
`git ls-files 'plugin/crew/*.md' | xargs cat | wc -l` on the resolved index) changed.
`plugin/crew/README.md` changed on both sides: its `36 commands` claim is `:2554` and `4 agents`
`:2565` (re-grepped). Both install scripts, the root `README.md` and `plugin/README.md` changed on
T-0075's side only (the 35 -> 36 label, in place), so their citations stand. Neither install
script was executed.

## Re-anchor provenance - `f7163410` + `65bb3330` -> `23371afb`, 2026-09-27 (T-0075 merges T-0018's main)

`34b5f368` merges origin/main `67caa4b8` (T-0018 landed as crew 1.0.47, PR #245; its notes anchored
`65bb3330`) into T-0075's branch at `b5ef35df` (notes anchored `f7163410`), and `23371afb` bumps crew
to 1.0.48. The source files both sides changed since `bebbb97f` are `CHANGELOG.md`,
`.crew/verify.json`, `plugin/crew/README.md`, `plugin/crew/BUDGETS.md` and the version files;
`crew_autopilot.py`, `commands/autopilot.md` and the autopilot tests changed on main's side only,
`crew_config.py`, `crew_config_menu.py`, `CONFIG.md` and `sabotage.py` on T-0075's only. The
conflicting provenance sections keep both sides, main's first; each body citation into a file both
sides changed was mapped from the side its line came from onto the merged tree and re-read with
`sed -n`/`grep -n`. Of the cited paths, `.claude-plugin/marketplace.json` (`:218` 1.0.48; `:217` 36 commands, in
place), `plugin/PLUGINS.md` (`:14` 1.0.48; `:17` 36 commands) and `plugin/crew/BUDGETS.md` (marker
`:10`; `:11` 19,120 lines across 128 files, measured per file with `splitlines()` on the resolved
index) changed. `plugin/crew/README.md` changed on both sides: its `36 commands` claim is `:2569` and
`4 agents` `:2580` (re-grepped). Both install scripts, the root `README.md` and `plugin/README.md`
did not change on main's side, so their citations stand. Neither install script was executed.

## Re-anchor provenance - `23371afb` -> `764f6018`, 2026-09-27 (T-0075 review round 1)

`764f6018` fixes T-0075's review round 1. `git diff --name-only 23371afb 764f6018` is `CHANGELOG.md`,
`plugin/crew/BUDGETS.md`, `plugin/crew/CONFIG.md`, `plugin/crew/README.md`,
`plugin/crew/hooks/scripts/crew_config.py`, `plugin/crew/hooks/scripts/crew_config_menu.py`,
`plugin/crew/skills/crew-setup/config-menu.md` and three crew test files. Each citation into one
of them was mapped with a line diff from `87627d86` (the tree `23371afb` describes for those
files) and re-read with `sed -n`/`grep -n`. This note cites those files by name, by section or by historical
BUDGETS figures only, plus `crew_config.py` and `test_crew_config.py` by name; none of its line
citations moved. The install scripts did not change. Nothing was executed for this note.

## Re-anchor provenance - `764f6018` + `8de3c669` -> `7d217751`, 2026-09-27 (T-0075 successor build, merges T-0024's main)

`7d217751` is T-0075's crew 1.0.49 bump. Between `764f6018` (T-0075 review round 1, this note's
last anchor) and it: the successor build's steps 1-9 (`4911b896`..`763eaeff`: `crew_config_files.py`
new, `crew_config.py` and `crew_config_menu.py` redesigned, their tests and sabotage entries, the
menu procedure, `commands/config.md`, `config-setup.md`, `global-config.md`, `plugin/crew/README.md`,
`CONFIG.md`, the troubleshooting guide and `CHANGELOG.md`), `748a823d` merging origin/main `d2fbd408`
(T-0024 landed as 1.0.48, notes anchored `8de3c669`), `af1ee7ef` adding two paths to
`.crew/verify.json` rule 7, `cb67a6ef` rebuilding the troubleshooting guide, `plugin/crew/BUDGETS.md`
re-measured (19,280 lines across 128 files) and the bump. The merge's provenance sections keep both
sides, main's first. Each citation into a path `git diff --name-only 764f6018 7d217751` names was
checked against the tree it was written for (`git blame` on this note gives the commit) and re-read
at `7d217751` with `sed -n`/`grep -n`; none of this note's line citations moved. The install scripts did not change
in this range (`git log 6c497a14..7d217751` over both still returns `ecf69e43` and `a77a42d6`), so
the README pin landmine stands as written; `README.md:12`/`:18` still pin `6c497a14`. Version
1.0.49 at `.claude-plugin/marketplace.json:218` and `plugin/PLUGINS.md:14`; `:218` and `:17` still
state 36 commands (`ls plugin/crew/commands/*.md` is 36). Nothing was executed for this note.

## Re-anchor provenance - `7d217751` + `f96e9ec9` -> `8cabe586`, 2026-09-27 (T-0075 post-merge fixes, merges T-0077's main)

`8cabe586` is T-0075's crew 1.0.50 bump. Between `7d217751` and it: `ed7cb36c` (the stray line
step 6 left in `crew_config_menu.py:940`, a restore-line test's assertion, and the widening-warning
mutation re-anchored in `sabotage.py`, each found by the first full suite run after the build), a
1.0.48/1.0.49 step-back and re-set (`b80db8e1`, `81ed193c`), `3ebddc74` merging origin/main
`f96e9ec9` (T-0077 landed as 1.0.49: Windows directory handles in `crew_tracker.py`,
`crew_autopilot._rel`, their tests and mutations, three `plugin/crew/README.md` lines and its
`CHANGELOG.md` entry; main's notes were not refreshed for it) and the bump. Citations into the
paths `git diff --name-only 7d217751 8cabe586` names were mapped with `git diff -U0` and each
moved one checked by content at `8cabe586`; none of this note's line citations moved; the install scripts and
`README.md` did not change. Version 1.0.50 at `.claude-plugin/marketplace.json:218` and
`plugin/PLUGINS.md:14`; `:218` and `:17` still state 36 commands. Nothing was executed for this note.

## Re-anchor provenance - `8cabe586` + `81685adf` -> `3724731b`, 2026-09-28 (T-0075 review round 3, merge of `e6e10432`)

`3036dc02` is T-0075's review-round-3 fix (`crew_config.py`, `crew_config_files.py`,
`crew_config_menu.py`, their three test files, `sabotage_config.py`, and `README.md`, `CONFIG.md`,
`commands/config.md`, `config-menu.md`, `global-config.md`, `CHANGELOG.md`); `6d5f0b61` merges
origin/main `e6e10432` (T-0079 landed as crew 1.0.50: `review_prompt.py`, `review_run.py`,
`review_verdict.py`, `agents/reviewer.md`, their tests, `sabotage_review.py`,
`sabotage_webtest.py`, `test_webtest_guard.py`, `README.md`, `CHANGELOG.md`; its notes anchored
`81685adf`); `3724731b` re-bumps crew to 1.0.51 (`plugin.json`, `marketplace.json`,
`plugin/PLUGINS.md`, `plugin/crew/BUDGETS.md`, `CHANGELOG.md`). The merge's conflicting provenance
sections kept both sides, main's first; anchor lines kept T-0075's and are replaced here.

No citation in this note's body moved: it cites neither install script at a line either change
reaches (neither script changed), and the crew files the range touched are cited by name only.
Checked by a script mapping every explicit `path:N` through `git diff -U0`. Nothing was executed.

## Re-anchor provenance - `3724731b` + `9631c707` -> `938e3b11`, 2026-09-28 (T-0075 review round 4, merge of `f54af3fa`)

`7d473f24` merges origin/main `f54af3fa` (T-0072 landed as crew 1.0.51: `crew_autopilot.py`,
`commands/autopilot.md`, `crew_state.py`'s line-neutral `AUTOPILOT_DEFAULTS` hunk at `:1086-1090`,
`templates/config.template.json`, `skills/crew-setup/SKILL.md`, `CONFIG.md` §20, `README.md`, its
tests, `sabotage_autopilot.py`, `.crew/verify.json` rule 27's `seconds` and `why`; its notes
anchored `9631c707`); `07354a39`, `df419a55`, `7a206c8e`, `4112498e`, `1b31ed2f` and `7ef3c4f1` are
T-0075's review-round-4 steps 11-16 (`crew_config.py`, `crew_config_files.py`,
`crew_config_menu.py`, their three test files, `sabotage_config.py`, `README.md`, `CONFIG.md`,
`skills/crew-setup/config-menu.md`, `CHANGELOG.md`, `plugin/crew/BUDGETS.md`); `938e3b11` re-bumps
crew to 1.0.52 (`plugin.json`, `marketplace.json`, `plugin/PLUGINS.md`, `CHANGELOG.md`). The merge's
conflicting provenance kept both sides; anchor lines kept T-0075's and are replaced here.

No citation in this note's body moved: of the paths it cites, those that changed between `3724731b`
and `938e3b11` are the version files, docs and modules listed above, and the script found no body
citation into any of them that reaches a changed or shifted line.

Checked by a script mapping every `path:N` citation outside provenance sections, and every bare `:N`
carried from the last path named in its paragraph, from both `3724731b` and `9631c707` to the tree
at `938e3b11` (difflib equal blocks); every citation neither base maps to itself was read with `sed
-n` / `grep -n`. The script attributes some bare `:N` to the wrong file (a `crew_autopilot.py`
citation after an `autopilot.md` mention, a `plugin.json:3` in another plugin); those were read and
hold. Nothing else was executed for this note.

**Re-anchored `9631c707` -> `c99e31f6` on 2026-09-28 (T-0092, crew 1.0.52).** `c99e31f6` is T-0092's crew 1.0.52 version commit on `T-0092-build`, cut from main `f54af3fa` (T-0072's landing merge, whose only commit past `9631c707` is the refresh `f1f118de`). `git diff --name-only 9631c707 c99e31f6`, refresh artifacts aside, returns T-0092's files: `plugin/crew/hooks/scripts/review_patch.py` (+8: the docstring paragraph on `graphify-out/` and one comment line; `EXCLUDED` / `_EXCLUDE_SPEC` now at `:104-105`), `plugin/crew/hooks/scripts/review_prompt.py` (+4: one docstring line and the `excluded` line at `:89-91`, so `:84` -> `:85` and `:239` -> `:243`), `test_review_patch.py`, `test_review_prompt.py`, `sabotage_review.py`, line-neutral edits to `plugin/crew/README.md` (`:726`, `:860`), `plugin/crew/commands/review.md` (`:328-332` reflowed in place), `crew_autopilot.py` (`:55-56`), `completion_audit.py` (`:74-75`) and `TODO.md` (`:5048`), `CHANGELOG.md` (+26 at the top) and the three version files (1.0.52 at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`). Every body citation of the form `path:line` into those files was compared by script between `9631c707` and `c99e31f6`. The only differing citations are the version-file lines, changed in place, which the provenance notes cite with the value at their own commit. No citation moved. Nothing was executed for this note.

**Re-anchored `c99e31f6` -> `3c4f1a68` on 2026-09-28 (T-0092 merged onto `c426c018`, crew 1.0.53).** `95cc12cf` merged origin/main `c426c018` (T-0076 landed as crew 1.0.52 at `e329eb8f`) into `T-0092-build`; the merge was clean (both sides had set the version files to 1.0.52). `3c4f1a68` re-bumps crew to 1.0.53 and moves T-0092's four `1.0.52` mentions (`review_patch.py`'s docstring, `plugin/crew/README.md:871`, `TODO.md:5048`, the two test-file comments) to 1.0.53, all in place. `git diff --name-only c99e31f6 3c4f1a68`, refresh artifacts aside, returns T-0076's files - `plugin/crew/hooks/scripts/crew_context.py` (+4 inside `emit`, so `sys.stdout.write` moves `:1086` -> `:1090`), `plugin/crew/README.md` (`:1691` in place), `scripts/_test/uv-install.sh` and twelve test files - plus `CHANGELOG.md` (T-0076's entry merged below T-0092's) and the version files. Every body citation of the form `path:line` into those files was compared by script between `c99e31f6` and `3c4f1a68`: the only differences are version-file lines changed in place and `CHANGELOG.md` lines inside dated provenance notes, left as history; nothing here cites `crew_context.py` at or below `:1104`. Nothing was executed for this note.

**Re-anchored `3c4f1a68` -> `136f4b33` on 2026-09-28 (T-0092 merged onto `ff59160f`, T-0089, crew 1.0.54).** `e2220836` merges origin/main `ff59160f` (T-0089 landed as crew 1.0.53 at `0f526a8c`: `plugin/crew/tests/test_role_write_guard.py` fixtures and a `CHANGELOG.md` entry) into `T-0092-build`; the merge was clean. `136f4b33` re-bumps crew to 1.0.54 and moves T-0092's `1.0.53` mentions (`review_patch.py`'s docstring, `plugin/crew/README.md:871`, `TODO.md:5051`, the two test-file comments, its `CHANGELOG.md` heading) to 1.0.54, all in place. Every body citation of the form `path:line` into a file changed between `3c4f1a68` and `136f4b33` was compared by script: the only differences are version-file lines changed in place, `plugin/crew/README.md:871` in place, and lines cited inside dated provenance notes (`CHANGELOG.md`, which T-0089's entry shifts by 12 lines below `:80`, and `TODO.md:5048`), left as history at their own commit. No citation into `test_role_write_guard.py` exists here. Nothing was executed for this note.

## Re-anchor provenance - `938e3b11` + `136f4b33` -> `3648f59a`, 2026-09-28 (T-0075 review round 5, merge of `6387ab49`)

`9420bc16` merges origin/main `6387ab49` into `T-0075-build`: T-0076 (crew 1.0.52, `crew_context.py`'s byte-exact LF), T-0091 (`CLAUDE.md`'s Landmines paragraph, a `TODO.md` entry), T-0089 (crew 1.0.53, `test_role_write_guard.py` fixtures), T-0090 (mcp-servers 0.2.1, `SECURITY.md`) and T-0092 (crew 1.0.54: `review_patch.py` / `review_prompt.py` leave `graphify-out/` out of the review bundle), whose notes above are anchored `136f4b33`, `2442d367`, `c192b83d` or `b2553d26`. `faf4b0db`, `e7825a0e`, `04e3a01c`, `517628b9` and `d1460d77` are T-0075's review-round-5 steps 18-22 (`crew_config.py`, `crew_config_files.py`, their three test files, `sabotage_config.py`, `README.md`, `CONFIG.md`, `CHANGELOG.md`, `plugin/crew/BUDGETS.md`); `3648f59a` re-bumps crew to 1.0.55 (`plugin.json`, `marketplace.json`, `plugin/PLUGINS.md`, `CHANGELOG.md`). The merge's conflicting provenance kept both sides, T-0075's `## Re-anchor provenance` sections first and main's `**Re-anchored ...**` paragraphs after them; the anchor line kept T-0075's and is replaced here.

No body citation moved: the files this note cites that changed are `CHANGELOG.md`, `README.md`, `CONFIG.md`, `BUDGETS.md`, `crew_config.py` and `test_crew_config.py` (none cited by line outside provenance) and the version files, whose crew lines changed in place.

Checked by a script mapping every `path:N` citation outside provenance sections, and every bare `:N` carried from the last path named in its paragraph, from `938e3b11` for a line in T-0075's copy of this note and from `6387ab49` for a line only in main's, to the tree at `3648f59a` (difflib equal blocks); every citation that did not map to itself was read with `sed -n` / `grep -n`. The script attributes some bare `:N` to the wrong file (a `.crew/verify.json` range after a test-file mention, a `check-marketplace.py` range after a `PLUGINS.md` mention, a `SKILL.md` in another skill); those were read and hold. A citation inside a list of per-commit positions keeps its commit's line; only the current position is added. Nothing else was executed for this note.

## Re-anchor provenance - `50a275ea` + `81685adf` -> `360c4029`, 2026-09-28 (T-0010-solo merges T-0079's `e6e10432`)

`c312702b` merges origin/main `e6e10432` (T-0079 landed as crew 1.0.50, its code maps anchored
`81685adf`) into T-0010-solo `ac0b5151`; `360c4029` sets crew 1.0.51. The artifact conflicts were
anchor, version and provenance lines only: T-0010's side kept for anchors and body (its
`crew_autopilot.py` and `commands/autopilot.md` line numbers are this tree's), both sides'
provenance kept. `git diff --name-only 50a275ea 360c4029`, refresh artifacts aside, is T-0079's files
(`review_verdict.py`, `review_prompt.py`, `review_run.py`, `agents/reviewer.md`, their tests and
sabotage modules, identical to origin/main's), `plugin/crew/README.md` (two lines rewritten in
place, `:735` and `:739`, line-neutral), `CHANGELOG.md` and the version files. Every citation into
T-0079's files equals main's note at `81685adf` (compared by script). No test was run by this note.

## Re-anchor provenance - `360c4029` + `136f4b33` -> `d7c7c75c`, 2026-09-28 (T-0010-solo merges `6387ab49`)

`597a62b0` merges origin/main `6387ab49` into T-0010-solo `dbb22712`: T-0072 landed as crew
1.0.51, T-0076 as 1.0.52, T-0089 as 1.0.53 and T-0092 as 1.0.54, with T-0090 (mcp-servers 0.2.1)
and T-0091 (`CLAUDE.md`) beside them; main's code maps were anchored `136f4b33`. After it,
`bd066a97` moves `settings`' two policies to a second text line (T-0072's
`test_settings_line_names_deploy` pins the first line exactly), `ab85fed0` puts `deploy-allowed`
in T-0010's only-writer test, `250c6df7` rewraps one docstring line in place, `130bf67e` re-sets
crew 1.0.55 and `d7c7c75c` re-prices `.crew/verify.json` rule 29 in place (20 -> 21). The merge
took main's side of this note; it was then re-merged three-way from `e6e10432`, T-0010's side at
`dbb22712` (anchor `360c4029`) and main's at `6387ab49`, both sides' provenance kept, main's
first. Every body `path:line` citation into a file changed since its side's commit was mapped to
`d7c7c75c` with `difflib` (a bare `:N` taken as the last file named earlier in its paragraph);
a citation followed by `at <sha>`, `before` or `->`, and every provenance section, was left as
written. A citation inside a changed hunk cannot be mapped that way and was left as written unless
this section names it.

Of the paths this note cites, the version files (1.0.55 at `.claude-plugin/marketplace.json:218`,
`plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`), `plugin/crew/BUDGETS.md:11`
(19,007 lines across 126 files, re-measured) and `.crew/verify.json` changed in place; README and
CONFIG.md changed in paragraphs cited by name only. No install script, `README.md`,
`INSTALLATION.md` or `scripts/check-marketplace.py` changed. Neither install script was executed.

## Re-anchor provenance - `d7c7c75c` + `3648f59a` -> `cd106b8b`, 2026-09-28 (T-0010-solo merges T-0075's `e878cc31`)

`acbb0fb2` merges origin/main `e878cc31` into T-0010-solo `07032fc7`: T-0075 (`/crew:config` menu mode and
`/crew:config-setup`) landed as crew 1.0.59, its code maps anchored `3648f59a`. `92e0717a` re-measures
`plugin/crew/BUDGETS.md` (19,494 lines across 128 files) and rebuilds the troubleshooting guide's DOCX and
PDF; `cd106b8b` re-sets crew 1.0.60, one past main. The code merged without a conflict (T-0010 and T-0075 change
disjoint scripts); the conflicts were this note's anchor, provenance and a few cited lines. Both sides'
provenance was kept, main's first. Every body `path:N` citation was traced to the side whose copy of this
note carries its line (`07032fc7` or `e878cc31`) and mapped to `cd106b8b` through a `difflib` line diff
(`/root/crew-tmp/t-0010/citemap.py`, machine-local); each line that did not map to itself was read with
`sed -n` / `grep -n`. The script takes a bare `:N` as the last path named on its line, so some flags were
that misattribution (a `crew_ticket.py` or `review_ledger.py` line after another file's mention) and hold.

No install script, `README.md`, `INSTALLATION.md` or `scripts/check-marketplace.py` changed in the merge
beyond main's own edits already in its note; the version files changed in place (1.0.60 at
`.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`).
Neither install script was executed.

## Re-anchor provenance - `cd106b8b` -> `bbd9a66d`, 2026-09-29 (T-0010 landing branch)

`T-0010-land` merges T-0010-solo `6b89c1df` into origin/main `2693d0fa` (README re-pin only past `e878cc31`,
so the merged tree is `6b89c1df` plus that README change). `08eeaa3e` adds the ruff fix-at-land lint fixes
(owner standing rule 2026-09-28; owner decision 2026-09-29 "Fix at land"): ISC004 parentheses in
`plugin/crew/hooks/scripts/crew_autopilot.py`, `plugin/crew/tests/sabotage_autopilot.py` and
`plugin/crew/tests/test_scope_guard.py`; `# noqa: BLE001` on five fail-closed broad excepts in
`plugin/crew/hooks/scripts/crew_autopilot.py`, `plugin/crew/hooks/scripts/crew_ticket.py` and
`plugin/crew/hooks/scripts/scope_guard.py`; an I001/RUF100/C0207 fix in
`plugin/crew/tests/test_crew_autopilot_policy.py`. `bbd9a66d` re-sets crew 1.0.61. Each edited line kept its
number (the parentheses and comments were added in place) except in `test_crew_autopilot_policy.py`, whose
import block lost one line; no note cites that file by line. Re-anchor only; nothing was executed for this note.

**Re-anchored `9631c707` -> `b5c37635` on 2026-09-28 (T-0087, crew 1.0.52).** `b5c37635` is T-0087's crew 1.0.52 bump on `T-0087-build`, after `d05727af` merged main `f54af3fa` (T-0072 landed as crew 1.0.51). `git diff --name-only 9631c707 b5c37635`, refresh artifacts aside, returns T-0087's files (the review/gate harness, its tests, the golden corpus, `scripts/check-tooling-pr.py`, rule 31 in `.crew/verify.json`, `CLAUDE.md`'s tooling-alone bullet, the docs and guides) plus the three version files and `CHANGELOG.md`. This note's body cites none of them at a moved line: its `plugin/crew/README.md` and `CLAUDE.md` citations sit in provenance sections, kept as history. Its citations of the three version lines (`.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`) changed in place and now read 1.0.52. Neither install script changed or was executed.

**Re-anchored `b5c37635` -> `1da1233d` on 2026-09-28 (T-0087, crew 1.0.52).** `1da1233d` is T-0087's crew 1.0.52 bump re-set after two reflow commits: `4648581a` rewrapped `plugin/crew/commands/review.md` to its 551-line allowance and `plugin/crew/commands/autopilot.md` to its 100-line budget, and `4304a9da` kept the sabotage anchor "are the human's. Go back" on one line (no rule changed in either). `git diff --name-only b5c37635 1da1233d`, refresh artifacts aside, returns those two command files and the three version files, which read 1.0.52 on both sides. This note cites neither file by line. Neither install script changed or was executed.

**Re-anchored `1da1233d` -> `0d331967` on 2026-09-28 (T-0087, crew 1.0.52).** `0d331967` adds `plugin/crew/BUDGETS.md` to `scripts/check-tooling-pr.py`'s `ALONGSIDE` (its line count moves with every crew doc edit, and the checker refused this branch's own re-measure) and the `harness+budgets` must-allow case to `scripts/_test/tooling-pr.py`, red first (7 passed, 1 failed), then 8 passed. `git diff --name-only 1da1233d 0d331967`, refresh artifacts aside, returns those two scripts and `CHANGELOG.md`, plus the 1da1233d..08ed88a5 changes (`plugin/crew/BUDGETS.md`, `plugin/crew/tests/sabotage_refresh.py`, version files unchanged net). This note cites neither script by line. Nothing was executed for this note.

**Re-anchored `0d331967` -> `c8cc69ec` on 2026-09-28 (T-0087, now crew 1.0.53).** Main moved: `c426c018` (T-0076, the crew suite on native Windows) landed as crew 1.0.52, so T-0087 merged it with a merge commit (no conflict) and re-bumped to 1.0.53 at `c8cc69ec`. `git diff --name-only 0d331967 c8cc69ec`, refresh artifacts aside, returns T-0076's files (`plugin/crew/hooks/scripts/crew_context.py` +4 at `:1086`, where `emit` now forces LF stdout; `plugin/crew/tests/crew_fixtures.py`, `review_fixtures.py`, `sabotage_context.py` and nine test files; `scripts/_test/uv-install.sh`; one `plugin/crew/README.md` table cell; its `CHANGELOG.md` entry), the README refund paragraph's version text, and the three version files. Every body `path:N` citation into those files was mapped by script (difflib over the two blobs) and every bare `:N` after one of their names was listed and read: none moved. Neither install script changed or was executed.

**Re-anchored `c8cc69ec` -> `c0768d0e` on 2026-09-28 (T-0087, crew 1.0.53).** `c0768d0e` is T-0087's merge of main `f8b6c8d7` (T-0091, no plugin version change) into `T-0087-build`; crew stays 1.0.53, one past main's 1.0.52, and `c8cc69ec` is still the last `plugin/crew` commit. `git diff --name-only c8cc69ec c0768d0e`, refresh artifacts aside, returns `CLAUDE.md` (T-0091's Landmines truncating-`open` measurement paragraph, +35/-18 at `:189`, so every later line moves +17) and `TODO.md`. Every other body `CLAUDE.md:N` citation here is at or above `:189`, or sits inside a dated re-anchor note that states the coordinates of its own commit, so none moved. Nothing was executed for this note.

**Re-anchored `136f4b33` / `c0768d0e` -> `379ab5e6` on 2026-09-28 (T-0087 merged onto `6387ab49`, crew 1.0.55).** `01dd3854` merges origin/main `6387ab49` into `T-0087-build`: T-0089 (crew 1.0.53, `plugin/crew/tests/test_role_write_guard.py`), T-0090 (mcp-servers 0.2.1: `SECURITY.md`, ten files under `mcp-servers/`) and T-0092 (crew 1.0.54: `graphify-out/` left out of review bundles - `review_patch.py`, `review_prompt.py`, `completion_audit.py`'s comment, `crew_autopilot.py`'s docstring, `commands/review.md`, `plugin/crew/README.md`, `TODO.md`, three test files). `379ab5e6` re-bumps crew to 1.0.55, one past main's 1.0.54, and moves T-0087's `1.0.53` mentions (`plugin/crew/README.md:754`, its `CHANGELOG.md` entry) to 1.0.55 in place. The code-map, INDEX, diagram, rules and graph conflicts were resolved mechanically - both sides' provenance notes kept, main's first; the version sentence, `.claude/rules/` and `graphify-out/` taken from main and then refreshed. Every body citation of the form `path:line` was re-mapped by script (difflib over each cited file, from the anchor of the side `git blame` puts the note line on, both anchors for a line common to both, never guessed): none moved in this map. Citations the script could not map, or where the two sides' anchors disagree on a line common to both, were not re-read here and are unchanged; they predate this merge (for example `CHANGELOG.md`'s "117 -> 119" is cited at `:654-655` on both sides and sits at `:909-910`), and this pass only re-anchors.

**Re-anchored `379ab5e6` -> `17fa035e` on 2026-09-28 (T-0087 review round 1, crew 1.0.55 unchanged - not yet released).** `bbe68e85` fixes review round 1: autopilot lets a refunded round's `/crew:review` rerun past its no-progress stop, rule 31 triggers on its suites and seam consumers, `scripts/check-tooling-pr.py` admits no production code or prompt alongside the harness (a `SEAM` consumer only with a `Tooling-seam:` trailer), `golden_build.redact` bounds both sides of a match, a malformed `successors` loads as corrupt, `review_run.py`'s summary line counts charged rounds, a worktree rename is parsed, and the guides stop calling a post-refund rerun free; `17fa035e` re-prices rule 31. `git diff --name-only 379ab5e6 17fa035e`, refresh artifacts aside, returns those scripts, their tests, one golden fixture, `.crew/verify.json`, `CLAUDE.md`, `CHANGELOG.md`, `plugin/crew/README.md`, `plugin/crew/BUDGETS.md`, `commands/autopilot.md`, `commands/review.md` and the troubleshooting guide. Body citations of the form `path:line` into those files were re-mapped by script (difflib over each cited file from `379ab5e6` to `bbe68e85`, only for note lines committed before this pass, never guessed): none moved in this map.

## Re-anchor provenance - `bbd9a66d` + `17fa035e` -> `9e38a891`, 2026-09-29 (`T-0087-build` merges T-0010's `8ab733d7`)

`0fc7f609` merges origin/main `8ab733d7` (T-0010 landed as crew 1.0.61, its code maps anchored
`bbd9a66d`) into `T-0087-build` `674bc4e5` (T-0087's Windows-portability successor plan, Steps 1-5
built; its maps anchored `17fa035e`). After it, `ae448309` renames T-0087's harness rule to rule 32
in text and re-measures `plugin/crew/BUDGETS.md` (19,666 lines across 129 files), `167f69a0` says
the refund ships in 1.0.62 (README, CHANGELOG), `e537e4ce` re-sets crew 1.0.62, one past main, and
`9e38a891` rebuilds the daily-workflow and troubleshooting guides from their merged sources. The code
conflicts were `crew_autopilot.next_phase` (main's `policy` argument plus T-0087's refunded-rerun
pop), `sabotage.py`'s `MUTATIONS +=` line and `test_crew_autopilot.py` (both sides kept) and the
README's Stops line (main's text plus T-0087's refunded-review clause). The artifact conflicts took
main's side for body text and kept both sides' provenance, main's first. Every body `path:N`
citation was traced to the side whose copy of this note carries its line (`674bc4e5` or
`8ab733d7`) and mapped to this tree with a `difflib` line diff (`/root/crew-tmp/t-0010/citemap.py`
and `/root/crew-tmp/t-0087/citeapply.py`, machine-local). The script takes a bare `:N` as the last
path on its line; each misattribution it produced (a `crew_autopilot.py` line after a
`review_ledger.py` or `commands/autopilot.md` mention, a `.crew/verify.json` range after a
`sabotage.py` one, a historical `at <sha>` README line) was reverted or re-read by symbol with
`grep -n`. `crew_autopilot.py` is 1751 lines: T-0087's refund hunks add 16 lines from `:522`, so
main's citations at or past `:522` moved by 6 to 16 (`next_phase` `:556`, `settings` `:745`,
`deploy_allowed` `:943`, `main` `:1648`) and nothing above it moved. T-0087's `sabotage_tooling`
import at `plugin/crew/tests/sabotage.py:82` puts the `MUTATIONS +=` statement at `:3054-3057`
(refresh `:3054`; resume, autopilot, tracker and route `:3055`; policy, approval, config and tooling
`:3056`). `.crew/verify.json` is 33 rules and 370 lines: T-0087's harness rule is rule 32 at
`:340-365`, after T-0024's rule 31 at `:332-339`. Nothing was executed for this note; the suites ran
with the build.

No install script, `INSTALLATION.md` or `scripts/check-marketplace.py` changed in the merge beyond
main's own edits; the version files changed in place (1.0.62). Neither install script was executed.

## Re-anchor provenance - `9e38a891` -> `78b7080a`, 2026-09-30 (`T-0087-build` merges T-0088's main `a61a6f38`)

`f702cb24` merges origin/main `a61a6f38` (T-0088 landed as crew 1.0.69, after #263-#267: crew 1.0.62-1.0.68's CI ruff and xdist changes, gate-first review, the steward skill and `crew-qa-standards`) into `T-0087-build`, with a merge commit; its conflicts were mechanical and both sides were kept. `a9bc8877` moves T-0087's version text to 1.0.70 and its harness rule to `.crew/verify.json` rule 35, `90b71bbf` re-sets crew 1.0.70, one past main's 1.0.69, and `78b7080a` rebuilds two guides. Every body citation of the form `path:line` was re-mapped by script (difflib over each cited file, from T-0087's `cb9b79b1` for a note line both parents carry and from `a61a6f38` for a line only main carries, to this tree; a bare `:N` binds to the last path named on its line, with or without a line number): none moved in this map. Citations the script could not attribute to a file that has that line (a bare `:N` after a different file's name, or a short name with no directory) predate this merge and were left unchanged. Re-anchor only: no other claim moved and nothing was executed for this note.

## Re-anchor provenance - `78b7080a` -> `b142d8e3`, 2026-09-30 (T-0087 review round 4 fixes)

`dc412c5c` limits the refunded-rerun marker to the `review` phase in `crew_autopilot._review_phase` (+2 lines, so every `crew_autopilot.py` line from `_toward_review` on moves by 2), with a must-block test and sabotage entry (ac); `b5f87132` re-maps `plugin/crew/docs/external-tool-formats.md`'s citations and adds a test that pins them; `af7eccbe` re-times `.crew/verify.json` rule 35 in place (no line moved); `b142d8e3` corrects a CHANGELOG figure. Every body citation of the form `path:line` was re-mapped by script (difflib from `78b7080a` to `b142d8e3`; a bare `:N` binds to the last path named on its line), and the `crew_autopilot.py` citations whose path is on the line above were re-mapped by hand. Citations the script could not attribute predate this change and were left unchanged. Re-anchor only: no other claim moved and nothing was executed for this note.
**Re-anchored `9631c707` -> `22399a9c` on 2026-09-28 (T-0085, crew 1.0.52).** `22399a9c` is T-0085's version commit on `T-0085-build` (the change is `d02fe008`, from origin/main `f54af3fa`). Of the paths this note cites, T-0085 changed `README.md` (`:168` and `:874`, 29 -> 30 skills, line-neutral), `plugin/PLUGINS.md` (`:14` 1.0.52, `:17` 30 skills, and one skills-table row added below `:213`), `.claude-plugin/marketplace.json` (`:217` 30 skills, `:218` 1.0.52), `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/crew/README.md` (a section added after `:750`), `.gitignore`, `CLAUDE.md`, `.crew/verify.json` (one rule appended) and `plugin/crew/skills/crew-setup/SKILL.md` (`!.crew/standards.md` in the shipped template). Every body citation into those files was compared by script at both commits; only the skills figure moved, corrected above. Neither install script changed. Nothing was executed for this note.

**Re-anchored `22399a9c` -> `2aa49bb8` on 2026-09-28 (T-0085 merged onto main `c426c018`, crew 1.0.53).** `c49f3aca` merged origin/main `c426c018` (T-0076 landed as crew 1.0.52) into `T-0085-build`, one mechanical conflict (the crew description's skills count in `.claude-plugin/marketplace.json`, kept at 30), and `2aa49bb8` bumped crew to 1.0.53. `git diff --name-only 22399a9c 2aa49bb8`, refresh artifacts aside, returns T-0076's files (`plugin/crew/hooks/scripts/crew_context.py`, four lines added inside `emit()` at `:1086-1089`; `plugin/crew/README.md`, one line in place; `scripts/_test/uv-install.sh`; eleven test files) and the version files. Every body citation into a changed file was compared by script at both commits; none moved. No suite was executed for this note.

**Re-anchored `2aa49bb8` -> `b82035e6` on 2026-09-28 (T-0085 merges main `f8b6c8d7`, T-0091).** `17b70570` merged origin/main `f8b6c8d7` into `T-0085-build` (mechanical conflicts only: anchors, provenance paragraphs, INDEX history cells, generated rules and graph); `b82035e6` moves the crew skills claim at `plugin/README.md:414` and `INSTALLATION.md:252` from 29 to 30 (spec Touch amendment). Of the paths this note cites, `git diff --name-only 2aa49bb8 b82035e6` returns `CLAUDE.md`, `INSTALLATION.md` and `plugin/README.md`. `CLAUDE.md`'s change is T-0091's Landmines truncating-`open` paragraph, whose citations were moved on main's side and merged in, plus T-0085's four-line ignore-policy reflow, which shifts no line. Every `CLAUDE.md:N`, `INSTALLATION.md:N` and `plugin/README.md:N` citation was compared by script against its text at `2aa49bb8`, `c192b83d` and HEAD; the one sentence saying both still read 29 is corrected in place. No suite was executed for this note.

**Re-anchored `136f4b33` -> `8a084c6c` on 2026-09-28 (T-0085 merges main `6387ab49`, T-0089, T-0090, T-0092; crew 1.0.55).** `f97219dc` merged origin/main `6387ab49` into `T-0085-build` (mechanical conflicts only: crew version lines, CHANGELOG, anchors, provenance paragraphs, INDEX history cells, diagram headers, generated rules and graph); `8a084c6c` re-bumps crew to 1.0.55, one past main's 1.0.54. Each side had already re-verified its own changes (main's line to `136f4b33`/`2442d367`/`b2553d26`, T-0085's to `b82035e6`), so this pass checks the files BOTH sides changed: the crew version lines (`.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`, value only, same line), `CHANGELOG.md` (both sections kept; release bookkeeping), `plugin/crew/README.md` and `plugin/crew/commands/review.md` (main's T-0092 edits are in place and line-neutral: 2883 and 551 lines, as on T-0085's side), `plugin/crew/hooks/scripts/review_prompt.py` (main's docstring line split in two at `:6-7` and three `excluded` lines added at `:96-98` shift T-0085's lines below them by 4) and `plugin/crew/tests/test_review_prompt.py`. Every `path:N` citation into those files was compared by script against its text on the side that wrote it (`f3ad630b` or `6387ab49`) and at the merged tree; none moved. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `8a084c6c` -> `07bcaf3b` on 2026-09-28 (T-0085 review round 1 fixes).** `07bcaf3b` changes `plugin/crew/hooks/scripts/crew_standards.py` (`gate_applies`, `checklist_block`, `stamp`, `_plugin_sets`, the module docstring), its tests and sabotage entries, `.crew/standards.md` (REPO-03's rule text), `.crew/verify.json` (rule 31 gains two test files; its `seconds` and `why`), `CHANGELOG.md` (T-0085's bump bullet, two lines to three), `plugin/crew/BUDGETS.md:10-11` (the count, in place), `plugin/crew/README.md` (three table rows, in place), `plugin/crew/commands/implement.md` (two lines reflowed in place; still 120 lines), `plugin/crew/commands/review.md` (step 6's reviewer-cell line becomes three, so lines below `:530` move by 2), `plugin/crew/skills/crew-standards/SKILL.md`, ADR 0004 and the working-with-codex guide. Every `path:N` citation in this note into those files was compared by script between `8a084c6c` and `07bcaf3b`: every hit is a `plugin/crew/BUDGETS.md:11` citation inside an earlier dated provenance paragraph, left as history; no body claim moved. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `07bcaf3b` -> `8abf7ffe` on 2026-09-28 (T-0085 provisional re-bump, crew 1.0.56).** `8abf7ffe` moves crew's version 1.0.55 -> 1.0.56 in place (`.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`), because the round-1 fixes changed `plugin/crew/` after 1.0.55 was set and `scripts/check-marketplace.py`'s version-drift check failed on it; it also rewords `.crew/standards.md` REPO-03 (the provisional bump) and T-0085's `CHANGELOG.md` heading and bump bullet (three lines to four). Every `path:N` citation in this note into those files was compared by script between `07bcaf3b` and `8abf7ffe`: the version-file citations hold (value changed in place, same line) and every hit sits inside an earlier dated provenance paragraph, left as history; no body claim states the version. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `3648f59a` / `8abf7ffe` -> `e3f5fa49` on 2026-09-29 (T-0085 merges main `2693d0fa`, T-0075 landed as crew 1.0.59, and applies the owner-accepted round-1 standards amendments).** `0fd1bdf8` reverts T-0085's provisional crew 1.0.56 bump (`8abf7ffe`); `0fd92334` merges origin/main `2693d0fa` into `T-0085-build` (mechanical conflicts only: crew version lines take main's 1.0.59, crew counts take main's 36 commands with T-0085's 30 skills, `plugin/crew/tests/sabotage.py` registers both `CONFIG_MENU_MUTATIONS` and `STANDARDS_MUTATIONS`, anchors, provenance paragraphs, INDEX history cells, diagram notes, generated rules and graph); `e3f5fa49` amends GEN-01 and GEN-04 in `plugin/crew/skills/crew-standards/references/generic.md` and REPO-03 in `.crew/standards.md`, drops the version from T-0085's `CHANGELOG.md` heading and re-measures `plugin/crew/BUDGETS.md`. The build branch now declares main's 1.0.59 and carries no bump of its own (REPO-03 as amended). Every `path:N` citation outside provenance was mapped by script (difflib equal blocks; a same-size in-place replacement counts as the same line) from the side that wrote it - `3648f59a` for a line in main's copy of this note, `0fd1bdf8` for a line only in T-0085's - to `e3f5fa49`, and every line that did not map to itself was read with `sed -n` / `grep -n`; the script attributes some bare `:N` to the wrong file, and those were read and hold. None moved; the crew count sentences now read 36 commands and 30 skills. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `e3f5fa49` -> `001f8a78` on 2026-09-29 (T-0085 successor plan, review round 2's fixes).** `bc3602df`..`001f8a78` change `plugin/crew/hooks/scripts/crew_standards.py` (`_scope` gains the merge-base fallback for a kept but unusable scope record, `_has_scope_entry` and `_noted` are new, so every definition from `_scope` down moves by +8 to +30 lines), its tests (`test_crew_standards.py`, `test_review_run_standards.py`, `test_lifecycle_commands.py`) and `plugin/crew/tests/sabotage_standards.py` (nineteen new entries; `STANDARDS_MUTATIONS` moves `:21` -> `:35`), `plugin/crew/skills/crew-standards/SKILL.md` (step 3, +5 lines), `plugin/crew/README.md` (one table row, in place), `CHANGELOG.md` (one bullet in T-0085's section, so every line below it moves +8) and `plugin/crew/BUDGETS.md:11` (the count, in place). Every `path:N` citation in this note into those files was mapped by script (difflib equal blocks; a same-size in-place replacement counts as the same line) from `e3f5fa49` to `001f8a78`; none moved. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `001f8a78` / `bbd9a66d` -> `a7f9c5e4` on 2026-09-29 (T-0085 merges main `8ab733d7`, T-0010 landed as crew 1.0.61).** `a7f9c5e4` merges origin/main `8ab733d7` (T-0010 landed as crew 1.0.61) into `T-0085-build` after T-0085's review round 3 fixes (`33521aa4`), with mechanical conflicts only: crew version lines take main's 1.0.61 with T-0085's 30 skills (the build branch carries no bump, REPO-03 as amended), `plugin/crew/tests/sabotage.py` registers `POLICY_MUTATIONS`, `APPROVAL_MUTATIONS`, `CONFIG_MENU_MUTATIONS` and `STANDARDS_MUTATIONS` on `:3056`, anchors, provenance (both sides kept, main's first), INDEX history cells, version sentences, diagram headers, generated rules and graph. Every body `path:N` citation was traced to the side whose copy of this note carries its line (`33521aa4` or `8ab733d7`) and mapped from that side's anchor to `a7f9c5e4` through a difflib line diff (`/root/crew-tmp/t-0085/citemap.py`, machine-local; only cited files that changed; a bare file name resolved when unique in `git ls-files`); each citation that did not map to itself was read with `sed -n` / `grep -n`, and the script's misattributed bare `:N` (a `sabotage_autopilot.py` or `crew_ticket.py` line after another file's name, a history list's earlier positions) were read and hold. `plugin/README.md:414` changed in place on T-0085's side (29 -> 30 skills) and holds; the version files changed in place (1.0.61). No install script changed on either side; neither was executed. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `a7f9c5e4` / `b4f39fd3` -> `69c7edbd` on 2026-09-30 (T-0085's landing merge of main `a61a6f38`, crew 1.0.70).** `69c7edbd` merges T-0085's build head `0c6f01e0` (round 4, owner-accepted) onto origin/main `a61a6f38` (crew 1.0.69: #263-#267 and T-0088) on `T-0085-land`, and sets crew 1.0.70. Every body `path:N` citation was mapped by script (`difflib` equal blocks, from the anchor of whichever side's copy of this note carries the line - `a7f9c5e4` for T-0085's, main's own anchor for main's - to `69c7edbd`); each that mapped to one new line was moved, and each that did not map, or mapped differently from the two sides, was read with `sed -n` / `grep -n`. The script attributes a bare `:N` to the last path cited with a line number, so a bare `:N` after a path named without one (`.crew/verify.json` rule ranges, `crew_tfplan.py`, `sabotage_autopilot.py`, `crew_ticket.py`, `crew_standards.py`) was read against its real file and put back where the script moved it wrongly; `.crew/verify.json` lines up to `:339` did not move, and T-0085's rule is now `:361-373`, the last. A bare `review.md` citation is ambiguous since #267 added `crew-qa-standards/references/review.md`, so the script skipped those; `plugin/crew/commands/review.md` moved only below `:543` (+1, +3), and its cited lines above that were re-read. In this note the plugin-level skills count reads 31 (T-0085's `crew-standards` plus #267's `crew-qa-standards`); the version and count lines at `plugin/PLUGINS.md:17`, `plugin/README.md:414` and `INSTALLATION.md:252` changed in place. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `69c7edbd` -> `7c86bd13` on 2026-09-30 (T-0085 landing: one sabotage anchor re-taken).** `git diff --name-only 69c7edbd 7c86bd13`, refresh artifacts aside, returns only `plugin/crew/tests/sabotage_standards.py`: the find and replace text of "review.md loses the self-check refusal" now end at `rebuild.` / `provider.`, because the merge joined main's exit-5 sentence onto that line. No line was added or removed; no citation moved. No suite was executed for this note.

**Re-anchored `7c86bd13` (`obsidian-vault`: `69c7edbd`) -> `c04dd2ef` on 2026-09-30 (T-0085 landing: `commands/review.md` rewrapped to its 551-line allowance, crew 1.0.71 then 1.0.72).** `git diff --name-only 7c86bd13 c04dd2ef`, refresh artifacts aside, returns the crew version files, `CHANGELOG.md`, `plugin/crew/BUDGETS.md` (20,707 lines, in place) and `plugin/crew/commands/review.md`: step 3's item 3 gains its last line on `:511`, item 4 and its `gh pr comment` paragraph and steps 8-9 are rewrapped at 100 columns, and the closing sentence is joined, taking the file from 557 to 551 lines with no text changed. Every line this note cites in `review.md` is at or above `:511` and holds; the version this note states now reads 1.0.72. No suite was executed for this note.

**Re-anchored `c04dd2ef` -> `8a89a596` on 2026-09-30 (T-0085 landing: catch-up merge of main `6813749b`, #268 T-0097, crew 1.0.70; T-0085 now 1.0.73).** `git diff --name-only 54192270 8a89a596` returns the crew version files, `CHANGELOG.md` (T-0097's entry below T-0085's), the 11 `.ps1` hook carriers (one `Resolve-CrewPython` line each: an empty probe answer is no longer piped into `ConvertFrom-Json`), `plugin/crew/tests/sabotage_scope.py` and `plugin/crew/tests/test_ps1_python_probe.py`. Citations into those files were moved by a line diff (`/root/crew-tmp/t-0085/remap_merge.py`, 11 moved, 0 unmapped); version-line citations (`marketplace.json:218`, `plugin.json:3`, `PLUGINS.md:14`) hold by line and now read 1.0.73. The `Resolve-CrewPython` copies stay byte-identical across all 11 carriers, so the copy-list claims hold. No suite was executed for this note.

**Re-anchored `8a89a596` -> `9b6b0da7` on 2026-09-30 (T-0085 landing: Windows fail-open fix, crew 1.0.74).** `git diff --name-only 58431f49 9b6b0da7` returns the crew version files, `CHANGELOG.md`, `plugin/crew/hooks/scripts/crew_standards.py` (`import stat`, new `_ancestor_problem` before `gate_applies`, which now proves a receipt absent only when the nearest existing ancestor is a directory), `plugin/crew/tests/test_crew_standards.py` (new `test_gate_applies_when_a_file_parent_is_reported_as_not_found`) and `plugin/crew/tests/sabotage_standards.py` (one entry). Path-qualified citations into those files were moved by a line diff (`/root/crew-tmp/t-0085/remap_merge.py`, 10 moved, 0 unmapped); `crew.md`'s bare `crew_standards.py` citations in its standards section were moved by the same diff (27). No suite was executed for this note.

**Re-anchored `9b6b0da7` -> `5c9a9db2` on 2026-09-30 (T-0085 landing: sabotage entry re-targeted, crew 1.0.75).** `git diff --name-only 33da9c91 5c9a9db2` returns the crew version files, `CHANGELOG.md` and `plugin/crew/tests/sabotage_standards.py` (the "receipt that cannot be looked up" entry now flips `gate_applies`' `OSError` verdict). Path-qualified citations into those files were moved by a line diff (`/root/crew-tmp/t-0085/remap_merge.py`, 9 moved, 0 unmapped). No suite was executed for this note.

## Re-anchor provenance - `b142d8e3` / main `5c9a9db2`-`37f4e807` -> `2697bf67`, 2026-09-30 (T-0087 review round 5 successor, merge of main `9af34e57`)

`4e97588e` (golden leak check) and `2de03e41` (review ledger successors path) fix review round 5; `7b62e321` adds their sabotage entries. `7ccff1db` merges origin/main `9af34e57` (T-0085 landed as crew 1.0.75, with #268, #276, #277, #279) into `T-0087-build` with a merge commit, and `2697bf67` re-sets crew 1.0.76. The merge's map conflicts were mechanical: a hunk that differed only in numbers or in the anchor took main's side, and a provenance hunk kept both. Every body citation of the form `path:line` was then re-mapped by script (difflib from the parent the line came from - T-0087's `7b62e321` for a line T-0087 carries, main's `9af34e57` otherwise - to this tree; a bare `:N` binds to the last path named on its line). `.crew/verify.json` now holds T-0085's standards rule as rule 35 (`:361-373`) and T-0087's harness rule as rule 36 (`:374-399`); those descriptions were re-read by hand. Citations the script could not attribute predate this change and were left unchanged. Re-anchor only: no other claim moved and nothing was executed for this note.

## Re-anchor provenance - `2697bf67` -> `45f32c3c`, 2026-09-30 (T-0087, after merging main `9af34e57`)

`5f52ba61` re-maps `plugin/crew/docs/external-tool-formats.md`'s `review_run.py` and `review.md` citations to the merged tree (in place; no line moved), and `2b7e7a05`/`45f32c3c` step crew back and re-set 1.0.76 as the last `plugin/crew` commit. No citation in this note points into a line that moved. Re-anchor only: no claim moved and nothing was executed for this note.

## Re-anchor provenance - `45f32c3c` -> `7c88bf3d`, 2026-09-30 (T-0087 review round 6 fix)

`cff30f72` makes the committed-corpus test in `plugin/crew/tests/test_review_golden.py` run `golden_build.leak` on every fixture (host name included), adds `test_corpus_leak_check_refuses_a_planted_host_name`, and adds sabotage entries (ah)-(ai) to `plugin/crew/tests/sabotage_tooling.py`; its CHANGELOG bullet moved later CHANGELOG lines by 4, and the CHANGELOG citations above were re-mapped by script (difflib `45f32c3c` -> `7c88bf3d`). `49ed9a29` / `7c88bf3d` step crew back and re-set 1.0.76. No other cited line moved. Re-anchor only: nothing was executed for this note.

**Re-anchored `5c9a9db2` -> `06cb9b51` on 2026-09-30 (T-0086 slice 1: the Python standards set, on main `301e478a`).** `git diff --name-only 5c9a9db2 06cb9b51` over this note's paths returns T-0086's files - `plugin/crew/skills/crew-standards/references/python.md` (new, set PYTHON), `plugin/crew/skills/crew-standards/SKILL.md`, `plugin/crew/skills/stack-python/SKILL.md`, `plugin/crew/tests/test_crew_standards.py` (four new tests), `plugin/crew/tests/sabotage_standards.py` (three entries), `plugin/crew/README.md`, `plugin/PLUGINS.md` (rows only), `plugin/crew/BUDGETS.md` (count only) and `CHANGELOG.md` (T-0086's entry on top) - plus main's own commits since `5c9a9db2`. Path-qualified citations into changed files were moved by a line diff (`/root/crew-tmp/t-0086/remap.py`, 9 moved); `plugin/crew/BUDGETS.md:10-11` citations stay on the claim line, whose number changed in place. No suite was executed for this note.
**Re-anchored `06cb9b51` -> `35100955` on 2026-09-30 (T-0086's merge of main `9af34e57`, #279: CI triggers, concurrency, PR CI on Python 3.12 only).** `git diff --name-only 06cb9b51 35100955` returns, outside refresh artifacts, only `.github/workflows/*.yml`, `AGENTS.md` and `.crew/verify.json` (one line rewritten in place, line count unchanged). No `AGENTS.md:NN` citation exists in any map, and no claim outside verification-harness.md states the CI trigger shape (checked by grep for `push, pull_request`, `six workflows`, `three Python versions`, `windows-latest`), so no citation moved. No suite was executed for this note.

**Re-anchored `35100955` -> `fb292689` on 2026-09-30 (T-0086 review round 1's FIX: PYTHON-07's finding count).** `git diff --name-only 35100955 fb292689` returns only `plugin/crew/skills/crew-standards/references/python.md` (PYTHON-07's Why, `6` -> `7` in place, line count unchanged), `plugin/crew/tests/test_crew_standards.py` (two tests and a pinned table inserted after `:302`) and `plugin/crew/tests/sabotage_standards.py` (four docstring lines after `:43`, two entries at the end; `STANDARDS_MUTATIONS` `:54` -> `:57`, 49 entries by `len()`). Every `path:N` citation into those files sits inside an earlier dated provenance paragraph, left as history. No suite was executed for this note.

**Re-anchored `fb292689` -> `f2cf0508` on 2026-09-30 (T-0086's merge of main `b601d450`, #280 L-0521: opt-in self-hosted runners).** `git diff --name-only fb292689 f2cf0508` returns, outside refresh artifacts, only `.github/workflows/pytest-crew.yml` (the `test` and `crew-shell-matrix` `runs-on` expressions) and `AGENTS.md` (one inserted paragraph after `:50`). No map cites `AGENTS.md:NN` or `.github/workflows/pytest-crew.yml:NN`; the one claim about those jobs' runner placement is verification-harness.md's, which main's own L-0521 commit already updated and the merge carries. No citation moved. No suite was executed for this note.

**Re-anchored `f2cf0508` -> `38b220cf` on 2026-09-30 (T-0086 review round 2's FIXes, merge of main `a7524aac` (T-0087, crew 1.0.76) as `142421d0`, crew 1.0.77).** `27387d83` fixes round 2: `plugin/crew/skills/crew-standards/references/python.md` (PYTHON-01's EncodingWarning quote whole, +1 line; PYTHON-03's splitlines table escapes U+2028/U+2029), `plugin/crew/tests/test_crew_standards.py` (two tests before `test_python_set_applies_to_python_files_only`), `plugin/crew/tests/sabotage_standards.py` (four docstring lines, two entries; `STANDARDS_MUTATIONS` `:57` -> `:61`, 51 by `len()`), `plugin/crew/BUDGETS.md` and `CHANGELOG.md`. `142421d0` merges main's T-0087 with a merge commit; its map conflicts were mechanical: anchors took T-0086's side, provenance hunks kept both (main's first), and one-line hunks differing only in numbers took theirs plus T-0086's own shift (ours + theirs - base, per number); INDEX rows keep main's history cell plus T-0086's additions; `sabotage.py`'s import `:84` -> `:85` and append `:3061` -> `:3062` were set in the body. `38b220cf` sets crew 1.0.77 (`plugin/crew/.claude-plugin/plugin.json:3`, `.claude-plugin/marketplace.json:218`, `plugin/PLUGINS.md:14`). BUDGETS.md re-measured at 21,421 lines across 136 files. No suite was executed for this note.

## Re-anchor provenance - `3648f59a` -> `ea764992`, 2026-09-29 (T-0094)

T-0094 is built on origin/main `2693d0fa`: `3648f59a` plus T-0075's landing branch (crew 1.0.56-1.0.59) and `17d057db`, which re-pinned `README.md:12`/`:18` to `e878cc31`. The paths this note cites that T-0094 changed are `.crew/verify.json` (rule 25 grew three lines; no rule position is cited here outside provenance) and `plugin/crew/README.md` (not cited by line outside provenance), plus the version files, whose crew lines changed in place. The Landmines bullet on the install-URL pin is corrected: it is current at `ea764992` (`git log e878cc31..ea764992` over both install scripts is empty), and its stale-pin history is kept below that sentence.

Checked by a script mapping every `path:N` citation outside provenance sections, and every bare `:N` carried from the last path named in its paragraph, from `3648f59a` to the tree at `ea764992` (difflib equal blocks); the only non-self mappings were `README.md:12` and `:18`, changed in place by the re-pin, read with `sed -n`. Nothing else was executed for this note.

## Re-anchor provenance - `ea764992` -> `f79e9f58`, 2026-09-29 (T-0094 review round 1)

`f79e9f58` ends T-0094's review-round-1 fixes (`abe87bc2`..`f79e9f58`). Of the paths this map cites, `.crew/verify.json` (rule 25's `seconds` and `why`, in place), `plugin/crew/README.md` (one refresh-admission paragraph reworded in place) changed; no citation here moved (checked by script, every `path:N` compared line by line from `ea764992` to `f79e9f58`, then the hits read). No claim changed.

## Re-anchor provenance - `bbd9a66d` + `f79e9f58` -> `6375524b`, 2026-09-29 (T-0094 merges `8ab733d7`; review round 2's successor)

`f050cd47` merges origin/main `8ab733d7` (T-0010 landed as crew 1.0.61, its code maps anchored `bbd9a66d`) into T-0094-build at `ca5b1f35` (T-0094's side anchored `f79e9f58`, plus review round 2's FIX 1 `da1532d6` and FIX 2 `ca5b1f35`). The artifact conflicts were anchor, version, provenance and cited-line text only: both sides' provenance kept, main's first; INDEX history columns joined; body hunks resolved to main's lines except T-0094's own refresh-admission paragraph and refresh-check entry point. After it, `157237c2` splits `.crew/verify.json` rule 25 (the admission suite is rule 32 at `:342-349`, rule 25 `:269-287`, every later rule moves by the merged and split lengths), restates the sabotage counts in `plugin/crew/tests/sabotage_refresh.py`, and edits `plugin/crew/README.md` and `docs/guides/crew/src/daily-workflow-scope.md` in place; `ef5b4c89` re-measures `plugin/crew/BUDGETS.md` (19,500 lines across 128 files); `fc348c89` sets crew 1.0.62; `6375524b` rebuilds the daily-workflow guide. `git diff --name-only bbd9a66d 6375524b`, refresh artifacts aside, is T-0094's files only: `.claude-plugin/marketplace.json`, `.crew/verify.json`, `CHANGELOG.md`, the daily-workflow guide and its source, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `commands/done.md`, `commands/implement.md`, `completion_audit.py`, `crew_refresh_check.py`, `scope_guard.py` and T-0094's five test files. Every body `path:N` citation was traced to the side whose copy of this note carries its line (`8ab733d7` or `ca5b1f35`) and mapped to HEAD with a `difflib` line diff (`/root/crew-tmp/t-0094/cite_map_merge.py`, machine-local); each that did not map to itself was read with `sed -n` / `grep -n`. The script takes a bare `:N` as the last path named on its line, so some flags were that misattribution and hold; a history position ("before", "at <sha>", "since ...") was left as written. No install script, `README.md`, `INSTALLATION.md` or `scripts/check-marketplace.py` changed; no body citation moved. Neither install script was executed.

## Re-anchor provenance - `6375524b` -> `f5d0f1b1`, 2026-09-30 (T-0094 merges `a61a6f38`, crew 1.0.70)

`0cd952b2` merges origin/main `a61a6f38` (T-0088 landed as crew 1.0.69, after #263-#267: crew 1.0.62-1.0.68, the review gate `review_gate.py`, the `crew-qa-standards` skill, parallel CI and `CLAUDE.md`'s evidence moved to `docs/claude-md-evidence.md`) into T-0094-build at `d331c192`. Its conflicts were the version lines, `CHANGELOG.md` (both entries kept, T-0094's first), `.crew/verify.json` (T-0094's rule 32 kept, main's three new rules after it as 33-35), `crew_refresh_check.py`'s imports (both kept) and `plugin/crew/BUDGETS.md` (re-measured, 19,921 lines across 132 files); no code map, diagram or rule file conflicted (main's maps were still at `bbd9a66d`, but for `obsidian-vault.md`). `f5d0f1b1` sets crew 1.0.70, one past main's 1.0.69. Per-path: `git diff --name-only 6375524b f5d0f1b1 -- <the 43 tracked paths this note cites>` returns `.claude-plugin/marketplace.json`, `.crew/verify.json`, `CHANGELOG.md`, `CLAUDE.md`, `INSTALLATION.md`, `README.md`, `plugin/PLUGINS.md`, `plugin/README.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/CONFIG.md`, `plugin/crew/README.md`, `plugin/crew/commands/review.md`, `plugin/crew/hooks/scripts/crew_autopilot.py`, `plugin/crew/hooks/scripts/crew_config.py`, `plugin/crew/hooks/scripts/crew_context.py`, `plugin/crew/hooks/scripts/crew_ticket.py`, `plugin/crew/tests/sabotage.py`, `plugin/crew/tests/sabotage_autopilot.py`. Citations were re-mapped by a `difflib` line diff from each cited file's copy at the old anchor to `f5d0f1b1` (`/root/crew-tmp/t-0094/cite_apply2.py`, `cite_ident.py`, `cite_explicit.py`, machine-local): an explicit `path:N`, and a bare `:N` whose file is the one named before it in the paragraph, or the one whose old line carries the identifier beside the citation; every mapped line is text-identical at both ends. History positions ("at <sha>", "before", "on <branch>", "it was") and the provenance sections were left as written; a bare `:N` the scripts attributed to the wrong file was found by that identifier check and put back. Neither install script, `scripts/check-marketplace.py` nor `README.md`'s install URLs changed; the crew skill count the note carries beside them is 30 now (re-read at `f5d0f1b1`). No body citation moved. Neither install script was executed.

**Re-anchored `f5d0f1b1` -> `2255fb4d` on 2026-09-30 (T-0094 review round 3).** `2255fb4d` is T-0094's review-round-3 fix commit (Codex round 3 on `e0ccd3f7`: 0 BLOCK / 4 FIX). `git diff --name-only f5d0f1b1 2255fb4d` returns `.crew/codemap/crew.md`, `CHANGELOG.md`, `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/tests/sabotage_refresh.py` and `plugin/crew/tests/test_refresh_admission.py`; the two commits after `f5d0f1b1` before it are refresh artifacts only. This note cites those files by name or in its provenance only; no body citation moved.

**Re-anchored `2255fb4d` -> `0c19512c` on 2026-09-30 (T-0094 crew 1.0.71).** `0c19512c` sets crew 1.0.71 (review round 3's fixes changed `plugin/crew/` after 1.0.70 was set, and origin/main is 1.0.70 too, T-0097 #268). Per-path: `git diff --name-only 2255fb4d 0c19512c` over this note's cited paths returns only `plugin/crew/README.md` (two in-place "since 1.0.70" -> "since 1.0.71" edits, line count unchanged), beside the version files and `CHANGELOG.md` (release bookkeeping). No body citation moved.

**Re-anchored `0c19512c` (T-0094) / `5c9a9db2` (main) -> `1b9e4bfe` on 2026-09-30 (T-0094 merges main `9af34e57`, T-0085 landed as crew 1.0.75; review round 4's successor, crew 1.0.76).** `e1144866` merges origin/main `9af34e57` into T-0094-build at `7c261a19`; this map conflicted on anchor, version, provenance and cited-line text only (both sides' provenance kept, main's first; body hunks resolved to main's lines for files T-0094 does not change, T-0094's for its own). `c815bed8` and `f3fe692f` are the successor's code steps (`crew_refresh_check.py`: `_names_no_commit` new before `_moved_from`, `_rendered_verdict` pairs its source case-folded; `completion_audit.py`: `_default_artifacts` new after `_verdicts`; their tests, fixtures and sabotage entries), and `1b9e4bfe` sets crew 1.0.76 with the README, CHANGELOG and daily-workflow guide text. Per-path, `git diff --name-only 5c9a9db2..1b9e4bfe` over this note's 50 cited, existing paths returns `.claude-plugin/marketplace.json`, `.crew/verify.json`, `docs/guides/crew/src/daily-workflow-scope.md`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `plugin/crew/commands/implement.md`, `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/hooks/scripts/scope_guard.py`, `plugin/crew/tests/sabotage_refresh.py`, `plugin/crew/tests/test_refresh_admission.py`; from T-0094's side, `0c19512c..1b9e4bfe` adds `.crew/standards.md`, `plugin/README.md`, `plugin/crew/commands/review.md`, `plugin/crew/hooks/scripts/crew_standards.py`, `plugin/crew/hooks/scripts/review_prompt.py`, `plugin/crew/skills/crew-setup/SKILL.md`, `plugin/crew/skills/crew-standards/SKILL.md`, `plugin/crew/skills/crew-standards/references/generic.md`, `plugin/crew/tests/sabotage.py`, `plugin/crew/tests/sabotage_scope.py`, `plugin/crew/tests/sabotage_standards.py`, `plugin/crew/tests/test_crew_standards.py`, `plugin/crew/tests/test_lifecycle_commands.py`, `plugin/crew/tests/test_ps1_python_probe.py`, `plugin/crew/tests/test_review_prompt.py` (main's T-0085, T-0097 and CI changes). Every body `path:N` citation was mapped by `/root/crew-tmp/t-0094/cite_map_merge.py` (difflib equal blocks, from the anchor of whichever side's copy carries the line; `MAIN_REV=origin/main`, `OURS_REV=7c261a19`) and each one it reported was read at HEAD. The skills figure takes main's 31. No body citation moved. No suite was executed for this note.

**Re-anchored `1b9e4bfe` -> `8a15557b` on 2026-09-30 (T-0094: `implement.md` step 6 rewrapped to its 120-line budget).** `git diff --name-only 1b9e4bfe 8a15557b`, refresh artifacts aside, returns `plugin/crew/BUDGETS.md` (the count, in place: 20,711 lines) and `plugin/crew/commands/implement.md`: the merged step-6 paragraph (T-0094's admission sentence beside main's self-check paragraph) was 122 lines, over `test_lifecycle_commands.py`'s 120-line command budget, and is rewrapped to 104 columns with its wording unchanged, so every line from the self-check paragraph down sits where main has it again (tracker `:112`, step 7 `:116`); the refresh check is still `:93`. No other body citation moved. No suite was executed for this note beyond `test_lifecycle_commands.py`.

**Re-anchored `8a15557b` -> `a0c171c7` on 2026-09-30 (T-0094 review round 5).** `git diff --name-only 8a15557b a0c171c7` over this note's cited paths, refresh artifacts and release bookkeeping aside, returns `docs/guides/crew/src/daily-workflow-scope.md` (one could-not-tell sentence extended, +1 line at `:104-106`), `plugin/crew/README.md` (one sentence extended in place, line count unchanged), `plugin/crew/hooks/scripts/crew_refresh_check.py` (`_present` new at `:327`, everything below it +19 to +25 lines), `plugin/crew/tests/sabotage_refresh.py` (+4 docstring lines, five entries appended after the round-5 marker), `plugin/crew/tests/test_refresh_admission.py` (+1 import line, the round-5 tests appended). No body citation of this note names a moved line of those files. Citations checked with `/root/crew-tmp/t-0094/cite_apply3.py` (DRY, machine-local) and `grep -n`. No suite was executed for this note.

**Re-anchored `a0c171c7` (T-0094) / main -> `a0db0703` on 2026-09-30 (T-0094 merges origin/main `a7524aac`, T-0087 landed as crew 1.0.76, #281, and L-0521, #280; crew 1.0.77, before review round 6).** `f6f2c2f0` merges `a7524aac` into T-0094-build at `75565970`; `a0db0703` re-sets the version one past main's 1.0.76 (plugin.json, marketplace.json, `plugin/PLUGINS.md:14`, two README sentences, the CHANGELOG heading). The code maps conflicted on anchor, version, provenance and cited-line text only: both sides' provenance kept, main's first. In body hunks a citation into a file only one side changed takes that side's number (`crew_autopilot.py`, `review_ledger.py`, `sabotage.py` and `CLAUDE.md` main's; `crew_refresh_check.py` T-0094's); positions in files both sides changed (`.crew/verify.json`, `plugin/crew/tests/sabotage_refresh.py`) were re-measured on the merged tree: T-0087's harness rule is rule 37 at `.crew/verify.json:384-409`, after T-0094's rule 32; `REFRESH_MUTATIONS` is at `plugin/crew/tests/sabotage_refresh.py:119`; the CLAUDE.md Lessons line is `:144`. Checked by a script mapping every `path:N` citation outside provenance sections, and every bare `:N` carried from the last path named in its paragraph, from each side's anchor (`a0c171c7` and main's own) to `a0db0703` (difflib equal blocks): no citation outside those re-measured positions fails both mappings. Carried as main has them, not corrected here: main's own `crew_autopilot.py` body citations in `crew.md` that already lag main's tree by a few lines (e.g. `next_phase` `:556`, the def is at `:559`) - outside T-0094's change.

**Re-anchored `a0db0703` (T-0094) / `38b220cf` (main) -> `65abeb8d` on 2026-09-30 (T-0094 merges origin/main `549cda24`, T-0086 landed as crew 1.0.77, #282, as `44407f8e`; the owner's split moves the harness half to L-0540 at `c974f997`; review round 6's successor `6ecb6403`..`b17266ed`; crew 1.0.78 at `65abeb8d`).** Per-path, `git diff --name-only a0db0703 65abeb8d` over this note's 68 cited, tracked paths returns `.claude-plugin/marketplace.json`, `.crew/codemap/crew.md`, `CHANGELOG.md`, `docs/guides/crew/src/daily-workflow-scope.md`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/hooks/scripts/scope_guard.py`, `plugin/crew/skills/crew-standards/SKILL.md`, `plugin/crew/skills/crew-standards/references/python.md`, `plugin/crew/skills/stack-python/SKILL.md`, `plugin/crew/tests/sabotage_refresh.py`, `plugin/crew/tests/sabotage_standards.py`, `plugin/crew/tests/test_crew_standards.py`, `plugin/crew/tests/test_refresh_admission.py`; from main's side, `git diff --name-only 38b220cf 65abeb8d` over the same paths returns `.claude-plugin/marketplace.json`, `.crew/codemap/crew.md`, `.crew/verify.json`, `CHANGELOG.md`, `docs/guides/crew/src/daily-workflow-scope.md`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `plugin/crew/commands/implement.md`, `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/tests/test_refresh_admission.py`. The merge's conflicts in this map were the anchor and provenance only (both kept, main's first). No body citation in this map names a line the successor or the merge moved (checked with `/root/crew-tmp/t-0094/cite_map_merge.py`, `MAIN_REV=origin/main`, `OURS_REV=b4d87187`, machine-local). No suite was executed for this note.

**Re-anchored `65abeb8d` -> `1f21f73b` on 2026-09-30 (T-0094 review round 7: `902fb96a`..`91da43bc` code and tests, docs, guide rebuilt, crew 1.0.78 un-set and re-set as `1f21f73b`).** `git diff --name-only 65abeb8d 1f21f73b` returns `CHANGELOG.md`, `docs/guides/crew/crew-1.0-daily-workflow.docx`, `docs/guides/crew/crew-1.0-daily-workflow.html`, `docs/guides/crew/crew-1.0-daily-workflow.pdf`, `docs/guides/crew/src/daily-workflow-scope.md`, `plugin/crew/README.md`, `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/tests/test_refresh_admission.py`. No body citation in this map names a line that moved. No suite was executed for this note.

**Re-anchored `1f21f73b` (T-0094) / main -> `17d0b1d2` on 2026-09-30 (T-0094 merges origin/main `d1462bbd`, L-0529 landed as crew 1.0.80 (#283), and re-sets crew 1.0.81 in the merge commit).** `git diff --name-only 79ef56c4 17d0b1d2`, refresh artifacts aside, returns `.claude-plugin/marketplace.json`, `CHANGELOG.md`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/README.md`, `plugin/crew/tests/crew_fixtures.py`, `plugin/crew/tests/test_context_watch_python_resolver.py`, `plugin/crew/tests/test_event_claim_crash_safety.py`, `plugin/crew/tests/test_path_link_farm.py`, `plugin/crew/tests/test_ps1_python_probe.py`, `plugin/obsidian-vault/.claude-plugin/plugin.json`, `plugin/obsidian-vault/hooks/scripts/_test/test_python_probe_proof.py`: main's L-0529 files plus the version statements. The merge's conflicts were version lines and the generated rules' stamps; main's body lines kept. No body citation moved (checked with `/root/crew-tmp/t-0094/cite_map_merge.py`, `MAIN_REV=origin/main`, `OURS_REV=79ef56c4`; its only flags are history positions in verification-harness.md's per-commit lists, left as written). No suite was executed for this note.

## Re-anchor provenance - main `6a8c60b1` -> `c43a54c1`, 2026-09-30 (T-0028, feature half, crew 1.0.84)

T-0028 (the Kimi Code provider, feature half after the owner's split; the review launch is L-0527)
merged origin/main `6a8c60b1` (L-0531 #284 and T-0099 #278, crew 1.0.83) with rerere disabled, taking main's code
maps. The branch differs from main only in the Kimi provider's feature files (`crew_state.py`,
`crew_config.py` with the launch gate, `kimi_probe.py`, the templates, provider docs and tests,
`.crew/verify.json`, the release files). This note is main's copy; every body citation into a
changed file was mapped by a `difflib` line diff from `6a8c60b1` to `c43a54c1` with
`/root/crew-tmp/t-0028/refresh/reanchor2.py` (machine-local), each moved citation landing on the
same line text. T-0028's earlier branch provenance is in git history. Re-anchor
only (owner refresh-artifact standing rule, 2026-09-28); no test suite was executed for this note.

## Re-anchor provenance - `c43a54c1` -> `f4adf923`, 2026-09-30 (T-0028 re-sets crew 1.0.85)

`f4adf923` changes only the release files (crew 1.0.84 -> 1.0.85: `plugin.json`, `marketplace.json`,
`PLUGINS.md`, the README's version mention and the CHANGELOG heading), because T-0505 targets
1.0.84. No cited line moved; the version sentences were re-read. Re-anchor only (owner
refresh-artifact standing rule, 2026-09-28); no test suite was executed for this note.

## Re-anchor provenance - `f4adf923` -> `328fdf4a`, 2026-09-30 (T-0028 round-7 fixes, crew 1.0.85 re-set)

`233701d5` fixes review round 7's four FIXes in `kimi_probe.py` (the owner accepted round 7 and
ordered the fixes); `328fdf4a` re-sets crew 1.0.85. Body citations were mapped by `difflib` from
`ea90a4e4` to `328fdf4a` with `/root/crew-tmp/t-0028/refresh/reanchor2.py` (machine-local), each moved
citation landing on the same line text. Re-anchor only (owner refresh-artifact
standing rule, 2026-09-28); no test suite was executed for this note.

**Re-anchored `17d0b1d2` -> `c4e2eb98` on 2026-09-30 (L-0520 PR 1, the merge train CLI, after merging main 42d5ef58 (T-0094)).** `git diff --name-only 17d0b1d2 c4e2eb98` adds L-0520's PR 1 outside refresh artifacts (crew_train.py, done.md, README, two guides, CHANGELOG, TODO, BUDGETS.md in place, verify.json, two tests); path-qualified citations outside dated provenance were moved by a line diff (`/root/crew-tmp/l-0520/tools/l0520_remap.py`, machine-local). No suite was executed for this note.

**Re-anchored `c4e2eb98` -> `0be97503` on 2026-09-30 (L-0520 PR 1 merges main 42af3fb7 (L-0531)).** `git diff --name-only c4e2eb98 0be97503` returns, outside refresh artifacts, only L-0531's `plugin/crew/tests/sabotage_qa.py`, `.crew/verify.json` and release bookkeeping; path-qualified citations were moved by a line diff (`/root/crew-tmp/l-0520/tools/l0520_remap.py`). No suite was executed for this note.

**Re-anchored `0be97503` -> `14bb59ef` on 2026-09-30 (L-0520 PR 1 merges main 6a8c60b1 (T-0099)).** `git diff --name-only 0be97503 14bb59ef` returns, outside refresh artifacts, T-0099's `review_prompt.py`, `sabotage_review.py`, `test_review_prompt.py` and release bookkeeping; path-qualified citations were moved by a line diff (`/root/crew-tmp/l-0520/tools/l0520_remap.py`). No suite was executed for this note.

**Re-anchored `14bb59ef` -> `8bf710ed` on 2026-09-30 (L-0520 PR 1 review round 1 fixes).** `git diff --name-only 14bb59ef 8bf710ed` returns crew_train.py, done.md and README.md (edits in place), BUDGETS.md, two tests and the version files; path-qualified citations outside dated provenance were moved by a line diff (`/root/crew-tmp/l-0520/tools/l0520_remap.py`). No suite was executed for this note.

**Re-anchored `8bf710ed` -> `14b52c91` on 2026-09-30 (L-0520 PR 1 merges main bd4b2f30 (T-0028 #288, crew 1.0.85, and the mailgun skill), crew 1.0.86).**  No suite was executed for this note.

**Re-anchored `14b52c91` -> `0c3508e9` on 2026-09-30 (L-0520 PR 1 merges main f7caa37d (L-0561 #289: mailgun registered as skills/mailgun 1.0.1, both install scripts, README, INSTALLATION.md), crew stays 1.0.86).**  No suite was executed for this note.

**Re-anchored `0c3508e9` -> `fe524012` on 2026-09-30 (L-0513, the shared gate runner `scripts/gate-runner.py`; repository tooling, no plugin version, crew stays 1.0.86).** `git diff --name-only 0c3508e9 fe524012` returns, outside refresh artifacts, `.crew/verify.json` (rule 22's `run`, `seconds` and `why` in place, and rule 40 appended after T-0028's Kimi rule 39 at `:426-430`), `CLAUDE.md` (a two-line gate-runner pointer in Commands, so every line from the old `:14` moved down 2), `CHANGELOG.md`, `README.md` (main's re-pin `767fa3ef`, in place), `scripts/gate-runner.py` and `scripts/_test/gate-runner.py`; no `plugin/crew` path. Every `CLAUDE.md:N` and `.crew/verify.json:N` body citation in this note was re-read with `grep -n`/`sed -n`. `767fa3ef` (on main) re-pinned `README.md:12`/`:18` to `f7caa37d`; the install-URL pin landmine was re-read and now names that pin. No suite was executed for this note.

**Re-anchored `fe524012` -> `4eacfacf` on 2026-09-30 (L-0513 step 6 fix: the inner gate runner exits 128+signum after a signal).** `git diff --name-only fe524012 4eacfacf` returns, outside refresh artifacts, `scripts/gate-runner.py`, `scripts/_test/gate-runner.py` and `.crew/verify.json` (rules 22 and 40: `why` text only, in place; line count unchanged, rule 40 still `:426-430`). No body citation in this note moved. No suite was executed for this note.

**Re-anchored `4eacfacf` -> `3437cbdd` on 2026-10-01 (L-0513 Fix phase: review round 1's 2 BLOCK and 6 FIX; repository tooling, no plugin version, crew stays 1.0.86).** `git diff --name-only 4eacfacf 3437cbdd` returns, outside refresh artifacts, `scripts/gate-runner.py`, `scripts/_test/gate-runner.py`, `CHANGELOG.md` (the L-0513 Unreleased entry, +9 lines) and `.crew/verify.json` (rules 22 and 40: `seconds` 12 -> 20 and `why` text, in place; line count unchanged, rule 40 still `:426-430`). No body citation of this map points into those files' changed lines. No suite was executed for this note.

**Re-anchored `3437cbdd` -> `e41bc6fd` on 2026-10-01 (L-0513 successor plan: review round 2's six fixes, after `git -c rerere.enabled=false merge origin/main` at `1899c370`; repository tooling, no plugin version of its own, crew is main's 1.0.89).** `git diff --name-only 3437cbdd e41bc6fd` returns, outside refresh artifacts, `scripts/gate-runner.py`, `scripts/_test/gate-runner.py`, `.crew/verify.json` (rules 22 and 40: `seconds` 20 -> 41, in place, line count unchanged), and from main's merge `.github/workflows/runner-autostart.yml`, `CHANGELOG.md` (+22 lines at `:31`, W-0116's entry), `plugin/PLUGINS.md:14`, `.claude-plugin/marketplace.json:224` and `plugin/crew/.claude-plugin/plugin.json:3` (crew 1.0.86 -> 1.0.89, in place), `plugin/crew/hooks/scripts/crew_refresh_check.py` (+43 lines, inserted after `:686`, `:694` and `:713`) and `plugin/crew/tests/test_refresh_admission.py`. No body citation of this map points into a moved line of those files. No suite was executed for this note.

**Re-anchored `e41bc6fd` -> `4a48f594` on 2026-10-01 (L-0513 Fix phase: review round 3's BLOCK, five FIX and the NIT; repository tooling, no plugin version of its own, crew is main's 1.0.89).** `git diff --name-only e41bc6fd 4a48f594` returns, outside refresh artifacts, `scripts/gate-runner.py`, `scripts/_test/gate-runner.py`, `.crew/verify.json` (rules 22 and 40: `seconds` 41 -> 55 and their `why` text, in place, line count unchanged) and `CHANGELOG.md` (+7 lines inserted after `:29`, inside L-0513's own entry). No map cites a `scripts/gate-runner.py` line. The `CHANGELOG.md:N` figures inside earlier re-anchor notes describe the file at those notes' own anchors and are left as written; none is a body citation of current content. No suite was executed for this note.

**Re-anchored `0c3508e9` -> `6e581365` on 2026-09-30 (T-0505 merges main 64b04c6b: W-0116 crew 1.0.89, runner auto-start #294; crew 1.0.91).** `git diff --name-only 0c3508e9 6e581365` outside the refresh artifacts returns W-0116's `plugin/crew/hooks/scripts/crew_refresh_check.py` and `plugin/crew/tests/test_refresh_admission.py`, `.github/workflows/runner-autostart.yml` (#294), the repo README, and T-0505's files: `promote-gate.sh`/`.ps1`, the new `_promote_tree.py`, `test_promote_gate_effective_tree.py`, `promote_tree_mutations.py`, `promote.md`, crew README, CONFIG.md (+2 lines in section 16), the crew-verification SKILL, INSTALLATION.md, `.crew/verify.json` (rule 4 path), the troubleshooting guide and its builds, the cloud handoff note and README, CHANGELOG.md and the version files (crew 1.0.91, past main's 1.0.89). A difflib re-map of every path-qualified `path:line` citation in the eight maps (history sections skipped) moved four: `crew_refresh_check.py:970` -> `:1013` (W-0116) and three `plugin/crew/CONFIG.md:2410-2417` -> `:2412-2419` (T-0505's sentence); none was unmapped. Re-applied by hand in `crew.md`: `promote-gate.sh:79` is the plain `crew_py()` call (re-read with `grep -n`), and `promote-gate.sh` is not a `crew_config.py` user (no `crew_config` import or `.crew/config.json` read in either flavour). Bare `:N` continuations and `CHANGELOG.md` citations in history sections were left as written. No suite was executed for this note.

**Re-anchored `6e581365` -> `9580571e` on 2026-10-01 (T-0505 raises promote.md's line ceiling in .budget-allowance.json, crew 1.0.91).** `git diff --name-only 6e581365 9580571e` outside the refresh artifacts returns only `plugin/crew/.budget-allowance.json`: promote.md's entry edited in place (`lines` 335 -> 380, reason `T8: to trim` -> a `raised:` reason), line count unchanged. No note cites a line of that file; a difflib re-map of every path-qualified citation moved none. No suite was executed for this note.

**Re-anchored `0c3508e9` -> `bf7ce780` on 2026-09-30 (L-0558: L-0520 round-2 fixes and the rerere rule, crew 1.0.87).**  No suite was executed for this note.

**Re-anchored `bf7ce780` -> `dbad6519` on 2026-09-30 (L-0558 self-review fixes, crew 1.0.87).** `git diff --name-only bf7ce780 dbad6519` touches only crew_train.py, its tests and CHANGELOG.md's top entry; nothing this map cites by line moved. No suite was executed for this note.

**Re-anchored `dbad6519` -> `c8118baf` on 2026-09-30 (L-0558 lint fix and version re-set).** `git diff --name-only dbad6519 c8118baf` returns, outside refresh artifacts, `plugin/crew/tests/test_crew_train.py` (one trailing blank line dropped) and the three version files (stepped back and re-set to 1.0.87 on the same lines); nothing any map cites by line moved. No suite was executed for this note.

**Re-anchored `c8118baf` -> `afd976ee` on 2026-09-30 (L-0558 review round 1 fix).** `git diff --name-only c8118baf afd976ee` returns, outside refresh artifacts: CHANGELOG.md plugin/crew/README.md plugin/crew/hooks/scripts/crew_train.py plugin/crew/tests/test_crew_train.py - see the merge-train section for crew_train.py citations, re-mapped by definition name; no other cited line moved. No suite was executed for this note.

**Re-anchored `afd976ee` -> `d21fa82d` on 2026-09-30 (L-0558 round-2 fixes and main merge, crew 1.0.95).** `git diff --name-only afd976ee d21fa82d` returns, outside refresh artifacts: .claude-plugin/marketplace.json CHANGELOG.md plugin/PLUGINS.md plugin/crew/.claude-plugin/plugin.json plugin/crew/README.md plugin/crew/hooks/scripts/crew_refresh_check.py plugin/crew/hooks/scripts/crew_train.py plugin/crew/tests/test_crew_train.py plugin/crew/tests/test_refresh_admission.py - crew_train.py citations in the merge-train section were re-mapped by definition name; W-0116's crew_refresh_check.py and test_refresh_admission.py are main's (merged with rerere disabled at 8935fc25), and no line this map cites in them is relied on here without re-reading; the version files moved value, not line. No suite was executed for this note.

**Re-anchored `9580571e` -> `b0ac0e1a` on 2026-09-30 (L-0558 merges main 6fe0e0db (T-0505), crew 1.0.95).** Both histories are kept above: main's T-0505 chain to 9580571e and L-0558's chain to d21fa82d, merged at f7118a04 with rerere disabled. `git diff --name-only 9580571e b0ac0e1a` outside refresh artifacts is L-0558's change (crew_train.py, test_crew_train.py, plugin/crew/README.md, the two guide sources and their outputs, CHANGELOG.md, .crew/verify.json rule 37, the version files) plus main's W-0116 files already in 9580571e's ancestry; the merge-train section's crew_train.py citations were re-mapped at d21fa82d and crew_train.py has not changed since; no other cited line moved. No suite was executed for this note.

**Re-anchored `b0ac0e1a` (main) and `b0ac0e1a` (L-0558) -> `89ebda03` on 2026-10-01 (L-0558 merges main 52489039: T-0110 #297, T-0040 #290; crew 1.0.102).** Both histories are kept above; the merge (c481ada4) ran with rerere disabled. `git diff --name-only b0ac0e1a 89ebda03` outside refresh artifacts is 36 paths: L-0558's change (crew_train.py, test_crew_train.py, plugin/crew/README.md, two guide sources and outputs, CHANGELOG.md, .crew/verify.json rule 37, the version files) plus main's commits since b0ac0e1a; the merge-train section's crew_train.py citations hold (crew_train.py unchanged since 7a71faff); no other line this map cites was re-checked beyond the merge. No suite was executed for this note.

**Re-anchored `0c3508e9` -> `5ab63076` on 2026-09-30 (L-0516: deadline polls replace fixed sleeps in the flaky crew tests, crew 1.0.89; verify.json gains rule 10 so later rules shift by one and six lines).**  No suite was executed for this note.

**Re-anchored `5ab63076` -> `805b0a25` on 2026-09-30 (L-0516 split per the tooling-PR rule: sabotage_qa.py back to main's copy, its four entries move to L-0563; verify.json rule 10's why and CHANGELOG reworded in place).**  No suite was executed for this note.

**Re-anchored `805b0a25` -> `7ecbdc7f` on 2026-09-30 (L-0516 re-bumps crew to 1.0.91 after the split; version files, CHANGELOG heading and the two version sentences only).**  No suite was executed for this note.

**Re-anchored `7ecbdc7f` -> `a9c0d9ab` on 2026-09-30 (L-0516: pylint R1732 fix in test_poll_fixtures.py (with-blocks, no line this map cites moves) and crew re-bumped to 1.0.92; version files, CHANGELOG heading and the two version sentences in place).**  No suite was executed for this note.

**Re-anchored `a9c0d9ab` -> `083cda66` on 2026-10-01 (L-0516 merges main `64b04c6b` (W-0116 #292: `crew_refresh_check.py` gains the Windows `_FINAL_PATH` check, `test_refresh_admission.py` two Windows premises; runner-autostart.yml) and crew re-bumped to 1.0.93; version files, CHANGELOG heading and the two version sentences in place).** `git diff --name-only a9c0d9ab 083cda66` over this map's cited paths: no cited line moved.  No suite was executed for this note.

**Re-anchored `083cda66` -> `908c03af` on 2026-10-01 (L-0516 review round 1 fixes: `poll_until` reads the clock before each probe after the first, `test_poll_fixtures.py` reaps its children with `wait(timeout=10)`, CHANGELOG corrected; crew re-bumped to 1.0.97; version files, CHANGELOG heading and the two version sentences in place).** `git diff --name-only 083cda66 908c03af` over this map's cited paths: no cited line moved.  No suite was executed for this note.

**Re-anchored `908c03af` -> `11f476a2` on 2026-10-01 (L-0516 merges main `6fe0e0db` (T-0505 #296: promote-gate judges the deploy's tree, crew 1.0.92) without rerere and re-bumps crew to 1.0.98).** Conflicts were refresh artifacts, CHANGELOG, BUDGETS.md and the version files only; each map keeps both branches' history notes (main's first). `git diff --name-only 908c03af 11f476a2` outside the refresh artifacts returns T-0505's files (`promote-gate.sh`/`.ps1`, `_promote_tree.py`, `test_promote_gate_effective_tree.py`, `promote_tree_mutations.py`, `promote.md`, crew README, CONFIG.md, `.budget-allowance.json`, the crew-verification SKILL, INSTALLATION.md, `.crew/verify.json` rule 4's path, the troubleshooting guide and its builds, the cloud handoff note and README), CHANGELOG.md, BUDGETS.md (21,621 lines, still `:11`) and the version files. Main's own re-maps of those files (`CONFIG.md:2412-2419`, `promote-gate.sh:79`) arrived with the merge; a difflib re-map of every path-qualified citation from `908c03af` to `11f476a2` moved none outside history sections, where `CHANGELOG.md` and `CONFIG.md` citations are left as written. `crew_refresh_check.py`'s `main()` `:1406` and `artifact_verdicts` `:1013` keep this branch's values (re-read with `grep -n`; main's map still read `:1363`/`:970`). No suite was executed for this note.

**Re-anchored `11f476a2` -> `1390bb23` on 2026-10-01 (L-0516 merges main `52489039` (T-0110 #297 at crew 1.0.97, T-0040 #290 at 1.0.98) without rerere and re-bumps crew to 1.0.100).** Main moved while this lane's suites ran. Conflicts were refresh artifacts, CHANGELOG and BUDGETS.md only; maps, diagram notes and INDEX keep both histories (main's first). A citation re-map that follows each line's origin (this branch's lines from `e9375690`, main's from `52489039`, each to `1390bb23`; history skipped) moved nothing: main's own lines already carry T-0040's moves (`CONFIG.md`, `crew_config.py`, crew README). Re-read by hand: `crew.md`'s W-0116 `_FINAL_PATH` sentence keeps this branch's text (`crew_refresh_check.py:716`); `verification-harness.md`'s verify.json paragraph now reads 42 rules / 443 lines (T-0040's rule 42 at `.crew/verify.json:433-439`, `default` `:441`, `unmapped` `:442`), and rule 39 `:418-431` is unchanged. No suite was executed for this note.

**Re-anchored `1390bb23` -> `0027f794` on 2026-10-01 (L-0516 merges main `05a679bf` (L-0558 #293 at crew 1.0.102) without rerere and re-bumps crew to 1.0.103).** Main moved while this lane's required checks ran. Conflicts were refresh artifacts, CHANGELOG and the version files only; maps, diagram notes and INDEX keep both histories (main's first). Main's change outside refresh artifacts is `crew_train.py`, `test_crew_train.py`, crew README, the daily-workflow and troubleshooting guides, CHANGELOG, the version files and `.crew/verify.json` rule 37's line rewritten in place (443 lines at both `1390bb23` and `0027f794`, so no `.crew/verify.json:N` citation moves). Main's own lines already carry L-0558's `crew_train.py` moves; no line this branch added cites `crew_train.py`, `test_crew_train.py`, the crew README or either guide by line. `crew.md`'s version sentence names 1.0.103 in place. No suite was executed for this note.

**Re-anchored `9580571e` (main's side of the merge) and `4a48f594` (L-0513's side) -> `de32cb87` on 2026-10-01 (L-0513 merges origin/main `44d3dbc6` at `293b78a1` with `git -c rerere.enabled=false`, bringing T-0110 #297 and crew 1.0.97, then review round 4's five fixes; repository tooling, no plugin version of its own).** The merge's conflicts in this map were the anchor header and these history notes only; both sides' notes are kept above. `git diff --name-only 9580571e de32cb87` outside refresh artifacts returns L-0513's `scripts/gate-runner.py`, `scripts/_test/gate-runner.py`, `.crew/verify.json` (rules 22 and 40: `seconds` 55 -> 57 and their `why`, in place, line count unchanged), `CLAUDE.md` (L-0513's two-line pointer in Commands) and `CHANGELOG.md`, and main's T-0110 files: `.github/workflows/pytest-crew.yml`, `AGENTS.md`, eight files under `plugin/crew/tests/` (`crew_fixtures.py`, `test_msys_tmp_pin.py` and six others) and the version files `.claude-plugin/marketplace.json`, `plugin/PLUGINS.md:14` and `plugin/crew/.claude-plugin/plugin.json:3` (crew 1.0.97, in place). A difflib re-map of every path-qualified `path:line` citation in the eight maps and two diagrams (history notes skipped), from each merge parent's anchor to `de32cb87`, found every one mapping onto itself from at least one parent, except the in-place version lines and `CHANGELOG.md:N` figures inside history notes, left as written; `crew.md`'s version sentence now reads 1.0.97. No suite was executed for this note.

**Re-anchored `de32cb87` -> `f23b01b4` on 2026-10-01 (L-0513 Fix phase: review round 5's two FIX findings; repository tooling, no plugin version of its own, crew is main's 1.0.97).** `git diff --name-only de32cb87 f23b01b4` outside refresh artifacts returns `scripts/gate-runner.py` (`_valid_result` now takes the table step, requires phase/group/argv/cwd/timeout, and refuses a FAIL whose rc `classify()` would not call FAIL), `scripts/_test/gate-runner.py` (two new cases, `part_row`), `.crew/verify.json` (rules 22 and 40: `seconds` 57 -> 58 and their `why`, in place, line count unchanged) and `CHANGELOG.md` (+3 lines inside L-0513's entry, at :30-36). A difflib re-map of every path-qualified `path:line` citation in the eight maps and two diagrams (history notes skipped) from `de32cb87` found every one mapping onto itself except nine `CHANGELOG.md:N` citations in `crew.md`, shifted +3 to the lines they cited, and the in-place `.crew/verify.json:260`/`:430` lines. No suite was executed for this note.

**Re-anchored `f23b01b4` (L-0513's side) and main's side -> `71038cb9` on 2026-10-01 (L-0513 owner amendment for review round 6's BLOCK at `fbd48532`, then `git -c rerere.enabled=false merge origin/main` `52489039` (T-0040 #290, crew 1.0.98) at `74130bbd`, then rules 22 and 40 repriced at `71038cb9`; repository tooling, no plugin version of its own).** `git diff --name-only f23b01b4 71038cb9` outside refresh artifacts returns L-0513's `scripts/gate-runner.py` and `scripts/_test/gate-runner.py` (the BLOCK fix: no process-group signal once the leader is reaped, and its two cases), `CHANGELOG.md` (L-0513's entry +3 lines; T-0040's 1.0.98 entry now sits below it) and `.crew/verify.json` (rules 22 and 40 `seconds` 58 -> 60 and `why`, in place; T-0040's shell-route rule appended as rule 41 at `:432-437`), and T-0040's own paths, which main's side of this map already describes. Where the merge conflicted here it was the anchor header and these provenance notes: both sides kept, main's first. The `CHANGELOG.md:N` citations in older provenance notes name lines at the commits those notes name and were not shifted. Refresh artifacts per owner rule 2026-09-28; no test suite was executed for this note.

**Re-anchored `71038cb9` (L-0513's side) and `89ebda03` (main's side) -> `0d159692` on 2026-10-01 (L-0513 merges origin/main `05a679bf` - L-0558 #293, crew 1.0.102 - at `0d159692` with `git -c rerere.enabled=false`; repository tooling, no plugin version of its own).** The merge's conflicts in this map were the anchor header and these history notes only; both sides' notes are kept, main's first. `git diff --name-only 71038cb9 0d159692` outside refresh artifacts is main's L-0558 change only: `plugin/crew/hooks/scripts/crew_train.py`, `plugin/crew/tests/test_crew_train.py`, `plugin/crew/README.md`, the daily-workflow and troubleshooting guide sources and their six builds, `.crew/verify.json`, `CHANGELOG.md` and the three version files (crew 1.0.102). A difflib re-map of every path-qualified `path:line` citation in the eight maps and two diagrams (history notes skipped), from each merge parent's anchor to `0d159692`, found every one mapping onto itself from at least one parent except three `CHANGELOG.md:N` citations in `crew.md` from L-0513's side, moved to the lines they cited (`:485-486` -> `:519-520`, `:645-646` -> `:679-680`, `:274` -> `:308`); `crew.md`'s version sentence now reads 1.0.102. No suite was executed for this note.

**Re-anchored `0027f794` (L-0516's side) and `0d159692` (main's side) -> `ec95c8aa` on 2026-10-01 (L-0516 merges origin/main `cacf7ff0` - L-0513 #301, the gate runner; crew stays 1.0.102 on main - with `git -c rerere.enabled=false`; crew 1.0.104, re-bumped at `1f2114bc` past 1.0.103, which L-0510's worktree claimed first).** Conflicts were refresh artifacts and CHANGELOG only; each map keeps both re-anchor histories. `git diff --name-only 0027f794 ec95c8aa` outside refresh artifacts returns main's L-0513 paths (`.crew/verify.json` rule 22 rewritten in place at `:262-266` and its gate-runner rule appended at `:432-436`, `CLAUDE.md`, `scripts/gate-runner.py`, `scripts/_test/gate-runner.py`) and the three version files plus CHANGELOG; `git diff --name-only 0d159692 ec95c8aa` returns L-0516's own paths. A difflib re-map of every path-qualified `path:line` citation in the eight maps and two diagrams (history notes skipped), from each merge parent's anchor, found every one mapping onto itself from at least one parent except the version lines (changed in place) and nine `CHANGELOG.md:N` citations in `crew.md` from main's side, which L-0516's CHANGELOG entry above them moved by 35 (`:519-520` -> `:554-555`, `:679-680` -> `:714-715`, `:308` -> `:343`, `:676-677` -> `:711-712`, `:887-888` -> `:922-923`, `:898-899` -> `:933-934`, `:1114-1115` -> `:1149-1150`, `:1238` -> `:1273`, `:1134` -> `:1169`). `verification-harness.md`'s verify.json section now reads the merged tree (448 lines, 43 rules). No suite was executed for this note.

**Re-anchored `ec95c8aa` -> `5ffffbe3` on 2026-10-01 (L-0516 merges origin/main `ddcbf90d` - W-0115 #299, T-0040's shell-route sabotage mutations, crew 1.0.106 - with `git -c rerere.enabled=false` and re-bumps crew to 1.0.110, skipping 1.0.105 (L-0557), 1.0.107 (T-0504), 1.0.108 (L-0510) and 1.0.109 (T-0501)).** Conflicts were the three version files and CHANGELOG only. `git diff --name-only ec95c8aa 5ffffbe3` outside refresh artifacts returns W-0115's paths (`plugin/crew/tests/sabotage.py`, `plugin/crew/tests/sabotage_shell.py`, `.crew/verify.json`'s last rule gaining one path line) plus the version files and CHANGELOG. A difflib re-map of every path-qualified citation (history notes skipped) moved two `plugin/crew/tests/sabotage.py` citations in `crew.md` by +2 (`:3055` -> `:3057`, `:3056` -> `:3058`; W-0115 adds an import at `:86` and a comment line at `:3055`), the nine main-side `CHANGELOG.md` citations in `crew.md` by +15 for W-0115's entry, and `verification-harness.md`'s verify.json header to 449 lines; every other citation maps onto itself. No suite was executed for this note.

**Re-anchored `0c3508e9` -> `b1d8a4e8` on 2026-09-30 (L-0557: per-test XDG_CACHE_HOME for every pwsh the suites spawn, crew 1.0.89, obsidian-vault 0.4.16).** `git diff --name-only 0c3508e9 b1d8a4e8` returns, outside refresh artifacts, L-0557's test-only files (`plugin/crew/tests/conftest.py`, `plugin/crew/tests/crew_fixtures.py`, new `plugin/crew/tests/test_pwsh_cache_isolation.py`, both `test_flavour_guard.py` copies, the obsidian-vault `_test` suites, six `scripts/_test/*.sh`), `.crew/verify.json` (one new rule, appended after the Kimi rule), `plugin/crew/README.md` (one paragraph after the test-layer table), the harness reference's H4 table (one row), `CHANGELOG.md`, `plugin/crew/BUDGETS.md` and the version files. Body `path:line` citations into those files were moved by difflib from `0c3508e9` (`/root/crew-tmp/l-0557/tools/remap.py`, machine-local): 25 moved, in crew.md (CHANGELOG), obsidian-vault.md (its `_test` suites) and verification-harness.md (verify.json range unchanged). No hook or production script changed. No suite was executed for this note.

**Re-anchored `b1d8a4e8` -> `d9ccfd5a` on 2026-10-01 (L-0557 merges main 0c0275e8 (W-0116 #292, crew 1.0.89) and re-sets crew 1.0.95).** `git diff --name-only b1d8a4e8 d9ccfd5a` returns, outside refresh artifacts, W-0116's `plugin/crew/hooks/scripts/crew_refresh_check.py` (a final-path check in `_read_regular`'s no-dir_fd branch, hunks from :684) and `plugin/crew/tests/test_refresh_admission.py`, `CHANGELOG.md` (both sides' Unreleased entries kept) and the version files (crew 1.0.95). Body `path:line` citations into those files were moved by difflib from `b1d8a4e8` (`/root/crew-tmp/l-0557/tools/remap.py`, machine-local), each onto the same line text. No suite was executed for this note.

**Re-anchored `d9ccfd5a` -> `97ace923` on 2026-10-01 (L-0557 review round 1 fixes, crew 1.0.96).** `git diff --name-only d9ccfd5a 97ace923` returns, outside refresh artifacts, L-0557's test-only `plugin/crew/tests/conftest.py` (the per-test cache dir is now `tmp_path_factory.mktemp("xdg-cache")`), `plugin/crew/tests/crew_fixtures.py` (one comment), `plugin/crew/tests/test_pwsh_cache_isolation.py` (the static guard judges values and returned environments, reports unreadable suites), `CHANGELOG.md` (L-0557's entry, five lines longer) and the version files (crew 1.0.96: 1.0.95 is also claimed by L-0558, #293). Body `path:line` citations into those files were moved by difflib from `d9ccfd5a` (`/root/crew-tmp/l-0557/tools/remap.py`, machine-local): none in this map (all 10 are `CHANGELOG.md` in crew.md). No hook or production script changed. No suite was executed for this note.

**Re-anchored `97ace923` / `9580571e` -> `550c39cd` on 2026-10-01 (L-0557 merges main 6fe0e0db: T-0505 #296 crew 1.0.92, runner auto-start #294; crew stays 1.0.96).** `550c39cd` is a two-parent merge made with `git -c rerere.enabled=false merge origin/main`; its conflicts were refresh artifacts, version files and CHANGELOG only. This side's notes were anchored `97ace923` and main's `9580571e`; `git diff --name-only 9580571e 6fe0e0db` outside the refresh artifacts returns only the 1.0.92 version files and CHANGELOG, so main's notes already describe every non-artifact change it brings, and this side's notes describe L-0557's. Body `path:line` citations were moved by difflib, each from the anchor of the side whose copy of this map carries the line (`/root/crew-tmp/l-0557/tools/remap2.py`, machine-local): 17 moved - 10 `CHANGELOG.md` in crew.md (T-0505's 1.0.92 entry now sits below L-0557's) and 7 `plugin/crew/CONFIG.md` in verification-harness.md (T-0505's CONFIG.md edit), every one an exact-text match. No suite was executed for this note.

**Re-anchored `550c39cd` -> `038d5d10` on 2026-10-01 (L-0557 merges main 44d3dbc6: T-0110 #297, crew 1.0.97; L-0557 re-sets crew 1.0.99 at `4fc11923`).** `038d5d10` is a two-parent merge made with `git -c rerere.enabled=false merge origin/main`; its conflicts were version files, CHANGELOG and one generated rules file. `git diff --name-only 6fe0e0db 44d3dbc6` outside the refresh artifacts returns T-0110's `.github/workflows/pytest-crew.yml`, `AGENTS.md`, `plugin/crew/tests/crew_fixtures.py` (new helpers below L-0557's, auto-merged), seven crew test files, CHANGELOG and the 1.0.97 version files. T-0110 updated verification-harness.md's `pytest-crew.yml` sentence itself; the other files are cited by name only. Body `path:line` citations were moved by difflib (`/root/crew-tmp/l-0557/tools/remap2.py`, machine-local): 10 moved, all `CHANGELOG.md` in crew.md (T-0110's 1.0.97 entry now sits below L-0557's), every one an exact-text match. No suite was executed for this note.

**Re-anchored `038d5d10` / `44d3dbc6` -> `90186613` on 2026-10-01 (L-0557 merges main 52489039 at `327e6ec1`: T-0040 #290, crew 1.0.98; L-0557 re-sets crew 1.0.101 at `90186613`).** `327e6ec1` is a two-parent merge made with `git -c rerere.enabled=false merge origin/main`; its conflicts were refresh artifacts, version files, CHANGELOG, BUDGETS.md's count and `.crew/verify.json` (both sides appended one rule; both kept). Main's notes (anchor line `44d3dbc6`) were re-taken by T-0040 on its own merged tree `52489039`, so a line only in main's copy of a map is measured from `52489039`; a line in this side's copy is measured from `038d5d10`. Body `path:line` citations were moved by difflib (`/root/crew-tmp/l-0557/tools/remap2.py`, machine-local): 73 moved, all from this side's lines - `plugin/crew/README.md` (+11 lines from T-0040 above :743), `plugin/crew/CONFIG.md` (+11 from T-0040), `CHANGELOG.md` (T-0040's 1.0.98 entry, then this side's below it), `plugin/crew/tests/test_crew_config.py` and `plugin/crew/hooks/scripts/crew_config.py` (T-0040); every one an exact-text match, none on a changed line. T-0040's own claims about crew_shell.py, crew_status.py and the shell-route config are main's notes above and were not re-derived here. No suite was executed for this note.

**Re-anchored `89ebda03` (main) and `90186613` (L-0557) -> `773ce841` on 2026-10-01 (L-0557 merges main `05a679bf`, L-0558 #293, crew 1.0.102, at `2169bd11` with rerere disabled; L-0557 re-sets crew 1.0.105 at `773ce841`).** Both provenance histories are kept above, main's first. Body citations were re-checked by mapping each one from the tree its line came from (`89ebda03` for main's lines, `74dd1aa5` for L-0557's) to this tree with difflib: no citation moved. Citations into the version lines of `plugin/crew/.claude-plugin/plugin.json`, `plugin/PLUGINS.md` and `.claude-plugin/marketplace.json` keep their line numbers (the value changed in place). No suite was executed for this note.

**Re-anchored `0d159692` (main, L-0513 #301) and `773ce841` (L-0557) -> `a9608aa5` on 2026-10-01 (L-0557 merges main `cacf7ff0`, L-0513 #301: `scripts/gate-runner.py`, no plugin version; rerere disabled; crew stays 1.0.105).** Both provenance histories are kept, main's first. Where both sides had re-mapped the same citation, main's line was taken, and each citation was then mapped with difflib from the tree its line came from (`cacf7ff0` for main's lines, `95036b4c` for L-0557's) to this tree: no citation moved. No suite was executed for this note.

**Re-anchored `a9608aa5` -> `c43a9ce3` on 2026-10-01 (L-0557 merges main `ddcbf90d`, W-0115 #299, crew 1.0.106, at `0597e5c6` with rerere disabled, and re-sets crew 1.0.111 at `c43a9ce3`).** The merge touched no code map. `git diff --name-only a9608aa5 c43a9ce3` outside refresh artifacts is W-0115's `plugin/crew/tests/sabotage.py`, `sabotage_shell.py` and `.crew/verify.json` plus the version files and CHANGELOG; each citation into a changed file was mapped with difflib from `92448f1a` to this tree: no citation moved. No suite was executed for this note.

**Re-anchored `5ffffbe3` (main, L-0516 #298) and `c43a9ce3` (L-0557) -> `6053b65d` on 2026-10-01 (L-0557 merges main `2906dcbd`, L-0516 #298, crew 1.0.110, at `2f3fb34c` with rerere disabled, and re-sets crew 1.0.114 at `6053b65d`).** Both provenance histories are kept, main's first, and main's body citations were taken where both sides had re-mapped the same one. Each citation into a changed file was then mapped with difflib from the tree its line came from (`2906dcbd` for main's lines, `a54ff87b` for L-0557's) to this tree: no body citation moved; the `.crew/verify.json:433-439` range in L-0516's provenance note was kept, because it describes that tree. No suite was executed for this note.

**Re-anchored `6053b65d` -> `f5cab1f9` on 2026-10-01 (T-0503 merges origin/main `ffd11270`, L-0557 #300, crew 1.0.114, at `f5cab1f9` with rerere disabled; bitbucket 1.2.3).** The merge took main's side of every code map. `git diff --name-only ffd11270 f5cab1f9` is T-0503's own change only: `.claude-plugin/marketplace.json` (bitbucket version), `CHANGELOG.md` (its entry, 33 lines at the top), the `bitbucket` catalog row in `README.md` and `skills/README.md` (edited in place, no line count changed), `docs/handoff/cloud/T-0503.md`, and `skills/bitbucket/` (`SKILL.md`, `references/api.md`, `scripts/_test/merge_gate.sh`). Every citation into those files was compared by script against `ffd11270` (158 checked across the eight maps); no other cited line moved. Re-anchor only, under the refresh-artifact standing rule (owner 2026-09-28); no suite was executed for this note.

**Re-anchored `f5cab1f9` -> `b4f04e23` on 2026-10-02 (L-0578 merges origin/main `8d84786d`, W-0117 #302, crew 1.0.115, at `b4f04e23` with rerere disabled; crew 1.0.119).** L-0578's own change is `review_metrics.py` (new), `review_run.py`, `review_patch.py`, `commands/review.md`, the README, BUDGETS.md, external-tool-formats.md, `.crew/verify.json` rule 38, its tests and sabotage entries, and the version files and CHANGELOG. Every full `path:line` citation into a changed file was compared by script (difflib) against the old anchor: none moved; the only citations whose line text changed are the version and count lines (`plugin/crew/.claude-plugin/plugin.json:3`, `.claude-plugin/marketplace.json:224`, `plugin/PLUGINS.md:14`, `plugin/crew/BUDGETS.md:10-11`), which still sit on the lines they cite. No suite was executed for this note.

**Re-anchored `3648f59a` -> `0da787d3` on 2026-09-29 (T-0107, gizmoduck 0.5.4). Current despite the lag.** `crew_refresh_check.py` named README.md, plugin/README.md as changed since the anchor. T-0107 edits exactly one line of each, in place (`git diff --numstat 2693d0fa 0da787d3 -- README.md plugin/README.md` is `1 1` for both): the gizmoduck catalog row, `README.md:875` and `plugin/README.md:415`, gains one clause naming the routine. No line shifted, and a script over every `README.md:N[-M]` citation in `.crew/codemap/` found none covering either line. `plugin/PLUGINS.md` changes only at `:441`, `:446`, `:451` and `:470` (+2 lines after it), and no note cites a `PLUGINS.md` line at or after `:441`. No claim re-read; nothing was executed for this note.

**Re-anchored `bbd9a66d` -> `8730119f` on 2026-09-29 (T-0107 merges origin/main `8ab733d7`). Current despite the lag.** `8730119f` merges origin/main (T-0010 landed, crew 1.0.61, main's anchor `bbd9a66d`) into `T-0107-build`; the conflicts were this header and the provenance tail, resolved mechanically - main's anchor taken, both sides' provenance kept, main's first. `git diff --numstat bbd9a66d 8730119f -- README.md plugin/README.md` is `1 1` for each: T-0107's gizmoduck catalog row, still `README.md:875` and `plugin/README.md:415`, edited in place. No citation outside provenance covers either line, and `plugin/PLUGINS.md` changes only at `:441`, `:446`, `:451` and `:470` (+2 after it), where no note cites a line. Nothing was executed for this note.

**Re-anchored `6053b65d` -> `40292eca` on 2026-10-02 (T-0107 merges origin/main `ffd11270`, without rerere). Current despite the lag.** `40292eca` merges origin/main into `T-0107-build`; the header conflict took main's anchor and both sides' provenance notes were kept, main's first. `crew_refresh_check.py` named README.md and plugin/README.md: `git diff --numstat 6053b65d 40292eca -- README.md plugin/README.md` is `1 1` for each, T-0107's gizmoduck catalog row edited in place, now `README.md:876` (main's side added a line above it) and `plugin/README.md:415`. The only citations covering those lines sit in dated notes that state their own commit's coordinates. gizmoduck is re-set to 0.5.4, one patch above main's 0.5.3, after the last content change. Nothing was executed for this note.

**Re-anchored `f5cab1f9` -> `e60394fd` on 2026-10-02 (T-0107 merges origin/main `8d84786d`, without rerere). Current despite the lag.** `e60394fd` merges origin/main (W-0117, crew 1.0.115) into `T-0107-build`; the header conflict took main's anchor and both sides' provenance notes were kept, main's first. Against the scope base `8d84786d`, `crew_refresh_check.py` named README.md and plugin/README.md: `git diff --numstat 8d84786d e60394fd -- README.md plugin/README.md` is `1 1` for each, T-0107's gizmoduck catalog row edited in place, still `README.md:876` and `plugin/README.md:415`. The only citations covering those lines sit in dated notes that state their own commit's coordinates. gizmoduck stays 0.5.5 (main is 0.5.3). Nothing was executed for this note.

**Re-anchored `b4f04e23` -> `56f28a16` on 2026-10-02 (T-0107 merges origin/main `04dde5a2`, without rerere). Current despite the lag.** The header conflict took main's anchor and both sides' provenance notes were kept, main's first. Against the scope base `04dde5a2`, `git diff --numstat 04dde5a2 56f28a16 -- README.md plugin/README.md` is `1 1` for each: T-0107's gizmoduck catalog row, edited in place (`README.md:889`, `plugin/README.md:415`). The only citations covering those lines sit in dated notes that state their own commit's coordinates. gizmoduck stays 0.5.5 (main is 0.5.3). Nothing was executed for this note.

**Re-anchored `56f28a16` -> `d6e51bb8` on 2026-10-02 (T-0107 merges origin/main `d2ec37d3`, W-0120's re-pin, without rerere; no conflict).** `git diff -U0 56f28a16 d6e51bb8 -- README.md` is main's two install-URL lines, `:12` and `:18`, re-pinned in place to `04dde5a2` (no line shifts); T-0107's gizmoduck catalog row is still `README.md:889` and `plugin/README.md:415`, unchanged. The landmine bullet's pin claim was updated in place to `04dde5a2` and re-read; the older pins stay as history. gizmoduck stays 0.5.5 (main is 0.5.3). Nothing was executed for this note.
