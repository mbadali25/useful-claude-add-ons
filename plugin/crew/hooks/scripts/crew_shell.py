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

import json
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


# --- the probe and its machine-local cache ---------------------------------------

LIST_TIMEOUT = 15
TOOLS_TIMEOUT = 30  # covers a cold start of a `Stopped` VM
TOOLS_CHECK = "command -v python3; command -v git"
locate = shutil.which  # module-level so a test can replace it

# What the not-installed recommendation cites. Two hosts, two dates, two
# procedures: reported side by side and never blended (spec, Evidence).
MEASURED = (
    "dadeush-desktop, 2026-09-28: 50 forks Git Bash 1.70 s, pwsh 0.93 s, WSL2 0.03 s; "
    "200 small writes Git Bash 0.13 s, pwsh 0.051 s, WSL2 ext4 0.007 s, WSL2 on /mnt/c 0.70 s. "
    "dadeush-legion, 2026-09-22: 50 forks Git Bash 27.7-35.5 s, WSL2 0.19-0.20 s; "
    "200 small writes /mnt/c 4.43 s, WSL2 ext4 0.062 s."
)


def _now():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _result(state, detail, **extra):
    import socket
    out = {"state": state, "distro": None, "version": None, "python3": None, "git": None,
           "detail": detail, "probedAt": _now(), "host": socket.gethostname()}
    out.update(extra)
    return out


def _parse_listing(text):
    """`[(name, version, is_default)]` from `wsl.exe --list --verbose`. A row
    whose last column is not a number (the header, in any locale) is skipped."""
    rows = []
    for line in text.splitlines():
        stripped = line.strip()
        default = stripped.startswith("*")
        parts = stripped.lstrip("*").split()
        if len(parts) >= 3 and parts[-1].isdigit():
            rows.append((parts[0], parts[-1], default))
    return rows


def _call(runner, argv, timeout):
    """`(code, out, err, None)` or `(None, None, None, (state, detail))`. A
    timeout is `broken`; a runner that could not run at all is `unknown`,
    never `not-installed` -- an unknown must not collapse into an answer."""
    shown = " ".join(argv[:3])
    try:
        code, out, err = runner(argv, timeout)
    except subprocess.TimeoutExpired:
        return None, None, None, ("broken", f"{shown} timed out after {timeout}s")
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return None, None, None, ("unknown", f"{shown} could not run: {exc}")
    return code, out, err, None


def probe(runner=None, which=None, distro=None):
    """Is WSL2 usable from this Windows side? Off native Windows this returns
    `{"state": "n/a"}` and runs nothing. Never installs, updates or changes a
    default: the only calls are `--list --verbose` and one `command -v`."""
    if not on_windows():
        return {"state": "n/a", "detail": "not native Windows"}
    runner = runner or capture
    which = which or locate
    if not which("wsl.exe"):
        return _result("not-installed", "wsl.exe is not on PATH")
    code, out, err, failed = _call(runner, ["wsl.exe", "--list", "--verbose"], LIST_TIMEOUT)
    if failed:
        return _result(*failed)
    listing = decode(out)
    text = (listing + "\n" + decode(err)).strip()
    lowered = text.lower()
    if "no installed distributions" in lowered:
        return _result("no-distro", text.splitlines()[0])
    if "is not installed" in lowered or "is not enabled" in lowered:
        return _result("not-installed", text.splitlines()[0])
    if code != 0:
        return _result("broken", f"wsl.exe --list --verbose exit {code}: {text}")
    rows = _parse_listing(listing)
    if distro:
        target = next((row for row in rows if row[0].casefold() == distro.casefold()), None)
        if target is None:
            installed = ", ".join(row[0] for row in rows) or "none"
            return _result("no-distro", f"configured distro {distro} is not installed (installed: {installed})")
    else:
        target = next((row for row in rows if row[2]), None)
        if target is None:
            return _result("no-distro", "wsl.exe --list --verbose shows no default distro")
    name, version = target[0], target[1]
    if version != "2":
        return _result("wsl1-only", f"distro {name} is WSL{version}, not WSL2", distro=name, version=version)
    code, out, err, failed = _call(runner, ["wsl.exe", "-d", name, "-e", "sh", "-c", TOOLS_CHECK], TOOLS_TIMEOUT)
    if failed:
        return _result(*failed, distro=name, version=version)
    if code not in (0, 1, 127):
        return _result("broken", f"wsl.exe -d {name} exit {code}: {(decode(err) or decode(out)).strip()}",
                       distro=name, version=version)
    found = [line.strip() for line in decode(out).splitlines() if line.strip()]
    python3 = next((path for path in found if path.endswith("/python3")), None)
    git = next((path for path in found if path.endswith("/git")), None)
    extra = {"distro": name, "version": version, "python3": python3, "git": git}
    if not python3:
        return _result("no-python3", f"python3 is not on PATH inside {name}", **extra)
    if not git:
        return _result("no-git", f"git is not on PATH inside {name}", **extra)
    return _result("usable", f"WSL2 distro {name} has python3 and git", **extra)


def recommendation(result):
    """The install recommendation, printed and never run, or None."""
    if (result or {}).get("state") not in ("not-installed", "no-distro"):
        return None
    return ("WSL2 is recommended for crew's shell-heavy jobs on this machine. To install it, run "
            "`wsl --install -d Ubuntu` in an elevated (Administrator) shell, then reboot. "
            "crew never runs it. Measured: " + MEASURED)


def probe_path():
    """`~/.claude/crew/shell-route.json`, beside the machine-global config and
    never under a repo: which shell is usable is a fact about this machine.
    Resolved at call time so a patched `crew_state.GLOBAL_CONFIG_PATH` holds."""
    import crew_state
    return os.path.join(os.path.dirname(crew_state.GLOBAL_CONFIG_PATH), "shell-route.json")


def load_cache():
    path = probe_path()
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {"state": "unknown", "detail": "never probed"}
    except (OSError, ValueError):
        return {"state": "unknown", "detail": f"cache unreadable: {path}"}
    if not isinstance(data, dict) or not isinstance(data.get("state"), str):
        return {"state": "unknown", "detail": f"cache unreadable: {path}"}
    return data


def write_cache(result):
    """Atomic and LF: the full text is computed before any file is opened, then
    written to a temp file and `os.replace`d, so a payload that raises leaves
    the previous cache byte-identical."""
    path = probe_path()
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


# --- config -------------------------------------------------------------------------

def settings(root):
    """The resolved config for `root`, both layers."""
    import crew_config
    return crew_config.resolve_config(root)


def _block(cfg):
    block = (cfg or {}).get("shellRoute")
    return block if isinstance(block, dict) else {}


def configured_distro(cfg):
    value = _block(cfg).get("distro")
    return value if isinstance(value, str) and value else None


# --- CLI ------------------------------------------------------------------------------

def _cmd_probe(args):
    result = probe(distro=configured_distro(settings(args.root)))
    if args.write:
        if result.get("state") == "n/a":
            print("crew-shell: not native Windows - nothing to probe, cache not written", file=sys.stderr)
        else:
            measured = load_cache().get("measured")
            if isinstance(measured, dict):
                result["measured"] = measured
            write_cache(result)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"wsl {result['state']}" + (f" ({result['distro']})" if result.get("distro") else "")
              + f" - {result.get('detail', '')}")
        advice = recommendation(result)
        if advice:
            print(advice)
    return 0


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("probe", help="is WSL2 usable from this Windows side")
    cmd.add_argument("--json", action="store_true")
    cmd.add_argument("--write", action="store_true", help="record the answer in the machine-local cache")
    cmd.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    return {"probe": _cmd_probe}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
