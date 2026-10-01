# Platform reference

Read this when `platform.sh` reports Windows or WSL, or when a check that passes
on one machine fails on another.

## Detection

```bash
bash ${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/scripts/platform.sh
```

On native Windows without a POSIX layer, use `platform.ps1` instead. Both emit
the same JSON shape. Record the result in `.crew/config.json`:

```json
"platform": {
  "os": "linux",
  "wsl": "yes",
  "wslVersion": "2",
  "distro": "Ubuntu",
  "windowsHostIp": "172.24.16.1",
  "repoFilesystem": "native",
  "shell": "bash"
}
```

**You no longer have to remember to re-detect.** A `SessionStart` hook
(`hooks/scripts/platform-sync.{sh,ps1}`, both delegating to `crew_platform.py`)
does it on every session start and repairs the block in place. `.crew/config.json`
is machine-local - the policy is `.crew/*` ignored with a named un-ignore list of
`codemap/`, `endpoints.json` and `verify.json`, and the config is not on it - so
the block is never wrong because it travelled. It goes wrong in place: the same
checkout opened from Windows and from WSL is two machines sharing one file, and
`windowsHostIp` is wrong for the same person after a reboot, since WSL2's gateway
changes.

It writes the seven derived facts above and nothing else. A preference this OS
cannot honour - an `autoClear.method` that only exists on the other platform, a
clone under `/mnt/`, CRLF in a committed `.sh` - is reported and left alone.
Anything a human chose (`tracker`, `qa`, `roles`, `tier`, `notify`, `emergency`,
the context thresholds) is never touched.

Running `platform.sh` by hand is still useful for the `tools` inventory, which
the hook does not record: what the machine *is* changes per clone, what is
*installed* changes per machine and is worth a deliberate look.

## The four environments

| `os` | What it means | Shell for commands |
|---|---|---|
| `linux` with `wsl: no` | Native Linux or a container | bash |
| `linux` with `wsl: yes` | WSL — Linux tools, Windows host | bash |
| `macos` | Darwin | bash |
| `windows-bash` | Git Bash / MSYS on Windows | bash, with caveats |
| `windows` (from `platform.ps1`) | Native Windows, no POSIX layer | PowerShell |

## Recommendation: prefer WSL when it exists

If WSL is available, run Claude Code inside it. One code path, one shell, and the
smoke harness matches CI. The native Windows path works, but it doubles the
surface area for no benefit unless the application genuinely requires Windows
(IIS-hosted .NET Framework, Windows-only services, MSMQ).

## WSL: the three things that actually bite

### 1. Repo location decides your test runtime

A repository under `/mnt/c/...` is on the Windows filesystem, accessed through a
translation layer. File operations are roughly an order of magnitude slower than
on the WSL filesystem. A smoke suite budgeted at ninety seconds can take ten
minutes purely from where the files live.

If `repoFilesystem` reports `windows-mount`, say so during setup and recommend
moving the clone to `~/code/...` inside WSL. This is usually the single largest
speed win available, and it costs one `git clone`.

