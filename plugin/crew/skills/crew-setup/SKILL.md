---
name: crew-setup
description: Bootstrap and configure a repository for the crew workflow, as guided phases. Use whenever the user says any of - set up crew, set up the crew, set up the team, set up the virtual team, phase setup, phased setup, run the setup, initialize crew, init crew, configure crew, onboard this repo, get this repo ready, add crew to this project, start the crew here - or otherwise asks to install, configure, or resume crew setup in a repository. Also use when they ask where setup got to, what phase they are on, or what is left to configure.
---

# Crew setup

Bootstrap one repository, as nine resumable phases.

## Start here

Read `${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/phases.md` and follow it. That file
is the single definition of the phases, the `.crew/STATUS.md` format, and the rule
that you stop and report after each phase rather than chaining them.

`/crew:init` runs the same thing. Whether the user typed the command or just said
"set up crew in this repo," the behaviour is identical — there is no second,
shorter path that skips the gates.

If `.crew/STATUS.md` already exists, say which phase they are on and what is
outstanding before doing anything else. Resuming beats restarting.

Ask before writing anything; this touches version control.

## Reference

The sections below are the detail behind Phases 0-2. Phases 3-7 delegate to
`crew:smoke-author`, `/crew:onboard`, `/crew:verify`, `crew:browser-tester`, and
the normal ticket loop.

## 1. Detect, do not assume

**Platform first**, because it decides which shell every later command uses:

```
bash ${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/scripts/platform.sh
```

If that fails because there is no bash, you are on native Windows — run
`platform.ps1` instead. Both emit the same JSON.

Then the repo itself:

```
bash ${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/scripts/detect.sh
```

It reports stack, existing tests, CI, and whether `codex` and Jira MCP are available.

Read `${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/platform.md` whenever the platform
result is Windows or WSL. Three things there change whether the setup works at
all: repo location under WSL (an order of magnitude in test runtime), `localhost`
not reaching the Windows host under WSL2, and CRLF line endings breaking shell
scripts with a misleading error.

Report what it found and what you propose to create. Wait for approval.

**Global `find-skills`.** If `detect.sh` reports one installed at
`~/.claude/skills/find-skills`, say so by name: its trigger fires on almost any
"how do I" question, which competes with `crew-setup` and `crew-verification`
for ordinary requests in this session. Offer to remove it. Never delete it
yourself, with or without asking — it is the user's own global configuration,
and a setup skill that quietly reaches into `~/.claude` is worse than the
collision it fixes.

## 2. Ask exactly three things

Do not ask more. Everything else has a sane default and can change later.

1. **QA reviewer:** Codex (detected/not detected) or Claude fallback?
2. **Tickets:** local files or Jira?
3. **Memory:** repo-local `.crew/` or an Obsidian vault path?

## 3. Create

```
.crew/config.json          # the switchboard — every command reads this
.crew/metrics.md           # header row only; /crew:review appends
.crew/codemap/INDEX.md     # empty until /crew:onboard runs
.work/INDEX.md             # files mode
.work/tickets/             # files mode
.work/cache/               # jira mode
_verify/                   # from template, NOT filled in
  README.md                # layout + status tables
  smoke.sh                 # fast and shallow
  run-all.sh               # regression suite
  cases/                   # one file per concern
docs/adr/0001-adopt-crew.md
CLAUDE.md                  # created if absent; if present, sections APPENDED, never overwritten
```

`config.json`:
```json
{
  "schema": 2,
  "tier": 0,
  "roles": ["explorer", "qa-reviewer"],
  "qa": { "provider": "auto" },
  "secondOpinion": { "provider": "none", "mode": "cli", "model": null, "keyEnv": "GEMINI_API_KEY", "sendsCode": false },
  "tracker": "files",
  "jira": { "project": null },
  "memory": { "mode": "repo", "vaultPath": null },
  "verifyGate": true,
  "context": { "enabled": true, "warnAt": 0.8, "budgetTokens": null, "handoffPath": ".work/HANDOFF.md", "keepTranscripts": 5 },
  "notify": { "provider": "none", "urlEnv": null, "tokenEnv": null, "chatId": null, "events": ["phase", "gate", "waiting"] },
  "platform": { "os": null, "wsl": null, "shell": null, "windowsHostIp": null },
  "pm": { "enabled": true, "mode": "adaptive", "quietLines": 8, "maxLines": 40, "authority": "report-only" },
  "graph": { "enabled": true, "tool": "graphify", "out": "graphify-out", "mode": "code-only", "commitHook": false, "obsidian": { "enabled": false, "dir": null, "confirmed": false } }
}
```

