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
4b. **Emit the goal line.** After the plan is agreed and before you edit
    anything, print a ready-to-paste `/goal` line. You cannot set it yourself —
    `/goal` is a built-in the user types, and crew has no way to invoke it — so
    print it and say plainly that pasting it is optional and what it buys.

    Three clauses, each from an artifact this repo already has:

    ```
    /goal <the ticket's "Done when", as one measurable end state>; proven by
    <the .crew/verify.json commands the ticket's paths map to> and <the
    specific new test this ticket adds>; no tracked file outside <the ticket's
    declared paths> is modified — the turn prints `git status --porcelain` to
    show it, and anything found outside is appended to TODO.md with its reason,
    not fixed
    ```

    **Why the third clause needs the second half.** The goal evaluator reads
    only what the turn surfaced in the conversation — it runs no commands and
    opens no files. So "no tracked file outside these paths is modified" is
    checkable only if the turn PRINTS the evidence. A turn that stays silent
    and a turn that stayed inside its paths look identical to the evaluator,
    and it returns Met for both. That is the failure this repo names over and
    over: an unknown collapsing into the safe-looking value.

    **Name the specific test, not only the mapped command.** `.crew/verify.json`
    rules are coarse globs — in this repository a single rule covers
    `plugin/**` and `skills/**` — so nearly every change maps to the same
    top-level checker. True, and not discriminating. The ticket's own new test
    is what makes the middle clause mean this change rather than any change.

    Skip this step and say why if the ticket has no observable "Done when";
    step 2 should already have stopped you.

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
   the pin after the fallback ran makes step 9 bar a family that did not write
   this diff and clear the one that did, which is worse than no record at all.
   Omit `--model` only for `claude`, an in-session subagent with no model flag.
   Re-record on every later implementation pass, including the one that fixes
   review findings: the last dispatch is the one that produced the diff being
   reviewed. Unrecorded is not neutral — `/crew:review` then reads `dev` out of
   the config, which describes the *next* run rather than this one, and has to
   say so in its verdict.

   **End the implementation turn by printing `git status --porcelain`,
   verbatim, including when it is empty.** Then name any path in it that is
   outside the ticket's declared scope, and say what you did about it — which
   under the scope clause means filed to `TODO.md`, not fixed. An empty result
   is printed as an empty result, not omitted: a turn that shows nothing and a
   turn that touched nothing are the same to every later reader, and only one
   of them is a claim anybody checked.

6. Verify. If `.crew/verify.json` exists, run the checks your changed paths map
   to (the Stop hook enforces this anyway; running it yourself is faster feedback).
   Otherwise `./_verify/smoke.sh`. On failure, fix and rerun. Never proceed past
   a red gate. If a changed path maps to no rule, add one before finishing.
7. If the change touches auth, input, SQL, secrets, or IaC -> `crew:security`.
   If it touches a migration, schema, or a big-table query and the `dba` role is
   enabled in `.crew/config.json` -> `crew:dba`.
8. If this ticket made a new endpoint externally reachable — a route, an
   Ingress, an API Gateway/API Management resource, an OpenAPI path — declare
   it now, the only way a candidate becomes an authoritative fact:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_state.py --root . \
     --declare-endpoint "<url or host>" --location <path:line> --ticket $1
   ```

   Name a URL or a bare host, not a free-text description (BLOCK 3) — the scan
   artifact later has to prove it covered THIS target by literally containing
   what you write here, and prose has nothing in it to search for.

   Do this even if `endpointUnscanned` never fired — that trigger only sees a
   candidate while its diff line is still uncommitted against HEAD; a ticket
   that merges without declaring the endpoint it just created loses the scan
   obligation entirely, silently, the moment the diff lands.
9. `/crew:review`.
10. If this added behaviour with no coverage, add a check: `crew:smoke-author` for
    API and data paths, `crew:browser-tester` for UI, CSS, or user flows. Those
    agents write the `.crew/verify.json` rule as part of writing the check and
    prove it fires — confirm both happened. A check nobody mapped never runs, and
    it reads as coverage while it does not.
    If the change touched migrations, schema, or procedures, the rule must cover
    fresh apply, rollback apply, and a round trip.
11. If this ticket involved an operational procedure that will be repeated, is
    destructive, or lived only in someone's head, run `/crew:runbook
    --from-ticket $1`. Build it from the commands actually run, not from memory.
12. Run `/crew:docs` — decide which documents this change should touch, per the
    `crew-docs` trigger table. "None" is the common and correct answer. If this
    is a Terraform module, run `terraform-docs .` rather than editing inside the
    `BEGIN_TF_DOCS` markers, which would be overwritten.
13. Update ticket status and a one-line Result. Files mode: edit the ticket and
    its INDEX line. Jira mode: `/crew:jira-sync $1 --push`. ServiceDesk Plus mode:
    `/crew:sdp-sync $1 --push` - which writes one note and transitions the
    request, and does not close it unless `sdp.closeOnDone` says to. Obsidian
    Kanban mode: set `status: done` in `.work/cache/$1.md`, then
    `/crew:obsidian-sync $1 --push` - which moves the card to the done lane and
    appends one note to the ticket note in the vault - and then edit the INDEX
    line too, the way files mode does. Obsidian mode keeps an INDEX because its
    keys are `T-####`, which the session brief can read.

14. Delete `.work/HANDOFF.md` if it exists. A stale handoff gets injected into
    every later session as though it were current, and that session has no way
    to know it is reading history.


Every role you dispatch carries the same scope clause: fix only what blocks the
task, file the rest to `TODO.md` with its `path:line` and its reason, and end
its report with `## Deferred — and where it went`, present even when empty.
Hold them to it. A role whose report has no Deferred section has not finished,
and "Nothing deferred." is the empty case written out rather than left off.

Stop there. I open the PR.
