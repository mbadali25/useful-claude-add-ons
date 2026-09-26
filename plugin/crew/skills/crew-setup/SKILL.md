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

The sections below are the detail behind Phases 0-2. Phases 3-7 cover the smoke
harness, `/crew:onboard`, `/crew:verify`, browser specs, and the normal ticket
loop — written in this session; crew 1.0 ships no writing agents.

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
2. **Tickets:** local files, Jira, ServiceDesk Plus, or an Obsidian Kanban
   board? Offer Jira and ServiceDesk Plus only when their MCP tools are
   actually reachable - `mcp__atlassian__*` / `sdp_*`. Offering a tracker that
   cannot connect produces a repo configured for an API nobody can call, and
   every later command stops on the same missing precondition.
   Obsidian has a different gate and needs a different question: there is no
   connector to probe, so what has to resolve is a **vault directory on this
   machine**. Offer it only when the user can name one, and check it exists
   before writing it down.
3. **Memory:** repo-local `.crew/` or an Obsidian vault path?

## 3. Create

```
.crew/config.json          # the switchboard — every command reads this
.crew/metrics.md           # header row only; /crew:review appends
.crew/codemap/INDEX.md     # empty until /crew:onboard runs
.work/INDEX.md             # files and obsidian modes
.work/tickets/             # files mode
.work/cache/               # jira, sdp and obsidian modes
_verify/                   # from template, NOT filled in
  README.md                # layout + status tables
  smoke.sh                 # fast and shallow
  run-all.sh               # regression suite
  cases/                   # one file per concern
docs/adr/0001-adopt-crew.md
CLAUDE.md                  # created if absent; if present, sections APPENDED, never overwritten
```

`config.json` — this JSON is a COPY, kept here for a human reading the skill.
It is not the source of truth: `${CLAUDE_PLUGIN_ROOT}/templates/config.template.json`
is, and that file is generated from `hooks/scripts/crew_config.py`'s
`default_config()`, which in turn pulls the `pm` and `graph` blocks straight
from `crew_state.PM_DEFAULTS` and `crew_upgrade.GRAPH_BLOCK` rather than
duplicating them a third time. A committed test asserts the template equals
`default_config()`'s output byte-for-byte, so this file drifting from either
one fails CI instead of shipping quietly. Copy the template, not this prose,
when actually creating `config.json`.

`/crew:init` writes this file; it never writes the optional machine-global
one at `~/.claude/crew/config.json`. If that file exists it sets defaults for
every crew repo on this machine, with the repo file you are about to write
taking precedence over it — see "Global config, and how it layers with the
repo file" in `README.md` §11.

The global file has its own guided walkthrough, `/crew:config`, defined in
`global-config.md` beside this file. Offer it during Phase 1; never run it
without being asked, and never write `~/.claude` on your own initiative — the
same reasoning that forbids deleting a global `find-skills`. Setup itself
still writes only the repo file.

