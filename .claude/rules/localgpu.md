---
paths:
  - "plugin/localgpu/**"
---
<!-- crew:generated source=.crew/codemap/localgpu.md sha256=c01289b8a8fce4c3 -- do not hand-edit; regenerate with crew_instructions.py rules -->
# localgpu
Code map anchor `f2bb919b`; if it is behind HEAD, re-check with `git diff --name-only f2bb919b..HEAD -- <cited paths>`.
Covers: The localgpu plugin: its two independent process trees, the shared-Ollama constraint that drives OLLAMA_MAX_LOADED_MODELS=1, the embed-model mismatch guard, .mcp.json provisioning, and the bootstrap.sh/bootstrap.ps1 parity verdict. Records that plugin/localgpu/commands/crew.md's role table names eleven crew roles that crew 1.0 deleted.
## Entry points
- `plugin/localgpu/mcp/server.py:253` — `main()`, which calls `mcp.run("stdio")` at `:254`.
- `plugin/localgpu/mcp/server.py:73` — `search_code`, MCP tool
- `plugin/localgpu/mcp/server.py:157` — `index_status`, MCP tool
- `plugin/localgpu/mcp/server.py:187` — `index_refresh`, MCP tool
- `plugin/localgpu/cli/localgpu_cli.py:568` — `main()`, the `localgpu` console script declared at `plugin/localgpu/pyproject.toml:16` (was `:247`)
- `plugin/localgpu/cli/localgpu_cli.py:112` — `cmd_shell`, starts the proxy on a background thread in THIS process and launches a child Claude Code against it (was `:100`)
- `plugin/localgpu/cli/localgpu_cli.py:158` — `cmd_proxy`, the same proxy in the foreground with no child session (was `:146`)
- `plugin/localgpu/cli/localgpu_cli.py:224` — `cmd_prompt`, one ungrounded question to `/api/generate` (new)
- `plugin/localgpu/cli/localgpu_cli.py:281` — `cmd_models`, what Ollama has pulled (new)
- `plugin/localgpu/cli/localgpu_cli.py:339` — `cmd_mcp_init`, writes `<repo>/.mcp.json` (new)
- `plugin/localgpu/cli/localgpu_cli.py:458` — `build_parser`, where every subcommand and its flags are declared
- `plugin/localgpu/bootstrap.sh` and `plugin/localgpu/bootstrap.ps1` — the install entry point, a matched pair
Full note: `.crew/codemap/localgpu.md`.
