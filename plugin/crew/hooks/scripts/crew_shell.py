"""Which shell crew's long-running jobs run in on Windows (T-0040).

    python3 crew_shell.py probe [--json] [--write] [--root .]
    python3 crew_shell.py measure [--write] [--root .]
    python3 crew_shell.py classify -- "<command>"
    python3 crew_shell.py run [--root .] -- "<command>"

Spec: `.work/tickets/T-0040/spec.md`. On native Windows, `run` resolves a route
from `shellRoute.mode` -- `auto`, `wsl`, `powershell` or `gitbash` -- prints one
`crew-shell:` route line on stderr naming the route and why, and runs the job
there. Off Windows (Linux, macOS, or inside a WSL session) nothing here probes,
prints or spawns anything extra: `run` is exactly `bash -c <command>`.

`shellRoute` is not `route`. `route` (`crew_route.py`) is plain-text lifecycle
routing of prompts to `/crew:` commands; `shellRoute` picks the shell a job
runs in.

No hook calls this module, and none may: a SessionStart hook must answer fast
on every machine, and `wsl.exe` can take seconds to start a stopped VM. Crew's
own record-writing jobs (`verify-gate.sh --all`, gate records, review ledgers)
are never routed through it either.

Standard library only. No crew module is imported at import time; `crew_config`
and `crew_state` are imported where they are used.
"""

import os
import platform
import re
import shlex
import shutil
import subprocess
import sys

MODES = ("auto", "wsl", "powershell", "gitbash")

# Any of these anywhere in a command means it is not provably plain argv. The
# classifier fails toward Git Bash: a character on this list costs a shell
# launch, a character missing from it costs a broken check.
METACHARACTERS = frozenset("|&;<>()$`*?[]{}~!#'\"\\\n")
# First words that are shell syntax, not programs.
SHELL_WORDS = frozenset(("sh", "bash", "zsh", "dash", "cd", "source", ".", "exec", "eval", "export",
                         "set", "env"))
# Replaced by `sys.executable`: on native Windows `python3` can resolve to a
# WindowsApps App Execution Alias that prints a Store prompt and exits 9009.
PYTHONS = ("python3", "python")

PWSH7 = "C:/Program Files/PowerShell/7/pwsh.exe"
GITBASH_DEFAULT = "C:/Program Files/Git/bin/bash.exe"

_DRIVE = re.compile(r"^([A-Za-z]):(?:[\\/](.*))?$")
_GITBASH_DRIVE = re.compile(r"^/([A-Za-z])(?:/(.*))?$")
_WSL_UNC = re.compile(r"^[\\/]{2}(wsl\$|wsl\.localhost)[\\/]([^\\/]+)(?:[\\/](.*))?$", re.IGNORECASE)


# --- host, paths, decoding ------------------------------------------------------

def host_os(system=None, env=None, osrelease=None):
    """`windows`, `windows-bash` (native Windows under Git Bash/MSYS), `linux`,
    `macos`, `wsl` (a Linux interpreter inside WSL) or `other`."""
    system = platform.system() if system is None else system
    env = os.environ if env is None else env
    upper = system.upper()
    if upper.startswith(("MSYS", "MINGW", "CYGWIN")):
        return "windows-bash"
    if system == "Windows":
        return "windows-bash" if env.get("MSYSTEM") else "windows"
    if system == "Darwin":
        return "macos"
    if system == "Linux":
        if osrelease is None:
            try:
                with open("/proc/sys/kernel/osrelease", encoding="utf-8") as handle:
                    osrelease = handle.read()
            except OSError:
                osrelease = ""
        return "wsl" if "microsoft" in osrelease.lower() else "linux"
    return "other"


def on_windows(host=None):
    return (host_os() if host is None else host) in ("windows", "windows-bash")


def _tail(rest):
    parts = [p for p in re.split(r"[\\/]+", rest or "") if p]
    return "/".join(parts)


def to_wsl_path(path, distro=None):
    """The path WSL sees for a Windows-side `path`, as `(path, "")`, or
    `(None, reason)`. Never a guess: a path this cannot translate is refused."""
    if not path:
        return None, "empty path"
    match = _DRIVE.match(path) or _GITBASH_DRIVE.match(path)
    if match:
        tail = _tail(match.group(2))
        return f"/mnt/{match.group(1).lower()}" + (f"/{tail}" if tail else ""), ""
    match = _WSL_UNC.match(path)
    if match:
        owner = match.group(2)
        if distro and owner.casefold() != distro.casefold():
            return None, f"path is inside WSL distro {owner}, not the routed distro {distro}"
        return "/" + _tail(match.group(3)), ""
    if path.startswith(("\\\\", "//")):
        return None, f"UNC path {path} is not on a WSL filesystem"
    if not path.startswith(("/", "\\")):
        return None, f"relative path {path} has no WSL translation"
    return None, f"{path} is not a Windows path"


