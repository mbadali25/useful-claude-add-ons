# Crew revamp plan (fresh start from main, crew 1.3.167) — revision 3

> ## Approval record
>
> **Approved by the owner, by typing in the Claude Code session, on 2026-11-18.** His words: "Approve as recommended, and also let's get started." Revision 3 of this plan is approved with every owner decision at the value the plan recommends.
>
> **Honesty note.** This record is transcribed by an agent from the session. It is not a signed attestation, and nothing in the repo can prove the owner typed those words. It is the written trace of an approval given in conversation (the very mechanism the plan proposes to harden in section 4.2 and 4.13).
>
> Decisions approved (section 8.2):
>
> | # | Decision approved |
> |---|---|
> | O1 | Guards are off until `/crew:init`, whose default answer is on. The CLAUDE.md sentence about blocking hooks defaulting off is reworded to match (ticket R-3B). |
> | O2 | `guided` mode for a user who runs `/crew:init` fresh; `directive` only when the machine's owner opts in. |
> | O3 | The plan's readings stand: Fable 5.2 counts as Opus 5.5 or higher; the serious list in section 4.13; a production write still needs a plan even with a properly scoped account. |
> | O4 | The production write and admin credentials are kept by a broker under its own OS account. |
> | O5 | The admin accounts are inventoried by ticket (R-A9 and the tickets it depends on), not assumed. |
> | O6 | Approval of a plan of record is attested by a presence key, plus the owner's forge review where a pipeline is the executor. |
>
> Plan revision: 3 (102 tickets, 14 phases). Cross-review: GPT 6.2 Astra, two rounds, logged in section 10 (revision 2, 30 findings) and section 11 (revision 3, 29 findings). Companion memory note: crew plugin vision, 2026-11-18. Approval page: artifact FJN2Ub27v38iwaFT9FngG8, published under a previous Claude login and no longer reachable from the current account.
>
> The sentence below, "Nothing here starts until the owner approves it", was true when written. It is kept as written; the approval above lifts it. The ticket queue made from section 6 is `pending-tickets.md` and `docs/tickets/pending/`.

---


Planner: Fable 5.2 (`claude-fable-5-2`). Cross-reviewer: GPT 6.2 Astra through the local Codex CLI (`codex-cli 0.167.0`, `model: gpt-6.2-astra`, read-only sandbox). Its verdict on revision 1 was "reject as written"; revision 2 answered all 30 findings (section 10). Revision 3 applies the owner's feedback on revision 2; Astra reviewed the revision-3 changes (section 11).
Grounding: fresh LF clone of origin/main at `5558cac` (PR #791), `plugin/crew/.claude-plugin/plugin.json` version `1.3.167`. Paths are repo-relative.
Labels: **[V]** verified by me (path:line or command). **[A]** reported by Astra with a path:line that I did not re-read. **[I]** inferred. **[?]** could not tell.

Nothing here starts until the owner approves it. This document changes no repo file, ticket, PR or Jira item.

---

## 0. What changed from revision 2, per the owner's feedback

### 0.1 How I read the feedback (correct me where this is wrong)

0. (Added later the same day.) **A configuration guide** for crew's `config.json`, with a blank template, shipped with the plugin so models can configure crew without asking the developer. Section 4.15 and Phase 13.
1. **Two operating modes.** `guided` holds a person's hand the whole way. `directive` takes a directive, plans and goals, then plans, decides, answers its own questions and keeps going. One machine-level key; a repo, ticket or run may only move toward `guided`.
2. **The system may decide.** Routine decisions are made by a model of Opus 5.5 or higher. I read "or higher" as including Fable 5.2. Haiku and Sonnet never decide. Codex and Kimi may advise and never decide.
3. **Money or anything serious** is fully automatable *after* a plan that a human and the Opus 5.5+ model built together (scope, research, plan), with the human's approval of that plan on record. Execution is then unattended.
4. **Production** is fully automatable under an approved plan. The plan must contain the scope-out and the research, and it covers permission changes and creating temporary accounts.
5. **Service accounts.** Each application and each automation process has its own read account and its own write account. A properly scoped account may always be used. Read-level access to production is always allowed, and read access is allowed in every environment.
6. **Full admin accounts** are authorised only when a need exists (the example: no suitable account exists and one must be made). The admin credential is used to create the scoped accounts or set their permissions, then work returns to the scoped accounts.

Two readings I had to choose, stated so they can be overruled:
- "Properly scoped accounts are always authorized to use" does **not** by itself authorise a production *write* with no plan. The same message says production needs an approved plan. So: the account needs no extra per-use approval and no admin, and a production write still has to match an approved plan.
- "Anything serious" has no definition in the feedback. Section 4.13 proposes a closed list; anything the classifier cannot place counts as serious.

### 0.2 Where revision 3 intentionally changes a revision-2 default

| Revision 2 | Revision 3 | Why |
|---|---|---|
| D2: `yes` then `confirm` for every production, destructive or bypass ask | `yes` + repeat-back + `confirm` only for approving or amending a plan of record and for the one-way list. A routine ask is answered by one plain reply (`guided`) or by the decider (`directive`) | point 2 |
| D3: only actions listed in a plan the owner typed approval for, matched field for field, each used once | Serious work: still a human-approved plan, but an action may be an **envelope** (explicit bounds) whose concrete values the decider binds at run time; standing plans may be reused inside an expiry and a use cap. Non-serious dev and QA work: the decider may approve the plan (`approved_via: decider`) | points 2, 3, 4 |
| D4: owner picks grant durations | One machine ceiling of 24 h in both modes; the suggested duration is 8 h in `directive` and 1 h in `guided` | point 2 |
| D5: the agent session never holds a production credential; native Windows refused | A session may hold verified **scoped** read credentials for any tier and write credentials for dev and QA. A production write is carried out with the application's write account by an executor outside the session (the pipeline, or a local broker running under its own OS account), one checked operation at a time. Native Windows is allowed. Changed after cross-review: the first draft of revision 3 handed the session an hour-long write credential | point 5 |
| D6: a production change with no provable backup is human only | It may run unattended when the human-approved plan lists that exact action as irreversible, with a cap; exact binding only, no envelope | point 3 |
| D7, D8 | Applied as recommended (machine-owned tiers and hours; worker-in-container). No longer asked | point 2 |
| Temporary = provider-issued expiry only | Still preferred. Where the provider cannot expire a temporary **account**, its credential stays in the broker, which refuses use after the deadline; only inside a human-approved plan | point 4 |
| Admin credentials: not addressed; unknown identity asks or is denied | Admin use is allowed on a need record checked against provider evidence, performed by the broker one exact operation at a time, limited to identity work on the named service accounts, audited at close | point 6 |
| `cli` and `autopilot` plan approvals never unlock a privileged action | Unchanged for serious work. For non-serious dev and QA work a `decider` approval is accepted | point 2 |

### 0.3 What did not change

The Never lane; the deny-first policy table; machine-owned tiers; protected policy (any widening needs the owner); approvals minted only in the prompt hook; the backup, scope and window checks before a production change; secrets redaction; the sandbox rules; the harness-alone rule; inert-first. Section 5 lists every invariant with its mechanism and marks the ones whose mechanism moved.

---

## 1. Executive summary

Crew's machinery is mostly right. Its defaults and its approval route are wrong for how the owner works, and a few things the owner asked for cannot be done safely by a command-reading hook alone.

1. **Reviewer naming.** Config keys are already per provider. "Codex" is hard-coded in the standalone probe, in labels and in prose. Fix: a provider registry and neutral labels.
2. **Approval is a chore** because an `ask` means "create a marker file" or "type a slash command with an id". Fix: two modes. In `guided` the person's plain reply answers; in `directive` an Opus 5.5+ decider answers routine questions itself and records why. The owner is asked only to approve a plan of record and for a short one-way list.
3. **Guards are rigid** because the only armed profile blocks six rules outright and nothing reads the approved plan. Fix: one decision table with four lanes, environment tiers, and "inside an approved plan = allowed".
4. **Loosening needs a real boundary, not a better regex.** A hook that reads command lines is a tripwire. Revision 2 put the boundary at "the agent holds no production credential". The owner's feedback moves it: the boundary is now **the provider-enforced scope of a service account**. Each application and automation process gets a read account and a write account that can touch only its own resources; a production write is carried out with that account by an executor outside the session (the pipeline, or a local broker under its own OS account), one checked operation at a time. Admin credentials are used only on a script-checked need, by the same broker. The owner's approval of a plan carries an attestation the session cannot produce.
5. **Files everywhere, host damaged twice.** One machine-owned path resolver, a deletion helper that cannot cross out of its root, one sandbox launcher, and a reproduction attempt in a disposable VM. The cause of the `/bin/bash` damage is not known.
6. **Money, serious work and production** run unattended once a human and the Opus 5.5+ model have built a plan of record together and the human's approval is recorded. Dev and QA are free.
7. **Orchestrator and the stages** map onto existing commands; triage, status maps, ticket updates as you go, and clean-up are the new parts.
   Also in this group, **nobody can tell how to configure crew.** A reference table ships with the plugin; no worked example, procedure or annotated blank template does, and nothing at session start points a model at it. Fix: a generated configuration guide inside `plugin/crew`, written for the owner and for AI models (4.15).
8. **Checks are sliced**: fast every round, heavy once at Gate, without dropping the cross-cutting rules.

102 tickets, all S or M, in 14 phases (0 to 13). 15 touch the review/gate harness and land alone; block-capable features also need a harness-only companion PR for their sabotage file. Every new *allow* ships inert first and is switched on by its own last ticket. Ticket ids from revision 2 are kept, so an id's first digit no longer names its phase.

---

## 2. What the code does today

### 2.1 Reviewer naming
- **[V]** `QA_PROVIDERS = ("claude", "codex", "copilot", "kimi")` — `plugin/crew/hooks/scripts/crew_state.py:1313`; default order `["codex", "kimi", "copilot", "claude"]` — `crew_state.py:992`.
- **[V]** Keys are per provider: `qa.codex.model`, `qa.codex.reasoningEffort`, `qa.copilot.model`, `qa.kimi.model`, `qa.roles`, `qa.order`, `qa.provider`, `qa.fallback` — `crew_keys.py:110-130`. A `secondOpinion.provider|mode|model` block exists — `crew_keys.py:151-156`.
- **[V]** The standalone `--probe` is Codex only — `review_run.py:2938-2939`; `--resolve-run` is written around the Codex probe — `review_run.py:2535-2585`.
- **[A]** Kimi already probes before its own launch and selection already walks eligible providers in order — `review_run.py:1416-1459, 2425-2428, 2519-2532`. So the gap is the standalone probe and the wording, not the absence of a Kimi probe.
- **[V]** Codex-named labels: `CODEX_LIMIT = "same-family: codex limit"`, `PROBE_LIMITED_NOTE = "codex-probe=5"` — `review_metrics.py:85,88`; `AUTO_PROVIDERS = ("codex", "kimi")` — `review_ledger.py:220`.
- **[V]** Prose: `commands/review.md:2,22,25,46`; `agents/reviewer.md:4,7,8`; wave lane prompt "crew:reviewer while Codex is out" — `crew_wave.py:1148`.
- **[V]** Review severities are `("BLOCK", "FIX", "NIT")` — `review_verdict.py:88`. Artifact 2 wants crit / high / medium / low / nit.
- **[I]** The "configuration issues when we sub Kimi" come from the Codex-shaped probe and fallback path. I did not reproduce a failing Kimi-first run.

### 2.2 Guards that block deploys, GitHub commands and cloud changes
- **[V]** Per-rule default `block` — `crew_guards.py:94`. Switch `guards.cloudGuard` default `off` — `crew_guards.py:190,228`.
- **[V]** `standard` blocks six rules with no approval route: `_ALWAYS_BLOCK = ("terraformApply", "forcePush", "mergeGate", "cloudDestructive", "sqlDestructive", "deployWorkflow")` — `crew_guards.py:250-258`.
- **[V]** `gh workflow run` / `gh api .../dispatches` are `guards.deployWorkflow`; `gh pr merge --admin` is `guards.adminMerge` — `cloud_guard.py:22-23`. A dispatch is judged only for workflows listed in the repo-only `environments.workflows` map, and `allow` covers nonProd only — `crew_dispatch.py:88-94`.
- **[A]** Production dispatch already has a dual-layer opt-in and live markers are accepted before some environment checks — `crew_dispatch.py:1149-1155, 1184-1191`; `cloud_guard.py:3114-3142`.
- **[V]** An `ask` is answered by a file the operator creates, good for 15 minutes; unattended, `ask` becomes `deny` — `cloud_guard.py:3258-3264`; `crew_guards.py:439`.
- **[V]** No IAM rule exists: `grep -rniE "\biam\b|attach-role-policy|put-role-policy" plugin/crew/hooks/scripts/*.py` prints nothing. AWS destructive is the prefixes `delete-`, `terminate-`, `purge-` — `cloud_guard.py:1452`.
- **[V]** What can stop an IAM write in crew is the identity rule: an identity crew cannot name is asked attended and denied unattended, for every call once any `cloud.*` pin is set — `cloud_guard.py:79-92`.
- **[?]** Which layer refused the owner's IAM changes (that rule, a production guard, or Claude Code's own permission layer). R-03 captures one.
- **[V]** The guard states its own limit: it cannot see a command named through a variable, a script file, runtime-built SQL, or anything an MCP server does. "Native permissions and restricted credentials are the boundary; this is a tripwire in front of them" — `cloud_guard.py:99-111`.

### 2.3 Approval mechanisms that exist
- **[V]** A plan approval records how it was made: `via` is `cli`, `user-prompt` or `autopilot` — `crew_ticket.py:1007-1037`. So "the plan is approved" does not by itself mean the owner approved it.
- **[V]** `/crew:approve` through the `UserPromptSubmit` hook is hash-bound to spec.md and plan.md; the plain-text form needs a second prompt; "yes" is refused on purpose — `approval_hook.py:1-49`.
- **[V]** Double confirm: propose, two distinct owner prompts within 15 minutes, digest-bound, `stale` if the file changed; only `humanOnly.*` and `guards.git.allow` — `crew_confirm_config.py:1-45, 90-102, 149-204`.
- **[V]** One-run receipts: request, owner-typed `/crew:allow-run <id>`, one-use receipt bound to command sha256, class, session, worktree, 900 s; one class, `verify-trust`; default off — `crew_runapproval.py:1-31, 67-68`.
- **[V]** Stated residual: the store is a file of the same OS user; a session that sets out to forge a receipt, or resumes its own session id in a child process, is not stopped — `crew_runapproval.py:36-55`.
- **[A]** Session matching happens in `check`, and `spend` takes no session argument — `crew_runapproval.py:573-597, 638-645`.
- **Can double-confirm generalize to guard bypass?** The state machine can. The run-approval module is the closer base because it is per command and single use. Both need the bindings in 4.2 added, and neither is a boundary against a same-user process.

### 2.4 Worktrees, scratch, Docker
- **[V]** Standard worktree root exists: `~/.claude/crew/worktrees/<repo>-<digest>/<name>`; `worktrees.root` may be set in the repo or machine layer and **the repo wins** — `crew_worktrees.py:10-13`. Opt-in through a `WorktreeCreate` hook the owner registers — `crew_worktrees.py:15-23`.
- **[V]** `lane-init` already admits the standard root as well as `<main>/.claude/worktrees` — `crew_wave.py:965-989`. (Revision 1 said the two disagreed; that was wrong.)
- **[V]** Review uses a caller-supplied `--scratch`, not a tree of its own — `review_run.py`.
- **[V]** 12 crew Python scripts and 7 shell files make their own temp dirs; no shared resolver.
- **[V]** Docker launchers: two argv builders in `scripts/crew-outcome-eval.py` (`:456` grading, `:1028` arm). The arm builder uses `--rm`, `--network none`, `--user uid:gid` and three mounts under the run directory.
- **[V]** Host-path writes in the repo: `scripts/cloud-env-setup.sh:193,231` (`ln -sf` into `/usr/local/bin`); a test symlinks every `/usr/bin` entry into a temp dir — `plugin/crew/tests/test_verify_gate_trust.py:544-546`.
- **[?]** What damaged `/bin/bash` and `/usr/bin/bash`. No command writing there was found by reading. Nothing in crew protects those paths today.