`schema: 2` — this repo is born current. It never trips `upgradeNeeded`, which fires only
when a config predates the `pm` and `graph` blocks. The `pm` and `graph` blocks above must
match `crew_state.PM_DEFAULTS` and `crew_upgrade.GRAPH_BLOCK` exactly — those modules are
the source of truth; this template is a copy of them, not the other way around.
`qa.provider`: `auto` uses Codex when present and falls back to Claude, announcing
which ran. Use `codex` to hard-fail instead of falling back, `claude` to force it.

## 3b. Jira only — wire the MCP connector

Only if the user chose Jira. Do NOT do this in files-mode repos.

1. Copy `${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/templates/mcp.json` to the repo
   root as `.mcp.json`, or merge it into an existing one. It uses the `/v1/mcp`
   HTTP endpoint — the older `/v1/sse` endpoint was retired mid-2026.
2. Tell the user to run `/mcp`, approve the server, and authenticate. A
   project-scope `.mcp.json` requires explicit approval; it will not connect silently.
3. Once connected, fetch the accessible cloud resources ONCE and write `cloudId`
   and the project key into `.crew/config.json` under `jira`. Never look them up again.
4. Set `tracker: "jira"` and create `.work/cache/`.

**Why per-repo, not bundled in the plugin.** A plugin-level `.mcp.json` connects
Atlassian in every repo where the plugin is enabled, including the ones tracking
work in files. Claude Code defers MCP tool definitions once they grow large, so
the standing context cost is smaller than it once was — but the auth prompts, the
connection, and the temptation to call the API mid-task all remain. Connect it
only where Jira is actually the source of truth.

Note: plugin-shipped agents cannot declare `mcpServers` in frontmatter, for
security reasons. Jira access therefore lives at session level. If Jira calls
should be isolated in their own context window, that agent must live in
`~/.claude/agents/` outside this plugin.

## 3a. Record the platform

Write the `platform` block from step 1 into `.crew/config.json`. Detect once at
setup, not on every run — re-detect only when something that used to work breaks.

Act on what it found, and say why:

- `repoFilesystem: windows-mount` — recommend re-cloning inside WSL. This is
  usually the largest single speed win available and costs one `git clone`.
- `crlfDetected: true` — offer to add `.gitattributes` with `* text=auto eol=lf`
  and run `git add --renormalize .` now, before anyone writes a script.
- Native Windows with WSL available — mention WSL is the simpler path (one shell,
  matches CI) and ask which they want. Do not decide for them; some applications
  genuinely need Windows.
- WSL2 with services on the Windows host — record `windowsHostIp` in
  `.env.smoke` as a variable, and note that it changes when the host reboots.

## 3c. Gitignore secrets before any exist

Append `.env`, `.env.*`, `!.env.example`, `.crew/*.local`, `.crew/.hook-*`, and
`.crew/transcripts/` to `.gitignore` during setup. Doing this before the first
secret exists is the only time it is free. `.crew/.hook-*` is the once-per-session
claim marker (see `hooks/scripts/hook_once.py`) — a repo that commits `.crew/`,
which crew's own design encourages, collects one of these per claimed hook per
session and shows them in every `git status` if they are not ignored.

## 4. Write the repo CLAUDE.md

### Triage first: does this rule belong here at all?

Most rules people want in CLAUDE.md should not be. Run each candidate through
this before writing it:

