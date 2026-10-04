# Cloud handoff: L-0680

**The session hooks (notify, handoff-read, handoff-write, context-watch) inherit the main checkout's repo config in a linked worktree**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

**Needs T-0096 merged first.** It uses the resolver T-0096 adds.

- **Role:** child ticket, split from T-0096, slice 1 of 2 (the other is L-0681).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0680-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0680/direction.md`, `docs/tickets/L-0680/spec.md`
- **Size:** about 150 production lines (four PowerShell copies of the resolver at about 28 each, reader edits about 40). No harness path: this is a feature PR. One PR.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0096 | open, not built (direction; handed off 2026-10-04) | Adds `crew_repo_config_dir` / `crew_repo_config_file` in `_common.sh` and `Get-CrewRepoConfigDir`, which this ticket calls and copies. Must be merged first. |
| T-0088 | merged | The Python resolver that is the reference behaviour, and the `_lane` test helper. |
| T-0087 | merged | The tooling-PR rule that decided the split (a dependency of the parent). |

This ticket blocks nothing.

Family order:

1. T-0096 (slice 0): the resolver and the guard-class readers outside the harness.
2. L-0680 (this ticket) and L-0681, in either order. Neither needs the other.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- No plan.md is published. The implementing session writes the plan.
- The resolver's function names and output contract are whatever T-0096 merged. Read T-0096's merged `_common.sh` and `cloud-guard.ps1` before planning; the spec follows what landed.
- Do not change the resolver here beyond copying the PowerShell function. A resolver fix is its own change to T-0096's files.
- Nothing these hooks write moves: transcripts, markers and the handoff note stay in the worktree. The `.crew/` directory gates stay.
- `notify.ps1` is also called in-process by `context-watch.ps1`: confirm the copied function is defined once per process or is safe to redefine.
- The docs edit depends on what has landed: the "not yet covered" list drops the session hooks, and is removed entirely if L-0681 has already landed.
- `test_worktree_config_shell.py` and the `.crew/verify.json` rule for it are created by T-0096; this ticket extends both.
- No harness path may be touched. Sabotage is by hand, recorded in the PR body.

## Open questions for the owner (recommended option taken)

1. A lane sends notifications with the main checkout's `notify` settings, so several lanes ping the same channel. Alternative: a lane that should be quiet writes its own config (already possible).
2. An inherited relative `context.handoffPath` names a file in the lane, not in the main checkout. Same as the Python readers.
3. The `.crew/` directory gate is unchanged, so a lane with no `.crew/` directory still gets no context warnings. Alternative: treat an inheriting lane as initialised, which makes a Stop hook create `.crew/` in a lane.
4. From the parent: T-0096 and this ticket could be one PR of about 290 production lines if fewer PRs are preferred. Default taken: separate PRs.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0680/` in the final PR unless the owner wants it kept.
