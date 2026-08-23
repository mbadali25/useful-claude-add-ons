# crew

A small virtual dev team for Claude Code: four to six agents that buy context isolation, tool restriction, or independent eyes — and nothing that merely renames Claude.

Built for the awkward case: several repositories, mixed stacks, legacy code, and almost no test coverage.

---

## Contents

1. [What this is, and what it is not](#1-what-this-is-and-what-it-is-not)
2. [Where it runs](#2-where-it-runs)
3. [Requirements and platforms](#3-requirements-and-platforms)
4. [Install](#4-install)
5. [Set up your first repository](#5-set-up-your-first-repository)
6. [Build the smoke harness](#6-build-the-smoke-harness-do-not-skip-this)
7. [Teach it the codebase](#7-teach-it-the-codebase)
7b. [The API and feature reference](#7b-the-api-and-feature-reference)
8. [Verification, secrets, and browser tests](#8-verification-secrets-and-browser-tests)
9. [Research and gap analysis](#9-research-and-gap-analysis)
10. [The daily loop](#10-the-daily-loop)
11. [Configuration reference](#11-configuration-reference)
12. [Optional: Codex as reviewer](#12-optional-codex-as-reviewer-gemini-as-design-partner)
13. [Optional: Jira via MCP](#13-optional-jira-via-mcp)
14. [Optional: Obsidian for memory](#14-optional-obsidian-for-memory)
15. [Optional: Teams and Telegram notifications](#15-optional-teams-and-telegram-notifications)
16. [Context handoff](#16-context-handoff)
17. [Linting, Terraform docs, and repo conventions](#17-linting-terraform-docs-and-repo-conventions)
18. [Document maintenance](#18-document-maintenance)
19. [Runbooks](#19-runbooks)
20. [Diagrams](#20-diagrams)
21. [AWS and Azure MCP](#21-aws-and-azure-mcp)
22. [Growing the crew](#22-growing-the-crew)
23. [Promotion: development to qa to production](#23-promotion-development-to-qa-to-production)
24. [Command and agent reference](#24-command-and-agent-reference)
25. [Troubleshooting](#25-troubleshooting)

---

## 1. What this is, and what it is not

**It is** a workflow: file-backed tickets, one implementation session, an independent reviewer, and deterministic gates that block on failure rather than offering an opinion.

**It is not** an org chart. A persona in a prompt adds no capability. A role earns its place only if it buys one of three things:

| Benefit | Which roles provide it |
|---|---|
| An isolated context window | `explorer`, `security`, `qa-reviewer` |
| A restricted tool set | `explorer` and `security` are read-only |
| Genuinely independent eyes | Codex, or `qa-reviewer` in its own context |

Everything else — project management, business analysis, architecture, documentation, training — is a file, a command, or you. Those are not agents because there is nothing for an agent to isolate.

The single most important design constraint: **every custom subagent loads your entire `CLAUDE.md` hierarchy at startup.** A 4,000-token `CLAUDE.md` across eight delegations is 32,000 tokens of overhead before any work happens. Keep `CLAUDE.md` to a routing table of 30–40 lines. Detail belongs in commands and skills, which load only when used.

---

## 2. Where it runs

**Claude Code.** That is the target, and it is the only surface where the whole thing works.

Plugins share a file format across Anthropic's surfaces, but installation does not sync between them. Installing a plugin from the Customize menu on claude.ai does not make it available in your terminal, and `/plugin install` in Claude Code does not make it appear on the web.

That distinction matters more than usual here. In Claude chat, hooks and sub-agents from a plugin are greyed out — bundled skills work in chat, Claude Desktop's Chat tab, and Cowork, but hooks and sub-agents run only in Cowork. Since `crew` is mostly hooks, sub-agents, and slash commands operating on a local git repository, installing it on the web would give you three skills' worth of written guidance and nothing that executes.

If you want it on both surfaces, push the plugin to a GitHub repository and add that marketplace in each place separately. Two installs, one source of truth.

---

## 3. Requirements and platforms

- Claude Code, reasonably current
- `git`, and either `bash` or PowerShell
- A repository you can commit to
- Optional: the `codex` CLI on your `PATH`
- Optional: an Atlassian Cloud account for Jira
- Optional: Obsidian, or any folder of markdown files

### Platform detection

Setup runs `platform.sh` (or `platform.ps1` on native Windows) before anything
else, and records the result in `.crew/config.json`. It distinguishes native
Linux, macOS, WSL1, WSL2, Git Bash on Windows, and native Windows, and reports
which toolchains are actually present.

Every hook is registered once, as bash, so `bash` must be on `PATH` — Git Bash
satisfies that. Only the `PreToolUse` guards branch, and they branch on which
**tool** the command came from rather than on the OS, so a `Bash` call is judged
by bash rules even on Windows. See
[How the Windows half works](#how-the-windows-half-works).

**If WSL is available, run Claude Code inside it.** One shell, one code path, and
the harness matches CI. Native Windows works but doubles the surface area for no
benefit unless the application genuinely requires it.

### The three WSL problems worth knowing before they cost you an hour

**Repo location decides your test runtime.** A clone under `/mnt/c/...` sits on
the Windows filesystem behind a translation layer, and file operations run
roughly an order of magnitude slower. A ninety-second smoke suite can take ten
minutes purely from where the files live. Setup flags this and recommends
re-cloning to `~/code/...` — usually the largest single speed win available, at
the cost of one `git clone`. You keep your Windows editor either way via `\\wsl$\`.

**`localhost` is not the Windows host under WSL2.** The Linux VM has its own
network namespace, so SQL Server, IIS, or a Docker Desktop container bound to the
Windows side is not reachable at `localhost`. Detection reports the gateway IP;
put it in `.env.smoke` as a variable, because it changes when the host reboots.
WSL1 shares the host stack and does not have this problem.

**CRLF breaks shell scripts with a misleading error.** A `smoke.sh` checked out
with Windows line endings fails as `bad interpreter: /usr/bin/env bash^M`, which
reads like a missing interpreter. Detection reports it; setup offers
`.gitattributes` with `* text=auto eol=lf` plus `git add --renormalize .` before
anyone writes a script.

Full detail, including a bash-to-PowerShell command translation table, is in
`skills/crew-setup/platform.md`.

---

### Resolving the toolchain

Detection tells you what you are on. It does not tell you whether the commands
in your verification map can actually run:

```
bash ${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/scripts/resolve-tools.sh
```

With no arguments it reads `.crew/verify.json`, extracts the first word of every
command in every `run`, `always`, `default` and environment list, and reports
each as **native**, **wsl only**, or **MISSING**.

That middle case is the one that wastes a day. A bare `terraform validate` in a
rule, on a machine where terraform lives only inside WSL, fails with "command not
found" - and the gate reports that as a *failed check*, not a missing tool. You
then debug a config problem that does not exist.

Resolve once at setup and write the resolved form into the map: `terraform` if
native, `wsl.exe -e terraform` if WSL-only. Never branch at runtime; a check that
means something different depending on which shell launched it is a check nobody
can reason about.

Before you wrap anything in `wsl.exe -e`, two things bite:

- **Paths cross, slowly.** WSL sees `C:\repos\x` as `/mnt/c/repos/x`, and
  `/mnt/c` is dramatically slower. Moving the clone inside WSL removes the
  problem instead of papering over it.
- **Credentials do not cross.** A Windows `aws` is not the WSL `aws`; they read
  different `~/.aws` directories.

## 4. Install

**From a local directory:**

```bash
mkdir -p ~/crew-marketplace
cp -r crew ~/crew-marketplace/
claude
```

Then inside Claude Code:

```
/plugin marketplace add ~/crew-marketplace
/plugin install crew@my-marketplace
```

**From GitHub**, once you have pushed it:

```
/plugin marketplace add your-org/crew-marketplace
/plugin install crew@my-marketplace
```

Verify with `/help` — you should see `/crew:ticket`, `/crew:work`, `/crew:review`, `/crew:onboard`, `/crew:scale`, and `/crew:jira-sync`.

Plugin components other than skills are cached at load time. After editing agents, hooks, or `.mcp.json`, run `/reload-plugins` or restart.

---

## 5. Set up your first repository

Pick the repository you change most often. Not the most important one — the one you touch weekly. You want feedback fast.

```
cd ~/code/that-repo
claude
```

Then run the guided setup:

```
/crew:init
```

This walks nine phases, **stopping after each one** so you can check the result
before the next thing is built on it. It is resumable — `/crew:init --status`
shows where you are, and it picks up from the first incomplete phase.

| # | Phase | Produces |
|---|---|---|
| 0 | Platform | OS/WSL detection, CRLF and filesystem fixes |
| 1 | Config | `.crew/`, `.work/`, a filled-in `CLAUDE.md` |
| 2 | Providers | Codex and Gemini verified by a real call |
| 3 | Smoke harness | `_verify/` created and documented; `_verify/smoke.sh` green from a clean checkout |
| 4 | Code map | `.crew/codemap/` with anchors |
| 5 | Verification map | `.crew/verify.json`, each pairing proven |
| 6 | Browser tests | `e2e/` specs, or `n/a` |
| 7 | First ticket | One real loop, end to end |

Status is written to `.crew/STATUS.md` with honest states — `partial` and
`blocked` are used, not rounded up to `done`. A status file that overstates
progress is how the whole system quietly stops meaning anything.

You do not have to remember the command. Plain language triggers the same
phased flow — "set up crew in this repo," "set up the team," "run the phased
setup," "what phase am I on," and similar all route to it, and the behaviour is
identical either way. There is no shorter path that skips the gates.

The other skills trigger the same way: "set up gemini" or "wire up the API key"
reaches `crew-providers`, "add browser tests" reaches `crew-verification`,
"expand the crew" reaches `crew-scaling`, "connect my vault" reaches
`crew-memory`, and "set up notifications" or "send updates to Teams" reaches
`crew-notify`.

Under the hood the phases live in one file, `skills/crew-setup/phases.md`, which
both the command and the skill read — so the two entry points cannot drift apart.

The skill will:

1. Run a detection script and report your stack, existing tests, CI, whether `codex` is on your `PATH`, and whether the repo is already configured
2. Ask exactly three questions — reviewer, ticket tracker, memory location
3. Create `.crew/`, `.work/`, `_verify/`, `docs/adr/`, and a `CLAUDE.md` if none exists
4. Tell you plainly that the setup is not yet usable

Commit all of it. `.work/` belongs in version control — it is the shared memory between sessions, and a session that cannot read it starts blind.

**Triage your rules before writing them.** Most rules people want in CLAUDE.md
belong in `.crew/verify.json` instead — where a hook enforces them and they are
not re-paid on every delegation. The test is: *could a command decide this?*

| Rule | Goes in |
|---|---|
| Playwright on CSS changes | `verify.json` |
| tflint + terraform-docs on `.tf` | `verify.json` |
| Fresh apply + rollback + round trip on migrations | `verify.json` |
| Production needs a verified rollback | CLAUDE.md |
| Check error logs after deploy | CLAUDE.md + runbook |
| Don't fix what you notice nearby | CLAUDE.md |

Worked examples ship in `skills/crew-setup/examples/` — a Terraform
`CLAUDE.md` and the matching `verify.json`.

**Fill in the `CLAUDE.md`.** The template leaves blanks on purpose: build and test commands, where the entry point lives, which directories are off limits, and the landmine that breaks every time someone touches it. Thirty lines beats three hundred, because every line is re-read on every delegation.

---

## 6. Build the smoke harness (do not skip this)

Checks live in **`_verify/`**. Setup looks for it first, along with `qa/`, `spec/` and `_test*/`; if the repo already has one of those it is adopted rather than duplicated. If none exists, `/crew:init` creates `_verify/` from the bundled template:

```
_verify/
  README.md       # what each check covers, and when it was last sabotage-tested
  smoke.sh        # fast and shallow: does it respond
  run-all.sh      # the regression suite: does everything else still work
  cases/          # one file per concern, called by the two runners
```

`_verify/README.md` is part of the deliverable. Its layout table says what each script covers and its status table records when each check last proved it could fail. `/crew:verify` cross-checks that README against `.crew/verify.json` and reports drift in either direction — a script with no rule never runs, and a rule pointing at a script the README does not list is a check nobody knows about.

A repo that already has a working `scripts/smoke.sh` keeps it. The gate checks `_verify/smoke.sh` first and falls back, so there is no reason to migrate a harness that works.

At this point `_verify/smoke.sh` exists but contains no checks, so the gate passes vacuously. The crew has no safety net.

```
@crew:smoke-author build the smoke harness for this repo
```

Do nothing else in this repository until that script runs green from a clean checkout.

This is not process ceremony. Agents working on untested legacy code produce confident, plausible, broken changes faster than you can review them. The gate is what converts speed into progress rather than into a slow-motion outage.

What good looks like:

- Five to nine checks, under ninety seconds total
- **Characterization, not aspiration** — capture what the application does *today*, bugs included. A test encoding current behavior is an asset. One encoding intended behavior is a wish.
- Contract level: does it boot, reject an anonymous request, accept an authenticated one, read, write, and round-trip through the database
- Deterministic: no wall clock, no randomness, no dependence on data that happens to exist
- Exit 0 or 1, one line per check, `SMOKE: n/m passed` at the end

Anything that cannot be tested without touching production does not get tested. It gets written into `.work/SMOKE-GAPS.md` so the gap is visible rather than assumed away.

Once it is green, the `Stop` hook takes over: if code changed and smoke fails, the turn cannot be reported as complete.

---

## 7. Teach it the codebase

```
/crew:onboard
```

This is the expensive one-time cost you are willing to pay. It spawns one `explorer` per subsystem in parallel, capped at six per run, and only their summaries reach your context.

The output is `.crew/codemap/<subsystem>.md`, each under sixty lines, each carrying:

```
anchor: repo@a1b2c3d
verified: 2026-08-22
```

**Anchors are the entire point.** Every claim names the file it came from, so any note can be re-verified:

```bash
git diff --name-only <anchor-sha>..HEAD -- <paths>
```

If the anchor files moved, re-verify that section before relying on it. A map without anchors rots silently and keeps being trusted, which is strictly worse than having no map — a stale note is confidently wrong in exactly the way a fresh search never is, and it arrives with the authority of something you wrote down deliberately.

**Code always wins over notes.** When they disagree, the note is wrong. Fix the note; do not reason from it.

Only `.crew/codemap/INDEX.md` loads by default. Everything else is read by path, one file at a time.

Re-map a single area after major surgery with `/crew:onboard --refresh <subsystem>`. Do not re-run the whole thing on a schedule — that is the cost you were avoiding.

---

## 7b. The API and feature reference

```
/crew:reference                # both, whole repo
/crew:reference --api          # endpoints only
/crew:reference --features     # jobs, consumers, CLI, flags, integrations
/crew:reference --audit        # report drift, change nothing
```

The code map and the reference answer different questions, and the second does not fall out of the first. `.crew/codemap/orders.md` saying *"handles order lifecycle, entry `src/Orders/`"* is a good codemap entry and tells you nothing about the eleven endpoints underneath it.

| Document | Audience | Question |
|---|---|---|
| `.crew/codemap/` | an agent about to change code | where does this live |
| `docs/reference/api.md` | a human calling the thing | what can I call, and what does it do to the system |
| `docs/reference/features.md` | a human operating the thing | what can it do, including the parts with no UI |

### The two rules

**Every entry is anchored to `file:line`.** Unanchored, it cannot be re-verified, so it rots silently and keeps being trusted. Same reason codemap notes carry anchors.

**Enumerate from the code, never from the existing docs.** The existing docs are what you are checking. A reference regenerated from a stale reference is a stale reference with a newer date.

### What is worth the effort

For an endpoint the signature is the guessable part. The valuable half is underneath it:

```
### POST /api/orders/{id}/ship
`src/Controllers/OrderController.cs:142`

Auth: bearer token, role `fulfilment`  (`Attributes/RequireRole.cs:20`)
Body: `{ carrier: string, tracking: string }`
Returns: 200 `{ shipmentId }` | 404 unknown order | 409 already shipped
Side effects: writes `shipments`, emits `order.shipped`, calls ShipStation
Notes: not idempotent - a retry creates a second shipment
```

Side effects, error responses, and idempotency. That last line is the one that causes incidents.

For features, the headless ones are what nobody documents and everybody needs: scheduled jobs and what happens when one is missed, queue consumers, admin scripts, feature flags and the config keys behind them.

### Keeping it honest

`--audit` reports drift both ways - endpoints in the code with no entry, and entries whose anchor no longer holds - and changes nothing. A reference quietly rewritten is indistinguishable from one that was right all along.

Anything unconfirmed is written as `undocumented - needs a human` and left visible. A reference that admits a gap is useful; one that implies full coverage while missing a third of the endpoints is worse than none, because a missing endpoint reads as proof it does not exist.

---

## 8. Verification, secrets, and browser tests

A code map describes the codebase. It does not verify anything. These three
artifacts are what actually reduce mistakes.

### The verification map

```
/crew:verify
```

Builds `.crew/verify.json` — a routing table from changed paths to the checks
those paths require:

```json
{
  "rules": [
    { "paths": ["src/Api/**"], "run": ["dotnet test tests/Api", "./_verify/smoke.sh"],
      "why": "Domain changes break API contracts" },
    { "paths": ["**/*.css", "src/components/**"], "run": ["npx playwright test --grep @visual"],
      "why": "Style changes are invisible to API tests" },
    { "paths": ["migrations/**"], "run": ["./_verify/cases/migrate-fresh.sh"],
      "agents": ["dba"], "why": "Fresh-apply catches ordering bugs" }
  ],
  "always": ["npm run lint"],
  "unmapped": "fail"
}
```

This is a data file a hook reads, deliberately not knowledge an agent carries.
Agent judgment about which tests to skip is exactly the judgment that skips the
important one, confidently, on the turn it mattered.

Each pairing is **verified when written**: break the code, run the mapped check,
confirm it goes red, revert. An unverified mapping is a guess written in JSON —
and a pairing that stays green has just told you about a coverage hole.

### Checks and rules are written together

**Whoever writes a check writes its rule, in the same turn.** `smoke-author` and
`browser-tester` both do this now, and both prove the rule fires before calling
it done — break the code, run the mapped command, confirm red, revert.

The failure this prevents is quiet and common: a check exists, is committed, is
visible in the repo, and never runs. Nobody finds out until the change it was
meant to catch ships. **An unmapped check is worse than a missing one, because
it reads as coverage.**

Watch the tag/grep interaction on browser tests in particular: a rule running
`--grep @visual` does not run your new `@flow` spec. That is the most common way
UI coverage ends up existing but never executing.

```bash
bash skills/crew-setup/scripts/map-audit.sh   # or /crew:verify --sync
```

Reports both directions — checks on disk that no rule invokes, and rules pointing
at files that no longer exist. Run it after any session that touched tests.

### After database changes

Code-level rules do not cover schema. A migration needs three checks, and the
rule runs all three:

| Check | Catches |
|---|---|
| Fresh apply to an empty database | Ordering bugs invisible on an already-migrated dev box |
| Rollback apply | An untested down script, which is not a rollback |
| Round trip through the changed path | Shape errors a successful migration hides |

The third is the one people skip, and it is the one that matters: a migration
that applies cleanly and leaves a column nullable the code assumes is populated
passes the first two and fails in production.

`dba` proposes the specific check — which script, what it asserts, which paths —
and `smoke-author` writes it, since `dba` is read-only.

`"unmapped": "fail"` is the most valuable line in the file. A changed path with
no rule blocks the turn and names the file, so "we forgot to test that area"
becomes a visible condition rather than a silent one, and the map improves as a
side effect of normal work.

### Secrets

**The agent learns the access pattern. It never handles the value.**
`.crew/secrets.md` records where a secret lives, its identifier, which
environment variable it lands in, and the command that retrieves it. Names and
commands only.

The reason is not squeamishness. A secret printed into a command result does not
stay in the conversation: it is written to the on-disk session transcript,
carried into compaction summaries, and repeated into every subagent receiving
that context. You cannot un-print it; rotation is the only remedy.

`guard.sh` enforces this — a bare `aws secretsmanager get-secret-value` is
blocked, while capturing into an environment variable is allowed.

Preferred order for test credentials, and the order people usually invert:

1. **No credential at all** — ephemeral containers with seeded fixtures
2. **`.env.smoke`, gitignored** — test-only values, offline, reviewable
3. **A secret store with test-scoped credentials** — read-only, separate account

Option 3 is reached for first and belongs last. A suite that needs cloud
credentials cannot run on a plane, in CI without a role, or on a new laptop.

Never: production credentials in any automated check, a secret in any config or
fixture, or `AWS_PROFILE=production` anywhere reachable.

### Browser tests

```
@crew:browser-tester cover the checkout flow and the pricing page styling
```

Deliverables are spec files under `e2e/`, runnable by `npx playwright test` with
no agent and no MCP server attached. A test that only works while an agent drives
a browser is a demo, not a regression suite.

- Locators: `getByRole`, `getByLabel`, `getByTestId`. Never CSS selectors tied to
  layout classes — those break on exactly the styling changes you are validating,
  producing failures that teach people to ignore the suite.
- CSS: screenshot comparison against committed baselines, dynamic regions masked,
  viewport pinned, animations disabled.
- `retries: 0`, deliberately. Retries convert a race condition into a
  statistically-passing test, which is how a real bug survives to production.
- Flaky and unfixable goes to `e2e/quarantine/` with a reason, never papered over.

Use the Playwright MCP server to *explore* a flow interactively, then write the
spec. The spec is the asset.

Tag specs `@visual` and `@flow` so `verify.json` can run them selectively.

---

## 9. Research and gap analysis

```
/crew:survey
/crew:survey the billing module
```

The `analyst` agent investigates and writes `.work/FINDINGS.md` — at most seven
findings, each with a file-and-line anchor, a concrete impact, and three options
where **option A is always "do nothing"** and is always a real option.

The failure mode it is written against is generic advice: "consider adding
caching," "error handling could be improved." That is what gets produced when
nothing was actually read, and it is worse than silence because it costs review
time and teaches you to skim.

It starts from evidence — `git log` file-change frequency, existing findings,
smoke gaps — rather than from a checklist, because the files that change
constantly are where the pain is.

It does not create tickets. You read the findings and decide; `/crew:ticket` is a
separate, deliberate step. A survey that automatically becomes a backlog is a way
of committing to seven things nobody agreed to.

Run it after the safety net exists, not before. Findings you cannot safely act on
are just a list.

---

## 10. The daily loop

### Scope it

```
/crew:ticket the export job times out on tenants with more than 50k rows
```

`explorer` checks what the change touches and whether it crosses repositories. You get one round of clarifying questions, then a ticket under twenty lines: Want, Scope, Done when, Notes.

"Done when" must be **observable**. "Export works properly" is not a ticket. "Export of a 100k-row tenant completes under 60s and the smoke check covers it" is.

Work spanning repositories gets one ticket per repository, cross-referenced by ID. Never a ticket that silently spans repos.

### Work it

```
/crew:work T-0042
```

The session reads exactly one ticket file, delegates the search to `explorer`, plans before editing, implements the smallest sufficient change, runs smoke, escalates to `security` or `dba` when the change warrants it, and runs review.

If the change added behavior with no smoke coverage, `smoke-author` adds a check. A feature without a check is how the next change breaks it silently.

### Review it

```
/crew:review
```

Codex if available, the `qa-reviewer` agent if not — and it always tells you which ran. Findings are reported verbatim before any argument about them. `BLOCK` items get fixed, smoke reruns, review runs once more.

Then it appends a line to `.crew/metrics.md`. That line is not bookkeeping; `/crew:scale` reads it to determine whether any of this is catching anything.

You open the pull request. The crew stops at the boundary of your judgment.

---

## 11. Configuration reference

Everything reads `.crew/config.json`:

```json
{
  "tier": 0,
  "roles": ["explorer", "qa-reviewer"],
  "qa": { "provider": "auto" },
  "secondOpinion": { "provider": "gemini", "mode": "cli", "model": "gemini-2.5-flash", "sendsCode": false },
  "tracker": "files",
  "jira": { "cloudId": null, "project": null },
  "memory": { "mode": "repo", "vaultPath": null },
  "verifyGate": true,
  "context": {
    "enabled": true,
    "warnAt": 0.8,
    "budgetTokens": null,
    "handoffPath": ".work/HANDOFF.md"
  },
  "notify": {
    "provider": "none",
    "events": ["gate", "review", "waiting"],
    "urlEnv": "CREW_TEAMS_WEBHOOK",
    "tokenEnv": "CREW_TELEGRAM_TOKEN",
    "chatId": null
  }
}
```

**The `context` and `notify` blocks are not optional decoration.** Four of the
six hooks read them, and each treats an absent block as "switched off" rather
than as an error — so a config without them produces a session where the context
watch never fires and no notification is ever sent, with nothing saying so. If
you do not want notifications, write `"provider": "none"` and mean it; do not
omit the block and assume.

| Key | Values | Effect |
|---|---|---|
| `verifyGate` | `true`, `false` | Whether the `Stop` hook blocks on failed checks. Set `false` only while first building the harness. |
| `context.enabled` | `true`, `false` | The `Stop` context watch. **Absent block = off.** |
| `context.warnAt` | `0.0`–`1.0` | Fraction of budget at which the handoff is requested. Default `0.8`. |
| `context.budgetTokens` | integer or `null` | `null` (the default) works the window out from the model id and this session's own peak usage. Set a number to pin it. |
| `context.handoffPath` | path | Where the handoff note lives. Default `.work/HANDOFF.md`. |
| `notify.provider` | `teams`, `telegram`, `none` | Outbound notifications. **Absent block = off.** Credentials come from env vars, never config. |
| `notify.events` | subset of `phase`, `gate`, `review`, `waiting`, `done` | Which events send. Empty or absent sends everything; a channel that pings constantly gets muted within a week. |
| `notify.urlEnv` / `notify.tokenEnv` | env var **name** | The name of the variable holding the webhook URL or bot token — never the value itself. |
| `notify.chatId` | string | Telegram only. Group ids are negative; that is normal. |
| `secondOpinion.provider` | `gemini`, `local`, `none` | Design partner. `sendsCode` stays `false` on any free tier. |
| `qa.provider` | `auto`, `codex`, `claude` | `auto` prefers Codex, falls back to Claude, announces which ran. `codex` fails loudly instead of falling back. |
| `tracker` | `files`, `jira` | Where tickets live. Jira additionally requires the MCP connector. |
| `memory.mode` | `repo`, `obsidian` | Where the code map lives. `obsidian` also needs `vaultPath`. |
| `tier` / `roles` | see §22 | Which agents are in play. Managed by `/crew:scale`. |

The promotion sequence lives in `.crew/verify.json`, not here — see §23. Config
holds preferences; `verify.json` holds the checks, so that one file answers "what
runs when" for both a working tree and a deployed environment.

---

## 12. Optional: Codex as reviewer, Gemini as design partner

A different model reviewing is real independent review. The same model family reviewing itself agrees with itself more than it should, because the author's reasoning is exactly the reasoning it finds persuasive.

Put `codex` on your `PATH` and set `qa.provider` to `auto` or `codex`. `/crew:review` writes the diff to a file, has Codex return one line per defect, and reads only the findings back — the diff never re-enters your context.

Without Codex, the `qa-reviewer` agent runs instead, in its own context window so it has not seen the reasoning that produced the code. Its prompt tells it outright that it shares a model family with the author and must compensate: ask "what input makes this wrong" before "does this look correct." That is genuinely weaker than a different model, and the command says so every time it happens, so you know to review harder yourself.

### Gemini for design

```
/crew:plan T-0042
/crew:plan should the export run inline or move to a queue
```

The `planner` agent gets an independent opinion on a design decision before
anything is built. Gemini's free tier suits this well — design questions are a
handful of calls a week, so rate limits never bite.

**It works from a brief, never from your code.** Free tiers are funded by prompts
and generally train on them, so what leaves the machine is the shape of the
problem: constraints, volumes, latency budgets, the options under consideration,
and what has already been ruled out. No source, no real schema names, no service
names, no ticket text.

The control is not a promise — it is an artifact. `planner` writes the brief to
`.work/briefs/`, shows it to you, and waits for approval before sending. You can
read exactly what goes out, every time.

Two rules that make the output worth having:

- **The disagreement is the product.** The agent reports where the external
  opinion differs *in full*, including reasoning it finds unconvincing, rather
  than blending both views into a smooth consensus. Merging it away means paying
  for a second opinion and throwing it out.
- **Don't hardcode the model name.** Free catalogs churn and models get retired.
  It lives in `secondOpinion.model` and is read at call time.

If code must not leave the machine at all, set `provider` to `local` and point it
at Ollama, or `none` and accept single-opinion planning. Both are legitimate —
the agent just has to say which is in effect.

### Verifying either one

```bash
bash skills/crew-setup/scripts/providers.sh
```

Presence on `PATH` is not working auth, and the difference shows up later as a
gate that never fails. Phase 2 of `/crew:init` requires one real round trip per
configured provider before marking itself done.

---

## 13. Optional: Jira via MCP

Only in repositories where Jira is actually the source of truth. `crew-setup` writes a project-scoped `.mcp.json`:

```json
{
  "mcpServers": {
    "atlassian": { "type": "http", "url": "https://mcp.atlassian.com/v1/mcp" }
  }
}
```

The older `/v1/sse` endpoint was retired in mid-2026. If you copy a configuration from a guide written before then, it will fail with an unhelpful connection error. If OAuth keeps dropping mid-session — a common complaint — switch to API token authentication.

Run `/mcp`, approve the server, authenticate. The cloud ID is then fetched once and cached in `.crew/config.json`, never looked up again.

**The cache is the actual strategy.** Tool *definitions* are less of a problem than they used to be; Claude Code defers MCP tool definitions automatically once they exceed roughly ten percent of the context window, which can turn tens of thousands of tokens into a few hundred. What deferral does not help with is *response* payloads, and a Jira issue is a fat one — rendered description, changelog, watchers, sprint metadata, custom fields.

So `/crew:jira-sync` keeps six fields and discards the rest, writing a compact local file that `/crew:work` reads instead of calling the API. That is the difference between paying for a ticket once and paying for it on every pickup, retry, and context reset. Sync happens at two boundaries only: pickup and completion. Three Jira calls in one ticket means the cache is wrong.

One limitation to know rather than discover: plugin-shipped agents cannot declare `mcpServers` in frontmatter, for security reasons. Jira access therefore lives at session level. If you want it isolated in its own context window, that agent has to live in `~/.claude/agents/` outside the plugin.

---

## 14. Optional: Obsidian for memory

Obsidian works here for an unglamorous reason: it is a folder of markdown files. Claude Code reads and writes it with no integration layer, and you get backlinks and graph view for free. There is nothing to build.

```
vault/
  repos/<repo>/codemap/<subsystem>.md
  repos/<repo>/decisions/<adr>.md
  contracts/<service-a>--<service-b>.md
  INDEX.md
```

**Only `INDEX.md` loads by default.** A vault is unbounded, and an agent asked to "check the vault" will happily pull forty thousand tokens of notes to answer a question the code would have answered in four hundred. Index first, then one targeted read. If a task needs more than three notes, the notes are badly organized.

The real payoff at five or more repositories is `contracts/`. That repository A's endpoint is consumed by repository B in a way B's code does not make obvious is a fact contained in no single repository. It is the one kind of note that cannot rot into irrelevance — only into inaccuracy, which anchors catch.

Symlink `.crew/codemap` into the vault rather than copying, so divergence is never a question.

---

## 15. Optional: Teams and Telegram notifications

**Outbound only.** crew sends messages; it never reads a channel and never takes
instructions from one.

```json
"notify": {
  "provider": "teams",
  "urlEnv": "CREW_TEAMS_WEBHOOK",
  "events": ["phase", "gate", "waiting"]
}
```

Events: `phase` (an init phase completed or blocked), `gate` (verification
failed), `review` (BLOCK/FIX counts), `waiting` (Claude needs you), `done`
(ticket finished). Opt into few — a channel that pings on everything gets muted
within a week, and a muted channel is worse than none because you believe you
are covered.

### Teams

The old `channel ••• → Connectors → Incoming Webhook` route is gone; Office 365
Connectors were permanently disabled across 18–22 May 2026. Any tutorial
describing that path is dead.

Current route: **••• next to the channel → Workflows → "Post to a channel when a
webhook request is received"**, confirm Team and channel, copy the URL. Export it
to `CREW_TEAMS_WEBHOOK` in your shell profile — that URL *is* the credential for
the channel, so keep it out of git.

Two things that will otherwise puzzle you: messages post as the **Flow bot**
(custom name and icon are not supported via Workflows webhooks), and the flow
runs under whoever created it — if that person leaves, notifications stop.

### Telegram

Yes, it's a bot — created through another bot. Message **@BotFather**, run
`/newbot`, take the token. Then **message your bot first**: a bot cannot open a
conversation with you. Read the chat id from `getUpdates`; group ids are negative,
which is normal rather than a bug.

Export `CREW_TELEGRAM_TOKEN` and put the chat id in `notify.chatId`.

### Payload discipline

One line, truncated at 280 characters. No diffs, no findings text, no ticket
bodies, no error output that might carry a connection string. A chat channel
syncs to phones, is searchable by people outside the project, and in Teams may be
retained under policies you don't control. Send the fact; the detail stays in the
repo.

### Two-way is available and mostly a bad idea

MCP servers exist for both — Microsoft's official Work IQ Teams server (preview,
read/write with no read-only flag), `floriscornel/teams-mcp` (npx, has a
read-only mode), `InditexTech/mcp-teams-server`, and several Telegram ones
including some built to ask a question and wait for the reply.

Two reasons to stay outbound. A chat message becomes an instruction to an agent
holding shell and filesystem access — anyone who can post there, and anything
quoted in from a ticket or forwarded email, is writing into its context. And
approving a plan on a phone is worse review, not more of it: if work already
queues on your attention, making it easier to say yes without reading properly
doesn't widen that bottleneck.

If you go ahead regardless: private channel, allowlisted sender ids, a fixed
vocabulary (`approve T-0042`, `status`) parsed **by a script** rather than by the
model. And check whether Claude Code's own mobile access already covers it —
first-party, auth handled, no new inbound path.

---

## 16. Context handoff

**First, a correction worth having up front:** Claude Code cannot clear its own
session, and a script launched by a hook cannot either — hooks run as child
processes, and a child cannot reset its parent's conversation.

You don't need it to. The lifecycle already covers the cycle:

| Moment | Hook | What happens |
|---|---|---|
| Nearing the limit | `Stop` | Estimates usage, asks for a handoff before the turn ends |
| Auto-compaction imminent | `PreCompact` | Snapshots the transcript, writes a skeleton handoff |
| After `/clear`, `/compact`, resume | `SessionStart` | Prints the handoff — stdout is injected as context |

So: crew tells you it's time, you type `/clear`, and the next session opens
already holding the note. The one manual step is the `/clear` — which is the
step that should stay manual.

### The threshold is an estimate

No hook reports token count. `context-watch.sh` measures the JSONL transcript
that hooks receive as `transcript_path`. Bytes aren't tokens and the file carries
JSON scaffolding the model never sees, so **calibrate once**: run `/context`,
compare, adjust `context.budgetTokens`. Being 20% early is fine; being late
defeats the purpose.

It fires **once per session**, gated by a marker file that `SessionStart`
clears. Without that gate, a `Stop` hook returning exit 2 fires every turn and
traps the session in a loop.

### Pointers, not narrative

```
/crew:handoff
```

The note is built from `git status`, the diff, the ticket, and the last gate
result — plus the two things only the session knows: the next action in one
concrete sentence, and the dead ends already tried.

A session at 85% context is the *least* reliable narrator of what it just did —
that's exactly when detail has been compacted away. The diff is more trustworthy
than the recollection of it. A good handoff says "look here," not "here's what
happened." Under 40 lines; if it's longer, the session was doing too many things
at once, and that's the real finding.

Anything uncertain goes under **Verify first** rather than being asserted as done.

### Auto-resume: not implemented, and deliberately so

`SessionStart` can in principle return an `initialUserMessage` to start the next
session working with no human turn. **crew does not do this.** `handoff-read.sh`
prints the note as plain context and stops there; the `context.autoResume` key is
accepted in config and read by nothing.

That is the intended behaviour, not an oversight. Auto-resume removes the one
moment where a human reads what the previous session claimed before more work is
built on top of it, and if a handoff is subtly wrong that is exactly how the
error compounds unattended. The key is kept so an existing config does not break;
setting it to `true` changes nothing.

### Housekeeping

`/crew:work` deletes `HANDOFF.md` on ticket completion. A stale handoff is worse
than none: it gets injected into every later session as though current, and that
session can't tell it's reading history.

`PreCompact` keeps the last five raw transcripts in `.crew/transcripts/`, which
setup gitignores — transcripts contain everything the session saw, including any
secret that reached it.

---

## 17. Linting, Terraform docs, and repo conventions

### Your `_verify` directories

**These are not discovered automatically.** Nothing in crew knows what a
`_verify/` directory is, and a check nobody runs reads like coverage to the next
person — which is worse than having none.

Phase 5 now searches for `_verify/`, `qa/`, `spec/`, `_test*/` and similar, and
when it finds one it **asks you** rather than guessing: what runs it, which
changes should trigger it, does it need credentials. Then it gets a rule of its
own, with the directory named in `why` so the mapping outlives the person who
explained it:

```json
{ "paths": ["src/loaders/**"],
  "run": ["bash _verify/run.sh loaders"],
  "why": "_verify/ holds the team's hand-written QA checks for loader changes" }
```

`smoke-author` also checks for these before writing anything, so it wires into
what exists instead of building a parallel suite that will drift out of
agreement with it.

### Linters

Path-scoped rules in `verify.json`, per the `crew-lint` skill: `ruff` for Python,
`PSScriptAnalyzer` for PowerShell, `phpstan` + `phpcs` for PHP, `fmt`/`validate`/
`tflint` for Terraform, `eslint`/`prettier` for JS.

Two rules that keep a gate alive:

**Format automatically, lint blockingly.** Formatter in write mode, committed;
linter in check mode, failing. Arguing with a formatter in review is wasted time.

**Baseline the legacy debt on day one.** `phpstan --generate-baseline`, ruff
per-file ignores, a PSScriptAnalyzer settings file. A gate that starts red never
becomes a gate — it becomes something people pass with `--force`. Burn the
baseline down as its own tickets.

Start phpstan at level 1 and PSScriptAnalyzer at `Error` only. Level 8 on legacy
PHP produces a wall nobody reads.

### terraform-docs and tflint

Templates ship for `.terraform-docs.yml`, `.tflint.hcl`, and `footer.md`.

The critical rule: **never edit inside `<!-- BEGIN_TF_DOCS -->`.** That block is
regenerated, so edits there are destroyed silently on the next run. To change it,
change the source — the `/** */` header at the top of `main.tf`, `footer.md`, or
the `description` on each variable and output. Hand-written prose lives *above*
the marker.

Put `terraform-docs markdown table . --output-file README.md --output-check` in the gate - the `--output-check` form, which fails on a stale
README rather than rewriting it mid-gate and tripping `unmapped: fail` on its own
edit. That way a variable added without a
`description` shows up as a README diff in the pull request, so undocumented
inputs become visible instead of accumulating quietly.

One tflint note worth keeping: the template disables `terraform_comment_syntax`
**deliberately**, because that rule flags the `/** */` block terraform-docs reads
its header from. The config carries a comment explaining why — leave it there, or
someone will "fix" it in six months and break the docs pipeline.

`tflint --init` must run once per machine and once in CI. A missing plugin fails
unhelpfully.

Requires terraform-docs >= 0.16.0; `footer-from` and `.Module` in `content` do
not exist earlier, and the failure is a template error rather than a version
message.

---

## 18. Document maintenance

```
/crew:docs           # update what this change should touch, and only that
/crew:docs --audit   # report staleness everywhere, change nothing
```

**The default is: do not touch.** Updating every document on every change is how
documentation becomes noise — a CHANGELOG with an entry per typo fix is
unreadable, and a README rewritten every sprint stops being trusted.

So each document has a trigger condition, checked once per ticket at step 10 of
`/crew:work`:

| Document | Update when | Never |
|---|---|---|
| `CHANGELOG.md` | Observable behaviour changed | Refactors, formatting, renames |
| `README.md` | Setup, commands, or the mental model changed | Every ticket |
| `SECURITY.md` | Reporting process or supported versions changed | Routine security fixes |
| `TODO.md` | Something deferred, with a reason | As a substitute for tickets |
| `docs/adr/` | A decision with a real rejected alternative | Implementation detail |
| `docs/diagrams/` | The structure a diagram shows moved | Cosmetic changes |

"None of them" is the common and correct answer, and the command says so plainly
rather than finding something to write.

Before editing any markdown it checks for generated-block markers and, if the
target is inside one, edits the source instead and tells you which. That covers
terraform-docs, OpenAPI generators, and anything using `AUTO-GENERATED`.

Two specifics worth stating: CHANGELOG entries are written from the ticket and
the diff in user-facing language — "rejects files with a BOM," not "added BOM
strip in `validate_header()`" — and `SECURITY.md` never logs an unfixed
vulnerability, because a public file describing an open hole is a disclosure.

`--audit` is worth running monthly. It reports rather than fixes: bulk
documentation diffs are unreviewable, which means they get approved unread.

---

## 19. Runbooks

```
/crew:runbook roll-back-inventory-loader
/crew:runbook --from-ticket T-0042
/crew:runbook --verify roll-back-inventory-loader
/crew:runbook --audit
```

A runbook answers exactly one question: **"it's 3am, this is broken, what do I
type?"** Not how the system works — that's architecture. Not why it was built
that way — that's an ADR. A procedure someone half-awake can follow without
judgement calls.

`/crew:work` step 10 captures one when a ticket involved a procedure that will
be repeated, is destructive, or lived only in one person's head. Drafts are built
from the commands **actually run in the session**, plus `verify.json` and the
terraform config for real resource names — never from memory, because a wrong
resource name in a runbook is worse than no runbook. It's followed under
pressure.

Format rules that make one usable at 3am: exact copy-pasteable commands, a
**verify line after every destructive step** (the failure mode is a step that
silently did nothing while the operator moves on), a rollback for the fix itself,
and a named escalation so "I'm stuck" isn't a decision.

### The index is keyed by symptom

`docs/runbooks/INDEX.md` lists symptom → runbook → severity → last verified.
Symptom-first because that's what you have at 3am: you don't know which component
failed, you know what you're seeing. Only the index loads by default; agents read
it, then one runbook — the same token rule as the code map.

### Verification is the whole value

**A runbook nobody has executed is a wish.** Commands drift, resource names
change, a step that used to work now needs a flag. And an unverified runbook is
actively dangerous, because it's trusted exactly when there's no time to check
it.

So every runbook carries `last verified: <date> by <who>`, drafts start at
`NEVER` rather than blank, and `--verify` walks it in dev and fixes what differed.
`--audit` reports anything unverified in 90 days or referencing resources that no
longer exist — and **reports rather than fixes**, because quietly updating a
stale runbook converts a known-stale procedure into an apparently-fresh one.

---

## 20. Diagrams

```
/crew:diagram architecture
/crew:diagram data-flow orders
/crew:diagram refresh
```

**Mermaid source lives in git; images are build output.** A PNG someone drew in a
tool is unreviewable in a pull request and un-updatable by anyone without the
source file, so it drifts from the code within a quarter and then actively
misleads. Mermaid diffs, and whoever changes the code changes the diagram in the
same commit.

Source goes to `docs/diagrams/*.mmd` with a provenance header and an anchor list
— the same re-verifiability idea as the code map. `refresh` diffs each diagram's
anchors against HEAD and only rebuilds the ones whose code moved.

Rendering needs Mermaid CLI:

```bash
npm install -g @mermaid-js/mermaid-cli
bash skills/crew-diagrams/scripts/render.sh docs/diagrams
```

That renders every `.mmd` to `out/*.svg` and `out/*.png`, skipping unchanged
sources. `mmdc` drives headless Chromium, so the script passes `--no-sandbox`
for containers and CI. Prefer SVG in docs — sharp at any size, text searchable —
and PNG only where the destination cannot take SVG, such as Teams or PowerPoint.
Use a white background for anything printed or pasted into chat; transparent PNGs
vanish on dark mode.

Where the destination renders fenced ```mermaid blocks natively (GitHub, GitLab,
most wikis), skip the render entirely and embed the source.

### Visio

`skills/crew-diagrams/scripts/visio.ps1 -Detect` checks for an installed licence.
If present, it builds a `.vsdx` from a small JSON node/edge spec via COM
automation — real shapes and connectors on a grid, which is a starting point a
human then arranges, not a finished templated deliverable.

If Visio is absent, the skill offers three honest alternatives rather than
faking it: import the rendered SVG into Visio, keep the PNG if the ask was really
"a picture for the deck," or use draw.io, which imports Mermaid and exports
`.vsdx`. That third one usually solves "the review board expects a Visio file"
without needing a licence at all.

---

## 21. AWS and Azure MCP

Official servers for both, configured per repo — the terraform repo needs the
IaC server; the AngularJS front end does not.

**The credential is the boundary, not a flag.** These servers authenticate as
you, with whatever your credential chain grants. If your default profile is
admin, so is the agent. There is no read-only mode that substitutes for scoping
the profile, and `guard.sh` blocking `aws` shell commands does not cover an MCP
tool call.

So: a dedicated read-only profile against a non-production account, never
`AWS_PROFILE=production` in a repo where an agent runs unattended, and start with
the servers that touch no account at all.

**AWS** — installed per-server with `uvx` from the `awslabs/mcp` suite:

```bash
claude mcp add aws-docs uvx awslabs.aws-documentation-mcp-server@latest
claude mcp add aws-pricing uvx awslabs.aws-pricing-mcp-server@latest
# account-reaching, add deliberately:
claude mcp add aws-api uvx awslabs.aws-api-mcp-server@latest
```

Docs and pricing need no credentials and are genuinely useful to `analyst` and
`planner`. There is also a consolidated AWS MCP Server now generally available,
and an Agent Toolkit for AWS positioned as the successor to the Labs servers,
with IAM condition keys distinguishing agent actions from human ones. If you are
wiring agents into a real account, that attribution is worth more than any
convenience the older suite offers — check the current guide before committing,
since this area has moved repeatedly.

**Azure** — one server, 40+ services:

```bash
claude mcp add azure-mcp -- npx -y @azure/mcp@latest server start
```

Needs Node 20 LTS or later, and you must authenticate to Azure *before* starting
it — an unauthenticated server produces confusing tool failures rather than a
clear error. Note that Claude Code uses the `mcpServers` config key while Visual
Studio and VS Code use `servers`; copying a snippet between them fails silently.

---

## 22. Growing the crew

```
/crew:scale
```

This answers three questions from `.crew/metrics.md` before recommending anything.

**Is review catching defects?** `BLOCK` plus `FIX` per ticket over the last ten:

- Below 0.3 — the review is broken, not thorough. Adding roles makes a system that finds nothing cost more and find nothing faster. Check that Codex is really running, the diff is not empty, and the base branch is right.
- 0.3 to 2.0 — healthy. Scaling questions are legitimate.
- Above 2.0 — tickets are too large. Cut scope before adding anyone.

**Where does work actually sit?** If tickets pile up waiting on *your* review, the bottleneck is your attention, and more agents make it strictly worse: more parallel output, same reviewer. The skill will tell you this even though it is not what you asked.

**Can the work genuinely run in parallel?** Parallelism scales on independent work units, not job titles.

| Arrangement | Actually parallel? |
|---|---|
| Two repositories | Yes — the good case at your repo count |
| Two git worktrees of one repo | Yes, with merge cost at the end |
| Two agents, one working tree | No. Conflicting edits and lost writes |

"Add three more developer agents" to a single working tree is not throughput. It is a race condition with a job title.

### Tiers

| Tier | Roles | Add when |
|---|---|---|
| 0 | `explorer`, `qa-reviewer` | Always start here |
| 1 | `+ security`, `smoke-author` | Security findings reach review; coverage gaps cause regressions |
| 2 | `+ dba`, `docs-writer` | Migrations are routine; documentation staleness costs real time |
| 3 | Parallel sessions, worktrees, agent teams | Every repository involved has green smoke |

Native multi-session coordination requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` and is experimental, with known limitations around session resumption and shutdown. Plain parallel sessions across repositories are less exciting and more reliable.

Every added role costs a full context load plus the `CLAUDE.md` hierarchy on every invocation. If that cost does not show up as findings in `metrics.md`, it is not there at all.

A scaling review that concludes "this is the right size" is a successful review.

---

## 23. Promotion: development to qa to production

A merge is not a deploy, a deploy is not a working application, and a green pipeline says only that the pipeline is green. Section 8 gates a *working tree*; this gates a *running environment*.

```
/crew:promote qa
/crew:promote production --dry-run
/crew:promote --status
```

### Five gates, in order, stopping at the first failure

| # | Gate | Answers |
|---|---|---|
| 1 | Pre-deploy | Is the source environment green, and is this the artifact it proved? |
| 2 | Deploy | Did the deployment mechanism report success? |
| 3 | Smoke | Does the deployed thing respond at all, in this environment? |
| 4 | Regression | Does everything that worked yesterday still work? |
| 5 | Verify | Are the environment's own signals clean — error logs, alarms, queues? |

Gate 2 is the weakest evidence in the list and the one most often mistaken for the whole set. A successful deploy proves bytes moved. Gates 3 to 5 are what prove the application works.

Smoke and regression are deliberately separate. Smoke passing tells you the deploy landed; it says nothing about the module three directories over that just broke. A promotion that only smoke-tests has skipped the gate that catches regressions, which is the gate that catches the expensive ones.

### Declared, not remembered

The sequence lives in the `environments` block of `.crew/verify.json`, beside the path rules:

```json
"environments": {
  "qa": {
    "requires":     ["development"],
    "deploy":       ["./scripts/deploy.sh qa"],
    "smoke":        ["./_verify/smoke.sh --env qa"],
    "regression":   ["./_verify/run-all.sh --env qa", "npx playwright test --grep @flow"],
    "verify":       ["./_verify/check-logs.sh qa --since 10m"],
    "soakMinutes":  10,
    "promotesTo":   "production"
  },
  "production": {
    "requires":     ["qa"],
    "deploy":       ["./scripts/deploy.sh prod"],
    "smoke":        ["./_verify/smoke.sh --env prod"],
    "regression":   ["./_verify/run-all.sh --env prod --read-only"],
    "verify":       ["./_verify/check-logs.sh prod --since 15m", "./_verify/check-alarms.sh prod"],
    "soakMinutes":  15,
    "rollback":     "docs/runbooks/rollback.md",
    "requireHuman": true
  }
}
```

`/crew:init` Phase 8 builds this by asking, per environment, what actually deploys it and what actually proves it worked. It fills in only what exists. A block with `deploy` and `smoke` and nothing else is honest; one with five aspirational commands nobody has run is worse than an empty file, because it reads as coverage.

### The promotion record

Every promotion appends a row to `.work/PROMOTIONS.md`, failures included:

```
| when (UTC) | env | sha | smoke | regression | verify | by |
|---|---|---|---|---|---|---|
| 2026-08-23T14:02Z | qa | a1b2c3d | pass | pass | pass | mbadali |
```

`requires` reads this file. It is also the only honest answer to "is production running what qa signed off on" — compare the shas, not the branch names. A promotions log with no failures in it is a log nobody is writing to.

### What a hook enforces, and what it cannot

`promote-gate.sh` fires on `PreToolUse` and refuses any command matching a
declared `deploy` entry unless, for the sha at HEAD:

- every environment in `requires` has an **all-pass** row in `.work/PROMOTIONS.md`
- the `rollback` runbook exists and carries `last verified: YYYY-MM-DD` inside 90 days
- `requireHuman` has an approval marker at `.crew/.approved-<env>-<sha>`
- the working tree is clean - you cannot deploy a sha plus uncommitted changes

`verify-gate.sh` then refuses to end a turn that deployed and recorded nothing.

What no hook can enforce: that `smoke`, `regression` and `verify` actually ran,
against the right environment, after the soak. A hook fires before a command and
after a turn; it cannot watch the middle. The row you append is a claim - which
is exactly why it must record failures too.

Two setup consequences: `.gitignore` must cover `.crew/` and `.work/`, or the
gate's own marker dirties the tree and blocks the next deploy; and the rollback
runbook needs a literal `last verified: YYYY-MM-DD` line, because that is what
the hook greps for.

### Rules with no override

- **The sha must match across environments.** A rebuild between qa and production is a different artifact, and qa proved nothing about it.
- **`verify` runs after the soak.** Errors surface on the first real traffic, which arrives after the deploy finishes, not during it.
- **Production needs a rollback runbook verified inside 90 days.** No verified rollback, no deploy.
- **A failed gate is a stop.** Roll back or fix forward, then run the whole sequence again from gate 1. Never resume mid-sequence.

### Starting from nothing

Most legacy repos have a deploy script and no post-deploy proof at all. Build it in payoff order, not all at once: `smoke` for the environment you deploy to most; then `verify`, where even `grep -c ERROR` over the last ten minutes beats nothing because it turns "looks fine" into a number; then `regression` last, being the most expensive to build and the least useful until the first two are trustworthy.

---

## 24. Command and agent reference

### Commands

| Command | Purpose |
|---|---|
| `/crew:ticket <description>` | Scope a request into a ticket |
| `/crew:work <id>` | Work one ticket end to end |
| `/crew:review` | Independent QA — Codex or Claude fallback |
| `/crew:onboard [--refresh <area>]` | Build or refresh the code map |
| `/crew:reference [--api\|--features\|--audit]` | Enumerate the API and features into `docs/reference/`, anchored to `file:line` |
| `/crew:init` | Guided phased setup, resumable |
| `/crew:plan <decision>` | Independent design opinion before building |
| `/crew:runbook <name\|--audit\|--verify>` | Write, verify, or audit operational runbooks |
| `/crew:docs [--audit]` | Update the documents this change should touch |
| `/crew:handoff` | Write the handoff note before clearing |
| `/crew:diagram <type>` | Architecture, data-flow, process and sequence diagrams |
| `/crew:verify` | Build or refresh the change-to-check map; creates `_verify/` if the repo has no check directory |
| `/crew:promote <env> [--dry-run\|--status]` | Promote development -> qa -> production with deploy, smoke, regression and post-soak verification as separate gates |
| `/crew:survey [area]` | Research gaps, produce ranked findings with options |
| `/crew:scale` | Evidence-based crew sizing |
| `/crew:jira-sync <KEY> [--push]` | Sync one issue with the local cache |

### Agents

| Agent | Tools | Tier | Role |
|---|---|---|---|
| `explorer` | read-only | 0 | Maps code, returns summaries not contents |
| `qa-reviewer` | read-only | 0 | Hostile review; the Codex fallback |
| `security` | read-only | 1 | Exploitable defects in the diff |
| `smoke-author` | read/write | 1 | Builds and repairs the safety net |
| `browser-tester` | read/write | 2 | Playwright specs, visual baselines, user flows |
| `analyst` | read-only | 2 | Anchored findings and options, never tickets |
| `planner` | read-only | 2 | Design second opinion from an abstracted brief |
| `dba` | read-only | 2 | Migrations, locks, online safety |
| `docs-writer` | read/write | 2 | Architecture and data flow from real code |

### Hooks

| Hook | Event | Behavior |
|---|---|---|
| `guard.sh` | `PreToolUse` on `Bash\|PowerShell` | Blocks `terraform apply`/`destroy`, destructive DDL, force push, hard reset, prod-targeted commands, and any command that would print a secret value into the transcript |
| `promote-gate.sh` | `PreToolUse` on `Bash\|PowerShell` | Refuses a declared `deploy` command unless the upstream environment has an all-pass row for **this sha**, the rollback runbook is verified inside 90 days, `requireHuman` is approved, and the tree is clean |
| `verify-gate.sh` | `Stop` | Runs the checks the changed paths map to; fails the turn on red, on a changed path with no rule, or on a deploy that recorded no promotion row |
| `context-watch.sh` | `Stop` | Estimates context use; asks for a handoff once per session |
| `handoff-write.sh` | `PreCompact` | Snapshots the transcript, writes a skeleton handoff |
| `handoff-read.sh` | `SessionStart` | Injects the handoff after clear, compact, or resume |
| `notify.sh` | `Notification`, plus called by commands | Outbound one-line message to Teams or Telegram. Never reads. |

**Every hook is inert until a repository has `.crew/config.json`.** Installing the
plugin arms nothing; `/crew:init` in a given repo is what turns the gates on there.
That is deliberate - a gate that fired in every repository you opened would be
hostile - but it does mean "I installed crew and nothing happened" is the expected
first experience, not a fault. Check with `ls .crew/` before concluding a hook is
broken.

Hooks are deterministic. That is their whole value — a hook cannot be argued out of blocking `terraform apply`, and an agent can.

### Three suites, and what each can actually prove

```bash
bash   hooks/scripts/_test/run-tests.sh           # 50 cases - the hooks
bash   hooks/scripts/_test/setup-walkthrough.sh   # 32 cases - the setup scripts
python hooks/scripts/_test/validate-prompts.py    # 91 checks - command/agent structure
```

| Suite | Proves | Cannot prove |
|---|---|---|
| `run-tests.sh` | Every gate blocks and allows what it should | - |
| `setup-walkthrough.sh` | Phases 0-8 scripts run against a real mixed-stack repo and produce their artifacts | that a human would like the result |
| `validate-prompts.py` | Frontmatter parses, tools are real, referenced agents and paths exist, read-only agents hold no write tools, commands that spawn subagents are permitted to | **whether the prompts produce good work** |

That last gap is real and no test closes it. The 16 commands and 9 agents are
instructions to a model; only a live session running a real ticket exercises
them. Setup Phase 7 exists for exactly that, and it is the one thing here that
has to be done by hand.

All three are sabotage-tested - reintroduce a bug each is meant to catch and it
goes red. If you add a rule, add the case that proves it, then break it once.

`run-tests.sh` is 50 cases: 20 the guard must block, 14 it must allow, 12 for the
promotion gate, plus the verify gate's root-level glob matching and its
`stop_hook_active` exit. `guard.sh` produced two
real regressions in two review passes — a substring `prod` match that blocked
`s3://my-product-images`, and a secret rule that exempted `> file` so writing a
secret to disk passed while printing one blocked. Both were found by running it,
not by reading it.

The suite has been sabotage-tested: reintroducing each of those bugs turns it
red (3 failures, 3 failures, and 1 for the stop-loop check). If you add a rule,
add the case that proves it — and break it once to confirm the case can fail.

### How the Windows half works

Each hook is registered **once**, as bash. Only the `PreToolUse` guard branches, and it branches on **which tool Claude used**, not on which OS is running:

```bash
INPUT=$(cat)
crew_tool_dispatch guard.ps1 "$INPUT"   # tool_name == PowerShell -> PowerShell rules
```

That distinction is load-bearing. A `Bash` tool call is bash syntax *even on Windows*, so judging it with PowerShell rules gets it backwards in both directions: it blocks the correct capture form (`DB_PASS=$(...)`) and misses the wrong one. Branch on the tool and each command is judged by the rules of the language it is written in.

The other five hooks judge no command and have no branch. They are reached through `bash`, so if they run at all bash is present and can do the work; a `.ps1` twin would be unreachable code. `verify-gate.ps1`, `context-watch.ps1`, `handoff-read.ps1` and `handoff-write.ps1` are kept for anyone wiring crew's hooks into a PowerShell-only harness by hand, and are not registered by `hooks.json`.

Two things worth knowing:

- **There is no `shell: powershell` field.** Claude Code does not read one. A hook registered with it looks configured and never runs. Versions of this plugin before 0.2.0 did exactly that, and on Windows the command guard blocked nothing while the `Stop` gate ran nothing.
- **`bash` must be on `PATH` on Windows.** Git Bash satisfies it. The bash script is the entry point even when the PowerShell twin does the work, so with no bash at all no hook fires.

`python3` is not required. Every script resolves `python3`, then `python`, then `py`, and `guard.sh` prefers `jq` when present. With none available the hook says so on stderr and exits 0 — loudly inert rather than silently passing.

---

## 25. Troubleshooting

| Symptom | Likely cause |
|---|---|
| Commands do not appear | Plugin not installed, or needs `/reload-plugins`. Check `/help`. |
| Agents ignore `CLAUDE.md` rules | The built-in Explore and Plan agents skip `CLAUDE.md` by design. Restate critical constraints in the delegation prompt. |
| Smoke gate never fires | `_verify/smoke.sh` has no checks, or `verifyGate` is `false` in `.crew/config.json`. |
| Gate blocks on a file it edited | A `run` command writes to the tree - almost always `terraform-docs .` without `--output-check`. Use the checking form. |
| Promotion says qa passed but prod broke | Compare the shas in `.work/PROMOTIONS.md`. A rebuild between environments means qa proved nothing about what prod got. |
| Review always returns CLEAN | Empty diff, wrong base branch, or `codex` silently missing. Check which reviewer the command reported. |
| Jira connection fails | Using the retired `/v1/sse` endpoint, or the server was never approved via `/mcp`. |
| Context fills fast anyway | `CLAUDE.md` has grown. Every line is multiplied across every delegation. Cut it back to a routing table. |
| Gate says "unmapped changes" | Working as intended. Add a rule to `.crew/verify.json` for that path, or mark it deliberately unchecked. |
| Visual tests fail after an unrelated change | Baselines are stale or a dynamic region is unmasked. Regenerate deliberately with `--update-snapshots`, never automatically. |
| A secret read is blocked | Capture it into an env var rather than printing it: `export X=$(aws secretsmanager get-secret-value ... --output text)`. |
| Teams webhook returns 404 or 410 | An old Office 365 Connector URL. Those were disabled in May 2026 — recreate it via Workflows. |
| Telegram `getUpdates` returns nothing | You have not messaged the bot yet. A bot cannot open the conversation. |
| Notifications stopped with no error | The Teams Workflow runs under its creator's account. Check whether they left or lost the licence. |
| Runbook commands fail when needed | It was never verified. `--verify` it in dev; check `last verified`. |
| crew skills stop triggering | A broadly-scoped skill is competing. `find-skills` is the first to test — see its BUNDLING-NOTE.md. |
| README keeps reverting | You edited inside `BEGIN_TF_DOCS`. Edit the `/** */` header in `main.tf`, `footer.md`, or the variable descriptions instead. |
| `tflint` fails with a plugin error | Run `tflint --init` once per machine and in CI. |
| terraform-docs template error | Needs >= 0.16.0 for `footer-from` and `.Module`. |
| A test exists but never runs | No rule invokes it. Run `/crew:verify --sync`. |
| Migration passed, production broke | The rule covered apply but not the round trip. Add all three DB checks. |
| `_verify` checks never run | Nothing maps to them. Add a rule in `.crew/verify.json` naming the directory. |
| Handoff prompt fires every turn | The marker file is not being cleared. Check that the `SessionStart` hook is registered. |
| Warning arrives too late | `budgetTokens` is set too high for the real window. Calibrate against `/context`. |
| Old handoff keeps reappearing | It was never deleted. Remove `.work/HANDOFF.md` when the work is done. |
| `mmdc` fails in a container | Headless Chromium needs `--no-sandbox`. The render script passes it; a direct `mmdc` call will not. |
| Rendered PNG unreadable in Teams | Transparent background on dark mode. Render with `-b white` for chat and print. |
| Azure MCP tools fail oddly | You are not authenticated. `az login` before starting the server. |
| MCP snippet copied from VS Code does nothing | VS Code uses the `servers` key; Claude Code uses `mcpServers`. |
| Plan command hangs | The Gemini CLI dropped into interactive mode. Confirm the non-interactive flag with `gemini --help`. |
| Provider call fails with model-not-found | Free catalogs churn. Update `secondOpinion.model` rather than debugging the request. |
| Survey returns generic advice | The analyst could not anchor its findings. Give it a narrower area and make sure the code map exists. |
| `bad interpreter: ...^M` | CRLF line endings. Add `.gitattributes` with `* text=auto eol=lf` and `git add --renormalize .`. |
| Tests connect fine on Windows, time out in WSL | WSL2 — the service is on the Windows host, not `localhost`. Use the gateway IP from `.crew/config.json`. |
| Smoke suite takes minutes instead of seconds | Repo is on `/mnt/c`. Re-clone inside WSL. |
| Hooks do not fire on Windows | Native Windows uses the `.ps1` hooks via the `PowerShell` tool. A bash hook path will not resolve. |
| Code map contradicts the code | The map is stale. Code wins. Re-run `/crew:onboard --refresh <area>` and delete what cannot be verified. |

---

## A note on the bundled find-skills

`skills/find-skills/` is a third-party skill from the open skills ecosystem,
vendored here rather than installed with `npx skills add`. That means no
updates — `npx skills check` won't see this copy, and upstream fixes have to be
pulled in by hand.

Installing it separately keeps it updatable and lets you disable it without
touching crew. Vendoring is right only if it needs to travel with the plugin to
machines that won't run the skills CLI.

Worth knowing: its upstream description fires on *"asks how do I do X"*, which is
close to "any question." That competes with crew's own skills for ordinary
requests, and selection gets worse as more broadly-scoped skills load. If
`crew-setup` stops firing on "set up crew," disable this for one session and see
whether the problem goes away. `BUNDLING-NOTE.md` beside it has a narrowed
description you can swap in that keeps the capability and removes the collision.

---

## On combining with other plugins

Keep `crew` separate from general skill libraries like `superpowers`. They
compose fine — plugin skills are namespaced, so nothing collides — and they solve
different problems: `superpowers` is broad methodology (TDD, debugging,
brainstorming) applied everywhere, while `crew` is a narrow gated workflow for a
specific kind of repo.

Install both if you want both. Do not merge them: bundling someone else's
20+ skills into this plugin means you inherit their update cadence, their
triggering behaviour, and their context cost, with no way to take one without the
other. Two plugins you can enable and disable independently is strictly more
control than one you cannot.

Watch for one interaction. Both libraries auto-trigger on natural language, and
more standing skills means more competition for the same request — if
`crew-setup` stops firing on "set up crew," a broadly-scoped skill from another
plugin is the first thing to check.

---

## Three things this plugin will tell you that you did not ask to hear

1. If review finds nothing, adding roles will not help.
2. If tickets pile up waiting on your review, more agents make it worse.
3. If the code map is stale, the code wins and the map gets deleted.

Those are written into `crew-scaling` and `crew-memory` deliberately. A setup that only agrees with you is the thing you were trying to avoid by adding a review step in the first place.
