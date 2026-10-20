<!-- Moved verbatim from plugin/crew/README.md (3. Requirements and platforms) by L-0726; the README keeps an index entry. -->

## 3. Requirements and platforms

- Claude Code, reasonably current
- `git`, and either `bash` or PowerShell
- A repository you can commit to
- Optional: the `codex` CLI on your `PATH`
- Optional: an Atlassian Cloud account for Jira
- Optional: Obsidian, or any folder of markdown files

### Platform detection

Setup runs `platform.sh` (or `platform.ps1` on native Windows) before anything
else, and records the result in `.crew/config.json`. It distinguishes native
Linux, macOS, WSL1, WSL2, Git Bash on Windows, and native Windows, and reports
which toolchains are actually present.

`hooks.json` registers **one launcher per event per shell** — `crew-hook.sh`, and
`crew-hook.ps1` with `shell: powershell` — because it cannot know which shell a
given machine has. On Windows the PowerShell launcher is the only one that runs
and the dispatcher it starts needs Git for Windows; elsewhere the bash launcher
runs. The `PreToolUse` guards branch on which **tool** the command came from
rather than on the OS, so a `Bash` call is judged by bash rules even on Windows.
See [How the Windows half works](25-command-and-agent-reference.md#how-the-windows-half-works).

**If WSL is available, run Claude Code inside it.** One shell, one code path, and
the harness matches CI. Native Windows works but doubles the surface area for no
benefit unless the application genuinely requires it.

**On native Windows, crew picks a shell route for its long-running jobs.** The
per-step tests and verify-map checks in `/crew:implement`, and graphify builds,
run through `crew_shell.py run`. It routes by `shellRoute.mode` (`auto`, `wsl`,
`powershell` or `gitbash`) and prints one `crew-shell:` line naming the route
and why. `auto` uses WSL2 when it is usable and either the repo lives inside
WSL or a measurement showed WSL faster for this repo. Otherwise it runs plain
argv directly and bash syntax in Git Bash. A bash string never goes to pwsh.
`/crew:status` shows the route on a `shell` line. Hooks do not change, and
nothing changes on Linux, macOS or inside WSL. See "Choosing the shell route on
Windows" in `skills/crew-setup/platform.md`.

### The three WSL problems worth knowing before they cost you an hour

**Repo location decides your test runtime.** A clone under `/mnt/c/...` sits on
the Windows filesystem behind a translation layer, and file operations run
roughly an order of magnitude slower. A ninety-second smoke suite can take ten
minutes purely from where the files live. Setup flags this and recommends
re-cloning to `~/code/...` — usually the largest single speed win available, at
the cost of one `git clone`. You keep your Windows editor either way via `\\wsl$\`.

**`localhost` is not the Windows host under WSL2.** The Linux VM has its own
network namespace, so SQL Server, IIS, or a Docker Desktop container bound to the
Windows side is not reachable at `localhost`. Detection reports the gateway IP;
put it in `.env.smoke` as a variable, because it changes when the host reboots.
WSL1 shares the host stack and does not have this problem.

**CRLF breaks shell scripts with a misleading error.** A `smoke.sh` checked out
with Windows line endings fails as `bad interpreter: /usr/bin/env bash^M`, which
reads like a missing interpreter. Detection reports it; setup offers
`.gitattributes` with `* text=auto eol=lf` plus `git add --renormalize .` before
anyone writes a script.

Full detail, including a bash-to-PowerShell command translation table, is in
`skills/crew-setup/platform.md`.

---

### The platform block fixes itself

`.crew/config.json`'s `platform` block describes the machine that ran
`/crew:init`, and that machine stops being the machine reading it. The config is
**not** committed — the gitignore policy is `.crew/*` ignored with a named
un-ignore list (`codemap/`, `endpoints.json`, `verify.json`), and `config.json`
is deliberately not on it — so the block goes wrong without ever leaving the
checkout it was written in: `windowsHostIp` changes when WSL2's gateway does
after a reboot, and one worktree opened from Windows and from WSL is two
machines sharing one file. (Until 2026-09-14 this paragraph said the config *was*
committed and was therefore wrong for everybody else. That was the rationale for
the hook and it was backwards about the mechanism, not about the need.)

So a `SessionStart` hook repairs it. Open the repo from Windows after the block
was written from WSL and the first thing the session says is:

```
## platform - config said linux, this is windows-bash; updated 5 field(s) in .crew/config.json
- platform.distro: 'Ubuntu' -> ''
- platform.os: 'linux' -> 'windows-bash'
- platform.windowsHostIp: '172.24.16.1' -> ''
- platform.wsl: 'yes' -> 'no'
- platform.wslVersion: '2' -> ''
```

**One rule makes this safe: it writes derived facts and nothing else.**

| | |
|---|---|
| Rewritten | `os`, `wsl`, `wslVersion`, `distro`, `shell`, `repoFilesystem`, `windowsHostIp` — every one an answer to "what machine is this", which nobody hand-edits usefully |
| Reported, not changed | a preference this OS cannot honour: an `autoClear.method` that only exists on the other platform, a clone under `/mnt/`, CRLF in a committed `.sh` |
| Never touched | everything else. `tracker`, `qa`, `roles`, `tier`, `notify`, `emergency`, the context thresholds, `verifyGate`. If a human chose it, it stays chosen |

That split is the whole design, and it is why this hook is allowed to write at
all. A choice a human made is *judgement* — whether a role earns its context is
not a fact. `platform.os` is a fact, it is wrong on the other machine,
and being asked about it once per clone would be worse than having it fixed.

It never writes when nothing changed, so it does not dirty your tree on every
session, and it preserves the file's existing line endings — rewriting a
LF config as CRLF would show up as a whole-file diff for everyone else.

**Both flavours delegate to one python module** (`hooks/scripts/crew_platform.py`)
rather than reimplementing detection twice. For a hook that writes config, two
implementations that disagree about what they write is the last thing you want —
and the `.sh`/`.ps1` pair here has drifted for a whole release before.

A read-only checkout, or no python at all, means it says what it *would* have
changed and changes nothing.

### The config heals itself

The same hook also recreates `.crew/config.json` itself, not just its
`platform` block, when the file has gone missing or stopped parsing —
a half-finished merge, a bad rebase, or an edit interrupted mid-save all
leave a repo that *looks* like a crew repo (the `.crew/` directory is right
there) but whose switchboard is gone or unreadable.

**CRITICAL GUARD: this only ever acts where `.crew/` already exists.** A
plain git repository that happens to be open when the hook runs is not
touched — `.crew/` absent means "not a crew repo," full stop, and the hook
must never create one just because a session started there.

Given a `.crew/` directory, three cases:

| `.crew/config.json` | What happens |
|---|---|
| Missing, or present but empty | Written fresh from the same template `/crew:init` uses. No backup — there is nothing to lose. |
| Present, non-empty, but does not parse as a config object | Copied aside to `config.json.broken` first (a previous `.broken` file from an earlier bad session is never overwritten — the first failure is still the best chance at recovery), then written fresh. |
| Present and parses as an object, however unusual | Untouched, byte for byte. This heals a config that **is not one** — it does not validate or judge one that already is. |

Either way the session says so, in one line:

```
## config - .crew/config.json was malformed; backed it up to .crew/config.json.broken and wrote defaults - tracker, roles, and every other choice are back to defaults; run /crew:init to re-record them
```

**Recreating the file means every human choice in it is gone** — `tracker`,
`roles`, `tier`, whichever Jira project or Obsidian vault was configured, all
of it, back to defaults. `platform-sync` cannot know what those choices were;
only `/crew:init` can put them back, which is why the message says to run it.
This trades a working-but-defaulted repo for a broken one, not a perfectly
restored one.

The default config itself has one source: `hooks/scripts/crew_config.py`'s
`default_config()`. `templates/config.template.json` (what `/crew:init`
copies down) and this heal path both call it, and a committed test asserts
the template equals its output byte-for-byte — so the two can never quietly
drift apart the way a hand-maintained template and a hand-maintained heal
path eventually would.

### Resolving the toolchain

Detection tells you what you are on. It does not tell you whether the commands
in your verification map can actually run:

```
bash ${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/scripts/resolve-tools.sh
```

With no arguments it reads `.crew/verify.json`, extracts the first word of every
command in every `run`, `always`, `default` and environment list, and reports
each as **native**, **wsl only**, or **MISSING**.

That middle case is the one that wastes a day. A bare `terraform validate` in a
rule, on a machine where terraform lives only inside WSL, fails with "command not
found" - and the gate reports that as a *failed check*, not a missing tool. You
then debug a config problem that does not exist.

Resolve once at setup and write the resolved form into the map: `terraform` if
native, `wsl.exe -e terraform` if WSL-only. Never branch at runtime; a check that
means something different depending on which shell launched it is a check nobody
can reason about.

Before you wrap anything in `wsl.exe -e`, two things bite:

- **Paths cross, slowly.** WSL sees `C:\repos\x` as `/mnt/c/repos/x`, and
  `/mnt/c` is dramatically slower. Moving the clone inside WSL removes the
  problem instead of papering over it.
- **Credentials do not cross.** A Windows `aws` is not the WSL `aws`; they read
  different `~/.aws` directories.
