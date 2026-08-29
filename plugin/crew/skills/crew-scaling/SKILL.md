---
name: crew-scaling
description: Decide when to add or remove agent roles and when to parallelize. Use when the user says grow the team, expand the crew, add more agents, run agents in parallel, speed this up, increase throughput, or asks whether the setup is worth its cost or the right size.
---

# Crew scaling

Answer three questions before proposing any change. Refuse to skip to the
recommendation.

## 1. Is the current review catching defects?

From `.crew/metrics.md`, BLOCK+FIX per ticket over the last 10:

- **< 0.3** — review is broken, not thorough. Adding roles makes a system that
  finds nothing cost more and still find nothing. Fix the reviewer first: is
  Codex actually running, is the diff non-empty, is the reviewer seeing the
  right base branch?
- **0.3 - 2.0** — healthy. Scaling questions are legitimate.
- **> 2.0** — tickets are too big. Cut scope before adding people.

## 2. Where does work actually sit?

- **Waiting on the human** — the bottleneck is review attention. More agents
  strictly worsen this: more parallel output, same reviewer. Say this plainly
  even though it is not what was asked.
- **In implementation** — parallelism may help. See question 3.
- **Same defect class recurring** — this is the one clean case for a new role.
  Name it after the defect class. One role, one failure mode.

## 3. Can the work actually run in parallel?

Parallelism scales on **independent work units**, not on job titles.

- Two repos: genuinely parallel. This is the good case with 5+ repos.
- Two git worktrees of one repo: parallel, merge cost at the end.
- Two agents, one working tree: not parallel. Conflicting edits, lost writes,
  and a debugging session that costs more than the work saved.

"Add three more developer agents" to one repo is not a throughput increase. It
is a race condition with a job title.

## Tiers

| Tier | Roles | Add when |
|---|---|---|
| 0 | explorer, qa-reviewer | always start here |
| 1 | + security, smoke-author | security findings reach review; coverage gaps cause regressions |
| 1 | + developer | the PM is running work end to end and the main session should stop being the one that implements |
| 2 | + dba, docs-writer, browser-tester | migrations are routine; a UI regression reached users; doc staleness costs real time |
| 2 | + analyst | you are choosing what to work on, not just working the queue |
| 2 | + planner | designs are being reworked after implementation started |
| 3 | parallel sessions / worktrees / agent teams | every involved repo has green smoke |

Tier 3 native coordination needs `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` and is
experimental, with known limitations around session resumption and shutdown.
Prefer plain parallel sessions across repos until that matters.

Shrinking follows this table in reverse, but not by hand-editing `config.json`:
run `/crew:pm offboard <role>` instead. That path requires naming the coverage
the removal loses, which is the part a direct edit would skip.

## Cost to state every time

Each additional role costs a full context load plus the whole CLAUDE.md hierarchy
on every invocation. Six roles at 3k tokens of standing context is 18k paid
repeatedly, for value that must show up in `metrics.md` or it is not there at all.

## The honest recommendation is often "nothing"

If the numbers do not support growth, say so and stop. A scaling review that
concludes "this is the right size" is a successful review.
