---
title: crew redesign - Fable design (final, addenda 1-5 and setup audit)
date: 2026-09-23
source: Claude Fable 5.1 designer, read-only, from .work/redesign-brief.md
status: draft - cross-review pending
---

# Crew redesign — Claude Fable 5.1 design

**Summary (5 lines)**
1. **Rebuild, not reshape**: crew 1.0 is a new, smaller plugin (same name, new layout) that keeps only the tested machinery — verify gate, scope base/report, codemap + graphify + freshness, platform detection, handoff, notify, sabotage harness — and drops the PM, the pulse, the journal and 50 of 54 agents.
2. The interactive session owns a ticket through **brainstorm → spec → plan → implement → tests → docs → review**; approval and scope are enforced by two new PreToolUse hooks, not prose.
3. Review gets a fixed adapter (working tree + untracked, spec in the prompt, two-round budget persisted per ticket), and moves to the end of the ticket.
4. Memory is plain Markdown: `AGENTS.md` (≤80 lines) + generated `.claude/rules/` + auto memory + codemap, injected by one budgeted hook module shared with Codex; Obsidian is consolidated onto `obsidian-vault` with one capture owner and a scheduled gardener; Serena is dropped in favour of the official LSP plugins.
5. Twelve ordered tickets; the first (review adapter fix, 0.20.16) ships this week; every feature ticket includes its guide section.

## 0. Rebuild vs reshape

**DERIVED** — the size that has to go: 27,194 Markdown lines, `agents/pm.md` 991 lines (`docs/review/README.md`), 54 agent descriptions ≈13k tokens per session (`docs/review/05-setup-audit.md` §2), 20 hook registrations (`plugin/crew/hooks/hooks.json:3-36`), 36 of 53 roles never dispatched in 60 days. **DERIVED** — what already works and is tested: `verify-gate.sh` (1,652 lines, fingerprint, lock, pricing, env pinning at `verify-gate.sh:1466`), `scope_base.py`/`scope_report.py`, `crew_freshness.py`, `crew_platform.py`, 60 test files under `plugin/crew/tests/` plus `tests/sabotage.py`. **DERIVED** — a guard that exists only in config: `GUARD_NAMES = ("terraformApply", "forcePush", "adminMerge", "mergeGate")` and `PROD_GUARD_NAMES` (`crew_guards.py:104,125`) with an `_classify_aws` (`:881`), but no `.sh`/`.ps1` wrapper imports `crew_guards` (grep over `hooks/scripts/`), `hooks.json` PreToolUse Bash runs only `promote-gate.sh` (`hooks.json:12-13`), and `README.md:618` credits a `guard.sh` that does not exist. **JUDGEMENT**: reshaping means editing a 991-line PM and 4,020 lines of commands around a model they were written against; rebuilding keeps the ~9k lines of Python/bash that carry the tests and rewrites the ~20k lines of prose from a one-session model. Rebuild. Keep the name `crew` (every install URL, `enabledPlugins` key and guide already says it; renaming buys nothing and costs the full registration chain in `CLAUDE.md`).

## 1. Target architecture

