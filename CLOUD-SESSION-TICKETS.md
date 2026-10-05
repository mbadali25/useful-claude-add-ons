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

| L-1503 | HIGH: `promote-gate.ps1` gives no gate on PowerShell when an environment's `deploy` string holds a `[set]` (e.g. `jq .items[0]` never matches itself) or an unreadable pattern (`[`, `[]`, `[z-a]` throws, iteration skipped). Pre-existing; found reviewing #407. | #489 | review-clean at 9dba8652 (round 4: 0 BLOCK, 0 FIX); lands BEFORE #407, which must adopt the union rule in _gate_pick |

| L-1504 | Harness-only: approval hook / scope guard accept only the owner's typed `/crew:autopilot sleep`, then unlock loosening. Note: a plain-text "good night"/"heading to bed" routed sleep (L-0662, live since batch 5) is NOT the owner's typed command and must not count as one; document in README/CONFIG when L-1504 lands in manual sleep (L-0652 ships tighten-only until then). Owner decision 2026-10-04. | none yet | needs ticket in your tracker |
| L-1505 | Harness-only: when a deploy command matches several environments (L-1503 union rule), verify-gate.sh records one PROMOTIONS row per matched environment instead of the joined name `staging,prod`, so a later `requires: [prod]` is satisfied. Fails closed until then. Also: verify-gate.sh:192/:207 parse the in-flight marker with `read -r DENV DSHA` (a name with a space splits) and :208 greps $DENV as a regex (`a|b` matches row `apple`, `.` matches any char) - escape the name and parse the marker by its last field (found in #489 round-4 review). | none yet | needs ticket in your tracker |
| L-1506 | CI: crew Windows default set split into 6 shards instead of 3 (owner request 2026-10-04, rush speed-up) | #491 | MERGED 9c8c0418 (no plugin version; CI-only) |
| L-1507 | CI: crew Windows slow set split into 3 shards (owner request 2026-10-04, after L-1506) | MERGED 1a5b3dca (#492; CI only) | needs ticket in your tracker |
| L-1508 | Ticket written (owner request): audit crew hook Python for bare-name `subprocess.run(["tool", ...])` where a check resolves the tool with `shutil.which` (PATHEXT) but the run uses CreateProcess (.exe only) - two Windows bugs today (T-0016 `_tmux_pane_pid`, T-0017 `_git_out`, the latter fail-open). Add a lint/test that flags the pattern. | #493: owner decided scope option 1 (2026-10-04); PR A REVIEW-CLEAN at dbff75d9 (round 2: 0 BLOCK, 0 FIX), CI green first run; next landing batch. Carry: webtest_guard allowlist gate cite :664 -> :658. PR B (9 harness files) follows, lands alone | needs ticket in your tracker |
| L-1509 | Follow-up to L-1508: `skills/repo-docs/scripts/git_changelog.py:71` and `repo_survey.py:140` run a bare `git`; also `plugin/obsidian-vault/hooks/scripts/vault_garden.py:662,667` (bare git via `_run_bounded`) and `plugin/rule-of-two/scripts/rule_of_two.py:577` (bare `codex`, an npm .cmd on Windows -> reads "ran: False"); resolve it with shutil.which ; also `plugin/gizmoduck/scripts/scanners/depcheck.py:101,112` runs bare `dependency-check` (a .bat on Windows) after `base.which` found it at :64 - same found-one-way-run-another bug; consider teaching the lint attribute calls for non-colliding wrapper names (run_tool, _run_bounded, capture, execute_job). Each plugin its own bump. | none yet | needs ticket in your tracker |
| L-1510 | `test_crew_ticket_mint.py::test_concurrent_mints_distinct` failed once on Windows CI (#493 shard 4/6): "crew_ticket.TicketError: .work/INDEX.md exists but could not be read" - ALSO RED ON MAIN (run 37221280492, a27c5e38). Cause: `_mint_taken` (crew_ticket.py:1079-1083) reads INDEX without the INDEX lock while another minter's tracker create does os.replace; Windows sharing violation -> read_text None -> mint refuses. Fix: retry on PermissionError or read under the lock. Harness (crew_ticket.py). Root-cause; never skip. | MERGED 8c0843ca (#494, crew 1.0.338) | needs ticket in your tracker |
| L-1511 | Follow-up to L-1510: `crew_tracker.py create` and `move` (or `_atomic_update` on INDEX) take `.work/INDEX.md.lock`, the same lock mint uses. Every unlocked `move` (implement.md:33,112, done.md:82, spec.md:46, review.md, plan.md) replaces INDEX while parallel lanes mint; on Windows mint then refuses (never a wrong id). Not harness. | none yet | needs ticket in your tracker |
| L-1512 | Windows CI: cloud-guard bash tests intermittently exit 2304 (MSYS bash SIGKILLed) - `test_cloud_guard.py::test_must_block_bash[aws-s3-rm-recursive]` (#493 slow 1/3) and `test_identity_bash[aws-read-known-profile-other-cloud-pinned-ok]` (#356 slow). Likely a per-test timeout killing a slow Git Bash under load. Root-cause; never skip. | #497 built (c56ffc72, CI green incl. 12 Windows jobs), in review. Cause: python probe in _common.sh SIGKILLed a live watchdog -> killed the hook itself (guard bypass risk: a killed hook is non-blocking) | needs ticket in your tracker |
| L-1514 | read-cloudhead skill on main: "read Cloudhead" resumes the cloud session from this notes branch | #495 MERGED | needs ticket in your tracker |
| L-1515 | Windows CI flake on main 3ccd527e (run 37240220917): `test_auto_cycle.py::test_the_detached_sender_does_not_outlive_kill_process_group` - "sanity: at most one live job member ([3212])". Did not recur on #394. Root-cause; never skip. | none yet | needs ticket in your tracker |
| L-1516 | Follow-up to L-1512: obsidian-vault hooks (vault-capture.sh, vault-guard.sh, bridge-status.sh) carry the same python probe whose kill -9 of a live watchdog can kill the hook itself on Windows; port the read -t watchdog fix (own obsidian-vault bump). | none yet | needs ticket in your tracker |
| L-1517 | promote-gate.ps1 writes a non-ASCII environment name into `.deploy-in-flight` as `?` (encoding), so the Stop check cannot match it to a PROMOTIONS row (fails closed; found in #407 review fuzz, pre-existing on main). | none yet | needs ticket in your tracker |
| L-1518 | README.md: replace the ~500 lines of stale generated "What's new in the plugins/skills/MCP" sections with one short "What's new" section (two latest updates + link to CHANGELOG.md), generated by scripts/sync-updates.py (owner request 2026-10-05). | building | needs ticket in your tracker |
| L-1513 | Harness (L-0671 family): sabotage entry "approve writes beside the receipt" (sabotage_autopilot.py) inserts 4-space code after crew_autopilot.py:1668, landing inside T-0053's try/finally -> SyntaxError (RED BUT UNPROVEN, exit 4). Broken on main since T-0053. Re-anchor. Also: no test ties argparse choices to the usage block (a new subcommand missing from usage escapes the writer check). | none yet | needs ticket in your tracker |

| C-0001 | PR #501 (c2a133b7, CI green 29/29, draft). TOP PRIORITY (owner). Owner request 2026-10-05: per-component CI skip (gizmoduck/crew/each skill/mcp run only if changed; shared paths run all) plus docs-only PRs skip Pytest, Pylint, Shell suites, MCP servers via a shared decide script (crew-windows-decide pattern, fail-closed: unknown diff runs). Marketplace, Instruction budgets, Verify gate always run. `.md` files that are prompts or are read by suites/checks are NOT docs. | builder on `C-0001-build` | CI-only PR, lands ALONE |

| C-0002 | From #496 review (NIT): on Windows, when git resolves to a `.cmd` shim, cmd.exe drops `^` from `^{commit}` / `^{tree}` peels at completion_audit.py:184, review_patch.py:282, :382, so the completion audit and the review bundle always refuse there (fail-closed). Use a peel without `^`. Harness: lands alone. | none yet | follow-up after #496 |
| C-0003 | From #496 review (NIT, pre-existing): verify_fingerprint `_sub_changed` turns a git failure into "nothing changed" and `_head` reports a failing git as "no-head", so an unknown collapses into the safe-looking value (CLAUDE.md Lessons). test_verify_fingerprint_listings_run_the_git_which_resolves pins the empty result. Harness: lands alone. | none yet | follow-up |

| C-0004 | From C-0001 build: `crew-windows-decide` (pytest-crew.yml) skips the Windows crew jobs when a PR changes only `scripts/**`, but crew's tests read scripts/ (check-tooling-pr.py, tooling-pr suite, etc.). Pre-existing gap. Make the Windows decide use the same selector (or treat scripts/** as crew). | none yet | after #501 |

| C-0005 | From #501 review (pre-existing): suites run by NO gated workflow: plugin/localgpu/{cli,mcp}/_test, plugin/rule-of-two/scripts/_test, skills/github/scripts/_test, skills/work-log-reporter/scripts/_test. Wire them into CI (and the selector map). | none yet | after #501 |

| C-0006 | Owner 2026-10-05: at the end of this push, bump crew to 1.1.0 (minor) and rename the guide files from crew-1.0-guide.* accordingly (guide build, links, claims). Lands as its own PR after the last batch. | none yet | last |

| C-0007 | From #357 review (pre-existing): a repo whose path ends in a space can't use autopilot focus: crew_ticket.toplevel/_git returns the path without its trailing space, so focus_path is None ("no git common dir"). Root-cause in crew_ticket._git; check every toplevel consumer. | none yet | after batch 7 |

| C-0008 | Owner 2026-10-05: gizmoduck tools in the cloud env. bootstrap.sh resolves 'latest' via api.github.com (403 here); direct release downloads and git ls-remote work. Fix: git-tags fallback in bootstrap.sh (+ idempotent skips), run it end to end here, and hand the owner a setup script that calls it. gizmoduck bump. | builder on C-0008-build | review, land |

| C-0009 | Owner 2026-10-05: ONE cloud setup script. Fold the coordinator's additions (pwsh, gizmoduck bootstrap, apt /tmp-755 sandbox fix, mermaid-cli + mcp npm, pytest uv-tool shadow fix) into the repo's scripts/cloud-env-setup.sh (#503, owner's other session). Stacked on #504 (bubblewrap). | builder on C-0009-build | after #504 |

| C-0010 | From #401 review (pre-existing): ci_receipt.py's parser lets a failing rule's own output inject `verify-gate: Ns  <cmd>` lines, producing an extra PASS row for a command (pending.pop then elapsed => PASS). Bind elapsed lines to the command the gate is actually running (sequence), not to any matching text. Not acceptance-affecting today (check never reads commands) but the receipt list can lie. | none yet | after #401 |

Next free untracked ID: **C-0011** (owner rule 2026-10-05: cloud-session tickets use the C-NNNN series from now on; L-1500 to L-1518 keep their IDs because they are already in PR titles and merged commits).

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
| T-0084 | #450 | 6dead441 | 1.0.331 |
| T-0053 | #403 | a27c5e38 | 1.0.332 (slice 1) |
| L-1506 | #491 | 9c8c0418 | none (CI workflow only: Windows 3 -> 6 shards) |
| T-0016 | #396 | f1cace4a | 1.0.333 |
| L-1507 | #492 | 1a5b3dca | none (CI workflow only: Windows slow set split into 3 shards) |
| T-0017 | #356 | d64f113e | 1.0.334 |
| T-0047 | #347 | 59fe7d84 | 1.0.335 |
| L-0677 | #456 | 644adfc2 | 1.0.336 |
| T-0082, T-0080 (H2a harness bundle) | #399 | 17934e60 | 1.0.337 (#475 closed) |
| L-1510 | #494 | 8c0843ca | 1.0.338 |
| T-0074 | #481 | a92dc59a | 1.0.339 (slice 1 of 3) |
| L-1508 (PR A) | #493 | 0bf91c95 | 1.0.340 |
| L-0652 | #427 | bbd1d0ee | 1.0.341 |
| L-1503 | #489 | a31ac3bb | 1.0.342 |
| L-0680 | #400 | 2aa06aca | 1.0.343 |
| T-0083 | #421 | cab38cfa | obsidian-vault 0.5.0 |
| T-0037 (A) | #394 | 189c3b80 | 1.0.344 |
| T-0052, T-0057, L-0662 (batch 5) | #498 (lands #364, #416, #420) | efcf4666 | 1.0.345 |
| L-1518 | #499 | 7ba4c184 | (repo tooling, no bump) |
| L-1512 | #497 | 2828acef | 1.0.346 |
| L-1508 (PR B, harness) | #496 | 8479a837 | 1.0.347 (also: root README.md added to check-tooling-pr ALONGSIDE) |
| T-0045, T-0041, L-0582, T-0050 (batch 6) | #502 (lands #500, #348, #338, #361) | 47f71e93 | 1.0.348 |

## Closed without merging (your instruction)

| Ticket | PR | Note |
|---|---|---|
| T-0104 | #274 | Closed; spec stays in `docs/handoff/cloud/`. |
| T-0500 | #275 | Closed; spec stays in `docs/handoff/cloud/`. |

## In the landing train (built, reviewed or under review)

| Ticket | PR | Head | Status | Notes |
|---|---|---|---|---|
| T-0059 | #366 | e14b5a45 | ready to land | Stacked on T-0052 (#364). |
| T-0058 | #365 | 16228584 | ready to land | Stacked on #364/#354. Carry: `_gate_stage` must pick stage like `_phase`; `split_report current=` from `_not_current`. Decision: absent sources read as unmeasured (owner-approved). |
| T-0098, T-0109, T-0101 | #418 (H1 bundle) | ea9dcc10 | ready to land (harness, lands alone) | #461 (T-0109) and #422 (T-0101) close at landing. Owner note: also tightens plain `--accept`/`--reject` (refuse multi-line / lookalike `auto:` names). T-0109 Q3 (name only, no owner auth) confirmed not to loosen the gate. |
| T-0045 | #407 | 6cada04c | ready to land | Slice 1 of 8 (`crew_ghdeploy.py check`). `check` now simulates both promote gates. |
| T-0057 | #416 | 2eaac674 | ready to land | Carry at landing merge: route the 3 autopilot sites through T-0069's `_route()`, drop `_LINE_BREAKS`, re-review the merge. Printable-ASCII allowlist for free text. Also fixes a main bug: `implement ſ-12` routed to S-12. |

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
| L-0652 | #427 | review-clean at 20a4168c (round 2: 0 BLOCK, 0 FIX, 3 NIT); manual sleep tighten-only until L-1504. Carry at landing: test for the 25-real-hour backstop (Antarctica/Troll case); thread+timeout guard on test_fstat_refuses_a_swapped_in_fifo... so an O_NONBLOCK regression fails instead of hanging CI; CHANGELOG:42 "24 hours after at" wording | manual /crew:autopilot sleep and wake (state file under git-common-dir/crew, gated on scop |
| L-0653 | #431 | not started (spec only) | sleep log and morning summary (.work/autopilot/sleep-log.md, sleep-note, sleep-summary) |
| L-0654 | #435 | not started (spec only) | sleep deploy override, nonprod only; production always waits while asleep |
| L-0655 | #438 | not started (spec only) | sabotage mutations for manual sleep, the sleep log and the deploy override (tooling-only P |
| L-0656 | #444 | not started (spec only) | sleep overrides for keys that do not exist yet (review policy, held pings) - BLOCKED until |
| L-0657 | #480 | not started (spec only) | T-0055 child 1: CI fails when a built crew guide is stale |
| L-0658 | #463 | not started (spec only) | A `--goal` handoff is checked against the goal file, not the branch and head |
| L-0659 | #469 | not started (spec only) | Bare `/crew:autopilot` finds a running goal when there is no usable handoff |
| L-0660 | #472 | not started (spec only) | Sabotage entries for goal resume: writers, handoff validation, discovery (tooling-only PR) |
| L-0661 | #417 | not started (spec only) | T-0057 child 1: sabotage mutations for the autopilot routing rows (tooling-only PR) |
| L-0662 | #420 | review-clean at aa3e06d5 (0 BLOCK, 0 FIX); stacked on #416, needs re-merge + re-bump after #416 lands | T-0057 child 2: plain-text routing rows for autopilot wave, split, sleep and wake |
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
| L-0678 | #462 | not started (spec only) | crew_memory.py migrate and restore - convert existing native memories, previewed and opt-i |
| L-0679 | #466 | not started (spec only) | sabotage entries for crew_memory.py (tooling-only PR) |
| L-0680 | #400 | REVIEW-CLEAN at 897f3faf (round 4: 0 BLOCK, 0 FIX), CI green incl. Windows; batch 4. Carry: -LiteralPath for Test-Path/Set-Content/Get-Content in handoff-write.ps1:504,530-531 and handoff-read.ps1:334,367; one CHANGELOG line on the trailing-backslash directory rule | T-0096 child 1: the session hooks (notify, handoff-read, handoff-write, context-watch) inh |
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
| T-0083 | #421 | review-clean at 41b1d576 (round 5: 0 BLOCK, 0 FIX, 1 NIT); obsidian-vault 0.5.0; batch 3. Untested on a real vault and on Windows | vault recall relevance: prefer this repo's project and concept/decision notes, skip archiv |
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

### Owner decisions, 2026-10-05 (cloud session)
- #407 T-0045: rebuild on a FRESH branch from main (#500), not revert-the-revert.
- T-0020 #357: **explicit focus only** — focus is on only after `/crew:autopilot focus <id>`; an active-ticket pointer is not focus. Main's plain-text routing wins. Rework for batch 7.
- Batch 6 ships with 4 (#500, #348, #338, #361); T-0020 held out.
- T-0020: plain-text "focus on T-1" turning focus on counts as EXPLICIT (owner confirmed 2026-10-05), same as "heading to bed" -> sleep. Keep the routing row.
- Notes: write after every action, but PUSH every ~30 min and at each merge (note.sh commits locally; `note.sh --push`; auto-push if last push >30 min).
- Windows-red review-clean PRs (#341 #342 #344 #346 #362 #363 #395): merge main into each and re-run Windows AFTER batch 7.
- crew 1.1.0 at the END of this push, plus a guide-rename PR (ticket C-0006).
- Owner 2026-10-05 05:10: crew 1.1.0 (C-0006) CLOSES this rush. The NEXT rush starts after it, on the remaining new draft PRs (the spec-draft waves in docs/handoff/cloud/WAVES-2026-10-04.md).
- T-0108 (#451): try installing Nuclei in the build container; if impossible, build anyway and mark the exclusion-beats-tags premise NOT VERIFIED in the PR (owner 2026-10-05, option A).
- C-0002..C-0005 (and C-0007) after batch 7.
- C-0001 (per-component CI skip) is TOP PRIORITY.
- #499 README: show 2 newest updates + changelog link (shipped).

## Owner decisions, 2026-10-04 evening (open questions that blocked builds)

| Ticket | Question | Decision |
|---|---|---|
| L-0674 (#404) | Build a gate-owned deadline for a hung rule? | **Not built.** #404 closed; T-0082 already fails a hung rule closed (COULD NOT TELL). Revisit only if real hangs show up |
| T-0029, T-0030 | No spec, branch or code; 8 tickets wait on them | **Deferred**, out of this rush: T-0031, T-0032, L-0633, L-0634, L-0636, L-0637, L-0635, L-0638 |
| T-0073 | Keep for `reviewAcceptance`, or close? | **Close as superseded** by L-0510 + T-0074 (no open PR found here; close it in your tracker) |
| L-0635 Q2 | Missing must-block test found by the sabotage PR | **Add it in that PR** (tests ride along under T-0087) |
| L-0639 Q5 | Home of the `depends-on:` parser and header status helpers | **L-0639 owns them, in `crew_ticket_state.py`**; `crew_ticket.py` (harness) untouched |
| L-0640 Q4 | Where `superseded-by:` lives | **spec.md line 2**, the line #394 already reads; next.md does not repeat it |
| L-0550 Q5 | Header words hold/landing/needs-owner? | **No header words.** hold = next.md `waiting-on`/`revisit`; needs-owner = INDEX row (#394); landing derived from a current review receipt |
| L-0551 Q7 | One status line or two | **One line:** `waiting  N on you: <ids> (/crew:status --owner)`, replacing #394's separate owner line |
