# Code map — index

Not counted as a subsystem by `crew_state.py` (`read_knowledge`,
`plugin/crew/hooks/scripts/crew_state.py:222-223` lists `INDEX.md` in
`_NOT_SUBSYSTEMS`). It exists purely as a table of contents.

Every subsystem file below carries an `anchor:` line
(`plugin/crew/hooks/scripts/crew_state.py:218-220` is the regex that reads it)
naming the short commit hash the file's claims were checked against. If HEAD
has since moved past that hash, `crew_state.py` will list the file under
`knowledge.behind` at the next SessionStart — that is a prompt to re-check the
claims, not proof they are wrong.

## Files

| File | Covers |
|---|---|
| [`marketplace-registration.md`](marketplace-registration.md) | The marketplace itself: what registers a skill vs. a plugin, the two install scripts, and the two separate version-check paths (`check-marketplace.py` vs. `_verify/smoke.sh`). |
| [`localgpu.md`](localgpu.md) | The `localgpu` plugin: its two independent process trees, the shared-Ollama constraint that drives `OLLAMA_MAX_LOADED_MODELS=1`, the embed-model mismatch guard, `.mcp.json` provisioning, and the bootstrap.sh/bootstrap.ps1 parity verdict. |
| [`crew.md`](crew.md) | The `crew` plugin: hooks, agents, commands, skills inventory, and how `crew_state.py` reads this very directory. |
| [`verification-harness.md`](verification-harness.md) | `_verify/smoke.sh`, `_verify/run-all.sh`, `scripts/check-marketplace.py`, and `.crew/verify.json` — what each actually runs, and where they overlap or don't. |

## How to read these files

Every non-obvious claim is marked **DERIVED** (read from source, with a
`path:line` a reader can re-check) or **JUDGEMENT** (this writer's
interpretation of why something is the way it is). A DERIVED claim that turns
out wrong on re-check is more valuable to flag than to quietly leave — say so
in the file rather than deleting the claim, so the next reader knows it was
checked and found stale.

These files do not restate `CLAUDE.md`. That file holds the judgement calls
and the landmines already earned by past incidents; this directory holds the
map — what is actually true of the code right now, at the anchored commit.
