# 9. One dispatcher behind sixteen hook registrations

**Status:** accepted, 2026-10-20 (L-0727 slice 2, landed as L-0850)
**Decided by:** the owner's Phase 4 ruling of 2026-10-08 and the approval of the L-0727 spec (re-approved 2026-10-19)

## Context

crew registered every hook twice: `bash "<script>.sh"` and a `shell: "powershell"` entry for the `.ps1`
twin, 18 hooks over 8 events, 36 entries in `hooks/hooks.json`. The pair existed because
`hooks.json` cannot say which shell a machine has: the `.sh` side exits 127 when Git's `usr/bin/bash.exe`
resolves first, and a `.ps1` twin exits on its first line off Windows. On Windows both flavours ran, the
scripts were written so exactly one of them acted on an event, and 15 `.ps1` files (10,718 lines) were
kept in step with the `.sh` they mirrored. A `Bash` call matched seven registrations; a `PowerShell` call
matched seven others.

## Decision

1. **Sixteen registrations.** Per event, one `bash "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew-hook.sh"
   <Event>` and one `shell: "powershell"` entry for `crew-hook.ps1 <Event>`. CLAUDE.md's "register each
   event once per flavour" still holds: it is one launcher per flavour. The PreToolUse and PostToolUse
   matchers are the union of the rows' tool names. Each event's timeout is its largest hook's plus 10 s
   (Stop 610). `crew_instructions.claude_hooks()` renders `hooks.json` from `crew_hook.TABLE`; a test
   holds the file equal to it. `codex_hooks()` renders the same launcher with `--harness codex`.
2. **One dispatcher, `crew_hook.py <Event>`.** `TABLE` has one row per logical hook (event, matcher,
   `.sh` script, argument, timeout, whether it can block, the PowerShell twin, the Codex matcher). The
   dispatcher reads stdin as bytes (bounded at 8 MiB and the deadline), parses it only for `tool_name`,
   selects the rows (a payload that does not parse runs every row of the event), runs them concurrently
   with the raw bytes, and kills each child with its tree at the earlier of its own timeout and the
   whole-dispatch deadline. It ports no hook logic: every script is still the program that decides.
3. **The merge (spec U2).** Exit 2 from any child wins, with each blocker's stderr in registration order.
   `permissionDecision` is deny over ask over allow, the winners' reasons joined. `decision: "block"`
   and `continue: false` from any child win. `additionalContext` and `systemMessage` are concatenated in
   registration order. A child's plain stdout is folded into `additionalContext` when another child
   emitted JSON and passed through as plain text otherwise. `suppressOutput` holds only when every child
   set it. Stdout that starts with `{` and does not parse is plain text, never dropped. Where Claude Code's
   documentation says nothing about combining hook results this is the rule, and it is accepted risk: the
   platform text was last read on 2026-10-08 and not re-fetched.
