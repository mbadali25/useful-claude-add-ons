# Plugin reference

What each plugin in [`plugin/`](.) actually contains, and — for the parts that execute on their own — what starts running the moment it is enabled. The one-line catalog is in [`README.md`](README.md); this is the detail behind it.

Read the **Hooks** section of any plugin before installing it. Commands and agents wait to be asked. Hooks do not.

---

## `crew` — virtual dev team for multi-repo legacy work

| | |
|---|---|
| **Source** | [`crew/`](crew) |
| **Version** | 0.8.0 |
| **Install** | `claude plugin install crew@useful-claude-add-ons` |
| **Menu item** | 21, `repo-plugins` — **off by default**. Menu item 22, `graphify`, is a separate, also-off-by-default install of the `graphify` CLI this plugin's graph feature depends on — see **The code graph** below. |
| **Registers** | 10 agents, 20 commands, 16 skills, 20 hook entries (10 scripts × `.sh`/`.ps1`) across 5 events |
| **Upstream guide** | [`crew/README.md`](crew/README.md) — 25 sections, the authoritative version |

Built for the awkward case: several repositories, mixed stacks, legacy code, and almost no test coverage. The workflow is file-backed tickets, one implementation session, an independent reviewer, and deterministic gates that block on failure rather than offering an opinion.

Its central design claim is worth repeating, because it is the opposite of how most agent bundles are built: **a persona in a prompt adds no capability.** A role earns its place only if it buys an isolated context window, a restricted tool set, or genuinely independent eyes. Project management, business analysis, architecture, documentation, and training are files, commands, or you — there is nothing for an agent to isolate. Every custom subagent also loads your entire `CLAUDE.md` hierarchy at startup, so a 4,000-token `CLAUDE.md` across eight delegations is 32,000 tokens of overhead before any work happens.

### Hooks — the part that runs without being asked

Ten scripts across five events, each shipped as a `.sh`/`.ps1` pair
registered on its own matcher or event — 20 hook entries. **These are why
menu item 21 is unticked by default.**

| Script | Event | What it does |
|---|---|---|
| `guard.sh` / `.ps1` | `PreToolUse` on the Bash / PowerShell tool | Blocks `terraform apply`/`destroy`, destructive DDL, force push, hard reset, prod-targeted commands, and any command that would print a secret value into the transcript |
| `promote-gate.sh` / `.ps1` | `PreToolUse` on the Bash / PowerShell tool | Refuses a declared `deploy` command unless the `requires` environment has an all-pass row for this sha, the rollback runbook is verified inside 90 days, `requireHuman` is approved, and the tree is clean |
| `handoff-read.sh` / `.ps1` | `SessionStart` | Injects the prior handoff back after a clear, compact, or resume |
| `platform-sync.sh` / `.ps1` | `SessionStart` | Detects this machine and repairs the `platform` block in `.crew/config.json` - the one block that is committed and therefore wrong for everybody who did not run `/crew:init`. **Writes config**, and is the only hook that does: strictly the seven derived facts (`os`, `wsl`, `wslVersion`, `distro`, `shell`, `repoFilesystem`, `windowsHostIp`) and nothing a human chose. Reports, without changing, a preference this OS cannot honour |
| `pm-brief.sh` / `.ps1` | `SessionStart` | Runs `crew_state.py` and prints a prioritized brief — schema currency, a stale or missing code graph, a pending handoff, stale or missing diagrams, review health, ticket sizing. Prints only; the acting is the PM's |
| `pm-pulse.sh` / `.ps1` | `Stop` | Re-engages the PM when the project state actually changed — a ticket closed, a gate broke, diagrams fell behind HEAD. **Fails the turn** to hand its findings back, so the crew acts without being asked. Gated on a state fingerprint, not on the event: turns that change nothing stay silent, and the same state can only interrupt once. Honours `stop_hook_active`, and stands down after 12 pulses in a session |
| `verify-gate.sh` / `.ps1` | `Stop` | Runs the checks the changed paths map to; **fails the turn** on red, on a changed path with no rule, or on a deploy that wrote no promotion row. Honours `stop_hook_active`, so a red check cannot pin the session. Stands down while an emergency lane is open, recording what did not run |
| `context-watch.sh` / `.ps1` | `Stop` | Reads actual window occupancy from the transcript's last `message.usage` record and asks for a handoff once per session, at the later of `context.warnAt` and `context.reserveTokens` of remaining headroom; instructs a full wrap-up instead if `context.autoWrapUp` is `true`. On the following turn it invokes `auto-clear`, which is inert unless `context.autoClear.enabled` is `true` |
| `auto-clear.sh` / `.ps1` | called by `context-watch`, not registered | **Experimental, off by default.** Types `/clear` into the *terminal* once the handoff is written — it cannot clear the conversation, it drives the terminal the way a human would. `tmux` targets a pane by id; every other method needs an explicit `windowTitle` and refuses without one. Refusals go to `.crew/.autoclear.log`, because a `Stop` hook's stderr is invisible on exit 0 |
| `handoff-write.sh` / `.ps1` | `PreCompact` | Snapshots the transcript and writes a skeleton handoff before compaction discards it |
| `notify.sh` / `.ps1` | `Notification`, and called directly by commands | One outbound line to Teams or Telegram. Never reads, never accepts instructions |

