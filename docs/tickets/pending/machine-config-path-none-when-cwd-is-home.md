# crew_hook.machine_config_path returns None when cwd or project root is ~ or an ancestor

Priority: P2 (a valid double confirmation silently does nothing).
Status: needs ticket (no T-/L-/C- id yet). Recorded 2026-11-17 night from tonight's session findings. Priority is the recording agent's proposal under owner authorization; the owner may change it. Scale used: P1 (correctness or safety hole) / P2 (reliability or hygiene) / P3 (docs or cleanup).

Labels: VERIFIED = read or run by a session tonight and reported; INFERRED = reasoned, not run. The recording agent re-read only the spots named under 'Re-checked'; everything else is relayed.

## Problem
VERIFIED by reading (`crew_hook.py` ~409): `machine_config_path` returns None when the cwd or project root is the home directory or an ancestor of it. A valid double confirmation then has no effect and gives no explanation.
## Recommended next step
Decide the behaviour (refuse with a clear message, or write to the user layer `~/.claude/crew/config.json`), then test both layers.
## Acceptance criteria
No silent no-op: either the write succeeds on a defined layer or the user sees why it was refused. Config docs updated (Configuration Guide rule) if a key or default changes.
