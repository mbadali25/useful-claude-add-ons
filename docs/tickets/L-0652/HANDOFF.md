# Cloud handoff: L-0652

**manual `/crew:autopilot sleep` and `wake` (state file under git-common-dir/crew, gated on `scope.allowCliApproval`)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

Not buildable until T-0053 has merged: it extends `crew_sleep.resolve`, which T-0053 adds.

- **Role:** child, split from T-0053, slice 2 of 6.
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0652-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0652/direction.md`, `docs/tickets/L-0652/spec.md`
- **Size:** about 160 production lines (`crew_sleep.py` about 95, `crew_autopilot.py` about 65). No harness path: `crew_autopilot.py` and `autopilot.md` are seam files, not harness, and `python3 scripts/check-tooling-pr.py` must exit 0.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0053 | ready, not merged | Slice 1: the resolver and overlay this extends. Must be merged first. |
| T-0018 | merged | The subcommand router this extends. |
| T-0010 | merged | `scope.allowCliApproval` gating. |

L-0651 is not required first.

Coordinates with, no order forced: T-0019 / L-0611, T-0012, T-0020 (same router and command file). Merge main before review; conflicts there are mechanical.

This ticket blocks: T-0057 (plain-text `sleep` / `wake`), L-0653 (summary on `wake`), L-0655 (its mutations).

Family order (parent T-0053, six slices):

1. T-0053: the schedule, the resolver, the `approval` / `questions` overrides.
2. After T-0053, in any order: L-0651 (sabotage mutations for slice 1, tooling-only PR), L-0652 (manual `sleep` and `wake`), L-0654 (the `deploy` override).
3. L-0653 (sleep log and morning summary): after T-0053 and L-0652.
4. L-0655 (sabotage mutations for L-0652 to L-0654, tooling-only PR): after L-0651, L-0652, L-0653 and L-0654.
5. L-0656 (overrides for keys that do not exist yet): BLOCKED until T-0029 or T-0067 (review half) and T-0051 (notify half) merge; also needs L-0653.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor. Lines inside `crew_sleep.py` are T-0053's and are read from the merged code.
- No plan.md is published. The implementing session writes the plan.
- `sleep` and `wake` become writers. The only-writer test (`test_approve_is_the_only_writing_subcommand`) is extended, and every document that states the one-writer rule (README, `autopilot.md`'s first paragraph, PLUGINS.md) is updated to name `approve`, `sleep` and `wake`.
- The state file is `<git-common-dir>/crew/autopilot-sleep.json`, written through a temp file and `os.replace`. It is never read from the worktree or from `.work/`.
- Could not tell wakes: a state file that cannot be trusted reads as "no manual state", with a warning.
- No edit to a harness path. `scope_guard.py` is not taught the new commands. No sabotage mutations here (L-0655).
- `autopilot.md` has a tested 110-line budget and is at 109 on `155fe6d8`. If the wording cannot fit, stop and ask: raising the budget is the owner's call.

## Open questions for the owner (recommended option taken)

1. Gating of a session-run `sleep`. Taken: honoured only where `scope.allowCliApproval` is exactly `true`; `wake` is always allowed.
2. `sleep` with no schedule configured. Taken: it ends after 12 hours or at `wake`, whichever is first.
3. The 110-line budget of `autopilot.md`. Taken: reword inside it; the detail is printed by the CLI. Alternative: raise the budget.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0652/` in the final PR unless the owner wants it kept.