| The rule | Where it goes | Why |
|---|---|---|
| "Run playwright on CSS changes" | `verify.json` rule | A path glob decides it. A hook enforces it. |
| "Run tflint and terraform-docs" | `verify.json` rule | Same — mechanism, not judgment. |
| "No deprecated Terraform syntax" | tflint rules, mostly | The linter already knows. CLAUDE.md only for what it can't see. |
| "Smoke and regression after deploy" | `verify.json` `environments` block | `/crew:promote` runs them as separate gates. Mechanism, not memory. |
| "Production needs a rollback" | **CLAUDE.md** | A judgment gate no command can evaluate. |
| "Check error logs after deploy" | **CLAUDE.md** + runbook | Post-deploy, so no pre-merge hook can cover it. |
| "Don't fix things you notice nearby" | **CLAUDE.md** | Pure judgment, and the most valuable line in the file. |

The test: **could a command decide this?** If yes, it goes in `verify.json`,
where it is enforced rather than hoped for, and is not re-paid on every
delegation. What stays in CLAUDE.md is judgment, boundaries, and repo facts.

Ask the user for their rules, then triage them out loud rather than pasting them
all in. A 200-line CLAUDE.md is the most expensive file in the repo.

Thin. 30-40 lines. Stack, commands table, where things are, do-not-touch paths,
repo-specific rules, known landmines. Nothing else — it loads into every subagent
on every delegation, so every line is paid for repeatedly.

### When the repo already has a CLAUDE.md

This is the common case, and the one that goes wrong quietly. Run:

```bash
bash ${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/scripts/claude-md-audit.sh
```

It reports which template sections are missing, which sections the repo has that
the template does not, the line count against the ceiling, and how many
placeholders remain. Then **append the missing sections; never regenerate the
file.** A repo's existing CLAUDE.md encodes things nobody wrote down twice, and
regenerating it from a template destroys exactly that.

The same command is how an existing crew repo picks up template changes. The
template is not versioned into repos, so nothing propagates on its own - when a
section is added to the template (promotion discipline was added in 0.2.0), the
only way an existing repo gets it is someone running this audit and appending.
`/crew:docs --audit` runs it too, so the drift surfaces during a normal docs pass
rather than never.

### Files to read before writing

- `${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/repo-claude-template.md` — the skeleton
  with the section headings and the line budget. Start from this.
- `${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/examples/terraform-CLAUDE.md` — a
  filled-in example. **Read it when the repo has `.tf` files**, and read it
  anyway if the user is unsure what a good rule looks like: the shape transfers
  to any stack, only the specifics change.
- `${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/examples/verify-terraform.json` — the
  matching verify map, showing which of the user's rules were mechanized instead
  of written into CLAUDE.md. Read these two together; the split between them is
  the point.

**Adapt, do not copy.** The example names real tables, real buckets, and a real
"business logic lives in `sql/procedures/`" fact. Those lines are valuable
precisely because they are specific to that repo — copying them into a different
one produces a file that is confidently wrong. Take the structure and the kinds
of rule; write the content from this repo.

Work through it with the user rather than filling the blanks yourself. The
sections you cannot answer from the code — the landmine, the do-not-touch paths,
what "done" means here — are the ones worth the most, and only they know them.

## 5. Stop and say this out loud

The setup is not usable yet. `_verify/smoke.sh` has no checks in it, so the
gate passes vacuously and the crew has no safety net.

Tell the user: the next step is `@crew:smoke-author build the smoke harness`,
and nothing else should happen in this repo until that script runs green from a
clean checkout. Offer to start it now.

Do not offer to "get started on a feature." That is the failure mode this whole
setup exists to prevent.

## 6. What comes after

Prefer `/crew:init`, which runs this as nine resumable phases with a status file
and stops after each one for review. Use it rather than reciting steps at the
user — a checklist they have to drive themselves is a checklist that gets
half-finished.

If they would rather go manually, the order is:

1. `@crew:smoke-author build the smoke harness` — nothing else until it is green
2. `/crew:onboard` — learn the code
3. `/crew:verify` — learn which checks each kind of change requires
4. `@crew:browser-tester` if this repo has a UI
5. `/crew:survey` once the above exist — a survey before the safety net just
   produces a list of things nobody can safely act on
