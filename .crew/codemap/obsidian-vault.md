# obsidian-vault
anchor: useful-claude-add-ons@a02331ee
verified: 2026-09-06

## Does
Turns one or more Obsidian vaults into Claude Code's durable memory: a PostToolUse guard that
holds notes to a contract, gardener and reflector agents that distil sessions into notes, and
per-vault MCP registration against Obsidian's Local REST API bridge. It is the only plugin here
whose hooks can block a write, so its regression suite is load-bearing rather than decorative.

## Entry points
- `plugin/obsidian-vault/hooks/hooks.json:1` - registers SessionStart, PostToolUse, SessionEnd
  and PreCompact, each as a bash + PowerShell pair. Verified as a pair on all four; this is the
  defect that shipped once in `crew`, where a bare command went to Git Bash on Windows and the
  guard stood down.
- `plugin/obsidian-vault/hooks/scripts/vault_guard.py:229` - `main()`, the PostToolUse guard,
  fired on Edit/Write/MultiEdit. Reads its config toggles at `:240-246`.
- `plugin/obsidian-vault/hooks/scripts/vault_guard.py:156` - `check_note`, the frontmatter/title/
  date contract, scoped by `notesPrefix`.
- `plugin/obsidian-vault/hooks/scripts/vault_ops.py:1059` - `register_commands`, builds the
  `claude mcp add` invocation per vault. Driven by `/obsidian-vault:install` and `:init`.
- `plugin/obsidian-vault/hooks/scripts/obsidian_common.py:286` - `resolve_vault_path`, the single
  reader of `~/.claude/obsidian/config.json`.

## Owns data
- The vault contents themselves, written by the gardener - outside this repo, at the path
  `obsidian_common.resolve_vault_path` returns (`plugin/obsidian-vault/hooks/scripts/obsidian_common.py:286`).
- Machine-global vault registry `~/.claude/obsidian/config.json`, including each vault's HTTP
  port; shape documented at `plugin/obsidian-vault/README.md:39`.

## Calls out to
- Obsidian's Local REST API plugin, one MCP server per vault on its own port, registered via
  `claude mcp add` at `plugin/obsidian-vault/hooks/scripts/vault_ops.py:1059`.

## Landmines
- **The three guard checks do not ship the same way.** `asciiOnly` and `requireFrontmatter`
  default OFF; `checkCanvas` defaults ON, via an `is not False` test at
  `plugin/obsidian-vault/hooks/scripts/vault_guard.py:243`. Assuming all three share a default is
  the easy mistake, and it inverts which rules a fresh install enforces.
- **Two differently-sized exemption sets, 20 lines apart.** `CLAUDE.md`, `README.md`, `AGENTS.md`
  and `GEMINI.md` are exempt from *requiring frontmatter*
  (`plugin/obsidian-vault/hooks/scripts/vault_guard.py:59`); only `CLAUDE.md` is also ASCII-exempt
  (`:39`). Widening one while reading the other is how an exemption silently grows.
- **`notesPrefix` scopes the note contract only** - not the ASCII check and not the canvas check.
- The guard reads file content from disk rather than from the hook payload, and scans only newly
  introduced text for ASCII violations (`written_text`,
  `plugin/obsidian-vault/hooks/scripts/vault_guard.py:93`).
- The regression suite is `plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh`, sabotage-tested
  per its own header. A change to any rule above needs a must-block and a must-allow case here
  before it ships - this repo's rule for a hook that can block.

## Unverified
- `plugin/obsidian-vault/agents/gardener.md`, `plugin/obsidian-vault/agents/reflector.md` and the eleven command markdown files were not
  opened; their existence and purpose come from the README command table, not from reading them.
- `plugin/obsidian-vault/hooks/scripts/vault_profiles.py` and
  `plugin/obsidian-vault/hooks/scripts/bridge_status.py` internals were inferred from their test files rather
  than read directly.
- The test suite was not executed in this pass, so "sabotage-tested" rests on the header comment
  and the committed cases, not on a red run observed here.