The reverse also holds: editing WSL files from Windows tools is fine over
`\\wsl$\`, so moving the repo does not cost you your Windows editor.

### 2. `localhost` is not the Windows host

Under WSL2, the Linux VM has its own network namespace. A service running on
Windows — SQL Server, IIS, a Docker Desktop container bound to the Windows host,
a dev server started from PowerShell — is **not** reachable at `localhost` from
inside WSL.

Use the gateway address that `platform.sh` reports as `windowsHostIp`, or the
`$(hostname).local` form. Put it in `.env.smoke` as a variable rather than
hardcoding it into specs — it changes when the host reboots.

Traffic the other direction (WSL service, Windows browser) usually does work on
`localhost` thanks to WSL2's port forwarding.

WSL1 shares the host network stack, so `localhost` works in both directions.
This is one of the few cases where WSL1 is simpler.

### 3. Line endings break shell scripts silently

If `git` checked out `_verify/smoke.sh` with CRLF endings, bash fails with
`bad interpreter: /usr/bin/env bash^M` — a message that looks like a missing
interpreter rather than a line-ending problem, which is why it costs people an
hour.

`platform.sh` reports `crlfDetected`. When true, fix it at the repo level:

```
# .gitattributes
* text=auto eol=lf
*.ps1 text eol=crlf
*.bat text eol=crlf
```

Then `git add --renormalize .`. Do this during setup, before anyone writes a
script, rather than after the first confusing failure.

## Writing commands that work on both

Record the resolved commands in the repo `CLAUDE.md` rather than making agents
infer them each time.

| Concern | bash | PowerShell |
|---|---|---|
| Env var | `$VAR`, `export VAR=x` | `$env:VAR`, `$env:VAR = "x"` |
| Path separator | `/` | `\` (but `/` usually works) |
| Command exists | `command -v x` | `Get-Command x` |
| Exit code | `$?` | `$LASTEXITCODE` |
| Chain on success | `a && b` | `a; if ($LASTEXITCODE -eq 0) { b }` |
| npm binaries | `npx x` | `npx.cmd x` |
| Null sink | `/dev/null` | `$null` |

Note that `&&` in PowerShell works in 7+ but not Windows PowerShell 5.1, which is
what ships with Windows. Do not assume it.

## Hooks

**Every hook is registered twice in `hooks.json`, once per flavour.** The
`shell` field (`"bash"` or `"powershell"`) is documented and Claude Code does
read it — the PowerShell side carries `shell: powershell` so it runs via
PowerShell without needing `CLAUDE_CODE_USE_POWERSHELL_TOOL`. What is *not*
configurable is the default for a bare `command` string with no `shell` field:
that goes to Git Bash on Windows (PowerShell only if Git Bash isn't installed),
so `bash` on `PATH` still matters for the `.sh` half to have a chance — Git Bash
satisfies that.

The `PreToolUse` guards additionally branch on **which tool the command came
from**, via separate `Bash` / `PowerShell` matchers, not on which OS is
running:

```json
{ "matcher": "Bash",       "hooks": [{ "type": "command", "command": "bash .../guard.sh" }] },
{ "matcher": "PowerShell", "hooks": [{ "type": "command", "shell": "powershell", "command": "& '.../guard.ps1'" }] }
```

That distinction matters. A `Bash` tool call is bash syntax *even on Windows*, so
judging it with PowerShell rules gets it wrong in both directions — it blocks the
correct secret-capture form and misses the wrong one.

The remaining hooks judge no command, so both flavours are simply wired to their
event with no branch — `hooks.json` has no way to know in advance which shell a
given machine actually has, so one flavour failing is expected, not a bug.
(`hooks/scripts/_common.sh` also ships a `crew_tool_dispatch` helper for judging
a command from inside a single bash-registered script, if you'd rather dispatch
that way for a hook you add yourself.)

If you add your own hook, follow the same shape: register both flavours (or
dispatch from one), and branch on the tool, never the OS.

## Docker

`docker` inside WSL usually means Docker Desktop with WSL integration enabled.
Check that the integration is on for *this distro*, not just installed — a
missing integration produces a confusing "cannot connect to the Docker daemon"
even though Docker is plainly running in the Windows tray.

Containers started from inside WSL are reachable at `localhost` from WSL.
Containers started from Windows-side Docker Desktop follow the host-IP rule above.

## Choosing the shell route on Windows

On native Windows, crew runs its long-running shell jobs through one wrapper:
the per-step test runs and verification-map checks in `/crew:implement`, and
the graphify build.

```
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_shell.py" run -- "<command>"
```

On Git Bash without `python3`, use `python` or `py -3` with the same arguments.

It prints one `crew-shell:` line on stderr naming the route and why, then runs
the job and returns its exit code. The route comes from `shellRoute.mode`,
settable on both config layers with `shellRoute.distro`. `shellRoute` is not
`route`: `route` routes plain-text prompts to `/crew:` commands, and
`shellRoute` picks the shell a job runs in.

| Mode | Plain argv job | Bash-syntax job |
|---|---|---|
| `auto` (default) | WSL when chosen (below), else direct exec, no shell | WSL when chosen, else Git Bash |
| `wsl` | WSL, or refuse with exit 3 | WSL, or refuse with exit 3 |
| `powershell` | pwsh, or refuse with exit 3 if none resolves | Git Bash, with the line `powershell requested; job is bash syntax -> gitbash` |
| `gitbash` | Git Bash | Git Bash |

`auto` routes to WSL only when WSL is usable and either the checkout is inside
WSL's filesystem (opened through `\\wsl$\` or `\\wsl.localhost\`), or the
checkout is on a Windows drive and `crew_shell.py measure --write` has shown
WSL faster than Git Bash on both forks and writes for that repo. `auto` never
picks pwsh. `wsl` never falls back. An unrecognised mode reads as `auto`, and
both the route line and `/crew:status` name the bad value. Every fallback is
stated on the route line.

**The probe.** `crew_shell.py probe --write` asks from the Windows side whether
WSL2 is usable. It checks for `wsl.exe`, reads `wsl.exe --list --verbose`
(UTF-16LE unless `WSL_UTF8=1`), and takes the default `*` distro unless
`shellRoute.distro` names one. It never picks a distro by list order. It then
checks WSL2 and `command -v python3; command -v git` inside that distro, under
`bash -lc`, the login shell a routed job runs in: a non-login `sh -c` misses
`$HOME/.local/bin`, where `pip --user` and `pipx` put tools. The
states are `usable`, `not-installed`, `no-distro`, `wsl1-only`, `no-python3`,
`no-git`, `broken` (the error quoted verbatim, joined onto one line) and
`unknown` (the probe itself could not run). `unknown` is never read as `not-installed`. The answer goes to
`~/.claude/crew/shell-route.json`, a machine-local cache. The probe never
installs, updates or sets a default version.

**The argv classifier.** A job runs with no shell only when the classifier can
prove it is plain argv: no shell metacharacter (`| & ; < > ( ) $` backtick
`* ? [ ] { } ~ ! #`, quotes, backslash, newline), no `sh -c`, `bash x`, `cd`,
`source` or env assignment, no token that starts with or embeds a POSIX path
(`/c/x`, `--root=/c/x`, `-I/c/x`, `a:/b`, `x,/y`; such a path is valid only
once MSYS converts it, so direct exec and Git Bash would pass different
arguments; a drive letter such as `C:/` and a URL such as `https://` are
fine), no `*.sh` first word, and an `argv[0]` that resolves. `python3` and `python` as `argv[0]` become the interpreter already
running `crew_shell.py`, because on native Windows `python3` can be a
WindowsApps alias that prints a Store prompt and exits 9009. Anything the
classifier cannot prove goes to bash. `crew_shell.py classify -- "<command>"`
prints the verdict and the reason. A bash string is never handed to pwsh, and
crew never translates a bash job into PowerShell. On the `powershell` route
each argument is single-quoted with `'` and U+2018 to U+201B doubled (pwsh
reads all five as single quotes), and a program that cannot start exits 1
with `crew-shell:` and the reason on stderr, never 0.

