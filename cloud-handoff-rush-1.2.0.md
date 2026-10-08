# Cloud handoff: feature rush 1.2.0

Live log of the cloud session `crew-rush-2` (session_01QLY3kk7DCXpucXGu3wSniW) working PRs #324-#538
into crew **1.2.0**. Lives on branch `claude/eloquent-wozniak-iqb4hf` (draft PR #514 into
`release/1.2.0`, docs-only, merges last). Every coordinator action appends a line to the Log via
`docs/handoff/cloud/rush-1.2.0/note.sh "<what happened>"`, which commits and pushes. Ticket status
and the group table are in `pending-tickets.md`, section "Feature rush 1.2.0".

Last updated: 2026-10-08T04:02Z

## >>> RESUME HERE

1. `git fetch origin`; check out `claude/eloquent-wozniak-iqb4hf`; read this file and
   `pending-tickets.md` "Feature rush 1.2.0".
2. Recreate the scratchpad helpers from `docs/handoff/cloud/rush-1.2.0/`: `BRIEF.md` (the builder
   brief, incl. HARNESS addendum and RESUME section), `codex-review.sh` + `review-schema.json` (fix the
   `S=` path inside to the new scratchpad), `note.sh`.
3. Codex: `codex login status` must say logged in; if not, `codex login --device-auth` and give the
   owner the code. Model `gpt-6-sol` (the owner's "gpt-6.0-sol"), `-c model_reasoning_effort=high`.
4. For each group branch `rush/<group>`: `git log origin/<base>..origin/rush/<group>` and the newest
   `$S/reviews/<group>-*.json` (lost if the scratchpad is lost: then re-review the branch head).
   Worktrees live at `/home/user/rush-<group>`; recreate with `git worktree add` from the pushed branch.
5. Relaunch one builder per unfinished group with the brief + that group's scope (table below).
   Builders push after every commit.
6. Tell the owner, in a short table, where things stand and what you do first.

## Standing rules (owner, 2026-10-05)

- **Merge rule (owner 2026-10-07, replaces the group-review rule):** every source PR / ticket gets its own
  Codex review (`gpt-6-sol`, high) to 0 BLOCK / 0 FIX. Once the builder has added it to a group (merge
  train) PR, the group needs NO further Codex review: the group PR merges on green CI on its head (plus
  the lander's gates and full crew suite). Merge commits only. Codex runs do not count toward the agent
  cap (10 Claude agents, owner 2026-10-07).
- **Structure:** groups -> `release/1.2.0` (feature lanes) -> one PR to `main`. Harness lanes go to
  `main` alone (CLAUDE.md T-0087): **H1 -> H3 -> release/1.2.0 -> H2**. H2 is last and sets crew
  **1.2.0**.
- **Versions:** ONE counter shared by release groups and H lanes on main (assigned at landing, in landing order); no bump when a source PR folds into a group; every merge into `release/1.2.0` or
  `main` takes the next free 1.1.x in the LAST commit; re-merge => re-bump (the drift check dates a
  version from its first commit). Other plugins bump their own patch.
- **New tickets** minted by this rush start at **C-0020**, recorded in `pending-tickets.md`.
- **Commits** end with `Claude-Session:` only (no Co-Authored-By) - owner confirmed 2026-10-05.
- **Add groups as needed** for late tickets (owner 2026-10-05).
- **Owner 2026-10-05 (recommendations accepted):**
  1. H1/H3: whichever is ready first lands first; the second merges main and gets a merge-only review.
  2. At most ~8 agents at once (4 cores, Codex capacity); start new builders only as others finish.
  3. Release groups land as soon as each is ready (only G0 before G3c, G2 before G6 are fixed).
  4. Per-ticket review cap 6 rounds; the coordinator reviews the round-6 fix itself.
  5. Close each source PR when its content reaches main, with a link to the group PR.
  6. G6's sleep tickets (#431, #435, #444) drop to after 1.2.0 if G2 lands after every other release group.
  7. Keep `gpt-6-sol`; switch reviews to `gpt-6.1-sol` only if capacity errors persist.
- The other landing session (ended at crew 1.1.0, #512) stays out of #324-#538 (owner asked it, 2026-10-05).

## State  [refreshed 2026-10-08T02:45Z, session_01H49aKnVMcvefcadqBGmuMu]

**10 of 12 waves are on main.** Each wave = one group PR into `release/1.2.0`, then `release/1.2.0` -> `main`.

| Ref | SHA | crew |
|---|---|---|
| `main` | `7a62e848` (wave 10, #569) | 1.1.19 |
| `release/1.2.0` | `196e31fa` (G3d, #567) | 1.1.19 |
| next free version | | **1.1.20** (G6a), then 1.1.21 (G6b), then **1.2.0** (H2b) |

### Remaining, in order

| # | Lane | Branch / PR | State | Next |
|---|---|---|---|---|
| 11 | G6a autopilot | `rush/g6a-autopilot` -> #570 (head `12d99dfe`, crew 1.1.20) | CI running | merge into release, then wave 11 PR release -> main |
| 12 | G6b goals+sleep | `rush/g6b-goals-sleep` (head `ebee2f34`, unmerged with release) | built, Codex-reviewed per ticket | builder: revert placeholder version, merge release, fast checks, crew 1.1.21 last, PR into release |
| last | H2b harness | `rush/h2b-sabotage` (head `6601d151`, no version commit, no PR) | built; Codex CLEAN (0/0/0) | after G6b on main: merge main, `git apply docs/tickets/H2b/deferred.patch` (115 entries), add the L-0651 (k) must-block test, re-check every anchor, delete the patch file, crew **1.2.0** last, PR to main alone |

H2b detail: 393 entries on main all RED; 115 deferred all RED on a scratch merge (anchors may move when
G6b really lands: re-run them). Unresolved: L-0651 (k) needs a new must-block test (G6b made
`autopilot.sleep.deploy` real; `reviewPolicy` has no assertion). Coordinator recommendation, not yet built.

### Side PRs (not part of the release)

| PR | What | State |
|---|---|---|
| #571 | README install URLs re-pinned to `7a62e848` (wave 10 changed both install scripts) | CI running; merge when green |
| #568 | CI: `CREW_WINDOWS_RUNNER` sends crew-windows-* jobs to a self-hosted pool | **do not merge yet**: trial on winrepo2 failed (wallclock 7.1 min vs 2.3 hosted, 8 timing bounds missed, `mktemp` not on PATH). Owner to fix the runners; fallback is to keep wallclock on hosted |
| #514 | these notes | docs-only, merges last |

### Runners (owner, 2026-10-08)
- Linux self-hosted pool live: repo variable `CREW_RUNNER=self-hosted` (set by hand; the infra playbook normally owns it and deletes it when the host idles). `test (3.12)` 18 min hosted -> 4.4 min self-hosted. `start-if-stopped` is now skipped (no more red).
- `CREW_WINDOWS_RUNNER=winrepo2` is set but only #568's workflow reads it; main ignores it until #568 merges.
- The proxy blocks Actions **variables/runners** APIs from cloud sessions; job re-runs (`POST .../actions/runs/<id>/rerun-failed-jobs`) work.

### Owner decisions this session (2026-10-07/08)
- Build H2b in parallel with the groups (deferred entries kept as a patch).
- Testing policy: builders run only fast checks + targeted pytest; the **full suite runs in PR CI** on the self-hosted runners.
- G6a: keep L-0666's contract for the stale-after-review stop (L-0522 stop names no command).
- 10-12 waves, one group per wave.

### Bugs the waves caught
- G3d / L-0708: kimi_probe read git's two-line "Stopping at filesystem boundary" answer as could-not-tell when TMPDIR sits on its own mount (self-hosted runner). Fixed in `dcb479c9` (`GIT_DISCOVERY_ACROSS_FILESYSTEM=1`, regression test).
- G6a: owner list showed `Complete/` archive as an open ticket; fixed with a test.

### Follow-ups after 1.2.0 (not blocking)
- C-0049..C-0064 (+ C-0033/35/36/38/41/48/62); next free **C-0065**.
- 10 sabotage entries STILL GREEN on release that are not ticketed (promote gate, auto-accept, 5 cloud-guard PowerShell, limit markers, sabotage-bound) -> mint one C ticket.
- C-0061 Windows wallclock overruns on hosted runners (wave 10 needed one re-run).
- Autopilot verify rule runs ~54s vs declared 30s (re-price).
- Owner: `RUNNER_START_TOKEN` 404 on github-runner-infra; #544/#545 (other session, stale 1.1.5).

### Tools (scratchpad is ephemeral: copies here)
`docs/handoff/cloud/rush-1.2.0/`: `codex-review.sh` (fix `S=`), `review-schema.json`, `waitci.sh`
(`bash waitci.sh <sha>`: waits for CI, prints non-success checks), `note.sh`, `BRIEF.md`, `LANDING.md`.
Merge with `gh api -X PUT repos/.../pulls/N/merge -f merge_method=merge -f sha=<head>` (the MCP merge tool 500s).
Close source PRs GitHub did not auto-mark merged, with a "landed via port" comment.

## Log (newest first)

- 2026-10-08T04:02Z H2b steps 1-6 done at 3bc9ef5d: 510/510 entries RED on the merged tree. L-0651 (k) test added. C-0038 scope_guard entry fixed by a stricter refresh-allowance test. Codex review of the apply commit started. Waiting for wave 12 #574 before merging main and writing 1.2.0.
- 2026-10-08T03:45Z MERGED #573 (G6b) into release at 16fc5147, crew 1.1.21. Opened WAVE 12 #574 (last feature wave). H2b lander started.
- 2026-10-08T03:23Z G6b #573: test (3.12) failed test_autopilot_report_calls_run_stop. The merge had joined goal-mark --reason-file onto the run-stop line in autopilot.md. Restored the break, rejoined the focus paragraph to stay in budget. 1644 autopilot.md tests pass. New head c43f89a7, crew 1.1.21 re-applied last.
- 2026-10-08T03:14Z Owner deleted CREW_WINDOWS_RUNNER. Closed #568 and kept the branch ci/windows-self-hosted for later.
- 2026-10-08T03:12Z Owner chose C: Windows CI stays on GitHub-hosted. #568 stays unmerged. CREW_WINDOWS_RUNNER=winrepo2 is still set; it must be deleted before #568 can ever merge, or main's Windows CI moves to winrepo2.
- 2026-10-08T03:11Z G6b opened #573. Fixed the 4 G6b settings' since-version 1.1.16 -> 1.1.21 inside a fresh version commit; new head b39c433220e81910dcc4e8df8644971b9527d2e2. H2b note: the anchor 'an edit to scope_guard.py runs no pytest rule' (verify.json block) matches 0 times after G6b; re-anchor it at H2b landing.
- 2026-10-08T03:09Z WAVE 11 MERGED #572 to main at 21bdec76 (crew 1.1.20). Closed #485 and #486 as landed. Next: G6b (1.1.21); its builder is running.
- 2026-10-08T02:51Z MERGED #571 (README install URLs re-pinned to 7a62e848) into main.
- 2026-10-08T02:50Z MERGED #570 (G6a) into release at e600ffdf, crew 1.1.20. Opened WAVE 11 #572. G6b builder started.
- 2026-10-08T02:40Z Owner asked for a handoff cleanup. Closed 10 cloud-handoff PRs landed via H2a #564: #413 #417 #419 #424 #429 #440 #466 #470 #482 #522. Kept the partials #423, #438 and #484 (the rest is in H2b), and every G6a/G6b/H2b source until landed. #391 updated, not closed (it is read-cloudhead's notes branch).
- 2026-10-08T02:35Z WAVE 10 MERGED #569 to main at 7a62e848 (crew 1.1.19); the wallclock re-run passed. Closed #434 and #547 as landed. Opened #571 to re-pin the README install URLs to 7a62e848.
- 2026-10-08T02:32Z Owner: keep L-0666 for the stale-after-review stop (G6a as built).
- 2026-10-08T02:31Z G6a opened #570 into release, head 12d99dfe, crew 1.1.20. Decision needed: the L-0522 vs L-0666 stale-after-review stop was resolved in L-0666's favour (no command in the stop). Also: crew_autopilot split into crew_autopilot_paste.py, and an owner-list bug fixed (Complete/ archive shown as open).
- 2026-10-08T02:22Z Owner set CREW_WINDOWS_RUNNER=winrepo2. #568 now accepts one bare label; pushed so its CI runs as the trial.
- 2026-10-08T02:14Z Wave 10 #569: crew-windows-wallclock overran (10.1s vs 10s) on hosted Windows. The same tree passed on #567. C-0061. Commented; will re-run once when the run completes.
- 2026-10-08T02:10Z MERGED #567 (G3d) into release at 196e31fa, crew 1.1.19. Opened WAVE 10 #569. TODO after merge: re-pin the README install URLs. G6a builder started.
- 2026-10-08T02:07Z Owner asked to try Windows CI on winrepo2 self-hosted runners (4). Opened #568 to main (CI-only, not harness): CREW_WINDOWS_RUNNER JSON-label switch with a fork guard. Codex: 1 BLOCK and 1 FIX, both fixed. Head 7c70fc32. Waiting for the owner to set the variable with the runners' labels.
- 2026-10-08T01:49Z G3d #567: test (3.12) failed 92 tests on a self-hosted runner. Real L-0708 bug: TMPDIR on its own mount makes git stop at the boundary with a two-line answer, read as could-not-tell. Fix dcb479c9 sets GIT_DISCOVERY_ACROSS_FILESYSTEM=1, plus a regression test (sabotage-checked). New head 0e29e05797d9f163ffd0a73b95097f7169a5743d, crew 1.1.19 re-applied last.
- 2026-10-08T01:40Z G3d opened #567 into release, head cf1224e4, crew 1.1.19. Command count now 38; both install scripts' catalog label changed, so re-pin the README install URLs after wave 10 reaches main. Local full pytest passed: 17438 passed.
- 2026-10-08T01:39Z Owner: run pytest on the self-hosted runners via PR CI instead of locally. From G3d on, builders run only fast checks plus targeted pytest before pushing; CI does the full suite. No group merges until CI is green.
- 2026-10-08T01:31Z Owner started 3 self-hosted Linux runners and set CREW_RUNNER=self-hosted by hand. Not verified from here (proxy blocks Actions paths). Check on G3d's PR CI: start-if-stopped should be skipped and test (3.12) should run on a self-hosted runner. Windows jobs stay on windows-latest.
- 2026-10-08T01:17Z WAVE 9 MERGED #566 to main at 720cc8cd (crew 1.1.18). Closed #408 and #410 as landed. Next: G3d (1.1.19); its builder is running.
- 2026-10-08T00:58Z MERGED #565 (G3c) into release at 33d35605, crew 1.1.18. Opened WAVE 9 #566. Starting the G3d builder on release 33d35605.
- 2026-10-08T00:34Z G3c opened #565 into release, head dfcc08a3, crew 1.1.18. Local checks clean. Gate sabotage step: 22 non-red entries, all identical on release cb17abdf (pre-existing, not G3c). Waiting on CI.
- 2026-10-07T23:29Z Codex review of H2b at 6601d15 came back CLEAN (0/0/0). It ran ~110 commands and checked that live and deferred anchors are unique; it did not execute tests (read-only sandbox). The builder's RED runs cover execution.
- 2026-10-07T23:25Z H2b built at 6601d151: 393 entries on main, all RED; 115 deferred in docs/tickets/H2b/deferred.patch, all RED on a scratch merge. L-0651 (k) unresolved (needs a new must-block test). Codex review of H2b started.
- 2026-10-07T22:30Z Owner OK'd building H2b in parallel. A builder started on rush/h2b-sabotage from main cb17abdf. Entries anchored on G3c/G6b code are held back. No version bump, no PR until G6b lands.
- 2026-10-07T22:17Z WAVE 8 H2a MERGED #564 to main at cb17abdf (crew 1.1.17). Release fast-forwarded to main. Closed #516 and #517 as landed. Next: G3c (1.1.18).
- 2026-10-07T21:56Z H2a opened #564 to main, head a93cd9b8, crew 1.1.17. Moved L-0682 tests to test_config_files.py (pylint cap). Local gates clean. Waiting on CI.
- 2026-10-07T21:40Z WAVE 7 MERGED #563 to main at 5a017c30 (crew 1.1.16). Closed #336 as landed via port. Next: H2a.
- 2026-10-07T21:16Z MERGED #562 (G4) into release at b0293543, crew 1.1.16. Opened WAVE 7 #563, subscribed.
- 2026-10-07T20:57Z G4 ready a4cc6582 (1.1.16; full crew 17040/0; Windows 16/16). Opened #562 (G4 -> release), subscribed.
- 2026-10-07T20:40Z H2a ready at d2c52fc0 (crew 1.1.17; 3 entries moved to H2b; 416/418 touched sabotage RED, 2 pre-existing greens C-0038/C-0064). Opens after G4's wave 7 lands (merge main first).
- 2026-10-07T20:26Z H2a built: rush/h2a-sabotage 9d1a89a8, 19 tickets CLEAN, +294 sabotage entries, Windows 16/16. Incl. T-0029/T-0030 harness halves (scope guard now refuses review_ledger --accept/--reject + gh pr merge --admin for subagents). Told to move 3 entries anchored on G3c/G6b code to H2b and set crew 1.1.17. New order: G4 1.1.16 -> H2a 1.1.17 -> G3c 1.1.18 -> G3d 1.1.19 -> G6a 1.1.20 -> G6b 1.1.21 -> H2b 1.2.0. C-0064 minted; next free C-0065.
- 2026-10-07T19:39Z Release FF'd to main eaeb2f4d. G4 lander resumed: merge release, crew 1.1.16, crew-docs gate, full suite, Windows.
- 2026-10-07T19:39Z MERGED WAVE 6 #561 (h5 C-0060, harness-only) into main, crew 1.1.15 (29/29 green). Next: FF release to main, then G4 1.1.16.
- 2026-10-07T19:08Z #561 check red: crew-docs (T-0055) wants Docs: none trailer for crew_ticket.py change. Re-wrote version commit with 'Docs: none - ...' trailer (revert + fresh), check-crew-docs OK locally, pushed.
- 2026-10-07T19:06Z Opened #561 (h5, C-0060, harness-only -> main, crew 1.1.15, head 39f1c498; merged main 9b3ff4f2; README install URLs re-pinned to 9b3ff4f2). After it: FF release to main, then G4 (1.1.16).
- 2026-10-07T19:04Z MERGED WAVE 5 #559 into main at 9b3ff4f2 (crew 1.1.14; G1b + C-0063). G1b sources closed. Next: README install-URL re-pin (G5+G1b changed install scripts) + h5 (C-0060, 1.1.15) to main.
- 2026-10-07T18:45Z MERGED #560 (C-0063) into release at 04b0bf57, crew 1.1.14. Wave 5 #559 now on 04b0bf57 (retitled), CI re-running.
- 2026-10-07T18:27Z Wave 5 #559 test 3.12 failed twice (test_sabotage_bound pidfile race = real). Opened #560 fix/c0063-pidfile-race -> release (crew 1.1.14, test-only, atomic pid write). h5 local fix dropped (reset to origin ac645dcf); h5 -> 1.1.15, G4 1.1.16, G3c 1.1.17, G3d 1.1.18, G6a 1.1.19, G6b 1.1.20.
- 2026-10-07T17:51Z Opened WAVE 5 #559 (G1b; release 1567e7df). Owner: H2 split into 2-3 harness PRs. H2a builder started (rush/h2a-sabotage from main): sabotage whose target is on main (19 source PRs as applicable, T-0029/T-0030 harness halves regenerated, C-0021/25/28/42); deferred to H2b: G4/T-0009/C-0046/C-0047 re-add, G3c, G3d (C-0051), G6a, G6b (C-0055). Non-sabotage harness C-tickets after 1.2.0.
- 2026-10-07T17:44Z MERGED WAVE 4 #558 into main at 4f4b89b5 (crew 1.1.12); G5 sources all closed (#441 #458 with link). MERGED #555 (G1b) into release.
- 2026-10-07T17:17Z MERGED #552 (G5) into release at a2ed7326 (crew 1.1.12). Opened WAVE 4 #558, subscribed. README install-URL re-pin deferred to after wave 5 (G1b also changes install scripts).
- 2026-10-07T17:17Z MERGED WAVE 3 #557 into main at 7d035d84 (crew 1.1.11; Windows slow/wallclock jobs re-run once after runner-acquisition failures). G3b sources: #447 auto-closed; #425 #414 closed with link. Next: G5 #552 -> release -> wave 4.
- 2026-10-07T16:41Z MERGED #551 (G3b) into release at ae63d3d7, crew 1.1.11. Opened WAVE 3 #557, subscribed.
- 2026-10-07T16:40Z MERGED WAVE 2 #556 into main at 66d90f66 (crew 1.1.10). G2 sources: #358/#369 auto-closed; #354 #342 #363 #365 #366 closed with link. C-0062 minted (review_checks timeout test flaky under load, harness); next free C-0063. Next: G3b #551 once its rerun is green.
- 2026-10-07T16:12Z G3b wallclock: single outlier (11.3s vs 7.5-9.4s across 18 runs); same commit 987f63ad passed on dispatch run 37649002217 and G5 (contains G3b) passed; earlier 'twice' was a never-acquired job. Re-ran failed jobs on #551's run once (passed on this exact commit). C-0061 minted (SECONDS granularity); next free C-0062.
- 2026-10-07T16:09Z MERGED #550 (G2) into release at bb5b47d5, crew 1.1.10 (CI fully green). Opened WAVE 2 #556 (release -> main), subscribed.
- 2026-10-07T15:59Z G6a fixed: head 5cc2d616 (1.1.15 placeholder). L-0666 closed sites -> decision look on 'cannot tell' (crew_autopilot_gates.closed); L-0551 unknown when main checkout/INDEX unreadable; owner FIXED_INSTEAD line added (exempted only on accept-review). Sabotage red for each; pylint 0; 2523 targeted passed; Windows 16/16 (runner-acquisition rerun). All builds done.
- 2026-10-07T15:58Z G3b #551 crew-windows-wallclock red twice (old+new head): test_context_watch_python_resolver crew_py_strict 11.3s > 8s deadline; G2 wallclock passes, no .sh diff G2..G3b. Investigator started (root-cause, no bound loosening), then re-stack G5/G1b.
- 2026-10-07T15:38Z Re-stack done: G2 7b84845c (1.1.10, + _dead_pid fix), G3b 987f63ad (1.1.11), G5 7c5c73d6 (1.1.12), G1b bdc957d2 (1.1.13, gizmoduck 0.5.11 for drift window). Full crew on G1b 16333/0. #551/#552 retitled; opened #555 (G1b), subscribed.
- 2026-10-07T15:36Z h5 ready: rush/h5-ghdeploy-state ac645dcf (C-0060 one line, Codex r2 CLEAN, harness suites green; based on ad36bec5 -> merge main + re-set version at landing). G4 ready except bookkeeping test: 8d7f9374 (verify rule split under 60s budget: 50s + 16s). Order: waves 2-5 (G2,G3b,G5,G1b) -> h5 -> FF release -> G4 -> G3c -> G3d -> G6a -> G6b -> H2.
- 2026-10-07T15:20Z MERGED WAVE 1 #554 (release -> main) at c996c7f1, main crew 1.1.9 (Windows 6/6 re-run passed once per owner; MCP merge 500 twice, gh api merge OK). 18 source PRs auto-closed as merged; #376 closed with link; #516/#517 stay open until H2 (harness halves). Next: G2 #550 (with pid-reuse test fix) -> release -> wave 2.
- 2026-10-07T14:58Z Wave 1 #554 Windows 6/6 red: G0 test _dead_pid races Windows pid reuse (code correct). Owner: re-run once (done) + robust test fix rides in G2. G4 at 411b4f07 (1.1.14 placeholder): only red = T-0068 test_every_crew_state_path_is_classified (.crew/.ghdeploy unclassified; fix is 1 line in HARNESS crew_ticket.py). Plan: after wave 5 (release==main) harness PR rush/h5-ghdeploy-state (C-0060) -> main 1.1.14, FF release, G4 1.1.15, then G3c 1.1.16, G3d 1.1.17, G6a 1.1.18, G6b 1.1.19. 12 waves total. Next free C-0061.
- 2026-10-07T14:36Z G6a r6 review: L-0550 + L-0670 CLEAN; L-0666 BLOCK (crew_autopilot.py:1027/1048 unknown successor -> closed); L-0551 BLOCK (_main_checkout why discarded / unreadable main INDEX -> 'nothing on you'). G6a fixer started incl. owner's 'fixed them instead?' line. C-0059 minted (cp1252 stdout); next free C-0060.
- 2026-10-07T14:34Z G6a done: head 6999aa44 (1.1.15 placeholder), 9 tickets, full crew 15450 passed, Windows green (2 reruns: G0 test_push_argv_never_forces, gizmoduck timeout - both pass on base). 4 capped r6 fixes -> coordinator review agent. Owner: keep L-0666 accept/reject FINDINGS stop + add 'fixed them instead? run the refresh check, then /crew:review' line; keep waiting line default-on (C-0056). Minted C-0056..C-0058; next free C-0059. ALL 14 GROUPS BUILT.
- 2026-10-07T14:26Z G2 re-stacked: 4df57590 crew 1.1.10 on release 6940da35; #550 retitled. Wave 1 #554 CI: 17 ok, 11 running.
- 2026-10-07T14:22Z Correction: old train lander IS re-stacking (G2 merge of release in progress since 14:21). Fresh lander stopped untouched (no double-work). Old lander continues G2 1.1.10 -> G3b -> G5 -> G1b.
- 2026-10-07T14:21Z G4 lander resumed: re-merge release 6940da35 (has retire), placeholder 1.1.14, anchor test must pass, full suite + Windows.
- 2026-10-07T14:21Z Old train lander stopped without re-stacking; fresh train lander started (G2 1.1.10 -> G3b 1.1.11 -> G5 1.1.12 -> G1b 1.1.13 on release 6940da35).
- 2026-10-07T14:20Z MERGED #553 (sync main->release) at 6940da35, crew 1.1.9. Opened WAVE 1 #554 (release -> main: G8, G1, G3, G0, G7 + sync), subscribed. Train lander re-stacking G2 1.1.10 / G3b 1.1.11 / G5 1.1.12 / G1b 1.1.13 on the new release.
- 2026-10-07T14:20Z G6b fixes done: head ebee2f34 (1.1.16 last); all 6 coordinator findings real and fixed with sabotage-verified tests (case test exercises listdir on Linux; check_dir realpath guard before/after makedirs incl. Windows junction test passing in CI; held/summary files guarded; asleep=? for unknown; summary sending/sent states, death mid-send reported not silent). Full pylint 10.00, 4867 targeted passed, Windows 16/16.
- 2026-10-07T13:53Z Sync done: head 776393e4 (crew 1.1.9; merges main 7cb44221 + ad36bec5), full crew 14936 passed, harness suites green, Windows 16/16. Opened #553 (sync -> release), subscribed. Next: merge #553, then wave 1 release -> main.
- 2026-10-07T13:45Z Coordinator review of G6b r6 fixes: L-0541 + T-0056 CLEAN; L-0658 test FIX (case check not exercised on Linux); L-0653 2 FIX + minor (makedirs before link check; Windows junction bypass; held/summary files unguarded; unknown sleep logged as awake); L-0656 BLOCK fail-open (death mid-send silently drops summary). G6b fixer started.
- 2026-10-07T13:39Z G6b done: head 945b62ef (1.1.16 placeholder), 7 tickets; Windows 16/16 green; L-0656 notify half only (review half -> C-0053). 5 capped r6 fixes (b1ad9cda, 4850aa34, bda1b115, fb541d48, 85a24505) -> coordinator review agent. Classifier outage blocking Bash since ~13:20.
- 2026-10-07T13:18Z MERGED #549 (C-0047 pt1 retire, harness-only) into main at ad36bec5, crew 1.1.8 (CI all green). Sync lander told to merge main and set 1.1.9.
- 2026-10-07T13:00Z G3c done: head 64758505 (placeholder 1.1.13), L-0633 r6 CLEAN, L-0634 capped -> coordinator reviewed 0fd24f13 CLEAN; Windows 16/16. Owner accepted 5-field binding (C-0052). G3d done: head acf00f60 (1.1.14 placeholder), T-0032/L-0636/L-0637/L-0667/L-0708 built, L-0637 r6 fix e56c54a9 coordinator-reviewed CLEAN; L-0708 U1 resolved (Kimi roots at any .git -> refuse when Kimi project files exist); Windows 16/16. Minted C-0049..C-0052; next free C-0053. Sync lander told to drop stray diff3 marker in CHANGELOG:632.
- 2026-10-07T12:34Z #552 G5 pylint red: test_crew_config.py 3406/3400 (stack), gizmoduck test_bootstrap C0301/W1514, test_bootstrap_version C0207. Sent to train lander for the re-stack; full CI-identical pylint now required on every stacked head.
- 2026-10-07T12:32Z Owner: 10-12 waves, no two massive waves. Plan: wave 1 = what release already holds (G8, G1, G3, G0, G7; unsplittable without 4 extra syncs), then ONE group per wave (G2, G3b, G5, G1b, G4, G3c, G3d, G6a, G6b), then H2 = 11 waves. Rule: no second group merges into release until the previous group's wave reached main.
- 2026-10-07T12:32Z Owner: ~10 WAVES release->main (one per group). Main has 131 commits release lacks (H1/H3). New order: #549 retire -> main as 1.1.8 (re-set, head d44da6fb) -> SYNC main->release 1.1.9 -> wave 1 release->main -> G2 1.1.10, G3b 1.1.11, G5 1.1.12, G1b 1.1.13 (re-stacked on synced release), each followed by a wave; then G4, G3c, G3d, G6a, G6b each + wave; H2 1.2.0 last. #550/#551/#552 hold until re-stack.
- 2026-10-07T12:24Z Opened #552 (G5 -> release, crew 1.1.11 / gizmoduck 0.5.10 / windows-ssm 1.0.2, head a3eef820, on G3b), subscribed. G1b (1.1.12) stacking next.
- 2026-10-07T12:20Z G1b lander done: head 581efa45, merged release 2c911427 (22 conflicts, both kept), full crew 13984 passed/0 failed, Windows 16/16 green (fixed fake codex on Windows; _existing_ticket refuses 'T-1\n'). Added to train stack after G5 as crew 1.1.12. G1b + G5 both change install scripts -> re-pin README URLs after main.
- 2026-10-07T12:19Z G2 fixed (crew_state split) head 63c0e080 on #550. Opened #551 (G3b -> release, crew 1.1.9, head e924e03b, on G2), subscribed. Builders warned about the 3400-line cap.
- 2026-10-07T12:07Z #550 G2 CI red: pylint C0302 crew_state.py 3405/3400 (G0+G7+G2 combination). Train lander told to split a helper module (no disable), re-set 1.1.8 last, re-stack G3b/G5, C0302 check on every stacked head.
- 2026-10-07T12:01Z Opened #550 (G2 -> release, crew 1.1.8, head 8b04d666, stacked on G7), subscribed.
- 2026-10-07T12:00Z G5 follow-up done: head c7665506; r4 BLOCK fixed (bootstrap --user runs --version, broken tool = failure, sabotage red); Windows skip REMOVED (test runs everywhere via bash kill); hard-kill leftover documented as Windows limitation; all 16 CI green; md5 stable. G5 added to train stack after G3b as crew 1.1.11 (1.1.10 = #549). README install URLs need re-pin after G5 reaches main.
- 2026-10-07T11:48Z MERGED #548 (G7) into release/1.2.0 at 96b5595f, crew 1.1.7 (29/29 CI). #549 (retire, main, 1.1.10) CI queued. G2 restack (1.1.8 on G7) pending.
- 2026-10-07T11:48Z Retire branch done (C-0047 pt1: 28 entries out, recorded; Codex r2 CLEAN). Coordinator re-set version 1.1.7 -> 1.1.10 (G7 holds 1.1.7), head cd8fe1b3; opened #549 -> main, subscribed. G4 head 60c76f54 (1.1.7 placeholder): r2 BLOCK+2 FIX fixed and sabotage-verified, full crew 14237 passed / 1 expected anchor fail. After #549: release merges main, then G4 re-merges release and takes its final version.
- 2026-10-07T11:02Z G5 lander: head 84a1139b (crew 1.1.10, gizmoduck 0.5.10, windows-ssm 1.0.2), CI green, full crew 13555 passed, gizmoduck 873. r4 BLOCK (bootstrap --user trusts command -v) unfixed -> sent back to fix (G4 precedent). Asked to justify Windows skip of test_an_interrupted_runner_leaves_no_capture_file. md5 of /usr/local/bin+/opt changed 09:15->later outside its run (investigating). Install scripts changed: re-pin README URLs after main.
- 2026-10-07T10:54Z Opened #548 (G7 -> release, crew 1.1.7, head cff852dd, contains release 55e45b60), subscribed. G2 (1.1.8) and G3b (1.1.9) restack in progress.
- 2026-10-07T10:51Z MERGED #546 (G0) into release/1.2.0 at 55e45b60, crew 1.1.6 (all CI green; start-if-stopped non-required). Train lander stacking G7 (1.1.7) -> G2 (1.1.8, on G7) -> G3b (1.1.9, on G2) for parallel CI. Retire PR (main) takes next free after. Next free: 1.1.10. Source PRs #516/#517 close when release reaches main.
- 2026-10-07T10:49Z G3b lander done: head 04da6c64 (1.1.8 provisional), contains release 2c911427, r1 BLOCK (case-insensitive config.json scan) + r2 BLOCK/2 FIX fixed with sabotage-verified tests; Windows run 37604277431 all 16 green. Queue: G0 -> retire(main) -> G7 -> G2 -> G3b.
- 2026-10-07T10:48Z G2 lander done: head f77e8d1b (1.1.12 provisional), merged release 2c911427 (14 doc/config conflicts, both kept), full crew suite 16538 passed + wallclock 29, Windows all green (fixed os.kill(pid,0)=Ctrl+C on Windows in unattended cleanup). Group review ran 4 rounds before the owner rule reached it; r4 fixes unreviewed. Landing queue: G0 -> retire(main) -> G7 -> G2. G6a/G6b told to merge f77e8d1b.
- 2026-10-07T10:47Z G7 lander done: head b4eb4ec0 (1.1.11 provisional), merged release 2c911427, full crew suite 13562 passed/0 failed, Windows all green, r1 BLOCK (.PS1 case) fixed, r2 FIX rejected with pwsh 7.6.6 measurement. G7 is next to land after G0 + retire; it re-merges release and takes its final version then. G0 0e196503: 28/28 real checks green, shell-matrix rollup queued.
- 2026-10-07T10:32Z G4: T-0009 not separable (8/10 tickets build on crew_dispatch.py). Stacked harness PR impossible: check-tooling-pr diffs vs origin/main. Owner approved RETIRE-THEN-READD: H-lane rush/h4-cloud-retire (main, harness-only, C-0047 part 1) retires the 28 orphaned sabotage_cloud.py entries, recorded in docs/tickets/C-0047/retired-entries.md; release merges main; G4 lands green; H2 re-adds anchored to new code. G4 lander does retire first, then r2 fixes on rush/g4-deploy.
- 2026-10-07T10:27Z G4 lander: head 2b8cb316 (1.1.7) red only on test_every_shipped_anchor (28 sabotage_cloud.py anchors lost by T-0009 rewrite; harness). Owner: SPLIT T-0009 out -> rebuild as rush/g4b-deploy from release with fresh commits (no revert; #336 not an ancestor); rush/g4-deploy kept as T-0009's record; T-0009 feature+re-anchor land together later. Owner: verify+fix r2 (BLOCK promote-gate.sh:381 literal match hides 2nd env; FIX ghdeploy symlink; FIX autopilot_deploy probe), no more rounds. Lander resumed.
- 2026-10-07T09:58Z G6b builder started (1.1.16; per-ticket loops for L-0659, L-0654, L-0653; build L-0656 #444; base G2 + release). Every lane now has an agent (10/10).
- 2026-10-07T09:58Z G0 fixer done: r1 BLOCK (remote HEAD via ls-remote --symref, unknown keeps lanes) + 2 FIX + r2's 1 BLOCK ({} start.json relaunch) fixed, sabotage-verified, 570 coord+wave passed, gates clean. Head 0e196503 (1.1.6 last). No r3 (owner rule). Waiting CI -> merge #546.
- 2026-10-07T09:57Z Owner rule: per-PR Codex review only; group PR needs no Codex review once a builder adds the PR (coordinator recommended a merge-only review; owner chose no group review). G0: finish r1 fixes, no further rounds. All 10 agents told. Agent cap 10; Codex runs don't count.
- 2026-10-07T09:43Z Owner: agent cap raised to 10. Builders started: G3c (1.1.13; L-0633 review, L-0634 loop), G3d (1.1.14; L-0637 loop, L-0667, then L-0708 #547), G6a (1.1.15; T-0027 confirm, then L-0550, L-0666, T-0067, L-0551, L-0687, L-0670). All merge latest G0 (+G2 for G6a) first. 10/10 agents busy. G6b waits for a slot.
- 2026-10-07T09:42Z Owner: #547 L-0708 (spec-only: kimi_probe asks git rev-parse instead of any .git) added to a later group -> G3d (not harness; no group touches kimi files). Built by the G3d builder after its 4 tickets; sabotage_kimi.py must-allow entry -> H2.
- 2026-10-07T09:13Z G0 Codex group r1 on 477aedbc: BLOCK 1 (wave cleanup trusts local origin/HEAD or guesses main -> may delete unmerged lane), FIX 2 (write_set drops deps keys outside --tickets; start.json receipts map unvalidated). Fixer started (8 agents = cap).
- 2026-10-07T09:10Z Codex logged in (device auth, 3rd code). G0 #546 whole-group Codex r1 running on 477aedbc. Landers started (6 agents + G0 review = 7): G4 (1.1.7), G3b (1.1.8), G1b (1.1.9, merge release), G5 (1.1.10), G7 (1.1.11), G2 (1.1.12); provisional, final in landing order. G3c/G3d/G6a/G6b builders wait for a free slot (and G0 landing).
- 2026-10-07T08:53Z #546 at 405f3115: only Windows 1/6 red (fixer's new [posix] lane-prompt case hard-coded a POSIX join; ntpath on the runner). Coordinator fixed test (ddd31a27), 1.1.6 re-applied last, pushed 477aedbc. 217 wave passed, check-marketplace + tooling-pr clean.
- 2026-10-07T08:37Z G0 Windows fixes pushed, head 405f3115 (1.1.6 last): coord file://C:\ drive on nt = path (prod), lane prompt script path '/' on nt (prod), 2 tests moved origins to short tmp base (128-char key rule kept), unlistable-dir test asserts UnknownKey where case-insensitive. 549 coord+wave passed; sabotage red. Coordinator read prod diff. CI re-running. Codex re-login: code expired untouched; waiting for owner 'ready'.
- 2026-10-07T08:28Z #546 G0 Windows 2/6 red: 4 G0 tests (test_crew_coord file:// drive-letter URL + 128-char key on Windows temp path; test_crew_wave lane prompt x2). Fixer agent started on rush/g0-coord-wave (revert 1.1.6, fix, re-apply 1.1.6 last). start-if-stopped red = RUNNER_START_TOKEN 404 on github-runner-infra (owner; also #544/#545), commented once + 1 re-run (same 404).
- 2026-10-07T08:16Z Owner: when #545 (L-0704, tests-only) is updated, fold it into G0 (#546): merge its head, drop its 1.1.5 bump, G0 re-sets 1.1.6 last, re-review, close #545 at landing. Watcher armed on its head (was 0d95c156).
- 2026-10-07T08:15Z New coordinator session session_01H49aKnVMcvefcadqBGmuMu resumed (container new; scratchpad reviews lost -> re-review heads). Codex re-login via device auth in progress. Opened #546 (G0 -> release, crew 1.1.6, head 4e9f4f25), subscribed. Seen: #544 L-0703 and #545 L-0704 (other session, to main) - #545 claims crew 1.1.5, which G3 already used on release.
- 2026-10-05T19:09Z G4 built (11/11 CLEAN, head a9f31d82, already on release 2c911427). Landers started: G4 (provisional 1.1.7) and G3b (provisional 1.1.8), reviewing in parallel; final version assigned in landing order. Minted C-0045..C-0048 from G4's report. pending-tickets groups table brought up to date.
- 2026-10-05T19:07Z L-0540 watcher fired falsely (empty baseline; L-0540-build is still #402's Oct 4 docs commit 0cca3aef, no seed). Re-armed with a checked baseline (bxp88jg0u). L-0688 is already on main (#405), so only the seed blocks L-0540.
- 2026-10-05T18:47Z MERGED #542 (H1) into main at 7cb44221, crew 1.1.4 (30/30 CI incl. all Windows shards; Codex CLEAN). Closed source PRs #418 #461 #422 #333 #340 #331 #343 #406 #490 (heads are ancestors of main). #402 L-0540 still waits on the owner's seed.
- 2026-10-05T18:34Z #542 H1 lander fixed the 5 Windows failures, all on the test side (UTF-8 decode in _cli, byte pipes in _classify, probe ignores the skipped-extension twin); head 28e95dab, crew 1.1.4, fix-range Codex CLEAN. Coordinator read the diff: no assertion dropped. Waiting for CI, then merge to main.
- 2026-10-05T18:30Z MERGED #543 (G3) into release/1.2.0 at 2c911427, crew 1.1.5 (30/30 CI, Codex group r6 CLEAN). G0 lander told release moved: re-merge, keep crew 1.1.6. Source PRs for G3 close when release reaches main. Next free 1.1.7.
- 2026-10-05T18:25Z #542 H1 CI red on Windows shard 2: L-0690 test_a_timed_out_probe_says_so (unpack) and T-0098 supersede by_fullwidth_auto (None.startswith). Sent to H1 lander with instruction to collect all Windows shard failures into one push.
- 2026-10-05T18:19Z Owner: L-0640 superseded-by lives in next.md, as built (open question 4 closed).
- 2026-10-05T18:19Z G3 landed on branch (5fa60b93, crew 1.1.5; group review 6 rounds -> CLEAN, all fixes fail-closed). PR #543 -> release opened. G0 lander started (crew 1.1.6; will re-merge release after #543 merges).
- 2026-10-05T18:15Z G2 cleared: slices logic is one total function checked against an exhaustive oracle (fails on old code; last Codex round asked only for more test cases). T-0059 stays in 1.2.0. G6 split and started: G6a (autopilot core, base G2+G0+release), G6b (L-0541 goals family first, then sleep; base G2+release). New logic goes in new modules (crew_autopilot.py over its line limit).
- 2026-10-05T18:13Z H1 landed on branch (c309e324, crew 1.1.4, main 97dda0bd merged; group review 5 rounds -> CLEAN; full crew suite 13959 passed). Merge-train exit renumbered 6 -> 10 (L-0528 reserves 5-7). PR #542 -> main opened; waiting for CI.
- 2026-10-05T17:48Z G0 final fix CLEAN (repo-key sweep found nothing). G0 jumps the release queue (after G3). Started G3c (#408, #410, #412) and G3d (#434, #437, #442, #455), both based on rush/g0-coord-wave + release.
- 2026-10-05T17:41Z G0 fixes done (head 3488fbe4): invalid lane ids (T-0029), port in repo key and immediate recovery on provably dead PID (T-0030, owner decisions). Reused PID with different start time stays 'presented, never adopted' per spec line 64. Capped at r6 -> coordinator review of 3488fbe4 running (incl. repo-key sweep). Harness patches refreshed: coord 103 mutations, wave 16.
- 2026-10-05T17:14Z G1b fixes done: T-0036 (a9de262b) and L-0509 (308078ba) reviews CLEAN. G1b ready to land (head 308078ba). Release landing queue: G3 (lander running) -> G3b -> G5 -> G7 -> G1b -> G2/G0 when cleared.
- 2026-10-05T17:13Z MERGED #540 (H3) into main at 97dda0bd, crew 1.1.3 (30/30 CI, Codex CLEAN). Closed source PRs #526 #529 #531 #538 and #527 (superseded). H1 lander told to merge main and set 1.1.4. #533 L-0518 stays open until G7's feature half reaches main.
- 2026-10-05T17:12Z G2 slices: coordinator review of 46409268 found 2 more fail-open paths (unshipped predecessor hides unreadable chain; recorded merge_sha overrides live PR state). 8 paths over 5 rounds -> switched to exhaustive oracle enumeration test + single total function. If it can't be made fail-closed, T-0059 deferral goes to owner.
- 2026-10-05T17:10Z G7 built (9 tickets CLEAN; head 6020263c, placeholder 1.1.11). L-0534 ships enforced PWSH-16; six language slices candidates only; stack-php and stack-node skills added (crew skill count 33). Budget fix on L-0519 found on resume. C-0041..C-0044. Release landing queue: G3 (running) -> G3b -> G5 -> G7 -> G1b/G2/G0 when their fixes clear.
- 2026-10-05T17:00Z MERGED #541 (G1) into release/1.2.0 at 3dbc033b, crew 1.1.2 (30/30 CI green; the two timing flakes passed on re-run). Lander landing G3 as crew 1.1.5.
- 2026-10-05T16:57Z H3 group review r6 CLEAN, CI green on 86de0d81. Set crew 1.1.3 (415c2644, version only; gates pass); version-only Codex check running; then merge #540 to main. H1 reassigned to 1.1.4 (must merge main after H3). Open H3 follow-up: crew-providers SKILL.md / kimi_probe docstring still say /crew:review cannot launch Kimi (feature half, T-0028 (c)).
- 2026-10-05T16:43Z #541 on 195b6290: G1 Windows hostile-name failures (test_graph_ignore nested repo, test_refresh_check .PEM name) -> lander. Not G1's: test_ps1_python_probe near-deadline (L-0609 wallclock flake), test_review_ledger concurrent-claims _queue.Empty (Windows timing); watch whether they recur on the next head.
- 2026-10-05T16:25Z Owner will publish the L-0540 seed (.work/tickets/L-0540/seed/: 22 tests, 137 sabotage entries, harness-half.patch). When it appears, build L-0540 in an H lane.
- 2026-10-05T16:25Z H1 built (T-0098 bundle, L-0605, L-0526, L-0608, T-0068, L-0681, L-0690 CLEAN; L-0540 blocked on unpublished seed). Lander landing H1 -> main as crew 1.1.3 (one global version counter). C-0038..C-0040 minted.
- 2026-10-05T16:19Z G2 coordinator reviews: T-0070 CLEAN, T-0044 CLEAN; T-0058/T-0059 slices code 3 BLOCK + 1 FIX (fail-open allowed-base decisions) -> sent to G2 builder (max 3 rounds).
- 2026-10-05T16:15Z G2 built (8 tickets; T-0049 superseded by #513; head 7ece4366, placeholder 1.1.2). Capped: T-0070, T-0044, T-0058, T-0059 -> 4 coordinator reviews running. C-0035 (per-slice ledger budget; T-0059 stops after slice 1 without it), C-0036, C-0037 minted. G6 unblocks when G2 lands.
- 2026-10-05T16:14Z #541 G1 CI red (Linux 3.12): onboard refresh path lost 'Then run step 6.'; sabotage anchor 'migrate stages with a truncating open' lost in crew_migrate.py (harness can't change in a release lane -> restore anchor in feature code). Sent to G1 lander.
- 2026-10-05T16:10Z Coordinator reviews of G1b capped fixes: T-0065 CLEAN; T-0036 BLOCK (short Authorization in Markdown table / trailing #); L-0509 BLOCK (double locate_ticket probe) + FIX (closed status described as open). Sent to G1b builder (max 3 rounds).
- 2026-10-05T16:06Z G1 landed on rush/g1-ports (97f0b43b, crew 1.1.2, group review 7 rounds -> CLEAN); PR #541 opened. G5 built (9 tickets CLEAN; gizmoduck 0.5.19, windows-ssm 1.0.1). G1b built (T-0025, L-0590 CLEAN; T-0036, T-0065, L-0509 capped -> coordinator reviews running). G0: T-0030 final fix CLEAN; T-0029 1 FIX (invalid lane id) + owner decisions (port in repo key; recover on provably dead PID) sent to G0 builder. C-0031..C-0034 minted.
- 2026-10-05T15:23Z G0 ported (T-0030 7 rounds, T-0029 6 rounds; head 80027aa1). Both capped: coordinator reviews of 2dcbf27c3 (T-0030) and 80027aa1e (T-0029) running. Harness halves at $S/harness-T-0030.patch then harness-T-0029.patch (sabotage_coord 101, sabotage_wave 15, scope_guard never-list) -> H2. Builder ran pkill -f 'codex exec' once: other groups' in-flight reviews may have died. C-0029, C-0030 minted.
- 2026-10-05T15:21Z G3b built (L-0675, T-0103 [9 rounds, CLEAN], T-0106; head 99917c8d). L-0667 (#455) blocked on T-0064 (G1) -> G3c. Landing queue: G1 (lander running) -> G3 -> G3b. C-0027, C-0028 minted. Note: sabotage.py on G3b reports 32 STILL GREEN entries outside its files (L-0525 territory, H2).
- 2026-10-05T14:47Z Owner: gpt-5.6-sol allowed as review fallback. codex-review.sh: gpt-6-sol x3 then gpt-5.6-sol x3 on capacity; the model used is printed and logged.
- 2026-10-05T14:39Z Owner accepted recommendations 1-7 (H3 may land before H1; <=8 agents; land-when-ready; 6-round cap; close source PRs at main; G6 sleep tickets slip if G2 is last; keep gpt-6-sol).
- 2026-10-05T13:36Z L-0639 r7 on 08677b9: fix confirmed correct; only BLOCK is the version bump (set at landing) -> treated as CLEAN. G3 (L-0639, L-0640) ready to land after G1; its T-0030-blocked tickets (#408, #410, #412) become a later G3c after G0.
- 2026-10-05T13:35Z G1 built (T-0071, L-0604, T-0039, T-0064, T-0038; T-0081 superseded by #513). LANDING.md procedure written; lander agent landing G1 into release as crew 1.1.2. C-0025 (G1 sabotage -> H2), C-0026 (/crew:upgrade stub).
- 2026-10-05T13:30Z #540 H3 CI red: generated rules stale (Linux check 3.12); Windows test_review_delta (.Crew case, git-failure kept receipt) and test_review_run_kimi inline prompt; shards 4/5 unknown. All sent to H3 builder with the group-review findings.
- 2026-10-05T13:29Z MERGED #539 (G8) into release/1.2.0 at c510b764, crew 1.1.1 (Codex group r2 CLEAN, 30/30 CI green). Next free 1.1.2. H3 PR #540 opened; group review BLOCK x2 + FIX (L-0527 Kimi) sent back to builder. G3 done (L-0640 CLEAN; L-0639 r7 review running). Owner: T-0033 superseded. C-0023, C-0024 minted.
- 2026-10-05T12:42Z H3 built (L-0528, L-0514, L-0518 tooling, L-0522 PR2, L-0527 all CLEAN; head ddb96134, crew 1.1.12). T-0033 held: owner question. C-0022 minted. codex-review.sh now </dev/null (a round hung on stdin). H3 waits for H1 to land first.
- 2026-10-05T12:31Z gpt-6-sol returned 'model at capacity' on G8 r2; codex-review.sh now retries up to 6x with 1-16 min backoff (all builders share it). G8 r2 re-running.
- 2026-10-05T12:29Z G8 group review r1: 1 BLOCK (verify rules 2/3 lacked --pending-bump) - verified real, fixed in 346ca361 (tests 398 passed/2 skipped, version-drift 12/12). Group review r2 running.
- 2026-10-05T12:02Z G8 done (L-0517, L-0511 PR1, L-0530 all CLEAN). Re-bumped to crew 1.1.1 (6c8d475a), opened PR #539 -> release/1.2.0, final group Codex review running. C-0021 minted (L-0530 sabotage -> H2).
- 2026-10-05T11:57Z Owner: public change sets do NOT count toward the bar -> G7 ships the 7 sets as candidates only (PWSH-16 command-resolution half admitted on this repo's own reviews); Terraform set id TF. G7 un-held.
- 2026-10-05T11:40Z G7 research done (scratchpad g7/research/, public evidence only). G7 language sets HELD pending owner: do public change sets count toward the 3-reviewed-change-sets bar? Also: TERRAFORM set name too long for loader (2-6 chars).
- 2026-10-05T11:38Z Owner decisions: diff ticket list (awaiting list); T-0030 1-of-3 is the T-0030/31/32 family; SQL+PHP ship thin, C-0020 minted; trailers Claude-Session only.
- 2026-10-05T11:22Z Owner approved: landing order H1 -> H3 -> release -> H2; L-0515 nothing to build (folded into L-0520); T-0033 question to owner only if the builder finds one.
- 2026-10-05T11:22Z Owner asked the other landing session to stay out of #324-#538.
- 2026-10-05T11:05Z Handoff notes created (this file); brief, review script, schema and note.sh copied to docs/handoff/cloud/rush-1.2.0/.
- 2026-10-05T11:00Z Owner: research the G7 files with an Opus agent. Research agent launched (public evidence only, scratchpad output); G7 builder told to wait for $S/g7/research/README.md.
- 2026-10-05T10:50Z Container restart killed all builders. Pushed every rush/* branch's committed state (~290 unpushed commits). Relaunched 12 builders with a RESUME section in the brief; new rule: push after every commit.
- 2026-10-05T10:40Z G7: all seven language sets blocked on owner-only research files; parked.
- 2026-10-05T10:30Z L-0522 PR 2 of 3 (#538, harness, never reviewed) -> H3. Landing order revised: H1 -> H3 -> release -> H2. L-0511 PR 2 deferred.
- 2026-10-05T10:20Z Owner-added tickets found as PRs #515-#537 (20 tickets; closed duplicates #520, #524, #532). G7 (standards), G8 (late tooling), H3 (review harness) created; L-0518 split G7/H3.
- 2026-10-05T10:00Z T-0029-wave (#516) and T-0030-coord (#517) pushed by owner; G0 created to port them first.
- 2026-10-05T09:50Z main moved to a555ff37 (crew 1.1.0: #512, and #513 batch 9 which landed rush PRs #478 T-0081 and #395 T-0049). release/1.2.0 fast-forwarded; all builders told to merge it.
- 2026-10-05T09:45Z Prerequisite audit: T-0030 and T-0029 missing from the remote (blocked 10 PRs); L-0541 published by owner (#515).
- 2026-10-05T09:25Z Owner: ~10 groups. Split G1 -> G1/G1b, G3 -> G3/G3b; H1 started.
- 2026-10-05T09:05Z release/1.2.0 cut from main e84a8bfe; G1-G5 launched; #514 opened (pending-tickets rush section).
- 2026-10-05T08:55Z Codex logged in via device auth; model gpt-6-sol verified.
