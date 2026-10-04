# Cloud handoff: L-0669

**Sabotage mutations for the T-0071 tracker fixes (tooling PR)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

Blocked: not workable until T-0071 has merged. The mutation anchors do not exist before then.

- **Role:** child, split from T-0071, slice 1 of 1.
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0669-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0669/direction.md`, `docs/tickets/L-0669/spec.md`
- **Size:** 0 production lines. About 110 lines of mutation tuples in `plugin/crew/tests/sabotage_tracker.py`.
- **Harness:** yes. `plugin/crew/tests/sabotage_tracker.py` is a harness path, so this lands alone as a tooling-only PR. `scripts/check-tooling-pr.py` must print a line starting `tooling-pr: OK`.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0071 | spec, draft PR in this batch, not merged | The code these mutations patch. Hard dependency. |
| T-0087 | merged | The rule that makes this a separate PR. |
| T-0021 | merged | `sabotage_tracker.py` itself. |

This ticket blocks nothing.

Family order: T-0071 (feature PR) -> L-0669 (this tooling PR).

Related, no ordering stated in the spec: PR #394's announced follow-up (T-0037 PR B) also registers mutations in `sabotage_tracker.py`. Whichever lands second merges main.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor. Re-read `crew_tracker.py` and `fix.md` on main after T-0071 merges, before planning.
- No plan.md exists for this ticket. The implementing session writes the plan.
- The spec's `../../spec.md` and `children/1/` references are the local folder layout. Here the parent's spec is `docs/tickets/T-0071/spec.md` on branch `T-0071-build`.
- The mutation list (a) to (k) follows the merged T-0071 code and test names, not the spec's list, if review changed them.
- No production code and no prompt in this PR. `plugin/crew/tests/sabotage.py` is not edited.
- Do not re-anchor an existing mutation. If T-0071 moved an anchored line, that is a T-0071 defect: stop and report it.
- A mutation that comes back green means its test is vacuous for that branch: tighten the test here and say which mutation exposed it.
- After the sabotage run, `git status --porcelain` must print nothing.
- `plugin/crew/tests/` ships inside the plugin, so crew still gets a version bump.

## Open questions for the owner (recommended option taken)

None that block. The parent's open questions are in T-0071's HANDOFF.md; the answer to its question 1 (compatibility read) would change mutations (c) and (d).

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0669/` in the final PR unless the owner wants it kept.
