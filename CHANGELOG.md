# Changelog

All notable changes to this repository are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows the `version` field on each plugin entry in [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json) rather than a single repo-wide version, since skills ship independently.

## [Unreleased]

### Added

- **`crew` 0.12.4: an SOP and a SOC 2 policy for pre-deployment security
  review.** Two cross-linked documents under `plugin/crew/docs/`. The rule they
  state is that no website reaches production without both a peer security
  review and an external vulnerability scan of the deployed hostname - the two
  are not interchangeable, because the review reads the change while the scan
  tests what is actually serving, and a reviewed change can still deploy onto a
  host running an end-of-life web server.

  Both are marked DRAFT with no owner, approver or effective date, and the
  policy says outright that it is a template until those exist. The Trust
  Services Criteria mapping is labelled provisional and says to confirm it with
  the auditor. A policy is evidence because a named person approved it on a
  date; shipping one that implies otherwise is the first thing an auditor pulls
  on.

  Three constraints are written in because they were learned rather than
  reasoned about: scan the public hostname from outside rather than the origin,
  since an edge that terminates TLS makes the origin's configuration invisible
  to the internet; never commit raw scanner JSONL, which embeds full HTTP
  responses and has twice captured live session tokens that keyword secret
  scanning failed to detect; and state the limits alongside the result, because
  a clean signature-based scan oversold is worse than no scan.

  Reports are published to `<project>/docs/security/` in a monolith or
  `docs/security/` at the root of a single-project repository, date-stamped so a
  later run cannot overwrite the comparison point.

- **`gizmoduck` 0.2.1: reports itemise Critical/High/Medium and count the rest,
  and rendering moves into its own module.** A scan of a healthy site returned 1
  Medium and 42 Info, and the report listed all 43 — so the one finding somebody
  was expected to fix sat underneath forty-two version banners, DNS records and
  "a form exists". Low and Info are now counted in the severity table and
  dropped. The table labels each row `itemised` or `count only` and a line
  states how many were suppressed, so the omission is visible rather than
  looking like truncation.

  `--min-severity` now raises that floor and never lowers it: `high` reports
  High and Critical, while `info` gets the counts it implies rather than pages
  of noise. `report`'s per-command default moved High -> Medium to match, which
  is the bug the first cut shipped with — every test passed `--min-severity
  info` explicitly, so the default path was never exercised and the Medium was
  silently suppressed. Running it with no flags is what caught it. `tickets`
  deliberately stays at High: a Medium is worth reading without being worth
  auto-opening a ticket for.

  New `scripts/report_template.py` owns HTML/PDF rendering; `gizmoduck.py` keeps
  the data prep and delegates. Its module docstring carries the constraint that
  matters: **wkhtmltopdf renders through Qt WebKit 4.8**, which predates
  flexbox, grid and custom properties and silently produces an unstyled column
  instead of an error, so every layout is built from tables and verified in the
  PDF rather than a browser. Findings are numbered in severity order, since that
  number is the remediation order.

  `dedupe()` also gained `raw_count` alongside `instances`. `instances` counts
  distinct locations, not detections — `http-missing-security-headers` fires
  once per absent header — so a summary reading 42 Info beside rows summing to
  20 looked like a rendering fault. Both numbers are now reported and labelled.
  Additive: `tickets` and `diff` read `instances` and are unchanged.

### Fixed

- **`crew` 0.13.0: the command guard's git rules were bypassed by every option
  form.** `guard.sh` and `guard.ps1` both required the subcommand to sit
  immediately after `git`, so `git -C <path> push --force`, `git -c a=b push
  -f` and `git --git-dir=... reset --hard` walked past the force-push,
  `reset --hard` and `clean -f` rules alike — which is exactly the spelling a
  worktree-per-agent setup types. Both flavours now swallow any run of leading
  git options between `git` and the subcommand, and `git push origin +main`
  (a force push carrying no `--force` token) blocks too. `--follow-tags`,
  `git -C <path> status`, `git clean -n` and `git stash push` stay allowed.

  `guard.ps1` had no test coverage at all — the same asymmetry
  `test_gates_powershell.py` exists for. `plugin/crew/tests/test_guard_powershell.py`
  now runs the same must-block/must-allow matrix against it. Both suites were
  sabotage-tested: restoring the old adjacent-only patterns turns
  `run-tests.sh` red on 15 cases and the new file red on 8, each naming the
  command that got through.

- **`crew` 0.12.3: the Stop hook's verify gate ran twice on any machine with
  both shells installed.** `hooks.json` registers `verify-gate.sh` AND
  `verify-gate.ps1` for every Stop, so a single-shell machine always gets
  exactly one gate run - that is the whole reason both are registered. Most
  Windows dev boxes have both, since Git for Windows ships `bash.exe`
  alongside native PowerShell, so both ran the full smoke/verify gate on every
  turn: duplicate work up to the 600s hook timeout, and two processes racing
  on the same scratch files.

  Statically deferring to one flavour was rejected. `Resolve-CrewBash` finds a
  real `bash.exe` on nearly every Windows box, so "defer when bash exists"
  would leave `verify-gate.ps1` permanently unreachable and its incident and
  config lanes untestable. Each script now takes a short-lived per-turn lock
  at `.crew/.verify-gate.lock` immediately before the expensive part;
  whichever process gets there first does the real work and the other backs
  off, and the winner's exit code still governs the turn.

  **The lock records a timestamp, never a PID.** A PID-based first draft of
  this fix was a no-op in the one situation the lock exists for. The two
  flavours do not share a PID namespace on Windows - `$PID` in PowerShell is a
  Windows pid, `$$` in Git Bash is an MSYS pid - and neither can test the
  other's for liveness: `kill -0` on a live Windows pid reports dead, and
  `Get-Process -Id` on a live MSYS pid reports dead. Each side therefore
  called the other's held lock stale, reclaimed it, and ran the gate anyway.
  It failed the other way too, since the two id spaces overlap numerically: a
  coincidental match reads as a live holder and the gate is silently skipped,
  which this script's own header calls worse than the double-run. Age now
  comes from the lock directory's own mtime, which `mkdir` stamps as it
  creates the directory, so there is no half-written state to misread and no
  window in which a lock exists with no age.

  The holder removes its own lock as it exits (a bash `trap` on EXIT INT TERM,
  `Register-EngineEvent PowerShell.Exiting` on the other side), so the 700s age
  window - comfortably above the hook's own 600s timeout - is the backstop for
  a hard-killed holder rather than the primary path. Two simultaneous
  reclaimers of the same abandoned lock settle it with a token write and a
  one-second re-read, on the reclaim path only, so the common path pays
  nothing.

  The lock sits deliberately AFTER the emergency lane and the empty-changed-set
  exit: the holder is what removes the lock, so a turn that does no work must
  not claim one.

  Covered by `tests/test_verify_gate_lock.py` and `tests/test_verify_gate_lock_sh.py`
  (seeded-lock cases per flavour, plus a direct assertion that the lock records
  no PID) and by `tests/test_verify_gate_lock_concurrent.py`, which runs the
  real bash/PowerShell pair against a smoke script that appends one line per
  execution and counts the lines. That last one is the test the first draft
  needed: both flavours passed their own seeded-lock suites while the lock did
  nothing, because each seeded a lock in the shape its own shell writes.
  Sabotage-tested - restoring the PID-based lock makes the concurrent case
  report two smoke runs.

- **`crew` 0.12.2: the `pm_pulse` stand-down now has the regression test it
  always owed.** The repo's own rule is that a hook which can block ships with
  must-block and must-allow cases, sabotage-tested — and 0.12.1 changed
  `pm_pulse`'s blocking behaviour past the per-session cap while the suite
  stayed at 101 passed, which said the suite did not cover the path, not that
  the change was safe. Two cases added: the pulse that trips the cap blocks
  once, and a genuinely new state afterwards does not block again.

  The first draft of the second case passed under sabotage, for the wrong
  reason — it changed `tier` and `roles`, which the fingerprint does not cover,
  so the digest never moved and the case would have gone green against a broken
  hook. It moves `handoffPending` now, which is one of the five fields the
  fingerprint is actually built from. Sabotage-tested properly after that:
  keying the over-cap claim back on `digest` turns it red, restoring the fixed
  marker turns it green.

- **`gizmoduck` 0.1.3: `diff` keeps its Low severity floor.** 0.1.2 moved
  `--min-severity` from one global default to per-command resolution and swept
  `diff` in with `report` and `tickets` at High. `commands/diff.md` passes
  `${3:-low}`, so the command path never changed — but a hand-run
  `gizmoduck.py diff old.jsonl new.jsonl` had its floor silently raised, on the
  one question where a Medium appearing for the first time is the answer. The
  floors are now explicit per command and match what each command file passes.

- `plugin/PLUGINS.md`'s `obsidian-vault` version row read 0.1.0 against a
  registered 0.1.2. `check-marketplace.py` compares `marketplace.json` history
  to file changes and cannot see a stale version string in prose, so this kind
  of drift passes CI silently.

### Changed

- **`crew` 0.13.0: six recurring failure shapes moved from "a lesson someone
  remembers" into the role and command instructions.**
  - `qa-reviewer` and `/crew:review` now treat any test, guard or assertion a
    diff adds as the primary subject of the review, with the shapes that stay
    green forever named (a floor far below the real count, stale expected
    data, a parse check reported as an execution, a sample that cannot
    discriminate, an assertion on the run rather than the job). `/crew:review`
    re-runs the author's mutation instead of reading a transcript of it, and
    treats an unverified control as a BLOCK.
  - `/crew:review` lands its verdict with `gh pr review`, not `gh pr comment`.
    A verdict that exists only as a comment cannot be acted on by anything.
  - `dba` and `crew-verification`: a migration is BLOCKING until it has been
    applied to a real or ephemeral database inside the change, with the
    changelog row selected back and a width assertion on every string literal.
    Parse-check plus review is a different claim from "it runs".
  - `/crew:promote` gains a pre-deploy reconcile gate (hash the live artifact
    against the source tree and classify every difference, so a branch that
    was never reconciled cannot roll production backwards), and now asserts on
    the deploy *job* and the artifact on the box rather than on the workflow's
    green tick.
  - `pm`: the line between coordinating and operating, drawn as a table —
    applying migrations, triggering deploys and infra recon are dispatched,
    not done. The PM never holds a merge decision, and re-engages live roles
    rather than accumulating idle ones.
  - `security`: a literal infrastructure endpoint in committed config is a
    finding on its own, because the fact acquires copies and infra work
    updates one of them. A credential already suppressed in a scanner baseline
    is still BLOCKING and still needs rotating.
  - `/crew:ticket`: the ticket key exists before the branch does, one owner per
    branch is recorded in the ticket rather than in chat, and decisions land in
    the ticket before anyone acts on a relayed version of them.

### Added

