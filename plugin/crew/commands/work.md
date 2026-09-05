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

1. Read the ticket. Files mode: `.work/tickets/$1.md`. Jira, ServiceDesk Plus
   and Obsidian Kanban mode: `.work/cache/$1.md`, and if it is missing run
   `/crew:jira-sync $1`, `/crew:sdp-sync $1` or `/crew:obsidian-sync $1` first.
   Do NOT read INDEX.md or any other ticket.
2. If Scope is unclear or "Done when" is not observable, stop and ask me.
3. Use the `crew:explorer` subagent to locate the code. Do not grep yourself.
4. Plan mode. Show me the plan before editing.
5. Implement the smallest change that satisfies Done. Who types is not assumed:
   read the effective dev table first with
   `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_config.py --root . --models`
   and dispatch whatever `dev.roles.developer` names, else `dev.provider`.
   `claude` means the `crew:developer` subagent; `codex` or `copilot` means that
   CLI writes the change. In Obsidian Kanban mode,
   set `status: in-progress` in `.work/cache/$1.md` and run
   `/crew:obsidian-sync $1 --push` first — that command reads the status from
   the cache and moves the card, and a board nobody moves is a board nobody
   trusts.

   **Record the dispatch the moment it returns**, with the provider and model
   that actually ran:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_state.py --root . \
     --record-dispatch dev --role developer --provider <provider> --model <model>
   ```

   Record what RAN, never the pin. If the pinned model was gone and
   `dev.fallback` fired, the fallback is the value that goes in — a record naming
   the pin after the fallback ran makes step 8 bar a family that did not write
   this diff and clear the one that did, which is worse than no record at all.
   Omit `--model` only for `claude`, an in-session subagent with no model flag.
   Re-record on every later implementation pass, including the one that fixes
   review findings: the last dispatch is the one that produced the diff being
   reviewed. Unrecorded is not neutral — `/crew:review` then reads `dev` out of
   the config, which describes the *next* run rather than this one, and has to
   say so in its verdict.
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
    request, and does not close it unless `sdp.closeOnDone` says to. Obsidian
    Kanban mode: set `status: done` in `.work/cache/$1.md`, then
    `/crew:obsidian-sync $1 --push` - which moves the card to the done lane and
    appends one note to the ticket note in the vault - and then edit the INDEX
    line too, the way files mode does. Obsidian mode keeps an INDEX because its
    keys are `T-####`, which the session brief can read.

13. Delete `.work/HANDOFF.md` if it exists. A stale handoff gets injected into
    every later session as though it were current, and that session has no way
    to know it is reading history.

Stop there. I open the PR.
