# obsidian-vault

anchor: useful-claude-add-ons@875c9c6f
verified: 2026-09-05

## Does

Bridges Claude Code to Obsidian's Local REST API across one or more vaults:
registers an MCP server per vault, diagnoses and repairs port collisions,
enables the REST plugin, reloads a running vault, and detects what a vault is
for. Shipped as 0.3.0 in PR #64 after nine hostile review rounds.

**The rule the whole design rests on** (`plugin/obsidian-vault/hooks/scripts/
vault_ops.py:373`, `select()`'s docstring): discovery may see every vault on
disk, because a collision caused by an unconfigured vault is otherwise
unexplainable — but `--all` means every *configured* vault, never every vault
found. Naming a vault is consent; being on the same disk is not.

## Entry points

- `hooks/scripts/vault_ops.py` — the CLI. Subcommands: `scan`, `diagnose`,
  `fix-ports`, `reload`, `register`, `enable-plugin` (alias `install-plugin`),
  `add-vault`, `graph-health`, `profile`.
- `plugin/obsidian-vault/hooks/scripts/vault_ops.py:373` — `select()`, the consent gate every acting
  subcommand routes through.
- `plugin/obsidian-vault/hooks/scripts/vault_ops.py:239` — `parse_mcp_get_key()`, split out so the
  `claude mcp get` parser is testable against captured output.
- `hooks/scripts/vault_ops.py` — `run_command()`, the single execution boundary
  so a test can replace it and assert nothing ran.
- `hooks/scripts/bridge_status.py` — the `SessionStart` bridge report.
- `hooks/scripts/vault_guard.py` — `PostToolUse` contract guard; the frontmatter
  and ASCII rules default off, the canvas shape check defaults on.
- `hooks/scripts/vault_capture.py` — `SessionEnd` / `PreCompact` capture into
  the vault's `inbox/`.

## Owns data

- Each vault's `.obsidian/plugins/obsidian-local-rest-api/data.json` — ports
  written by `fix-ports`. The `apiKey` and `enableInsecureServer` are read,
  never written.
- `~/.claude/obsidian/config.json` — the plugin's own vault registry.
- The user's MCP registration, via `claude mcp add` / `remove`.

## Calls out to

- The `claude` CLI — `mcp list`, `mcp get`, `mcp add`, `mcp remove`.
- Obsidian's Local REST API over HTTP/HTTPS on localhost.
- Obsidian's own vault registry, `~/AppData/Roaming/obsidian/obsidian.json`.

## Landmines

- **The consent boundary is the thing to not break** (`plugin/obsidian-vault/hooks/scripts/vault_ops.py:373`, and
  again at `:753` for `fix-ports`, which edits a vault's own `data.json` — a
  heavier write than the MCP config). Scoping to X must never let a command
  touch X's neighbour's file.
- **The running plugin reads `data.json` only at load, and writes its own
  in-memory state back over it.** An external edit is invisible until
  `app:reload`, and can be silently clobbered before then. Observed live this
  session: `enableInsecureServer` was set to `true`, reverted by Obsidian, and
  only stuck on a write-then-reload.
- **`enableInsecureServer` is diagnosed, never written** (`plugin/obsidian-vault/hooks/scripts/vault_ops.py:564`).
  `plugin/obsidian-vault/hooks/scripts/bridge_status.py:42` records an incident where it was wrongly blamed for a
  port collision.
- **A collision is not a partial failure.** Two vaults declaring the same HTTPS
  port means the loser binds neither protocol, so the HTTP port you configured
  also goes silent. It looks like an auth or TLS problem and is not.
- **`claude mcp list` prints only name and URL.** URL equality is not evidence
  the stored key is current — `mcp get` is what reads the header back.

## Unverified

- Whether `plugin/obsidian-vault/hooks/hooks.json` registers each hook once per
  shell flavour per the marketplace-wide rule. The rule is in `CLAUDE.md`; the
  file was not opened by the explorer. (Read separately this session and it
  does appear to — but that is not a codemap-grade verification.)
- Exact line for the "reads data.json but touches no socket" purity claim in
  `obsidian_common.py`; seen in grep context around `:533`, function boundaries
  not confirmed.
- `plugin/obsidian-vault/hooks/scripts/vault_guard.py:35` exempts `CLAUDE.md` from the ASCII check but **not** from
  the frontmatter check, so every edit to a vault's own instructions file
  blocks on a rule that file can never satisfy. Observed twice this session.
  Believed a real defect; not yet filed.
