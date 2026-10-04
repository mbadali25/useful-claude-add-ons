# Cloud handoff: L-1508

**A tool is run the way it was found: no bare-name subprocess on Windows**

Created on 2026-10-04 by owner request, after two Windows-only bugs in one landing batch (T-0016 `_tmux_pane_pid`, T-0017 `_git_out`, the second fail-open).

- **Role:** parent, 2 slices: PR A (feature) then PR B (harness-only, lands alone under T-0087).
- **INDEX status:** direction + spec written; plan to be written by the implementing session.
- **Branch:** `L-1508-build`, new from origin/main `f1cace4a`; docs only, no implementation yet.
- **Files here:** `direction.md`, `spec.md`.
- **Size:** about 40 production lines (resolver plus ~12 call sites) and about 200 test lines in PR A; about 15 production lines in PR B.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0016 | merged (#396) | Carries the `_tmux_pane_pid` fix this ticket generalises. |
| T-0017 | #356, landing | Carries the `_git_out` fix; land it first so PR A does not conflict in `crew_autocycle.py`. |
| L-1507 | #492, open | CI only; no overlap. |

## Read before writing code
- `docs/tickets/L-1508/direction.md` and `spec.md`
- `skills/intune-graph/scripts/auth.py` `_find_az` (the precedent)
- `scripts/check-tooling-pr.py` `HARNESS`, `SEAM`, `ALONGSIDE`
- The two fixes: `git show cdb7b508` and `git show 9a34b335`

## Notes for the builder
- Never skip a Windows test to get green; a red Windows shard here is a real finding.
- Get PR A's own Windows CI green before asking for it to be batched.
