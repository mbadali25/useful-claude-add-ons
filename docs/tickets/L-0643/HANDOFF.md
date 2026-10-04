# Cloud handoff: L-0643

**Sabotage mutations for T-0043's autopilot fixes and the fence parser (tooling PR, lands alone)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** child, split from T-0043, slice 2 of 2 (the family is T-0043, L-0642, L-0643). The spec calls it a complete ticket on its own.
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0643-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0643/direction.md`, `docs/tickets/L-0643/spec.md`
- **Size:** 0 production lines; about 60 lines (ten table rows) in `plugin/crew/tests/sabotage_autopilot.py`. **This touches a review/gate harness path**, so it lands alone as a tooling-only PR with no feature work.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0043 | ready, not started | Must be merged first: it adds the FINDINGS branch, the reworded reason and the three tests the first three mutations name. |
| L-0642 | direction, spec written, not started | Must be merged first: it adds the parser and the tests the seven fence mutations name. |
| T-0087 | merged | The tooling-PR rule and the harness verify rule this PR runs under. |
| T-0004 | merged | `sabotage_autopilot.py` itself. |

Blocked until T-0043 and L-0642 are on main. If L-0642 is delayed, this ticket waits with it (the option taken).

This ticket blocks nothing. It is the last of the family.

Family order:

1. **T-0043**: the FINDINGS-stop fixes. Feature PR.
2. **L-0642**: the fence parser. Feature PR.
3. **L-0643** (this ticket): ten sabotage mutations. Tooling-only PR.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (this branch starts at `ce235468`); re-check each anchor. The anchors themselves do not exist until the two feature PRs land; read the merged `crew_autopilot.py` then, and quote each `find` string with a `grep -c` of 1. The parent's hand-off notes that child spec evidence was spot-checked only.
- There is no plan.md and none is published. The implementing session writes the plan.
- No production file changes: nothing under `plugin/crew/hooks/`, `plugin/crew/commands/`, `plugin/crew/agents/` or `scripts/`. No `Tooling-seam:` trailer. If a mutation cannot be anchored without editing `crew_autopilot.py`, stop and report it.
- No new test of behaviour. Each mutation names a test T-0043 or L-0642 already added; name the test that was measured to go red, not the expected one.
- No change to `plugin/crew/tests/sabotage.py`, to the golden corpus, or to any other mutation's anchor.
- Other tickets also append to `sabotage_autopilot.py` in their own tooling PRs (L-0668, L-0671). Whichever lands later merges main in.
- The harness verify rule is run in full and its result quoted; any step that did not run is named as not verified.
- `sabotage.py` is a heavy suite: run it once, serially, and report the wall time. Quote any failure verbatim. Afterwards `git status --short` shows no `.bak`.
- A stated mutation count in any document is re-measured, never incremented by hand.

## Open questions for the owner (recommended option taken)

1. If L-0642 is delayed, this ticket waits with it. Alternative: land T-0043's three mutations first and file the fence mutations as a further tooling ticket.
2. One tooling PR after both feature PRs. Alternative: one tooling PR per feature PR.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0643/` in the final PR unless the owner wants it kept.
