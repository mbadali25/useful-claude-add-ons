---
title: Memory: Obsidian, code maps and session injection
date: 2026-09-23
source: Claude Fable 5.1 researcher agent, vendor docs fetched 2026-09-23
status: input to the crew redesign
---

**Context7 was not available in this session** (its tools were not exposed), so everything below is sourced from vendor docs and GitHub, fetched today (2026-09-23). Verified = I fetched the page; unverified = search snippet only.

## 1. Recommendation

**Primary: "rules + one hook + basic-memory"**
- Vault stays plain Markdown on disk; **Obsidian does not need to run** for reads. Use **basic-memory** (v0.23.2, 2026-08-25, AGPL, SQLite index, no LLM key, Win/Linux, Codex plugin) as the Obsidian-compatible MCP and SessionStart briefing.
- A **custom `crew` hook** (one Python module, `.sh`/`.ps1` wrappers as this repo already does) on `SessionStart`, `UserPromptSubmit`, `PostToolUse(Read|Edit|Write)` that maps touched/mentioned files → `.crew/codemap/<subsystem>.md` section + `graph.json` neighbours → `hookSpecificOutput.additionalContext`. Nothing published does this exact join; the closest are graphify's PreToolUse "nudge" and code-review-graph's Read/Edit hooks.
- **`.claude/rules/*.md` with `paths:`** generated from the codemap for the static "Does/Landmines" part (zero runtime).
- Same hook registered for Codex via `.codex/hooks.json` with `[features] hooks = true`.

**Fallback (no daemon, no hook code):** `.claude/rules` `paths:` files generated from codemap + Obsidian Local REST API v5's built-in `/mcp/` endpoint for pull-only vault access. Codex gets the same content via `AGENTS.md` (32 KiB cap).

## 2. Comparison

| Tool | Obsidian | Obs. running? | Win/Linux | Injection | Code-map aware | Key/DB | Maintenance | Codex |
|---|---|---|---|---|---|---|---|---|
| basic-memory | Native MD+wikilinks | No | Both native | SessionStart briefing + PreCompact (plugin) | No | None / SQLite | v0.23.2 2026-08-25, ~4k★ | Plugin, config.toml |
| mcp-obsidian (REST) | Via REST API | **Yes** | Both, Docker | Pull only | No | None | last commit 2026-08-31, 4.4k★ | Not stated |
| Local REST API v5 built-in MCP | Native | **Yes** | Both | Pull only | No | None | 2.9k★, v5.x | Any MCP client |
| Smart Connections MCP (msdanyg) | Reads `.smart-env` embeddings | No (embeddings refresh needs Obsidian) | Not stated | Pull only | No | Local transformers.js | 56★, date unverified | Not stated |
| claude-mem | No (own viewer) | n/a | Both (Node 20+, Bun) | SessionStart: last 10 summaries + 50 obs; UserPromptSubmit/PostToolUse/Stop capture | No | **Anthropic/OpenRouter/Gemini key or hosted observer**; SQLite+Chroma | v13.25.3 2026-09-21, ~94k★ | Claimed |
| mem0 (Claude Code plugin) | No | n/a | Not stated | UserPromptSubmit: ≤5 memories | No | **MEM0_API_KEY (cloud)** | 65.9k★ | Skills listed |
| Graphiti/Zep | No | n/a | Docker | Pull only (MCP) | No | **LLM key + Neo4j/FalkorDB** | 31.1k★ | No |
| Cognee plugin | No | n/a | Win PS + Linux | SessionStart/UserPromptSubmit/PostToolUse/Stop/SessionEnd | Yes, auto code-graph index | **LLM_API_KEY local mode** (README says keyless; docs disagree) | v1.6.0 2026-09-18, 30.9k★ | Not stated |
| Letta Code (MemFS) | MD+frontmatter, git; vault path support unstated | n/a | Desktop Win/Linux; CLI unverified | `system/` files every turn | No | Cloud default; local mode | 3.4k★ | No |
| Serena | `.serena/memories/*.md` | No | uv, both | Pull only (tools) | Yes, LSP symbols | None | v1.7.0 2026-08-09, 29.8k★ | Yes |
| graphify | `--obsidian-dir` export into vault | No | Both (note PowerShell `/graphify`) | PreToolUse nudge to `graphify query` | Yes (AST graph) | None for AST | v0.9.66 2026-09-22, ~120k★ | Yes |
| code-review-graph | Obsidian export | No | Yes (exe path caveats) | Read/Edit/Write hooks (events unverified) | Yes | Optional local embeddings; SQLite | date unverified | `--platform codex` |
| mnemonic | MD+YAML+git; Obsidian unstated | No | Unix tools; Win unverified | SessionStart/PreToolUse/UserPromptSubmit/PostToolUse/Stop | Partial (memory paths per file) | None | 23★ | No |
| lucasrosati Obsidian+Graphify | Native | No | macOS/Linux scripts | `/resume` manual + SessionEnd capture | Graphify | None (AST) | 992★, MIT | No |

## 3. Injection mechanism (verified)

