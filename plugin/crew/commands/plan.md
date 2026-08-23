---
description: Get an independent design opinion before building
argument-hint: <the decision, or a ticket id>
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent
---

Design review for: $ARGUMENTS

1. If this is a ticket id, read that ticket. Otherwise take the argument as the
   question directly.
2. Use `crew:explorer` if you need to understand the current shape of the code —
   but remember that what explorer returns stays local. Only the abstracted brief
   goes outward.
3. Invoke `crew:planner`. It writes the brief, shows it to me for approval,
   sends it, and reports the disagreement.
4. Present the options with tradeoffs. Recommend one. Say what would change your
   recommendation.

Then stop. Do not start implementing. A plan I have not agreed to is not a plan.

If `secondOpinion.provider` is `none` or unreachable, do the analysis yourself
and say plainly that this is a single opinion, not a reviewed one.