```json
{
  "schema": 7,
  "tier": 0,
  "roles": ["explorer", "reviewer"],
  "qa": {
    "provider": "auto",
    "order": ["codex", "copilot", "claude"],
    "fallback": "claude-sonnet-5",
    "codex": { "model": null, "reasoningEffort": null },
    "copilot": { "model": null },
    "roles": {}
  },
  "dev": {
    "provider": "claude",
    "fallback": "claude-sonnet-5",
    "codex": { "model": null, "reasoningEffort": null },
    "copilot": { "model": null },
    "roles": {}
  },
  "worktree": { "root": null },
  "secondOpinion": { "provider": "none", "mode": "cli", "model": null, "keyEnv": "GEMINI_API_KEY", "sendsCode": false },
  "tracker": "files",
  "jira": { "project": null, "cloudId": null },
  "sdp": { "portal": null, "noteVisibility": "private", "closeOnDone": false },
  "obsidian": { "vaultPath": null, "boardDir": null, "board": "Board.md", "columns": { "backlog": "Backlog", "ready": "Ready", "inProgress": "In Progress", "review": "Review", "done": "Done" } },
  "memory": { "mode": "repo", "vaultPath": null, "inject": true, "recall": { "vaults": [], "maxChars": 800 } },
  "verifyGate": true,
  "context": { "enabled": true, "warnAt": 0.5, "budgetTokens": null, "reserveTokens": 0, "handoffPath": ".work/HANDOFF.md", "keepTranscripts": 5, "autoClear": { "enabled": null, "method": "auto", "windowTitle": null, "command": "/clear", "delaySeconds": 3, "minHandoffLines": 5, "unsafeFocus": false, "onlyRepos": null, "onlySessions": null }, "autoWrapUp": true, "autoResume": true, "staleHandoff": { "maxAgeHours": 72, "maxCommitsBehind": 3 } },
  "resume": { "auto": null },
  "emergency": { "standDown": true, "ttlMinutes": 120, "maxTtlMinutes": 480 },
  "notify": { "provider": "none", "urlEnv": null, "tokenEnv": null, "chatId": null, "events": ["phase", "gate", "waiting"] },
  "platform": { "os": null, "wsl": null, "shell": null, "windowsHostIp": null },
  "pm": { "enabled": true, "mode": "adaptive", "quietLines": 8, "maxLines": 40, "authority": "report-only", "ticketGranularity": "system", "maxDispatches": 3 },
  "graph": { "enabled": true, "tool": "graphify", "out": "graphify-out", "mode": "code-only", "commitHook": false },
  "docs": { "theme": null, "reportTheme": null },
  "bitbucket": { "mergeGate": { "enabled": false, "branch": null, "preset": "standard" } },
  "github": { "mergeGate": { "enabled": false, "branch": null } },
  "install": {"policy": "manual"},
  "guards": { "terraformApply": "block", "forcePush": "block", "adminMerge": "block", "mergeGate": "block",
              "cloudDestructive": "block", "sqlDestructive": "block",
              "prodDatabase": "none", "prodServer": "none", "roleWrites": "off", "cloudGuard": "off" },
  "production": { "databases": [], "hosts": [] },
  "cloud": { "awsProfiles": [], "awsRegions": [], "azureSubscriptions": [] },
  "change": { "requester": null, "implementor": null, "requireForProduction": false,
              "sdpTemplate": "Change Management Request", "jiraIssueType": "Change", "category": null },
  "scope": { "mode": "off", "allowCliApproval": false },
  "autopilot": { "mode": "off", "maxPhases": 12 }
}
```

`scope.mode` above is the shipped default, `off`; `/crew:init` changes it to `auto`
(report for ten tickets, then block) in a **new** repo's file only — see Phase 1 in
`phases.md`. An existing `config.json` is never given a `scope` it did not have.

`schema: 7` — this repo is born current. It never trips `upgradeNeeded`, which fires on
any config predating the `pm` and `graph` blocks, the per-role provider table, the
`docs.theme` default moving to null, `install.policy`, the `guards` block, or the
`change` block. `change` is `/crew:change`'s: `requester` and `implementor` are the
person and default into the template's Requestor Details, `sdpTemplate` and
`jiraIssueType` name what the SDP and Jira backends file against, and
`requireForProduction` is `false`, so `/crew:promote production` asks for no change
request until somebody turns it on. It is the one key in crew a repo may only turn
ON — see CONFIG.md §17. `production.databases` and
`production.hosts` are the globs `guards.prodDatabase` and `guards.prodServer`
match commands against, and they are repo-only: the LEVEL is a machine fact, what
IS production is a fact about this checkout. Empty lists mean those two guards
match nothing, which is why they can default to `none` and change no behaviour.
`qa.provider`: `auto` walks `qa.order` and uses the first provider that passes its
probe, announcing which ran. Name a provider (`codex`, `copilot`, `claude`) to pin it
and hard-fail instead of falling back.

`qa.order`: the candidate sequence `auto` walks. A provider that is not on `PATH`, or
whose block is not configured, is skipped out loud — never silently.

