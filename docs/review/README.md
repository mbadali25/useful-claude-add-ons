---
title: crew review, September 2026
date: 2026-09-23
status: accepted as the input to the crew redesign
---

# crew review, September 2026

Three reviews of the `crew` plugin, written because sessions were slow and unfocused. They are
the input to the redesign in `04-redesign.md`. The owner has accepted their recommendations.

| File | By | Covers |
|---|---|---|
| `01-field-comparison-and-pain-points.md` | Claude Fable 5.1 researcher | crew compared with other Claude Code and Codex orchestration tools; each pain point traced to its root cause and fix; whether a more agentic setup would help |
| `02-memory-and-injection.md` | Claude Fable 5.1 researcher | Obsidian-compatible memory servers, how Claude Code and Codex inject context, and a hook design that pairs the codemap with memory |
| `03-codex-review.md` | Codex gpt-6-astra, effort `max` | independent review of the plugin code against both research reports |
| `04-redesign.md` | Claude Fable 5.1 and Codex gpt-6-astra, merged | the accepted crew 1.0 design and the owner's decisions; `04a`, `04b` and `04c` hold the two designs and their cross-reviews |
| `05-setup-audit.md` | Claude Fable 5.1 auditor | machine-wide plugins, skills, hooks, MCP servers and Codex config, with keep/remove/add tables and the missing hooks |

A published summary of 01 lives at https://claude.ai/artifact/DxYFsqXexjqW1CAe1xMLgq (private).

## Where the three reviews agree

- **Keep** the verification gates, commit-anchored codemap, graphify graph, cross-family Codex
  review, hard stops and bash/PowerShell parity. No surveyed tool has all of them.
- **Reshape** the orchestration. One interactive session owns an ordinary ticket. The standing PM
  and the Stop-hook pulse that hands maintenance work to every turn leave the default path.
- **Plan against a spec** (intent, exclusions, acceptance checks) and review against that spec.
  Limit review to two rounds, then re-plan.
- **Memory is layered and lives in the repo:** a short `AGENTS.md`/`CLAUDE.md`, path-scoped
  `.claude/rules/`, auto memory, and the codemap and graph. Obsidian is the human-readable
  knowledge store with **one** capture and recall owner.

## Where they disagree

| Question | Researcher | Codex |
|---|---|---|
| Memory server | basic-memory plus a custom injection hook | plain Markdown plus targeted search; add a database only after a demonstrated retrieval failure |
| Subagent `memory: project` | add it to reviewer roles | it silently grants Read/Write/Edit, so not harmless on read-only roles |
| Codex integration | move to `codex exec` | crew already uses `codex exec` (`plugin/crew/commands/review.md:399`) |
| Pulse cost | re-engages the PM every Stop | fingerprint dedup, a loop guard and a 12-pulse cap already exist (`plugin/crew/hooks/scripts/pm_pulse.py:359`) |

## Verified defects found during the review

- **`/crew:review` does not review uncommitted work.** It builds the patch with
  `git diff "$BASE"...HEAD` (`plugin/crew/commands/review.md:311`). On a dirty tree at
  `8b8a4028` that produced 0 bytes while `git diff HEAD` held about 100 KB, and untracked files
  never enter the patch.
- **A named PM cannot dispatch** when `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, because naming
  makes it a teammate. Fixed in the working tree as 0.20.15, uncommitted.
- **`/crew:upgrade` pinned built-in defaults**, including `pm.authority: report-only`, into the repo
  config, where they shadow the machine-global file. Fix in progress under 0.20.15.
- **A third-party plugin (dotnet-pilot) rewrote `~/.claude/settings.json` and `~/.claude/CLAUDE.md`
  before every tool call.** Disabled.

## Measured on this machine, 2026-09-23

- The plugin has 27,194 Markdown lines across 157 files. `agents/pm.md` is 991 lines.
- 53 roles are enabled. In 60 days of transcripts, **17 roles were ever dispatched and 36
  never were**. Counts are `subagent_type` occurrences in `~/.claude/projects` JSONL, which records
  each call more than once, so read them as a ranking, not a tally:

  | Role | Count | | Role | Count |
  |---|---|---|---|---|
  | developer | 154 | | python-pro | 12 |
  | scribe | 62 | | skill-author | 10 |
  | qa-reviewer | 56 | | researcher | 10 |
  | docs-writer | 52 | | browser-tester | 10 |
  | analyst | 44 | | planner | 6 |
  | dba | 36 | | php-pro | 4 |
  | explorer | 24 | | smoke-author, security, multi-agent-coordinator | 2 each |
  | pm | 16 | | | |

- Obsidian: two vaults. `/repos/claude-memories` holds 3,011 notes and is served over MCP;
  `~/Global Claude Vault` holds 7 files, has 0 ingests, and was the one injected at every session
  start. MCP vault tools were called **5 times in 305 sessions** over 30 days. **95 captured
  sessions** are waiting in `inbox/pending-reflect.md` for the gardener. Seven Obsidian-related
  plugins are enabled.

## Not verified

Billed tokens and wall-clock time per session; whether the missing uncommitted diff caused the
five-round review; live Windows behaviour of any recommendation.
