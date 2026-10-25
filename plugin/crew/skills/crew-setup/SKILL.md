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
scripts with a misleading error. On native Windows it also covers choosing the
shell route, which is automatic and informed by
`crew_shell.py probe --write` and `measure --write`.

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
AGENTS.md                  # generated (step 4); a hand-written one is left alone
.github/workflows/crew-verify.yml  # OPT-IN, only once .crew/verify.json exists (below)
```

`.github/workflows/crew-verify.yml` — the verify gate as a pull-request job
(`verify-gate.sh --ci`: the whole map, network/host rules named but not run, a
SKIP or an empty run fails). It is opt-in: offer it, and write it only when the
user says yes. It is meaningful only once `.crew/verify.json` exists, so on a
fresh repo offer it after `/crew:verify` has built the map (Phase 5), not now.
To install it:

0. Check the map can run unattended FIRST. `--ci` runs only rules it can
   prove local: a rule with no `reach` that the scanner cannot clear (any
   `bash script.sh`, wrapper or inline shell) is excluded, and a map of
   nothing but those exits 2 on every PR ("zero commands to run ... nothing
   was checked"). Run `/crew:verify --stamp-reach` (a dry run) and show its
   table: the classifier proposes `local`/`network` where it can tell, and
   each wrapper rule needs the user to say `--set N=local` (or `network`/`host`)
   - never choose for them. Re-run with `--apply` and those `--set N=...`
   choices to write the map, commit that diff on its own, then run
   `bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/verify-gate.sh --ci < /dev/null`
   (in the background: it is the whole map). Offer the workflow only once
   that run executes commands; if it still exits 2 for "zero commands", say
   why and stop.
1. Copy `${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/templates/github/crew-verify.yml`
   to `.github/workflows/crew-verify.yml`.
2. Replace `__CREW_SHA__` with the full commit of the crew the user installed.
   Let `C` be `${CLAUDE_PLUGIN_ROOT}/../..` (the marketplace checkout) and run
   these checks in order. If ANY fails or cannot be run - a plugin cache has no
   `.git` - ask the user for the SHA instead. Never write a branch or tag: the
   gate judging a PR must not move under it.
   - (a) `git -C "$C" rev-parse --show-toplevel` equals `C` resolved
     (`cd "$C" && pwd -P`), so a parent repository is never trusted;
   - (b) `git -C "$C" remote get-url origin` names `mbadali25/useful-claude-add-ons`;
   - (c) `git -C "$C" rev-parse HEAD` is the SHA, and is exactly 40 hex characters;
   - (d) the commit is pushed: after `git -C "$C" fetch -q origin`,
     `git -C "$C" branch -r --contains <sha>` prints something - a local-only
     commit cannot be fetched by the job;
   - (e) that commit's gate has `--ci`: `git -C "$C" show
     <sha>:plugin/crew/hooks/scripts/verify-gate.sh | grep -q -- '--ci) CI_MODE=1'`
     succeeds. Test the feature, not a version number: versions are bumped
     on every merge, and comparing them as strings gets 1.0.99 > 1.0.231.
   A SHA the user gives you must pass (c) and, where you can fetch, (d) and (e).
3. Fill in the marked install step with the tools the map's commands call, or
   delete it (add `fetch-depth: 0` to the checkout if a command needs history).
   Tell the user the job checks only what the map maps, and that a PR controls
   more than its code: it can edit its own `.crew/verify.json`, and it can edit
   or delete this workflow file. Only CODEOWNERS review, or a ruleset, on
   `.crew/verify.json` and `.github/workflows/` prevents a PR switching its own
   gate off, so suggest one.
4. Tell the user the job only REPORTS until they make it required: in the repo's
   branch protection or ruleset for the default branch, add the status check
   `verify` (the job id; GitHub may show it as `crew verify / verify`). GitHub
   lists a check there only after it has run once, so open one PR first. Setup
   cannot set that - it is a repository setting - so say it plainly; until
   then a red job does not block a merge.

`config.json` — this JSON is a COPY, kept here for a human reading the skill.
It is not the source of truth: `${CLAUDE_PLUGIN_ROOT}/templates/config.template.json`
is, and that file is generated from `hooks/scripts/crew_config.py`'s
`template_config()`: `default_config()`, which in turn pulls the `pm` and
`graph` blocks straight from `crew_state.PM_DEFAULTS` and
`crew_upgrade.GRAPH_BLOCK` rather than duplicating them a third time, minus the
personal `autopilot` keys. Those are the owner's to set once in
`~/.claude/crew/config.json` (`/crew:config`); a new repo that spelled them
would hold the owner's choice down. A committed test asserts the template
equals `template_config()`'s output byte-for-byte, so this file drifting from
either one fails CI instead of shipping quietly. Copy the template, not this prose,
when actually creating `config.json`.

`/crew:init` writes this file; it never writes the optional machine-global
one at `~/.claude/crew/config.json`. If that file exists it sets defaults for
every crew repo on this machine, with the repo file you are about to write
taking precedence over it — see "Global config, and how it layers with the
repo file" in `README.md` §11.
One global block is machine-only in the stronger sense: `unattendedCloud`
(T-0044), the cloud identity `crew_unattended.py launch` hands an unattended
run, is read from the machine file alone. Never write it into a repo's
`config.json`; a repo copy is ignored and reported (`CONFIG.md`,
"`unattendedCloud`"). Its template shape, all `null` and naming nothing:
`"unattendedCloud": {"aws": {"readOnly": {"profile": null, "identity": null, "region": null}, "nonProd": {}}}`.

The global file has its own guided walkthrough, `/crew:config`, defined in
`global-config.md` beside this file. With no argument it opens a menu
(`config-menu.md`; `/crew:config-setup` is the same menu) that sets either
layer, machine or repo, from a list of values and deletes the repo config with
a backup. Offer it during Phase 1; never run it without being asked, and never
write `~/.claude` on your own initiative — the same reasoning that forbids
deleting a global `find-skills`. Setup itself still writes only the repo file.

```json
{
  "schema": 8,
  "qa": {
    "provider": "auto",
    "order": [
      "codex",
      "kimi",
      "copilot",
      "claude"
    ],
    "fallback": "claude-sonnet-5",
    "codex": {
      "model": null,
      "reasoningEffort": null
    },
    "copilot": {
      "model": null
    },
    "kimi": {
      "model": null
    },
    "roles": {}
  },
  "dev": {
    "provider": "claude",
    "fallback": "claude-sonnet-5",
    "codex": {
      "model": null,
      "reasoningEffort": null
    },
    "copilot": {
      "model": null
    },
    "kimi": {
      "model": null
    },
    "roles": {}
  },
  "secondOpinion": {
    "provider": "none",
    "mode": "cli",
    "model": null
  },
  "tracker": "files",
  "jira": {
    "project": null,
    "cloudId": null
  },
  "obsidian": {
    "vaultPath": null,
    "boardDir": null
  },
  "memory": {
    "mode": "repo",
    "vaultPath": null
  },
  "verifyGate": true,
  "context": {
    "enabled": true,
    "warnAt": 0.4,
    "reserveTokens": 0,
    "autoClear": {
      "enabled": null,
      "method": "auto",
      "delaySeconds": 3,
      "minHandoffLines": 5,
      "onlyRepos": null,
      "onlySessions": null,
      "wrapUp": null
    }
  },
  "resume": {
    "auto": null
  },
  "emergency": {
    "standDown": true,
    "maxTtlMinutes": 480
  },
  "notify": {
    "provider": null,
    "tokenEnv": null,
    "chatId": null,
    "events": [
      "blocker",
      "deploy",
      "question"
    ]
  },
  "platform": {
    "os": null,
    "wsl": null,
    "shell": null,
    "windowsHostIp": null
  },
  "pm": {
    "authority": "report-only",
    "maxDispatches": 3
  },
  "graph": {
    "out": "graphify-out"
  },
  "install": {
    "policy": "manual"
  },
  "guards": {
    "profile": "off",
    "overrides": {}
  },
  "production": {
    "databases": [],
    "hosts": []
  },
  "cloud": {
    "awsProfiles": [],
    "awsRegions": [],
    "azureSubscriptions": []
  },
  "environments": {
    "nonProd": [],
    "prodUnattended": false,
    "workflows": {}
  },
  "change": {
    "requireForProduction": false
  },
  "git": {
    "forbiddenTrailers": []
  },
  "scope": {
    "mode": "off",
    "allowCliApproval": false
  },
  "autopilot": {
    "maxAutoReplans": 0,
    "ship": "merge",
    "sleep": {
      "schedule": null,
      "approval": null,
      "questions": null,
      "deploy": null
    },
    "maxTicketsPerRun": 3,
    "maxTokensPerSession": 2000000,
    "maxLanes": null,
    "reviewPolicy": "stop"
  },
  "tickets": {
    "baseBranch": null
  },
  "route": {
    "enabled": false
  }
}
```

`scope.mode` above is the shipped default, `off`; `/crew:init` changes it to `auto`
(report for ten tickets, then block) in a **new** repo's file only — see Phase 1 in
`phases.md`. An existing `config.json` is never given a `scope` it did not have.

`schema: 7` — this repo is born current. It never trips `upgradeNeeded`, which fires on
any config predating the `pm` and `graph` blocks, the per-role provider table, the
`docs.theme` default moving to null, `install.policy`, the `guards` block, or the
`change` block. `change` is `/crew:change`'s: it asks for the requester, the implementor and
the category every time and files against the fixed `Change Management Request` template and
`Change` issue type, and `requireForProduction` is `false`, so `/crew:promote production` asks for no change
request until somebody turns it on. It is the one key in crew a repo may only turn
ON — see docs/crew/config-rationale.md. `production.databases` and
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

`docs.theme` / `docs.reportTheme` are not config keys any more. The brand a document carries is
doc-builder's own five-step resolution, and `skills/crew-house-style/SKILL.md` passes no `--brand`
(`crew_state.DOCS_THEME` and `DOCS_REPORT_THEME` are both `None`) unless the person names one in
the request. A `docs` block left in a config file has no effect. Say so if the user asks why their
theme stopped applying; `/crew:migrate` reports the key as inert.

`bitbucket.mergeGate` and `github.mergeGate` are not config keys any more. The merge-gate step of
`/crew:promote` runs only when the person asks for it on the command line (`--merge-gate
<github|bitbucket>`, optionally `--merge-gate-branch NAME`); a gate that arrived switched on would
start failing merges nobody asked it to watch. Without `--merge-gate-branch` the repo's main branch
is resolved from the provider's API rather than assumed to be `main`, and the Bitbucket preset is
fixed at `"standard"` and binds to nothing. A `mergeGate` block left in a config file has no effect.

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

# The named un-ignore list, and it is a closed list. These four describe the
# CODE, are decided once, and are worth the same on every clone: the code map,
# the endpoint ledger a security scan is owed against, the verification map and
# the development standards overlay (crew-standards; absent is fine).
!.crew/codemap/
!.crew/endpoints.json
!.crew/verify.json
!.crew/standards.md

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

Language and tool patterns (`__pycache__/`, `node_modules/`, `/<project>/bin/`, ...) never go in
this block: they are `crew_gitignore.py`'s managed block (`# crew:gitignore:managed`, at the top of
the file), which Phase 1 applies and `/crew:onboard` keeps current. That script never edits this block.

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

## 3e. .graphifyignore from the secrets denylist

`.gitignore` does not stop graphify reading a tracked file: only
`.graphifyignore` can. So, before any graph is built, run:

```
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_graph_ignore.py --root . --write
```

It appends every missing denylist pattern to `.graphifyignore` under one
marked block and changes nothing else. Report what it printed: the patterns
it added, or that none were needed. On exit 1 (a path still uncovered, or a
`!` line kept open) or 2 (the reason), report it and do not build a graph.
Repo-specific secret paths (`config/`, `/init.php`) go in
`.claude/secrets-denylist`, one gitignore pattern per line. Commit both files. The crew-graph skill's **Secrets denylist** section lists every
source.

## 4. Write the repo CLAUDE.md

### Writing it

Read `claude-md-authoring.md` before writing a line of it. It covers
the triage question (does this rule belong here at all), what to do
when the repo already has a CLAUDE.md, and the files to read first.

Then `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_instructions.py" agents --root .`
writes `AGENTS.md`, what Codex and other agents read: how to verify a change, and where things
are. `/crew:verify` and `/crew:onboard` regenerate it. Report its output; never replace a
hand-written one.

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
