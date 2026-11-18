# verify-gate.sh: trust-check codes 10-13 exit 0, only 14 exits 2

Priority: P2 (a Stop may finish after a message saying nothing was verified; possibly intended).
Status: needs ticket (no T-/L-/C- id yet). Recorded 2026-11-17 night from tonight's session findings. Priority is the recording agent's proposal under owner authorization; the owner may change it. Scale used: P1 (correctness or safety hole) / P2 (reliability or hygiene) / P3 (docs or cleanup).

Labels: VERIFIED = read or run by a session tonight and reported; INFERRED = reasoned, not run. The recording agent re-read only the spots named under 'Re-checked'; everything else is relayed.

## Problem
VERIFIED (read by a session; `git show origin/main:plugin/crew/hooks/scripts/verify-gate.sh` shows `14) gate_trust_broken; exit 2 ;;`, line ~1777): trust-check codes 10 UNTRUSTED, 11 CHANGED, 12 REMOTE CHANGED and 13 UNKNOWN exit 0; only 14 exits 2. The message says nothing was verified, yet the turn may finish.
UNDETERMINED: whether this is intended (warn-only trust) or a gap.

## Recommended next step
Read the design note for the trust states, decide intended or not, then add a must-block/must-allow case for each code to the suite and sabotage-test it (CLAUDE.md "Adding a hook" rule).

## Acceptance criteria
Each of 10-14 has a stated, tested exit behaviour; the message matches the exit.

## Owner question
Should an unverified Stop block (exit 2) for 10-13, or is warn-and-allow the design?
