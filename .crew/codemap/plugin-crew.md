# plugin/crew
anchor: useful-claude-add-ons@875c9c6f
verified: 2026-09-05

## Does
The marketplace's one full plugin: 24 slash commands and 17 subagents that
run a project "crew", over a Python hook-script layer that keeps durable
state in `.crew/` and `.work/`. Its load-bearing part is not the roles but
the guards — a PreToolUse command guard and a self-review guard that stops
the model family which wrote a diff from reviewing it.

## Entry points
- `plugin/crew/hooks/hooks.json:3` — `SessionStart`: handoff-read, platform-sync, pm-brief
- `plugin/crew/hooks/hooks.json:11` — `PreToolUse`: guard + promote-gate, matched per tool (`Bash` at `:12`/`:16`, `PowerShell` at `:14`/`:18`)
- `plugin/crew/hooks/hooks.json:21` — `PreCompact`: handoff-write
- `plugin/crew/hooks/hooks.json:25` — `Notification`: notify
- `plugin/crew/hooks/hooks.json:29` — `Stop`: context-watch, pm-pulse, verify-gate
- 20 hook entries total: every event registered once per shell flavour, `shell: powershell` on the PowerShell side
- `plugin/crew/hooks/scripts/crew_state.py:2061` — `main`, the state CLI every command reads first
- `plugin/crew/hooks/scripts/crew_config.py:1079` — `main`, `--author-stale` reaches `model_report` here
- `plugin/crew/hooks/scripts/crew_incident.py:416`, `plugin/crew/hooks/scripts/pm_brief.py:402`, `plugin/crew/hooks/scripts/pm_pulse.py`, `plugin/crew/hooks/scripts/crew_platform.py`, `plugin/crew/hooks/scripts/hook_once.py` — the other five CLIs
- `plugin/crew/commands/` — 24 commands; `plugin/crew/agents/` — 17 agents

## Owns data
- `.crew/config.json` via `plugin/crew/hooks/scripts/crew_config.py:377` (`resolve_config`), backed up to `.crew/config.json.v1.bak`
- `.crew/codemap/` — this map; backed up once to `.crew/codemap.v1.bak/`
- .crew/incident.json, .crew/incidents/, .crew/incident-skips.log (runtime; created on first incident) via `plugin/crew/hooks/scripts/crew_incident.py:16`
- `.work/dispatch.d/` via `plugin/crew/hooks/scripts/crew_state.py:981` — append-only, one immutable file per dispatch
- .work/dispatch.json (runtime) — legacy/display slot only, recomputed from the store at read time
- .work/HANDOFF.md (runtime) via the PreCompact hook
- `docs/diagrams/` via `/crew:diagram`

## Calls out to
- `graphify` — reads `graphify-out/graph.json`; `plugin/crew/skills/crew-graph/scripts/crew_upgrade.py:461` reconciles it into this codemap
- `git` — branch and HEAD, via `crew_state.current_branch` and `_head`
- `skills/web-testing-playwright/scripts/check_env.py` — the only real code link out of this subsystem
- Otherwise self-contained: of 8548 graph links, the cross-boundary ones are almost all pytest fixture pseudo-nodes