`qa.codex.model` / `qa.codex.reasoningEffort`: both `null` means "pass no flag", i.e.
whatever the Codex CLI itself defaults to. This is deliberate — it keeps an upgraded
repo behaving exactly as it did before. Set `reasoningEffort` to `"high"` for a
materially harder review at higher latency and cost; set `model` only to pin a
specific Codex model. Read at call time, never hardcoded in the command.

`qa.copilot.model`: **required before Copilot can run at all.** Copilot CLI defaults to
`claude-sonnet-4.6`, the author's own family, which makes it a worse reviewer than the
Claude fallback while looking like a stronger one. `/crew:review` therefore refuses an
unpinned Copilot rather than quietly running a same-family review. Pin a model from a
family that is neither the author's nor Codex's — a Google model such as
`gemini-3.7-flash` — so the review is actually independent. Verify the name
against the current catalog; a stale one fails at startup.

`qa.roles` / `dev.roles`: **empty by default, and that emptiness is the whole design.**
A role with no entry runs on its block's own `provider`, which is what every repo did
before schema 3 — so a repo born here and a repo upgraded into here dispatch
identically. Add an entry to send one role somewhere else:

    "dev": { "roles": { "developer": { "provider": "codex", "model": "gpt-6-astra" } } }

`qa.fallback` / `dev.fallback`: the model a role falls back to when the model it is
pinned to has been *retired*. Default `claude-sonnet-5`. This is a different failure
from the one `qa.order` handles: `qa.order` covers a provider that is missing or
unauthorised, this covers a provider that answers fine while the model name is gone —
`crew-providers` records two names that died exactly that way. Configurable rather than
hardcoded for that same reason. **A fallback that fires is announced, never silent**: a
review that quietly ran on the fallback looks identical to one that ran on the pin, and
the difference matters most exactly when the pin was chosen to get a different family
onto the diff.

`docs.theme` / `docs.reportTheme`: `theme` is a doc-builder theme-pack skill name, passed
straight through as that tool's `--brand`.

**The pass-through consumer is prose, not code, and that is the whole reason this paragraph
kept going wrong.** `skills/crew-house-style/SKILL.md` is what reads both keys — it instructs
the model to route to `doc-builder` and pass `--brand <docs.theme>`, preferring
`docs.reportTheme` for a findings report. A grep for `--brand` or `resolve_brand` in crew's
own Python finds nothing, which is what this paragraph previously read as "the wiring does
not exist"; the wiring is a skill instruction, and `tests/test_docs_routing.py` is the
committed regression test that binds `docs.reportTheme` to the findings-report genre — it
asserts the flag by running doc-builder's own argparse, not by grepping for the string.
`CONFIG.md` §7 carries the consumer table for both keys, and its §9 subsection "Keys whose
only consumer is prose" lists `docs.reportTheme`.

So: this paragraph asserted the pass-through in the present tense until 2026-09-12, was
rewritten to deny it entirely, and is corrected again on 2026-09-14. Both earlier versions
were wrong in the same way — they treated "no Python reads it" and "nothing reads it" as the
same sentence. Before editing it a fourth time, check `crew-house-style/SKILL.md` and
`tests/test_docs_routing.py`, not just a grep of the scripts.

A null theme passes no `--brand` at all and lets doc-builder resolve for itself, so do not
tell the user a theme is in effect when either key is null — that is doc-builder's answer to
give, not crew's.

Both default to `null`, and null means the same thing in both: **"I have no answer, ask the
next authority."** For `reportTheme` that authority is `docs.theme`; for `docs.theme` it is
doc-builder's own five-step resolution. Set `reportTheme` only when reports need a different
brand from the rest of the docs, which is the client-deliverable case.

