# Cloud handoff: L-0681

**The verify gate, the scope and completion wrappers and the review gate inherit the main checkout's repo config in a linked worktree (tooling PR)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

**Needs T-0096 merged first.** **Tooling PR: every production file here is a review/gate harness path, so this lands alone with no feature work.**

- **Role:** child ticket, split from T-0096, slice 2 of 2 (the other is L-0680).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0681-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0681/direction.md`, `docs/tickets/L-0681/spec.md`
- **Size:** about 125 production lines (three PowerShell copies of the resolver at about 28 each, bash edits about 25, Python about 10, PowerShell reader edits about 10). **Touches harness paths:** `verify-gate.sh`/`.ps1`, `scope-guard.sh`/`.ps1`, `completion-audit.sh`/`.ps1`, `review_gate.py`, `verify_fingerprint.py`, `sabotage_limit_worktree.py`. Risk is marked high in the spec. One PR.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0096 | open, not built (direction; handed off 2026-10-04) | Adds `crew_repo_config_dir` in `_common.sh` and the `Get-CrewRepoConfigDir` PowerShell function this ticket uses and copies. Must be merged first. |
| T-0088 | merged | The Python resolver, and the two pins this slice removes (the `ALLOWED` entries in `test_worktree_config.py` and the lane test in `test_review_gate.py`). |
| T-0087 | merged | The tooling-PR rule and the harness rule's suites this PR must pass. |

This ticket blocks nothing.

Family order:

1. T-0096 (slice 0): the resolver and the guard-class readers outside the harness.
2. L-0681 (this ticket) and L-0680, in either order. Neither needs the other.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- No plan.md is published. The implementing session writes the plan.
- No file outside `HARNESS` and `ALONGSIDE` in `scripts/check-tooling-pr.py` may change. No `Tooling-seam:` trailer is expected; if a `SEAM` file turns out to need an edit, stop and amend the spec first.
- The resolver is used as T-0096 landed it. Read merged main for its names before planning; make no bash resolver change here.
- `verify-gate.sh` and `review_gate.py` move in one commit, so they never disagree about a stand-down. The pinned test `test_a_lane_follows_its_own_gate_not_the_main_checkouts_stand_down` is flipped, not deleted.
- This ticket also adds the sabotage mutations for the whole T-0096 family (resolver, cloud guard, these readers) to `sabotage_limit_worktree.py`, not to `sabotage.py`, which is at its module-line limit.
- If L-0680 has not landed, its eight scripts go in the new allowlist test with the reason L-0680, and the docs keep only L-0680's hooks in the "not yet covered" note.
- The first gate run in each inheriting lane after the upgrade re-runs its commands once, because the fingerprint now hashes the main checkout's config.
- The sabotage suite is heavy; the spec says the cloud session runs it.

## Open questions for the owner (recommended option taken)

1. This can loosen a lane: an inherited `"verifyGate": false` stands the lane's Stop gate down and `/crew:review` reads NO_GATE there, where today the lane's gate runs. Default taken: yes, it is the owner's setting; a lane that must be gated writes its own config. `verify-gate --ci` still exits 2.
2. With no python, a lane where git cannot name the main checkout (`unknown`) is not provably off, so writes and the Stop are blocked. Alternative: today's fail-open.
3. `.crew/verify.json` is not inherited; a lane with no verification map still has no gate. Unchanged.
4. Accepted as risk in the spec: Windows PowerShell 5.1 fails closed on a present resolved config (no System.Text.Json), as it does on the own file today.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0681/` in the final PR unless the owner wants it kept.