- **`gizmoduck` 0.1.0 — a third plugin under `plugin/`.** Runs
  [Nuclei](https://github.com/projectdiscovery/nuclei) against hosts and
  websites, diffs the run against a baseline so what is *new* is visible,
  renders a triaged report as Markdown/HTML/PDF, and turns Critical and High
  findings into ServiceDesk Plus tickets keyed on `[Nuclei <template-id>]` so a
  second run adds a note instead of a duplicate. Six commands over one Python
  CLI; **no hooks and no agents**, so nothing runs unless you type a command.
  Registered in `marketplace.json`, `plugin/README.md`, `plugin/PLUGINS.md`,
  the root `README.md`, and both install scripts — the repo-plugins picker now
  offers three entries, and `menu-groups.sh` asserts against 3 rather than 2.
  Nuclei is MIT-licensed and self-hosted, so no findings leave the machine;
  only scan assets you own or have written permission to test.

  Hardened before registering it, off the back of two Codex review passes. A
  `nuclei` that fails — bad target, missing templates, no network — used to
  write an empty findings file and exit 0, which is indistinguishable from a
  clean scan and poisons the next run's baseline; it now fails loudly and
  writes nothing. Exit 1 is the ambiguous case, since `-ec` uses it to mean
  "findings exist" and it is also a plain failure code: findings on stdout
  settle it, and exit 1 with an empty stdout is treated as the failure it is. Both bootstrap scripts fail when the template download fails,
  for the same reason: an engine with no templates reports every target as
  healthy. `update` checks its return codes instead of printing `done`. A
  `wkhtmltopdf` that is installed but broken falls through to WeasyPrint
  instead of taking the report command down with it. `--min-severity` now
  resolves per command — High for `report`, `tickets`, and `diff`, everything
  for `summary` and `parse` — so a hand-run `tickets` cannot quietly open a
  ticket per Info finding. Missing positional arguments produce an argparse
  error naming what is missing rather than a `TypeError`. The report's
  "Hosts scanned" line said no such thing — it counts hosts *with findings* —
  and now says so. Both bootstrap scripts pointed at a `/scan-site` command
  that does not exist; it is `/gizmoduck:scan`.

- **`crew` 0.12.0: `developer`, the eleventh agent.** Implements one scoped
  change in its own context and returns a summary — never reviews its own diff,
  never merges, pushes, or rewrites history. Tier 1 in `crew-scaling`'s ladder,
  and the one role in `crew-pm/onboarding.md` justified by a delegation
  decision rather than by a defect class in `.crew/metrics.md`: the question is
  whether the PM is expected to take work from assigned to done on its own. A
  PM with no developer either narrates or does the work itself. `onboarding.md`
  also gained the full role roster, since a name in `config.json.roles` with no
  `agents/<role>.md` behind it dispatches nothing and fails silently.

### Changed

- **`crew` 0.12.0: the PM is standing, and it wears one hat.** Three defects
  fixed together, because they were the same defect seen from three angles.

  *It kept disappearing.* The PM was spawned fresh per invocation, so it knew
  the state JSON and nothing else — not what it dispatched an hour ago, not
  what the user vetoed, not why a trigger was judged not worth acting on. It is
  now spawned once per session under the name `crew-pm` and stays addressable;
  `/crew:pm` calls `ListAgents` and messages the existing one rather than
  spawning a second. It also no longer ends when the queue empties: it reports
  what is outstanding and waits. The flat-roster limit still applies — a
  session that is itself a teammate cannot spawn a named one, so that path
  dispatches unnamed and says out loud that the PM will not persist.

  *It did other people's jobs.* `agents/pm.md` now states the PM's own hat —
  assess scope, onboard and offboard, communicate, keep tickets current — and
  carries a routing table from kind-of-work to role: implementation to
  `developer`, review through `/crew:review`, security/dba/docs/explorer/
  planner/analyst/smoke-author/browser-tester to the role that owns each. Its
  own writes stay scoped to `.crew/`, ticket text, `TODO.md`, and generated
  diagrams.

  *It narrated instead of dispatching.* Its characteristic failure was
  producing a convincing plan — lanes, roles, an order — and ending the turn
  without a single Agent call, which the relaying session then passed upward as
  progress. `pm.md` now requires a real Agent call with a read result behind
  every role named as dispatched, calls out future tense as the tell, and asks
  for independent roles in one message so they actually run concurrently.
  `/crew:pm` refuses to relay a report written in the future tense and sends it
  back once instead.

  Two more from the same Codex review. `/crew:pm`'s `allowed-tools` did not
  grant `ListAgents` or `SendMessage`, so the command that is supposed to find
  and continue the standing PM could do neither — both are now granted, and
  `validate-prompts.py` knows the names. Separately, `pm_pulse`'s per-session
  cap did not actually stand the hook down: past the cap, every *new*
  fingerprint still claimed cleanly and blocked the turn to repeat the same
  "standing down" line. The stand-down claim is now keyed on a fixed marker
  rather than on the state, so it is said once and then the hook is genuinely
  quiet.

- **`crew` 0.12.0: model tiers are declared, not inherited.** Every agent used
  to sit on `inherit` or an ad-hoc `opus`, which made the tier depend on
  whoever spawned it. Now: `pm` on `opus`, because every dispatch decision
  derives from the picture it holds and a bad assignment is inherited by every
  role below; `qa-reviewer` on `opus`, because it shares a model family with
  the author and the tier is the only compensation left when Codex is absent;
  every working role on `sonnet` — narrow brief, clean context, one
  deliverable. `validate-prompts.py` enforces the map and rejects `inherit`
  outright; sabotage-tested by flipping `explorer` back to `inherit` and
  confirming the suite goes red.

  QA itself still defaults to **Codex** — `qa.provider` ships as `auto`, so a
  machine with `codex` on `PATH` gets a different model family reviewing, and
  `/crew:review` says which reviewer ran. `qa-reviewer` now says so too if
  something dispatches it directly and skips that check, because skipping it
  does not merely swap reviewers, it swaps a different family for the same one
  that wrote the code and reports the result as though nothing changed.

  These are model *tiers*, not pinned versions: an agent asks for a tier and
  gets whatever the session's strongest model at that tier is. A plugin cannot
  pin a point release, and the docs no longer imply one.

### Added

- **`mcp-servers` install scripts can now enable write access at registration
  time.** `MCP_MS_ALLOW_WRITES` is a boolean gate, not a credential, so unlike
  `MS_ADMIN_*`/`MS_USER_*` it is safe to bake into a server's own `claude mcp
  add --env` rather than requiring it in the launching shell too — scoped to
  that server, not every process on the machine. Set it in the shell running
  `install-prerequisites.sh`/`.ps1` before the `ms-mcp` item runs and every
  server it registers gets writes enabled; left unset, every server registers
  read-only and the item prints the exact per-server one-liner to flip it
  later. `mcp-servers/README.md` gained a section spelling out both the
  per-server and global ways to set it, since the answer wasn't written down
  anywhere before now — only its meaning was.

### Added

- **`mcp-servers` 0.2.0 — the three admin-scope servers authenticate with no
  app registration at all, if you're already signed in with `az login`.**
  `@badali404/mcp-ms-core`'s new `buildAdminCredential()` (replacing
  `getAdminCredential()`) tries a credential chain in order: (1) client
  secret via `ClientSecretCredential`, app-only, unchanged — used whenever
  all three `MS_ADMIN_TENANT_ID`/`_CLIENT_ID`/`_CLIENT_SECRET` are set; (2)
  `AzureCliCredential`, delegated, zero prompts against an existing
  `az login` session; (3) `DeviceCodeCredential`, delegated, an interactive
  one-time-per-process sign-in as the last resort — using
  `MS_ADMIN_CLIENT_ID` as a public-client app id if set, else the Azure
  CLI's own well-known client id. `MS_ADMIN_AUTH=secret|cli|device` forces
  one link instead of the auto fallback. Device-code prompts go to
  **stderr only**, never stdout (the MCP JSON-RPC channel). Each server's
  `doctor` subcommand now reports which link authenticated and whether the
  resulting token is app-only or delegated, alongside the scopes/roles it
  decodes from the token as before. `mcp-o365-user` is unaffected — its
  device-code-only, `/me`-scoped auth is deliberately not part of this
  chain and was not widened. `@azure/identity`'s persistent token cache was
  evaluated and not enabled (it needs a separate native-dependency plugin
  package); a device-code sign-in is a per-process-launch prompt, not
  persisted across restarts, by design. 19 new offline tests
  (`packages/core/test/adminAuth.test.ts`) cover the fallback order,
  `MS_ADMIN_AUTH` forcing each mode, stderr-not-stdout for the device-code
  prompt, and `doctor` reporting the resolved mode. All five packages
  bumped `0.1.3` → `0.2.0` in lockstep (core pin updated in all four
  servers); `mcp-servers/README.md`, `docs/remaining-setup.md` (now a
  3-tier walkthrough: `az login` only / device code with a public-client
  app / full app-only registration), `INSTALLATION.md`, and both install
  scripts updated — the `ms-mcp` item now also checks `az account show` as
  sufficient to register the admin servers, still writing no secrets.

- **`mcp-servers/` — four local Microsoft MCP servers on one shared auth/HTTP
  workspace package.** `mcp-msgraph` (tenant directory), `mcp-intune` (device
  management), `mcp-o365-admin` (mailboxes/licenses/password reset — all
  app-only, tenant-wide), and `mcp-o365-user` (the signed-in user's own
  mail/calendar/files, delegated device-code sign-in). Not marketplace
  plugins — npm packages under `mcp-servers/packages/`, npm-workspace-linked
  against `@badali404/mcp-ms-core`, built with the official
  `@modelcontextprotocol/sdk`. Every write/destructive tool is gated behind
  **both** `MCP_MS_ALLOW_WRITES=1` and a per-call `confirm: true`; every
  server ships a `doctor` subcommand that acquires a real token and prints
  the scopes/roles actually granted. Offline test suite (mocked `fetch`, no
  live tenant) via `npm test`; wired into
  `.github/workflows/mcp-servers.yml`.

  Azure Resource Manager is deliberately not a fifth server: the official
  `@azure/mcp` already covers ARM comprehensively (dozens of service-scoped
  tool groups, plus generic `arm` CRUD), so this repo does not duplicate it —
  see `mcp-servers/README.md` for the reasoning.

  **Menu item 21, `ms-mcp` — off by default, needs tenant credentials.**
  Unlike the item 9–12 MCP servers, none of these four are on npm yet, so the
  item can't `npx -y <pkg>@latest` them: it detects `mcp-servers/package.json`
  under the current directory (this script never resolves its own location),
  builds it with `npm install && npm run build`, then runs `npm install -g .`
  inside each server package it has credentials for and registers the
  resulting global bin name (`mcp-msgraph`, `mcp-intune`, `mcp-o365-admin` —
  need `MS_ADMIN_TENANT_ID` + `MS_ADMIN_CLIENT_ID` + `MS_ADMIN_CLIENT_SECRET`;
  `mcp-o365-user` — needs `MS_USER_CLIENT_ID`), printing what's missing and
  skipping rather than failing otherwise. The global install works pre-publish
  because these are npm workspace members — it symlinks rather than
  reinstalling, so the dependency on `@badali404/mcp-ms-core` still resolves
  through the workspace's hoisted `node_modules` instead of 404ing against the
  registry.

  **The npx path is now real, not just documented.** Five packages carry
  `publishConfig`/`files`/`bin` shaped for `npm publish`: `files` is scoped to
  `dist/src` only (no compiled test output in the tarball — verified with
  `npm pack --dry-run` per package), and each server's `build` script chmods
  its compiled `cli.js` to `0o755` so the `#!/usr/bin/env node` shebang is
  executable on Linux (Windows needs neither — npm's own `.cmd`/`.ps1` shims
  handle it there). `.github/workflows/publish-mcp-servers.yml` publishes all
  five — core first, since the four servers pin an exact
  `"@badali404/mcp-ms-core": "0.1.0"` dependency — on a pushed `mcp-servers-v*`
  tag, via `npm publish --provenance --access public` authenticated with an
  `NPM_TOKEN` repository secret. Until the `@badali404` npm scope exists and
  that secret is set and a tag is actually published, `npx -y @badali404/<pkg>`
  cannot resolve anything — `mcp-servers/README.md` says so plainly and
  documents `npm install -g` (Option B, what the installer now uses) and the
  direct-path form (Option A) as the two working interim installs.

### Fixed

- **`crew` 0.11.4 — `crew:pm` could fail to dispatch with "Teammates cannot
  spawn other teammates."** `pm.md` (the only crew role with the `Agent` tool)
  had no guidance on whether to pass a `name` when dispatching a role, so it
  could end up spawning dispatched roles as named, addressable teammates. The
  runtime's team roster is flat -- a teammate (which the PM itself may be,
  depending on how it was invoked) cannot spawn further named teammates, only
  plain subagents. `pm.md`'s "Dispatching" section now says explicitly: never
  pass `name` to the Agent tool when dispatching a role. Every dispatched role
  is read and reported on within the same turn it was sent, so none of them
  ever needed to be individually addressable afterward.

- **`mcp-servers/` QA pass: a merge-blocking `npm publish --provenance`
  failure, a status-vs-parse ordering bug, and no throttling handling.** All
  five `package.json` now carry `"repository"` (type/url/directory) —
  `--provenance` refuses to publish without it, which would have killed the
  publish workflow's very first step. `GraphClient`'s `request()` and
  `getAllPages()` used to call `JSON.parse` before checking `res.ok`; a
  non-JSON error body (a WAF's HTML, a plain-text 5xx from an intermediate
  proxy) threw a `SyntaxError` and lost the real status code. Both now read
  the body first, parse it as JSON only if it looks like JSON, and fall back
  to the raw text inside a proper `GraphApiError` that still carries the
  status. Neither method handled `429` at all — Graph throttles routinely in
  real tenants — so both now share a bounded retry (max 3 attempts) that
  honors `Retry-After` (seconds or an HTTP date) and caps the wait at 30s.
  `getAllPages()` also used to truncate silently at `maxPages`, presenting a
  partial list as if it were complete; it now returns `{ items, truncated }`,
  and every server's list tool (`pagedResult()`, new in
  `packages/core/src/toolResult.ts`) appends a plain-text note to the tool
  result when truncated, so the model knows more data may exist. `post`/
  `patch`/`put`/`delete` on `GraphClient` now carry a doc comment stating they
  perform no write-gating themselves — every caller routes through
  `assertWriteAllowed` by convention, not by the type system. 12 call sites
  across all four servers and 2 in `packages/core/test/graphClient.test.ts`
  updated for the new return shape; new tests cover a non-JSON 500/502/503, a
  204 and an empty-200 body, a 429 that retries then succeeds, a 429 that
  exhausts its retry budget, a capped wait, and both `truncated: true` and
  `truncated: false`. `Install-MsMcpGlobal` (defined nested inside an
  `Invoke-Step` scriptblock in `install-prerequisites.ps1`, unlike this
  script's other helpers) was sabotage-tested against
  `scripts/check-powershell.ps1` — a typo'd call is caught (the checker's AST
  walk recurses into nested scriptblocks) — so it was left in place rather
  than moved to the top level.
- **New plugin `obsidian-vault` 0.1.1 - one or more Obsidian vaults as Claude
  Code's durable, token-efficient memory.** Cross-platform
  (Windows/Linux/macOS), no vault path hardcoded, and **multi-vault by
  design**: `~/.claude/obsidian/config.json` models named vaults
  (`vaults: { memory: {...}, codegraphs: {...} }`) because a machine-generated
  vault (a `graphify` code-graph export) commonly runs into the hundreds of
  thousands of notes on the same machine as a hand-curated one, on its own
  Local REST API port - so this plugin registers one MCP server per vault,
  never one server juggling two, and applies the frontmatter/ASCII/canvas
  contract guard only to the default vault.

  `/obsidian-vault:init` sets up the Local REST API bridge and per-vault MCP
  registration; `bridge-status`, `vault-guard`, and `vault-capture` hooks
  (each a `.sh`/`.ps1` pair sharing one Python module) probe every configured
  vault's bridge at session start, enforce the configurable contract on edit
  (every check OFF by default), and queue sessions for gardening.
  `obsidian-vault:gardener` and `obsidian-vault:reflector` agents distill and
  recall, with an explicit rule against fabricating a citation.
  `/obsidian-vault:canvas` and `/obsidian-vault:map` generate structural aids;
  `/obsidian-vault:graph` builds (`graphify . --no-viz --code-only`) and
  exports (`graphify export obsidian`, a separate subcommand - `--obsidian` on
  the build command is silently ignored) into a dedicated codegraphs vault
  laid out `<org>/<repo>/`, with a stub note left in the default vault. Ships
  with a committed, sabotage-tested regression suite for the one blocking hook
  (12 cases; the ASCII check was disabled once during development to confirm
  the suite goes red).

  **Named `obsidian-vault`, not `obsidian`**, specifically to avoid colliding
  with a third-party plugin already named plainly `obsidian` (from the
  `obsidian-skills` marketplace, wired into `install-prerequisites.sh` item
  18). `vault-automation/` (Windows-only prior art for the same
  capture/gardener idea) is marked superseded in its own README pointing here,
  but its scripts are left in place because the root `README.md` still
  documents them as a runnable quickstart. `claude-obsidian-setup/` targets a
  different thing - vault creation for the third-party `claude-obsidian`
  plugin's own conventions - and was left untouched. See
  `plugin/obsidian-vault/README.md`'s "Related" section for the full
  accounting.
- **`crew` 0.11.3 - config becomes two layers: an optional machine-global
  file plus the per-repo one.** `~/.claude/crew/config.json`, written by
  hand (no command creates it), sets defaults for every crew repo on the
  machine; the repo's own `.crew/config.json` still wins where both set the
  same thing. Merged one level deep with the same policy `/crew:upgrade`
  already used to bring a v1 config's `pm` and `graph` blocks forward - now
  named `crew_state.merge_defaults` and shared by both, instead of a second
  implementation that could quietly diverge. A malformed global file is
  treated exactly like an absent one and never touched. Two things
  deliberately skip this layering: `schema`, which is a fact about the repo
  file's own version and would otherwise look current the moment any global
  file exists; and the heal path plus `platform-sync`, which write only the
  repo file, always.

  - **crew-graph's Obsidian export gets a configurable target layout.**
    `graph.obsidian.layout` is `"flat"` (default, unchanged behaviour -
    `graph.obsidian.dir` is the export target verbatim) or `"org/repo"`
    (`dir` is a per-org folder and the skill appends `/<repo>` under it, for
    a vault laid out as `<vault>/<org>/<repo>/`). The export subcommand
    syntax and the `graph.obsidian.confirmed` consent gate are unchanged.
  - **0.11.1 -> 0.11.2:** CI caught a pylint `consider-using-dict-items` in
    a test, and fixing it exposed a real cyclic import between
    `crew_state` and `crew_config` (the first draft of this layering had
    `crew_state.collect` reach back into `crew_config` to resolve the
    global layer). `collect()` now takes the resolved config as a plain
    `cfg_override` argument; `crew_config.layered_state(root)` is the new
    composition point that supplies one. `pylint $(git ls-files '*.py')`
    exits `0`.
  - **0.11.2 -> 0.11.3, three QA guard gaps:** `hook_once.claim()` no
    longer fails open when `session_id` is absent - it derives a
    calendar-day fallback key instead, so the `.sh`/`.ps1` pair can no
    longer race a duplicate write when the payload happens to carry no
    session id. `resolve_config()` now exempts `schema` structurally
    rather than by caller discipline - a global file carrying one can no
    longer leak into an unmigrated v1 repo's resolved config. And the
    template-drift test now also covers the inline JSON copy in
    `crew-setup/SKILL.md`, extracted and compared parsed rather than
    byte-wise, so a field added to `default_config()` and forgotten in
    the doc fails CI too.

- **`crew` 0.11.0 - `.crew/config.json` recreates itself when it goes missing
  or stops parsing.** The `platform-sync` `SessionStart` hook, which already
  repaired the `platform` block, now also recreates the whole file: missing
  or empty gets fresh defaults straight away, a present-but-malformed file
  gets copied aside to `config.json.broken` first (never overwriting an
  earlier `.broken` from a prior bad session), and anything that already
  parses as an object is left alone byte for byte. **Guard: only where
  `.crew/` already exists** - a plain git repo with no crew setup is never
  colonized just because a session opened in it. Recreating the file resets
  every human choice - `tracker`, `roles`, `tier`, and the rest - back to
  defaults, and the one-line report says so and points at `/crew:init` to
  re-record them.

  - **One source for the defaults, not three.** `hooks/scripts/crew_config.py`
    is the new module that owns `default_config()`, built from
    `crew_state.PM_DEFAULTS`, `crew_upgrade.GRAPH_BLOCK`, and
    `crew_state.SCHEMA_CURRENT` rather than a fourth hand-copied literal. The
    committed template `templates/config.template.json` - what `/crew:init`
    writes - and the heal path both call it, and a test asserts the template
    equals its output byte-for-byte so the two can never quietly drift apart.

