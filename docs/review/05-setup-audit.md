---
title: Machine setup audit - plugins, skills, hooks, MCP
date: 2026-09-23
source: Claude Fable 5.1 audit agent, read-only, Claude Code 2.1.280 / Codex 0.155.1 on Linux
status: input to the crew redesign and machine cleanup
---

## Setup audit — Claude Code 2.1.280 / Codex 0.155.1, Linux (root)

### 1. Verdict
1. **No hooks of your own.** `~/.claude/settings.json` has `hooks: null`; every hook you have comes from plugins (crew 20, obsidian-vault 8, superpowers 1, org-synced security-guidance). Nothing formats, lints, or guards `aws`/`az`/`terraform`/`rm -rf`.
2. **Sprawl with near-zero use.** 63 marketplace plugins enabled + ~20 org-synced claude.ai plugins. In 60 days (308 transcripts, 3 projects) the Skill tool fired 22 times across 19 skills — all crew, obsidian-vault, github, doc-builder. Roughly 45 enabled plugins were never invoked.
3. **Global CLAUDE.md is owned by a disabled plugin** (`<!-- DotnetPilot v2.5.3 -->` wrapper), contradicts itself on `var`, cites a hook (`dnp-git-autoapprove`) and MCP (`mcp__roslyn__*`) that no longer exist, and says nothing about Python, Terraform, PowerShell, Angular, SQL or Bash.
4. **MCP noise:** 19 connected servers exposing ~407 tools (deferred, names only); 25 more org-synced servers fail auth every startup; `github@official` and `serena` never connect (no token / not started).
5. **Codex is bare:** no global `AGENTS.md`, no user skills, no profiles, one malformed hook pointing at a missing `~/.thumbgate/runtime`.

### 2. Keep / remove / add

**Plugins (marketplace)**

