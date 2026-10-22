# /crew:autopilot - the rationale

`commands/autopilot.md` is the procedure a session follows. This file keeps what
the command no longer carries: the ticket and owner decisions each clause came
from, and the explanations that sat in parentheses. It is repo-only reference;
the installed plugin does not ship it and nothing here is read at run time
(L-0870, slice 5 of L-0727).

Nothing moved here changes what a session does. Every procedure step, refusal,
never-list entry and command line is still in the command. What moved is history
(which ticket added the clause), descriptions of what a script prints or does,
and the reasons behind a rule. Where a test pins a clause as an instruction it
stayed in the command (for example `section 2's first paragraph (the `coord`
check, T-0030)`).

The command is at 18,995 bytes against the 12,288 the budget asks for, so the
target is not met. The rest is procedure, and a procedure cut was ruled out by
the owner (2026-10-22). The file keeps a per-file allowance of 19,000 bytes in
`plugin/crew/.budget-allowance.json`; the Phase 4 close-out may tighten it.

## The command prefix

Twenty-three lines named `python3 -B ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/<script>`.
The command now defines `$H` once for that prefix and uses `$H/<script>.py`
where the line is prose. The lines a test or a sabotage mutation reads by their
literal text (`route`, `status`, `settings`, `resume`, `goal-run`, `next`) and the
fenced `claim` line stay spelled out, so each still carries `-B` and runs as
written. `-B` keeps `status` from writing a bytecode cache, and `status` is
read-only (the clause "not even a bytecode cache" explained why).

## Section by section

Intro. `sleep` "only tightens until L-1504": until that ticket lands, sleep can
make autopilot stricter and never looser.

Section 0. `route --first goal`, never `--args`: the goal's text stays off every
shell line. The cloud-launch pointer named the README. Both refusals and the
`route` output format are unchanged.

Section 1. `crew_bridge.py pending` was added by L-0636. The `-B` note: status is
read-only to the point of not writing a bytecode cache.

Section 2. The `coord` check is T-0030. `deploy` was cross-referenced to
CONFIG.md section 20 ("nothing here deploys"). A `warning: inert:` line names a
key this crew ignores. The `sleep-summary` warning means unreported sleep
decisions or held pings (L-0653, L-0656); the command sends the morning summary
itself. The handoff `resume:` line must match `branch:` and `head:` (L-0658 for
a `--goal` line while the goal is `running`); the one-running-goal source is
`goal-file` (L-0659); `goal-run` is L-0541; `maxTicketsPerRun` and
`maxTokensPerSession` are the caps `backlog` goes on inside. `activate` also
records the scope base. `claim` is T-0049; `refused:` covers held by another,
stale and unreadable.

Section 3. `decision=` is L-0666. `ship` is T-0011, `next-slice` T-0059,
`split-check` T-0058, `fix` T-0067, the approval policy T-0010, `auto-reject`
T-0074 and the tracker step T-0022. `replan-check` is L-0670 and `approve`
refuses what it refuses. `sleep-note` is L-0653: it writes only the local sleep
log, and only for an answer taken asleep or with sleep unknown (`?`).
`next` refreshes after implement and before a round it reaches itself, never
after an accepted review, because that would stale the receipt. An INCOMPLETE
round that was refunded reruns, even straight after `/crew:review`. The auto-accept
extension is L-0510. Implement's `status: review` edit keeps the approval
(T-0026). The FINDINGS stop names `autopilot.reviewPolicy` and ends "fixed them
instead? run the refresh check, then /crew:review" (L-0666 over T-0043; owner
2026-10-07). A document owed after the receipt is `docs-after-review`. The
tracker command is Jira or SDP when delegated.

Section 4. A round `--auto-accept` refuses includes a verdict recovered from
stray lines and any `ignored_lines` it could not tell; those are the owner's.
`direction-unknown` means no INDEX row here or in the main checkout.
`auto-replan-cap` counts `maxAutoReplans` successor plans already on the ledger.
`deploy-target` and `failed-deploy` are L-0649. `offboard-role` is offboarding or
removing a role, `delete-map` a codemap file or a diagram.

Section 5. `handoff-resume` is T-0056. `crew_notify.py run-stop` decides what
pings; the reason is never passed on a command line because it can quote ticket
text. A goal's `goal-run` marks `running` and `done` itself.

Sections 6 to 9. `focus` is T-0020, `wave` T-0029, bridge messages T-0032. The
terminator rule exists because a message line equal to it would end the heredoc
early and run the rest as shell. `goal_status=printed` means autopilot cannot
see Claude Code's /goal state. The main session is the hub for messages
(L-0637). `--to <label>` records the ring so `pending` reports it until the peer
moves the record.
