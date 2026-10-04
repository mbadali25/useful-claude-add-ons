---
description: Report a ticket's standing (status), or drive it through the lifecycle until a human is needed (run)
argument-hint: "[status|run|assign|goal|focus] [ticket id | --goal <slug>]"
allowed-tools: Read, Write, Edit, Bash, Agent, Skill
---

Subcommands `status`, `run`, `assign`, `goal`, `focus`; a bare ticket id or nothing is `run`: drive
one ticket through spec, plan, approval, implement, refresh, review and done, following each phase
command's procedure here in the order `crew_autopilot.py next` names from disk, stopping when a
phase needs a person. Nothing here accepts a review or skips a phase, and nothing approves except
section 3's `approve`, under the approval policy; it writes `approval.json`, `scope-tickets.json`
on a ticket's first approval, and a distinct successor plan's NEEDS_REPLAN -> IN_REVIEW ledger move.

## 0. Route

If the arguments hold a quote, `$`, a backtick or a backslash, stop without
running anything: no subcommand or ticket id has one. Otherwise:

```bash
python3 -B ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py route --root . --args '$ARGUMENTS'
```

It prints `sub=<s> stop=<0|1> ticket=<t> reason=<r>`. Anything but a `sub=` line - no output,
a traceback, a non-zero exit - is a stop. `stop=1`: print the reason and stop (an unknown word is
never read as a ticket; `assign`, `goal`, `focus` arrive with T-0019, T-0012, T-0020). `sub=status`:
section 1 only. `sub=run`: sections 2 to 5. `<ticket>` is route's `ticket=`, never re-read from the
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
in `.crew/config.json` turns it on. Note `maxPhases`, `deploy` (CONFIG.md §20; nothing here deploys),
`approval`, `questions`, `sleep=`. `resume` with no ticket tries the handoff's `resume:` line (only when its `branch:`
and `head:` match this checkout), then this worktree's active ticket, then `.work/INDEX.md` only when one ticket is
open. Print the `source`, every `fell through:` and any `disagreement:` line (disk wins).
`stop=1`: print the reason and stop - that includes a ticket that is not this worktree's
active one. `activate=1` (no pointer is set): run
`python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_ticket.py activate --root . --ticket <ticket>`
so the scope guard judges edits by it; it also records the scope base (print its stderr). Never pick from `## Next action`.

## 3. The loop - keep `N` (phases run, from 0) and `LAST` (last command, empty)

```bash
python3 -B ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py next --root . \
  --ticket <ticket> --phases-run N --last-command "LAST"
```

It prints `phase=<p> stop=<0|1> command=<c> reason=<r>`.
No output, a traceback or a non-zero exit is a stop.
- `stop=0` - announce `phase <p>: <c>` and follow that command's `commands/*.md` here, or run a
  refresh command (`/crew:onboard --refresh`, `/crew:diagram refresh`, `graphify update .`) as
  named and commit it. Then `LAST=<c>`, `N+=1`, again.
- `stop=1` with `phase=approve` or `phase=open-questions` - not yet a stop: the policy below.
- any other `stop=1` - print the phase, the reason and the command the human types (may be
  empty), then **stop** - never run it yourself.

The policy (T-0010; `next`'s reason names it; `human` always stops) is the only writer here:
`python3 -B ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py approve --root . --ticket <ticket>`
prints `self-approved ...` (report it by name, go round again) or `refused:` (stop; the
human types `/crew:approve <ticket>`). For a question, research it (crew:explorer, crew:researcher)
into `questions.md`: `## Q<n>: <question>`, a `Research:` line, then 2-4 `### Option <id>`
blocks, the first marked `(recommended)`, each with a `Cost:` line. Then run
`python3 -B ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py questions-check --root . --ticket <ticket>`:
`valid=1 action=take` - add `taken: Option <id> by autopilot (<policy>)`, answer the item
`none - <option> (autopilot)`, recheck, report each `taken:`; anything else stops.

A review phase ends at its verdict: stop following `review.md` once the round is recorded, from
`/crew:review` or inside `/crew:implement` step 6; never fix and rerun inside the phase. Report
BLOCK and FIX lines verbatim; fixing, `review_ledger.py --accept` and `gh pr review`
are the human's. Go back through `next`: it stops at FINDINGS or an unrefunded INCOMPLETE (a
refunded one reruns, even straight after `/crew:review`). One extension, neither fixing nor rerunning (L-0510): after `review: auto-accept: eligible`, first run step 2d's control re-runs and, with no specialist or control BLOCK, step 3.3's `--auto-accept` and follow-up filing. A phase's own refusal - no approved plan, a red verify gate, a `/crew:done`
check - stops here, reported verbatim; never retry around it or edit a gate. Implement's
`status: review` edit keeps the approval (T-0026). Refresh runs after implement and before each
later round, never after an accepted review (that stales the receipt): `next` enforces it.

## 4. Stops

A person: `brainstorm` (no approved direction) and `review-acceptance` (FINDINGS with any BLOCK, or a round `--auto-accept` refuses - a verdict recovered from stray lines, or `ignored_lines` it could not tell, among them - are the owner's, at every setting); `plan-approval` and `open-questions` are a person unless section 3's
policy allows. `next` enforces from disk, every turn: `needs-replan`, `needs-replan-or-revert`,
`unknown-ledger`, `failed-validate`, `direction-unknown`, `unsettled-artifact`, `ticket-mismatch`,
`max-phases`, `no-progress`. This procedure: `review-verdict`, `failed-done-check`,
`failed-phase`. No deploy (T-0005), merge or PR (T-0011), new ticket (T-0012) except section 3's step 3.3 follow-up, lane or writer.
Never without an explicit yes (`crew_state.AUTONOMOUS_STOPS`):
- `offboard-role` - offboarding a role, or removing one from the roster.
- `delete-map` - deleting a codemap file or a diagram.
- `rewrite-metrics` - rewriting .crew/metrics.md.
- `git-destruction` - force-push, branch delete, history rewrite, or rm of a tracked file.

## 5. Context runs low, and the report

When context-watch asks for a handoff: finish the step in hand, run `/crew:handoff` with
`resume: /crew:autopilot <ticket>` (T-0006's grammar) and `branch:`/`head:` on their own lines,
then stop. Report the ticket and its source, each phase run with its command, every
`self-approved` and `taken:` line, where `next` stopped, why, and the command the human types next.
