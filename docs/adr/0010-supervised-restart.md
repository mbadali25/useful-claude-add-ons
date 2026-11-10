# 10. A supervisor wrapper restarts a session; nothing inside the session can

**Status:** accepted, 2026-11-06 (owner-approved; spike measurements below, real `claude` behaviour open)
**Decided by:** the owner

## Context

A running Claude Code session cannot be told to restart itself from inside. No hook, no channel message and
no relayed peer message can run `/clear`, `/reload-plugins`, `/rename` or an MCP reconnect. Remote Control
refuses `/reload-plugins`. On native Windows crew has no keystroke path at all (`crew_platform.py:405`), so
the POSIX terminal-typing route (`auto-clear.sh`, ADR 8) has no Windows equivalent. The only actor that
stays alive across a session's end is its parent process, so the restart has to come from a process that
launched `claude`.

`crew_resume.py:65-68` sets `RESUME_SOURCES = ("clear", "compact")`, and startup and resume never
auto-resume (`crew_resume.py:777`). A restart therefore starts a session of source `startup` or `resume`
and needs its own handoff carrier; crew's resume line will not supply one.

The hooks documentation (https://code.claude.com/docs/en/hooks.md, re-fetched 2026-11-06, characters
0-200000 of 289837 read) says of SessionStart output: "`sessionTitle` | Sets the session title, with the same
effect as `/rename`. Applies when `source` is `"startup"`, `"resume"`, or `"fork"`". So a SessionStart hook
can name a restarted session. The last 89,837 characters of that page were not read.

## Decision

1. **A supervisor in `plugin/ai-connect/integrations/supervisor/`.** It launches `claude -n <name>` as a
   child, keeps its handle, and relaunches it. A restart resumes with `claude --resume <name>`, or starts a
   fresh session, as the trigger asks.
2. **Who may trigger.** A trigger from `User:<owner>` or from an explicitly listed peer. Anything else is
   ignored. `force` (restart while the child is busy) is owner-only.
3. **Remote Control.** The nudge card is notice-only: it tells the person a restart is needed. It does not
   restart anything.
4. **No restart-all in v1.** One session per request.
5. **Serialise restarts.** One at a time; a second request waits or is refused, never overlaps.
6. **Stop order.** On Windows, `CTRL_BREAK_EVENT` first to a child created with `CREATE_NEW_PROCESS_GROUP`,
   then a job object as the backstop. On POSIX, `SIGTERM` to the child's process group (child started with
   `start_new_session`), then `SIGKILL` after a grace period. The supervisor ignores `CTRL_C`.
7. **Leftover lock files are stale on restart.** A forced stop leaves them (measurements), so the new
   session treats a lock whose owner is gone as stale.

## Measurements

`scripts/spikes/supervisor/` (not a gate; no CI step runs it; `spike_child.py` is a Python stand-in, not a
real `claude`). The stand-in writes two-part records so a kill mid-record is visible, holds a lock file and
spawns a grandchild.

Windows 11, Python 3.14 (run 2026-11-06, `run_windows.py`, own console):

| Scenario | Exit | Time | Signal seen | Work file | Lock | Grandchild |
|---|---|---|---|---|---|---|
| `CTRL_BREAK` to new-group child, handler | 0 | 0.19 s | 21 | flushed | removed | dead |
| `CTRL_BREAK`, no handler | 0xC000013A | 0.01 s | none | half-written | remains | dead |
| `CTRL_C` to pid 0, child in a new group (handler or not) | still running after 3 s | n/a | none | n/a | remains | alive; supervisor (SIGINT ignored) survived |
| `CTRL_C` to pid 0, child in the same group (control) | 0 | 0.04 s | 2 | flushed | removed | dead |
| `TerminateJobObject` | 1 | 0.0 s | none | half-written | remains | ALIVE |
| close job handle, `KILL_ON_JOB_CLOSE` | 0 | 0.0 s | none | half-written | remains | ALIVE |

The two job-object rows are an invalid test for grandchildren: the child was assigned to the job after it had
already spawned the grandchild. NOT VERIFIED that a job created before the spawn kills grandchildren. The
exit 0 on the handle-close row is unexplained; it was recorded as the run returned it.

Linux (WSL Ubuntu-26.04, Python 3.14.4; the original results file had been deleted, so the four scenarios
were re-run on 2026-11-06 and agree with the first run's figures):

| Scenario | Exit | Time | Work file | Lock | Grandchild |
|---|---|---|---|---|---|
| `SIGTERM` to the process group, handler | 0 | 0.21 s | flushed | removed | dead |
| `SIGTERM`, no handler | -15 | 0.0 s | half-written | remains | dead |
| `SIGTERM`, slow handler (1.5 s flush), 1 s grace re-measured with a longer wait | 0 | 1.72 s | flushed | removed | dead |
| child ignores `SIGTERM`, `SIGKILL` after 1 s | -9 | 1.0 s | half-written | remains | dead |

## Limits of the evidence

- A Python stand-in, not a real `claude`. Real `claude`'s signal handling is unmeasured.
- `claude -n <name> "<prompt>"` is accepted syntactically (`claude --help`, v2.1.319). Whether a leading
  slash command in that prompt runs is could-not-tell: a throwaway `CLAUDE_CONFIG_DIR` cannot authenticate
  ("Not logged in").
- One machine per platform, one run each (the Linux set run twice).

## Consequences

- Leftover lock files are stale on restart (Decision 7); a forced stop is the only path that leaves one, and
  it also leaves a half-written file, so a restart cannot assume the last write completed.
- The supervisor ignores `CTRL_C`: sent to pid 0 it reaches every process on the console, and a child in its
  own group does not receive it, so an interactive `CTRL_C` must not take the supervisor down.
- `CTRL_BREAK` first, then the job-object backstop, on Windows. The backstop is not yet shown to reap
  grandchildren.
- A restart needs its own handoff carrier because `crew_resume.py` does not resume on `startup`/`resume`.

## Open items

1. Real `claude` behaviour on `CTRL_BREAK` and `SIGTERM` (flush, lock, exit code).
2. A job object created before the spawn: does it kill grandchildren?
3. Does a leading slash command in the `claude -n <name> "<prompt>"` launch prompt run?
4. Restart-all, and an out-of-memory lock case.
5. The unread tail of the hooks page (89,837 characters).

## Phased plan

1. This record and the spike scripts (this PR; no plugin code, no version bump).
2. Supervisor core, local only.
3. `ai-connect` trigger.
4. `/crew:restart`, with crew's full doc set (README, CONFIG, PLUGINS row, guides, code map, diagrams).
5. Remote Control nudge card.
