---
name: crew-best-practices
description: Community best practices for working with Claude Code - context management, planning, TDD, hooks, skills, subagents, slash commands and MCP - with what crew already does, where crew departs on purpose, and what is genuinely unsettled. Use when asked how to use Claude Code well, whether a practice is worth adopting, why crew is built the way it is, or when auditing a repo's CLAUDE.md, hooks or skill layout against community consensus.
---

# Claude Code best practices, and where crew stands on each

Source: <https://rosmur.github.io/claudecode-best-practices/> — a synthesis of
roughly twelve practitioner sources. Audited against crew on 2026-09-17.

**Read it as practitioners, not as a specification.** Its own §5 records five
contradictions between its sources, unresolved. Where it disagrees with itself,
this skill says so rather than picking a side and presenting it as consensus.

## The three claims it puts above the rest

1. **Context management is the primary failure mode.** Not model capability —
   context degradation.
2. **Planning before implementation is non-negotiable** for production code.
3. **Simplicity beats complexity.** Every abstraction layer makes debugging
   exponentially harder.

## What to do about it here

| If you are... | Do this |
|---|---|
| Asked "how should I use Claude Code" | Answer from `references/practices.md`, not from memory |
| Auditing a repo's CLAUDE.md | `references/claude-md.md` has the size limits and the anti-patterns |
| Asked why crew has 54 agents or 26 commands | `docs/adr/0003-crew-departs-from-three-community-best-practices.md` |
| Tempted to "fix" crew to match the document | Read the ADR first. Three departures are deliberate |
| Adding a hook, skill or command | `references/practices.md` §Hooks, §Skills, §Commands |

## Already true of crew — do not re-implement

Claiming these as gaps wastes a session. Each is checked, with where it lives:

| Practice | Crew |
|---|---|
| Plan before coding | `/crew:plan`, the `planner` role |
| Aggressive context clearing | `context-watch` hook, `context.warnAt` 0.5 since 0.19.52 |
| "Document & Clear" pattern | `handoff-write` (PreCompact) + `handoff-read` (SessionStart) |
| Quality-gate hooks | `verify-gate` on Stop, over `.crew/verify.json` |
| Multi-instance review | `/crew:review` — prefers a different model family, not a clone |
| Dev docs system | `.work/`, `/crew:ticket`, `/crew:handoff` |
| Utility scripts in skills | every `skills/*/scripts/` directory |
| Don't block at write time | 0.19.52 removed the PreToolUse command guard, kept the Stop gate |

That last row is the document's §4.3.2 and crew reached it independently.

## Where crew departs, on purpose

Three of the document's rules call crew's architecture an anti-pattern:
specialised subagents (crew has 54), a large slash-command surface (26), and
being a multi-agent system at all.

**These are recorded decisions, not oversights.** The reasoning, and the cost
of each, is in `docs/adr/0003-crew-departs-from-three-community-best-practices.md`.
Do not re-open them from the source document alone.

## The rules worth applying, in priority order

Full detail in `references/practices.md`. The short form:

1. **Clear context early.** The document says 60k tokens or 30%; crew's default
   is now `warnAt: 0.5` with `reserveTokens: 0`. Waiting for the limit is the
   mistake.
2. **Avoid `/compact`.** Automatic compaction is opaque and poorly optimised.
   Prefer writing a handoff and clearing — which is what crew's hooks do.
3. **Be specific.** "Add a user settings page" produces vague work. Name the
   route, the sections, the component pattern, the tests.
4. **Review everything, including your own.** Fresh context or a different
   model family. A clone inherits the blind spot.
5. **Keep CLAUDE.md small.** 100–200 lines at the root, under ~2000 tokens.
   `references/claude-md.md` has the anti-patterns, which are the useful part.

## What the document gets wrong for this repo

Two of its numbers do not transfer, and saying so is part of using it well:

- **"Clear at 60k tokens"** was written for a 200k window. On a 1M window that
  is 6%, which would clear several times per task. Crew expresses the same
  intent as a fraction (`warnAt`) so it scales, and auto-detects the window
  from the model rather than assuming one.
- **"Keep total CLAUDE.md under 2000 tokens"** is good advice for a project
  CLAUDE.md and bad advice for this repo's, which is a landmine list earned by
  shipped defects. Length is not the metric; whether each line changes a
  decision is.

## Measuring, not asserting

The document's §9 offers metrics. Two are worth running here:

- **Skill size.** Main `SKILL.md` under 500 lines, with progressive disclosure
  into `references/`. Check with `wc -l plugin/crew/skills/*/SKILL.md`.
- **MCP token cost.** "More than 20k tokens of MCPs" is its threshold for
  crippling a session. Crew registers no MCP server of its own.

## Reference files

- `references/practices.md` — the full rule set by area: TDD, quality gates,
  code review, commits, context, planning, skills, hooks, subagents, slash
  commands, MCP, search, workflow, testing standards, headless mode.
- `references/claude-md.md` — CLAUDE.md structure, size limits, the four
  anti-patterns, and what to write instead.
- `references/contradictions.md` — the five the document itself records as
  unresolved, with crew's position on each.
