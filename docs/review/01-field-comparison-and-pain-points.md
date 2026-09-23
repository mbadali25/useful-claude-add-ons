---
title: crew vs the field, and the pain points
date: 2026-09-23
source: Claude Fable 5.1 researcher agent, two passes, vendor docs fetched 2026-09-23
status: input to the crew redesign
---

Research is complete. Two reports follow: the original brief (landscape, scorecard, architectures) and the widened one (pain points, memory, "would agentic be better"). One combined source list at the end serves both.

Note on sourcing: Context7's tools were advertised in MCP instructions but never surfaced as callable functions this session, so every vendor claim below is from the vendor's own doc site fetched directly, labelled as such. Star counts are from the GitHub API on 2026-09-23. Repo reads were limited to `README.md`, `hooks/hooks.json`, `plugin.json`, `agents/pm.md` (first 120 lines), `skills/crew-pm/SKILL.md` (first 100), the `commands/`/`agents/`/`hooks/scripts/` listings, and `plugin/obsidian-vault/README.md` plus `agents/gardener.md`; nothing else was traced.

---

# Report 1: crew vs the field

## 1. Executive verdict

crew's *gates* (deterministic hooks, cross-family review, commit-anchored codemap, sabotage-tested guards) are ahead of every community framework surveyed; its *orchestration* (an Opus PM re-engaged on every Stop, dispatching from a 53-role roster, with each spawn re-loading the CLAUDE.md hierarchy) is the part the platform has since absorbed and the part both Anthropic's and Cognition's evidence says is the wrong shape for coding work. The earlier pass was right on the platform facts but its star counts were stale by 2x, and it overstated the "teammates cannot spawn agents" rule that motivated the unnamed-PM change. Keep the gates, shrink the org chart, move fan-out onto native workflows, and make Codex a `codex exec` reviewer rather than an MCP peer, because `codex mcp-server` has been removed.

## 2. Ranked recommendations

**1. Single Claude session + plan mode + spec files + Codex reviewer via `codex exec` (recommended).** Orchestrator is the interactive session, not a subagent. Keep crew's three roles that buy isolation or independence by its own rule (`README.md:50-54`: explorer, security, qa-reviewer), `verify-gate`, `role-write-guard`, `promote-gate`, `handoff-read/write`, codemap and graphify. Delete: the PM agent and `pm-pulse`, the other ~50 roles (convert any with real domain content into skills, which load on demand), the `multi-agent-coordinator`/`workflow-orchestrator` agents. Make `AGENTS.md` the canonical instruction file: Claude Code reads it natively; Codex does not read `CLAUDE.md` unless added to `project_doc_fallback_filenames`, and stops at 32 KiB by default. Migration: (i) move `CLAUDE.md` body into `AGENTS.md` ≤200 lines plus `.claude/rules/` path-scoped files; (ii) add a `/spec` skill producing `requirements/design/tasks` (Kiro shape) or adopt Spec Kit; (iii) wire `codex exec --json` into `crew:review`; (iv) retire the PM last, after two weeks of `pm-journal.md` showing it added no dispatch a human would not have made. Tradeoff: you lose "the crew decides what's next"; you gain roughly one context load per task instead of one per role.