**This is what "the moment the plugin is enabled" means in practice: a `SessionStart` hook now fires on every session's `startup`, unconditionally, in a repository with `.crew/config.json` present.** `handoff-read` and `pm-brief` both run before you type anything, so enabling the plugin changes what the very first turn of every session looks like, not just what later tool calls are allowed to do.

**Since 0.8.0 it also changes how turns end.** `pm-pulse` is a `Stop` hook that *fails the turn* when the project's state has changed, handing its findings back so the crew picks up the next thing without being asked. That is the point of it, and it is also the part to understand before enabling: a hook that can block is a hook you cannot talk out of it. It is gated on a state fingerprint rather than on the event, so turns that change nothing are silent; it honours `stop_hook_active`, so it cannot loop; and it stands down after 12 pulses in a session. Set `pm.enabled: false` in `.crew/config.json` to switch it off along with the brief.

Every event is registered twice, once per flavour, each with the matching `shell` field on the PowerShell side — a `shell: powershell` entry is documented and Claude Code does read it, running that entry via PowerShell without needing `CLAUDE_CODE_USE_POWERSHELL_TOOL`. `guard.sh` / `guard.ps1` and `promote-gate.sh` / `promote-gate.ps1` additionally branch on `tool_name` at the `PreToolUse` matcher — a `PowerShell` tool call goes to the `.ps1`, a `Bash` tool call is judged by the `.sh` — because that is which language the command is actually written in, not which OS is running. Branching on the OS instead would judge bash commands with PowerShell rules on Windows, which blocks the correct secret-capture form and misses the wrong one. The other hooks judge no command, so both flavours are simply wired to their event with no branch. `hooks/scripts/_common.sh` also ships a `crew_tool_dispatch` helper for judging a command from inside a single bash-registered script; it is unused here in favour of the explicit dual-matcher registration above, but stays available for a hook that wants that shape instead.

A hook cannot be argued out of blocking `terraform apply`; an agent can. That is the entire value, and also the reason a bootstrap run should not install one without the box being ticked.

Committed suites, all sabotage-tested: `hooks/scripts/_test/run-tests.sh` (95 cases across the three gates, the emergency lane, and the PM pulse), `setup-walkthrough.sh` (32 cases running every setup-phase script against a real mixed-stack scratch repo), `validate-prompts.py` (108 structural checks over the commands, agents and skills), and `tests/` under pytest (306 cases, including both flavours of `context-watch` and of the two gates that stand down). All but the pytest suite's Windows-only cases run in CI. What none of them proves is whether the prompts produce good work — that needs a live session on a real ticket, which is what setup Phase 7 is for.