**The WSL preflight.** Before a job goes to WSL, `run` checks its first word
with `command -v` under `bash -lc` inside the distro and, for `python3 -m
<module>`, that the distro's python imports the module. When either is
missing, `auto` falls to the direct-or-Git-Bash split and says why, and `wsl`
refuses with exit 3.

**Absolute resolution.** A bare `bash` from a process whose PATH does not start
with Git's directories reaches `C:\Windows\System32\bash.exe`, which is WSL's
launcher, not Git Bash. So Git Bash is resolved from `git --exec-path` (three
levels up, then `bin/bash.exe`), else `C:/Program Files/Git/bin/bash.exe`, and
never a System32 or WindowsApps path. pwsh is not on Git Bash's PATH, so it is
resolved as `C:/Program Files/PowerShell/7/pwsh.exe`, else Windows PowerShell
5.1 under `%SystemRoot%`. Git Bash has no `python3` of its own: commands and
docs resolve `python3`, then `python`, then `py -3`.

**Measured, per host, never blended.** `dadeush-desktop`, 2026-09-28, the
owner's session:

| Probe | Git Bash | pwsh | WSL2 ext4 | WSL2 on `/mnt/c` |
|---|---|---|---|---|
| 50 forks | 1.70 s | 0.93 s | 0.03 s | - |
| 200 small writes | 0.13 s | 0.051 s | 0.007 s | 0.70 s |

A real job there, `pytest test_review_prompt.py` over 3 runs: direct exec
1.72-2.02 s, Git Bash 1.85-2.12 s, pwsh 2.08-2.39 s. The launcher is noise on a
real job, so `auto` uses direct exec, the cheaper one, and not pwsh.

