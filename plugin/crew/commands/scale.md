---
description: Review whether the crew should grow, shrink, or stay the same
allowed-tools: Read, Write, Edit, Bash
---

Decide the crew size from evidence, not ambition.

Read `.crew/metrics.md` and `.crew/config.json`. Then tell me plainly which of
these is true, with the numbers:

**1. Is the current setup catching anything?**
Count BLOCK+FIX findings per ticket over the last 10 tickets.
- Under 0.3 per ticket: the review is not working. Do NOT add roles — fix or
  replace the reviewer first. Adding agents to a review that finds nothing
  multiplies cost and finds nothing faster.
- Above 2 per ticket: the implementation step is too large. Shrink tickets before
  adding anyone.

**2. What is the actual bottleneck?**
- If tickets sit in "review done, waiting on you" -> the bottleneck is my
  attention. More agents make this strictly worse. Say so directly.
- If tickets sit in "in progress" -> the bottleneck is implementation. Parallelism
  may help, but see rule 3.
- If the same class of defect keeps reaching review -> that is a case for one
  specific new role, named after the defect class. Nothing else.

**3. Parallelism scales on work units, not on job titles.**
Two agents on two repos, or two git worktrees, run genuinely in parallel.
Two agents on the same working tree produce merge conflicts and lost edits.
Never propose "add more developers" for a single repo. Propose splitting the
work instead, or say it cannot be split.

**Role tiers** (recommend moving up only when the evidence above supports it):
- Tier 0: main session + explorer + qa-reviewer. Everyone starts here.
- Tier 1: + security, smoke-author. Add when security findings reach review, or
  when smoke coverage gaps cause a regression.
- Tier 2: + dba, docs-writer. Add when migrations are frequent, or when
  onboarding a person costs more than generating docs would.
- Tier 3: parallel sessions across repos or worktrees. Only with green smoke in
  every repo involved. Requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` if you
  want native coordination, which is experimental with known rough edges.

Update `.crew/config.json` -> `roles` and `tier` with what I approve. Add nothing
without asking, and always state what it costs: each extra role is a full
context load plus a CLAUDE.md load on every invocation.

If the honest answer is "change nothing," say that. That is a successful run.
