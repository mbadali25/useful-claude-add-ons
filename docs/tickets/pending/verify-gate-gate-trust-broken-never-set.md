# verify-gate.sh: GATE_TRUST_BROKEN is tested but never set

Priority: P3 (dead branch, no known user-visible effect yet).
Status: needs ticket (no T-/L-/C- id yet). Recorded 2026-11-17 night from tonight's session findings. Priority is the recording agent's proposal under owner authorization; the owner may change it. Scale used: P1 (correctness or safety hole) / P2 (reliability or hygiene) / P3 (docs or cleanup).

Labels: VERIFIED = read or run by a session tonight and reported; INFERRED = reasoned, not run. The recording agent re-read only the spots named under 'Re-checked'; everything else is relayed.

## Problem
VERIFIED by grep on main, `verify-gate.sh` ~2689: `GATE_TRUST_BROKEN=0` is initialised and `[ "$GATE_TRUST_BROKEN" -eq 0 ] || _trust_rc=14` tests it; the grep found no assignment to a non-zero value (the grep output was limited to its first matches; re-confirm with a full search). If so the branch is dead.
## Acceptance criteria
Either set it where the broken-trust condition is detected (with a test) or delete the test and the dead code. Related: `verify-gate-trust-codes-10-13-exit-0.md`.
