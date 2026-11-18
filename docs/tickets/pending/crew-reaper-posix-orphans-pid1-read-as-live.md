# crew_reaper.py: POSIX orphans reparented to pid 1 read as live, reaper never kills them

Priority: P2 (leak of orphaned processes on POSIX; Windows path unaffected).
Status: needs ticket (no T-/L-/C- id yet). Recorded 2026-11-17 night from tonight's session findings. Priority is the recording agent's proposal under owner authorization; the owner may change it. Scale used: P1 (correctness or safety hole) / P2 (reliability or hygiene) / P3 (docs or cleanup).

Labels: VERIFIED = read or run by a session tonight and reported; INFERRED = reasoned, not run. The recording agent re-read only the spots named under 'Re-checked'; everything else is relayed.

## Problem
VERIFIED with synthetic process tables only, not on real Linux (session report; code near `crew_reaper.py` ~308 on main, `parent = procs.get(proc["ppid"])`): an orphan reparented to pid 1 (or a subreaper) finds a parent in the table and is judged owned, so it is never killed.
## Fix direction (INFERRED)
Treat pid 1 and a known subreaper as not an owner. Reproduce on a real Linux host first.
## Acceptance criteria
A real-Linux (or container) reproduction before and after; a synthetic-table test with pid 1 and a subreaper; sabotage test reverting the rule goes red.
