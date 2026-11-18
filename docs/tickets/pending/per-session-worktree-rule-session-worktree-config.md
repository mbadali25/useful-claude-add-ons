# Per-session worktree rule: one worktree per developer session or agent; design session.worktree off/warn/require

Priority: P1 (shared directories were clobbered tonight and many worktrees are broken).
Status: needs ticket (no T-/L-/C- id yet). Recorded 2026-11-17 night from tonight's session findings. Priority is the recording agent's proposal under owner authorization; the owner may change it. Scale used: P1 (correctness or safety hole) / P2 (reliability or hygiene) / P3 (docs or cleanup).

Labels: VERIFIED = read or run by a session tonight and reported; INFERRED = reasoned, not run. The recording agent re-read only the spots named under 'Re-checked'; everything else is relayed.

## Evidence
VERIFIED by the session: about 22 broken-gitfile directories under `C:\repos\worktrees`, and agents overwrote a shared scratch clone tonight. (Count not re-measured here; re-measure, do not trust it: a count changes itself.)
## Proposal (design needed)
Each session or agent gets its own worktree. A config key `session.worktree` with values `off` | `warn` | `require`: `warn` reports a session working in a directory another session owns; `require` blocks. Default and layer to be decided (`.crew/config.json` vs `~/.claude/crew/config.json`). INFERRED: ownership can be tracked with a marker file in the worktree naming the session.
## Acceptance criteria
Design note; a cleanup procedure for broken-gitfile directories (never reset another agent's directory); config key documented in the Configuration Guide in the same PR; if a hook is added it defaults OFF with a must-block/must-allow suite, sabotage-tested.
