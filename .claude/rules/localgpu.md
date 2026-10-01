---
paths:
  - "plugin/crew/**"
  - "plugin/localgpu/**"
---
<!-- crew:generated source=.crew/codemap/localgpu.md sha256=ec49084411356a11 -- do not hand-edit; regenerate with crew_instructions.py rules -->
# localgpu
Code map anchor `de32cb87`; if it is behind HEAD, re-check with `git diff --name-only de32cb87..HEAD -- <cited paths>`.
Covers: ; re-anchored to 6e581365 (T-0505 merges main 64b04c6b: W-0116 crew 1.0.89, runner auto-start #294; crew 1.0.91); re-anchored to 9580571e (T-0505 raises promote.md's line ceiling in .budget-allowance.json, crew 1.0.91)
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