## Landmines
- A `PreToolUse` guard branches on `tool_name`, never on the OS — `plugin/crew/hooks/scripts/_common.sh:20` is that test in shell. A `Bash` tool call is bash syntax even on Windows, and judging it with PowerShell rules is wrong in both directions.
- `crew_tool_dispatch` (`plugin/crew/hooks/scripts/_common.sh:18`, called at `plugin/crew/hooks/scripts/guard.sh:7`) ends in `exit $?`, and `plugin/crew/hooks/scripts/_common.sh:30` says why: `exec` there replaces only the subshell on the right of the pipe, so the guard stops blocking and nothing looks wrong.
- Every PowerShell hook command must end `; exit $LASTEXITCODE` and double-quote `"${CLAUDE_PLUGIN_ROOT}"`. Without the first, a guard's `exit 2` returns 1 — reported as a non-blocking error, command runs anyway. Without the second, PowerShell hands `&` the literal token and the hook dies. `scripts/check-marketplace.py` enforces both.
- The self-review guard's invariant: anything under `.work/` that could not be read makes `author_families`' source `unknown` — never `dispatch` (a positive claim) and never `config` (which asserts nothing was recorded). `plugin/crew/hooks/scripts/crew_state.py:1702`; a record naming a different branch strikes the recorded AND the configured family (`plugin/crew/hooks/scripts/crew_state.py:1715`).
- That report must be made at the filter that drops the evidence, not only in the funnel downstream: `plugin/crew/hooks/scripts/crew_state.py:1028` (`_dispatch_entries`), `plugin/crew/hooks/scripts/crew_state.py:1131` (`_history_items`), `plugin/crew/hooks/scripts/crew_state.py:1186` (`_merge_history`). An earlier filter that discards silently undoes a correct fix further down — this happened twice.
- **Nothing bounds the families within a branch, and nothing may** — `plugin/crew/hooks/scripts/crew_state.py:1221`. `_merge_history` dedups on family and caps *branches* only; `plugin/crew/hooks/scripts/crew_state.py:1617` (`_prune_dispatch_dir`) protects what the reader would keep plus every unreadable file. A prune that counts files and ignores that protection deletes the only evidence, and the next read answers `dispatch` with confidence.
- `.work/dispatch.d/` is append-only on purpose: it replaced a shared `dispatch.json` because read-modify-write is not portably race-safe. Any rewrite of a shared file loses the middle writer — and if that was the family that wrote the diff, the guard clears it to review its own work.
- Content change under `plugin/crew/` → bump `.claude-plugin/marketplace.json` **and** `plugin/crew/.claude-plugin/plugin.json` to the same value, in the **last** commit. `scripts/check-marketplace.py:151` fails on disagreement; `scripts/check-marketplace.py:298` fails when the files changed after the version was last set in git history.
- Anything that can block needs a mutation in `plugin/crew/tests/sabotage.py` that goes RED. Anchors are literal source strings (`plugin/crew/tests/sabotage.py:35`), so reformatting `crew_state.py` breaks the suite, and a mutation whose anchor no longer matches is a hard failure, not a skip (`plugin/crew/tests/sabotage.py:12`). Two ways it stops testing quietly: re-anchoring a retired mutation onto the nearest line instead of deleting it, and a mutation that stays green because it reroutes into a *different* reporting path rather than because the guard is sound.

## Unverified
- `plugin/crew/hooks/scripts/_common.sh:5` says "Every hook is registered once, as bash", but `hooks.json` registers both flavours for all 20 entries — the comment describes an architecture that changed. Whether `crew_tool_dispatch` is still reachable (`guard.sh` runs only under the `Bash` matcher, so it should never see a PowerShell `tool_name`) is open. Queued as TODO #8, not fixed here.
- The `.ps1` twins (`guard.ps1`, `promote-gate.ps1`, `verify-gate.ps1`) were not opened; that they mirror the `.sh` fail-closed semantics is assumed, as is whether the PowerShell twin of `crew_incident_active` (`plugin/crew/hooks/scripts/_common.sh:69`) rejects the same malformed-JSON cases.
- Judgment sections come from two sources: direct work on this subsystem during the 0.16.7 branch, and a `crew:explorer` pass whose every anchor was re-opened and confirmed before being folded in. Every `path:line` here resolves in range at `875c9c6f`; the *claims* rest on that work, not on the anchors being right.
- The graph's community partition is per-file here — 278 of 546 communities touch `plugin/crew` — so it gives no decomposition *within* the plugin. The grouping above is by role, not derived.
- Cross-boundary links are almost entirely pytest pseudo-nodes, so the AST graph cannot say whether crew is as self-contained at runtime as it looks. The hooks shell out to `git`, `graphify` and both shells; none of that is in the graph.