`docs.theme` shipped as `"neutral"` through 0.17.1 and `/crew:upgrade` rewrites that one
value to null — the only value the upgrade rewrites rather than preserving. Say so if the
user asks why their config changed, and say why it was safe: **through 0.17.1 the key had no
consumer at all**, so no value sitting in it could be a preference anyone formed by watching
it work. That is a claim about the releases the rewrite applies to, not about today —
`crew-house-style/SKILL.md` reads the key now, which is exactly why leaving `"neutral"` in
place would be harmful rather than merely inert: every upgraded repo would pass an explicit
`--brand neutral` that OVERRIDES an installed brand pack, de-branding documents that come out
correctly branded today, with nothing in the config file changed to explain it. A user who
did mean neutral sets it again and it is honoured. (`CONFIG.md` §7 cites this paragraph for
that justification, so keep the historical claim here if you reword it.)

`bitbucket.mergeGate`: off by default, because a gate that arrived switched on would start
failing merges nobody asked it to watch. `branch: null` means the repo's main branch is
resolved from the Bitbucket API rather than assumed to be `main` — a repo on `master` or a
Gitflow `develop` would otherwise get a gate that looks configured and guards nothing.

`github.mergeGate`: the same two keys for GitHub, for the same two reasons. There is no
`preset`, and the missing key is the decision: `bitbucket.mergeGate.preset` binds to
nothing and CONFIG.md §8 records why it stays unwired, so copying it would be shipping
that defect a second time on purpose.

`guards`: four keys, each `block` | `ask` | `allow`, all four arriving as `block`.
`terraformApply`, `forcePush` and `adminMerge` are read by crew's command guard;
`mergeGate` is read by `/crew:gate` and decides whether crew may take a live repo's merge
gate down at all. `ask` means crew prints the exact command and refuses until the user
creates the one marker file it names — approving that command and no other. `allow` means
crew runs it and writes a row to `.crew/guard.log`; under `allow` nothing is silent.
**These four and `install.policy` resolve to the NARROWER of the repo and global layers,
not the repo's** — a repo travels inside a clone somebody else wrote, and under ordinary
precedence it could grant itself force-push rights on the machine of anyone who cloned it.
So a repo may ask for less than the machine allows and be obeyed, and may ask for more and
be refused; `/crew:config --explain` names which layer is holding a key down.

### Offer the per-role table — do not leave the user to find the keys

Ask this during Phase 1, alongside the reviewer question, and read the consequence
out loud rather than writing it silently. A setup that ships pins nobody was told about
is the failure `pm.authority` already taught us. Verified available on this machine
2026-09-05; probe before offering, since these names churn:

| Slot | Suggested pin | Family |
|---|---|---|
| `dev.roles.developer` | `codex` / `gpt-6-astra` | gpt |
| `dev.roles.security` | `codex` / `gpt-6-astra` | gpt |
| `qa.roles.phase1`, `qa.roles.smoke` | `codex` / `gpt-5.6-sol` | gpt |
| `qa.roles.review`, `qa.roles.gate` | `codex` / `gpt-5.6-luna` | gpt |
| a Copilot alternative | Kimi 2.7 (`kimi-k2.7-code`), or Kimi 3 (`kimi-k3`) | kimi |

Two things to say before writing any of it:

- **The family guard is evaluated FIRST, the pin second.** `gpt-5.6-sol` and
  `gpt-5.6-luna` are the same `gpt` family as `gpt-6-astra`, so on a diff **codex
  wrote** they are barred and QA falls to claude or kimi. **Pinning the developer to
  codex therefore means most dev work is codex-authored, so the Sol and Luna QA pins
  fire on claude-authored work and comparatively rarely elsewhere.** That may be exactly
  what the user wants. It must not be something they discover from a review log.
- **The `-code` suffix on Kimi 2.7 is load-bearing.** The display name is "Kimi 2.7";
  the value that goes in the config is `kimi-k2.7-code`. Bare `kimi-k2.7` is rejected by
  the Copilot CLI with `Model "kimi-k2.7" from --model flag is not available`.

`/crew:model` reports the resulting table per role — effective provider, model, family,
which fallbacks are armed, and whether the guard is currently barring anything.

If `.crew/` exists but `config.json` went missing or stopped parsing, you do not
need to recreate it by hand — the `platform-sync` `SessionStart` hook already
does, using this same template, the next time the repo is opened. See
"The config heals itself" in `README.md` §3.

