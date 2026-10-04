# T-0016 auto-clear that is safe for child processes          status: spec (reconstructed)   risk: high
owner: APPROVED 2026-10-04 (Matthew Badali) every `OWNER CHECK:` below as written, with the recommended options: macOS via `ps` with `procStart` unchecked; keep `windowTitle`'s global fallback but refuse it when another live session record exists or the window's pid is <= 1; resume typing in scope; no `allowHeadless`-style key; entrypoint allowlist `{"cli"}` plus a tty.
blocks: T-0017 (#356, branch T-0017-build)
## Intent
Auto-clear (and T-0013's resume typing, which uses the same resolver) types only into a terminal that is **provably this session's own**:
- The session is bound to its **owner process**: the nearest ancestor of the hook named by a live Claude Code session record (`${CLAUDE_CONFIG_DIR:-~/.claude}/sessions/<pid>.json`) whose `sessionId` equals the payload's `session_id` and whose `procStart` equals that process's start time wherever the start time can be read.
- The owner is classified `terminal`, `headless` or `unknown`. Only `terminal` may be typed into.
- A **headless** session (a `claude -p` child, an SDK run, no controlling tty) never types. It gets a headless notify: the handoff is written and verified, nothing was cleared, and the process that started this session must restart it, with the handoff path and its `resume:` line named.
- **Unknown** never types and is never reported as headless. An explicit typing method refuses with the reason; `auto` falls back to today's plain notify.
- For a `terminal` owner, the tmux pane or window is found by walking up **from the owner**, and the walk refuses when it passes through another Claude process, is truncated, or reaches a pane/window that also hosts another terminal.

Default behaviour on an unarmed machine (`context.autoClear.enabled` not true) is byte-identical to today's: silent.

## Downstream contract
| # | Expectation (verbatim) | Source | Met by |
|---|---|---|---|
| 1 | "auto-clear that is safe for child processes" | `origin/T-0017-build:docs/tickets/T-0017/direction.md:13` | Intent; acceptance 2-6 |
| 2 | "T-0016 decides whether there is a terminal to clear." | `origin/T-0017-build:docs/tickets/T-0017/direction.md:51` | `session_owner` + `classify` (plan step 2) |
| 3 | "A headless child still commits and writes its handoff, and T-0016's notify names the parent restart." | same, `:51` | headless notify (acceptance 3); the handoff checks stay before the binding, so a headless child's handoff is still verified |
| 4 | "T-0016 merged: the session-record binding and its test fixtures." | `origin/T-0017-build:docs/tickets/T-0017/plan.md:7` | `crew_fixtures.bind_session` / `write_session_record` / process stub (plan step 1) |
| 5 | "Order holds in both flavours: handoff checks -> wrap-up check -> method -> (T-0016 binding) -> claim -> inhibit -> send." | `origin/T-0017-build:docs/tickets/T-0017/plan.md:116` | acceptance 8 |
| 6 | "the chain end to end: T-0017 wrap-up -> T-0016 target proof -> clear -> T-0006 decide -> T-0013 typing." | `origin/T-0017-build:docs/tickets/T-0017/plan.md:175` | docs (plan step 6) |
| 7 | "No change to target identification (T-0016)." | `origin/T-0017-build:docs/tickets/T-0017/spec.md:23` | this ticket owns target identification; T-0017 only reads `plan`'s output |
| 8 | "T-0016 merged is also a precondition, because this ticket's tests build on its session-record fixture." | `origin/T-0017-build:docs/tickets/T-0017/spec.md:62` | row 4 |
| 9 | "`test_autoclear_binding.py` (T-0016)" must pass unchanged under T-0017 | `origin/T-0017-build:docs/tickets/T-0017/spec.md:125` | the suite's file name is fixed here |

No downstream ticket conflicts with another. One tension: T-0017's step 3 (`plan.md:108`) anchors on `auto-clear.sh:115-118` and `auto-clear.ps1:495-504, :513, :543`; T-0013 has since moved them, and this ticket moves them again. T-0017 re-greps at implement time; nothing here depends on its line numbers.

## Exclusions
- No change to the handoff checks (`verify_handoff`, `crew_autocycle.py:324-357`), the wrap-up marker, `context.autoWrapUp`, or anything T-0017 adds.
- No change to T-0006's `decide`, `parse_resume` or `record_run`, or to T-0013's ready probe and per-handoff marker. Only the method/target resolution T-0013 calls changes.
- No new consent key. `enabled`, `onlyRepos`, `onlySessions` and `method` keep their meaning. OWNER CHECK: no `context.autoClear.allowHeadless`-style escape hatch is added.
- No environment variable is evidence of ownership (`CLAUDE_PID`, `CLAUDE_CODE_ENTRYPOINT`, `CLAUDE_CODE_CHILD_SESSION` are inherited). The test stubs below are the only env inputs, the same standing as `CREW_AUTOCLEAR_WINDOW_STUB` (`crew_autocycle.py:77`).
- No hook registration change. `CREW_AUTOCLEAR_INHIBIT` and the claim-last sent marker (`plugin/crew/hooks/scripts/auto-clear.sh:283-285`) are untouched.
- No test reads the developer's real `~/.claude/sessions`, enumerates a real window, or sends a keystroke.

## Evidence (origin/main edb2b8ff unless marked)
- **Hook-anchored checks.** tmux `crew_autocycle.py:499-512` (`pane_pid not in ancestors()` at `:508`); xdotool `:514-524` (`resolve_target(ancestors(), ...)` at `:520`); `resolve_target` `:414-446` (title fallback over all windows at `:440-446`); `ancestors` `:374-380` (`_ANCESTOR_LIMIT = 16` at `:89`; `_ppid` returns 0 on failure `:360-371`). ps1: method switch `auto-clear.ps1:552-559`, ancestor walk `:660-665`, window pick `:671-690`.
- **The sequence a binding must slot into.** `plan` `crew_autocycle.py:532-567`: enabled -> `in_scope` -> warnings -> `verify_handoff` (`:553`) -> `resolve_method` (`:557`) -> notify zeroes delay (`:561`). sh sender: plan read `auto-clear.sh:224-239`, sent-marker claim `:283-285`, notify `:292-297`, inhibit `:304-307`. ps1: handoff checks `auto-clear.ps1:507-544`, notify claim `:595-600`, sendkeys claim `:842`.
- **Resume typing shares the resolver.** `resume_plan` `crew_autocycle.py:598-657` calls `resolve_method` at `:646`; the ps1 resume flavour resolves `sendkeys` natively (`crew_autocycle.py:643-645`, then the `auto-clear.ps1` window walk).
- **Existing process identity.** `crew_resume.session_process` `crew_resume.py:221-238` and `_proc_start` `:212-218` (field 22). CONFIG.md §14a documents it (`plugin/crew/CONFIG.md:1184-1188`).
- **Session record, measured 2026-10-04 here** (Claude Code 2.1.289, Linux, cloud container, `CLAUDE_CONFIG_DIR` unset): `~/.claude/sessions/<pid>.json` with keys `pid, sessionId, cwd, startedAt, procStart, version, peerProtocol, peerFeatures, kind, entrypoint, pidDomain, messagingSocketPath, name, nameSource, nameSince, updatedAt, status, statusUpdatedAt`. `sessionId` equals this session's payload id; `procStart` is the string `"581"`, equal to `/proc/120/stat` field 22; `kind: "interactive"` with `entrypoint: "remote_mobile"` while fd 0 is a pipe. A sibling `<pid>.<sha>.key` file also exists and is not read.
- **The local build's review findings** (golden replays on main): r1 `plugin/crew/tests/golden/review/uca-t0016--T-0016-teUWH9/out.txt:2-8`, r2 `plugin/crew/tests/golden/review/uca-t0016--T-0016-5S2mzB/out.txt:2-8`. Each becomes an acceptance check below.
- **Fixtures to extend.** `test_auto_cycle.py:_sendable` `:201-211` and `_tmux_env` `:191-198` make the test process the pane/window owner; `crew_fixtures.shim_env` `plugin/crew/tests/crew_fixtures.py:1276-1283`.
- **Tooling split.** `plugin/crew/tests/sabotage*.py` is HARNESS (`scripts/check-tooling-pr.py:58-84`), and `sabotage.py` is at `.pylintrc` max-module-lines 3400 (`.pylintrc:140`). The auto-clear verify rule already says its sabotage entries land as their own tooling PR (`.crew/verify.json:561`).

## Unknowns
- **`-p` record values.** The local build's spike reportedly measured `entrypoint: "sdk-cli"` for `claude -p` and the record appearing "74 ms at a -p startup" (r2 `out.txt:5`), but that spike lived in gitignored `.work/` and cannot be re-checked. Plan step 1 re-measures and commits it at `docs/tickets/T-0016/spike.md`. Until measured, nothing relies on `sdk-cli` as the only headless marker: the tty check and the allowlist below carry the safety.
- **The entrypoint allowlist.** OWNER CHECK: `terminal` requires `kind == "interactive"` AND `entrypoint` in a measured allowlist (initially `{"cli"}`), AND on POSIX a non-zero `tty_nr` (`/proc/<pid>/stat` field 7). A value outside the allowlist is `unknown` (logged with the value), never `terminal`. `headless` needs positive evidence: `entrypoint` starting `sdk`, a `kind` other than `interactive`, or `tty_nr == 0`. This fails closed on Windows, where `entrypoint` is unmeasured (r1 FIX `auto-clear.ps1:733`, r2 NIT `CHANGELOG.md:57`).
- **`sessionId` after `/clear`.** Whether the record's `sessionId` updates to the new id is unmeasured. It does not affect the clear (the binding is checked before the clear, against the session that asked), but it does affect T-0013's resume typing after the clear. Spike item; if it does not update, resume typing binds on pid + `procStart` only and says so.
- **No `/proc` (macOS, native Windows).** OWNER CHECK, recommended: on macOS, read parent and tty with `ps -o ppid=,tty= -p <pid>` and accept a record by pid + `sessionId` with `procStart` unchecked (stated limit: pid reuse within a record's life). On native Windows, parent via the existing `Get-CrewParentId` (`auto-clear.ps1:649-658`); no tty exists, so `terminal` rests on `kind` + allowlist alone. Any failure to read is `unknown`. Alternative: macOS stays `unknown` (no typing there at all).
- **Shared terminal servers.** One gnome-terminal-server, konsole, xfce4-terminal or VS Code pty host owns one X window for many tabs (r1 FIX `:786`). A sibling may be invisible to a session-record scan (`tmux attach`, `ssh`, another config dir, a plain shell; r2 FIX `:619`). The rule therefore uses ttys, not records: for xdotool, every descendant of the window-owning process that has a controlling tty must have the owner's tty; any other tty, or a descendant scan that fails or is truncated, refuses. On Windows, the existing Windows Terminal one-tab rule (`auto-clear.ps1:709-757`) stays the only multi-tab proof; a window owned by another live session record's ancestor chain also refuses.
- **Title fallback.** OWNER CHECK, recommended: keep `windowTitle`'s global fallback (`crew_autocycle.py:440-446`, ps1 `:686-694`) because a Windows console window is often owned by a non-ancestor (conhost/Windows Terminal), but refuse it whenever any other live session record exists on the machine, and refuse a window with no owning pid (`pid <= 1`) the same way (r2 BLOCK `:658`, r2 NIT `:875`). Alternative: drop the global fallback for typing methods.
- **Resume typing in scope.** OWNER CHECK, recommended yes: `resume_plan` gets the same binding, so a headless child's SessionStart never types into its parent's pane. It is the same resolver and one call site.
- **Headless notify wording.** OWNER CHECK: "crew: this session has no terminal of its own (<evidence>), so nothing was cleared or typed. Its handoff is written and verified at <handoffPath>; resume: <line>. The process that started this session must start a new one to continue." It names the restart, not `crew_resume.py` (a fresh process is a different author, so `decide` after `clear` would wait). Printed as a `systemMessage` and logged to `.crew/.autoclear.log` (a `-p` parent may not see the systemMessage; the log is the durable copy). Claims the sent marker like `notify`, so it fires once per session.
- **Python on Windows.** The binding is native PowerShell in `auto-clear.ps1` (parity, no python), as every other ps1 decision is (`crew_autocycle.py:1-4`). Both flavours run the same fixtures.

## Touch
- `plugin/crew/hooks/scripts/crew_autocycle.py`
- `plugin/crew/hooks/scripts/auto-clear.sh`
- `plugin/crew/hooks/scripts/auto-clear.ps1`
- `plugin/crew/tests/crew_fixtures.py`
- `plugin/crew/tests/test_autoclear_binding.py` (new)
- `plugin/crew/tests/test_auto_cycle.py` (`_sendable`/`_tmux_env` bind the fixture session; no assertion changes)
- `plugin/crew/tests/test_auto_clear.py`, `plugin/crew/tests/test_auto_clear_review_fixes.py`, `plugin/crew/tests/test_resume_typing.py` (only if their must-fire cases need the binding fixture; no assertion changes)
- `plugin/crew/tests/sabotage_autoclear_binding.py` (new), `plugin/crew/tests/sabotage.py` (registration) — separate tooling PR
- `docs/tickets/T-0016/spike.md` (new)
- `.crew/verify.json`
- `plugin/crew/CONFIG.md`, `plugin/crew/README.md`, `plugin/crew/skills/crew-context/SKILL.md`, `docs/guides/crew/src/auto-cycle.md`
- `CHANGELOG.md`, `TODO.md`, `plugin/crew/BUDGETS.md` (if flagged)
- At land only: `plugin/crew/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `plugin/PLUGINS.md`

## Acceptance checks
Every case sets `CREW_AUTOCLEAR_INHIBIT`, a fixture HOME (and `CLAUDE_CONFIG_DIR` where named), the window stub and a process-table stub; sh runs through `auto-clear.sh --dry-run` unless it checks the claim; ps1 cases skip without pwsh and say so.
1. **Spike committed.** `docs/tickets/T-0016/spike.md` records, with Claude Code version and OS: the record for an interactive tmux session, a `claude -p` child started from a parent's Bash tool, and a `script -qc claude` child (kind, entrypoint, `tty_nr`, `procStart`); `sessionId` before and after `/clear`; the record path under `CLAUDE_CONFIG_DIR`. Unmeasured platforms are listed as unmeasured (r2 FIX `TODO.md:11`).
2. **must-allow (send)**, both flavours where the method exists:
   - tmux: bound `terminal` owner, pane pid a strict ancestor of the owner, no other Claude process between -> `would send`, method tmux.
   - xdotool: window owned by a **strict ancestor** of the owner (the terminal, not claude), only the owner's tty under it -> `would send` (r1 FIX `test_autoclear_binding.py:357`).
   - sendkeys (ps1): bound `kind: interactive`, `entrypoint: cli` owner, window on a strict ancestor -> `would send`.
   - `notify` with a `terminal` or `unknown` owner -> today's notify text, byte-identical.
3. **must-block: headless child.** Owner record `entrypoint: sdk-cli` or `tty_nr == 0`, inside a parent's tmux pane (pane pid an ancestor) or under a parent's window: with `auto`, `tmux`, `xdotool` and `sendkeys`, nothing is typed; the headless notify is printed once, names the handoff path and the `resume:` line, and says the starting process must restart it; the sent marker is claimed once. A second Stop prints nothing.
4. **must-block: the walk crosses another session** (r1 BLOCK `crew_autocycle.py:786`, r1 FIX `auto-clear.ps1:733`). An interactive child under its own pty, whose parent is another live record's pid, with the parent's pane/window above it -> refuse ("passes through another Claude Code session (pid N)"), both flavours.
5. **must-block: shared window** (r1 FIX `:786`, r2 FIX `:619`). xdotool with the window on a terminal-server ancestor and, under it, a process on another tty: (a) a second live record, (b) a reparented `tmux attach` client, (c) a plain shell, (d) a descendant scan that fails -> refuse. ps1: a window owned by a process that is also on another live record's chain -> refuse.
6. **must-block: could-not-tell is never "headless" or "safe".**
   - No record under the config dir -> `unknown`: explicit tmux refuses with "could not identify this session's process", `auto` gives plain notify, and the text never says "no terminal" (r1 FIX `:519`). `CLAUDE_CONFIG_DIR` set: a record only there is found (positive control); a record only under `~/.claude` is not (refusal).
   - `sessionId` mismatch, `procStart` mismatch (pid reuse), unreadable or non-object record -> `unknown`.
   - entrypoint outside the allowlist (e.g. `remote_mobile`) -> `unknown`, value logged.
   - Ancestry truncated at 16, or `_ppid` failing mid-chain -> refuse (r2 NIT `:651`).
   - Window `pid <= 1`, or title fallback, with another live record present -> refuse; the same without another record -> unchanged (r2 BLOCK `:658` and its failing control, r2 NIT `:875`).
7. **Resume typing** (OWNER CHECK scope): `auto-clear.sh --resume --dry-run` with a headless owner in a parent's pane -> refuse, nothing typed; with a `terminal` owner in its own pane -> `would send` as today.
8. **Order** (contract row 5): in both flavours the binding runs after `verify_handoff`/the ps1 handoff checks and after the method resolves, and before the sent-marker claim. A binding refusal leaves `.crew/.autoclear-sent-<key>` absent (test).
9. **Unarmed and existing suites.** `enabled` off -> no output, no log, no record read (stub records an access). `test_auto_cycle.py`, `test_auto_clear*.py`, `test_resume_typing*.py`, `test_context_watch*.py` pass, with only the fixture binding added to their must-fire helpers.
10. **Sabotage** (tooling PR): each mutation turns its named test red, tree restored byte-identical; anchors present exactly once:
    - walk from the hook instead of the owner (`ancestors()` for `ancestors(owner)`) -> check 3;
    - drop the other-session-in-chain refusal -> check 4;
    - drop the sibling-tty refusal -> check 5;
    - `pid <= 1` guard removed -> check 6 (window pid);
    - unknown treated as `terminal` -> check 6 (allowlist);
    - no record treated as `headless` -> check 6 (wording);
    - ignore `CLAUDE_CONFIG_DIR` -> check 6;
    - walk only the owner itself (`[owner]`) -> check 2 xdotool (r1 FIX `:357`);
    - binding after the claim -> check 8.
11. **Docs and release.** CONFIG.md §14 method table and the target rules, README's method table (`plugin/crew/README.md:2014-2020`), `auto-cycle.md` method table and refusal table (`docs/guides/crew/src/auto-cycle.md:144-147`, `:166`, `:182-185`, including the missed `sendkeys` row, r1 NIT `:134`), SKILL.md, `auto-clear.sh`'s header (`:33-35`) and `crew_autocycle.py` rule 3 (`:22-25`) describe the owner binding, the three classes, the headless notify and the stated limits (Windows entrypoint, macOS). `.crew/verify.json`'s auto-clear rule lists `test_autoclear_binding.py` in paths and run. CHANGELOG entry. `python3 scripts/check-marketplace.py` passes at land with the bump.

## Risk
High. This is the only thing standing between a child session and its parent's keyboard, and a wrong "safe" types `/clear` into someone else's work. Two prior review rounds found a BLOCK each. Same-family review is a stated risk if no other reviewer is available.