**Every hook is inert until the repository has `.crew/config.json`.** Installing the plugin arms nothing - `/crew:init` in a repo is what turns the gates on there. A gate firing in every repository you opened would be hostile, so this is deliberate; it does mean "installed it, nothing happened" is expected rather than broken.

**The `Stop` gate is additionally inert until you build its map.** `verify-gate.sh` reads `.crew/verify.json`; with no such file there is nothing to run. `/crew:verify` builds it. Set `verifyGate: false` in `.crew/config.json` to disable the gate without uninstalling.

**Windows — fixed in 0.2.0, corrected in 0.3.0.** In 0.2.0 `guard.sh` and `verify-gate.sh` exited 0 on MSYS/MINGW to "defer" to `.ps1` twins that nothing ever invoked, so on Windows the command guard blocked nothing and the `Stop` gate ran nothing — which reads as "the gate passed" rather than "the gate never ran". 0.3.0 registers **both flavours on every matcher-less event on purpose**, not because each one fires — `hooks.json` has no way to know in advance which shell a given machine actually has, so both are wired and one is expected to fail; `PreToolUse` is the exception, where `guard.sh`/`guard.ps1` and `promote-gate.sh`/`promote-gate.ps1` are registered on separate `Bash` and `PowerShell` matchers instead, so the branch is by *which tool Claude used*, not by OS. The PowerShell side carries `shell: powershell`, a field Claude Code documents and reads — it runs that entry via PowerShell without needing `CLAUDE_CODE_USE_POWERSHELL_TOOL`. What is not configurable is the *default* interpreter for a bare `command` string with no `shell` field: that goes to `sh -c` on macOS/Linux and to **Git Bash** on Windows (PowerShell only when Git Bash isn't installed) — so a `bash` resolved from some non-MSYS parent process is not necessarily what runs it. On Windows this is measured, not hypothetical: Git for Windows ships two `bash.exe` binaries, and `usr/bin/bash.exe` exits 127 running these scripts where `bin/bash.exe` runs them fine, so which one resolves first on `PATH` decides whether the `.sh` side works at all; on a machine where a non-MSYS parent process resolved `bash` to the WSL launcher, the `.sh` side exited 127 on every script while the `.ps1` twin exited 0. **One flavour failing is expected behavior, not a bug** — it is not evidence the hook itself didn't run. What is genuinely unverified is the opposite combination, real hook-runner behavior with **no `pwsh` on Linux**; that was never exercised, so treat it as unconfirmed rather than assumed fine. The remaining requirement on Windows is that Git Bash (or WSL) is on `PATH` for the `.sh` half to have any chance; without any bash at all, that half never fires, and the plugin does not pretend otherwise.

**`python3` is no longer required.** The scripts resolve `python3`, then `python`, then `py`, and `guard.sh` prefers `jq` when it is present. With none of them available the affected hook says so on stderr and exits 0 rather than failing open in silence.

**`context.autoWrapUp` and `context.autoResume`** (both default `false`) change what happens around the handoff, not whether it happens:
- `autoWrapUp` changes what `context-watch` tells the session to do at `warnAt` — reach a stopping point and write the handoff, instead of just asking for one. **The `/clear` itself stays manual regardless of this setting, because no hook can trigger one** — a hook runs as a child process and cannot reset its parent's conversation. Without stating that plainly, the feature reads as broken (why doesn't it actually clear?) rather than as what it is: bounded by a real constraint.
- `autoResume` makes the next `SessionStart` open already holding the last handoff, emitted as `additionalContext` rather than `initialUserMessage` — the latter is confirmed only for non-interactive `-p` invocations, and could not be confirmed to behave the same way in an interactive session, so the safer field was used. That means the session opens **with the handoff in view**; it does not start working unattended. A human still gives the first turn.

