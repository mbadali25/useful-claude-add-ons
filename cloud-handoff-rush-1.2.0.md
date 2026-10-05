# Cloud handoff: feature rush 1.2.0

Live log of the cloud session `crew-rush-2` (session_01QLY3kk7DCXpucXGu3wSniW) working PRs #324-#538
into crew **1.2.0**. Lives on branch `claude/eloquent-wozniak-iqb4hf` (draft PR #514 into
`release/1.2.0`, docs-only, merges last). Every coordinator action appends a line to the Log via
`docs/handoff/cloud/rush-1.2.0/note.sh "<what happened>"`, which commits and pushes. Ticket status
and the group table are in `pending-tickets.md`, section "Feature rush 1.2.0".

Last updated: 2026-10-05T16:19Z

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

- **Merge rule:** a group PR merges only when a Codex review (`gpt-6-sol`, high) of its current head
  has **0 BLOCK and 0 FIX**, and CI is green on that head. Merge commits only.
- **Structure:** groups -> `release/1.2.0` (feature lanes) -> one PR to `main`. Harness lanes go to
  `main` alone (CLAUDE.md T-0087): **H1 -> H3 -> release/1.2.0 -> H2**. H2 is last and sets crew
  **1.2.0**.
- **Versions:** no bump when a source PR folds into a group; every merge into `release/1.2.0` or
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

## State

- `main` = `a555ff37` (crew 1.1.0). `release/1.2.0` = `a555ff37` (fast-forwarded 2026-10-05).
- Merged into release/1.2.0: #539 G8 (c510b764, crew 1.1.1). Next free crew version: **1.1.2**.
- Open group PRs: #540 H3 -> main (lands after H1). Source PRs are closed when their content reaches main.

### Groups (scope given to each builder)

| Group | Branch base | Scope, in order | Placeholder crew |
|---|---|---|---|
| G0 coord+wave | release | T-0030 (#517) then T-0029 (#516), feature halves; harness halves saved as `$S/harness-T-00{29,30}.patch` | 1.1.9 |
| G1 ports | release | #478 T-0081 (superseded by #513), #464 T-0071, #376 L-0604, #346 T-0039, #367 T-0064, #370 T-0038 | 1.1.1 |
| G1b ports | release | #345 T-0036, #349 T-0065, #359 T-0025, #341 L-0509, #324 L-0590 | 1.1.6 |
| G2 autopilot ports | release | #354 T-0012, #395 T-0049 (superseded by #513), #342 T-0070, #358 T-0022, #369 T-0044, #363 T-0060, #365 T-0058, #366 T-0059 | 1.1.2 |
| G3 contracts | release | #409 L-0639, #411 L-0640; blocked until G0 lands: #408 T-0031, #412 L-0634, #410 L-0633 | 1.1.3 |
| G3b bridge/config | release | #425 L-0675, #414 T-0103, #447 T-0106, #455 L-0667; blocked until G0: #434 T-0032, #437 L-0636, #442 L-0637 | 1.1.7 |
| G4 deploy | release | #336 T-0009 (feature half), #467 T-0062, #428 L-0644, #432 L-0645, #436 L-0646, #439 L-0647, #445 L-0648, #471 L-0664, #473 L-0665, #488 L-0689, #452 L-0649 | 1.1.4 |
| G5 platform | release | #441 T-0102, #458 L-0684, #468 L-0685, #476 T-0506, #474 T-0055, #480 L-0657, #454 T-0054, #465 T-0502, #477 T-0093 | 1.1.5 |
| G6 autopilot builds | release, after G2 lands | #485, #486, #397, #426, #443 (needs T-0029), #449, #446, #453, #483, #444, #431, #435, L-0541 (#515), #459, #463, #469 | next free |
| G7 standards | release | L-0519 (#525), L-0518 feature half (#533), then L-0532 #535, L-0535 #519, L-0536 #523, L-0538 #534, L-0533 #536, L-0534 #537, L-0537 #530 from public-source research in `$S/g7/research/` | 1.1.11 |
| G8 late | release | L-0517 (#518), L-0511 PR 1 (#528), L-0530 (#521); L-0511 PR 2 deferred until L-0522 PR 2 is on main | 1.1.10 |
| H1 harness | main | #418 T-0098 bundle (+#461, #422), #333 L-0605, #340 L-0526, #331 L-0608, #343 T-0068, #402 L-0540, #406 L-0681, #490 L-0690 | 1.1.8 |
| H3 review harness | main | L-0528 #526, L-0514 #529, T-0033 #527, L-0518 tooling half #533, L-0522 PR 2 #538, L-0527 #531 | 1.1.12 |
| H2 sabotage | main, last | #472, #413, #415, #417, #419, #423, #424, #429, #430, #438, #440, #448, #457, #460, #466, #470, #482, #484, #487, L-0525 #522, harness halves of #336, T-0029, T-0030 | **1.2.0** |
| last | | #479 T-0507 code-map refresh | |

Untouched: #391 (the other session's notes branch).

### In flight

| What | State |
|---|---|
| Builders G0, G1, G1b, G2, G3, G3b, G4, G5, G7, G8, H1, H3 | running (relaunched after the 10:45 container restart) |
| Research agent (Opus) | writing `$S/g7/research/{sql,php,powershell,dotnet,terraform,node,angular}.md` + `changesets-*.txt` + README.md (last) from public evidence only |
| Watcher | PRs numbered above #538 |

### Waiting on the owner

1. Owner's local session to send its list of tickets pushed today; coordinator diffs it against #515-#538.

Decided 2026-10-05: T-0030 "1 of 3" = the family T-0030 -> T-0031 (#408) -> T-0032 (#434), all in the
rush; SQL/PHP ship thin from public evidence with C-0020 to re-check against private repos;
commits keep `Claude-Session:` only.

## Log (newest first)

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