`dadeush-legion`, 2026-09-22, from two vault sessions (a different procedure):
50 trivial forks 27.7-35.5 s in Git Bash against 0.19-0.20 s in WSL2; 20
subshell+pipe round trips 20.4 s against 0.28 s; 200 small writes 4.43 s on
`/mnt/c` against 0.062 s on WSL's ext4.

`dadeush-desktop` again, 2026-09-28, through `crew_shell.py measure` itself (T-0040's
native acceptance run; three runs each, range shown; each shell times its own loop):

| Side | 50 forks | 200 small writes |
|---|---|---|
| Git Bash, repo on `C:` | 1.61-1.72 s | 0.073-0.082 s |
| pwsh, repo on `C:` | 0.88-0.91 s | 0.057-0.059 s |
| WSL2 on `/mnt/c` | 0.027-0.030 s | 0.40-0.43 s |
| WSL2 ext4 (`mktemp -d`) | 0.028 s | 0.0055-0.0079 s |
| Git Bash, repo in WSL via `\\wsl.localhost\` | 1.34-1.36 s | 1.45-1.52 s |
| pwsh, repo in WSL via `\\wsl.localhost\` | 0.90-0.94 s | 0.36-0.38 s |
| WSL2, repo in WSL (ext4) | 0.027-0.028 s | 0.0049-0.0057 s |

Verdicts: the `C:` checkout is `gitbash-faster` (WSL loses on writes through `/mnt/c`), so
`auto` does not route it to WSL; the in-WSL clone is `wsl-faster`. `run` was exercised once per
mode on a `D:` checkout: `auto` ran pytest direct, `gitbash` and `powershell` ran it through
their shells (242 passed each), `powershell` sent `bash .../render.sh` to Git Bash with the
line `powershell requested; job is bash syntax -> gitbash`, and `wsl` routed to WSL, where the
job failed with `No module named pytest`: the preflight then checked only the first word
(`python3`), so a distro missing the job's module read as a failed check. That refuted the
spec's claim that a missing tool was resolved by design; the preflight now also checks
`-m <module>` importability and runs under `bash -lc` (see "The WSL preflight"), so that job
refuses with exit 3 under `wsl`, naming the module, and runs direct under `auto`. That is
fixture-tested; the native run was not repeated. `wsl.exe --cd` took `/mnt/d/...` with a space in it and
`/home/...` for a `\\wsl.localhost\` root. From Git Bash, pass a WSL root as
`//wsl.localhost/<distro>/...`: a leading `\\` reaches Python as a single `\`. MSYS leaves a
one-argument command string alone unless the whole string starts with `/`. `dadeush-lenovo`
and `dadeush-legion` were not measured through `crew_shell.py`.

Legion's Git Bash fork cost is 16-21x desktop's. That spread is why `auto`
consults a per-machine measurement and not a constant. It is also why a
Windows-drive repo goes to WSL only when measured: on desktop, WSL on `/mnt/c`
writes slower than Git Bash (0.70 s against 0.13 s).

**The in-WSL clone.** `measure` also times WSL's own ext4 filesystem when the
repo is on a Windows drive, and prints the in-WSL clone offer with those
numbers. crew offers it and never makes it: a move changes paths that other
tools and sessions use, so the owner decides.

**When WSL is not installed**, crew recommends it with the measured reason and
the exact command, `wsl --install -d Ubuntu` in an elevated shell, then a
reboot. `/crew:init`, `/crew:config` and `/crew:status` print that. crew never
runs it.

**Not routed:** hooks, `verify-gate.sh --all`, anything that writes crew's own
records (gate records, approval receipts, review ledgers, metrics), git
operations, and interactive or one-off commands. A WSL git reading a Windows
checkout sees different stat data and filemode, so a record written that way
would disagree with the one the native Stop hook writes. Off native Windows
nothing changes: no probe, no status line, and `run` is exactly `bash -c`.

## What to tell the user during setup

Report platform, and only mention what is actionable:

- On `windows-mount`: recommend moving the clone into WSL, with the expected
  speed difference stated plainly.
- On `crlfDetected`: offer to add `.gitattributes` and renormalize now.
- On native Windows with WSL available: mention that WSL is the simpler path and
  ask which they want, rather than deciding for them. The shell route for
  crew's own jobs is separate: see "Choosing the shell route on Windows".
- On WSL2 with services on the host: record `windowsHostIp` in `.env.smoke` and
  note that it changes on reboot.
