---
description: Removed in crew 1.0 - use /crew:implement
argument-hint: <ticket id>
allowed-tools: Read
---

`/crew:work` was removed in crew 1.0. It is not an alias and does nothing.
Use `/crew:implement $1`, which needs an approved `plan.md` for the ticket.
The 1.0 lifecycle is `/crew:brainstorm`, `/crew:spec`, `/crew:plan`, `/crew:implement`,
`/crew:review`, `/crew:done`. Tell the user that, and stop.
