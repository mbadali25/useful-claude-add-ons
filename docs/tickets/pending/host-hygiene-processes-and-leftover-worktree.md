# Host hygiene: runaway bash and secrets-guard processes, memory pressure, one leftover worktree directory

Priority: unassigned (owner to set).
Status: needs ticket (no T-/L-/C- id yet). Recorded 2026-11-17 from the owner's open-item list.

## Problem

The Windows host that runs the agents is resource-starved, which makes suites time out and agents' waiters get killed. This ticket is about the host and the process lifecycle, not a code change yet.

## Evidence

From the owner's observations (NOT measured by this ticket's author, treat as INFERRED until re-measured):
- About 240 bash processes alive.
- Four `secrets-guard.sh` processes started from `C:/repos/anew/TheSelectSource`, alive for over a day, each at roughly 11 to 13 CPU-hours.
- Memory pressure kills the agents' waiters.
- A leftover empty directory `C:\repos\worktrees\rev774-r10-sonnet`.

VERIFIED while writing this ticket: ordinary commands (`git status`, `gh`, `python3`, `ls` in the scratchpad) in this session took 60 to 120 s or timed out, consistent with a starved host. Process counts and CPU time were not measured.

Several PRs record the same symptom in their own bodies (#777: a Git Bash plus python probe takes 27 to 37 s; #775: about 6 s per Git Bash case; #774/#775 `[sh]` cases hanging to the 100 s bound), but none of them establishes the cause.

## Recommended next step

1. Measure: list `bash.exe` and `secrets-guard.sh` processes with parent, start time and CPU time. Identify why the four `secrets-guard.sh` runs never exit (a hook with no timeout, or a loop on a repo outside this one).
2. Owner decides whether to stop them (they belong to another repo's hook, `TheSelectSource`; do not kill without the owner).
3. If a hook in this repo can leave such processes, file a separate guard ticket (hook change needs a regression suite). If it is only the other repo's hook, say so.
4. Remove `C:\repos\worktrees\rev774-r10-sonnet` after confirming it is empty and not registered (`git worktree list`).

## Acceptance criteria

- A measured count of bash processes and their CPU time, with the command and date.
- The owner of each long-lived `secrets-guard.sh` is identified and its stop condition understood.
- The empty directory is removed or its use is explained.
- Whatever is found is recorded as the cause or as "could not tell"; no cause is asserted from the symptom.

## Owner questions

1. May the four `secrets-guard.sh` processes be stopped?
2. Is `secrets-guard.sh` from this marketplace or another repo's hook?
3. Is there a cap on concurrent agents to set below 20 until this is understood (the CLAUDE.md rule allows 20)?

## Out of scope

Changing any hook or guard; killing processes without the owner's yes.

## Related

CLAUDE.md "Standing rule - one new agent per task" (guards timing out, "reduce lanes rather than disable guards"); #777.
