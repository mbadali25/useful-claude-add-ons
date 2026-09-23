---
title: crew redesign - Codex design
date: 2026-09-23
source: Codex gpt-6-astra, reasoning effort xhigh, read-only, from .work/redesign-brief.md (read before addenda 3-5 were appended)
status: draft - to be cross-reviewed against the Fable design
---

**JUDGEMENT:** One interactive session owns each ordinary ticket; PM becomes a status command.  
**JUDGEMENT:** Fix complete-change review first; enforce specifications and a durable two-round limit.  
**JUDGEMENT:** Keep three isolated roles; preserve useful expertise in skills and references.  
**JUDGEMENT:** Use one Markdown memory owner, with confirmed Obsidian setup on Windows and Linux.  
**JUDGEMENT:** Make “Ahead” measurable; removing overhead alone can only match native behavior.

**DERIVED — Starting evidence.** Only 17 of 53 enabled roles appeared in the usage ranking; these are not exact dispatch counts. There are 54 agent files including PM. Crew itself requires isolation, restricted tools, or independent eyes to justify a role. Actual session costs remain unverified. Sources: [review README:58](../../docs/review/README.md:58), [Codex review:13](../../docs/review/03-codex-review.md:13), [crew README:48](../../plugin/crew/README.md:48), [measurement limits:79](../../docs/review/README.md:79).

**JUDGEMENT — Architecture and ticket contract.** A small Python runner owns state transitions, verification receipts, review bundles, and policy decisions. Commands are thin entry points. The interactive owner explores, plans, implements, tests, documents, then requests review. Optional native workers handle explicitly independent work; ordinary tickets require no delegation.

**JUDGEMENT:** Remove the PM agent. `/crew:pm` becomes a deprecated alias for read-only `/crew:status`. Delete the Stop pulse: **zero injected lines**. Replace PM brief, handoff reader, and platform reporting with one SessionStart brief: **maximum 12 lines**, containing facts and pointers.

**JUDGEMENT:** Keep `.work/tickets/<id>.md`; normalize external tracker caches into that contract. Require intent, exclusions, allowed paths, `path:line` evidence, unknowns, acceptance checks, test/doc obligations, owner, base commit, and approved plan. `/crew:plan` requires a draft; `work`, `review`, `done`, and `promote` require the approved contract. Defects require diagnosis.

**JUDGEMENT:** Scope/authority PreToolUse hooks validate Write/Edit/apply_patch, rename endpoints, canonical paths, symlinks, and deletions. Arbitrary shell/MCP writes are denied; approved runners test disposable copies and apply only permitted changes. Policy and review state are runner-owned. Scope expansion changes the approved contract. PostToolUse/completion audits detect bypasses; they cannot undo writes.

**JUDGEMENT:** `report-only` permits inspection; `act` permits approved ticket operations; `autonomous` adds routine choices within those boundaries. Production and destructive operations retain explicit authorization, artifact/environment receipts, rollback requirements, and hard stops. Hooks supplement native permissions, never replace the sandbox.

**DERIVED — Review defects.** The patch uses `BASE...HEAD`, excluding dirty content; tests and docs follow review. Sources: [review.md:311](../../plugin/crew/commands/review.md:311), [work.md:186](../../plugin/crew/commands/work.md:186).

**JUDGEMENT — Review adapter.** Freeze the ticket’s complete intended result: committed changes since its base, staged/unstaged content, untracked additions, deletions, renames, modes, and binary/submodule contents and manifests. Use a temporary index, never the user’s index. Ambiguous pre-existing edits require explicit inclusion or an isolated worktree. Oversized changes split into bundles within one round, never silently truncate.

**JUDGEMENT:** Every reviewer receives the same spec, plan, complete patch, source snapshot, map warnings, test receipts, documentation, and previous finding dispositions. Unreadable or unsupported content means INCOMPLETE, never CLEAN. Bind acceptance to spec/snapshot hashes; later edits invalidate it. Review starts after tests and docs are finished.

**JUDGEMENT:** Reserve one of **two total rounds atomically before launch**, including crashed attempts. Persist the ticket ledger in the common Git directory, shared across worktrees; portable ticket bundles carry it between machines. Missing state is UNKNOWN. Two unsuccessful rounds set NEEDS_REPLAN; no third review or automatic approval. A successor requires an explicit revised plan and links the exhausted ticket.