- **`crew` 0.10.0 - an Obsidian Kanban board is now a fourth ticket tracker,
  alongside `files`, `jira` and `sdp`.** Set `tracker: "obsidian"` and point
  `obsidian.vaultPath` at a vault. The board is a markdown file the
  [Kanban plugin](https://github.com/mgmeyers/obsidian-kanban) round-trips, so
  crew writes files and Obsidian draws a board.

  - **No connector, and therefore a different precondition.** Jira and SDP are
    offered during setup only when their MCP tools answer. Obsidian has nothing
    to probe, so what has to resolve is a vault directory that exists on this
    machine. Bolting that onto the MCP sentence would have produced a tracker
    that looks configured and is not.
  - **The vault is the remote, exactly as Jira is.** Ticket notes and the board
    live in the vault; `.work/cache/T-####.md` is the terse local mirror
    `/crew:work` reads, so the vault is touched at pickup and completion only.
    The key keeps its `T-####` shape, so nothing that recognises a ticket by its
    `LETTERS-digits` form needed changing — no Python moved for this release.
    It is also the reason this mode, alone among the non-file trackers, keeps
    `.work/INDEX.md`: the session brief finds the open ticket by reading that
    file, and `SDP-40219` was never going to be in it while `T-0042` can be. So
    the Obsidian tracker closes a blind spot Jira and SDP still have.
  - **Five lanes, and dragging a card is how status changes.** Backlog, Ready,
    In Progress, Review, Done, renameable via `obsidian.columns`. On pull the
    card's lane wins for status and the note wins for content; on push crew
    writes both. That rule is stated because both sides here are local markdown
    and both look equally authoritative, which makes the divergence hazard
    *worse* than Jira's rather than absent. `/crew:obsidian-sync` refuses to
    fall back to file tickets for the same reason `/crew:jira-sync` does.
  - **The board is edited in place, never regenerated.** Three parts are
    load-bearing and a naive rewrite destroys all three, after which the file
    silently opens as plain text instead of a board: the `kanban-plugin: board`
    frontmatter, the trailing `%% kanban:settings` block, and the `**Complete**`
    marker in the done lane. An archive sits below a `***` break under
    `## Archive` and is left alone. Format verified against the plugin's own
    parser at 2.0.51, not reconstructed from memory.
  - **New command `/crew:obsidian-sync <T-####> [--push]`**, argument shape
    identical to the other two syncs. 21 commands now; `validate-prompts.py` is
    at 110 checks.

  Two things the docs say plainly rather than leaving to be discovered: the
  vault lives outside the repo, so ticket state does not travel with a branch
  and is not on a colleague's machine — that is the trade for a board you can
  drag cards on. And crew never commits the vault.

### Fixed

- **`crew` 0.9.1 - two test-suite defects, both found by CI rather than by
  reading.** `test_pm_brief.py` re-imported `json` inside a function that
  already had it at module scope; pylint reported W0404 and exited 4 while
  still printing "rated at 10.00/10", which is exactly why this repo's rule is
  to judge pylint by its EXIT CODE and never by the rating line.

  The second was pre-existing and latent: `test_a_hand_edited_schema_does_not_
  crash_collect` named its scratch directories `s{abs(hash(str(bad))) % 9999}`.
  Python randomises string hashing per process, so on some seeds two of the
  five values collide, `make_repo` dies on `FileExistsError`, and the suite
  fails for a reason having nothing to do with what the test checks. Observed
  failing locally on that collision, then confirmed fixed across five explicit
  `PYTHONHASHSEED` values. Named by index now.

### Fixed

- **`infra-work-ticketing` 1.1.1 - dropped a stray `.claude/settings.local.json`
  that shipped with the skill.** It registered a `SessionStart` hook pointing at
  `C:/Users/d3ade/.local/bin/headroom.EXE`, a binary on one machine. Anyone who
  installed the skill and opened a session inside its directory got
  `No such file or directory` from a hook they never configured. Nothing else in
  the skill used it.

### Added

- **`crew` 0.9.0 - PM autonomy is now a switch, with guardrails.** 0.8.0 gave
  the PM assign authority unconditionally, which is the right behaviour for
  someone who asked for it and the wrong default for everyone else. It is now
  `pm.authority` in `.crew/config.json`.

  - **`report-only` (default) vs `act`.** `report-only` recommends and stops;
    `act` dispatches roles and refreshes diagrams on its own. The default is
    deliberate: a plugin update must not turn someone's PM autonomous
    underneath them, because consent to install is not consent to delegate.
    The field already existed in `PM_DEFAULTS`, in the config templates and in
    `README.md` - documented as "always `report-only`" and read by nothing.
    It is now the actual switch.

  - **It fails closed.** An unrecognised value resolves to `report-only`
    rather than raising or guessing, because for a field that grants
    permissions the failure direction has to be the restrictive one. `"Act"`,
    `"ACT"` and `" act "` are accepted as `act` - same intent typed carelessly,
    not a different one. Normalisation happens once in `collect()`, so no
    consumer downstream ever re-decides what a typo means and they cannot
    disagree.

  - **The pulse says different things.** Under `act` the `Stop` hook emits a
    work order; under `report-only` it emits recommendations and explicitly
    forbids dispatching. Sending the wrong one would make the setting a lie -
    config saying "ask me" while the hook said "go".

  - **The rabbit-hole rule.** Autonomy's failure mode is not doing the wrong
    thing, it is doing too many things: refresh a diagram, notice a bug, fix
    it, notice thin tests, write tests, and the diagram is still stale. So a
    problem the PM stumbles on is fixed **only when it blocks a finding it was
    already working** - build broken, harness will not run, migration will not
    parse. Unblocking the current job is finishing the job. Everything else is
    recorded and left alone: a ticket when `tracker` is set, otherwise a
    `TODO.md` line with the reason it was deferred. The report must say what
    was deferred and where it went, because a guardrail whose effects are
    invisible reads as the PM having found nothing.

  - **`pm.maxDispatches`** (default 3) caps roles per pass. Blockers found
    mid-task do not count against it.

  - **`/crew:pm authority [report-only|act]`** reads or sets it, and
    `/crew:init` now asks as its fourth setup question, defaulting to
    `report-only` on any hesitation. `/crew:pm assign` still acts anywhere -
    typing it *is* the explicit instruction - and says when the config
    disagrees, so a user who wanted it permanent learns there is a setting.

  - 24 new cases (shell suite 95 -> 101, pytest 306 -> 324), sabotage-tested:
    making an unknown authority widen to `act` instead of failing closed turns
    both suites red.

- **`crew` 0.8.0 - the PM assigns work, and re-engages itself when state
  changes.** Three related gaps, reported together: the PM only ever spoke at
  session start, so a session that opened clean and then closed a ticket or
  broke a gate heard nothing; the `pm` agent was structurally unable to act on
  what it found, holding no `Write` tool and returning a report that the user
  then had to act on themselves; and architecture, process and data-flow
  diagrams had no staleness signal at all, so nothing ever noticed they had
  drifted.

  - **New `pm-pulse` `Stop` hook.** Re-engages the PM when the project's state
    actually transitioned - a ticket closed, a gate broke, diagrams fell behind
    HEAD. The gate is a **state fingerprint, not the event**: `Stop` fires once
    per turn, and a brief on every turn is the noise that makes people switch
    the PM off, at which point they get nothing. Turns that change nothing stay
    silent.

    It blocks (exit 2) to hand its findings back to the model, because stdout
    on `Stop` reaches the user but never the session - a PM that cannot be
    heard by the thing doing the work cannot assign any. Three loop guards:
    `stop_hook_active` is honoured first and unconditionally, the fingerprint
    marker means one state can only interrupt once, and the hook stands down
    after 12 pulses in a session rather than becoming the thing you disable.

    `hook_once` is deliberately **not** used - its own module docstring says
    why. Its marker is keyed on `(hook, session)` and never cleared, so a claim
    taken on turn 1 silences the hook for the rest of the session, which is
    exactly what this hook must not do. Keying the marker on the fingerprint
    instead de-duplicates the `.sh`/`.ps1` pair and gates on state change with
    one mechanism.

  - **The `pm` agent now dispatches.** It gains `Write`, `Edit` and `Agent`,
    and a dispatch table mapping each trigger to the role that closes it. A
    manager whose only output is a recommendation is a manager the user has to
    manage. Three bounds keep it honest: a **stated user priority outranks**
    the PM's trigger ordering, and it says so when it re-orders; **removal and
    deletion still need an explicit yes** - offboarding, deleting a codemap or
    diagram, rewriting `metrics.md` - because adding capability is reversible
    and removing it destroys the evidence that would say whether removing it
    was right; and a multi-agent run is **announced before** it happens. Writes
    stay scoped to `.crew/` and `docs/diagrams/`. `/crew:pm assign` is the
    manual entry point.

  - **Diagram freshness is now a tracked fact.** `crew_state.py` reads
    `docs/diagrams/*.mmd`, parses the short sha out of the documented
    `%% Generated from <repo>@<sha>` header, and reports `diagrams.behind` and
    `diagrams.missing`. Two new triggers, `diagramsStale` and `diagramsMissing`,
    sort **below** `graphStale` and `knowledgeBehind` on purpose: a diagram
    regenerated from a code map that is itself behind HEAD is stale output
    wearing a fresh anchor, which is worse than the diagram it replaced because
    it no longer advertises its age. `diagramsMissing` stays quiet until there
    is a codemap, so a fresh setup is not nagged about three diagrams on
    session one.

    Diagrams are the **only** documentation artifact the crew regenerates
    unasked. That is not a general licence: they carry a machine-checkable
    anchor, so "is this still true" has a real answer. Prose docs keep
    `crew-docs`'s deliberate *do not touch* default, because whether a change
    deserves a CHANGELOG entry is a judgement about what users can observe and
    no sha answers it.

  - Found while writing the tests: reusing the codemap's `_ANCHOR_RE` for
    diagrams reads **every** correctly-anchored diagram as stale. That regex
    requires the line to start with `anchor:`, which is a syntax error in a
    Mermaid source - provenance there has to live inside a `%%` comment. The
    bug looks like the feature working, right up until nothing is ever current.
    `_DIAGRAM_ANCHOR_RE` handles the documented header and the hand-written
    `%% anchor:` form.

  - 40 new cases in `run-tests.sh` (50 -> 90), sabotage-tested both ways:
    removing the `stop_hook_active` guard and reverting the anchor regex each
    turn the suite red.

- **`crew` 0.7.0 - the `platform` block repairs itself at session start.** It is
  the one block in `.crew/config.json` that is committed and is therefore wrong
  for everybody who did not run `/crew:init` - and `windowsHostIp` is wrong for
  the same person after a reboot, because WSL2's gateway changes. Open a repo on
  Windows that was set up in WSL and the session now opens with
  `## platform - config said linux, this is windows-bash; updated 5 field(s)`,
  itemised, and the config already fixed.
  - **One rule makes it safe: it writes derived facts and nothing else.** The
    seven writable keys are `os`, `wsl`, `wslVersion`, `distro`, `shell`,
    `repoFilesystem` and `windowsHostIp` - each an answer to "what machine is
    this", which nobody hand-edits usefully. A test pins that list, because
    adding a preference to it would turn the hook into something that overrules
    people.
  - **Preferences are reported, never rewritten:** an `autoClear.method` that
    only exists on the other platform (which would otherwise make auto-clear
    stand down silently), a clone under `/mnt/` where every file operation goes
    through the Windows translation layer, CRLF in a committed `.sh` that bash
    reports as "bad interpreter: ...^M". `tracker`, `qa`, `roles`, `tier`,
    `notify`, `emergency`, the context thresholds and `verifyGate` are never
    touched.
  - This is why it may write when the PM may not: the PM's subject is
    *judgement*, and whether a role earns its context is not a fact.
    `platform.os` is a fact, it is wrong on the other machine, and being asked
    about it once per clone would be worse than having it fixed. It still says
    what it changed - a silent config edit would be indefensible.
  - It does not write when nothing changed, so it never dirties a tree just by
    opening a session, and it preserves the file's existing line endings - a
    CRLF config rewritten as LF is a whole-file diff for whoever committed it.
    A read-only checkout, or no python, reports what it *would* have changed.
  - Detection covers native Linux, WSL1, WSL2 (including reading the gateway as
    the Windows host address), macOS, native Windows, and Git Bash on Windows -
    which `sys.platform` cannot distinguish from a cmd session, so `MSYSTEM`
    decides whether crew should be writing bash or PowerShell here.
  - Both flavours are thin wrappers over one python module
    (`hooks/scripts/crew_platform.py`), the `pm-brief` pattern. For a hook that
    writes config, two implementations that disagree about what they write is
    the last thing anybody wants, and this plugin's `.sh`/`.ps1` pairs have
    drifted for a whole release before.
  - `tests/test_platform_sync.py`, 29 cases. The detection paths are exercised
    by faking `platform.system()` and the `/proc` files WSL is recognised by,
    because a suite that only covers the OS it runs on is how a cross-platform
    bug survives.
  - Found while writing it: reading the config in text mode let universal-newline
    translation strip CRLF before anything could see it, so the
    line-ending-preserving write silently rewrote a CRLF config as LF.

- **`crew` 0.6.2 - `context.autoClear`, experimental, off by default.** A matched
  pair of scripts that type `/clear` into the terminal once the handoff note is
  written. This does **not** contradict the standing correction that a hook
  cannot clear its own session - it does not touch the conversation. It drives
  the *terminal*, typing at the prompt the way a human would, which is a
  different mechanism with a different failure mode.
  - That failure mode is why it is experimental: typing into a terminal is only
    safe if you know which terminal. `tmux` targets `$TMUX_PANE` by id and never
    touches focus, so in tmux this needs no configuration beyond
    `enabled: true`. `xdotool`, `wtype` and the Windows `SendKeys` path all
    depend on focus, so they **require** `context.autoClear.windowTitle` and
    refuse rather than guessing; `wtype` additionally needs `unsafeFocus: true`,
    because Wayland offers no way to check what has focus at all. The Windows
    child re-checks the foreground window's title immediately before typing, so
    alt-tabbing during the delay cancels the send rather than redirecting it.
  - Five conditions before it types anything: `enabled` exactly `true` (the
    string `"true"` is not), the handoff was actually requested this session,
    the note exists and is **newer** than that request, it has at least
    `minHandoffLines` non-blank lines (default 5 - clearing on a two-line
    placeholder loses the work and leaves a note that says "continue the work"),
    and nothing has claimed the one-per-session attempt.
  - The attempt is claimed immediately **before** the send, not with the
    conditions, so a misconfiguration does not burn the session's only try -
    fixing `windowTitle` mid-session actually retries. A `--dry-run` does not
    claim it either.
  - Every refusal is written to `.crew/.autoclear.log`, because a `Stop` hook's
    stderr is invisible when it exits 0 and without it "nothing happened" cannot
    be told apart from "the feature is broken".
  - `--dry-run` / `-DryRun` prints the method, target, command and delay it would
    use and sends nothing; `--force` / `-Force` skips the handoff conditions so
    the plan can be inspected outside a real session.
  - `tests/test_auto_clear.py` - 32 cases across both flavours, every one either
    `--dry-run` or against a fake `tmux`/`xdotool` on `PATH`, so no test can send
    a keystroke to the machine running it. Sabotage-tested three ways: moving the
    claim back into the conditions block (5 red), dropping the CR strip (12 red),
    and allowing a focus-based method with no window title (1 red).
  - A third bug, found by CI rather than by me: on a Linux runner with pwsh
    installed, `auto-clear.ps1` ran every condition, claimed the
    one-per-session attempt and reported "sent" - on a platform where its
    SendKeys path cannot type anything. Reporting success while delivering
    nothing is worse than failing, because the log then says it worked. It now
    exits immediately unless `$IsWindows`, the suite treats that flavour as
    native-Windows-only, and a new case pins the stand-down on a non-Windows
    pwsh. 0.6.0 and 0.6.1 were set on the branch and never published; the
    released version is 0.6.2, which also carries the ANEWINF-758 pytest
    determinism fix this branch merged in from `main`.
  - Two bugs found by running it rather than reading it, both now covered. The
    config was read as tab-separated fields with a tab as the field separator,
    and a tab is IFS *whitespace*, so bash collapsed consecutive separators and
    an empty `windowTitle` - the default - shifted every later field left by
    one. And python on Windows writes CR-LF, so every value arrived with a
    trailing carriage return: the `enabled` comparison failed and the script
    exited having done nothing. Both were invisible failures from a `Stop`
    hook, which is the worst kind.

- **`crew` 0.5.2 - ServiceDesk Plus as a third tracker.** `tracker: "sdp"` plus
  `/crew:sdp-sync <REQUEST-ID> [--push]`, mirroring the Jira path rather than
  inventing a second shape: pull keeps id, subject, status, requester, priority,
  category and the last three notes and discards the rest, `/crew:work` reads
  that cache instead of the API, and sync happens at pickup and completion only.
  `/crew:ticket` and `/crew:work` both learned the mode, and `/crew:init` offers
  it as the third answer to the tracker question - **only when the `sdp_*` tools
  are actually reachable**, since a repo configured for an API nobody can call
  stops every later command on the same missing precondition.
  - **The local key is `SDP-<id>`, not the bare request number.** SDP ids are
    plain integers and the rest of crew recognises a ticket by its
    `LETTERS-digits` shape, so a bare `40219` is invisible to the session brief,
    to `/crew:work` and to the index. Both halves of that claim are now pinned by
    tests, because the failure mode is silence: every SDP repo would report "no
    ticket open" forever.
  - Three things the command has to get right that Jira does not have: notes are
    **requester-visible** unless private (`sdp.noteVisibility` defaults to
    `private`, and that is not a substitute for scrubbing), a bad field value
    **rejects the whole write** rather than partially applying it (resolve
    against `sdp_list_metadata` first), and **closing is not crew's decision** -
    `sdp.closeOnDone` defaults to `false`, so push transitions a request and
    leaves closure to whoever owns the queue.
  - No `.mcp.json` ships for it, deliberately: the SDP connector is normally
    registered at user or session scope, and a per-repo one would prompt for
    approval in every repository where the plugin is enabled.
  - New config block `"sdp": { "portal": null, "noteVisibility": "private",
    "closeOnDone": false }`. Documented in `crew/README.md` 13b, the
    configuration table, `PLUGINS.md`, and both setup docs.

- **`crew` 0.5.1 — `/crew:emergency`, a time-boxed lane for when something is
  actually broken.** The gates that normally earn their keep are, during an
  outage, standing between you and the fix, and the honest options are to work
  around them silently or to make standing them down a decision with a record
  and a clock on it. `/crew:emergency <what is broken>` writes
  `.crew/incident.json`; while it exists and its `expiresAtEpoch` is in the
  future, `verify-gate` exits 0 without running the checks and `promote-gate`
  computes its preconditions, records the ones that failed, and allows the
  deploy. `status`, `extend [minutes]` and `end` are the rest of the surface.
  Declaring also fans out read-only investigation lanes in parallel — what
  changed in the window before the symptom, what shares the failing path, the
  most probable causes with the cheapest observation that would kill each, plus
  `security` and `dba` lanes when the symptom calls for them.
  - **It expires on its own.** The gates compare an integer epoch, so nothing
    runs and no file is touched to re-gate. Forgetting to close an incident is
    the realistic failure — nobody forgets to declare one during an outage — and
    it cannot leave a repository permanently ungated. `emergency.ttlMinutes`
    defaults to 120; `extend` is capped by `emergency.maxTtlMinutes` (480) and
    measured from *now* each time, so repeated extensions cannot compound.
  - **The command guard never stands down.** `guard.sh` / `guard.ps1` has no
    incident branch and must not get one. Standing down a check that says a
    change is wrong is a trade; standing down the one that stops a change being
    unrecoverable — a force push, a destructive Terraform verb, a history
    rewrite, a secret read into the transcript — is not, and an incident is
    precisely when someone is tired enough to need it.
  - **The debt list is the deliverable.** Every skipped gate is recorded to
    `.crew/incident-skips.log`, one row per gate and reason rather than one per
    turn, and `end` turns it into `.work/INCIDENT-<id>.md` plus an archived
    record under `.crew/incidents/`. Deleting the state file is what puts the
    gates back, and it happens only after the archive is on disk.
  - **Every session start says so.** `incidentActive` and `incidentUnclosed`
    are the two highest-priority PM triggers, above `upgradeNeeded`, and the
    incident line sits in the brief's quiet lines so no line cap can truncate
    it away. A session that does not know the gates are off is a session about
    to merge unverified work believing it was checked.
  - **A repository can forbid the whole thing.** `emergency.standDown: false`
    keeps every gate gating; the incident is still declared, recorded, briefed,
    and still spawns its lanes.
  - Covered by `tests/test_incident.py` (24 cases), 15 new cases in
    `hooks/scripts/_test/run-tests.sh` — including that the guard still blocks
    during an incident and that an expired one gates again — and
    `tests/test_gates_powershell.py`, which runs the same scenarios against the
    `.ps1` gates. All sabotage-tested in both flavours.

### Fixed

- **`crew` 0.5.4 - ANEWINF-758: the `plugin/crew` pytest suite was
  nondeterministic, 87-97 of ~182 tests passing on identical code across
  consecutive runs.** Every `git` `subprocess.run` call in the suite - and
  two in production code - left `stdin` at its default, so `git` inherited
  whatever OS handle the parent process's stdin currently pointed at.
  pytest's fd-based output capturing tears down and rebuilds file descriptor
  0 on every test's setup/teardown, so an inherited handle can go stale
  mid-suite; on Windows that surfaces as `OSError: [WinError 6] The handle
  is invalid` inside `subprocess._make_inheritable`, and the documented
  equivalent on a CI runner whose own stdin is a pipe is `EBADF`. A second,
  quieter instance of the same bug lived in `crew_state.py`'s `git_out()`
  and `crew_upgrade.py`'s `_head()`: both wrap their `subprocess.run` call in
  `except (OSError, subprocess.SubprocessError): return None`, written to
  turn "git is absent" into a soft `None` - which also silently swallowed
  the transient handle-invalid error and returned a wrong-but-non-crashing
  `None` on an unpredictable subset of runs. All eight call sites (four in
  `tests/crew_fixtures.py`, one each in `tests/test_crew_fixtures.py` and
  `tests/test_gates_powershell.py`, plus the two production sites) now pin
  `stdin=subprocess.DEVNULL`, removing the dependency on the inherited
  handle entirely. Proven with five consecutive full-suite runs reporting
  an identical pass count and exit 0 each time; before the fix, five
  consecutive runs ranged from 74 failed/113 passed to all passing with no
  code change in between.
- **`crew` 0.5.3 - a comment, from an advisory review.** `read_skips` now
  dedupes on `(gate, detail)`, which made the per-gate loop in `report()`
  look like a redundant second dedupe worth deleting. It is not: what it does
  that `read_skips` does not is drop empty details, which would otherwise
  print as a bare bullet - and the count beside it is distinct debts rather
  than how many turns declined to run something. Both are now stated where
  someone would go to simplify it.

- **`crew` 0.5.1 - findings from the Codex review pass, fixed before merge.** 0.5.0
  was set on the branch and never published; the released version is 0.5.1.

  - `crew_incident_active` in `_common.sh` pulled `expiresAtEpoch` out with
    `sed`, so `{ not json "expiresAtEpoch": 9999999999` stood every gate down in
    bash while the PowerShell twin's `ConvertFrom-Json` correctly rejected it -
    a gate switchable off by a typo, and a flavour disagreement in the
    fail-*open* direction. It now parses the document in full and treats every
    failure, including no python at all, as "no incident". Two regression cases
    cover it, and the old implementation demonstrably read that epoch.
  - Skip-log rows are deduplicated on read as well as on write, so a race
    between the two hook flavours can no longer inflate the count of what is
    owed, and tabs, carriage returns and newlines are normalised out of gate
    names and details in all three implementations - a `rollbackReason` with a
    newline in it would otherwise forge a row.
  - `end()` re-reads the state file and refuses to close an incident whose id
    changed underneath it, before writing anything: a declaration landing mid
    close would otherwise be archived under the previous id and deleted,
    re-gating a repository someone had just declared an incident for.
  - `_write_state` uses a pid-unique temp file, so two writers cannot interleave
    into one and publish a torn document.
  - Documented rather than fixed, both in `crew/README.md` 24: the expiry is
    wall-clock, so a machine whose clock moves backwards extends the window; and
    the `.crew/.handoff-requested` marker is per repository rather than per
    session, so two sessions in one repo share one context warning. The second
    is pre-existing and wrong rather than deliberate - the fix is to key it on
    the payload's `session_id`.

- **`crew` 0.5.1 — the context watch no longer asks for a handoff with 200k
  tokens still free.** `context.warnAt` was tuned when every window was 200k,
  where 0.8 leaves 40k: about enough to finish a thought and write the note. The
  same 0.8 on a 1M window leaves 200,000 tokens unused and still asks you to
  wrap up, which is a whole 200k session's worth of room thrown away — and no
  percentage fixes it, because the right amount of headroom is an absolute
  number. The threshold is now the **later** of `warnAt * budget` and
  `budget - context.reserveTokens` (new, default 100000), so the floor can only
  ever push the warning later: a 200k window still fires at exactly 80% (40k
  < 100k, so the percentage wins) and a 1M session moves from 80% to 90%.
  `reserveTokens: 0` or `null` restores the pure percentage, and `warnAt: 0`
  still fires immediately — the floor is skipped entirely for it rather than
  quietly outranking the one explicit override. The warning now names which rule
  fired, with both figures and the remaining headroom, so a threshold behaving
  oddly is visible instead of mysterious. New cases in
  `tests/test_context_watch.py` pin the no-regression case, the 1M case, the
  default, the `warnAt: 0` override, and full stderr parity between the two
  flavours on the new branch.
- **`crew` 0.5.1 — the once-per-session handoff marker is now claimed
  atomically** (`noclobber` in bash, `FileMode::CreateNew` in PowerShell). On
  Windows with Git Bash installed both flavours of the `Stop` hook really do
  run, and a test-then-create let both through, so the same warning was emitted
  twice. The PowerShell side also had to take the absolute path: `[System.IO.
  File]` resolves a relative one against `[Environment]::CurrentDirectory`,
  which `Set-Location` does not update, so the claim would have landed in
  whatever directory the hook was spawned from.
- **`crew` 0.5.1 — `Resolve-CrewBash`'s PATH fallback could return an empty
  interpreter.** A `bash` function or alias defined in a PowerShell profile is
  returned by `Get-Command bash -All` ahead of any `bash.exe` with an empty
  `.Source`; `.StartsWith()` on that throws and returning it handed
  `& $bashExe` nothing, so the gate reported a smoke failure that was really a
  resolution failure. Tier b now takes `Application` entries only — the same
  guard the git walk-up already had.
- **`validate-prompts.py` counted a slash-command reference as a subagent
  dispatch.** `/crew:pm` in a command's prose is a pointer to another command,
  not an `Agent` call, but several names are both an agent and a command — so
  `scale.md`, which only mentions `/crew:pm`, was told to declare a tool it
  never uses. The check now excludes the slashed form.

### Changed

- **`scripts/check-powershell.ps1` now checks every tracked `.ps1`, not just the
  installer.** It defaulted to `install-prerequisites.ps1` alone, which left the
  crew plugin's hook scripts — the ones that run from a hook on someone else's
  machine, where a thrown exception is invisible — completely unguarded by the
  one check that catches a call to a function that does not exist. All 18 files
  pass; sabotage-tested by mis-naming a call in `verify-gate.ps1`, which the old
  default would not have caught. `-Path` still checks a single file. The first
  CI run of the wider check immediately earned it, by failing on the
  `ScheduledTasks` cmdlets in `vault-automation/setup-vault-automation.ps1`:
  that module ships with Windows and does not exist on the Linux runner, so
  those calls resolve for a developer and not for CI. They are in the
  `$externallyProvided` allowlist by exact name rather than by a
  `*-ScheduledTask*` pattern, so a typo in one of them is still caught -
  verified by introducing one.
- **CI runs the crew hook regression suite and the prompt validator.** Both were
  committed, documented as the safety net for hooks that can block a turn, and
  run only when somebody remembered to. A gate that stops gating still exits 0,
  which is exactly the kind of regression a suite nobody runs cannot catch.

### Fixed

- **`crew` 0.4.5 — the Windows `Stop` hook ran the verify smoke inside WSL.**
  With WSL installed, PowerShell resolves a bare `bash` to
  `C:\Windows\system32\bash.exe`, so `verify-gate.ps1` ran `_verify/smoke.sh`
  in a distro with no terraform, no python and a different `~`, and reported
  `SMOKE: 0/9 FAIL` on trees where Git Bash reads 12/12 — a blocking gate
  failing for a reason that had nothing to do with the repository.
  `Resolve-CrewBash` in `hooks/scripts/verify-gate.ps1` now walks up from
  `git.exe`'s own directory to `bin\bash.exe` or `usr\bin\bash.exe`, falls
  back to `Get-Command bash -All` minus System32 and WindowsApps, and only then
  to a bare `bash`, so nothing changes off Windows. Both call sites use it —
  the `smoke.sh` invocation and the `run: ["bash ..."]` rules from
  `.crew/verify.json` — and the failure output now names the interpreter it
  used. `tests/test_verify_gate_bash_resolver.py` covers the four resolution
  shapes: System32 first on PATH, a `mingw64` install, the WindowsApps
  execution alias, and a `git` defined as a PowerShell function, which used to
  throw a terminating error out of the hook. The PATH fallback carries the same
  guard as the walk-up, for the same reason: a `bash` function or alias in a
  PowerShell profile is returned by `Get-Command bash -All` ahead of any real
  executable with an empty `.Source`, which the gate would have run as an empty
  interpreter and reported as a smoke failure.
  0.4.4 was set on the branch and never published; the released version is
  0.4.5.
- **`crew` 0.4.5 also carries the five ANEWINF-720 silent-failure fixes**, which
  merged without a version bump and so never reached an installed copy: the
  rollback gate fails closed instead of skipping when `.crew/verify.json` omits
  `rollback`, generated `STATUS.md` and `verify.json` state that enforcement is
  session-local, `/crew:review` writes ticket-scoped scratch paths rather than
  racing concurrent reviews, the tool matcher sees commands invoked from inside
  a script, and the guard no longer fires on an incidental substring match.

- **`crew` 0.4.3 — the context watch no longer ends Windows sessions on turn one,
  and knows that Claude 5 models have a 1M window.** Three causes, all in the
  `Stop` hook pair `hooks/scripts/context-watch.{sh,ps1}`:
  - `context-watch.ps1` still estimated occupancy from transcript file size
    (`bytes/4*0.75`) against a hardcoded 200k. The transcript is cumulative, so on
    real sessions that read 158%, 195% and 664% — the handoff prompt fired on the
    first turn of every Windows session. It now reads the transcript's last
    `message.usage` record exactly as the bash flavour does, with the same model
    table, the same observed-peak correction, and byte-identical output.
  - The model table in both flavours said `opus`, `sonnet` and `fable` are 200k.
    `claude-opus-5`, `claude-sonnet-5` and `claude-fable-5` ship with 1M; the
    observed-peak self-correction only rescued that past 190k, so the 160k–190k
    band fired falsely on every Claude 5 session. The table now carries the 1M
    entries above the generic 200k ones. The observed-peak correction also went
    the other way: it tripped at 95% of the table figure, so a Claude 5 session
    that legitimately passed 950k of a correct 1M entry was bumped to the 2M
    tier and the gate never fired. It now triggers only on a peak the window
    could not have held.
  - A pinned `context.budgetTokens` the session has already exceeded (an older
    `/crew:init` wrote `200000` into every config) is now overridden by the
    observed peak and reported as `configured+observed`. A stale pin the session
    is still *under* cannot be detected; set it to `null`.
  - Subagent turns were never counted — Claude Code writes them to
    `<session>/subagents/*.jsonl`, which the watch does not open — and that is
    now stated in the docs and pinned by a test; inline `isSidechain` records from
    older builds are skipped explicitly.
  - `tests/test_context_watch.py` previously fed both flavours a byte blob with
    no usage record, so the PowerShell drift was invisible. It now feeds real
    usage transcripts for every branch (Claude 5 at 170k must not fire, Haiku at
    170k must, stale pin override, subagent exclusion) and compares the two
    flavours' full stderr on the measured path.

### Removed

- **The `claude-mem` and VoltAgent menu items are gone from both install scripts.**
  They were items 9 and 10, both on by default, so a bootstrap run installed a memory
  plugin, Bun as its worker runtime, a `CLAUDE_MEM_WORKER_PORT` patch to
  `settings.json`, and ten VoltAgent subagent plugins whether or not you wanted any of
  them. All of that is out: the `--voltagent` / `-VoltAgent` flag and its sub-picker
  group, the `VOLTAGENT_*` / `$script:VoltAgentCatalog` catalogs, `install_bun` /
  `Install-Bun`, and `set_claude_mem_worker_port` / `Set-ClaudeMemWorkerPort`. The menu
  is now 20 items, 8 of them on by default. **Everything after the hole shifted down by
  two** — the MCP servers are 9–12, Supabase 13, Context7 14, Playwright CLI 15, SkillUI
  16, Strix 17, Obsidian 18, this repo's plugins 19, `graphify` 20 — so any script
  passing `--select` by *number* needs updating; the stable keys (`--select
  supabase,strix`) do not. Both scripts were changed together and verified to produce
  the same 20-row menu and the same answer for `--select 19` / `-Select 19`. The
  removal is documented across `README.md` (both tables, the switch table, and every
  per-item note that names a number), `INSTALLATION.md`, `MARKETPLACE.md` and
  `SECURITY.md`; `scripts/_test/menu-groups.sh` now exercises the range and
  out-of-range cases against the skills group instead of the VoltAgent one, and
  `check-marketplace.py` no longer expects a `VOLTAGENT_KEYS` array. Nothing already
  installed on a machine is touched — uninstall those plugins by hand if you want them
  gone (`claude plugin uninstall claude-mem@thedotmack`, and likewise for each
  `voltagent-*@voltagent-subagents`). The removed flag fails differently on the two
  platforms, so a script still passing it needs editing either way: `--voltagent a,b`
  on the `.sh` warns `Unknown option` twice (once for the flag, once for its argument,
  which no longer gets shifted past) and then installs the rest of the selection, while
  `-VoltAgent a,b` on the `.ps1` is a parameter-binding error and the script does not
  run at all.

### Fixed

- **`crew` 0.4.2 — every PowerShell hook was dead on Windows, and the command guard
  blocked nothing there for the second time.** `hooks.json` wrote each PowerShell entry
  as `& '${CLAUDE_PLUGIN_ROOT}/hooks/scripts/x.ps1'`. For a `shell: powershell` entry
  Claude Code substitutes that placeholder as a PowerShell *environment reference*, and
  PowerShell does not expand anything inside single quotes — so `&` was handed the token
  verbatim and the hook died with "is not recognized as a name of a cmdlet". Only the two
  `SessionStart` hooks reported it visibly, because they are the ones that fire at
  startup; `guard.ps1`, `promote-gate.ps1`, `handoff-write.ps1`, `notify.ps1`,
  `verify-gate.ps1` and `context-watch.ps1` were failing just as silently. Fixing the
  quoting exposed a second failure underneath it: `& script.ps1` inside PowerShell's
  `-Command` does not propagate the script's exit code, so a guard's `exit 2` arrived as
  1 — a non-blocking error — and the command ran anyway. Every PowerShell entry now
  double-quotes the path and ends with `; exit $LASTEXITCODE`, verified end to end
  against `guard.ps1` (blocking `git push --force`, exit 2; allowing `Get-ChildItem`,
  exit 0). The bash entries got the same double-quoting, which they needed for a home
  directory with a space in it. `scripts/check-marketplace.py` grew a
  `check_hook_commands` check that fails CI on either mistake, and both new rules are
  written into `CLAUDE.md`. This was not an install-script problem — the repo and
  installed copies were byte-identical, so every Windows install of `crew` had it.

### Changed

- **Re-pinned the README's one-liner install URLs** from `8fc09be` to `ae58c21`, per the
  rule in `CLAUDE.md`. `8fc09be` predates the menu trim above, so the documented
  one-liner was still installing `claude-mem`, Bun and the ten VoltAgent packs by
  default, and still numbering its menu 1–22.
- **Re-pinned the README's one-liner install URLs** from `f59faf1` to `7059ede`, per the
  rule in `CLAUDE.md`. The old pin predated everything below, so the documented one-liner
  was still handing people the installer with the broken `claude plugin update` call.

### Fixed

- **Every installed skill was frozen at whatever it looked like on the day it was first
  published.** `claude plugin update` decides whether to re-copy a plugin by comparing
  declared versions, and no skill in this marketplace had ever had its `version` bumped -
  all 25 sat at `1.0.0` from the day they were added. Nineteen of them had had real
  content changes since. The CLI answered every update with "already at the latest
  version (1.0.0)" and copied nothing, so anyone who ran the installer once was still
  running the original text of every skill, with no indication anything was wrong. The
  matching `claude plugin update` bug (below) had been masking it behind a warning that
  looked like the real explanation. The 18 skills whose files had changed since their
  version was set are now `1.1.0`; `crew` goes to `0.3.0` (its `0.2.0` was declared a
  commit before the Windows hook fix landed, and two further changes landed after that).
  The seven skills whose files genuinely had not changed are left at `1.0.0`.

### Added

- **`crew` 0.3.0 — a report-only project manager, a code graph, and a v1→v2
  upgrade path.** Three connected pieces, all off by default in what they can
  do to `.crew/config.json`:
  - **The PM.** `/crew:pm` (status with no argument; `onboard <role>` /
    `offboard <role>` with explicit yes/no confirmation before either touches
    config) and the `crew:pm` subagent, which holds no `Write` tool at all —
    it reads `crew_state.py`'s output, correlates the full metrics history or
    audits every codemap anchor when that would cost more context in the main
    session than the answer is worth, and returns a report plus one
    recommendation, under 200 words. It never applies anything; the session
    that invoked it acts, or not. A new `SessionStart` hook, `pm-brief.sh` /
    `.ps1`, runs the same state read at the start of every session and prints
    a prioritized brief — schema drift, a stale or missing code graph, a
    pending handoff, review health — before you type anything. Two related
    `context` settings, both default `false`: `autoWrapUp` changes what the
    `Stop` hook tells the session to do at the warning threshold (reach a
    stopping point and write the handoff, rather than just ask), and
    `autoResume` opens the next session already holding the last handoff as
    `additionalContext` — `initialUserMessage` was ruled out because it is
    confirmed only for non-interactive `-p` runs. Neither setting makes
    `/clear` itself automatic; no hook can trigger one.
  - **The code graph.** The `crew-graph` skill wraps the third-party
    `graphify` CLI (PyPI package `graphifyy`, double-y) to build and query a
    code graph at `graph.out` (default `graphify-out/graph.json`), gated on
    `--no-viz --code-only` for a keyless build. Freshness is read from
    `graphify`'s own `built_at_commit` field in
    `graph.json`, never a file timestamp — a `git pull` that predates the
    last build now correctly reports as stale instead of falsely current.
    Exporting into Obsidian needs an explicit `graph.obsidian.confirmed` set
    by hand; nothing sets it for you.
  - **The upgrade path.** `/crew:upgrade` brings a pre-schema config (no
    `schema` key, now `schema: 1`) forward to `schema: 2`: backs up
    `.crew/codemap/` before any other write, builds the graph if it's
    missing or stale, derives `Entry points` / `Owns data` / `Calls out to`
    per subsystem from the graph, and writes `.crew/codemap/UPGRADE.md`
    reporting contradictions and stale-on-purpose anchors rather than
    resolving either automatically. `## Does`, `## Landmines`, and
    `## Unverified` pass through byte-identical, always. An anchor only
    bumps on a section actually re-verified this run.

  `.crew/config.json` gains `schema`, a `pm` block (`enabled`, `mode`,
  `quietLines`, `maxLines`, `authority` — always `report-only`), and a
  `graph` block (`out`, `obsidian.confirmed`) — see `plugin/crew/README.md`
  §11. The plugin now registers 10 subagents, 18 slash commands, and 16
  bundled skills, up from 9/14/14.
- **Both `.sh` and `.ps1` are now wired for every hook event, not just
  `PreToolUse`.** `verify-gate.ps1`, `context-watch.ps1`, and
  `handoff-read.ps1` existed on disk but were never referenced in
  `hooks.json`; `handoff-write.ps1` and `notify.ps1` are new. 8 scripts × 2
  flavours = 16 hook entries across the same 5 events (including the
  `promote-gate.sh`/`.ps1` pair added below), registered unconditionally —
  one flavour is expected to fail per machine, and that is by design, not a
  regression. On Windows this closes the gap the 0.2.0 entry below flagged
  as a known, documented-not-fixed limitation; on Linux with no `pwsh`, the
  real hook-runner behaviour remains unverified rather than assumed fine.
- **The `repo-plugins` install item (21) now detects a global `find-skills`
  collision instead of only documenting it.** If
  `~/.claude/skills/find-skills` exists — from menu item 5, or a direct
  `npx skills add vercel-labs/skills --skill find-skills` — the step warns
  that two active copies of `find-skills` can both trigger on the same
  prompt and prints the manual `rm -rf` to remove the global one. Detection
  only; it never deletes anything itself.
- **Menu item 22, `graphify` — off by default, no new flag.** Installs the
  `graphify` CLI (`uv tool install graphifyy`) and registers it
  **per-repository**, never globally, with `graphify install --project`.
  Reuses `--select` / `-Select` like every other item. Installing it alone
  does nothing; `crew`'s `crew-graph` skill and `/crew:upgrade` are what call
  it.
- **`--dry-run` / `-DryRun`.** Settles the selection, prints it, and stops without
  installing anything - the quickest way to see what a set of flags actually resolves
  to, and what `scripts/_test/menu-groups.sh` uses so a test run cannot reach `apt-get`
  or `npm install -g`.
- **Every menu row that installs more than one thing now has a sub-picker.** Only the
  repo's own skills row did; the team, community, VoltAgent and repo-plugin rows were
  all-or-nothing, so wanting one of the three team plugins, or two of the ten VoltAgent
  packs (154 subagents), meant taking the lot or editing the script. All five rows are
  now marked `>` in the menu, open their own picker on the right arrow, and carry a live
  `N of M` count. New flags for the non-interactive path, matching `--skills`:
  `--team` / `-Team`, `--community` / `-Community`, `--voltagent` / `-VoltAgent`,
  `--plugins` / `-Plugins`, each taking names, numbers, `all` or `none`. A name matches
  the plugin key or the short label the picker shows, so `--voltagent infra` and
  `--voltagent voltagent-infra` are the same thing. Naming items inside a row also
  selects that row - which is what makes `--plugins crew` work at all, since that row is
  off by default - but never overrides a choice made at the menu. Only the marketplaces behind a ticked plugin are registered now, so
  `--team excalidraw-generator` adds one marketplace instead of three. The five catalogs
  are the single source for the menu label, the picker, the flag and the install loop,
  so a row cannot say "3 of 3" and then install something else - all five, including the
  skills, go through one `install_group` / `Install-Group`. That also fixed a smaller
  thing: a marketplace behind several ticked plugins is registered once rather than once
  per plugin, so the community row no longer re-clones `claude-settings` three times.

- **Content-drift detection in both install scripts.** A version bump fixes today's
  staleness; this stops it recurring silently. For an already-installed plugin the
  scripts compare the commit its marketplace is on against the commit Claude Code
  recorded at install time, and then ask git whether *that plugin's* files changed
  between the two - one commit anywhere in a marketplace moves `HEAD` for everything it
  publishes, so this also keeps unrelated commits off the slow path. If the files did
  change and `claude plugin update` still copies nothing, that is the unbumped-version
  case, and the scripts now say so plainly instead of reporting the plugin as current.
  New `--force-refresh` / `-ForceRefresh` reinstalls such a plugin (`claude plugin
  uninstall --keep-data` then install), which is the only way to make the CLI re-copy it.
  Anything the check cannot answer - no `git`, no history, a commit pruned by a
  force-push - falls back to the previous CLI path. Regression suite:
  `scripts/_test/drift-detection.sh` (15 assertions over 7 scenarios, asserting on the
  bytes on disk and not only on what the script printed; sabotage-tested by
  reintroducing both original bugs).
- **`scripts/check-marketplace.py` + a `Marketplace` CI workflow.** Fails when a skill's
  files have changed since its version was last set - the bug above, caught in the repo
  instead of on users' machines - and checks every registration rule in `CLAUDE.md`:
  directories registered in `marketplace.json` and vice versa, required fields, `source`
  paths, no nested `marketplace.json`, `SKILL.md` frontmatter names matching their
  directories, `plugin.json` versions agreeing with the marketplace, the `SKILL_KEYS` /
  `SkillCatalog` catalogs in both install scripts matching in content and order, and a
  table row in each of the three catalog docs. Sabotage-tested against eight
  reintroduced faults. It also holds the two install scripts to `CLAUDE.md`'s rule
  that they are a matched pair: same menu keys, same order, same default flags, and
  the same entries in every sub-picker group - a mismatch there makes `--select 3,7`
  mean different things on Windows and Linux and silently invalidates every doc that
  names an item by number.
- **`scripts/check-powershell.ps1` + `scripts/_test/menu-groups.sh`.** The PowerShell
  script is Windows-only end to end, so a call to a function that does not exist parses
  cleanly, is never reached on a CI runner, and only fails on the one platform that
  matters - which is how a mis-named picker call got through review here and would have
  killed every sub-picker on Windows. `check-powershell.ps1` resolves every `Verb-Noun`
  call against the script's own functions and the available cmdlets, with a short,
  justified allowlist for names a runtime `Import-Module` supplies. `menu-groups.sh`
  covers the sub-picker catalogs, the `--<group>` spec parser and the parent-implication
  rule (32 assertions). Both were sabotage-tested; the menu suite caught a weakness in
  its own first draft, which asserted on the message a flag printed rather than on the
  row actually being installed.

### Fixed

- **Install scripts — installing this repo's skills took minutes, and every re-run
  warned about all of them.** Two problems compounded. First, `claude plugin update`
  was called with a bare plugin name; the CLI only accepts `name@marketplace` and
  rejects a bare name with `Plugin "<name>" not found`, so *every* update in a re-run
  failed and printed `'claude plugin update <name>' failed - keeping the installed
  version.` — 25 spawned CLI processes that could not have succeeded, plus 25 warnings
  that read like real breakage. Second, both scripts reloaded the entire plugin list
  (`claude plugin list --json`) after every single install, doubling the CLI spawns on
  a fresh run. `install_plugin` / `Install-ClaudePlugin` now compare the marketplace
  clone's HEAD commit against the commit Claude Code recorded for the installed copy
  (`installed_plugins.json`) and skip the update spawn entirely when they match, pass
  the fully qualified `name@marketplace` when they do not, and add a freshly installed
  plugin to the in-memory cache instead of re-reading the whole list. Both SHA lookups
  are file reads, and either one being unavailable (no `git`, an unreadable state file,
  a plugin installed from a different marketplace) reports "cannot tell" and falls back
  to the old CLI path. Measured on the 25-skill item: re-run 38.5s -> 5.8s, fresh
  install 51s -> 32s, and no spurious warnings.

- **`crew` 0.2.0 — the Windows hooks never ran.** `guard.sh` and `verify-gate.sh` exited 0
  on MSYS/MINGW to "defer" to `.ps1` twins, and the twins were registered with a
  `shell: powershell` field that Claude Code does not read — `verify-gate.ps1`,
  `context-watch.ps1` and `handoff-read.ps1` were referenced by nothing at all, and
  `handoff-write.ps1` did not exist. The net effect on Windows was a command guard that
  blocked nothing and a `Stop` gate that ran nothing, which reads as "the gate passed"
  rather than "the gate never ran". Each hook is now registered once as bash and hands
  control to its twin from inside the script (`crew_win_dispatch` in
  `hooks/scripts/_common.sh`, `exec` so stdin passes through); `handoff-write.ps1` has
  been written. Verified by test: `terraform apply -auto-approve` now exits 2 on Windows.
- **`crew` — the verification map silently skipped every root-level file.** `fnmatch` and
  PowerShell's `-like` both let `*` span `/`, so a `**/*.tf` rule demanded a literal slash
  and never matched `main.tf` — exactly the file a Terraform module keeps at its root.
  With `"unmapped": "fail"` that meant editing `main.tf` failed the gate *and* skipped
  fmt, validate and tflint. Both gate implementations now also test the `**/`-stripped
  form.
- **`crew` — a failing `Stop` check could pin the session.** `verify-gate.sh` never read
  stdin, so it could not see `stop_hook_active` and blocked its own retry. Both
  implementations now honour it.
- **`crew` — `python3` was a hard dependency** of five hook scripts, and Git Bash ships
  without it. They now resolve `python3`, then `python`, then `py`; `guard.sh` prefers
  `jq`. With none available the hook says so on stderr instead of failing open silently.
- **`crew` — `terraform-docs .` in the gate edited the tree it was gating.** The writing
  form rewrites `README.md`, making it a changed file with no rule on the next run, which
  trips `unmapped: fail` on the gate's own edit. Every example now uses
  `--output-check`, which fails on a stale README and writes nothing.
- **`crew` — `$LASTEXITCODE` was read after `Invoke-Expression`** in `verify-gate.ps1`.
  A cmdlet leaves the previous value in place, so a stale 0 read as a pass. It is now
  reset before each command and `$?` is checked alongside it.
- **`crew` — dead agent frontmatter.** `effort: high` (2 files) and `memory: project`
  (6 files) are not part of the subagent schema and were silently ignored, so
  `qa-reviewer` was not running at the high effort its file claimed. Removed.

- **`crew` — the command guard was judging bash with PowerShell rules on Windows.**
  Found by the second QA pass, and introduced by the first: dispatch branched on the
  OS, so a `Bash` tool call on Windows was handed to `guard.ps1`. That inverted the
  secret rule in both directions - it blocked the correct capture form
  (`DB_PASS=$(...)`) and let `vault kv get ... > secret.txt` through. Dispatch now
  branches on `tool_name`, which is what actually determines the language a command is
  written in. The other five hooks judge no command, are reached through `bash`, and
  no longer branch at all.
- **`crew` — the secret rule treated persistence as an exemption.** A `>` redirect or a
  `| tee` marked a command safe, so writing a secret to disk passed while printing one
  blocked - and the block message recommended a form the guard itself rejected. Both
  now block; the only exemption is assigning to a variable.
- **`crew` — the production guard matched `prod` as a substring**, blocking
  `aws s3 ls s3://my-product-images`, `select * from products` and
  `reproducible-builds`. Now a whole-token match. A guard people route around is not a
  guard.
- **`crew` — an ERE portability bug made the capture allowlist match nothing.** `\(`
  is a literal paren in POSIX ERE but a group opener in some greps ("Unmatched ( or
  \("). Bracket expressions are used instead.
- **`crew` — the verify loop could eat its own command list.** `eval "$c"` shared stdin
  with the `while read` over the here-string, so a check that reads stdin silently
  consumed the remaining checks. Now `</dev/null`.
- **`crew` — `context-watch.sh` called `python3` directly in six places**, every one
  suppressed with `2>/dev/null`, so on a host with only `python` the context warning
  silently never fired. It resolves once through `crew_py` and says so on stderr if
  there is none.
- **`crew` — `claude-md-audit.sh` required bash 4.** `declare -A` is a parse error on
  macOS's stock bash 3.2. Rewritten without associative arrays or process substitution.
- **`crew` — `_verify/run-all.sh --read-only` used a denylist.** An unmarked case ran
  against production; only a self-declared `# writes: yes` skipped it. It is now an
  allowlist - a case runs under `--read-only` only if it declares `# readonly: yes`,
  and skips are reported.
- **`crew` — `git branch --show-current` needs git 2.22+**, and the `|| echo 'not a git
  repo'` fallback made an older git look like a missing repo. Uses `rev-parse
  --abbrev-ref HEAD`.

- **`crew` — `/crew:reference`, the API and feature reference.** The code map answers
  "where does this live"; nothing answered "what can this system do, and how do I call
  it". `docs/reference/api.md` enumerates every endpoint with its auth, body, returns,
  **side effects, error responses and idempotency** - the parts that are not guessable
  from the name - and `docs/reference/features.md` covers the headless capabilities
  nobody documents: scheduled jobs and what a missed run does, queue consumers, admin
  scripts, feature flags. Every entry is anchored to `file:line` so it can be
  re-verified, `--audit` reports drift in both directions without rewriting anything,
  and unconfirmed entries are left visible as `undocumented - needs a human`. Wired
  into `/crew:onboard` as the second of four artifacts and owned by `crew:docs-writer`.

- **`crew` — promotion is now enforced by a hook, not by instructions.**
  `promote-gate.sh` (`PreToolUse`) fires on any command matching a declared `deploy`
  entry and refuses it unless, for the sha at HEAD, every `requires` environment has an
  all-pass row in `.work/PROMOTIONS.md`, the `rollback` runbook exists with
  `last verified` inside 90 days, `requireHuman` has an approval marker, and the tree is
  clean. `verify-gate.sh` additionally refuses to end a turn after a deploy that wrote
  no promotion row. What a hook still cannot see is the middle - that smoke, regression
  and verify actually ran after the deploy - and `/crew:promote` now says so explicitly
  rather than implying coverage.
- **`crew` — `resolve-tools.sh`: platform detection that adapts instead of just
  reporting.** It reads `.crew/verify.json`, extracts the first word of every command,
  and reports each tool as native, WSL-only, or missing. The WSL-only case is the
  expensive one: a bare `terraform validate` on a machine where terraform lives only
  inside WSL fails with "command not found", and the gate reports that as a *failed
  check* rather than a missing tool. Resolve once at setup, write `wsl.exe -e terraform`
  into the map, never branch at runtime.
- **`crew` — two more committed suites.** `setup-walkthrough.sh` builds a mixed-stack
  scratch repo and runs every script phases 0-8 invoke (32 assertions);
  `validate-prompts.py` checks all 16 commands, 9 agents and 14 skills for frontmatter
  that parses, tools that exist, referenced agents and paths that resolve, read-only
  agents that hold no write tools, and subagent-spawning commands that are permitted to
  (91 checks). Both sabotage-tested. Neither proves the prompts produce good work -
  only a live session on a real ticket does that.

- **`crew` — a committed regression suite for the hooks**,
  `hooks/scripts/_test/run-tests.sh`. 38 cases: 20 the command guard must block, 14 it
  must allow, plus the verify gate's root-level glob matching and its
  `stop_hook_active` exit. `guard.sh` shipped two real regressions in two review
  passes and both were found by running it rather than reading it, so the suite is
  itself sabotage-tested — reintroducing the substring `prod` match, the `>`-as-
  exemption secret bug, or removing the stop-loop check each turns it red.

### Removed

- **`crew` — `skills/crew-setup/templates/smoke.sh`**, orphaned by the `_verify/`
  restructuring and diverging from the new `--env`-aware interface.
- **`crew` — four duplicate trees.** `docs/README.md` was byte-identical to `README.md`;
  `examples/` was byte-identical to `skills/crew-setup/` and referenced by nothing;
  `docs/crew-howto.pdf` was a third copy of the README in an undiffable format; and
  `plugin/crew/.claude-plugin/marketplace.json` was a stub naming a nonexistent source,
  which this repo's `CLAUDE.md` already forbids. ~380 KB, no functional change.

### Added

- **`crew` — `/crew:promote <development|qa|production>`, with `--dry-run` and
  `--status`.** Promotion runs as five separate gates — pre-deploy, deploy, smoke,
  regression, post-soak verify — stopping at the first failure. Smoke and regression are
  deliberately distinct: smoke passing tells you the deploy landed and says nothing about
  the module three directories over that just broke. The sequence is declared in an
  `environments` block in `.crew/verify.json` rather than remembered, production requires
  a rollback runbook verified inside 90 days and explicit human approval, and every
  promotion appends a row — failures included — to `.work/PROMOTIONS.md`, which is the
  only honest answer to "is production running what qa signed off on". New setup Phase 8
  builds the block by asking what actually deploys each environment and what actually
  proves it worked.
- **`crew` — `_verify/` as the canonical home for checks.** Setup looks for `_verify/`
  first (then `qa/`, `spec/`, `_test*/`) and adopts an existing convention rather than
  duplicating it; where none exists it creates `_verify/` from a template carrying
  `README.md`, `smoke.sh`, `run-all.sh` and `cases/`. The README is part of the
  deliverable: a layout table for what each check covers and a status table for when each
  last proved it could fail. `/crew:verify` cross-checks it against `.crew/verify.json`
  and reports drift both ways — a script with no rule never runs, and a rule naming a
  script the README omits is a check nobody knows about. `scripts/smoke.sh` is still
  honoured; the gate checks `_verify/smoke.sh` first and falls back.
- **`crew` — promotion discipline in the CLAUDE.md templates.** Both the generic and the
  Terraform template now carry the judgment half: the fixed `development -> qa ->
  production` order, the same sha through all three, smoke *and* regression *and*
  post-soak verification after every deploy, no production deploy without a verified
  rollback, and a failed gate restarting the whole sequence rather than resuming.

- **A `plugin/` tree, and the `crew` plugin in it — the repo's first entry that is a
  plugin rather than a skill.** `crew` 0.2.0 is a virtual dev team for multi-repo legacy
  work: 9 context-isolated subagents, 16 slash commands, 14 bundled skills, and 7 hooks
  across 5 events (`PreToolUse`, `Stop`, `PreCompact`, `SessionStart`, `Notification`).
  Beyond the safety gates it now carries a handoff note across a `/clear` or an
  auto-compact, and watches context use. Roles
  exist only where they buy an isolated context window, a restricted tool set, or
  genuinely independent eyes — project management, BA, and architecture are files and
  commands, not agents. Codex QA, Jira, Obsidian memory, and Teams/Telegram notifications
  are all optional. Registered in [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json)
  with `source` `./plugin/crew`, so `claude plugin install crew@useful-claude-add-ons`
  works the same way a skill install does.
- **`plugin/README.md` — the plugins counterpart to `skills/README.md`**, with the same
  five-column overview table, inlined into the root `README.md` between
  `<!-- BEGIN plugin/README.md -->` markers exactly as the skills table is. It leads with
  the distinction that actually matters: a skill is a document Claude reads, whereas a
  plugin can register subagents, slash commands, and **hooks** — and a hook runs whether
  or not Claude agrees with it.
- **`plugin/PLUGINS.md` — the per-plugin reference the catalog points at.** `skills/` gets
  away with one file because a skill is one `SKILL.md`; a plugin is a bundle, so the
  catalog row cannot carry the detail. This is where every command, agent, bundled skill,
  and hook is listed, with the hooks first, because they are the only part that runs
  without being asked. It also records what is *not* wired: only `PreToolUse` pairs a
  `.sh` with a `shell: powershell` twin, so `verify-gate.ps1`, `context-watch.ps1`, and
  `handoff-read.ps1` sit on disk unreferenced and the `Stop` gate never fires on a
  Windows box with no `bash` on `PATH`. Documented rather than fixed — it is a change to
  `crew`'s runtime behaviour, not to its packaging.
- **Menu item 21, `This repo's plugins`, in both bootstrap scripts — off by default.**
  Appended at the end of the menu so items 1–20 keep their numbers and no existing
  `--select 3,7` invocation changes meaning. New `PLUGIN_KEYS` / `PLUGIN_NAME` arrays in
  the `.sh` and `$script:PluginCatalog` in the `.ps1` mirror the skill catalogs. The item
  adds this repo's marketplace itself, so it stands alone whether or not item 3 ran, and
  finishes by printing the per-repository setup (`/crew:init`, `/crew:onboard`,
  `/crew:verify`). It is unticked by default *on purpose*: every other menu row installs
  something Claude may choose to use, whereas `crew`'s `PreToolUse` hook blocks
  `terraform apply`/`destroy`, destructive DDL, force push, hard reset, and any command
  that would print a secret, and its `Stop` hook fails a turn whose checks go red. Those
  are deterministic and start the moment the plugin is enabled, which is not something a
  bootstrap run should add without the box being ticked.
- **A plugin registration rule in `CLAUDE.md`**, alongside the existing skill rule: the
  same four places, plus two that only apply to plugins — a hook-bearing plugin defaults
  to OFF in the menu, and every hook script ships in both `.sh` and `.ps1` flavours,
  because a bash-only hook is silently inert on Windows and reads as "the gate passed"
  rather than "the gate never ran".

### Fixed

- **Section-comment numbering in both install scripts had drifted by one from item 14
  onward** — `obsidian-mcp` was inserted at position 14 without renumbering the comments
  below it, so the block installing menu item 20 was labelled `# --- 19. Obsidian`.
  Comment-only; no behaviour change. Verified by parsing `MENU_KEYS`/`MENU_DEFAULT` out
  of the `.sh` and `$script:Catalog` out of the `.ps1` and diffing them: 21 keys each,
  same order, same defaults.

### Changed

- **`plugin/crew/.claude-plugin/plugin.json` no longer ships placeholder metadata** —
  its author was `{ "name": "you" }`. It now carries the repo's owner, homepage, and
  repository. A stray `plugin/crew/.claude-plugin/marketplace.json` naming a marketplace
  `my-marketplace` owned by `you` was removed: the repo root's marketplace is the only
  one here, and a nested one makes the plugin directory look like a second marketplace.

- **`claude-memories-vault` and `claude-memories-canvas` skills — the conventions of the
  `claude-memories` Obsidian vault, written on the workstation during the 2026-08-19
  memory migration and only now given a canonical home.** `claude-memories-vault` covers
  the folder layout, the six required frontmatter fields, the `type`/`status` value sets
  the `HOME.md` Dataview queries filter on, how wikilinks resolve by *filename* on Windows
  (a `:` cannot appear in one, so the link must match the file and not the prose), the
  `vault-lock.ps1` write lock the nightly gardener respects, the single-writer rule on
  `inbox/pending-reflect.md`, and the decision rule for vault versus Claude Code
  auto-memory. `claude-memories-canvas` covers the `wiki/maps` node and edge schema
  actually in use, the colour and id styles, the column-and-group geometry, and the two
  rules that make a canvas findable at all: facts live in notes because a canvas-only fact
  is invisible to search, and every canvas is linked from its `Project - *.md` because
  canvases do not backlink.

  Both keep the concrete `C:\repos\claude-memories` path rather than a placeholder — the
  same choice `vault-automation/` already makes with its `-VaultPath` default — because
  these are the conventions of one real vault and a parameterised version has never been
  tested. Both name their siblings explicitly in the `description`: the generic
  `obsidian-canvas` for any other vault, and `obsidian-vault-server` for hosting one.
  `obsidian-canvas` gained a matching one-line pointer back.

- **`obsidian-vault-server` skill — a self-hosted Obsidian vault on a headless Ubuntu
  host.** The real Obsidian desktop app in a container (Sync has no headless client, so
  there is no other way), signed in to an obsidian.md account, with the
  `obsidian-local-rest-api` plugin's built-in MCP endpoint reached over an SSH tunnel —
  no separate MCP server process. Three references cover install, the Claude wiring, and
  getting a workstation's plugins onto the server. The safety rails are the point: the
  container's web GUI has a terminal with passwordless `sudo`, so the skill treats
  firewalling it and never overwriting the REST API key as non-negotiable rather than
  advisory.

- **`claude-obsidian-setup/` now installs the Obsidian community plugin set.** The setup
  scripts installed *Claude Code* plugins but never the Obsidian plugins a working vault
  needs. `obsidian-plugin-profile.json` pins 15 community plugins with their repos plus
  the 27 core plugins to enable, and `install-obsidian-plugins.ps1` / `.sh` install them
  from GitHub releases. Same house contract as the setup scripts: dry run by default,
  `--apply` / `-Apply` to write, PASS/FIX/FAIL against stable check ids, idempotent.
  Additive — `community-plugins.json` and `core-plugins.json` are unioned with whatever
  the vault already enables, in both the list and object-map shapes. Verified on both
  platforms: 15/15 at pinned versions, second run all PASS, pre-existing entries kept.

- **Menu item: `obsidian-mcp` — register the Obsidian vault server's MCP endpoint.** Off
  by default, on both scripts, with identical keys and order. Not a launched command: the
  endpoint is a plugin already running in the vault-server container, listening on the
  *server's* loopback, so the URL is a local port forwarded by SSH. The API key is
  per-deployment and cannot be baked in, so without `-ObsidianMcpKey` /
  `--obsidian-mcp-key` the item explains how to get one and skips rather than failing.
  `Add-McpServer` / `add_mcp_http_server` gained header support for the bearer token.

- **`vault-automation/` — self-feeding vault pipeline.** New component that automates
  the Obsidian memory loop end to end: Claude Code `SessionEnd`/`PreCompact` hooks
  queue every session into `inbox/pending-reflect.md`; a nightly `Claude Vault
  Gardener` scheduled task runs headless Claude to distill queued sessions into
  source-cited `wiki/concepts` pages and `wiki/daily` digests (with a provenance pass
  that promotes well-attested concepts); a `HOME.md` Dataview dashboard surfaces
  stale/unsourced concepts and the live queue; five community plugins installed
  file-level. Obsidian-Sync-aware: git is an optional layer (`-UseGit`/`-GitRemote`)
  and the gardener skips git operations on git-less vaults. Dry-run by default,
  idempotent, documented in `vault-automation/README.md` (incl. run-the-gardener-on-
  one-machine-only and cost/safety notes). Root README gained a "Vault automation"
  section with the run commands.

### Fixed

- **`install-prerequisites.sh` aborted on startup with `MENU_DEFAULT[$_i]: unbound
  variable`.** The `obsidian-mcp` menu item was added to `MENU_KEYS` but never to the two
  arrays that run parallel to it, leaving 20 keys against 19 defaults and 19 names. Under
  `set -u` the `MENU_STATE` initialiser walked off the end of `MENU_DEFAULT` and killed
  the script before it drew anything, so *no* item could be installed on Linux — not just
  the Obsidian one. `MENU_NAME` was short in the same way, and because the gap sat at
  index 13, every label from `obsidian-mcp` onward was displaying the *next* item's text:
  row 14 read "Supabase plugin", row 19 read "Strix", and row 20 had no label at all.
  Both arrays now carry all 20 entries, matching `$script:Catalog` in the `.ps1` key for
  key, name for name, and default for default.

  The menu-numbering fallout was documentation-only but wide: `README.md` and
  `INSTALLATION.md` both still described a 19-item menu, so every reference to items
  14–19 was off by one from the moment `obsidian-mcp` landed. Renumbered to 15–20, with
  the item itself now documented in the menu table, the "what each item installs" table,
  the MCP-servers walkthrough, and the switch table — `--obsidian-mcp-url` and
  `--obsidian-mcp-key` had never been listed there either.

- **The installers' skill catalogs had fallen two skills behind the marketplace.**
  `obsidian-canvas` and `obsidian-vault-server` were registered in
  `.claude-plugin/marketplace.json` and `skills/README.md` but never added to
  `SKILL_KEYS`/`SKILL_NAME` in `install-prerequisites.sh` or `$script:SkillCatalog` in
  the `.ps1`, so the per-skill picker offered 21 of the 23 that existed and neither could
  be selected by name. Both were also missing from the `<!-- BEGIN skills/README.md -->`
  mirror in the root `README.md`, which had silently stopped being a mirror. Both are in
  the catalogs and the mirror now, alongside the two new
  `claude-memories-*` skills, and the hard-coded counts in `README.md` and
  `INSTALLATION.md` — plus the stale "all nineteen" in both installer headers — now read
  25, matching the directory count, the marketplace manifest, and both catalogs.

- **`claude-obsidian-setup` — a Python below the 3.11 floor is now repaired rather than
  only reported.** Both scripts previously stopped with "install python3.11+ yourself" on
  any distro whose `python3` predates 3.11. That was over-broad: it treated the hardest
  case as if it were the only one. They now, in order, (1) use a newer versioned
  interpreter that is already installed, (2) install one — `python3.13`/`3.12`/`3.11` —
  from the repositories **already configured on the machine** and use it alongside the
  untouched system `python3`, or (3) stop with the concrete remedy. `update-alternatives`
  is never touched and no third-party repository is ever added, so the original objection
  still applies to the only case it was ever true of.

  Every downstream invocation now runs through a selected-interpreter variable rather than
  a hardcoded `python3`. Verified by putting a stub `python3` reporting 3.10 first on
  `PATH`: the script found the real `python3.12`, used it, and produced a complete 14-file
  vault with `doctor ok` and `lint 0 issues`.

- **`claude-obsidian-setup/setup-claude-obsidian.sh` creates the product checkout's parent
  explicitly.** `git clone` does create missing parents — this was verified, and the review
  finding that claimed otherwise was wrong — so nothing was broken. The `mkdir -p` removes
  the dependency on that behaviour and makes an unwritable root fail obviously.

### Added

- **Menu item 19 — Obsidian desktop + `claude-obsidian` and `obsidian-skills`
  plugins.** Off by default, on both scripts, with identical keys, order, and default
  flags. The app is not on npm, so it installs from a package manager: Chocolatey then
  winget on Windows, flatpak then snap on Linux — distro repositories generally do not
  carry it. Chocolatey needs elevation; without it the app is skipped with a warning and
  the two plugins still install. The item then registers
  `AgriciDaniel/claude-obsidian` (the vault engine: transactional writes, provenance
  ledgers, deterministic lint, the `/claude-obsidian:*` skills) and
  [`kepano/obsidian-skills`](https://github.com/kepano/obsidian-skills) (Obsidian's own
  upstream references for Obsidian Flavored Markdown, Bases, JSON Canvas, the Obsidian
  CLI, and Defuddle).

  The item deliberately stops there. Creating a vault writes to disk under a reviewed
  transaction, so it is a separate, explicitly previewed step rather than a side effect
  of a bootstrap run. `--obsidian-repo-root` / `-ObsidianRepoRoot` sets the root the item
  suggests for it (default `C:\repos` on Windows, `~/repos` on Linux).

- **`claude-obsidian-setup/` — vault setup for Windows (WSL) and Linux.** A matched pair
  of installers that bring both platforms to the same claude-obsidian standard, plus a
  README. Dry-run by default, idempotent, `PASS`/`FIX`/`FAIL` per check against stable
  check ids, non-zero exit on failure, and a closing `doctor` + `lint` against the new
  vault. Vault creation follows the product's own preview-then-apply contract: run the
  plan, read back its `approved_plan_sha256`, pass that exact hash to `--apply`.

  Everything hangs off one root — `C:\repos` / `~/repos` — so `-RepoRoot` /
  `--repo-root` relocates the vault and the product checkout together;
  `-VaultPath`/`--vault` and `-ProductRoot`/`--product` override either half.

  The Windows script exists mostly to repair four failures that are otherwise silent and
  hard to diagnose:

  1. **Native Windows cannot write to a vault at all.** Mutation safety is bound to POSIX
     directory descriptors and `fcntl.flock`; native Python has no `fcntl`, so the core
     refuses every write with `UNSUPPORTED_PLATFORM`. Reads and dry-runs work natively —
     writes are routed through WSL, which is why the vault is created from inside it.
  2. **`python3` resolves to a Microsoft Store stub.** Windows ships no `python3.exe`, so
     the name hits the App Execution Alias and prints an install advert instead of running
     Python — breaking the plugin's `SessionStart`/`Stop` hooks and every documented
     `python3 …` command. Fixed with a hard link `python3.exe → python.exe`.
  3. **`/mnt/c` mounts without `metadata`.** DrvFs then rejects `chmod` with `EPERM` and
     every apply dies with `CORRUPT_RUNTIME_STATE: cannot write confined bundle copy`.
     This cannot be fixed by remounting live; it needs an `[automount]` stanza in
     `/etc/wsl.conf` and a full `wsl --shutdown`. The existing file is backed up first.
  4. **Git identity does not cross the WSL boundary.** `checkpoint` runs inside WSL, where
     Windows' `git config --global` is invisible, so it fails `GIT_FAILED: Author identity
     unknown`. Fixed by setting identity repo-locally, which both environments read.

### Fixed

- **Both install scripts — Superpowers came from a second marketplace and could land
  disabled.** Item 4 registered `obra/superpowers-marketplace` unconditionally, but
  `install_plugin` / `Install-ClaudePlugin` detect plugins by *bare name*. On any machine
  that already had `superpowers@claude-plugins-official` — which items 6 and 7 register —
  the install was skipped, leaving an orphaned `superpowers-marketplace` registration and
  a second, disabled `superpowers@superpowers-marketplace` entry: exactly the duplicate
  [`skills/claude-code-tuneup`](skills/claude-code-tuneup/references/symptoms.md) tells you
  to clean up. Item 4 now takes Superpowers from `anthropics/claude-plugins-official`, the
  marketplace the scripts already register elsewhere, so there is one source for it.

  Superpowers for Claude Code is plugin-only by design and cannot be installed by copying
  `skills/` into `~/.claude/skills/`: its `SessionStart` hook resolves
  `${CLAUDE_PLUGIN_ROOT}`, which only exists for plugins, and that hook is what injects
  `using-superpowers` and makes the other skills fire. Six of the fourteen skills also
  cross-reference each other as `superpowers:<name>`, which unprefixed personal skills
  would break.

  Existing machines keep the stray `superpowers-marketplace` registration — the scripts
  deliberately do not remove marketplaces, since a bootstrap installer should not delete
  something a user may have added on purpose. Drop it with
  `claude plugin marketplace remove superpowers-marketplace`.

- **Both install scripts — an installed-but-disabled plugin is now switched back on.**
  Installing a plugin and having it load are different things: a plugin disabled in
  `settings.json` is installed, at the right scope, and completely inert. New
  `ensure_plugin_enabled` / `Enable-ClaudePlugin` run on the *already-installed* paths
  (update and already-current skip) and call `claude plugin enable --scope` when no enabled
  copy of the name exists. Best-effort by design — the plugin is installed either way, so a
  failure warns instead of failing the step.

  **Not** called after a fresh install: `claude plugin install` already enables what it
  installs. The first cut of this called it there too, which broke a brand-new machine —
  a just-installed plugin can still read as disabled in `claude plugin list --json`, so
  every plugin in the run got an enable attempt, and the CLI's benign "already enabled at
  user scope" reply was reported as a failed step. 18 of them on one run.

  Three separate defects behind that, all fixed:

  - `Enable-ClaudePlugin` used `2>$null` with no `try`/`catch`. Under
    `$ErrorActionPreference = 'Stop'` a native command's stderr line — or any non-zero exit
    when `$PSNativeCommandUseErrorActionPreference` is `$true` — becomes a *terminating*
    error, so `Invoke-Step` marked the step failed. The same hazard is already documented
    at the Claude Code update check. Both preference variables are now shadowed
    function-locally, and the whole call is wrapped, so this function cannot throw.
  - Success was judged from the CLI's message. It can't be: `claude plugin enable` reports
    "is already enabled at user scope" even for a plugin that does not exist. Both scripts
    now judge the outcome from `claude plugin list --json` instead.
  - The bash version was a silent no-op. `local spec="$1" name="${spec%%@*}"` doesn't work
    — bash declares every name in a `local` before expanding the values, so `$spec` read
    the empty new local and `name` was always empty. Assigned on its own line now, matching
    the existing style in `install_plugin`.

- **`install-prerequisites.ps1` — a disabled duplicate could mask an enabled plugin.**
  `Get-ClaudePlugins` keys its map on the bare name with last-write-wins, so with both
  `superpowers@claude-plugins-official` (enabled) and `superpowers@superpowers-marketplace`
  (disabled) installed, the disabled copy won on id sort order and the plugin was reported
  as disabled. An enabled entry now wins over a disabled one.

- **`install-prerequisites.sh` — `json_query` output is stripped of trailing `\r`.** Under
  Git Bash / WSL interop on Windows both `jq` and `python3` emit CRLF, leaving a stray
  carriage return on the last tab-separated field. Every caller compares that field exactly
  (`"$enabled" = "1"`, `"$repo" = "$id"`), so `marketplace_installed` could miss a
  marketplace matched by repo, and the new enablement check read every plugin as disabled.

### Added

- `skills/notify` — **two-way Telegram now works in both directions.** `--wait` only ever
  covered replies to a question Claude asked; a message the user sent on their own
  initiative was thrown away twice over. The dispatcher's `_on_message` dropped anything
  that matched no pending question, and direct mode fast-forwarded its `getUpdates`
  offset past everything already queued before it started listening — so a message typed
  while Claude was busy, or between questions, was silently discarded.

  New `scripts/inbox.py` is the store both halves share: `<spool>/inbox.jsonl` for
  inbound messages and `<spool>/state/offset.json` for the `getUpdates` offset. The
  offset has to be shared rather than per-process because Telegram answers a second
  concurrent `getUpdates` with `409 Conflict` — the daemon owns polling when it is up,
  the client polls only when it is not, and either way the next read resumes where the
  last one stopped.

  `notify.py --inbox` hands Claude what is waiting (exit 0 with messages, 5 without, so
  it works as a "did they say anything?" check in a loop), `--peek` leaves them
  unconsumed, `--wait` blocks for up to `--timeout` seconds, and `--job` filters to one
  topic. A read consumes what it returns, so no message is delivered twice. In topics
  mode the arriving thread is reversed through `topics.json` to attribute the message to
  the right job.

  Appends guard against a fused record: a write killed mid-line leaves no trailing
  newline, and appending onto it would produce one unparseable line and lose the *new*
  message as well as the broken one, so `append()` closes the dangling line first.

- `skills/claude-code-tuneup` — audits a Claude Code installation for what is making it
  slow or bloated and hands back a ranked cleanup plan. `scripts/cc_audit.py` (stdlib
  only, read-only) inventories every settings file in scope, loose skills in
  `~/.claude/skills/` against skills provided by installed plugins, `enabledPlugins`,
  hooks from both settings *and* every plugin's `hooks/hooks.json`, subagents, rules
  files, `CLAUDE.md` sizes, MCP servers, marketplaces, and the plugin cache.

  It catches the duplicate-install case in **both** plugin layouts — a plugin bundling
  `skills/<name>/SKILL.md`, and a plugin whose root *is* the skill, which is what this
  repo's own marketplace publishes. Missing the second layout is why a naive check finds
  none of this repo's skills duplicated. Duplicates are labelled
  `plugin@marketplace`, because the same plugin name published by two marketplaces is
  exactly the case worth catching, and a loose copy shadowing a *disabled* plugin is
  reported separately from one shadowing an enabled plugin — only the latter costs
  context.

- **Menu item 9 (claude-mem) now installs Bun.** claude-mem's hooks run its worker under
  Bun (`package.json` declares `engines.bun >= 1.0.0`) via `scripts/bun-runner.js`, which
  resolves the interpreter with `where`/`which bun` and only then falls back to
  `$HOME/.bun/bin/bun`. Neither install script ever installed it and the plugin's own
  hooks cannot bootstrap it, so on a fresh machine every claude-mem hook failed with
  "Bun not found". Windows uses `choco install bun` when Chocolatey is present *and* the
  run is elevated — the shim lands a real `bun.exe` on `PATH`, which is what
  `bun-runner.js` looks for first — and falls back to bun's per-user installer
  otherwise, since that needs no Administrator rights and writes the documented
  fallback path. Linux prefers `npm install -g bun` (keeping bun on the same `PATH` as
  node) and falls back to `bun.sh/install`; no distro ships a bun package, so there is
  no `as_root` path. Both halves detect first: an existing bun, however it was
  installed, is left alone.

### Removed

- **Perplexity MCP server** — dropped from both install scripts. It was menu item 13
  (off by default), the only row that needed an API key, so the whole up-front key
  prompt goes with it: `read_mcp_api_key` / `read_mcp_api_keys` and `PERPLEXITY_KEY`
  in the `.sh`, `Read-McpApiKey` / `Read-McpApiKeys` and `$script:ApiKeys` in the
  `.ps1`. Every remaining row now installs without asking for anything mid-menu.

  **Menu numbers below it shift by one on both platforms**: MCP servers are 11–13,
  Supabase 14, Context7 15, Playwright CLI 16, SkillUI 17, Strix 18. Scripted runs
  that pass positions (`--select 15,19`) need updating; the stable keys
  (`--select supabase,strix`) were unaffected and remain the better habit. The
  `perplexity-mcp` key itself is gone, so a run that names it now selects nothing for
  that token. An already-registered `perplexity` server is left alone — remove it by
  hand with `claude mcp remove perplexity` if you want it gone.

- `skills/ppt-master` — a vendored copy of the upstream `hugohe3/ppt-master` plugin
  (12,230 files, 88 MB) that was never registered in `marketplace.json`, either
  README, or either install script's skill catalog, so nothing here ever offered it.
  The installer already installs the same plugin from its own marketplace as part of
  menu item 6 (Community marketplaces + plugins), so removing the copy changes nothing
  for anyone running the bootstrap — it just stops the repo carrying 88 MB of upstream
  code it would have to re-sync by hand. This also clears the Pylint CI failure: 845
  of the 855 findings were in that tree.

### Added

- `skills/notify` — **a body over Telegram's 4096-character limit now splits across
  several messages** instead of failing the send. `tg.split_body()` breaks on a
  newline where it can, then a hard cut, and it splits the *raw* text before
  HTML-escaping so a break can never land inside an `&amp;` entity and invalidate
  the message. Whitespace is preserved exactly — rejoining the parts reproduces the
  input byte for byte. Parts are headed `(1/3)`, `(2/3)`, …

  The budget is computed against the **assembled** message, not the body chunk
  alone. Each part carries a `<b>subject (cont.) (2/3)</b>` header, the subject is
  caller-supplied, and escaping can grow it 5×, so a fixed reserve was not enough —
  a 300-character subject produced a 4,346-character message that Telegram would
  have rejected. The header cost is now measured per call and a pathological subject
  is truncated rather than eating the whole budget.

  Buttons go on the last part only, and `send_message()` returns that last message,
  so `notifyd`'s `message_id → req_id` correlation still resolves a button tap or a
  reply to the final part. Replying to an *earlier* part is not indexed and falls
  back to the newest open question in that topic. Parts are spaced one second apart
  to stay under Telegram's per-chat rate limit; `--dry-run` reports the part count.

### Fixed

- `skills/notify/scripts/notify.py` — stdout and stderr are reconfigured to UTF-8 with
  `errors="replace"` at startup. On a Windows console (cp1252) printing a body that
  contained any non-ASCII character — an em dash, an emoji, non-Latin text — raised
  `UnicodeEncodeError` and killed the run, which made `--dry-run` unusable for exactly
  the messages worth checking before sending.

- `skills/notify/scripts/*.py` — the four config reads now pass `encoding="utf-8"` to
  `Path.read_text()`. Without it Python picks the locale encoding, which is cp1252 on
  Windows, and a UTF-8 `config.json` then fails in one of two ways depending on the
  character. Most non-ASCII text decodes silently wrong: an em dash (`E2 80 94`)
  becomes `â€”` in the message that gets sent. Text whose UTF-8 bytes include one of
  the five undefined cp1252 positions (`81 8D 8F 90 9D`) raises `UnicodeDecodeError`
  and takes the run down — Japanese `あ` is `E3 81 82`, so a config with CJK in it
  crashes outright. Both are Windows-only. Also split the comma-form imports and
  wrapped two over-length lines, so `pylint $(git ls-files '*.py')` is back to
  10.00/10.

### Added

- `skills/notify` — a new skill (1.0.0) that pings you out of band about a session or
  job: a two-way Telegram bot (a `question` event blocks until you reply from your
  phone, and a `notifyd` dispatcher gives each concurrent job its own forum topic) or
  email over SMTP or an M365/Gmail MCP connector. Registered in `marketplace.json`,
  both READMEs, `INSTALLATION.md`, and both install scripts, taking this repo's
  catalog from 19 skills to 20.

- `scripts/install-prerequisites.ps1` / `.sh` — **the `notify` skill asks about setup.**
  It is the only skill here that needs anything on the machine, so ticking it prints
  its prerequisites alongside the menu (Python 3.8+, a `@BotFather` token, a `chat_id`,
  `TELEGRAM_BOT_TOKEN` exported, a config file, polling mode with no webhook) and then
  asks whether to scaffold `~/.config/notify/config.json`. Answering yes checks for
  Python and writes a starter config; it never overwrites an existing one and never
  writes the bot token anywhere. `--notify-setup` / `-NotifySetup` answers yes without
  asking; `--all` / `--non-interactive` prints the prerequisites and skips the
  scaffold. Because `notify` is a sub-picker entry rather than a top-level menu key,
  the gate reads the skill catalog (`skill_selected` / `Test-SkillSelected`) instead of
  `is_selected` / `Test-Selected`, which would never match.

- `CLAUDE.md` — repo-level instructions for Claude Code. Two documentation rules are
  stated as requirements rather than suggestions: an edit to either install script
  must update `README.md` (menu table, "what each item installs" table, switch table,
  and any prose that names an item by number) in the same change, and a new directory
  under `skills/` is not finished until it is registered in all four places —
  `marketplace.json`, `skills/README.md`, `README.md`, and both install scripts.

- `scripts/install-prerequisites.ps1` / `.sh` — **the Claude Code CLI row now checks
  for an update** when `claude` is already installed, instead of reporting the version
  and moving on. It compares the local version against the npm registry and runs
  `npm install -g @anthropic-ai/claude-code@latest` only when they differ. The version
  is read from the last line of `claude --version` (which prints
  `2.1.226 (Claude Code)`, and can be preceded by a wrapper's banner).
  `-NoUpdate` / `--no-update` reports the installed version and skips the check.

- `scripts/install-prerequisites.ps1` / `.sh` — **five new opt-in menu items**:
  - **Supabase** (15) — `supabase@claude-plugins-official`, through the same
    detect-then-install helper as every other plugin.
  - **Context7** (16) — `npx -y ctx7@latest setup`. The wizard is interactive, so bash
    hands it the terminal explicitly (under `curl | bash`, fd 0 is still the script);
    with no terminal at all both scripts print the command rather than hang.
  - **Playwright CLI** (17) — `npm install -g @playwright/cli@latest`, detected by
    whether `playwright-cli` already resolves on `PATH`.
  - **SkillUI** (18) — `skillui`, plus `playwright` and its Chromium build. Playwright
    is installed **globally**; upstream's `npm install playwright` would leave a
    `node_modules` tree in whatever directory the script was run from. Both Playwright
    steps warn rather than fail the item. A quick start is printed afterwards; you're
    asked up front, and `--skillui-guide` / `-SkillUIGuide` answers yes without asking.
  - **Strix** (19) — upstream's own installer, `curl -sSL https://strix.ai/install |
    bash`. Installing it is not enough to run it, so the next steps (Docker running,
    `STRIX_LLM`, `LLM_API_KEY`) print on every run, including one that skipped the
    install. Windows has no POSIX shell, so the script runs the installer through WSL,
    falls back to Git Bash, and warns with the manual command if neither exists.

- `scripts/install-prerequisites.ps1` / `.sh` — the install menu is now a **cursor
  picker**: ↑/↓ to move, Space to tick, Enter to start, `A`/`N`/`D` for all/none/
  defaults, `Q` or Escape to cancel. Rows scroll inside a viewport when the window
  is short, and every printed line is clipped to the window width, because a
  wrapped line breaks the redraw and smears the menu over whatever was above it.
  The numbered prompt is still there as the fallback and is chosen automatically
  when raw key input is not possible — no terminal, no `stty`, `TERM=dumb`,
  PowerShell ISE, a redirected console, or a window under ten lines. Bash restores
  the saved `stty` state and the cursor from an `EXIT`/`INT` trap so Ctrl-C in the
  menu cannot leave the user's shell with echo off.

- `scripts/install-prerequisites.ps1` / `.sh` — **individual skills can be
  installed instead of all nineteen**. Pressing → on the repo's row opens a second
  picker listing every skill in this repo; `-Skills 'cloudflare,drata'` /
  `--skills cloudflare,drata` does the same non-interactively and also accepts
  `all`, `none`, and positions (`1,4-6`). It composes with `-All` /
  `-NonInteractive`, so CI can install everything except the skills, or only the
  skills. The catalog (`SKILL_KEYS` in bash, `$script:SkillCatalog` in PowerShell)
  is now the single source of both the picker rows and the install loop, replacing
  the duplicated `own_plugins` / `$ownPlugins` arrays. The repo's menu row shows a
  live count (`+ 3 of 19 skills`) rather than a hardcoded nineteen.

- `skills/infra-work-ticketing` — `ticketctl.py` gained **`update`** and
  **`close`**, so the API fallback covers all four write verbs rather than just
  `create` and `note`. `update` sets title, status, priority, category,
  subcategory, group, technician, urgency, impact, type and (on SDP) the
  resolution and an `--update-reason` for the audit trail; `close` takes a closure
  comment, `--closure-code`, and `--requester-ack`. On Jira, `close` looks the
  transition up by name from the issue's own transition list rather than
  hardcoding an id, and `--category` maps to a component — the nearest equivalent
  Jira has. Both go through the same build/execute split as the existing verbs, so
  `--dry-run` covers them.

  Two limits are documented rather than papered over. **Closing through
  `ticketctl.py` is not equivalent to `sdp_close`**: SDP Cloud v3 has no close
  sub-resource, so the fallback PUTs a terminal status plus `closure_info` to the
  edit endpoint and a desk with mandatory closure rules can reject it. And
  **nothing can create or rename a category** — the v3 API documents no endpoint
  for the taxonomy and the connector's metadata tool is read-only, so that stays
  an SDP admin-UI job. Setting the category on a ticket works from either path.

- `skills/infra-work-ticketing` — an `mcp` block in the config file records how
  ticket writes are routed: connector name, endpoint, tool prefix, whether to
  prefer MCP, and which `ticketctl.py` provider takes over when it refuses.
  `ticketctl.py doctor` prints the resolved routing and probes the connector's
  `/health` (5-second timeout, `--no-mcp-probe` to skip). Routing metadata only —
  the connector authenticates per person through Claude Code, so no credential
  belongs in the block. `INFRA_TICKET_PREFER_MCP` and `INFRA_TICKET_MCP_ENDPOINT`
  override it per session.

### Removed

- `scripts/install-prerequisites.ps1` / `.sh` — **six menu items**: the Firecrawl,
  Chrome DevTools, and Glyphs MCP servers, the OmniRoute gateway, Headroom, and GSD.
  The helpers that existed only for them went with them: `tcp_port_open` and
  `add_mcp_http_server` in bash, `Test-TcpPort`, `Get-PythonLauncher`,
  `Add-UserScriptsToPath` and `Get-PipxPythonArgs` in PowerShell, along with the
  `FIRECRAWL_API_KEY` prompt, the OmniRoute guided-setup question, and the Headroom
  mode question. The `-HeadroomMode` / `--headroom-mode` switch is gone.

  The menu is 19 items rather than 20, and items 1–10 are the default set (was 1–11).
  Item numbers below 10 are unchanged; everything above shifted. Scripted runs should
  use the stable keys (`--select supabase,strix`) rather than positions.

### Changed

- `scripts/install-prerequisites.ps1` / `.sh` — the per-skill picker's descriptions are
  fuller: each of the nineteen rows now names what the skill actually does rather than
  restating its title (`cloudflare - Cloudflare v4: DNS, WAF, cache, Workers, Zero
  Trust`). Text is sourced from the skills table in `README.md`. The rows are written
  for a window of about 95 columns; narrower consoles clip them with an ellipsis, as
  they already did for the longest of the old labels.

### Fixed

- `skills/infra-work-ticketing` — a `ticketctl.py` write that failed while
  *planning* rather than sending was not queued, so the text was lost. Resolving
  `#40219` to an internal id is itself an API call, which means a down service desk
  failed in exactly that window. Planning is now inside the guarded region for
  `note`, `update` and `close`. `--dry-run` still never queues.

- `scripts/install-prerequisites.ps1` / `.sh` — a picker that failed *after* the
  capability gate passed did not fall back. In bash the failure return was ignored,
  leaving an empty selection that printed `Nothing to do.` and exited 0 — the same
  output as a deliberate cancel. In PowerShell, `$ErrorActionPreference = 'Stop'`
  meant a `SetCursorPosition` throw (a window shrunk between frames) killed the
  whole installer. Both now drop through to the numbered menu and say why. The
  capability gate only ever proved the picker could *start*.

- `scripts/install-prerequisites.sh` — the `/dev/tty` probe printed
  `No such device or address` to stderr on hosts without a controlling terminal.
  The redirection is now grouped so `2>/dev/null` actually covers it.

- `scripts/install-prerequisites.ps1` — hiding the cursor threw
  `"The handle is invalid"` on hosts that don't implement `Console.CursorVisible`,
  which would have taken the whole menu down with it. It is cosmetic, so it is now
  best-effort.

- `skills/visio-diagrams` — creates, edits, and verifies Microsoft Visio `.vsdx`
  files. Two paths from one spec: a stdlib-only writer (`vsdx_writer.py` +
  `diagram_from_spec.py`) that generates a native `.vsdx` plus an SVG preview
  with no Visio install and no third-party packages, so it runs in CI and on
  air-gapped boxes; and PowerShell COM automation (`New-VisioDiagram.ps1`) for
  real stencil masters, themes, containers, and swimlanes. Also covers reading
  and retitling an existing `.vsdx` via the `vsdx` package (the template + data
  pattern that preserves corporate stencils). Leads by challenging whether Visio
  is the right output at all, and refuses to call a file verified when
  `verify_vsdx.py` could only check OPC structure. Two reference files (`.vsdx`
  OOXML format and symptom → cause table, COM automation). Registered in
  `.claude-plugin/marketplace.json` and both install scripts — 19 skills total.

- `skills/claude-code-defaults` — configures how Claude Code itself behaves by
  default. Separates instructions (`CLAUDE.md`, `.claude/rules/`, loaded into
  context) from enforcement (`settings.json`, permission `allow`/`ask`/`deny`,
  hooks, applied by the client), and routes a request to the right file at the
  right scope — user, project, local, or managed. Inventories existing config
  and merges rather than clobbering, backs up before editing, validates the JSON,
  and verifies via `/status`, `/context`, and `/doctor`. Four reference files
  (permissions, CLAUDE.md, settings keys, copy-paste templates for solo/shared/
  locked-down/fleet). Refuses to hand out `bypassPermissions` as a default.
  Registered in `.claude-plugin/marketplace.json` and both install scripts —
  18 skills total.

- `scripts/install-prerequisites.ps1` / `.sh` — the VoltAgent
  [`awesome-claude-code-subagents`](https://github.com/VoltAgent/awesome-claude-code-subagents)
  collection is now installed as plugins from its own marketplace
  (`voltagent-subagents`), all ten category plugins: `voltagent-core-dev`,
  `-lang`, `-infra`, `-qa-sec`, `-data-ai`, `-dev-exp`, `-domains`, `-biz`,
  `-meta`, `-research`.

- `scripts/install-prerequisites.ps1` — `-InstallScope` (aliased to the old
  `-PluginHubScope`) now applies `--scope` to *every* marketplace and plugin
  install, not just the community set. Same for `--scope` on the Linux script.

- `skills/terraform-docs-readme` — regenerates a Terraform module's `README.md`
  with `terraform-docs`. Covers first-time setup (`.terraform-docs.yml`, the
  `main.tf` narrative header block, `footer.md`, the `BEGIN_TF_DOCS`/`END_TF_DOCS`
  injection markers) as well as re-runs after variables, outputs, or resources
  change, and diagnoses the usual failures — missing markers, a header that
  isn't picked up, a footer that isn't rendered, a version older than 0.16.
  Ships a stdlib-only, read-only preflight script and copy-ready assets.
  Registered in `.claude-plugin/marketplace.json` and in both install scripts.

- `skills/cisco-meraki` — Cisco Meraki Dashboard API v1 skill for a single
  organization, covering MX/MS/MR. Reads inventory, device status, the network
  event log, the org configuration change log, MX security/IDS events, and Air
  Marshal; runs live diagnostics (ping, cable test, throughput, ARP/MAC table,
  wake-on-LAN); and makes configuration changes behind a snapshot → diff →
  confirm gate with single-command rollback. Bulk changes route through staged
  Action Batches so Meraki validates the payload server-side before commit.
  Stdlib-only Python, no pip install. Includes the repo's first unit test suite
  (`python -m unittest discover -s skills/cisco-meraki/tests -p "test_*.py"`).

### Changed

- `scripts/install-prerequisites.ps1` / `.sh` — **all marketplace and plugin
  installs now use the native `claude plugin marketplace add` and `claude plugin
  install` commands.** The `npx -y claudepluginhub <repo>` wrapper is gone, along
  with the `Invoke-PluginHub` / `pluginhub` helpers that called it. The wrapper
  registered each repo as a *local directory* marketplace under a generated name
  (`cpd-<repo>-user`) that the scripts' own detection could not match, so those
  plugins were reinstalled on every run, and it was a recurring source of Windows
  failures. Marketplace names are now taken from each repo's own
  `.claude-plugin/marketplace.json` — notably `fcakyon/claude-codex-settings`
  publishes itself as `claude-settings`, which the old name-or-repo detection
  never matched either.
- `scripts/install-prerequisites.ps1` / `.sh` — claude-mem installs through its
  marketplace (`claude plugin marketplace add thedotmack/claude-mem` +
  `claude plugin install claude-mem@thedotmack`) instead of
  `npx claude-mem install`. Upstream documents both paths. `find-skills` and GSD
  still use `npx`: neither publishes a Claude Code marketplace.
- `MARKETPLACE.md` / `INSTALLATION.md` — bootstrap command lists rewritten to
  match, with the repo-name-vs-marketplace-name trap called out explicitly, and
  a troubleshooting row for leftover `cpd-*-user` marketplaces.

### Removed

- `scripts/install-prerequisites.ps1` — the `Resolve-GitRoot` and
  `Register-GitBash` helpers, plus the `C:\repos\awesome-claude-code-subagents`
  clone and its `bash install-agents.sh` invocation. Its Linux counterpart
  (`~/repos/...` clone) is gone too. That step needed Git Bash on Windows and so
  failed outright on a non-elevated run, where Chocolatey — and therefore `git` —
  had already been skipped. An existing checkout from an earlier run is now
  unused and safe to delete.
- `aiskillstore/marketplace` and its `xlsx` / `mcp-integration` entries. That
  repo is the Skill Store content repo, not a Claude Code marketplace (no
  `.claude-plugin/marketplace.json`), so there is no native
  `claude plugin install` for it. `anthropic-office-skills@claude-settings`
  replaces `xlsx`; either skill can still be installed by hand with
  `npx skillstore add aiskillstore/<skill>`.

- `scripts/install-prerequisites.ps1` / `.sh` — the `find-skills`
  (`vercel-labs/skills`) step is now prompted rather than unconditional, and is
  detected before it runs. It installs as a user-level skill, not a Claude Code
  plugin, so detection is a filesystem check on
  `${CLAUDE_CONFIG_DIR:-~/.claude}/skills/find-skills/SKILL.md`. Already
  installed: the prompt offers a re-install for updates; `-NoUpdate` /
  `--no-update` skips it entirely. The step now also verifies the skill actually
  landed on disk instead of trusting the installer's exit code.

### Fixed

- `skills/terraform-docs-readme` arrived double-nested
  (`skills/<name>/<name>/SKILL.md`) with a leftover `terraform-docs.zip` and a
  zip-oriented `INSTALL.md` — the same layout problem fixed for `aws-opensearch`
  and `intune-graph` in the 2026-07-28 baseline. Flattened to the standard
  `skills/<name>/SKILL.md` layout; the duplicate tree, the archive, and the
  now-inaccurate `INSTALL.md` were removed (installation for this repo's skills
  is covered by `INSTALLATION.md` and `MARKETPLACE.md`).
- `INSTALLATION.md`'s "What the own-marketplace step installs" list was stale at
  10 skills and missing `cisco-meraki`, `infra-work-ticketing`, `repo-docs`,
  `shipstation`, `web-testing-playwright`, and `work-log-reporter`. Now lists all
  17, matching `marketplace.json`, `skills/`, and both install scripts.

## [2026-07-28]

### Added

- DevOps scaffolding for distributing skills to the team: `Skill-Authoring-Standard.md`, `Skill-Pipeline.md`, `SECURITY.md`, `INSTALLATION.md`, `MARKETPLACE.md`, this `CHANGELOG.md`.
- `.claude-plugin/marketplace.json` — registers this repo as a Claude Code plugin marketplace with one plugin entry per skill.
- `scripts/install-prerequisites.ps1` and `scripts/install-prerequisites.sh` — bootstrap Git, AWS CLI (Windows) / native package manager (Linux), Node.js, Python, the Claude Code CLI itself (with `PATH` export), and the team's standard marketplaces/plugins (Superpowers, find-skills, GSD, claude-mem, frontend-design, excalidraw-generator).
- Populated `skills/README.md` with a skill overview table (name, category, purpose, invocation mode) for all 10 skills.
- Root `README.md` now embeds the skills overview and links every new doc.
- Populated root `.gitignore`.

### Fixed

- `aws-opensearch` and `intune-graph` skill directories were double-nested (`skills/<name>/<name>/SKILL.md`), breaking the standard `skills/<name>/SKILL.md` discovery convention and marketplace `source` paths. Flattened to the standard layout.

### Skills present as of this baseline

`aws-opensearch`, `bitbucket`, `checkpoint-email`, `cloudflare`, `drata`, `i-have-adhd`, `intune-graph`, `mermaid-svg-bitbucket`, `sophos-central`, `wazuh-onprem` — see [`skills/README.md`](skills/README.md) for details on each.
