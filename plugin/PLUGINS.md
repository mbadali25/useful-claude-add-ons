# Plugin reference

What each plugin in [`plugin/`](.) actually contains, and — for the parts that execute on their own — what starts running the moment it is enabled. The one-line catalog is in [`README.md`](README.md); this is the detail behind it.

Read the **Hooks** section of any plugin before installing it. Commands and agents wait to be asked. Hooks do not.

---

## `crew` — virtual dev team for multi-repo legacy work

| | |
|---|---|
| **Source** | [`crew/`](crew) |
| **Version** | 0.2.0 |
| **Install** | `claude plugin install crew@useful-claude-add-ons` |
| **Menu item** | 21, `repo-plugins` — **off by default** |
| **Registers** | 9 agents, 14 commands, 14 skills, 7 hooks across 5 events |
| **Upstream guide** | [`crew/README.md`](crew/README.md) — 20 sections, the authoritative version |

Built for the awkward case: several repositories, mixed stacks, legacy code, and almost no test coverage. The workflow is file-backed tickets, one implementation session, an independent reviewer, and deterministic gates that block on failure rather than offering an opinion.

Its central design claim is worth repeating, because it is the opposite of how most agent bundles are built: **a persona in a prompt adds no capability.** A role earns its place only if it buys an isolated context window, a restricted tool set, or genuinely independent eyes. Project management, business analysis, architecture, documentation, and training are files, commands, or you — there is nothing for an agent to isolate. Every custom subagent also loads your entire `CLAUDE.md` hierarchy at startup, so a 4,000-token `CLAUDE.md` across eight delegations is 32,000 tokens of overhead before any work happens.

### Hooks — the part that runs without being asked

Seven hook entries across five events. **These are why menu item 21 is unticked by default.**

| Script | Event | What it does |
|---|---|---|
| `guard.sh` | `PreToolUse` on the Bash tool | Blocks `terraform apply`/`destroy`, destructive DDL, force push, hard reset, prod-targeted commands, and any command that would print a secret value into the transcript |
| `guard.ps1` | `PreToolUse` on the PowerShell tool | The same guard, registered with `shell: powershell` |
| `verify-gate.sh` | `Stop` | Runs the checks the changed paths map to; **fails the turn** on red, or on a changed path with no rule |
| `context-watch.sh` | `Stop` | Estimates context use and asks for a handoff once per session |
| `handoff-write.sh` | `PreCompact` | Snapshots the transcript and writes a skeleton handoff before compaction discards it |
| `handoff-read.sh` | `SessionStart` | Injects that handoff back after a clear, compact, or resume |
| `notify.sh` | `Notification`, and called directly by commands | One outbound line to Teams or Telegram. Never reads, never accepts instructions |

A hook cannot be argued out of blocking `terraform apply`; an agent can. That is the entire value, and also the reason a bootstrap run should not install one without the box being ticked.

**The `Stop` gate is inert until you build its map.** `verify-gate.sh` reads `.crew/verify.json`; with no such file there is nothing to run. `/crew:verify` builds it. Set `verifyGate: false` in `.crew/config.json` to disable the gate without uninstalling.

**Known gap — the Windows dispatch is incomplete.** Only `PreToolUse` pairs a `.sh` with a `shell: powershell` twin, because there the branch is chosen by *which tool Claude used*, not by which OS you are on. The other five entries invoke `bash` unconditionally. `verify-gate.ps1`, `context-watch.ps1`, and `handoff-read.ps1` all exist on disk but nothing in `hooks.json` references them, and `handoff-write.sh` has no `.ps1` at all. On a Windows machine with no `bash` on `PATH`, the `Stop` verification gate, the context watch, and both halves of the handoff cycle never fire — and nothing says so, which reads as "the gate passed" rather than "the gate never ran". `crew/README.md`'s hook table currently describes `verify-gate.ps1` as registered; it is not. Tracked, not fixed here.

### Commands — 14, all explicit

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

First run in a new repository: `/crew:init`, then `/crew:onboard`, then `/crew:verify`.

### Agents — 9, tiered

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

`explorer`, `qa-reviewer`, `security`, `analyst`, `planner`, and `dba` are read-only — a restricted tool set is one of the three things that earns a role its place.

### Bundled skills — 14

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
| `find-skills` | Discovering and installing other skills |

### Optional integrations

All off unless configured: Codex as an independent reviewer, Gemini as a design partner, Jira over MCP, Obsidian for memory, and Teams or Telegram for notifications. `crew` works with none of them.

### Uninstall

```bash
claude plugin uninstall crew@useful-claude-add-ons
```

The hooks go with it. To keep the plugin but stop the `Stop` gate, set `verifyGate: false` in the repository's `.crew/config.json`.
