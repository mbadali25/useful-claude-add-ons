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

Detect once at setup, not on every run. Re-detect only when something breaks
that used to work, or when the developer changes machines.

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

**Every hook is registered once, as bash.** `hooks.json` has no `shell` field —
Claude Code does not read one, and a hook registered with `shell: powershell` is
silently inert, which reads as "the gate passed" rather than "the gate never
ran". So `bash` must be on `PATH`; Git Bash satisfies that on Windows.

Only the `PreToolUse` guards branch, and they branch on **which tool the command
came from**, not on which OS is running:

```bash
INPUT=$(cat)
crew_tool_dispatch guard.ps1 "$INPUT"   # tool_name == PowerShell -> PowerShell rules
```

That distinction matters. A `Bash` tool call is bash syntax *even on Windows*, so
judging it with PowerShell rules gets it wrong in both directions — it blocks the
correct secret-capture form and misses the wrong one.

The remaining hooks judge no command. They are reached through `bash`, so if they
run at all bash is present and can do the work; a `.ps1` beside them would be
unreachable. The twins exist for anyone wiring crew's hooks into a
PowerShell-only harness by hand, and `hooks.json` does not reference them.

If you add your own hook, follow the same shape: register it as bash, and branch
inside the script if it needs to.

## Docker

`docker` inside WSL usually means Docker Desktop with WSL integration enabled.
Check that the integration is on for *this distro*, not just installed — a
missing integration produces a confusing "cannot connect to the Docker daemon"
even though Docker is plainly running in the Windows tray.

Containers started from inside WSL are reachable at `localhost` from WSL.
Containers started from Windows-side Docker Desktop follow the host-IP rule above.

## What to tell the user during setup

Report platform, and only mention what is actionable:

- On `windows-mount`: recommend moving the clone into WSL, with the expected
  speed difference stated plainly.
- On `crlfDetected`: offer to add `.gitattributes` and renormalize now.
- On native Windows with WSL available: mention that WSL is the simpler path and
  ask which they want, rather than deciding for them.
- On WSL2 with services on the host: record `windowsHostIp` in `.env.smoke` and
  note that it changes on reboot.
