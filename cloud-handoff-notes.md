# Cloud handoff notes

Live log of the cloud session working PRs #337, #350–#375 and #378 (session
`session_014TLaGTaf3GDU1wccRotE67`). It is updated and pushed after every action, so if the session
stops, the last entry is where it stopped. Ticket status and dependencies are in `pending-tickets.md`.

Last updated: 2026-10-03 23:04 UTC

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
