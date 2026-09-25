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
12b. [Optional: Perplexity MCP for web-grounded QA](#12b-optional-perplexity-mcp-for-web-grounded-qa)
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
22. [The crew](#22-the-crew)
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
| An isolated context window | `explorer`, `security`, `reviewer`, `researcher` |
| A restricted tool set | `explorer` holds no `Write`, `Edit` or `Bash`; `security` holds no `Write` or `Edit` but does hold `Bash` |
| Genuinely independent eyes | Codex, or `reviewer` in its own context |

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

Every hook is registered **twice** in `hooks.json` — once as bash, once as its
`.ps1` twin with `shell: powershell` — because `hooks.json` cannot know which
shell a given machine has, so one flavour failing is expected rather than a
fault. Only the `PreToolUse` guards branch, and they branch on which **tool** the
command came from rather than on the OS, so a `Bash` call is judged by bash rules
even on Windows. See
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

`.crew/config.json`'s `platform` block describes the machine that ran
`/crew:init`, and that machine stops being the machine reading it. The config is
**not** committed — the gitignore policy is `.crew/*` ignored with a named
un-ignore list (`codemap/`, `endpoints.json`, `verify.json`), and `config.json`
is deliberately not on it — so the block goes wrong without ever leaving the
checkout it was written in: `windowsHostIp` changes when WSL2's gateway does
after a reboot, and one worktree opened from Windows and from WSL is two
machines sharing one file. (Until 2026-09-14 this paragraph said the config *was*
committed and was therefore wrong for everybody else. That was the rationale for
the hook and it was backwards about the mechanism, not about the need.)

So a `SessionStart` hook repairs it. Open the repo from Windows after the block
was written from WSL and the first thing the session says is:

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

That split is the whole design, and it is why this hook is allowed to write at
all. A choice a human made is *judgement* — whether a role earns its context is
not a fact. `platform.os` is a fact, it is wrong on the other machine,
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

Verify with `/help` — you should see `/crew:brainstorm`, `/crew:spec`, `/crew:plan`, `/crew:implement`, `/crew:review`, `/crew:done`, `/crew:status`, `/crew:migrate`, and `/crew:onboard`.

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
"connect my vault" reaches
`crew-memory`, and "set up notifications" or "send updates to Teams" reaches
`crew-notify`.

Under the hood the phases live in one file, `skills/crew-setup/phases.md`, which
both the command and the skill read — so the two entry points cannot drift apart.

The skill will:

1. Run a detection script and report your stack, existing tests, CI, whether `codex` is on your `PATH`, and whether the repo is already configured
2. Ask exactly three questions — reviewer, ticket tracker, memory location
3. Create `.crew/`, `.work/`, `_verify/`, `docs/adr/`, and a `CLAUDE.md` if none exists
4. Tell you plainly that the setup is not yet usable

<!-- crew-ignore-policy:list -->
**Commit the part that is about the code, not the part that is about your box.**
The policy `/crew:init` writes is `.crew/*` ignored plus a named un-ignore list —
`!.crew/codemap/`, `!.crew/endpoints.json`, `!.crew/verify.json`. Those three
describe the repository: the code map, the endpoint ledger a security scan is
owed against, and the verification map. Commit them, and `_verify/`, `docs/adr/`
and `CLAUDE.md` with them. `.crew/config.json`, `.crew/STATUS.md`, the transcripts
and the gate's own marker files stay out, and so does the whole of `.work/` —
they describe one checkout on one machine. (This line used to say `.work/`
belongs in version control. It does not; the marker files under it dirty the tree
and block the next promotion.)

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
/crew:init --phase 3
```

The session fills `_verify/` itself; crew 1.0 ships no writing agents.

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

`agents` names **any installed subagent**, not only crew's own roles. This
sentence said "crew's eleven" until 2026-09-14, long after `agents/` stopped
holding eleven files; the count is deliberately gone rather than corrected,
because the roster moves and nothing checks a number written here — the same
shape `commands/review.md` uses, which `tests/test_verify_absent_and_diagram_kind.py`
holds in place. Both rules above happen to name roles crew does ship, but a name
from any other installed plugin works the same way. A bare name resolves to
crew's own role first
(`security` → `crew:security`), then to any other installed agent of that name;
namespace it when you mean the other one. This is how a machine's domain
specialists get pulled in *by path match* rather than when somebody remembers
they exist — the change touches `.tf` under `iam/`, so the IAM auditor reviews it,
every time, without being asked.

The safeguard matters as much as the feature. `.crew/verify.json` is committed
and travels between machines — it is one of the three paths on the un-ignore list
(`!.crew/codemap/`, `!.crew/endpoints.json`, `!.crew/verify.json`) that `.crew/*`
would otherwise ignore — so a rule naming an agent the author has and a teammate
does not would quietly review less on the second machine while producing output
that looks identical. Travelling is exactly what makes the gap possible; it is
also the only reason the map is worth writing once. `/crew:review` therefore reports a named-but-missing
agent as a gap and logs it to `.crew/metrics.md`, so "this rule asked for
`security-auditor` eleven times and never got it" becomes evidence for either
installing it or deleting the rule.

Each pairing is **verified when written**: break the code, run the mapped check,
confirm it goes red, revert. An unverified mapping is a guess written in JSON —
and a pairing that stays green has just told you about a coverage hole.

### Checks and rules are written together

**Whoever writes a check writes its rule, in the same turn.** The implementing
session does this, and proves the rule fires before calling
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

The implementing session writes the specific check — which script, what it
asserts, which paths — with the `stack-sql` skill loaded.

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
Write Playwright specs for the checkout flow and the pricing page styling
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

`crew:explorer` investigates, one pass per subsystem, and returns at most seven
findings, each with a file-and-line anchor, a concrete impact, and three options
where **option A is always "do nothing"** and is always a real option.

The failure mode it is written against is generic advice: "consider adding
caching," "error handling could be improved." That is what gets produced when
nothing was actually read, and it is worse than silence because it costs review
time and teaches you to skim.

It starts from evidence — `git log` file-change frequency, existing findings,
smoke gaps — rather than from a checklist, because the files that change
constantly are where the pain is.

It does not create tickets. You read the findings and decide; `/crew:brainstorm` is a
separate, deliberate step. A survey that automatically becomes a backlog is a way
of committing to seven things nobody agreed to.

Run it after the safety net exists, not before. Findings you cannot safely act on
are just a list.

---

## 10. The daily loop

### Scope it

```
/crew:brainstorm the export job times out on tenants with more than 50k rows
/crew:spec T-0042
```

`/crew:brainstorm` mints the ticket and settles a direction, one question at a time; `/crew:spec` fills the contract (Intent, Exclusions, Evidence, Unknowns, Touch, Acceptance checks), with `explorer` checking what the change touches and whether it crosses repositories.

Acceptance checks must be **observable**. "Export works properly" is not a ticket. "Export of a 100k-row tenant completes under 60s and the smoke check covers it" is.

Work spanning repositories gets one ticket per repository, cross-referenced by ID. Never a ticket that silently spans repos.

### Work it

```
/crew:implement T-0042
```

The session reads exactly one ticket file, delegates the search to `explorer`, plans before editing, implements the smallest sufficient change, runs smoke, escalates to `security` (or loads a `stack-*` skill) when the change warrants it, adds any missing checks and docs, and runs review last.

If the change added behavior with no smoke coverage, the implementing session adds a check. A feature without a check is how the next change breaks it silently. Review comes after the tests and the docs (since 0.20.17), so the reviewer reads the finished change rather than a draft that later edits move out from under it.

### Review it

```
/crew:review
```

Codex if available, the `reviewer` agent if not — and it always tells you which ran. Findings are reported verbatim before any argument about them. `BLOCK` items get fixed, smoke reruns, review runs once more — and that second round is the last one.

The reviewer reads a **bundle**, not a `git diff` of the committed range: `hooks/scripts/review_patch.py` stages committed, staged, unstaged and untracked changes into a temporary index (your own index is never written) and diffs the ticket base against it. Renames, file-mode changes, binary files (git's marker plus both blob ids and sizes) and submodules are listed in the manifest. A large bundle is split into ordered parts — never truncated — and the manifest records a sha256 over them.

Then it appends a line to `.crew/metrics.md`. That line is not bookkeeping; `/crew:status` reads it to show whether any of this is catching anything.

### Review: verdicts and the two-round budget

(This section lives here because the 1.0 guide sources under `docs/guides/crew/src/` do not exist yet; the HTML guides in `docs/guides/crew/` have no generator.)

**The verdict is computed by a script**, `hooks/scripts/review_verdict.py`, from the reviewer's output and exit status:

| Verdict | When |
|---|---|
| `CLEAN` | exactly one `CLEAN` line, exit 0, and a `READ|<part>` line for every bundle part |
| `FINDINGS` | at least one `BLOCK`, `FIX` or `NIT` line, and nothing below applies |
| `INCOMPLETE` | non-zero exit, unknown exit, timeout, empty output, any line outside the contract (a code fence, or a finding with an empty field, included), a part not acknowledged, a bundle part that no longer matches its manifest size and sha256, an unreadable line in Codex's event stream, or `CLEAN` beside findings |

`INCOMPLETE` is never `CLEAN`. Codex runs as `codex exec --json --sandbox read-only` with stdin closed, and a turn that failed in its event stream is `INCOMPLETE` even when the process exited 0. Each round writes `.work/tickets/<id>/review.json` (verdict, counts, provider, model, model family, bundle hash, base/head, round).

**Two rounds per ticket, in total.** `hooks/scripts/review_ledger.py` keeps the ledger at `<git-common-dir>/crew/review/<id>.json`, so every worktree of the repo shares it. `review_run.py` reserves the round *before* it launches the reviewer, so a reviewer that crashes or hangs has still spent it. A third reservation is refused and the ticket becomes `NEEDS_REPLAN`; that refusal and an explicit `review_ledger.py --ticket <id> --reject --by <who>` are the only ways in, so finishing round 2 with `FINDINGS` or `INCOMPLETE` leaves the ticket `REVIEWED`, not `NEEDS_REPLAN`. A result is recorded only for the most recent reserved round, only once, and only by the provider and model it was reserved for; once `NEEDS_REPLAN`, no result changes the state. No environment variable, flag or config key raises or resets the budget; deleting the ledger file by hand is outside that promise, and is what a reviewer of your repo's history would see. Since crew 1.0 (T3) the one way past `NEEDS_REPLAN` is an approved successor plan: approving a *different* plan (`/crew:approve <id>`) opens a fresh budget of two rounds under that plan (see "Scope and approval" below); re-approving the same plan does not.

**The receipt is bound to the bundle.** A `CLEAN` round writes an acceptance receipt carrying the bundle sha256. `FINDINGS` you decide to accept become one only through `review_ledger.py --ticket <id> --accept --by <who>`, which records who and when and refuses if the tree changed since that round. It accepts only the most recent round, only once that round completed with `FINDINGS`, only once per round, and never once the ticket is `NEEDS_REPLAN` — so round 2's FINDINGS can be accepted until a third reservation is refused or the ticket is rejected, and not after (since 0.20.18). `review_ledger.py --ticket <id> --check-receipt` rebuilds the bundle from the receipt's base and exits non-zero when there is no receipt or the hash differs — any edit after review invalidates it; committing the reviewed change does not. `/crew:done` will gate on it; for now, run it yourself before you open the pull request.

The prompt every reviewer reads also carries the ticket's spec sections (Intent, Exclusions, Evidence, Unknowns, Acceptance checks) from `.work/tickets/<id>/spec.md`, the plan from `plan.md`, the codemap landmines, and the verify gate's latest receipts. A missing piece is written into the prompt as `MISSING`, never left out.

You open the pull request. The crew stops at the boundary of your judgment.

### Scope and approval

A crew 1.0 ticket is a directory, `.work/tickets/<id>/`, holding `direction.md`, `spec.md` (Intent, Exclusions, Evidence, Unknowns, **Touch**, Acceptance checks) and `plan.md` (steps, each with `Files:`, `Test:` and `Risk:`). `## Touch` is one repo-relative glob or path per bullet line; `*`, `?` and `[...]` match within one path segment and never cross `/`, `**` spans segments, and an entry with no wildcard also covers everything under it as a directory. These scripts in `hooks/scripts/` enforce it:

| Script | What it does |
|---|---|
| `crew_ticket.py validate --ticket <id>` | Every spec section present; every plan `Files:` entry inside Touch. A plan path outside Touch is an error, never a silent widening. |
| `/crew:approve <id>` — `approval_hook.py` (UserPromptSubmit) | **How you approve.** When the prompt *you* submit is exactly `/crew:approve <id>`, the hook reads `spec.md` and `plan.md` once, validates those bytes and writes `<git-common-dir>/crew/tickets/<id>/approval.json` with their sha256 and their approval digest (below), `approved_via: "user-prompt"`, and the prompt's session id and time. A contract that does not validate blocks the prompt and says why; nothing is recorded. |
| `crew_ticket.py approve --ticket <id> [--by <who>]` | The same receipt from a shell, for tests and CI, marked `approved_via: "cli"`. The guard and the audit accept a `cli` receipt only when `scope.allowCliApproval` is `true` (default `false`). |
| `crew_ticket.py status --ticket <id>` | `approved`, `stale` (spec or plan edited since, other than the header's status value) or `none`. Exit 0 only for `approved`. |
| `crew_ticket.py activate --ticket <id>` | Makes `<id>` this worktree's active ticket (`<git-common-dir>/crew/active-ticket`, keyed by worktree). Without it, the open ticket in `.work/INDEX.md` is used when its `.work/tickets/<id>/` directory exists. |
| `scope_guard.py` (PreToolUse `Write\|Edit\|MultiEdit\|NotebookEdit\|Bash\|PowerShell`) | Refuses an edit when the active ticket has no current approval from your prompt, or when the target is outside Touch. Refuses a shell command that runs `crew_ticket.py approve`, names the approval hook, or writes under `<git-common-dir>/crew/`. |
| `completion_audit.py` (Stop) | Diffs the whole tree against the ticket's scope base — committed, staged, unstaged and untracked, both ends of a rename — so shell-made writes are caught too. `--check --ticket <id>` is the form `/crew:done` calls. |

**What the guard judges.** The real path, following symlinks and junctions the way the OS will, *and* the path as named, when that is inside the worktree — so a link cannot carry a write out of Touch or launder one into it. `..` is resolved where the OS resolves it. The ticket's own `.work/tickets/<id>/` files are always writable, so you can amend the spec and plan. Nothing else is exempt: not `.crew/`, not `TODO.md`, not `.claude/`, not crew's own policy files — put them in Touch if the ticket changes them. Anything under `<git-common-dir>/crew/` (approval receipts, the review ledger, the active-ticket pointer, the ramp count) and `.crew/.scope-base` are refused to Write/Edit in every mode but `off`, ticket or no ticket. A path outside the worktree (a scratch directory) is not a repository path and is allowed, except the git directory.

**Amending scope** is editing `spec.md` `## Touch` (and `plan.md`), then `/crew:approve <id>` again. The edit makes the approval stale, so edits outside the ticket directory are refused until you approve.

**The status edit keeps the approval.** The receipt binds each file's approval digest (`digest: "crew-approval/2"`, fields `spec_digest` and `plan_digest`), which normalises exactly one thing: the value of the header's `status:` token, so `/crew:plan`, `/crew:implement` and `/crew:done` can move a ticket through `spec` -> `planned` -> `review` -> `done` without a fresh approval. It applies only when line 1 starts with `# `, holds exactly one `status:` (counted case-insensitively), and that token's value is one of `spec`, `planned`, `approved`, `in-progress`, `review`, `done`, `merged`. Everything else still stales it: `risk:`, the title, whitespace, line endings, any body line, a second `status:` anywhere, a value outside that list, and a `status:` added where there was none. `plan_sha256`/`spec_sha256` stay the raw full-file sha256, which the review ledger's successor-plan rule still reads. A receipt written before T-0026 has no `digest` field and is compared on the raw sha256, so it verifies on unchanged files and goes stale once on its first status edit; approving again writes a `/2` receipt. A `digest` naming any other scheme reads `stale`, never a raw fallback.

**Modes** — `scope.mode` in `.crew/config.json`:

| Value | Behaviour |
|---|---|
| `off` (default) | Both hooks do nothing. A repo that never set the key is here. `/crew:init` writes `auto` instead for a repo it creates `.crew/config.json` in (crew 0.20.25); an existing config is left alone. |
| `report` | Everything is allowed; each would-be refusal is logged to `.crew/guard.log` and shown as a system message. Approval/ledger state is still refused. |
| `block` | Refusals block (the edit guard exits 2; the audit blocks the Stop once, in at most six lines, and never re-blocks a `stop_hook_active` continuation). |
| `auto` | `report` for the first ten tickets approved in this repository, then `block`. The count lives in `<git-common-dir>/crew/scope-tickets.json`. |

A `.crew/config.json` that exists but does not parse, or a value outside those four, is treated as `block` and says so. A hook payload that does not parse is refused whenever the effective mode is `block` (`auto` past its ramp included). An active-ticket pointer naming a ticket that does not exist is refused under `block`, never read as "no ticket". If python cannot run at all, the wrappers fail closed unless `.crew/config.json` is absent or *provably* sets `scope.mode` to `off`. bash has no JSON parser, so from bash a config that exists is never provable: with no usable python, a present config blocks writes and the Stop until python is available. PowerShell proves it with a strict `System.Text.Json` parse (not `ConvertFrom-Json`, which accepts trailing commas), and fails closed where that type cannot load; the Stop audit then blocks at most once in a row per session, so a broken python cannot loop the Stop.

**Threat model.** These guards stop *drift and accidental bypass*: a session editing outside the plan, approving its own plan through the CLI, or writing the approval state through Write/Edit or an obvious shell command. They do not stop a session that sets out to forge local state. It has a shell, and the receipt, the active-ticket pointer and the ramp count are files on your machine: a command that hides the path in a variable or an encoded string, or a script that writes JSON, passes the textual shell check. The Stop audit and review are the backstop — the audit diffs the whole tree after the fact, and a reviewer sees the change and the receipt's `approved_via`. Treat an approval as "the user asked, and nothing obviously went around it", not as a signature.

**What this does not do.** The edit guard judges only the four editing tools against Touch; the Stop audit is what catches `sed -i`, redirects and formatters, after the fact. The audit sees what git sees: gitignored files (`.crew/*` among them) and `.work/` are outside it.

### Measuring 1.0

`.crew/metrics.jsonl` (append-only; `.crew/metrics.md` from 0.20 becomes this via `/crew:migrate`, with every historical value it cannot recover marked `UNKNOWN`, never `0`) is where crew 1.0's own validation claim gets checked: at least 30% lower median active time or cost against the 0.20 baseline, 100% review-budget enforcement, zero unapproved scope changes, and no rise in escaped defects, over 10–20 matched tickets (docs/review/04-redesign.md, "Validation").

`hooks/scripts/crew_metrics.py` writes and reads it:

| Command | What it does |
|---|---|
| `crew_metrics.py record --ticket <id>` | Appends one row: phases and timestamps, active time and tokens (from `--transcript <path>`, an idle-capped sum of gaps between transcript events — `UNKNOWN` without it), cost (`UNKNOWN`; no priced source exists yet), review rounds (the review ledger), scope blocks (`.crew/guard.log`), injected characters (the context log, by `--session` or the ticket's approval session), and unapproved scope changes at record time (the completion audit). Confirmed/rejected/duplicate findings and escaped defects are `UNKNOWN` from `record` — no source in this repository derives finding disposition automatically. **`/crew:done` runs this on every close:** `python3 hooks/scripts/crew_metrics.py record --ticket <id>`. |
| `crew_metrics.py escaped --ticket <id> --count N [--note <text>]` | Appends a row setting `escapedDefects`, once a defect is found after the ticket closed. Never edits the `record` row — metrics are append-only; rewriting a line is an `AUTONOMOUS_STOP`. |
| `crew_metrics.py baseline` | Median active time/cost over every 0.20/migrated ticket, with `n` and how many are `UNKNOWN`. Historical rows are almost always `UNKNOWN` for both — reconstruct one from an old transcript with `record --schema 0.20 --transcript <old-transcript>`. |
| `crew_metrics.py compare --since <n\|date>` | The last `n` (or every ticket recorded on/after the `date`, matched by that ticket's own `record` row timestamp, not a later `escaped` correction) prospective 1.0 tickets against the baseline: medians, percent change, review-budget enforcement rate, unapproved scope changes, escaped defects, and a `PASS`/`FAIL`/`INSUFFICIENT DATA` per success criterion. The median-based criterion needs at least 10 KNOWN values on both the prospective and the baseline side to PASS or FAIL on — fewer than that reads `INSUFFICIENT DATA` regardless of the computed percentage. Any row in `metrics.jsonl` that failed to parse, or any prospective ticket with an unknown value feeding a criterion, keeps the OVERALL verdict from reading `PASS`; combining criteria, any `FAIL` wins over any `INSUFFICIENT DATA`, which wins over `PASS`. |

A count this module could not measure is always the string `UNKNOWN`, never `0` — a `0` here is a real measurement (the guard log exists and names no block for this ticket), and collapsing "could not tell" into `0` is exactly the failure mode that made 0.20's own review-rate metric read low (see `crew_state.read_metrics`).

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
`pm.authority: report-only` while the user believed the 0.20 PM was autonomous.
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
- It marks a **widening** with a `!` line, on both the dry run and the write,
  naming the tier being granted and what that tier buys. `pm.authority`,
  `install.policy` and all six `guards.*` are the values a user cannot recover
  from by noticing.

`--explain` also names the **narrowing source** for the seven keys that ratchet.
Those do not resolve by precedence, so the merged value is the wrong thing to
print for them: before this was fixed, a repo `install.policy: auto` over a
machine-global `manual` printed `install.policy  repo  "auto"` while crew
behaved as `manual` — a report contradicting the run, in the direction that
reads as "you have it". It now prints the effective value and, underneath, the
line that says which layer is holding it down and what each layer asked for.

`templates/global.template.json` is the shape, and a committed test asserts it
equals `default_global_config()` byte-for-byte — the same drift gate the repo
template has. It is deliberately not a copy of the repo template: it carries
only what is a property of the machine or the person (`pm.authority`, `qa`,
`dev`, `secondOpinion`, `notify`, `memory.vaultPath`), and no `schema`.

A global file that is missing, empty, or fails to parse is treated exactly
like an absent one — the same reasoning `_read_config_strict` documents for
the repo side — so a typo in your global config degrades one repo's settings
to defaults rather than breaking every session on the machine.

### §11b. `guards` — the guardrails you can turn down, per machine

Six keys added by schema 6, in **two vocabularies**: four are
`block` | `ask` | `allow`, shipping as `block`; the two production-access keys
are `none` | `read` | `full`, shipping as `none`. Since then `guards.roleWrites`
(see §18 of CONFIG.md) and, with the cloud guard, `guards.cloudDestructive`,
`guards.sqlDestructive` and the `guards.cloudGuard` switch. The command keys
below govern something **only while `guards.cloudGuard` is `report` or
`block`** — it ships `off`; see [Cloud guard](#cloud-guard).

| Key | Governs | Read by |
|---|---|---|
| `guards.terraformApply` | `terraform`/`tofu`/`terragrunt` `apply` and `destroy` | `hooks/scripts/cloud_guard.py`, when `cloudGuard` is on |
| `guards.forcePush` | `git push --force` / `-f` / `--force-with-lease` / a `+ref` | `hooks/scripts/cloud_guard.py`, when `cloudGuard` is on |
| `guards.adminMerge` | `gh pr merge --admin` | `hooks/scripts/cloud_guard.py`, when `cloudGuard` is on |
| `guards.mergeGate` | whether `/crew:gate` may take a live repo's merge gate down | `commands/gate.md`, `commands/promote.md` |
| `guards.prodDatabase` | a SQL client aimed at a `production.databases` pattern | `hooks/scripts/cloud_guard.py`, when `cloudGuard` is on |
| `guards.prodServer` | `ssh`/`plink`/`scp` aimed at a `production.hosts` pattern | `hooks/scripts/cloud_guard.py`, when `cloudGuard` is on |
| `guards.cloudDestructive` | `aws … delete-*/terminate-*/purge-*`, `s3 rm/rb`, `s3 sync --delete`, `az … delete/purge`, `Remove-Az*` | `hooks/scripts/cloud_guard.py`, when `cloudGuard` is on |
| `guards.sqlDestructive` | `DROP`/`TRUNCATE` sent to `psql`, `mysql`, `mariadb`, `sqlcmd`, `sqlite3`, `Invoke-Sqlcmd` | `hooks/scripts/cloud_guard.py`, when `cloudGuard` is on |
| `guards.cloudGuard` | whether the cloud guard judges commands at all: `off` (default) / `report` / `block` | `hooks/scripts/cloud_guard.py` |

- **`block`** refuses, exactly as the guard did before these keys existed.
- **`ask`** refuses, prints the **exact** command, and names the one file that
  approves **that** command:
  `.crew/.approved-guard-<name>-<sha256(command)[:16]>`. Create it, re-run, and
  it goes through; the next command asks again. It is a marker rather than a
  prompt because a `PreToolUse` hook has no interactive stdin — an `ask`
  implemented as a question would have been `block` under another name.
- **`allow`** runs it, says so, and appends a row to `.crew/guard.log`. **Under
  `allow` nothing is silent.** The stderr line goes with the session; the row
  is the durable half, and it is written for every decision rather than only
  the permissive ones.

**The two production guards are `none` | `read` | `full`.** `none` refuses
every command aimed at a declared target; `read` permits only what crew can
**positively classify** as read-only, so an interactive `psql`, an unrecognised
binary over `ssh` and anything it cannot parse are refused as writes; `full`
permits everything and logs each one. `ask` is not a value here — these answer
"how much of production may crew reach", a standing posture rather than a
per-command question.

**The level is a machine fact; what is production is not.** The two levels
ratchet across both layers. `production.databases` and `production.hosts` — the
glob lists they match against — are **repo-only**: `prod-db-*` names one
cluster in one repo and something else in the next, so a machine-global list
would describe the wrong estate everywhere else. **With no patterns declared
the guard matches nothing**, which is how the strictest level can be the
default and still change nobody's behaviour on upgrade.

**A repo may only narrow.** Every `guards.*` key and `install.policy` resolve to the
**narrower** of the repo and machine-global layers, not by precedence. crew
reads config out of cloned repositories: under precedence, a repo shipping
`guards.forcePush: allow` would grant itself force-push rights on the machine
of anyone who cloned it. So `allow` needs **both** layers to say `allow`, and
`--explain` names the layer holding a key down when they disagree.

### Cloud guard

A `PreToolUse` hook on the **Bash and PowerShell** tools
(`hooks/scripts/cloud-guard.sh` / `cloud-guard.ps1`, both delegating to
`cloud_guard.py`). **It ships off** — `guards.cloudGuard: "off"` — because a
hook that can block defaults off. Set it to `report` first: every decision it
*would* make goes to `.crew/guard.log` and nothing is refused. `block` enforces.
A repo cannot turn off a machine-global `block`.

When on, it reads each command into the simple commands it actually runs —
through `&&`, `;`, `|`, `sudo`, `env X=Y`, `bash -c`, `pwsh -Command`, `$( )`,
heredocs and PowerShell script blocks — and judges only those. A word inside an
argument is never a finding: `git commit -m "terraform destroy"` and
`psql -c "SELECT 'DROP TABLE x'"` both pass. That is the difference from the
command guard removed in 0.19.52, which matched words anywhere.

| It recognises | Decided by |
|---|---|
| `terraform`/`tofu` `apply`, `destroy` (`-auto-approve`, `-chdir=` included) | `guards.terraformApply` |
| `git push --force`, `-f`, `--force-with-lease`, `+ref` | `guards.forcePush` |
| `gh pr merge --admin` | `guards.adminMerge` |
| `aws … delete-*/terminate-*/purge-*`, `aws s3 rm/rb`, `az … delete/purge`, `Remove-Az*` | `guards.cloudDestructive` |
| `DROP`/`TRUNCATE` via `-c`/`-e`/`-Q`, heredoc, pipe or `Invoke-Sqlcmd -Query` | `guards.sqlDestructive` |
| a SQL client or `ssh` aimed at a declared `production.*` pattern | `guards.prodDatabase` / `guards.prodServer` |
| the AWS profile/region or Azure subscription of every `aws`/`az` command | `cloud.awsProfiles`, `cloud.awsRegions`, `cloud.azureSubscriptions` |

`block` answers `permissionDecision: "deny"`, `ask` answers `"ask"`, and `allow`
prints nothing — the guard never answers `"allow"`, which would skip your own
permission prompt. `report` mode answers with no decision at all and a
`systemMessage` saying what `block` would have done. Every refusal names its
rule, e.g. `[terraformApply] terraform destroy: guards.terraformApply is block`.
A command it could not read — nested more than six shells deep, or hook input
that is not a readable Bash/PowerShell call — is refused as `[cloudGuard]`; a
destructive-capable tool behind `xargs`/`parallel` is judged as destructive
under its own rule. `--dry-run`, `-WhatIf` and `-help` are not destructive.

**Identity.** The repo-only `cloud` block pins which AWS profiles/regions and
Azure subscriptions this checkout may act as. A command resolving to anything
else is denied. One whose identity the guard cannot name — no profile set,
static `AWS_ACCESS_KEY_ID` keys, an Az PowerShell context, or any destructive
command in a repo that pinned nothing — is **unknown**, and unknown is never
allowed unattended: it asks when a person is there, and is denied under
`CREW_UNATTENDED=1`, `CI`, or a `bypassPermissions`/`dontAsk` session, with the
one-shot approval file (`.crew/.approved-guard-<rule>-<hash>`, 15 minutes, that
command only) named in the refusal. Once **any** pin is set, a read-only call
with an unnamed identity is unknown too; only a repo that pins nothing lets it
through, reported once. `az account show` is never run; the default
subscription is read from `azureProfile.json`. Details and examples:
`skills/crew-cloud/SKILL.md`.

**It fails closed only when it knows it is armed.** A config file that exists
and will not parse forces `block`; so does a malformed `cloud` block under an
armed guard. With no usable python, each wrapper greps both config files for
`cloudGuard` and refuses (exit 2) if either arms it. The bash wrapper judges
every Bash call and the `.ps1` wrapper judges every PowerShell call — the
split is by tool, not by OS, decided in `cloud_guard.py`'s `stands_down` from
which flavour set `CREW_CLOUD_GUARD_FLAVOUR`, so the guard runs once per call
on any platform, never twice and never zero times.

**What it cannot see:** a command named through a variable, a script file it
runs, SQL built at runtime, Terraform's provider credentials, and MCP tool
calls. Tests: `tests/test_cloud_guard.py` (every case through python, bash and
pwsh) and the `cloud-guard.sh` section of `hooks/scripts/_test/run-tests.sh`.

### §11c. `change` — change requests, added by schema 7

Six keys, all settable in **either** layer. `change.requester` and
`change.implementor` are facts about a person and belong in the machine-global
file; `change.sdpTemplate` (`"Change Management Request"`),
`change.jiraIssueType` (`"Change"`) and `change.category` name what the desk
expects; `change.requireForProduction` ships `false`. §24b is what they do.

`change.requireForProduction` uses the same ratchet as the six `guards.*` keys
and **runs the other way round**: the narrower value is `true`, because
requiring a change request takes a capability away from a promotion. So a repo
may turn the requirement **on** and never off — a machine-global `true` is not
defeated by a `false` in a repo somebody cloned. Absent or `null` means
`false`, so upgrading changed nobody's promotions; a value that is neither
`true` nor `false` means `true`, so a typo stops a promotion and names the key
instead of quietly waving it through. CONFIG.md §17.

**Two of these are new refusals, not preserved ones.** `guards.adminMerge`
refuses `gh pr merge --admin`, which no crew guard refused before — measured
against the previous release, both flavours exited 0 — and
`guards.terraformApply` now covers `tofu` as well as `terraform`. Both were
bypasses rather than features. The `/crew:upgrade` report says so out loud,
because a user told only "the default is `block`, so nothing changed" will meet
a command that ran yesterday being refused today and go looking for a bug in
their tooling.

Both shell flavours resolve the value through `crew_config.py --guard`; neither
implements the layering itself. `guard.sh` and `guard.ps1` drift independently
— three of the bypasses fixed in #132 were open in both — and the rule whose
entire point is that a repo cannot widen it must not have two implementations.
Any failure of that resolver is `block`, with the reason on stderr: "could not
check" never becomes "checked, and fine".

The full key reference is **[`CONFIG.md`](CONFIG.md)** — every key in both
layers with its type, its default, which layer may set it, and a `path:line`
for the code that reads it. It is derived by executing `default_config()` and
`default_global_config()` rather than by reading comments, and it marks the
keys for which no consumer could be found instead of assuming one exists.

A sample `.crew/config.json` used to sit here, and a table of selected keys
under it. Both are **deleted rather than corrected**, deliberately. The sample
had drifted to 59 leaves against the real 85: twelve keys it showed no longer
existed, and twenty-eight that did were missing, including the whole `dev`
block. It drifted because it was a second copy of something derived elsewhere,
which is the same failure as the `UPDATE.md` mirrors and the stale schema
numbers — and like those, it passed every green check the repo had. A duplicate
that agrees today is a duplicate that disagrees later, so correcting it would
only have reset the clock.

`CONFIG.md` is derived by executing `default_config()` and
`default_global_config()`, and `tests/test_crew_config.py` holds drift gates
that compare both committed templates and `crew-setup/SKILL.md`'s inline copy
against those functions byte-for-byte. That is why there is no third copy here.

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

Last is the `reviewer` agent — on `opus`, in its own context window, so it has at least not seen the reasoning that produced the code. Its prompt tells it outright that it shares a model family with the author and must compensate: ask "what input makes this wrong" before "does this look correct." That is genuinely weaker than a different family, and the command says so every time it happens, so you know to review harder yourself. It also says so itself if something dispatches it directly and skips the provider walk.

Two knobs on the Codex rung, both read at call time and both passing no flag when null, so an upgraded repo behaves exactly as it did before: `qa.codex.model` pins a model, and `qa.codex.reasoningEffort` takes `none`, `minimal`, `low`, `medium`, `high`, `xhigh` or `max`. A wrong effort value is safe to get wrong — Codex rejects it with a 400 naming the supported set rather than quietly returning a shallower review.

### Gemini for design

```
/crew:plan T-0042
/crew:plan should the export run inline or move to a queue
```

`/crew:plan`'s optional second opinion gets an independent view on a design
decision before anything is built. Gemini's free tier suits this well — design questions are a
handful of calls a week, so rate limits never bite.

**It works from a brief, never from your code.** Free tiers are funded by prompts
and generally train on them, so what leaves the machine is the shape of the
problem: constraints, volumes, latency budgets, the options under consideration,
and what has already been ruled out. No source, no real schema names, no service
names, no ticket text.

The control is not a promise — it is an artifact. `/crew:plan` writes the brief to
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

## 12b. Optional: Perplexity MCP for web-grounded QA

A code reviewer reads the diff. It cannot tell you that the API the diff calls
was deprecated four months ago, or that the dependency it adds has an open
advisory. The 0.20 `qa-researcher` specialist that did this second pass was
removed in crew 1.0 with the other specialists; `crew:researcher` answers the
same class of question from fetched sources (web tools and Context7), and a
Perplexity MCP server you configure yourself is one more source it can use.

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

So `/crew:jira-sync` keeps six fields and discards the rest, writing a compact local file that `/crew:implement` reads instead of calling the API. That is the difference between paying for a ticket once and paying for it on every pickup, retry, and context reset. Sync happens at two boundaries only: pickup and completion. Three Jira calls in one ticket means the cache is wrong.

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
shape — so a bare `40219` is invisible to `/crew:status`, to `/crew:implement`, and
to the index. `/crew:sdp-sync` accepts either form and always writes `SDP-40219`.

The caching argument is identical to Jira's: a request payload runs thousands of
tokens across resolution HTML, the full note history, SLA timers, approvals and
every UDF the desk has ever defined, and about forty of them affect what you
build. `/crew:sdp-sync` keeps id, subject, status, requester, priority, category
and the last three notes, and `/crew:implement` reads that file instead of the API.

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
local mirror that `/crew:implement` reads, and `/crew:obsidian-sync` touches the
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
| Backlog | Deferred or untriaged. Where a non-blocking finding is parked. |
| Ready | Scoped by `/crew:spec` and pickup-able. |
| In Progress | `/crew:implement` has it. |
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

### Auto-wrap-up (on by default since 0.19.52)

`context.autoWrapUp` changes what the `Stop` hook says at `warnAt`, not
whether it fires. On (the default), it instructs the session to reach a
stopping point — finish or safely abandon the change in flight, write the
handoff, update the ticket — before telling you it's ready. Off, it just asks
you to write the handoff.

It blocks **once per threshold crossing per session**: keyed on the payload's
`session_id`, never on a `stop_hook_active` continuation, and re-armed only
when a measured reading drops back under the threshold (a compaction). It is
the one blocking `Stop` crew keeps besides the verify gate, as a documented
exception. The `/clear` that follows is yours to type unless this machine
opted in to auto-clear, below.

### Auto-clear (off by default, opt-in per machine)

The correction at the top of this section stands: a hook cannot clear the
conversation, because a hook is a child process and a child cannot reset its
parent. `context.autoClear` does not contradict that. It does something else —
it drives the **terminal**, typing `/clear` at the prompt the way you would.

Together with the wrap-up (above) and the resume (below) it is one cycle:
**wrap-up → handoff → clear → resume**. The full user guide is
`docs/guides/crew/src/auto-cycle.md`.

**It is a machine opt-in.** `enabled` is read from the machine-global
`~/.claude/crew/config.json`; a repo's `.crew/config.json` can switch it
*off* (`false`) but a repo `true` does not switch it on — the thing it drives is
this machine's keyboard, and templates written since 0.19.52 carried `true` in
every repo. The other keys layer normally, repo over machine.

```json
{ "context": { "autoClear": {
    "enabled": true,
    "method": "auto",
    "windowTitle": null,
    "command": "/clear",
    "delaySeconds": 3,
    "minHandoffLines": 5
} } }
```

| Method | How it finds the target | Confidence |
|---|---|---|
| `tmux` | `$TMUX_PANE`, and only when that pane's pid is an ancestor of the hook | **Exact.** No focus involved. Use this if you can. |
| `xdotool` | the one window owned by the nearest ancestor process; `windowTitle` narrows or, failing that, is a fallback that must match exactly one window | Activates that window id, re-checks it is active, then types. |
| `notify` | no window — types nothing | Prints a `systemMessage` saying the handoff is written and verified and it is safe to run the configured command yourself. Never claims anything was cleared or compacted, because nothing was. `auto` resolves here on native Windows with no tmux pane. |
| `sendkeys` | the same rule through `EnumWindows` (renamed from the pre-1.0 `"windows"` literal); at send time that exact window handle must have foreground | **Opt-in only — `auto` never resolves here.** Windows Terminal hosts every tab in one window and nothing outside UI Automation can tell which tab is active, so a Windows-Terminal-owned target declines and falls back to `notify`, logged to `.crew/.autoclear.log`. Request it by name after reading what it does. |
| `wtype` | cannot identify a window | **Refused**, whatever `unsafeFocus` says. |

#### What has to be true before it types anything

1. This machine opted in, as above.
2. `context-watch` asked **this session** for a wrap-up. The marker is
   `.crew/.handoff-requested-<session_id>` — it used to be one file per repo,
   so two terminals shared it.
3. The context reading behind that request was a measurement: not an estimate
   from transcript size, not an unknown model window, not a reading from before
   a compaction. A marker that is empty or not the hook's JSON — the shape of
   the Windows low-context `/clear` — is unknown, and unknown never clears.
4. The handoff exists, is **newer** than the request, has at least
   `minHandoffLines` non-blank lines, and is not PreCompact's automatic skeleton.
5. The target window is identified uniquely (the table above). Zero or several
   candidates is a refusal, never a guess — this step does not apply to
   `notify`, which identifies no window because it types nothing.
6. Nothing has claimed this session's one attempt (`.crew/.autoclear-sent-<session_id>`).

Fail any of those and it writes a line to `.crew/.autoclear.log` saying which,
and does nothing. That log exists because a `Stop` hook's stderr is invisible
when it exits 0, so without it "nothing happened" is indistinguishable from
"the feature is broken".

#### When it runs

On the `Stop` that ends the forced continuation — the turn the wrap-up block
sent back to write the handoff. `context-watch` never blocks on
`stop_hook_active`, but it does hand that turn to auto-clear; before this it
exited first, so the clear waited for your next message.

#### The delay, and why it is not zero

The hook runs *while the turn is still ending*, so the prompt does not exist yet
and typing immediately types into nothing. The keystroke is handed to a detached
child that sleeps first. Three seconds is usually enough; raise it on a slow
machine. The parent exits 0 straight away so the turn is not held up.

#### A `/clear` is not undoable

With `minHandoffLines` set too low, or a handoff the session wrote badly, you
lose the context and keep a note that does not replace it. Watch the first few,
and read `.work/HANDOFF.md` before trusting the next session to resume from it.

#### Try it without risking anything

```bash
bash   ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/auto-clear.sh --dry-run --force
pwsh -File ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/auto-clear.ps1 -DryRun -Force
```

`--dry-run` prints the method, target, command and delay it *would* use and sends
nothing. `--force` skips the handoff and reading conditions so you can see the
plan without being deep into a session. Neither consumes the one attempt.

If you run Claude Code in a tmux pane inside WSL, prefer the `.sh` flavour: it
addresses a pane by id and never touches focus, which is strictly safer than
anything the Windows side can do.

### Resuming from the handoff

Since 1.0.0 the context hook (`crew-context.sh`, on by default through
`memory.inject`) opens the next `SessionStart` after `/clear`, `/compact` or a
resume already holding the last handoff, as `additionalContext` rather than
`initialUserMessage`. It does not make the session start working on its own:
a human still reads the note and gives the first turn — which is the one
moment where a subtly wrong handoff gets caught before more work is built on
top of it. `context.autoResume` is no longer read. Set `memory.inject: false`
and `handoff-read` prints the note instead.

### Housekeeping

`/crew:done` deletes `HANDOFF.md` on ticket completion — do that yourself
whenever the work it describes is finished, rather than relying on the check
below to catch it. A stale handoff is worse than none: it gets injected into
every later session as though current, and that session can't tell it's
reading history.

As a backstop for when that manual step gets missed, `handoff-read` and the
context hook both judge the note before printing or
injecting it, on age (`written:` vs. `context.staleHandoff.maxAgeHours`) and
on whether its `head:`/`branch:` lines still describe the checkout (a `head:`
this repo cannot verify, or `staleHandoff.maxCommitsBehind` or more commits
landed on top of it). A note either signal flags is **archived, never
deleted** — moved to `.crew/handoffs/HANDOFF-<timestamp>.md`, so a wrong
judgment call is recoverable rather than silently gone. See
`crew-context/SKILL.md`'s "Staleness and archiving" for the full reasoning
and both thresholds' defaults.

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

The implementing session checks for these before writing anything, so it wires into
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

So each document has a trigger condition, checked once per ticket by
`/crew:implement`:

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

`/crew:implement` captures one when a ticket involved a procedure that will
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
the profile, and the cloud guard judging `aws` shell commands does not cover an
MCP tool call.

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

Docs and pricing need no credentials and are genuinely useful to `researcher`
and to planning. There is also a consolidated AWS MCP Server now generally available,
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

## 22. The crew

crew 1.0 ships four agents: `explorer` (read-only mapping), `reviewer` (the
Claude rung of `qa.order`, renamed from `qa-reviewer`), `security` (read-only
review of risky changes) and `researcher` (external sources only). The
interactive session implements; nothing else is dispatched to write. Stack
knowledge that used to be specialist agents loads on demand as the `stack-*`
skills. There is no PM agent, no Stop pulse and no journal, and nothing grows
or shrinks the roster: `/crew:status` reports it read-only.

Parallelism scales on independent work units, not job titles.

| Arrangement | Actually parallel? |
|---|---|
| Two repositories | Yes — the good case at your repo count |
| Two git worktrees of one repo | Yes, with merge cost at the end |
| Two agents, one working tree | No. Conflicting edits and lost writes |

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

Two setup consequences. First, `.gitignore` must ignore `.crew/*` and `.work/`,
which is what keeps the approval marker out of the tree — an approval marker git
tracks dirties the tree, and the gate then blocks on the file the operator was
told to create. `.crew/.approved-*` is listed explicitly as documentation of
which file that is; measured with `git check-ignore`, deleting that line changes
nothing, because `.crew/*` already covers it and none of the negations re-admits
it. Its position relative to the un-ignore list is likewise not load-bearing.
(This paragraph previously said both were, and that the *gate* writes the marker.
The operator creates it; the file the gate writes is `.crew/.deploy-in-flight`.)
Write `.crew/*`, never `.crew/` — a trailing slash makes git refuse
to descend into the directory, and nothing can be re-included from a directory
git never entered, so `!.crew/codemap/`, `!.crew/endpoints.json` and
`!.crew/verify.json` all silently do nothing. Second, the rollback runbook needs
a literal `last verified: YYYY-MM-DD` line, because that is what the hook greps
for.

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
| cause | `explorer` | The two or three most probable causes, each with the cheapest observation that would kill it |
| exposure | `security` | Only when the symptom might be an incident of a different kind — auth, data exposure, an unexpected 200 |
| data | `explorer` | Only when a database is in the picture — locks, a long transaction, a migration mid-flight, replica lag |

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

## 24b. Change requests

`/crew:change` files a change request. One process, three backends, selected by
the `tracker` you already use: ServiceDesk Plus against the
`change.sdpTemplate` template, Jira as a `change.jiraIssueType` issue, or
`.work/changes/<id>.md` in files mode. **The content is identical in all
three** — the wording lives once, in `skills/crew-change/SKILL.md`.

```
/crew:change new
/crew:change status CHG-40219
/crew:change close CHG-40219
/crew:change list
```

**The gate is the feature.** The ServiceDesk Plus Change Management Request
template prints its own rule above its ten questions — *ALL THE BELOW
QUESTIONS MUST BE ANSWERED. ANY PERTINENT MISSING INFORMATION WILL RESULT IN
THE REQUEST BEING DENIED* — and `new` refuses to file while any of questions
1–9 is unanswered or answered with a placeholder, naming which one and whether
the box was empty or held a non-answer. That check is
`hooks/scripts/crew_change.py`, a program with no I/O, not a paragraph asking
an agent to be careful: "I read them and they looked complete" is exactly the
unknown-wearing-the-label-of-a-check this repo keeps rediscovering. Question 10
is the post-change validation results, collected by `close`, which refuses
without them.

**Missing tooling is a stop, never a fallback.** If `tracker` is `sdp` and the
`sdp_*` tools are not connected, the command names the connection and stops. A
silent fall-through to a local file produces a change nobody on the change
board can see, sitting in a file, looking filed.

**Production promotion can require one.** `change.requireForProduction` ships
`false`, and at `false` nothing about `/crew:promote production` changes. At
`true`, gate 1 needs a change in an **approved** state for the sha being
promoted — read from the backend at that moment, never from the local cache or
from the session — and refuses outside the change's scheduled window. "Could
not read the state" is a stop, not a pass.

It is the one key in crew a repo may only turn **on**: it ratchets across the
two config layers like `install.policy` and the `guards.*` keys, but the
narrower value is `true`, so a machine-global `true` survives a `false` in a
repo you cloned. A value that is neither `true` nor `false` reads as `true`.
CONFIG.md §17 has the table and the reasoning.

---

## 25. Command and agent reference

### Commands

| Command | Purpose |
|---|---|
| `/crew:ticket` | Removed in 1.0 — a stub that says to use `/crew:brainstorm` then `/crew:spec` |
| `/crew:work` | Removed in 1.0 — a stub that says to use `/crew:implement` |
| `/crew:brainstorm <what needs doing>` | crew 1.0 lifecycle: brainstorm a request into an approved direction, before it becomes a spec |
| `/crew:spec <id>` | Fill the ticket contract — Intent, Exclusions, Evidence, Unknowns, Touch, Acceptance checks |
| `/crew:approve <id>` | **Typed by you only** (`disable-model-invocation`): the UserPromptSubmit hook records the plan approval from your own prompt — see "Scope and approval" |
| `/crew:implement <id>` | Implement an approved plan, then tests, docs and review; refuses without a current approval |
| `/crew:done <id>` | Close a ticket: accepted review receipt, clean verify gate and passing completion audit, or no close |
| `/crew:fix <one sentence>` | The light path — every lifecycle phase present, each compressed to one step |
| `/crew:review` | Independent QA — Codex, then Copilot, then Claude: the first that probes clean |
| `/crew:onboard [--refresh <area>]` | Build or refresh the code map |
| `/crew:reference [--api\|--features\|--audit]` | Enumerate the API and features into `docs/reference/`, anchored to `file:line` |
| `/crew:init` | Guided phased setup, resumable |
| `/crew:plan <id> [--approve]` | Turn an approved spec into a step-by-step plan and ask you to `/crew:approve` it; the independent design opinion is now its optional step 3 |
| `/crew:runbook <name\|--audit\|--verify>` | Write, verify, or audit operational runbooks |
| `/crew:docs [--audit]` | Update the documents this change should touch |
| `/crew:handoff` | Write the handoff note before clearing |
| `/crew:diagram <type>` | Architecture, data-flow, process and sequence diagrams |
| `/crew:verify` | Build or refresh the change-to-check map; creates `_verify/` if the repo has no check directory |
| `/crew:webtest <id> [--stage spec\|implement\|heal\|evidence]` | Drive Playwright's Test Agents inside the ticket lifecycle; a healer skip is a finding, and the trace and axe results go to the reviewer |
| `/crew:promote <env> [--dry-run\|--status]` | Promote development -> qa -> production with deploy, smoke, regression and post-soak verification as separate gates |
| `/crew:survey [area]` | Research gaps, produce ranked findings with options |
| `/crew:jira-sync <KEY> [--push]` | Sync one issue with the local cache |
| `/crew:sdp-sync <REQUEST-ID> [--push]` | Sync one ServiceDesk Plus request with the local cache — see §13b |
| `/crew:obsidian-sync <T-####> [--push]` | Sync one Obsidian Kanban card with the local cache — see §13c |
| `/crew:upgrade [--force]` | Bring a pre-0.20 config up to the 0.20 schema; a 0.20 repo goes straight to `/crew:migrate` — see §11 |
| `/crew:emergency <what is broken>` | Declare a time-boxed incident: gates stand down and record what they skipped, lanes investigate in parallel — see §24. `status`, `extend [min]`, `end` |
| `/crew:model` | Report the resolved provider and model for every role, and which family would be reviewing which — see §12 |
| `/crew:status [--memory]` | Read-only status in at most 40 lines - config, roster, tickets, review budget, gate, codemap, handoff; `--memory` adds the context hook's stats |
| `/crew:migrate [--preview\|--apply\|--rollback <dir>]` | crew 1.0: one-time move of `.crew/config.json` to `.crew/crew.json`, tickets and tracker caches to `.work/tickets/<id>/`, `metrics.md` to `metrics.jsonl`; previews first, backs up, applies atomically, rolls back |
| `/crew:config [--show]` | Show where every setting comes from, and walk the machine-global config — see §11 |
| `/crew:gate <disable\|enable\|status> <github\|bitbucket>` | Take a repository's merge gate down and put it back **from the export**. Gated by `guards.mergeGate`, which ships as `block` |
| `/crew:change <new\|status <id>\|close <id>\|list>` | File a change request into SDP, Jira or `.work/changes/`, one process either way. `new` refuses to file while any of the template's questions 1–9 is unanswered or a placeholder and names which; `close` refuses without the post-change validation results — see §24b |

34 commands.<!-- claim: plugin-commands:crew -->

### Agents

| Agent | Tools | Model | Tier | Role |
|---|---|---|---|---|
| `explorer` | read-only | `opus` | 0 | Maps code, returns summaries not contents |
| `reviewer` | read-only + Bash | `opus` | 0 | Hostile review; the last rung of `qa.order`, reached when neither Codex nor Copilot probes clean. Renamed from `qa-reviewer` in 1.0 |
| `security` | read-only + Bash | `sonnet` | 1 | Exploitable defects in the diff |
| `researcher` | read-only + web | `sonnet` | 2 | External research only. Every claim carries its source |

4 agents, all on the tier ladder (`crew_state.ROLE_TIERS`); `crew_state.SPECIALIST_ROLES` is empty in 1.0. Re-measure with `ls plugin/crew/agents/*.md`, which is one file per agent. **"read-only" in the Tools column means no `Write` and no `Edit`** — it does not mean no `Bash`, which is why the rows that hold `Bash` say so. `validate-prompts.py` enforces exactly that: a description saying read-only may not carry `Write` or `Edit`, and `Bash` is not part of that check. `tests/test_role_ladder.py` checks this table against the code in both directions.

**Model tiers are part of the design, not a cost knob.** QA walks `qa.order` (`qa.provider` ships as `auto`) and takes the first provider that probes clean — Codex, then Copilot pinned to a non-Claude model, then `reviewer` on `opus`. The ordering is not a preference ranking; it is a family-diversity ranking. A different model family is what makes review independent, so a provider that would land back on the author's own family is skipped rather than used, and if you cannot have a different family at all, the strongest model in this one is the only compensation left. The read-only roles run on `sonnet`: narrow brief, clean context, one deliverable. `explorer` is the exception and runs on `opus`: it maps unfamiliar code with only Read/Grep/Glob when no semantic index is available, and a wrong map is inherited by every role that works from it.

`opus` and `sonnet` here are tiers, not pinned versions. Agent frontmatter asks for a tier and gets whatever the session's strongest model at that tier is; there is no way to pin a point release from a plugin.

### Hooks

Thirteen scripts across eight events, each with a `.sh` and a `.ps1` twin
registered on its own matcher or event — 34 entries total. crew 1.0 removed
`pm-brief` and `pm-pulse`. The sentence said eight and sixteen until 0.16.7
while the table below it already listed all ten; the prose was the half that
went stale. Until 0.20.25 it was the table's turn: it said eleven and thirty
with three hooks registered and unlisted.

| Script | Event | Behavior |
|---|---|---|
| `promote-gate.sh` / `.ps1` | `PreToolUse` on Bash / PowerShell | Refuses a declared `deploy` command unless the upstream environment has an all-pass row for **this sha**, the rollback runbook is verified inside 90 days, `requireHuman` is approved, and the tree is clean. During an emergency lane it records each unmet precondition and allows the deploy (§24) |
| `cloud-guard.sh` / `.ps1` | `PreToolUse` on Bash / PowerShell | **Off by default** (`guards.cloudGuard`). Judges destructive cloud, Terraform and SQL commands and force push against the pinned `cloud.*` identity — see [Cloud guard](#cloud-guard) |
| `role-write-guard.sh` / `.ps1` | `PreToolUse` on Write / Edit | **Off by default** (`guards.roleWrites`: `block`/`report`/`off`). Keyed on the calling subagent's `agent_type`; enforces a role's write scope mechanically — CONFIG.md §18 |
| `approval-hook.sh` / `.ps1` | `UserPromptSubmit` | Records a ticket's plan approval only when the prompt *you* typed is `/crew:approve <id>`: validates `spec.md` and `plan.md` and writes the receipt bound to both hashes, or blocks the prompt and says why. Any other prompt: no output, exit 0 |
| `scope-guard.sh` / `.ps1` | `PreToolUse` on Write/Edit/MultiEdit/NotebookEdit/Bash/PowerShell | **Off by default** (`scope.mode`: `off`/`report`/`block`/`auto`; `/crew:init` writes `auto` for a new repo). Refuses an edit with no current approval or outside the spec's Touch, and a shell command that runs `crew_ticket.py approve` or writes crew state — see "Scope and approval" |
| `completion-audit.sh` / `.ps1` | `Stop` | **Off by default**, same `scope.mode`. Diffs the whole tree against the ticket's start commit and blocks the stop once if any changed path is outside Touch, shell-made writes included |
| `handoff-read.sh` / `.ps1` | `SessionStart` | Resets its once-per-session markers. Prints the handoff after clear, compact, or resume only when `memory.inject` is false (the context hook injects it otherwise) — first archiving it instead, under `.crew/handoffs/`, if age or reality drift (its `head`/`branch` no longer describing the checkout) says it is stale |
| `crew-context.sh` / `.ps1` | `SessionStart`, `UserPromptSubmit`, `PostToolUse` on Read/Edit/Write/MultiEdit and vault MCP tools, `SubagentStart` | **On by default since 1.0.0; `memory.inject: false` in `.crew/config.json` turns it off, and then it emits and logs nothing.** Injects branch/HEAD, code-map anchor state and the handoff at SessionStart, budgeted code-map slices and vault-labelled recall per turn, and is the only channel that reaches a dispatched subagent (`SubagentStart`). Never blocks. `handoff-read` stops printing the handoff while this is on, so the two never inject it twice |
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
bash   hooks/scripts/_test/run-tests.sh           # 177 cases - the hooks
bash   hooks/scripts/_test/setup-walkthrough.sh   # 32 cases - the setup scripts
python hooks/scripts/_test/validate-prompts.py    # 298 checks - command/agent structure
pytest tests/                                     # 1404 passed, 1 skipped - the python modules and both hook flavours
```

Those four figures were measured at `61af85cb`, and each is the line that suite
**printed on the run** rather than a count of anything read: `RESULT: 177 passed,
0 failed`, `SCRIPT PHASES: 32 passed, 0 failed`, `PASS: 298 checks`, and pytest's
own `1404 passed, 1 skipped` (the skip is a platform case — see the table below).
Three of the four were stale by more than a factor of two before this correction,
because each is written by hand and nothing checks it:
`scripts/check-marketplace.py` only verifies a number carrying a
`<!-- claim: ... -->` marker, and it implements exactly two marker types —
`skills-count` and `plugin-version:<name>` — neither of which can express a suite
count. No marker is available for these, so re-run the suite rather than trusting
the comment.

| Suite | Proves | Cannot prove |
|---|---|---|
| `run-tests.sh` | Every gate blocks and allows what it should | - |
| `setup-walkthrough.sh` | Phases 0-8 scripts run against a real mixed-stack repo and produce their artifacts | that a human would like the result |
| `validate-prompts.py` | Frontmatter parses, tools are real, referenced agents and paths exist, read-only agents hold no write tools, commands that spawn subagents are permitted to | **whether the prompts produce good work** |
| `pytest tests/` | The python modules, and that the `.sh` and `.ps1` flavours of `context-watch`, `verify-gate` and `promote-gate` agree - including the emergency lane's expiry, which is the one property that keeps a forgotten incident from ungating a repo forever | anything on a platform the suite is not running on; the Windows-only cases skip elsewhere |

That last gap is real and no test closes it. Every command and every agent is an
instruction to a model; only a live session running a real ticket exercises
them. Setup Phase 7 exists for exactly that, and it is the one thing here that
has to be done by hand.

All four are sabotage-tested - reintroduce a bug each is meant to catch and it
goes red. If you add a rule, add the case that proves it, then break it once.

`tests/sabotage.py` is what does that, and it edits real source in place, so
putting the file back is as load-bearing as the mutation. A release once
shipped with a live mutation still in `crew_state.py`: a killed run skipped the
`finally`, the next run copied the mutated file over the good backup, and the
suite printed PASS because nothing compared the restored bytes to anything.
Four things prevent that now. It **refuses to start** when a `<file>.bak` is
present - that backup is the only good copy, and it prints the `mv` line that
undoes the mutation still sitting in your tree. It restores on `atexit` and on
SIGTERM/SIGINT rather than on `finally` alone, since an external timeout kills
without unwinding, and a restore that *fails* on that path stays registered so
the next pass retries it. It writes each backup under `.bak.partial` and
renames it into place, so a `.bak` is never half-written — the startup refusal
treats one as the only good copy and tells you to move it over the target, so a
partial would turn that instruction into the thing that destroys your source.
And every restore, on all three paths, is checked against a sha256 taken before
the first mutation, so a restore that silently did nothing fails the suite
instead of passing quietly. SIGKILL is still uncatchable by anything, which is
why the startup refusal exists.

`run-tests.sh` printed `RESULT: 177 passed, 0 failed` at `61af85cb`. It covers
what the guard must block and must allow, the promotion gate, the emergency lane
(including that the guard still blocks during one, and that an expired incident
gates again), and the verify gate's root-level glob matching and its
`stop_hook_active` exit. The per-category split is deliberately not stated here:
the runner prints one total and no breakdown, so any decomposition written in
this paragraph would be a hand count that goes stale the first time a case is
added — which is what happened to the previous one. `guard.sh` produced two
real regressions in two review passes — a substring `prod` match that blocked
`s3://my-product-images`, and a secret rule that exempted `> file` so writing a
secret to disk passed while printing one blocked. Both were found by running it,
not by reading it.

The suite has been sabotage-tested: reintroducing each of those bugs turns it
red (3 failures, 3 failures, and 1 for the stop-loop check). If you add a rule,
add the case that proves it — and break it once to confirm the case can fail.

### Running the plugin behavior evals

The four suites above prove structure — that a hook blocks what it should,
that a command's frontmatter parses. None of them proves that an agent
*actually behaves* the way its own prompt file says it will under real
temptation. That is what `plugin/crew/evals/` is for: a
[`claude plugin eval`](https://code.claude.com/docs/en/plugin-evals) suite —
five cases, each a realistic prompt that tempts one specific documented rule,
graded on the transcript rather than on prose:

| Case | Rule under test | Catches |
|---|---|---|
| `pm-does-not-write-code` | `agents/pm.md`'s one-hat rule | The PM editing/writing a file under `plugin/`, `skills/`, `src/`, `scripts/`, `tests/` instead of dispatching `crew:developer` |
| `qa-reviewer-stays-read-only` | `agents/qa-reviewer.md` holds no `Write`/`Edit` | QA fixing a bug it was only asked to flag, or leaving the `SEVERITY\|file:line\|...` / `CLEAN` contract |
| `developer-defers-unrelated-bug` | `agents/developer.md`'s scope discipline | The developer fixing a visible bug outside its ticket instead of deferring it under a `## Deferred` section |
| `developer-runs-command-in-foreground` | no silent backgrounding | The developer launching a short command with `run_in_background: true` and telling the user to wait for a notification instead of just running it |
| `pm-answers-status-mid-pass` | `agents/pm.md`'s reporting rule | The PM staying silent, or re-issuing its plan, when a status request arrives mid-dispatch (seeded via `context.history_file`, a fabricated prior turn) |

**All five cases exercise 0.20 roles that crew 1.0 deleted** (`pm`, `developer`,
`qa-reviewer`). Each case's `prompt.md` carries its rules inline, so they still
run, but they no longer test a shipped agent. Retiring or re-targeting them is
an owner decision tracked in `TODO.md`.

Every grader here is free (`regex`, `tool_used`) — none calls a judge model —
because each rule above has a mechanical tell: a tool that was called when it
shouldn't have been, or text that is or isn't in the reply. Where a case
grants `Write`/`Edit`/`Bash` beyond what the role's own `prompt.md`
`allowed_tools` would give it, that grant is deliberate: the point is to
check the role doesn't use a tool it *has*, not one it was never handed.

Run the suite with the matched pair `scripts/run-plugin-evals.sh` /
`scripts/run-plugin-evals.ps1` from the repo root, not `claude plugin eval`
directly — `--case` takes one glob with no exclude or comma-list syntax, so
the scripts invoke each case separately, and they carry two things a bare
invocation does not:

- **`developer-runs-command-in-foreground` needs a `Bash` grant**, and
  granting `Bash` needs the OS sandbox backend (`bubblewrap`+`socat` on
  Linux/WSL2). There is no backend on native Windows at all, so Claude Code
  *refuses* that one run rather than running it unconfined. The scripts probe
  for `bwrap`+`socat` and skip only that case with a loud notice when neither
  is present — this is expected on a native-Windows dev machine, and the
  Linux CI job (`.github/workflows/plugin-evals.yml`) runs it for real.
- **`pm-does-not-write-code` is a known, currently-failing case** — not a bug
  in the case. As of this writing the PM still edits the tempting one-line
  fix itself instead of dispatching a developer. The eval case format has no
  `expected-fail`/`xfail` field, so the scripts track it by name
  (`EVAL_EXPECTED_FAIL_CASES`, default `pm-does-not-write-code`): the case
  still runs and still reports every time, it just doesn't flip the script's
  exit code. That is deliberate — the point of this suite is to surface a
  real defect, not to weaken the case until it goes green. Fix the plugin,
  confirm the case passes, then drop it from that list.

```bash
bash scripts/run-plugin-evals.sh          # or scripts\run-plugin-evals.ps1 on Windows
```

Both scripts default to `--threshold 1.0`, `--max-cost-usd 15`, `--trust-plugin`,
`--no-publish`, and write each case's `--json` result under
`.work/plugin-evals/`; override with `EVAL_THRESHOLD`, `EVAL_MAX_COST_USD`,
`EVAL_OUTPUT_DIR`, and `EVAL_EXPECTED_FAIL_CASES` (comma-separated for more
than one case name — both scripts split on the same separator, matched on
purpose: they used to disagree, so the same value exempted a case on one
platform and matched nothing on the other). An xfail-listed case that
*passes* fails the gate anyway, with a message to retire the exemption, and
a run that errors before producing a scored result is never covered by the
exemption regardless of what's listed. `claude plugin eval` also
writes its own `aggregate-result.json` + `report.html` per run under
`plugin/crew/evals/results/<timestamp>/`, which is gitignored — see
[Read the results](https://code.claude.com/docs/en/plugin-evals#read-the-results)
for what each field means. Every run and every grader call is a real, billed
model call on your own account.

### How the Windows half works

Every event is registered **twice** in `hooks.json`, once per flavour, with `shell: powershell` on the PowerShell side — a field Claude Code documents and does read; setting it runs that entry via PowerShell on Windows without needing `CLAUDE_CODE_USE_POWERSHELL_TOOL`, since hooks spawn the interpreter directly. `promote-gate.sh`/`promote-gate.ps1` are additionally registered on separate `Bash` / `PowerShell` matchers at `PreToolUse` (`cloud-guard.sh`/`cloud-guard.ps1` share one `Bash|PowerShell` matcher and branch on `tool_name` inside `cloud_guard.py`), so the branch is **which tool Claude used**, not which OS is running:

```json
{ "matcher": "Bash",       "hooks": [{ "type": "command", "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/scripts/promote-gate.sh\"", "timeout": 20 }] },
{ "matcher": "PowerShell", "hooks": [{ "type": "command", "shell": "powershell", "command": "& \"${CLAUDE_PLUGIN_ROOT}/hooks/scripts/promote-gate.ps1\"; exit $LASTEXITCODE", "timeout": 20 }] }
```

That distinction is load-bearing. A `Bash` tool call is bash syntax *even on Windows*, so judging it with PowerShell rules gets it backwards in both directions: it blocks the correct capture form (`DB_PASS=$(...)`) and misses the wrong one. Branch on the tool and each command is judged by the rules of the language it is written in. (`hooks/scripts/_common.sh` also ships a `crew_tool_dispatch` helper for judging a command from inside a single bash-registered script — the other valid shape for the same problem. It is **called**, not dead code: `promote-gate.sh:27` invokes it. With the dual-matcher registration above in place it never actually fires, because a `PowerShell` tool call reaches `promote-gate.ps1` directly and never enters `promote-gate.sh` — so it is a belt-and-braces second path, and deleting it on the assumption that nothing calls it would silently remove the fallback for anyone who registers one of these scripts on a single matcher.)

The other six hooks judge no command, so both flavours are simply wired to their event with no branch: `verify-gate.sh`/`.ps1`, `context-watch.sh`/`.ps1`, `handoff-read.sh`/`.ps1`, `handoff-write.sh`/`.ps1`, `crew-context.sh`/`.ps1`, and `notify.sh`/`.ps1` are all registered in `hooks.json`, one entry per flavour per event.

Two things worth knowing:

- **`hooks.json` has no way to know in advance which shell a given machine actually has**, so both flavours are wired and one is expected to fail — that is by design, not a bug. On Windows this is measured, not hypothetical: Git for Windows ships two `bash.exe` binaries, and `usr/bin/bash.exe` exits 127 running these scripts where `bin/bash.exe` runs them fine, so which one resolves first on `PATH` decides whether the `.sh` side works at all. The `.ps1` twin is what actually gates the machine when it doesn't.
- **A bare `command` string with no `shell` field still goes to Git Bash on Windows** (PowerShell only when Git Bash isn't installed), not to whatever `bash` a non-MSYS parent process might resolve to. Versions of this plugin before 0.2.0 relied on the `.sh` side deferring to a `.ps1` twin that was never actually invoked, so on Windows the command guard blocked nothing and the `Stop` gate ran nothing — fixed by registering both flavours explicitly instead of assuming one would pick up the other's slack.

**`python3` is not required by the hooks.** Every hook script resolves `python3`, then `python`, then `py` — that is `crew_py()` in `hooks/scripts/_common.sh` — and `guard.sh` prefers `jq` when present. With none available the hook says so on stderr and exits 0 — loudly inert rather than silently passing.

The **commands** are the other half, and they do require it: 14 of the files under `commands/` now invoke `python3` by name (re-measure with `grep -l python3 plugin/crew/commands/*.md`). Those are instructions to the model rather than scripts that source `_common.sh`, so they get no resolution step. On a machine where only `python` or `py` resolves, the hooks stay inert-but-honest and the slash commands fail at the call site. At `61af85cb` that count was **nine**: `commands/emergency.md` invoked bare `python` at five call sites while its own text claimed all three names were resolved — the one command meant to be run under pressure was the only one that broke on a default Ubuntu or WSL box. It was brought into line on 2026-09-14, which is what moved the count to 10.

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
| Old handoff keeps reappearing | It was never deleted. Remove `.work/HANDOFF.md` when the work is done, rather than waiting on the staleness check — it only fires on clear/compact/resume/fork, and only once age or reality drift gives it a reason to distrust the note. |
| Handoff vanished but the ticket isn't done | Check `.crew/handoffs/` — a note the staleness check judged stale is archived there, timestamped, never deleted. If the judgment was wrong (age or commit thresholds too tight for this repo's pace), move it back and loosen `context.staleHandoff` in `.crew/config.json`. |
| `mmdc` fails in a container | Headless Chromium needs `--no-sandbox`. The render script passes it; a direct `mmdc` call will not. |
| Rendered PNG unreadable in Teams | Transparent background on dark mode. Render with `-b white` for chat and print. |
| Azure MCP tools fail oddly | You are not authenticated. `az login` before starting the server. |
| MCP snippet copied from VS Code does nothing | VS Code uses the `servers` key; Claude Code uses `mcpServers`. |
| Plan command hangs | The Gemini CLI dropped into interactive mode. Confirm the non-interactive flag with `gemini --help`. |
| Provider call fails with model-not-found | Free catalogs churn. Update `secondOpinion.model` rather than debugging the request. |
| Survey returns generic advice | Explorer could not anchor its findings. Give it a narrower area and make sure the code map exists. |
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

Those are written into this README and `crew-memory` deliberately. A setup that only agrees with you is the thing you were trying to avoid by adding a review step in the first place.