**JUDGEMENT:** Preserve Codex → Copilot → Claude ordering, filtering actual author/model families first. Provider names do not establish independence. Unknown authorship or same-family fallback cannot certify independence. Specialists participate inside the same round.

**JUDGEMENT — Exact roster.** Keep `explorer`, `security`, `qa-reviewer`, with restricted tools and immutable review snapshots. Remove every other agent file, preserving useful material as follows. All mappings are **JUDGEMENT**; references load individually.

| Replacement skill/reference | Removed roles |
|---|---|
| Delivery and Git | developer, backend-developer, git-workflow-manager |
| crew-docs / crew-house-style | docs-writer, scribe, ai-writing-auditor |
| Planning, architecture, modernization | analyst, planner, architect-reviewer, api-designer, graphql-architect, microservices-architect, legacy-modernizer |
| crew-verification / review checklists | smoke-author, browser-tester, code-reviewer |
| Research | researcher, qa-researcher |
| Database checks | dba, database-administrator, sql-pro |
| Version-specific language references | angular-architect, dotnet-core-expert, dotnet-framework-4.8-expert, node-developer, php-pro, powershell-5.1-expert, powershell-7-expert, python-pro, react-specialist, rust-engineer |
| Infrastructure references | infrastructure-architect, platform-engineer, network-engineer, windows-infra-admin |
| Security checklists | ad-security-reviewer, powershell-security-hardening, penetration-tester, compliance-auditor |
| Microsoft operations | exchange-online-specialist, sharepoint-developer, power-automate-specialist |
| Payments | fintech-engineer, payment-integration |
| Design references | design-bridge |
| Skill authoring | skill-author |
| crew-terraform | terraform-engineer |
| crew-providers adapter | kimi-consult |
| Status command | pm |
| Native workflow recipes: dependencies, retries, cancellation | multi-agent-coordinator, workflow-orchestrator |

**JUDGEMENT:** High usage preserves developer/scribe/DBA knowledge, not personas; low usage does not erase security’s isolation benefit. Drop generic coordination boilerplate and unsupported numeric promises. Verification rules naming removed agents migrate to reviewer-plus-checklist mappings.

**JUDGEMENT — Instruction surface.** Shared `AGENTS.md`: ≤120 lines/8 KiB. Root `CLAUDE.md`: ≤15 lines, importing `@AGENTS.md`; status successor ≤40 lines; commands ≤60 lines each; retained agents ≤80 lines. Preserve rules in typed policy and incident history in referenced documents. CI checks sizes, stale names, contradictory policy IDs, generated-file drift, and broken references. Independent review catches semantic contradictions that lint cannot prove.

**JUDGEMENT — Hook catalogue.** Every hook defaults **OFF in the install menu**, with explicit per-repo enablement. All rows are **JUDGEMENT**; costs are targets, not measurements.

| Hook | Event | Blocks? | Cost when enabled |
|---|---|---|---|
| Context/platform brief | SessionStart; UserPromptSubmit; PostToolUse reads/edits | No | ≤200 ms/event; bounded context below |
| Scope, authority, production guards | PreToolUse edits/shell/MCP | Yes | ≤100 ms/call; silent on allow |
| Review budget | PreToolUse review launch; mandatory adapter check | Yes | ≤100 ms/launch; zero otherwise |
| Verification/completion | Stop, TaskCompleted, promotion PreToolUse | Yes | ≤200 ms cached; changed checks ≤60 s at Stop |
| Format-on-edit | PostToolUse edits | No | Debounced, ≤1 s/file; zero model tokens |
| Handoff/memory capture | PreCompact, SessionEnd | No | ≤200 ms/event; zero ordinary-turn cost |
| Vault contract | PreToolUse vault mutations | Yes | ≤100 ms/write |
| Notifications | Notification | No | Optional, ≤1 s/event |
| Graph refresh | Git post-commit | No | Background; measured duration; zero turn injection |

**JUDGEMENT:** Stop emits zero lines on success, at most six on failure. Deferred checks remain unverified; `/crew:done` cannot pass them. Prevent continuation loops without declaring success. Formatting stays inside scope and invalidates receipts. Retire terminal auto-clear and blocking context-watch; capture checkpoints instead. Remove automatic REST probing for filesystem memory. Notifications require separate opt-in.

