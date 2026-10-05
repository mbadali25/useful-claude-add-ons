---
description: Report a ticket's standing (status), or drive it through the lifecycle until a human is needed (run)
argument-hint: "[status|run|sleep|wake|assign|goal|focus] [ticket id | off | --goal <slug>]"
allowed-tools: Read, Write, Edit, Bash, Agent, Skill
---

`run` (a bare ticket id, or nothing) drives one ticket through its phases and `status` reports it,
each phase by its command's procedure, in the order `crew_autopilot.py next` names from disk, stopping
when a person is needed. Nothing here accepts a review or skips a phase, and nothing approves except
section 3's `approve`, under the approval policy; it writes `approval.json`, `scope-tickets.json`
on a ticket's first approval, and a distinct successor plan's NEEDS_REPLAN -> IN_REVIEW ledger move.
`sleep` (only tightens until L-1504) and `wake` write only `<git-common-dir>/crew/autopilot-sleep.json`.

## 0. Route

A first word of exactly `goal`: run the line below as `route --root . --first goal`, never `--args` (the goal's text stays off every shell line); `sub=goal stop=0` is section 7 only.
If the arguments hold a quote, `$`, a backtick or a backslash, stop without
running anything: no subcommand or ticket id has one. Otherwise:

```bash
python3 -B ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py route --root . --args '$ARGUMENTS'
```

It prints `sub=<s> stop=<0|1> ticket=<t> reason=<r>`. Anything but a `sub=` line - no output,
a traceback, a non-zero exit - is a stop. `stop=1`: print the reason and stop (an unknown word is
never a ticket; `assign` comes with T-0019, `--goal` resume with L-0541). `sub=status`: section 1; `sub=focus`: section 6 only; `sub=goal`: section 7 only;
`sub=sleep`, `sub=wake`: run (as route ran) `crew_autopilot.py sleep --root .` or
`crew_autopilot.py wake --root .`, print its line, stop. `sub=run`: sections 2 to 5; `<ticket>` is route's
`ticket=`, never re-read from the arguments; from `resume` on, `<ticket>` is the `ticket=` resume printed.

## 1. status

```bash
python3 -B ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py status --root .  # --ticket <ticket> if ticket= is set
```

Print its lines as they are, then stop: read-only, armed or not (`-B`: not even a bytecode cache), no other command, no edit, no phase. `unknown` means it could not tell.

## 2. Arm, then pick the ticket

```bash
python3 -B ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py settings --root .
python3 -B ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py resume --root .  # ticket= empty
python3 -B ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py resume --root . --ticket <ticket>
python3 -B ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_inflight.py claim --root . --ticket <ticket> --runner autopilot
```

`settings`: anything but `mode=plan` - stop, print its `warning:` lines, and say `autopilot.mode: plan` in `.crew/config.json` turns it on. Note `maxPhases`, `deploy` (CONFIG.md §20; nothing here deploys), `maxAutoReplans` (0: off), `approval`, `questions`, `sleep=`; print each `warning: inert:` line (a key this crew ignores) - it never stops a run. `resume` with no ticket tries the handoff's `resume:` line (only when its `branch:` and `head:` match this checkout), then this worktree's active ticket, then `.work/INDEX.md` only when one ticket is open. Print the `source`, every `fell through:` and any `disagreement:` line (disk wins).
`stop=1`: print the reason and stop - that includes a ticket that is not this worktree's active one. `activate=1` (no pointer is set): run
`python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_ticket.py activate --root . --ticket <ticket>` so the scope guard judges edits by it; it also records the scope base (print its stderr). Never pick from `## Next action`.
Then `claim` (T-0049): `claimed` or `refreshed` goes on; `refused:` (held by another, stale, unreadable) stops.

## 3. The loop - keep `N` (phases run, from 0) and `LAST` (last command, empty)

```bash
python3 -B ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py next --root . \
  --ticket <ticket> --phases-run N --last-command "LAST" --runner autopilot
```

It prints `phase=<p> stop=<0|1> command=<c> reason=<r>`. No output, a traceback or a non-zero exit is a stop.
- `stop=0` - announce `phase <p>: <c>` and follow that command's `commands/*.md` here, or run a
  refresh command (`/crew:onboard --refresh`, `/crew:diagram refresh`, `graphify update .`) as
  named and commit it, or run `commit-refresh`'s `git add -- ... && git commit ... -- ...` exactly as printed; then the tracker step (below). `auto-replan`: run its `auto-reject` line, report every line verbatim, send them as `review.md` step 5's notification. A `replan` that does not stop: `/crew:plan` writes a successor plan whose steps quote every BLOCK and FIX line of the rejected round verbatim, each with a neighbouring-case check, and differs from every plan approved before. `phase=ship` (T-0011): print the lines of
  `python3 -B ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py ship --root . --ticket <ticket>`; `stop=1` stops. Then `LAST=<c>`, `N+=1`, again.
- `stop=1` with `phase=approve` or `phase=open-questions` - not yet a stop: the policy below.
- any other `stop=1` - print the phase, the reason and the command the human types (may be empty), then **stop** - never run it yourself. `phase=needs-owner` waits on the owner's answer to the questions it names; `phase=closed` also covers INDEX or header `cancelled`/`superseded`.

The policy (T-0010; `next`'s reason names it; `human` always stops) is one writer here (the other policy writer is `auto-replan`'s `auto-reject`, T-0074, which writes only the ledger's REVIEWED -> NEEDS_REPLAN):
`python3 -B ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py approve --root . --ticket <ticket>`
prints `self-approved ...` (report it by name, go round again) or `refused:` (stop; the human types `/crew:approve <ticket>`). For a question, research it (crew:explorer, crew:researcher)
into `questions.md`: `## Q<n>: <question>`, a `Research:` line, then 2-4 `### Option <id>` blocks, the first marked `(recommended)`, each with a `Cost:` line. Then run
`python3 -B ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py questions-check --root . --ticket <ticket>`:
`valid=1 action=take` - add `taken: Option <id> by autopilot (<policy>)`, answer the item `none - <option> (autopilot)`, recheck, report each `taken:`; anything else stops.

A review phase ends at its verdict: stop following `review.md` once the round is recorded, from `/crew:review` or inside `/crew:implement` step 6; never fix and rerun inside the phase. Report
BLOCK and FIX lines verbatim; fixing, `review_ledger.py --accept` and `gh pr review` are the human's. Go back through `next`: it stops at FINDINGS or an unrefunded INCOMPLETE (a
refunded one reruns, even straight after `/crew:review`). One extension, neither fixing nor rerunning (L-0510): after `review: auto-accept: eligible`, first run step 2d's control re-runs and, with no specialist or control BLOCK, step 3.3's `--auto-accept` and follow-up filing. A phase's own refusal - no approved plan, a red verify gate, a `/crew:done`
check - stops here, reported verbatim; never retry around it or edit a gate. Implement's `status: review` edit keeps the approval (T-0026). Refresh runs after implement and before each later round, never after an accepted review (that stales the receipt): `next` enforces it. `fresh-uncommitted` is committed (`commit-refresh`), never reviewed or closed over. Docs runs before refresh (a document owed after the receipt is `docs-after-review`).
The tracker step (T-0022), after each phase and after `/crew:done` succeeds, moves the tracker to the status on disk and records each `/crew:docs` run (`next` stops once two leave a document `MISSING`, and at once on `docs-unknown`); no tracker write enters the review bundle:
`python3 -B ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py tracker --root . --ticket <ticket> --after "<c>"`
`tracker=delegated`: run its `command=` (Jira, SDP) here. `stop=1`: print the reason and the `command=` retry, stop.

## 4. Stops

A person: `brainstorm` (no approved direction) and `review-acceptance` (FINDINGS with any BLOCK, or a round `--auto-accept` refuses - a verdict recovered from stray lines, or `ignored_lines` it could not tell, among them - are the owner's; a BLOCK is never accepted here, at any setting, and only `auto-replan` rejects one); `plan-approval` and `open-questions` are a person unless section 3's
policy allows. `next` enforces from disk, every turn: `needs-replan`, `needs-replan-or-revert`, `unknown-ledger`, `failed-validate`, `direction-unknown` (no INDEX row here or in the main checkout), `index-disagreement`, `unsettled-artifact`, `ticket-mismatch`,
`max-phases`, `no-progress`, `auto-replan-cap` (`maxAutoReplans` successor plans already on the ledger), `drift`, `in-flight`, `handover-elsewhere`, `docs-missing`, `docs-unknown`, `docs-after-review`; the tracker step: `tracker-failed`, `tracker-unavailable`. This procedure: `review-verdict`, `failed-done-check`, `failed-phase`. No deploy (T-0005), merge or PR but `ship`'s (never by hand), new ticket (T-0012) except section 3's step 3.3 follow-up, lane or writer.
Never without an explicit yes (`crew_state.AUTONOMOUS_STOPS`):
- `offboard-role` - offboarding a role, or removing one from the roster.
- `delete-map` - deleting a codemap file or a diagram.
- `rewrite-metrics` - rewriting .crew/metrics.md.
- `git-destruction` - force-push, branch delete, history rewrite, or rm of a tracked file.
- `clear-inflight` - clearing another runner's in-flight marker (a stop names the owner's `clear`).

## 5. Context runs low, and the report

When context-watch asks for a handoff: run `/crew:handoff --wrap-up` with `resume: /crew:autopilot <ticket>` as its resume line, then stop. At every stop after the claim, first run section 2's `crew_inflight.py release --root . --ticket <ticket>`. Report the ticket and its source, each phase run with its command, the PR, every `self-approved`, `auto-rejected` and `taken:` line, every successor plan, where `next` stopped, why, and the command the human types next.

## 6. focus - a scope lock on one ticket (T-0020)

`python3 -B ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py focus --root .`, with `--ticket <ticket>` for `focus <ticket>`, `--off` only for route's `off=1` (the owner typed `focus off`), nothing for `focus`; print
its output as-is, stop. Focus is on only once `focus <ticket>` sets it, never from the active ticket alone; then `route` refuses other work and `next` stops at `drift`. Never fix an out-of-scope finding in the diff: add a TODO entry (path:line, why deferred, what unblocks it) to the file `focus --findings --ticket <ticket>` prints. Autopilot never runs `focus off` itself.

## 7. goal - research once, propose, print the /goal line, ask for the split

Research the goal once (crew:explorer, crew:researcher) and write `.work/autopilot/<name>.proposal.json`: `goal`, a one-line `done_condition`, `findings`, and `tickets` (`title`, `risk`, `depends_on`: indexes of earlier tickets), the recommendation first, in dependency order. Then:
`python3 -B ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py goal-propose --root . --proposal-file <file>`
Show its lines as printed: the proposal, and its `goal_line:` for the owner to paste (`goal_status=printed` - autopilot cannot see Claude Code's /goal state). `refused:` stops. Then
`python3 -B ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py goal-approve --root . --goal <slug>`
and print its lines; `refused:` stops - the human types its `owner:` line. Either way mint nothing and stop: minting, `--goal` resume and backlog arrive with L-0541.
