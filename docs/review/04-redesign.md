---
title: crew 1.0 redesign (merged)
date: 2026-09-23
source: merged from 04a (Claude Fable 5.1), 04b (Codex gpt-6-astra xhigh) and their cross-reviews in 04c
status: accepted by the owner 2026-09-23 - ready to build
---

# crew 1.0 redesign

Two designers worked independently from `.work/redesign-brief.md`, then reviewed each other's
designs. This file records what they converged on and what the owner decided. The
evidence, `path:line` citations and full reasoning are in `04a`, `04b` and `04c`.

## Summary

- **Rebuild, not reshape.** crew 1.0 keeps the name, replaces the orchestration and instruction
  layer, and carries forward only tested machinery: verify gate, scope base, codemap + graph +
  freshness, platform sync, handoff, notify, and the sabotage harness. There are no compatibility
  aliases. A one-time `/crew:migrate` carries data forward.
- **One interactive session owns a ticket** through brainstorm → spec → plan → implement → tests →
  docs → review → done. The PM agent, the Stop pulse and the PM journal are deleted.
  `/crew:status` is read-only.
- **Enforcement uses hooks and scripts, not prose:** plan approval before edits, scope, a
  two-round review budget, and cloud/destructive guards.
- **Memory is plain Markdown in the repo** (`AGENTS.md`, generated `.claude/rules/`, auto memory,
  the codemap and graph), delivered by one budgeted context hook shared with Codex. Obsidian has one
  capture owner and a scheduled gardener.
- The first ticket (the review adapter) ships this week as 0.20.16. The rebuild follows as 1.0.0.

## Converged design

### Lifecycle and commands

| Phase | Command | Artifact | Enforced by |
|---|---|---|---|
| Brainstorm | `/crew:brainstorm` | `.work/tickets/<id>/direction.md` | one question per message, options with the recommendation first; ends in an approved direction |
| Spec | `/crew:spec` (replaces `/crew:ticket`) | `spec.md`: Intent, Exclusions, Evidence (`path:line`), Unknowns, Touch, Acceptance checks | required by plan, implement, review and done |
| Plan | `/crew:plan` | `plan.md`: steps with files, test and risk | plan mode; an approval receipt bound to the plan hash; plan paths are validated against `spec.Touch` and never silently widen it |
| Implement | `/crew:implement` (replaces `/crew:work`) | code, tests, docs | scope guard; refuses without an approved plan |
| Review | `/crew:review` | ledger + `review.json` | review adapter, below |
| Done | `/crew:done` | metrics row | accepted review receipt and verify gate |
| Status | `/crew:status` (replaces `/crew:pm`, `/crew:roster`, `/crew:scale`) | none | read-only, ≤40 lines |

Tickets become directories under `.work/tickets/<id>/`, with tracker caches normalised into the same
shape. Scope expansion requires amending the spec and approving again.

### Review adapter (T1, this week)

- The **bundle is frozen from a temporary git index**: committed changes since the ticket base,
  staged and unstaged changes, and untracked files, with renames, file modes and binary/submodule
  manifests. The user's index is never touched. Oversized bundles are split, never truncated.
- The **verdict is CLEAN, FINDINGS or INCOMPLETE**. Unreadable content or a non-zero exit is
  INCOMPLETE, never CLEAN.
- The prompt carries the full contract (intent, exclusions, evidence, unknowns, acceptance, plan),
  the codemap landmines, and the test receipts.
- **Two rounds in total, reserved atomically before launch**, so crashed attempts count. The ledger
  lives at `<git-common-dir>/crew/review/<id>.json` and is shared across worktrees. Exhaustion sets
  NEEDS_REPLAN, and only an approved successor plan continues. A writable flag cannot reset the
  budget. Completion is gated on an accepted receipt bound to the bundle hash, and later edits
  invalidate it.
- Provider order stays Codex → Copilot → Claude `reviewer`. Independence comes from the actual
  model family, not the provider name.
- Review runs **after** tests and docs.

### Roster: 54 agents → 4

