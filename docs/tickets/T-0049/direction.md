# T-0049 direction
## Ask
Reconstructed (2026-10-04); the owner's verbatim ask is not published. What the downstream tickets say it was:
- T-0060's lane reason "reads T-0049's in-flight markers and takes its staleness from T-0049's heartbeat TTL, never a timeout of its own" (`origin/T-0060-build:docs/tickets/T-0060/direction.md:9`).
- "autopilot's in-flight check (T-0049) reads another runner's marker as `stale`, which covers a dead pid and a heartbeat older than T-0049's TTL" (`origin/T-0060-build:docs/tickets/T-0060/spec.md:6`).

So: when two runners (an `/crew:autopilot` session, a workflow lane, a person's session) could drive the same ticket, crew needs a record of who is driving it right now, a way to tell that the driver died or stalled, and a stop in autopilot that refuses to double-drive.

## What investigation found (origin/main edb2b8ff, crew 1.0.321)
- **Nothing in-flight exists on main.** No `crew_inflight.py`, no `--runner`, no `in-flight` phase, no heartbeat (`git grep -n -iE 'inflight|in-flight|heartbeat' -- plugin/crew/hooks/scripts` finds only `.deploy-in-flight` and a comment). No branch on origin carries `crew_inflight.py`.
- **autopilot cannot see another driver.** `next_phase` (`plugin/crew/hooks/scripts/crew_autopilot.py:568-605`) checks the phase from disk, the active-ticket pointer of THIS worktree, `maxPhases` and no-progress. Two worktrees that both activate one ticket, or two sessions in one worktree, both get `stop=0`.
- **The nearest precedent is the merge train.** `crew_train.py` keeps shared state under `<git-common-dir>/crew/train/`, never breaks a lock by age, reports a dead-looking hold as `stale?: <evidence>`, and releases it only by `release --force --by <who> --reason <text>`, which logs an event (`plugin/crew/hooks/scripts/crew_train.py:63-67`, `:423-445`, `:703-723`).
- **T-0030's cross-machine coordinator (`crew_coord.py`, never merged) found the traps first.** Its golden review output (`plugin/crew/tests/golden/review/uca-t0030--T-0030-coord--81NGuE/out.txt`) records: a pid probe inside Claude Code's Linux sandbox (`bubblewrap --unshare-pid`) reads a LIVE process as gone (BLOCK); a heartbeat lock keyed by ticket rather than holder leaves a new holder with no heartbeat (FIX); a holder compared by session id alone lets `claude --resume` take a working claim (FIX); peer-written fields printed unsanitised (FIX).
- **autopilot.md is one line under its budget.** 109 lines against `AUTOPILOT_MAX_LINES = 110` (`plugin/crew/tests/test_lifecycle_commands.py:112-119`), and T-0060 needs a line after this ticket. T-0060's "120 of 120" (`spec.md:23`) is stale.
- **`crew_state.py` is at pylint's `max-module-lines`** (3400 lines, `.pylintrc:140`). Adding an `AUTONOMOUS_STOPS` row needs an equal condensation.
- **The tooling-PR rule classes every `sabotage*.py` as harness** (`scripts/check-tooling-pr.py:76`), and `crew_autopilot.py`, `autopilot.md`, `crew_status.py` are `SEAM` (`:86-92`). The QA analysis says T-0049 "got the same finding in both rounds" over exactly this (`origin/L-0509-build:docs/review/08-qa-rounds-analysis.md:112-115`).

## Options
1. **A marker file per ticket under `<git-common-dir>/crew/inflight/`, a detached heartbeat, a pure `holds()` reader, and an autopilot stop (recommended).** One new module, `crew_inflight.py`, owns the marker. `holds(root, ticket, ...)` answers one of six states and never writes. `crew_autopilot.py next --runner autopilot` reads it and stops. Clearing a stale marker is the owner's, with `--by` and `--reason`, logged.
2. **Reuse the merge train's state.** Rejected: the train serialises gate+land per Touch set and is armed per clone; in-flight is per ticket, always on, and must answer during implement, long before the gate.
3. **A stall timer or daemon that watches lanes.** Rejected: T-0060 forbids it ("No stall timer and no daemon", `spec.md:12`) and it is a process nobody asked to run. Staleness is computed when someone reads the marker.
4. **Lock with an OS file lock held for the run's lifetime.** Rejected: a Bash tool call ends, and its lock with it; a lock held by a detached child is the same machinery as option 1's heartbeat without the readable `since` and `runner` that T-0060 prints.

## Recommendation
Option 1.

- **States.** `free`, `mine`, `live`, `stale`, `elsewhere`, `unknown`. Anything that cannot be read, parsed, probed or trusted is `unknown`, never `free` (CLAUDE.md, Lessons).
- **TTL.** One constant, 30 minutes; heartbeat every `min(600 s, TTL/3)`. OWNER CHECK: no config key (T-0060 calls it "T-0049's constant").
- **Never cleared automatically.** A stale marker is reported with the exact `clear` command; the owner runs it. Autopilot never runs it: a new `AUTONOMOUS_STOPS` row (the only `crew_state.py` change, as L-0582 measured from this ticket's local branch: `origin/L-0582-build:docs/tickets/L-0582/spec.md:75`).
- **Autopilot.** `next --runner autopilot` stops with phase `in-flight` on `live`, `stale`, `unknown`; with `handover-elsewhere` on `elsewhere`; proceeds on `free` and `mine`. Without `--runner`, `next` behaves exactly as today.
- **Status.** `/crew:status` lists in-flight markers with their state and, for stale, the clear command (T-0060 sends `lane-unknown` with unblock `/crew:status`).

## Open questions
- None blocking the direction. The spec's Unknowns hold three that the build measures before any code (the heartbeat surviving a Bash call, the holder identity, the sandbox pid probe).
