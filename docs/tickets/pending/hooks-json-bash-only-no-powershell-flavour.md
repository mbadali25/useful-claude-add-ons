# hooks.json registers only bash crew-hook.sh, no per-flavour powershell entries

Priority: P1 (CLAUDE.md landmine says a bare command goes to Git Bash on Windows; a host without Git Bash on PATH may run no crew hook).
Status: needs ticket (no T-/L-/C- id yet). Recorded 2026-11-17 night from tonight's session findings. Priority is the recording agent's proposal under owner authorization; the owner may change it. Scale used: P1 (correctness or safety hole) / P2 (reliability or hygiene) / P3 (docs or cleanup).

Labels: VERIFIED = read or run by a session tonight and reported; INFERRED = reasoned, not run. The recording agent re-read only the spots named under 'Re-checked'; everything else is relayed.

## Problem
VERIFIED (`git show origin/main:plugin/crew/hooks/hooks.json`, re-checked 2026-11-17): every registration is `bash "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew-hook.sh" <Event>` with no `"shell": "powershell"` sibling. `plugin/PLUGINS.md` still describes dual registration (VERIFIED by the session, not re-read here). `CLAUDE.md` landmines say to set `shell: "powershell"` and register each event once per flavour.
INFERRED, unrun: on a Windows host where Git Bash is not on PATH, `bash` fails and no crew hook runs; the failure may be silent.

## Recommended next step
Run the hooks on a Windows host without Git Bash on PATH and record what happens. Then either restore per-flavour entries or correct PLUGINS.md and the landmine to say the single bash entry is intended (and why the native Python route makes it safe).

## Acceptance criteria
- A recorded run on a host without Git Bash on PATH (host, shell and result stated).
- hooks.json, PLUGINS.md and CLAUDE.md agree. A crew change updates every doc per CLAUDE.md; hook-adding rules apply (default OFF, must-block and must-allow suite, sabotage test) if entries are added.

## Owner question
Is bash-only intended since the Python `crew_hook.DIRECT` route?