**2. Option 1 plus Claude Code dynamic workflows for fan-out.** For audits, migrations, per-file review and cross-checked research, save a `.claude/workflows/*.js` script (shippable in the plugin's `workflows/` dir, namespaced `/crew:<name>`). Defaults: 16 concurrent agents (1–256 via `CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS`), 1,000 agents/run, 4,096 items per `parallel()`, resumable within the session, `schema` on `agent()` for typed returns. This replaces PM-dispatched parallel roles with something rerunnable and inspectable. Tradeoff: no mid-run human input; script is JS with no imports.

**3. Cross-agent runner (vibe-kanban local mode or claude-squad) with worktrees.** Only if you want Codex *implementing* in parallel lanes. Weak fit: claude-squad is tmux-based (no Windows story), vibe-kanban's company shut down 2026-04-10 (community-maintained, local mode works), Crystal is deprecated (Feb 2026) for Nimbalyst, Conductor is macOS-only. Native `claude --worktree` plus `isolation: worktree` subagents covers most of this without a third tool.

## 3. Comparison table

| Tool | Orchestration | Memory/state | Autonomy gating | Cross-model review | Windows | Adoption (2026-09-23) |
|---|---|---|---|---|---|---|
| **crew** | Opus PM subagent, Stop-hook pulse, 53 roles | `.crew/` JSON, codemap, pm-journal | report/act/autonomous tiers, hook guards | Codex→Copilot→Claude | bash+ps1 pairs, tested | 1 author |
| Claude Code agent teams | lead + teammates, shared task list | `~/.claude/teams`, tasks persist | inherits lead mode; TeammateIdle/TaskCompleted hooks | none | split panes not in Windows Terminal | experimental, env-gated |
| Claude Code workflows | script holds the plan | script vars, resumable | per-run approval; `Workflow` allow rule | adversarial cross-check pattern | yes | all paid plans |
| wshobson/agents | 16 orchestrators, 202 agents, multi-harness | Pensyve integration | model tiers | no | not stated | 39,908 stars |
| Ruflo (ex claude-flow) | queen-led swarm, GOAP | AgentDB/HNSW | trust scoring | multi-provider incl. Codex | native PowerShell | 73,143 |
| obra/superpowers | skills, subagent-driven dev, worktrees | design docs | TDD/verification skills | supports 18 agents incl. Codex | not documented | 290,573 |
| BMAD-METHOD | role workflows, phases | carried decisions | phase gates | Claude Code + Codex plugins | not stated | 53,389 |
| SuperClaude | 20 agents, 7 modes, 30 commands | Serena MCP `/save` `/load` | modes | no | not stated | 23.9k (page) |
| VoltAgent subagents | catalogue, 161+ | none | none | no | n/a | 25.3k (page) |
| Codex subagents | parallel workers, TOML in `.codex/agents/` | none documented | `max_concurrent_threads_per_session` | n/a | native sandbox in PowerShell | GA by default |
| Spec Kit | constitution→specify→plan→tasks→implement→converge | spec files in repo | human gates between phases | agent-agnostic | yes | 138.6k |
| vibe-kanban / claude-squad / Crystal | kanban or tmux over worktrees | none | none | drives both CLIs | vk yes; squad no; Crystal deprecated | 28,173 / 8,525 / 3.1k |

## 4. Design-choice scorecard

| Choice | Verdict | Evidence |
|---|---|---|
| Prose instruction surface vs scripts | **Behind** | Anthropic: instructions are "context, not enforced configuration"; enforce with hooks. crew already has the hooks; the prose around them (this repo's CLAUDE.md is thousands of words vs the ≤200-line guidance, and `README.md:58` warns every subagent reloads it) is the cost. |
| 53 roles vs few generalists + skills | **Behind** | `README.md:46-56` itself says a persona adds no capability; field moved to skills (superpowers) and workflows. Codex ships three built-ins (`default`, `worker`, `explorer`). |
| Hook-driven PM pulse on Stop | **Behind** | Cognition: single-threaded agent + compression; Anthropic: coding has few parallelizable tasks, ~15x tokens. `pm.md:31-40` rationale overstated: docs say teammates cannot spawn *teammates* or *background* subagents, but foreground subagents are allowed, and naming only makes a teammate when `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` and the session is interactive. |
| Commit-anchored codemap + graphify + Mermaid | **Ahead** | No surveyed tool has verifiable, dated anchors. Matches Anthropic's "structured note-taking". |
| Authority tiers + hard stops | **Par** | Equivalent to plan/acceptEdits/auto modes plus ask rules; crew's are prose, the platform's are enforced. |
| Cross-family review | **Ahead** | Only Ruflo and BMAD touch Codex; none make a different family the default reviewer. |
| Dual bash/PowerShell hooks | **Par, correct** | `shell: powershell` is the documented mechanism; both registrations firing per event is the documented cost. |
| Memory in `.crew/pm-journal.md` | **Behind** | Native subagent `memory: project` and auto memory (first 200 lines/25 KB) do this without custom scripts. |

## 5. Quick wins

1. Cut `CLAUDE.md` to a ≤200-line router; move sections to `.claude/rules/*.md` with `paths:`. Every spawn pays for it today.
2. Rename/copy to `AGENTS.md`; Claude Code reads it, Codex only reads it.
3. Replace `pm-journal.py` with `memory: project` frontmatter on `pm`, `qa-reviewer`, `explorer`.
4. In `crew:review`, call `codex exec --json` with the ticket's acceptance criteria in the prompt so each round reviews against a spec, not the diff alone.
5. Set `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=0` in project settings so a stray `name` can never convert a role into a teammate, then the unnamed-PM rule becomes belt-and-braces instead of load-bearing.

## 6. Sources: see combined list after Report 2.

## 7. Could not determine

Claude Code docs never use the word "GA" for workflows (only "available on all paid plans"); whether Codex subagents nest (changelog mentions "nested subagent token usage" but the subagents page does not document it); SuperClaude/VoltAgent Windows support; Ruflo's real-world reliability (stars measured, quality not); whether `crew:review` re-sends the full diff each round (repo code not traced; that is `crew:analyst`'s).

---

# Report 2: pain points, memory, and "would agentic be better?"

## 1. Pain point → root cause → fix

| Pain | Root cause in crew | What the field does | Fix |
|---|---|---|---|
| **Efficiency** (tokens, turns, 5 Codex rounds) | Every Stop fires six hook entries (`hooks.json:29-36`), one being `pm-pulse` that can re-spawn an Opus PM; each role spawn reloads the CLAUDE.md hierarchy (`README.md:58`); review is post-hoc against a diff with no spec (`crew-pm/SKILL.md:56-58` routes review to Codex, but nothing gives Codex acceptance criteria). | Anthropic: smallest high-signal token set, just-in-time retrieval; Spec Kit's `converge` and Kiro's `tasks.md` make "done" checkable before review; workflows cross-check findings once, in-script. | Spec first (Kiro-shape files in `.work/<ticket>/`), then implement, then one Codex `exec` round reviewing against the spec; cap rounds at two and escalate to a human on the third. Remove `pm-pulse` from Stop. |
| **Focus drift** | Guards protect paths for the PM (`role_write_guard.py`, `pm.md:105-109`) but developers get prose ("Scope discipline" in CLAUDE.md), and prose is not enforced. | Worktree isolation blocks edits to the main checkout; `tasks.md` with one task per turn; `TaskCompleted` hooks reject completion. | `claude --worktree <ticket>` per ticket; a `PreToolUse` Edit guard that allows only paths listed in the ticket's spec; TDD skill (superpowers) so "nearby fixes" fail a test they did not write. |
| **Assumptions** | The PM is told to label claims (`pm.md` "Every claim is labeled") but nothing checks it; roles lack a read-only exploration phase. | Plan mode is read-only until a plan is approved; workflow `agent()` with `schema` forces typed answers; superpowers `verification-before-completion`. | Start every ticket in `--permission-mode plan`; require the plan to cite `path:line` from the codemap; make the Stop `verify-gate` the only thing that can mark a ticket done. |
| **Planning** | `/crew:plan` and `/crew:ticket` exist but are optional; `/crew:work` "picks up a ticket and works it end to end". | Spec Kit (constitution→specify→plan→tasks, human gate each phase), Kiro (`requirements.md` EARS, `design.md`, `tasks.md` with dependency waves), BMAD (Clarify→Plan→Build→Learn). | Make `/crew:work` refuse a ticket without `requirements.md` and `tasks.md`. Adopt Spec Kit if you want a maintained tool (138.6k stars, Windows, agent-agnostic so Codex reads the same spec). |
| **Understanding** | The codemap is the right artifact but lives in prose the PM summarises; 53 roles each rediscover it. | Nested `CLAUDE.md` and `.claude/rules` load on demand when files are read; just-in-time retrieval over lightweight identifiers. | Keep graphify + codemap; add `.claude/rules/<subsystem>.md` with `paths:` that point at the codemap file for that subsystem, so the map loads exactly when the code does. |

## 2. Memory

Two vault plugins on one host means two capture paths (`obsidian-vault`'s `vault-capture` on SessionEnd/PreCompact writing `inbox/pending-reflect.md`, plus `vault`'s ingest queue) feeding two distillers, and neither is read back automatically at session start except through prose instructions. That is why it "doesn't seem right": capture is automatic, recall is not.

| Option | Loads how | Fit |
|---|---|---|
| CLAUDE.md / AGENTS.md | every session, whole file | rules and routing only; ≤200 lines |
| `.claude/rules/` with `paths:` | when matching files are read | subsystem knowledge, codemap pointers |
| Auto memory | first 200 lines/25 KB of `MEMORY.md`, per repo | corrections and preferences; on by default |
| Subagent `memory: project` | per agent, versioned in repo | reviewer/explorer learnings |
| Obsidian vault (gardener) | only via MCP or manual read | human-curated decisions; slow past 50k notes (`obsidian-vault/README.md:55-59`) |
| basic-memory (4.0k) | MCP, markdown, Obsidian-compatible | if you want one vault both humans and MCP write |
| mem0 (65.9k) / Graphiti (31.1k) | MCP, vector or temporal graph, needs a DB and LLM key | overkill for one developer; adds a service to run on two OSes |
| Code graph (graphify) | file read | structure, not decisions |

**Recommendation:** AGENTS.md router + `.claude/rules/` + auto memory on + `memory: project` for `qa-reviewer`, `explorer`, `security` + graphify. Uninstall one of the two vault plugins. Keep Obsidian only as a human decision log the gardener writes to; if you want it machine-readable too, replace the REST bridge with basic-memory rather than adding mem0 or Graphiti.

## 3. Would agentic systems be better?

Agentic versus what: crew *is* an agentic system; the question is which shape.

| Shape | Evidence | Fit for these pains |
|---|---|---|
| (a) One agent + skills + plan mode + Codex reviewer | Cognition (2025-06-12): single-threaded agent with a compression layer; share full traces; conflicting implicit decisions come from parallel workers. Anthropic (2025-06-13): multi-agent is for breadth-first research, ~15x tokens, "most coding tasks involve fewer truly parallelizable tasks". | **Best.** Directly attacks tokens, drift and lost context. |
| (b) Deterministic workflow | Claude Code workflows: script holds the loop, results stay out of context, adversarial cross-check built in. | Best for audits, migrations, per-file review. Not for a single ticket. |
| (c) Fuller autonomous framework (Ruflo, agent teams, BMAD party mode) | Anthropic: pay only when task value covers the token multiple; teams are experimental, no resume, task status lags. | Worst fit: amplifies every pain listed. |
| crew today | Sits between (a) and (c): PM re-engaged by hook, roles per domain. | Its gates belong in (a); its dispatch belongs in (b) or nowhere. |

Plain answer: no, a *more* agentic system would not help. A less agentic core with crew's gates kept, spec-first planning, and workflows reserved for genuinely parallel jobs fits this user.

## 4. Spec-driven options, where they land

Spec Kit for the planning gate (agent-agnostic, Windows, phases with human approval); Kiro's three-file shape if you prefer in-repo files without a tool; BMAD if you want role-based planning but it reintroduces personas, which is the thing to shrink.

---

## Sources

**Verified (fetched):**
- https://code.claude.com/docs/en/agent-teams — experimental, env var, named→teammate (interactive only), no nested teams, foreground-only subagents, TeammateIdle/TaskCreated/TaskCompleted, split panes unsupported in Windows Terminal (undated; cites v2.1.257)
- https://code.claude.com/docs/en/workflows — paid plans, 16 concurrent default, 1,000/run, 4,096 items, resumable, `.claude/workflows/`, plugin `workflows/` (cites v2.1.271)
- https://code.claude.com/docs/en/sub-agents — nesting depth 3 default, `memory:` scopes, 200 lines/25 KB
- https://code.claude.com/docs/en/hooks — 33 events, `shell: powershell`
- https://code.claude.com/docs/en/memory — CLAUDE.md ≤200 lines, AGENTS.md read natively, auto memory
- https://code.claude.com/docs/en/worktrees — `--worktree`, `isolation: worktree`, Windows junction note
- https://code.claude.com/docs/en/agents — status labels per approach
- https://code.claude.com/docs/en/permission-modes — plan mode, Bash sandbox macOS/Linux/WSL2 only
- https://platform.claude.com/docs/en/managed-agents/memory — beta `agent-memory-2026-07-22`, platform API, 8 stores/session
- https://learn.chatgpt.com/docs/agent-configuration/subagents, /agents-md, /cloud, /mcp-server (removal), /app-server, /codex/cli, /sandboxing, /windows/windows-sandbox, /changelog (2026-09-23)
- https://www.anthropic.com/engineering/multi-agent-research-system (2025-06-13); https://cognition.com/blog/dont-build-multi-agents (2025-06-12); https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents (2025-09-29)
- https://kiro.dev/docs/specs/ (updated 2026-08-27); https://github.com/github/spec-kit
- GitHub API 2026-09-23: ruvnet/ruflo, obra/superpowers, wshobson/agents, bmad-code-org/BMAD-METHOD, BloopAI/vibe-kanban, smtg-ai/claude-squad; repo pages: SuperClaude, VoltAgent, container-use, stravu/crystal, mem0, graphiti, basic-memory; https://conductor.build/; https://www.vibekanban.com/blog/shutdown (2026-04-10)

**Unverified (search snippets only):**
- Codex subagents "GA March 2026" and Windows native sandbox "released March 2026" (third-party blogs)
- Codex changelog line about nested subagent token budgets (from gradually.ai summary, not the primary changelog text)

**Not checked:** SuperClaude/VoltAgent/container-use Windows behaviour; Spec Kit's current agent list; whether `crew:review` resends full diffs per round (repo code, belongs to `crew:analyst`).