# Dev-review waiver receipt for tsslive: waiver commit chases main, one waiver slot per rung

Priority: P2 (two PRs (TheSelectSource #2925 and #2926) contend for one slot).
Status: needs ticket (no T-/L-/C- id yet). Recorded 2026-11-17 night from tonight's session findings. Priority is the recording agent's proposal under owner authorization; the owner may change it. Scale used: P1 (correctness or safety hole) / P2 (reliability or hygiene) / P3 (docs or cleanup).

Labels: VERIFIED = read or run by a session tonight and reported; INFERRED = reasoned, not run. The recording agent re-read only the spots named under 'Re-checked'; everything else is relayed.

## Problem
VERIFIED by the session (not re-read here): the waiver commit chases main, so a receipt goes stale whenever main moves, and there is one waiver slot per rung, so TheSelectSource PR #2925 and PR #2926 contend for it.
## Acceptance criteria
Decide a receipt that binds to the PR head or a merge-base, or a slot per PR; document it; a test with two concurrent PRs. Owner question: is one waiver per rung intended?
