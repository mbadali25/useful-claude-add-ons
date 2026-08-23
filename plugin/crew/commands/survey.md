---
description: Research the app for real gaps and propose options with tradeoffs
argument-hint: [area, e.g. "performance" or "the billing module"]
allowed-tools: Read, Grep, Glob, Bash, Agent
---

Survey $ARGUMENTS (whole repo if no area given).

1. Invoke the `crew:analyst` subagent. Give it the area, `.crew/codemap/INDEX.md`,
   and anything you already know is painful.
2. For a broad survey, run analyst once per subsystem in parallel rather than once
   over everything — a single pass over a large repo produces shallow findings.
   Cap at four.
3. Read `.work/FINDINGS.md` when they finish.

Then present to me, in this order:

- The findings you would act on, with their evidence line
- The findings you would not, and why they did not clear the bar
- Anything the analyst flagged as low confidence that you think is actually right

Do NOT create tickets. I decide what becomes work; `/crew:ticket` is a separate
step and a deliberate one. A survey that automatically becomes a backlog is just
a way of committing to seven things nobody agreed to.

If the honest result is "nothing here worth doing right now," say that plainly.
That is a useful answer and a common one in a codebase that is working.