| Action | Plugin | Reason / evidence |
|---|---|---|
| Keep | crew | 300+ subagent dispatches; all 19 used skills are here or below. Its 54 agents cost ~13k tokens/session — for the redesign, not this cleanup |
| Keep | obsidian-vault, doc-builder, github@useful-claude-add-ons, notify, microsoft-docs, context7, playwright | used, or cheap and on-stack |
| Keep | claude-code-tuneup, claude-code-defaults | on-topic for this task; `disable-model-invocation` style keeps them cheap |
| Remove (dup) | github@claude-plugins-official | never connects (needs `GITHUB_PERSONAL_ACCESS_TOKEN`); duplicates `github@useful-claude-add-ons` and `gh` |
| Remove | serena | not in `claude mcp list` at all; overlaps LSP plugins |
| Remove | php-lsp, excalidraw-generator, eli5, colosseum, codex-hud (11 commands), codex-bridge, codex-dispatch, codex-review, obsidian@obsidian-skills, obsidian-canvas, claude-memories-canvas/-vault, obsidian-vault-server, vault | 0 invocations; obsidian stack has four overlapping plugins doing memory |
| Remove | superpowers | 0 skill invocations, but injects 65 lines every SessionStart and its `using-superpowers` skill demands invocation "before ANY response" — competes with crew's PM for the same job |
| Remove | feature-dev, frontend-design, claude-code-setup, claude-md-management, skill-creator, code-simplifier, commit-commands | 0 uses; `/code-review`, `/simplify`, `/init`, `/security-review` are built in (skill list, verified locally) |
| Disable per-project | vendor skills: aws-opensearch, checkpoint-email, cisco-meraki, cloudflare, drata, exchange-*, intune-graph, knowbe4, power-automate, shipstation, sophos, wazuh, gizmoduck, jira-manager, infra-work-ticketing, work-log-reporter, terraform-docs-readme, visio-diagrams, report-builder, solomon-* | 0 uses in 60 d; each description is 400–1,500 chars loaded every session. Enable at project scope in the repos that need them |
| Turn off synced | small-business (44 skills, 35 MCP), sales (36/23), unity (31), marketing, product-management, finance, legal, HR, design, engineering, activecampaign, qodo, postiz | org-pushed "knowledge-work-plugins"; 25 servers report `Needs authentication`/failed at every start. Disable in `/plugin` Installed tab (docs: synced plugins can be disabled unless "required") |
| Add | csharp-lsp, pyright-lsp, typescript-lsp | official LSP plugins (marketplace.json verified locally); give diagnostics after every edit. Binaries needed: `csharp-ls`, `pyright-langserver`, `typescript-language-server` — none installed here |
| Add | terraform (HashiCorp MCP, official marketplace) | runs `docker run hashicorp/terraform-mcp-server:0.4.0`; **docker missing on this box** |
| Add | aws-core, aws-agents-for-devsecops, databases-on-aws (AWS-authored, official marketplace) | replace the deprecated `awslabs aws-api-mcp-server` your Windows box runs (its log says "entering end of development… migrate to the AWS MCP Server") |
| Add | azure (microsoft/azure-skills, bundles Azure MCP) | `az` CLI missing here; install first |
| Add | security-guidance (official; it's already reaching you via org sync) or hookify | pattern warnings on edit + LLM diff review on Stop; hookify generates custom PreToolUse guards |
| Add | session-report | measures per-session token/skill cost — the evidence this audit had to estimate |

**Skills hygiene:** docs state descriptions always load, body loads on invoke, and `description + when_to_use` truncates at 1,536 chars; no hard max on skills, but `/skill-doctor` and the `/plugin` Stats tab flag never-invoked ones (verified). Codex caps the skills list at ~2% of context and silently shortens descriptions when crowded (verified).

**MCP servers**

| Action | Server | Evidence |
|---|---|---|
| Keep | Atlassian (208 calls), Solomon Intune/Cloudflare/OpenSearch/Drata/SDP/M365, Microsoft Learn, context7, playwright, obsidian-claude-memories | on-stack or used |
| Remove | Gmail (30 tools), Google Calendar (9), AccuWeather (9), AWS Marketplace (6), duplicate `claude.ai Atlassian Rovo`, Google Drive/M365 stubs | 0 calls; pure tool-list cost |
| Add | Terraform MCP, AWS MCP Server (`aws-core`), Azure MCP (`azure`) | see plugins |
| Undetermined | thumbgate (47 tools, connected) | not in `settings.json`, `installed_plugins.json` or the synced manifest; source not found |

### 3. Missing hooks (put in `~/.claude/settings.json`; matcher = tool name)

| Purpose | Event | Blocks | Command (Linux) | Windows note |
|---|---|---|---|---|
| Format/lint on edit | `PostToolUse` `Edit\|Write` | no | dispatch on extension: `terraform fmt`; `dotnet format --include`; `prettier --write` + `eslint --fix` (Angular); `ruff format && ruff check --fix`; `sqlfluff fix`; `pwsh -c Invoke-ScriptAnalyzer -Fix`; `shellcheck` | use exec form with `args` and `node`/`pwsh` executables — `.cmd` shims fail in exec form (docs, verified). Register a `shell: "powershell"` twin, as crew does |
| Destructive-command guard | `PreToolUse` `Bash` | **yes** (exit 2 / `permissionDecision: deny`) | deny `terraform destroy\|apply -auto-approve`, `aws … delete-\|terminate-\|rm --recursive`, `az … delete`, `rm -rf /`, `git push --force`, `DROP TABLE`. Fires even in `bypassPermissions` (docs, verified) | second hook with `matcher: PowerShell`, `shell: powershell` |
| Protect secrets | `PreToolUse` `Edit\|Write\|Read` | yes | block `.env`, `*.tfvars`, `~/.aws/credentials`, `appsettings.*.json` with secrets | same |
| Validate IaC | `PostToolUse` `Edit\|Write` on `*.tf` | no (advisory) | `terraform validate && tflint` — tflint missing here | — |
| Test gate | `Stop` | yes | `prompt`-type hook: "verify tests pass" (docs example, verified); crew's `verify-gate` already does this in crew repos | — |
| Context re-injection | `SessionStart` `compact\|resume` | no | short `echo` of stack rules; keep under 20 lines | — |
| Notification | `Notification` | no | crew's `notify.sh` already covers this; don't duplicate | — |

Tools to install first (missing here): `tflint`, `terraform-ls`, `dotnet` SDK (so `dotnet format` and `csharp-ls` work), `prettier`, a current `eslint` (v6.4.0 is Debian's 2019 build), `ruff`, `pyright`, `sqlfluff`, `shellcheck`, PSScriptAnalyzer, `docker`, `az`. Present: `terraform`, `pwsh 7.6`, `aws` CLI, `node 22`, `uv`.

**How crew fits:** crew already owns SessionStart (handoff, PM brief, platform-sync), PreToolUse (promote-gate, role-write-guard), PreCompact, Notification, Stop (verify-gate, context-watch, pm-pulse), each as a bash+PowerShell pair. Your global hooks should cover only what crew doesn't: formatters, destructive-command and secret guards, and LSP. Don't add a second Stop gate or notifier.

### 4. Global CLAUDE.md
Problems: (a) whole file sits inside DotnetPilot markers — a hook from a plugin now **disabled** will rewrite it if re-enabled; (b) `var` rule contradicts itself (line 8 vs 14 and 58); (c) duplicates: file-scoped namespaces, records, `.Result`, `CancellationToken` each stated twice; (d) references dead `dnp-git-autoapprove` hook and `mcp__roslyn__*`; (e) Jira `[BE]/[FE]` and NuGet rules are project policy, not global; (f) nothing for 6 of your 8 languages.

Proposed ~40 lines:
```
## Working style      (5 lines: direct, confirm non-trivial approach, one clarifying question, flag breaking changes)
## Verification       (state ref+layer with every number; quote failures verbatim; say what wasn't run)
## Git                (no Co-Authored-By; CODEOWNERS reviewers; one-batch commit context)
## Languages          (1–3 lines each: C# = var, file-scoped ns, CancellationToken, Result<T>;
                       Python = ruff, type hints; PowerShell = 5.1 vs 7 named explicitly, PSScriptAnalyzer;
                       Terraform = fmt/validate, never apply; SQL = parameterised only; Angular = eslint/prettier; Bash = shellcheck, set -euo pipefail)
## Per-project        ("Project CLAUDE.md overrides")
```
Move the .NET testing/NuGet/error-handling blocks to `.claude/rules/dotnet.md` in the .NET repos, or a `paths:`-scoped skill.

### 5. Codex setup
- Docs moved: `developers.openai.com/codex/*` 308-redirects to `learn.chatgpt.com` (verified).
- Add `~/.codex/AGENTS.md` mirroring the short CLAUDE.md; set `project_doc_fallback_filenames = ["CLAUDE.md"]` so repos without AGENTS.md still get instructions (default fallback list is empty; `project_doc_max_bytes` default 32 KiB — verified).
- Skills: Codex scans `$CWD/.agents/skills`, `$REPO_ROOT/.agents/skills`, `~/.agents/skills` — SKILL.md is the same agentskills.io format (verified). You have only the 6 `.system` skills. Symlink your kept marketplace skills into `~/.agents/skills`.
- Hooks: documented syntax is `hooks.json` at `~/.codex/hooks.json` or `.codex/hooks.json`, events `SessionStart, PreToolUse, PostToolUse, UserPromptSubmit, Stop…`, exit 2 blocks, enabled by default (verified). Your `[hooks.user_prompt_submit]` table uses an undocumented lowercase form and `exec npm exec --yes thumbgate@latest` against a missing runtime — remove it. `~/.codex/config.json` holds Claude-format hooks Codex never reads — dead file.
- Profiles: `$CODEX_HOME/<name>.config.toml` + `--profile` (verified); make `review` (read-only sandbox) and `work` (workspace-write) profiles. `model = "gpt-6-astra"` is not named in the config reference (unverified whether valid).

### 6. Estimated context saved per session
Measured description sizes: enabled skills/commands 164 → ~14.6k tokens; agents 61 → ~13.4k (crew 12.9k). Pruning to crew + ~10 skills saves **~10k tokens**; CLAUDE.md 112→40 lines saves ~1k; removing superpowers' SessionStart injection ~1.2k; dropping ~25 unused/failed MCP servers saves ~100 deferred tool names (~1–2k). **Total ≈ 13–15k tokens (≈7% of 200k) before crew's own agent-roster cost**, which the crew redesign owns. Confirm with `session-report` or `/context`.

### 7. Sources and gaps
Verified (fetched): code.claude.com/docs/en/hooks; /hooks-guide; /skills; /plugins; /discover-plugins; learn.chatgpt.com/codex/hooks, /codex/build-skills, /codex/agent-configuration/agents-md, /codex/config-file/config-reference. Local files verified: `~/.claude/settings.json`, `installed_plugins.json`, marketplace caches, hook manifests, 308 transcripts, `~/.codex/config.toml`, `~/.aws/aws-api-mcp/*.log`.
Unverified: karanb192/claude-code-hooks and disler/claude-code-hooks-mastery (search results only); the AWS MCP migration guide URL (quoted from the log); `gpt-6-astra` validity.
Not determined: where thumbgate is enabled; whether the two research subagents ever ran (no result returned); PSScriptAnalyzer presence (pwsh query returned nothing); the Windows machine's state; exact per-session token cost (estimated from character counts at 4 chars/token, not measured).