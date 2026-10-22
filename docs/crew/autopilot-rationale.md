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

The command is at 19,853 bytes against the 12,288 the budget asks for, so the
target is not met. The rest is procedure, and a procedure cut was ruled out by
the owner (2026-10-22). The file keeps a per-file allowance of 19,900 bytes in
`plugin/crew/.budget-allowance.json`; the Phase 4 close-out may tighten it.
Review round 1 found four dropped instructions (the FINDINGS-stop wording, the
refunded-INCOMPLETE rerun, the literal activate and notify prefixes) and the
round 2 audit restored them and eight smaller ones; what is below is only what
is left out.

## The command prefix

Twenty-three lines named `python3 -B ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/<script>`.
The command now defines `$H` once for that prefix and uses `$H/<script>.py`
where the line is prose. The lines a test or a sabotage mutation reads by their
literal text (`route`, `status`, `settings`, `resume`, `goal-run`, `next`), the fenced
`claim` line and the `approve`, `activate` and `run-stop` lines (the scope guard
judges the first and the others had no `-B`) stay spelled out, so each still carries `-B` and runs as
written. `-B` keeps `status` from writing a bytecode cache, and `status` is
read-only (the clause "not even a bytecode cache" explained why).

## Section by section

Intro. `sleep` "only tightens until L-1504": the command keeps the clause.

Section 0. `route --first goal`, never `--args`: the goal's text stays off every
shell line. The cloud-launch pointer named the README.

Section 1. `crew_bridge.py pending` was added by L-0636. The `-B` note: status is
read-only to the point of not writing a bytecode cache.

Section 2. The `coord` check is T-0030. `deploy` was cross-referenced to
CONFIG.md section 20. The `sleep-summary` warning means unreported sleep
decisions or held pings (L-0653, L-0656). The handoff `resume:` line (L-0658),
the one-running-goal source `goal-file` (L-0659), `goal-run` (L-0541), `claim`
(T-0049).

Section 3. `decision=` is L-0666. `ship` is T-0011, `next-slice` T-0059,
`split-check` T-0058, `fix` T-0067, the approval policy T-0010, `auto-reject`
T-0074 and the tracker step T-0022. `replan-check` is L-0670 and `approve`
refuses what it refuses. `sleep-note` is L-0653. The auto-accept extension is
L-0510; implement's `status: review` edit keeps the approval (T-0026); the
FINDINGS stop wording is L-0666 over T-0043 (owner 2026-10-07). A document owed
after the receipt is `docs-after-review`.

Section 4. `direction-unknown` means no INDEX row here or in the main checkout.
`auto-replan-cap` counts `maxAutoReplans` successor plans already on the ledger.
`deploy-target` and `failed-deploy` are L-0649.

Section 5. `handoff-resume` is T-0056. `crew_notify.py run-stop` decides what
pings; the reason is never passed on a command line because it can quote ticket
text. A goal's `goal-run` marks `running` and `done` itself.

Sections 6 to 9. `focus` is T-0020, `wave` T-0029, bridge messages T-0032. The
terminator rule exists because a message line equal to it would end the heredoc
early and run the rest as shell. `goal_status=printed` means autopilot cannot
see Claude Code's /goal state. The main session is the hub for messages
(L-0637). `--to <label>` records the ring so `pending` reports it until the peer
moves the record.
