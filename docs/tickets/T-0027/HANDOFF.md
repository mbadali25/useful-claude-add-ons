# Cloud handoff: T-0027

**T-0010 round-6 follow-ups: `status` warns only when armed; `approve` names an unreadable config**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** standalone ticket (no split children). Already split once on 2026-09-30 into L-0542 and L-0543, which are separate tickets.
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `T-0027-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0027/direction.md`, `docs/tickets/T-0027/spec.md`
- **Size:** about 20 production lines in `plugin/crew/hooks/scripts/crew_autopilot.py`. No harness path.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0010 | merged (PR #261) | The approval and questions policies these findings are about. |

Nothing blocks this ticket and it blocks nothing. It can be worked at any time.

Related, no ordering: L-0542, L-0543 and the in-flight tickets on `crew_autopilot.py` (T-0019/L-0611, T-0029, T-0049) touch the same file in different places. Whichever lands second merges main and re-checks its anchors.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since; re-check each anchor.
- Keep the line `    if not settings(top)["armed"]:` in `approve` byte for byte, and do not rename `test_route_and_status_unaffected_by_approval_policy`. Both are sabotage anchors (`sabotage_autopilot.py`), and this PR may not edit the harness.
- No sabotage mutation is added here: `plugin/crew/tests/sabotage*.py` is harness and may not ride with a feature change. A later tooling-only ticket can add two mutations.

## Open questions for the owner (recommended option taken)

1. Under an unreadable `.crew/config.json` or a non-object autopilot block, `status` keeps the could-not-tell warning. Alternative: print no warning that names a policy key.
2. `settings` returns policy warnings under a new additive key `policyWarnings`. Alternative: no new key, `status` re-derives them.
3. The NIT (approve names an unreadable config) is fixed here. Alternative: decline it.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/T-0027/` in the final PR unless the owner wants it kept.
