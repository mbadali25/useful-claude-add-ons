# Cloud handoff: T-0096

**Worktree config inheritance for the shell and PowerShell config readers T-0088 excluded: the resolver, and the guard-class readers outside the harness (slice 0 of three)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** parent ticket, narrowed to slice 0. Children: L-0680 (session hooks) and L-0681 (harness readers, tooling PR).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `T-0096-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0096/direction.md`, `docs/tickets/T-0096/spec.md`
- **Size:** about 140 production lines (`_common.sh` about 42, three PowerShell copies of the resolver at about 28 each, reader edits about 15). No harness path: this is a feature PR. Risk is marked high in the spec.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0088 | merged | The Python resolver (`crew_common.repo_config_dir`) the shell resolvers must agree with, and the `_lane` test helper. |
| T-0087 | merged | The tooling-PR rule (`HARNESS` in `scripts/check-tooling-pr.py`) that forces the harness readers into their own PR. |

Nothing open blocks this ticket. It blocks L-0680 and L-0681: both use the resolver added here.

Family order:

1. T-0096 (this ticket, slice 0): the resolver in both flavours, plus `_common.sh` (incident stand-down), `cloud-guard.sh`/`.ps1`, `promote-gate.ps1`, `auto-clear.ps1`.
2. L-0680 and L-0681, in either order. Each needs T-0096 and neither needs the other. L-0681 is a tooling PR and lands alone.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor. Other lanes edit these hooks.
- No plan.md is published (none existed). The implementing session writes the plan.
- In direction.md and spec.md, "child 1" and `children/1` mean L-0680; "child 2" and `children/2` mean L-0681.
- No harness path may be touched here: not `verify-gate.*`, `scope-guard.*`, `completion-audit.*`, `review_gate.py`, nor any `plugin/crew/tests/sabotage*.py`. `test_a_lane_follows_its_own_gate_not_the_main_checkouts_stand_down` and the `review_gate.py` allowlist entry stay exactly as they are and stay green.
- Sabotage is by hand in this PR, recorded in the PR body with the red test named for each mutation. The mutations are added to the sabotage suite by L-0681.
- The PowerShell resolver is copied verbatim into each script that needs it (there is no shared `.ps1` file); a test asserts the copies are byte-identical.
- Between this slice and L-0681, `verify-gate.ps1`'s inline incident stand-down check reads the worktree's own file while the bash gate and `crew_incident.py` read the inherited one. The docs this slice edits must name that.
- The change can loosen as well as tighten: an inherited `cloudGuard: off` applies in a lane.

## Open questions for the owner (recommended option taken)

1. In a no-python guard fallback, when git cannot name the main checkout (`unknown`), the cloud guard counts as armed and refuses. Alternative: treat it as the own file being absent, which is today's fail-open. Cost of the default: a lane with broken git and no python blocks until one works.
2. The `.crew/` directory gates in `context-watch` and `auto-clear` stay as they are, so a lane with no `.crew/` directory still gets no context warnings even when the main checkout has a config. Alternative: treat an inheriting lane as initialised.
3. Three PRs and three crew version bumps. L-0681 must be separate (tooling-PR rule); T-0096 and L-0680 could be one PR of about 290 production lines if fewer PRs are preferred.
4. An inherited relative `context.handoffPath` names a file in the lane, not in the main checkout. Same as the Python readers.
5. The `verify-gate.ps1` stand-down divergence between this slice and L-0681 is accepted and documented. Alternative: land L-0681 immediately after this slice.
6. `.crew/verify.json` is not inherited (the resolver covers `config.json` and `crew.json` only). Unchanged.
7. Accepted as risk in the spec: no git timeout in the bash resolver, and symlinked `.git` paths on Windows PowerShell 5.1 (must read `unknown`, never `main`, if 5.1 differs).

Questions that belong to the children (an inherited `verifyGate: false` loosening a lane; every lane notifying with the main checkout's settings) are listed in L-0681 and L-0680.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/T-0096/` in the final PR unless the owner wants it kept.