4. **Fail closed in an armed repo (B8).** The launchers supervise `crew_hook.py` instead of handing the
   process over. Exit 0 and 2 pass through. Anything else (an import or syntax error before `main`, a
   signal, the deadline) is exit 2 naming the cause on PreToolUse, UserPromptSubmit and Stop, where a
   child may block, and exit 0 elsewhere and in an unarmed repo. Inside the dispatcher a guard row that
   times out, a missing script or an exception is the same. "Armed" means a repo config is found (own,
   or the main checkout's for a linked worktree), or the machine-global config exists, or either cannot be
   told; only two positive "none" answers make a repo unarmed. The launchers' own check is a superset of
   `crew_hook.armed`, and a test holds them to it.
5. **One deadline.** The launcher takes it once, as `CREW_HOOK_DEADLINE` (epoch ms): the registration
   timeout minus 5 s. It covers the python probe, the stdin read, the Git Bash resolution, the children
   and the cleanup. A watchdog kills a dispatcher that cannot run its own handling 2 s after the deadline,
   so the dispatcher's own message wins the race and the outer timeout is still 3 s away.
6. **Windows (B4, B7, B9, B10).** `crew-hook.ps1` is the single path; `crew-hook.sh` exits 0 on
   `uname -s` MINGW*/MSYS*/CYGWIN*, and on `OS=Windows_NT` only when uname names no POSIX kernel (an
   environment variable cannot stand the guards down on Linux or macOS), while `crew-hook.ps1` tells a real
   Windows host by the platform and not by `$env:OS`. The dispatcher runs `.sh` children through
   `crew_shell.resolve_gitbash(strict=True)` and never a `usr/bin/bash.exe` or a PATH `bash`. A `PowerShell`
   tool call goes to a row's PowerShell twin when the file exists (cloud-guard, env-guard, promote-gate;
   `cloud_guard.py` and `env_guard.py` stand down for exactly that call), and to the `.sh` otherwise, so no
   slice leaves PowerShell cloud or environment-dump commands unjudged. With no strict Git Bash an armed
   repo is refused on PreToolUse, UserPromptSubmit and Stop, SessionStart prints one `systemMessage`, and
   the other events exit 0. With no python on Windows an armed repo is refused on the same three events;
   an unarmed one exits 0, except a PreToolUse write by a restricted or unreadable role, which keeps
   `role-write-guard.ps1`'s config-independent fallback.
7. **No python on POSIX.** `crew-hook.sh` runs the event's `.sh` scripts itself from a static list that a
   test holds equal to `TABLE`, in parallel, any exit 2 winning and stdout concatenated. Each script's own
   no-python fallback then decides, as it did when registered alone.

## Parity evidence

`record_golden_hooks.py` recorded, from the real scripts at the base, what every `.sh` hook does for a
matrix of 107 cases in armed and unarmed repos: every event, the tool names of every matcher including
`PowerShell` and an MCP vault tool, a must-block and a must-allow payload per guard, stdin with a UTF-8 BOM,
non-ASCII, CRLF and malformed JSON, Codex payloads, and the same matrix with no python. The suites replay it
through the real launcher and hold it to an oracle that does not call the code under test. Sabotage entries
(a dropped row, a swallowed exit 2, a dropped deny, stdin minus its first bytes, a launcher that reads a crash
as an allow, a guard timeout read as an allow, an armed check that fails open, a forgotten no-python script)
each go red.

## Latency (A6)

Median of 3 warm runs on dadeush-buntu-laptop (Linux, 20 CPUs, load average 5.5), all of an event's
matching hooks started at once as Claude Code starts them, 25 interleaved runs for the figure behind them:

| Event | Before (registered scripts) | After (launcher + dispatcher) | Rise | Limit |
| --- | --- | --- | --- | --- |
| PreToolUse(`Bash`) | 117 ms | 146 ms | 29 ms | 60 ms |
| Stop (clean tree) | 124 ms | 159 ms | 35 ms | 100 ms |

The security pass (below) added a deadline to the no-python path, which does not touch these figures. Two
things made that number, and one first measurement was wrong. A `Popen.wait(timeout)` in the
dispatcher polls with sleeps that grow to 50 ms and added about 45 ms to every hook; a blocking wait in a
thread, joined with the timeout, does not. The launcher tries the first `python3` on PATH before the
`crew_py_strict` probe (about 17 ms) and falls back to the probe only on exit 1, 126 or 127, which
`crew_hook.py` never returns once it has started, so nothing runs twice. The first "before" figure fed
each hook its payload one process at a time and so serialised them; payloads now go to every process at
once. The files are `golden_hooks/latency-before.json` and `latency-after.json`.

## Security pass

The read-only pass (crew:security, 2026-10-20) found two BLOCKs, five FIXes and four NOTEs. Both BLOCKs and four
of the FIXes are fixed in this PR; the fifth is accepted below:

- `$OS` stood the bash launcher down on any host, so `OS=Windows_NT` in the hook environment switched every
  guard off on Linux (BLOCK). Now uname decides on a POSIX kernel; the PowerShell launcher uses
  `OSVersion.Platform`.
