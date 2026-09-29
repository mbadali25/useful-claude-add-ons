---
description: Report a ticket's standing (status), or drive it through the lifecycle until a human is needed (run)
argument-hint: "[status|run|assign|goal|focus] [ticket id | --goal <slug>]"
allowed-tools: Read, Write, Edit, Bash, Agent, Skill
---

Subcommands `status`, `run`, `assign`, `goal`, `focus`; a bare ticket id or nothing is `run`:
drive one ticket through spec, plan, approval, implement, refresh, review and done, following
each phase command's procedure here in the order `crew_autopilot.py next` names from disk,
stopping when a phase needs a person. Nothing here approves, accepts a review, or skips a phase.

## 0. Route

If the arguments hold a quote, `$`, a backtick or a backslash, stop without
running anything: no subcommand or ticket id has one. Otherwise:

```bash
python3 -B ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py route --root . --args '$ARGUMENTS'
```

It prints `sub=<s> stop=<0|1> ticket=<t> reason=<r>`. Anything but a `sub=` line - no output,
a traceback, a non-zero exit - is a stop. `stop=1`: print the reason and stop
(an unknown word is never read as a ticket; `assign`, `goal`, `focus` arrive
with T-0019, T-0012, T-0020). `sub=status`: section 1 only. `sub=run`:
sections 2 to 5. `<ticket>` is route's `ticket=`, never re-read from the
arguments; from `resume` on, `<ticket>` is the `ticket=` resume printed.

## 1. status

```bash
python3 -B ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py status --root .  # --ticket <ticket> if ticket= is set
```

Print its lines as they are, then stop: read-only, armed or not (`-B`: not even a
bytecode cache), no other command, no edit, no phase. `unknown` means it could not tell.

## 2. Arm, then pick the ticket

```bash
python3 -B ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py settings --root .
python3 -B ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py resume --root .  # ticket= empty
python3 -B ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py resume --root . --ticket <ticket>
```

`settings`: anything but `mode=plan` - stop, print its `warning:` lines, and say `autopilot.mode: plan`
in `.crew/config.json` turns it on. Note `maxPhases` and `deploy` (CONFIG.md §20; nothing here deploys).
`resume` with no ticket tries the handoff's `resume:` line (only when its `branch:` and `head:` match
this checkout), then this worktree's active ticket, then `.work/INDEX.md` only when one ticket is
open. Print the `source`, every `fell through:` and any `disagreement:` line (disk wins).
`stop=1`: print the reason and stop - that includes a ticket that is not this worktree's
active one. `activate=1` (no pointer is set): run
`python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_ticket.py activate --root . --ticket <ticket>`
so the scope guard judges edits by it. Never pick from `## Next action`.

## 3. The loop - keep `N` (phases run, from 0) and `LAST` (last command, empty)

```bash
python3 -B ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py next --root . \
  --ticket <ticket> --phases-run N --last-command "LAST"
```

It prints `phase=<p> stop=<0|1> command=<c> reason=<r>`. Anything but a
`stop=0` line - no output, a traceback, a non-zero exit - is a stop.
`stop=1`: print the phase, the reason and the command the human types (may
be empty), then **stop** - never run it yourself. `stop=0`: announce
`phase <p>: <c>` and follow that command's `commands/*.md` here, or run a
refresh command (`/crew:onboard --refresh`, `/crew:diagram refresh`,
`graphify update .`) as named and commit it. Then `LAST=<c>`, `N+=1`, again.

A review phase ends at its verdict: stop following `review.md` once the round is recorded,
from `/crew:review` or inside `/crew:implement` step 6; never fix and rerun inside the phase.
Report BLOCK and FIX lines verbatim; fixing, `review_ledger.py --accept` and `gh pr review`
are the human's. Go back through `next`: it stops at FINDINGS or INCOMPLETE. A phase's own
refusal - no approved plan, a red verify gate, a `/crew:done` check - stops here, reported
verbatim; never retry around it or edit a gate. Implement's `status: review` edit keeps the
approval (T-0026). Refresh runs after implement and before each later round, never after an
accepted review (that stales the receipt): `next` enforces it.

## 4. Stops

A person, always (policies are T-0010): `brainstorm` (no approved direction),
`plan-approval` (only the human types `/crew:approve <ticket>`), `review-acceptance`
(FINDINGS are the owner's), `open-questions`. `next` enforces from disk, every turn:
`needs-replan`, `needs-replan-or-revert`, `unknown-ledger`, `failed-validate`,
`direction-unknown`, `unsettled-artifact`, `ticket-mismatch`, `max-phases`, `no-progress`.
This procedure: `review-verdict`, `failed-done-check`, `failed-phase`. No deploy (T-0005),
merge or PR (T-0011), new ticket (T-0012), lane or writer. Never without an explicit yes
(`crew_state.AUTONOMOUS_STOPS`):
- `offboard-role` - offboarding a role, or removing one from the roster.
- `delete-map` - deleting a codemap file or a diagram.
- `rewrite-metrics` - rewriting .crew/metrics.md.
- `git-destruction` - force-push, branch delete, history rewrite, or rm of a tracked file.

## 5. Context runs low, and the report

When context-watch asks for a handoff: finish the step in hand, run
`/crew:handoff` with `resume: /crew:autopilot <ticket>` (T-0006's grammar)
and `branch:`/`head:` on their own lines, then stop. Report the ticket and its
source, each phase run with its command, where `next` stopped, why, and the
exact command the human types next.
