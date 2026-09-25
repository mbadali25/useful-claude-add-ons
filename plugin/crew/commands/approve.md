---
description: Approve a ticket's plan - only you can, by typing this; the prompt hook records the receipt
argument-hint: <ticket-id>
allowed-tools: Read
disable-model-invocation: true
---

The user typed `/crew:approve $1`. **The approval has already been decided
before you read this.** crew's UserPromptSubmit hook (`approval_hook.py`) saw
that prompt, read `.work/tickets/$1/spec.md` and `plan.md` once, and either:

- **recorded** the receipt at `<git-common-dir>/crew/tickets/$1/approval.json`,
  bound to the sha256 of both files, `approved_via: "user-prompt"` - its
  message says "the user approved $1 from their own prompt"; or
- **refused** it and blocked the prompt, saying why ("/crew:approve was NOT
  recorded -- ...") - in which case you are probably not reading this at all.

Your whole job here is to relay that result in one or two sentences:

- Recorded: say so, and that `/crew:implement $1` can start. Any later edit to
  `spec.md` or `plan.md` makes this approval stale; the user re-approves by
  typing `/crew:approve $1` again.
- Refused, or no hook message in context: say the approval was **not**
  recorded, quote the reason if one was given, and stop. Point at
  `crew_ticket.py validate --ticket $1` for the contract error.

**Never run `crew_ticket.py approve` yourself**, and never write
`approval.json` by any route. An approval exists only because the user typed
this command; the scope guard refuses the shell form, and a receipt made that
way is marked `approved_via: "cli"`, which the guard and the completion audit
reject unless `scope.allowCliApproval` is on. If `scope.mode` is `off`, the
receipt is still recorded but nothing enforces it.
