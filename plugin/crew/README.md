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

**On native Windows, crew picks a shell route for its long-running jobs.** The
per-step tests and verify-map checks in `/crew:implement`, and graphify builds,
run through `crew_shell.py run`. It routes by `shellRoute.mode` (`auto`, `wsl`,
`powershell` or `gitbash`) and prints one `crew-shell:` line naming the route
and why. `auto` uses WSL2 when it is usable and either the repo lives inside
WSL or a measurement showed WSL faster for this repo. Otherwise it runs plain
argv directly and bash syntax in Git Bash. A bash string never goes to pwsh.
`/crew:status` shows the route on a `shell` line. Hooks do not change, and
nothing changes on Linux, macOS or inside WSL. See "Choosing the shell route on
Windows" in `skills/crew-setup/platform.md`.

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

Once `/crew:verify` has built `.crew/verify.json` (Phase 5), setup offers one more,
opt-in output: `.github/workflows/crew-verify.yml`, a pull-request job that runs
`verify-gate.sh --ci` with crew fetched, outside the workspace, at the commit you installed (never a
branch). Network and host rules are named there but not run.

<!-- crew-ignore-policy:list -->
**Commit the part that is about the code, not the part that is about your box.**
The policy `/crew:init` writes is `.crew/*` ignored plus a named un-ignore list —
`!.crew/codemap/`, `!.crew/endpoints.json`, `!.crew/verify.json`,
`!.crew/standards.md`. Those four describe the repository: the code map, the
endpoint ledger a security scan is owed against, the verification map and the
development standards overlay (the `crew-standards` skill). Commit them, and `_verify/`, `docs/adr/`
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

**`.gitignore` kept right for the languages in the repo (T-0039).** `/crew:init` Phase 1, `/crew:onboard` and `/crew:onboard --refresh` run `crew_gitignore.py apply --root .`; `/crew:implement` step 6 runs `check`, and `/crew:status` shows one `gitignore` line. Languages come from the files git lists (never an ignored `node_modules/`), the patterns from a table vendored from github/gitignore (CC0-1.0, `NOTICE.md`), and "already covered" is measured with `git check-ignore` against the working tree's ignore files only - a machine-global excludes file does not travel with a clone, so it never counts. Missing patterns are added without asking (owner decision) inside one `# crew:gitignore:managed` block at the top of `.gitignore`, so every human rule below it wins; crew never edits a human line, never touches the `.crew` policy block, and never drops an entry from its own block. It never untracks: a tracked file a new pattern matches is named, and a tracked secret-shaped file (`*.pem`, `.env`, ...) is a `needs-owner` line, exit 3. The `.env.*` row re-includes the usual templates (`.env.example`, `.sample`, `.template`, `.dist`, `.defaults`). Known limit: a committed test-fixture key or certificate (`*.pem`, `*.key` under `tests/`) is still reported `needs-owner`; there is no acknowledgement mechanism, so the owner decides. A directory pattern that would defeat a human `!` re-include is a `conflict`, not added. `# crew:gitignore:off` in `.gitignore` makes it report-only; inside a ticket whose Touch lacks `.gitignore` it refuses (exit 5), because an ignore line could hide the ticket's own files from the completion audit. Exits: 0 current, 1 pending, 3 owner, 4 unknown (including an unreadable file or any unexpected error - never 1), 5 refused.

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

Before the first plan step, `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/recurring_findings.py" --root . --ticket <id>` prints the **recurring-findings checklist**: the defect classes earlier reviews kept finding (processes and races, claims that are not true at HEAD, tests that cannot fail, fail-open handling, PowerShell/Bash drift, guard bypass, version and registration, in descending order of how often they were found), only those whose path globs meet the spec's Touch list, at most four probes each and 60 lines in all, with a cut announced by id. The data is the tracked `skills/crew-qa-standards/references/recurring-findings.md`, so every machine prints the same list; an unreadable spec or Touch list (a spec that is not a regular file, such as a FIFO, included) lists every class under `UNKNOWN:` and exits 1, and an unreadable or malformed data file prints `UNREADABLE:`/`PROBLEM:` instead, never "no class applies", and also exits 1. `/crew:implement` pastes it into every developer dispatch and re-runs it before the self-check, and `/crew:review`'s prompt carries the classes keyed to the bundle's changed files, after the standards checklist (`recurring_findings.review_block`). It is advisory: no gate reads it.

Between the refresh and the review sits the **required standards self-check** (see "Development standards" below): every standard in the effective set answered in `.work/tickets/<id>/selfcheck.md`, then stamped with `crew_standards.py stamp`. `/crew:review` refuses to spend a round without a current stamp.

### Review it

```
/crew:review
```

Codex if available, the `reviewer` agent if not — and it always tells you which ran. Findings are reported verbatim before any argument about them. `BLOCK` items get fixed, smoke reruns, review runs once more — and that second round is the last one.

The reviewer reads a **bundle**, not a `git diff` of the committed range: `hooks/scripts/review_patch.py` stages committed, staged, unstaged and untracked changes into a temporary index (your own index is never written) and diffs the ticket base against it, leaving out every path byte-identical to the latest merged integration commit — `git merge-base HEAD <base branch>`, the base branch being `tickets.baseBranch` when set (T-0061) — (`hooks/scripts/merged_main.py`, T-0100): after a merge of main the reviewer reads this ticket's change, not the landed work main brought in. A file main changed that the ticket changes again is diffed from the merged commit's version, so main's lines read as context and only the ticket's as `+`/`-`. The manifest's `merged_main` names that commit, the paths left out and the paths diffed from it (`diffed_from_merged`), `bundle_base_tree` the tree the patch was diffed from, and the prompt prints a `merged main:` line; when the commit cannot be told (no integration ref, a configured base branch naming no commit, detached HEAD) nothing is left out and each of those says `could not tell`. `merged_main.fork` is the merge-base of the ticket start and the merged commit; when git gives no answer for it, it is `null` with a `fork_reason`, every path main also changed is diffed from the start (more shown, never less, so main's lines there may read as the ticket's), and that is said by `fork_reason`, the summary line's `diffed-from-merged=could-not-tell`, the prompt's `merged main:` line and `--check-receipt`'s `fork: could not tell` — an empty `diffed_from_merged` never passes as "main changed none of them". Renames, file-mode changes, binary files (git's marker plus both blob ids and sizes) and submodules are listed in the manifest. A large bundle is split into ordered parts — never truncated — and the manifest records a sha256 over them. `.work/` (crew's scratch) and the generated `graphify-out/` are never in the bundle; the manifest's `excluded` names both and the prompt's bundle block prints them, so a reviewer knows what was left out (T-0092).

Then `review_run.py` itself appends the round's line to `.crew/metrics.md` - the main checkout's, also from a linked worktree - right after the ledger records the round: `<date> | <ticket> | <provider>/<model> (r<N>, std:..., <family>) | <BLOCK> | <FIX>`, with `INCOMPLETE` in both count cells for a round with no verdict and the family named against the author's (`same-family`, `different family` only when a dispatch record proves it, `different family unproven` when it came from config, `family unknown` when it could not be read, or `same-family: codex limit`), and the `std:` token the round was reserved under, never one recomputed afterwards. A symlinked or junctioned `.crew`, or a metrics path that is not a regular file, is refused, not followed. It used to be a prose step, and 118 of 162 rounds had no line (L-0578). A write that fails never changes the verdict; it prints the exact line to append by hand. That line is not bookkeeping; `/crew:status` reads it to show whether any of this is catching anything. Every reader (`crew_state.py`'s health, `crew_standards.py metric`, `/crew:status`) resolves the same file through `crew_common.metrics_crew_dir`: from a linked worktree it is the main checkout's, and when git cannot name the main checkout each says `could not tell` and reads nothing rather than the worktree's own copy.

### Review: verdicts and the two-round budget

(This section lives here because the 1.0 guide sources under `docs/guides/crew/src/` do not exist yet; the HTML guides in `docs/guides/crew/` have no generator.)

**The verdict is computed by a script**, `hooks/scripts/review_verdict.py`, from the reviewer's output and exit status:

| Verdict | When |
|---|---|
| `CLEAN` | exactly one `CLEAN` line, exit 0, and a READ line for every bundle part - its path exactly as listed, or its bare file name |
| `FINDINGS` | at least one `BLOCK`, `FIX` or `NIT` line, and nothing below applies - including a round recovered despite harmless stray lines (below) |
| `INCOMPLETE` | non-zero exit, unknown exit, timeout, empty output, any line outside the contract that is not recovered (a finding with an empty field, a decorated or lower-case contract line, a `|`-table row, a line matching the shortfall wording list `review_verdict._SHORTFALL`, and any stray line beside `CLEAN`, included), a part not acknowledged, a bundle part that no longer matches its manifest size and sha256, an unreadable line in Codex's event stream, or `CLEAN` beside findings. Each INCOMPLETE is classed `tool`, `reviewer` or `tree` (`review_verdict.failure_class`); only `tool` is refunded (below) |

**Harmless stray lines are recovered, never beside `CLEAN` (L-0576).** A round whose findings parse, whose every part is acknowledged, that exited 0 and has no other reason, is `FINDINGS` even when it also printed prose, a heading or a code fence - the shape that cost T-0100 round 2. The ignored lines go in `review.json`'s `ignored_text`, their count in its `ignored_lines` (an int on every round, 0 when none) and in the ledger row (null there when that value is missing or malformed - unknown is never 0), and a `review: FINDINGS kept; N line(s) outside the contract were ignored` line names the first; report them with the findings. A stray line that might be a contract line the parser failed to read, or that matches the shortfall wording list `review_verdict._SHORTFALL` ("incomplete", "skipped", "truncated", "could not review", ...), is "could not tell" and keeps the round `INCOMPLETE`. That wording net cannot be complete: an admission it misses ("I only inspected one of the nine files") is ignored as prose and the round is `FINDINGS`, which is why recovery never reaches `CLEAN` and the lines are always shown. `review_verdict.py`'s docstring states the rule in full.

A READ line naming anything else - a path outside the bundle, or the same file name in another directory - counts for no part; the part it failed to cover is what makes the round `INCOMPLETE`. The prompt quotes that form from `review_verdict.READ_FORM`, so the two cannot disagree again (T-0079). From crew 1.0.50, `review.json`'s `parts_expected` and `parts_missing` name each part by its listed path, not its bare file name. `INCOMPLETE` is never `CLEAN`. Codex runs as `codex exec --json --sandbox read-only` with stdin closed, and a turn that failed in its event stream is `INCOMPLETE` even when the process exited 0. Each round writes `.work/tickets/<id>/review.json` (verdict, counts, provider, model, model family, bundle hash, base/head, round).

**Two rounds per ticket, in total.** `hooks/scripts/review_ledger.py` keeps the ledger at `<git-common-dir>/crew/review/<id>.json`, so every worktree of the repo shares it; the merge train (below) keeps its queue beside it, at `<git-common-dir>/crew/train/`. `review_run.py` reserves the round *before* it launches the reviewer, so a reviewer that crashes or hangs has still spent it. A third reservation is refused and the ticket becomes `NEEDS_REPLAN`; that refusal and an explicit `review_ledger.py --ticket <id> --reject --by <who>` are the only ways in, so finishing round 2 with `FINDINGS` or `INCOMPLETE` leaves the ticket `REVIEWED`, not `NEEDS_REPLAN`. A result is recorded only for the most recent reserved round, only once, and only by the provider and model it was reserved for; once `NEEDS_REPLAN`, no result changes the state. No environment variable, flag or config key raises or resets the budget; deleting the ledger file by hand is outside that promise, and is what a reviewer of your repo's history would see. Since crew 1.0 (T3) the one way past `NEEDS_REPLAN` is an approved successor plan: approving a *different* plan (`/crew:approve <id>`) opens a fresh budget of two rounds under that plan (see "Scope and approval" below); re-approving the same plan does not.

**No new linter findings before a round is reserved (L-0574).** After the CLEAN-receipt check and the verify gate, and before the standards self-check, `review_run.py` runs `hooks/scripts/review_checks.py` over exactly the files the bundle changes, with the linters `.crew/verify.json` lists under `preReview` (ruff, ShellCheck, PSScriptAnalyzer with a rule allowlist, actionlint). Each file is linted at its base blob and at its bundle blob. The linter config comes from the bundle too, never from the live tree. A finding the bundle adds, keyed by path, rule and message with line numbers ignored, refuses the round with exit 5 and nothing spent, and `--allow-unverified` does not override it. A tool that is missing, crashes, times out, prints unparseable output, or cannot parse a changed file on either side is `COULD NOT CHECK`, never a pass. It also refuses with exit 5, unless `--allow-unverified` is given, which `review.json` records as `prereview.overridden`. A linter with no matching changed file is `n/a` and is never even looked for. Only an active incident stands the checks down, logging a `prereview-checks` skip. No `preReview` key means no checks, and the run says so. `preReview` accepts only `linters`; any other key, `_note` included, is could-not-check. A linter config the bundle renames away is gone, not reloaded from the base. A tool row the checks cannot read does not discard the rows already read, so a new finding among them still refuses, and a timeout kills the linter's whole process group. The `preReview` config is the bundle's own `.crew/verify.json` (the base commit's, or the bundle's change to it), never a later working-tree edit; only an untracked map is read from the working tree. Every program the checks and the review runner start is resolved from an absolute path or absolute `PATH` entry, never the current directory; every file they read must be a regular file reached through no symlink (a symlink at the file or at any directory below the repo root or scratch directory, a FIFO or a device is could-not-check); a linter's rows are kept beside an unexpected exit, a row missing a field is never given a default, every printed field and every line `review_run.py` prints is one line, and on Windows a timeout ends the linter's or reviewer's whole job object; a config `null` or a key a tool does not use is could-not-check; and each run's record is bound to the round it reserved (`prereview-<ticket>-r<N>.json`). A spent budget skips the checks, because the reservation refuses anyway. `review.json` carries `prereview`: the record written for this bundle, in exactly the shape the checks write and with a result its checks add up to, or `{"result": "not-recorded", ...}`, never a bare null. Run the same checks without reserving anything with `review_checks.py --root . --manifest <scratch>/manifest.json` (exit 0 pass, 1 new findings, 3 could not check).

**A round the tool lost is refunded (crew 1.0.76, T-0087).** An `INCOMPLETE` round is classed from facts, not from reason text, in this order. A bundle part or web-test report that changed under the reviewer is `tree`. Otherwise, an answer that never arrived intact is `tool`: a timeout, an unknown or non-zero exit, empty output, or a failed or unreadable Codex stream. Anything else is `reviewer`, meaning output that arrived and broke the contract. Only `tool` is refunded, automatically and at most `REFUND_LIMIT` (2) times per plan. A refunded round stays in the ledger, but it is not charged against the two-round budget. A third tool failure under the same plan is recorded as `refund_refused` and counts. These are never refunded: `reviewer` and `tree` rounds, a round with no recorded result, and ledger rows written before 1.0.76, which carry no `failure_class`. The refund shows in the ledger row (`failure_class`, `refunded`, `refund_refused`), in `review.json`, in the `review:` lines (`review: round N was a tool failure (...); refunded - ...`) and in `/crew:status` (`1/2 rounds used, 1 refunded`). Nothing else resets the count, and a successor plan starts both the budget and the refund count afresh. This is the review-side twin of T-0082's gate rule: a killed, hung or timed-out run is "could not tell", never a pass.

**Harness checks (T-0087).** A committed golden corpus of real, redacted reviewer output (`tests/golden/review/`, built by `tests/golden_build.py`, which also replays every local review with `--check-local`) runs through the verdict parser. `tests/test_review_contracts.py` feeds each producer's real output to its real consumer at every review-format seam: the manifest, READ and finding lines, the verdict vocabulary, the gate record and the approval and ledger paths. `tests/test_review_canary.py` runs a whole review end to end against a replayed real Codex stream. `.crew/verify.json`'s harness rule runs all of these, plus `scripts/check-tooling-pr.py`, which refuses feature work riding on a harness change. The facts crew relies on from Codex CLI, `wsl.exe` and `gh` output are in `docs/external-tool-formats.md`, with sources.

**The receipt is bound to the bundle.** A `CLEAN` round writes an acceptance receipt carrying the bundle sha256. `FINDINGS` you decide to accept become one only through `review_ledger.py --ticket <id> --accept --by <who>`, which records who and when and refuses if the tree changed since that round. It accepts only the most recent round, only once that round completed with `FINDINGS`, only once per round, and never once the ticket is `NEEDS_REPLAN` — so round 2's FINDINGS can be accepted until a third reservation is refused or the ticket is rejected, and not after (since 0.20.18). `review_ledger.py --ticket <id> --check-receipt` rebuilds the bundle from the receipt's base and exits non-zero when there is no receipt or the hash differs — any edit after review invalidates it; committing the reviewed change does not. `/crew:done` will gate on it; for now, run it yourself before you open the pull request.

