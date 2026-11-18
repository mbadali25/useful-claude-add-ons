# crew_reaper.py: only the parent is re-validated before kill; stale child pids can hit a reused pid

Priority: P1 (taskkill /F on a reused pid could kill an unrelated process).
Status: needs ticket (no T-/L-/C- id yet). Recorded 2026-11-17 night from tonight's session findings. Priority is the recording agent's proposal under owner authorization; the owner may change it. Scale used: P1 (correctness or safety hole) / P2 (reliability or hygiene) / P3 (docs or cleanup).

Labels: VERIFIED = read or run by a session tonight and reported; INFERRED = reasoned, not run. The recording agent re-read only the spots named under 'Re-checked'; everything else is relayed.

## Problem
VERIFIED by reading (`crew_reaper.py` ~497): before a kill only the parent is re-validated. Child pids come from a snapshot that may be more than 5 s old; if a child exited and its pid was reused, `taskkill /F` could kill an unrelated process. INFERRED: the reuse window is real but no reuse was reproduced.
## Fix direction (INFERRED)
Re-validate each child (pid plus start time or creation time, and ppid) immediately before killing it.
## Acceptance criteria
A test with a table where the child pid is reused (different start time) is not killed; sabotage test goes red when the re-check is removed.
