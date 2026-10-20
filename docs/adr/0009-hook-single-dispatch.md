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
   `uname -s` MINGW*/MSYS*/CYGWIN* or `OS=Windows_NT`. The dispatcher runs `.sh` children through
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

Median of 3 warm runs on dadeush-buntu-laptop (Linux, 20 CPUs, load average about 3.6), all of an event's
matching hooks started at once as Claude Code starts them, 25 interleaved runs for the figure behind them:

| Event | Before (registered scripts) | After (launcher + dispatcher) | Rise | Limit |
| --- | --- | --- | --- | --- |
| PreToolUse(`Bash`) | 120 ms | 144 ms | 24 ms | 60 ms |
| Stop (clean tree) | 120 ms | 147 ms | 27 ms | 100 ms |

Two things made that number, and one first measurement was wrong. A `Popen.wait(timeout)` in the
dispatcher polls with sleeps that grow to 50 ms and added about 45 ms to every hook; a blocking wait in a
thread, joined with the timeout, does not. The launcher tries the first `python3` on PATH before the
`crew_py_strict` probe (about 17 ms) and falls back to the probe only on exit 1, 126 or 127, which
`crew_hook.py` never returns once it has started, so nothing runs twice. The first "before" figure fed
each hook its payload one process at a time and so serialised them; payloads now go to every process at
once. The files are `golden_hooks/latency-before.json` and `latency-after.json`.

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

Comments that still say both flavours are registered, left for that follow-up because the files are outside
this PR: `cloud-guard.sh`, `env-guard.sh`, `handoff-write.sh`, `context-watch.sh`, `verify-gate.sh`,
`cloud_guard.py`, `crew_context.py`, `hook_once.py`, `event_claim.py` and the `.ps1` twins' own headers.

## Trigger to re-evaluate

A Claude Code per-OS hook registration, or a single hook command that runs on every shell. Re-check then
whether the launcher pair can become one.