def repo_location(path):
    """`windows-drive`, `wsl-fs` (a checkout inside WSL's own filesystem,
    opened through `\\\\wsl$\\` or `\\\\wsl.localhost\\`) or `unknown`."""
    if _DRIVE.match(path or "") or _GITBASH_DRIVE.match(path or ""):
        return "windows-drive"
    if _WSL_UNC.match(path or ""):
        return "wsl-fs"
    return "unknown"


def decode(data):
    """`wsl.exe` writes UTF-16LE unless `WSL_UTF8=1`. NUL bytes mean UTF-16;
    the BOM and any stray NUL are stripped, as `platform.ps1` does."""
    if not data:
        return ""
    if b"\x00" in data:
        text = data.decode("utf-16-le", errors="replace")
    else:
        text = data.decode("utf-8", errors="replace")
    return text.replace("\ufeff", "").replace("\x00", "")


def capture(argv, timeout):
    """The default runner: `(returncode, stdout bytes, stderr bytes)`. Raises
    `OSError` when the program cannot start and `subprocess.TimeoutExpired`."""
    done = subprocess.run(argv, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL, check=False)
    return done.returncode, done.stdout, done.stderr


# --- the argv classifier ---------------------------------------------------------

def _bash(reason):
    return "bash", None, reason


def classify(cmd, which=shutil.which):
    """`("plain", argv, reason)` only when the command is provably plain argv,
    else `("bash", None, reason)` naming the first offending token."""
    if not cmd or not cmd.strip():
        return _bash("empty command")
    for char in cmd:
        if char == "\n":
            return _bash("newline in command")
        if (ord(char) < 32 and char != "\t") or ord(char) == 127:
            return _bash(f"control character {char!r} in command")
    tokens = cmd.split()
    for index, token in enumerate(tokens):
        hit = next((char for char in token if char in METACHARACTERS), None)
        if hit:
            return _bash(f"token {token!r} has shell metacharacter {hit!r}")
        if token.startswith("/"):
            return _bash(f"token {token!r} is a POSIX path, valid only after MSYS converts it")
        if index == 0:
            if token in SHELL_WORDS:
                return _bash(f"{token!r} is shell syntax")
            if "=" in token:
                return _bash(f"{token!r} is an environment assignment")
            if token.endswith(".sh"):
                return _bash(f"{token!r} is a shell script")
    try:
        argv = shlex.split(cmd)
    except ValueError as exc:
        return _bash(f"shlex cannot parse it: {exc}")
    if not argv:
        return _bash("empty command")
    if argv[0] in PYTHONS:
        return "plain", [sys.executable] + argv[1:], f"plain argv; {argv[0]} -> sys.executable ({sys.executable})"
    found = which(argv[0])
    if not found:
        return _bash(f"argv[0] {argv[0]!r} does not resolve on PATH")
    return "plain", [found] + argv[1:], f"plain argv; {argv[0]} -> {found}"


# --- absolute shell resolution ---------------------------------------------------

def _pwsh51(env):
    return (env.get("SystemRoot") or "C:\\Windows") + "\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"


def resolve_pwsh(exists=os.path.isfile, env=None):
    """pwsh 7 at its absolute path, else Windows PowerShell 5.1, else None.
    Never the bare name `pwsh`: it is not on Git Bash's PATH. Runs nothing."""
    env = os.environ if env is None else env
    tried = [PWSH7, _pwsh51(env)]
    for path in tried:
        if exists(path):
            return path, f"PowerShell at {path}"
    return None, "no PowerShell found (tried " + ", ".join(tried) + ")"


def _is_launcher(path):
    """WSL's `bash.exe` launcher in System32, or a WindowsApps alias. A bare
    `bash` reaches these before Git Bash from a PATH that does not start with
    Git's directories."""
    norm = path.replace("\\", "/").lower()
    return "/windows/system32/" in norm or "/windowsapps/" in norm


def resolve_gitbash(runner=None, exists=os.path.isfile, which=shutil.which):
    """Git Bash's `bash.exe`, absolutely: three levels above `git --exec-path`
    plus `bin/bash.exe`, else the default install path, else a PATH `bash`
    that is not WSL's launcher. `(None, reason)` naming every path tried."""
    runner = runner or capture
    try:
        code, out, _ = runner(["git", "--exec-path"], 10)
        exec_path = decode(out).strip() if code == 0 else ""
    except (OSError, subprocess.SubprocessError):
        exec_path = ""
    candidates = []
    parts = [part for part in exec_path.replace("\\", "/").split("/") if part]
    if len(parts) > 3:
        candidates.append("/".join(parts[:-3]) + "/bin/bash.exe")
    candidates.append(GITBASH_DEFAULT)
    tried = []
    for path in candidates:
        tried.append(path)
        if not _is_launcher(path) and exists(path):
            return path, f"Git Bash at {path}"
    found = which("bash")
    if found:
        tried.append(found)
        if not _is_launcher(found):
            return found, f"Git Bash at {found}"
    return None, "Git Bash not found (tried " + ", ".join(tried) + ")"


if __name__ == "__main__":
    sys.exit(0)
