# Plugin reference

What each plugin in [`plugin/`](.) actually contains, and — for the parts that execute on their own — what starts running the moment it is enabled. The one-line catalog is in [`README.md`](README.md); this is the detail behind it.

Read the **Hooks** section of any plugin before installing it. Commands and agents wait to be asked. Hooks do not.

---

## `crew` — virtual dev team for multi-repo legacy work

| | |
|---|---|
| **Source** | [`crew/`](crew) |
| **Version** | 0.3.0 |
| **Install** | `claude plugin install crew@useful-claude-add-ons` |
| **Menu item** | 21, `repo-plugins` — **off by default**. Menu item 22, `graphify`, is a separate, also-off-by-default install of the `graphify` CLI this plugin's graph feature depends on — see **The code graph** below. |
| **Registers** | 10 agents, 16 commands, 16 skills, 14 hook entries (7 scripts × `.sh`/`.ps1`) across 5 events |
| **Upstream guide** | [`crew/README.md`](crew/README.md) — 24 sections, the authoritative version |

Built for the awkward case: several repositories, mixed stacks, legacy code, and almost no test coverage. The workflow is file-backed tickets, one implementation session, an independent reviewer, and deterministic gates that block on failure rather than offering an opinion.

Its central design claim is worth repeating, because it is the opposite of how most agent bundles are built: **a persona in a prompt adds no capability.** A role earns its place only if it buys an isolated context window, a restricted tool set, or genuinely independent eyes. Project management, business analysis, architecture, documentation, and training are files, commands, or you — there is nothing for an agent to isolate. Every custom subagent also loads your entire `CLAUDE.md` hierarchy at startup, so a 4,000-token `CLAUDE.md` across eight delegations is 32,000 tokens of overhead before any work happens.

### Hooks — the part that runs without being asked

Seven scripts across five events, each shipped as a `.sh`/`.ps1` pair
registered on its own event — 14 hook entries. **These are why menu item 21
is unticked by default.**

| Script | Event | What it does |
|---|---|---|
| `guard.sh` / `.ps1` | `PreToolUse` on the Bash / PowerShell tool | Blocks `terraform apply`/`destroy`, destructive DDL, force push, hard reset, prod-targeted commands, and any command that would print a secret value into the transcript |
| `handoff-read.sh` / `.ps1` | `SessionStart` | Injects the prior handoff back after a clear, compact, or resume |
| `pm-brief.sh` / `.ps1` | `SessionStart` | Runs `crew_state.py` and prints a prioritized brief — schema currency, a stale or missing code graph, a pending handoff, review health, ticket sizing. Report-only: it never writes anything |
| `verify-gate.sh` / `.ps1` | `Stop` | Runs the checks the changed paths map to; **fails the turn** on red, or on a changed path with no rule |
| `context-watch.sh` / `.ps1` | `Stop` | Estimates context use and asks for a handoff once per session; instructs a full wrap-up instead if `context.autoWrapUp` is `true` |
| `handoff-write.sh` / `.ps1` | `PreCompact` | Snapshots the transcript and writes a skeleton handoff before compaction discards it |
| `notify.sh` / `.ps1` | `Notification`, and called directly by commands | One outbound line to Teams or Telegram. Never reads, never accepts instructions |

**This is what "the moment the plugin is enabled" means in practice: a `SessionStart` hook now fires on every session's `startup`, unconditionally, in a repository with `.crew/config.json` present.** `handoff-read` and `pm-brief` both run before you type anything — the PM brief in particular is new in 0.3.0 and is the first thing a reader needs to know exists, because it means enabling the plugin changes what the very first turn of every session looks like, not just what later tool calls are allowed to do.

A hook cannot be argued out of blocking `terraform apply`; an agent can. That is the entire value, and also the reason a bootstrap run should not install one without the box being ticked.

**The `Stop` gate is inert until you build its map.** `verify-gate.sh` reads `.crew/verify.json`; with no such file there is nothing to run. `/crew:verify` builds it. Set `verifyGate: false` in `.crew/config.json` to disable the gate without uninstalling.