**Review closure: a final 0-BLOCK round auto-accepts (L-0510, owner policy 2026-09-30).** A changed default for every install: when the last round the budget allows completes as `FINDINGS` with 0 BLOCK from a reviewer of another model family than the author's (Codex or Kimi; owner decision 2026-10-01), `review_run.py` prints `review: auto-accept: eligible` and `/crew:review` step 3 runs `review_ledger.py --ticket <id> --auto-accept --follow-up <new id>`, then files ONE follow-up ticket whose `direction.md` quotes every FIX/NIT line verbatim. The receipt is kind `auto-accepted`, `accepted_by` is fixed to `auto: 0 BLOCK, owner policy 2026-09-30`, and it carries the lines, the follow-up id, the provider, the model family and the sha256 and `ignored_lines` count of the `review.json` it read; it stands only while those equal its round's and that file's (an edited, missing, linked or unreadable `review.json`, or one with a duplicate key, is could-not-tell). The ledger refuses, changing nothing, unless the row's `provider` is `codex` or `kimi` and its `model_family` is recorded and not `claude` (a Claude-fallback round, a missing provider or family, and any other provider such as Copilot are refused), the verdict is exactly `FINDINGS`, the counts are integers with BLOCK 0, the verdict was not recovered from stray lines (the row's `ignored_lines`, L-0576's count, is 0, and so is this round's `review.json` count; missing, mistyped or unreadable is could-not-tell, never 0 - owner decision 2026-10-01, so no round is eligible until L-0576 lands), the recorded finding lines are each one FIX or NIT line (no embedded line break) and agree with each count separately, no healer skip is open and the webtest state is known, the round is final under the current plan, and the tree still builds the reviewed bundle; every case it cannot tell (INCOMPLETE, a missing or mistyped count, a round recorded before this rule) is a refusal. Any BLOCK or refusal stops for the owner with 2-4 options, recommended first. `--accept --by` refuses a name starting `auto:`. `--check-receipt` stands an auto receipt only while its round still passes the guard, and `review_ledger.py --ticket <id> --check-follow-up` matches every line verbatim (split on newlines only, so U+2028 is text) and as often as the receipt carries it, and treats a non-UTF-8 `direction.md` or an unknown receipt kind as could-not-tell; `/crew:done` does not run it yet (L-0568 adds it to check 1), so run it yourself before closing. Specialist and control-rerun BLOCKs are not on the ledger: `review.md` step 3 says the lane does not auto-accept then. No flag or config key turns it off. An auto-accepted receipt, like an owner-accepted one, never short-circuits a later review.

The prompt every reviewer reads also carries the ticket's spec sections (Intent, Exclusions, Evidence, Unknowns, Acceptance checks) from `.work/tickets/<id>/spec.md`, the plan from `plan.md`, the codemap landmines, the verify gate's evidence for HEAD (a clean local pass, the local gate's answer, or a CI receipt the gate accepted), the development standards checklist (below), and the recurring-findings checklist the implementer saw, scoped to the bundle's changed files (`recurring_findings.review_block`: it says the list does not bound the review, and a manifest whose file lists are unusable lists every class under `UNKNOWN:`). A missing piece is written into the prompt as `MISSING`, never left out; a repo with no verify gate says `No verify gate` instead.

You open the pull request. The crew stops at the boundary of your judgment.

### Landing through the merge train

Parallel lanes that gate against a base which then moves pay for a catch-up merge and a fresh gate round each time. Since L-0520 a clone can serialise the **gate+land** stage per overlapping Touch set while lanes keep implementing in parallel — nothing on the implement path consults the train. `hooks/scripts/crew_train.py` keeps one locked queue per clone under `<git-common-dir>/crew/train/` (`state.json`, an append-only `events.jsonl`, and `merge-log/<id>.jsonl`), shared by every worktree of the clone.

- **Armed per clone, not by config.** `crew_train.py arm` creates `state.json` exclusively; until then nothing changes, so a single session is untouched. `disarm` refuses while any entry exists. There is no config key.
- **The queue rule.** An entry (one ticket on one base) holds the train iff no holding entry and no earlier-queued waiting entry on the same base has an overlapping Touch set. Overlapping tickets gate and land one at a time in the order they reached their gate; disjoint ones hold at once; the same Touch on two bases is two trains. Overlap is conservative: two Touch entries overlap when the literal prefix of one (its case-folded segments before the first wildcard segment) is a segment prefix of the other, so `a/*.py` and `a/b/c.py` serialise. Refresh artifacts (`.crew/codemap/`, `.claude/rules/`, `docs/diagrams/`, `graphify-out/`) are not counted for overlap; version files named in Touch are, so in this repo crew tickets share one train. The moved-path checks below (`merge <base> first`, `check-land`) and the merged-path notices judge the **full** Touch, refresh artifacts included: a base that moved a path the ticket names is a tree its verdict did not cover (L-0558). An undeclared Touch — no spec.md, no `## Touch`, no bullet, a parse problem, unreadable — overlaps everything, and `status` names it `undeclared: <why>`.
- **Take it before the gate round.** `crew_train.py acquire --ticket <id>` holds the train or refuses (exit 1): waiting behind an overlapping ticket, or `merge <base> first` when the base holds commits touching this ticket's Touch that HEAD lacks. It names the blocker and each colliding pair (`colliding: <mine> x <theirs>`), and every wait is logged as a `wait` event with those paths. In this release the lane (or you) calls it before `/crew:review`; `review_run.py` taking it itself is a follow-up (L-0526).
- **Catch-up is a merge, with rerere but never autoupdate.** `crew_train.py catch-up --ticket <id>` fetches the base (see the land check; a failed fetch is could-not-tell, exit 3), makes `rerere.enabled` true in this worktree (`git config --worktree` when `extensions.worktreeConfig` is already on, else `--local`; never `--global`, never switching the extension on), and runs `git -c rerere.autoupdate=false merge --no-edit` on the SHA that fetch returned (never the ref by name) — never a rebase or cherry-pick. It never writes `rerere.autoupdate` (owner rule, 2026-09-30: a shared rerere cache once replayed another lane's version resolution unseen), so a replayed resolution is left in the working tree **unstaged** for you to inspect and `git add`. The version files — `plugin/crew/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `plugin/PLUGINS.md`, `CHANGELOG.md` — are never replayed: each one the merge left conflicted gets `git rerere forget` and its conflict markers back (`git checkout -m`), and the output names it as forgotten, for you to resolve by hand. It refuses a dirty tree (untracked files outside `.work/` included), and never commits a conflicted or rerere-resolved merge: `MERGE_HEAD` is left for you to resolve, `git add` and `git commit --no-edit`. Every catch-up is a line in `merge-log/<id>.jsonl` (head before, base sha, outcome, conflicted, rerere-replayed and rerere-forgotten files); `merge-log --ticket <id>` prints it; show the replayed files to your reviewer as changes to review (the prompt lists them itself once L-0526 lands). It works whether or not the train is armed.
- **The land check.** `crew_train.py check-land --ticket <id> [--pr <n>]` refuses unless this worktree's entry holds the train, the base fetched (with an explicit `+refs/heads/<branch>:refs/remotes/<remote>/<branch>` refspec, so the ref judged is the one fetched even where `remote.<remote>.fetch` is unset; a base that then disagrees with `FETCH_HEAD` is could-not-tell; every later check judges that fetched SHA, never the ref by name, which another worktree's fetch can move), `git merge-tree --write-tree <base> HEAD` is clean (conflicts are listed; a git older than 2.38 is could-not-tell), the base has not moved in Touch paths since HEAD's merge-base with it (moved only outside Touch is allowed and said), and HEAD carries a current review receipt and a verify gate `VERIFIED` or `NO_GATE` (a CI receipt VERIFIED for HEAD counts as `VERIFIED`, above); HEAD is read once before those checks, and the hold and HEAD are re-checked under the lock before it answers. Then it prints `LAND_OK head=<sha>` and `gh pr merge <n> --merge --match-head-commit <sha>`. The train never merges, pushes or opens the PR; only autopilot's ship step does, under `autopilot.ship` (T-0011). After the merge, `release --ticket <id> --merged <merge sha>` records the merged paths; every overlapping entry is told once, on its next `acquire` or `status`, `<id> merged <sha> touching <paths> - merge <base> now` (a merge whose paths cannot be read is told to every entry).
- **Nothing is broken silently.** The train is "not armed" only when `state.json` is proven missing (not found under a directory); one that cannot be looked up, read or parsed, has an unknown schema, a malformed top-level field (`schema`, `seq`, `order`, `entries`, `armed_at`, `armed_by`; a boolean or float is never an integer) or a malformed entry, a git call that fails, and a lock still held after 10 seconds are could-not-tell (exit 3); an `events.jsonl` record without an event's shape is told to every entry as `could not tell whether ... concerns you` on every read until the file is repaired, whatever its seq, never skipped, and `arm` refuses on it; events are written before `state.json` and both are rolled back if either write fails, so no hold or release commits unlogged; a lock is never removed for being old. A hold that looks dead (its worktree gone, its head already in the base, held for hours) is printed `stale?: <evidence>` and never released automatically: `release --force --by <who> --reason <text>` releases it and logs a `force-release` event the other lanes see.

Exit codes: 0 ok or holding, 1 refused or waiting (and `train not armed`), 2 usage, 3 could not tell. What it does not cover: lanes in separate clones of one repository (each clone has its own train), and a delta gate — until one exists, the verdict `check-land` accepts after a catch-up is a full review receipt on the merged head. A refusal names the landing order: `catch-up` (resolve any conflict), bump the version one past the base's, refresh the artifacts, commit, gate the merged head, review it again if `review_ledger.py --check-receipt` reads stale, then `check-land` again — so the tree the gate passed is the tree that lands. After the review, a re-anchor changes only the `anchor:` sha (or a diagram header's sha) and regenerates the rules; provenance prose goes in the ticket's `notes.md`.

### Development standards and the pre-review self-check

Review kept finding the same classes of defect, so since T-0085 crew applies them the first time the code is written. The `crew-standards` skill ships **GEN-01 to GEN-12**, crew-generic standards mined from crew's own QA review findings (`skills/crew-standards/references/generic.md`; each cites the findings that earned it and needs three distinct reviewed change sets). Per-language sets (T-0086) are further files in that directory, each applying when a changed file matches its `applies-to` globs, under the same three-change-set bar. The first ships: `references/python.md`, set `PYTHON`, nine standards (PYTHON-01, -03, -04, -06, -07, -08, -10, -11, -13), applied when a changed file matches `**/*.py`; the `stack-python` skill lists its eight candidates, which lack a third change set. The other stacks (SQL, PHP, PowerShell, .NET, Terraform, Node.js, Angular) follow as further files.

A repository adds its own in the **overlay**, `.crew/standards.md` (set `REPO`, tracked through the ignore policy's un-ignore list): standards of its own and `## Supplements <GEN-id>` sections carrying its literal commands. The overlay adds and supplements; it never removes, reuses or weakens a plugin standard. No overlay means generic only, and the summary says so. An overlay that cannot be read, is not UTF-8 or is malformed is could-not-tell: the stamp and the review gate refuse until it is fixed.

| Where | What happens |
|---|---|
| `/crew:plan` | Each step carries `Standards: <ids>` (or `none - <why>`), and the self-review asks whether every step names them |
| `/crew:implement`, `/crew:fix` | `crew_standards.py init` writes `selfcheck.md` with a row per effective standard; each is `addressed` with evidence or `n/a` with a reason; `crew_standards.py stamp` refuses an incomplete record and binds a complete one to the review bundle's sha256 and the standards digest. A recorded start that is gone or no longer an ancestor of HEAD stamps against the same merge-base fallback `/crew:review` bundles with, marked `(fallback)`; so does a start first recorded on a branch already past the default branch (recorded as the merge-base, a guess). A `.crew/.scope-base` that cannot be read is refused without naming `--record`, which would rewrite it with one ticket's entry. Any later edit needs a new stamp |
| `review_run.py` | Before reserving the round, for every provider, once the budget is known not to be spent (a spent budget is refused first, exit 4): a missing, unreadable, incomplete, unstamped or stale self-check is exit 2, no round spent. It applies to a ticket with an approval receipt, or whose receipt cannot be proven absent; in an active incident it stands down and logs a `standards-selfcheck` skip. On a pass it prints `review-run: standards self-check current (std:<8 hex>)` |
| The review prompt | Ends with the effective set's rules and self-check questions. The author's answers are withheld from the prompt, so the reviewer judges applicability itself, and the list does not bound the review. Withheld, not hidden: `selfcheck.md` stays in `.work/tickets/<id>/`, which a reviewer that can read the checkout could open; the prompt never names it |
| After a round | `crew_standards.py proposals` writes `standards-proposals-r<N>.md` with every BLOCK/FIX line verbatim, and refuses an `out.txt` the verdict parser calls INCOMPLETE, writing nothing; you approve or reject each proposed standard or amendment. Nothing is added to a standards file automatically |
| `.crew/metrics.md` | Written by `review_run.py`, one row per recorded round, in the main checkout. The reviewer cell carries `std:<first 8 of the digest>` (or `std:none`, or `std:unknown` when it could not be computed); `crew_standards.py metric` prints first-round BLOCK+FIX per ticket before (no `std:` token) and after (`std:<8 hex>`), with unknown-round rows, `std:none` rows and unreadable `std:` tokens counted on neither side, and "not enough data" below 10 tickets a side. `--record` appends a pipe-free summary line the other readers skip. `crew_standards.py metric` reads, and `--record` appends to, the main checkout's file from a linked worktree, and exits 1 without writing when git cannot tell which file that is |

### Scope and approval

A crew 1.0 ticket is a directory, `.work/tickets/<id>/`, holding `direction.md`, `spec.md` (Intent, Exclusions, Evidence, Unknowns, **Touch**, Acceptance checks) and `plan.md` (steps, each with `Files:`, `Test:`, `Risk:` and `Standards:`). `## Touch` is one repo-relative glob or path per bullet line; `*`, `?` and `[...]` match within one path segment and never cross `/`, `**` spans segments, and an entry with no wildcard also covers everything under it as a directory. These scripts in `hooks/scripts/` enforce it:

| Script | What it does |
|---|---|
| `crew_ticket.py validate --ticket <id>` | Every spec section present; every plan `Files:` entry inside Touch. A plan path outside Touch is an error, never a silent widening. |
| `/crew:approve <id>` — `approval_hook.py` (UserPromptSubmit) | **How you approve.** (Several tickets at once: below.) When the prompt *you* submit is exactly `/crew:approve <id>`, the hook reads `spec.md` and `plan.md` once, validates those bytes and writes `<git-common-dir>/crew/tickets/<id>/approval.json` with their sha256 and their approval digest (below), `approved_via: "user-prompt"`, and the prompt's session id and time. A contract that does not validate blocks the prompt and says why; nothing is recorded. |
| `crew_ticket.py approve --ticket <id> [--by <who>]` | The same receipt from a shell, for tests and CI, marked `approved_via: "cli"`. The guard and the audit accept a `cli` receipt only when `scope.allowCliApproval` is `true` (default `false`). |
| `crew_autopilot.py approve --ticket <id>` | T-0010: the `autopilot` receipt (`approved_via: "autopilot"`), written only while autopilot is armed and `autopilot.approval` allows it — which always needs `scope.allowCliApproval: true`. `accepted` re-checks the policy on every read. It approves one ticket at a time and can never carry a group confirm: `crew_ticket.approve` refuses `via=autopilot` with an `expect`. |
| `crew_ticket.py status --ticket <id>` | `approved`, `stale` (spec or plan edited since, other than the header's status value) or `none`. Exit 0 only for `approved`. |
| `crew_ticket.py activate --ticket <id>` | Makes `<id>` this worktree's active ticket (`<git-common-dir>/crew/active-ticket`, keyed by worktree), and records the ticket's scope base at branch cut (an existing record is kept; a "could not tell" is printed and the pointer is still set). Without it, the open ticket in `.work/INDEX.md` is used when its `.work/tickets/<id>/` directory exists. |
| `scope_guard.py` (PreToolUse `Write\|Edit\|MultiEdit\|NotebookEdit\|Bash\|PowerShell`) | Refuses an edit when the active ticket has no current approval from your prompt, or when the target is outside Touch. Refuses a shell command that runs `crew_ticket.py approve`, names the approval hook, or writes under `<git-common-dir>/crew/`. |
| `completion_audit.py` (Stop) | Diffs the whole tree against the ticket's scope base (`scope_base.py`: the commit the ticket started from, else the merge-base with the base branch — `tickets.baseBranch` in `.crew/config.json`, default `origin/HEAD`'s target; a configured branch that names no commit is "could not tell" and fails the audit, never a fall back to `origin/HEAD`) — committed, staged, unstaged and untracked, both ends of a rename — so shell-made writes are caught too. A refresh artifact is admitted without Touch only when the ticket's change reaches it and the edit is a re-anchor or a regeneration (`crew_refresh_check.artifact_verdicts`, crew 1.0.81; the audit applies it once L-0540 lands, and until then admits the whole artifact dirs under approval, as since 1.0.36). A path byte-identical to the merged integration commit is not counted (T-0100, the rule the review bundle shares, `merged_main.py`); a merged-in path taken out of the index (`git rm --cached`) is identical only when its bytes and the mode `git add` would record match, and that mode carries the execute bit only when `core.fileMode` is not false, as the bundle's `add -A` does; the verdict says `merged main <sha> (<ref>): <n> path(s) identical to it not counted`, or `merged main: could not tell` and counts every path — on a pass as well as a failure. `--check --ticket <id>` is the form `/crew:done` calls. |
| `crew_gitignore.py check\|apply\|summary --root . [--json]` | T-0039. `check` (read-only): detected languages, and per vendored pattern `missing`, `covered`, `tracked` (files it cannot untrack), `conflict` (would defeat a human `!` line), `overridden`, `needs-owner` (a tracked secret-shaped file). `apply` writes only the `# crew:gitignore:managed` block at the top of the root `.gitignore`, atomically, keeping CRLF and a BOM, and prints the diff. `summary` is `/crew:status`'s line. Exit 0 current, 1 pending, 3 owner decision, 4 unknown (git failed or timed out, undecodable `.gitignore`, malformed block), 5 refused (`# crew:gitignore:off`, a non-regular `.gitignore`, or an active ticket whose Touch lacks `.gitignore`). |
| `crew_refresh_check.py --root . --ticket <id> [--json]` | Read-only (since 1.0.36). Per code map, diagram and code graph that the ticket's changed paths reach: `fresh`, `stale` (with the refresh command — `/crew:onboard --refresh <subsystem>`, `/crew:diagram refresh`, and for the graph `graphify update .` where the repo tracks `GRAPH_REPORT.md` beside `graph.json`, else `graphify . --no-viz --code-only`) or `unknown`; `not applicable` when the repo has no graph file; and `fresh-uncommitted` (crew 1.0.349) when everything is current but a refresh-artifact path is uncommitted. `--json` adds `base_source` (`record`, or the fallback used), `stop` (why no refresh can settle the answer, or null) and `uncommitted` (those paths). Since 1.0.350 it also prints a `diagram-embeds` line per README whose generated diagram section has drifted from its sources (whatever the ticket reached): `stale` with `refresh with python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_diagrams.py embed --root .`, or, for malformed markers, `stale` with `stop - needs judgement`; an unreadable source is `unknown`. Exit 0 only when everything is `fresh` — current and committed. |
| `crew_graph_ignore.py --root . --check \| --write [--json]` | Would a graph build read a secrets-denylisted file? The denylist is the union of built-in patterns (`.env`, `.env.*` but not `.env.example`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `id_rsa*`, `id_ed25519*`), the optional tracked `.claude/secrets-denylist` (gitignore syntax) and every in-repo `Read(...)` deny rule in `.claude/settings.json` and `.claude/settings.local.json`. `--check` lists every file on disk it matches that the root `.graphifyignore` does not exclude (`.gitignore` does not count: graphify reads a tracked file whatever `.gitignore` says), judged by git's own matcher in a scratch repository. Exit 0 covered, 1 uncovered (paths only, never content), 2 unknown (git missing, a settings file that will not parse, a nested `.graphifyignore`, an unexcluded nested repository, a symlink leaving the repo, a deny-all `Read` rule). The denylist match ignores case and coverage does not; a symlink is judged by its target too. `--write` appends the missing patterns, plus each path they still miss as a literal (`/.ENV`), under one marked block, atomically, keeping the file's mode and line endings. It writes a literal only for a path that is one line of plain text (no control character or line separator), and never overrides a `!` line of yours: it names that line and the path it re-includes, writes the rest, and exits 1. Read-only without `--write`. Called by `crew_refresh_check.py`, `/crew:status`'s `graph-ignore` line and crew-graph's **Build**. |

**Artifacts stay current (since 1.0.36).** The order is implement, then refresh artifacts, then review, then done. `/crew:implement` step 6 runs `crew_refresh_check.py` after `/crew:docs`, runs the command each `stale` line names, commits, and re-runs until `fresh` — before `/crew:review`, so the reviewer reads the refreshed artifacts and the receipt covers them. `/crew:done`'s check 4 runs the same check and refuses on anything but `fresh`; it never runs a refresh itself, because a write after review stales check 1's receipt. Since crew 1.0.349 (T-0063) there are five values, and `fresh` means current **and committed**: an artifact whose own file — the map, the diagram source or a same-stem render, anything under the graph dir — is modified, staged, or untracked and not ignored reads `fresh-uncommitted`, and so does the whole answer when any path under the refresh-artifact dirs is (an out-of-scope map, a `.claude/rules/` file), listed on an `uncommitted:` line. It refuses like `stale`, the fix is a commit, and that commit leaves a review receipt current, because the review bundle is the working state. Precedence: `unknown`, then `stale`, then `fresh-uncommitted`, then `fresh`; a listing git cannot give is `unknown`. The graph is also `fresh` when it is behind by sha but graphify's own `<graph.out>/manifest.json` records the current MD5 of every committed code path that moved since its `built_at_commit` — graphify leaves `graph.json` untouched when the topology did not change, which used to read `stale` for ever; a missing or unparseable manifest leaves the sha answer, and uncommitted code is never confirmed. Staleness is scoped to the paths the ticket changed (scope base against the working tree plus untracked files) and the paths each artifact cites, so an anchor lag from commits outside those paths does not refuse, and an uncommitted edit in a cited path reads `stale` ("commit, then refresh"). Release bookkeeping — `CHANGELOG.md`, `TODO.md` (where check 3 files every ticket's findings), `plugin/PLUGINS.md`, `.claude-plugin/marketplace.json`, any `.claude-plugin/plugin.json`, `plugin/*/BUDGETS.md` — never stales an artifact on its own: every release moves it without invalidating a word. A code map's citations are backticked paths with an optional `:line` or `:start-end`, dot-directories included; a cited directory, or one named on a diagram's `%% Anchors:` line, reaches every path under it. An anchor that names no commit, a code map citing no path, a diff git could not run, a graph with no `built_at_commit`, graphify missing on this machine, a code-map or diagrams dir that cannot be listed, a map or diagram that cannot be read, a `.crew/crew.json` or `.crew/config.json` that exists and does not parse (never read as the defaults), and a scope base that hides the change (none at all, or a fallback equal to HEAD — on the default branch the merge-base is HEAD and hides every commit) are each `unknown`, which refuses like `stale`. Any other fallback base (the merge-base with the default branch, a `record-fallback` entry) is used only when HEAD is on a branch that is not the default one and no commit behind the base names the ticket in its subject — otherwise the ticket's commits may already sit behind it (work pushed to the default branch, or a branch fast-forwarded into it and given one more commit), and the answer is `unknown`, `fallback base <sha> may hide <ticket>'s commits`. A recorded base gets the same subject check: `scope_base.py --record` in a successor checkout whose earlier commits already reached the default branch records HEAD, and the answer is `unknown`, `recorded base <sha> may hide <ticket>'s commits`. Whenever the base hides or may hide the change, every artifact measured against it reads `unknown` too, its reason the top line's stop, in the text and in `--json`'s `artifacts[]` — a `fresh` measured against the wrong diff is never printed. When a fallback base is used, every artifact line says `[fallback base]`. A ticket whose commits reached the default branch under subjects that do not name it is not caught. Some `unknown`s a refresh settles: an anchor that names no commit (usually a squash-merged branch), a map citing no path, or a graph with no `built_at_commit` print `refresh with <command>` like a `stale` line, and `/crew:implement` runs it. The rest print `stop`, and are reported rather than refreshed around; a scope base or config that cannot be trusted puts the `stop` on the top line, and when nothing was measured the output says `not measured - <why>` rather than claiming no artifact is reached. Documents are reported `not measured` — whether a change should touch one is `/crew:docs`'s judgement — and never `fresh`. The refreshes write paths no Touch names, so an approved ticket may write them — and the audit admits them only in the shape a refresh leaves (see "What the guard judges").

**What the guard judges.** The real path, following symlinks and junctions the way the OS will, *and* the path as named, when that is inside the worktree — so a link cannot carry a write out of Touch or launder one into it. `..` is resolved where the OS resolves it. The ticket's own `.work/tickets/<id>/` files are always writable, so you can amend the spec and plan. Since 1.0.36 a ticket with a current approval from your prompt (a `cli` receipt only under `scope.allowCliApproval`) may also write the refresh-artifact paths — `.crew/codemap/`, the configured diagrams dir (`docs.diagramsDir`), the graph dir (`graph.out`) and `.claude/rules/` — because `/crew:implement` step 6 refreshes them for every ticket whose changes reach them, and no Touch names them. The guard admits the whole dir, because a write-time check sees one Edit of a multi-Edit refresh (claims first, `anchor:` last) and would refuse the legitimate intermediate state. The completion audit is narrower (`crew_refresh_check.artifact_verdicts`, crew 1.0.81, applied by the audit once L-0540 lands): under the same approval it admits a changed artifact without Touch only when a path the ticket changed since its scope base reaches it — merged-in main paths included; of the release bookkeeping only a `.claude-plugin/plugin.json`, so a version bump reaches the map citing it, while `CHANGELOG.md`, `marketplace.json` and the rest, which every release moves and most maps cite, reach nothing — and the edit is a re-anchor or a regeneration. A code map (not `INDEX.md`, `UPGRADE.md` or `MIGRATION.md`) must exist in the base and on disk, its BASE copy must cite a changed path (an edit cannot cite its way in), and its `anchor:` must have moved forward to a commit that is HEAD or behind it — never backwards from a base anchor on HEAD's history, and an anchor whose text did not change never moved; its claims, line numbers and prose may change with it. `INDEX.md` passes when every line that differs from the base, deleted lines included, is the row of such a map. A diagram source is reached through its base copy's `%% Anchors:` line (none: any code path) and its provenance sha must move the same way; a rendered diagram passes beside its admitted same-stem source, whatever the case of the source's extension. A `.claude/rules/` file passes when its bytes equal what `crew_instructions.py rules` writes, or when it was a generated rule no map expects any more and was removed. The graph dir passes when the ticket changed a code path. Every kind must also be a regular file on disk: a deleted rendered diagram or graph file, a symlink at the path or along its directories, a file whose git mode differs from its base copy's, one git stages as a link (120000) or gitlink (160000), or one the base holds and the index no longer does (`git rm --cached` with the file left on disk, since the commit deletes it) never passes, and when two configured artifact dirs hold a path the most specific one decides its kind (two equally specific ones are could-not-tell). Anything else there is judged against Touch, and the audit's listing names why in brackets: `[anchor did not move]`, `[no changed path reaches it]`, `[anchor <sha> is not reachable from HEAD]`, `[anchor moved from <sha> to <sha>, not forward]`, `[new file, not a re-anchor]`, `[INDEX.md line <n> is not the row of a re-anchored map]` (`base line <n>` for a deleted one), `[bytes differ from expected_rules ...]`, `[graph changed with no code change since the base]`, `[deleted, not a regeneration]`, `[a symlink, which no refresh writes]`, `[mode changed from <a> to <b>, ...]`, `[removed from the index, so the commit deletes it; ...]`. When git, a base copy, the config or the rule renderer cannot answer, a rule file cannot be read, a short base or new anchor is ambiguous (two commits share it), the base's tree cannot be read, the artifact dirs themselves cannot be resolved, or a directory the hook cannot search hides whether the config, a rule or a map exists (only a path proven missing is absent), the verdict is `[could not tell: ...]`, which never admits. An unapproved ticket's artifacts are not judged at all. So an edit to a map's version sentence without moving its `anchor:` (what `93da92af` did) now needs Touch or a re-anchor. The audit judges shape and reach, not truth: a re-anchored map's claims stay the reviewer's. The match is on whole path segments after `..` is collapsed (`.crew/codemapX` is not the code map), both the real and the named path must be artifacts, and a configured dir that resolves to the repository root opens nothing. Nothing else is exempt: not the rest of `.crew/`, not `TODO.md`, not the rest of `.claude/`, not crew's own policy files — put them in Touch if the ticket changes them. Anything under `<git-common-dir>/crew/` (approval receipts, the review ledger, the merge train's state, the active-ticket pointer, the ramp count) and `.crew/.scope-base` are refused to Write/Edit in every mode but `off`, ticket or no ticket. A path outside the worktree (a scratch directory) is not a repository path and is allowed, except the git directory.

**Approving several tickets at once (since 1.0.48).** One prompt may name several tickets: `/crew:approve T-4 T-5` (spaces, or commas between two ids — `T-1,` and `,T-1` are refused), a range `/crew:approve T-0010..T-0012` (one prefix, start ≤ end, padded like the start), or the one plain-text form — the whole prompt, on one line — `approve T-1 and T-2`, `please approve T-1, T-2, and T-3`, `approve T-0010 through T-0012` (`thru`/`to` too). An id in the plain-text form is prefix-dash-number, so "approve it", "lgtm" and "does the reviewer approve T-1?" are not approvals. At most 20 tickets per request. A range token that is also a ticket folder is refused as ambiguous. Only the prompt's own command counts: in the expanded `<command-name>`/`<command-args>` form the tags must be the prompt's outermost structure with nothing outside them (for a single id too, since 1.0.45), and a command tag nested inside another (an example, a quoted `<command-message>`) or left unclosed is refused; a command quoted in a code fence or mid-sentence is not an approval.

- **Nothing is recorded on the first prompt.** Any request for more than one ticket, and *any* plain-text request (even for one), is checked ticket by ticket and then blocked with a PENDING list — one line per ticket with its plan and spec sha256 prefixes. Nothing is written but the list itself (`<git-common-dir>/crew/approval-pending/`, one per worktree). A single `/crew:approve <id>` still records at once.
- **You confirm with `/crew:approve --confirm`**, on one line with nothing else on it (whitespace after it — spaces, blank lines — is ignored; any other text after a line break refuses it), in the same session (a `/clear` starts a new one and voids the list) and within 10 minutes. Then every ticket is checked again, and every spec.md and plan.md must still hash to what the list showed you. "yes" is not a confirm: it is the commonest reply to any question, and would confirm a list you were not looking at. The confirm is yours only: autopilot's self-approval (`autopilot.approval`) approves one ticket at a time and is refused if it carries a group's hashes.
- **Refuse all, never the rest.** If any ticket fails — no folder, a contract that does not validate, a row closed in `.work/INDEX.md` (`done`, `merged`, `closed`, `shipped`, `complete(d)`, `cancelled`, `superseded`; the row's id cell is its first id-shaped cell — an index column is skipped — matched whole and in any case; a row naming it as a whole cell elsewhere, or with no status cell, cannot be told and is refused), an unreadable receipt, or a hash that changed before the confirm — nothing is recorded, nothing stays pending, and every failing id is named with its reason. A subset is a decision you did not make.
- **Receipts stay per ticket.** Each confirmed ticket gets its own `approval.json`, `approved_via: "user-prompt"`, bound to its own hashes and the confirm prompt's session and prompt ids — written through the same `crew_ticket.approve` as a single approval, with the confirmed hashes passed in, so a file edited between the check and the write is refused. A NEEDS_REPLAN ticket goes through the same successor-plan rule. There is no cross-file transaction: a write that fails part-way blocks the prompt and names which tickets were recorded and which were not — judged by this confirm's own entry (its session, prompt and hashes) in each receipt's history, never by history growth another session could cause, and "could not tell" when a receipt cannot be read.
- **Any approval-shaped prompt replaces or clears the list**, and a confirm consumes it whatever the outcome. The wrappers now hand python any prompt containing the word "approve"; with no usable python only a prompt containing `crew:approve` is blocked, so a plain-text approval then passes through unrecorded rather than blocking every prompt that uses the word.

**Amending scope** is editing `spec.md` `## Touch` (and `plan.md`), then `/crew:approve <id>` again. The edit makes the approval stale, so edits outside the ticket directory are refused until you approve.

**The status edit keeps the approval.** The receipt binds each file's approval digest (`digest: "crew-approval/2"`, fields `spec_digest` and `plan_digest`), which normalises exactly one thing: the value of the header's `status:` token, so `/crew:plan`, `/crew:implement` and `/crew:done` can move a ticket through `spec` -> `planned` -> `review` -> `done` without a fresh approval. It applies only when line 1 (ending at the first line break the spec parser splits on - `\n`, `\r\n`, a bare `\r`, or any other `str.splitlines` break) starts with `# `, holds exactly one `status:` (counted case-insensitively), and that token's value is one of `spec`, `planned`, `approved`, `in-progress`, `review`, `done`, `merged`. Everything else still stales it: `risk:`, the title, whitespace, line endings, any body line, a second `status:` anywhere, a value outside that list, and a `status:` added where there was none. `plan_sha256`/`spec_sha256` stay the raw full-file sha256, which the review ledger's successor-plan rule still reads. A receipt written before T-0026 has no `digest` field and is compared on the raw sha256, so it verifies on unchanged files and goes stale once on its first status edit; approving again writes a `/2` receipt. A `digest` naming any other scheme reads `stale`, never a raw fallback.

**Modes** — `scope.mode` in `.crew/config.json`:

| Value | Behaviour |
|---|---|
| `off` (default) | Both hooks do nothing. A repo that never set the key is here. `/crew:init` writes `auto` instead for a repo it creates `.crew/config.json` in (crew 0.20.25); an existing config is left alone. |
| `report` | Everything is allowed; each would-be refusal is logged to `.crew/guard.log` and shown as a system message. Approval/ledger state is still refused. |
| `block` | Refusals block (the edit guard exits 2; the audit blocks the Stop once, in at most six lines, and never re-blocks a `stop_hook_active` continuation). |
| `auto` | `report` for the first ten tickets approved in this repository, then `block`. The count lives in `<git-common-dir>/crew/scope-tickets.json`. |

A `.crew/config.json` that exists but does not parse, or a value outside those four, is treated as `block` and says so. A hook payload that does not parse is refused whenever the effective mode is `block` (`auto` past its ramp included). An active-ticket pointer naming a ticket that does not exist is refused under `block`, never read as "no ticket". If python cannot run at all, the wrappers fail closed unless `.crew/config.json` is absent or *provably* sets `scope.mode` to `off`. bash has no JSON parser, so from bash a config that exists is never provable: with no usable python, a present config blocks writes and the Stop until python is available. PowerShell proves it with a strict `System.Text.Json` parse (not `ConvertFrom-Json`, which accepts trailing commas), and fails closed where that type cannot load; the Stop audit then blocks at most once in a row per session, so a broken python cannot loop the Stop.

**Focus (T-0020): `/crew:autopilot focus <id>`.** Focus is explicit (owner decision, 2026-10-05): it is on only once you type `focus <id>`, which writes this worktree's entry in `<git-common-dir>/crew/autopilot-focus.json`, the focus marker. The active-ticket pointer alone is never a focus — not one `crew_ticket.py activate` set for the scope guard, not the `.work/INDEX.md` fallback — so with no marker entry the router answers exactly as it does without T-0020: plain text aimed at `assign`, `goal`, `wave` or `split` gets the answer it gets without focus (`wave` routes since 1.1.6; the others are not available yet, so it asks or produces no line), never a focus refusal. No new hook. `focus <id>` is refused, with nothing written, when `.work/tickets/<id>/` does not exist, when the pointer is broken, when the marker cannot be read, or when focus is already on another ticket; when the pointer names another ticket or none it is re-pointed through `crew_ticket.activate`, which records the ticket's start in `.crew/.scope-base` (T-0061), and `focus` prints that, the scope-base line included (a could-not-tell or fallback too); the same ticket again is a no-op. `focus off` drops only this worktree's marker entry (the file goes when no entry is left) and leaves the active ticket as it was; both writes hold `<marker>.lock` (an exclusive create, waiting at most 5 seconds), so two worktrees focusing at once cannot drop each other's entry, and a lock that cannot be taken refuses with nothing written; `focus` shows `focus=<id>`, `focus=none` or `focus=unknown <why>` with `scope.mode`. While focused, autopilot's router refuses `run` of any other ticket (named, or taken from the handoff), `assign`, `goal` and any other subcommand, each refusal naming the focused ticket and `/crew:autopilot focus off`; if the pointer stops naming the focused ticket, everything but `focus <id>` (which re-points it) is refused. `status`, `focus off`, `sleep` and `wake` always run: they neither start nor switch work. A marker that is not a file, does not parse, cannot be read, or holds an entry that is not a ticket (an INDEX-shaped id, or one with a `.work/tickets/` folder) is *could-not-tell*, never "no focus": `focus` shows `focus=unknown`, the router refuses everything but `status`, `sleep` and `wake`, `next` stops as `drift`, and `focus off` refuses too rather than delete a file it cannot read. Every such message ends with the removal command for the exact path — `rm -- '<path>'` (POSIX shell) or `Remove-Item -LiteralPath '<path>'` (PowerShell), printed only when the path survives pasting unchanged (no control character, run of spaces or curly quote), else the path as JSON and "remove this file by hand" — and says that removing it drops every worktree's focus, since the marker is one file for all of them. Once the focused ticket's plan is approved, every `next` runs the completion audit's own `audit(root, ticket)` read-only, and a changed path outside Touch — or an audit that could not run — stops as `drift`, listing the paths. An out-of-scope finding is filed, never fixed in the diff: `crew_autopilot.py focus --findings --ticket <id>` names `TODO.md` when the approved Touch covers it, else `.work/tickets/<id>/out-of-scope.md`, because the scope guard exempts nothing outside Touch. Autopilot never releases focus itself: `focus off` runs only when your own arguments are `focus off`. Under `scope.mode: off` nothing refuses a write as it happens, so focus is held by the router and the drift stop only, and `focus` says so. Every `focus` output ends with a reminder that Claude Code's built-in `/focus` only toggles the display (just your prompt, summary, and response) and only you can type it: it scopes nothing. Not a security boundary: a session can edit or remove the marker itself (the threat model below).

**Threat model.** These guards stop *drift and accidental bypass*: a session editing outside the plan, approving its own plan through the CLI, or writing the approval state through Write/Edit or an obvious shell command. They do not stop a session that sets out to forge local state. It has a shell, and the receipt, the active-ticket pointer and the ramp count are files on your machine: a command that hides the path in a variable or an encoded string, or a script that writes JSON, passes the textual shell check. The Stop audit and review are the backstop — the audit diffs the whole tree after the fact, and a reviewer sees the change and the receipt's `approved_via`. Treat an approval as "the user asked, and nothing obviously went around it", not as a signature. The merge train's state (`<git-common-dir>/crew/train/`) is the same kind of local file: a session set on it could forge a hold or a release, so the train prevents lanes colliding by accident, and `check-land`'s `merge-tree`, receipt and gate checks — and your review of the merge — are the backstop.

**What this does not do.** The edit guard judges only the four editing tools against Touch; the Stop audit is what catches `sed -i`, redirects and formatters, after the fact. The audit sees what git sees: gitignored files (`.crew/*` among them) and `.work/` are outside it.

### Autopilot: one ticket, driven until a person is needed

`/crew:autopilot [<id>]` (since 1.0.41, **off by default**) drives one ticket through spec, plan, approval, implement, docs, refresh artifacts, review, done and (since 1.0.349) ship, following each phase command's own procedure in the same session. It does not decide the order itself: every turn it runs `hooks/scripts/crew_autopilot.py next --root . --ticket <id>`, which names the next phase from files on disk only, so a skipped phase is visible and a phase that cannot be told stops.

**Five writers, by design (T-0010, T-0074, L-0652, T-0020).** `crew_autopilot.py` is read-only — `next`, `resume`, `settings`, `stops`, `route`, `status`, `questions-check`, T-0072's `deploy-allowed` and T-0011's `ship` (but for a sliced plan's `slices.json`, below) write no file — except `approve`, and only when `autopilot.approval` allows it under the configured policy (below; it always needs `scope.allowCliApproval: true`, which defaults to `false`, so out of the box nothing self-approves), T-0074's `auto-reject` (below), and L-0652's `sleep` and `wake`, which write or remove only `<git-common-dir>/crew/autopilot-sleep.json` (the manual sleep state, below; `sleep` also needs `scope.allowCliApproval: true`). `approve` writes exactly what `crew_ticket.approve` writes for every approval route, `/crew:approve` included, all under `<git-common-dir>/crew/`: `approval.json`; the scope ramp's `scope-tickets.json` on a ticket's first approval; and, when the review ledger is NEEDS_REPLAN and the plan is a distinct successor, the ledger itself, moved NEEDS_REPLAN -> IN_REVIEW (the successor continuation, which opens a fresh review budget). `route` and `status` read no policy of their own: `route` answers the same, and `status`'s lines — the approve and open-questions reasons included — read the same under every setting (`next` is what names the policy's route); the one policy effect `status` shows is `crew_ticket.accepted`'s, which honours an `autopilot` receipt only while the policy still allows it; `approve`, `auto-reject` and `questions-check` are script subcommands, not `/crew:autopilot` subcommands. `auto-reject` (T-0074) writes only the review ledger, through `review_ledger.reject`: REVIEWED -> NEEDS_REPLAN, with `rejected.by` the fixed name `autopilot (policy: autopilot.maxAutoReplans)`, and only when `auto_replan_policy` allows (below). Nothing in autopilot accepts a review, and a BLOCK is never accepted at any setting. `crew_ticket.py assign` and `crew_ticket.py mint` (T-0019) write a new ticket, not `crew_autopilot.py`, so the writers there stay `approve`, `auto-reject`, `sleep`, `wake` and `focus`. `ship` writes no file either; it is the one action outside the checkout — a push, a PR and, under `autopilot.ship: merge`, one merge commit (below). T-0020's `focus` approves nothing: `focus --ticket <id>` writes this worktree's entry in `<git-common-dir>/crew/autopilot-focus.json` (the explicit focus marker) and, only when the active-ticket pointer names another ticket or none, re-points it through `crew_ticket.activate` (which records `.crew/.scope-base`); `focus --off` drops only the marker entry, removing the file when no entry is left, and leaves the active ticket as it was. T-0058's `crew_autopilot.py split --check` writes `crew_split.check`'s record, and `split --apply` writes what `crew_split.apply` writes (the children, `spec.pre-split.md`, the parent's status) only while `crew_split.ticket_split_policy` allows it; bare `split` writes nothing. T-0059's `ship` on a sliced plan, `slice-done` and `next-slice` write `<git-common-dir>/crew/tickets/<id>/slices.json`, and `next-slice` creates the next slice's branch (PR slices, below). T-0012's `goal-propose` and `goal-approve` write one working file, `.work/autopilot/<slug>.json`, and never a receipt — below.

**Subcommands** (since 1.0.47, T-0018). The command hands its whole argument string to `crew_autopilot.py route --root . --args '$ARGUMENTS'`, which decides the subcommand and the ticket in code, so a typo is refused rather than driven as a ticket id. It is single-quoted, and arguments holding a quote, `$`, a backtick or a backslash stop before anything runs, so the shell never expands them; `route --first <token>` routes one token alone. The whole string, not `$1`/`$2`: Claude Code numbers positional arguments from `$0` and leaves an out-of-range `$N` literal (measured on 2.1.283), so `$2` never reaches a command.

| `/crew:autopilot ...` | Does |
|---|---|
| `status [<id>]` | Read-only report in at most 12 lines — below. Works whether or not autopilot is armed. |
| `run [<id>]`, `<id>`, or nothing | Drives the ticket, as this section describes. `<id>` is an INDEX-shaped id (`T-0018`) or a folder under `.work/tickets/`. |
| `run <id>` for an id named like a subcommand | A ticket whose id is `status`, `run`, `assign`, `goal` or `focus` is driven as `/crew:autopilot run <id>`, and `status` suggests it that way; the bare name routes to the subcommand. |
| `assign` | Not yet from the command: stops with "arrives with T-0019". The route lands with L-0611; until then `crew_ticket.py assign` (since 1.0.302, T-0019) mints the ticket from the command line — below. |
| `goal "<goal>"` | T-0012 (below): researches the goal once, writes the goal file and proposal, prints the `/goal` line for you to paste, and asks for the split approval. It mints nothing yet. |
| `--goal <slug>`, `run --goal <slug>` | Not yet: resuming a goal stops with "arrives with L-0541". |
| `focus <id>`, `focus off`, `focus` | T-0020's scope lock on one ticket: sets, releases or shows this worktree's explicit focus marker (a plain active-ticket pointer is not focus) — "Focus" under "Scope and approval". `focus off` must be exactly those two words. |
| `wave`, `wave --set <slug>`, `wave <id> <id>...` | Runs an owner-designed, approved set of tickets as parallel isolated lanes (T-0029) — "`wave`" below. |

Any other word (`stauts`, `Status`, `rm`) stops with "unknown subcommand; one of status\|run\|assign\|goal\|focus\|sleep\|wake\|wave, or a ticket id". A second word that is not a ticket id (`status stauts`), or a third word, stops too: route never reads it as a ticket.

**`/crew:autopilot goal "<goal>"`** (T-0012). The goal's text never goes on a shell line: the command routes it with `route --root . --first goal`, researches the goal once (crew:explorer, crew:researcher) and stages a proposal at `.work/autopilot/<name>.proposal.json` — `goal`, a one-line `done_condition`, `findings`, and `tickets`, each with a `title`, a `risk` and `depends_on` (indexes of earlier tickets; the recommendation first, in dependency order). `crew_autopilot.py goal-propose --root . --proposal-file <f>` refuses, writing nothing, a file outside `.work/autopilot/` (symlinks resolved) or not regular, no goal text, an empty `done_condition`, a dependency that is unknown, a cycle or out of order, or a title `mint` would refuse; otherwise it writes the goal file `.work/autopilot/<slug>.json` (schema 1; the slug is T-0006's `--goal` grammar, `-2`, `-3` on a collision) and prints `slug=<slug> goal_status=printed ...`, one line per ticket, and `goal_line: /goal <condition> - or /crew:autopilot has stopped naming a command only the owner types` (one line, at most 300 characters; the condition is cut, never the clause, so Claude Code's evaluator treats an owner stop as met). **Autopilot prints that line for you to paste; it never runs, types or reports `/goal` as set**, because Claude Code's `/goal` is only the user's to type and its state cannot be observed (`goal_status` is always `printed`). T-0013's typer is offered only when `resume.auto` is armed, `crew_autocycle.resolve_method` names a sender, and T-0013 exposes a `/goal` typing entry point — today it does not, so a `typer: not offered` line names what is missing.

The split is approved under `autopilot.approval` (`crew_autopilot.py goal-approve --root . --goal <slug>`): `self` approves it, `risk` only when every proposed ticket is a known `risk: low` (the goal's risk is its highest ticket risk; an unknown one reads `high`), `human` stops — and every setting needs `scope.allowCliApproval: true` and autopilot armed. The policy is re-asked on every call; the `approval: {via: "autopilot:<policy>", proposal_sha256}` note it leaves in the goal file grants nothing. The owner's own approval is `/crew:approve goal:<slug>`, a receipt at `<git-common-dir>/crew/goals/<slug>/approval.json` bound to the sha256 of the goal, proposal and tickets (a minted id is not part of it), valid at any setting until the proposal is edited. `goal-approve` reads that receipt; recording it is `approval_hook.py`'s, a review-harness change that lands separately — until then the hook refuses `/crew:approve goal:<slug>`. Minting comes after the split approval and is T-0019's `crew_ticket.mint`, one call per ticket; that, the minted tickets' approval one at a time under `autopilot.approval` (never a group confirm), `mode: backlog`, the per-run caps and `--goal` resume are L-0541's. Until it lands, `goal-approve` names `crew_ticket.py mint` for you to run in list order.

**`crew_ticket.py assign`** (T-0019; `/crew:autopilot assign <work>`, which researches the work into the staging file and runs this for you, lands with L-0611 — until then run it yourself, then `/crew:autopilot run <id>`). The staging file is `.work/autopilot/assign-<n>.md`: a `title:` and a `risk: low|med|high` line, then `## Ask` (the work verbatim), `## Options`, `## Recommendation` and `## Open questions` (or `none`) in `/crew:brainstorm`'s format. `crew_ticket.py assign --root . --direction-file <that file>` (a relative path is read against `--root`, and a leading BOM is dropped) refuses, minting nothing, when the file is not under `.work/autopilot/` (symlinks resolved), autopilot is not armed, the `title:` line or a section is missing, or a section is empty, the file is not a regular file (a FIFO is refused at once, never waited on), or the call carries `--title` or `--status` (refused, never ignored); a risk that is not `low|med|high` is written `high`, with a warning. Otherwise it mints exactly one ticket, `ready`, whose direction.md carries an `origin: /crew:autopilot assign` line, the title and risk, and the sections, and prints `ticket=<id> risk=<r>`. Title and risk are read from the file, never from an argument: the scope guard refuses a shell command naming `crew_ticket` with the word "approve", so a title like "approve flow" would fail there.

An assigned ticket is approved under `autopilot.approval` like any other ticket (the owner's 2026-09-26 decision): `self` approves it, `risk` only a `risk: low` spec, `human` stops, and T-0010's rules — `scope.allowCliApproval: true`, autopilot armed, a readable review ledger, `crew_ticket.validate` passing, no open question left — all apply. The `origin:` line is provenance only; nothing that grants or refuses an approval reads it. So under `self`, an assigned ticket can run from its direction to implementation with no stop before review acceptance, which, like a production deploy, always stops for you. `assign` is not `goal` (T-0012): one ticket, no goal file, no split approval.

**`crew_ticket.py mint`** is the one way code creates a ticket (`mint --root . --title <t> [--status ready|direction] [--direction-file <f>]`, or `crew_ticket.mint` in process; any other `--status` prints `refused:` and exits 1). It takes one past the highest `T-` number over `.work/tickets/` folders and `.work/INDEX.md` rows, claims it with an exclusive `mkdir`, writes direction.md complete or not at all, and only then asks `crew_tracker.py create` for the INDEX row — and, under `obsidian`, the vault note and Kanban card — then `move` to `ready`. It never writes INDEX itself. A tracker `id taken` releases the folder and takes the next id; a direction write that fails, a lock that cannot be taken, or a `create` that keeps failing, releases the folder (and, under `obsidian`, the note that `create` wrote) and refuses. A `create` whose row lands but whose card does not refuses too, keeping the ticket at `direction` and saying so. Mints hold `.work/INDEX.md.lock` across both tracker calls, `create` and the `move` to `ready`, so two concurrent mints never lose each other's row, and the id scan reads INDEX under the same lock, so it never opens INDEX while another mint replaces it (a sharing violation on Windows, L-1510). `crew_tracker.py create` and `crew_tracker.py move` run on their own do not take that lock yet (follow-up L-1511); a `create` that raises before its row is in INDEX releases the folder too, and one that raises after keeps it and says so. It refuses before claiming anything under `jira`, `sdp`, no tracker, or a tracker that could not tell, and on a title that is empty, over 120 characters, holds a `|` or a line break. A `move` to `ready` that fails leaves the ticket at `direction` with a warning: a row the move did set to `ready` (its board half failing) is put back, and the reported status is always the INDEX row's. `/crew:brainstorm` and `/crew:fix` still pick their id in prose; moving them onto `mint` is a follow-up.

**`status`** (`crew_autopilot.py status --root . [--ticket <id>]`) prints: the mode; the ticket and where that choice came from (the argument, the handoff, the active ticket or `.work/INDEX.md`); the phase `next` names and its command, or why it stopped; who it waits on — `owner` with the command they type (or, when `next` stopped on the active-ticket pointer rather than on the phase, the `crew_ticket.py activate` that re-points it — or `autopilot` when no pointer is set, since `run` activates the ticket first), `autopilot`, `reviewer` for a round reserved with no result, `nobody` for a closed ticket, `owner` for `hold` and `needs-owner`, `the land step - see the phase reason` for `landing` and `another ticket - see the phase reason` for `blocked` (never `autopilot`); the review rounds left; and the handoff's `resume:` line with whether it is usable (`no .work/HANDOFF.md`, `unavailable (T-0006 not landed)`, `<line> (usable)` or `not usable: <reason>` — usable only where `resume` would take it, so a line naming no ticket or a ticket with no folder is not usable), then any `fell through:`, `disagreement:` and `warning:` lines; `--json` prints the same fields as one line of JSON. The `resume:` line is judged on the handoff status itself read, and a `.work/HANDOFF.md` that is there but cannot be read — denied, a directory, a dangling or looping symlink — prints `unknown`, never `no .work/HANDOFF.md`. What it cannot tell reads `unknown`, never a safe-looking value: an unreadable review ledger prints `review: unknown (ledger unreadable)`, not a rounds count, and a phase name it does not map prints `waiting on: unknown`. It writes nothing — no file, no git index refresh, no ledger reservation, no active-ticket change — and exits 0.

| On disk | Phase | |
|---|---|---|
| in a lane worktree, the ticket folder only in the main checkout | `folder-elsewhere` | stop — names the `cp -r` to make; a contract is never read from another checkout, because the scope guard reads Touch from this one |
| no ticket folder here, and `git worktree list` could not name the main checkout | `folder-elsewhere` | stop — says it could not tell whether the folder is in the main checkout, and why; never read as "no folder" |
| no `direction.md`, or INDEX status `direction` | `brainstorm` / `direction-approval` | stop — a human dialogue |
| INDEX rows for the ticket here and in the main checkout whose status cells differ | `direction-approval` | stop — `index-disagreement`, naming both files and both cells |
| no INDEX table row for the ticket here or, in a lane worktree, in the main checkout (or no INDEX), or a status cell that is not `ready`, `open`, `spec`, `planned`, `approved`, `in-progress`, `implement` or `review` | `direction-approval` | stop — cannot tell whether the direction was approved (Jira and ServiceDesk Plus modes write no row; a blank or unknown cell is not a yes) |
| INDEX status `cancelled`, `superseded`, `merged`, `closed`, `shipped`, `complete(d)`, or `done` without a `status: done` spec header | `closed` | stop — never re-driven; a `superseded` row names its successor (the line under the spec header, else `next.md`'s `superseded-by:`, else "successor not named") |
| INDEX status `hold`, `landing` or `needs-owner`; with none of them, the same word in the spec header as `crew_ticket_state.view` reads it (L-0550, `crew_autopilot_gates.py`) | `hold` / `landing` / `needs-owner` | stop, read-only — `hold` quotes `next.md`'s `reason:` and `revisit:` ("(passed)" once due; a date never lifts a hold, only the owner editing the status does); `landing` says the land step owns it, even with a current receipt; `needs-owner` quotes `next:` and the unanswered `## Open questions`, or says it cannot tell what is asked. A `next.md` it cannot read is said, never read as "nothing asked" |
| spec header `cancelled` or `superseded` under an INDEX cell that is not a closed word (`view`'s header read) | `closed` | stop — names the successor as above |
| `view` cannot tell the gate (two INDEX rows for the ticket disagree, or INDEX unreadable) | `direction-approval` | stop — cannot tell, quoting why |
| spec header `status: cancelled` or `superseded` | `closed` | stop — never re-driven; the reason quotes a `split-into:` / `superseded-by:` line |
| spec header `status: done` (INDEX `done` or not), autopilot unarmed | `closed` | stop — shipping is autopilot's; nothing is pushed |
| … armed: the branch's PR is merged and its merged head (`headRefOid`) is this checkout's HEAD (full SHAs), or open under `autopilot.ship: pr` | `closed` | stop — "PR #n open, merge by hand" |
| … armed: the branch's PR is merged but HEAD has moved past its merged head, or either head cannot be read | `ship` | stop — ship the later commits on a new branch and PR; autopilot never opens a second PR on a merged branch |
| … armed: detached HEAD, `gh pr view` failed or answered something that is not a PR state, the PR closed unmerged, a working tree that differs from HEAD, or the review receipt no longer stands | `ship` | stop |
| … armed: no PR yet, or one open under `autopilot.ship: merge` | `ship` | runs `crew_autopilot.py ship --ticket <id>` |
| an item under an `Open questions` heading (any level, sub-headings included) in direction.md, spec.md or plan.md | `open-questions` | stop — answered by writing `none - <answer>` or checking it `[x]`; `None of us has decided` is still open. Code fences (L-0642): main's reading is the floor; a fence at column 0, closed at column 0 by the same marker, hides nothing (its lines are neither headings nor items); any other fence shape, or a fence left open, in a file that names an Open-questions section is `could not tell` and stops, so put fences at column 0 and close each one |
| no `spec.md` / no `plan.md` | `spec` / `plan` | runs `/crew:spec` / `/crew:plan` |
| `crew_ticket.validate` refuses | `spec` / `plan` | stop, with the problems |
| the plan's `## PR slices` breaks a rule (T-0059) | `plan` | stop, `PR slices: <problems>` |
| a sliced plan's `slices.json` unreadable or out of shape, or a `status: done` header while an earlier slice is current | `slices` | stop |
| a non-final slice recorded done (`slice-done`) | the ship rows above, but a merged slice (or one open under `ship: pr`) is `next-slice` | runs `crew_autopilot.py next-slice --ticket <id>` |
| approval not accepted (none, stale, a `cli` receipt without `scope.allowCliApproval: true`, or an `autopilot` receipt the policy no longer allows) | `approve` | stop — **you** type `/crew:approve <id>`, unless `autopilot.approval` allows (`self`, or `risk` for a `risk: low` spec; both need `scope.allowCliApproval: true` and autopilot armed): then `/crew:autopilot` runs `crew_autopilot.py approve` and reports it. `status` names only `/crew:approve <id>` here, under every setting |
| approved, and a `depends-on:` ticket is not closed (`open`, `cancelled`, `superseded`, `unknown`), or the line cannot be read (L-0550) | `blocked` | stop — names each dependency with its state and why; a blocked ticket still gets its spec and plan, and one already in review stops too |
| review ledger `UNKNOWN` / `NEEDS_REPLAN` | `review` / `replan` | stop — except a NEEDS_REPLAN that autopilot's own `auto-reject` wrote for the latest round, while `autopilot.maxAutoReplans`, the cap and `autopilot.approval` still allow: then `replan` runs `/crew:plan` for a successor plan that quotes every BLOCK and FIX line |
| no review round under the current plan | `implement` | runs `/crew:implement` (its step 6 runs tests, docs, the refresh check, then review) |
| latest round reserved with no result | `review` | stop — another run would spend a round |
| latest round FINDINGS, no standing receipt, a round left, a BLOCK or FIX line, and `autopilot.reviewPolicy: fix-and-rereview` (T-0067, `crew_autopilot_fix.py`) | `fix` | runs `fix-findings <id> round <n>`: each BLOCK and FIX fixed test-first inside Touch, verify gate, commit, then each line quoted verbatim under `## Round <n>` in `.work/tickets/<id>/fixes.md` with a `fixed:` line; once fixes.md quotes every BLOCK and FIX line and the bundle changed, the refresh and `/crew:review` follow. A finding it cannot fix inside Touch, or disputes, is the `fix-refused` stop. Anything it cannot read (the policy, `rounds_left`, the row's findings, base or bundle hash, fixes.md, a bundle rebuild) is the `accept-review` stop below, naming the cause; `fix` named again right after it ran is `no-progress` |
| latest round FINDINGS, no standing owner- or auto-accepted receipt | `accept-review` | stop — names `--auto-accept` when its guard passes, else quotes its refusal; acceptance is then the owner's |
| that round has a BLOCK, no round is left, and `auto_replan_policy` allows (T-0074) | `auto-replan` | runs `crew_autopilot.py auto-reject` and reports every BLOCK and FIX line; at the cap it is the `auto-replan-cap` stop, which names `autopilot.maxAutoReplans` and every successor plan |
| no receipt stands and no review round is left | `review` | stop — `/crew:review` would reserve a third round and write NEEDS_REPLAN, which only a new approved plan leaves; revert the edit that staled the receipt, or replan |
| latest round INCOMPLETE, a refunded tool failure | `review` (`refresh` first when stale) | runs `/crew:review` |
| latest round INCOMPLETE (not refunded) | `accept-review` | stop — it cannot be accepted; a human reruns review or replans |
| artifacts `fresh-uncommitted`, receipt current or not | `commit-refresh` | runs `git add -- <the listed paths> && git commit -m "<id>: commit refreshed artifacts" -- <the same paths>` as printed, which commits only those paths (anything else already staged stays staged) — the commit changes no byte of the working state the review bundle is built from, so a receipt stays current; stop when the check names no path |
| receipt not current, the docs check `unknown` (no trusted scope base, an unreadable `docs.json`, git could not read a base blob, the check raised) | `docs-unknown` | stop at once — another `/crew:docs` run cannot settle it |
| receipt not current, a document `MISSING` | `docs` | runs `/crew:docs <id>`; stop once two recorded runs since the latest review round leave one `MISSING` |
| receipt not current, artifacts stale | `refresh` | runs the command T-0008's check names |
| receipt not current, an artifact unknown for a cause a refresh cannot settle | `refresh` | stop |
| receipt not current, artifacts fresh | `review` | runs `/crew:review` |
| receipt current, artifacts not fresh | `stale-after-review` | stop, nothing written — a refresh now would stale the receipt |
| receipt current, a document owed | `docs-after-review` | stop, nothing written — writing it now would stale the receipt |
| receipt current, artifacts fresh | `done` | runs `/crew:done` |

**Implement's status edit keeps the approval.** `/crew:implement` step 7 writes `status: review` into spec.md's header, which T-0026's approval digest normalises, so `next` moves on. An approval that edit still stales — a receipt written before T-0026, or a value outside `crew_ticket.STATUS_VALUES` — stops at `approve`; when changing only that `status:` word back makes spec.md hash to the approved bytes (and plan.md is unchanged), the reason says only the header changed, so it reads differently from a Touch widened mid-implement.

**A review phase ends at its verdict.** Whether reached as `/crew:review` or inside `/crew:implement` step 6, autopilot stops following `review.md` once the round is recorded and its BLOCK and FIX lines are reported: step 3.2's fix-and-rerun, `review_ledger.py --accept` and `gh pr review` are the human's. One extension, which neither fixes nor reruns (L-0510): after `review: auto-accept: eligible`, the phase also runs step 2d's control re-runs and, with no specialist or control BLOCK, step 3.3's `--auto-accept` and follow-up filing. The next `next` stops at FINDINGS or an unrefunded INCOMPLETE. A round `next` reaches itself gets a refresh first; the FINDINGS stop names the refresh the human runs after fixing (`crew_refresh_check.py --root . --ticket <id>`, rerun until it says fresh, committing what each `refresh with` writes and each `uncommitted:` path) and before `/crew:review` (T-0043). An accepted FINDINGS round whose receipt a later edit staled goes to refresh, then review, like a stale CLEAN receipt.

**The ticket is re-checked every turn.** `next` stops (`ticket-mismatch`) before any phase that would run while `crew_ticket.resolve_active` — what the scope guard and the completion audit read — names another ticket, none, or a broken pointer. Anything `next` or `resume` raises prints `stop=1` with the exception, and the command treats any answer but a `stop=0` line as a stop.

**In-flight markers: one runner drives a ticket at a time (T-0049).** Before its loop the command claims the ticket with `hooks/scripts/crew_inflight.py claim --root . --ticket <id> --runner autopilot` and releases it at every stop (`release`); a `refused:` claim is a stop. The marker is `<git-common-dir>/crew/inflight/<id>.json`, shared by every worktree of one clone (two clones share nothing; that case is out of scope): the runner (`autopilot`, `lane` or `session`), a token, the holder, the worktree and branch, `since` and `heartbeat_at`. The holder is `CLAUDE_CODE_SESSION_ID` plus the long-lived Claude Code process: `CLAUDE_PID` when it is an ancestor of the claiming command that started before it (a hint that cannot be checked, for example when no process chain can be read, is never trusted: any environment, a project's settings included, can set it), else the nearest ancestor named `claude`; a Claude Code session where neither can be found records no pid, and only when neither side has a pid does the session id decide alone; a lane's script records its own shell. Each pid comes with its start time, pid namespace, boot id and host. `claim`, `release` and `clear` write their event to `events.jsonl` first and do nothing if it cannot be written; the refusal names the file to fix or move aside before retrying. `claim` publishes the marker with `os.link`, so two claimers never both win, and starts one detached heartbeat that rewrites `heartbeat_at` every 600 s (`min(600, TTL/3)`) and exits when the marker is gone, names another token, or its holder is measured gone. `crew_inflight.holds(root, ticket)` answers `free`, `mine`, `live` (another holder in this worktree), `elsewhere` (a fresh holder in another worktree), `stale` (no heartbeat for 30 minutes, the TTL, or the holder's pid measured gone, a zombie or reused) or `unknown` (anything it cannot read, parse, probe or trust, including a reader whose own git cannot name its worktree — never `free`), and writes nothing. The pid is measured only when host, boot id and pid namespace all match the reader's: `/proc` on Linux, `kill -0` plus `ps` on macOS and other POSIX systems, the process's exit code and creation time on Windows. Where it cannot be measured (a sandbox, a session with no pid), the heartbeat stops by itself once its holder has gone 30 minutes unconfirmed, so a dead holder still goes stale within 70 minutes (2 × TTL plus one heartbeat, 4200 s): **the TTL decides whenever the pid cannot**. `next --runner autopilot` stops as `in-flight` on `live`, `stale` and `unknown`, naming the runner, ticket and since, and as `handover-elsewhere` on `elsewhere`; `free` and `mine` change nothing, and without `--runner` `next` is unchanged. **Nothing clears a marker by age, and autopilot never clears one** (`clear-inflight`): a stale or unknown stop prints the owner's command, `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_inflight.py" clear --root . --ticket <id> --by <you> --reason "<why>"`. It re-reads the state under the lock, accepts only `stale` or `unknown` (an unreadable marker is cleared by the owner, never by age), and logs who and why. `holds --root . --ticket <id> [--json]` prints the answer on one line. A workflow lane adopts the same CLI with `--runner lane`.

**Refresh sits between implement and review, every round.** A review bundle excludes only `.work/`, generated `graphify-out/` and paths byte-identical to merged main, so a codemap, diagram or `.claude/rules/` refresh written after an accepted review stales its receipt and `/crew:done` refuses (a graph rebuild alone no longer does, since 1.0.54); autopilot therefore never refreshes after review. A merge of main that touches no reviewed path does not stale a receipt (T-0100): the rebuilt bundle leaves out paths identical to the merged commit and `--check-receipt` says how many (and `fork: could not tell` when the merge-base of the start and the merged commit had no answer); a merge that changes a reviewed path still does, conflict or not, because that file's diff now starts from main's version. The freshness judgement is T-0008's `crew_refresh_check.ticket_freshness`. A `stale` artifact is refreshed with the command it names. An `unknown` one is refreshed only in T-0008's orphaned-anchor case — the anchor names no commit (a squash merge dropped it), T-0008 marks it refreshable and names the command; every other `unknown` (graphify missing, no or a fallback scope base, a check that raised) stops, as `/crew:implement` step 6 does. When the module cannot be imported the phase stops as "refresh-artifacts unavailable (T-0008 not landed)" rather than being skipped. A `fresh-uncommitted` answer (crew 1.0.349) is the `commit-refresh` phase, before review and after an accepted one alike: committing exactly the paths the check lists leaves the review bundle — the working state — unchanged, so it is never a reason to review again or to close over unsaved artifacts.

**Which ticket** (`crew_autopilot.py resume [--ticket <id>]`): the id you gave; else the handoff's `resume:` line, parsed by T-0006's `crew_resume.parse_resume` and used only when the handoff's `branch:` and `head:` match this checkout and the ticket folder exists; then this worktree's active ticket; then `.work/INDEX.md`, **only when exactly one** open ticket has a folder — several open tickets and no pointer stop and list them. In a lane worktree (crew 1.0.349, T-0063) the main checkout's INDEX — the first record of `git worktree list --porcelain` — supplies the rows this checkout's lacks, and the source then reads `.work/INDEX.md (main checkout)`; the folder must still be here. `next` reads a ticket's INDEX row the same way, and `--json` names the file that answered as `index_source`; rows in both that disagree stop as `index-disagreement`, and a listing git cannot give is kept in the stop's reason, never read as "no row". A handoff that cannot be used (no line, `resume: none`, unparseable, branch or head mismatch, no folder, T-0006 not installed) falls through with its reason printed; `## Next action` prose is never guessed from. When the handoff names a different command from the one disk names, disk wins and the disagreement is printed. `resume: /crew:autopilot --goal <slug>` stops until L-0541. **A ticket that is not this worktree's active one stops**, naming both — the scope guard and the completion audit judge edits by the active pointer; with no pointer set, autopilot activates the ticket it drives (`crew_ticket.py activate`). When context runs low, autopilot writes `resume: /crew:autopilot <id>` into the handoff and stops.

**Documents before review, the tracker after every phase (T-0022, ported in the 1.2.0 feature rush).** The phase order is implement, docs, refresh, review, done. `/crew:docs <id>` records why each document it leaves alone is `not needed`, and each deferral, in `.work/tickets/<id>/docs.json`; the read-only `crew_docs_check.py --root . --ticket <id>` then prints every document `updated`, `not needed (<reason>)` or `MISSING`, plus `adr, runbooks: not measured`. The CHANGELOG rule is mechanical and never waived: a marketplace entry whose source changed needs a line added under `## [Unreleased]` naming `` `<name>` `` and its current version (release bookkeeping and `.work/` alone owe none). README (an entry's `commands/`, `agents/`, `skills/*/SKILL.md`, `hooks/hooks.json` or `CONFIG.md` changed, or the marketplace's entry names did) and SECURITY.md (a guard, `approval_hook.py`, `promote-gate.*`, a `hooks.json`, an install script, a workflow) need an edit or a recorded reason once triggered; every deferral must reach TODO.md. No trusted scope base, an unreadable docs.json, or git unable to read a document at the base is `unknown` (never `updated`), which refuses like MISSING. `/crew:implement` step 6 and `/crew:done` check 5 run the same check; check 5 never edits. Autopilot runs the docs phase before the refresh, at most twice per review round for a `MISSING` document and not at all for `unknown`, which stops at once (`docs-unknown`) (`crew_autopilot.py tracker --after "/crew:docs <id>"` records each run), and a document owed after an accepted receipt stops as `docs-after-review`. After each phase and after `/crew:done`, `crew_autopilot.py tracker --root . --ticket <id>` derives the status from disk (`in-progress` once a path outside `.work/` changed since the recorded scope base, which `activate` records before implement) and calls T-0021's `crew_tracker.move`: unchanged when the tracker agrees, the sync command handed back for Jira or SDP, a stop with the reason and the `crew_tracker.py move` retry when it could not update. It may follow an accepted review because no tracker write enters the bundle — `.work/INDEX.md` is excluded, a vault outside the worktree or one git ignores is not staged, and T-0021 refuses an in-worktree vault git does not ignore; `test_tracker_move_after_receipt_keeps_bundle_hash` measures it against `review_patch`'s own hash.

**Stops.** Always a person: `brainstorm` and `review-acceptance` — accepting review FINDINGS with any BLOCK, or a round `review_ledger.py --auto-accept` refuses, is the owner's (`review_ledger.py --accept`), at any setting; only a final 0-BLOCK round is accepted by the ledger's guarded verb. With `autopilot.maxAutoReplans` an out-of-rounds BLOCK round is rejected and replanned instead, never accepted. `plan-approval` and `open-questions` are a person unless the owner's policy below allows. Enforced by `next` from disk: the ticket's gate `hold`, `landing` and `needs-owner`, and `blocked` (L-0550), `needs-replan`, `needs-replan-or-revert`, `unknown-ledger`, `failed-validate`, `direction-unknown`, `index-disagreement`, `unsettled-artifact`, `ticket-mismatch`, `max-phases`, `auto-replan-cap` (`autopilot.maxAutoReplans` successor plans already on the ledger), `drift` (explicitly focused and approved, a changed path outside Touch — "Focus" under "Scope and approval"), `no-progress` (the command just run is named again; not `/crew:review` after a refunded tool-failure round, which is a new round each time it records one, nor `/crew:docs` after a recorded attempt), `docs-missing`, `docs-unknown`, `docs-after-review`; enforced by the tracker step: `tracker-failed`, `tracker-unavailable`, and, with `--runner`, `in-flight` and `handover-elsewhere` (in-flight markers, below). Enforced by the command's procedure, not by `next` — which sees them only as `no-progress` if the same command comes round again: `review-verdict`, `failed-done-check`, `failed-phase`, `fix-refused` (T-0067). And every `AUTONOMOUS_STOPS` entry — `offboard-role`, `delete-map`, `rewrite-metrics`, `git-destruction`, `clear-inflight` — which `commands/autopilot.md` names and a test pins against `crew_state.AUTONOMOUS_STOPS`. `crew_autopilot.py stops` lists them all from code. No deploy or new ticket: T-0005, T-0012 (the one push, PR and merge are `ship`'s, below); the new tickets are step 3.3's follow-up after `--auto-accept` and the children of a split autopilot applies under the policy (below). Since T-0058 `next` also enforces `split-approval` and `split-check-unknown`.

**The size check after spec and after plan (T-0058).** Once the spec validates, and again once the plan validates, `next` runs the split rulebook's measures (`crew_split.measure` and `triggers`, below: acceptance checks, codemap subsystems, the findings rate, and plan steps after plan). **A trigger means look, never split.** Nothing fired continues. A fired trigger with no current `split.md` decision is `split-check` — not a stop: autopilot runs `crew_autopilot.py split --root . --ticket <id>`, judges the boundaries by the rulebook (crew:explorer), writes `split.md` with `answered:` naming every fired trigger, and runs `split --check`; a decision is current only while it passes the rulebook and names every trigger now fired, so a trigger that first fires after plan re-opens a decision taken after spec. `not-too-big` continues. `slices` continues after spec; after plan only when the plan's `## PR slices` validate through T-0059's `crew_split.parse_slices`, and until that lands it stops as `split-check-unknown` naming T-0059 — never continuing as though the slices were checked. `split` is `split-approval`, a stop: `crew_autopilot.py split --apply` runs `crew_split.apply --via autopilot`, which is allowed only by `crew_split.ticket_split_policy` — T-0012's split rule on the parent's spec risk (`self` any risk, `risk` only a known `risk: low`, `human` never; always `scope.allowCliApproval: true` and `autopilot.mode: plan`), asked at apply time and never read from a record. **In Jira mode a split always stops for the owner**, whatever `autopilot.approval` says: autopilot never creates a Jira issue, and the owner runs `/crew:split <KEY>`. SDP stops: SDP is a service desk, not where this work gets decomposed. Any caller may pass `--via autopilot` — as with `crew_ticket.approve`, whoever calls, the gate is the repository's policy, not the caller, and out of the box it refuses (`scope.allowCliApproval` false, autopilot off). `split --check` and `split --apply` apply the gate's rules at the gate's stage (`plan` only once plan.md validates): both refuse while a measure is unknown, with the gate's `split-check-unknown` wording, and both hold `split.md`'s `answered:` to every trigger firing now. A refusal prints `owner: the human types /crew:split <id>` last; autopilot never runs `/crew:split` itself. Once applied the parent is `superseded` and reads `closed`. A measure whose source is there and cannot be read or counted stops as `split-check-unknown`, naming the fix: a `.crew/codemap/` with no readable subsystem, an unreadable `.crew/metrics.md`, and T-0052's zero counts — an Acceptance section of plain `- ` bullets with no `- [ ]`, a plan whose steps are `## Step` rather than `### Step`, a Touch entry no codemap subsystem covers; a source the repository does not have at all — no codemap, no review recorded yet — is printed as `unmeasured: <name> (<why>)` and does not stop (`crew_split.absent_sources`). `/crew:autopilot split <id>` runs the same check on demand. At a `split-approval` stop the report's `crew_notify.py run-stop` sends T-0060's blocker `Approval waiting -> /crew:split <id>` (once per `split.md`).

**Settings** (`.crew/config.json`, and since T-0050 the machine-global file too for `mode`, `maxPhases`, `deploy`, `approval` and `questions`: the stricter of the two layers wins, a silent layer imposes nothing — CONFIG.md §20a; `maxAutoReplans`, `sleep`, `ship`, `knownFailures` and `ciTimeoutMinutes` stay repo only): `autopilot.mode` — `off` (default) or `plan`; only the exact string `plan` arms it, and any other value reads as `off` with a warning. `autopilot.maxPhases` — phases one invocation may run, default 12; anything but a positive integer reads as 12 with a warning. `autopilot.deploy` — `none` (default), `nonprod` or `all`: where a deploy may run without asking. Production needs `all` **and** `environments.prodUnattended: true` in **both** config layers, with `guards.cloudGuard` armed in `block`; anything crew cannot tell asks, and an active emergency refuses. `crew_autopilot.py deploy-allowed --env <name> --class <class>` answers `allow`, `ask` or `refuse` and prints a report line for every production decision. Nothing in this version dispatches a deploy — the key is inert until T-0045 consumes it (CONFIG.md §20). `autopilot.maxAutoReplans` (T-0074) — `0` (default, off) or an integer from 1 to 5: how many successor plans one ticket may have before an out-of-rounds BLOCK round stops for you again. At 1 or more, armed, and only where `autopilot.approval` would approve the successor plan, autopilot rejects a final FINDINGS round with a BLOCK itself (`crew_autopilot.py auto-reject`), runs `/crew:plan` for a successor plan, approves it under the policy and reviews again; an INCOMPLETE round, a same-family or unknown reviewer, a round still left, or anything it cannot tell is today's stop. The cap counts every successor plan on the ledger, yours included; the recommended value when you turn it on is 2. Anything but a non-negative integer reads as 0 with a warning, and anything above 5 reads as 5. `autopilot.ship` (T-0011) — `merge` (default) or `pr`; anything else reads as `pr` with a warning. `autopilot.knownFailures` — `[]`; anything but a list of strings reads as `[]`. `autopilot.ciTimeoutMinutes` — `60`; anything but a positive integer reads as 60. All three are read by `ship` (below) and shown by `settings --json`. An `autopilot` block only in `.crew/crew.json` is reported, not silently ignored; `/crew:migrate` carries the block to crew.json's top-level `autopilot` with a note that this copy is never read: crew reads `.crew/config.json`, and the personal keys also the machine-global file, where the stricter value wins (CONFIG.md §20a). `crew_autopilot.py settings --root .` shows what is in force: `mode`, `maxPhases`, `deploy` and `maxAutoReplans` on its first line, `approval` and `questions` on the second, the sleep window's `sleep=` line on the third, and all of it with `--json`. A key this crew does not act on yet (`maxTicketsPerRun`, `mode: backlog`, or a typo) adds a `warning: inert:` line naming the ticket that brings it; it never stops a run. The same keys are named in one `Inert settings` line at every session start and an `inert` line in `/crew:status` (T-0070, CONFIG.md §20).

**Approval and questions policies** (T-0010). `autopilot.approval` and `autopilot.questions` are `human`, `self` or `risk` (default `risk`); any other value reads as `human`, with a warning, and `human` always stops. At the plan-approval phase autopilot runs `crew_autopilot.py approve --root . --ticket <id>`: `self` approves at any risk, `risk` only when the spec's header says `risk: low` (a missing or unparseable risk is `high`). **Every `autopilot.approval` setting also needs `scope.allowCliApproval: true`** (`autopilot.questions` does not), a readable config (a `.crew/config.json` that exists but cannot be read as a JSON object, or an `autopilot` value that is not an object, reads both policies as `unknown` — could not tell — so `approve` refuses, a question stops and autopilot reads as off; an absent file or block still reads the defaults), autopilot armed, and a readable review ledger. A NEEDS_REPLAN ledger does not refuse: approving a different successor plan is its only way out, and the ledger still refuses a plan approved before (`crew_autopilot.py approve` exits 3 and says so). The receipt says `approved_via: "autopilot"`, the command prints `self-approved <id> under approval=<policy>, risk=<risk>`, and `crew_ticket.accepted` re-asks the policy on every read — a later spec edit, `approval: human` or `allowCliApproval: false` demotes it. The scope guard allows only that bare command, only while the policy says yes; `crew_ticket.py approve` stays refused. Autopilot never uses the group confirm ("Approving several tickets at once"): that stays the owner's own prompt, and `crew_ticket.approve` refuses an `autopilot` approval that carries a group's hashes, whatever the policy says. At an open question autopilot researches it (crew:explorer, crew:researcher), writes `.work/tickets/<id>/questions.md` — 2-4 options per question, the recommendation first, each with a `Cost:`, plus a `Research:` line — and `crew_autopilot.py questions-check --root . --ticket <id>` validates it and prints `action=take|stop`: `self` takes the recommendation, `risk` only on `risk: low`, `human` stops. A taken answer is recorded as `taken: Option <id> by autopilot (<policy>)`, naming the policy that took it; the check refuses one naming a policy that never takes (only `self` or `risk` does), and every `taken:` line while the policy in force says `stop` — a later switch between `self` and `risk` does not void an earlier honest record. Every self-approval and taken answer is reported by name.

**Sleep schedule** (T-0053). `autopilot.sleep.schedule` (`HH:MM-HH:MM`, machine local time, may cross midnight; default `null`, off) names one nightly window. Inside it, `autopilot.sleep.approval` and `autopilot.sleep.questions` (`human`, `self`, `risk`, or `null` for "keep the day value") replace the two day values, so an overnight run can approve its own plan or take a recommendation where the day setting would stop. The window is re-read from the clock at every decision, so a run that crosses the end of the window is back on the day values at its next one. A schedule, `sleep` block, clock or resolver crew cannot read is `unknown`, with a warning: per key the stricter of the day value and a valid night override applies (`human` over `risk` over `self`), never a looser one; an override that is not a policy (`"Human"` included) or cannot be read at all counts as `human`, and a non-object `autopilot.sleep` reads `human` for both keys. The clock is local time in the process's `TZ`, and `approve` / `questions-check` run in the model's shell environment. A window may be up to 23h59, and a looser night value applies for all of it; `scope.allowCliApproval: true` and every stop still bind asleep. `crew_autopilot.py settings` prints `sleep=<off|awake|asleep|unknown> schedule=... approval=... questions=...`, and a policy a night override set ends its reason with `(asleep <window>; day value <day>)`. **A receipt written asleep stops standing when the window ends** if the day value would not have approved it: `crew_ticket.accepted` re-asks the policy, so in the morning that ticket waits for `/crew:approve <id>` (the overnight work stays). **Manual sleep** (L-0652): `/crew:autopilot sleep` starts sleep mode now, until the window's end (12 hours with no window), and `/crew:autopilot wake` ends it now; the state lives in `<git-common-dir>/crew/autopilot-sleep.json` (UTC times, a regular file only), shared by every worktree, and `settings` adds `source=manual until=<HH:MM>`. **Until L-1504 a manual sleep only tightens** (owner decision 2026-10-04): outside the window it applies a night value only where it is stricter than the day value, because the session can run the CLI itself; L-1504 makes the approval hook accept only the owner's typed `/crew:autopilot sleep` and then unlocks loosening. `sleep` refuses unless `scope.allowCliApproval` is exactly `true`, autopilot is armed and some override is stricter than its day value (or the window is open); a state file crew cannot trust reads `unknown` (the stricter value per key), and `wake` never loosens a night value stricter than the day. CONFIG.md §20 has the details.

**Ship** (T-0011, `crew_autopilot.py ship --root . --ticket <id>`, after `/crew:done`). It refuses unless `next` names `ship`, refuses the default branch (or one it cannot read) and a working tree that differs from HEAD (`git status --porcelain --untracked-files=all`, ignored files aside; a receipt can cover uncommitted edits a push does not carry) before pushing, runs `git push -u origin <branch>` (never force), `gh pr create --head <branch> --fill` when there is no PR, and under `autopilot.ship: merge` polls `gh pr checks <n> --required` every 30 s up to `autopilot.ciTimeoutMinutes` (60). It merges with exactly `gh pr merge <n> --merge --match-head-commit <HEAD>` — bound to the commit whose checks and receipt it read, so a push that lands afterwards is refused rather than merged; a merge commit, never `--squash` or `--rebase`, because either rewrites the ticket's commits and orphans every codemap and diagram `anchor:` that names one (D-028); never `--admin`, never a bypass of branch protection — only when every required check is `pass` or fails under a name listed **exactly** in `autopilot.knownFailures` (names and states are read verbatim, never trimmed or re-cased), the PR's head and this checkout's HEAD are still the commit it took right after the push (checked before and after every poll and again right before the merge), the tree is still clean, the review receipt still stands after the wait on the same ledger bytes the review families came from, and the base branch has no merge queue (a queue picks its own merge method and keeps merging after `ship` stops; one it cannot read stops too); it then confirms the PR reads MERGED. If gh queued the PR anyway (a queue enabled after the check), `ship` dequeues it once with GraphQL's `dequeuePullRequest` — the only mutation it ever sends — and stops, naming the queue and whether the dequeue worked. The settings, the risk and the review families are re-read on every poll, so disarming autopilot, switching to `ship: pr` or a ledger that turns same-family while CI runs all stop it, and a green that lands after the timeout stops like a pending one. Pending, or no required check reported yet, waits; skipped, unknown, unreadable or an unlisted failure stops. **A `high`-risk ticket (or one whose header names no risk) never merges on same-family reviews** — every completed round `claude`, or with no `model_family` recorded, which counts as the author's family. Codex, the only cross-family reviewer here, was out until 2026-10-01, and while it is unavailable every review is same-family, so every `high`-risk ticket stops at `ship: merge` with its PR open for you to merge. It prints `action=… stop=… pr=… reason=…`, then the `checks:` and review `families:` it rested on. gh 2.46's `gh pr checks` has no `--json`, so its text output is parsed; a line or exit code that does not fit - a row that is not exactly five tab-separated fields (gh prints a check's name and description unescaped, so a tab inside one is unreadable and that check never ships unattended), exit 1 with no failing row, or anything on stderr beside the rows - reads as unreadable, never green.

### Ticket statuses

One vocabulary, owned by `crew_tracker.py` (`STATUS_ORDER`, `OWNER_STATUSES`, `CLOSED_STATUSES`, `LANE_FOR_STATUS`); every other reader's list is held to it by `tests/test_status_vocabulary.py` (T-0037).

| Word | Open or closed | Written in | A spec header edit to it | Obsidian lane | Jira / SDP |
|---|---|---|---|---|---|
| `direction`, `ready` | open | INDEX, tracker | stales the approval (not in `STATUS_VALUES`) | `backlog` | nothing pushed |
| `spec`, `planned`, `review` | open | INDEX, tracker, spec header | keeps the approval | `ready` (`spec`, `planned`), `review` | nothing pushed |
| `in-progress` | open | INDEX, tracker, spec header | keeps the approval (T-0059's non-final slice) | `inProgress` | pushed |
| `needs-owner` | open, waiting on the owner | INDEX, tracker only — never a spec header | stales it, like any unknown word | `backlog` | nothing pushed |
| `done` | closed | INDEX, tracker, spec header | keeps the approval | `done`, checked | pushed |
| `cancelled`, `superseded` | closed | INDEX, tracker, spec header | stales the approval on purpose | `done`, checked | nothing pushed; the owner closes the item by hand |

Any other INDEX word maps to no lane: `move` refuses it with nothing written, and `crew_tracker.py read` reports it as `could not tell` (`INDEX status <s> is not a status crew knows (...)`), never as a disagreement. The words the owner retired on 2026-10-05 get a text-only hint naming their replacement (`RETIRED_STATUSES`: `approved` -> `spec`, `merged` -> `done`, `closed` -> `done`, `new` -> `direction`, `parked` -> `needs-owner`) — never a lane, a write or an exit code (L-0530).

`approved` and `merged` are spec-header words only (they keep the approval; a header `merged` does not close a ticket for autopilot). `crew_ticket.STATUS_VALUES` is unchanged by T-0037: it is the approval-keeping subset, so a blocking hook accepts nothing new.

- **Closed** means closed in every reader: the session brief and `crew_ticket.resolve_active`'s INDEX fallback skip the row (a prose `- Cancelled: T-1` line too, in any case), `/crew:approve`'s precheck refuses it as "closed in .work/INDEX.md", autopilot stops it as `closed` (waiting on nobody), and `/crew:status` lists it on no line.
- **Cancel** a ticket with `crew_tracker.py move --ticket <id> --to cancelled`; the INDEX row alone closes it. A ticket replaced by others is `superseded`, with `split-into: <id>, <id>` (T-0052) or `superseded-by: <id>` on its own line under the spec header. Moving out of `done`, `cancelled` or `superseded` — to any word — needs `--reopen`, and without it the move is refused with nothing written.
- **`needs-owner`** moves to and from any open word without `--reopen`. The question for the owner goes under the ticket's existing `## Open questions`. `/crew:status` prints `owner    <ids> (needs-owner)`. A non-ticket item that needs the owner is minted `ready` (`crew_ticket.py mint`), then moved to `needs-owner`.
- **Derived, never typed: `blocked` and `needs-replan`** (L-0639). `hooks/scripts/crew_ticket_state.py` answers them for one ticket, read-only, and autopilot's `hold`, `landing`, `needs-owner`, `closed` and `blocked` stops act on it (L-0550; L-0551's owner list will too). `blocked` comes from the optional `depends-on: [T-1, T-2]` line under the spec header (hashed with the spec, so changing it needs `/crew:approve` again): each dependency is `closed`, `open`, `cancelled`, `superseded` or `unknown`, read from its INDEX status cell first and, with no row, its spec header (`done` or `merged` is closed). Every state but `closed` blocks - a cancelled or superseded dependency will never close as done, so it blocks and is named. `needs-replan` comes from the review ledger's `NEEDS_REPLAN`. A typed `blocked` or `needs-replan` INDEX cell is reported as a problem, never obeyed. The could-not-tell rule holds throughout: an unreadable INDEX, a row with no status cell or no row and no spec makes a dependency `unknown` (it blocks); no spec or an unreadable `depends-on:` line makes `blocked` None, an unreadable INDEX makes the gate `unknown`, and an unreadable ledger makes `needs_replan` None with a problem - never False. **`done` counts as closed** for a dependency, before it is merged (approved 2026-09-26; accepted as risk). The gating statuses `hold`, `landing`, `needs-owner`, `cancelled` and `superseded` are read from the INDEX cell first, then the spec header; `hold` stays an open word everywhere else.
- **`next.md`: who a ticket waits on and what happens next** (L-0640). A ticket folder may hold `.work/tickets/<id>/next.md` with up to five `key: value` lines (key case-insensitive, blank and `#` lines skipped, unknown keys ignored): `waiting-on:` (`owner`, `agent`, `external` or a ticket id), `next:` and `reason:` (one line of free text, shown clipped to 200 characters), `revisit:` (`YYYY-MM-DD` only) and `superseded-by:` (a ticket id). `crew_ticket_state.read_next` parses it and `view` carries the fields as `next`, plus `revisit_due` (True on or after the date, False before it, None with no date or a bad one). It is local state and not part of the contract: it is not hashed, `/crew:approve` does not validate it, and nothing in crew writes it automatically - you edit it by hand. A bad, empty or repeated value is a problem and that field is unset; a `next.md` that cannot be read, or that resolves outside the ticket folder, is a problem and every field is unset (cannot tell, never "nothing asked"). A `needs-owner` gate with no `next:` reports `needs-owner: cannot tell what is asked (no next: in next.md)`, and a `superseded` gate reports that it cannot tell what replaced it when neither `next.md`'s `superseded-by:` nor a `split-into:` / `superseded-by:` line under the spec header names the successor ticket ids (`TBD` names none).

### Splitting a ticket: one rulebook (`/crew:split`)

`hooks/scripts/crew_split.py` holds `/crew:split`'s judgement as code (T-0052), and T-0058's `/crew:autopilot split` calls the same functions, so there is one set of split rules in every tracker. Its module docstring is the API and the `split.md` format.

- **Measures and triggers.** `crew_split.py --root . --ticket <id>` prints the ticket's measures (`plan_steps`, `acceptance`, `touch`, `subsystems`, `findings_rate`, `tickets_too_large`) and the fired triggers for its stage. A measure it cannot read prints `unknown` and its trigger `unknown:<name>`, never "not fired" — including a readable section that yields nothing (no checkbox bullet under `## Acceptance checks`, no `### Step` heading, an empty Touch) and a Touch entry no codemap subsystem covers. **A trigger means look, never split.**
- **Thresholds, each with its evidence** (constants in `crew_split.py`, measured 2026-09-26 on 19 review ledgers; re-measure at 10 more): `PLAN_STEPS_LOOK = 9` (at plan; the only tickets past 4 rounds or 30 findings had 9 and 10 steps, r = 0.73 with findings), `ACCEPTANCE_LOOK = 12` (at spec; T-0004's pre-split spec, the one real split, had 12), `SUBSYSTEMS_LOOK = 2` (Touch entries in two or more codemap subsystems, kept from the command's old table), and the repo-wide findings rate above `HEALTHY_HIGH` (`findings-rate`, `tickets-too-large`), a reason to look and never a verdict on one ticket. The Touch count is reported with no threshold (r = 0.24 with rounds).
- **The rules.** `check_proposal` accepts `decision: split`, `slices` or `not-too-big` with at least one `## Evidence` line whose key is in `EVIDENCE_KEYS` (`plan-steps`, `acceptance-count`, `subsystems`, `findings-rate`, `tickets-too-large`, `separable-criteria`; any other key is refused). A split also needs 2-5 children, each with a title, a `risk:`, a `subsystem:`, at least one criterion and one exclusion; every parent acceptance criterion placed verbatim (whitespace aside) exactly once across the children and `## Stays on parent`; nothing placed that the parent lacks; and a `separable-criteria` line. "Not too big" is a result.
- **Per tracker.** `files` and `obsidian`: `crew_split.py apply --root . --ticket <id> --via command` writes `spec.pre-split.md` byte-identical to `spec.md`, mints each child `ready` through `crew_ticket.mint` with a direction quoting its criteria and exclusions and pointing back to the parent, records each id under a trailing `## Minted` in `split.md` as it returns, and only after every mint returned sets the parent's spec header to `status: superseded` with a `split-into: <ids>` line and moves its INDEX row (and Obsidian card) to `superseded`. A failed mint names the minted and unminted children, leaves the parent's status unchanged and drops the check record, so a re-run needs a fresh `check` and yes; it then skips a child only when an apply record (`split-apply.json`) exists, the ticket carries apply's provenance (`origin: split of <parent>`, `split-child: <n>` in its direction) and an INDEX row, and its direction is exactly what the CURRENT proposal's child would get; it adopts a child minted whose id never reached `split.md` on the same terms. A minted child the edited proposal no longer matches stops the apply, naming it, with nothing minted and the parent untouched; restore that child's text, or cancel the stale ticket (`crew_tracker.py move --ticket <child> --to cancelled`) and re-run `check` — a `cancelled` or `superseded` child is never reused, and a fresh one is minted in its place. A `## Minted` section apply did not write (not last, holding anything but `- Child N: <id>` lines, or with no apply record) is refused, and the proposal hash covers every byte but a valid trailing block. A spec or proposal that is not UTF-8 is refused before the first mint. `jira`: `/crew:split`'s MCP steps as before (sub-task or linked issue, one parent comment, the cache files, the parent untransitioned), now with `check` before the confirmation and `confirm` before the first create. `sdp`: stops — SDP is a service desk, not where this work gets decomposed. `apply --via autopilot` (T-0058) is autopilot's path under `ticket_split_policy` (Autopilot, above): it skips only the human-turn confirmation and runs every other check, the existing-children verification included; `--via command` needs no policy.
- **The confirmation gate.** `/crew:split` stays model-invocable, so asking a session to split a ticket works, and the guard is on the confirmation itself. `check`, on a pass, records the proposal's sha256 and the session's current human-turn id (the `turn.id` the context hook writes on UserPromptSubmit, found through `CLAUDE_CODE_SESSION_ID`) at `<git-common-dir>/crew/tickets/<id>/split-check.json`. `confirm` (and `apply` through it) passes only when the proposal is unchanged and a different turn id is readable for the same session, set by a prompt (the hook's `lastPrompt`) that is readable, is not a harness envelope (a `<task-notification>`, wake, webhook — anything opening with `<`) and is not the prompt `check` ran under (a loop re-sending it, or the owner typing the same words twice; the first 500 characters are compared). No session id, no or an unreadable turn record (the context hook off, or `memory.inject: false`), an empty turn id or prompt, or a check that saw none is a refusal. A successful apply spends the check record. Accepted limits (owner decision 2026-10-04): **the gate is not owner-proof against the session itself — a session can schedule its own plain-text "yes" (`send_later`, a routine) and pass it**, because a scheduled prompt delivered as plain text reads as typed. `CLAUDE_CODE_SESSION_ID` is an environment variable any process can set, and a human prompt that is not a yes also passes the code gate. The gate stops a session answering its own question in the same turn or from a harness envelope, not one that sets out to forge the answer; the prose confirmation is what reads it. The follow-up routes split approval through the `/crew:approve` harness path (`TODO.md`).

### PR slices: one ticket, ordered slice PRs (T-0059)

A ticket that holds together but is too large for one review stays one ticket; its plan ends with a `## PR slices` section that groups the steps into ordered slices, each shipped as its own PR with its own review budget.

```
## PR slices
### Slice 1: <name>
Steps: 1, 2
Base: main
### Slice 2: <name>
Steps: 3-4
Base: slice 1
```

- **The rule** is `crew_split.parse_slices(plan_text)` (`SLICES_MIN`/`SLICES_MAX` = 2/5, the children's bounds): slices numbered 1, 2, ... in order; every plan step in exactly one slice; each slice's steps one contiguous run, after the previous slice's; `Base: slice <k>` only for an earlier k; `Base: main` only when the slice's steps' `Files:` share nothing (equal or glob-matching) with any earlier slice's, and a step with no `Files:`, or any pair of Files entries not provably disjoint, is "cannot tell" (after `crew_ticket`'s segment normalisation, a pair is disjoint only when the literal prefixes, a literal entry being a whole directory, differ case-folded at an index both have), never "shares nothing". A `### Step N` heading written after the section is still a step (and ends the section), so leaving it out of every slice is refused; a `## Step N` heading is refused, because `measure` counts only `### Step` (case-sensitive, as `parse_slices` is). No section is still a valid plan. `/crew:autopilot`'s `next` stops at `plan` with `PR slices: <problems>` when the section breaks a rule. `crew_ticket.validate` does not report it yet: that file is a harness path (CLAUDE.md, T-0087), and its hook is a separate tooling PR.
- **One slice at a time.** `<git-common-dir>/crew/tickets/<id>/slices.json` records `current`, the slices `done` and each shipped slice's `pr`, `branch`, `base` and `merge_sha`; absent means slice 1, and an unreadable or out-of-shape file stops `next` as `slices`. `next` prefixes each phase's reason with `slice n of m (<name>): steps a-b only`, and `/crew:implement` works only the steps `crew_autopilot.py slice --ticket <id>` prints. `/crew:done` on a non-final slice sets the header to `in-progress` (T-0037 kept it in `STATUS_VALUES`, so the approval stands) and runs `crew_autopilot.py slice-done`; only the last slice's `/crew:done` sets `done`. A `status: done` header while an earlier slice is current stops as `slices`.
- **Ship per slice.** `ship` opens `gh pr create --head <slice branch> --base <base> --title "<id> slice n/m: <name>"` (with a body naming the steps and, when stacked, the PR it stacks on), never ships slice n before slice n-1 is merged (or opened, under `autopilot.ship: pr`), and merges only through `merge_argv`'s merge commit. The base rule (`slice_base`): the default branch for slice 1, for a `Base: main` slice, and once every earlier slice is merged; otherwise the branch of the latest unmerged slice down its `Base: slice <k>` chain. Slice 1 ships from the ticket's branch, slice n from `<that branch>-s<n>`. A merged non-final slice (or an open one under `ship: pr`) names `next-slice`.
- **Per-slice review budget.** Each slice gets its own `BUDGET` rounds; rounds spent on earlier slices stay in the ledger and are never refunded. `crew_autopilot.py next-slice` creates the next slice's branch off its base and calls `review_ledger.open_slice` (a `slices` row the round count starts from). `open_slice` is a harness change landing in its own tooling PR; until it does, `next-slice` refuses with nothing written, so a sliced ticket stops after its first slice ships rather than reviewing slice 2 on slice 1's spent budget.

### Plain-text lifecycle: short prompts that name a command

With `route.enabled: true` (since 1.0.46, **off by default**), a short plain-text prompt can stand in for a lifecycle command. crew's UserPromptSubmit context hook matches the **whole** prompt against a small table (`hooks/scripts/crew_route.py`, `PHRASES`) and, on a match, puts one `crew route:` line first in that turn's context: the `/crew:<command> <ticket>` whose procedure Claude should run through the Skill tool. The hook runs nothing and blocks nothing, and the command's own checks still decide.

| You type (whole prompt) | Routes to |
|---|---|
| `brainstorm <topic>` | `/crew:brainstorm <topic>`, in your words |
| `write the spec`, `write the spec for <id>`, `spec it`, `spec <id>` | `/crew:spec <ticket>` |
| `plan it`, `plan <id>`, `write the plan` | `/crew:plan <ticket>` |
| `implement it`, `implement <id>`, `start implementing` | `/crew:implement <ticket>` |
| `review it`, `review <id>`, `run the review` | `/crew:review <ticket>` |
| `close it`, `close it out`, `mark it done` | `/crew:done <ticket>` |
| `continue`, `keep going`, `carry on` | whatever `crew_autopilot.next_phase` names from disk for the ticket |
| `status`, `crew status` | `/crew:status` |
| `autopilot status`, `autopilot status <id>`, `what's autopilot doing?` | `/crew:autopilot status [<ticket>]` |
| `take care of <work>`, `handle <work>` | `/crew:autopilot assign <work>`, in your words |
| `work toward <goal>`, `work towards <goal>`, `make it so <goal>` | `/crew:autopilot goal <goal>`, in your words; the line also asks Claude to say what changed and how to undo it |
| `pick the goal back up`, `resume the goal` | never routes: asks you to type `/crew:autopilot run --goal <slug>` |
| `focus on <id>` (an explicit id only) | `/crew:autopilot focus <ticket>` |
| `run <id> and <id> in parallel`, `run <id>, <id> and <id> in parallel` (two or more distinct ids) | `/crew:autopilot wave <ticket> <ticket> ...`; an id with no folder asks, naming it |
| `split this ticket`, `split it`, `split <id>`, `this ticket is too big`, `<id> is too big` | `/crew:autopilot split <ticket>` (never `/crew:split` directly) |
| `I'm heading to bed`, `heading to bed`, `going to sleep`, `I'm going to sleep` | `/crew:autopilot sleep`; the line also asks Claude to say what changed and how to undo it |
| `I'm back` | `/crew:autopilot wake` |
| `good night`, `morning`, `good morning` (bare greetings) | never routes (owner decision, 2026-10-04): asks "did you mean `/crew:autopilot sleep`?" (or `wake`) |

**Autopilot rows** (since 1.0.345, T-0057). Whether each `/crew:autopilot` subcommand runs yet is read from `crew_autopilot.route` when the prompt arrives, so a row goes live the day its command lands with no edit here. Until then (today `assign`, `goal` and `run --goal`; `focus` since T-0020) the matched prompt gets a line that runs nothing: it says the command is not available yet and tells Claude to answer your prompt as written, so "handle the merge conflict" is still an ordinary instruction. A router that cannot be read asks; a subcommand the router does not know produces no line. Work starting with `it`, `this`, `everything` and the like (`handle it for me`), work naming the stem `approv` (spaced-out letters included), and a Unicode line break produce no line. Otherwise assign, goal and focus prompts may hold only ASCII letters, digits, space and `.,:;_#()-`; any other character (a quote, a lookalike letter, an accent, an invisible character, a fullwidth or lookalike `/` or `?`, or `/ ? " $ \ | & < > *`) asks you to retype instead, so the routed command is exactly what you typed (a leading `let's` is fine). A word starting with `-` (`handle --goal x`) asks, since it reads as a flag; a hyphen inside a word (`sign-off`) routes. A trailing `not`, `no`, `nope`, `wait`, `cancel`, `cancel that`, `never mind` or `forget it` asks. The two status questions are the only rows that accept a trailing `?`.

**Wave, split, sleep and wake** (since 1.0.345, L-0662). `sleep` and `wake` route today, because L-0652's manual sleep mode made them `/crew:autopilot` subcommands, `split` since T-0058 made it one, and `wave` since T-0029. They take the same allowlist; `sleep` and `wake` also accept the apostrophe in `I'm`, straight or the curly `’` iOS and macOS type (a curly quote anywhere else asks). A bare greeting is never a command: `good night`, `morning` and `good morning` ask whether you meant sleep or wake. `go to sleep mode later`, a question about sleep mode, quoted text, `split the file` and a bare `this is too big` never route.

`it` and `this` mean the ticket, as does leaving it out. The prompt is normalised first: surrounding space, one trailing `.` or `!`, and one leading `please`, `ok`, `now` or `let's` are dropped, and case is ignored. Nothing else routes: not a mention inside a longer sentence, not a question, not a prompt with a line break (any line boundary Python's `str.splitlines` knows, U+2028 and U+0085 included) or over 80 characters, not a slash command or anything in backticks. `do it`, `go`, `go ahead`, `yes`, `ok`, `sure`, bare `done`, bare `next` and `ship it` never route — they usually answer Claude's last question.

**Three outcomes.** `route` — an unambiguous phrase and a ticket that resolves to exactly one. `ask` — the phrase matched but no single command can be passed on as named: an id with no `.work/tickets/<id>/` folder, a broken active-ticket pointer, several open tickets and no pointer (listed), none at all, a `continue` whose next phase is a stop (with its reason), or a command that would have to be cut (over 200 characters) or reflowed to fit the line — a route never passes a command other than the one named. The line then tells Claude to ask you which before running anything. `none` — no line at all, so the context is exactly what it was. The ticket comes from the id you typed, else this worktree's active ticket, else `.work/INDEX.md` **only when exactly one** open ticket has a folder; the INDEX fallback that takes the first open line is never used.

**Routing never approves.** No phrase routes to `/crew:approve`, a `continue` whose next step is approval asks instead, and `/crew:approve` is not model-invocable anyway. Type `/crew:approve <id>` yourself.

**Settings.** `route.enabled` in `.crew/config.json` or the machine-global file; only the JSON value `true` arms it (`"true"`, `1` and `yes` read as off, with a warning). `/crew:init` writes `false` into a new repo's file, and the repo value wins, so a machine-wide `true` needs the key removed or set `true` there too. A `route` block only in `.crew/crew.json` is reported, not read. Under Codex no line is emitted, and `memory.inject: false` silences it with the rest of the hook. `python3 crew_route.py settings --root .` shows what is in force; `python3 crew_route.py decide --root . --prompt "review it"` shows what a prompt would do. CONFIG.md §21 has the key.

**`wave`** (T-0029; `hooks/scripts/crew_wave.py`). Design happens in the main session with the owner — `/crew:brainstorm`, `/crew:spec`, `/crew:plan` per ticket — and `crew_wave.py set --slug <s> --tickets <ids> [--deps <id>=<id>,<id>|none]` records the set in `.work/autopilot/<s>.json` (a set that was started is fixed: `set` refuses to rewrite it, and a second `start` relaunches only the lanes the first one launched, so a new ticket goes in a new set). Approval is the owner's own group approval (T-0024: `/crew:approve T-a T-b`, then `/crew:approve --confirm`). `crew_wave.py plan --set <s>` is read-only: per ticket `eligible` or `refused: <reason>` — no current approval, INDEX status `direction` or closed, a dependency not closed, dependencies `unknown` (no set-file deps and no parseable `(depends on ...)` in the INDEX row: never read as none), a Touch that overlaps another lane's, or more lanes than `autopilot.maxLanes` — then the wave, the later waves and a provisional landing order by crew version. `crew_wave.py start --set <s>` writes one lane file per lane under `.work/autopilot/<s>/lanes/` and prints one launch per lane: an `Agent` with `isolation: worktree`, never any other launch — the Step 1 spike measured that only an isolated lane's hook payload carries its own worktree as `cwd`, so only there does the scope guard judge its writes by its own ticket. Each lane first runs `crew_wave.py lane-init`, which refuses to run in the main checkout, outside `<main>/.claude/worktrees/`, in a worktree another lane names, or where the ticket branch is checked out elsewhere; it checks out or creates `<id>-wave`, copies the ticket folder and `.crew/config.json` in byte-identical, and requires `crew_ticket.accepted` to say `approved` and the scope guard to be at `block` there before it activates the ticket. The lane then implements, refreshes, reviews (reserving and recording rounds through `review_run.py`; a relaunch hands a reserved, unrecorded round back instead of reserving another) and runs `completion_audit.py --check`, and ends with exactly one `crew_wave.py lane-done --state clean|findings|question|failed`. `crew_wave.py collect --set <s>` prints one batch: each lane's state (a missing or unreadable lane file is `unknown`, never `clean`; an `owner-accepted` receipt written while the lane ran marks it `failed`), every open question with its recommendation first, the exact `/crew:approve` lines, the landing order of clean lanes and the later waves. It lands nothing — merging is T-0011's. `crew_wave.py cleanup --set <s>` removes a lane's worktree (`git worktree remove`, never `--force`) and branch (`git branch -d`, never `-D`) only when its branch is on origin's default branch after a fetch and the worktree is clean with nothing untracked; everything else, and anything it cannot tell, is kept and named. **The wave refuses to run unless `scope.mode` is `block` for every lane ticket** (`scope-not-enforcing`, naming the fix; the config is read where the scope guard reads it, so a linked worktree with no `.crew/config.json` of its own is judged by the main checkout's, and its own config, when present, wins whole), and a lane never accepts or rejects a review, approves a plan or merges. The lane prompt forbids it; `crew_ticket.py approve` is already refused by the scope guard, and the guard's subagent never-list — `review_ledger.py --accept|--reject` with every abbreviation, `allow_abbrev=False` in `review_ledger.py`, and `gh pr merge --admin` from any subagent — is review-harness work that lands separately (T-0087). **Until it lands, nothing mechanical stops a lane from accepting a review or admin-merging; only the prompt does.** Settings (repo only): `autopilot.maxLanes` — lanes at once, default the resolved `pm.maxDispatches`, which it can only lower; `autopilot.reviewPolicy` — `stop` (default: the lane ends at the first verdict), `clean-only` (a CLEAN round goes on to the done checks) or `fix-and-rereview` (fix and re-review within the ledger's two rounds); anything else reads as `stop`, with a warning. The Workflow tool is not used: the spike could not measure whether crew's hooks fire inside it.

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
| Repo | `.crew/config.json` | `/crew:init` (first write); `platform-sync` (the `platform` block, and the whole file when it heals — see §3); the `/crew:config` menu (`crew_config.py --set ... --repo`, `crew_config_menu.py save`) |

Repo overrides global overrides built-in defaults, merged recursively with
`crew_state.merge_defaults` — the same policy `crew_upgrade.upgrade_config` (run by `/crew:migrate` for a pre-0.20 config) uses to bring a
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

A key the global filter drops (a `scope` or `emergency` block, a `tracker`) takes
effect nowhere. It is not silent:
every session start names it in its `Inert settings` line as
`key=value (global, not read)` (T-0070), and `/crew:config --show` lists it.

**In a linked git worktree.** `.crew/*` is gitignored, so a lane made with
`git worktree add` starts with no `.crew/config.json` or `.crew/crew.json`. Since
crew 1.0.69 (T-0088) such a worktree reads the **main checkout's** repo config,
found through `git rev-parse --git-common-dir` (`crew_common.repo_config_dir`).
A worktree with either file of its own reads only its own files: they win whole,
even when partial, and are **never merged** with the main checkout's. When `.git`
is a file but git cannot name the main checkout, the source is `unknown`,
nothing is inherited, and `/crew:status` and `/crew:config --explain` say so
rather than showing the config as simply absent. A submodule, or a bare common
directory, is its own repo. Inheritance is read-only: no writer (`/crew:init`,
the heal path, `platform-sync`, `/crew:migrate`, the auto-clear setup) ever
writes the main checkout's file, and the heal path no longer creates a default
config in an inheriting worktree, because that default would shadow the owner's
(nor in one where git could not tell; it asks again next session).

**A lane made before 1.0.69 still reads its own file.** Every SessionStart heal
on crew 1.0.68 or earlier wrote a default `.crew/config.json` into a lane that
had none, and that file wins whole. `/crew:status` and `/crew:config --explain`
say so (`... the main checkout's (<path>) is not read ...`); if the lane's file is
a default nobody edited, delete it (and `.crew/crew.json`) to inherit.

**Behaviour change:** every Python guard in a lane worktree now reads the owner's
settings where it read the built-in defaults before - `guards.forcePush: allow`
instead of `block`, `scope.mode`, `scope.allowCliApproval`, `roleWrites` and
`cloudGuard` the same way. Ratcheted guard keys still take the narrower of repo
and machine-global. A lane that wants its own guards writes its own
`.crew/config.json`, and that file then wins whole.

**The shell and PowerShell readers (crew 1.0.330, T-0096, partly).** `_common.sh`'s
`crew_repo_config_dir` and the PowerShell `Get-CrewRepoConfigDir` (one body,
copied into each script that uses it) resolve the same directory by the same
rules, without python. Routed through them: the incident stand-down read
(`emergency.standDown`, in `_common.sh` for every bash gate and in
`promote-gate.ps1`), both cloud-guard no-python fallbacks, and `auto-clear.ps1`'s
repo veto. In the cloud guard's fallback an `unknown` source counts as armed: a
lane whose git cannot name its main checkout, with no usable python, refuses Bash
until one works. Inheritance can loosen as well as tighten: an inherited
`cloudGuard: off` applies in a lane. The session hooks (`notify`,
`handoff-read`, `handoff-write`, `context-watch`, both flavours) read the
resolved file too (crew 1.0.343, L-0680): a lane notifies with the main
checkout's `notify` settings, so several lanes ping the same channel unless one
writes its own config, and an inherited `context.handoffPath`,
`keepTranscripts` or threshold applies in the lane while the handoff path
stays inside the lane: a relative one names a file there, and one that leaves
it (absolute, `..`, a symlink out) or names a directory is the lane's
`.work/HANDOFF.md`, with a warning. The PowerShell hooks are stricter on links:
Windows PowerShell 5.1 cannot resolve one as `realpath` does, so any symlink or
junction on the way counts as leaving, even one that points back inside. What they write (transcripts, markers, the
handoff note) stays in the lane, and `context-watch` still needs a `.crew/`
directory there before it measures. **Not yet covered** (they read only the
worktree's own file): the verify gate, the scope and completion wrappers, and
`review_gate.py`. Until those land, **the PowerShell
verify gate reads the lane's own `emergency.standDown`** while the bash verify
gate (through `_common.sh`) and `crew_incident.py` read the inherited one.

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
Every file was valid; nothing surfaced the discrepancy. `/crew:config` runs
`--check-global` and reports the same findings.

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
equals `global_template_config()` (`default_global_config()` minus the personal
keys) byte-for-byte — the same drift gate the repo template has. It is deliberately not a copy of the repo template: it carries
only what is a property of the machine or the person (`pm.authority`, `qa`,
`dev`, `secondOpinion`, `notify`, `memory.vaultPath`), and no `schema`.

A global file that is missing, empty, or fails to parse is treated exactly
like an absent one — the same reasoning `_read_config_strict` documents for
the repo side — so a typo in your global config degrades one repo's settings
to defaults rather than breaking every session on the machine.

### Personal defaults, backups, and rebuilding a lost config (T-0050)

```
python3 hooks/scripts/crew_config.py --set autopilot.approval='"self"' --apply  # global default
python3 hooks/scripts/crew_config.py --root . --explain --all       # every key, layer, shadows
python3 hooks/scripts/crew_config.py --root . --unset autopilot.mode --repo --apply
python3 hooks/scripts/crew_config.py --root . --rebuild --repo      # dry run; then --apply
python3 hooks/scripts/crew_config.py --root . --backups --repo      # stamps, newest first
python3 hooks/scripts/crew_config.py --root . --restore <stamp> --repo --apply
```

- **Global defaults for the personal keys.** `autopilot.mode`, `maxPhases`,
  `deploy`, `approval` and `questions` can be set once in
  `~/.claude/crew/config.json` for every repo on the machine. They combine per
  key: the stricter of the layers that set the key wins, and a silent layer
  imposes nothing — so a global value is a default a repo may narrow, never a
  grant it cannot refuse (CONFIG.md §20a). New repos no longer spell these
  keys; a repo set up before this spells `autopilot.mode: "off"`, which holds a
  global `plan` down — `--explain --all` names each such `shadow:`, and
  `--unset <key> --repo --apply` removes it on your yes.
- **Every crew script write is backed up first** to `~/.claude/crew/backups/`
  (newest 20 per file; a hand edit is not), and a failed backup refuses the write. `--backups` lists them
  and `--restore <stamp>` puts one back, backing up the current file first.
- **The profile.** `--set`/`--unset --apply`, the menu's Save and
  `--save-profile --apply` keep your non-default values in
  `~/.claude/crew/profile.json` (and `<memory.vaultPath>/crew/profile.json`
  when you keep a vault, so it syncs). `--rebuild --repo|--global` regenerates
  a lost or corrupt config from the template plus that profile; a dry run
  until `--apply`, exit 3 when the profile is there and unreadable.
  SessionStart's heal still writes crew's defaults, never the profile — it
  names the rebuild instead.

### The `/crew:config` menu — set either layer, or delete the repo config

`/crew:config` with no argument, and its alias `/crew:config-setup`, open a
menu (`skills/crew-setup/config-menu.md`, backed by
`hooks/scripts/crew_config_menu.py`). Pick the **layer** — this machine's
`~/.claude/crew/config.json` or this repo's `.crew/config.json` — then an
**area** (models, autopilot, guards, notify, memory and tracker, auto-clear,
other), then a **setting**, then a **value from a list**. Each value shows the
current effective value, the layer that decided it, and the recommendation
first; the owner never has to type one.

- **Data-driven.** The rows are `crew_config.py`'s own key lists
  (`default_global_config()` for the machine layer, `default_config()` for the
  repo), so a key added to crew appears with no menu edit, and a committed test
  runs every offered value through the writer. The machine layer also lists
  `platform.*` and `schema` read-only, and an absent or unparseable
  `.crew/config.json` makes every repo row read-only with the writer's own
  refusal as the reason.
- **Offered means accepted.** Every candidate value is probed through the
  layer's own planner on the file Save would produce, the pending set
  included (`spec --pending`). A row no value can pass — a bad value already
  in the file, such as an unknown `qa.provider` — is read-only with the
  planner's reason, which names the key to fix first.
- **Selection only, Save once per layer.** Picks collect in a pending set that
  spans areas and both layers. Save validates **both** layers before writing
  either, shows the dry-run diff with `!` widening lines and "held down by the
  machine-global layer" lines, then writes each changed layer once. A write
  that fails or is refused after validation (the file changed underneath)
  reports which layer landed and which did not. The dry run prints each
  changed layer's `digest:`, and the machine digest whenever anything
  changes, since a repo value's widening marks are judged against the
  machine file (as this Save leaves it); `absent` names a file that does not
  exist. `--apply --expect-machine/--expect-repo` checks both before either
  write and binds each writer to them, the repo write to the machine digest
  too, so a file another session changed or created since the dry run is
  refused, never merged over. Discard writes nothing.
- **One validated repo writer.** `crew_config.py --set PATH=JSON --repo
  [--apply]` (`plan_repo_write` / `write_repo_config`) merges, refuses unknown
  keys, takes a whole-block value leaf by leaf (as the machine writer does),
  checks enum values, validates providers, writes
  atomically and keeps the file's line ending and BOM. It refuses `platform.*`
  (platform-sync owns it), `schema`, and `context.autoClear.onlyRepos` /
  `.onlySessions` (read from the machine file only), and takes only a veto
  (`false`) or `null` for `context.autoClear.enabled` and `resume.auto` —
  exactly those, by identity, so `0` is refused.
- **Both writers judge per leaf, write per leaf, and judge the whole file.**
  Each update is expanded to its leaves, so a whole-block value such as
  `context={"autoClear": {"unsafeFocus": true}}` cannot carry a refused key
  past the machine writer, and each leaf is written on its own: the block's
  untouched siblings (unknown keys included) survive, and a widening is
  marked on the leaf that widens. A role-table value (`qa.roles`) is written
  one whole pin per role, the other pins kept. `null` is accepted only where
  the layer gives it a meaning: at the repo layer it inherits the machine
  value for a machine-settable key, or clears a veto; an open key is unset;
  an enum key at the machine layer refuses it. Then the merged file is
  checked, every known leaf: a bad enum value, a consent key in the machine
  file, or an armed veto-only key in the repo file already there refuses an
  unrelated write, naming the key to fix first. Nothing goes under a leaf
  and no object sits at one; `qa.roles` / `dev.roles` and their entries are
  objects or `null`, so `qa.roles=1` is refused rather than wiping every pin.
- **Both writers are compare-and-swap.** Read, merge and replace happen inside
  an `O_CREAT|O_EXCL` lock file beside the config (`config.json.lock`, 3 s
  wait, then a refusal naming the lock and its PID), so two sessions never
  merge against stale snapshots; `--set` prints `digest:` (`absent` for no
  file) and `--apply --expect <digest|absent>` refuses a file that changed,
  or appeared, since; `--set --repo` also prints `machine digest:` and takes
  `--expect-global`. A malformed machine file is refused rather than
  overwritten from `{}`. An OS error (a lock, the machine directory, the
  write) is a refusal with exit 2, never a traceback.
- **`crew_config_files.py` is the one file layer** under both writers, delete
  and restore: the lock, the strict read, the `restorable` predicate and the
  regular-file read delete and restore share, the digest, the atomic
  replace, and the no-clobber move: a rename that never replaces an existing
  destination, by the rename itself rather than a check before it.
- **`scope.*` is refused on purpose.** `scope.mode` and
  `scope.allowCliApproval` are the scope guard's trust root, and
  `.crew/config.json` is untracked, so the completion audit (which diffs
  tracked files) would never see a one-command write that disarmed it. They
  stay a hand edit by the owner or `/crew:init`, shown read-only in the menu.
- **Delete the repo config.** Two phases. The preview reads and holds the
  file's bytes and walks its own leaves: a `!` on anything that widens
  (`scope.mode` returning to `off` included), `-> (removed)` for a key crew
  does not know, a `stays` line for a ratcheted key the repo narrowed under a
  wider machine value (deleting does not widen it), and the `platform.*`
  keys platform-sync writes (`crew_platform.DERIVED_KEYS`) in a "re-detected
  by platform-sync" group, which promises no value: a key it finds none for on
  this machine is left unset. Any other `platform.*` key is `-> (removed)`.
  Then the `repo digest:` and
  `machine digest:` it was built from. A file a restore could not take back
  (unparsable, empty, `{}`, not an object, or not a regular file, such as a
  symlink) is refused: that is platform-sync's to heal, or the owner's to
  remove by hand. The delete requires the typed repo name (the checkout's
  `git rev-parse --show-toplevel` basename) and both preview digests
  (`--expect-repo`, `--expect-machine`), so it is the delete the preview
  showed; then, under the machine lock and then the repo config lock (crew's
  one nesting order), it reads the machine digest again (a machine write since
  the preview refuses, exit 2, nothing deleted),
  moves the file to `.crew/config.json.bak-<UTC timestamp>` in one rename —
  the backup is the original, never a copy — and compares the moved bytes
  with the held ones: a file that changed since the preview is moved straight
  back, never over a file saved in between, and nothing is deleted. A file
  another writer puts at `.crew/config.json` during the rename is never
  unlinked: it keeps a second name, `*.moving`, and the command exits 1
  naming the backup, the config and that name — nothing is lost. It prints the restore command three ways,
  `restore (sh):`, `restore (cmd):` and `restore (PowerShell):`
  (`crew_config_menu.py restore-repo --from <backup> --apply`); each form is
  executed by a test, and restore accepts exactly what delete does, exiting 1
  the same way when another writer interleaves with its move-aside. Until the next
  SessionStart there is no config, so `isCrew` is false and every hook that
  gates on it stands down; then platform-sync's heal recreates the built-in
  defaults. `.crew/crew.json`, `verify.json`, backups and ticket state are
  untouched.
- **Headless.** With no way to ask, `crew_config_menu.py spec --layer
  <layer>` prints the plan and a write needs the explicit
  `save --changes '<json>' --apply --expect-machine/--expect-repo <digest>` or
  `delete-repo --confirm <name> --apply --expect-repo <digest>
  --expect-machine <digest>`.

Both writers now refuse a value outside the key's own tier or provider list
(`pm.authority`, `pm.ticketGranularity`, `qa.provider`, `dev.provider` and every
ratcheted key), refuse `null` for one of those at the machine layer, and refuse
a `--set` value that is not JSON. Before T-0075 a global `--set
pm.authority=bogus` was written and then read as `report-only`.

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
| `environments.nonProd` | **repo-only** globs naming the terraform workspaces/environments that may run unattended (default `[]`) | `hooks/scripts/cloud_guard.py`, when `cloudGuard` is on |
| `environments.prodUnattended` | whether production may too — true only when **both** layers say `true` (default `false`) | `hooks/scripts/cloud_guard.py`, when `cloudGuard` is on |

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
argument is never a finding of the rule it names: `psql -c "SELECT 'DROP TABLE
x'"` passes. That is the difference from the command guard removed in 0.19.52,
which matched words anywhere. A quoted terraform word is the one exception,
below: it makes the line one crew could not tell.

| It recognises | Decided by |
|---|---|
| `terraform`/`tofu` `apply`, `destroy` (`-auto-approve`, `-chdir=` included) | `guards.terraformApply` |
| `terraform`/`tofu`/`terragrunt` `workspace delete` — a destroy, in every armed state; `workspace new`/`select -or-create` once `environments` is configured | `guards.terraformApply` |
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

**Environments and destroys (crew 1.0.42).** A terraform command is also
judged by its target environment and by whether it destroys, both read without
running terraform. Under `guards.terraformApply: ask`, an `apply` of a saved
plan that deletes nothing, and `workspace new` / `select -or-create`, aimed at
a workspace matching a repo-only `environments.nonProd` glob **runs
unattended** and is logged as `env:nonProd:<name>`. Production does too only
when `environments.prodUnattended` is `true` in **both** config layers, and it
says so on screen. An environment crew cannot identify — no signal, a
non-literal `TF_WORKSPACE=$WS`, signals that disagree, a `cd` in the command,
no `.terraform/environment` (which is not read as `default`) — is **unknown**,
and nothing allows unknown unattended. A saved plan is readable only through
its sidecar, written outside the hook:

```bash
terraform plan -out p.tfplan
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_tfplan.py" summarize p.tfplan
TF_WORKSPACE=staging terraform apply p.tfplan
```

Three separate commands: a saved-plan apply is trusted only when it is the
only command in its invocation, since anything beside it could rewrite the
plan after the hook hashed it. The sidecar records the workspace the plan is
bound to, read from the plan file, and any directory or environment change
the hook cannot read makes the environment unknown.

**Terraform lines are judged word by word, or not at all (crew 1.0.42).** A
command line that RUNS `terraform`, `terragrunt` or `tofu` — its command word,
after assignments and wrappers such as `env`, `sudo`, `timeout` or `xargs`,
read with quotes and escapes taken out, so `"terraform"`, `t'erraform'`,
`$'\x74erraform'` and `terr\aform` all count, or a command inside `bash -c`,
`eval`, `pwsh -c`, `$(...)` or backquotes — is judged only
when every word on it is a plain literal (`^[A-Za-z0-9_./:=@%+,-]+$`) joined by
`;`, `&&`, `||`, `|`, `&` or a plain `>`/`>>`/`<` redirection. Anything else on
such a line — a quote, `$`, a backquote, a backslash, a glob or brace, `<(`, a
heredoc or here-string, a comment, a control character — makes it **could not
tell**: asked about when someone is attending, **refused unattended** (and
under `block`), never allowed, logged as `could-not-tell`. The check reads the
raw text before the parser does, so no parser mistake can turn a shape it
misread into an allow. Unusual quoting on a terraform line is asked about, not
allowed; spell the line with plain words to have it judged. The rule is about
the command being run: mentioning terraform in a commit message, a search or a
file name (`git commit -m "fix terraform apply"`, `grep 'terraform apply' .`,
`vim terraform.tf`) is not gated. A command word crew cannot read (`$x`,
`$(...)`) is could not tell only on a line that names terraform, `destroy`,
`apply` or `workspace`, so `x=terraform; $x destroy` is refused and `$EDITOR
notes.md` is not. Where crew cannot split a line with certainty — a `case`
arm, a function definition, a script piped into `bash`, `ssh`, `source` — it
falls back to the older, wider rule: any word naming terraform.

**A terraform command crew cannot follow is could not tell even in plain
words.** An alias (`alias tf=terraform`, `hash -p`, PowerShell's `Set-Alias`
and `alias:` drive), a binary the same line copies or links to another name
and then runs by that name with `destroy`, `apply` or `workspace`, zsh's
`=terraform`, a script runner crew does not split (`flock`, `ssh`, `source`)
and PowerShell's `Start-Process terraform` are asked about and refused
unattended: the parser would not see terraform in them. Run terraform by its
own name to have it judged. Options before the subcommand are read the way
terraform and terragrunt read them, so `terragrunt --working-dir infra
destroy` is a destroy; an option crew does not know, followed by `apply` or
`destroy`, is read as that operation. Two things are not gated for their
quoting: a read-only subcommand (`plan`, `show`, `output`, `fmt`, `validate`,
`init`, `workspace list`, ...) spelled where it cannot be another one, so
`terraform plan -var 'environment=staging'` runs as before; and the arguments
of any program that is not terraform (`cp -r terraform "$BACKUP_DIR"`, `rg
terraform "$file"`). A PowerShell line follows the same command-word rule:
`&`, `.`, `terraform.exe`, a path and `Start-Process terraform` run terraform,
`git commit -m "fix terraform apply"` and `Select-String terraform *.md` do
not.

**The always-stops.** A destroy is never applied unattended, at any setting:
`destroy`, `apply -destroy`, `apply -replace`, `workspace delete`, a saved plan
that deletes, and any apply whose plan crew cannot read — including
`terraform apply -auto-approve` with no saved plan. **BREAKING in 1.0.42:**
under `terraformApply: allow` these now ask (and are denied unattended) where
they used to run; approve one command with the marker the refusal names.
`prodUnattended` does not stand down `promote-gate.sh`'s `requireHuman`.
Details: [CONFIG.md §16](CONFIG.md), `environments.*`.

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
calls. For the terraform name specifically: a name built at run time from
parts crew never sees whole (`$TF`, `$(printf te)$(printf rraform)`, a
PowerShell string concatenation) and a wildcard that keeps fewer than three
letters of it (`t*`) are not read as terraform. Tests: `tests/test_cloud_guard.py` (every case through python, bash and
pwsh), `tests/test_cloud_guard_environments.py` and `tests/test_crew_tfplan.py`
(the environment layer and the sidecar), and the `cloud-guard.sh` section of
`hooks/scripts/_test/run-tests.sh`.

#### What the guard does not catch

The guard is a tripwire for an agent's accidental or direct destructive
command, not a sandbox against deliberate evasion (owner decision,
2026-09-26). It catches `terraform`, `terragrunt` and `tofu` written directly:
bare or path-qualified, behind the listed wrappers (`env`, `sudo`, `doas`,
`nice`, `ionice`, `timeout`, `stdbuf`, `nohup`, `command`, `exec`, `time`,
`xargs`, `parallel`, `sem`, `watch`, `flock`, `chroot`, `nsenter`, `wsl`,
`pwsh -c`, `aws-vault exec`, `unbuffer`), inside `bash|sh|zsh -c` and `eval` strings, with global options before the
subcommand (`-chdir=`, terragrunt's `--working-dir`), and PowerShell's `&`,
`.`, `terraform.exe` and `Start-Process`. PowerShell strips the same listed
wrappers. An option a listed `xargs`, `parallel`, `sem`, `aws-vault` or
`unbuffer` does not know makes a line that names terraform could-not-tell:
crew cannot tell where the command starts. So does an `Invoke-Expression`
whose script is not a literal string. terragrunt's `apply-all`,
`destroy-all`, `stack run`, `graph` and `backend delete` are read as the
apply or destroy they run, and `terragrunt exec -- cmd` is unwrapped like any
listed wrapper. On a PowerShell line, every mention of terraform, tofu or
terragrunt must be one crew accounts for -- the command word of a command it
judged, a literal script given to `Invoke-Expression`, or, when nothing on the
line can run a value made at run time, a literal argument of a plainly named
command (`git commit -m "terraform destroy"`) or a string it only prints or
assigns -- or the line is could-not-tell (`return terraform destroy`,
`$t="terraform"; Start-Process $t destroy`,
`[Diagnostics.Process]::Start("terraform","destroy")`). A mention inside a
comment is dropped before counting; a name built at run time from parts is
still not read (above). It does not try to catch a program renamed or
started some other way. Each of these runs unjudged:

- a rename by alias, function, symlink or copy, unless the same line makes a
  plain copy or link and runs it by that name: `env ln -sf /usr/bin/terraform ./ls && PATH=.:/usr/bin ls destroy -auto-approve`,
  `X=1 cp /usr/bin/terraform ./ls && PATH=.:/usr/bin ls destroy -auto-approve`,
  `sudo ln -s /usr/bin/terraform /usr/local/bin/tf; tf destroy -auto-approve`
- `env -S` escape strings: `env -S 'terraform\_destroy\_-auto-approve'`
- BusyBox applets: `busybox env terraform destroy -auto-approve`,
  `busybox timeout 60 terraform destroy -auto-approve`
- git `!` aliases: `git -c alias.tf='!terraform' tf destroy -auto-approve`
- an interpreter (`python -c`, `node -e`, ...): `python3 -c 'import os; os.system("terraform destroy")'`
- a script file: `bash deploy.sh`
- a wrapper not in the list above: `strace -f terraform destroy`,
  `strace -f terraform $'\x64estroy' -auto-approve`, `strace =terraform destroy`,
  `systemd-run terraform destroy`
- a program that runs another it is handed: `git bisect run terraform destroy`,
  `git -C infra bisect run terraform destroy`,
  `git -C add bisect run terraform destroy`, `rg --pre terraform destroy .`
- a container's entrypoint: `docker run --rm hashicorp/terraform:1.9 destroy -auto-approve`

No command-line guard can close these: unattended work has to run
interpreters, scripts and build tools, and any of them can start terraform
under another name, so a guard that refused them would refuse the work
itself. The real boundary is the credentials an unattended run holds — scope
them so the run cannot destroy what it must not. That is
`crew_unattended.py launch`, next.

#### Unattended runs: sealed cloud credentials

`hooks/scripts/crew_unattended.py` (T-0044) starts an unattended Claude
session holding short-lived credentials for ONE identity the machine owner
named, with the machine's credential stores unreadable to it, or refuses and
starts nothing. It holds whatever the command line says, because it decides
what the process can authenticate as and what it can read.

```bash
python3 plugin/crew/hooks/scripts/crew_unattended.py check  --root . [--environment dev] [--json]
python3 plugin/crew/hooks/scripts/crew_unattended.py launch --root . [--environment dev] -- claude [args...]
```

The owner (or the owner's scheduler) runs it. Crew never starts an unattended
session by itself, and a hook cannot change the environment of a session that
is already running, so `/crew:autopilot` touching the cloud unattended is
started this way. The identity comes from `unattendedCloud` in the machine
file `~/.claude/crew/config.json` only (CONFIG.md, "`unattendedCloud`"); a
repo copy is ignored and reported. Seven checks run in order, and the first that
is not `ready` refuses with its reason printed verbatim. `unknown` ("could not
tell") refuses exactly like `refuse` and keeps its own label:

1. **platform** -- native Windows refuses: `sandbox probe not implemented for native Windows`.
2. **config** -- no identity or profile named, a provider other than `aws`, or
   `--environment NAME` without both a machine `nonProd` entry and the repo's
   `environments.nonProd` classifying `NAME` as nonProd. There is no
   production entry.
3. **settings** -- the launch passes `--setting-sources user`, so the repo's
   `.claude/settings.json` and `.claude/settings.local.json` do not load
   (their `excludedCommands`, `allowRead`, hooks and `env` never reach the
   sealed session). It fails closed anyway: a repo file with any `sandbox`
   key or a `Read` allow rule refuses. Your own `~/.claude/settings.json`
   (or `$CLAUDE_CONFIG_DIR/settings.json`) does load and its lists merge with
   the sealed ones, so `sandbox.excludedCommands` (those commands run
   unsandboxed), a `sandbox.filesystem.allowRead` entry at or under a store or
   holding a glob, or `sandbox.filesystem.disabled: true` refuses. A settings
   file that exists but is not a JSON object is `unknown`. In a linked git
   worktree Claude Code reads `.claude/settings.local.json` from the MAIN
   checkout's root, so that file is checked too; a `.git` file whose main
   checkout cannot be found is `unknown`.
4. **version** -- `<claude> --version`, the same file the probe and the
   launch use, must print a version (`2.1.289 (Claude Code)`) at or above
   2.1.246: below it `--setting-sources` does not keep an excluded source's
   `sandbox.filesystem` entries, `Edit` rules and `Read` denies out of the
   sandbox. An older version, output that does not parse (a pre-release tag
   included), a non-zero exit or a timeout is `unknown`.
5. **export** -- `aws configure export-credentials --format process`, read
   into memory only. No `SessionToken` or `Expiration` (static keys), under 15
   minutes of lifetime, a non-zero exit, a timeout or non-JSON output refuses.
6. **identity** -- `aws sts get-caller-identity` in the sealed environment
   must print an ARN that starts with the named prefix (an assumed role ending
   in `/`); a `:user/` ARN or any other role refuses.
7. **sandbox** -- one headless `claude -p` call, made by the same `claude`
   file the launch will exec, from `--root`, with the same leading flags,
   runs a probe that tries `head -c1`/`ls` and `python3 open()` on every store
   root that exists plus a bounded sample of files inside each (two per
   directory, twelve per store: the sandbox denies a path and all under it, so
   the root is the test and the sample catches a deny that stopped at the
   directory). The output carries an index per store, the nonce first and an
   end marker last, so it stays far under the Bash tool's output limit. The
   verdict is read from the stream-json tool results, never the model's
   prose: any `OPEN` refuses; a missing nonce, a missing end marker (output
   cut short), a store not reported, an `ERR` or no tool call is `unknown`.

The launched session is exec'd as
`<claude> --settings <sealed> --setting-sources user [your args]`, in `--root`
(whatever directory the launcher was started from), and gets: no inherited
cloud or forge credential variable (`AWS_*`, `AZURE_*`, `ARM_*`, `CLOUDSDK_*`,
`GOOGLE_*`, `TF_TOKEN_*`, `KUBECONFIG`, `GITHUB_TOKEN`, `GH_TOKEN`,
`GH_ENTERPRISE_TOKEN`, `GITHUB_ENTERPRISE_TOKEN`, `DOCKER_CONFIG`,
`DOCKER_AUTH_CONFIG`, `TF_CLI_CONFIG_FILE`, `TFE_TOKEN`, `GITLAB_TOKEN`, and git's and
ssh's credential pointers `GIT_ASKPASS`, `SSH_ASKPASS`, `SSH_AUTH_SOCK`,
`GIT_CONFIG_PARAMETERS`, `GIT_CONFIG_COUNT`, `GIT_CONFIG_KEY_*`/`GIT_CONFIG_VALUE_*`,
`GIT_CONFIG_GLOBAL`, `GIT_CONFIG_SYSTEM`, `GIT_SSH`, `GIT_SSH_COMMAND`, `TERRAFORM_CONFIG`,
`GH_CONFIG_DIR`, `XDG_CONFIG_HOME`);
git's `credential.helper` reset to empty through `GIT_CONFIG_COUNT` (so no helper your
`~/.gitconfig` names answers git); the exported
temporary credentials; `AWS_EC2_METADATA_DISABLED=true`; `CREW_UNATTENDED=1`
(so T-0005's guard judges it unattended); `AWS_CONFIG_FILE` at a region-only
file and `AWS_SHARED_CREDENTIALS_FILE` at a path that does not exist, both in a
mode-0700 `crew-sealed-<pid>-*` temp directory that holds no credential; and
`--settings` with `sandbox.enabled`, `failIfUnavailable: true`,
`allowUnsandboxedCommands: false` (which also makes the sandbox admin-required,
so Claude Code itself ignores a repo's loosening settings), filesystem
isolation pinned on, and every store -- `~/.aws` whole, `~/.azure`,
`~/.terraform.d/credentials.tfrc.json`, `~/.config/gcloud`, `~/.kube`,
`~/.config/gh`, `~/.docker/config.json`, `~/.claude/crew/config.json`, `~/.ssh`,
`~/.git-credentials`, `~/.config/git/credentials`, `~/.terraformrc`, from
both `$HOME` and the account's real home -- in `sandbox.filesystem.denyRead`
and `denyWrite` and as `Read(...)` and `Edit(...)` denies. The sealed
directory and the user settings file are write-denied too, so the session
cannot rewrite its identity or its settings mid-run. A command other than
`claude`, one that is not an executable file or on `PATH`, or one passing its
own `--settings`/`--setting-sources`, refuses. It prints the checks and the
ARN, never a credential. `exec` leaves no process to clean up, so the next
`check` or `launch` removes any `crew-sealed-<pid>-*` directory you own whose
process has exited, and leaves one whose process is alive.

Because the session cannot read `~/.config/gh`, `~/.docker/config.json` or
`~/.kube` and holds no `GH_TOKEN`, `gh`, registry pushes and `kubectl` have no
credentials in an unattended run. That is deliberate: the run holds the one
cloud identity it was handed and nothing else. Claude Code itself configured
to run on Bedrock or Vertex through those variables is not supported by the
launcher, for the same reason.

**Host requirement.** Claude Code's sandbox has to run commands on the host.
Where it starts but cannot run anything -- measured on a host with
`kernel.apparmor_restrict_unprivileged_userns = 1`, every Bash call failing with
`apply-seccomp: write /proc/self/setgroups (nested userns is capability-restricted; caller must provide CAP_SYS_ADMIN): Permission denied`
-- the probe finds no nonce and every launch refuses with `sandbox: unavailable`
and that line. Making it usable (or running unattended work as a separate OS
user or container) is the host owner's call.

**Accepted risks.** Credentials that expire mid-run fail closed. Git's credential helpers
are reset for the session, but a key file `~/.gitconfig` names elsewhere
(`core.sshCommand -i <path>`) is outside the denies. A failing `aws` command's stderr is never printed (it may hold a
secret): the check names the command and its exit code, and you run it by hand. Claude Code
applies `Read(...)` denies to Grep and Glob "best-effort" (its own words); a
gap there is unmeasured. `/proc/<pid>/environ` of other root processes is
outside the session. The probe nonce is in the prompt, so a model that chose
to fake the probe's output could; the probe guards against an unusable or
leaky sandbox, not against an adversarial probe session. The probe tries
`head`, `ls` and `python3` only: a store that one of those can read is
refused, and the settings check -- not the probe -- is what keeps an excluded
or unsandboxed command out. Managed (organisation) settings always load and
are not inspected; an `excludedCommands` there is the administrator's. Hooks
and MCP servers run outside the sandbox: the user settings' ones are yours and
load; a repo's `.claude/settings.json` hooks do not load, and a repo's
`.mcp.json` servers are not inspected by the launcher. `--setting-sources`
excluding project settings from the sandbox build needs Claude Code 2.1.246 or
later, which the version check enforces; the admin-required behaviour needs
2.1.285 or later and is not checked, since the settings check already refuses
what it would ignore. The stale-directory sweep asks `kill(pid, 0)` in its own
PID namespace: a process in another namespace sharing the same `/tmp` is
invisible to it, so a sealed directory still in use there can be removed (its
settings file is already loaded; the session keeps running). Azure and TFC/HCP
are a provider seam only: any key other than `aws` refuses as not implemented.

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
bypasses rather than features. The migrate report's upgrade lines say so out loud,
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

Without Codex, `/crew:review` walks `qa.order` — `["codex", "kimi", "copilot", "claude"]` by default — and takes the first provider whose probe answers — a real call for Codex (`review_run.py --probe`), not just `command -v` — announcing every one it skipped and why.

When that Codex call fails on a usage limit, rate limit or quota (Codex's own messages, cited in `hooks/scripts/review_limit.py`), the round runs on the `reviewer` fallback instead, pinned or not, announced as `same-family (codex limit)` with the error quoted. A limit hit in the middle of a round is recorded beside the review ledger, so the next round goes to Claude without another call; the one after probes Codex again (T-0088).

Kimi Code (`kimi`) is the second rung of the default order since crew 1.0.85. Its family is `kimi` whatever it is pinned to, so it needs no pin to be independent of a Claude author, and every `qa.roles.<r>` and `dev.roles.<r>` slot accepts a Kimi pin. `/crew:review` does not launch it yet: the launch (the probe before the round is reserved, and a working-tree fingerprint, since `kimi -p` cannot be made read-only by a flag) is crew's review harness and lands separately as L-0527. Until then the launch gate keeps it out of the walk: `crew_config.review_launchable()` is `review_run.LAUNCHED` plus the in-session `claude`, and a `qa.order` provider outside it is reported `no - /crew:review cannot launch kimi yet` and skipped; adding `kimi` to `review_run.LAUNCHED` is what makes it eligible. `kimi_probe.py` answers now whether Kimi could review: `ok`, `not-installed`, `not-authenticated`, `rate-limited` or `unknown`, and only `ok` is launchable; `providers.sh --probe-kimi` runs it. See `skills/crew-providers/SKILL.md`, "Kimi Code".

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
"obsidian"` (`tracker.kind` in `crew.json`) plus a vault path that exists and
holds `.obsidian/`. The board is a markdown file the
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

**One interface, called by the lifecycle itself.** `hooks/scripts/crew_tracker.py`
is the only code that writes a tracker, and the lifecycle commands call it at
their status transitions — no sync command to remember:

| Command | Call | Lane |
|---|---|---|
| `/crew:brainstorm` | `create` (INDEX row, card, ticket note); on approval `move --to ready` | Backlog |
| `/crew:spec`, `/crew:plan` | `move --to spec`, `move --to planned` | Ready |
| `/crew:implement` step 1 | `move --to in-progress` | In Progress |
| `/crew:implement` step 6, before `/crew:review` | `move --to review` | Review |
| `/crew:done` | `move --to done` | Done |

`/crew:fix` makes the same calls, compressed. `resolve` reads the kind from
1.0's `.crew/crew.json` (`tracker.kind`) and 0.20's `.crew/config.json`
(`tracker`) alike; when both state one and they differ it says `could not tell`
and every write refuses — it never picks one. The same holds for the vault and
`boardDir` each file *yields*, fallbacks included: crew.json falling back to
`memory.vaultPath` while config.json names another vault is `could not tell`,
not a quiet write to the memory vault. Jira and ServiceDesk Plus are pushed at
the boundaries only: `move --to in-progress` and `--to done` answer `delegated`
with `/crew:jira-sync <KEY> --push --to <status>` (or `/crew:sdp-sync`), which
the model runs because a script cannot call an MCP tool; every other move
prints `nothing to push`.

**Forward only, unless you say otherwise.** A move backwards by the lifecycle
order (`direction`, `ready`, `spec`, `planned`, `in-progress`, `review`,
`done`) exits 1 unless `--reopen` is passed, and so does a move from a status
crew does not know (`merged`, say), because whether it goes backwards cannot be
told. `/crew:implement` passes `--reopen` on a successor plan.

**A tracker write never undoes a transition.** A write that fails prints
`could not update: <reason>` and exits 1; the command tells you "tracker not
updated" and the phase stands.

**Confined to the vault, atomic, and loud.** Before anything is written —
`INDEX.md` included — the vault must exist and hold `.obsidian/`, `boardDir`
must be relative with no `..`, `board` a bare file name, the board and note must
not resolve out of the vault through a symlink, and a board or note inside the
worktree must be ignored by git (otherwise it would enter the review bundle) —
checked per file, so a vault that *contains* the repo is caught too. Any of
those fails, the board lacks its frontmatter key, a configured lane is
missing or doubled, or the done lane lacks exactly one `**Complete**`: exit 1,
nothing written anywhere. Board writes are an
exclusively created temp file (a link planted at its name is never followed)
plus `os.replace`, keeping the board's mode and owner, re-reading the board
first and recomputing if Obsidian saved it meanwhile. Every vault write reaches
its directory from the vault root one component at a time with
`O_DIRECTORY|O_NOFOLLOW` and writes relative to that directory, so a directory
swapped for a link after the checks is refused rather than written through.
Every directory from the vault down is also matched against the one the checks
found (T-0081): by device and inode on POSIX, by volume and file id on Windows,
so a real directory renamed away and replaced by another, even a byte-identical
copy, is refused too. An identity that cannot be told (none recorded, or an
inode or file id of 0) refuses as "could not tell", never "the same".
That fd follows its directory if it is renamed out of the vault, so the walk is
repeated and matched by device and inode before the temp is written, before the
replace and after it; a note that landed in a directory that left is removed
through the fd. Windows has no such calls, so it holds the directories instead (since 1.0.49, T-0077): it opens a handle on the vault and on every directory down to the target, each denying `FILE_SHARE_DELETE`, and keeps them open for the length of the write, so the OS refuses to rename any of them meanwhile. A handle that is a reparse point, not a directory, the wrong vault, or has no file id is refused (no file id is "could not tell", never "the same"), and the path is still re-checked against the held directory's id at the same three points.
A platform with neither mechanism refuses the write. On POSIX a move inside the last window
remains a residual race; on Windows the held handles close it.

**Whose card.** The ticket note is written once and never rewritten, and
records `repo-id:` — the origin URL with `.git` dropped and only its scheme and
host (with the port) case-folded, or the git common dir's real path when there is no origin or the origin is a relative path
(`../origin/app.git` from `a/app` and `b/app` is one string naming two
repositories). The ssh username and the path keep their case (since T-0071):
`ssh://Alice@host/~/repo.git` and `ssh://alice@host/~/repo.git`, or
`https://host/Team/Repo` and `https://host/team/repo`, are two owners. A note an
older crew wrote for an origin with capitals in its user or path holds the
all-lowercase id and is refused like any foreign note; the refusal says so and
names the fix, `repo-id: <this repo's id>`, which you edit in by hand — crew
never accepts the old id on its own, because it is exactly the ambiguous one.
An ssh origin keeps its username and drops only a password:
`alice@host:repo.git` and `bob@host:repo.git` are two users' repositories. Every
other scheme drops the whole userinfo, because `https://<token>@host/...` puts a
token where a username goes and the id is written into a note a human reads. A
local origin is its real path, and a `file://` one is percent-decoded first, as
git decodes it: `file:///srv/a%20b.git` is `/srv/a b.git`. A `file://`
authority is not path text: on POSIX any authority is dropped, as git drops it,
so `file:///srv/app.git`, `file://localhost/srv/app.git` and `/srv/app.git` are
one owner; on Windows an empty or `localhost` authority is dropped with the `/`
before a drive letter (`file:///C:/repos/app.git` is `C:/repos/app.git`), and any
other authority keeps the common-dir identity (git for Windows not measured).
A quote around the note's `repo-id:` value is stripped only as a matched pair
(`"<id>"` or `'<id>'`); a lone quote is part of the id. An id that itself begins
and ends with the same quote character loses that pair when read back.
Never the directory's name: `a/app` and `b/app` share that. With `boardDir` unset every
repo shares one board, so a note naming another repo refuses `create`, `move`
and `read`. A card whose owner cannot be told — no note, a note with no
`repo-id:` — refuses `create` and `move` (`read` says so on its line), naming
the fix: put `repo-id: <this repo's>` in the note. There is no exception: ids
start over in every repo and titles repeat, so a card's text matching this
repo's INDEX row proves nothing. `create` refuses an id INDEX already holds —
read before the vault, so a vault failure never hides it — whatever its title,
and an id the board holds for another or an unknown repo. Its claim on a new id
is the note's exclusive creation, before the INDEX row and the card: a note
another repo creates after the owner check makes the claim fail, and nothing
follows it. Each refusal begins `id taken`, and `/crew:brainstorm` and
`/crew:fix` then take the next free id; any other failed `create` stops them
before anything is written under that id. A `move` whose INDEX
half refuses — another session moved the ticket on meanwhile — leaves the
board alone, and a card already in its lane is repaired in place (checked in
Done, below `**Complete**`; unchecked elsewhere; a card with no checkbox gets one,
and a marker glued to its text, `- [ ]T-0042`, is given its space). The board
half places the card where INDEX has the ticket when the board is written, not
where the call meant to put it, and reads INDEX again after the write, so two
overlapping moves leave the board and INDEX agreeing (since T-0071; the line
says `(INDEX moved on to <status>)`). INDEX unreadable or holding an unknown
status at that point leaves the board alone: `could not tell where INDEX has`.

**There is no `.work/cache/` mirror.** The ticket's content lives in
`.work/tickets/<id>/` for every mode; the board carries status only. The key
keeps the `T-####` shape, so nothing else in crew needed a new format.

**Unlike Jira and ServiceDesk Plus, this mode also keeps `.work/INDEX.md`.**
The session brief finds the open ticket by reading that file, and a key shaped
`SDP-40219` was never going to be in it — `T-0042` can be. So the board is the
human's view of the work and `INDEX.md` is the session's; the same `move`
writes both, and each half reports its own result.

**Five lanes, named by `obsidian.columns`.**

| Lane | Means |
|---|---|
| Backlog | Deferred or untriaged. Where a non-blocking finding is parked. |
| Ready | Scoped by `/crew:spec` and pickup-able. |
| In Progress | `/crew:implement` has it. |
| Review | Implementation done, `/crew:review` outstanding. |
| Done | Complete and verified. Carries the `**Complete**` marker. |

Dragging a card is yours to do; crew does not read it back as status.
`/crew:obsidian-sync $1` shows the board lane beside the INDEX status and says
when they disagree; `--push` moves the card to the lane the INDEX status names
and reports the lane it came from. Both sides are local markdown and both look
equally authoritative — which makes the divergence hazard *worse* than Jira's,
not absent — so a silent fallback to file tickets is refused the same way
`/crew:jira-sync` refuses it.

**The board file has three load-bearing parts** and a naive rewrite destroys all
three, after which the file silently opens as plain text instead of a board: the
`kanban-plugin: board` frontmatter, the trailing `%% kanban:settings` block, and
the `**Complete**` marker in the done lane. An archive, when one exists, sits
below a `***` break under `## Archive` and is nobody's business but Obsidian's.
So `crew_tracker.py` cuts one card and inserts it under the target heading;
every other byte, the archive included, is the byte it read.

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

**Native memories as pointers.** A Claude Code native memory file may carry one line in place of its body, `vault: <name> | note: <vault-relative path>`, naming the vault the way this host's `~/.claude/obsidian/config.json` names it (only the name `memory` falls back: to `memory.vaultPath`, then, when that file has no `vaults` block, to its legacy top-level `vaultPath`). `crew_memory.py resolve --file <memory file>` prints the note's path on this host; `crew_memory.py check --memory-dir <dir>` lists every memory file's state. Each failure is a named state with exit 1 - `malformed`, `no-vault-config`, `vault-unknown`, `vault-unavailable`, `note-missing`, `outside-vault`, `unreadable` - and an unavailable vault is never swapped for another. A config counts as missing only when it is not there; one that does not read, parse or match its expected shape is `no-vault-config`, naming the field. A bad Obsidian config stops every name; a bad crew config stops `memory`, the one name it can answer for, and any name when there is no Obsidian config to say which failure applies. A `vault:` first line is a pointer attempt only when `note:` or `|` is on it, or the next line starts with `|` or `note:`, or it is a bare vault name alone; otherwise it is prose. The `crew-memory` skill carries the state table.

**Saving a memory as a pointer.** `crew_memory.py save --file <memory file> --tag <tag> [--tag ...] [--title <t>] [--note <path>] [--type <type>] [--project <p>] [--apply]` writes the memory into the one writable vault and only then turns the memory into a pointer. Without `--apply` it prints the plan (vault, note, `create` / `append` / `unchanged`, the pointer line), writes nothing and exits 1. The vault is the single `role: primary` entry of `~/.claude/obsidian/config.json` (without roles, `default: true`, else the first; with no `vaults` block, `memory` as `resolve` finds it); it must hold `.obsidian/`, and a `recall` or `ignore` vault, or a substitute for a primary that is not there, is never written. The note defaults to `memories/<project>/<title>.md` (title from the memory's `name:` line, project from the repository folder), `type: concept`, the six-key frontmatter plus `project` and `memory_id` (the memory file's stem). A note already holding the same `memory_id` gains a dated `## Update` passage; any other existing note is a `collision`. The note is written through a temp file (a new one by hard link, or an exclusive create where hard links are refused; never renamed over a file; an existing note keeps every byte, only its `updated:` value changes and the passage is appended), its folder fsynced, read back and its pointer resolved; only then is the memory's body replaced (frontmatter bytes kept) through a temp file and `os.replace`. Two `save` runs by the same user on the same machine exclude each other with kernel locks (`flock`, or `msvcrt.locking` on Windows), the note's then the memory's, on files named by the sha256 of each file's case-folded real path and of its `dev:ino` (so a symlinked folder, `..`, a case variant and a hard link meet one lock) in `$XDG_CACHE_HOME` or `~/.cache` (`%LOCALAPPDATA%` on Windows) under `crew/memory-locks`, never in the vault (with no absolute cache folder, `lock failed`); the OS drops a lock when its save exits or is killed, so a second run's `another save is running now` means one is, and a lock that cannot be taken at all is `lock failed`. The lock does not cover a save on another machine syncing the vault, nor an edit by Claude Code or Obsidian, which never take it. The memory and an existing note are re-read and compared right before each rename, so an edit made earlier in the save is kept and refused as `changed during save`; an edit by another program in the instant between that last compare and the rename is not detected, because a rename cannot compare-and-swap. Every refusal prints `kept-full-text: <reason>` and leaves the memory byte-identical: `no vault configured` (exit 0), and with exit 1 `vault unavailable`, `no primary`, `several primaries`, `not a vault`, `config unreadable`, `collision`, `ascii-required` (`guard.asciiOnly`), `outside-vault`, `bad-note-path` (including a `.`-prefixed segment), `the existing note is not UTF-8`, `MEMORY.md is the index` (a case variant such as `memory.md` only where the file system folds case and it is the same file), `the memory file is a symlink`, `the memory has no body to save`, `another save is running now`, `lock failed`, `note write failed`, `the note changed during save`, `note not readable after write`, `the memory file changed during save`, `the memory file cannot be read again`, `pointer write failed`. A memory that is already a resolving pointer, including one another save just wrote, is `already-pointer` (exit 0). `MEMORY.md` is never edited.

**Converting existing memories, and back.** `crew_memory.py migrate --memory-dir <dir> --tag <tag> [--tag ...] [--only <file name> ...] [--type <type>] [--project <p>] [--note-dir <vault folder>] [--apply]` runs `save` over every memory file in one folder (never `MEMORY.md`), in name order. Without `--apply` it writes nothing and prints one row per file: `convert` or `append` with the note it would write (`<note-dir or memories/<project>>/<name>.md`; the project is `--project`, else `<slug>` when the folder is `~/.claude/projects/<slug>/memory`, else the repository folder's name; a `/` in `--project` is a usage error), `skip: already a pointer`, `skip: <state>` for a pointer that does not resolve or is `malformed`, or `refuse: <reason>` for anything `save` refuses, plus `title is not a portable file name` (`< > : " / \ | ? *`, a control character, a trailing dot or space, or a device name such as `CON` or `COM1`, with any extension) `duplicate note path` (two files that would write one note, compared case-folded), `note belongs to another project (<project>/<memory_id>)` (the note exists but its frontmatter `project:` is not this run's, so a second project's folder never appends to the first's note) and `not a file`; then a count per action and `MEMORY.md was not edited`. The dry run exits 1 while any row is `convert`, `append` or `refuse`. With `--apply` each `convert` and `append` row goes through `save`'s apply, one file at a time; a row whose save fails is `failed (kept-full-text: <reason>)` and the loop goes on, so one failure never stops or undoes the others; exit 0 only when nothing was refused or failed. With no writable vault it prints `nothing to migrate: <reason>` and exits 0 for `no vault configured`, 1 otherwise. No state file is written: the preview is recomputed from disk, so a second `--apply` is a no-op. `crew_memory.py restore --file <memory file> [--apply]` is the way back for one pointer that resolves: the note's text after its frontmatter, LF-only, becomes the body, after the pointer file's frontmatter bytes and a blank line; the dry run prints the first line and the line count. It writes through a temp file and `os.replace` under `save`'s lock, then confirms the file reads as `full-text`; a note whose text is empty or would read as a pointer is refused. Any other state is printed with exit 1 and nothing written; `full-text` is nothing to do (exit 0). The note is never edited or deleted. Neither runs automatically: no hook, `/crew:init` or `/crew:upgrade` calls them, and `/crew:migrate` (the 0.20-to-1.0 config move) is a different command.

---

## 15. Optional: Teams and Telegram notifications

**Outbound only.** crew sends messages; it never reads a channel and never takes
instructions from one.

Set it once in the machine-global `~/.claude/crew/config.json`; a repo's
`.crew/config.json` overrides any key it sets, a repo `null` inherits, and a repo
`"provider": "none"` opts out on purpose.

```json
"notify": {
  "provider": "telegram",
  "tokenEnv": "CREW_TELEGRAM_TOKEN",
  "chatId": "-1009876543210",
  "events": ["blocker", "deploy", "question"],
  "realertHours": 6
}
```

Three events send, each led by a subject that says what happened (T-0051, T-0060):

- `deploy` — every `/crew:promote` result: `Promotion passed` (silent) or
  `Deploy FAILED` (loud); a result naming neither is `Promotion outcome
  unknown` (loud), never a pass.
- `question` — Claude Code stopped and is waiting on you: `Question` (an
  AskUserQuestion or an elicitation) or `Needs permission` (any other tool),
  from the `Notification` hook's `notification_type` (`notify.questionTypes`
  overrides the built-in five). An idle "finished" prompt never pings. The line
  says what it is waiting on — the pending question, or the tool — read from
  the session transcript, capped and redacted. One ping per waiting episode:
  no repeat until your next typed message in that session. Approving a
  permission prompt does not reset it, so a second prompt in the same turn is
  silent.

- `blocker` — work stopped and only you can move it (T-0060), loud:
  `Approval waiting` (autopilot stopped at `approve`), `Review out of rounds`
  (autopilot stopped at `accept-review`/`replan` with the budget spent and a
  BLOCK open), `Lane stalled` / `Lane state unknown` (autopilot's in-flight
  check read another runner's marker as `stale`, or could not tell; needs
  T-0049's markers and takes its staleness from their TTL; `live` and
  `elsewhere` send nothing), and `Stop gate refused` (the same ticket refused
  at Stop twice in a row, recorded by `crew_notify.py stop`; the gates' calls
  land in a harness-only change). Autopilot's report runs `crew_notify.py
  run-stop` at every stop, and that code decides which stop pings.

The per-phase, per-review and per-ticket pings are retired; an old config's
`gate` reads as `deploy`, `waiting` as `question`, and `phase`/`review`/`done` as
`blocker`, each with a notice; a send under those three old names sends nothing. The same message is sent once per `realertHours`, and both that
record and the episode record advance only on a confirmed send.
`python3 hooks/scripts/crew_notify.py config --root .` prints what this repo
runs with, and why.

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

Export `CREW_TELEGRAM_TOKEN` and put the chat id in `notify.chatId`. `tokenEnv`
and `urlEnv` count only in the global file (a repo's is ignored), so a cloned repo
cannot pick the request URL; a redirect is a failed send, never followed. If the
notify skill is already set up on this machine, its `telegram.bot_token_env` and
`chat_id` fill a null `tokenEnv` / `chatId` (read-only; its example chat id
`-1001234567890` counts as unset).

### Payload discipline

One line, the reason cut at 280 characters and the transcript excerpt at 200,
every line redacted first. No diffs, no findings text, no ticket
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
| After `/clear`, `/compact`, resume | `SessionStart` | Prints the handoff — stdout is injected as context, byte-exact LF on every OS |

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

With `context.autoClear.wrapUp` armed (machine file only, and only where
auto-clear is armed), the warning becomes the one wrap-up procedure — finish
the step, commit only if its `Test:` passes, run `/crew:handoff --wrap-up`,
end the turn — and auto-clear waits until the handoff's `head:` is HEAD, its
`branch:` matches, no tracked file is modified and its `resume:` line parses
(or is `resume: none`). A refusal is shown to you and fed back to the session
once. Crew checks the commit, not the test (CONFIG.md §14).

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
| `tmux` | `$TMUX_PANE`, and only when that pane's pid is this session's own process or an ancestor of it | **Exact.** No focus involved. Use this if you can. |
| `xdotool` | the one window owned by the nearest ancestor of this session's own process, hosting no other terminal; `windowTitle` narrows or, failing that, is a fallback that must match exactly one window (and refuses while another session is live) | Activates that window id, re-checks it is active, then types. |
| `notify` | no window — types nothing | Prints a `systemMessage` saying the handoff is written and verified and it is safe to run the configured command yourself. Never claims anything was cleared or compacted, because nothing was. `auto` resolves here on native Windows with no tmux pane. |
| `sendkeys` | the same rule, from this session's own process, through `EnumWindows` (renamed from the pre-1.0 `"windows"` literal); at send time that exact window handle must have foreground | **Opt-in only — `auto` never resolves here.** Windows Terminal hosts every tab in one window and nothing outside UI Automation can tell which tab is active, so a Windows-Terminal-owned target declines and falls back to `notify`, logged to `.crew/.autoclear.log`. Request it by name after reading what it does. |
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
5. This session is bound to its **own** process (T-0016): the nearest ancestor
   named by a Claude Code session record
   (`${CLAUDE_CONFIG_DIR:-~/.claude}/sessions/<pid>.json`) with this session's
   id and that process's start time. A headless session — `claude -p`
   (entrypoint `sdk-cli`) or one with no controlling terminal — types
   nothing whatever the method: it gets one `notify-headless` message naming
   the handoff and its `resume:` line and saying the process that started it
   must start a new one. A session that cannot be identified, or whose
   entrypoint was never measured, types nothing either (`auto` falls back to
   plain `notify`). [CONFIG.md §14](CONFIG.md) has every rule.
6. The target window is identified uniquely (the table above), walking up
   from that process: through another Claude Code session, past a chain that
   could not be read, or into a window that hosts another terminal, it
   refuses. Zero or several candidates is a refusal, never a guess — this
   step does not apply to `notify`, which identifies no window because it
   types nothing.
7. Nothing has claimed this session's one attempt (`.crew/.autoclear-sent-<session_id>`).

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

#### Auto-resume (`resume.auto`, off by default)

`/crew:handoff` writes one machine-readable line into the note's header,
`resume: /crew:done T-0001` (or `resume: none`), and with `resume.auto: true`
in `~/.claude/crew/config.json` the context hook works out, on the
`SessionStart` after `/clear` or a manual `/compact`, whether that command may
be resumed. Only the machine file can switch it on; a `false` in
`.crew/crew.json` or `.crew/config.json` vetoes it, and a repo `true` does
nothing (`CONFIG.md` §14a). Never on `startup`.

**Nothing starts on its own yet.** Claude Code 2.1.282 drops a SessionStart
`initialUserMessage` in an interactive session (spike, 2026-09-25), so crew
never sends one. When the checks pass, the injected handoff carries
`Auto-resume: ready to run /crew:done T-0001.` and says it did not start from
the hook — press Enter or type it, unless crew types it (below). When
they do not, it carries `Auto-resume did not start: <reason>.` The reasons:
compact was not a manual /compact; no handoff note, or the handoff was
archived as stale (or is stale and could not be archived); the handoff is the
automatic PreCompact skeleton (it names no next action); no resume line,
`resume: none`, or a line the grammar refuses (two lines, trailing text, an
unknown or excluded command such as `/crew:approve`); the `branch:` or
`head:` line does not match the checkout; the ticket's `.work/tickets/<id>/`
(or the goal file) does not exist; the command is not installed;
`handoff-author.json` could not be read; no record of which session wrote
this handoff; a later handoff write could not replace or remove `handoff-author.json` (`handoff-author.json.stuck`), or the file and its directory are both read-only so it can be neither replaced nor removed; the handoff changed since its author session wrote it; the
handoff was written by another session; this session's process could not be
identified (always on a host without `/proc` — native Windows, macOS); the
record of past auto-resumes (`resume-state.json`) could not be read, or its
directory cannot be searched; this handoff was already resumed; the progress
fingerprint could not be computed; the same command with no progress since
the last auto-resume; or `internal error` (the decision itself failed — the
handoff is still injected).

**Typing it (T-0013).** Where the terminal can be driven, crew types the
command into its own session. On that SessionStart the context hook runs its
own flavour's `auto-clear` sender in resume mode, before its context claim.
Consent is `resume.auto`; `context.autoClear` only describes the terminal
(`method`, `windowTitle`, `onlyRepos`, `onlySessions`). The sender claims a
per-handoff marker (`<git-common-dir>/crew/resume-typed-<sha256[:16]>`) only
after every refusal, records the run with `crew_resume.py record` (a failed
record types nothing), and then a detached sender types. In tmux it waits
`resume.typeDelaySeconds` (2), polls the pane up to
`resume.readyTimeoutSeconds` (15) for an idle, empty input line, and sends
the text and, half a second later, Enter. On native Windows it types only
under an explicit `method: sendkeys`, after the delay, with the focus and
tab rechecks; `auto` there is `notify` and types nothing. The context says
`Auto-resume: typing /crew:done T-0001 into this session in 2s (method
tmux); ...`, or keeps the line above and adds `Auto-resume was not typed:
<reason>.` Refusals, each logged to `.crew/.autoclear.log` (off is silent):
`decide` did not say run; no usable method, `$TMUX` unset, or a pane that is
not an ancestor; `wtype` or `xdotool`; the other flavour's method; already
typed once (marker); the run could not be recorded; the input line is not
empty; the input line was not ready in time; on Windows, focus lost or a tab
not provable after the delay. The 2 s default comes from the T-0013 spike
(input ready by 0.134 s on Claude Code 2.1.282). A delay is a guess, not a
proof: Windows has no probe, so on a loaded machine a key can land before
the box is ready (`CONFIG.md` §14b).

A note resumes only in the session that wrote it (T-0042). When the note is
written with Write, Edit or MultiEdit on an armed machine, the context hook
records who wrote it in `<git-common-dir>/crew/handoff-author.json`: after
`/compact` the session id must match, and after `/clear` (which changes the
session id) the Claude Code process must. A note written by Bash, by hand,
or before the machine was armed has no such record, so it waits. The allowlist is `crew_resume.RESUME_COMMANDS`:
`/crew:spec`, `/crew:plan`, `/crew:implement`, `/crew:review`, `/crew:done`,
`/crew:autopilot` and `/crew:status`. No gate changes: the resumed command's
own approval, scope, verify and review gates still decide.

A handoff written while `/crew:autopilot` drives a ticket carries
`resume: /crew:autopilot <id>`; typing `/crew:autopilot` with no argument in
the next session reads that line and recomputes the phase from disk (see
"Autopilot").

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

### Cross-session claims (`crew_coord.py`)

Since 1.1.6. When several sessions — same or different repositories, same or
different machines — work one backlog, each **claims** a ticket before working
it, so two sessions never hold the same one. The record is not in `.work/`
(ignored and per worktree) but on a git branch, `crew-coord/<channel>`, on a
shared remote. Its tree holds `claims/<repo>__<id>.json` per claim and an
append-only `log.jsonl`. You claim with the commands below: no crew command claims for you yet - neither a `/crew:autopilot` run nor a wave, which only run `status` first.

```
python3 hooks/scripts/crew_coord.py status  --channel <c> --remote origin
python3 hooks/scripts/crew_coord.py claim   --channel <c> --remote origin --ticket <id>
python3 hooks/scripts/crew_coord.py release --channel <c> --remote origin --ticket <id>
python3 hooks/scripts/crew_coord.py done    --channel <c> --remote origin --ticket <id>
python3 hooks/scripts/crew_coord.py recover --channel <c> --remote origin --ticket <id>
```

`--channel` and `--remote` default to `coord.channel` and `coord.remote`
(remote falling back to `origin`) in `.crew/config.json`.

**The `<repo>` half of the key is derived, never typed:** it is the `origin`
remote's URL as git resolves it — `git remote get-url origin`, so
`url.<base>.insteadOf` applies and an alias names the repository it points
at — reduced to its host and every path segment, lowercased, with `.git` and any
user or token removed, and a port removed only when it is the scheme's default (ssh 22,
https 443, http 80, git 9418): `ssh://host:2222/team/repo` gives `host_3a2222.team.repo`,
so two repositories behind two ports of one host are two keys. Each of those parts is written so it can
be read back one way only — every byte outside `a-z`, `0-9` and `-` becomes
`_` and two hex digits, so `.` is `_2e` and `_` is `_5f` — and the parts are
joined with a dot (`https://github.com/Owner/Repo.git`,
`ssh://git@github.com/Owner/Repo.git` and `git@github.com:Owner/Repo.git` all
give `github_2ecom.owner.repo`; `https://gitlab.com/group/sub/repo.git` gives
`gitlab_2ecom.group.sub.repo`). So every worktree and clone of one repository
names a ticket alike, and two different repositories never do — not on
different hosts, not in different groups with the same last two names, and
not where a dot inside a name would otherwise read as a separator
(`team/a.b/repo` and `team/a/b.repo` are two keys). A network URL keeps that
lowercasing and `.git` stripping because a hosting service serves those
spellings as one repository; a local one does not. A local path, or the path
a `file://` URL names (percent-decoded as git decodes it, with an empty or
`localhost` host), gives `file_` and its segments **with their case and any
`.git` kept**, because on a case-sensitive filesystem `Repo.git` and
`repo.git` are two directories, and `repo` beside `repo.git` is two
repositories anywhere. A local segment may be any name the filesystem allows
(`.git`, a dot-directory, a space); only one that is not UTF-8 reads
`unknown`. The path keyed is the repository git itself opens for
it: a leading `~` or `~user` is expanded as git expands it, a relative path is
read against the worktree git runs in, then git's own
suffix order is applied (`<path>/.git`, `<path>`, `<path>.git/.git`,
`<path>.git` — `enter_repo` in git's `setup.c`, read at v2.53.0), a gitfile is
followed and a linked worktree's git directory is taken to its common one, and
the result is made real (`..` and symlinks resolved) and each component is
spelled as its directory lists it, so on a case-insensitive volume (macOS and
Windows defaults) the case on disk is keyed, not the case typed. So
`remote.git` from `/srv/work`, `/srv/work/remote.git/`, `/srv/work/remote`
when only `remote.git` exists, and `file:///srv/work/remote.git` are one key;
a non-bare `/srv/src` and its `/srv/src/.git` are one key; and a path that is
not a repository here is keyed as written. A component whose directory cannot
be listed, on a volume where its case does not matter, reads `unknown`,
because its spelling on disk cannot be told. Every Azure DevOps form of one repository gives
`dev_2eazure_2ecom.<org>.<project>.<repo>`: `https://dev.azure.com/<org>/<project>/_git/<repo>`,
`https://dev.azure.com/<org>/_git/<repo>` (a project's default repository,
whose name is the project's, so project = repo),
`<org>.visualstudio.com/[DefaultCollection/][<project>/]_git/<repo>` and
`ssh.dev.azure.com:v3/<org>/<project>/<repo>` — each name percent-decoded and
lowercased, then written like any other part, so `My%20Project` and
`My-Project` stay two projects. The markers `_git`, `v3` and
`DefaultCollection` are compared after that decoding too, so `%5Fgit` is
`_git`. An origin the key cannot be told
from reads `unknown` (exit 3) and nothing is written: an Azure DevOps URL that
fits none of those forms or whose names are not UTF-8, a network URL's host or
path segment that is not letters, digits, `.`, `_`, `-`, a local path segment
that is not UTF-8, a key over 128 characters, a URL with no
path, a network URL with no host once any user and port are dropped
(`https:///owner/repo`, `https://user@/owner/repo`, `https://:443/owner/repo`,
`ssh:///owner/repo` — never read as a local path), a `file://` URL naming
another host or not percent-encoded UTF-8, an empty `origin` URL, or a
`get-url` that fails. That includes an
on-premises Azure DevOps Server URL
(`https://server/tfs/<collection>/<project>/_git/<repo>`), whose `_git`
segment is outside the rule. It never falls back to a directory name, which
would give one ticket a second key. Only when git says `origin` has no URL at
all (`git config` exit 1) does it use the main worktree's directory name, and
it prints why; a `git config` or `git rev-parse --git-common-dir` probe that
fails is `unknown` too, never that fallback. `--ticket <repo>:<id>` is still accepted, but
the `<repo>` given must be that derived name (compared lowercased); any other
is refused, because a free-text repo gives one ticket several keys and so
several holders. **The `<id>` half is upper-cased** for the same reason:
tracker ids — Jira keys, SDP ids, the local `T-NNNN` — name one ticket
whatever case they are typed in, so `t-0030` and `T-0030` are one key, not
two holders.

- **Writes never force.** Every change is a new commit on the freshly fetched
  tip, built with git plumbing (no checkout, no working tree, index, `.work/`,
  `HEAD` or `FETCH_HEAD` touched; other files on the channel keep their mode)
  and sent with a plain `git push`. crew_coord.py will never force: no
  `--force`, `-f`, `--force-with-lease` or `+` refspec. The push goes to
  `crew-coord--push`, a remote defined only in the push's environment
  (`GIT_CONFIG_COUNT`, git 2.31+) with the real remote's url, pushurl, proxy
  and receivepack, and never its fetch or push refspecs or `mirror`: git
  writes no remote-tracking ref, no local ref moves, and
  no URL — or a token inside one — appears in the process's arguments. A
  remote with several push URLs reads `unknown`, and so does one whose push
  configuration cannot be read: each of those keys is read with
  `git config --get-all`, where exit 1 means the key is absent and any other
  failure is `unknown` with nothing pushed, never a missing pushurl that would
  send the claim to the fetch URL. It runs with `--no-verify`,
  so the repo's pre-push hook (husky, lefthook) never runs on a claim or a
  heartbeat. A rejected push
  re-fetches, re-applies the change — a peer's claim that landed in between is
  then seen and refused — and retries at most 3 times, then reports
  `unknown - could not push`. A fetch that fails reads `unknown`, never current,
  and a claim is refused rather than granted on it.
- **The TTL is 30 minutes** (`coord.ttlMinutes`; anything but a number above
  0 and at most 10080, 7 days — a string, `0`, `NaN`, `Infinity`, `1e308` — is
  a config error: every command exits 2 naming the key before any fetch or
  push, so nothing is written). `claim` starts a detached
  heartbeat that pushes `heartbeat_at` every 10 minutes while the session's
  `CLAUDE_PID` lives and exits once it is gone, is reused by another process
  (a different start time), or the claim is no longer `working` for it. One
  loop runs per claim and holder — the holder's session id, machine,
  worktree, pid and start time, every field that makes a holder: a second
  loop for the same holder finds the first's lock and exits, while a new
  holder's loop — after a release and a claim by another session, the same
  session and pid claiming from another worktree, or a recover — takes a lock
  of its own and does not wait for the old holder's loop, which exits on its
  next tick. Inside
  Claude Code's sandbox (bubblewrap `--unshare-pid`) the loop cannot see
  `CLAUDE_PID`, reads it gone and exits at once, so the claim reads
  `owner unknown` after the TTL; the claim recorded no PID namespace (below),
  so recovery never adopts it: a false alarm, never a false grant. Its log
  and locks live in a private per-user directory in the system
  temp directory (`crew-coord-<uid>`, mode 0700; refused if it is a symlink,
  another user's, or open to others), the log opened 0600 without following a
  symlink. A `working` claim whose heartbeat is older than the TTL reads
  `owner unknown (last heartbeat <age>)`, **never free**: a new claim on it is
  refused. Staleness alone never releases or hands over a claim.
- **Only the holder** releases, finishes or heartbeats a claim. A holder is
  one session id in one process on one machine and worktree: session id,
  machine, worktree and `CLAUDE_PID` all equal, and the pid's start time equal
  where both sides recorded one. The same session id from another process or
  worktree — `claude --resume <id>` while the original is still open — is
  another holder: its `claim` is refused with the holder named, and it goes
  through `recover`'s rules, never a silent reclaim. **Only the
  owner** breaks one: `release --break --by <name>`, run from a terminal
  outside Claude Code (it refuses while `CLAUDECODE` or
  `CLAUDE_CODE_SESSION_ID` is set) and logged. That signal can be stripped
  with `env -u`, so it stops accidental breaks, not a determined agent — it is
  a documented rule, not an enforced one.
- **Recovery when a session's id changes.** `/clear` changes the session id,
  so a claim the previous session made looks foreign. `status` lists such
  claims **first**, marked `yours from a previous session`, each with its one
  recommended action. `recover` adopts one only when all of these hold: the
  claim's machine is this host, its worktree is this worktree, the local
  identity file (`<git-common-dir>/crew/coord-identity.json`, written by the
  script) names the claim's holder, and the holder's `CLAUDE_PID` is
  **provably gone** — then at once, however fresh its heartbeat (owner
  decision, rush g0). Where the end cannot be proven (a sandbox's namespace,
  a probe error, macOS), a fresh heartbeat says to wait for the TTL, and past
  it the claim is still only presented. Anything else — another machine, a
  live pid, a pid reused with a different start time, a missing or corrupt
  identity file, a check that cannot tell — reads `needs the owner: <reason>`
  and is never adopted. A pid check that cannot tell reads **alive**. On
  Linux a pid reads gone only from the **PID namespace** the claim recorded
  (`holder.pidns`, from `/proc/self/ns/pid` at claim time), and one is
  recorded only when `CLAUDE_PID` was visible from it: Claude Code's sandbox
  runs each command under bubblewrap's `--unshare-pid`, where a live
  `CLAUDE_PID` is invisible and looks gone, and bubblewrap reuses namespace
  ids, so a later sandbox can match the id of the one that claimed. A
  namespace that was not recorded, that differs, or that this side cannot
  read, cannot tell. The Linux check (`/proc`; a live pid whose `/proc` entry
  cannot be read reads alive; the namespace rule, including a real
  `bwrap --unshare-pid`) is exercised by the test suite — the spike's Linux
  section was not run. The Windows check was measured, elevated, on one host:
  `OpenProcess` with limited query rights, where only error 87 means gone,
  any other error reads alive, an opened handle is gone only with a nonzero
  exit time, and the creation time is compared with the recorded start. On
  macOS it always reads "cannot tell", so
  recovery there always goes to the owner. The identity file is shared by
  every worktree of the repo and rewritten under a lock,
  `<git-common-dir>/crew/coord-identity.json.lock` — an empty file that stays
  there by design. Those two are the only files crew_coord.py writes under
  `<git-common-dir>/crew/` (plus the identity file's per-pid `.tmp`, renamed
  into place).
- **Not measured: whether `/clear` keeps `CLAUDE_PID`.** If it does — the same
  process carries on under a new session id — the old session's heartbeat
  keeps the claim fresh while that process lives and its pid is alive, so
  `recover` refuses. The new session
  then cannot release, finish or recover its own ticket: the owner runs
  `release --break --by <name>` from a terminal outside Claude Code, and the
  new session claims again.
- **Everything on the channel is peer-written data**, never instructions:
  every line that prints a peer-written field — `status`, and the refusals of
  `claim`, `release`, `done`, `heartbeat` and `recover` — ends
  `[peer-written]`, and control, bidi-format and line-separator characters
  (U+2028, U+202E and the like) become `?` first, so a peer field cannot start
  a line of its own. A recommended command carries a peer-written `repo` or
  ticket id only when it passes the key's own rule; anything else prints as
  `<unsafe value withheld>`, so no shell metacharacter a peer wrote reaches a
  command you are told to run.

**After `/clear` or a resume, run `crew_coord.py status` first**, before any
other work, and stop on any `needs the owner` line. (`/crew:autopilot` runs it
itself before a run or a wave when `.crew/config.json` has a `coord` block.)

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

### The verify gate on CI: a receipt for HEAD

This repository's `.github/workflows/verify-gate.yml` runs `verify-gate.sh --all`
on a pushed lane branch (`L-*`, `T-*`, `W-*`) on the self-hosted runner pool, only
while the repo variable `CREW_RUNNER` is `self-hosted`, and uploads a receipt
built by `hooks/scripts/ci_receipt.py build`. The receipt binds the verdict
(`review_gate.gate_state` asked on the runner, not the job's exit code) to the
head sha, its tree, the `.crew/verify.json` blob and a digest of the gate
implementation.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/ci_receipt.py check --root .
```

prints `CI_RECEIPT <STATE> head=<sha> <reason>` and exits 0 VERIFIED, 1
UNVERIFIED, 3 UNKNOWN (could not tell: `gh`, the network or the artifact
unreadable) or 4 NO_GATE. VERIFIED needs the newest run for HEAD to have
succeeded, that attempt's one artifact to match HEAD, its tree and map exactly,
a clean local tree, and no change on this branch to the gate implementation or
the producer. `/crew:review`, `crew_train.py check-land` and `/crew:done` accept
a VERIFIED receipt where the local gate is UNVERIFIED or UNKNOWN; any other
receipt answer leaves the local verdict standing. The Stop hook does not consult
it: that would put network calls in a hook that runs every turn.

The receipt's per-command list is informative only. A command reads PASS, FAIL,
SKIP or UNKNOWN; UNKNOWN is a `COULD NOT TELL` line, or a command named failed,
skipped or could-not-tell with no elapsed line after it (L-0673). `log_complete` is
false unless the gate's total line comes after its last per-rule line, and with a
non-zero gate exit the job summary calls the list partial.

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

**Embedded where people and agents read (since 1.0.350, T-0035).**
`python3 hooks/scripts/crew_diagrams.py embed --root .` writes every diagram into
the README nearest its `%% Anchors:` paths, between `<!-- crew-diagrams:begin -->`
and `<!-- crew-diagrams:end -->`: a `## Diagrams` heading, then per diagram its
title, its `%% Purpose:` text, the fenced ```mermaid block (the source without its
`%%` lines) and a link to the source. GitHub draws it for a person; an agent reads
the same text. The `.mmd` stays the one source and nothing is hand-copied: text
outside the markers is never touched, and a second run changes no byte. The
repo-root README, a `SKILL.md`, a README inside the diagrams dir and one another
generator owns (a `<!-- generated by` first line, such as `docs/qa/README.md`) are
never targets, and no README is created. `%% Embed: <path>/README.md` or
`%% Embed: none` in the source overrides the choice. Where `origin` is on
bitbucket.org, which renders no mermaid fence, the block becomes the rendered
`out/<name>.svg` as an image with the source in a `<details>`, with a warning when
git ignores that SVG. `crew_diagrams.py check` exits 1 on drift (a section that is
not what `embed` writes now), malformed markers or an unreadable source; a README
not embedded yet is reported `pending` and passes, so adopting is one `embed` run.
`/crew:diagram` runs `embed` after each draw and refresh; `crew_refresh_check.py`
reports drift as a `diagram-embeds` line (below), and `scripts/check-marketplace.py`
runs the same check in this repository.

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

**A GitHub Actions deploy** (first slice only) is described by a `github` entry in the environment: the workflow filename, a branch-name `ref` (checked as a name only: a bare tag name is not detected), fixed `inputs`, and optionally `shaInput`, `correlationInput`, `deployJob`, `watchMinutes` and `identifySeconds`. `deploy` must list each entry's canonical prefix (`gh workflow run <workflow> --ref <ref> -f k=v ...`). `python3 hooks/scripts/crew_ghdeploy.py check --root . --env <name>` validates the entry, refuses any value outside `[A-Za-z0-9._/@:+-]` by name, refuses a map either promote gate refuses, and prints the literal dispatch for HEAD with `gated-as:` - every environment the gates apply to it (the union rule of L-1503: a command matching several environments carries all their requirements); it writes nothing and runs no `gh`. Dispatching, identifying, watching and recording the run are not built yet. The key table is in the crew-verification skill, section 4.

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
declared `deploy` entry unless, for the sha at HEAD of **the tree the deploy
runs from** (the Bash call's `cwd`, moved by a leading `cd <dir> &&` and named
by any `git -C <dir>`; it must be a worktree of the same repository, and any
literal sha in the command must be its HEAD):

- every environment in `requires` has an **all-pass** row in `.work/PROMOTIONS.md`
- `rollback` is set: a runbook that exists and carries `last verified: YYYY-MM-DD` inside 90 days, or the literal `"none"` plus a `rollbackReason` - an absent key blocks the deploy
- `requireHuman` has an approval marker at `.crew/.approved-<env>-<sha>`
- that tree is clean - you cannot deploy a sha plus uncommitted changes

Both flavours (`.sh` and `.ps1`) choose the environment by one rule, on the
working map and, when that is dirty, the committed map alike (L-1503):

- the command loses every CR and its trailing newlines; a command that is then
  empty or only whitespace deploys nothing and passes
- a declared command matches when either one contains the other - a plain
  substring test, ignoring case (on Windows `./Deploy.ps1` and `./deploy.ps1`
  are one file). `*`, `?` and `[...]` are literal text, never wildcards
- every key the gates read - `environments`, `deploy`, `requires`,
  `rollback`, `rollbackReason`, `requireHuman` - is read ignoring case
  (`"RequireHuman": true` requires a human); a map with a key repeated in one
  object - exactly, or differing only by case (`deploy` and `Deploy`) - is
  refused and the command blocks
- a `deploy` that is not a command or a list of commands - `null` included -
  or a `requireHuman` that is a list or an object refuses the map and the
  command blocks; `"deploy": []` and `[""]` declare nothing
- an environment name that is empty, holds a control character (a newline, a
  tab) or holds a comma refuses the map; `-`, `_` and `.` are fine
- the map must be strict JSON in both: a comment or a single-quoted or
  unquoted key refuses it. One difference is left: PowerShell reads a
  trailing comma that the bash flavour refuses
- if more than one environment matches, the strictest union of their
  requirements applies: every matched environment's `requires`, `rollback`
  and `requireHuman` must hold. They are named together - `staging,prod` - in
  the block message and in `.crew/.deploy-in-flight`, so the promotions row
  that clears the Stop check names `staging,prod` too. So `git push`, inside
  both `git push staging main` and `git push prod main`, needs prod's approval.
  That combined row is not a row for `staging` or for `prod`: after such a
  deploy, an environment that `requires` one of them still needs an
  unambiguous deploy record for it first - deploy with a command that matches
  only that environment, and record that (L-1505 is to write one row per
  matched environment instead)
- if the comparison itself fails, the command blocks rather than skipping
  that environment

So a clean worktree deploys while the main checkout is dirty, and a clean main
checkout cannot wave a dirty or wrong-sha worktree through. `.crew/verify.json`,
`.work/PROMOTIONS.md`, the approval markers and `.crew/.deploy-in-flight` are
read from the session's project directory on purpose - they are gitignored
per-checkout state that a fresh worktree lacks and a throwaway one could forge -
so an uncommitted change to the project's `.crew/verify.json` (edit, deletion,
untracked, or hidden by skip-worktree - compared with HEAD's copy) blocks too.
The directory the command runs in must also be clean. A command that changes
directory after it starts (`env -C` and `make -C` included), names two trees,
uses `--git-dir`, or puts `git` in a form the gate cannot read with certainty is
refused rather than guessed at (T-0505). When the gate blocks,
`/crew:promote` fixes the precondition it names; it never hands the owner the
command to run past the hook.

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
| `/crew:approve <id>` | **Typed by you only** (`disable-model-invocation`): the UserPromptSubmit hook records the plan approval from your own prompt; several ids or a range go pending until your `/crew:approve --confirm` — see "Scope and approval" |
| `/crew:implement <id>` | Implement an approved plan, then tests, docs, artifact refresh and review; refuses without a current approval |
| `/crew:done <id>` | Close a ticket: accepted review receipt, clean verify gate, passing completion audit and current artifacts, or no close |
| `/crew:fix <one sentence>` | The light path — every lifecycle phase present, each compressed to one step |
| `/crew:autopilot [status\|run\|focus\|wave] [<id>\|off\|--set <slug>]` | `run` (or a bare id, or nothing): drive one ticket through the lifecycle until a person is needed; with no id, resume from the handoff's `resume:` line, the active ticket, or the one open ticket. Off until `autopilot.mode: plan`. `status`: a read-only 12-line report. `focus <id>` / `focus off`: an explicit scope lock on one ticket (T-0020); the active ticket alone is not focus. `wave`: run an approved set as parallel isolated lanes (T-0029). `goal "<goal>"` (T-0012): propose, print the `/goal` line, approve the split. `assign` arrives with L-0611 (`crew_ticket.py assign` works from the command line since 1.0.302); `--goal` resume with L-0541 — see "Autopilot" |
| `/crew:review` | Independent QA — Codex, then Copilot, then Claude: the first that probes clean (a real call for Codex; a Codex usage limit runs Claude) |
| `/crew:onboard [--refresh <area>]` | Build or refresh the code map |
| `/crew:reference [--api\|--features\|--audit]` | Enumerate the API and features into `docs/reference/`, anchored to `file:line` |
| `/crew:init` | Guided phased setup, resumable |
| `/crew:plan <id> [--approve]` | Turn an approved spec into a step-by-step plan and ask you to `/crew:approve` it; the independent design opinion is now its optional step 3 |
| `/crew:runbook <name\|--audit\|--verify>` | Write, verify, or audit operational runbooks |
| `/crew:docs [<id>] [--audit]` | Update the documents this change should touch; with a ticket id, record each decision in `docs.json` and run the docs check |
| `/crew:handoff` | Write the handoff note before clearing |
| `/crew:diagram <type>` | Architecture, data-flow, process and sequence diagrams |
| `/crew:verify` | Build or refresh the change-to-check map; creates `_verify/` if the repo has no check directory |
| `/crew:webtest <id> [--stage spec\|implement\|heal\|evidence]` | Drive Playwright's Test Agents inside the ticket lifecycle; a healer skip is a finding, and the trace and axe results go to the reviewer |
| `/crew:promote <env> [--dry-run\|--status]` | Promote development -> qa -> production with deploy, smoke, regression and post-soak verification as separate gates |
| `/crew:survey [area]` | Research gaps, produce ranked findings with options |
| `/crew:jira-sync <KEY> [--push --to <status>]` | Sync one issue with the local cache |
| `/crew:sdp-sync <REQUEST-ID> [--push --to <status>]` | Sync one ServiceDesk Plus request with the local cache — see §13b |
| `/crew:obsidian-sync <T-####> [--push]` | Sync one Obsidian Kanban card with the local cache — see §13c |
| `/crew:upgrade` | Removed - `/crew:migrate` upgrades a pre-0.20 config itself |
| `/crew:emergency <what is broken>` | Declare a time-boxed incident: gates stand down and record what they skipped, lanes investigate in parallel — see §24. `status`, `extend [min]`, `end` |
| `/crew:model` | Report the resolved provider and model for every role, and which family would be reviewing which — see §12 |
| `/crew:status [--memory \| --approvals]` | Read-only status in at most 40 lines - config, inert settings, roster, tickets, review budget, in-flight markers (T-0049: one `in-flight:` line per ticket with its state, runner, since and, for stale or unknown, the owner's `clear` command; at most 5), gate, codemap, gitignore, handoff; `--memory` adds the context hook's stats; `--approvals` prints only the `/crew:approve <id>` lines for tickets whose approval is missing, stale or unaccepted |
| `/crew:migrate [--preview\|--apply\|--rollback <dir>]` | crew 1.0: one-time move of `.crew/config.json` to `.crew/crew.json`, tickets and tracker caches to `.work/tickets/<id>/`, `metrics.md` to `metrics.jsonl`; previews first, backs up, applies atomically, rolls back; a pre-0.20 config (no schema, or 1-6) is upgraded to the current schema first, in the same backup and rollback |
| `/crew:config [--show\|--models]` | Show where every setting comes from; with no argument, the menu that sets the machine or repo config from a list and deletes the repo config with a backup — see §11 |
| `/crew:config-setup` | The `/crew:config` menu under its own name — see §11 |
| `/crew:gate <disable\|enable\|status> <github\|bitbucket>` | Take a repository's merge gate down and put it back **from the export**. Gated by `guards.mergeGate`, which ships as `block` |
| `/crew:change <new\|status <id>\|close <id>\|list>` | File a change request into SDP, Jira or `.work/changes/`, one process either way. `new` refuses to file while any of the template's questions 1–9 is unanswered or a placeholder and names which; `close` refuses without the post-change validation results — see §24b |

36 commands.<!-- claim: plugin-commands:crew -->

### Agents

| Agent | Tools | Model | Tier | Role |
|---|---|---|---|---|
| `explorer` | read-only | `opus` | 0 | Maps code, returns summaries not contents |
| `reviewer` | read-only + Bash | `opus` | 0 | Hostile review; the last rung of `qa.order`, reached when neither Codex nor Copilot probes clean, or when Codex's probe hits a usage limit. Renamed from `qa-reviewer` in 1.0 |
| `security` | read-only + Bash | `sonnet` | 1 | Exploitable defects in the diff |
| `researcher` | read-only + web | `sonnet` | 2 | External research only. Every claim carries its source |

4 agents, all on the tier ladder (`crew_state.ROLE_TIERS`); `crew_state.SPECIALIST_ROLES` is empty in 1.0. Re-measure with `ls plugin/crew/agents/*.md`, which is one file per agent. **"read-only" in the Tools column means no `Write` and no `Edit`** — it does not mean no `Bash`, which is why the rows that hold `Bash` say so. `validate-prompts.py` enforces exactly that: a description saying read-only may not carry `Write` or `Edit`, and `Bash` is not part of that check. `tests/test_role_ladder.py` checks this table against the code in both directions.

**Verify before you state** (T-0041). `explorer`, `researcher` and `security` carry the rule: a claim about code, config, history or state is verified this session (a `path:line`, a command and its output, or a ref) or labelled `not verified` / `inferred`, and a prior decision is looked up in `CHANGELOG.md`, `docs/adr/` or a ticket's `direction.md` before a change to it is proposed. Their reports end with a **Not verified** section, and so do `/crew:done`'s and `/crew:debug`'s. `crew-best-practices` carries the same rule, and `crew-plan`'s self-review and `crew-brainstorm`'s approaches step look decisions up. `validate-prompts.py`'s `check_verification_rule` fails when any of these drops out; it reads every `agents/*.md` by default. `reviewer` is exempt by name until the review-harness half of T-0041 lands (its output is the contract `review_verdict.py` parses, so it gets no report section). The rule is crew's own and is not written into repos crew sets up.

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
| `promote-gate.sh` / `.ps1` | `PreToolUse` on Bash / PowerShell | Refuses a declared `deploy` command unless the upstream environment has an all-pass row for **this sha**, the rollback runbook is verified inside 90 days, `requireHuman` is approved, and the tree the deploy runs from (payload `cwd`, leading `cd`, `git -C`; same repository) is clean and at that sha. During an emergency lane it records each unmet precondition and allows the deploy (§24) |
| `cloud-guard.sh` / `.ps1` | `PreToolUse` on Bash / PowerShell | **Off by default** (`guards.cloudGuard`). Judges destructive cloud, Terraform and SQL commands and force push against the pinned `cloud.*` identity — see [Cloud guard](#cloud-guard) |
| `role-write-guard.sh` / `.ps1` | `PreToolUse` on Write / Edit | **Off by default** (`guards.roleWrites`: `block`/`report`/`off`). Keyed on the calling subagent's `agent_type`; enforces a role's write scope mechanically — CONFIG.md §18 |
| `approval-hook.sh` / `.ps1` | `UserPromptSubmit` | Records a ticket's plan approval only when the prompt *you* typed is `/crew:approve <id>`: validates `spec.md` and `plan.md` and writes the receipt bound to both hashes, or blocks the prompt and says why. Any other prompt: no output, exit 0 |
| `scope-guard.sh` / `.ps1` | `PreToolUse` on Write/Edit/MultiEdit/NotebookEdit/Bash/PowerShell | **Off by default** (`scope.mode`: `off`/`report`/`block`/`auto`; `/crew:init` writes `auto` for a new repo). Refuses an edit with no current approval or outside the spec's Touch, and a shell command that runs `crew_ticket.py approve` or writes crew state — see "Scope and approval" |
| `completion-audit.sh` / `.ps1` | `Stop` | **Off by default**, same `scope.mode`. Diffs the whole tree against the ticket's start commit, not counting a path byte-identical to merged main (T-0100), and blocks the stop once if any changed path is outside Touch, shell-made writes included |
| `handoff-read.sh` / `.ps1` | `SessionStart` | Resets its once-per-session markers. Prints the handoff after clear, compact, or resume only when `memory.inject` is false (the context hook injects it otherwise) — first archiving it instead, under `.crew/handoffs/`, if age or reality drift (its `head`/`branch` no longer describing the checkout) says it is stale |
| `crew-context.sh` / `.ps1` | `SessionStart`, `UserPromptSubmit`, `PostToolUse` on Read/Edit/Write/MultiEdit and vault MCP tools, `SubagentStart` | **On by default since 1.0.0; `memory.inject: false` in `.crew/config.json` turns it off, and then it emits and logs nothing.** Injects branch/HEAD, code-map anchor state and the handoff at SessionStart, budgeted code-map slices and vault-labelled recall per turn, and is the only channel that reaches a dispatched subagent (`SubagentStart`). Never blocks. `handoff-read` stops printing the handoff while this is on, so the two never inject it twice |
| `platform-sync.sh` / `.ps1` | `SessionStart` | Detects this machine and repairs the `platform` block in `.crew/config.json` — see §3b. The only hook that writes config: the seven derived facts, plus recreating the whole file from defaults when it is missing or malformed (backing up a malformed one first) — never when `.crew/` itself does not exist. See "The config heals itself" in §3 |
| `verify-gate.sh` / `.ps1` | `Stop` | Runs the checks the changed paths map to; fails the turn on red, on a changed path with no rule, or on a deploy that recorded no promotion row. A rule passes only on a completion record its wrapper writes; a killed, never-started or unrecorded rule is FAILED as COULD NOT TELL (T-0082). Stands down while an emergency lane is open (§24), recording what did not run |
| `context-watch.sh` / `.ps1` | `Stop` | Measures window occupancy from the transcript; asks for a handoff once per session at the later of `warnAt` and `reserveTokens` remaining, or instructs a wrap-up if `context.autoWrapUp` is on; with `context.autoClear.wrapUp` armed, sends the wrap-up procedure and feeds a refused wrap-up back once |
| `handoff-write.sh` / `.ps1` | `PreCompact` | Snapshots the transcript, writes a skeleton handoff |
| `notify.sh` / `.ps1` | `Notification` (`hook`) | Thin wrappers around `crew_notify.py`: a `question` ping for the permission and elicitation types only, never `idle_prompt`, one per waiting episode. `/crew:promote` calls `notify.sh deploy ... --outcome` itself. Outbound only; never reads. |

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

Every pwsh those suites spawn runs with a throwaway `XDG_CACHE_HOME` of its own
(L-0557). pwsh reads its multicore-JIT startup profile from
`$XDG_CACHE_HOME/powershell/StartupProfileData-NonInteractive` at start-up and
rewrites it at exit, so concurrent pwsh sharing `~/.cache/powershell` race on one
file, and the loser dies before running a statement ("Stack overflow.", exit -6,
or SIGSEGV, -11). `tests/conftest.py` sets the variable per test and refuses, by
audit hook, a pwsh spawned without it; `tests/test_pwsh_cache_isolation.py` scans
every `tests`/`_test` suite in the repo, Python and shell, for a pwsh spawn that
would skip it. There is no retry. Windows pwsh keeps the profile under
`LOCALAPPDATA`, so the variable changes nothing there.

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

Each entry also runs **bounded** (T-0080, `tests/sabotage_bound.py`), because a
mutation can turn a bounded read into an unbounded one: an uncapped run once
grew one python3 past 19 GB and the OOM killer took the session with it. The
entry's pytest starts in its own process group under a data-segment cap
(`RLIMIT_DATA`, default 4096 MiB per process, `CREW_SABOTAGE_MEM_MB`; `0` means no
cap) that every process the test spawns inherits, and a wall-clock limit
(default 600 s per entry, `CREW_SABOTAGE_TIMEOUT_S`). Over the cap the test
fails on its own assertion, so the entry is `RED (good)` for real; a timeout
stops the whole group and reads `RED BUT UNPROVEN -- timed out`, failing the
suite. An unreadable value refuses the run rather than meaning the default.
The cap is enforced on Linux only: elsewhere the `bound:` line the run prints
first says `memory cap absent`, and only the timeout applies; the same below Linux
4.7, where `RLIMIT_DATA` does not cover mmap. It never covers `MAP_SHARED` memory or
files written to a tmpfs - those are bounded by the timeout alone. When an entry
returns, on every path, its whole process group is KILLed, so a test that
backgrounds a process leaves nothing running; a process that calls `setsid`
leaves the group and is out of reach. The standalone runners `tests/sabotage_event_claim.py`,
`sabotage_autocycle.py` and `sabotage_resume.py` run under the same bound.

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
| On Windows a guard reads git differently from your shell | crew runs the tool `shutil.which` finds (PATHEXT order, the same as bash and pwsh), never a bare name. `where git` (cmd) or `Get-Command git -All` (pwsh) shows the order; the first hit is the git crew judges. A failing `git.cmd` shim first on PATH now makes guards say "could not tell". |
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

<!-- crew-diagrams:begin -->
<!-- generated by crew_diagrams.py embed from docs/diagrams: edit the .mmd sources there, then run it again; text between these markers is replaced -->
## Diagrams

### Data flow crew config autoclear

context.autoClear: how its settings are read straight from both raw files (not through resolve_config), and how its writer refuses a malformed machine file before handing off to the shared writer.

```mermaid
flowchart TB

    subgraph AutoClear["NEW at this anchor: context.autoClear's global-only keys and their writer"]
        direction TB
        ACREAD["<b>crew_autocycle.settings(root)</b><br/>reads BOTH raw files directly,<br/>NOT resolve_config"]
        ACWRITE["<b>crew_autoclear_setup.py</b><br/>write_autoclear_method() /<br/>write_autoclear_enabled()"]
        ACCHECK{"global file<br/>readable?"}
        ACRAISE>"<b>GlobalConfigUnreadable</b><br/>refuses to write over<br/>a malformed global file"]
        ACGO["<b>crew_config.</b><br/><b>write_global_config()</b><br/>the SAME atomic writer"]
    end
    ACWRITE --> ACCHECK
    ACCHECK -->|malformed| ACRAISE
    ACCHECK -->|ok or absent| ACGO
```

Source: [`docs/diagrams/data-flow-crew-config-autoclear.mmd`](../../docs/diagrams/data-flow-crew-config-autoclear.mmd)

### Data flow crew config menu

The /crew:config menu (its rows, choices, Save, and repo-file delete and restore) and the one file layer every crew config write goes through: lock, compare-and-swap update, no-clobber move.

```mermaid
flowchart TB

    subgraph Files["NEW (T-0075): the one file layer - plugin/crew/hooks/scripts/crew_config_files.py"]
        direction TB
        FLOCK["<b>Lock</b> :104<br/>&lt;path&gt;.lock holding the PID;<br/>machine_lock() first"]
        FUPD["<b>update_json()</b> :364<br/>read, compare digest, mutate,<br/>replace - inside the lock"]
        FMOVE["<b>move_no_clobber()</b> :466<br/>a rename that NEVER<br/>replaces its destination"]
        FREST["<b>read_restorable()</b> :199<br/>the ONE read delete refuses by<br/>and restore accepts by"]
        FLOCK --- FUPD
    end
    subgraph Menu["NEW (T-0075): the /crew:config menu - plugin/crew/hooks/scripts/crew_config_menu.py"]
        direction TB
        MSPEC["<b>menu_spec()</b> :317<br/>rows from the layer's template"]
        MCHOICE["<b>choices()</b> :215<br/>a value is offered only when<br/>the layer's planner accepts it"]
        MSAVE["<b>save()</b> :480<br/>plans BOTH layers<br/>before writing either"]
        MPLAN["<b>plan_delete()</b> :800<br/>holds the file's bytes and digests;<br/>delete_preview()"]
        MDEL["<b>apply_delete()</b> :852<br/>move_aside() to<br/>.crew/config.json.bak-UTC"]
        MREST["<b>restore_repo_config()</b> :962<br/>moves any current file aside,<br/>create_bytes()"]
        MSPEC --> MCHOICE
        MCHOICE --> MSAVE
        MPLAN --> MDEL
    end
    MDEL --> FMOVE
    MREST --> FMOVE
    FREST -.-> MPLAN
    FREST -.-> MREST
```

Source: [`docs/diagrams/data-flow-crew-config-menu.mmd`](../../docs/diagrams/data-flow-crew-config-menu.mmd)

### Data flow crew config no python

What two guards do when they cannot find python: role-write-guard.sh cannot read guards.roleWrites, so it always blocks a restricted role; cloud-guard.sh reads cloudGuard crudely from the resolved repo file and the machine file, and refuses when armed or when git cannot name a lane's main checkout.

```mermaid
flowchart LR

    subgraph NoPython["role-write-guard.sh's no-python fallback - a NARROWER contract than the old one"]
        direction TB
        NP1["<b>_resolve_role_write_python()</b><br/>finds no usable interpreter"]
        NP2["<b>_role_write_fallback_decision()</b><br/>cannot evaluate<br/>guards.roleWrites at all"]
        NP3["Unrestricted role: allowed.<br/>Restricted or unreadable role:<br/>ALWAYS BLOCKED (exit 2)"]
        NP1 --> NP2 --> NP3
    end

    subgraph CloudNoPython["cloud-guard's fallback - reads the resolved repo file (T-0096)"]
        direction TB
        CG1["no usable python,<br/>or cloud_guard.py failed"]
        CG2["<b>_cloud_guard_armed</b><br/>resolved repo file +<br/>machine file"]
        CG3["unknown, or cloudGuard<br/>not off: REFUSED (exit 2)"]
        CG1 --> CG2 --> CG3
    end
```

Source: [`docs/diagrams/data-flow-crew-config-no-python.mmd`](../../docs/diagrams/data-flow-crew-config-no-python.mmd)

### Data flow crew config ratchet

The keys that do not follow repo-beats-global: the two ratchet tables (read side and write side), the thirteen keys that resolve by the lower rank, and how a corrupt config file forces the role-write guard to block.

```mermaid
flowchart TB

    subgraph Ratchet["Two DIFFERENT ratchet tables, not one - 14 write-side, 13 read-side"]
        direction TB
        RG["<b>READ side:</b><br/>crew_guards.RATCHETED_KEYS<br/>13 keys"]
        RC["<b>WRITE side:</b><br/>crew_config._RATCHETED<br/>14 keys: the thirteen + pm.authority"]
        RSHAPE["Confirmed by import + diff + type():<br/>tuple field order differs, so<br/>not one table as written"]
        RG --- RC --- RSHAPE
    end
    subgraph Corrupt["A corrupt config file is its own state, and it BEATS the ratchet"]
        direction TB
        LS["<b>crew_config.layer_state(path)</b><br/>absent / corrupt / ok,<br/>either layer"]
        FORCE["<b>role_write_guard.py</b><br/>corruption in either layer<br/>forces policy = block"]
        LS --> FORCE
    end
    FORCE -.->|"overrides the resolved value"| Ratchet
    subgraph Except["Thirteen keys do NOT follow the precedence above (read-side ratchet)"]
        direction TB
        E1["<b>13 RATCHETED_KEYS</b><br/>resolve by the LOWER rank,<br/>not by repo-beats-global"]
        E2["effective value = the<br/><b>lower-ranked</b> of the two layers<br/>effective_ratcheted :564"]
        E3["Why: crew reads config<br/>out of CLONED repositories"]
        E4["Absent = the narrowest tier<br/>for ELEVEN of the thirteen"]
        E5["<b>guards.roleWrites, guards.cloudGuard</b><br/>the two exceptions to E4:<br/>DEFAULT is not their FLOOR"]
        E6["install.policy: auto is safe -<br/>no repo string becomes a command<br/>(crew_guards.INSTALLABLE)"]
        E1 --- E2 --- E3 --- E4 --- E5 --- E6
    end
```

Source: [`docs/diagrams/data-flow-crew-config-ratchet.mmd`](../../docs/diagrams/data-flow-crew-config-ratchet.mmd)

### Data flow crew config read

The read side: the three config sources (built-in defaults, the machine file, the repo file), how the machine layer is pruned to its template before merging, and how resolve_config() merges them.

```mermaid
flowchart TB

    subgraph Sources["Three sources, lowest precedence first"]
        direction TB
        DEF["<b>default_config()</b><br/>crew_config.py:245<br/>141 leaves, repo template"]
        GLB[("<b>~/.claude/crew/config.json</b><br/>read_global_config()<br/><i>never raises</i>")]
        RES{"which .crew/?<br/>own, else the main<br/>checkout's (a lane)"}
        REPO[("<b>.crew/config.json</b> - schema 7<br/>crew_state.load_config()")]
    end

    subgraph Gate["The global layer is filtered BEFORE it is merged"]
        direction TB
        TMPL["<b>default_global_config()</b><br/>crew_config.py:432<br/>81 leaves across 20 blocks"]
        PRUNE["<b>_prune()</b><br/>keeps only keys present<br/>in the template"]
        FILT["<b>filter_global()</b><br/>returns (kept, ignored)"]
    end

    subgraph Merge["resolve_config() - plugin/crew/hooks/scripts/crew_config.py:820 - the single resolver"]
        direction TB
        NULLS["<b>without_null_shadows()</b><br/>drops a repo <i>null</i> only where<br/>the global layer supplies a value"]
        M1["<b>merge_defaults</b><br/>(default_config(), global)"]
        M2["merge_defaults(that, repo)<br/>call: crew_config.py:854"]
        SCHEMA{"schema<br/>lifted OUT of the merge<br/>crew_config.py:855-858"}
        OUT(["<b>resolved config</b><br/><i>repo beats global beats default</i>"])
    end

    DEF --> M1
    GLB --> FILT
    TMPL -.->|"the shape to prune to"| PRUNE
    PRUNE --> FILT
    FILT -->|kept| M1
    FILT -.->|"ignored - named, never silent"| IGN>"keys a global file may not set"]
    RES --> REPO
    REPO --> NULLS
    NULLS --> M2
    M1 --> M2
    M2 --> SCHEMA
    SCHEMA -->|"in repo file: use it"| OUT
    SCHEMA -->|"absent: pop it entirely"| OUT
```

Source: [`docs/diagrams/data-flow-crew-config-read.mmd`](../../docs/diagrams/data-flow-crew-config-read.mmd)

### Data flow crew config shell route

shellRoute: the two config keys read through resolve_config, beside the machine-local probe cache that is not a config layer, both feeding crew_shell.decide().

```mermaid
flowchart LR

    subgraph ShellRoute["T-0040: shellRoute is config; the probe's answer is not"]
        direction TB
        SR["<b>shellRoute.mode / .distro</b><br/>both layers, read through<br/>resolve_config"]
        SRC[("<b>~/.claude/crew/shell-route.json</b><br/>the probe cache -<br/>NOT a config layer")]
        SRD["<b>crew_shell.decide() / status_line()</b><br/>native Windows only"]
        SR --> SRD
        SRC --> SRD
    end
```

Source: [`docs/diagrams/data-flow-crew-config-shell-route.mmd`](../../docs/diagrams/data-flow-crew-config-shell-route.mmd)

### Data flow crew config split

What may be set in the machine file versus only in the repo file (measured leaf counts), and the one asymmetry between the read rule and the write rule.

```mermaid
flowchart TB

    subgraph Asym["The asymmetry, stated because 'exactly what' hides it"]
        direction TB
        A1["Both rules agree on which PATHS."]
        A2["The WRITE path additionally<br/>rejects VALUES the READ path<br/>only reports."]
        A3["resolve_config NEVER raises -<br/>a malformed file must not wedge<br/>every session on the machine."]
        A1 --- A2 --- A3
    end

    subgraph Split["What may be set where - measured, not asserted (executed this pass)"]
        direction TB
        S1["<b>81 global-settable</b> leaves<br/>across twenty blocks"]
        S2["<b>60 repo-only</b> leaves<br/>(set difference, executed)"]
        S3["<b>Counts are executed,</b><br/><b>not read by eye.</b><br/>141 / 81 / 60"]
        S4["<b>Consent is not capability.</b><br/>context.autoClear.unsafeFocus<br/>is excluded from the global template"]
        S1 --- S2 --- S3 --- S4
    end
```

Source: [`docs/diagrams/data-flow-crew-config-split.mmd`](../../docs/diagrams/data-flow-crew-config-split.mmd)

### Data flow crew config two files

An open question: crew_config.py reads .crew/config.json while crew_context.py reads .crew/crew.json first, so which file governs depends on which module asks.

```mermaid
flowchart TB

    subgraph TwoFiles["OPEN AUTHORITY QUESTION - two modules read two different repo files as \"the config\""]
        direction TB
        CFGREAD["<b>crew_config.py</b> reads ONLY<br/>.crew/config.json (schema 7)"]
        CTXREAD["<b>crew_context.load_crew_config()</b><br/>.crew/crew.json FIRST,<br/>then .crew/config.json"]
        MIGRATE["<b>crew_migrate.py --apply</b><br/>the ONLY writer of<br/>.crew/crew.json (schema 1).<br/>Rewrites config.json only<br/>for a pre-0.20 config (upgrade stage),<br/>backed up and restored by --rollback"]
        OPEN["<b>Net effect:</b> which file governs<br/>depends on which module asked.<br/>OPEN - not resolved here"]
        TRKREAD["<b>crew_tracker.resolve()</b><br/>reads BOTH files; answers<br/>'could not tell' on disagreement"]
        MIGRATE -.-> CTXREAD
        CFGREAD --- OPEN --- CTXREAD
        TRKREAD -.- OPEN
    end
```

Source: [`docs/diagrams/data-flow-crew-config-two-files.mmd`](../../docs/diagrams/data-flow-crew-config-two-files.mmd)

### Data flow crew config unattended

unattendedCloud (T-0044): read from the MACHINE file only by crew_unattended.py, never through resolve_config; a repo copy is dropped from resolution and reported as ignored.

```mermaid
flowchart LR
    GLB2[("~/.claude/crew/config.json<br/>unattendedCloud")]
    REPO2[(".crew/config.json")]
    UCREAD["crew_unattended.py<br/>resolve_target :345"]
    UCDROP["resolve_config / explain_config<br/>repo copy dropped, repoIgnored"]
    CHAIN["run_checks :767<br/>settings, export, identity, sandbox probe"]
    GLB2 -->|"machine file only"| UCREAD
    REPO2 -.->|"environments.nonProd only"| UCREAD
    REPO2 -.->|"unattendedCloud ignored"| UCDROP
    UCREAD --> CHAIN
```

Source: [`docs/diagrams/data-flow-crew-config-unattended.mmd`](../../docs/diagrams/data-flow-crew-config-unattended.mmd)

### Data flow crew config write

The two writers behind /crew:config --set: the machine-file planner and the repo-file planner, the per-leaf and merged-file checks both share, and where each refuses.

```mermaid
flowchart TB

    subgraph Write["The WRITE side - /crew:config --set, and the menu's Save (machine layer)"]
        direction TB
        PLAN["<b>plan_global_write()</b><br/>crew_config.py:2936, <i>pure</i>"]
        ISG{"per LEAF:<br/>allowed?"}
        REFUSE>"GlobalWriteRefused (class :2286)<br/>names the path AND lists every allowed one"]
        MERGED{"merged file<br/>OK?"}
        WIDEN["<b>_plan_on()</b><br/>writes the judged leaves,<br/>marks each with _widens()"]
        WRITE["<b>write_global_config()</b><br/>the only crew write<br/>outside the repo"]
    end

    PLAN --> ISG
    ISG -->|"refused leaf"| REFUSE
    ISG -->|ok| MERGED
    MERGED -->|"bad value in the merged file"| REFUSE
    MERGED -->|ok| WIDEN
    WIDEN --> WRITE
    subgraph RepoWrite["NEW (T-0075): the repo writer - /crew:config --set --repo, the only path into .crew/config.json"]
        direction TB
        RPLAN["<b>plan_repo_write()</b><br/>crew_config.py:3136"]
        RREF>"<b>RepoWriteRefused</b><br/>(class :2988)"]
        RWIDEN["<b>repo_widens()</b> :3068<br/>the ratchet against<br/>what is in force"]
        RWRITE["<b>write_repo_config()</b><br/>crew_config.py:3162<br/>never creates the file"]
        RPLAN -->|"refused leaf, or a bad value in the merged file"| RREF
        RPLAN --> RWIDEN --> RWRITE
    end
    ISG -.->|"the same per-leaf judgement and merged-file check"| RPLAN
    MERGED ~~~ RPLAN
```

Source: [`docs/diagrams/data-flow-crew-config-write.mmd`](../../docs/diagrams/data-flow-crew-config-write.mmd)

### Data flow crew config

How one crew config value reaches a run, and what may set it where, as a map of the part diagrams (each box is one data-flow-crew-config-<part>.mmd); only the main flows between parts are drawn. no-python is a standalone fallback with no link to any other part, see data-flow-crew-config-no-python.mmd.

```mermaid
flowchart LR
    menu["<b>menu</b><br/>/crew:config menu + file layer"]
    read["<b>read</b><br/>sources, filter, merge"]
    write["<b>write</b><br/>machine and repo writers"]
    ratchet["<b>ratchet</b><br/>ratchet tables, exceptions"]
    autoclear["<b>autoclear</b><br/>autoClear read and writer"]
    twofiles["<b>two-files</b><br/>OPEN: config.json or crew.json"]
    split["<b>split</b><br/>what may be set where"]
    shell["<b>shell-route</b><br/>shellRoute config"]

    menu -->|"writes both files"| read
    menu -->|"Save"| write
    read -.->|"same template"| write
    write -.->|"widening notice"| ratchet
    read -.->|"raw files"| autoclear
    read -.->|"repo file"| twofiles
    read -.->|"resolved config"| split
    read -->|"resolved config"| shell
```

Source: [`docs/diagrams/data-flow-crew-config.mmd`](../../docs/diagrams/data-flow-crew-config.mmd)

### Process crew brief crew context

The crew-context SessionStart hook: how it reads the config, applies the stale-handoff rule and the auto-resume decision, and what it emits as additionalContext for each session source.

```mermaid
flowchart TB
    CC[crew-context]
    subgraph crewContext["crew-context (crew_context.py)"]
        CC --> cc1{".crew/ directory?<br/>:993"}
        cc1 -- no --> ccx([emit nothing])
        cc1 -- yes --> cc2["read crew.json else config.json<br/>:121-132"]
        cc2 --> cc3{"memory.inject?<br/>:1000-1003"}
        cc3 -- off --> cc4[incident banner only]
        cc3 -- on --> cc5["branch@HEAD, incident banner,<br/>codemap-behind line<br/>:881-892"]
        cc5 --> stale{"handoff stale?<br/>72h / 3 commits / branch"}
        stale -- yes --> arch["archive to .crew/handoffs/<br/>never delete<br/>crew_state.py:774, :980"]
        stale -- no --> cc6
        arch --> cc6
        stale -. "stale but the move failed:<br/>note stays, stale passed on (:893)" .-> cc6
        cc6{"auto-resume armed?<br/>:900"}
        cc6 -- "no (off)" --> src{"source?"}
        cc6 -- "run / wait" --> rs1["one line: ready to run,<br/>or did not start: reason<br/>resume_line :687"]
        rs1 --> src
        src -- startup --> ptr["pointer + next action<br/>:908-910"]
        src -- "resume/clear/compact/fork" --> full["full note, next action first,<br/>then the auto-resume line<br/>:911-923"]
    end

    ptr --> out(["additionalContext JSON<br/>:1090"])
    full --> out
    cc4 --> out
```

Source: [`docs/diagrams/process-crew-brief-crew-context.mmd`](../../docs/diagrams/process-crew-brief-crew-context.mmd)

### Process crew brief handoff read

The handoff-read SessionStart hook: the three checks that make it exit, and when it prints the handoff note. In crew 1.0 it usually exits, because crew-context delivers the note instead.

```mermaid
flowchart TB
    HR[handoff-read]
    subgraph handoffRead["handoff-read.sh"]
        HR --> hr1{"source is<br/>clear/compact/resume/fork?<br/>:34"}
        hr1 -- no --> hrx([exit 0])
        hr1 -- yes --> hr2{"memory.inject on?<br/>:41 (1.0 default: on)"}
        hr2 -- yes --> hrx
        hr2 -- no --> hr3{"resolved config.json?<br/>(own, else main checkout's)<br/>:48-50"}
        hr3 -- no --> hrx
        hr3 -- yes --> hr4[stale check / print note<br/>:69-95]
    end

    hr3 -. "? 1.0-only repo (crew.json, no config.json)<br/>with inject:false gets no handoff" .-> hrx
```

Source: [`docs/diagrams/process-crew-brief-handoff-read.mmd`](../../docs/diagrams/process-crew-brief-handoff-read.mmd)

### Process crew brief platform sync

The platform-sync SessionStart hook: silent without a crew config, otherwise it heals a broken config and records the machine it is running on.

```mermaid
flowchart TB
    PS[platform-sync]
    subgraph platformSync["platform-sync (crew_platform.py)"]
        PS --> ps1{"config or .crew/?<br/>:507-530"}
        ps1 -- no --> psx([exit 0, silent])
        ps1 -- yes --> ps2["heal_config if broken<br/>:547-563"]
        ps2 --> ps3["detect machine,<br/>write changed platform fields<br/>:566-584"]
    end
```

Source: [`docs/diagrams/process-crew-brief-platform-sync.mmd`](../../docs/diagrams/process-crew-brief-platform-sync.mmd)

### Process crew brief status

What /crew:status reads when run on demand, and the one place it differs from the SessionStart hooks: it checks a fixed handoff path and applies no stale rule.

```mermaid
flowchart TB
    subgraph status["/crew:status (on demand)"]
        st1["status.md:14<br/>crew_status.py --root ."] --> st2["report lines:<br/>git header, config, roster,<br/>tracker, tickets ... gitignore,<br/>handoff :224-254"]
        st2 -. "? checks fixed .work/HANDOFF.md (:245),<br/>not handoffPath, no stale rule" .-> st3([report, capped at 40 lines])
    end
```

Source: [`docs/diagrams/process-crew-brief-status.mmd`](../../docs/diagrams/process-crew-brief-status.mmd)

### Process crew brief

What crew 1.0 does when a session starts: hooks.json fans out to three SessionStart hooks, each drawn in its own file, plus the on-demand /crew:status report.

```mermaid
flowchart TB
    start([Session starts<br/>source: startup / resume / clear / compact / fork])
    start --> reg["3 SessionStart pairs<br/>hooks.json:3-10"]

    reg --> HR["handoff-read<br/>process-crew-brief-handoff-read.mmd"]
    reg --> PS["platform-sync<br/>process-crew-brief-platform-sync.mmd"]
    reg --> CC["crew-context<br/>process-crew-brief-crew-context.mmd"]

    status(["/crew:status (on demand)<br/>process-crew-brief-status.mmd"])
```

Source: [`docs/diagrams/process-crew-brief.mmd`](../../docs/diagrams/process-crew-brief.mmd)

### Process crew lifecycle approve

How /crew:approve, typed by the user only, records or refuses a plan approval through the approval hook, including the group-approval path, and how the ticket then moves to planned.

```mermaid
flowchart TB
    subgraph approve["/crew:approve - typed by the user only"]
        ap0["user types /crew:approve id<br/>approve.md:5"]
        ap0 --> ap1{"approval-hook verdict?<br/>hooks.json:14"}
        ap1 -- refused --> apx([prompt blocked, reason shown<br/>:15])
        ap1 -- recorded --> ap2["approval.json =<br/>digest(spec.md, plan.md)<br/>:12-13"]
        ap1 -- "several ids, a range,<br/>or plain text" --> apg["PENDING list, nothing recorded<br/>until the user's --confirm<br/>approve.md:27-32"]
        apg -- "confirmed, every hash unchanged" --> ap2
    end

    ap2 --> planned["spec.md 'status: planned',<br/>move --to planned<br/>plan.md:60-63"]
    planned --> to_im0>"next: implement part<br/>crew_ticket.py validate"]
```

Source: [`docs/diagrams/process-crew-lifecycle-approve.mmd`](../../docs/diagrams/process-crew-lifecycle-approve.mmd)

### Process crew lifecycle brainstorm

How a request enters the crew lifecycle: a small change takes /crew:fix, anything else goes through /crew:brainstorm until the user approves a direction and the ticket moves to ready.

```mermaid
flowchart TB
    ask([A request])
    ask --> small{"small change?<br/>brainstorm.md:90-91"}
    small -- yes --> fix["/crew:fix - same phases,<br/>one step each, one review round<br/>fix.md:2, :75, :95"]
    small -- no --> BR

    subgraph brainstorm["/crew:brainstorm"]
        BR["mint T-####: crew_tracker.py create<br/>INDEX row 'direction'<br/>brainstorm.md:15-40"] --> br2["one question per message,<br/>then 2-3 options, recommendation first<br/>:45, :54"]
        br2 --> br3["write direction.md, show, STOP<br/>:63-73"]
    end

    br3 --> ok1{user approves<br/>the direction?}
    ok1 -- no --> br2
    ok1 -- yes --> rdy["crew_tracker.py move --to ready<br/>brainstorm.md:81"]

    fix -.-> BR
    fix -. "same /crew:approve,<br/>/crew:review, /crew:done" .-> to_ap0>"next: approve part<br/>user types /crew:approve id"]
    rdy --> to_sp1>"next: spec-plan part<br/>direction.md?"]
```

Source: [`docs/diagrams/process-crew-lifecycle-brainstorm.mmd`](../../docs/diagrams/process-crew-lifecycle-brainstorm.mmd)

### Process crew lifecycle done

/crew:done's four checks, all of which must pass before the ticket is marked done, and the optional landing through the merge train.

```mermaid
flowchart TB
    subgraph done["/crew:done - all four or nothing<br/>done.md:7"]
        dn1{"1 review receipt<br/>--check-receipt<br/>done.md:10-13"}
        dn1 -- pass --> dn2{"2 verify gate all pass<br/>crew_status.py, or a CI receipt for HEAD<br/>(ci_receipt.py check)<br/>:21-38"}
        dn2 -- pass --> dn3{"3 completion audit<br/>passes?<br/>:40-53"}
        dn3 -- pass --> dn5{"4 artifacts current and committed<br/>crew_refresh_check.py, read-only<br/>:55-66"}
        dn5 -- fresh --> dn4["trailer report, then<br/>'status: done', move --to done,<br/>report + Not verified<br/>:68-98"]
        dn1 -- fail --> dnx([refuse done])
        dn2 -- fail --> dnx
        dn3 -- fail --> dnx
        dn5 -- "stale / unknown /<br/>fresh-uncommitted" --> dnx
        dn4 --> ln0{"train armed?<br/>crew_train.py status<br/>done.md:100-103"}
        ln0 -- yes --> ln1{"check-land passes?<br/>done.md:105-110"}
        ln1 -- LAND_OK --> ln2["you run the printed gh pr merge,<br/>then release --merged sha<br/>(crew never merges) :110-111"]
        ln1 -- "refused: catch-up, resolve,<br/>bump, refresh, commit, gate,<br/>review again if the receipt is stale<br/>:111-115" --> to_im5>"back: implement part<br/>then /crew:review last"]
    end
```

Source: [`docs/diagrams/process-crew-lifecycle-done.mmd`](../../docs/diagrams/process-crew-lifecycle-done.mmd)

### Process crew lifecycle implement

/crew:implement from the approval check to handing over to /crew:review: the plan steps under the scope guard, the refresh-artifacts loop and the required standards self-check.

```mermaid
flowchart TB
    subgraph implement["/crew:implement"]
        im0{"plan approved?<br/>implement.md:17-23"}
        im0 -- "no / stale" --> imx([refuse: /crew:plan id --approve])
        im0 -- yes --> im1["scope_base --record (kept if activate<br/>recorded; exit 1 could not tell), then<br/>crew_tracker.py move --to in-progress<br/>:28, :33"]
        im1 --> im2["steps in order, test first,<br/>scope-guard on every write<br/>:38-42"]
        im2 --> im3a["changed-file list, verify<br/>:59, :69"]
        im3a --> im3["step 6: tests, then /crew:docs<br/>:88-91"]
        im3 --> rf1{"crew_refresh_check.py<br/>:94"}
        rf1 -- "refresh with ..." --> rf2["run the named refresh,<br/>commit, re-run"]
        rf2 --> rf1
        rf1 -- "fresh-uncommitted" --> rf3["commit the paths its<br/>uncommitted: line lists, re-run<br/>:99"]
        rf3 --> rf1
        rf1 -- "stop" --> rfx([report the reason, stop])
        rf1 -- fresh --> sc1["required standards self-check<br/>:106-110"]
        sc1 --> im4["spec.md 'status: review',<br/>move --to review<br/>:111-113"]
        im4 --> im5["then /crew:review last<br/>:114"]
    end

    im5 --> to_pf0>"next: review part<br/>preflight first"]

    stop["Stop hooks every turn:<br/>verify-gate, completion-audit<br/>hooks.json:58, :62"] -.- im2
```

Source: [`docs/diagrams/process-crew-lifecycle-implement.mmd`](../../docs/diagrams/process-crew-lifecycle-implement.mmd)

### Process crew lifecycle review

/crew:review: the preflight, pre-review and self-check gates that run before a round is spent, then the review rounds and their verdicts, ending in a receipt or NEEDS_REPLAN.

```mermaid
flowchart TB
    subgraph review["/crew:review - two rounds per ticket"]
        pf0{"preflight (#264):<br/>receipt, gate, budget?"}
        pf0 -- "CLEAN receipt: CLEAN,<br/>no round, no self-check" --> rcpt
        pf0 -- "gate not passed or unknown:<br/>exit 5, no round spent,<br/>self-check not asked<br/>review.md:449" --> vg0["run the verify gate,<br/>then review again"]
        vg0 --> to_im5
        pf0 -- "go on" --> pr0{"pre-review checks<br/>pass? (L-0574)"}
        pr0 -- "NEW finding or COULD NOT CHECK:<br/>exit 5, no round spent<br/>review.md:449" --> fx0["fix the finding or the tool,<br/>then review again"]
        fx0 --> to_im5
        pr0 -- "pass / n/a / none configured,<br/>override recorded, or an active<br/>incident (skip logged)" --> rv0{"self-check<br/>stamped?"}
        pf0 -- "no rounds left or NEEDS_REPLAN:<br/>budget refusal answers first<br/>review_run.py:850-861" --> replan
        rv0 -- "no: exit 2,<br/>no round spent<br/>review.md:446-449" --> to_sc1
        rv0 -- "yes (or no approval receipt,<br/>or an incident: skip logged)" --> rv1["reserve a round, run<br/>Codex / Copilot /<br/>crew:reviewer fallback<br/>review.md:25-28, :451"]
        rv1 --> rv2{"verdict (the script's)<br/>:440, :482-486"}
        rv2 -- "CLEAN (exact: no other line)" --> rcpt["receipt written<br/>:510"]
        rv2 -- "FINDINGS (stray prose<br/>ignored and named)" --> rv3{"final round,<br/>0 BLOCK?"}
        rv3 -- "auto-accept or owner :508" --> rcpt
        rv3 -- "fix, round 2" --> again_rv1
        rv2 -- "INCOMPLETE (tool failure: refunded, :485-486)" --> again_rv1
        rv2 -- "INCOMPLETE (reviewer / tree, a contract-like<br/>or shortfall stray line): counts" --> again_rv1
        rv2 -- "third round refused" --> replan([NEEDS_REPLAN:<br/>back to /crew:plan<br/>or autopilot auto-reject])
    end

    again_rv1>"again: reserve a round,<br/>run the reviewers (above)"]
    to_im5>"back: implement part<br/>then /crew:review last"]
    to_sc1>"back: implement part<br/>required standards self-check"]
    rcpt --> to_dn1>"next: done part<br/>1 review receipt"]
```

Source: [`docs/diagrams/process-crew-lifecycle-review.mmd`](../../docs/diagrams/process-crew-lifecycle-review.mmd)

### Process crew lifecycle spec plan

/crew:spec writes spec.md from the approved direction, then /crew:plan writes plan.md, amending the spec's Touch list first when a step reaches outside it, and stops for approval.

```mermaid
flowchart TB
    subgraph spec["/crew:spec"]
        sp1{"direction.md?<br/>spec.md:10"}
        sp1 -- missing --> spx([refuse: run /crew:brainstorm])
        sp1 -- yes --> sp2["write spec.md<br/>Touch one path per bullet<br/>:15, :38-43"]
        sp2 --> sp3["crew_tracker.py move --to spec<br/>:45-48"]
    end

    subgraph plan["/crew:plan"]
        sp3 --> pl1["write plan.md: steps with<br/>Files / Test / Risk / Standards<br/>plan.md:27, :36"]
        pl1 --> pl2{"every Files: entry<br/>inside Touch?<br/>:44"}
        pl2 -- no --> amend["amend spec Touch first<br/>spec.md:57"]
        amend --> pl1
        pl2 -- yes --> pl3["show the plan, STOP<br/>:49"]
    end

    pl3 --> to_ap0>"next: approve part<br/>user types /crew:approve id"]
```

Source: [`docs/diagrams/process-crew-lifecycle-spec-plan.mmd`](../../docs/diagrams/process-crew-lifecycle-spec-plan.mmd)

### Process crew lifecycle

The whole crew ticket lifecycle at a glance, one node per stage; each stage is drawn in full in its own process-crew-lifecycle-<part>.mmd file.

```mermaid
flowchart LR
    ask([A request])
    fix["/crew:fix<br/>(brainstorm part)"]
    brainstorm["/crew:brainstorm<br/>(brainstorm part)"]
    spec["/crew:spec<br/>(spec-plan part)"]
    plan["/crew:plan<br/>(spec-plan part)"]
    approve["/crew:approve<br/>(approve part)"]
    implement["/crew:implement<br/>(implement part)"]
    review["/crew:review<br/>(review part)"]
    done["/crew:done<br/>(done part)"]
    ask -- "small: yes" --> fix
    ask -- "small: no" --> brainstorm
    fix -.-> brainstorm
    brainstorm --> spec --> plan --> approve --> implement --> review --> done
    fix -. "same /crew:approve,<br/>/crew:review, /crew:done" .-> approve
```

Source: [`docs/diagrams/process-crew-lifecycle.mmd`](../../docs/diagrams/process-crew-lifecycle.mmd)
<!-- crew-diagrams:end -->