- A guard that crashed (exit 1, a signal) and left no other output came back from the merge as exit 1, which
  the launcher read as "the interpreter failed" and retried with the stdin it had already consumed, so every
  row ran on an empty payload and the fault became an allow (BLOCK). The merge now returns only 0 or 2, and a
  guard row that exits otherwise is a fault: exit 2 in an armed repo on PreToolUse, UserPromptSubmit and Stop,
  a note elsewhere.
- The no-python path had no deadline, stdin bound or size cap, and ignored a child that did not decide: it now
  reads stdin from a bounded file, runs the scripts under the watchdog, and treats an undecided guard as above.
- `CREW_HOOK_TRACE_FILE` is honoured only for a path ending `.crew-trace` and never through a symlink.
- On Windows the dispatcher no longer uses a bare `taskkill` or `powershell` name (CreateProcess searches the
  repo directory first); an unresolved PowerShell is a row error.
- An unset `HOME` now counts as armed in the bash launcher's check.

A second read of the fixes (crew:security again, 0 BLOCK, 2 FIX, 6 NOTE) closed both BLOCKs and added two more fixes:
the PowerShell launcher now wraps everything after its functions in one try/catch that exits 2 for an armed blocking
event (without it a terminating error ended the script with no exit code, and the registration's
`exit $LASTEXITCODE` said 0), and the watchdog sets its TERM trap before its sleeper starts and ends the sleeper through
the job table. Noted, not fixed: a watchdog can signal a pid its script has already reaped, only at the deadline; the
no-python path counts a non-guard script that crashes as a fault on blocking events (it over-blocks, never under-blocks);
a PATH-planted `uname` or `python3` is the same trust as before.

Accepted, not fixed: the fast path trusts the first `python3` on PATH to run `crew_hook.py` when it exits 0.
Whoever controls PATH for the hook already controls the interpreter every guard script runs under, as before.
A payload over 8 MiB (a `Write` of a very large file) is a fault and is refused when armed.

## Rejected options

- **Keep the dual registration.** It is the 36-entry, 15-twin design this replaces.
- **`exec` the dispatcher.** An import or syntax error before `main` could then only be read as the
  hook's own exit code, which Claude Code treats as non-blocking for anything but 2.
- **Port the hook scripts to Python now.** Excluded by the ticket: a later one may, once the dispatcher is
  proven.

## Consequences

B1 (36 to 16 registrations; a hook override naming a script path stops matching), B4 (Windows needs a
strictly resolved Git Bash), B7 (a `PowerShell` call on Windows reaches `scope-guard.sh`, not its twin),
B8 (fail closed), B9 (the scripts no longer run twice on Windows), B10 (no python on Windows). Slices 3 and 4
delete the fourteen twins this PR leaves in place, and slice 3 updates the commands, skills and
`INSTALLATION.md` text that still describes them.

**Outcome (slice 3, L-0867, crew 1.2.60):** the ten non-harness twins (`cloud-guard`, `env-guard`,
`role-write-guard`, `crew-context`, `handoff-read`, `handoff-write`, `notify`, `platform-sync`,
`context-watch`, `auto-clear`) are deleted. `crew_hook.select` uses a row's `twin` only when the file exists, so
the `cloud-guard.ps1` and `env-guard.ps1` rows in `TABLE` now route a Windows `PowerShell` call to the `.sh`
with no dispatcher edit; those two `twin=` entries are dead and are removed by a later harness PR together with
the four harness twins of slice 4. `promote-gate.ps1` stays.

Comments that still say both flavours are registered, left for that follow-up because the files are outside
this PR: `cloud-guard.sh`, `env-guard.sh`, `handoff-write.sh`, `context-watch.sh`, `verify-gate.sh`,
`cloud_guard.py`, `crew_context.py`, `hook_once.py`, `event_claim.py` and the `.ps1` twins' own headers.

## Trigger to re-evaluate

A Claude Code per-OS hook registration, or a single hook command that runs on every shell. Re-check then
whether the launcher pair can become one.