### 2.5 Waves, tickets, autopilot
- **[V]** `/crew:autopilot wave` commands and its never-list (a lane never accepts a review, approves a plan or merges) — `crew_wave.py:1-48`.
- **[V]** Trackers `("files", "obsidian", "jira", "sdp")`; statuses `direction, ready, spec, planned, in-progress, review, done` plus `needs-owner`, `cancelled`, `superseded`; Jira and SDP pushed only at `in-progress` and `done` — `crew_tracker.py:94, 118-120, 162-163`.
- **[V]** Autopilot policies `human | self | risk` — `crew_autopilot.py:2171`; deploy `none | nonprod | all` — `crew_autopilot.py:282`.
- **[V]** Sleep overrides may only be stricter than the day values — `crew_sleep.py:1-22`.
- **[V]** Handoffs go to `.work/HANDOFF.md`, and `.work/` is ignored, so they cannot be committed. `docs/handoff/` is tracked.
- **[V]** The sealed launcher hands a session temporary credentials for one owner-named identity, denies every credential store, starts no MCP server, and answers `unknown` on native Windows — `crew_unattended.py:1-57`.

### 2.6 CI and smoke
- **[V]** `.crew/verify.json`: 103 rules with `paths`, `run`, `seconds`, `reach`; `seconds` total 11,950; largest 755; a `preReview` block exists (measured with `python` over the file).
- **[A]** Some `seconds` are lower bounds or platform-specific — `.crew/verify.json:51-88`.
- **[V]** `scripts/gate-runner.py` (cheap, heavy A/B, solo; PASS / FAIL / SKIP / COULD-NOT-TELL) and `scripts/ci-select.py` (answers "everything" when it cannot tell).
- **[V]** 11 workflows; 317 `test_*.py` and 41 `sabotage*.py` under `plugin/crew/tests`.
- **[I]** "playtest" is the Playwright path (`/crew:webtest`, `webtest_guard.py`, skill `web-testing-playwright`); "doc test / doc checks" are `crew_docs_check.py`, `scripts/check-crew-docs.py` and the doc-builder skills. No file is named playtest.

### 2.7 Constraints
- **[V]** `HARNESS` (`scripts/check-tooling-pr.py:58-101`) includes `review_*.py`, `verify-gate.sh|ps1`, `verify_trust.py`, `approval_hook.py`, `crew_runapproval.py`, `scope_guard.py`, `hooks.json`, `crew_hook.py`, `commands/review.md`, `agents/reviewer.md`, `tests/sabotage*.py`, `tests/golden/**`. The check reads paths, not ticket labels. `cloud_guard.py`, `crew_guards.py`, `crew_worktrees.py`, `crew_wave.py`, `crew_tracker.py` are not harness.
- **[V]** `plugin/crew/CONFIG.md` has 599 physical lines (`(Get-Content CONFIG.md).Count`); the cap is under 600. Revision 1 said 527, which counted non-blank lines. New keys cannot be documented there without removing lines; they go in the built guide.
- **[V]** CLAUDE.md: a blocking hook defaults OFF and needs must-block / must-allow cases, sabotage-tested. Artifact 3: "Every guard is on by default." Decision D1.
- **[V]** Crew itself uses `git push --no-verify` and `commit-tree --no-gpg-sign` for its coordination channel — `crew_coord.py:674,722`.