**Claude Code**: `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse` all accept `hookSpecificOutput.additionalContext`; SessionStart context "persists across compaction"; `SessionStart` matchers `startup|resume|clear|compact|fork`; PostToolUse input carries `tool_input.file_path`; `shell: "powershell"` per hook. **Undocumented hard limit: 10,000 chars, silently replaced by a 2,000-char preview** (issue #94358, open, 2026-09-14, v2.1.270; affects SessionStart, UserPromptSubmit and raw stdout). `.claude/rules` `paths:` load "when Claude reads files matching the pattern"; auto-memory `MEMORY.md` loads first 200 lines/25 KB; CLAUDE.md target <200 lines.

**Codex**: hooks (`SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PreCompact`…) in `~/.codex/hooks.json` or `<repo>/.codex/hooks.json`, gated by `[features] hooks = true`; same `hookSpecificOutput.additionalContext` shape; **~2,500-token cap per message (`additionalContextLimit`)**, overflow spilled to disk; `commandWindows` for Windows overrides. `AGENTS.md` chain: root→cwd, once per run, `project_doc_max_bytes` 32 KiB, `AGENTS.override.md`, **no path-scoped rules**. Built-in memories: global, off by default, `~/.codex/memories/`, "generated state" not meant for hand-editing.

## 4. Reference design (Win + Linux)

One `crew_context.py`, wrappers `.sh` + `.ps1` (`shell: "powershell"`), also referenced from `.codex/hooks.json` with `commandWindows`.

| Event | Injects | Budget |
|---|---|---|
| `SessionStart` (all matchers) | branch/HEAD, codemap INDEX rows with anchor state (current/behind/unresolvable), last vault handoff note, `MEMORY.md` pointer | ≤6,000 chars |
| `UserPromptSubmit` | paths/subsystem names found in prompt → that codemap's "Does"+"Landmines" + top-5 `graph.json` neighbours by degree | ≤3,000 chars; emit nothing if no match |
| `PostToolUse` matcher `Read\|Edit\|Write` | `tool_input.file_path` → subsystem; first hit per subsystem per `session_id` (state file in scratchpad) → same slice | ≤3,000 chars |
| `.claude/rules/<subsystem>.md` `paths:` | static codemap summary, regenerated by `/crew:onboard --refresh` | <100 lines each |
| `SessionEnd`/`PreCompact` | keep one-line capture; basic-memory PreCompact writes the session note | existing |

Hard-cap every emission at 8,000 chars (under both Claude's 10k-char and Codex's 2.5k-token limits).

**Retire**: the second `vault` plugin's scan/ingest queue and its SessionEnd capture (duplicate of obsidian-vault's); obsidian-vault's `bridge-status` SessionStart hook once reads go filesystem-first (keep REST/MCP only for the gardener's writes and Omnisearch); any third-party mcp-obsidian if REST API v5's built-in MCP is adopted. Keep the gardener; point it at basic-memory's note folder or the vault directly.

## 5. Risks and costs

- **Tokens**: ~1.5k at start + ≤0.8k per matched prompt/file; 3–8k per typical session. Budgeting is mandatory because both harnesses truncate silently.
- **Privacy**: primary is fully local. claude-mem, mem0, Graphiti, Cognee send transcripts/content to an LLM or cloud.
- **Moving parts**: graph freshness (post-commit hook already rebuilds), codemap anchors drifting, two hook registrations per event (bash + PowerShell), Codex feature flag off by default.
- **Codex parity gap**: no `paths:` rules, so the PostToolUse hook is the only per-file channel there.

## Sources

**Verified (fetched)**
- https://code.claude.com/docs/en/hooks.md — decision-control table, SessionStart persistence, matchers, Windows shell
- https://code.claude.com/docs/en/memory — rules `paths:`, MEMORY.md 200 lines/25 KB, CLAUDE.md sizing, AGENTS.md handling
- https://github.com/anthropics/claude-code/issues/94358 — 10,000-char truncation (open, 2026-09-14)
- https://learn.chatgpt.com/docs/hooks — Codex hook events, `additionalContextLimit` 2,500 tokens, `commandWindows`, `[features] hooks`
- https://learn.chatgpt.com/docs/agent-configuration/agents-md — 32 KiB cap, discovery, no path rules
- https://learn.chatgpt.com/docs/customization/memories — global, off by default, generated state
- https://github.com/basicmachines-co/basic-memory (+ releases.atom, DeepWiki plugin page) — Obsidian compat, hooks, v0.23.2 2026-08-25
- https://github.com/thedotmack/claude-mem + https://docs.claude-mem.ai/hooks-architecture (+ releases.atom)
- https://docs.mem0.ai/integrations/claude-code; https://github.com/getzep/graphiti; https://github.com/topoteretes/cognee + https://docs.cognee.ai/integrations/claude-code; https://github.com/letta-ai/letta-code + https://docs.letta.com/letta-code/memfs; https://raw.githubusercontent.com/oraios/serena/main/README.md (+ releases.atom)
- https://github.com/MarkusPfundstein/mcp-obsidian (+ commits atom); https://github.com/coddingtonbear/obsidian-local-rest-api; https://github.com/msdanyg/smart-connections-mcp; https://obsidian.md/cli
- https://github.com/Graphify-Labs/graphify (+ releases.atom); https://github.com/lucasrosati/claude-code-memory-setup; https://github.com/EduardKononov/code-review-graph; https://github.com/modeled-information-format/mnemonic; https://community.obsidian.md/plugins/graph-context-for-claude-code

**Unverified (snippets only)**
- Codex memories 6-hour idle consolidation and 2026-04-16 launch (exsesx.dev, memorylake.ai)
- Local REST API "version 5" MCP claim (contextbolt.com; README confirms endpoint but not version)
- claude-mem Codex support (README tagline only)

**Could not determine**: Serena's exact memory-loading semantics (docs page 404); code-review-graph's hook event names and release date; whether Letta Code CLI runs natively on Windows; whether Cognee local mode truly needs an LLM key (README and plugin docs disagree); any Claude Code doc statement of the 10k-char limit (only the GitHub issue states it).