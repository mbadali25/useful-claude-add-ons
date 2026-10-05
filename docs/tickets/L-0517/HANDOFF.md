# Cloud handoff: L-0517

**heavy-run logs each lane's slot wait (lane, slot, waited seconds, start/end) so contention is measurable**

Handed to a cloud session on 2026-10-05 by the orchestrator under the owner's standing self-approve authority.

- **Role:** standalone ticket (repository tooling).
- **INDEX status:** spec (direction and spec approved for hand-off 2026-10-05; plan to be written by the implementing session)
- **Branch:** `L-0517-build`, new from origin/main `a555ff37`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0517/direction.md`, `docs/tickets/L-0517/spec.md`, `docs/tickets/L-0517/heavy-run.snapshot` (copy of the machine-local wrapper, 2026-10-03, sha256 `171b95c2...`)
- **Size:** about 6 production lines in `scripts/gate-runner.py`, 2-3 suite cases, and a ~25-line patch to the machine-local wrapper.
- **Harness:** no. `scripts/gate-runner.py` is not in `HARNESS`; no `plugin/crew/` change, no crew version bump.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| L-0513 | done (PR #301) | The gate runner this extends. |
| L-0570 | direction | Also edits `scripts/gate-runner.py`, other lines. No ordering; merge conflicts only. |

This ticket blocks nothing.

## Read before writing code

- Two parts. (1) In-repo: `gate-runner.py --inner` records `HEAVY_RUN_SLOT` as `slot` in `heavy-part.json`, the outer copies it to `status.json`'s `heavy_run.slot` (`null` when absent or malformed). (2) Machine-local: write `docs/tickets/L-0517/heavy-run.patch` against `heavy-run.snapshot`: one JSONL line per invocation to `/root/crew-tmp/heavy-run-waits.jsonl` from the EXIT trap, and `export HEAVY_RUN_SLOT` while a slot is held.
- A cloud session cannot reach `/root/crew-tmp`. Check that the patch applies and passes `bash -n`; the LOCAL acceptance checks run on the owner's host after the patch is applied there.
- Unknowns must stay unknown: `slot`, `acquired`, `held_s` are `null` when there was no slot; `lane` is `"unknown"` when nothing identifies it. Never a guessed default.
- Evidence anchors were checked at origin/main `a555ff37`; re-find by content if main has moved.
- No plan.md is published. The implementing session writes the plan.

## Open questions for the owner (recommended option taken)

All in direction.md under "Open questions (default taken)": log path and JSONL format, lane identity order, one line per invocation from the EXIT trap (a call that gave up waiting logs `acquired: null`), no rotation, no aggregator script. Option taken: the wrapper logs every acquisition and the gate runner records its slot (over in-repo-only logging, which misses most callers, and over moving heavy-run into the repo).

## Before landing

Merge origin/main, follow the repo's CLAUDE.md (scope discipline, repository-tooling CHANGELOG entry with no plugin version, codemap re-anchor), have the owner's local session apply `heavy-run.patch` to `/root/crew-tmp/heavy-run` and run the LOCAL checks, then remove `docs/tickets/L-0517/` in the final PR unless the owner wants it kept.
