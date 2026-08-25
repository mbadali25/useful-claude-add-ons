---
description: Pick up a ticket and work it end to end
argument-hint: <ticket id, e.g. T-0042, PROJ-123 or SDP-40219>
allowed-tools: Read, Edit, Write, Bash, Grep, Glob, Agent
---

Work ticket $1.

When the ticket is complete and verified, and `notify.provider` is not `none`,
send one line - this is the `done` event:
`bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/notify.sh done "$1 complete"`
Only after the checks pass. "Done" that means "I stopped typing" is the reason
nobody trusts a notification channel.

1. Read the ticket. Files mode: `.work/tickets/$1.md`. Jira and ServiceDesk Plus
   mode: `.work/cache/$1.md`, and if it is missing run `/crew:jira-sync $1` or
   `/crew:sdp-sync $1` first. Do NOT read INDEX.md or any other ticket.
2. If Scope is unclear or "Done when" is not observable, stop and ask me.
3. Use the `crew:explorer` subagent to locate the code. Do not grep yourself.
4. Plan mode. Show me the plan before editing.
5. Implement the smallest change that satisfies Done.
6. Verify. If `.crew/verify.json` exists, run the checks your changed paths map
   to (the Stop hook enforces this anyway; running it yourself is faster feedback).
   Otherwise `./_verify/smoke.sh`. On failure, fix and rerun. Never proceed past
   a red gate. If a changed path maps to no rule, add one before finishing.
7. If the change touches auth, input, SQL, secrets, or IaC -> `crew:security`.
   If it touches a migration, schema, or a big-table query and the `dba` role is
   enabled in `.crew/config.json` -> `crew:dba`.
8. `/crew:review`.
9. If this added behaviour with no coverage, add a check: `crew:smoke-author` for
   API and data paths, `crew:browser-tester` for UI, CSS, or user flows. Those
   agents write the `.crew/verify.json` rule as part of writing the check and
   prove it fires — confirm both happened. A check nobody mapped never runs, and
   it reads as coverage while it does not.
   If the change touched migrations, schema, or procedures, the rule must cover
   fresh apply, rollback apply, and a round trip.
10. If this ticket involved an operational procedure that will be repeated, is
    destructive, or lived only in someone's head, run `/crew:runbook
    --from-ticket $1`. Build it from the commands actually run, not from memory.
11. Run `/crew:docs` — decide which documents this change should touch, per the
    `crew-docs` trigger table. "None" is the common and correct answer. If this
    is a Terraform module, run `terraform-docs .` rather than editing inside the
    `BEGIN_TF_DOCS` markers, which would be overwritten.
12. Update ticket status and a one-line Result. Files mode: edit the ticket and
    its INDEX line. Jira mode: `/crew:jira-sync $1 --push`. ServiceDesk Plus mode:
    `/crew:sdp-sync $1 --push` - which writes one note and transitions the
    request, and does not close it unless `sdp.closeOnDone` says to.

13. Delete `.work/HANDOFF.md` if it exists. A stale handoff gets injected into
    every later session as though it were current, and that session has no way
    to know it is reading history.

Stop there. I open the PR.