Leave `platform` as nulls. The `platform-sync` `SessionStart` hook fills it in
on the first run and repairs it whenever the repo is opened on a different OS -
`config.json` is machine-local (`.crew/*` ignores it and it is not on the
un-ignore list), but "this machine" is not fixed: one checkout is opened from
Windows and from WSL, and WSL2's `windowsHostIp` changes on reboot. Do not
hand-write values there; they will be overwritten, which is the point.

## 3b-3d. Tracker wiring (Jira, ServiceDesk Plus, Obsidian)

Only one of these runs, decided by the tracker chosen in step 2.
Read `trackers.md` for the one that applies - it carries the MCP
connector checks, the two ServiceDesk Plus settings, the Obsidian
vault resolution and the Kanban board template.

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

<!-- crew-ignore-policy:list - this block is the shipped template. check-marketplace.py's
     check_crew_ignore_policy asserts its un-ignore list matches this repo's own
     .gitignore, so the template cannot drift from the policy it teaches. -->

Append this block to `.gitignore` during setup, in this order. Doing it before
the first secret exists is the only time it is free.

```gitignore
.env
.env.*
!.env.example

# crew state. `.crew/*`, NOT `.crew/`: a trailing slash makes git refuse to
# descend into the directory at all, and nothing can be re-included from a
# directory git never entered - every negation below would silently do nothing.
.crew/*

# The named un-ignore list, and it is a closed list. These three describe the
# CODE, are decided once, and are worth the same on every clone: the code map,
# the endpoint ledger a security scan is owed against, and the verification map.
!.crew/codemap/
!.crew/endpoints.json
!.crew/verify.json

# Documentation, not mechanism: `.crew/*` above already ignores every one of
# these and no negation re-admits them, so deleting these lines changes nothing
# git does. They are listed because `.crew/.approved-<env>-<sha>` is the
# promotion approval marker THE OPERATOR creates - promote-gate only looks for
# it - and a tracked one dirties the tree, after which the gate blocks on the
# very file you were told to create. Keep them if you ever narrow `.crew/*`.
.crew/.approved-*
.crew/*.lock
.crew/*.local
.crew/.hook-*
.crew/transcripts/
.work/
```

Everything under `.crew/` not on that list - `config.json` with its machine
paths and its `pm.authority` trust decision, `STATUS.md`, `metrics.md`, the
incident state - describes one checkout on one machine. A fresh clone runs
`/crew:init` and generates its own.

`.work/dispatch.json` and `.work/dispatch.d/` are covered by `.work/` above; if
this repo tracks part of `.work/` for its own reasons, ignore **both** by name.
They are the record of which roles, providers and models have run here —
the self-review guard reads them to know who WROTE the diff. **Both**: since
0.16.7 each dispatch writes its own file under `.work/dispatch.d/` and
`dispatch.json` keeps only a convenience pointer to the most recent one, so
ignoring the single file and not the directory commits the actual record. It
describes one checkout on one machine, so a committed copy would travel to a
colleague and claim a dispatch that never happened there. `.crew/.hook-*` is the
once-per-session claim marker (see `hooks/scripts/hook_once.py`): `.crew/*`
already covers it, and it is named anyway because it is the entry whose absence
shows up as noise in every `git status` rather than as a failure.

## 4. Write the repo CLAUDE.md

### Writing it

Read `claude-md-authoring.md` before writing a line of it. It covers
the triage question (does this rule belong here at all), what to do
when the repo already has a CLAUDE.md, and the files to read first.

## 5. Stop and say this out loud

The setup is not usable yet. `_verify/smoke.sh` has no checks in it, so the
gate passes vacuously and the crew has no safety net.

Tell the user: the next step is building the smoke harness (`/crew:init --phase 3`),
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

1. Build the smoke harness — nothing else until it is green
2. `/crew:onboard` — learn the code
3. `/crew:verify` — learn which checks each kind of change requires
4. Browser specs if this repo has a UI
5. `/crew:survey` once the above exist — a survey before the safety net just
   produces a list of things nobody can safely act on