`explorer` (read-only), `reviewer` (renamed from `qa-reviewer`), `security`, and `researcher`
(isolated web tools). Everything else is deleted. The knowledge the owner's stack needs becomes
skills that load on demand: `stack-terraform`, `stack-dotnet`, `stack-angular` (AngularJS and
Angular), `stack-python`, `stack-sql` (SQL Server, MySQL and PostgreSQL), `stack-powershell`
(separate 5.1 and 7 checks) and `stack-bash`, plus AWS/Azure knowledge in `crew-cloud`. Docs roles
become the `/crew:docs` command and the `crew-docs` skill. Off-stack personas are deleted, and git
history keeps them.

### Instruction surface

| File | Now | Target |
|---|---|---|
| `AGENTS.md` (new, shared by Claude and Codex) | none | ≤80 lines |
| repo `CLAUDE.md` | 319 lines | `@AGENTS.md` plus ≤10 lines |
| `/crew:status` | pm.md is 991 lines | ≤40 lines |
| command files | up to 496 lines | ≤120 lines each |
| generated `.claude/rules/<subsystem>.md` | none | ≤30 lines each, `paths:`-scoped, with a source hash |
| plugin Markdown total | 27,194 lines | ≤6,000 lines, marked with a checked claim marker |

CI checks the size budgets, stale names, generated-file drift, broken references and typed policy
IDs. Semantic contradictions go to review.

### Hooks crew ships

| Hook | Event | Blocks | Notes |
|---|---|---|---|
| context | SessionStart; UserPromptSubmit; PostToolUse Read/Edit/Write | no | SessionStart ≤12 lines / 1,500 chars on startup, ≤3,000 chars when resuming a handoff; per-turn slices ≤2,000 chars combined; hard cap 6,000 chars per emission; deduplicated per subsystem and compaction epoch. Also routes selected vault recall. The low-context warning becomes a one-time non-blocking note. |
| plan-approval + scope guard | PreToolUse Write/Edit/MultiEdit/NotebookEdit | yes | no blanket exemption for crew's own policy or approval files; handles canonical paths, renames and symlinks |
| completion scope audit | Stop | yes | diffs the whole tree against the scope base, catching shell-made writes too, and refuses `done` on out-of-scope paths |
| cloud/destructive guard | PreToolUse Bash/PowerShell | yes/ask | wires crew's existing but unenforced `guards.*` (`terraformApply`, `forcePush`, `prodDatabase`). Covers `terraform apply`/`destroy`, `aws` delete/terminate, `az` delete/purge, and SQL `DROP`/`TRUNCATE`. Checks the effective AWS profile/region and Azure subscription; an unknown identity is never allowed unattended. |
| verify gate | Stop | yes | 0 lines on pass, ≤6 on fail; deferred checks stay UNVERIFIED |
| handoff capture | PreCompact | no | kept |
| notify | Notification | no | opt-in |
| removed | the pulse, pm-brief, handoff-read (folded into context), auto-clear, and context-watch as a Stop blocker | | |

Format-on-edit lives in the owner's **global** settings, not crew, with one formatter owner. crew's
`stack-*` skills write the lint rules into `verify.json`. A missing tool gives a bounded warning and
an UNVERIFIED check, never PASS. Registration is one per handler where the documented exec form
works on both OSes, which is probed rather than assumed; otherwise matched `.sh`/`.ps1` wrappers.

### Memory and Obsidian

- Plain Markdown plus targeted search. basic-memory stays optional and is adopted only if a
  measured retrieval failure appears. Subagent `memory:` is not used, because it grants Write/Edit.
- `obsidian-vault` owns setup, capture and gardening; `/crew:init` delegates to it. Setup detects
  or installs Obsidian (winget; flatpak, deb or AppImage), creates or adopts a vault, and asks before
  each change. It is idempotent. The REST bridge is optional.
- Captures go to per-host queue files. Gardening runs on one designated host, at most 5 items or 10
  minutes per run, and acknowledges each item only after a successful write. Only owned files are
  committed. A seeded note proves the whole loop: capture, distillation, recall.
- `claude-memories-vault` and `claude-memories-canvas` become portable vault profiles, then leave
  the marketplace. `vault-automation/` retires once its functions are replaced.
  `claude-obsidian-setup/` stays, because it serves a different plugin.

