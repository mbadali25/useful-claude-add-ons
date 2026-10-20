# 8. POSIX session typing stays; native resume does not cover it

**Status:** accepted, 2026-10-19 (re-evaluate on the trigger below)
**Decided by:** the owner's approval of the L-0727 spec (2026-10-19)

## Context

crew clears or compacts a session and starts the next turn itself: `auto-clear.sh` types into the
terminal (tmux and similar), `crew_autocycle.py` decides when, and `crew_resume.py` supplies the resume
line. On Windows the equivalent is `sendkeys` in `auto-clear.ps1` (`crew_autocycle.py` refuses it on
POSIX; `crew_platform.py` lists it for Windows). L-0727 asked whether Claude Code's native resume now
makes that typing unnecessary.

Claude Code installed on the evaluating host: 2.1.293 on 2026-10-08, 2.1.302 on 2026-10-18, 2.1.303 on
2026-10-19. The platform claim below was researched on 2026-10-08 and not re-fetched.

## Decision

1. **Native resume does not cover session typing.** No Claude Code feature clears or compacts a
   session and then starts the next turn from hook-supplied text without terminal input. `--resume` and
   `--continue` reopen a past session; they do not start a turn after a clear.
2. **POSIX session typing stays**, with `auto-clear.sh`, `crew_autocycle.py` and `crew_resume.py`
   unchanged. The owner has it on (`~/.claude/crew/config.json`: `context.autoClear.enabled: true`,
   `method: "auto"`, `resume.auto: true`; read 2026-10-08 and 2026-10-18).
3. **Windows `sendkeys` goes**, and `auto-clear.ps1` with it, in L-0727 slice 3 (owner decision D3).
   Nothing in slice 1 changes it. Neither owner config layer sets `sendkeys`.

## Rejected option

Drop the whole session-typing resume now. It would remove `auto-clear.sh`, `crew_autocycle.py` and
`crew_resume.py`, but the unattended clear-and-continue loop they run has no native replacement.

## Trigger to re-evaluate

A Claude Code feature that clears or compacts and starts the next turn from hook-supplied text without
terminal input. Re-check then whether `auto-clear.sh`, `crew_autocycle.py` and `crew_resume.py` can
go.

## Consequences

No code changes in slice 1.
