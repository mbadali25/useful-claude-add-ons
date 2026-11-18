# crew_standards.py export digest is wrong in a CRLF checkout (core.autocrlf=true)

Priority: P2 (digest check fails or passes wrongly on this Windows host).
Status: needs ticket (no T-/L-/C- id yet). Recorded 2026-11-17 night from tonight's session findings. Priority is the recording agent's proposal under owner authorization; the owner may change it. Scale used: P1 (correctness or safety hole) / P2 (reliability or hygiene) / P3 (docs or cleanup).

Labels: VERIFIED = read or run by a session tonight and reported; INFERRED = reasoned, not run. The recording agent re-read only the spots named under 'Re-checked'; everything else is relayed.

## Problem
VERIFIED by the session: the standards export digest computed in a CRLF checkout differs from the digest of the committed LF text.
## Fix direction
Make `crew_standards.py export` normalise line endings before hashing, or refuse when CRLF is detected. Test with a CRLF fixture; sabotage-test it. Crew change, so docs per CLAUDE.md (`Docs: none - <why>` if none).