**JUDGEMENT — Memory and maps.** Choose plain Markdown plus targeted search: repository contracts/ADRs/codemaps remain authoritative; Obsidian holds selected cross-project lessons. `obsidian-vault` owns capture and retrieval; crew’s context hook calls that owner without a second recall hook.

**JUDGEMENT:** SessionStart: ≤3,000 characters/750 tokens. Prompt/file-triggered context together: ≤2,000 characters/500 tokens per turn, deduplicated by subsystem/content/compaction epoch. Hard-cap each message at 6,000 characters/1,500 tokens, including its envelope; count tokens rather than assuming four characters per token. Missing, stale, or unresolvable evidence retains that label.

**JUDGEMENT:** Generate `.claude/rules/<subsystem>.md` with `paths`, ≤30 lines, source hash, anchors, responsibilities, landmines, and retrieval pointers. Refresh explicitly; preserve handwritten rules. Include dirty-path freshness and atomic graph/report generation. Do not export graph nodes into Obsidian.

**JUDGEMENT:** Auto memory holds short preferences/corrections and pointers, never ticket status; target its index at ≤60 lines. Do not enable subagent `memory:` on retained read-only roles.

**DERIVED:** Subagent memory grants Write/Edit; the measured vault setup had 95 pending captures. Sources: [Codex review:59](../../docs/review/03-codex-review.md:59), [review README:73](../../docs/review/README.md:73).

**JUDGEMENT — Obsidian setup and consolidation.** `/crew:memory-setup` delegates to `/obsidian-vault:init`, starting with a read-only plan. Windows detection combines executable/registry checks and winget inventory; offer `Obsidian.Obsidian` if absent. Linux checks Flatpak, AppImage locations, and deb inventory; offer an appropriate verified distribution or skip. Distinguish missing, inaccessible, and unknown.

**JUDGEMENT:** Ask before **each change**: installation, vault creation/adoption, configuration, hook enablement, scheduler creation, optional backend/plugin. Merge settings with backups and atomic writes; rerunning accepted setup produces no changes. Adopt existing conventions; recommend Markdown templates, index, provenance/supersession, and core search/Canvas. REST/community plugins are optional. Installed application, accessible vault, and working memory loop are separate outcomes.

**JUDGEMENT:** Ship a portable queue writer and lock. Capture unique host/session checkpoints; distil on one designated host through Task Scheduler or systemd user timer/cron. Bound runs to five items/ten minutes, serialize manual runs, and acknowledge items only after successful writes. Missing transcripts remain unresolved. Prove capture→distil→recall with a seeded note and actual scheduled run. Never sweep unrelated staged files into commits.

**JUDGEMENT:** Keep basic-memory optional, sharing the vault and ownership. Adopt it only after a retrieval benchmark beats Markdown; disable duplicate capture/briefing.

**DERIVED:** Five marketplace entries match the requested names: [marketplace.json:47](../../.claude-plugin/marketplace.json:47), [:137](../../.claude-plugin/marketplace.json:137), [:245](../../.claude-plugin/marketplace.json:245).

**JUDGEMENT:** Keep `obsidian-vault` as owner, `obsidian-canvas` as generic authoring, and `obsidian-vault-server` as optional remote hosting. Merge `claude-memories-vault` and `claude-memories-canvas` into selectable vault-profile references, then retire their entries after approval. External plugin/hook auditing remains outside this design.

**JUDGEMENT — Codex parity.** Generate `.codex/hooks.json` from the shared event/policy registry, using `commandWindows` and verified tool-name mappings. Probe event delivery and effective settings: configured must not imply enforced. Provide CLI/skill entry points, shared `AGENTS.md`, and `codex exec --json --sandbox read-only` with structured review output. Empty output/nonzero exit never passes. Unsupported hooks mean visibly reduced operation; runner/CI still gate completion and promotion.

