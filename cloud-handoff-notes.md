# Cloud handoff notes

Live log of the cloud session working ALL open PRs #323-#379 (session
`session_01YVvVmFJquzLKR26dG6oSQS`, branch `ccr-b039f2bb-6jks7g`, which carries only this file and
merges last). It is pushed after every action: the last log entry is where it stopped. Ticket status
and dependencies are in `pending-tickets.md`. The previous session's log is kept at the bottom.

Last updated: 2026-10-04 10:13 UTC

## Standing rules (owner, 2026-10-03, restated 2026-10-04)

- **Merge rule.** A PR merges only when all three hold: a Sonnet 5 review of its current head has
  **0 BLOCK and 0 FIX** (NITs fine; after a main merge a merge-only review suffices); CI green on that
  head; first in line. Merge commits only, never squash or rebase.
- **Owner 2026-10-04:** merge as I go; build ALL docs-only handoffs too.
- **After each merge:** merge `main` into the next PR (generated files take main's side, rules
  regenerated), crew version set in the LAST commit, merge-only Sonnet review, CI, merge.
- **Commits** carry only `Claude-Session:`. Never `Co-Authored-By`.
- **Versions:** the next PR in the train takes the next free number. Builders use 1.0.300+
  placeholders and are re-bumped at landing. Next free for landing: see the latest log line (main is crew **1.0.256** at c9263465; placeholders 1.0.319-1.0.327 are in use and get re-bumped at landing).