**Both flavours are registered on every matcher-less event on purpose**, not because each one fires — `hooks.json` has no way to know in advance which shell a given machine actually has, so both are wired and one is expected to fail. On Windows this is not hypothetical: measured, Git for Windows' `usr/bin/bash.exe` exits 127 running these scripts where its own `bin/bash.exe` runs them fine, so which `bash` resolves first on `PATH` decides whether the `.sh` side works at all. On the machine this was measured on it is neither of those: from a non-MSYS parent — which is what spawns a hook — `bash` resolved to `C:\Windows\System32\bash.exe`, the WSL launcher, which cannot open a Windows path at all and exits 127 on every one of these scripts while the `.ps1` twin exits 0. The `.ps1` twin is what actually gates the machine in that case. **One flavour failing is expected behavior, not a bug** — it is not evidence the hook itself didn't run. What is genuinely unverified is the opposite combination, real hook-runner behavior with **no `pwsh` on Linux**; that was never exercised, so treat it as unconfirmed rather than assumed fine.

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

### Commands — 16, all explicit

| Command | Purpose |
|---|---|
| `/crew:init` | Guided phased setup, resumable |
| `/crew:onboard [--refresh <area>]` | Build or refresh the code map |
| `/crew:verify` | Build or refresh the change-to-check map the `Stop` gate reads |
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
| `/crew:pm [onboard\|offboard <role>]` | Talk to the crew's manager: status with no argument, or add/remove a role with explicit yes/no confirmation before either touches `.crew/config.json` |
| `/crew:upgrade [--force]` | Bring a pre-schema-2 (`v1`) setup forward: backs up the codemap first, builds the graph if missing, reconciles derived facts per subsystem, and reports contradictions and stale-on-purpose anchors rather than resolving them |

First run in a new repository: `/crew:init`, then `/crew:onboard`, then `/crew:verify`.

### Agents — 10, tiered plus one report-only

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
| `pm` | Read, Bash, Grep, Glob — **no `Write`** | — (outside the ladder) | Heavy crew-management analysis in its own context: correlates defect classes across `.crew/metrics.md`, audits codemap anchors, assembles tier-change evidence. Report-and-recommend only |

`explorer`, `qa-reviewer`, `security`, `analyst`, `planner`, `dba`, and `pm` are read-only — a restricted tool set is one of the three things that earns a role its place. `pm` is deliberately more restricted than that: it holds no `Write` tool at all, so in practice it writes nothing — not `config.json`, not `metrics.md`, not even a report file. Its final message is the report. Role and tier changes always need the user's explicit yes in the session that invoked it; the agent itself is structurally incapable of applying one.

### Bundled skills — 16

These are ordinary skills, scoped to `crew`'s own workflow. They work on every Claude surface, including chat, unlike the hooks and agents.

| Skill | What it covers |
|---|---|
| `crew-setup` | Platform detection, phased setup, provider wiring, the repo `CLAUDE.md` template |
| `crew-verification` | The change-to-check map, secrets handling, browser-test policy |
| `crew-context` | Context exhaustion — warn near the limit, write handoffs, resume after a clear or compact |
| `crew-docs` | Keeping `CHANGELOG.md`, `README.md`, `SECURITY.md`, `TODO.md`, and ADRs current as work lands |
| `crew-lint` | Linters and formatters for PowerShell, PHP, Python, Terraform, and JavaScript, wired into the gate |
| `crew-terraform` | `terraform-docs` and `tflint` for a module — header block, `footer.md`, README injection |
| `crew-runbooks` | Writing, indexing, and maintaining operational runbooks |
| `crew-diagrams` | Architecture and data-flow diagrams, with a Visio path |
| `crew-providers` | Codex as reviewer, Gemini as design partner, and verifying either |
| `crew-memory` | Obsidian-backed memory |
| `crew-notify` | Teams and Telegram payload discipline |
| `crew-cloud` | AWS and Azure MCP |
| `crew-scaling` | Evidence for growing or shrinking the crew |
| `crew-pm` | Field meanings and the report-only authority rule behind `/crew:pm` and the `pm-brief` hook |
| `crew-graph` | Building and querying the `graphify` code graph, the reconcile shape `/crew:upgrade` reads, and the Obsidian export consent gate |
| `find-skills` | Discovering and installing other skills |

### Optional integrations

All off unless configured: Codex as an independent reviewer, Gemini as a design partner, Jira over MCP, Obsidian for memory, and Teams or Telegram for notifications. `crew` works with none of them.

### Uninstall

```bash
claude plugin uninstall crew@useful-claude-add-ons
```

The hooks go with it. To keep the plugin but stop the `Stop` gate, set `verifyGate: false` in the repository's `.crew/config.json`.