**DERIVED:** Current Codex docs say hooks default on, specify approximately 2,500-token context limits, and identify coverage exceptions: [docs/hooks:1085,1164,1229](https://learn.chatgpt.com/docs/hooks). Claude supports explicit imports: [docs/en/memory:444](https://code.claude.com/docs/en/memory). The installer must probe versions rather than inherit the reports’ assumptions.

**JUDGEMENT — Serena.** Optional, separately installed and version-pinned; no vendoring. Compare symbol/reference tasks and edits in .NET, Python, and TS against [native Claude LSP](https://code.claude.com/docs/en/plugins-reference#lsp-servers) plus codemap, and Codex plus search. Potential value: semantic navigation/editing. Costs: uv, language servers, indexing, and Windows runtime/path setup. Codemap retains architectural reasons and freshness. Enable only for ≥20% lower median task time or tokens with equal correctness.

**DERIVED:** Upstream distinguishes MIT SolidLSP from GPL-3.0-or-later application code, preserving historical MIT releases: [060_license.html:52](https://oraios.github.io/serena/01-about/060_license.html). Its current C# backend requires .NET 10+ and PowerShell 7 on Windows: [020_programming-languages.html:77](https://oraios.github.io/serena/01-about/020_programming-languages.html).

**JUDGEMENT — Migration.** Next 0.20.x patch fixes review; 0.21–0.24 add opt-in components; 1.0 removes legacy orchestration after the pilot. Schema 7→8 preserves unknown keys and explicit choices; earlier schemas migrate sequentially, future schemas refuse mutation. `/crew:upgrade` previews, backs up, applies atomically, validates, and supports rollback. Never pin inherited defaults or silently remove suspected historical pins.

**JUDGEMENT:** Preserve codemap prose/anchors, verification/endpoints maps, trackers, metrics, and dispatch history. Import old measurements as legacy/unknown; archive PM journal. Initialize ignored ticket state explicitly in worktrees. Entry retirement requires approval. Bump every changed entry’s applicable manifest/marketplace/catalog declarations together; update both installers, ordering, licences/NOTICE, and supported claim markers.

**DERIVED — Scorecard evidence.** Baselines appear in [field comparison:45](../../docs/review/01-field-comparison-and-pain-points.md:45); comparative superiority remains unproven in [Codex review:60](../../docs/review/03-codex-review.md:60). These are scoped targets, not earned ratings.

**JUDGEMENT — Prose versus scripts.** **Ahead means:** fewer missed obligations than Spec Kit/native instructions at lower context cost. **Design:** executable contracts and thin commands. **Proof:** seeded omissions produce zero false completions; ≥50% less loaded crew instruction text.

**JUDGEMENT — Roster.** **Ahead means:** better accepted-ticket throughput than superpowers/native generalists. **Design:** three justified roles and selective references. **Proof:** matched trials achieve ≥30% time or cost reduction without quality loss. Fewer files proves nothing.

**JUDGEMENT — Stop pulse.** **Ahead means:** less interruption without lost work. **Design:** no automatic PM; explicit status. **Proof:** zero unsolicited dispatches and lost resumptions versus native Claude/Codex. **Removal alone reaches Par, not Ahead: zero native overhead cannot be beaten.**

**JUDGEMENT — Codemap/graph/Mermaid.** **Ahead means:** more trustworthy impact analysis than Serena, graphify alone, or native LSP. **Design:** joined anchors, dirty-state checks, consistent artifacts. **Proof:** all seeded stale/unresolvable cases flagged; ≥90% correct affected-subsystem answers.

**JUDGEMENT — Authority.** **Ahead means:** ticket-specific scope and receipts beyond BMAD/native permission modes. **Design:** hooks, native permissions, runner-owned state. **Proof:** sabotage/bypass matrix blocks supported unauthorized mutations and allows authorized work. No claim of stronger sandbox security.

**JUDGEMENT — Cross-family review.** **Ahead means:** fewer escaped seeded defects than Ruflo/BMAD/native review at bounded cost. **Design:** complete snapshots, actual-family evidence, two rounds. **Proof:** 100% intended-file coverage, zero false CLEAN on failures, fewer misses at equal review budget.

**JUDGEMENT — Dual hooks.** **Ahead means:** portable correctness with one registration per handler. **Design:** shared Python core, generated platform registration, matched wrappers; remove duplicate bundled activation. **Proof:** identical decisions and exactly one invocation on both OSes. **Native execution superiority remains unproven: Par until benchmarked.**

**JUDGEMENT — Memory.** **Ahead means:** more useful, fresher recall than native auto memory/basic-memory alone. **Design:** provenance, supersession, codemap joins, one owner. **Proof:** ≥80% useful top-three recall, zero unlabelled stale injections, backlog under 48 hours.

**JUDGEMENT — Delivery tickets.** Sizes are engineering days. Each ships independently with guide sections; incomplete integrations remain disabled.

| Order | Ticket and acceptance | Size |
|---|---|---|
| T1 | Complete-review adapter and tests/docs ordering; committed/dirty/untracked fixtures covered | 1–2d; this week |
| T2 | Contract/state runner and two-round ledger; restart/race/missing-state cases pass | 3d |
| T3 | Scope/authority/completion hooks; sabotage and permission-boundary matrix passes | 4d |
| T4 | Shared instructions, skill extraction, optional reduced roster; 54 roles mapped, legacy compatibility retained | 2–3d |
| T5 | Context, codemap rules, Markdown retrieval; budgets/dedup/freshness pass | 3d |
| T6 | Obsidian setup, queue, scheduling, profiles; fresh/adopt/rerun/rollback pass both OSes | 4d |
| T7 | Codex parity/single registrations; live delivery and decisions verified | 3d |
| T8 | Upgrade/rollback and retirement; schema fixtures preserve user data | 2d |
| T9 | Twenty-ticket pilot, Serena comparison, published scorecard; adopt/revise decision | 3d plus observation |

**JUDGEMENT — Work guides.** Ship under `docs/guides/crew/`; feature acceptance requires executable examples and expected hook behavior.

- **Quickstart — T2/T7/T8:** install, enable, init, first ticket, recovery; novice completes in ≤10 minutes on declared Windows/Linux VM/network fixtures.
- **Daily workflow — T1–T4:** what to type: ticket → plan → work → check → review → done; scope expansion, receipts, two-round replanning.
- **Memory and Obsidian — T5/T6:** setup choices, captured content, session recall, gardener logs, backlog recovery, optional backend.
- **Codex alongside Claude — T2/T7:** shared contract, handoff, authorship, review commands, parity limitations.
- **Troubleshooting — T1/T3/T8:** stale installation, hook noise/logs, review exhaustion, disabling hooks, rollback.

**JUDGEMENT:** Replace `crew-overview`, `crew-capabilities`, and `crew-technical-reference` families, including Solomon/HTML/PDF/DOCX variants, with guide-derived exports. Archive the dated progress-report family as historical evidence.

**JUDGEMENT — Validation.** Compare ten matched old/new ticket pairs, stratified by repository, risk, language, OS, harness/model. Record elapsed/active/wait time, billed tokens/cost or UNKNOWN, hook overhead/injection, interventions, scope violations, rounds, accepted/duplicate/rejected findings, escaped defects, and recall usefulness. Target ≥30% lower median active time or cost, no quality regression, zero severe escapes/unapproved scope changes, and fulfilled budgets. Treat this as a pilot; observe escapes for 30 days.

**JUDGEMENT:** Every blocker needs must-block/must-allow pairs: outside/inside scope, missing/valid authority, third/second review, stale/current receipts, invalid/valid vault writes. Test malformed inputs, absent interpreters, timeouts, duplicate events, concurrency, and unmanaged repos. Sabotage each refusal and verify the intended assertion fails. Nonblockers test bounded output, no-op behavior, reported failures, and deduplication.

**JUDGEMENT:** Run marketplace gate, smoke, self-claims, pytest, then pylint; inspect exit codes. Prove native Windows, Git Bash, and Linux behavior. Keep `.sh` LF; measure blob/worktree separately, use native-visible temporary paths, resolve interpreters, and scope `MSYS_NO_PATHCONV` per command. This is design-only: no files changed or validation suites run.

**Open questions for the owner**

- **JUDGEMENT — Vault:** adopt populated `claude-memories` **(recommended)**; create a fresh vault; retain separate project vaults.
- **JUDGEMENT — Gardening:** nightly on one designated host **(recommended)**; attended runs only.
- **JUDGEMENT — Serena:** optional pilot after the core redesign **(recommended)**; defer entirely.