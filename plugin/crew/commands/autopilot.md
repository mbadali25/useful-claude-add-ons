---
description: Resume one ticket from the handoff and drive it through the lifecycle until a human is needed
argument-hint: "[ticket id]"
allowed-tools: Read, Write, Edit, Bash, Agent, Skill
---

Drive one ticket - spec, plan, approval, implement, refresh artifacts,
review, done - by following each phase command's own procedure here, in this
session, in the order `crew_autopilot.py next` names from files on disk. Stop
the moment a phase needs a person. Every gate still decides; nothing here
approves, accepts a review, or skips a phase.

## 0. Refuse unless armed

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py settings --root .
```

Anything but `mode=plan` - stop, print its `warning:` lines, and say
`autopilot.mode: plan` in `.crew/config.json` turns it on. Note `maxPhases`.

## 1. Which ticket

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py resume --root .  # no $1
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py resume --root . --ticket $1
```

With no `$1` it tries the handoff's `resume:` line (T-0006's parser; only when
its `branch:` and `head:` match this checkout), then this worktree's active
ticket, then `.work/INDEX.md` only when exactly one ticket is open. Print the
`source`, every `fell through:` and any `disagreement:` line (disk wins).
`stop=1`: print the reason and stop - that includes a ticket that is not this
worktree's active one. `activate=1` (no pointer is set): run
`python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_ticket.py activate --root . --ticket <ticket>`
so the scope guard judges edits by this ticket. Never pick from `## Next action`.

## 2. The loop

Keep `N` (phases run, from 0) and `LAST` (the command last run, empty at
first). Each turn:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py next --root . \
  --ticket <ticket> --phases-run N --last-command "LAST"
```

It prints `phase=<p> stop=<0|1> command=<c> reason=<r>`. Anything but a
`stop=0` line - no output, a traceback, a non-zero exit - is a stop.

- `stop=1` - print the phase, the reason and the command the human types
  (may be empty), then **stop**. Do not run that command yourself.
- `stop=0` - announce `phase <p>: <c>` and follow that command's procedure
  here: `/crew:spec`, `/crew:plan`, `/crew:implement`, `/crew:review`,
  `/crew:done` are their `commands/*.md`; a refresh command
  (`/crew:onboard --refresh <subsystem>`, `/crew:diagram refresh`,
  `graphify update .`) is run as named and committed. Then `LAST=<c>`,
  `N+=1`, and go round again.

A review phase ends at its verdict: stop following `review.md` once the
round is recorded, from `/crew:review` or inside `/crew:implement` step 6;
never fix and rerun inside the phase. Report the BLOCK and FIX lines verbatim
(review.md step 3.1); steps 3.2 to 3.4 - fixing and rerunning,
`review_ledger.py --accept`, and `gh pr review` - are the human's. Go back
through `next`: it stops at FINDINGS or INCOMPLETE and puts a refresh before
any later round.

If a phase's own procedure refuses or stops - no approved plan, a red verify
gate, a `/crew:done` check - stop there and report it verbatim. Never retry
around it or edit a gate to get past it. (Implement's `status: review` edit
keeps the approval, T-0026; a pre-T-0026 receipt stops at `approve`.)

## 3. Refresh sits between implement and review

`/crew:implement` step 6 runs T-0008's check before `/crew:review`; `next`
names `refresh` before every later round. Never after an accepted review: a
bundle excludes only `.work/`, so that refresh stales the receipt - `next`
says `stale-after-review` and writes nothing. An `unknown` artifact is
refreshed only when T-0008 names a command for its orphaned-anchor case; any
other `unknown` stops. T-0008 missing stops as "refresh-artifacts unavailable".

## 4. Stops

Always a person (policies are T-0010): `brainstorm` (no direction, or an
INDEX status that does not say it was approved), `plan-approval` (only the
human types `/crew:approve <ticket>`; autopilot never runs it or writes an
approval), `review-acceptance` (FINDINGS are the owner's), `open-questions`
(any item under an `Open questions` heading in direction.md, spec.md or plan.md).

Enforced by `next` from disk: `needs-replan`, `needs-replan-or-revert` (no
round left and no receipt: a review would write NEEDS_REPLAN), `unknown-ledger`,
`failed-validate`, `direction-unknown` (no INDEX row to say it is approved),
`unsettled-artifact`, `ticket-mismatch` (the scope guard's ticket is not this
one, checked on every turn), `max-phases`, `no-progress`.

Enforced by this procedure: `review-verdict` (above), `failed-done-check`,
`failed-phase`. `next` sees these only as `no-progress` later.

The autonomous stops hold here as everywhere (`crew_state.AUTONOMOUS_STOPS`;
`crew_autopilot.py stops` lists them) - never without an explicit yes:

- `offboard-role` - offboarding a role, or removing one from the roster.
- `delete-map` - deleting a codemap file or a diagram.
- `rewrite-metrics` - rewriting .crew/metrics.md.
- `git-destruction` - force-push, branch delete, history rewrite, or rm of a
  tracked file.

No deploy (T-0005), merge or PR (T-0011), new ticket (T-0012), lane or writer.

## 5. Context runs low

When context-watch asks for a handoff: finish the step in hand, run
`/crew:handoff` with the resume line `resume: /crew:autopilot <ticket>`
(T-0006's grammar) and `branch:`/`head:` on their own lines, then stop. The
next `/crew:autopilot` reads it and recomputes the phase from disk.

## 6. Report

The ticket and its source, each phase run with its command, where `next`
stopped, why, and the exact command the human types next.
