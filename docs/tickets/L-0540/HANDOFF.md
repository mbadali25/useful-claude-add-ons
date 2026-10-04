# Cloud handoff: L-0540

**T-0094 tooling half: completion_audit.py + scope_guard.py refresh-artifact admission**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

**Not first in its family: L-0688 must be merged to main before this ticket is built.**

- **Role:** parent ticket with one child, L-0688 (split 2026-10-04). The child is the feature-side fix and lands first; this ticket keeps the title, the seed and the tooling half.
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session, after L-0688 has merged)
- **Priority:** high
- **Branch:** `L-0540-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0540/direction.md`, `docs/tickets/L-0540/spec.md`
- **Size:** about 80 added production lines (`completion_audit.py` about 70 with docstrings, `scope_guard.py` 7 of docstring), plus about 560 lines of tests and sabotage entries, mostly from the seed.
- **Harness:** yes. `completion_audit.py`, `scope_guard.py` and `plugin/crew/tests/sabotage*.py` are review/gate harness paths, so this lands alone as a tooling-only PR. Nothing outside `HARNESS` and `ALONGSIDE` in `scripts/check-tooling-pr.py` may ride with it.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| L-0688 | direction (spec approved for hand-off; branch `L-0688-build`) | The `:795` fix in `crew_refresh_check.py`. Owner rule of 2026-09-30: both holes are closed before the audit calls `artifact_verdicts`. It is a feature PR and cannot ride with harness paths. |
| T-0094 | merged (PR #285, `42d5ef58`) | Ships `crew_refresh_check.artifact_verdicts`, which this ticket wires into the audit. |
| W-0116 | merged (`7de96ec1`) | Closes MUST-FIX `:706`. This ticket only adds its missing sabotage entry. |
| W-0117 | merged (`e51f9db7`) | Rewrote `_on_disk`'s mode check. One seed sabotage entry must be re-pointed at it. |
| T-0100 | INDEX says approved; its code is on origin/main | Added the merged-main narrowing to `completion_audit.audit`. The port sits on top of it. |

Family order: 1. L-0688, 2. L-0540.

The facts recorded for this hand-off list the child as "not filed". The spec says it was filed as L-0688 on 2026-10-04. The spec wins.

This ticket blocks nothing: no INDEX row names L-0540 as a dependency. The docs already describe the narrower rule, so they are wrong until this lands.

Related, no ordering:

- L-0624 (direction) adds W-0117's sabotage entry to the same `sabotage_refresh.py`.
- L-0539 (direction) would let a feature's own sabotage entries ride with the feature. It changes the split rationale, not this ticket's content.
- L-0553 (direction) edits `worktree_changes` in the same harness file.
- L-0511 and L-0522 (direction, in progress) concern when the refresh runs.

Whichever lands second merges main (never rebase) and re-runs the anchor test.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`), and the line numbers move again when L-0688 lands. Re-check each anchor after L-0688 is on main.
- No plan.md is published. The spec says to plan after L-0688 has merged, against main at that time. The implementing session writes the plan.
- The spec's first acceptance check is a precondition that stops the work if L-0688 has not landed. Run it first.
- **The seed is not in this PR.** direction.md and spec.md refer to `.work/tickets/L-0540/seed/` and `harness-half.patch`. `.work/` is not tracked, and only direction.md and spec.md were published. Whether the cloud session can get the seed files could not be told from the files; ask the owner before re-deriving them.
- The seed's `completion_audit.py` is not copied over main's. T-0100 changed the same function, so the four admission functions (`_verdicts`, `_default_artifacts`, `_outside_refresh_artifacts`, `_entry`) and the docstring paragraph are ported by hand.
- One seed sabotage entry (`git diff --raw failing reads as unchanged`) matches nothing on main since W-0117 and must be re-pointed. 11 of the 15 `completion_audit.py` entries match only after the port.
- Nothing was run when the spec was written: no pytest, no sabotage. The seed's sabotage anchors were checked statically only.
- No edit to `crew_refresh_check.py`, `plugin/crew/commands/done.md` or `implement.md`, `scripts/check-tooling-pr.py` or `plugin/crew/tests/sabotage.py`. New sabotage entries go in `sabotage_refresh.py`.
- Design defaults taken in the spec: the artifacts judged come from the merged-main-narrowed list, and `reach` is the un-narrowed list. Reuse the second listing the audit already makes; do not add a third.
- The spec asks for the hand-run RED results in `.work/tickets/L-0540/sabotage-run.md`. That path is untracked, so where a cloud session records them could not be told; put them in the PR body unless the owner says otherwise.

## Open questions for the owner (recommended option taken)

1. Order and identity: L-0688 (the `:795` fix, feature PR) lands before L-0540, and L-0540 keeps the title, the seed and the tooling half. Alternative: make L-0540 the fix and the wiring the child.
2. Fold L-0624 (W-0117's sabotage entry) into L-0540? Recommended: fold, since both edit `sabotage_refresh.py` in a tooling-only PR. Taken: **not folded** (another ticket's scope). This is the one place where the recommended option was not taken.
3. Reach after a catch-up merge is un-narrowed, so merged-in main paths can reach an artifact (matches the README and `ticket_freshness`). Alternative: only the ticket's own paths reach, which makes the audit refuse a re-anchor that `/crew:done` check 4 demands.
4. The dangling-symlink rule test keeps `[could not tell:` by stubbing `_read_regular`, and a second audit test asserts `[a symlink, which no refresh writes]`.
5. L-0688: a staged index copy whose bytes differ from the disk copy is still judged from disk. Left out of scope; say if it should be a follow-up.
6. T-0100's INDEX row says "approved" although its code is on origin/main. The row was not edited.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0540/` in the final PR unless the owner wants it kept.
