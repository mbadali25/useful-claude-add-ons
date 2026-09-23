---
title: crew redesign - cross-reviews
date: 2026-09-23
source: Claude Fable 5.1 (reviewing 04b) and Codex gpt-6-astra xhigh (reviewing 04a, after reading addenda 3-5)
status: input to 04-redesign.md
---

# Fable reviews Codex

## Cross-review of `docs/review/04b-redesign-codex.md` against my design (`04a`)

### 1. Where Codex is right, and I change

- **Temp-index review bundle.** My adapter built the patch as `git diff <base>` plus one `--no-index` diff per untracked file, which loses rename detection, mode changes and binary/submodule handling. Codex's temporary index (`GIT_INDEX_FILE=<tmp> git add -A && git diff --cached <base>`) gives one patch with all of that and never touches the user's index. **Adopt.** DERIVED baseline is unchanged: `review.md:311` yields 0 bytes at `8b8a4028` against 107,107 bytes of `git diff HEAD` and 7 untracked files.
- **INCOMPLETE is a verdict, never CLEAN.** My design recorded a manifest but had no explicit verdict for "could not read part of the bundle". That is exactly the repo's named recurring defect (`CLAUDE.md`, "an unknown collapsing into the safe-looking value"; `review.md` step 2b already says "never record a CLEAN verdict from a run that exited non-zero"). **Adopt** a three-valued verdict: CLEAN / FINDINGS / INCOMPLETE.
- **Reserve the round before launch.** My "third invocation exits" leaves a crashed round uncounted. Reserving atomically (`O_CREAT|O_EXCL`, the idiom `pm_pulse.py:claim` already uses) before the provider runs closes that. **Adopt.**
- **Ledger in the common git dir.** `.crew/` and `.work/` are gitignored and per-worktree (`CLAUDE.md` gitignore policy; `crew_state.worktree_path` at `crew_state.py:2921`), so a ticket worked in two worktrees would get two budgets. `$(git rev-parse --git-common-dir)/crew/review/<ticket>.json` is the one location shared across worktrees of a clone. **Adopt**, with a rendered copy in the ticket's `review.json` for humans. I drop the "portable bundles" half: the budget is a fact about one clone, and a clone elsewhere starts at zero honestly.
- **Hard cap 6,000 chars, not 8,000.** My 8,000-char cap at a conservative 3 chars/token is ~2,700 tokens, over Codex's ~2,500-token `additionalContextLimit` (`02-memory-and-injection.md` §3). **Adopt 6,000.** I do not adopt token counting in the hook: it needs a tokenizer dependency on both OSes; a 3-chars/token ratio is the safe side of both limits.
- **Retire auto-clear; move context-watch off Stop.** `context-watch.sh:13-24` documents the false `/clear` at low context on Windows; `auto-clear` drives a terminal keystroke by window title (`.crew/config.json` `context.autoClear.windowTitle`). A blocking Stop nag is the only way a Stop hook reaches the model, which is why it blocks. **Delta:** retire auto-clear; re-home context-watch as a non-blocking `UserPromptSubmit` `additionalContext` line, once per threshold crossing; `handoff-write` on PreCompact stays as the capture checkpoint.
- **Stop output budget.** Zero lines on success, ≤6 on failure. **Adopt.**
- **Designated gardening host, bounded runs.** Matches my open question 4(a); `gardener.md:27` already takes "up to 5" entries. **Adopt** the 5-items/10-minutes bound and acknowledge-after-write.
- **Pulse removal alone is Par.** Correct: native Claude and Codex have no pulse to beat. My scorecard row overclaimed. **Delta:** the row reaches Ahead only through what fires on Stop instead — the verify gate's per-rule verified record and priced reach (`ff48c381`, `verify_record.py`), which no surveyed tool produces. Removal = Par; receipts = Ahead; the row now says both.

### 2. Where Codex is wrong