### The code graph

`crew-graph` (below) wraps the third-party `graphify` CLI to build a code
graph at `graph.out` (default `graphify-out/graph.json`, configurable in
`.crew/config.json`), and `/crew:upgrade` (next) uses it to bring an older
setup forward. Neither is a hook — nothing here runs on its own — but both assume
`graphify` is on `PATH`, which is a **separate, off-by-default install**:
menu item 22 (`uv tool install graphifyy` — the PyPI package is `graphifyy`,
double-y; the CLI it installs is `graphify`). A keyless build needs both
`--no-viz` and `--code-only`: without `--code-only`, `graphify` errors on any
repository containing docs, rather than skipping them. Exporting the graph
into Obsidian is gated on `graph.obsidian.confirmed` being set explicitly by
the user in `.crew/config.json`; `/crew:upgrade` never sets that flag itself.

### The emergency lane

`/crew:emergency` is a time-boxed, recorded decision to stop gating while
something is actually broken. `.crew/incident.json` is the whole mechanism:
while it exists and its `expiresAtEpoch` is in the future, `verify-gate` exits 0
without running the checks and `promote-gate` computes its preconditions,
records the ones that failed, and allows the deploy anyway. Everything skipped
goes to `.crew/incident-skips.log`, one row per gate and reason, and
`/crew:emergency end` turns that into `.work/INCIDENT-<id>.md` plus an archived
record under `.crew/incidents/`.

Three properties are worth stating, because they are what make this safe enough
to ship:

- **It expires on its own.** The gates compare an integer epoch; no command runs
  and no file is touched to re-gate. Forgetting to close an incident - the
  realistic failure, since nobody forgets to declare one during an outage -
  cannot leave a repository permanently ungated. `emergency.ttlMinutes`
  defaults to 120 and `extend` is capped at `emergency.maxTtlMinutes` (480),
  measured from *now* each time, so repeated extensions cannot drift.
- **The command guard never stands down.** `guard.sh` / `guard.ps1` has no
  incident branch and must not get one: standing down the checks that say a
  change is wrong is a trade, and standing down the ones that stop it being
  unrecoverable - a force push, a destructive Terraform verb, a history
  rewrite, a secret read - is not. An incident is precisely when someone is
  tired enough to need that hook.
- **A repo can forbid it.** `emergency.standDown: false` in `.crew/config.json`
  keeps every gate gating; the incident is still declared, recorded, and named
  in the session brief. For a repository where skipping verification is not a
  decision anyone local gets to make.

Every session start says so while an incident is open, and keeps saying so
after it expires unclosed - `incidentActive` and `incidentUnclosed` are the two
highest-priority PM triggers, above `upgradeNeeded`, and the incident line sits
in the brief's quiet lines so no line cap can truncate it away.

Enforcement is session-local, like every other gate here: an incident stands
the hooks down for sessions in this repository on this machine. It does nothing
to CI or to branch protection.

### Commands — 20, all explicit

