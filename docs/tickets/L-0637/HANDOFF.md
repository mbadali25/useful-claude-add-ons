# Cloud handoff: L-0637

**Cross-session messaging: the main session is the hub, lanes never ring a peer**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

**Blocked: implementation cannot start until T-0029, T-0030 and T-0032 are merged to main.** T-0029 and T-0030 are only on local branches that are not on the shared remote, and `crew_bridge.py` (T-0032) is not written yet.

- **Role:** child ticket, split from T-0032, slice 2 of 3 (the other children are L-0636 and L-0638).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0637-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0637/direction.md`, `docs/tickets/L-0637/spec.md`
- **Size:** about 60 production lines (`crew_bridge.py` about 35, the prompt validator about 25). The spec says no harness path. `plugin/crew/commands/autopilot.md` is a `SEAM` path, which matters only beside a harness change. The sabotage mutations are L-0638.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0029 | in-progress, not on main, not in this hand-off | Defines the wave's lane marker and the lane prompt this slice reads and edits. |
| T-0030 | in-progress, not on main, not in this hand-off | The channel code `crew_bridge.py` is built on. |
| T-0032 | ready (PR in this hand-off) | `crew_bridge.py`, which this slice extends. |
| L-0636 | direction (PR in this hand-off) | Not a functional dependency, but both edit `crew_bridge.py` and `autopilot.md`; land it first to avoid a conflict. |

This ticket blocks: L-0638.

Order of the whole family:

1. T-0030 lands on main (not part of this hand-off). T-0029 must also be on main before L-0637.
2. T-0031 (PR in this hand-off): ordering only, the owner's order is T-0030, T-0031, T-0032.
3. T-0032: the doorbell grammar (`ring`, `receive`) and the untrusted-data rules.
4. L-0636: an unanswered doorbell reads `could not tell`.
5. L-0637: the hub rule, lanes never ring a peer. After L-0636, because both edit `crew_bridge.py` and `autopilot.md`.
6. L-0638: the sabotage mutations for the bridge script, as a tooling-only PR. Last.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (this branch's base is `ce235468`); re-check each anchor.
- No plan.md is published. The implementing session writes the plan, after the tickets above land.
- The lane marker's name and location are whatever T-0029 lands. If T-0029 lands no readable marker, stop and return to the owner. Do not fall back to "linked worktree means lane": an owner may run a main session in a linked worktree.
- An unreadable or corrupt lane marker refuses as `unknown` (exit 3), never as "not a lane".
- The lane prompt's path is named by T-0029. Touch lists `plugin/crew/commands/autopilot.md`; if the lane prompt lives in another file, amend Touch before editing it.
- The tool-name allowlist in `validate-prompts.py` keeps both tool names; only granting them to an agent is refused.
- Known limit, to be stated in the README: a lane can still call `SendMessage` directly if the harness offers the tool to it regardless of the prompt.
- No hook, no change to `hooks.json`, `scope_guard.py`, `crew_ticket.py` or any other `HARNESS` path, and no `sabotage*.py` file.
- direction.md refers to `.work/tickets/T-0030/direction.md` (part 5). That file is not published here.

## Open questions for the owner (recommended option taken)

1. Does the owner want a PreToolUse hook that blocks `SendMessage` in lanes, as a later ticket? Taken: no, until the two cheap controls here are shown to be insufficient. A new blocking hook is a stop-and-ask in this repo, and it is not measured whether hooks fire for that tool.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0637/` in the final PR unless the owner wants it kept.