- **Three roles: dropping `researcher`.** Codex maps it to a "Research" reference. A reference does not isolate context; `researcher`'s value is that `WebSearch`/`WebFetch`/context7 output (`agents/researcher.md` frontmatter) stays out of the working session — rule 1 of `README.md:48-54`, and a restricted toolset (no Bash, no Write). 10 uses in 60 days is more than `security`'s 2, which Codex keeps. **Keep four.**
- **Denying arbitrary shell/MCP writes.** A PreToolUse hook cannot classify writes inside `bash -c`, heredocs, `python -c`, or redirects; crew's own `_classify_shell` (`crew_guards.py:812`) is a best-effort tokenizer, and the scope layer was made report-only for precisely this reason (`scope_report.py:3-8`). Denying shell writes blocks `git commit`, `terraform fmt`, test fixtures. "Approved runners test disposable copies" is a second execution engine with its own Windows story. **Keep mine:** guard `Write|Edit|MultiEdit|NotebookEdit` pre-call, and at Stop diff the whole tree from `.crew/.scope-base` (`scope_base.py`, recorded at `work.md` step 1) — exhaustive regardless of how the write happened — and refuse `done` on out-of-scope paths.
- **A 12-line SessionStart for every source.** On `clear|compact|resume` the brief must carry the handoff note and its `Next action`, which is what makes resume work (`pm_brief.py:664-712`, `_resume_context`); 12 lines cannot. **Mine:** ≤12 lines at `startup`; ≤3,000 chars when a handoff exists (Codex's own cap).
- **Folding platform-sync into the brief.** It is not reporting: it *repairs* the platform block of `.crew/config.json` (`platform-sync.sh:2-7`, `crew_platform.py`). It stays a write step, silent on success.
- **A queue lock across hosts.** The vault is Obsidian-Synced and committed by Obsidian Git every 15 minutes (`skills/claude-memories-vault/SKILL.md:18-20`); a lock file synced between hosts produces conflict copies, not mutual exclusion. **Mine:** per-host queue files `inbox/pending-reflect.<host>.md`, no lock; the designated host drains all of them.
- **Serena as a pilot.** DERIVED: Serena is enabled (`~/.claude/settings.json:65`), listed in 147 tool lists, called 0 times in 310 transcripts; the native `LSP` tool 0 times. A pilot needs a demand signal; there is none. Codex's licence finding (GPL-3.0-or-later application, MIT SolidLSP) is UNVERIFIED here (not fetched) and immaterial either way: crew would not vendor Serena, and use is unrestricted under GPL. **Keep skip;** if the owner wants a pilot, Codex's ≥20% median-time entry criterion is the right bar.
- **"Every hook defaults OFF"** is stricter than `CLAUDE.md`'s rule, which is about the plugin's *install-menu row* (`install-prerequisites.sh:1949`, "a row that is off by default (--plugins crew)"). Both designs comply; Codex's per-hook OFF would ship a verify gate nobody turns on.
- **Codex hooks "default on"** (Codex, citing docs) versus "gated by `[features] hooks = true`" (`02-memory-and-injection.md` §3). Unresolved; Codex's own remedy — probe at install — is right and I adopt the probe.

### 3. Revised delta (only what changes in `04a`)

| Section | Change |
|---|---|
| §3 Review | Bundle via temporary index; verdict CLEAN/FINDINGS/INCOMPLETE; round reserved atomically before launch; ledger at `<git-common-dir>/crew/review/<ticket>.json`, rendered into the ticket's `review.json` |
| §1/§6 Budgets | SessionStart ≤12 lines at `startup`, ≤3,000 chars with a handoff; per-turn slices ≤2,000 chars combined; hard cap 6,000 chars per emission; Stop: 0 lines on pass, ≤6 on fail |
| §9 Hooks | `auto-clear` retired; `context-watch` moves from Stop (exit 2) to `UserPromptSubmit` (`additionalContext`, once per crossing); `platform-sync` kept, silent |
| §7 Obsidian | Per-host queue files, no lock; one designated gardening host; runs bounded to 5 items / 10 minutes; acknowledge after successful write |
| §11 Codex | `/crew:init` probes hook delivery and prints "configured, not proven" until a test event round-trips |
| §14 Scorecard | "PM pulse on Stop": removal = Par; Ahead claimed only via verify-gate receipts, with the proof being the per-rule verified record |
| §16 Tickets | T1 acceptance adds: rename and mode-change fixtures, INCOMPLETE on an unreadable file; T2 adds the common-git-dir ledger |

### 4. Remaining disagreements

| Topic | Codex | Mine (recommended) | Evidence |
|---|---|---|---|
| Roster | 3 (explorer, security, qa-reviewer) | 4 (+ `researcher`) | isolation rule `README.md:48-54`; 10 uses vs security's 2 |
| Shell/MCP writes | deny pre-call; disposable-copy runners | guard editors pre-call; exhaustive Stop-time diff from scope base | `crew_guards.py:812`, `scope_report.py:3-8` |
| Role content | preserve all 54 as references | delete 28 off-stack roles; 7 `stack-*` skills for the owner's stack | 0–4 uses; Addendum 3; git history keeps them |
| SessionStart | ≤12 lines always | ≤12 at startup, ≤3,000 chars on resume | `pm_brief.py:664-712` |
| Token counting | count tokens | chars at 3/token, 6,000 cap | no tokenizer dependency on Windows |
| Gardening queue | shared queue + lock | per-host queues, no lock | Obsidian Sync conflict copies; `claude-memories-vault/SKILL.md:18-20` |
| Serena | optional pilot | skip; LSP plugins | 0 calls in 310 transcripts while installed |
| Superpowers/brainstorm | (not addressed) | remove plugin; vendor ≤120-line skills | audit §2; `brainstorming/SKILL.md:206`, `writing-plans/SKILL.md:99` |
| Migration | 0.21–0.24 opt-in, 1.0 later; schema 8 | rebuild as 1.0 with one-time `/crew:migrate`; no compatibility shims | Addendum 5; `crew_upgrade.py:417` blocks are the migration source |
| Old guides | archive progress report, replace three families | same, plus Markdown sources under `docs/guides/crew/src/` | `TODO.md:3236` (no generator today) |

### Critical Files for Implementation
- /repos/personal/useful-claude-add-ons/plugin/crew/commands/review.md
- /repos/personal/useful-claude-add-ons/plugin/crew/hooks/scripts/scope_report.py
- /repos/personal/useful-claude-add-ons/plugin/crew/hooks/scripts/pm_brief.py
- /repos/personal/useful-claude-add-ons/plugin/crew/hooks/scripts/context-watch.sh
- /repos/personal/useful-claude-add-ons/plugin/crew/hooks/scripts/crew_guards.py

# Codex reviews Fable (and revises its own design)

**JUDGEMENT:** Rebuild crew 1.0; remove compatibility aliases and staged schema upgrades.  
**JUDGEMENT:** Require brainstorm → spec → plan → implement, including lightweight fixes.  
**JUDGEMENT:** Specialize around the owner’s seven language groups, AWS, and Azure.  
**JUDGEMENT:** Adopt Fable’s isolated researcher and ticket-directory layout.  
**JUDGEMENT:** Reuse superpowers through adapters, with one approval mechanism and review ledger.

The following replaces the affected decisions in [my original design](../../docs/review/04b-redesign-codex.md). Recommendations are **JUDGEMENT**; cited observations are **DERIVED**.

**Revised delta**

- **Clean rebuild.** Delete `/crew:pm`, compatibility wrappers, “legacy compatibility retained,” and the 0.21–0.24 transition sequence. Keep the name `crew`, but introduce `.crew/crew.json` schema 1 and `.work/tickets/<id>/` containing direction, spec, and plan artifacts. Review receipts remain runner-owned. Preserve tested verification, codemap, platform, and scope functions selectively; existing tests do not justify retaining their entire surrounding architecture. Addendum 5 explicitly removes compatibility as a constraint. [Brief:156](../../.work/redesign-brief.md:156)

- **One-time migration.** Replace sequential schema upgrades with a previewable, backed-up, atomic importer covering file tickets **and tracker caches**, codemaps, and metrics. Preserve identifiers, provenance, and original measurements; unavailable historical values remain UNKNOWN. Archive unsupported configuration rather than interpreting it at runtime. No aliases survive solely to support old commands.

- **First-class phases.** Add `/crew:brainstorm` and `/crew:spec`; redefine `/crew:plan`; use `/crew:implement` instead of `/crew:work`. Wrap version-pinned superpowers skills, adapting artifact paths, approval receipts, and final-review handoff. The lightweight path compresses all four phases into a short contract and plan; it skips none. Full treatment triggers on uncertain diagnosis, new behavior or interfaces, multiple subsystems, more than two files, or security/cloud/schema changes. Enter plan mode before implementation; scope expansion requires an amended contract and renewed approval.

- **Stack and roster.** Replace my indiscriminate preservation of deleted personas with seven focused skills: Terraform, .NET Core, AngularJS/Angular, Python, SQL, PowerShell, and Bash. Include all three SQL dialects and separate PowerShell 5.1/7 checks. Retain relevant AWS/Azure infrastructure and security knowledge; remove unrelated domain bundles. Add `researcher` as a fourth role: its separate web-tool allowlist provides concrete isolation. Rename `qa-reviewer` to `reviewer`. [researcher.md:23](../../plugin/crew/agents/researcher.md:23)

- **Cloud and delivery.** Add explicit AWS/Azure identity checks and approved Terraform-plan receipts to the existing runner design. Supply documentation-only MCP options first, then separately enabled account access with restricted credentials. Keep the small complete-review patch first; follow with the new lifecycle/ledger, scope/cloud controls, and stack integrations before the pilot. Adopt Fable’s 80-line `AGENTS.md`, 1,500-character SessionStart ceiling, and Markdown guide sources. Each guide must demonstrate both full and lightweight workflows on Windows and Linux.

**Remaining disagreements**

| Point | Fable’s claim or omission — DERIVED evidence | My recommendation — JUDGEMENT |
|---|---|---|
| **Superpowers and lightweight work** | [Fable:139](../../docs/review/04a-redesign-fable.md:139) replaces three skills and skips brainstorm/plan for fixes. Yet its approval guard requires a plan at line 42. Skipping phases contradicts [brief:139](../../.work/redesign-brief.md:139). | Wrap the installed skills; do not uninstall superpowers as part of this repository redesign. Define one review handoff so superpowers and crew cannot launch separate review loops. Lightweight means shorter artifacts and interaction. |
| **Scope contract and parser** | [Fable:136](../../docs/review/04a-redesign-fable.md:136) lets plan-file unions populate `Touch`. Its claimed reusable parser actually recognizes `- touch:` and flat ticket files, not the proposed heading/directory structure. [scope_report.py:34](../../plugin/crew/hooks/scripts/scope_report.py:34), [:64](../../plugin/crew/hooks/scripts/scope_report.py:64) | Validate plan paths against the approved spec; never silently expand it. Rewrite the contract parser. Remove blanket `.crew/` and `.work/` write exemptions, which include policy and approval state. Cover shell/MCP mutations, canonical paths, renames, and symlinks. |
| **Review completeness** | [Fable:49](../../docs/review/04a-redesign-fable.md:49) constructs a patch and manifest but leaves reviewer source live. Its prompt omits evidence, unknowns, and the plan. | Freeze the complete intended result, including binary/submodule handling; supply the full contract and receipts. Bind acceptance to hashes. Later edits invalidate acceptance. Verify actual model-family independence rather than treating provider configuration as proof. |
| **Two-round enforcement** | [Fable:52](../../docs/review/04a-redesign-fable.md:52) refuses a third invocation but blocks completion when `rounds > 2`; that predicate is unreachable if refusal works. | Atomically reserve attempts in the durable ledger. Gate completion on an accepted receipt, not counter overflow. Exhaustion requires an explicitly approved successor plan; a writable `replanned` flag cannot reset the budget. |
| **Cloud enforcement** | [Fable:128](../../docs/review/04a-redesign-fable.md:128) relies on command classification and cached context. The repository already documents repeated shell-parser bypasses and explicitly says shell guards miss MCP. [verify_record.py:178](../../plugin/crew/hooks/scripts/verify_record.py:178), [crew-cloud:30](../../plugin/crew/skills/crew-cloud/SKILL.md:30) | Use structured runner operations, effective account/subscription identity, pinned invocation context, and restricted credentials. Revalidate destructive operations immediately. Unknown identity cannot become unattended permission to proceed. |
| **Formatting and linting** | [Fable:126](../../docs/review/04a-redesign-fable.md:126) combines formatting with automatic lint fixes and a single SQL dialect setting. | Choose one formatter owner. Resolve project and dialect per path; keep mutations within approved scope. Make broader lint fixes explicit operations. Missing tools produce a bounded warning and unverified checks, never PASS. |
| **Stop behavior and defaults** | [Fable:122](../../docs/review/04a-redesign-fable.md:122) retains a blocking context nag, contradicting its “Stop cost = gate cost only” target at line 159. New hooks also have unexplained ON defaults. | Remove the nag; retain nonblocking checkpoints. All install-menu hooks start OFF, with explicit initialization choices. Stop reports completion failures only. |
| **Instruction checks and budgets** | [Fable:86](../../docs/review/04a-redesign-fable.md:86) treats the same command with different arguments as a contradiction; legitimate examples would fail while semantic contradictions escape. | Use typed policy identifiers, drift checks, and semantic review. Keep commands ≤60 lines, status ≤40, and generated rules ≤30 with source hashes. Those remain tighter than Fable’s limits. |
| **Memory delivery** | [Fable:95](../../docs/review/04a-redesign-fable.md:95) specifies codemap injection but no vault-retrieval path. Session-only deduplication lacks compaction handling; character ceilings do not establish token ceilings. | Route selected vault recall through the same context owner. Deduplicate by content and compaction epoch; enforce combined per-turn character **and token** budgets. Bound auto-memory and label stale evidence. |
| **Obsidian retirement** | [Fable:105](../../docs/review/04a-redesign-fable.md:105) calls both root setups superseded. Its cited README explicitly says `claude-obsidian-setup` serves a different third-party plugin. [README:206](../../plugin/obsidian-vault/README.md:206) | Withdraw that deletion. Retire vault-specific marketplace entries into portable profiles; retire `vault-automation` only after replacing its remaining functions and references. |
| **Obsidian operational completeness** | “Drain 95 on first run” at [Fable:103](../../docs/review/04a-redesign-fable.md:103) conflicts with the gardener’s five-session ceiling. The queue writer is explicitly missing; the gardener stages everything. [memory skill:319](../../skills/claude-memories-vault/SKILL.md:319), [gardener:55](../../plugin/obsidian-vault/agents/gardener.md:55) | Ship the portable queue and locking first; drain bounded batches on one designated host. Commit only owned files. Prove scheduled capture→distillation→recall. Make REST optional; existing initialization requires a manual REST-plugin prerequisite. |
| **Serena and language coverage** | [Fable:109](../../docs/review/04a-redesign-fable.md:109) uses zero Serena calls to favor native LSP despite also reporting zero native calls. TypeScript coverage alone does not establish Angular-template coverage; Angular provides a dedicated [language service](https://angular.dev/tools/language-service). | Keep the optional measured pilot, expanded across the owner’s stack. Probe coverage rather than infer it from plugin names. Keep Serena separately installed and pinned; its application and SolidLSP have [different licences](https://oraios.github.io/serena/01-about/060_license.html). |
| **Single registration** | [Fable:166](../../docs/review/04a-redesign-fable.md:166) says one registration is impossible. Current Claude documentation supports direct executable hooks through `command` plus `args`, without a shell. [Official reference](https://code.claude.com/docs/en/hooks#exec-form-and-shell-form) | Generate one effective registration per handler using a verified interpreter; retain matched wrappers where needed. Prove exactly one invocation on both operating systems. |
| **Codex parity** | [Fable:143](../../docs/review/04a-redesign-fable.md:143) omits verification/completion from its generated hook list. Codex documents tool-path exceptions and no new PreToolUse check for `write_stdin`. [Official hooks documentation](https://learn.chatgpt.com/docs/hooks) | Test effective event delivery and complete runner/CI enforcement, including completion and promotion. Unsupported paths require explicit reduced operation; configuration alone does not establish parity. |
| **Migration coverage** | [Fable:147](../../docs/review/04a-redesign-fable.md:147) migrates file tickets but omits tracker caches. Existing code identifies caches as this repository’s active ticket location. [scope_report.py:55](../../plugin/crew/hooks/scripts/scope_report.py:55) | Import both locations, preserve tracker identity and provenance, and report collisions. Rebuild indexes from imported records; preserve original metrics without inventing missing values. |
| **Validation and “Ahead”** | [Fable:151](../../docs/review/04a-redesign-fable.md:151) permits 10% of tickets beyond the hard cap. Its four-role roster cannot satisfy “fewer than three” at line 158. Reported usage numbers are rankings, not dispatch tallies. [review README:60](../../docs/review/README.md:60) | Require 100% budget enforcement. Use prospective matched tickets, active time/cost, confirmed defects, and subsequent escapes. Benchmark named alternatives; file counts, internal tests, and removing native-equivalent overhead do not establish Ahead. |

No files were modified.

**Open questions for the owner**

- Superpowers: **version-pinned wrappers (recommended)**; maintained vendored replacements.
- .NET Framework 4.8: **exclude unless an active repository needs it (recommended)**; provide a separate optional reference.