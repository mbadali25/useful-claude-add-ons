---
description: Pick up a ticket and work it end to end
argument-hint: <ticket id, e.g. T-0042 or PROJ-123>
allowed-tools: Read, Edit, Write, Bash, Grep, Glob, Agent
---

Work ticket $1.

1. Read the ticket. Files mode: `.work/tickets/$1.md`. Jira mode: `.work/cache/$1.md`,
   and if it is missing run `/crew:jira-sync $1` first. Do NOT read INDEX.md or
   any other ticket.
2. If Scope is unclear or "Done when" is not observable, stop and ask me.
3. Use the `crew:explorer` subagent to locate the code. Do not grep yourself.
4. Plan mode. Show me the plan before editing.
5. Implement the smallest change that satisfies Done.
6. Verify. If `.crew/verify.json` exists, run the checks your changed paths map
   to (the Stop hook enforces this anyway; running it yourself is faster feedback).
   Otherwise `./scripts/smoke.sh`. On failure, fix and rerun. Never proceed past
   a red gate. If a changed path maps to no rule, add one before finishing.
7. If the change touches auth, input, SQL, secrets, or IaC -> `crew:security`.
   If it touches a migration, schema, or a big-table query and the `dba` role is
   enabled in `.crew/config.json` -> `crew:dba`.
8. `/crew:review`.
9. If this added behavior with no coverage, add a check: `crew:smoke-author` for
   API and data paths, `crew:browser-tester` for UI, CSS, or user flows. Then add
   the path to `.crew/verify.json`. A feature without a check is how the next
   change breaks it silently.
10. Update ticket status and a one-line Result. Files mode: edit the ticket and
    its INDEX line. Jira mode: `/crew:jira-sync $1 --push`.

Stop there. I open the PR.
