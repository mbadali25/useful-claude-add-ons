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
import sys

WSL_MODES = ("auto", "wsl", "powershell", "gitbash")

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
    return text.replace("﻿", "").replace("\x00", "")


if __name__ == "__main__":
    sys.exit(0)
