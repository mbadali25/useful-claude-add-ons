# T-0016 direction
## Ask
Owner (Matthew Badali, 2026-09-25), verbatim, as quoted by T-0017 (`origin/T-0017-build:docs/tickets/T-0017/direction.md:3`): "add the ability to fix auto clear and in a way to allow auto clear to work even if its child process and autowrap up (depends on auto clear)". This ticket is the first half: auto-clear that is safe for child processes. T-0017 is the auto wrap-up half and depends on it.

T-0017 states what it needs from this ticket (`direction.md:51`): "T-0016 decides whether there is a terminal to clear. A headless child still commits and writes its handoff, and T-0016's notify names the parent restart."

## What investigation found (origin/main edb2b8ff, crew 1.0.321)
- **Nothing of T-0016 is on main.** No session binding, no headless check, no `test_autoclear_binding.py`. `pending-tickets.md` (branch L-0522-build, :74) lists T-0016 as "not started anywhere". The local build reached review round 2 and was never pushed (`.crew/standards.md:39-42` cites r1 @1275d2c4 and r2 @57656e34; neither commit is on GitHub).
- **Every target check is anchored on the hook, not on the session.**
  - tmux: the pane's pid must be an ancestor of the hook (`plugin/crew/hooks/scripts/crew_autocycle.py:508`).
  - xdotool: the nearest ancestor of the hook that owns a window wins (`crew_autocycle.py:520`, `resolve_target` `:414-446`).
  - sendkeys: the same walk from `$PID` (`plugin/crew/hooks/scripts/auto-clear.ps1:660-690`).
  - So a `claude -p` started from a parent session's Bash tool inherits `$TMUX`/`$TMUX_PANE`, and the parent's pane pid is an ancestor of the child's hook. At the child's wrap-up, `auto` resolves to tmux and types `/clear` into the **parent's** pane. The same walk reaches the parent's X11 or console window.
- **T-0013's resume typing uses the same resolver** (`resume_plan` calls `resolve_method`, `crew_autocycle.py:646`), so it has the same hazard on a child's SessionStart.
- **A primitive already exists for "this session's process".** `crew_resume.session_process` (`plugin/crew/hooks/scripts/crew_resume.py:221-238`, T-0042) finds the nearest ancestor whose `/proc/<pid>/comm` is `claude`, keyed by pid and start time. It is Linux-only by design.
- **Claude Code writes a per-process session record.** Measured in this cloud session (Claude Code 2.1.289, Linux): `~/.claude/sessions/120.json` holds `pid`, `sessionId` (equal to the hook payload's `session_id`), `procStart` (`"581"`, the string form of `/proc/120/stat` field 22), `kind` (`"interactive"`), `entrypoint` (`"remote_mobile"`), `cwd`, `status`. The same process's stdin is a pipe and `CLAUDE_CONFIG_DIR` is unset. So `kind: interactive` alone does not prove a terminal: this session has none.
- **What the local build did** (read from the review findings, not from code):
  - bound the session to its owner process through that record (`session_owner`, a `bind_session` test fixture, `crew_autocycle.py:519` record lookup);
  - treated `entrypoint` starting `sdk` (measured `sdk-cli` for `-p` by its spike) and no controlling terminal as headless, and sent a notify that named `crew_resume.py`;
  - walked windows up from the owner, not the hook (`crew_autocycle.py:786`), and added `_shared_window` to refuse a window that also hosts a sibling session (`:619`, `:651-658`).
  - Reviewers found (BLOCK/FIX): the walk could pass through another live session's process into the parent's window (r1 BLOCK `:786`); one terminal server hosts many tabs, so proving the owner does not prove the window (r1 FIX `:786`, r2 FIX `:619`, siblings invisible under `tmux attach`, `ssh`, another config dir or a plain shell); the pid-0 window guard had no failing control (r2 BLOCK `:658`); the record path ignored `CLAUDE_CONFIG_DIR`, so "could not tell" read as "headless" (r1 FIX `:519`); ps1 had no tty check and relied on an unmeasured Windows `entrypoint` (r1 FIX `auto-clear.ps1:733`); no must-fire case had the window on a strict ancestor (r1 FIX `test_autoclear_binding.py:357`); the spike lived only in gitignored `.work/` (r2 FIX `TODO.md:11`).

## Options
1. **Bind to the session record, classify, then prove the target from the owner (recommended).**
   - Owner: the nearest ancestor of the hook named by a live record in `${CLAUDE_CONFIG_DIR:-~/.claude}/sessions/<pid>.json` whose `sessionId` equals the payload's `session_id` and whose `procStart` equals the process's start time where it can be read.
   - Classify: `terminal` (interactive, entrypoint on a measured allowlist, a controlling tty on POSIX), `headless` (positive evidence: `sdk*` entrypoint, non-interactive kind, or no tty), or `unknown` (anything else, including no record).
   - Headless: never type; a notify names the handoff and the parent restart. Unknown: never type; explicit methods refuse, `auto` falls back to plain notify.
   - Target, for a `terminal` owner only: walk from the owner. Refuse when the chain passes through another Claude process, is truncated, or the window/pane also hosts another terminal.
2. **Use `CLAUDE_PID` / `CLAUDE_CODE_ENTRYPOINT` from the environment.** Rejected: a variable is copied into every child, so it proves nothing about which process is this session (`crew_resume.py:225-226` makes the same call).
3. **Refuse auto-clear whenever any parent process is a Claude session.** Rejected: it makes the child safe but does not let auto-clear "work even if its child process", and it cannot tell a headless child from an interactive one.

## Recommendation
Option 1. The rule is REPO-01 (`.crew/standards.md:15-43`): ownership is proven by a fact unique to this instance (pid plus start time plus the session id the record names), never inferred from ancestry alone, and two siblings under one shared parent give a refusal.

**Boundaries.**
- T-0017 decides when to wrap up and checks the commit/handoff; it calls nothing new here and adds its check before the method (T-0017 `plan.md:116`).
- T-0006 decides whether a new session resumes; T-0013 types it. This ticket only changes which terminal T-0013 may type into (the same resolver).
- `notify`'s existing text for a human at a terminal is unchanged.

## Open questions
- OWNER CHECK: the items marked in `spec.md` (allowlist, macOS, title fallback, resume path, wording).
- Coordination: none of T-0017's files are edited here. T-0017 imports the fixture this ticket adds (`crew_fixtures.bind_session`).
