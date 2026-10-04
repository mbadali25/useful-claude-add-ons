# Cloud session tickets — hand-back file

Session: https://claude.ai/code/session_016wQA2o38aSB65bpjaGpMVJ · started 2026-10-04 11:12 UTC
Last updated: 2026-10-04 (live; refreshed as PRs move)

Use this file to update your local tracker. One row per ticket. "Head" is the PR branch head when this file was written. Versions on unmerged PRs are **placeholders**; the real version is set to main+1 at landing.

## Status words

| Status | Meaning |
|---|---|
| merged | On `main`. Close the ticket. |
| ready to land | Review clean on the current head. Waiting its turn in the one-at-a-time train. |
| in review | Built or fixed; an adversarial review of the current head is running. |
| fixing | A review found BLOCK/FIX items; the builder is fixing them. |
| building | Builder working from the spec. |
| bundled | Built inside another PR (harness bundle). Close with that PR; its own PR closes at landing. |
| not started | Spec-only draft PR; no code yet. |
| closed | PR closed without merging, on your instruction. |

## New ticket IDs minted this session (you said: start untracked work at L-1500)

| Ticket | What | PR | Status |
|---|---|---|---|
| L-1500 | Windows CI: concurrent mint dies on a delete-pending lock name; exact-1s timing assertion | #392 | merged (crew 1.0.324) |
| L-1501 | Windows CI: sabotage mutations for Lock's delete-pending branch (harness-only) | #393 | merged (crew 1.0.325) |
| L-1502 | *Proposed:* `promote-gate.sh` lets a deploy through when `_common.sh` fails to load (pre-existing on main; found reviewing #398) | none yet | needs ticket in your tracker |

| L-1503 | HIGH: `promote-gate.ps1` gives no gate on PowerShell when an environment's `deploy` string holds a `[set]` (e.g. `jq .items[0]` never matches itself) or an unreadable pattern (`[`, `[]`, `[z-a]` throws, iteration skipped). Pre-existing; found reviewing #407. | #489 | in review |

| L-1504 | Harness-only: approval hook / scope guard accept only the owner's typed `/crew:autopilot sleep`, then unlock loosening in manual sleep (L-0652 ships tighten-only until then). Owner decision 2026-10-04. | none yet | needs ticket in your tracker |

Next free untracked ID: **L-1505**.

## Merged this session

| Ticket | PR | Merge commit | crew |
|---|---|---|---|
| T-0048 | #360 | e9364a70 | 1.0.323 |
| L-1500 | #392 | ce235468 | 1.0.324 |
| L-1501 | #393 | baf193aa | 1.0.325 |
| L-0522 | #377 | f3f319d1 | 1.0.326 (L-0522 slice 1 of 3) |
| T-0069 | #352 | b863b773 | 1.0.327 |
| T-0066 (part 1 of 2) | #351 | 86d96fa1 | 1.0.328 |
| L-0688 | #405 | 66be99cd | 1.0.329 |
| T-0096 (slice 0) | #398 | 3c4ccd2f | 1.0.330 |

## Closed without merging (your instruction)

| Ticket | PR | Note |
|---|---|---|
| T-0104 | #274 | Closed; spec stays in `docs/handoff/cloud/`. |
| T-0500 | #275 | Closed; spec stays in `docs/handoff/cloud/`. |

## In the landing train (built, reviewed or under review)

| Ticket | PR | Head | Status | Notes |
|---|---|---|---|---|
| T-0017 | #356 | 5e37f872 | ready to land | Stacked on #396 (T-0016). Carry NIT: stdout backslashreplace for non-ASCII refusal reasons. |
| T-0059 | #366 | e14b5a45 | ready to land | Stacked on T-0052 (#364). |
| T-0058 | #365 | 16228584 | ready to land | Stacked on #364/#354. Carry: `_gate_stage` must pick stage like `_phase`; `split_report current=` from `_not_current`. Decision: absent sources read as unmeasured (owner-approved). |
| T-0098, T-0109, T-0101 | #418 (H1 bundle) | ea9dcc10 | ready to land (harness, lands alone) | #461 (T-0109) and #422 (T-0101) close at landing. Owner note: also tightens plain `--accept`/`--reject` (refuse multi-line / lookalike `auto:` names). T-0109 Q3 (name only, no owner auth) confirmed not to loosen the gate. |
| T-0045 | #407 | 6cada04c | ready to land | Slice 1 of 8 (`crew_ghdeploy.py check`). `check` now simulates both promote gates. |
| T-0053 | #403 | 791af057 | landing (batch 1, crew 1.0.332) | Slice 1. Decisions taken for you: unknown = strictest per key; non-object block = human; carry: a typo night value (not a policy) reads strictest. |
| T-0047 | #347 | 877ef4b8 | in review | PowerShell fail-closed backstop added. |
| T-0074 | #481 | 858c5336 | ready to land | Slice 1 of 3. OWNER DECIDED Q4 (2026-10-04): as specified, follows autopilot.approval. Review clean. Carry: daily-workflow.md:189 cap-limit wording. Q7 open. |
| T-0057 | #416 | 2eaac674 | ready to land | Carry at landing merge: route the 3 autopilot sites through T-0069's `_route()`, drop `_LINE_BREAKS`, re-review the merge. Printable-ASCII allowlist for free text. Also fixes a main bug: `implement ſ-12` routed to S-12. |
| T-0084 | #450 | 4e9ee867 | landing (batch 1, crew 1.0.331) | Review clean (round 6). Carry: treat a bare `vault:` first line as a pointer attempt. Decisions taken for you: near-miss pointers = malformed; legacy `vaultPath` ignored when a `vaults` block exists. |
| T-0082, T-0080 | #399 (H2a bundle) | ed58c3d9 | building | Harness-only. #475 (T-0080) closes at landing. |

## Review-clean on older bases (catch-up merge + version at their turn)

| Ticket | PR | Head | Notes |
|---|---|---|---|
| T-0035 | #344 | f6a74770 | also bumps localgpu |
| T-0036 | #345 | 0350da69 | stacked on #344 |
| T-0070 | #342 | 904ca36f | |
| L-0509 | #341 | 7dddc79d | |
| L-0526 | #340 | c7f7354d | harness, lands alone |
| L-0582 | #338 | 0d1766b1 | draft; file follow-up tickets |
| T-0039 | #346 | 7983d85a | draft |
| T-0041 | #348 | 4708d96b | |
| T-0011 | #353 | b04bd6b3 | carry: daily-workflow.md:106 "the train never merges"; `since` ×3 + guide.md on re-bump |
| T-0020 | #357 | af805254 | |
| T-0050 | #361 | 5473c6c8 | |
| T-0051 | #362 | 2156b68b | carry: SKILL.md caveat |
| T-0060 | #363 | e62b3577 | stacked on #362 + #395 |
| T-0052 | #364 | 1b0de3cb | |
| T-0063 | #368 | 29889e98 | |
| T-0037 | #394 | 96080457 | carry: status-vocabulary test covers memory-and-obsidian guide |
| T-0049 | #395 | 1b6a6046 | carry: ctypes argtypes; stop Windows walk at a reused parent |
| T-0016 | #396 | d7eb9fbd | carry: CONFIG §14 shared-tty note |

Untouched by owner request: #324 (L-0590, owner WIP). The docs-only notes PR #391 merges last.

## The 91 spec-only handoff drafts (#397–#488)

Build plan with dependencies, harness bundles and blocked list: `docs/handoff/cloud/WAVES-2026-10-04.md` (if present) or this session's `WAVES.md`. Built so far: T-0053 #403, T-0045 #407, T-0096 #398, L-0688 #405, T-0084 #450, T-0057 #416, T-0074 #481, plus bundles H1 (#418) and H2a (#399) — see the train table above.

Tickets with open owner questions that have no recommended answer (need you before planning): L-0639, L-0640, L-0550, L-0551, L-0635 (Q2), T-0074 (Q7).
Held for your go: L-0674 (#404).

| Ticket | PR | Status | Title |
|---|---|---|---|
| L-0540 | #402 | not started (spec only) | T-0094 tooling half: completion_audit.py + scope_guard.py refresh-artifact admission |
| L-0550 | #426 | not started (spec only) | autopilot stops on hold, landing, needs-owner, cancelled/superseded and blocked |
| L-0551 | #446 | not started (spec only) | /crew:status --owner and the waiting line |
| L-0633 | #410 | not started (spec only) | Cross-session dependencies <channel>:<id> in the autopilot wave |
| L-0634 | #412 | not started (spec only) | The wave refuses a ticket whose built-against contract hash no longer matches |
| L-0635 | #415 | not started (spec only) | Sabotage mutations for cross-session contracts and dependencies (tooling PR) |
| L-0636 | #437 | not started (spec only) | Cross-session messaging: an unanswered doorbell reads `could not tell` and is surfaced to  |
| L-0637 | #442 | not started (spec only) | Cross-session messaging: the main session is the hub, lanes never ring a peer |
| L-0638 | #448 | not started (spec only) | Cross-session messaging: sabotage mutations for the bridge script (tooling PR) |
| L-0639 | #409 | not started (spec only) | T-0037 child 1: cancelled and superseded close a ticket; blocked and needs-replan are deri |
| L-0640 | #411 | not started (spec only) | T-0037 child 2: next.md - waiting-on, next, reason, revisit and superseded-by, read into t |
| L-0641 | #413 | not started (spec only) | T-0037 child 3: sabotage mutations for ticket state (closed words, dependency state, next. |
| L-0642 | #486 | not started (spec only) | autopilot's open-questions stop sees through code fences, and stops when it cannot tell |
| L-0643 | #487 | not started (spec only) | sabotage mutations for T-0043's autopilot fixes and the fence parser (tooling PR, lands al |
| L-0644 | #428 | not started (spec only) | crew_ghdeploy.py prepare - refuse or snapshot before a GitHub Actions dispatch |
| L-0645 | #432 | not started (spec only) | crew_ghdeploy.py identify - exactly one new workflow run, or could-not-tell |
| L-0646 | #436 | not started (spec only) | crew_ghdeploy.py watch - pass, fail or unknown from the run and its deploy job |
| L-0647 | #439 | not started (spec only) | crew_ghdeploy.py record and the /crew:promote github sequence |
| L-0648 | #445 | not started (spec only) | promote-gate reads the github entry - the sha input must be the reviewed HEAD |
| L-0649 | #452 | not started (spec only) | autopilot's deploy phase - promote to the first nonProd GitHub environment after the merge |
| L-0650 | #457 | not started (spec only) | wire the GitHub-deploy mutations into the sabotage harness (tooling only) |
| L-0651 | #423 | not started (spec only) | sabotage mutations for the sleep schedule overlay (tooling-only PR) |
| L-0652 | #427 | not started (spec only) | manual /crew:autopilot sleep and wake (state file under git-common-dir/crew, gated on scop |
| L-0653 | #431 | not started (spec only) | sleep log and morning summary (.work/autopilot/sleep-log.md, sleep-note, sleep-summary) |
| L-0654 | #435 | not started (spec only) | sleep deploy override, nonprod only; production always waits while asleep |
| L-0655 | #438 | not started (spec only) | sabotage mutations for manual sleep, the sleep log and the deploy override (tooling-only P |
| L-0656 | #444 | not started (spec only) | sleep overrides for keys that do not exist yet (review policy, held pings) - BLOCKED until |
| L-0657 | #480 | not started (spec only) | T-0055 child 1: CI fails when a built crew guide is stale |
| L-0658 | #463 | not started (spec only) | A `--goal` handoff is checked against the goal file, not the branch and head |
| L-0659 | #469 | not started (spec only) | Bare `/crew:autopilot` finds a running goal when there is no usable handoff |
| L-0660 | #472 | not started (spec only) | Sabotage entries for goal resume: writers, handoff validation, discovery (tooling-only PR) |
| L-0661 | #417 | not started (spec only) | T-0057 child 1: sabotage mutations for the autopilot routing rows (tooling-only PR) |
| L-0662 | #420 | not started (spec only) | T-0057 child 2: plain-text routing rows for autopilot wave, split, sleep and wake |
| L-0663 | #424 | not started (spec only) | T-0057 child 3: sabotage mutations for the wave, split, sleep and wake routing rows (tooli |
| L-0664 | #471 | not started (spec only) | promote-gate.ps1 treats a workflow dispatch of a declared deploy workflow as that deploy |
| L-0665 | #473 | not started (spec only) | promote-gate reads the newest PROMOTIONS.md row for an environment and sha, not the first |
| L-0666 | #449 | not started (spec only) | T-0067 child 1: autopilot stop messages name only owner decisions (a contract test over ev |
| L-0667 | #455 | not started (spec only) | T-0067 child 2: /crew:graph - one command for graph status, the sanctioned refresh and que |
| L-0668 | #460 | not started (spec only) | T-0067 child 3: sabotage mutations for the review policy, the fix phase and the stop contr |
| L-0669 | #470 | not started (spec only) | T-0071 child 1: sabotage mutations for the T-0071 tracker fixes (tooling PR) |
| L-0670 | #483 | not started (spec only) | T-0074 child 1: autopilot approves a successor plan after an automatic reject only when it |
| L-0671 | #484 | not started (spec only) | T-0074 child 2: sabotage entries for the auto-replan policy and the successor-plan check;  |
| L-0672 | #482 | not started (spec only) | sabotage mutations for crew_tracker's per-component identity check (tooling-only PR) |
| L-0673 | #401 | not started (spec only) | T-0082 child 1: the CI receipt's per-command list never reads a missing failure line as PA |
| L-0674 | #404 | not started (spec only) | T-0082 child 2: the verify gate ends a hung rule itself and reports it FAILED (could not t |
| L-0675 | #425 | not started (spec only) | T-0083 child 1: crew passes the repo's project to vault recall and falls back cleanly on a |
| L-0676 | #429 | not started (spec only) | T-0083 child 2: sabotage mutations prove the recall project tests (tooling-only) |
| L-0677 | #456 | not started (spec only) | crew_memory.py save - write the vault note, then turn the native memory into a pointer |
| L-0678 | #462 | not started (spec only) | crew_memory.py migrate and restore - convert existing native memories, previewed and opt-i |
| L-0679 | #466 | not started (spec only) | sabotage entries for crew_memory.py (tooling-only PR) |
| L-0680 | #400 | not started (spec only) | T-0096 child 1: the session hooks (notify, handoff-read, handoff-write, context-watch) inh |
| L-0681 | #406 | not started (spec only) | T-0096 child 2: the verify gate, the scope and completion wrappers and the review gate inh |
| L-0682 | #419 | not started (spec only) | T-0103 child 1: sabotage entries for the config leaf checks, os_error_text and the delete  |
| L-0683 | #440 | not started (spec only) | T-0105 child 1: sabotage rows for migrate's autopilot mapping and note (tooling-only PR) |
| L-0684 | #458 | not started (spec only) | gizmoduck tool lookup: one tool home, and an explicit override beats PATH (external report |
| L-0685 | #468 | not started (spec only) | gizmoduck bootstrap.sh without sudo, and a CI and containers guide (external report item 9 |
| L-0686 | #430 | not started (spec only) | L-0550 child 1: sabotage mutations for autopilot's hold, landing, needs-owner, closed and  |
| L-0687 | #453 | not started (spec only) | L-0551 child 1: the owner list and the waiting line know hold, blocked, landing and needs- |
| L-0689 | #488 | not started (spec only) | promote-gate matches a fragment of a declared deploy command and leaves a false in-flight  |
| T-0027 | #397 | not started (spec only) | T-0010 round-6 accepted findings follow-up: status reads no policy warnings (FIX crew_auto |
| T-0031 | #408 | not started (spec only) | cross-session versioned contracts and `<channel>:<id>` dependencies in the wave (depends o |
| T-0032 | #434 | not started (spec only) | cross-session messaging: the bridge as the doorbell, inbound messages as untrusted data (d |
| T-0043 | #485 | not started (spec only) | T-0004 follow-up: stop message names the refresh; no false INCOMPLETE after owner acceptan |
| T-0054 | #454 | not started (spec only) | full /crew:autopilot guide, its own document, with every owner-requested example (depends  |
| T-0055 | #474 | not started (spec only) | CI enforces crew doc updates: docs touched or "Docs: none - <reason>" declared; built guid |
| T-0056 | #459 | not started (spec only) | autopilot goals survive /clear, branch switches and crashes: every handoff writer emits -- |
| T-0062 | #467 | not started (spec only) | promote-gate judges the tree and ref the deploy actually uses, not CLAUDE_PROJECT_DIR (PRI |
| T-0067 | #443 | not started (spec only) | autopilot runs mechanical steps itself: reviewPolicy fix-and-rereview for single-ticket ru |
| T-0071 | #464 | not started (spec only) | T-0021 accepted-findings follow-up: repo-id case folding merges repos (PRIORITY), file://  |
| T-0080 | #475 | bundled into H2a #399 | sabotage harness bounds memory: two cloud_guard entries read without bound and OOM-killed  |
| T-0081 | #478 | not started (spec only) | crew_tracker vault walk checks every component's identity, not just the vault's, on Window |
| T-0083 | #421 | not started (spec only) | vault recall relevance: prefer this repo's project and concept/decision notes, skip archiv |
| T-0093 | #477 | not started (spec only) | CLAUDE.md truncation paragraph: build_gallery.py:206 re-run can raise OverlayInvalid if a  |
| T-0101 | #422 | bundled into H1 #418 | review prompt's receipts block says 'not yet run (gate follows review)' instead of MISSING |
| T-0102 | #441 | not started (spec only) | how to use Linux tools on a Windows system, and SSM's limits (no oversized payloads trunca |
| T-0103 | #414 | not started (spec only) | T-0075 round-6 follow-up: sabotage entries for the two round-5 leaf checks, apply_delete n |
| T-0105 | #433 | not started (spec only) | crew_migrate maps a 0.20 autopilot key to 1.0's top-level autopilot instead of unmapped.au |
| T-0106 | #447 | not started (spec only) | crew_autoclear_setup apply-migrate --scan-root finds every repo with autoClear.enabled for |
| T-0108 | #451 | not started (spec only) | gizmoduck headless and CI: bootstrap without apt/sudo guidance, tool-home lookup order, sa |
| T-0109 | #461 | bundled into H1 #418 | review_ledger: --reject --by owner can override an owner-accepted receipt (today only a re |
| T-0502 | #465 | not started (spec only) | crew-setup _verify diagrams case renders as root (puppeteer --no-sandbox when EUID=0) and  |
| T-0506 | #476 | not started (spec only) | concurrent pwsh runs corrupt the shared ~/.cache/powershell startup profile; every later p |
| T-0507 | #479 | not started (spec only) | Refresh the 7 code maps (crew, install-scripts, localgpu, marketplace-registration, obsidi |
