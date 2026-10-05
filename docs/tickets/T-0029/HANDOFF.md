# Cloud handoff: T-0029

**`/crew:autopilot wave`: owner-designed ticket set, one group approval, parallel lanes (plan, start/lane-init, lane-prompt/lane-done, collect) (depends on T-0004, T-0018)**

Handed to a cloud session on 2026-10-05 by owner instruction. Do not pick up locally.

- **INDEX status:** in-progress (risk: high)
- **Branch:** `T-0029-wave` (existing local branch, first pushed 2026-10-05). Head before this commit `574985ce`.
- **Implementation:** present. 24 own commits since merge base `6813749b` (2026-09-30); ~2,600 lines across 22 files,
  chiefly `plugin/crew/hooks/scripts/crew_wave.py` (new), `crew_autopilot.py`, `crew_state.py`, `review_ledger.py`,
  `scope_guard.py`, `commands/autopilot.md`. Branch declares crew 1.0.71 and a CHANGELOG entry for it.
- **Review ledger:** budget 2, no rounds run, no receipt. Next phase: review.
- **Files here:** `docs/tickets/T-0029/direction.md`, `spec.md`, `plan.md` (copies of gitignored `.work/tickets/T-0029/`).

## Read before continuing

- **Far behind main:** ~2,870 commits behind origin/main (main is at crew 1.0.35x). Merge origin/main first; expect conflicts in
  `crew_autopilot.py`, `crew_state.py`, `scope_guard.py`, CHANGELOG, version files, codemap and graphify-out.
  Re-bump crew above main's version (from the coordinator) after the merge.
- The scope guard and review ledger are touched: `scope_guard.py` / `review_ledger.py` changes are blocking-hook and
  harness paths. Check `scripts/check-tooling-pr.py` after the merge; if it refuses, split per the tooling-PR rule
  (feature PR, then a tooling-only PR).
- The must-block/must-allow suite (`test_scope_guard_wave.py`) must be sabotage-tested (repo CLAUDE.md, "Adding a hook").
- Owner decisions recorded 2026-09-30: route read + one allowlist entry (lane-init's own-path config copy).
- `graphify-out/` was left dirty locally (a background rebuild, not committed); regenerate with `graphify update .` after the merge.

## Downstream

Blocks T-0031 (#408), T-0067 (#443), L-0656 (#444).

## Before landing

Merge origin/main, take a crew version above main's, follow the repo's CLAUDE.md (scope discipline, doc updates for
`plugin/crew` changes, tooling-PR rule), land as a merge commit, and remove `docs/tickets/T-0029/` in the final PR unless the owner wants it kept.