| Command | Purpose |
|---|---|
| `/crew:init` | Guided phased setup, resumable |
| `/crew:onboard [--refresh <area>]` | Build or refresh the code map |
| `/crew:reference [--api\|--features\|--audit]` | Enumerate endpoints, jobs, consumers, CLI commands and feature flags into `docs/reference/`, each anchored to `file:line` |
| `/crew:verify` | Build or refresh the change-to-check map the `Stop` gate reads, creating `_verify/` if the repo has no check directory |
| `/crew:promote <env> [--dry-run\|--status]` | Promote development -> qa -> production, running deploy, smoke, regression, and post-soak verification as separate gates |
| `/crew:emergency <what is broken>\|status\|extend [min]\|end` | Declare a time-boxed incident: the `verify` and `promote` gates stand down and record what they skipped, parallel read-only lanes investigate the cause at once, and `end` writes the debt list. The command guard does **not** stand down |
| `/crew:ticket <description>` | Scope a request into a ticket |
| `/crew:work <id>` | Work one ticket end to end |
| `/crew:review` | Independent QA — Codex, or the `qa-reviewer` agent as fallback |
| `/crew:plan <decision>` | Independent design opinion before building |
| `/crew:survey [area]` | Research gaps, produce ranked findings with options |
| `/crew:scale` | Evidence-based crew sizing |
| `/crew:docs [--audit]` | Update the documents this change should touch |
| `/crew:runbook <name\|--audit\|--verify>` | Write, verify, or audit operational runbooks |
| `/crew:handoff` | Write the handoff note before clearing |
| `/crew:diagram <type>` | Architecture, data-flow, process, and sequence diagrams |
| `/crew:jira-sync <KEY> [--push]` | Sync one issue with the local cache |
| `/crew:sdp-sync <REQUEST-ID> [--push]` | Sync one ServiceDesk Plus request with the local cache: pull the forty tokens that matter out of a several-thousand-token payload, push one note and a transition |
| `/crew:pm [assign\|onboard\|offboard <role>]` | Talk to the crew's manager: status with no argument, `assign` to let it decide and dispatch the next work itself, or add/remove a role. Offboarding still needs an explicit yes before it touches `.crew/config.json` |
| `/crew:upgrade [--force]` | Bring a pre-schema-2 (`v1`) setup forward: backs up the codemap first, builds the graph if missing, reconciles derived facts per subsystem, and reports contradictions and stale-on-purpose anchors rather than resolving them |

First run in a new repository: `/crew:init`, then `/crew:onboard`, then `/crew:verify`.

### Agents — 10, tiered plus the manager

Tier 0 installs with everyone; tiers 1 and 2 are added as the work demands. `/crew:scale` decides from evidence rather than taste.

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
| `pm` | read/write + `Agent` | — (outside the ladder) | The manager. Reads state, decides what the crew does next, and **dispatches the roles that do it**. Also does the heavy analysis that would cost more context in the main session than the answer is worth: correlating defect classes across `.crew/metrics.md`, auditing codemap anchors, assembling tier-change evidence |

`explorer`, `qa-reviewer`, `security`, `analyst`, `planner`, and `dba` are read-only — a restricted tool set is one of the three things that earns a role its place.

`pm` is the exception, and it is a deliberate one. A manager whose only output is a recommendation is a manager the user has to manage, so this one assigns work itself and reports afterwards. Three bounds keep that honest: a priority the user has stated **outranks** the PM's own trigger ordering and the PM says so when it re-orders; **removal and deletion still need an explicit yes** — offboarding a role, deleting a codemap or a diagram, rewriting `metrics.md`, because adding capability is reversible and removing it destroys the evidence that would say whether removing it was right; and a multi-agent run is **announced before** it happens, which is not a permission gate but the difference between a manager and a surprise. It writes only inside `.crew/` and `docs/diagrams/` — application source is always someone else's job.

### Bundled skills — 16

These are ordinary skills, scoped to `crew`'s own workflow. They work on every Claude surface, including chat, unlike the hooks and agents.

