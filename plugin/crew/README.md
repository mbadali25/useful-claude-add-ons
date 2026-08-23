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
6. [Build the smoke harness](#6-build-the-smoke-harness--do-not-skip-this)
7. [Teach it the codebase](#7-teach-it-the-codebase)
8. [Verification, secrets, and browser tests](#8-verification-secrets-and-browser-tests)
9. [Research and gap analysis](#9-research-and-gap-analysis)
10. [The daily loop](#10-the-daily-loop)
11. [Configuration reference](#11-configuration-reference)
12. [Optional: Codex as reviewer](#12-optional-codex-as-reviewer)
13. [Optional: Jira via MCP](#13-optional-jira-via-mcp)
14. [Optional: Obsidian for memory](#14-optional-obsidian-for-memory)
15. [Optional: Teams and Telegram notifications](#15-optional-teams-and-telegram-notifications)
16. [Diagrams](#16-diagrams)
17. [AWS and Azure MCP](#17-aws-and-azure-mcp)
18. [Growing the crew](#18-growing-the-crew)
19. [Command and agent reference](#19-command-and-agent-reference)
20. [Troubleshooting](#20-troubleshooting)

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

Both hook sets ship. The bash hooks match the `Bash` tool; the PowerShell hooks
match the `PowerShell` tool and carry `shell: powershell`. The bash hooks also
stand down if they detect MSYS or Cygwin, so the two sets cannot both act on the
same command.

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

This walks eight phases, **stopping after each one** so you can check the result
before the next thing is built on it. It is resumable — `/crew:init --status`
shows where you are, and it picks up from the first incomplete phase.

| # | Phase | Produces |
|---|---|---|
| 0 | Platform | OS/WSL detection, CRLF and filesystem fixes |
| 1 | Config | `.crew/`, `.work/`, a filled-in `CLAUDE.md` |
| 2 | Providers | Codex and Gemini verified by a real call |
| 3 | Smoke harness | `scripts/smoke.sh` green from a clean checkout |
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
3. Create `.crew/`, `.work/`, `scripts/smoke.sh`, `docs/adr/`, and a `CLAUDE.md` if none exists
4. Tell you plainly that the setup is not yet usable

Commit all of it. `.work/` belongs in version control — it is the shared memory between sessions, and a session that cannot read it starts blind.

**Fill in the `CLAUDE.md`.** The template leaves blanks on purpose: build and test commands, where the entry point lives, which directories are off limits, and the landmine that breaks every time someone touches it. Thirty lines beats three hundred, because every line is re-read on every delegation.

---

## 6. Build the smoke harness — do not skip this

At this point `scripts/smoke.sh` exists but contains no checks, so the gate passes vacuously. The crew has no safety net.

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
    { "paths": ["src/Api/**"], "run": ["dotnet test tests/Api", "./scripts/smoke.sh"],
      "why": "Domain changes break API contracts" },
    { "paths": ["**/*.css", "src/components/**"], "run": ["npx playwright test --grep @visual"],
      "why": "Style changes are invisible to API tests" },
    { "paths": ["migrations/**"], "run": ["./scripts/_smoke/migrate-fresh.sh"],
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
  "verifyGate": true
}
```

| Key | Values | Effect |
|---|---|---|
| `notify.provider` | `teams`, `telegram`, `none` | Outbound notifications. Credentials come from env vars, never config. |
| `secondOpinion.provider` | `gemini`, `local`, `none` | Design partner. `sendsCode` stays `false` on any free tier. |
| `qa.provider` | `auto`, `codex`, `claude` | `auto` prefers Codex, falls back to Claude, announces which ran. `codex` fails loudly instead of falling back. |
| `tracker` | `files`, `jira` | Where tickets live. Jira additionally requires the MCP connector. |
| `memory.mode` | `repo`, `obsidian` | Where the code map lives. `obsidian` also needs `vaultPath`. |
| `verifyGate` | `true`, `false` | Whether the `Stop` hook blocks on failed checks. Set `false` only while first building the harness. |
| `tier` / `roles` | see §18 | Which agents are in play. Managed by `/crew:scale`. |

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

## 16. Diagrams

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

## 17. AWS and Azure MCP

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

## 18. Growing the crew

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

## 19. Command and agent reference

### Commands

| Command | Purpose |
|---|---|
| `/crew:ticket <description>` | Scope a request into a ticket |
| `/crew:work <id>` | Work one ticket end to end |
| `/crew:review` | Independent QA — Codex or Claude fallback |
| `/crew:onboard [--refresh <area>]` | Build or refresh the code map |
| `/crew:init` | Guided phased setup, resumable |
| `/crew:plan <decision>` | Independent design opinion before building |
| `/crew:diagram <type>` | Architecture, data-flow, process and sequence diagrams |
| `/crew:verify` | Build or refresh the change-to-check map |
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
| `guard.sh` | `PreToolUse` on Bash | Blocks `terraform apply`/`destroy`, destructive DDL, force push, hard reset, prod-targeted commands, and any command that would print a secret value into the transcript |
| `verify-gate.sh` | `Stop` | Runs the checks the changed paths map to; fails the turn on red, or on a changed path with no rule |
| `guard.ps1` / `verify-gate.ps1` | same events, `PowerShell` tool | Native Windows equivalents, registered with `shell: powershell` |
| `notify.sh` | `Notification`, plus called by commands | Outbound one-line message to Teams or Telegram. Never reads. |

Hooks are deterministic. That is their whole value — a hook cannot be argued out of blocking `terraform apply`, and an agent can.

---

## 20. Troubleshooting

| Symptom | Likely cause |
|---|---|
| Commands do not appear | Plugin not installed, or needs `/reload-plugins`. Check `/help`. |
| Agents ignore `CLAUDE.md` rules | The built-in Explore and Plan agents skip `CLAUDE.md` by design. Restate critical constraints in the delegation prompt. |
| Smoke gate never fires | `scripts/smoke.sh` is not executable, has no checks, or `smokeGate` is `false`. |
| Review always returns CLEAN | Empty diff, wrong base branch, or `codex` silently missing. Check which reviewer the command reported. |
| Jira connection fails | Using the retired `/v1/sse` endpoint, or the server was never approved via `/mcp`. |
| Context fills fast anyway | `CLAUDE.md` has grown. Every line is multiplied across every delegation. Cut it back to a routing table. |
| Gate says "unmapped changes" | Working as intended. Add a rule to `.crew/verify.json` for that path, or mark it deliberately unchecked. |
| Visual tests fail after an unrelated change | Baselines are stale or a dynamic region is unmasked. Regenerate deliberately with `--update-snapshots`, never automatically. |
| A secret read is blocked | Capture it into an env var rather than printing it: `export X=$(aws secretsmanager get-secret-value ... --output text)`. |
| Teams webhook returns 404 or 410 | An old Office 365 Connector URL. Those were disabled in May 2026 — recreate it via Workflows. |
| Telegram `getUpdates` returns nothing | You have not messaged the bot yet. A bot cannot open the conversation. |
| Notifications stopped with no error | The Teams Workflow runs under its creator's account. Check whether they left or lost the licence. |
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
