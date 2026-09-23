---
title: Independent review of the crew plugin
date: 2026-09-23
source: Codex gpt-6-astra, reasoning effort max, read-only, against the 0.20.15 working tree at 8b8a4028
status: input to the crew redesign
---

**Reshape crew substantially.** Keep its verification scripts, code maps, focused expertise, and independent review; make one interactive session responsible for ordinary tickets. Retire the always-active PM and automatic maintenance dispatch from the default workflow. The evidence supports testing this simplification, but neither research report proves how much time or money it will save here.

**What I measured**

- `plugin/crew` contains **27,194 Markdown lines across 157 files**. The PM agent alone is **991 lines**, with another **475** in its skill. This is the instruction inventory, not the amount loaded into every call.
- There are **54 agent files**, including PM. This repository enables all 53 other roles and configures autonomous PM operation with **13 dispatches** ([configuration](../../.crew/config.json:199)).
- Pure rendering of current state produced a **13-line, 207-word brief** and a **17-line, 463-word pulse**. One state collection took **0.087 seconds**. These measurements do not establish actual session totals.
- Crew registers six SessionStart and six Stop commands; per tool, Bash and PowerShell match one command each, Write/Edit two, and Read/Grep/Agent none. Platform pairs and deduplication affect actual execution ([hooks](../../plugin/crew/hooks/hooks.json:3)).
- Metrics contain **five review rounds for one ticket**, totaling **4 BLOCK and 23 FIX entries**. They contain no duration, cost, accepted-findings, or role-utilization data. The dispatch reader returned zero entries; that does not establish that no agents ran.

**Root causes**

| Pain | Assessment and evidence |
|---|---|
| Efficiency | **Crew worsens it.** PM must delegate even small engineering work, then perform coordination and reporting around it. Combined with the large instruction surface and 13-dispatch allowance, ordinary tickets can become management exercises. Mandatory delegation is explicit in [pm.md:84](../../plugin/crew/agents/pm.md:84). |
| Focus | **Crew introduces competing work.** The pulse tells agents to act on maintenance findings; user priority changes their ordering rather than removing them ([pm_pulse.py:261](../../plugin/crew/hooks/scripts/pm_pulse.py:261)). Scope enforcement is weaker than the prose suggests: `roleWrites` is currently `report`, and developer roles have no path restriction in this guard ([role_write_guard.py:27](../../plugin/crew/hooks/scripts/role_write_guard.py:27)). |
| Assumptions | **Crew both mitigates and creates them.** Debugging and evidence-labeling instructions help. Conversely, review-health logic interprets high findings as “tickets too large” and low findings as “review not catching defects,” without establishing either cause. Repeated findings across rounds accumulate; one ticket is enough for a verdict ([crew_state.py:279](../../plugin/crew/hooks/scripts/crew_state.py:279)). |
| Planning | **Crew mitigates it unevenly.** `/crew:work` already requires clear acceptance criteria, exploration, debugging for defects, and a plan before editing ([work.md:31](../../plugin/crew/commands/work.md:31)). PM’s direct developer routing does not establish the same mandatory sequence ([pm.md:527](../../plugin/crew/agents/pm.md:527)). Worse, `/crew:work` reviews before subsequent coverage and documentation changes ([work.md:186](../../plugin/crew/commands/work.md:186)). |
| Understanding | **Crew helps with anchored code maps but worsens instruction competition.** The repository’s 319-line instructions and global 112-line instructions add substantial context. Global typing rules contradict each other ([global CLAUDE.md:8](~/.claude/CLAUDE.md:8, machine-local)). More specialist personas cannot resolve conflicting authority or missing acceptance criteria. |
| Memory | **Crew adds accumulation without enough selection.** PM rereads its standing instructions in full, while only the journal has a bounded read ([pm.md:260](../../plugin/crew/agents/pm.md:260)). Multiple memory mechanisms lack a clearly established owner for current facts, superseded advice, and retrieval. |

**The most concrete correctness defect should come first:** `/crew:review` supplies `git diff "$BASE"...HEAD`, excluding uncommitted changes ([review.md:311](../../plugin/crew/commands/review.md:311)). On this dirty `main` checkout, that expression produced **zero bytes despite approximately 87 KB of tracked changes and three untracked files**. Untracked filenames enter context selection, but their contents do not enter the review patch. I cannot establish that this caused the historical five rounds, but it makes a clean verdict unreliable for the advertised working-diff review.

