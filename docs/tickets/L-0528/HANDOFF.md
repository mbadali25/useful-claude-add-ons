# Cloud handoff: L-0528

**review_run.py: EXIT_UNVERIFIED and EXIT_PROBE_LIMITED are both 5 (tooling-only PR)**

Handed to a cloud session on 2026-10-05 by owner instruction. Do not pick up locally.

- **Role:** standalone. Filed by owner decision 2026-09-30 from the T-0028 lane's report.
- **INDEX status:** spec (direction and spec approved for hand-off 2026-10-05; the implementing session writes the plan)
- **Branch:** `L-0528-build`, new from origin/main `a555ff37`. Docs only so far, no implementation yet.
- **Files here:** `docs/tickets/L-0528/direction.md`, `docs/tickets/L-0528/spec.md`
- **Size:** 3 production lines in `review_run.py` (the constant and its docstring), about 6 lines in review.md, about 10 test assertions, 1 new test, 1 sabotage entry, plus doc and diagram lines.
- **Harness:** yes. `review_run.py`, `commands/review.md` and `sabotage*.py` are review/gate harness paths, so this lands alone as a tooling-only PR.
- **Breaking:** yes, for any out-of-repo script that reads review exit 5 as "gate red". It now reads 9. Flag it in the CHANGELOG and the PR body.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| L-0527 | spec (PR open, not merged) | Reserves `EXIT_PROBE_CHANGED = 8`, which is why 8 is skipped. Either can land first. |
| T-0087 | merged | The rule that tooling PRs land alone. |

This ticket blocks nothing.

## Read before writing code

- Re-find every `path:line` by content. They were checked at `a555ff37`.
- The decision: `EXIT_UNVERIFIED` moves from 5 to 9, and the probe's 5/6/7 stay. Two reasons. Persisted metrics notes say `codex-probe=5` (`review_metrics.PROBE_LIMITED_NOTE`). And `crew-providers/SKILL.md`, which documents the probe codes, is not in `ALONGSIDE`, so a tooling PR cannot edit it.
- The distinct-values test must find the `EXIT_*` constants by introspection, so a code added later (L-0527's 8) is covered without editing the test.
- Put the sabotage entry in `plugin/crew/tests/sabotage_review.py` (`REVIEW_FIX_MUTATIONS`). `sabotage.py` is at 3381 of 3400 lines.
- A harness change runs the harness rule's suites: the tooling checker, its suite, the golden replay, the seam contracts, and the canary review.

## Open questions for the owner (recommended option taken)

- The new value is 9 (8 is reserved for L-0527).
- The three refusal reasons stay one code, and their stderr text is unchanged.
- Option 2 (moving the probe codes instead) was rejected because it would change the meaning of persisted metrics.

## Before landing

Merge origin/main and take a crew version above main's from the coordinator. Follow the repo's CLAUDE.md: scope discipline, doc updates for `plugin/crew` changes (README, review.md, the guides plus a rebuild, the diagrams, `.crew/codemap/crew.md`), and the tooling-PR rule. Remove `docs/tickets/L-0528/` in the final PR unless the owner wants it kept.
