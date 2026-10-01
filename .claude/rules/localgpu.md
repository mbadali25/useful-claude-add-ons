---
paths:
  - "plugin/crew/**"
  - "plugin/localgpu/**"
---
<!-- crew:generated source=.crew/codemap/localgpu.md sha256=1b39deeb4ee19956 -- do not hand-edit; regenerate with crew_instructions.py rules -->
# localgpu
Code map anchor `71038cb9`; if it is behind HEAD, re-check with `git diff --name-only 71038cb9..HEAD -- <cited paths>`.
Covers: The localgpu plugin: its two independent process trees, the shared-Ollama constraint that drives OLLAMA_MAX_LOADED_MODELS=1, the embed-model mismatch guard, .mcp.json provisioning, and the bootstrap.sh/bootstrap.ps1 parity verdict. Records that plugin/localgpu/commands/crew.md's role table names eleven crew roles that crew 1.0 deleted.; re-anchored to c4e2eb98 (L-0520 PR 1, the merge train CLI, after merging main 42d5ef58 (T-0094)); re-anchored to 0be97503 (L-0520 PR 1 merges main 42af3fb7 (L-0531)); re-anchored to 14bb59ef (L-0520 PR 1 merges main 6a8c60b1 (T-0099)); re-anchored to 8bf710ed (L-0520 PR 1 review round 1 fixes); re-anchored to 14b52c91 (L-0520 PR 1 merges main bd4b2f30 (T-0028 #288, crew 1.0.85, and the mailgun skill), crew 1.0.86); re-anchored to 0c3508e9 (L-0520 PR 1 merges main f7caa37d (L-0561 #289: mailgun registered as skills/mailgun 1.0.1, both install scripts, README, INSTALLATION.md), crew stays 1.0.86); re-anchored to 6e581365 (T-0505 merges main 64b04c6b: W-0116 crew 1.0.89, runner auto-start #294; crew 1.0.91); re-anchored to 9580571e (T-0505 raises promote.md's line ceiling in .budget-allowance.json, crew 1.0.91); L-0513 re-anchored fe524012 -> 4eacfacf -> 3437cbdd -> e41bc6fd -> 4a48f594 -> de32cb87 -> f23b01b4 (the gate runner scripts/gate-runner.py and its review fixes; repository tooling, no plugin version; per-step notes in this map's provenance), then merged with main 52489039 (T-0040, crew 1.0.98) and re-anchored to 71038cb9
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
