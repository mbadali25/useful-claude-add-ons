# Verify CREW_HOOK_POSIX_TMP with a live Claude Code Stop trace

Priority: P2 (set by crew-hook.sh but only exercised by tests, not by a real Stop).
Status: needs ticket (no T-/L-/C- id yet). Recorded 2026-11-17 night from tonight's session findings. Priority is the recording agent's proposal under owner authorization; the owner may change it. Scale used: P1 (correctness or safety hole) / P2 (reliability or hygiene) / P3 (docs or cleanup).

Labels: VERIFIED = read or run by a session tonight and reported; INFERRED = reasoned, not run. The recording agent re-read only the spots named under 'Re-checked'; everything else is relayed.

## Problem
VERIFIED by grep on main: `crew-hook.sh` now sets `CREW_HOOK_POSIX_TMP` (documented in `crew_hook.py`: the MSYS runtime rewrites `/tmp` on the way). NOT done: a live Claude Code Stop trace showing the value reaches the process and temp files land where expected.
## Acceptance criteria
A recorded Stop trace on this Windows host (host, shell, layer stated) plus a doc line in the crew docs describing the variable.