### Codex parity

`AGENTS.md`; `.codex/hooks.json` generated from the same hook table, with `commandWindows`;
`project_doc_fallback_filenames`; `review` (read-only) and `work` profiles; `codex exec --json
--sandbox read-only` for review. Hook delivery is probed at init, and anything unproven is reported
as "configured, not proven".

### Migration

`/crew:migrate` is a one-time step that previews, backs up, applies atomically and can roll back. It
moves `.crew/config.json` (schema ≤7) to `.crew/crew.json` (schema 1) and imports file tickets **and**
tracker caches with their identities and provenance. Codemaps and anchors are left untouched.
`metrics.md` becomes `metrics.jsonl`, with missing historical values marked UNKNOWN. The PM journal is
archived.

### Validation

Per ticket, record: phases and timestamps, active time, tokens or cost (UNKNOWN when unavailable),
review rounds, confirmed/rejected/duplicate findings, scope blocks, injected characters, and escaped
defects. Compare 10–20 prospective matched tickets against the 0.20 baseline. Success means at least
30% lower median active time or cost, 100% review-budget enforcement, zero unapproved scope changes,
and no rise in escaped defects. Every blocking hook needs must-block/must-allow cases in both shells
and a sabotage mutation.

### Scorecard, honestly

Each row is "Ahead" only once its proof in `04a` §14 or `04b` passes:
- Stop-pulse removal alone reaches **Par**; the row is Ahead only through the verify gate's receipts.
- The dual-hook row is **Par** until single-invocation parity is proven on Windows and Linux.
- Every other "Ahead" claim needs a benchmark against a named alternative. File counts and internal
  tests are not enough.

### Guides

Markdown sources under `docs/guides/crew/src/`, rendered by doc-builder. There are five: Quickstart,
Daily workflow (full and light worked examples), Memory and Obsidian, Working with Codex, and
Troubleshooting. The overview, capabilities and technical-reference families are replaced; the
progress report is archived. A feature isn't done until its guide section exists.

### Ticket order

T1 review adapter (0.20.16) → T2 1.0 skeleton + migrate + status + quickstart → T3 contract,
plan-approval, scope guard and completion audit → T4 lifecycle commands + daily-workflow guide →
T5 cloud/destructive guard + env pinning + stack skills → T6 context hook, generated rules,
`AGENTS.md`, Codex parity + Codex guide → T7 Obsidian consolidation + memory guide → T8 instruction
budgets and checks → T9 metrics harness → T10 troubleshooting guide, retire old guides, README re-pin
→ T11 LSP and tool install steps in both install scripts → T12 validation after 10–20 tickets.

## Decisions for the owner

Decided by the owner on 2026-09-23. Each one settles a point where the two designers disagreed.

| Question | Decision | Rejected alternative |
|---|---|---|
| Brainstorm/plan skills | **Vendor three ≤120-line crew skills** (brainstorm, plan, execute) and uninstall superpowers. Check the licence before reusing any text and credit it in `NOTICE.md`. | Wrapping pinned superpowers through adapters |
| Light path (`/crew:fix`) | **Compressed, every phase present**: a one-line direction, a short spec, a one-step plan, then approval | Skipping brainstorm and plan |
| Write guarding | **Edit guard before the call, plus a Stop-time whole-tree scope audit** | Also denying shell/MCP writes through a runner |
| Scope guard default after init | **`report` for the first 10 tickets, then `block`** | `block` immediately; report permanently |
| Serena | **Skip.** Adopt the official C#, Python and TypeScript LSP plugins and the Angular language service. | Optional measured pilot |
| Implementer | **The interactive Claude session implements; Codex reviews** | Codex implements; choosing per ticket |
| .NET Framework 4.8 | **A short 4.8 section in `stack-dotnet`** | Leaving it out |
| Windows parity proof | **A GitHub Actions `windows-latest` job running the hook parity suite** | A manual run per release; accepting Par |
| Gardening | **One designated host, daily, bounded runs** (both designers agree) | Running at SessionEnd |
| Guide format | **Markdown sources rendered by doc-builder** (both designers agree) | Hand-built HTML |
