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
13b. [Optional: ServiceDesk Plus via MCP](#13b-optional-servicedesk-plus-via-mcp)
13c. [Optional: an Obsidian Kanban board](#13c-optional-an-obsidian-kanban-board)
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
24. [The emergency lane](#24-the-emergency-lane)
25. [Command and agent reference](#25-command-and-agent-reference)
26. [Troubleshooting](#26-troubleshooting)

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

### The platform block fixes itself

`.crew/config.json` is committed, and its `platform` block describes the machine
that ran `/crew:init`. The moment it lands in git it is wrong for everybody else
— and `windowsHostIp` is wrong for the same person after a reboot, because WSL2's
gateway changes.

So a `SessionStart` hook repairs it. Open the repo on Windows after someone
committed it from WSL and the first thing the session says is:

```
## platform - config said linux, this is windows-bash; updated 5 field(s) in .crew/config.json
- platform.distro: 'Ubuntu' -> ''
- platform.os: 'linux' -> 'windows-bash'
- platform.windowsHostIp: '172.24.16.1' -> ''
- platform.wsl: 'yes' -> 'no'
- platform.wslVersion: '2' -> ''
```

**One rule makes this safe: it writes derived facts and nothing else.**

| | |
|---|---|
| Rewritten | `os`, `wsl`, `wslVersion`, `distro`, `shell`, `repoFilesystem`, `windowsHostIp` — every one an answer to "what machine is this", which nobody hand-edits usefully |
| Reported, not changed | a preference this OS cannot honour: an `autoClear.method` that only exists on the other platform, a clone under `/mnt/`, CRLF in a committed `.sh` |
| Never touched | everything else. `tracker`, `qa`, `roles`, `tier`, `notify`, `emergency`, the context thresholds, `verifyGate`. If a human chose it, it stays chosen |

That split is the whole design, and it is why this hook is allowed to write when
the PM is report-only. The PM's subject is *judgement* — whether a role earns its
context is not a fact. `platform.os` is a fact, it is wrong on the other machine,
and being asked about it once per clone would be worse than having it fixed.

It never writes when nothing changed, so it does not dirty your tree on every
session, and it preserves the file's existing line endings — rewriting a
LF config as CRLF would show up as a whole-file diff for everyone else.

**Both flavours delegate to one python module** (`hooks/scripts/crew_platform.py`)
rather than reimplementing detection twice. For a hook that writes config, two
implementations that disagree about what they write is the last thing you want —
and the `.sh`/`.ps1` pair here has drifted for a whole release before.

A read-only checkout, or no python at all, means it says what it *would* have
changed and changes nothing.

### The config heals itself

The same hook also recreates `.crew/config.json` itself, not just its
`platform` block, when the file has gone missing or stopped parsing —
a half-finished merge, a bad rebase, or an edit interrupted mid-save all
leave a repo that *looks* like a crew repo (the `.crew/` directory is right
there) but whose switchboard is gone or unreadable.

**CRITICAL GUARD: this only ever acts where `.crew/` already exists.** A
plain git repository that happens to be open when the hook runs is not
touched — `.crew/` absent means "not a crew repo," full stop, and the hook
must never create one just because a session started there.

Given a `.crew/` directory, three cases:

| `.crew/config.json` | What happens |
|---|---|
| Missing, or present but empty | Written fresh from the same template `/crew:init` uses. No backup — there is nothing to lose. |
| Present, non-empty, but does not parse as a config object | Copied aside to `config.json.broken` first (a previous `.broken` file from an earlier bad session is never overwritten — the first failure is still the best chance at recovery), then written fresh. |
| Present and parses as an object, however unusual | Untouched, byte for byte. This heals a config that **is not one** — it does not validate or judge one that already is. |

Either way the session says so, in one line:

```
## config - .crew/config.json was malformed; backed it up to .crew/config.json.broken and wrote defaults - tracker, roles, and every other choice are back to defaults; run /crew:init to re-record them
```

**Recreating the file means every human choice in it is gone** — `tracker`,
`roles`, `tier`, whichever Jira project or Obsidian vault was configured, all
of it, back to defaults. `platform-sync` cannot know what those choices were;
only `/crew:init` can put them back, which is why the message says to run it.
This trades a working-but-defaulted repo for a broken one, not a perfectly
restored one.

The default config itself has one source: `hooks/scripts/crew_config.py`'s
`default_config()`. `templates/config.template.json` (what `/crew:init`
copies down) and this heal path both call it, and a committed test asserts
the template equals its output byte-for-byte — so the two can never quietly
drift apart the way a hand-maintained template and a hand-maintained heal
path eventually would.

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

Verify with `/help` — you should see `/crew:ticket`, `/crew:work`, `/crew:review`, `/crew:onboard`, `/crew:scale`, `/crew:pm`, `/crew:upgrade`, and `/crew:jira-sync`.

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
| 6 | Browser tests | Playwright specs passing with no agent attached, or `n/a` |
| 8 | Promotion gates | `promote-gate.sh` and `verify-gate.sh` armed; `.work/PROMOTIONS.md` |
| 7 | First ticket | One real loop, end to end |

The rows are in run order, which is why 8 sits above 7 — First ticket runs
last, and the numbers do not match the order. Seven of the nine phases carry a
gate that stops the sequence: Phase 4 does not, and Phase 7 is last so there is
nothing after it to stop. Just one of those gates is enforced by a hook rather
than written down. See
[Setup phase order](../PLUGINS.md#setup-phase-order) in `PLUGINS.md` for the
sequence diagram, every gate, and why the order is what it is.

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
      "agents": ["dba"], "why": "Fresh-apply catches ordering bugs" },
    { "paths": ["**/*.ps1"], "run": ["pwsh -NoProfile -Command \"Invoke-ScriptAnalyzer -Path . -Recurse -EnableExit\""],
      "agents": ["powershell-security-hardening"], "why": "runs with real privilege; a linter sees style, not blast radius" }
  ],
  "always": ["npm run lint"],
  "unmapped": "fail"
}
```

This is a data file a hook reads, deliberately not knowledge an agent carries.
Agent judgment about which tests to skip is exactly the judgment that skips the
important one, confidently, on the turn it mattered.

`agents` names **any installed subagent**, not only crew's eleven. That last rule
names one crew does not ship. A bare name resolves to crew's own role first
(`security` → `crew:security`), then to any other installed agent of that name;
namespace it when you mean the other one. This is how a machine's domain
specialists get pulled in *by path match* rather than when somebody remembers
they exist — the change touches `.tf` under `iam/`, so the IAM auditor reviews it,
every time, without being asked.

The safeguard matters as much as the feature. `.crew/verify.json` is committed
and travels between machines, so a rule naming an agent the author has and a
teammate does not would quietly review less on the second machine while producing
output that looks identical. `/crew:review` therefore reports a named-but-missing
agent as a gap and logs it to `.crew/metrics.md`, so "this rule asked for
`security-auditor` eleven times and never got it" becomes evidence for either
installing it or deleting the rule.

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

Everything reads `.crew/config.json`. If it goes missing or stops parsing,
`platform-sync` recreates it from `templates/config.template.json` the next
time the repo is opened — see "The config heals itself" in §3; this is the
same shape that produces:

### Global config, and how it layers with the repo file

An optional machine-global file at `~/.claude/crew/config.json` sets defaults
for every crew repo on this machine, without hand-editing each one. Three
layers, lowest precedence first:

| Layer | Source | Written by |
|---|---|---|
| Built-in defaults | `hooks/scripts/crew_config.py`'s `default_config()` | Nothing — this is code, not a file |
| Global | `~/.claude/crew/config.json` | `/crew:config` — a guided walkthrough that shows the plan first and writes only after a yes. It is also the only thing in crew that writes outside the repository. Hand-editing still works. |
| Repo | `.crew/config.json` | `/crew:init` (first write); `platform-sync` (the `platform` block, and the whole file when it heals — see §3) |

Repo overrides global overrides built-in defaults, merged recursively with
`crew_state.merge_defaults` — the same policy `/crew:upgrade` uses to bring a
v1 config's `pm` and `graph` blocks forward: a nested override wins, a scalar
where a dict belongs is discarded rather than corrupting the block under it.
`crew_config.resolve_config(root)` is the one place that computes this; every
reader that wants *effective settings* calls it rather than reading
`.crew/config.json` directly.

Two things never go through this layering, on purpose:

- **`schema`** is a fact about the repo file's own layout version, not a
  setting — it is read straight from `.crew/config.json`, never merged. The
  built-in-defaults layer always reports the current schema, so merging it
  would make an unmigrated `v1` repo (no `schema` key at all) look current
  the moment *any* global file exists on the machine.
- **The `platform` block and the heal path both write only the repo file.**
  `platform-sync` never reads or writes the global file, and recreating a
  missing or broken `.crew/config.json` always writes plain built-in
  defaults — never a merge that could smuggle a global preference into a
  file every teammate who clones the repo will also read.

### `/crew:config` — see where a value comes from, and set the global file

```
python3 hooks/scripts/crew_config.py --root . --explain        # value + source
python3 hooks/scripts/crew_config.py --root . --check-global   # what is wrong
python3 hooks/scripts/crew_config.py --set pm.authority='"act"'          # dry run
python3 hooks/scripts/crew_config.py --set pm.authority='"act"' --apply  # write
```

`--explain` prints every globally-settable key with its effective value and
the layer that decided it. That column is the point. The reason this command
exists is a machine where the global file carried `tier`, `roles`, `qa` and
`sdp` but **no `pm` block**, so every repo on it resolved to
`pm.authority: report-only` while the user believed the PM was autonomous.
Every file was valid; nothing surfaced the discrepancy. `/crew:upgrade` now
runs `--check-global` and reports the same findings.

Four rules the script enforces rather than documents:

- It **merges**. A key in an existing global file that the walkthrough never
  asked about survives untouched.
- It **refuses** any key outside `default_global_config()`, by name, exit 2.
  That keeps repo facts (`tracker`, `jira.project`, `graph.out`, `platform`,
  `tier`, `roles`) out of a file every repo reads — and it is what makes
  `graph.obsidian.confirmed` un-grantable from a guided flow: it is consent to
  write into your own notes outside the repo, not a capability.
- It is a **dry run by default**. `--apply` is a second, deliberate call.
- It marks a widening of `pm.authority` with a `!` line, on both the dry run
  and the write. That value is the one a user cannot recover from by noticing.

`templates/global.template.json` is the shape, and a committed test asserts it
equals `default_global_config()` byte-for-byte — the same drift gate the repo
template has. It is deliberately not a copy of the repo template: it carries
only what is a property of the machine or the person (`pm.authority`, `qa`,
`dev`, `secondOpinion`, `notify`, `memory.vaultPath`), and no `schema`.

A global file that is missing, empty, or fails to parse is treated exactly
like an absent one — the same reasoning `_read_config_strict` documents for
the repo side — so a typo in your global config degrades one repo's settings
to defaults rather than breaking every session on the machine.

This is the same shape that produces:

```json
{
  "schema": 2,
  "tier": 0,
  "roles": ["explorer", "qa-reviewer"],
  "qa": { "provider": "auto" },
  "secondOpinion": { "provider": "gemini", "mode": "cli", "model": "gemini-2.5-flash", "sendsCode": false },
  "tracker": "files",
  "jira": { "cloudId": null, "project": null },
  "sdp": { "portal": null, "noteVisibility": "private", "closeOnDone": false },
  "obsidian": {
    "vaultPath": null,
    "boardDir": null,
    "board": "Board.md",
    "columns": {
      "backlog": "Backlog",
      "ready": "Ready",
      "inProgress": "In Progress",
      "review": "Review",
      "done": "Done"
    }
  },
  "memory": { "mode": "repo", "vaultPath": null },
  "verifyGate": true,
  "context": {
    "enabled": true,
    "warnAt": 0.8,
    "budgetTokens": null,
    "reserveTokens": 100000,
    "handoffPath": ".work/HANDOFF.md",
    "autoClear": { "enabled": false, "method": "auto", "windowTitle": null, "command": "/clear", "delaySeconds": 3, "minHandoffLines": 5 },
    "autoWrapUp": false,
    "autoResume": false
  },
  "emergency": { "standDown": true, "ttlMinutes": 120, "maxTtlMinutes": 480 },
  "notify": {
    "provider": "none",
    "events": ["gate", "review", "waiting"],
    "urlEnv": "CREW_TEAMS_WEBHOOK",
    "tokenEnv": "CREW_TELEGRAM_TOKEN",
    "chatId": null
  },
  "pm": { "enabled": true, "mode": "adaptive", "quietLines": 8, "maxLines": 40, "authority": "report-only", "maxDispatches": 3 },
  "graph": { "out": "graphify-out", "obsidian": { "dir": null, "layout": "flat", "confirmed": false } }
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
| `schema` | integer | Config layout version. Absent means a pre-PM (`v1`) setup — `/crew:upgrade` brings it to the current schema (2). Never hand-edit this; `/crew:upgrade` sets it. |
| `verifyGate` | `true`, `false` | Whether the `Stop` hook blocks on failed checks. Set `false` only while first building the harness. |
| `context.enabled` | `true`, `false` | The `Stop` context watch. **Absent block = off.** |
| `context.warnAt` | `0.0`–`1.0` | Fraction of budget at which the handoff is requested. Default `0.8`. |
| `context.budgetTokens` | integer or `null` | `null` (the default) works the window out from the model id and this session's own peak usage. Set a number to pin it. |
| `context.reserveTokens` | integer (default `100000`), or `0`/`null` for off | Headroom floor. The warning fires at the **later** of `warnAt` and this many tokens remaining, so it can only ever delay it. Without this, 0.8 of a 1M window asks for a handoff with 200k still free. See §16. |
| `context.handoffPath` | path | Where the handoff note lives. Default `.work/HANDOFF.md`. |
| `emergency.standDown` | `true` (default), `false` | Whether `/crew:emergency` may stand the `verify` and `promote` gates down. `false` keeps them gating; the incident is still declared, recorded and briefed. The command guard never stands down either way. See §24. |
| `emergency.ttlMinutes` | integer (default `120`) | How long a declared incident lasts before it expires on its own and the gates come back. |
| `emergency.maxTtlMinutes` | integer (default `480`) | Ceiling on one `extend`, measured from now, so repeated extensions cannot drift into a permanent state. |
| `notify.provider` | `teams`, `telegram`, `none` | Outbound notifications. **Absent block = off.** Credentials come from env vars, never config. |
| `notify.events` | subset of `phase`, `gate`, `review`, `waiting`, `done` | Which events send. Empty or absent sends everything; a channel that pings constantly gets muted within a week. |
| `notify.urlEnv` / `notify.tokenEnv` | env var **name** | The name of the variable holding the webhook URL or bot token — never the value itself. |
| `notify.chatId` | string | Telegram only. Group ids are negative; that is normal. |
| `secondOpinion.provider` | `gemini`, `local`, `none` | Design partner. `sendsCode` stays `false` on any free tier. |
| `qa.provider` | `auto`, `codex`, `claude` | `auto` prefers Codex, falls back to Claude, announces which ran. `codex` fails loudly instead of falling back. |
| `tracker` | `files`, `jira`, `sdp`, `obsidian` | Where tickets live. `jira` and `sdp` each additionally require their MCP connector; without it every ticket command stops on the same missing precondition. `obsidian` requires no connector — its precondition is a vault directory that exists on this machine. |
| `obsidian.vaultPath` | path or `null` | The vault holding the board. `null` falls back to `memory.vaultPath`, so one vault needs one setting. |
| `obsidian.boardDir` | path relative to the vault | Where the board and its ticket notes live. `Boards/<repo>` by default — one folder per repo, so cards can be `[[T-0042]]` wikilinks that resolve. |
| `obsidian.board` | filename (default `Board.md`) | The board file inside `boardDir`. |
| `obsidian.columns` | five lane names | Maps crew's statuses to the board's headings. Rename lanes here rather than on the board, so an existing board keeps working. A named lane that is absent is a setup error, not a lane to create. |
| `sdp.noteVisibility` | `private` (default), `public` | Whether the push note lands on the requester-visible thread. Private by default because a requester is often not an engineer. |
| `sdp.closeOnDone` | `true`, `false` (default) | Whether completing a ticket closes the request or only transitions it. `false` leaves closure to whoever owns the queue. |
| `sdp.portal` | string or `null` | Only needed where the connector serves more than one SDP instance. |
| `memory.mode` | `repo`, `obsidian` | Where the code map lives. `obsidian` also needs `vaultPath`. |
| `tier` / `roles` | see §22 | Which agents are in play. Managed by `/crew:scale`. |
| `context.autoWrapUp` | `true`, `false` (default `false`) | At `warnAt`, instructs the session to reach a stopping point and write the handoff, instead of just asking. The `/clear` itself stays manual either way — no hook can trigger one. See §16. |
| `context.autoResume` | `true`, `false` (default `false`) | Opens the next `SessionStart` already holding the last handoff as `additionalContext`. See §16 — read the limitation before enabling it. |
| `context.autoClear.enabled` | `true`, `false` (default `false`) | **Experimental.** Types `/clear` into the terminal once the handoff is written. Read §16's "Auto-clear" before enabling — it presses a key on your behalf. |
| `context.autoClear.method` | `auto`, `tmux`, `xdotool`, `wtype`, `windows`, `none` | How the keystroke is delivered. `tmux` is the only one that targets its destination exactly; the rest depend on window focus. |
| `context.autoClear.windowTitle` | string or `null` | Required for every method except `tmux`. Without it those methods refuse rather than typing into an unidentified window. |
| `context.autoClear.command` | string (default `/clear`) | What gets typed. `/compact` is the other sensible value. |
| `context.autoClear.delaySeconds` | integer (default `3`) | How long to wait for the prompt to come back before typing. |
| `context.autoClear.minHandoffLines` | integer (default `5`) | Refuse to clear if the handoff has fewer non-blank lines than this. A stub note is worse than no clear. |
| `pm.enabled` / `mode` / `quietLines` / `maxLines` | see `crew-pm` skill | Whether and how verbosely the `SessionStart` PM brief speaks, and whether the `Stop` pulse re-engages it at all. |
| `pm.authority` | `report-only` (default), `act` | What the PM does about what it finds. `report-only` recommends and stops. `act` lets it dispatch crew roles and refresh diagrams on its own — see the `crew-pm` skill for the guardrails that bound it. An unrecognised value resolves to `report-only`: a typo in a permissions field must fail closed. |
| `pm.maxDispatches` | integer (default `3`) | Roles the PM may dispatch in one pass under `act`. Blockers it hits mid-task do not count against it. |
| `graph.out` | path (default `graphify-out`) | Where `graphify` wrote `graph.json`. Freshness is read from graphify's own `built_at_commit` field in that file, never a timestamp. |
| `graph.obsidian.dir` | path or `null` | Export target directory. What it means depends on `graph.obsidian.layout` — see `crew-graph`'s Obsidian section. |
| `graph.obsidian.layout` | `flat` (default), `org/repo` | How the skill asks you to structure `graph.obsidian.dir`. `flat`: `dir` is the export target verbatim, e.g. `<vault>/codegraphs/<repo>/` — unchanged from before this key existed. `org/repo`: `dir` is a per-org folder, e.g. `<vault>/<org>`, and the skill appends `/<repo>`. |
| `graph.obsidian.confirmed` | `true`, `false` (default `false`) | Consent gate for exporting the graph into an Obsidian vault. Only explicit consent given in session sets this — `/crew:upgrade` never grants it. See `crew-graph`'s Obsidian section. |

The promotion sequence lives in `.crew/verify.json`, not here — see §23. Config
holds preferences; `verify.json` holds the checks, so that one file answers "what
runs when" for both a working tree and a deployed environment.

---

## 12. Optional: Codex as reviewer, Gemini as design partner

A different model reviewing is real independent review. The same model family reviewing itself agrees with itself more than it should, because the author's reasoning is exactly the reasoning it finds persuasive.

Put `codex` on your `PATH` and set `qa.provider` to `auto` or `codex`. `/crew:review` writes the diff to a file, has Codex return one line per defect, and reads only the findings back — the diff never re-enters your context.

`auto` is the shipped default, so a machine with `codex` installed gets Codex review without configuring anything.

Without Codex, `/crew:review` walks `qa.order` — `["codex", "copilot", "claude"]` by default — and takes the first provider that probes clean, announcing every one it skipped and why.

GitHub Copilot is the middle rung, and it earns its place for one reason: it is a gateway to model families nothing else here reaches. Pin `qa.copilot.model` to a Google model such as `gemini-3.7-flash` and the reviewer is genuinely independent of both the author and Codex. Confirm the name against Copilot's current catalog rather than copying one from documentation - the names churn, and a stale one fails at startup with `Model "<name>" from --model flag is not available`. Leave it unset and Copilot is **skipped entirely** — its own default is `claude-sonnet-4.6`, the author's family, so an unpinned Copilot would be a same-family review wearing an independent one's costume. That is worse than the fallback below, which at least admits what it is.

Last is the `qa-reviewer` agent — on `opus`, in its own context window, so it has at least not seen the reasoning that produced the code. Its prompt tells it outright that it shares a model family with the author and must compensate: ask "what input makes this wrong" before "does this look correct." That is genuinely weaker than a different family, and the command says so every time it happens, so you know to review harder yourself. It also says so itself if something dispatches it directly and skips the provider walk.

Two knobs on the Codex rung, both read at call time and both passing no flag when null, so an upgraded repo behaves exactly as it did before: `qa.codex.model` pins a model, and `qa.codex.reasoningEffort` takes `none`, `minimal`, `low`, `medium`, `high`, `xhigh` or `max`. A wrong effort value is safe to get wrong — Codex rejects it with a 400 naming the supported set rather than quietly returning a shallower review.

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

## 13b. Optional: ServiceDesk Plus via MCP

Same bargain as Jira, a different desk, and one extra category of care.

`tracker: "sdp"` plus a reachable ServiceDesk Plus MCP connector (tools named
`sdp_*`). Crew ships no `.mcp.json` for it: the SDP connector is normally
registered at user or session scope, and a per-repo one would prompt for
approval in every repository where the plugin is enabled. If the tools are not
there, `/crew:sdp-sync` says so and stops rather than quietly writing a file
ticket — a silent fallback splits the source of truth and nobody notices until
two people are working from divergent state.

**The local key is `SDP-<id>`, not the bare request number.** SDP request ids are
plain integers, and the rest of crew recognises a ticket by its `LETTERS-digits`
shape — so a bare `40219` is invisible to the session brief, to `/crew:work`, and
to the index. `/crew:sdp-sync` accepts either form and always writes `SDP-40219`.

The caching argument is identical to Jira's: a request payload runs thousands of
tokens across resolution HTML, the full note history, SLA timers, approvals and
every UDF the desk has ever defined, and about forty of them affect what you
build. `/crew:sdp-sync` keeps id, subject, status, requester, priority, category
and the last three notes, and `/crew:work` reads that file instead of the API.

**What is different from Jira, and worth knowing before the first write:**

| | Why it matters |
|---|---|
| Notes are requester-visible unless private | A requester is often not an engineer. `sdp.noteVisibility` defaults to `private`, and that is not a substitute for scrubbing: hostnames, credentials and internal addresses do not belong in a desk record either way. |
| A bad field value rejects the *whole* write | SDP does not partially apply an update. Resolve status, category and priority against `sdp_list_metadata` first and send what the desk accepts, not what the local ticket happens to call it. |
| Closing is somebody's job, not crew's | `sdp.closeOnDone` defaults to `false`: push transitions the request and leaves closure alone. Set it `true` only for a queue that is genuinely yours, and let `sdp_close` do it — it goes through the desk's closure endpoint and satisfies mandatory closure fields, which a faked `sdp_update` does not. |
| A failed write is gone | There is no local outbox. If a note fails it is not queued anywhere; re-read with `sdp_get` before retrying so a partial success is not duplicated. |

The writes act as the signed-in user, so the desk's audit trail names a person
rather than "an automation". `sdp_whoami` tells you which person, and is the
cheapest way to prove the connector is live before configuring a repo around it.

---

## 13c. Optional: an Obsidian Kanban board

The fourth tracker, and the only one with nothing to connect to. `tracker:
"obsidian"` plus a vault path that exists. The board is a markdown file the
[Kanban plugin](https://github.com/mgmeyers/obsidian-kanban) round-trips, so
crew writes files and Obsidian draws a board — there is no API, no auth, and no
payload to amortise.

```
vault/
  Boards/<repo>/
    Board.md          # kanban-plugin: board
    T-0042.md         # the ticket note
    T-0041.md
```

The vault is the remote, exactly as Jira is: `.work/cache/T-####.md` is a terse
local mirror that `/crew:work` reads, and `/crew:obsidian-sync` touches the
vault at pickup and completion only. The key keeps the `T-####` shape, so
nothing else in crew needed a new format to recognise.

**Unlike Jira and ServiceDesk Plus, this mode also keeps `.work/INDEX.md`.**
The session brief finds the open ticket by reading that file, and a key shaped
`SDP-40219` was never going to be in it — `T-0042` can be. So the board is the
human's view of the work and `INDEX.md` is the session's, which costs one line
per ticket and is why the brief names a real ticket here rather than nothing.

**Five lanes, and dragging a card is how status changes.**

| Lane | Means |
|---|---|
| Backlog | Deferred or untriaged. Where the PM parks a non-blocking finding. |
| Ready | Scoped by `/crew:ticket` and pickup-able. |
| In Progress | `/crew:work` has it. |
| Review | Implementation done, `/crew:review` outstanding. |
| Done | Complete and verified. Carries the `**Complete**` marker. |

On pull the card's lane wins for status and the note wins for content; on push
the cache's `status:` names the lane — `--push` takes no lane argument and
infers nothing, so a card cannot land in Done because the turn went well. That rule exists because both sides here are local markdown
and both look equally authoritative — which makes the divergence hazard *worse*
than Jira's, not absent. A silent fallback to file tickets is therefore refused
the same way `/crew:jira-sync` refuses it.

**The board file has three load-bearing parts** and a naive rewrite destroys all
three, after which the file silently opens as plain text instead of a board: the
`kanban-plugin: board` frontmatter, the trailing `%% kanban:settings` block, and
the `**Complete**` marker in the done lane. An archive, when one exists, sits
below a `***` break under `## Archive` and is nobody's business but Obsidian's.
So the board is edited in place, one card or one lane at a time, never
regenerated from the cache.

**Two things to accept before choosing this.** The vault lives outside the repo,
so ticket state does not travel with a branch and is not on a colleague's
machine — that is the trade for a board you can drag cards on. And crew never
commits the vault; if it is versioned, its history is yours to manage, and a
board edited in two places at once conflicts the way any markdown file does.

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

### The threshold is a measurement

No hook input reports token count, but the JSONL transcript that hooks receive
as `transcript_path` carries `message.usage` on every assistant turn, and the
last one is the real prompt size. Both `context-watch` flavours read that. The
window comes from the model id (Claude 5 family 1M, Haiku and the 4.x
generation 200k) and is corrected upward by the session's own peak usage, so a
`[1m]` variant that recorded its base id still gets the right budget. Subagent
transcripts live in separate files and are never counted. `budgetTokens` stays
`null` unless you have a reason to pin it - a stale `200000` from an older
`/crew:init` is the one thing that still makes the gate fire early.

It fires **once per session**, gated by a marker file that `SessionStart`
clears. Without that gate, a `Stop` hook returning exit 2 fires every turn and
traps the session in a loop. The marker is claimed atomically (`noclobber` in
bash, `FileMode::CreateNew` in PowerShell) because on Windows with Git Bash
installed both flavours really do run on the same `Stop`, and a
test-then-create lets both through.

### Two rules, and the later one wins

`warnAt` alone was tuned when every window was 200k, where 0.8 leaves 40k — about
enough to finish a thought and write the note. The same 0.8 on a 1M window
leaves **200,000 tokens** unused and still asks you to wrap up: a whole 200k
session's worth of room thrown away. That is the "it ends a bit earlier than it
should" complaint, and a percentage cannot fix it, because the right amount of
headroom is an absolute number, not a fraction.

So the threshold is the **later** of:

| Rule | Threshold | Wins on |
|---|---|---|
| percentage | `warnAt × budget` | small windows — 0.8 of 200k = 160k, leaving 40k |
| headroom | `budget − reserveTokens` | large windows — 1M − 100k = 900k, i.e. 90% |

Taking the later of the two means `reserveTokens` can only ever push the
warning **later**, never earlier. A 200k repo behaves exactly as it did; a 1M
session gets the extra 100k it was being denied. Set
`context.reserveTokens: 0` for the old pure-percentage behaviour, and note that
`warnAt: 0` still means "fire immediately" — the floor does not outrank the
one explicit override.

The warning names which rule fired, with absolute numbers on both, so a
threshold that behaves oddly is visible rather than mysterious.

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

### Auto-wrap-up is off by default

`context.autoWrapUp` changes what the `Stop` hook says at `warnAt`, not
whether it fires. Off (the default), it just asks you to write the handoff.
On, it instructs the session to reach a stopping point — finish or safely
abandon the change in flight, write the handoff, update the ticket — before
telling you it's ready. **Either way, the `/clear` itself stays manual**,
because no hook can trigger one: hooks run as child processes, and a child
cannot reset its parent's conversation. `autoWrapUp` bounds what happens
before you clear; it does not remove the clear.

### Auto-clear (experimental, off by default)

The correction at the top of this section stands: a hook cannot clear the
conversation, because a hook is a child process and a child cannot reset its
parent. `context.autoClear` does not contradict that. It does something else —
it drives the **terminal**, typing `/clear` at the prompt the way you would.

That is why it can work, and also why it is experimental: typing into a terminal
is only safe if you know *which* terminal, and the available methods answer that
question with very different confidence.

| Method | How it finds the target | Confidence |
|---|---|---|
| `tmux` | `$TMUX_PANE`, by pane id | **Exact.** No focus involved. Use this if you can. |
| `xdotool` | window title, then activates it | Steals focus. Right window if the title is right. |
| `wtype` | types into whatever has focus | None. Wayland offers no way to check. Needs `unsafeFocus: true`. |
| `windows` | SendKeys, title-checked at send time | Right window *if it still has focus* when the delay expires. |

```json
"context": {
  "autoClear": {
    "enabled": false,
    "method": "auto",
    "windowTitle": null,
    "command": "/clear",
    "delaySeconds": 3,
    "minHandoffLines": 5
  }
}
```

**In tmux this needs no configuration beyond `enabled: true`.** Everywhere else
it needs `windowTitle`, and refuses without it rather than guessing.

#### What has to be true before it types anything

1. `context.autoClear.enabled` is exactly `true`. The string `"true"` is not.
2. `context-watch` actually asked for a handoff this session.
3. The handoff file exists and is **newer** than that request — a leftover note
   from a previous session is not this session's note.
4. It has at least `minHandoffLines` non-blank lines. Clearing on a two-line
   placeholder loses the session's work and leaves a note that says "continue
   the work", which is the worst of both outcomes.
5. Nothing has claimed the one-per-session attempt yet.

Fail any of those and it writes a line to `.crew/.autoclear.log` saying which,
and does nothing. That log exists because a `Stop` hook's stderr is invisible
when it exits 0, so without it "nothing happened" is indistinguishable from
"the feature is broken".

#### The delay, and why it is not zero

The hook runs *while the turn is still ending*, so the prompt does not exist yet
and typing immediately types into nothing. The keystroke is handed to a detached
child that sleeps first. Three seconds is usually enough; raise it on a slow
machine. The parent exits 0 straight away so the turn is not held up.

#### Two ways it can go wrong, stated plainly

- **On Windows, focus is the whole mechanism.** SendKeys goes to the foreground
  window. The child re-checks the title immediately before typing, so alt-tabbing
  during the delay means nothing is sent — but if you alt-tab to *another window
  with a matching title*, that is where `/clear` lands. Keep the title specific.
- **A `/clear` is not undoable.** With `minHandoffLines` set too low, or a
  handoff the session wrote badly, you lose the context and keep a note that does
  not replace it. Watch the first few, and read `.work/HANDOFF.md` before
  trusting the next session to resume from it.

#### Try it without risking anything

```bash
bash   ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/auto-clear.sh --dry-run --force
pwsh -File ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/auto-clear.ps1 -DryRun -Force
```

`--dry-run` prints the method, target, command and delay it *would* use and sends
nothing. `--force` skips the handoff conditions so you can see the plan without
being deep into a session. Neither consumes the one-per-session attempt.

If you run Claude Code in a tmux pane inside WSL, prefer the `.sh` flavour: it
addresses a pane by id and never touches focus, which is strictly safer than
anything the Windows side can do.

### Auto-resume is off by default

`context.autoResume` opens the next `SessionStart` already holding the last
handoff, and I'd leave it off. It is implemented as `additionalContext`, not
`initialUserMessage` — `initialUserMessage` is confirmed only for
non-interactive `-p` invocations, and could not be proven to behave the same
way in an interactive session, so the safer, universally-confirmed field was
used instead. That means enabling it puts the handoff in view at the start of
the next session; **it does not make the session start working on its own.**
A human still reads the note and gives the first turn — which is the one
moment where a subtly wrong handoff gets caught before more work is built on
top of it.

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

### Onboarding and offboarding a role

```
/crew:pm onboard <role>
/crew:pm offboard <role>
```

Growing the crew is a decision, not a command that just runs: `/crew:pm
onboard <role>` names the specific defect class the role closes and confirms
`.crew/metrics.md` actually supports adding it, then stops and asks yes/no
before touching `.crew/config.json` or recomputing `tier`.

Offboarding is the same shape in reverse, and checks a precondition first: the
role has to actually be on the crew. `/crew:pm offboard <role>` reads `roles`
from `crew_state.py`'s output before doing anything else — running the
procedure for a role that was never active would append a real `offboarded
<role>` line to `.crew/metrics.md` for coverage that never existed, and that
file is what `/crew:scale` reads to decide whether the crew is catching
anything. If the role is on the crew, it walks the removal, then states —
out loud, every time — which failure mode the removal leaves uncovered. That
sentence is the point of the command, not a courtesy.

Neither direction ever changes `config.json` on its own. Both need your
explicit yes, no matter how obvious the recommendation looks — see the
`crew:pm` agent's authority rule below.

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
    "rollback":       "none",
    "rollbackReason": "qa is rebuilt from the latest development deploy; there is nothing to roll back to",
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
- `rollback` is set: a runbook that exists and carries `last verified: YYYY-MM-DD` inside 90 days, or the literal `"none"` plus a `rollbackReason` - an absent key blocks the deploy
- `requireHuman` has an approval marker at `.crew/.approved-<env>-<sha>`
- the working tree is clean - you cannot deploy a sha plus uncommitted changes

**Limitation: this enforcement lives in the session, not the repo.** All three
gates - `guard.sh`, `verify-gate.sh`, `promote-gate.sh` - are hooks that run
only inside a Claude Code session with the crew plugin active. A fresh
session that does not have the plugin installed - a teammate who skipped
setup, a different machine, any tool other than Claude Code - gets none of
these guarantees, even though `.crew/verify.json`, `.crew/STATUS.md`, and
this README are all still sitting in the repo looking fully configured.
Nothing here is durable across that boundary except the plugin being active.

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
- **Every gated environment declares a rollback plan, or says why it does not need one.** A verified runbook inside 90 days, or `rollback: "none"` plus a `rollbackReason` - an absent key blocks the deploy. Production without a verified runbook is the one case with no override.
- **A failed gate is a stop.** Roll back or fix forward, then run the whole sequence again from gate 1. Never resume mid-sequence.

### Starting from nothing

Most legacy repos have a deploy script and no post-deploy proof at all. Build it in payoff order, not all at once: `smoke` for the environment you deploy to most; then `verify`, where even `grep -c ERROR` over the last ten minutes beats nothing because it turns "looks fine" into a number; then `regression` last, being the most expensive to build and the least useful until the first two are trustworthy.

---

## 24. The emergency lane

Something is broken in an environment right now. The gates that normally earn
their keep — the `Stop` gate running the changed-files checks, the deploy gate
demanding an all-pass row for this sha — are, for the next twenty minutes,
standing between you and a fix. The honest options are to work around them
silently, or to make standing them down a decision with a record and a clock on
it.

```bash
/crew:emergency prod checkout returning 500 since the 14:02 deploy
/crew:emergency status
/crew:emergency extend 45
/crew:emergency end
```

### What stands down, and what does not

| | During an incident |
|---|---|
| `verify-gate` (`Stop`) | Does not run the checks at all. Records "stop gate stood down with N changed file(s) unverified". |
| `verify-gate`'s deploy-record check | Stands down. Records the deploy that has no `PROMOTIONS.md` row. |
| `promote-gate` (`PreToolUse`) | Still computes every precondition — they are file reads, not test suites — records each one that failed, then allows the deploy. |
| `guard` (`PreToolUse`) | **Unchanged. Still blocks.** |

The guard's exemption from all of this is the point rather than an oversight.
Standing down a check that tells you a change is wrong is a trade you can make
at 03:00; standing down the one that stops a change being *unrecoverable* — a
force push, a destructive Terraform verb, a history rewrite, a secret read into
the transcript — is not a trade, it is just removing the thing you most need
while tired. If the guard is genuinely in the way, run that one command by hand
outside the session.

### It expires on its own

`emergency.ttlMinutes` (default 120) sets the window. Past it, the gates gate
again: they compare an integer epoch, so nothing has to run and no file has to
be touched for normal service to resume. That matters because the realistic
failure here is not declaring an incident when you should not have — nobody does
that during an outage — it is **forgetting to close one afterwards**, and this
design makes that recoverable by default.

`extend` is capped by `emergency.maxTtlMinutes` (default 480) and measured from
now each time, so four extensions cannot compound into a permanently ungated
repository. Eight hours is one shift; past that, the environment is not in an
incident any more, it is in its new normal, and the checks should be back on.

Two honest limits on that clock. It is **wall time**: a machine whose clock is
moved backwards extends the window until real time catches up, which matters for
a badly-skewed VM and not much else - anyone who wants the gates off can set
`verifyGate: false` and not have to be clever about it. And the bash flavour's
stand-down needs a python (`python3`, `python`, or `py`) to parse the state file
strictly - the state has to be *valid JSON*, not merely contain a future epoch,
or `{ not json "expiresAtEpoch": 9999999999` would switch every gate off. With
no python at all it reports no incident and the gates keep gating, which is the
safe direction, but it does mean the lane does nothing on a python-less machine
where the `.sh` half is what runs.

### The debt list is the deliverable

Every skipped gate goes to `.crew/incident-skips.log`, one row per gate and
reason — not one per turn, because the same unrun check is one debt however many
times the gate declined to run it. `/crew:emergency end` turns that into
`.work/INCIDENT-<id>.md`: what did not run, what is owed, and what to verify
before trusting the list. The record is archived under `.crew/incidents/` and
the state file is deleted, which is what puts the gates back.

Then pay it: run the checks that did not run, add the missing `PROMOTIONS.md`
row, and open a ticket per remaining item. A debt list nobody has a ticket for
is a debt nobody pays.

While an incident is open — and after it expires unclosed — every session start
says so. `incidentActive` and `incidentUnclosed` are the two highest-priority PM
triggers, above `upgradeNeeded`, and the line sits in the brief's quiet lines so
no line cap can truncate it away. A session that does not know the gates are off
is a session about to merge unverified work believing it was checked.

### The lanes

Declaring also fans out **read-only** investigation lanes in parallel, each
briefed with the symptom and nothing else:

| Lane | Agent | Question |
|---|---|---|
| change | `explorer` | What shipped in the window before the symptom — commits, deploys, config, flags, migrations? |
| blast radius | `explorer` | What else calls the failing path or shares the resource, and is already broken without knowing? |
| cause | `analyst` | The two or three most probable causes, each with the cheapest observation that would kill it |
| exposure | `security` | Only when the symptom might be an incident of a different kind — auth, data exposure, an unexpected 200 |
| data | `dba` | Only when a database is in the picture — locks, a long transaction, a migration mid-flight, replica lag |

They investigate; they do not fix. Two plausible fixes that both need trying get
a worktree each, so a half-applied one cannot land on top of the other.

### When this is the wrong tool

- **Enforcement is session-local.** An incident stands the hooks down for
  sessions in this repository on this machine. It does nothing to CI, to a
  colleague's machine, or to a branch protection rule. If CI is what blocks the
  fix, this will not help.
- **Some repositories should never do this.** `emergency.standDown: false`
  keeps every gate gating. The incident is still declared, recorded and briefed,
  and the lanes still run — you get the investigation and the paper trail
  without the exemption.

---

## 25. Command and agent reference

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
| `/crew:sdp-sync <REQUEST-ID> [--push]` | Sync one ServiceDesk Plus request with the local cache — see §13b |
| `/crew:obsidian-sync <T-####> [--push]` | Sync one Obsidian Kanban card with the local cache — see §13c |
| `/crew:pm [onboard\|offboard <role>]` | Crew-manager status, or add/remove a role — see §22 |
| `/crew:upgrade [--force]` | Bring a pre-schema-2 (`v1`) setup forward — see §11 |
| `/crew:emergency <what is broken>` | Declare a time-boxed incident: gates stand down and record what they skipped, lanes investigate in parallel — see §24. `status`, `extend [min]`, `end` |
| `/crew:model` | Report the resolved provider and model for every role, and which family would be reviewing which — see §12 |
| `/crew:roster` | Print the crew as configured: roles, tier, and what each one is for |
| `/crew:config [--show]` | Show where every setting comes from, and walk the machine-global config — see §11 |

24 commands.

### Agents

| Agent | Tools | Model | Tier | Role |
|---|---|---|---|---|
| `explorer` | read-only | `sonnet` | 0 | Maps code, returns summaries not contents |
| `qa-reviewer` | read-only | `opus` | 0 | Hostile review; the Codex fallback |
| `security` | read-only | `sonnet` | 1 | Exploitable defects in the diff |
| `smoke-author` | read/write | `sonnet` | 1 | Builds and repairs the safety net |
| `developer` | read/write | `sonnet` | 1 | Implements one scoped change; never reviews it |
| `browser-tester` | read/write | `sonnet` | 2 | Playwright specs, visual baselines, user flows |
| `analyst` | read-only | `sonnet` | 2 | Anchored findings and options, never tickets |
| `planner` | read-only | `sonnet` | 2 | Design second opinion from an abstracted brief |
| `dba` | read-only | `sonnet` | 2 | Migrations, locks, online safety |
| `docs-writer` | read/write | `sonnet` | 2 | Architecture and data flow from real code |
| `infrastructure-architect` | read-only | `sonnet` | 2 | AWS network and account design, with tradeoffs. Never applies to a live account |
| `scribe` | read/write | `sonnet` | 2 | The durable record: ADRs, CHANGELOG entries, handoff notes, and what was rejected |
| `researcher` | read-only + web | `sonnet` | 2 | External research only. Every claim carries its source |
| `pm` | read/write, scoped to `.crew/` and generated diagrams | `opus` | — | The standing manager: scope, onboarding, communication, ticket hygiene, and dispatch |

14 agents. `pm` sits outside the tier ladder — it is not sized in or out by `/crew:scale`, it is the thing doing the sizing.

**Model tiers are part of the design, not a cost knob.** The PM runs on `opus` because it holds the whole project picture and every dispatch decision derives from it — a cheap manager makes cheap assignments and every role below inherits the mistake. Working roles run on `sonnet`: narrow brief, clean context, one deliverable. QA walks `qa.order` (`qa.provider` ships as `auto`) and takes the first provider that probes clean — Codex, then Copilot pinned to a non-Claude model, then `qa-reviewer` on `opus`. The ordering is not a preference ranking; it is a family-diversity ranking. A different model family is what makes review independent, so a provider that would land back on the author's own family is skipped rather than used, and if you cannot have a different family at all, the strongest model in this one is the only compensation left.

`opus` and `sonnet` here are tiers, not pinned versions. Agent frontmatter asks for a tier and gets whatever the session's strongest model at that tier is; there is no way to pin a point release from a plugin.

**The PM is standing.** It is spawned once per session under the name `crew-pm` and stays addressable; `/crew:pm` reaches the existing one with a message rather than spawning a fresh one. That matters because the roles it dispatches each see one slice of the work and are gone — the PM is the only thing that remembers what was decided, what was deferred, who was onboarded, and why. A PM respawned per invocation knows the JSON and nothing else, and a PM that signs off when the queue empties has to be rehired at the cost of the entire project picture. It reports what is outstanding and waits.

**One hat per role, the PM's included.** The PM manages: it assesses scope, onboards and offboards roles, communicates to you and to the crew, and keeps tickets current. It does not write application code, tests, docs, migrations, or reviews — implementation goes to `developer`, review goes through `/crew:review`, and everything else goes to the role that owns it. Its own writes are `.crew/` bookkeeping, ticket text, `TODO.md`, and the generated diagram artifacts its triggers name.

### Hooks

Eight scripts across five events, each with a `.sh` and a `.ps1` twin
registered on its own matcher or event — 16 entries total.

| Script | Event | Behavior |
|---|---|---|
| `guard.sh` / `guard.ps1` | `PreToolUse` on Bash / PowerShell | Blocks `terraform apply`/`destroy`, destructive DDL, force push, hard reset, prod-targeted commands, and any command that would print a secret value into the transcript |
| `promote-gate.sh` / `.ps1` | `PreToolUse` on Bash / PowerShell | Refuses a declared `deploy` command unless the upstream environment has an all-pass row for **this sha**, the rollback runbook is verified inside 90 days, `requireHuman` is approved, and the tree is clean. During an emergency lane it records each unmet precondition and allows the deploy (§24) |
| `handoff-read.sh` / `.ps1` | `SessionStart` | Injects the handoff after clear, compact, or resume |
| `pm-brief.sh` / `.ps1` | `SessionStart` | Runs `crew_state.py`, prints the prioritized PM brief (triggers, health, knowledge, graph freshness) — report-only, changes nothing |
| `platform-sync.sh` / `.ps1` | `SessionStart` | Detects this machine and repairs the `platform` block in `.crew/config.json` — see §3b. The only hook that writes config: the seven derived facts, plus recreating the whole file from defaults when it is missing or malformed (backing up a malformed one first) — never when `.crew/` itself does not exist. See "The config heals itself" in §3 |
| `verify-gate.sh` / `.ps1` | `Stop` | Runs the checks the changed paths map to; fails the turn on red, on a changed path with no rule, or on a deploy that recorded no promotion row. Stands down while an emergency lane is open (§24), recording what did not run |
| `context-watch.sh` / `.ps1` | `Stop` | Measures window occupancy from the transcript; asks for a handoff once per session at the later of `warnAt` and `reserveTokens` remaining, or instructs a wrap-up if `context.autoWrapUp` is on |
| `handoff-write.sh` / `.ps1` | `PreCompact` | Snapshots the transcript, writes a skeleton handoff |
| `notify.sh` / `.ps1` | `Notification`, plus called by commands | Outbound one-line message to Teams or Telegram. Never reads. |

Both flavours are registered **on every event, on purpose** — not because
each fires everywhere, but because `hooks.json` cannot know which shell a
given machine has. On Windows, the `.sh` side can fail outright depending on
which `bash` resolves first on `PATH`: measured, Git for Windows' `usr/bin/bash.exe`
exits 127 on these scripts where its own `bin/bash.exe` runs them fine. The
`.ps1` twin — registered with a `shell: powershell` field, which Claude Code
documents and does read — is what actually gates the machine when that
happens; one flavour failing there is expected, not a bug. The reverse gap —
no `bash` at all — is why the pairing exists in the first place. What is
**not** verified is real hook-runner behavior with no `pwsh` on Linux; that
combination was never exercised, so treat it as unconfirmed rather than
assumed fine.

**Every hook is inert until a repository has `.crew/config.json`.** Installing the
plugin arms nothing; `/crew:init` in a given repo is what turns the gates on there.
That is deliberate - a gate that fired in every repository you opened would be
hostile - but it does mean "I installed crew and nothing happened" is the expected
first experience, not a fault. Check with `ls .crew/` before concluding a hook is
broken.

Hooks are deterministic. That is their whole value — a hook cannot be argued out of blocking `terraform apply`, and an agent can.

### Four suites, and what each can actually prove

```bash
bash   hooks/scripts/_test/run-tests.sh           # 77 cases - the hooks
bash   hooks/scripts/_test/setup-walkthrough.sh   # 32 cases - the setup scripts
python hooks/scripts/_test/validate-prompts.py    # 110 checks - command/agent structure
pytest tests/                                     # 234 cases - the python modules and both hook flavours
```

| Suite | Proves | Cannot prove |
|---|---|---|
| `run-tests.sh` | Every gate blocks and allows what it should | - |
| `setup-walkthrough.sh` | Phases 0-8 scripts run against a real mixed-stack repo and produce their artifacts | that a human would like the result |
| `validate-prompts.py` | Frontmatter parses, tools are real, referenced agents and paths exist, read-only agents hold no write tools, commands that spawn subagents are permitted to | **whether the prompts produce good work** |
| `pytest tests/` | The python modules, and that the `.sh` and `.ps1` flavours of `context-watch`, `verify-gate` and `promote-gate` agree - including the emergency lane's expiry, which is the one property that keeps a forgotten incident from ungating a repo forever | anything on a platform the suite is not running on; the Windows-only cases skip elsewhere |

That last gap is real and no test closes it. The 24 commands and 14 agents are
instructions to a model; only a live session running a real ticket exercises
them. Setup Phase 7 exists for exactly that, and it is the one thing here that
has to be done by hand.

All four are sabotage-tested - reintroduce a bug each is meant to catch and it
goes red. If you add a rule, add the case that proves it, then break it once.

`run-tests.sh` is 77 cases: 20 the guard must block, 14 it must allow, 12 for the
promotion gate, 15 for the emergency lane (including that the guard still blocks
during one, and that an expired incident gates again), plus the verify gate's
root-level glob matching and its `stop_hook_active` exit. `guard.sh` produced two
real regressions in two review passes — a substring `prod` match that blocked
`s3://my-product-images`, and a secret rule that exempted `> file` so writing a
secret to disk passed while printing one blocked. Both were found by running it,
not by reading it.

The suite has been sabotage-tested: reintroducing each of those bugs turns it
red (3 failures, 3 failures, and 1 for the stop-loop check). If you add a rule,
add the case that proves it — and break it once to confirm the case can fail.

### How the Windows half works

Every event is registered **twice** in `hooks.json`, once per flavour, with `shell: powershell` on the PowerShell side — a field Claude Code documents and does read; setting it runs that entry via PowerShell on Windows without needing `CLAUDE_CODE_USE_POWERSHELL_TOOL`, since hooks spawn the interpreter directly. `guard.sh`/`guard.ps1` and `promote-gate.sh`/`promote-gate.ps1` are additionally registered on separate `Bash` / `PowerShell` matchers at `PreToolUse`, so the branch is **which tool Claude used**, not which OS is running:

```json
{ "matcher": "Bash",       "hooks": [{ "type": "command", "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/guard.sh", "timeout": 10 }] },
{ "matcher": "PowerShell", "hooks": [{ "type": "command", "shell": "powershell", "command": "& '${CLAUDE_PLUGIN_ROOT}/hooks/scripts/guard.ps1'", "timeout": 10 }] }
```

That distinction is load-bearing. A `Bash` tool call is bash syntax *even on Windows*, so judging it with PowerShell rules gets it backwards in both directions: it blocks the correct capture form (`DB_PASS=$(...)`) and misses the wrong one. Branch on the tool and each command is judged by the rules of the language it is written in. (`hooks/scripts/_common.sh` also ships a `crew_tool_dispatch` helper for judging a command from inside a single bash-registered script — a valid alternative shape — but it is unused here in favour of the explicit dual-matcher registration above.)

The other six hooks judge no command, so both flavours are simply wired to their event with no branch: `verify-gate.sh`/`.ps1`, `context-watch.sh`/`.ps1`, `handoff-read.sh`/`.ps1`, `handoff-write.sh`/`.ps1`, `pm-brief.sh`/`.ps1`, and `notify.sh`/`.ps1` are all registered in `hooks.json`, one entry per flavour per event.

Two things worth knowing:

- **`hooks.json` has no way to know in advance which shell a given machine actually has**, so both flavours are wired and one is expected to fail — that is by design, not a bug. On Windows this is measured, not hypothetical: Git for Windows ships two `bash.exe` binaries, and `usr/bin/bash.exe` exits 127 running these scripts where `bin/bash.exe` runs them fine, so which one resolves first on `PATH` decides whether the `.sh` side works at all. The `.ps1` twin is what actually gates the machine when it doesn't.
- **A bare `command` string with no `shell` field still goes to Git Bash on Windows** (PowerShell only when Git Bash isn't installed), not to whatever `bash` a non-MSYS parent process might resolve to. Versions of this plugin before 0.2.0 relied on the `.sh` side deferring to a `.ps1` twin that was never actually invoked, so on Windows the command guard blocked nothing and the `Stop` gate ran nothing — fixed by registering both flavours explicitly instead of assuming one would pick up the other's slack.

`python3` is not required. Every script resolves `python3`, then `python`, then `py`, and `guard.sh` prefers `jq` when present. With none available the hook says so on stderr and exits 0 — loudly inert rather than silently passing.

---

## 26. Troubleshooting

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
| Warning arrives too late | `budgetTokens` is set too high for the real window, or `reserveTokens` is larger than the headroom you actually want. Calibrate against `/context`. |
| Warning still fires early on a 1M model | The `Threshold:` line in the warning says which rule fired. `warnAt 80%` on a 1M window is 800k; set `context.reserveTokens` (default 100000) to the headroom you want kept and the later rule wins. |
| Gates stopped blocking and nobody said why | An emergency lane is open - the session brief names it at every session start. `/crew:emergency status`, then `end`. It also expires on its own; see 24. |
| An incident will not stand the gates down | `emergency.standDown` is `false` in `.crew/config.json`, or the incident has expired. Both are reported by `/crew:emergency status`. |
| Warning fires far too early on a 1M model | `.crew/config.json` still carries `"budgetTokens": 200000` from an older `/crew:init`. Set it to `null`; the warning's `Budget source:` line says `configured` when this is the cause. |
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
| One hook flavour errors, the other runs | Expected on a matcher-less event (`SessionStart`, `PreCompact`, `Notification`, `Stop`) — both `.sh` and `.ps1` are registered unconditionally there, and only one shell is actually on the machine. Check which one succeeded before assuming a real failure. |
| No hook fires at all on Windows | No `bash` and no PowerShell resolve, or the wrong `bash.exe` is first on `PATH` — Git for Windows ships two, and only `bin/bash.exe` runs these scripts reliably. |
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

This is now checked for you, not just documented. The `repo-plugins` install
step detects a **separate**, globally-installed copy at
`~/.claude/skills/find-skills` — the one `find-skills` (menu item 5) or
`npx skills add vercel-labs/skills --skill find-skills` puts there — and warns
that two active copies can both trigger on the same prompt. The check is
detection-only: it never deletes anything, it just prints the collision and
the manual `rm -rf` to remove the global copy if you want crew's vendored one
to be the only one loaded.

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
