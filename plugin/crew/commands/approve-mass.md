---
description: Approve ONE blocked mass delete, create or change - only you can, by typing this
argument-hint: <id>
allowed-tools: Read
disable-model-invocation: true
---

The user typed `/crew:approve-mass $1`. The cloud guard (`guards.mass`, crew
1.3.28) stopped a shell command that would delete, create or change a mass of
files, and printed a 12-digit id with the stop. Typing this command with that id
is the owner's yes to THAT command only: the UserPromptSubmit hook
(`approval_hook.py`) records it from the prompt in
`<git-common-dir>/crew/mass-approvals/<id>.json`, good for 15 minutes. The id
binds the exact command line and the worktree, so it cannot be spent on another
command; one id covers every limit that command trips.

The hook is what records it. If it printed a refusal (a bad id, not a git
repository), relay that verbatim; nothing was approved. Otherwise tell the user
to re-run the exact command that was stopped.

**Never approve a mass operation yourself.** Never write into
`<git-common-dir>/crew/mass-approvals/` by any route (the scope guard and the
cloud guard both refuse it), never invent an id, and never split a stopped
command into pieces to get under a limit: the limits are `guards.mass.deleteCount`,
`createCount` and `changeCount` (`CONFIG.md`, "Mass operations"), and a command
you reshape to dodge them is the thing the stop exists to catch. Ask the user
instead.