### 2.8 Accounts, admin and model identity today (added in revision 3)
- **[V]** The machine config already names cloud identities for unattended runs: `unattendedCloud.aws.readOnly.profile|identity|region` and `unattendedCloud.aws.nonProd` — `crew_keys.py:363-374`. The launcher reads only `readOnly` and `nonProd.<environment>` — `crew_unattended.py:452,464`. There is no production write entry.
- **[V]** The launcher refuses a long-lived `:user/` identity and requires the STS ARN to start with the named prefix — `crew_unattended.py:408-424`. So "roles, not keys" is already crew's rule for unattended identities.
- **[V]** No approval receipt carries a model identity reported by the runtime: `Select-String` over `plugin/crew/hooks/scripts/*.py` for `payload.get("model"`, `modelUsage` and a `["model"] =` assignment finds no hit. Plan approval receipts carry `approved_by` and `approved_via` — `crew_ticket.py:34-44, 1025, 1061`. (`--model` is parsed in several scripts, including `crew_state.py` and `review_ledger.py`; none of those attests which model answered. Narrowed after Astra's finding 29.)
- **[V]** `crew_ticket.py` is a HARNESS path, with `approval_hook.py`, `crew_runapproval.py`, `hooks.json`, `crew_hook.py` and `tests/sabotage*.py` — `scripts/check-tooling-pr.py:58-101`. So a new `approved_via` value is a harness change.
- **[V]** No service-account registry, naming convention or admin-use record exists: `grep -niE "serviceAccount|service account"` over `crew_keys.py` and `crew_unattended.py` prints nothing.
- **[?]** What a headless Claude Code run reports about the model that actually answered, and whether a fallback to another model is visible in that report. R-06 measures it.
- **[I]** The exact model id for Opus 5.5 (written `claude-opus-5-5` below). This session's own id is `claude-fable-5-2` **[V]** (stated by the runtime).
- **[I]** The AWS mechanics used in 4.14 (session policies on `AssumeRole`, `SourceIdentity`, permissions boundaries, `aws:CurrentTime` conditions, CloudTrail lookup by source identity) are from my knowledge of AWS, not re-read against AWS documentation in this pass. R-A8 verifies each before it is relied on.

---

## 3. What to keep

Keep: the family interlock; the hash-bound plan approval and its `via` field; the verify trust store with per-repo hashes as the default; the machine/repo ratchet; "could not tell" as its own value; the sealed launcher; the scope guard's refusal of approval-state writes; `crew_backup.py`; `ci-select.py`; the wave never-list; every existing must-block and sabotage suite.

Change: profiles and defaults; how an `ask` is answered and by whom; reviewer naming; where files go; when the tracker is updated; what sleep is for; which credentials a session holds. The existing `unattendedCloud` identities become rows of the account registry.

Drop: the operator-created `.approved-guard-*` marker. It stays readable for the rules it serves today for one release, and is never honoured for a new approval class.

---

## 4. Design

### 4.0 Three layers, stated once

1. **Tripwire** (hooks that read commands and writes). Cheap, catches drift and accidents, can be walked past by a script file, an MCP server or a same-user process. Good enough for dev and QA.
2. **Records** bound to one operation: a person's typed approval (minted in the prompt hook), or a decider decision (4.12). Good enough for routine asks.
3. **Boundary**, changed in revision 3. Two parts. (a) What the provider enforces on the credential: a scoped service account can reach only its application's resources (4.14). (b) Who can touch the credential and who can vouch for the owner: production write and admin credentials are held by an **executor outside the session's OS identity** (the pipeline, or the local broker of 4.14), which carries out one checked operation at a time; and a plan-of-record approval carries an **attestation** the session cannot produce (4.13). Serious work needs layer 3 and an attested, human-approved plan of record.

Every loosening below says which layer carries it. Sections 4.11 to 4.14 are new in revision 3 and are referenced from the earlier sections.

### 4.1 Reviewer-family neutrality

- **Provider registry** (`review_providers.py`): one row per provider with family rule, executable, command builder, probe, event parser, limit detector, events file. `review_run.py`'s `provider == "codex"` branches move into the Codex row.
- **One probe per attempt.** The standalone `--probe` accepts any launched provider, and a provider that probes inside its own launch (Kimi) is not probed twice. A provider limit confers no review authority: the family interlock is asked separately, and a same-family review happens only under the existing explicit exception.
- **Neutral labels**: `same-family: <provider> limit`, note `probe=<provider>:<exit>`; readers keep accepting the old spellings.
- **Five severities** (crit / high / medium / low / nit) in the reviewer prompt and `review_verdict.py`; BLOCK / FIX / NIT still parse (BLOCK = crit, FIX = medium, NIT = nit) so old ledgers and goldens replay. Blocking: crit, high, medium block; low blocks when the ticket is flagged money; nit never.
- **Prose**: "the QA reviewer (`<provider>`, `<model>`)" everywhere; provider notes under per-provider headings; a string check keeps it so.
- **Config**: no key rename. `reasoningEffort` becomes valid under any provider block, with a validation ticket that says what each CLI does with it. The Codex default model pin stays and is described as the default for provider `codex`.
- **Tests**, each independent: probe count per attempt; pinning; eligibility with Kimi first; limit then fallback to a *different* family; the explicit same-family exception.

### 4.2 Approval by conversation (layer 2)

**Flow.**
1. A guard refuses and records a **request**. Fields: request id; class; the parsed operation as structured fields (never raw command text for display); sha256 of the exact command; working directory; git ref and HEAD sha; cloud account and identity as resolved by the guard; the resolved executable path; digests of any file the command reads as input (a saved plan, a SQL file, a script); session id; worktree; created and expiry times.
2. The agent asks the owner in plain language.
3. The owner replies with an approval word as the **whole prompt**: exactly one of `yes`, `approve`, `approved`, `go ahead`, `do it` (case-insensitive, surrounding whitespace only). Anything after the word makes it not an approval, so a qualified answer ("yes but only staging") is never read as a yes.
4. The hook freezes the set of live requests for this session and worktree against this prompt's id, and blocks the prompt with a repeat-back built from the structured fields: guard, operation, target, environment, account, what could go wrong. Control characters are escaped; values that match a secret shape are replaced by their name. With several requests it shows them lettered.
5. The owner replies `confirm` (or `confirm b`) as a whole prompt, in a different prompt, within 5 minutes. The hook resolves the letter against the frozen set, never against the current list, claims the request atomically and mints a one-use receipt that expires in 15 minutes.
6. The agent re-runs. The guard spends the receipt only if the command sha, working directory, HEAD sha, identity, executable and input digests all still match and the session matches at the spend. A mismatch spends nothing and says which field moved.

**Why a hostile file, tool output or agent cannot approve.** Approvals are created only inside the `UserPromptSubmit` handler from the payload's prompt, session id and prompt id. `yes` mints nothing; it only triggers a repeat-back the hook wrote from the guard's record. A notification, ticket comment or agent message carries no authority.

**Which actions use it (revision 3).** The two-step form (`yes`, repeat-back, `confirm`) is kept for exactly two things: approving or amending a plan of record (4.13), and the one-way list (guard bypass, guard or policy widening, switching the machine to `directive`, declaring an emergency). A serious action that is in no approved plan is **not** on that list: it is `needs-plan`, and no receipt of any kind, including a genuine one-way receipt, authorises it (a spend test holds that). A **routine** ask (conditional lane, non-serious, dev or QA) is answered in one step: in `guided` by the person's whole-prompt reply, which the same hook mints as a `routine` record with the same bindings; in `directive` by the decider. The one-step reply is bound to one request: the hook records which request's question was shown before this prompt, a bare `yes` counts only when exactly one such request is pending, and otherwise the reply must carry the request's letter from the frozen set. A request that arrived after the question was shown is never answered by that reply. A routine record can never be spent on a serious class; the class is fixed by the guard when the request is recorded, not by the answer. Never-lane actions record no request. Dev and QA Free actions never ask.

**Unattended.** A routine request goes to the decider in either mode when nobody is there (in `guided` it waits for the person unless they said "you decide" for that ticket). For a one-way or plan-of-record request: the request is recorded, the owner is notified, the ticket goes to `needs-owner`, and the lane moves on. The request (not a receipt) lives up to 8 hours. When the owner returns, `/crew:status` lists waiting requests; the owner answers in the session that resumes that worktree; the request is re-validated against current state before the repeat-back; the receipt is still 15 minutes. A request whose session is gone is re-issued in the resuming session rather than transferred. Requests can be cancelled.

**Must be measured before building (R-21).** That the current Claude Code client shows the owner the text of a blocked prompt's hook output, and that a plain reply reaches the hook unchanged. If the repeat-back is not visible, the design falls back to the agent relaying it plus a typed short code.

**Limit.** A same-user process can write the store or resume the session. Layer 2 does not fix that, which is why unattended production uses layer 3.

**Verify trust.** Per-repo hash approval stays the default. The chore is removed by letting `approve` be answered in conversation (R-22 gives it the same flow). A standing owner allowance stays a separate, explicit machine decision with a `--under <dir>` boundary; `/crew:init` does not offer it by default, because `verify_trust.py:26-36` documents that a forged local git config passes it on first sight.

### 4.3 One decision table, four lanes

`crew_policy.py` (new) holds one deny-first table. Inputs: operation, tier (dev / qa / prod / unknown), seriousness class (4.13), provenance (plan of record, standing plan, decider-approved plan, record, none), the account in use and its verification state (4.14), presence (attended / unattended), emergency. Output: allow, ask-routine, ask-owner, needs-plan, deny, plus the reason. **The operating mode is not an input.** Mode only decides who answers an `ask-routine` (4.11), so no mode can turn a deny into an allow. Order of evaluation, first match wins:

1. Never lane → deny.
2. Any machine-layer `block`, identity mismatch, unreadable input, or an account that is not the one the tier map names → deny (unattended) or ask-owner (attended).
3. Tier unknown, conflicting or unlisted → never unattended; the decider may not classify a target as dev or QA.
4. Admin operation requested with no open need, or outside the open need's exact operations → deny. An open need is a prerequisite, never an allow: evaluation continues.
5. Serious class → needs an attested, human-approved plan of record that covers it (exact or envelope), and for production the checks in 4.5. No plan: needs-plan, which starts the 4.13 flow; it is never answered by the decider or by any receipt.
6. Read with a verified read account, any tier → allow.
7. Destructive, non-serious (the ticket's own dev or QA data and files) → backup rule, then allow.
8. Conditional → its stated condition; if the condition cannot be shown, ask-routine.
9. Free.

| Lane | Operations (examples) | Condition, and where it is decided |
|---|---|---|
| Free | fetch, pull, rebase own branch, branch, worktree, commit, push own branch, open/update a PR; start a dev or QA deploy or fast check; read files, logs, plans, tickets; comment and attach evidence | none. Credential stores stay denied to reads (`crew_unattended.py:12-16`); "read any file" does not include them |
| Free | SQL reads | by connecting with a read-only database identity. The first-word classifier (`crew_guards.py:1014`) stays a tripwire only; it cannot prove a called function has no side effects |
| Conditional | force-push own branch | `--force-with-lease` pinned to the checked sha; branch is the lane's own; protection status known |
| Conditional | start Implement | approved spec on the ticket (existing) |
| Conditional | merge a PR | review clean and gate PASS for the same head sha; approver is not the author family |
| Conditional | land in next tier | prior tier landed; its smoke PASS |
| Conditional | terraform apply | nonProd: allow and log. Prod: 4.5 |
| Conditional | grant a permission | 4.4 |
| Conditional | remove a worktree | results published and verified |
| Conditional | change ticket status | status is on the tracker's map |
| Plan of record (new) | any serious class (4.13): money; a production write; a permanent permission change; creating an account; admin use in production; destroying data the ticket does not own; an irreversible or outside-system effect; a change with no provable backup | runs unattended when a human-approved plan of record covers it and the 4.5 checks pass; otherwise needs-plan |
| Human only (one-way list) | skip a gate; widen guard or policy config; switch the machine to `directive`; declare an emergency; amend a plan of record; push to a protected branch or admin-merge outside a plan; hand-edit terraform state; delete another's branch or worktree; a second workflow restart | `yes`, repeat-back, `confirm`; recorded on the ticket. The decider never answers these |
| Never | skip hooks or signing (`--no-verify`, `--no-gpg-sign`) from a model-run command; approve own spec; review own code; grant itself an exception; write a secret in plain text; change guard config directly; invent a status | deny, no request. Crew's own coordination push (`crew_coord.py`) runs inside crew's process, not as a model command, and is unaffected; a test holds that |

"Bypass a guard" is Human only when a person approves it and Never when the agent does it itself. An exception exists only as an owner-minted record.

**Tiers are machine-owned.** Which workspace, workflow, database or account is dev, QA or prod lives in the machine config (`tiers`), widened only by owner confirmation. A repo file may mark a target *more* restricted, never less. A target the map does not name is unknown.

**Profiles.** New profile `balanced` implements the table; `off`, `standard`, `strict` are unchanged.

**On by default (D1).** Recommended: installing arms nothing; `/crew:init` asks once and its default answer is `balanced`; turning a guard off afterwards is an owner-confirmed widening; every block-capable rule keeps its must-block / must-allow and sabotage suite. One sentence in CLAUDE.md changes.

**Protected policy.** Every key that can widen what an agent may do is protected as a set: `guards`, `approvals`, `humanOnly`, `environments`, `production`, `tiers`, `cloud`, `unattendedCloud`, `worktrees.root`, `autopilot.sleep`, `scope`, and new in revision 3 `mode`, `decider`, `serious`, `accounts`, `applications`, `admin`. The check compares the *effective policy before and after* a write, so deletion, whole-file replacement and a write through a link are all caught; any widening needs the owner's confirmation; narrowing is free.

**Secrets.** The claim is narrowed: a shape scan is a tripwire, not proof that no secret is exposed. What is scripted: redaction of secret-shaped values before anything is written to a receipt, log, tracker post or committed evidence; refusal of a command whose text carries a secret shape; the SSM pattern from artifact 3 (ship a script that fetches the secret on the host) as a template.

### 4.4 Planned = approved; temporary grants

**What counts as approved (revision 3).**
- *Serious work*: only a plan of record whose receipt says `approved_via: user-prompt`, whose digest is current, which has not expired, and, to run unattended, whose approval is attested (4.13). A `cli`, `autopilot` or `decider` approval never unlocks a serious action. A test holds each of the three as a mandatory refusal.
- *Non-serious work in dev and QA*: a plan approved by the decider (`approved_via: decider`, with the model id, 4.12) is accepted in `directive` mode. In `guided` the person approves it in one reply.

**Exact or envelope.** An action in a plan is either *exact* (every field below bound, as in revision 2) or an *envelope*: the same closed schema with explicit bounds in place of values that cannot be known when the plan is approved. Envelope fields are defined per kind, and an envelope is accepted only where the executor can establish every bound from the real artifact:
- `workflow-dispatch`: the workflow file by digest; every input bound to an enumerated list of allowed values (a free-text input makes the action exact-only); every action and reusable workflow it calls pinned by sha (an unpinned dependency makes it ineligible); a ref rule (`default branch head that passed Gate`).
- `terraform-apply`: workspace and backend; resource addresses inside the application's prefix; per address the allowed action (`create`, `update`, never `delete` or replace unless listed) **and the attribute paths that may change**, read from the saved plan's JSON; a maximum count. A change to an attribute not listed, or one the plan JSON marks unknown or sensitive, is outside the envelope. Cost is a bound only where a cost estimate is produced from that same plan; otherwise the action is exact-only.
- No other kind may be an envelope.
A wildcard that crosses the application prefix is rejected by the validator. At run time the decider binds the concrete values, the binding is recorded, and a script checks the bound action against the envelope using the artifact itself (the plan JSON, the workflow file at that sha); outside it the run stops with `needs-owner`. **Exact only, never an envelope:** money, permission grants, account creation, admin operations, anything irreversible, anything with no provable backup.

**Typed operations (added after cross-review).** The closed schema gains three kinds so that money, accounts and admin work are operations a script can match, not prose: `payment` (payee or product, currency, amount cap, provider reference), `account-create` (name, provider, permission profile, boundary, trust, expiry if temporary) and `admin-identity-op` (the exact operation and its payload digest: policy document, boundary, trust). The template's Accounts, Permissions and Money sections (4.13) are generated views of the Actions block, never a second source. Every execution must resolve to exactly one validated action and satisfy all of its constraints; zero or two matches refuse.

**Reservations.** Before an action is dispatched, a script reserves, in one atomic step, its money amount against both caps, one use of the plan (and of the standing plan), and the action's single use, and writes the provider operation key it will dispatch with. The reservation is released only by reconciliation: confirmed not landed releases it, confirmed landed consumes it, could not tell keeps it and raises `needs-owner`. Two targets cannot both spend the last of a cap, and a crash after submission cannot free an action that landed.

**Standing plans.** A plan of record may be marked standing so that routine production work (a deploy of an application from the gated default branch through its listed workflow) does not need a new human session each time. Limits: envelope kinds only; an expiry (30 days default, 90 cap); a use cap; void as soon as the tier map entry, the account registry row or the workflow file digest it names changes. Never for the exact-only kinds above.

**Actions block.** A closed schema per operation kind; an unsupported form is rejected, not guessed.

| Kind | Fields that must all be bound |
|---|---|
| workflow-dispatch | repo, workflow file, ref (sha), inputs (all), tier |
| terraform-apply | workspace, backend, saved-plan sha256, merged revision, manifest digest (4.5) |
| permission-grant | account, principal, exact permission set (policy ARN or document digest), scope, expiry, tier |
| sql | database identity, statement file sha256, expected row-count bound, tier |
| cloud-change | account, service, operation, resource id, parameter digest, tier |
| destructive | the above for its kind, plus what is deleted, how many, and the backup reference |

Each action carries `uses: 1` unless stated; a spent action does not match again. The matcher parses the command with the guards' existing fail-closed reader; anything it cannot read whole is not planned.

**Permission changes.** In production, and permanent ones anywhere, are serious: the principal, the exact permission set, the scope and (if temporary) the expiry are in the plan of record, exact. "The plan mentions this resource" is not enough. A wider grant stops with `needs-owner`. A grant may never give a service account identity-management rights or `*` on `*`; that would make it an admin account, which 4.14 handles differently.

**Temporary grants.**
- Provider-issued expiry is the rule: an STS session duration, a policy condition on `aws:CurrentTime`, an Azure role assignment end time or PIM activation. Crew records the provider's grant id.
- Revocation is by verified grant id with the identity that created it, never by replaying a stored command.
- Dev and QA: a temporary grant to an existing crew account is allowed when the permission set is one of the **grantable profiles** the application's onboarding plan listed; `directive` logs it, `guided` asks once per ticket. Anything else, and every production grant, is in a plan of record. Unattended and expiry or ownership cannot be proved: refused.
- One machine ceiling, 24 hours, in both modes (a protected key). The mode only changes the suggested duration (8 hours in `directive`, 1 hour in `guided`); the same request is allowed or refused identically in either mode. The earlier permission set is recorded first.
- One ticket per provider; a provider without one is refused, not approximated.

**Temporary accounts (new).** Creating any account, permanent or temporary, in any tier, is serious: it is listed exactly in a plan of record as an `account-create` action with its permission profile and expiry, and created through an admin need (4.14). Named `crew-tmp-<ticket>-<n>`; recorded in the registry with its expiry. Expiry must hold with no help from crew's own clean-up: either the provider enforces it (on AWS a policy condition on `aws:CurrentTime`, so the permissions stop even if deletion never runs), or, where the provider has nothing of the kind, the account's credential never leaves the broker, which refuses every use after the deadline (24 hour cap; registry row marked `crew-held`). A sweep (at `/crew:status`, in the pipeline and on the broker's timer) deletes expired accounts and posts what it removed; the test for this rule runs with the sweep switched off.

### 4.5 Autopilot and unattended production (layer 3)

| Tier | Policy |
|---|---|
| Dev | always, any time; data backup before a data change |
| QA | always, any time; data change noted on the ticket |
| Prod read, verified read account | always, any time, both modes |
| Prod write, covered by a plan of record or a live standing plan | unattended, in a window, after the checks, with the application's write account |
| Prod write, not covered | needs-plan: the 4.13 flow with a human |
| Prod emergency | owner-declared, scoped (below) |
| Unknown tier | never unattended |

**Who holds the production write credential (revision 3; replaces "the agent never does").**
- Preferred, unchanged: the pipeline. A GitHub Actions job behind a protected Environment, or a Terraform Cloud VCS run, holds the application's write account as its own secret and runs `crew_prodcheck` before it applies. Where this exists the session never sees the credential.
- Otherwise the **broker** (4.14), a small local service that runs under its own OS account and holds the references to the write and admin credentials. The session never receives a production write credential. It sends the broker a request naming one action of one plan; the broker verifies the plan's attestation, runs `crew_prodcheck`, reserves the action (4.4), carries out that one operation itself with the application's write account, and returns the result. Where the provider can express it, the broker narrows its own session to that operation's resources and to the shorter of 15 minutes and the end of the window. A second write, even inside the same application, is a second request with its own checks.
- The pipeline's privileged part is pinned apart from the change being deployed: the workflow that holds the Environment secret, the check script and the manifest reader come from a protected ref (or a separate repository) the candidate revision cannot alter, and the job verifies the attestation with a public key stored in the Environment. A test changes the candidate's workflow, check script and artifact after approval and requires each to fail.
- The account is still verified as scoped (4.14), so even the executor can reach only that application.
- Native Windows is no longer refused: the broker is the boundary there, not the sealed launcher, which still answers `unknown` (`crew_unattended.py`).
- **If the broker is not installed** (it needs one administrator-level install, owner decision O4), production writes run only through the pipeline. A same-user broker is offered as an explicit, weaker choice; with it a process running as the owner's user can reach the write credential without crew's checks, and the session-start line says so.

**When a production action is eligible.** All three, checked by the executor at the moment it acts: the machine's timing rule allows it (below); the time is inside the window the plan of record names for that action; and the plan says `unattended: yes` for it, a field that has no default and must be set explicitly in either mode. Tests sit just outside each boundary, on both executors.

**Checks, at execution time, per operation** (`crew_prodcheck.py`):
- `plan-scope`. Terraform: a manifest generated from the exact saved plan (every resource address with its action and a digest of the planned change), bound to the plan binary's sha256, backend, workspace, expected prior state serial and merged revision; only that artifact is applied; anything not in the approved Actions fails. Other kinds: the bound fields of 4.4.
- `plan-scope` for an envelope: the bound action is inside every bound, the binding record names an allowlisted decider model, and the standing plan (if any) is unexpired, under its use cap and not voided.
- `attestation`. The plan's approval attestation verifies against the exact plan digest (4.13).
- `account`. The credential in use is the account the tier map names for this target and access level, and it verifies PASS now, against the provider, not from a cached result (4.14).
- `backup`. Provider-verified, not "a non-empty file": the snapshot or export id, its target, completion status and time from the provider's API, within a freshness limit, with the provider's own integrity or restorability signal. One ticket per backup provider. **Changed in revision 3:** an action with no provable backup is no longer always human only. It runs unattended only when the plan of record lists that exact action under "irreversible", with a cap (amount, count or blast radius) and a preflight (a dry run, a provider validation call, or a read that shows the expected prior state). The approval repeat-back shows the irreversible list on its own. Exact binding, one use, no envelope, no standing plan. Without that listing: needs-plan. A backup that was required and whose probe failed is a different case and always refuses; "approved as having no backup" never excuses a failed backup. A missing or failed preflight refuses, and so does a replay.
- `rollback`. A stated procedure per action. It is not run automatically after an ambiguous outcome: the executor first reconciles remote state (did the change land?), then either rolls back a known partial state or stops and raises `needs-owner`.
- The receipt binds one operation, its expected prior state and one attempt. It cannot be reused for another resource or after the state moved.

**Timing** (`crew_prodwindow.py`, pure): `production.hours` and `production.windows`, machine-owned; each window is an owner-confirmed record. Outside hours or inside a window: eligible. Inside hours: queued. Missing or unreadable: ask a human.

**Queue** (durable states `queued → claimed → submitted → reconciled`, one claim per target, a remote operation id so a crash after remote success does not dispatch twice). On drain everything is re-validated: the plan approval, the window, the credentials, the tier.

**Sleep.** `autopilot.sleep.production: "drain"` makes the sleep window the default production window. It is a protected key. The existing rule that sleep only tightens approval and question policies is untouched.

**Emergency.** Declared only by the owner's typed prompt, with the same repeat-back. It names the incident, the target, the action, an expiry and a use count. It waives timing and the review loop, not the backup check, not the account rule and not the admin need record. Afterwards the change goes through the normal workflow. A recurring kind of emergency is better served by a standing plan written in advance (4.4).

**Money.** A money action (a payment, a purchase, a subscription or billing change, reserved capacity, or infrastructure whose estimated monthly cost is over `serious.costThreshold`; an estimate that cannot be made counts as over) is exact-only: payee or product, currency, a per-action cap and a plan total cap. The amount is reserved atomically before dispatch and held until reconciliation (4.4), so two actions cannot both spend the last of a cap. The threshold default is set by the decider at 50 USD a month and is a protected key.

**Conflict stated plainly.** Revision 2 followed artifact 1 and kept irreversible production actions for a human at execution time. The owner's feedback moves the human to planning time: with a solid plan built together and approved, execution is unattended. Revision 3 follows the feedback and keeps the scripted checks at execution time.

### 4.6 Standard locations, clean-up, clean return, handoff

**Roots are machine-owned.** `crew_paths.py` resolves every location from the machine config; a repo value may not move the worktree or scratch root (today the repo wins for `worktrees.root`; that becomes a protected key). Each run gets an exclusive directory with an ownership record.

| What | Location |
|---|---|
| Developer worktree | `<root>/worktrees/<repo>-<digest>/dev-<ticket>` |
| Reviewer input | `<root>/review/<repo>-<digest>/<ticket>-r<round>-<provider>/in` — an exported snapshot of the PR head, read-only, with no `.git` |
| Reviewer output | `.../out` — the only place a reviewer writes |
| Wave lane | `<root>/worktrees/<repo>-<digest>/lane-<set>-<ticket>` |
| Scratch | `<root>/scratch/<repo>-<digest>/<ticket>/<role>/` |
| Tests | `$CREW_TEST_ROOT`, default `<root>/scratch/tests/<run-id>/` |
| Sandbox | `<root>/scratch/sandbox/<run-id>/{in,home,out}` |

"Each reviewer gets their own worktree" is met with a snapshot rather than a linked git worktree, because a linked worktree shares git's administrative state and is writable by the same user. The reviewer still has its own tree at a standard place.

**Deletion.** One helper. It refuses an empty path, a root, a system path and anything outside the run's directory; it walks without following links, refuses reparse points and junctions on Windows, refuses to cross a mount, and checks the ownership record first. Tested on native Windows and Linux against disposable trees.

**Clean-up belongs to the coordinator**, under a checkout lock, never to a lane:
1. Publish findings, gate results and evidence to the ticket; re-read to confirm; reconcile after a timeout before posting again.
2. Delete local findings only after the publish is confirmed and no reader remains.
3. Remove the ticket's worktrees without `--force`; a dirty or unpushed one is kept, named, and the ticket goes to `needs-owner`.
4. Return the main checkout to the default branch, fast-forwarded and clean; if that would discard work, stop and say what is there.
5. Sweep that ticket's scratch.

**Verify gate in a dirty worktree.** When the tree holds changes that are not the candidate's, the gate runs against the exact candidate sha in a clean tree it creates under the standard root, and credits the result only when the tree fingerprint, the trusted verify-map digest, the expected rule set and every shard's result all match. If it cannot do that it returns an explicit NOT VERIFIED state, quietly and in one line, which callers must treat as not passing. Both shell drivers change together.

**Handoff notes, committed** (`docs/handoff/<ticket>.md`):

```
# Handoff <ticket> — <UTC time> — <session>
Branch / PR / worktree:
State: <phase>, round <n>
Done:            (what, evidence link)
Left:
Verified:        (command or path)
Not verified:
Waiting on the owner:
Next command:
```

The scope guard allowance for that file is a harness change and lands alone (R-54); the command and format land after it (R-55).

### 4.7 Docker sandbox

**What the launcher is and is not.** `crew_sandbox.py run` builds safe arguments for the runs crew starts. It does not isolate a host from an agent that has a host shell and a reachable Docker daemon; a raw `docker run` finding in the cloud guard is a tripwire for that. Real isolation for unattended or untrusted work is to run the worker itself inside the sandbox, with no daemon socket and no host shell (R-64).

Rules in the argv: `--rm`, read-only root, tmpfs `/tmp`, `--network none` unless a named allowlisting proxy, non-root `--user`, `--cap-drop ALL`, `no-new-privileges`, pid, memory and CPU limits. Refused: `--privileged`, host pid/ipc/network, `--cap-add`, `--device`, `--volumes-from`, a raw `-v` or `--mount`. Mounts are asked for by role and created by the launcher under the run's directory; the input mount is read-only and is a copy or snapshot, never the host checkout; output goes to a separate directory. A destination may never be `/`, `/bin`, `/sbin`, `/usr`, `/etc`, `/lib`, `/lib64`, `/boot`, `/dev`, `/proc`, `/sys`, `/root`, `/var/run` or the daemon socket. Clean-up uses the deletion helper.

**Tests.**
- must-block: each forbidden flag and destination; source escapes (a link out, `..`, an empty variable, a junction); must-allow: the standard mounts and a named proxy.
- Host-change detection runs only in a disposable VM or a private filesystem image with write auditing, comparing content and metadata of the system directories before and after. It never plants a change on a shared runner. Elsewhere it is SKIP, not PASS.
- Suite hygiene: tests write only under `CREW_TEST_ROOT`; the deletion helper is the only recursive delete the suites use.
- The real entry points are exercised under the boundary: the agent run, both eval builders, the Compose template.

**Root cause (R-02).** Run the suites and the eval inside a disposable VM with write auditing on the system directories. A hit names the writer. A clean run is reported as "not reproduced", never as "the suite is safe".

### 4.8 Orchestrator and the phases

**Orchestrator.** Opus 5.5, medium effort; routes and checks; extends `crew_route.py`. `crew_triage.py` (pure): four factors 0 to 2, legacy modifiers, size, starting model; mechanical task types go straight to Haiku 5.5. Role defaults from artifact 1 become the shipped `dev.roles` / `qa.roles`. A brief template for hand-off. One re-route, counted on the ticket, so a third call is refused by a script. One workflow restart, likewise counted.

| Phase | Crew today | Change | Who, in a wave |
|---|---|---|---|
| 0 Triage | none | `crew_triage.py`; L/XL becomes an epic, Blocked, notify | coordinator |
| 1 Brainstorm | `/crew:brainstorm` | none | coordinator |
| 2 Spec | `/crew:spec`, `/crew:plan` | Actions block | coordinator |
| 3 Approve | `/crew:approve` | an advisor review of the spec first, in a separate session, using the existing `secondOpinion` keys. Then: serious ticket, the 4.13 flow and the owner's approval; non-serious, the person (`guided`) or the decider (`directive`) | coordinator; owner for serious |
| 4 Implement | `/crew:implement` | own worktree; ticket updated as you go | lane |
| 5 Review | `/crew:review` | reviewer snapshot; neutral; five severities | lane requests, never accepts |
| 6 Fix | `/crew:fix` | model by round: 1-3 assigned, 4-5 one step up, 6-9 Fable 5.2, 10 restart once | lane |
| 7 Gate | `/crew:gate`, `/crew:verify` | scripted and sliced; agent only on failure | scripts; credit by coordinator |
| 8 Land | `/crew:promote` | per tier; executor for prod | coordinator |
| 9 Clean up | `/crew:done` | 4.6 | coordinator |

That is ten stages numbered 0 to 9. A wave lane runs 4 to 6 only, which keeps the existing never-list true.

**Documentation path.** Skips 1 to 3 only for files on an explicit allowlist of non-executable prose. Command files, agent files and skill files are instructions, not documents, and take the normal path.

**Tickets.** "The ticket" is the configured tracker. Status maps for all four kinds: Jira gets artifact 2's 13 statuses; files, Obsidian and SDP keep the existing ones including `needs-owner`, `cancelled` and `superseded`, with `Blocked or Parked` mapped to `needs-owner`. Events (approved spec, progress, review round, fix, land, clean-up) each carry a durable id so a retry does not post twice; updates are conditional on the last seen state; a failed post is retried and reported and blocks only where the phase needs the record. `/crew:done` refuses while a required event is missing.

### 4.9 Fast, sliced checks

- A rule is `fast` when its measured `seconds` is under the threshold (120 by default) **and** the measurement is a real figure for this platform; a lower bound or another platform's figure counts as heavy.
- Fast rules matching the change run every round; heavy rules once at Gate.
- Selection never drops what the map already requires: every matching cross-cutting rule, the `preReview` checks, `reach`, and the `unmapped` behaviour. So a docs change under `plugin/crew` still runs the marketplace rule; "docs only runs the doc slice" was wrong in revision 1.
- `gate-runner.py --slice k/n` splits the selected set by `seconds`, deterministic by rule id. Credit needs every slice's result for the same candidate; a missing or skipped required check shows as not verified.
- Worker count from a probe; when the probe fails, the conservative value, said out loud.
- PASS is one line; FAIL prints the failing lines.
- Web tests and doc checks are named slices. A per-tier smoke template under two minutes.

### 4.10 Plain language

One-line refusals (what was stopped, why, what to reply). A "what can I say" page in `/crew:help`. A session-start line when a guard is off, a grant or temporary account is live, an admin need is open, or the mode is `directive`. `/crew:status` leads with what is waiting on the owner.

### 4.11 Two operating modes (new)

**Key.** `mode: guided | directive` in the machine config. It is a protected key: moving the machine to `directive` is on the one-way list. A repo config, a ticket or a run flag (`--guided`) may set `guided` only; a `directive` value in any of those is ignored and reported. Unknown or unreadable resolves to `guided`. `/crew:init` on a machine with no mode sets `guided`.

**What a mode can change.** Only who answers an `ask-routine`, how much is explained, and a few defaults. It is not an input to the policy table, so it cannot change an allow, a deny or a needs-plan.

| | `guided` | `directive` |
|---|---|---|
| Who it is for | someone who does not know development | an owner who gives a directive, plans and goals |
| Stage transitions (4.8) | asks before each one; says what the next stage does, why, and what it will touch | proceeds; one log line |
| A question that comes up | asked in plain language, with options, the decider's recommendation and its reason; "you decide" hands that ticket's routine questions to the decider | the decider answers, and the decision, the rationale and the alternatives go on the ticket's evidence trail |
| Routine ask (conditional lane, dev and QA) | the person's one-line reply | the decider |
| Explanations | teaches as it goes: what the step is, what could go wrong, a short glossary entry the first time a term appears | terse |
| Non-serious plan | walked through section by section, then approved by the person | written and approved by the decider (`approved_via: decider`) |
| Plan of record for serious work | same flow as 4.13, with each section explained and read back; the planner suggests "attended" | 4.13; the planner suggests "unattended in the window". Either way `unattended` is an explicit field the owner approves, with no default, so the same approved plan runs the same in both modes |
| Repeat-back | on every approval, with a plain explanation of the risk | on plan-of-record approvals and the one-way list |
| Temporary grant, dev and QA | asked once per ticket; suggested 1 h | allowed and logged; suggested 8 h. One 24 h ceiling in both |
| Status | narrative, what happened and what comes next | exceptions and what waits on the owner |
| Unattended | routine questions wait for the person unless "you decide" was said | keeps going |

**Identical in both modes.** The Never lane; the deny-first table and its order; the serious list and the plan-of-record requirement; `crew_prodcheck` (scope, account, backup, window); the admin need record; the broker; the attestation; account verification; approvals minted only in the prompt hook, with the whole-prompt grammar and the bindings at spend; the Opus 5.5+ decider rule (in `guided` it applies to every recommendation and delegated decision); protected policy; redaction; the sandbox. One test table runs under both modes (R-M4). Every non-ask row must give the same outcome. For ask rows the test follows the answer through: the same request with the same answer must end in the same grant, with the same duration ceiling, and the same execution result in both modes.

### 4.12 The decider (new)

**Who may decide.** A model whose **exact id** is in the machine-owned catalog `decider.models`. The catalog is a list of ids the owner has confirmed, not a rule about families or tiers, so an older Opus is not admitted by its name. Proposed first entries: the Opus 5.5 id (**[I]**, to be read from the runtime in R-06) and `claude-fable-5-2`, the latter only if the owner confirms the reading in O3. Adding an id is a protected change. Sonnet, Haiku and non-Claude models are never eligible. Codex and Kimi are advisors: their output may be attached to a request as input and is never a decision record.

**How it runs.** `crew_decider.py decide --request <id>` starts a fresh headless run that crew launches itself, with the model pinned in the launch arguments, no write tools and no cloud credentials. Input: the request's structured fields, the ticket, the plan, advisor notes. Output: one JSON object with an outcome taken from the request's own closed list (for example `allow`, `deny`, `escalate`, or one of the lettered options of a question), a rationale, the alternatives considered, and evidence references. Free text cannot widen the outcome list.

**The record.** Decision id; request id and sha; outcome; rationale; alternatives; the model id asked for; the model id the runtime reported; runtime name and version; run id; the asking session's id; advisor references; mode; time. It is stored with the approvals and posted to the ticket's evidence trail.

**Enforcement, by script.**
- A record is valid only when the reported model equals the requested model and is on the allowlist. A missing or unreadable reported model is "could not tell", which is not a decision. R-06 measures what the runtime reports and whether a fallback to another model shows, and it exercises the alternative as well: a direct API call whose response metadata names the model. Whichever source R-06 shows to be trustworthy is the only one R-D1 accepts.
- A downgrade is never a decider. When no allowlisted model is available (limit, outage), the request waits and the ticket goes to `needs-owner`. There is no fallback to Sonnet, Haiku or another family.
- The asking session cannot be its own decider: the run id must differ from the asking session id, and the guard spends a decider record only for the request it names, with the same bindings as 4.2 step 6.
- Where two allowlisted models are available, the decider is the one that did not author the work (Opus authored, Fable decides, and the reverse). Otherwise the record is marked `same-model`.
- A `deny` or `escalate` is sticky for that request's bindings; re-asking the same operation returns the stored answer. Decisions are counted per ticket and class; past the cap (20 by default) the ticket goes to `needs-owner`.

**What the decider can never do.** Approve or amend a plan of record; answer a one-way item; act on anything the classifier marks serious without a plan; classify an unknown target's tier; confirm any admin need except a temporary grant of a listed grantable profile in dev or QA; change a protected key. These are refused by the class table in `crew_policy.py`, not by the decider's prompt.

**Limit.** The decider reads text that a hostile repo may have written, so it can be talked into a wrong routine decision. What bounds the damage is the list above and the closed outcomes. Like every layer-2 record, a decider record can also be forged by a process running as the same user.

### 4.13 Plan of record: working with a human on a solid plan (new)

**When it is required (the serious list, closed, in `crew_policy.py`).** Money (4.5); any production write; a permanent permission change in any tier and any permission change in production; creating any account, permanent or temporary, in any tier; any admin use other than a temporary grant of a listed grantable profile in dev or QA; destroying data the ticket does not own; an irreversible or outside-system effect (a message to customers, a public release, a DNS cut-over); a change with no provable backup. Anything the classifier cannot place is serious.

**The flow.** It is stage 2 and 3 of 4.8 for a serious ticket, and it has its own states so a script can refuse to skip one.

| Step | Who | Output | Script refuses to go on when |
|---|---|---|---|
| 1 Directive | owner | goal, constraints, what is out of bounds, in the owner's words | empty |
| 2 Scope-out | Opus 5.5+ planner, read accounts only | targets with tier, applications, accounts, what is out of scope | a target's tier is unknown |
| 3 Research | planner | findings, each with evidence and a label: verified, inferred or could not tell; the list of questions that must be answered | a required question is "could not tell" and the owner has not accepted it by name |
| 4 Draft | planner | the template below, with the machine-readable Actions block | the validator rejects a section or an action |
| 5 Advisor check | a model of another family (Codex or Kimi) | findings attached; advisory | the check did not run and no reason is recorded |
| 6 Human session | owner and planner | questions settled; the owner's changes applied | open questions remain |
| 7 Approval | owner, through the prompt hook | `yes`, a repeat-back the hook builds from the validated plan, `confirm` | hashes moved since the repeat-back |
| 8 Execution | unattended | each action matched, checked, recorded | an action is outside the plan: stop, `needs-owner`, amend by approving the delta |

The repeat-back at step 7 is short and structured: number of actions by kind; the irreversible list; accounts to be created; admin needs; permission changes; money caps; windows; whether it runs unattended; the expiry.

**Proof that the flow happened (added after cross-review).** A filled-in template proves nothing about who filled it. So the flow keeps a state record beside the draft, and each step appends to it: steps 2 to 4 append the planner's run record in the same form as a decider record (requested and reported model id, run id, the draft digest it produced), so an ineligible model cannot have done scope or research; step 6 appends the prompt ids of the owner's own turns, captured by the prompt hook, each bound to the draft digest at that moment. Step 7 refuses unless every step has its record and the chain of digests ends at the plan being approved.

**The attestation (added after cross-review).** A receipt file that says `approved_via: user-prompt` can be written by any process running as the owner's user, so on its own it cannot carry a production write. At `confirm`, the approval is therefore attested over the exact plan digest by something the session cannot use. Two forms, either accepted:
- *Presence key.* A signing key held by the operating system that needs the owner's presence to use (a platform prompt or a hardware key). The hook asks for one signature at `confirm`. Whether this is available and scriptable on the owner's machines is **[?]**; R-07 measures it.
- *Forge review.* The plan is committed and the owner approves that commit from their own forge account, while agents work under a separate service account that cannot approve as the owner. The executor reads the approval from the forge.
Both executors verify the attestation themselves before acting: the pipeline against a public key or the forge, the broker likewise. Without an attestation a plan of record can still be approved and run **attended**; it is not eligible for unattended serious work. Which form to use is owner decision O6.

**Template** (`docs/plans/<ticket>.md`, validated by `crew_planrecord.py`):

```
# Plan of record <ticket> — <title>
Mode:            Planner model:            Advisor:
1  Directive        (the owner's words)
2  Scope            in / out; each target with tier and application
3  Research         finding | evidence | verified / inferred / could not tell
4  Actions          machine block: exact or envelope, per the closed schema (4.4)
5  Accounts         generated view of the Actions block: service accounts used;
                    account-create actions; admin-identity-op actions
6  Permissions      generated view: principal | profile | scope | expiry
7  Money            generated view: payee or product | currency | caps
8  Backup, rollback per action; the irreversible list with cap and preflight
9  Windows          per action: when; unattended yes or no (no default)
10 Stop conditions  what halts the run; who is told
```

The approval is **not** part of the plan file. The receipt and the attestation are stored separately and name the plan's digest, which covers the whole file as approved; writing the receipt therefore cannot change the bytes it approves. A plan of record expires (30 days by default) and is void when its digest moves.

### 4.14 Service accounts and admin use (new)

**Convention.** One read account and one write account per application per tier, and the same per automation process:

| Kind | Name | Example |
|---|---|---|
| Application | `crew-<app>-<tier>-<ro\|rw>` | `crew-billing-prod-ro` |
| Automation process | `crew-auto-<process>-<tier>-<ro\|rw>` | `crew-auto-backup-prod-rw` |
| Temporary | `crew-tmp-<ticket>-<n>` | `crew-tmp-R-A9-1` |

On AWS these are roles under the path `/crew/`, assumed for short sessions, never users with long-lived keys; the launcher already refuses a `:user/` identity **[V]**. Other providers use their nearest equivalent and say so in the registry row.

**Where it is recorded.** A machine-owned registry (`accounts` in the machine config, a protected key): name, provider, provider account id, principal id, application or process, tier, access level, digest of the permission set, a **reference** to the credential (a profile name, a secret-store entry name; never the secret), the ticket and plan that created it, state (`active`, `quarantined`, `expired`), and the last verification with its result and time. The existing `unattendedCloud.aws.readOnly` and `nonProd` entries become rows.

**How the tier map uses it.** `tiers.<target> = {tier, application, accounts: {read, write}}`, by registry name. Which application a workspace belongs to is machine-owned as well. A remote URL is only a string that any clone can copy, so the binding is an **enrolment**: the onboarding plan enrols a specific checkout (its real path and repository identity) on this machine, or an authenticated CI workload (the pipeline's own identity claims), and only an enrolled workspace is given that application's accounts. A test presents two checkouts with the same remote and requires the unenrolled one to be refused.

**Verification** (`crew_accounts.py verify`, one ticket per provider). Crew does not try to judge arbitrary policies. Onboarding creates accounts from a small set of **permission profiles** crew ships per provider (read, write, and the grantable temporary profiles), and verification checks that the account still is one of them: the provider says the credential is that principal; its effective permissions, including inherited ones (groups, attached and inline policies, boundaries), equal the profile; the profile has no identity-management rights and no `*` on `*`; resources are limited to the application's; the read profile has no mutating action. An account that was not made from a supported profile is COULD-NOT-TELL. The result is PASS, FAIL or COULD-NOT-TELL, and it is checked against the provider **at the time of issuance**, not read from a cache.

**What a properly scoped account may do, by script.**
- Read account, any tier including production: always, in both modes, attended or not.
- Write account in dev and QA: always.
- Write account in production: for an action covered by a plan, after `crew_prodcheck`, through the executor. No extra per-use approval and no admin.
- FAIL or COULD-NOT-TELL: no credential is issued, in any tier, and no routine reply or decider decision changes that. The way forward is to re-onboard the account.

**Where credentials can and cannot leak.** Two classes, with different claims.
- *Production write and admin credentials* never enter the session or any process it starts. They stay inside the executor (the pipeline or the broker), which performs the operation itself. This is the class where "never in a command or a log" is a guarantee.
- *Read credentials and dev and QA write credentials* are issued to the child process through its environment or a `credential_process`, never as arguments. Here the claim is narrower and says so: a child can still copy its own credential into an argument, a debug file or a tracker post. What is scripted is the redactor on everything crew publishes, the 4.3 secret tripwire on commands, and end-to-end tests that plant a credential in child stderr, in a subprocess argument and in an evidence post and require each to be caught before publication.

**Creating accounts is a ticketed, planned step.** Onboarding an application is a plan-of-record template (R-A9): it enrols the workspace, lists each account as an `account-create` action with its permission profile and permissions boundary, lists the grantable temporary profiles, and names the admin need that creates them. The registry row is written by the script from the provider's response.

**The broker.** A small local service (`crew-broker`) that runs under its own OS account. It alone can read the references to production write and admin credentials. The session talks to it over a local channel and can ask for exactly two things: "carry out action N of plan P" and "carry out operation K of need D". The broker checks, executes the one operation itself, records it and returns the result. It has no "give me the credential" request. Installing it needs administrator rights on the machine once (owner decision O4). Without it: production writes go through the pipeline only, and admin use is attended only.

**Admin use.** An admin credential is a registry row of kind `admin`, enrolled by the owner (crew cannot infer that an admin account exists or is missing from its own local records). Only the broker can resolve it.

1. **The need record** (`crew_admin.py need`). Fields: need id; ticket; plan reference; provider and account; application; a reason code from a closed list; the exact operations wanted, each with its payload digest (the policy document, the permissions boundary, the trust document, the principal name); a time box; who confirmed it.
2. **The script check, per reason code, on provider evidence.** `no-suitable-account`: the provider's own listing, read with the read account, shows no account of the needed profile for that application and tier. `permission-missing`: the provider's simulation, or a recorded denial, shows the scoped account lacks exactly the capability requested. `bootstrap`: the owner has enrolled an admin account for that provider and the provider shows no crew accounts for the application. A conforming name or an empty local registry is never evidence. A probe that cannot tell is not a need.
3. **Who may confirm it.** Every need is listed, exact, as `admin-identity-op` actions in an attested plan of record, with one exception: a temporary grant of a listed grantable profile to an existing crew account in dev or QA, which the decider (`directive`) or the person (`guided`) may confirm. Unknown tier: the owner.
4. **Closed list of admin operations.** Create, change or delete a principal under the crew path; attach or set a policy on it; set its permissions boundary; set its trust; create its credential, delivered straight to the secret store and never printed. Nothing else: no data, no deploys, no other principals. Each operation runs only with the payload whose digest the need names, so the right principal with a different policy, boundary or trust recipient is refused.
5. **Execution.** The session asks the broker for one operation of the need. The broker confirms the need is open and unspent for that operation, that the plan's attestation verifies, and that the payload digest matches; it then performs the call itself. Where the provider supports it, the broker's own session is time-boxed (AWS: an assumed role for 15 minutes, 60 at most), stamped with the need id (AWS: `SourceIdentity`) and narrowed to those operations (AWS: a session policy), and new principals must carry a permissions boundary. Because the credential never leaves the broker, the time box does not depend on the provider being able to expire a copied credential. One need open per provider account at a time; each operation is used once. AWS mechanics are **[I]** until R-A8 verifies them.
6. **Close** (automatic when the last operation is done or the box ends). Records the end; pulls the provider's audit trail for that session and compares it with the need's operations and payloads; verifies the new accounts against their profiles; posts the need, the operations and the audit summary to the evidence trail. A mismatch quarantines the new accounts, flags the need and raises `needs-owner`. Work continues on the scoped accounts.
7. **Outside crew.** The bootstrap adds a provider-side alert to the owner on every admin session, so admin use is visible even if crew's records are bypassed.
8. **Other providers** (R-AC). Where a provider has no session scoping, the broker is the only control on what the admin credential does: the closed operation list and payload digests still apply because the broker makes the calls, and the audit is the provider's API if it has one, else the broker's own log. The registry marks such an admin row `weak`.

**Limit.** The broker moves the admin and write credentials out of the session's reach; it does not make the machine trustworthy. Someone with administrator rights on the machine, or a provider console session, is outside it. With the same-user fallback (O4 option b) the old residual returns in full: a process running as the owner's user can use those credentials without crew.

### 4.15 A configuration guide that ships inside the plugin (new)

**The owner's point.** Neither he nor an AI model can tell how to fill in crew's `config.json`, so models ask the developer instead.

**What exists today.**
- **[V]** `plugin/crew/CONFIG.md` ships with the plugin. It is 599 lines and generated whole by `docs/guides/crew/src/config_reference.py` from the defaults, the ratchet tables, the profile map and `crew_keys.KEY_META`; its own header says not to edit it by hand. It lists 102 keys (63 settable in the machine file, 39 repo-only). It is mostly reference tables, with procedures for a few families (for example how to find and confirm a `/crew:confirm-config` change id, lines 31-90); it has no start-to-finish set-up procedure and no worked example files. (Corrected after Astra's finding 28.)
- **[V]** `/crew:init` writes only the repo file and never the machine file; the machine file has its own guided walkthrough, `/crew:config`, defined in `skills/crew-setup/global-config.md` — `skills/crew-setup/SKILL.md:170-188`. So set-up guidance exists but is spread over a skill, a command and a reference table. The deliverable is a consolidated guide a model can find, not the first documentation.
- **[V]** `plugin/crew/templates/config.template.json` (93 leaf keys) and `global.template.json` (58) ship with the plugin and are what `/crew:init` copies. Both leave out the same five keys that the defaults have (`autopilot.approval|deploy|maxPhases|mode|questions`; defaults have 98 and 63 leaves). They hold values only: no explanation, allowed values or layer. Tests compare them with builders in `crew_config.py` (`tests/test_crew_config.py:40-44`, `tests/test_change_command.py:406-410`), so the omission looks deliberate **[I]**.
- **[V]** The narrative guide (`docs/guides/crew/src/configuration-reference.md` and the built HTML, DOCX and PDF) and the reasoning (`docs/crew/config-rationale.md`) live outside `plugin/crew`. The installed plugin copy on this machine has `CONFIG.md` and the template and no `docs/guides` (`~/.claude/plugins/cache/useful-claude-add-ons/crew/1.3.75`).
- **[V]** That installed copy is version 1.3.75; main is 1.3.167. Whatever ships reaches a model only after the plugin is updated.
- **[V]** Inside the plugin, `CONFIG.md` is named by `README.md`, `commands/config.md`, `skills/crew-setup/SKILL.md` and `crew_upgrade.py`. `crew_hook.py` does not name it, and no other command file does, so session start, `/crew:init` and `/crew:help` do not point a model at it.
- **[V]** The commands a guide can lean on exist: `crew_config.py --explain`, `--all`, `--check`, `--check-global`, `--set PATH=JSON` with `--apply` and `--repo` or `--global`.
- **[V]** A published Claude Docs doc titled "Configuration Guide", which CLAUDE.md names, is not among the owner's eight Docs-type artifacts or the first 200 artifacts listed. An ordinary artifact "Crew Config Reference" exists (last updated 2026-11-11); I did not read it. More artifacts exist past the first 200, so absence is **[?]**.

**What to build**, all under `plugin/crew/docs/configuration/` so every deployment carries it:

| File | Content | Made by |
|---|---|---|
| `guide.md` | the two layers in plain words; how an owner sets crew up; how an AI model should; worked examples; where each key family is explained | hand-written, with generated tables included |
| `config.blank.json`, `global.blank.json` | a complete blank template per layer: every key that layer may set, at its default | generator |
| `keys.json` | per key: default, allowed values, which layer may set it (machine only, repo only, either, ratcheted, machine-arms, protected), one plain-language line, the version it arrived in | generator, from `KEY_META` |
| `template.annotated.md` | the blank template again with that information beside each key, since JSON cannot hold comments | generator |
| `examples/*.json` | `guided` and `directive` machine files; reviewer settings after the neutral rename (Kimi first, Codex first); tier map, service accounts and production hours; a minimal repo file | hand-written, each validated in CI |

**"How an AI model should configure this"** (a section of `guide.md`, written as steps): read `guide.md` and `keys.json` from `${CLAUDE_PLUGIN_ROOT}/docs/configuration/`; run `crew_config.py --explain --all` to see the effective values and which layer set each; ask the owner the listed questions (mode, tracker, reviewers, applications and tiers, accounts, production hours) and nothing the guide answers; write repo keys with `--set ... --apply --repo`; never write a machine-only or protected key from a repo file, and never hand-edit either file; send a protected machine key through the owner's confirmation; put credential **references** in the registry, never a secret; run `--check` and `--check-global`; report what was set and what was left at its default.

**Kept from drifting.** `config_reference.py --write` produces the generated files and `--check` (already run by `scripts/check-marketplace.py`) fails when any is stale. Added checks: the blank template's keys equal the registry's keys for that layer, with any exclusion (the five `autopilot` keys, if they stay out) named in the registry with its reason; every registry key has a plain-language line, its allowed values, its layer class and the version it arrived in; every repo example passes `crew_config.py --check` and every machine example `--check-global`; and applying each blank template to an otherwise empty layer leaves the effective policy exactly as it was, so copying a blank can never widen or narrow anything (this is why override keys such as the five `autopilot` ones may have to stay out of a blank, each exclusion named). Each later ticket that adds a key updates the registry and the examples in the same PR, which is the existing owner rule.

**The 599-line cap.** `CONFIG.md` is generated, and this plan adds key families (`mode`, `decider`, `serious`, `accounts`, `applications`, `admin`, `tiers`, `production`). It becomes a short generated index, one line per key and a pointer to the guide; the layer rules and per-family tables move into the guide directory. Whether `BUDGETS.md` puts a line budget on new files under `plugin/crew/docs` is **[?]**; R-C4 reads it first.

**So models find it.** A pointer from `skills/crew-setup`, `/crew:init`, `/crew:help` and `/crew:config`; a `crew_config.py --guide` that prints the path; a session-start line when the config is missing or fails `--check`. The built HTML, DOCX and PDF and the Claude Docs "Configuration Guide" are produced from the same source.

---

## 5. Safety invariants

| Invariant | Mechanism | Test |
|---|---|---|
| A plan approval cannot be fabricated **(new)** | attestation over the plan digest by a presence key or the owner's forge review; verified by each executor itself; flow state record with planner run records and the owner's prompt ids; receipt stored outside the plan | receipt and hashes written by a same-user process with no attestation; attestation for another digest; a step's record missing; plan bytes changed after approval |
| One checked operation at a time **(new)** | production write and admin credentials stay in the pipeline or the broker; the broker has no request that returns a credential; atomic reservation held until reconciliation | second write in the same application without its own checks; request for a credential; two actions racing for the last of a cap; crash after submission |
| No self-approval **(moved)** | human approvals minted only in the prompt hook; serious actions need `approved_via: user-prompt` and, unattended, the attestation; a decider is a separate crew-launched run, never the asking session, and never decides a serious or one-way class; family interlock for code review unchanged | current autopilot, cli and decider receipts refused for a serious action; forged payload; other session; asking session as its own decider |
| Injected text cannot approve **(moved)** | whole-prompt grammar; for plan-of-record and one-way approvals `yes` mints nothing and the hook writes the repeat-back; frozen set; bindings checked at spend; a routine reply or a decider record cannot be spent on a serious class; decider outcomes come from a closed list | approval text in a tool result, file, agent message, multi-line prompt; list changed between prompts; command, cwd, sha, identity or input changed; routine record offered for a production write; decider output outside the list |
| Only Opus 5.5+ decides **(new)** | machine-owned catalog of exact, owner-confirmed model ids; model pinned at launch; reported model must equal requested; could not tell is not a decision; no downgrade fallback | Sonnet, Haiku, Codex, Kimi, an older Opus as decider; reported model differs; reported model missing; catalog edit without the owner |
| No unscoped plan **(new)** | plan-of-record validator: every section present, research labelled, closed Actions schema, envelope bounds closed, exact-only kinds; expiry | missing section; required "could not tell"; wildcard crossing the application prefix; envelope on a money, permission, account or irreversible action; expired plan |
| Admin only on a need, and only for that need **(new)** | need checked on provider evidence; the broker performs each operation with the payload digest the need names; provider time box, source identity and session policy where supported; one need at a time, each operation once; audit compared at close; quarantine on mismatch; a need is a prerequisite and never an allow | no need; probe could not tell; right principal with a different policy, boundary or trust; second use; past the box; audit shows an unlisted call; need confirmed only by a decider outside the grantable-profile case; serious action passing on an open need alone |
| Properly scoped accounts only **(new)** | registry; workspace enrolment; supported permission profiles; effective permissions verified at issuance; tier map names the account | second checkout with the same remote; profile drifted; inherited extra right; read account with a write right; account not from a profile; cached PASS after a provider-side change; issuance after a routine reply to a FAIL |
| Credentials never in a command or log **(new)** | production write and admin: never leave the executor. Others: environment or `credential_process`, redactor on everything published, secret tripwire | request to the broker for a credential; credential planted in child stderr, a subprocess argument and an evidence post |
| Same rules in both modes **(new)** | mode is not an input to the policy table; one grant ceiling; `unattended` explicit in the plan | the whole table under `guided` and `directive`, following ask rows through to the final grant and execution |
| Secrets | redaction before any record; shape tripwire; fetch-on-host template | token shapes; a secret name is allowed |
| No guard self-config | effective-policy comparison; widening only by owner confirmation | set, delete, replace file, link, alternate writer |
| No invented status | tracker status map per kind | unit test per kind |
| Backup and rollback before a production change **(moved)** | provider-verified backup; reconcile before rollback; receipt per operation, prior state and attempt; an action with no provable backup runs only when the plan of record lists it exactly as irreversible with a cap and a preflight | failed or stale backup; reused receipt; ambiguous outcome; irreversible action not listed; listed but over its cap; listed in an envelope or a standing plan |
| Plan scope **(moved)** | closed Actions schema; exact actions matched field for field; envelope actions checked against closed bounds after the decider binds them; terraform manifest bound to the plan binary | one extra resource; same address, different value (exact); bound value outside the envelope; standing plan expired, over its use cap or voided; unsupported form |
| Production timing | machine-owned hours and windows; unknown asks | clock tables; missing config |
| Emergency | owner-declared, scoped, counted; backup still required | agent-declared; second use |
| Temporary grants and accounts **(moved)** | provider expiry and grant id; a temporary account's expiry is enforced by the provider or, failing that, by the broker refusing every use after the deadline; 24 h ceiling; sweep as clean-up only | no expiry proof; wider than plan; revoke by id; with the sweep switched off, an expired account or a credential issued before expiry still works |
| Unattended production **(moved)** | attested plan of record or live standing plan; eligibility is machine timing and the plan's window and `unattended: yes`; checks at execution; the pipeline (pinned apart from the candidate) or the broker performs the operation | no plan; decider-approved plan; no attestation; just outside each of the three boundaries; candidate changes the workflow, check script or artifact after approval; another application's account; unverified account |
| Sandbox | launcher rules; deletion helper; worker-in-container for unattended | 4.7 list, in a disposable VM |

---

## 6. Roadmap and tickets

Rules. Each PR lands alone and leaves main working. **H** = harness PR with no feature work; a feature that needs a new `tests/sabotage*.py` gets a harness-only companion PR for that file first. Every new allow is built inert (report-only) and switched on by a separate last ticket. Size per artifact 2; model per artifact 1.

### Phase 0 — Find out, lay foundations (no behaviour change)
| ID | Title | Size | Model | Depends | Acceptance |
|---|---|---|---|---|---|
| R-01 | `crew_policy.py` decision table, report-only, with `explain` | M | Opus 5.5 | — | positive and negative cases per operation, including unknown tier, unknown protection and unknown ownership |
| R-02 | Reproduce the host damage in a disposable VM with write auditing | M | Opus 5.5 | — | names the writer, or says "not reproduced"; evidence committed |
| R-03 | Capture one refused IAM write and one refused dispatch | S | Haiku 5.5 | — | refusal text, guard.log rows, config layer and ref |
| R-04 | `crew_paths.py`: machine-owned roots and the deletion helper | M | Opus 5.5 | — | link, junction, mount-crossing and root-replacement cases on Windows and Linux |
| R-05 | Machine-owned tier map, report-only | S | Opus 5.5 | — | repo can only narrow; unlisted is unknown |
| R-06 (new) | Measure what a crew-launched headless run reports as the answering model and whether a fallback shows; exercise the direct API path and its response metadata too | S | Fable 5.2 | — | both sources measured on the installed client, version stated; the trustworthy one named; the exact Opus 5.5 id read from the runtime |
| R-07 (new) | Measure the two attestation forms: an owner-presence signing key on Windows and Linux, and a forge review by the owner while agents use a separate account | S | Fable 5.2 | — | each form shown working or not on the owner's machines; the verification step runnable by a pipeline and by the broker |

### Phase 1 — Reviewer-family neutrality
| ID | Title | Size | Model | Depends | Acceptance |
|---|---|---|---|---|---|
| R-10 **H** | Provider registry; one probe per attempt | M | Opus 5.5 | — | goldens replay; no double probe; limit confers no authority |
| R-11 **H** | Neutral labels and notes; old spellings read | S | Sonnet 5.5 | R-10 | old ledgers parse |
| R-12 **H** | `review.md` and `reviewer.md` in neutral words | S | Sonnet 5.5 | R-10 | budgets hold; canary review passes |
| R-13 | Neutral wording elsewhere, string check, `reasoningEffort` validation | S | Sonnet 5.5 | R-11 | planted "Codex review" fails the check |
| R-14 **H** | Five severities and the money rule, old severities read | M | Opus 5.5 | R-10 | goldens replay; low blocks only with the money flag |

### Phase 2 — Approval by conversation
| ID | Title | Size | Model | Depends | Acceptance |
|---|---|---|---|---|---|
| R-20 **H** | Store tripwire stops refusing everyday commands | S | Opus 5.5 | — | recorded over-refusals pass; must-blocks hold |
| R-21 | ADR and measurement: is a blocked prompt's hook text shown; does a plain reply arrive unchanged | S | Fable 5.2 | — | measured on the installed client, version stated |
| R-22 **H** | Request classes and bindings; session checked at spend | M | Opus 5.5 | R-20, R-21 | each binding has a moved-field refusal |
| R-23 **H** | Whole-prompt grammar, frozen repeat-back, atomic claim | M | Opus 5.5 | R-22 | section 5 row 2 |
| R-24 | Cloud guard records requests and spends receipts, behind a switch; no marker for new classes | M | Opus 5.5 | R-23 | off by default; marker refused for new classes |
| R-25 | Unattended requests: inbox in `/crew:status`, resume, cancel, re-validate. Holds only one-way and plan-of-record items once Phase 3 is on | M | Opus 5.5 | R-24 | request outlives the lane; stale state re-validated |
| R-26 | Verify trust: hash stays default; owner allowance is a separate bounded decision | S | Sonnet 5.5 | R-23 | init offers no owner-wide trust |

### Phase 3 — Modes and the decider (new in revision 3)
| ID | Title | Size | Model | Depends | Acceptance |
|---|---|---|---|---|---|
| R-M1 | `mode` key: machine-owned, protected; repo, ticket and run may only set `guided`; unknown is `guided` | S | Opus 5.5 | R-32 | a repo `directive` is ignored and reported; init sets `guided` |
| R-D1 | `crew_decider.py`: launch with a pinned model, catalog of exact owner-confirmed ids, decision record with requested and reported model id; report-only | M | Opus 5.5 | R-06, R-01 | Sonnet, Haiku, an older Opus and a mismatched or missing reported model give no decision |
| R-D2 | Decision classes in `crew_policy.py`: which asks are routine, closed outcomes per class, sticky denials, per-ticket cap | M | Opus 5.5 | R-01, R-D1 | serious, one-way and unknown-tier classes are never decider-eligible |
| R-D3 | Advisors: Codex or Kimi output attached as input, never a decision | S | Sonnet 5.5 | R-D1, R-10 | an advisor "approve" changes nothing |
| R-D5 **H** | Routine records in the approval store and the `decider` approval value in `crew_ticket.py`: one-step reply bound to the one request that was shown, letter required when several are pending, class fixed at request time | M | Opus 5.5 | R-23, R-D2 | a routine record is refused for a serious class; a genuine one-way receipt is refused for unplanned serious work; a bare `yes` with two pending requests mints nothing |
| R-D4 | Switch on: routine asks go to the person (`guided`) or the decider (`directive`) | S | Opus 5.5 | R-D5, R-24, R-M1, R-P6, R-M4 | in `directive`, and in `guided` after a recorded "you decide", the owner inbox holds only one-way and plan items; in `guided` without it, routine questions wait for the person |
| R-M2 | `guided` messaging: ask before each stage, explain template, glossary, "you decide" | M | Sonnet 5.5 | R-M1, R-73 | each stage transition asks; delegation is per ticket and recorded |
| R-M3 | `directive` behaviour: self-answered questions with decision, rationale and alternatives on the evidence trail; exceptions-only status | M | Opus 5.5 | R-D4, R-72 | every self-answered question has a record; none without a model id |
| R-M4 | Parity suite: one table run under both modes, ask rows followed through to the final grant and execution | M | Opus 5.5 | R-M1, R-D2 | every non-ask row gives the same outcome; the same answered request ends in the same grant ceiling and the same execution in both modes; a planted mode-dependent deny fails the suite |

### Phase 4 — Lanes and planned actions (inert first)
| ID | Title | Size | Model | Depends | Acceptance |
|---|---|---|---|---|---|
| R-30 | Actions schema per kind, validation | M | Opus 5.5 | R-01 | unsupported form rejected |
| R-31 | Planned-action matcher for exact actions, report-only | M | Opus 5.5 | R-30 | autopilot, cli or decider approval never matches a serious action; a spent action does not match |
| R-32 | Protected policy: effective-policy comparison | M | Opus 5.5 | R-01 | every widening route refused without confirmation |
| R-33 | Never lane: hook-skipping flags, redaction, secret tripwire | M | Opus 5.5 | R-01 | crew's own coordination push unaffected |
| R-34 | Human-only findings: terraform state edits, deleting another's branch | S | Sonnet 5.5 | R-01 | must-block and must-allow |
| R-35 | `balanced` profile for dev and QA | M | Opus 5.5 | R-05, R-32, R-33 | dev/QA deploys allowed and logged; unknown never unattended |
| R-36 | Read-only database identity setup and check; becomes the database row of account verification (4.14) | S | Sonnet 5.5 | R-05, R-A1 | a write through the read identity fails at the database |
| R-37 | Temporary grants, AWS | M | Opus 5.5 | R-30, R-32 | provider expiry and grant id; wider than plan asks |
| R-38 | Temporary grants, Azure | M | Opus 5.5 | R-37 | same |
| R-39 | Switch on planned actions, one kind at a time: a kind is enabled only when its own control ticket has landed (permission grants after R-37 or R-38 and R-A8; account and admin kinds after R-A8b; envelopes after R-P4) | S | Opus 5.5 | R-31, R-32, R-24, R-P2, R-P3, R-P8 | a planned IAM attach runs only with its controls present; a kind whose control is missing stays refused; one moved field stops with `needs-owner` |
| R-3A | Session-start line content: guards off, live grants and temporary accounts, open admin need, `directive` mode, same-user broker residual. Written to the status file that R-C6 reads; touches no harness path | S | Haiku 5.5 | R-35, R-37, R-M1, R-AA, R-A8, R-B1, R-C6 | one line; absent when nothing applies |
| R-3B | CLAUDE.md wording for O1 | S | Sonnet 5.5 | O1 | rule and init agree |

### Phase 5 — Plan of record (new in revision 3)
| ID | Title | Size | Model | Depends | Acceptance |
|---|---|---|---|---|---|
| R-P6 | Serious classifier: the closed list; could not place is serious; cost threshold | S | Opus 5.5 | R-01 | each class has a must-be-serious case; an unknown operation is serious |
| R-P1 | Plan-of-record template and validator (`crew_planrecord.py`): sections, research labels, typed operations (`payment`, `account-create`, `admin-identity-op`), per-kind envelope fields, exact-only kinds, generated Accounts, Permissions and Money views, expiry | M | Opus 5.5 | R-30, R-P6 | a missing section, a crossing wildcard, a free-text dispatch input, an unpinned dependency and an envelope on an exact-only kind are rejected; an execution matching zero or two actions refuses |
| R-P2 | The collaboration flow as states with a state record: planner run records (requested and reported model) and the owner's prompt ids, each bound to the draft digest | M | Opus 5.5 | R-P1, R-73, R-D1, R-D3 | a step cannot be skipped; a step done by an ineligible model is refused; a required "could not tell" blocks until accepted by name |
| R-P3 **H** | Approval of a plan of record in the prompt hook: refuses unless the R-P2 state is complete; structured repeat-back; receipt stored outside the plan, naming the plan digest | M | Opus 5.5 | R-23, R-P1, R-P2 | digest moved after the repeat-back refuses; decider and autopilot receipts refused; writing the receipt does not change the approved bytes |
| R-P7 **H** | Attestation issued at `confirm` over the plan digest (presence key), or recorded from the owner's forge review | M | Opus 5.5 | R-07, R-P3 | a receipt with no attestation is not eligible unattended; an attestation for another digest refuses |
| R-P8 | Attestation verification library used by both executors | S | Opus 5.5 | R-P7 | a fabricated receipt and hashes with no valid attestation are refused by the pipeline and by the broker |
| R-P4 | Envelope matcher: decider binds values, script checks the bounds from the real artifact (plan JSON attribute paths, workflow file and pinned dependencies) | M | Opus 5.5 | R-31, R-D1, R-41 | an unlisted attribute change, an unknown or sensitive value, an input off its list and an unpinned dependency each stop |
| R-P4b | Money ledger and reservations: atomic reserve before dispatch, release only by reconciliation | M | Opus 5.5 | R-P1 | the action that would pass a cap is refused; a race for the last of a cap has one winner; could-not-tell keeps the reservation |
| R-P5 | Standing plans: expiry, use cap, void on tier, account or workflow drift | S | Opus 5.5 | R-P4, R-P4b, R-A1 | expired, exhausted and voided plans refuse; exact-only kinds cannot be standing |

### Phase 6 — Service accounts and admin use (new in revision 3)
| ID | Title | Size | Model | Depends | Acceptance |
|---|---|---|---|---|---|
| R-A1 | Account registry, naming convention, workspace enrolment (checkout or authenticated CI workload), tier map references; existing `unattendedCloud` rows migrated | M | Opus 5.5 | R-05, R-32 | a second checkout with the same remote is refused; a name off the convention is rejected |
| R-B1 | `crew-broker`: local service under its own OS account, closed request protocol (one action of a plan, one operation of a need), no request that returns a credential; same-user fallback marked weak | M | Opus 5.5 | R-A1, R-P8, R-43 | a request for a credential is refused; a second write needs its own request and checks; the session's user cannot read the broker's references |
| R-B2 | Broker install and enrolment as a planned step, both install scripts untouched; removal path | S | Sonnet 5.5 | R-B1 | install reports "already installed" on a second run; without it production writes go to the pipeline only |
| R-A2 | Permission profiles and `crew_accounts.py verify`, AWS: effective permissions including inherited ones equal the profile; checked at issuance | M | Opus 5.5 | R-A1 | drift, an inherited extra right and a write right on a read account give FAIL; an account not made from a profile gives COULD-NOT-TELL; neither is ever issued |
| R-A4 | Profiles and verify, GitHub tokens and App installations | S | Sonnet 5.5 | R-A1 | a token with wider scopes than its profile fails |
| R-A5 | Verify, Azure | M | Opus 5.5 | R-A2 | same as R-A2 |
| R-A6 | Issuing read and dev and QA write credentials to a child: references, environment or `credential_process`, redactor on everything published | M | Opus 5.5 | R-A1, R-A2, R-33 | no credential in arguments; a credential planted in child stderr, a subprocess argument and an evidence post is caught before publication; nothing issued on FAIL or COULD-NOT-TELL |
| R-A7 | Admin need record and checks per reason code on provider evidence, exact operations with payload digests; report-only | M | Opus 5.5 | R-A1, R-A2, R-P6 | a probe that cannot tell is not a need; a conforming name or empty registry is not evidence; a need outside a plan of record is refused except the grantable-profile case |
| R-A8 | Admin operations through the broker, AWS: each mechanism verified against the provider first; time box, source identity, session policy, permissions boundary; one operation per request with its payload digest | M | Opus 5.5 | R-A7, R-B1, R-P8 | the right principal with a different policy, boundary or trust is refused; second use refused; an operation outside the list fails at the provider |
| R-A8b | Admin close: provider audit pull, comparison with the need's operations and payloads, quarantine, evidence post, automatic close | M | Opus 5.5 | R-A8 | an unlisted call in the audit quarantines the new accounts and raises `needs-owner` |
| R-A9 | Onboarding plan template: enrol the workspace and the admin account, create the read and write accounts per tier from profiles, list grantable profiles, set the owner alert | M | Opus 5.5 | R-P1, R-A8b | registry rows written from the provider response; verify PASS before first use |
| R-AA | Temporary accounts: provider-enforced expiry, or broker-held credential refused after the deadline; sweep as clean-up from `/crew:status`, the pipeline and the broker timer | M | Opus 5.5 | R-37, R-A1, R-A8b | with the sweep switched off, an expired account and a credential issued before expiry do not work |
| R-AC | Admin operations on providers without session scoping, through the broker, marked weak | M | Opus 5.5 | R-A7, R-B1 | closed operations and payload digests still enforced by the broker; the row is marked weak |
| R-AB | Switch on: verified scoped accounts authorised; production read always | S | Opus 5.5 | R-A2, R-A6, R-35 | production read runs unattended in both modes; an unverified account does not |

### Phase 7 — Production
| ID | Title | Size | Model | Depends | Acceptance |
|---|---|---|---|---|---|
| R-40 | `crew_prodwindow.py` | S | Opus 5.5 | R-32 | clock tables; missing config asks |
| R-41 | Terraform action manifest from the saved plan | M | Opus 5.5 | R-30 | same address, different value fails |
| R-42 | Backup evidence, first provider (AWS RDS snapshots) | M | Opus 5.5 | — | failed, stale or wrong-target snapshot fails |
| R-43 | `crew_prodcheck.py` receipt per operation, prior state, attempt | M | Opus 5.5 | R-41, R-42 | reuse refused |
| R-44 | Pipeline executor template: the protected Environment holds the write account; the privileged workflow, check script and manifest reader come from a protected ref; the job verifies the attestation | M | Opus 5.5 | R-43, R-P8 | where used, the session holds no production write credential; changing the candidate's workflow, check script or artifact after approval fails |
| R-45 | Production queue with durable states and atomic reservation of the action, the plan use and the money amount, held until reconciliation | M | Opus 5.5 | R-40, R-P4b | crash after remote success does not dispatch twice or free the reservation; two actions cannot both take the last of a cap |
| R-46 | Switch on unattended production, by pipeline or broker; eligibility is machine timing and the plan's window and `unattended: yes` | S | Opus 5.5 | R-39, R-43, R-44, R-45, R-AB, R-B1, R-P5, R-P8, R-48 | no plan, no attestation, an unverified account or a failed check each refuse; refused just outside each of the three boundaries, on both executors |
| R-47 | Owner-declared, scoped emergency | S | Opus 5.5 | R-23, R-43 | agent- or decider-declared refused; backup still required |
| R-48 (new) | Irreversible actions: listed exactly in the plan, cap and preflight, one use | S | Opus 5.5 | R-43, R-P1 | refused: unlisted, over cap, in an envelope, in a standing plan, replayed, missing or failed preflight, and a required backup whose probe failed; allowed: the exact approved action with matching prior state and a passing preflight |

### Phase 8 — Locations, clean-up, handoff
| ID | Title | Size | Model | Depends | Acceptance |
|---|---|---|---|---|---|
| R-50 | Init registers the owner-local worktree hook; both lane roots covered | S | Sonnet 5.5 | R-04 | no edit to shipped `hooks.json` |
| R-51 **H** | Reviewer snapshot: read-only input, separate output | M | Opus 5.5 | R-04, R-10 | reviewer cannot write the developer's tree or git state |
| R-52 | Coordinator clean-up with checkout lock | M | Sonnet 5.5 | R-04, R-72 | two lanes cannot switch the same checkout |
| R-53 **H** | Verify gate: candidate-sha clean tree, explicit NOT VERIFIED, both shells | M | Opus 5.5 | R-04 | wrong bytes never credited |
| R-54 **H** | Scope guard allowance for the active ticket's handoff file | S | Opus 5.5 | — | other tickets' files refused |
| R-55 | Handoff format and `/crew:handoff` commit | S | Sonnet 5.5 | R-54 | file validates |

### Phase 9 — Sandbox
| ID | Title | Size | Model | Depends | Acceptance |
|---|---|---|---|---|---|
| R-60 | `crew_sandbox.py run` | M | Opus 5.5 | R-04, R-02 | must-block and must-allow tables |
| R-61 | Disposable-VM host-change test and suite hygiene | M | Sonnet 5.5 | R-60 | never mutates a shared runner |
| R-62 | Both eval builders and a Compose template use the launcher | S | Sonnet 5.5 | R-60 | argv comes from the launcher |
| R-63 | Raw `docker run` tripwire in the cloud guard | S | Sonnet 5.5 | R-60 | forbidden mount asks |
| R-64 | Worker-in-container mode for unattended lanes | M | Opus 5.5 | R-60 | worker has no daemon socket and no host shell |

### Phase 10 — Orchestrator and workflow
| ID | Title | Size | Model | Depends | Acceptance |
|---|---|---|---|---|---|
| R-70 | `crew_triage.py` | S | Sonnet 5.5 | — | the artifact's cases as tables |
| R-71 | Role defaults, escalation by round, re-route and restart counters | S | Sonnet 5.5 | R-70 | third call and second restart refused |
| R-72 | Status maps and event ids for all four trackers | M | Opus 5.5 | — | no duplicate post after a timeout |
| R-73 | Phase state machine; documentation allowlist | M | Opus 5.5 | R-70, R-72 | a command file is not a document |
| R-74 | Wave: lanes run Implement to Fix; coordinator does the rest | M | Sonnet 5.5 | R-73, R-50 | never-list test still passes |
| R-75 | Advisor review of the spec before approval (the owner's for serious work, the person's or the decider's otherwise) | S | Sonnet 5.5 | R-73 | separate session; verdict on the ticket; an advisor verdict is never the approval |

### Phase 11 — Checks
| ID | Title | Size | Model | Depends | Acceptance |
|---|---|---|---|---|---|
| R-80 | Tiers and slices in `gate-runner.py` | M | Sonnet 5.5 | — | selected set covered exactly once; cross-cutting rules kept |
| R-81 **H** | Verify gate: fast per round, heavy at Gate, shard completeness | M | Opus 5.5 | R-80, R-53 | missing shard is not verified |
| R-82 | Web test and doc slices; smoke template | S | Sonnet 5.5 | R-80 | named slices selected by path |

### Phase 12 — Plain language
| ID | Title | Size | Model | Depends | Acceptance |
|---|---|---|---|---|---|
| R-90 | Refusal template applied to guard reasons | S | Sonnet 5.5 | R-35 | each reason fits the template |
| R-91 | `/crew:help` and `/crew:status` for owners | S | Sonnet 5.5 | R-25 | waiting items first |

### Phase 13 — Configuration guide shipped in the plugin (new in revision 3; starts right after Phase 0)
| ID | Title | Size | Model | Depends | Acceptance |
|---|---|---|---|---|---|
| R-C1 | Registry completeness: every key has a plain-language line, allowed values, a layer class and its arrival version | S | Sonnet 5.5 | — | a key missing any of the four fails the check |
| R-C2 | Generator writes `config.blank.json`, `global.blank.json`, `keys.json` and `template.annotated.md` into `plugin/crew/docs/configuration/`; `--check` covers them | M | Opus 5.5 | R-C1 | template keys equal registry keys per layer; each exclusion named with a reason; applying a blank to an empty layer leaves the effective policy unchanged; a one-byte edit fails `--check` |
| R-C3 | `guide.md`: layers, owner set-up, the AI procedure, worked examples as files validated in CI | M | Sonnet 5.5 | R-C2 | repo examples pass `--check`, machine examples `--check-global`; the procedure names only commands that exist |
| R-C4 | `CONFIG.md` becomes a generated index under its cap; prose and family tables move to the guide; budgets read and set | S | Sonnet 5.5 | R-C2 | `CONFIG.md` under 600 lines with room for the new key families |
| R-C5 | Pointers from crew-setup, `/crew:init`, `/crew:help`, `/crew:config`; `crew_config.py --guide` | S | Sonnet 5.5 | R-C3 | each surface names the path under `${CLAUDE_PLUGIN_ROOT}` |
| R-C6 **H** | Session-start line in `crew_hook.py` that prints a status file other tickets write to, plus the line for a missing or invalid config naming the guide | S | Opus 5.5 | R-C5 | absent when nothing applies; later status lines need no harness change; harness suites pass |
| R-C7 | Built HTML, DOCX and PDF from the same source | S | Sonnet 5.5 | R-C3 | built files pass `build.py --check` |
| R-C7b | Publish the Claude Docs "Configuration Guide" from the same source and bring the existing "Crew Config Reference" artifact into line; state who may publish and how it is checked | S | Sonnet 5.5 | R-C7 | the doc exists, names its source commit, and a check compares it with the built guide |

**Order.** Phases are delivery groups, not barriers: the real order is each ticket's own Depends column, and a ticket may start as soon as the tickets it names have landed. Three prerequisites are pulled forward because other groups lean on them: R-32 (protected policy), R-73 (stage state machine) and R-P6 (serious classifier) are scheduled with Phase 0's follow-ons. Phase 13 (the configuration guide) starts beside Phase 1, because every later ticket that adds a key writes into it. Phases 1, 10 and 11 can run beside Phase 2. The safety-critical chain is: Phase 2, then R-D1 to R-D5 and R-P1 to R-P8, then R-A1 to R-B2, then Phase 7. Each switch-on ticket (R-D4, R-39, R-AB, R-46) names every control it turns on; a kind whose control has not landed stays off. A script checks the Depends columns for unknown ids and cycles (run on this file: none).

Harness tickets: R-10, R-11, R-12, R-14, R-20, R-22, R-23, R-D5, R-P3, R-P7, R-C6, R-51, R-53, R-54, R-81 (15). That count is a floor: the check reads paths, so any ticket found at implement time to touch a HARNESS path (`crew_ticket.py`, `crew_hook.py`, `hooks.json`, `approval_hook.py`, `crew_runapproval.py`, the review and gate files, `tests/sabotage*.py`) gets a harness-only PR split off first. R-C6 exists so that later session-start lines (R-3A) write to a status file and need no harness change. Sabotage companions are expected for R-32, R-33, R-35, R-37, R-43, R-60, and new: R-D1, R-P4, R-P4b, R-P8, R-A6, R-A7, R-A8, R-B1, R-M4.

**Totals.** 102 tickets: phase 0 seven, 1 five, 2 seven, 3 nine, 4 twelve, 5 nine, 6 fourteen, 7 nine, 8 six, 9 five, 10 six, 11 three, 12 two, 13 eight. 43 are new in revision 3 (R-06, R-07, R-48, R-M1 to R-M4, R-D1 to R-D5, R-P1 to R-P8 and R-P4b, R-A1, R-A2, R-A4 to R-AC, R-A8b, R-B1, R-B2, R-C1 to R-C7 and R-C7b); eight of those were added by the revision-3 cross-review.

---

## 7. Risks

1. The plan is larger again (59 to 102 tickets) because the owner's rules need a decider, a plan-of-record flow with an attestation, an account registry, a broker and a shipped configuration guide.
2. Same-user forgery remains for layers 1 and 2, and now matters more (see 7.1).
3. Fifteen harness PRs plus companions is the slowest path.
4. The cause of the host damage may not reproduce.
5. Docs load on every crew change; CONFIG.md has one line of headroom.
6. Tracker event posting adds failure modes mid-task.
7. Sizes are estimates; R-37, R-42, R-44, R-B1 and R-P2 are the likeliest to split again.
9. The broker needs one administrator-level install per machine and the attestation needs either a presence key or a second forge account. Until both exist, serious work runs attended or through the pipeline only (R-07 measures the attestation forms).
8. The AWS mechanisms in 4.14 are inferred until R-A8; a provider that lacks one moves that control from "boundary" to "tripwire" for that provider.

### 7.1 Where the owner's rules reduce safety against revision 2, and what compensates

| # | Reduction | What still holds, by script | What is left |
|---|---|---|---|
| 1 | A model, not the owner, answers routine asks | closed outcomes; serious, one-way and unknown-tier classes never decider-eligible; separate run with no write tools; exact model id verified from the runtime's report; sticky denials; per-ticket cap; every decision on the evidence trail | a hostile repo can talk the decider into a wrong routine decision in dev or QA |
| 2 | Plans may hold envelopes and be standing, so the owner no longer approves every concrete value | per-kind bounds checked against the real artifact (attribute paths, enumerated inputs, pinned dependencies); exact-only for money, permissions, accounts, admin, irreversible; expiry and use cap; void on drift | a bad change that fits inside an approved envelope runs |
| 3 | Production writes run with nobody watching, using a service account on the owner's own machine or pipeline (revision 2: pipeline or sealed launcher only, Linux and WSL only) | the write credential stays in the pipeline or the broker, which performs one checked operation per request; attested plan; account verified at issuance; reservation | with the same-user broker fallback, or for someone with administrator rights on the machine, the write account is reachable without crew's checks; damage is limited to that application |
| 4 | A change with no provable backup may run unattended | only when the attested plan lists that exact action as irreversible, with a cap and a passing preflight; shown separately at approval; one use; a failed required backup always refuses | an approved irreversible action that turns out to be wrong cannot be undone |
| 5 | Admin credentials are usable by automation | need checked on provider evidence; broker performs each operation with the named payload digest; provider time box, source identity and session policy where supported; one at a time; audit compare and quarantine; provider-side alert to the owner | on providers with no session scoping the broker is the only control; with the same-user fallback a process as the owner's user can use the admin credential directly |
| 6 | Native Windows may run unattended production | the broker, not the sealed launcher, is the boundary | none beyond row 3 when the broker is installed |
| 7 | A temporary account may exist where the provider cannot expire it | credential never leaves the broker, which refuses use after the deadline; 24 h ceiling; sweep deletes it | the account object exists until the sweep runs, with no usable credential |
| 8 | A decider-approved plan unlocks non-serious dev and QA work | never a serious class; dev and QA only; tier is machine-owned | a self-directed mistake in dev or QA |
| 9 | `directive` mode stops less often | same policy table, same grant ceiling, explicit `unattended` field; parity suite; evidence trail; exceptions-first status | fewer chances for a person to notice something odd |
| 10 | Read access to production is always allowed | read profile verified at issuance to have no mutating action; credential stores stay unreadable | production data can be read, and so copied, by any agent session; a read cannot be undone either |

---

## 8. Decisions

### 8.1 Defaults this plan proposes in place of the old owner questions

Proposed by the planner (Fable 5.2, `claude-fable-5-2`) with GPT 6.2 Astra advising. They are proposals: no crew decider exists yet, so no decision record exists either. They take effect when the owner approves this plan, and each is a protected machine key the owner can change later.

| Was | Proposed default | Basis |
|---|---|---|
| D2 reply forms | one reply or the decider for routine asks; `yes`, repeat-back, `confirm` for a plan of record and the one-way list | feedback points 2 and 3 |
| D3 reach of "planned = approved" | attested, human-approved plan of record for serious work, exact or envelope, standing allowed; decider-approved plans for non-serious dev and QA | points 2, 3, 4 |
| D4 grant durations | one 24 h ceiling; suggested 8 h in `directive`, 1 h in `guided`; provider expiry | point 2 |
| D5 production credentials | scoped service accounts; the pipeline or the broker performs production writes; native Windows allowed | point 5 |
| D6 unprovable backup | runs when the plan of record lists the exact action as irreversible with a cap and a passing preflight | point 3 |
| D7 who defines production | machine-owned config; a repo may only tighten | recommendation applied |
| D8 sandbox strength | launcher, then unattended workers inside the container | recommendation applied |
| new: cost threshold for "money" | 50 USD a month estimated; cannot estimate counts as over | default |
| new: plan expiry, standing plan limits, admin time box | 30 days; 30 days and a use cap, 90 max; 15 minutes, 60 max | defaults |

### 8.2 What the owner must still decide

| # | Question | Options | Recommendation | Why it stays with the owner |
|---|---|---|---|---|
| O1 (was D1) | Guards on by default, against the repo rule that a blocking hook defaults off | (a) on at install; (b) off until `/crew:init`, whose default answer is on; (c) stay off | (b) | it rewrites an owner rule in CLAUDE.md, which no agent may authorise |
| O2 | Operating mode | (a) `guided`; (b) `directive` | `guided` for anyone running `/crew:init` fresh; `directive` only when the machine's owner opts in | switching to `directive` is on the one-way list |
| O3 | Are my readings right: Fable 5.2 counts as "Opus 5.5 or higher"; the serious list in 4.13; a production write still needs a plan even with a properly scoped account | (a) yes; (b) corrections | (a) | it defines what the system may decide alone |
| O4 | Where the production write and admin credentials are kept on a machine with no pipeline | (a) a broker under its own OS account (one administrator-level install); (b) a same-user broker, weaker; (c) pipeline only | (a) | (a) installs a system service, which the repo's install rule reserves for the owner; (b) accepts the residual in 7.1 rows 3 and 5 |
| O5 | The admin accounts themselves | which admin account exists per provider and where its credential is referenced; whether to run the onboarding plan (R-A9) | — | crew cannot hold what it has not been given |
| O6 | How your approval of a plan of record is attested | (a) a presence key (one touch or prompt at `confirm`); (b) your review of the plan commit from your own forge account, with agents on a separate account; (c) neither: serious work runs attended | (a), with (b) where the pipeline is the executor | without one, a process running as your user can fabricate a plan approval |

Still the owner's at run time, by design and not open questions: approving and amending each plan of record; any widening of guard or policy config; declaring an emergency.

---

## 9. What I did not verify

- The cause of the `/bin/bash` and `/usr/bin/bash` damage.
- Which layer refused the owner's IAM changes.
- A failing Kimi-first review; and the Astra-reported lines marked [A] (Kimi's in-launch probe, dispatch dual opt-in, marker ordering, `spend` session argument, verify.json lower bounds).
- That the client shows a blocked prompt's hook text to the owner, and that a plain reply reaches the hook unchanged (R-21 measures it).
- Any test suite. Nothing was run; `drift-detection.sh` was not run.
- The owner's actual config layers; defaults were read from code.
- That GitHub Environments and Terraform Cloud are available on the owner's work repos.
- Sizes: estimates, not spikes.
- Added in revision 3: whether an owner-presence signing key is available and scriptable on the owner's machines, and whether agents already use a forge account separate from the owner's (R-07); what installing a service under its own OS account takes on the owner's Windows machine; what a headless run reports as the answering model (R-06); the exact Opus 5.5 model id; every AWS mechanism named in 4.14 (R-A8); how Azure, GitHub and the owner's other providers scope and time-box an admin session; which admin and service accounts the owner already has; that a provider-side alert on admin sessions can be set up in the owner's accounts.
- Verified in revision 3 by reading the clone at `5558cac`: the `unattendedCloud` keys and that there is no production write entry; the launcher's refusal of `:user/` identities; that no approval receipt carries a runtime-reported model id; the `approved_via` values; that `crew_ticket.py` is a HARNESS path; the shipped config templates and their five missing keys; that `/crew:init` writes only the repo file; the installed plugin copy's version and contents.
- Not verified: the existing "Crew Config Reference" artifact's contents; whether a Claude Docs "Configuration Guide" exists beyond the first 200 artifacts listed; what `BUDGETS.md` requires of new files under `plugin/crew/docs`.

---

## 10. Cross-review log

Reviewer: GPT 6.2 Astra (`codex exec -m gpt-6.2-astra -s read-only`, first attempt, no fallback model needed). Raw output: `astra-review.txt`; final message: `astra-last.txt`. Verdict on revision 1: reject as written. I re-read the code for findings 1, 24, 29 and 30 before accepting them.

| # | Sev | Finding | Result | What changed |
|---|---|---|---|---|
| 1 | crit | A current plan hash does not prove the owner approved; autopilot and cli approvals exist | Accepted (verified `crew_ticket.py:1007-1037`) | 4.4: only `user-prompt` approvals unlock privileged actions; test added |
| 2 | crit | Matching on kind, verb, target, environment omits what the operation does; no use count | Accepted | 4.4 closed schema, all effect-bearing fields bound, `uses` |
| 3 | crit | Permission extension allowed when a plan merely names the target; stored revoke commands | Accepted | 4.4: principal, permission set, scope, expiry in the plan; provider expiry and grant id only |
| 4 | crit | Repo can influence tier classification; unknown must stay closed | Accepted | 4.3 machine-owned tiers; deny-first order |
| 5 | crit | Non-empty file is not a backup; receipt reusable; blind auto-rollback | Accepted | 4.5 provider-verified backup, per-operation receipt, reconcile first |
| 6 | crit | An agent with production credentials defeats per-action approval | Accepted | 4.0 layers; 4.5 executor; D5 |
| 7 | crit | A launcher is not isolation; linked worktree shares git state | Accepted in part | 4.6 reviewer snapshot; 4.7 says what the launcher is not; R-64. Not accepted: removing the host shell from the owner's interactive sessions, which would stop normal work |
| 8 | high | Numbered confirms can drift; trailing words; raw text display | Accepted | 4.2 whole-prompt grammar, frozen set, structured display |
| 9 | high | Spend weaker than existing flow; legacy markers | Accepted | 4.2 bindings at spend; no marker for new classes |
| 10 | high | Unattended request has no resume path; long TTL | Accepted | 4.2 request vs receipt lifetimes, resume, cancel |
| 11 | high | Owner-wide verify trust at init is weak provenance | Accepted | 4.2 hash stays default; R-26 |
| 12 | high | SQL read classifier cannot prove a read; "read any file" vs credential stores | Accepted | 4.3 read-only database identity; credential denial kept |
| 13 | high | Terraform sidecar lacks counts and addresses | Accepted | 4.5 manifest from the saved plan; R-41 |
| 14 | high | Policy precedence unresolved; emergency unscoped | Accepted | 4.3 evaluation order; 4.5 scoped emergency; R-47 depends on R-43 |
| 15 | high | Config denylist incomplete; secret claim too strong | Accepted | 4.3 protected set by effective policy; narrowed secret claim |
| 16 | high | Repo wins `worktrees.root`; one-time realpath check | Accepted | 4.6 machine-owned roots; deletion helper |
| 17 | high | Clean restricted run proves nothing; canary unsafe on shared runner | Accepted | 4.7 disposable VM; "not reproduced"; both eval builders |
| 18 | high | Clean sibling may verify other bytes | Accepted | 4.6 candidate sha and fingerprint; NOT VERIFIED state |
| 19 | high | Lanes cannot approve or merge, yet got those phases | Accepted | 4.8 lanes run 4 to 6; coordinator the rest; lock |
| 20 | high | Queue lacks claim, recovery, idempotency | Accepted | 4.5 durable states and operation id |
| 21 | high | One guard per lane is not testable | Accepted | R-01 decision cases per operation |
| 22 | high | Harness check reads paths; R-54 mixed | Accepted | R-54 / R-55 split; sabotage companions; owner-local hook registration |
| 23 | high | New allows before their controls; R-34 and R-41 too big | Accepted | inert-first rule; R-39 and R-46 switch on last; grants and backup split by provider |
| 24 | medium | Wave root conflict already resolved | Accepted (verified `crew_wave.py:965-989`) | 2.4 corrected; R-50 narrowed |
| 25 | medium | Kimi already probes; fallback fixture contradicts the interlock | Accepted | 4.1 one probe per attempt; fixtures corrected |
| 26 | medium | Crew uses the forbidden git flags itself; docs path covers instruction files | Accepted | 4.3 note and test; 4.8 allowlist |
| 27 | medium | `seconds` has lower bounds; docs under crew match the marketplace rule | Accepted | 4.9 |
| 28 | medium | Files tracker lost `cancelled` / `superseded`; four trackers | Accepted | 4.8; R-72 |
| 29 | medium | Controls with no ticket | Accepted (verified `crew_keys.py:151-156`) | R-14, R-71, R-75, R-13, R-90/R-91 split |
| 30 | low | Counts wrong; CONFIG.md is 599 lines; R-23/R-25 mix-up; no log | Accepted (verified, 599) | counts redone; 2.7 corrected; this log |

---

## 11. Cross-review log, revision 3

Reviewer: GPT 6.2 Astra (`codex exec -m gpt-6.2-astra -s read-only`, `codex-cli 0.167.0`, first attempt, exit 0, no fallback model). It was asked to review only the revision-3 changes and whether any loosening reopens a failure mode, and told the owner's rules are not up for debate. Raw output: `astra-review-r3.txt`; final message: `astra-last-r3.txt`; prompt: `astra-prompt-r3.txt`. Verdict: "revise before implementation. The owner's automation rules can stand, but approval provenance, operation-bound execution and the switch-on dependencies need enforceable contracts first." 29 findings: 4 critical, 17 high, 6 medium, 2 low. I re-read the code for findings 25, 28 and 29 before accepting them. Astra has not seen the changes below.

| # | Sev | Finding | Result | What changed |
|---|---|---|---|---|
| 1 | crit | A same-user process can fabricate the plan, its hashes and its `user-prompt` receipt | Accepted | 4.13 attestation (presence key or forge review), verified by both executors; R-07, R-P7, R-P8; owner decision O6 |
| 2 | crit | An hour-long application-wide write credential lets a second write skip the checks | Accepted | 4.5 and 4.14: the session never gets a production write credential; the pipeline or the broker performs one checked operation per request; R-B1 |
| 3 | crit | A worker that can resolve the admin reference can skip `open`; on a weak provider a copied credential outlives the launcher | Accepted | 4.14 broker under its own OS account holds the admin reference and makes the calls; R-B1, R-B2; O4 |
| 4 | crit | Rule 4 let an open need pass before the serious check; right principal, wrong policy or trust | Accepted | 4.3 rule 4 is a prerequisite only; need binds exact operations and payload digests |
| 5 | high | 4.2 put unplanned serious work on the two-prompt list while 4.3 said needs-plan | Accepted | 4.2 corrected; spend test in R-D5 |
| 6 | high | A filled template does not prove an eligible model planned or the human took part; R-P3 could land without R-P2 | Accepted | 4.13 state record with planner run records and the owner's prompt ids; R-P3 depends on R-P2 |
| 7 | high | No payment or account-creation kind; prose sections not joined to operations | Accepted | 4.4 typed operations; template sections 5 to 7 are generated views; exactly-one-match rule |
| 8 | high | Address prefix and verb do not bound a Terraform update; workflow digest does not bound inputs or dependencies | Accepted | 4.4 per-kind envelope fields checked against the real artifact |
| 9 | high | Running total races; a crash can free a landed action | Accepted | 4.4 reservations; R-P4b, R-45 |
| 10 | high | Crew-held expiry depends on a sweep that may never run | Accepted | 4.4: provider-enforced, or the credential stays in the broker; test with the sweep off |
| 11 | high | A remote digest is a copyable string | Accepted | 4.14 workspace enrolment; two-checkout test |
| 12 | high | Digest match or one failed write does not show effective scope; cached PASS goes stale | Accepted | 4.14 permission profiles, effective permissions, checked at issuance; no issuance on FAIL or COULD-NOT-TELL |
| 13 | high | Redaction in the broker does not stop a child leaking its own credential | Accepted | 4.14 two classes: production write and admin never leave the executor; the narrower claim for the rest is stated, with end-to-end tests |
| 14 | high | One-step reply has no selector with two pending requests | Accepted | 4.2 reply bound to the request that was shown; letter required otherwise |
| 15 | high | Mode changed grant caps and the unattended default | Accepted | one ceiling; `unattended` explicit with no default; R-M4 follows ask rows through |
| 16 | high | "In a window" versus "any time outside hours"; plan window and `unattended` not required | Accepted | 4.5 eligibility is the intersection of three; boundary tests |
| 17 | high | Tier rule would admit an older Opus; R-06 only named the fallback; 8.1 claimed decisions with no record | Accepted | catalog of exact owner-confirmed ids; R-06 exercises both sources; 8.1 relabelled as proposals |
| 18 | high | Temporary account rules disagreed across 4.4, 4.13, 4.14; a name or empty registry is not evidence | Accepted | account creation is plan-bound in every tier; needs checked on provider evidence; admin account enrolled by the owner |
| 19 | high | Switch-on tickets lacked their controls as dependencies | Accepted | R-D4, R-39 (per kind), R-46 dependencies |
| 20 | high | A protected Environment can release its secret to candidate-controlled code | Accepted | 4.5 privileged workflow pinned to a protected ref; R-44 test |
| 21 | high | R-48 acceptance too thin | Accepted | R-48 refusals and one positive case |
| 22 | medium | Writing the approval into the plan changes the hashes it approves | Accepted | receipt stored outside the plan |
| 23 | medium | Phase ordering had cycles through R-32 and R-73 | Accepted | phases are delivery groups; three prerequisites pulled forward; cycle check |
| 24 | medium | R-3A lacked producer dependencies; R-D4 inbox criterion ignored `guided` | Accepted | both rows |
| 25 | medium | Harness classification of session-start and sweep features | Accepted (verified `scripts/check-tooling-pr.py`: `crew_ticket.py` and `crew_hook.py` are HARNESS) | R-C6 becomes the one harness ticket that reads a status file; R-3A writes to it; sweep no longer runs from session start; the H count is stated as a floor |
| 26 | medium | R-A8, R-P4, R-C7 too big | Accepted | split into R-A8 and R-A8b, R-P4 and R-P4b, R-C7 and R-C7b |
| 27 | medium | Arrival versions not required; a copied blank could change policy | Accepted | R-C1, R-C2, R-C3 |
| 28 | low | `/crew:init` writes only the repo file; a global walkthrough and some procedures already exist | Accepted (verified `skills/crew-setup/SKILL.md:170-188`, `CONFIG.md:31-90`) | 4.15 baseline corrected; deliverable described as a consolidated, findable guide |
| 29 | low | "The only `--model` uses" was too broad | Accepted (verified by grep) | 2.8 narrowed |

Net effect of the review on the design: revision 3's first draft trusted a file for the owner's approval and handed credentials to the session. The reviewed version keeps every owner rule and adds two things the owner must choose (O4, O6): where the powerful credentials are kept, and how his approval is attested.