- **Helpers** (this session's scratchpad, lost on restart; recreate from the description):
  `catchup.sh <branch>` merges origin/main, takes main's side for graphify-out, .claude/rules, and
  anchor-only code map and diagram conflicts, then regenerates the rules. `setver.py`/`bump.sh` commit
  the merge with main's version, then make a version-only commit last.

## Where things stand (snapshot 2026-10-04 10:05 UTC)

Merged this session: #374, #375, #385, #386, #387, #388 (notes), #390, #378, #339, #379, #389 (tooling), #350.
main = c9263465, crew 1.0.256.

### Landing train (in order)

| # | PR | Head | State |
|---|---|---|---|
| 1 | #355 T-0013 | 97c8e6fd (1.0.321) | merge-only review CLEAN; CI 17/24 green, rest running -> MERGE when green |
| 2 | #371 T-0100 (harness, alone) | 3bca38dd | review CLEAN (Windows autocrlf fixture fix); was CONFLICTED with main so PR CI never ran -> land-prep running (1.0.326) |
| 3 | #344 T-0035 | 6af8d6fd | r2 CLEAN (embeds adopted in 3 READMEs, localgpu 0.1.21); CONFLICTED -> land-prep running (1.0.327) |
| 4 | #360 T-0048 | 7d442123 (1.0.323) | merge review 1 FIX fixed (baseBranch row kind); delta review running |
| 5 | #368 T-0063 | d48fa7a5 (1.0.323) | merge-only review running (diagram split + stale '1.0.213' mentions) |
| 6 | #342 T-0070 | c6b33f3f (1.0.324) | 3 FIX fixed; r2 review running (incl. post-#361 check) |
| 7 | #351 | - | land-prep running (1.0.320) |
| 8 | #376 L-0604 | | r1 FIX is a harness docstring (review_verdict.py) -> needs tooling PR or ruling |
| 9 | #377 #352 #353 #357 #358 #359 #362 #367 | | review CLEAN, need land-prep |
| 10 | #361 T-0050, #348 T-0041, #349 T-0065, #369 T-0044, #370 T-0038, #354 T-0012 | | review CLEAN, need land-prep |
| 11 | harness (each alone): #333, #331, #336 (split sabotage_cloud.py first), #343 T-0068 | | |
| 12 | #338 L-0582 WIP port; #324 owner WIP | | |

NOTE: #355 and #360 both change config leaf counts / CONFIG.md -> whichever lands second re-merges carefully.
NOTE: a PR that conflicts with main gets NO pull_request CI (only "Verify gate receipt") - check mergeable_state.

### Builds (worktrees /home/user/pr-<n>)

| PR | Ticket | State |
|---|---|---|
| #340 #341 #346 #347 #345 | L-0526 (harness), L-0509, T-0039, T-0047, T-0036 (after #344) | queued, not started |
| #356 #363 #364 #365 #366 | | BLOCKED: T-0016, T-0037, T-0049 have no ticket/spec (owner) |

## How to resume

1. Read this file and `pending-tickets.md`. `git fetch`; compare each branch head with the table.
2. Front of the train: re-merge main, re-bump, merge-only Sonnet review, CI, then merge.
3. A build whose branch head is still docs-only did not finish: restart it from `docs/tickets/<T>/`.

## Log (newest first)

- 10:13: #371 merge-only review 00cdf632: 0/0/0 CLEAN. Waits CI (waiter running), then merge.
- 10:11: #371 re-merged main edb2b8ff -> 00cdf632 crew 1.0.322 (version/CHANGELOG conflicts only; 157 tests + tooling-pr 17 pass); merge-only review + CI. #360 land-prep started (add KEY_META rows for #355's keys, 1.0.332).
- 10:10: MERGED #355 at edb2b8ff (crew 1.0.321; CI 24/24 + review clean). Next: re-merge #371 (harness) -> 1.0.322; #360 land-prep (config conflicts with #355).
- 10:09: #342 delta review f42ed026: 0/0/0 CLEAN. Waits CI.
- 10:08: #342 CI red on 41b113c6: build (3.12) pylint C0302 test_crew_config.py 3401/3400 (merge-caused). Fixed by hand: comment rewrap -> 3400, crew 1.0.331, head f42ed026; delta review started. WATCH: #351/#355/#360 also grow test_crew_config.py - check line cap at each re-merge.
- 10:07: #371 merge review 147c3f5d: 0/0/0 CLEAN (dropped heading was stale T-0061 leftover). Waits CI.
- 10:07: #351 merge review f542d4f4: 2 FIX (CONFIG 'Measured' para 72/130 should be 73/131; config read/write diagram + codemap crew_config.py line cites stale by 10-14) + 3 NIT (since 1.0.320 placeholder; renders fine - FAILs are layout-check only, container-dependent). Fixer started (1.0.330).
- 10:05: #344 merge review e96cade3: 0/0/0 CLEAN. Waits CI + turn.
- 10:05: #342 merge review 41b113c6: 0/0/0 CLEAN. Waits CI + turn.
- 10:05: #371 land-prep done: head 147c3f5d (1.0.326), still harness-only, autocrlf suites green; dropped an empty CHANGELOG heading (to verify). Merge-only review started.
- 10:04: #368 merge review d48fa7a5: 1 FIX ('since crew 1.0.213' stale in troubleshooting.md + codemap headings) + 1 NIT (done.mmd header cites) -> fixer (1.0.329). LANDING STEP: when re-bumping #368 and #351, also re-point their 'since crew X' text (#368 troubleshooting.md+codemap, regen guide; #351 CONFIG.md s22). #344 merge-only review started on e96cade3.
- 10:04: #344 land-prep done: head e96cade3 (1.0.327, localgpu 0.1.21 restored after taking main's version files), embed re-run no-op, check fresh. Merge-only review next.
- 10:03: #342 land-prep done: head 41b113c6 (1.0.328), NIT1 fixed + test (red/green/sabotage). Merge review started.
- 10:00: #342 conflicted with main -> land-prep started (1.0.328) carrying NIT1 fix + test.
- 09:59: #342 r2 c6b33f3f: 0 BLOCK 0 FIX 2 NIT CLEAN (NIT1: _inert_warnings list-comp outside try -> settings() can raise if completion_audit import fails; carry into land-prep push. NIT2: dangling INDEX symlink wording). Post-#361 merge check: 789 pass.
- 09:59: #360 delta review 7d442123: 0/0/0 CLEAN. Waits CI + its turn (re-merge after #355).
- 09:59: #351 land-prep done: head f542d4f4 (1.0.320); leaf count 131 (git.forbiddenTrailers), diagrams moved into split parts, 3 renders FAIL in container (kept main's PASS - unverified). Merge-only review started. NOTE #351/#355/#360 ALL change config leaf counts -> each later one re-merges carefully.
- 09:58: Snapshot table refreshed; notes now pushed after every action (owner request).
- 09:57: #360 fixer: head 7d442123 (kind branch + test, docs regen), version 1.0.323 (placeholder). Delta review started.
- 09:57: #371 and #344 are CONFLICTED with main (mergeable_state dirty) so pull_request CI never ran (only verify-gate receipt). Land-prep started: #371 -> 1.0.326, #344 -> 1.0.327. #355 CI 15/24 green, merges first.
- 09:56: #344 r2 6af8d6fd: 0 BLOCK 0 FIX 1 NIT (embedded Source: links relative, dangle in plugin cache). Review-clean; waits its turn.
- 09:55: #342 fixer done: head c6b33f3f, 3 FIX + NIT fixed (global-not-read wording, approvals unknown, escaping incl --inert lines), 1.0.324. r2 review started (incl post-#361 merge check).
- 09:55: #355 merge review 97c8e6fd: 0/0/0 clean. Lands after #371 (re-merge+rebump then).
- 09:55: #360 merge review aedd225b: 0 BLOCK 1 FIX (tickets.baseBranch row kind 'type' renders 'coerced'; should be 'branch'/checked). Fixer started.
- 09:54: #368 land-prep done: head d48fa7a5, 1.0.323; lifecycle diagram split by main #375 -> PR nodes moved into implement/done parts; guide docx/pdf rebuilt. Open: diagrams not rendered; stale '1.0.213' mentions in README/guide/codemap. Merge review started.
- 09:54: #344 fixer done: head 6af8d6fd; FIX1 unknown for unreadable README (+2 tests, sabotage red); FIX2 embed run in crew/localgpu/skills READMEs, gate live; localgpu 0.1.21, crew 1.0.325. r2 review started.
- 09:53: #371 delta review 3bca38dd: 0 BLOCK 0 FIX 1 NIT (git wrapper drops check= kw; no caller uses it). Waiting CI.
- 09:53: #355 land-prep done: merged main, leaf count 132, crew_state.py comment trimmed to 3400 (pylint cap), BUDGETS re-measured, 1.0.321, head 97c8e6fd. Merge-only review started. NOTE #355 and #360 both touch config leaf counts/CONFIG -> 2nd to land re-merges.
- 09:53: #360 land-prep done: merged main c9263465, added KEY_META row tickets.baseBranch (main's T-0061), regen config ref (130 keys), BUDGETS re-measured, version 1.0.322, head aedd225b. Merge-only review started.
- 09:51: #371 fixer: Windows autocrlf fixture fix (clone -c core.autocrlf=false) + version 1.0.319, head 3bca38dd; sabotage red; awaiting CI + delta review.
- 09:49: #344 r1 on eb7fd11f: 0 BLOCK, 2 FIX (unreadable README with markers skipped silently; no README adopted so gate inert - decision: adopt embeds in this PR, bump localgpu) + 2 NIT; plan steps 1 nested, 4 audit allowance, 6 migration missing -> split tickets/follow-ups. Fixer started (1.0.325).
- 09:48: #342 r1 on eb57cc07: 0 BLOCK, 3 FIX (global deploy called repo-only vs owner decision; --approvals reads missing/corrupt INDEX as nothing pending; inert key/value printed raw incl. into SessionStart context) + 1 NIT -> fixer (1.0.324).
- 09:48: #354 r2 on ab1bb915: CLEAN (0/0/1 NIT: symlinked parent dir unchecked - residual behind scope_guard). Joins train.
- 09:47: Land-prep (content merge of current main, then version-last) started in parallel for #351 (1.0.320), #355 (1.0.321), #360 (1.0.322), #368 (1.0.323) per scratchpad LANDPREP.md - they are 342 commits behind with real content conflicts. Notes PR #391 open.
- 09:46: CONTAINER RESTARTED ~05:30 (worktrees + scratchpad survived; 3 agents lost mid-work: T-0035 builder had pushed eb7fd11f, #354 r2 and #342 reviews re-run). OWNER: autopilot.deploy MAY be global (T-0050 #361 wins over T-0070 #342's repo-only). MERGED #350 at c9263465 (crew 1.0.256). #371 CI: Windows-only 11 tests fail - git merge exit 2 in new merged_main_fixtures.py (likely autocrlf dirty tree) -> fixer (1.0.319). #344 review started (reconstructs plan-step status). Next free 1.0.320.
- 05:19: BATCH (written while the branch carried #389): MERGED #388 (notes). OWNER chose waiver for #370's 1-line harness retarget, BUT a waiver keeps verify-gate red (check-tooling-pr), so instead opened tooling PR #389 (crew 1.0.254): sabotage UPGRADE_DOC resolves to upgrade-report.md if present else upgrade.md - lands alone first, then #370 is green without a harness edit. #370 dup crash-test anchor fixed in-branch (1acdeba3, 1.0.313). #369 r2: 2 FIX (no claude --version check for --setting-sources >=2.1.246; sweep owner check untested) -> fixer. #343 r2: 1 FIX (guard.log still deadlocks the audit -> bookkeeping) -> fixer. #350 CI running. #369 r2 FIXes pushed ea6bc6c9 (claude --version >=2.1.246 check, worktree main-checkout settings.local.json, sweep tests; 1.0.314); r3 started. #389 tooling review CLEAN (0/0/2). #349 T-0065 built 187e2d48 (1.0.309; verify_agents.py, provider_probe.py, UPGRADE.md history, per-test TMPDIR; full suite 9251 passed; harness follow-ups: verify-gate cleanup, sabotage entries, review.md names). Review started. #349 r1 CLEAN (0/0/2). #369 r3 CLEAN (0/0/4). #350 CI red on 459b9724: test_scope_discipline pins 'not from the verify gate's own marker' which #350's implement.md edit dropped (all 4 red checks same test) - fixed 9a3df424 crew 1.0.255, review + CI again. #350 fix review CLEAN; waits CI. #343 r2 FIX fixed -> 741cbce2 (guard.log/.autoclear.log/.cloud-guard-unpinned-noted -> bookkeeping; decision markers stay state, pinned; 4 mutations red; full suite 9380 passed; 1.0.315); r3 started. MERGED #389 at 11dcb99d (tooling, crew 1.0.254). #350 re-merged -> 8917caf9 crew 1.0.256 (merge-only review + CI). #370 re-merged (with #389) -> f6db6878 crew 1.0.257, BUDGETS 22,335/140; r2 review. #354 T-0012 built 803c656a (narrowed scope; minting moved to L-0541; harness follow-up: approval_hook goal:<slug> token) - review started. Next free 1.0.258. 
- 04:46: #370 r1 on 03f99760: 0 BLOCK, 1 FIX (sabotage anchors: (a) upgrade.md stub lost '- **Schema 6 → 7**' -> needs harness retarget of UPGRADE_DOC in sabotage.py; (b) duplicate crash-test anchor -> fixed in-branch by rewording test_migrate.py:598, 1.0.313). (a) awaits OWNER decision: waive tooling rule for the 1-line retarget in #370, or land #370 with that test red then a tooling PR.
- 04:45: #350 merge-only review on 459b9724: CLEAN (0/0/2 NIT: codemap says 1.0.184; stray CHANGELOG blank line). Fits #378's scope_base exactly. Waiting CI.
- 04:44: #343 3 FIX fixed -> 1292b863 (four lists: bookkeeping/write-allowed(metrics.md only)/state/content; rule 2 refuses gate files even in Touch; 13 new mutations, 40/40 red; full suite 9305 passed). r2 started incl. guard.log bookkeeping-vs-state question.
- 04:44: MERGED #379 at d67098ad (crew 1.0.252; Windows fix verified by CI 25/25). #350 re-merged -> 459b9724 crew 1.0.253 (BUDGETS 22,550), merge-only review + CI next. #369 fixes pushed 9ba064c1 (--setting-sources user per docs, denyWrite, env/stores widened, bounded probe) - r2 started. #370 T-0038 built 03f99760 - review started (1 known red: sabotage anchor in upgrade.md stub needs harness retarget). #361 r2 CLEAN -> train. mmdc installed locally for diagram renders. Next free 1.0.254.
- 04:41: #361 r2 on ccce8df4: CLEAN (0/0/2 NIT). Joins landing train.
- 04:39: #348 r1 on 7ec4750f: CLEAN (0/0/2 NIT: docs/diagrams README/index.html embedded done-diagram stale - regenerate with diagram_doc.py --write where mmdc exists; validate-prompts glob cwd). Joins the landing train.
- 04:37: #348 T-0041 feature half built -> 7ec4750f (1.0.308 placeholder; 18 tests, 5 hand sabotages red; harness half = follow-ups: review_verdict U+2028 split, review_run output_sha256, reviewer.md/review.md rule, sabotage_review entries). Sonnet review started.
- 04:33: #379 fix review on c5dbf597: CLEAN (0/0/1); CI running. #361 FIXes + 2 safety NITs pushed ccce8df4 (1.0.307 placeholder; full suite 9343 passed); Sonnet r2 started.
- 04:27: #379 CI on a5b44398: Windows default shards red - REAL: _read_regular os.set_blocking on a file -> WinError 87 refused every assign/mint --direction-file on Windows (round-2 FIFO fix). Fixed 523f0b7c (only restore blocking where O_NONBLOCK set; Windows-simulating test, sabotage red), version 1.0.252 c5dbf597 pushed. Sonnet review of the fix + CI next.
- 04:06: #369 r1 on ce400de3: 1 BLOCK (repo .claude/settings sandbox.excludedCommands can widen past the probe), 4 FIX (probe cwd != exec cwd; no denyWrite on stores/identity config/sealed dir; only AWS env stripped; probe output truncation), 2 NIT. Fixer started (docs-verified settings semantics), 1.0.311 placeholder.
- 04:05: #343 r1 on 514ca132: 0 BLOCK, 3 FIX (rule 5a opens trust inputs tfplan/incident/deploy-in-flight to Write/Edit -> forged plan sidecar lets destroy apply; opens verify-gate marker/fingerprint -> forged green gate; bundle/audit exclusion hides committed trust files). Fixer started: split WRITE_ALLOWED (metrics only) vs AUDIT/BUNDLE-EXCLUDED (crew-script bookkeeping only). 1.0.310 placeholder.
- 04:04: MERGED #387 (notes). #379 merge-only r2 on a5b44398: CLEAN; CI running. #350 pre-merged main locally (BUDGETS re-measure 22,541 pending in its version commit).
- 04:03: MERGED #339 at af2bf9d2 (crew 1.0.248; CI 25/25 green after runner disk fix; 3 merge-only reviews clean). #379 re-merged -> a5b44398 crew 1.0.250, merge-only review r2 + CI next. Next free 1.0.251.
- 04:01: #343 T-0068 (harness, lands alone) built -> 514ca132 (1.0.300 placeholder; list in crew_ticket.py not crew_common.py to stay harness-only; 69 tests, 26 sabotages red incl ps1 via scratch pwsh 7.4.6). Sonnet adversarial review started. Builder started: T-0065 #349 (1.0.309).
- 04:01: #369 T-0044 built -> ce400de3 (1.0.305 placeholder; 87+9 tests, 22/23 hand sabotages red (1 equivalent mutation); follow-up sabotage_unattended.py). Sonnet security review started. Builder started: T-0041 #348 (1.0.308).
- 03:56: #379 merge-only review on a88e9b07: CLEAN (0/0/0; ASSIGN 34/34 + SCOPE sabotage red, 7 pwsh-only green w/o pwsh). Waits on CI.
- 03:56: #361 r1 on e6c5fa6a: 0 BLOCK, 2 FIX (approval=null widening warning blank; --restore of corrupt stamp writes it saying nothing to change), 4 NIT. Fixer started (1.0.307 placeholder) incl. 2 safety NITs.
- 03:52: OWNER: runner disk resolved. CI running on #339 c2a3ccb5 and #379 a88e9b07.
- 03:52: #361 T-0050 built -> e6c5fa6a (1.0.301 placeholder; 120 new tests, 21 hand sabotages red, full suite 9316 passed; harness follow-ups: allowCliApproval global, sabotage_config_layers.py). Sonnet review started. Builder started: T-0038 #370 (1.0.306).
- 03:50: MERGED #378 at f7ab26b9 (crew 1.0.247; CI 25/25 green incl verify-gate, merge-only review clean; marked ready then merged). #339 re-merged -> c2a3ccb5 crew 1.0.248, merge-only review CLEAN; CI pending runner disk fix (owner fixing runners 4/5/6 on the self-hosted host). #379 re-merged -> a88e9b07 crew 1.0.249 (543 tests pass on merged tree), merge-only review next. Next free: 1.0.250.
- 03:37: BLOCKER (owner): self-hosted runner host DISK FULL - #339 verify-gate rerun: 'verify-gate.sh: line 911: printf: No space left on device' (runner-6). Earlier pwsh SIGBUS -7 on runners 4/5 same cause. All PR CI red until freed. Notes pushes paused (they trigger CI on the same runners). #339 and #378 are review-clean, merge on green after cleanup.
- 03:36: #339 CI 6da2a486: verify-gate red at ~03:29 on self-hosted runner-5: pwsh killed by SIGBUS (-7) and the full suite errored en masse, then every later step (even 0s scripts) failed - host fault (same minute as runner-4's -7s on #387). Re-ran the failed job ONCE (run 37173806451). If it fails again the same way: host needs attention (tmpfs/memory) - owner.
- 03:34: #379 r3 on d93f3e5a: CLEAN (0/0/3 NIT: mint --status '' -> ready; untested drop-note branch; >4300-digit id ValueError). All 6 r2 findings verified red-on-revert. Train reordered: #379 lands right after #378 (unblocks #354 T-0012).
- 03:30: #387 (notes, docs-only) crew-shell-matrix ubuntu red on 0a53c7cd: 698 ps1-flavour tests exit -7 (pwsh killed by signal 7) on self-hosted runner-4 - runner fault, not content. Docs PR merges regardless (owner). Watching #339/#378 for the same.
- 03:29: #379 T-0019: round-2 BLOCK + 5 FIX fixed test-first, merged main, pushed d93f3e5a (1.0.302 placeholder; full crew suite 9280 passed; ASSIGN sabotage 34/34 red). Sonnet round-3 review started. Builder started: T-0044 #369 (1.0.305).
- 03:25: #378 merge-only review on 9b701365: CLEAN (0/0/2 NIT: diagram comment sha, version gap 243-246 reserved).
- 03:24: OWNER: docs-only PRs need no gates, just merge. MERGED #386 (notes, 1ffbe7a5). Notes now pushed to branch ccr-b039f2bb-6jks7g after every action (read the BRANCH to resume); merged to main periodically via a docs PR.
- 03:24: #378 local suites on merged tree: 582 passed, tooling-pr 17/17; merge-only Sonnet review of 9b701365 started. Owner 03:2x: 'merge when ready' (standing).
- 03:22: #331 r2 on 4a368125: CLEAN (0/0/0; full crew suite 8834 passed). Harness clean set: #331, #333, #336 (needs split at landing).
- 03:22: #378 merged main + re-bumped -> 9b701365 crew 1.0.247 pushed (CI early signal; will re-merge after #339). #333 r2 on 5b8be69d: CLEAN (0/0/0). Next free: 1.0.248.
- 03:21: #339 merge-only review r2 on 6da2a486: CLEAN (0/0/0); CI running. #378 pre-merged main locally (not pushed): im1 relabel moved into main's split process-crew-lifecycle-implement.mmd; re-bump waits for #339 to land. Suites running.
- 03:20: MERGED #385 (35cfcfcf: verify.json maps the handoff docs; notes). #339 re-merged main -> 6da2a486 (no plugin change, crew stays 1.0.246); merge-only review + CI next. Notes continue on a new PR from ccr-b039f2bb-6jks7g.
- 03:13: #377 r1 (Sonnet) on 05be104b: CLEAN (0 BLOCK, 0 FIX, 2 NIT: implement.md reflow, LANDING_ORDER literal duplicated in test).
- 03:12: #339 CI verify-gate red: every row PASS but 'UNMAPPED CHANGES: cloud-handoff-notes.md, pending-tickets.md' (#374 added them without a verify.json rule -> gate exit 2 on EVERY PR). Fix dc9c2154 on #385 (docs rule maps both). #385 now lands FIRST; then #339 re-merges main.
- 03:09: #333 FIX pushed 5b8be69d (terminate OSError -> CouldNotCheck, must-block/allow tests, sabotage entry; 1.0.304 placeholder). Sonnet re-review r2 started.
- 03:06: #331 FIX pushed 4a368125 (pwsh-simulated label test + typo must-block, sabotage red; 1.0.303 placeholder). Sonnet re-review r2 started.
- 03:06: #336 r1 (Sonnet) on f08ae7fb: 0 BLOCK, 0 FIX, 2 NIT (numeric workflow ID / gh alias read as unlisted; docstring limit list). CI verify-gate red ONLY on check-tooling-pr.py (owner waiver in PR body). Plan at landing: split the harness part (sabotage_cloud.py) into its own tooling PR, as L-0516/L-0563 did, so both go green.
- 03:04: #333 r1 (Sonnet) on 73af42d7: 0 BLOCK, 1 FIX (review_checks.py:755 bare job.terminate() on clean exit raises OSError, not CouldNotCheck), 1 NIT. Fixer started, placeholder 1.0.304.
- 03:03: #331 r1 (Sonnet) on 5bd46939: 0 BLOCK, 1 FIX (test_every_platform_only_label_names_exactly_one_shipped_mutation fails without pwsh), 2 NIT. Fixer started, placeholder crew 1.0.303.
- 03:02: Content reviews (Sonnet) started on #377, #333, #331, #336 (current heads); merge-only reviews follow at landing. #339 CI: Windows legs, shell, test 3.12, verify-gate still running.
- 03:01: RESUMED by new session (owner 2026-10-04: work all open PRs #323-#379, merge as I go, build all handoffs). Merged #374 (b1e9bd7e) and #375 (38adba44, crew 1.0.242). #339 re-merged main -> 210901b0 crew 1.0.246, merge-only Sonnet review CLEAN (1 NIT CHANGELOG blank line), CI running. Builders started: T-0068 #343, T-0050 #361, T-0019 #379 fixes.
## Previous session's log (session_014TLaGTaf3GDU1wccRotE67)


- 02:24: #339 r2 on 8855e68f: CLEAN (0 BLOCK, 0 FIX; ps1 STILL GREEN ruled NIT - no skip mechanism in sabotage.py, harness follow-up). Queued right after #375 (needs re-merge once #375 lands). Follow-up ticket: sabotage.py needs a 'requires pwsh' skip state.
- 02:24: #376 r1: PASS, 1 FIX (review_verdict.py docstring overclaim) + 2 NIT (review.md:485 harness follow-up; sabotage_review entry). Land-prep agent started: fix, merge main (26 generated/version conflicts), crew 1.0.245. Next free: 1.0.246.
- 02:23: #339 r1: PASS code (5/6 sabotage RED; ps1 entry STILL GREEN w/o pwsh = pre-existing trait), FIX version + ticket docs. Done by hand: merged main (clean), CHANGELOG entry, removed docs/tickets/L-0563, crew 1.0.244 -> 8855e68f pushed; gates green; r2 review started. Next free: 1.0.245.
- 02:22: Triage B: #336 T-0009 REVIEW (complete, owner-waived tooling rule for sabotage_cloud.py; verify-gate red = that waiver); #333 L-0605 REVIEW (harness-only, ADR 0005); #331 L-0608 REVIEW (harness, real sabotage.py conflict; coordinate with #336); #348 T-0041, #349 T-0065 BUILD; #324 L-0590 WIP (draft, owner collecting timings); #274 T-0104, #275 T-0500 WIP (owner-marked, 1381 behind) - leave. Running now: reviews #339 #376 #377, fixer #379.
- 02:21: Triage C: #376 L-0604 REVIEW, #377 L-0522(1/3) REVIEW (both complete, conflicts only generated/version); #379 T-0019 BUILD-finish (draft harness PR, r2 1 BLOCK+5 FIX unresolved; unblocks #354/#364/#365); #344 T-0035 BLOCKED on #375; #345 T-0036 BLOCKED on #344; #361 T-0050, #369 T-0044, #370 T-0038 BUILD (docs-only). #354/#356/#363/#364/#365/#366 still blocked (T-0016/T-0037/T-0049 have no PR). Starting reviews #376, #377 and #379 finish.
- 02:21: #375 merge-only review on 8bf5c021: CLEAN. Waiting on CI. #339 first review started.
- 02:21: Triage A: #338 L-0582 PORT (WIP real code, 600 behind, conflicts verify.json/README, no CI); #339 L-0563 REVIEW (harness-only sabotage_qa.py, merges clean, re-run sabotage on main); #340 L-0526, #341 L-0509, #342 T-0070, #343 T-0068, #346 T-0039, #347 T-0047 = BUILD (docs-only handoffs; #340/#343 builds are harness PRs, #347 sabotage separate). None superseded.
- 02:19: #375 re-merged main cce7e486 -> 8bf5c021 (crew 1.0.242, BUDGETS 22,520/139; gates + 90 tests green); pushed; merge-only review + CI running. Triage of unreviewed PRs started in 3 groups: A #338-#347, B #348/#349/#336/#333/#331/#324/#274/#275, C #376/#377/#379/#344/#345/#361/#369/#370 + blocked-chain check. Next free: 1.0.243.
- 02:18: RESUMED (owner: other session done; work all remaining open PRs). main now cce7e486 (#383 crew 1.0.232, #384 crew 1.0.233 from other session). Next free: 1.0.242. Step 1: re-merge main into #375 -> 1.0.242. Parallel: triage of unreviewed open PRs.
- 01:35: PAUSED by owner (another session working). No merges, no pushes, no agents running. Cancelled check-ins (#375, PR-set 3); unsubscribed #374/#375. RESUME STATE: #375 head f4045346 (crew 1.0.241) review clean, CI was running - verify Windows green + main still 3473f08f before merge. Then #378 (worktree /home/user/pr-378, 1.0.242). Clean & waiting: #352 113eccbf, #353 ea342f1f, #358 88e7295f, #362 0920f1eb, #367 00910e28 (+ #350/#351/#355/#357/#359/#360/#368/#371 earlier). Follow-ups: render.sh drive-letter dir bug; lint for tests calling bare bash; process-qa-gates.mmd rule count.
- 01:32: #375 fix r2 review on f4045346: CLEAN (0 BLOCK, 0 FIX, 1 NIT stale timing). Waiting on CI (Windows is the real proof).
- 01:31: #375 fix review on 25f64976: FIX - test passed C:/... dir; render.sh rewrites non-/ dirs to ./C:/... -> still red on Windows. Fixed: cwd=tmp_path + relative docs/diagrams, probe timeout; crew 1.0.241; pushed f4045346; Sonnet r2 started. Follow-up ticket: render.sh treats a drive-letter dir as relative (affects real Windows callers too). Next free: 1.0.242.
- 01:29: #375 CI red on a8752c4e: crew-windows-default (1/3) test_render_sh_records_the_source_hash... - shutil.which('bash') = WSL launcher (no distro, exit 1). This PR's test. Fixed with crew_fixtures.resolve_bash() + sha256 probe via that bash; crew 1.0.240; pushed. Sonnet review of fix next. Next free: 1.0.241.
- 01:14: #375 merge-only review on a8752c4e: CLEAN (0 BLOCK, 0 FIX, 2 NIT: process-qa-gates.mmd says 49 rules (main's file); README only reproducible with local renders, by design). Waiting on CI.
- 01:13: #367 r4 review on 00910e28: CLEAN (0 BLOCK, 0 FIX, 3 NIT: stale codemap prose cites, backslashreplace untested, in-process coverage() exception). Waits its turn.
- 01:12: #375 re-merged main 3473f08f -> a8752c4e (crew 1.0.239; verify.json conflict = keep both rules; BUDGETS 22,411/139 in version commit; rendered 3 new QA diagrams, all PASS, README/index regenerated; gates + 67 tests green). #362 r3 CLEAN on 0920f1eb. Merge-only review of #375 next.
- 01:11: MERGED #337 (L-0618) at d9e75c15 -> main 3473f08f (CI 23 ok/1 skipped, merge-only review clean, owner approved scope). Next: re-merge main into #375 -> 1.0.239. Batch 3 (T-0050/T-0044/T-0038) now unblocked.
- 01:09: #362 r2 fixes pushed 0920f1eb (crew 1.0.238; urlEnv global-only, _NoRedirect for all sends, short chatId masked). Sonnet r3 started.
- 01:09: #367 r3 fixes pushed 00910e28 (crew 1.0.237; shown()/listed() used by status + refresh-check + reasons, backslashreplace stdout, crash -> exit 2, ! + unjudgeable test). Sonnet r4 started.
- 01:05: Check-in 2 (01:05): #337 CI 20 ok/2 running; #375 conflicted (expected - re-merged after #337 lands); #374 behind (merges last). #372/#373 merged. Re-armed check-in 3 (+4h).
- 01:04: #362 r2 review on 2be1ea4c: PASS (0 BLOCK), telegram_base held vs 27 hostile URLs; 2 FIX (repo urlEnv can divert ping text; urllib follows redirects with token in path) + 2 NIT. Fixer started; target 1.0.238. Next free: 1.0.239.
- 01:02: #367 r3 review on 47b66400: PASS (0 BLOCK), 3 FIX (status/refresh-check print hostile names raw -> terminal injection; reason strings unescaped + non-UTF-8 crash exits 1 not 2; unknown-with-! branch untested). Fixer started; target 1.0.237. Next free: 1.0.238.
- 00:59: #367 r2 fixes pushed 47b66400 (crew 1.0.236; _plain allow-list, never override user ! line - exit 1 naming it, dangling symlink test, CRLF by majority; troubleshooting guide rebuilt). Sonnet re-review r3 started.
- 00:53: #337 merge-only review on d9e75c15: CLEAN (0 BLOCK, 0 FIX). Waiting on CI, then merge (owner approved).
- 00:53: #362 fixes pushed 2be1ea4c (crew 1.0.235; loopback-only Telegram base, global-only tokenEnv, chatId masked, unknown outcome, promote via notify.sh). Sonnet re-review r2 started (incl. urlEnv same-class question).
- 00:52: #337 re-merged main 0bdc17a8 -> d9e75c15 (crew 1.0.230; BUDGETS conflict -> re-measured 22,346/139 in the version commit; gates + 318 tests green). Pushed; merge-only Sonnet review started; subscribed for CI. #362 fixes pushed 2be1ea4c (1.0.235) - re-review next.
- 00:51: MERGED #372 (L-0562) at 860db77f -> main 0bdc17a8 (CI 24 success/1 skipped, merge-only review clean). Next: re-merge main into #337 -> 1.0.230.
- 00:50: #367 r2 re-review on 156a2702: FAIL, 1 BLOCK (newline in a filename injects a ! line into .graphifyignore via --write literals), 2 FIX (silent override of user ! negation; no dangling-symlink test), 2 NIT. Decision: allow-list literals; --write refuses to override a user's ! line and names it. Fixer started; target 1.0.236. Next free: 1.0.237.
- 00:48: #353 r3 re-review on ea342f1f: CLEAN (0 BLOCK, 0 FIX, 1 NIT line width). Waits its turn in merge order.
- 00:48: #353 r2 re-review on 50685af5: PASS, 1 FIX (codemap Ship paragraph still said MERGED=closed) + 2 NIT. Fixed by hand: ea342f1f (codemap + verify.json why 153 + rules regen; plugin/crew untouched, version commit stays last). Gates green. Sonnet r3 started.
- 00:47: #367 fixes pushed: 156a2702 (crew 1.0.234; nested repo/symlink -> unknown, backslash rules, --write literals for case, write keeps mode/symlink/CRLF; 8 sabotages red). Side-effect to judge: appended literal overrides a user's ! negation. Sonnet re-review r2 started.
- 00:45: #353 fix pushed: 50685af5 (crew 1.0.233; _merged_phase: closed only if merged headRefOid == HEAD, else stop; 7 sabotage-red tests). Sonnet re-review r2 started.
- 00:45: #352 r3 re-review on 113eccbf: CLEAN (0 BLOCK, 0 FIX, 1 NIT wording). Waits its turn in merge order.
- 00:44: #358 r3 re-review on 88e7295f: CLEAN (0 BLOCK, 0 FIX, 2 NIT cosmetic). Waits its turn in merge order (needs main merge + re-bump + merge-only review at front).
- 00:44: #352 fixes pushed: 113eccbf (crew 1.0.231; accepted-risk sentence + docstring + test, stuck-marker clear hint). Sonnet re-review r3 started.
- 00:42: #358 fixes pushed: 88e7295f (crew 1.0.232; corrupt base -> unknown; cat-file-only + README GitFailed tests, sabotage red). Sonnet re-review r3 started.
- 00:42: OWNER: approved #337 scope ('Merge 337') - documented-limit accepted. Proceeding: #372 merge on green CI, then re-merge main into #337 (1.0.230), merge-only review, CI, merge.
- 00:41: #362 first review on e4bf90f9: PASS, 0 BLOCK, 6 FIX (SECURITY: CREW_NOTIFY_TELEGRAM_BASE accepts any host -> token exfil via repo settings env; chatId printed; approvals don't reset episode (docs); CONFIG 70->74; missing --outcome reads pass; stale base). Fix agent started (+promote.md bare python3 NIT); target 1.0.235. #374 windows red on d4fea557 = superseded-cancel, not a failure. Next free: 1.0.236.
- 00:40: #367 first review on 70533df5: FAIL - BLOCK is only stale base (3 behind main; merge at queue front), 5 code FIX (nested repo skipped, symlinks by name, backslash Read rules dropped, case-fold dead end, --write loses mode/symlink/CRLF). Fix agent started; target 1.0.234. Next free: 1.0.235.
- 00:40: #353 first review on 8e63b3aa: PASS, 0 BLOCK, 1 code FIX (MERGED PR reads closed without comparing headRefOid to HEAD) + base 3 behind main (handled at queue front) + 3 NIT. Fix agent started; target 1.0.233. Next free: 1.0.234.
- 00:39: #358 re-review on 68611aed: PASS, 0 BLOCK, 2 FIX (corrupt base marketplace.json collapses to 'added'; cat-file-only + README GitFailed paths untested, sabotage green) + 1 NIT (CHANGELOG blank line). Fix agent started; target 1.0.232. Next free: 1.0.233.
- 00:39: #352 re-review on 26c18d41: PASS, 0 BLOCK, 1 FIX (author-record residual not in CONFIG.md Accepted risks) + 2 NIT. Fix agent started; target crew 1.0.231 (1.0.230 reserved for #337 re-merge). Next free: 1.0.232.
- 00:38: #372 merge-only Sonnet review on 860db77f: PASS (0 BLOCK/0 FIX/0 NIT). Waiting on CI.
- 00:37: Recovered 6 results lost to the restart: ports pushed #353 8e63b3aa (1.0.196, incl. round-2 fixes), #362 e4bf90f9 (1.0.197), #367 70533df5 (1.0.198); fixes pushed #352 26c18d41 (1.0.224), #358 68611aed (1.0.226); #337 merge-only review CLEAN on 55cb1c47 (main has moved since). Started 5 Sonnet reviews: #353, #362, #367 (first), #352, #358 (re-review). #372 merge-only review on 860db77f running.
- 00:36: Container restarted ~23:55; worktrees and scratchpad survived. #372 CI on 11d5194e went ALL GREEN, but main had moved to 5cbe3d01 (#381, #382 from session ccr-05486a34; crew 1.0.169; verify.md and AGENTS.md generation). Re-merged #372 (versions, CHANGELOG, BUDGETS conflicts; verify.md auto-merged, 226 lines within allowance) -> crew 1.0.229; gates pass; 100 tests pass. Needs a merge-only review and CI again. Next free: 1.0.230.
- 23:42: #337 round-8 re-review on 0df0cb2b: CLEAN (0 BLOCK, 0 FIX). Then re-merged main (#380) -> 55cb1c47, crew 1.0.228; gates pass, qa+state tests 387 passed; needs CI + merge-only review. MERGE OF #337 HELD for owner OK on review scope (unlisted words in 'by' name = documented limit). Next free: 1.0.229.
- 23:40: #337 round-7 FIX pushed (0df0cb2b, crew 1.0.227): name words split on apostrophes. Round-8 Sonnet re-review started.
- 23:38: #337 round 7: PASS 0 BLOCK, 1 FIX (apostrophe glued to a listed refusal form, e.g. "by Ann Revoked'", passes). All round-6 items + boundary attacks confirmed; doc list == code list (82). Sent to fixer, target 1.0.227. Next free: 1.0.228.
- 23:36: #337 round-6 fixes pushed (7c12bbef, crew 1.0.225): 'no/no-one/noone' refuse inside names; verb inflections added; whole word reported before stem; limit documented. Round-7 Sonnet re-review started (scope: unlisted name-slot words = documented limit, pending owner OK).
- 23:35: #358 review: PASS 0 BLOCK, 3 FIX (_base_text git-fail collapses to 'all added'; implement.md says unknown stops but autopilot reruns -> decided: stop at once on unknown; no integration test of real ticket_docs via next_phase). Sent to builder, target 1.0.226. Next free: 1.0.227.
- 23:34: #337 round 6: FAIL, 1 BLOCK ('accepted by No One' PASS: 'no' dropped inside names) + 2 FIX (bare verbs Retract/Decline as names; 2nd-by evidence word). Name-fix confirmed, no boundary leaks. Sent to fixer, target 1.0.225. Round-7 reviewer scope: an unlisted word in the name slot is a DOCUMENTED LIMIT (needs owner OK). Next free: 1.0.226.
- 23:33: #352 review: PASS 0 BLOCK, 2 FIX (both unlink+blank fail -> stale author record still trusted, must wait; remove docs/tickets/T-0069). Sent to builder; target 1.0.224. Next free: 1.0.225. #372: waiting CI on 11d5194e (bf87f024 run was cancelled).
- 23:33: #372 red Windows fan-in on bf87f024 = default/slow jobs CANCELLED by the 11d5194e push (wallclock passed); not a failure. #337 round-5 FIX pushed (4e77771a, crew 1.0.222): stems stay out of 'by' names, GAP names the word. Round-6 Sonnet re-review started.
- 23:32: #358 T-0022 built + pushed 99409651 (crew 1.0.191): docs + tracker autopilot phases, crew_docs_check.py; suite 8869 passed; 21/21 sabotage red; harness follow-up sabotage_docs.py. Sonnet review of #358 started. Port T-0051 (#362, 1.0.197, WIP-unverified) started in /home/user/pr-362. #337 round-6 commits made locally (to 1.0.222), gating.
- 23:31: #372 merge-only re-review on 11d5194e: CLEAN (0/0/0). Review rule satisfied on the current head; waiting for CI on 11d5194e, then merge.
- 23:30: #352 T-0069 built + pushed eaae7b72 (crew 1.0189): 4/6 fixes (T-0023 x2, T-0042 x2); T-0024's two + sabotage entries -> harness-only PR. Suite 8823 passed. Sonnet review of #352 started. Port T-0064 (#367, 1.0.198) started in /home/user/pr-367. Merge-only re-review of #372 running.
- 23:30: main took #380 (crew 1.0.167, verify-gate CLAUDE_PLUGIN_ROOT). #372 re-merged main (version/CHANGELOG conflicts only) -> 11d5194e, crew 1.0.223; gates pass, reach + gate tests 23 passed. Needs fresh CI, plus a merge-only Sonnet re-review. #375 round-3 re-review CLEAN (e22687da). #337 round 5: 0 BLOCK, 1 FIX (refusal stems hit names like Denise) -> fixer, target 1.0.222. Next free: 1.0.224.
- 23:27: #375 round-2 fixes pushed (e22687da, crew 1.0.218): char-level path parser (arc flags), per-subpath segments, renamed/stray edges UNKNOWN (invisible links excluded), render.sh writes .svg.src source hash. 33 real renders still PASS. Round-3 Sonnet re-review started.
- 23:26: #337 round-4 fix pushed (2f0bdf32, crew 1.0.221): names only after 'by'; refusal stems by prefix; limits documented. Round-5 Sonnet re-review started. If round 5 fails, recommend owner switch secrets.md acceptance to structured columns.
- 23:25: #355 re-review on c2bfb51d: CLEAN (0 BLOCK, 0 FIX, 2 NITs). Clean set: #371, #360, #378, #350, #351, #359, #368, #357, #355. Pending: #372 CI; #337 round 5 fixing; #375 round 2 fixing.
- 23:23: #337 round-4: FAIL, structural BLOCK (free-standing capitalised qualifier read as a name: 'accepted Maybe/Cancelled/Void' PASS). Decision: a name only counts after 'by'; refusal words matched by stem/prefix; residual limit ('accepted by Maybe') documented. Sent to fixer; target 1.0.221. Next free: 1.0.222. #372 still waiting on CI bf87f024.
- 23:22: #372 round-3 re-review on bf87f024: CLEAN (0 BLOCK, 0 FIX, 2 NITs left alone to avoid a new review cycle). Up to date with main 7846261c. FIRST MERGE CANDIDATE: waiting for CI on bf87f024 to finish green, then merge (merge commit).
- 23:22: #337 round-3 fix pushed (d1577de8, crew 1.0.219): strict whole-cell acceptance grammar; 'accepted revoked/expired/...' = GAP (refusal word), others UNKNOWN; 4 sabotage mutations red. Round-4 Sonnet re-review (adversarial, 40+ values) started.
- 23:21: CLEAN: #368 re-review on ca084ea2 (0 BLOCK, 0 FIX, 2 NITs) and #357 T-0020 first review on d4dd47a3 (0 BLOCK, 0 FIX, 4 NITs). Clean set now: #371, #360, #378, #350, #351, #359, #368, #357.
- 23:21: #372 round-2 re-review: PASS w/ 1 FIX (cache re-key only holds in the checkout that ran it) -> fixed by hand + shared-old-key test (sabotage red) -> bf87f024, crew 1.0.220; round-3 re-review started. #355 FIX fixed by agent (c2bfb51d, crew 1.0.214: 'left to the PowerShell hook' vs 'not typed'); re-review started. Next free: 1.0.221.
- 23:19: #368 code-map citations re-derived and pushed (ca084ea2; 56 moved, 2 pre-existing wrong fixed; no plugin change). Sonnet re-review of #368 started. Red CI on #337 4aa98c36, #372 cc96f702 and #374 6b98600c are superseded heads (cancelled), not failures.
- 23:19: #337 round-3 re-review: FAIL, 1 BLOCK (acceptance 'name' slot takes any lowercase word: 'accepted revoked/expired/maybe' PASS). Reach + map fixes confirmed. Decision: strict whole-cell grammar (accepted|yes [by Capitalised Name<=3] [ISO date]; refusal word -> no; else UNKNOWN). Sent to fixer; target 1.0.219. Next free: 1.0.220.
- 23:18: #357 T-0020 built + pushed d4dd47a3 (crew 1.0.190): focus = existing pointer, no new hook; full suite 8891 passed; 22/22 sabotage red. Harness follow-up: 4 mutations in sabotage_autopilot.py. Note: autopilot.md now 117/120 lines (tight for T-0012/T-0019). Sonnet review of #357 started. Ports T-0051/T-0064 held until a build finishes (load ~25).
- 23:17: #375 re-review on 16e92602: original BLOCK + 6 FIX resolved (all 33 real renders PASS), but 4 new FIX (arc flags not 0/1-validated, 2nd M joined by a segment, unrecognised edges -> PASS with 0 edges, mtime freshness not proof). Sent back to fixer; target crew 1.0.218. Next free: 1.0.219.
- 23:17: #359 T-0025 first review on 66d25049: PASS, 0 BLOCK, 0 FIX (3 NITs) -> CLEAN. Install scripts changed as a matched pair (36->37 label); README re-pin needed after it merges.
- 23:16: #368 fixes pushed (309575c2, crew 1.0.213): _main_folder carries 'could not tell' into the stop; cp -r paths shlex-quoted. Fixer now re-deriving moved crew_autopilot.py code-map citations (no plugin change) before re-review.
- 23:16: #337 round-2 fixes pushed (a9c56d43, crew 1.0.215): acceptance allow-list (parse_acceptance yes/no/unknown; bare name no longer accepted), qualified reach UNKNOWN, unparseable map UNKNOWN, parse_live trailing text UNKNOWN. Round-3 Sonnet re-review started.
- 23:15: #351 round-3 re-review on c610fe28: PASS, 0 BLOCK, 0 FIX (1 NIT) -> CLEAN. #375 red crew-shell-matrix on f6208e20/be507112: Windows jobs 'cancelled' by newer pushes (log: DEFAULT/SLOW/WALLCLOCK_RESULT cancelled), not failures; head is 16e92602. #337 round-2 fixer has 3 local commits (to 1.0.215), gating before push.
- 23:15: Fixes pushed: #372 a2651e47 (1.0.208, rekey cache, null reach, cwd classify, --map removed); #375 be507112 + 16e92602 (1.0.210, parser/UNKNOWN fixes; 7 stale diagrams re-rendered, all 33 PASS); #351 c610fe28 (1.0.217, --first-parent limit documented); #359 built + pushed 66d25049 (1.0.216). Sonnet re-reviews started: #372, #375, #351 (round 3); first review: #359. Next free version: 1.0.218.
- 23:12: #359 T-0025 built (11/11 sabotage red, suite 8924 passed pre-fix) but not pushed: version commit was not last. Decision: version-only final commit 1.0.216 (no reset), remove docs/tickets/T-0025, then push. Harness follow-ups: scope_guard deny text, review.md no-ticket stop, sabotage_help.py. After merge: re-pin README install URLs (both install scripts' label changed 36->37 commands). Next free: 1.0.217.
- 23:10: #337 re-review round 2: FAIL - new BLOCK (E5 acceptance is a deny-list: 'denied','never','rejected 2026-10-01' pass) + 2 FIX (reach negations 'not prod' read as prod; unreadable verify.json gives N/A). Original 4 resolved. Sent back to fixer; target crew 1.0.215. #351 fixes pushed (be8365c3, crew 1.0.211 + code map --first-parent); Sonnet re-review of #351 started. Next free version: 1.0.216.
- 23:08: #337 fixes pushed (4aa98c36, crew 1.0.209): E5 BLOCK fixed (live yes/no/unknown, blank reach UNKNOWN, acceptance must be affirmative), read_text absent vs unreadable, whole-word headers + env-name reach parsing, G4 ls-files rc. Each test red with fix reverted. Sonnet re-review of #337 started.
- 23:07: #360 re-review (Sonnet 5.5) on 23556e0f: PASS, 0 BLOCK, 0 FIX (NITs only) -> CLEAN; merges on its turn once CI green. #337 fix agent committed 3 commits locally (73054896, 911b9dcf, 4aa98c36 = 1.0.209), gating before push.
- 23:06: #360 FIX fixed and pushed (23556e0f, crew 1.0.212): guide + README no longer say questions need allowCliApproval; crew-guide.py rule (e) added, sabotage red. DOCX/PDF NOT rebuilt (LibreOffice broken here) - owner: run build.py --guide guide. Sonnet re-review of #360 started.
- 23:04: #374: red crew-shell-matrix (windows) on b64a18d5 is a cancelled superseded run (log: decide job 'cancelled'), not a failure. Note: frequent pushes to this branch cancel each other; only the latest head's CI counts.
- 23:03: Re-review #378 + #350: both PASS, all 4 earlier FIX resolved. Pair note: #350 must be merged forward after #378 lands (planned re-merge step). Uncommitted qa_audit_env.py in the primary checkout is the #337 fix agent's work in progress, not abandoned.
- 23:03: Helper in place: each action from now appends one line here and pushes.
- 23:03: Started this file (owner request). Earlier entries are in order, without exact times.
- Fix agent started for #355 (1 FIX).
- Round-1 reviews complete for all 11. Fix agents started for #372, #337, #375, #351, #360
  and #368. #350 fixed by hand: CONFIG.md §10 count, implement.md exit-1 wording, BUDGETS count,
  version 1.0.207 set last. A gate failure did not stop one push (a pipe hid it); this was repaired
  by 2d83d373, and pushes now use `set -o pipefail`.
- #374 review FIX items fixed (b72269d9): merge order and scope line.
- Owner approved review-gated merging. Eleven Sonnet 5.5 reviews started. The dependency map
  was added to `pending-tickets.md`.
- main took #334 (crew 1.0.163). #372, #337 and #375 were re-merged and re-bumped
  (1.0.203–1.0.205).
- Group A done: #350, #351, #355, #360, #368 and #371 merged with main and verified.
