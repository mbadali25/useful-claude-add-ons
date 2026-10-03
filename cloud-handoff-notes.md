# Cloud handoff notes

Live log of the cloud session working PRs #337, #350–#375 and #378 (session
`session_014TLaGTaf3GDU1wccRotE67`). It is updated and pushed after every action, so if the session
stops, the last entry is where it stopped. Ticket status and dependencies are in `pending-tickets.md`.

Last updated: 2026-10-03 23:19 UTC

## Standing rules (owner, 2026-10-03)

- **Merge rule.** A PR merges only when all three hold:
  - a Sonnet 5.5 review of its current head has **0 BLOCK and 0 FIX** (NITs are fine);
  - CI is green on that head;
  - it is first in line.

  Merge commits only, never squash or rebase.
- **Merge order:** #372 → #337 → #375 → #378 → #350 → #371 → #351 → #355 → #360 → #368 → #374 (last;
  it holds these notes).
- **After each merge:**
  - Merge `main` into the next PR (version files and CHANGELOG conflict only).
  - Set a new crew version in the LAST commit; any plugin change after it fails the drift gate.
  - Wait for green CI, then merge.

  Only the front of the queue is re-merged.
- **Commits** carry only `Claude-Session:`. Never `Co-Authored-By` (owner's global CLAUDE.md).
- **Versions** are allocated in `pending-tickets.md`. Next free: **1.0.215**.

## Where things stand

### Merge train (review round 1 done; fixes in flight)

| PR | Branch | Round-1 review | Fix | Re-review | CI | Version |
|---|---|---|---|---|---|---|
| #372 | L-0562-stamp-reach | BLOCK: `--apply` changes `rule_key`, orphaning timing cache + 3 FIX | in progress | – | – | → 1.0.208 |
| #337 | ccr-c7dcab79-8iwqt8 | BLOCK: E5 unknown `live`/acceptance → PASS + 3 FIX | in progress | – | – | → 1.0.209 |
| #375 | crew-diagram-standard | BLOCK: zero nodes measured → PASS + 6 FIX | in progress | – | – | → 1.0.210 |
| #378 | T-0061-harness | 2 FIX (both resolved by #350 landing next) | n/a | running (paired with #350) | – | 1.0.181; needs main merge |
| #350 | T-0061-build | 2 FIX | done, 2d83d373 | running | pending | 1.0.207 |
| #371 | T-0100-build | **clean** | – | – | needs main merge | 1.0.202 |
| #351 | T-0066-build | 2 FIX | in progress | – | – | → 1.0.211 |
| #355 | T-0013-build | 1 FIX | in progress | – | – | → 1.0.214 |
| #360 | T-0048-build | 1 FIX | in progress | – | – | → 1.0.212 |
| #368 | T-0063-build | 2 FIX | in progress | – | – | → 1.0.213 |
| #374 | pending-tickets | 2 FIX | done, b72269d9 | due when it is next | – | – |

The round-1 findings are recorded in each PR's fix commit messages.

### Builds and ports (batch 2), each with its own worktree under /home/user/pr-<n>

| PR | Ticket | State | Version |
|---|---|---|---|
| #352 | T-0069 | building | 1.0.189 |
| #357 | T-0020 | building | 1.0.190 |
| #358 | T-0022 | building | 1.0.191 |
| #359 | T-0025 | building | 1.0.192 |
| #353 | T-0011 | porting onto main | 1.0.196 |
| #362 | T-0051 | not started (port) | 1.0.197 |
| #367 | T-0064 | not started (port) | 1.0.198 |

Batch 3, not started: #361 T-0050 (1.0.193), #369 T-0044 (1.0.194), #370 T-0038 (1.0.195, after
#337 merges).

## How to resume (a new session)

1. Read this file and `pending-tickets.md`.
2. For each PR in the merge-train table, check its branch head against the table:
   `git log -1 origin/<branch>`. A newer head means a fix landed after this file was written.
3. Any PR whose fix is "done" but whose re-review is "–" needs a fresh Sonnet 5.5 review of its
   current head before it can merge.
4. Batch-2 branches: an unchanged head (still docs-only) means the build did not finish; restart it
   from the ticket's `docs/tickets/<T>/` files.

## Log (newest first)

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