**Ranked directions**

1. **A thin crew around one session — recommended.** Delete automatic PM work orders and mandatory handoffs for routine implementation; retire redundant role wrappers after measuring their use. Keep verification gates, anchored code maps, diagnosis guidance, and independent Codex review. Build one compact ticket contract containing intent, exclusions, relevant evidence, unknowns, and observable acceptance checks. Build a scripted review adapter that supplies the complete intended change and records exactly what was reviewed. The evidence is concrete: mandatory coordination, competing maintenance work, inconsistent planning routes, and incomplete review input.

2. **The same core with optional native parallel execution.** Delete bespoke orchestration where native facilities provide the needed behavior; keep crew’s domain checks and task contract. Build a small workflow for demonstrably independent audits or migrations, initially limited to two workers. Native [workflows](https://code.claude.com/docs/en/workflows) provide the mechanism, but do not prove a speedup for dependent coding tasks. Worktrees also need explicit base selection and initialization of ignored crew/ticket state. Validate this on Windows and Linux before expanding it.

Replacing crew with another large framework would preserve the orchestration problem while adding migration cost.

**Obsidian**

Obsidian is reasonable for durable, human-readable knowledge. It is not, by itself, a memory strategy.

Keep current acceptance criteria and execution state beside the repository; keep architectural decisions and verified code-map anchors there too. Use Obsidian for selected cross-project knowledge, with provenance, dates, and supersession links. Crew’s existing [memory skill](../../plugin/crew/skills/crew-memory/SKILL.md:24) already recommends index-first retrieval and checking notes against code.

Choose **one capture/recall owner**. The sibling plugin’s gardener and reflector are not scheduled automatically ([README:150](../../plugin/obsidian-vault/README.md:150)); the separately installed vault plugin already injects context at SessionStart. Neither installation nor automatic injection proves useful recall. Plain Markdown plus targeted search is sufficient to start; another memory database is unnecessary without a demonstrated retrieval failure.

**Migration**

- **This week:** run a reversible, single-repository trial with `pm.enabled=false` and one interactive owner. Separately fix review input and move final review after all implementation, tests, and documentation changes. Preserve the existing verification requirements.
- **Next:** consolidate contradictory instructions into a short shared entry point; move incident history into referenced notes. Persist a per-ticket review-attempt budget. After two rounds, unresolved blockers trigger diagnosis or replanning, never automatic approval. Record duplicate/rejected findings separately from confirmed defects.
- **Then:** compare 10–20 reasonably matched tickets using elapsed time, human intervention, tokens/cost, scope violations, confirmed defects, and escaped defects. Adopt a target such as 30% lower time or cost without worse quality as a decision criterion, not a promised result. Remove unused orchestration only after this trial; introduce parallel execution selectively.

**Disagreements with the research**

- Planning and exploration are already present in `/crew:work`; their absence is not the diagnosis.
- A one-rerun instruction already exists ([review.md:457](../../plugin/crew/commands/review.md:457)). Another prose limit will not make it durable across sessions.
- Current pulse code has fingerprint deduplication, a loop guard, and a 12-pulse cap; “every Stop always restarts PM” overstates current behavior ([pm_pulse.py:359](../../plugin/crew/hooks/scripts/pm_pulse.py:359)).
- Crew already uses `codex exec`; it does not need migration away from `codex mcp-server` ([review.md:399](../../plugin/crew/commands/review.md:399)).
- Native subagent memory is not a harmless replacement for read-only roles: enabling it automatically enables Read, Write, and Edit ([official documentation](https://code.claude.com/docs/en/sub-agents)).
- Claims of superior gates or proven framework efficiency exceed the available comparative evidence.

**Limits**

I reviewed both reports and the changing, uncommitted 0.20.15 tree at `8b8a4028`; the installed registry currently reports 0.20.14. Historical upgrade-default pinning reproduces in committed code, while a pending working-tree fix addresses new default pins. Dotnet-pilot is currently disabled. I could not verify the 100-minute timeline, actual billed tokens, findings’ validity, live Claude dispatch behavior, or Windows execution. I modified no files and did not run mutation-producing hooks or tests.