- One interactive session owns an ordinary ticket. Subagents are used only where the README's own rule holds (`plugin/crew/README.md:48-54`): isolation or restricted tools.
- **PM → `/crew:status`**, a read-only command (≤60 lines) rendering the same state `pm_brief.render` renders today, on demand. `pm.md`, `crew-pm/SKILL.md`, `pm_journal.py`, `pm_pulse.py`, `/crew:pm`, `/crew:roster`, `/crew:scale` are deleted; role on/off moves to `crew.json`.
- **Stop-hook pulse: removed.** It is a blocking hook (exit 2, `pm_pulse.py:395`) whose purpose was re-engaging a PM that no longer exists. Stop keeps `verify-gate` and `context-watch` only.
- **SessionStart brief: ≤12 lines / 1,500 chars** (today's cap is 40 lines, `pm_brief.py:594`): branch, open ticket + phase, handoff pointer, codemap freshness (one line), gate state. Emitted via `additionalContext` so it survives compaction.

## 2. Ticket contract

`.work/tickets/<KEY>/spec.md` (files mode; tracker modes cache the same file at `.work/cache/<KEY>/spec.md`):

```
# T-0042 <title>          status: spec|planned|implementing|review|done   risk: low|med|high
## Intent        2-3 sentences
## Exclusions    what this ticket must NOT do
## Evidence      path:line facts the spec rests on (from explorer/codemap)
## Unknowns      each with how it will be resolved, or "accepted"
## Touch         globs (feeds the scope guard)
## Acceptance    - [ ] observable checks; the verify.json rule(s) and the new test by name
```

`plan.md` (steps, each with files, test, risk; frontmatter `approved: <sha-of-plan-body>` written only by `/crew:plan --approve`), `review.json` (rounds, manifests), `metrics.json`. Commands that require a spec: `/crew:plan`, `/crew:implement`, `/crew:review`. Scope enforcement: **`scope-guard`** (PreToolUse `Edit|Write|MultiEdit`, bash + PowerShell) reads `Touch` via the existing `declared_paths` parser (`scope_report.py:41`) and refuses writes outside it plus the carve-outs `work.md` step 4b already names (`TODO.md`, `.crew/`, `.work/`). It also refuses any write while `plan.md` lacks a matching `approved:` — that is how "the owner approves before any edit" becomes a mechanism. Modes `off|report|block`; ships `off` (CLAUDE.md hook rule), `/crew:init` asks to set `block`.

## 3. Review

**DERIVED**: `review.md:311` builds `git diff "$BASE"...HEAD`; re-measured at `8b8a4028` today: 0 bytes, while `git diff HEAD` is 107,107 bytes with 7 untracked files. `review.md:457` caps re-runs in prose only. `work.md:186-197` reviews at step 9, before coverage (10) and docs (12).

Design: `crew_review.py` adapter (one module, both shells):
1. Patch = `git diff <scope-base>` (tracked, committed and uncommitted) + `git diff --no-index /dev/null <f>` for each untracked non-ignored file; manifest (files, bytes, sha256) written to `review.json` so "what was reviewed" is a record, not a claim.
2. Prompt = today's byte-identical hostile-QA prompt + the spec's Intent/Exclusions/Acceptance + intersecting codemap landmines.
3. Provider order unchanged (Codex → Copilot → `qa-reviewer`), author-family strike unchanged (`crew_state.author_families`). Codex runs `codex exec --sandbox read-only -C <root> --skip-git-repo-check` (flags confirmed by `codex exec --help`, 0.155.1).
4. **Budget**: `review.json.rounds` ≤ 2. A third invocation exits with "budget spent — `/crew:plan --replan`", and the Stop gate refuses `done` while `rounds > 2 && !replanned`. Findings recorded per round as confirmed / rejected / duplicate.
5. Order: implement → tests → docs → review; `/crew:implement` refuses to call review while `Acceptance` has unchecked test/doc items.

## 4. Roster

Rule applied: a role stays only if it buys isolation, restricted tools, or independent eyes (`README.md:48-54`), and the usage table.

| Keep (4) | Why |
|---|---|
| `explorer` | read-only, no Bash (`agents/explorer.md` frontmatter); isolates search noise; 24 uses |
| `reviewer` (today's `qa-reviewer`) | fallback independent eyes, own context, Opus; 56 uses |
| `security` | read-only + Bash for scanners; 2 uses but gate-triggered |
| `researcher` | web tools isolated from the working context; 10 uses |

| Delete → replacement |
|---|
| `pm` (16) → `/crew:status`; `planner` (6) → `/crew:brainstorm`; `developer` (154), `backend-developer`, `node-developer`… → the session itself; Codex/Copilot as implementer via `codex exec` profile `work`, not an agent |
| `scribe` (62), `docs-writer` (52) → `/crew:docs` + `crew-docs` skill (both exist) |
| `analyst` (44) → `explorer` with a "verdict" output mode; `smoke-author` → `crew-verification` skill; `browser-tester` (10) → `stack-angular` skill + playwright plugin |
| Stack specialists with real content → **skills** (loaded on demand, ~100-char descriptions): `dba.md` (299 lines) + `sql-pro` → `stack-sql` (SQL Server/MySQL/PostgreSQL); `dotnet-core-expert` + `dotnet-framework-4.8-expert` → `stack-dotnet`; `angular-architect` → `stack-angular` (incl. AngularJS); `python-pro` → `stack-python`; `powershell-5.1-expert` + `powershell-7-expert` + `powershell-security-hardening` → `stack-powershell`; `terraform-engineer` + `infrastructure-architect` → `stack-terraform` (merges `crew-terraform`); new `stack-bash` |
| Delete outright (0–4 uses, off-stack): php-pro, rust, react, graphql, microservices, fintech, payment, network, platform, legacy-modernizer, git-workflow-manager, compliance-auditor, penetration-tester, ad-security-reviewer, exchange-online, sharepoint, power-automate, windows-infra-admin, multi-agent-coordinator, workflow-orchestrator, api-designer, architect-reviewer, code-reviewer, database-administrator, design-bridge, ai-writing-auditor, qa-researcher, skill-author (built-in skill-creator), kimi-consult (already a review rung) |

Proof: agent-description cost falls from ~13k to ~1k tokens per session (measure with `/context`).

## 5. Instruction surface

| File | Target | Note |
|---|---|---|
| `AGENTS.md` (repo) | ≤80 lines | routing + hard rules; read natively by Claude Code and Codex. `CLAUDE.md` becomes `@AGENTS.md` plus ≤10 Claude-only lines (today 319 lines) |
| `.claude/rules/<subsystem>.md` | ≤60 lines each, `paths:` scoped | generated by `/crew:onboard` from codemap "Does"+"Landmines"; the Landmines/Lessons prose in `CLAUDE.md` moves here and into the codemap |
| `/crew:status` | ≤60 lines | pm.md successor |
| Command files | ≤120 lines each (today up to 496) | procedure only; rationale moves to the codemap |
| Machine `~/.claude/CLAUDE.md` | ≤40 lines | per the setup audit; not crew's |

Contradictions are caught mechanically: `scripts/check-marketplace.py::check_instructions` (a) fails when the same backticked command appears with different arguments across `AGENTS.md`, rules, and commands unless the line carries `<!-- deliberate -->`; (b) fails when a command file exceeds its line budget; (c) `/crew:docs` runs a Codex `exec` read-only "find contradictory instructions" pass over `AGENTS.md` + rules and reports, not edits.

## 6. Memory and injection

One module `crew_context.py`, wrappers `.sh` + `.ps1`, also referenced by `.codex/hooks.json` with `commandWindows`.

| Event | Injects | Budget |
|---|---|---|
| SessionStart (all matchers) | the brief (§1) | ≤1,500 chars |
| UserPromptSubmit | codemap Does+Landmines for paths/subsystems named in the prompt, top-5 graph neighbours by degree | ≤2,500 chars; nothing on no match |
| PostToolUse `Read\|Edit\|Write` | same slice, first hit per subsystem per session (marker in `.crew/.ctx-<session>`) | ≤2,000 chars |
| PreCompact | handoff write (existing) | — |

Hard cap 8,000 chars per emission (Claude truncates at 10k, Codex ~2.5k tokens — `02-memory-and-injection.md` §3); Codex gets a 2,000-char variant. Static layer: generated rules files (zero runtime). Auto memory on. Subagent `memory:` **not used** — it grants Write/Edit to read-only roles (`03-codex-review.md`). **basic-memory: no.** DERIVED: vault MCP tools were called 5 times in 305 sessions, basic-memory 0 times in 310 transcripts; the codemap is 6,997 lines and the graph 13,306 nodes / 23,598 links, both grep-able. JUDGEMENT: a SQLite daemon on two OSes for retrieval nobody performs is cost without a demonstrated failure; revisit when a recorded ticket shows a recall miss that `rg` over the vault could not answer.

## 7. Obsidian setup and consolidation

`/obsidian-vault:init` already detects the OS, installs (`winget install Obsidian.Obsidian`, Flatpak, AppImage — `commands/init.md:39-41`, `obsidian-setup/SKILL.md:67-75`), scans/adopts vaults, dry-runs via `vault_ops.py`; `install-prerequisites.sh:2891` already detects an installed Obsidian on Linux. So crew does not get a second installer: `/crew:init` phase "memory" invokes `/obsidian-vault:init` via Skill. Extend `obsidian-vault` (bump) with: `.deb`/`dpkg -s obsidian` detection; **one capture owner** = `vault-capture` (SessionEnd/PreCompact), with `doctor` failing when a second capture hook is registered; **gardener scheduling** as an opt-in step that installs the cron/systemd-timer/Task-Scheduler entry from the `obsidian-scheduling` skill (today "neither is scheduled by this plugin", `README.md:148-152`), and drains the 95 queued sessions on first run; optional basic-memory offered last, default no. Every step idempotent, dry-run then yes.

Marketplace: `obsidian-vault` stays and absorbs; `obsidian-canvas` and `obsidian-vault-server` stay (generic, distinct); `claude-memories-vault` and `claude-memories-canvas` retire from the marketplace into `/repos/claude-memories/.claude/skills/` (they describe one vault, `SKILL.md:3-6`); root `vault-automation/` and `claude-obsidian-setup/` are deleted (already "superseded", `obsidian-vault/README.md:190-200`); the disabled `obsidian-vault-for-claude-code` and the `vault` plugin are not reinstalled.

## 8. Serena: skip

DERIVED: enabled (`~/.claude/settings.json:65`), its tools appear in 147 tool listings and were called **0 times** across 310 transcripts; the native `LSP` tool: 0 calls; `~/.serena/memories` holds one file. Official `csharp-lsp`, `pyright-lsp`, `typescript-lsp` plugins exist in the marketplace cache. JUDGEMENT: Serena's symbol tools are what LSP plugins give per edit with no daemon, no per-project index, no uv/Windows path issues; its memories duplicate the codemap. Adopt the three LSP plugins (binaries: `csharp-ls`, `pyright-langserver`, `typescript-language-server`, all absent here); Terraform, PowerShell and SQL have no official LSP plugin, so their feedback comes from the format/lint hooks.

## 9. Stack, hooks, and layer ownership

**Layers.** Global (`~/.claude/settings.json`, the separate audit's job) owns what is true in every repo: format-on-edit, secret-file protection, LSP plugins. Crew owns what needs repo state (`.crew/`): scope guard, cloud/destructive guard with production patterns, verify gate, review budget, context injection, handoff, notify. Crew ships a format hook only as an OFF-by-default fallback (`hooks.formatOnEdit`), and `/crew:doctor` reports if both layers have one on.

| Hook | Event | Blocks | Default | Cost/turn | Absent tool |
|---|---|---|---|---|---|
| context (brief/slices) | SessionStart, UserPromptSubmit, PostToolUse Read/Edit | no | on | ~50 ms, ≤2.5k chars | n/a |
| scope-guard + plan-approval | PreToolUse Edit/Write | **yes** | off in menu; init asks | ~40 ms | n/a |
| cloud-guard | PreToolUse Bash/PowerShell | **yes / ask** | off in menu; init asks | ~40 ms; `az account show` cached 10 min | `az`/`aws` missing → "could not tell" printed, `ask` |
| review-budget | inside adapter + Stop | yes | on | 0 unless review | n/a |
| verify-gate | Stop | yes | on (existing) | measured per rule | rule reports UNKNOWN, not pass |
| context-watch/handoff | Stop, PreCompact | yes (nag) | on (existing) | ~30 ms | n/a |
| format-on-edit (fallback) | PostToolUse Edit/Write | no | off | 0.2–3 s | skips and prints "formatter missing: <name>" once per session |
| notify | Notification | no | off | ~20 ms | n/a |

Format/lint map (crew's fallback and the verify.json rules `stack-*` skills write): `*.tf` → `terraform fmt`, `validate`, `tflint`; `*.cs` → `dotnet format --include`; `*.ts/*.js/*.html` → `prettier --write`, `eslint --fix`; `*.py` → `ruff format`, `ruff check --fix`; `*.sql` → `sqlfluff fix --dialect <from crew.json>`; `*.ps1/psm1` → `Invoke-ScriptAnalyzer -Fix` (5.1 vs 7 rules from the skill); `*.sh` → `shellcheck`. DERIVED: `crew-lint/SKILL.md:16-64` already covers ruff, PSScriptAnalyzer, terraform fmt/tflint, eslint/prettier; `dotnet format`, `sqlfluff`, `shellcheck` are missing; on this box only `terraform`, `pwsh`, `eslint`, `npx` are present of that set.

**Cloud guard.** Wire the classifier that already exists (`crew_guards.classify_access`, `_classify_aws` at `:881`) into a real hook and extend it: `aws … delete-*|terminate-*|rm --recursive|s3 rb`, `az … delete|purge`, `terraform apply` (without `-target`? no — any apply) and `destroy`, `psql/sqlcmd/mysql` payloads with `DROP|TRUNCATE`. Policy `guards.cloudDestructive: block|ask|allow` (`ask` maps to `permissionDecision: "ask"`). Context checks: resolve profile from `--profile`/`AWS_PROFILE`, region from `--region`/`AWS_DEFAULT_REGION`; for `az`, subscription from `--subscription` or a cached `az account show`; refuse when the value matches `production.awsProfiles` / `production.azureSubscriptions`, and treat "unresolvable" as its own state (ask), never as allow. Env pinning: add `AWS_REGION`, `AZURE_SUBSCRIPTION_ID`, `ARM_SUBSCRIPTION_ID`, `TF_VAR_environment` to `PINNED_VARS` (`verify_record.py:151`, `verify-gate.sh:1466`). MCP/skills: `aws-core` + `databases-on-aws`, `azure` (bundles Azure MCP), HashiCorp `terraform` MCP once Docker exists (absent here), `crew-cloud` skill stays as the credential-scoping guide.

## 10. Brainstorm → spec → plan → implement

| Phase | Command | What it does | Existing thing |
|---|---|---|---|
| Brainstorm | `/crew:brainstorm <ask>` | one question per message, options with the recommendation first, assumptions and unknowns listed; explorer for evidence; optional Gemini/Codex second opinion (today's `/crew:plan`); ends with an approved direction written to `spec.md` §Intent | replaces `/crew:plan` and `planner`; **vendors** a ≤120-line crew rewrite of superpowers `brainstorming` (its rule "only one question per message", `brainstorming/SKILL.md:206`) |
| Spec | `/crew:spec` | fills the contract, files the tracker item | replaces `/crew:ticket` |
| Plan | `/crew:plan` | ordered steps, files per step (union → `Touch`), test per step, risks; `--approve` stamps `approved:` after the owner accepts in plan mode | vendors ≤120 lines of `writing-plans` (files per task, `writing-plans/SKILL.md:99`) |
| Implement | `/crew:implement` | steps in order, tests, docs, then `/crew:review`; refuses without an approved plan | replaces `/crew:work`; vendors the task-loop of `executing-plans` |

**Superpowers: remove** (audit: 65 injected lines per session, "before ANY response" skill, 0 invocations). Vendoring three ≤120-line skills that load only on invocation costs ~1k tokens when used versus ~1.2k every session; attribute the source in `NOTICE.md` (check its licence first). **Lightweight path** `/crew:fix`: one subsystem, no new behaviour, known cause, no auth/SQL/IaC/secrets/migrations; it writes a 6-line spec (intent, touch, acceptance = existing verify rule) and skips brainstorm and plan; scope guard and Stop gate still apply; review is one Codex round. Any failed trigger, a `/crew:debug` that finds no cause, or the owner saying "full" escalates to the full path.

## 11. Codex parity

`AGENTS.md` (shared); `.codex/hooks.json` generated by `/crew:init` from the same hook table (context, scope-guard, cloud-guard, review-budget; `commandWindows` for PowerShell); `~/.codex/config.toml` gets `project_doc_fallback_filenames = ["CLAUDE.md"]` and profiles `review` (read-only) and `work` (workspace-write); `codex exec` is the reviewer and, when `dev.provider = codex`, the implementer under the same scope guard. Codex has no `paths:` rules, so PostToolUse is its per-file channel.

## 12. Migration and version plan

`crew 1.0.0` (marketplace + `plugin.json`); 0.20.x tagged `crew-legacy`. `/crew:migrate` (replaces `/crew:upgrade`), one-time, backed up first: `.crew/config.json` schema ≤7 (`SCHEMA_CURRENT = 7`, `crew_state.py:173`; blocks at `crew_upgrade.py:417`) → `.crew/crew.json` schema 1 carrying only tracker, qa/dev, guards, production, verify, hooks, memory; codemap files unchanged (anchors and `_ANCHOR_RE` kept); `.crew/metrics.md` rows → `metrics.jsonl` via today's `read_metrics` parser; `.work/tickets/T-####.md` → `T-####/spec.md` (Want→Intent, Scope touch→Touch, Done when→Acceptance); `INDEX.md` kept. The machine-global config is filtered the same way. No shims.

## 13. Validation

Per ticket (`metrics.json`): wall-clock spec-approved→done, turns, tokens (`session-report`/transcript usage), review rounds, BLOCK/FIX per round, findings confirmed/rejected, scope-guard blocks, injected chars, gate runs/failures, escaped defects (found after done). Baseline: today's `.crew/metrics.md` has one ticket with 5 rounds (0-2 BLOCK, 3-8 FIX per round); reconstruct 10 recent tickets from transcripts for time and turns. Compare 10–20 matched tickets; success = ≥30% less wall-clock or tokens, ≤2 rounds on ≥90% of tickets, zero scope violations reaching review, no rise in escaped defects. Every blocking hook: must-block and must-allow cases in `tests/`, a mutation in `sabotage.py`, both shells (`test_flavour_guard.py` pattern).

## 14. Scorecard: reaching Ahead

| Row | Ahead means | Design | Proof |
|---|---|---|---|
| Prose vs scripts | every rule that can block is a hook with a sabotage-tested suite; instruction files under budget and contradiction-checked — no surveyed tool checks its own prose | §5, §9 | `check_instructions` red on a planted contradiction; `wc -l` budgets in CI |
| Roles vs skills | fewer agents than Codex's 3 built-ins + skills that load on demand; per-session roster cost <1.5k tokens | §4 | `/context` before/after |
| PM pulse on Stop | no blocking Stop hook except the verify gate; state on demand | §1 | zero pulse hooks in `hooks.json`; Stop cost = gate cost only |
| Codemap + graphify | already Ahead; add generated `paths:` rules and hook-time slices so the map loads when the code does | §6 | injected chars per session ≤8k; rules regenerated by onboard test |
| Authority tiers | tiers are `permissionDecision`s and guards, not directives | scope-guard, cloud-guard, plan-approval; `AUTONOMOUS_STOPS` become guard patterns | must-block suite per tier; `bypassPermissions` still blocked (hooks fire regardless) |
| Cross-family review | keep; add spec-in-prompt, full working-tree patch, manifest, budget | §3 | manifest bytes == `git diff` + untracked bytes; round cap test |
| Dual bash/PowerShell | one Python module per event, thin wrappers, parity asserted | `test_flavour_guard.py` extended to every hook | same fixture, same decision from both shells |
| Memory | layered, in-repo, budgeted, shared with Codex | §6 | budget tests; Codex 2k variant; recall-miss log |

Honest limit: "Dual hooks" cannot become one registration — Claude Code needs a `shell: "powershell"` twin (`CLAUDE.md` landmines) — so Ahead there is parity proof, not fewer entries. "Cross-family review" is Ahead by design, but *better defect capture* is unproven until §13 runs.

## 15. Work guides (`docs/guides/crew/`)

Source Markdown under `docs/guides/crew/src/`, built by `doc-builder` (the four current HTML files have no generator, `TODO.md:3236`). Replace `crew-overview` and `crew-capabilities` with 1 and 2; regenerate `crew-technical-reference` from `/crew:reference`; retire the dated progress report.

1. **Quickstart** (T2, T8): install on Windows and Linux; `/crew:init` phases; first `/crew:fix`; ten-minute checklist.
2. **Daily workflow** (T4): worked example of one ticket — brainstorm transcript (one question, three options, recommendation first), the spec, the plan with files/tests, plan-mode approval, the scope guard refusing an out-of-scope edit, tests, docs, review round 1 and 2, done; what each hook prints.
3. **Memory and Obsidian** (T7): setup, capture, gardener schedule, what the brief and slices inject, upkeep (`/crew:onboard --refresh`, anchors).
4. **Working with Codex** (T5, T3): AGENTS.md, profiles, `.codex/hooks.json`, review and implementer modes, when Codex is barred.
5. **Troubleshooting** (T10): stale install (version bump rule), hook noise (budgets, `hooks.*` toggles), review loops (budget file), turning things off (`guards.*`, `verifyGate`, `hooks.*`).

## 16. Ordered tickets

| # | Ticket | Size | Acceptance |
|---|---|---|---|
| T1 | **Review adapter** (0.20.16, this week): patch includes working tree + untracked; manifest; spec acceptance in prompt; `review.json` budget; move review after tests/docs in `work.md` | S (1 day) | test: dirty tree at a fixed fixture yields non-zero patch containing untracked file; third round refused |
| T2 | Rebuild skeleton 1.0.0-alpha: new layout, 4 agents, `/crew:status`, pulse/PM/journal removed, brief ≤12 lines; migrate command; quickstart guide | L | `/context` roster ≤1.5k tokens; migrate round-trips this repo's config, codemap, metrics, tickets |
| T3 | Ticket contract + scope-guard + plan-approval hook | M | must-block/must-allow both shells; sabotage mutation |
| T4 | Brainstorm/spec/plan/implement/fix commands; vendored skills; daily-workflow guide | M | worked example reproducible; `/crew:implement` refuses unapproved plan |
| T5 | Context hook module, generated rules, AGENTS.md, `.codex/hooks.json`, Codex profiles; Codex guide | M | budget tests; Codex receives ≤2k chars |
| T6 | Cloud guard + env pinning + stack skills (7) with format/lint rules; MCP registration in install scripts (matched pair) | M | must-block on `terraform destroy`, `az group delete`, `aws ec2 terminate-instances`; must-allow on `aws s3 ls`; absent-tool degradation test |
| T7 | Obsidian consolidation (obsidian-vault bump, scheduling step, retire 4 entries); memory guide | M | doctor reports one capture owner; 95 queued sessions drained |
| T8 | Instruction budgets + `check_instructions`; repo `CLAUDE.md` → `AGENTS.md` + rules | S | gate red on planted contradiction |
| T9 | Metrics + validation harness; 10-ticket baseline reconstruction | S | `metrics.jsonl` populated for the next 10 tickets |
| T10 | Troubleshooting guide; retire old guides; README re-pin | S | guide built; check-marketplace green |
| T11 | LSP plugins + machine tools install steps in both install scripts | S | idempotent "already installed" branch |
| T12 | Validation review after 10–20 tickets; remove anything unused | S | report against §13 thresholds |

## Open questions for the owner

1. **Codex as implementer by default?** (a) Claude session implements, Codex reviews — recommended: cross-family review is the independence that matters; (b) Codex implements, Claude reviews; (c) alternate per ticket.
2. **.NET Framework 4.8 content** in `stack-dotnet`: (a) keep a short 4.8 section — recommended, the 298-line agent exists and repos may still be on it; (b) drop it; (c) separate `stack-dotnet-framework` skill.
3. **Scope guard default after init**: (a) `block` — recommended; (b) `report` for the first ten tickets; (c) `off`.
4. **Gardener schedule**: (a) daily at a quiet hour — recommended; (b) on SessionEnd (unattended-permission tradeoff); (c) manual `/obsidian-vault:garden` only.

### Critical Files for Implementation
- plugin/crew/commands/review.md
- plugin/crew/hooks/hooks.json
- plugin/crew/hooks/scripts/scope_report.py
- plugin/crew/hooks/scripts/crew_guards.py
- plugin/crew/skills/crew-graph/scripts/crew_upgrade.py