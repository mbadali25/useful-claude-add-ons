# Cloud handoff: T-0081

**crew_tracker's vault walk matches every directory's identity, not just the vault's, on Windows and POSIX (T-0077 round-2 accepted FIX)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** parent with one child, L-0672 (the sabotage mutations for this guard, a tooling PR). This spec is slice 1 of 2.
- **INDEX status:** direction, priority med (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `T-0081-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0081/direction.md`, `docs/tickets/T-0081/spec.md`
- **Size:** about 45 production lines, all in `plugin/crew/hooks/scripts/crew_tracker.py`. No harness path: a feature PR. `git diff --name-only origin/main...HEAD` must list no harness path.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0077 | merged | The Windows handle pin (`_hold_dirs`, `_win_open_dir`) this ticket extends. |
| T-0021 | merged | `crew_tracker.py` and the POSIX pinned walk. |
| T-0087 | merged | The tooling-PR rule that forces the split of the sabotage mutations. |
| T-0076 | done | The native Windows crew suite is green and required; it resolves the Windows identity unknown before land. |

Nothing unmerged must land first. This ticket can be worked now.

Related, same file, no order forced: T-0071, L-0530, L-0571. Whichever lands second merges main and re-reads its line numbers. PR #394 (T-0037, open on 2026-10-04) also edits `crew_tracker.py`; that is not in the spec or the facts and is added here for the same reason.

This ticket blocks L-0672: its anchors do not exist until this merges.

Family order: T-0081 (this feature PR) -> L-0672 (tooling PR).

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- No plan.md exists for this ticket. The implementing session writes the plan.
- The existing sabotage anchors in `plugin/crew/tests/sabotage_tracker.py` (87 at `155fe6d8`) must each still occur exactly once in `crew_tracker.py`, and that file may not be edited here. Do not add a second line equal to any of the four the spec's Design names. Putting the new comparison in one helper avoids all four.
- An identity that cannot be told refuses as "could not tell": a recorded `None`, a list of the wrong length, or `st_ino` 0 on either side. It is never read as "the same directory".
- The Windows unknown is resolved only by a native Windows run of `test_crew_tracker.py` on the PR. If that check does not run, say so in the PR body; do not report the Windows branch as verified.
- Sabotage by hand is part of this PR's acceptance checks and is recorded in the PR body, on a scratch copy or with `PYTHONDONTWRITEBYTECODE=1`. The committed mutations are L-0672.
- `test_the_windows_pin_blocks_renames_while_held_and_frees_them_after` builds a `paths` dict by hand and needs the new key.
- direction.md's two "Owner decision 2026-09-30" notes describe the owner's local setup. The merge-not-rebase rule still applies. Whether the parallel-run setup exists in the cloud session: could not tell.

## Open questions for the owner (recommended option taken)

1. POSIX: a vault or component whose `st_ino` is 0 now refuses the write as "could not tell" (today it passes). Taken: refuse, as Windows already does. Is there a vault on a file system that reports no inodes that this would break?
2. The guard lands first and its committed mutations follow in L-0672, so main carries the guard without them for one PR. Taken: accept that order, with a by-hand sabotage of each new branch recorded in this PR's body. Mutations first is not possible: their anchors would not exist.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/T-0081/` in the final PR unless the owner wants it kept.