| Skill | What it covers |
|---|---|
| `crew-setup` | Platform detection **and toolchain resolution**, nine phased setup steps, provider wiring, and reconciling an existing repo `CLAUDE.md` against the template section by section |
| `crew-verification` | The change-to-check map, the `_verify/` layout, secrets handling, browser-test policy, and the five promotion gates for development -> qa -> production |
| `crew-context` | Context exhaustion — warn near the limit, write handoffs, resume after a clear or compact |
| `crew-docs` | Keeping `CHANGELOG.md`, `README.md`, `SECURITY.md`, `TODO.md` and ADRs current as work lands, plus the anchored API and feature reference under `docs/reference/` |
| `crew-lint` | Linters and formatters for PowerShell, PHP, Python, Terraform, and JavaScript, wired into the gate |
| `crew-terraform` | `terraform-docs` and `tflint` for a module — header block, `footer.md`, README injection |
| `crew-runbooks` | Writing, indexing, and maintaining operational runbooks |
| `crew-diagrams` | Architecture and data-flow diagrams, with a Visio path |
| `crew-providers` | Codex as reviewer, Gemini as design partner, and verifying either |
| `crew-memory` | Obsidian-backed memory |
| `crew-notify` | Teams and Telegram payload discipline |
| `crew-cloud` | AWS and Azure MCP |
| `crew-scaling` | Evidence for growing or shrinking the crew |
| `crew-pm` | Field meanings and the authority rule behind `/crew:pm` and the `pm-brief` / `pm-pulse` hooks — the PM dispatches work itself; a stated user priority outranks its ordering; removal and deletion still stop for an explicit yes |
| `crew-graph` | Building and querying the `graphify` code graph, the reconcile shape `/crew:upgrade` reads, and the Obsidian export consent gate |
| `find-skills` | Discovering and installing other skills |

### What it creates in a repository

Setup is nine resumable phases (`/crew:init`), and every artifact it writes is a file you can read and delete.

| Path | Written by | Holds |
|---|---|---|
| `.crew/config.json` | phase 1 | Provider, tracker, memory, context and notification settings |
| `.crew/verify.json` | phase 5 | Which checks a changed path requires, which specialist reviews it, and the promotion sequence per environment |
| `.crew/codemap/` | phase 4 | One note per subsystem, every claim anchored to `file:line` and a sha |
| `_verify/` | phase 3 | `smoke.sh`, `run-all.sh`, `cases/`, and a `README.md` recording what each check covers and when it last proved it could fail |
| `docs/reference/` | `/crew:reference` | Every endpoint and every headless capability, anchored |
| `.work/` | as work happens | Tickets, findings, the handoff note, and `PROMOTIONS.md` |
| `CLAUDE.md` | phase 1 | Created if absent; if present, missing sections are **appended, never overwritten** |

`.crew/` and `.work/` must be gitignored - the deploy gate writes a marker there, and an ungitignored marker dirties the tree and blocks the next deploy.

### Testing

Four committed suites, all sabotage-tested - three under `plugin/crew/hooks/scripts/_test/` and the pytest suite under `plugin/crew/tests/`:

| Suite | Cases | Covers |
|---|---|---|
| `run-tests.sh` | 95 | Every gate: what the command guard blocks and allows, root-level glob matching, the stop-loop exit, all four promotion preconditions, and the PM pulse — that `stop_hook_active` never blocks, that an unchanged state cannot interrupt twice, and that diagram freshness is read from the anchor rather than an mtime |
| `setup-walkthrough.sh` | 32 | Builds a mixed-stack scratch repo and runs every script phases 0-8 invoke |
| `validate-prompts.py` | 108 | Frontmatter, tool names, referenced agents and paths, read-only agents holding no write tools |
| `tests/` (pytest, one level up) | 306 | The Python behind the hooks: `crew_state`, `pm_brief`, `pm_pulse`, both flavours of `context-watch`, and the two gates that stand down. Run it — it is the suite that catches renderer regressions the shell suite cannot see, such as a new brief line squeezing the top finding out of a capped brief |

What none of them proves is whether the prompts produce good work. The 18 commands and 10 agents are instructions to a model; only a live session on a real ticket exercises those, which is what setup phase 7 is for.

### Optional integrations

All off unless configured: Codex as an independent reviewer, Gemini as a design partner, Jira over MCP, Obsidian for memory, and Teams or Telegram for notifications. `crew` works with none of them.

### Uninstall

```bash
claude plugin uninstall crew@useful-claude-add-ons
```

The hooks go with it. To keep the plugin but stop the `Stop` gate, set `verifyGate: false` in the repository's `.crew/config.json`.
