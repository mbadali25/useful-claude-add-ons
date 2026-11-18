# #780: STOP_BUDGET_BOUNDS includes 600 (= hook timeout); reader accepts 0 and floats the writer rejects

Priority: P2 (a budget equal to the hook timeout leaves no margin; reader/writer disagree).
Status: needs ticket (no T-/L-/C- id yet). Recorded 2026-11-17 night from tonight's session findings. Priority is the recording agent's proposal under owner authorization; the owner may change it. Scale used: P1 (correctness or safety hole) / P2 (reliability or hygiene) / P3 (docs or cleanup).

Labels: VERIFIED = read or run by a session tonight and reported; INFERRED = reasoned, not run. The recording agent re-read only the spots named under 'Re-checked'; everything else is relayed.

## Problem
VERIFIED by the session (not re-read here): `STOP_BUDGET_BOUNDS` is (1, 600) and 600 equals the hook timeout, so a budget of 600 cannot finish inside it. The reader at `verify-gate.sh` ~1935 accepts 0 and floats that the writer rejects.
## Acceptance criteria
Upper bound strictly below the timeout (or the timeout raised), reader and writer share one validation rule, tests for 0, floats and the bounds. Configuration Guide updated if a documented bound changes. Siblings: `follow-up-780-full-suite-and-unidentified-failure.md`.
