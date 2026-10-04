# Cloud handoff: L-0688

**Refresh admission refuses an artifact removed from the index (lands before L-0540)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** child ticket, split from L-0540 on 2026-10-04, slice 1 of 1. It lands before its parent.
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0688-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0688/direction.md`, `docs/tickets/L-0688/spec.md`
- **Size:** about 20 added production lines in `plugin/crew/hooks/scripts/crew_refresh_check.py` (the check and its reason in `_on_disk`, and the docstring paragraph).
- **Harness:** no harness path. This is a feature PR; `scripts/check-tooling-pr.py` should print `tooling-pr: no harness path changed`.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0094 | merged (PR #285) | Ships `_on_disk` and `artifact_verdicts`. |
| W-0117 | merged (`e51f9db7`) | The `--cached` pass this check extends. |

Nothing open blocks this ticket. It can be worked now.

It blocks L-0540 (the tooling-only PR that wires `artifact_verdicts` into the completion audit). Family order: 1. L-0688, 2. L-0540.

Related, no ordering: L-0624 (direction) adds W-0117's sabotage entry next to the same lines.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- No plan.md is published. The implementing session writes the plan.
- No edit to `completion_audit.py`, `scope_guard.py` or any `plugin/crew/tests/sabotage*.py`. Those are harness paths. The permanent sabotage entry for this check lands with L-0540; here the refusal is hand-run RED once and recorded in the PR body.
- A new artifact with no base copy (untracked or staged) must stay judged as today. The spec has two must-allow tests for it.
- Two unknowns are settled by the new test with real git, not by reasoning: the raw record git prints under `--cached` for a path in the base, absent from the index and present on disk, and whether the non-cached diff prints the same deletion record.
- The module docstring must stop naming L-0540 and must be true both before and after L-0540 lands.
- L-0540's first acceptance check looks for the test name `test_an_artifact_removed_from_the_index_but_left_on_disk_is_refused` in `plugin/crew/tests/test_refresh_admission.py`. Keep that name.
- `plugin/crew/` docs change in the same PR: the README and the daily-workflow guide's refusal list name the new case, and the guide is rebuilt.

## Open questions for the owner (recommended option taken)

1. Refuse only when the `--cached` diff against the base shows the path going to mode `000000` (the base holds it, the index does not). Alternatives: refuse every artifact with an empty `ls-files -s` (rejected, it refuses a new rendered diagram before `git add`), or compare the index blob with the bytes read (wider than the finding).
2. A staged index copy whose bytes differ from the disk copy is still judged from disk. Left out of scope; say if it should be a follow-up.
3. From the parent: L-0688 lands before L-0540, and L-0540 keeps the title, the seed and the tooling half. Alternative: make L-0540 the fix and the wiring the child.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0688/` in the final PR unless the owner wants it kept.
