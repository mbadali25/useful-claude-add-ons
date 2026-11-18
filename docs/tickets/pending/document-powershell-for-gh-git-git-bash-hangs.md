# Document PowerShell for gh and git: agents spawning git/gh under Git Bash hang on this host

Priority: P2 (repeated agent hangs; the rule is cheap to document).
Status: needs ticket (no T-/L-/C- id yet). Recorded 2026-11-17 night from tonight's session findings. Priority is the recording agent's proposal under owner authorization; the owner may change it. Scale used: P1 (correctness or safety hole) / P2 (reliability or hygiene) / P3 (docs or cleanup).

Labels: VERIFIED = read or run by a session tonight and reported; INFERRED = reasoned, not run. The recording agent re-read only the spots named under 'Re-checked'; everything else is relayed.

## Problem
VERIFIED by tonight's agents (not re-measured here): agents that spawn git or gh under Git Bash hang on this host. This ticket's own brief says run gh and git from PowerShell.
## Acceptance criteria
The agent-brief guidance (CLAUDE.md or the steward skill, whichever the owner prefers) states "gh and git from PowerShell on this host"; the cause is investigated and labelled (INFERRED candidates: MSYS fork limits, the "fork errno 11" noted in CLAUDE.md). Docs only unless a crew file changes.
