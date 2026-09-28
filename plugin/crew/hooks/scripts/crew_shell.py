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
import time

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


def raw_mode(cfg):
    value = _block(cfg).get("mode")
    return "auto" if value is None else str(value)


def mode(cfg):
    """`(mode, note)`. An unrecognised value is read as `auto`, and the note
    names it so the route line and the status line can say so."""
    value = raw_mode(cfg)
    if value in MODES:
        return value, None
    return "auto", f"shellRoute.mode {value!r} is not a mode - read as auto"


def effective_probe(cache, cfg):
    """The cached probe, or `unknown` when `shellRoute.distro` names a distro
    other than the one the cache probed: that answer is about another distro."""
    wanted = configured_distro(cfg)
    probed = cache.get("distro")
    if wanted and probed and wanted.casefold() != str(probed).casefold():
        return {"state": "unknown", "distro": None,
                "detail": f"cache probed {probed} but shellRoute.distro is {wanted} - "
                          "run crew_shell.py probe --write"}
    return cache


def _repo_key(root):
    return os.path.normcase(root)


def measured_verdict(cache, root):
    """`wsl-faster`, `gitbash-faster` or `none` for this repo."""
    measured = cache.get("measured") if isinstance(cache, dict) else None
    entry = measured.get(_repo_key(root)) if isinstance(measured, dict) else None
    verdict = entry.get("verdict") if isinstance(entry, dict) else None
    return verdict if verdict in ("wsl-faster", "gitbash-faster") else "none"


# --- decide ---------------------------------------------------------------------------

POWERSHELL_BASH = "powershell requested; job is bash syntax -> gitbash"
REFUSED = "-> refused (exit 3)"


def _wsl_state(probe_result):
    state = (probe_result or {}).get("state") or "unknown"
    detail = (probe_result or {}).get("detail")
    if state == "unknown" and detail == "never probed":
        return "WSL never probed (unknown)"
    return f"WSL {state}" + (f" ({detail})" if detail else "")


def fallback(job_class, why):
    """`auto` without WSL: plain argv runs with no shell, anything else in Git
    Bash. Never pwsh -- on a real job the launcher is noise and direct exec is
    the cheaper of the two."""
    if job_class == "plain":
        return "direct", f"{why}; plain argv -> direct", None
    return "gitbash", f"{why}; bash syntax -> gitbash", None


def decide(mode_value, probe_result, location, measured, host, job_class, pwsh):
    """`(route, reason, exit)`. `route` is `bash` (off Windows: plain `bash -c`,
    no message), `wsl`, `gitbash`, `direct`, `powershell` or `refuse` (with
    exit 3). A pure function of its arguments: the same job takes the same
    route on the same machine."""
    if not on_windows(host):
        return "bash", "", None
    note = ""
    if mode_value not in MODES:
        note = f"shellRoute.mode {mode_value!r} is not a mode - read as auto; "
        mode_value = "auto"
    state = (probe_result or {}).get("state") or "unknown"
    distro = (probe_result or {}).get("distro")
    if mode_value == "gitbash":
        return "gitbash", "shellRoute.mode gitbash -> gitbash", None
    if mode_value == "powershell":
        if job_class != "plain":
            return "gitbash", POWERSHELL_BASH, None
        if pwsh:
            return "powershell", f"shellRoute.mode powershell; plain argv -> powershell ({pwsh})", None
        return "refuse", f"shellRoute.mode powershell but {resolve_pwsh(exists=lambda _p: False)[1]} {REFUSED}", 3
    usable = state == "usable"
    if mode_value == "wsl":
        if not usable:
            return "refuse", f"shellRoute.mode wsl but {_wsl_state(probe_result)} {REFUSED}, no fallback", 3
        if location not in ("windows-drive", "wsl-fs"):
            return "refuse", f"shellRoute.mode wsl but the repo path has no WSL translation {REFUSED}", 3
        return "wsl", f"shellRoute.mode wsl; WSL2 usable ({distro}) -> wsl", None
    if usable and location == "wsl-fs":
        return "wsl", f"{note}auto: WSL2 usable ({distro}) and the repo is inside WSL -> wsl", None
    if usable and location == "windows-drive" and measured == "wsl-faster":
        return "wsl", f"{note}auto: WSL2 usable ({distro}) and measured faster than Git Bash here -> wsl", None
    if not usable:
        why = _wsl_state(probe_result)
    elif location == "windows-drive" and measured == "gitbash-faster":
        why = "WSL usable but measured slower than Git Bash for this repo on its Windows drive"
    elif location == "windows-drive":
        why = "WSL usable but this repo is on a Windows drive and not measured (crew_shell.py measure --write)"
    else:
        why = "WSL usable but the repo path has no WSL translation"
    return fallback(job_class, f"{note}auto: {why}")


# --- run ------------------------------------------------------------------------------

def wsl_argv(cmd, cwd, distro):
    return ["wsl.exe", "-d", distro, "--cd", cwd, "-e", "bash", "-lc", cmd]


def gitbash_argv(cmd, bash):
    return [bash, "-lc", cmd]


def pwsh_argv(argv, pwsh):
    """`argv` is the classified list, never a command string: each element is
    single-quoted with `'` doubled, so pwsh sees literal arguments."""
    quoted = " ".join("'" + part.replace("'", "''") + "'" for part in argv)
    return [pwsh, "-NoProfile", "-NonInteractive", "-Command", f"& {quoted}; exit $LASTEXITCODE"]


def execute_job(argv, cwd):
    """The default executor: stdio inherited, the child's exit code returned."""
    return subprocess.run(argv, cwd=cwd, check=False).returncode


_BUILTINS = ("cd", "source", ".", "exec", "eval", "export", "set")


def _first_word(cmd):
    """The program a bash job starts with, for the WSL preflight, or None when
    there is nothing to look up (a builtin, a path, an empty command)."""
    try:
        tokens = shlex.split(cmd)
    except ValueError:
        tokens = cmd.split()
    for token in tokens:
        token = token.lstrip("({")
        name = token.split("=", 1)[0]
        if not token or ("=" in token and name.isidentifier()):
            continue
        if token in _BUILTINS or "/" in token:
            return None
        return token
    return None


def _preflight(runner, distro, cmd):
    """None when the job's first word resolves inside WSL, else why not."""
    word = _first_word(cmd)
    if word is None:
        return None
    argv = ["wsl.exe", "-d", distro, "-e", "sh", "-c", "command -v " + shlex.quote(word)]
    code, _, _, failed = _call(runner, argv, TOOLS_TIMEOUT)
    if failed:
        return f"the WSL preflight for {word} failed: {failed[1]}"
    return None if code == 0 else f"{word} is not on PATH inside {distro}"


def _absolute(root):
    if _DRIVE.match(root) or root.startswith(("\\\\", "//")):
        return root
    return os.path.abspath(root)


def run(cmd, root=".", runner=None, execute=None):
    """Run `cmd` on the resolved route and return its exit code. Off native
    Windows this is exactly `bash -c <cmd>`: no probe, no config read, no
    message."""
    execute = execute or execute_job
    if not on_windows():
        return execute(["bash", "-c", cmd], root)
    runner = runner or capture
    root = _absolute(root)
    cfg = settings(root)
    normal, _ = mode(cfg)
    cache = effective_probe(load_cache(), cfg)
    kind, argv, creason = classify(cmd)
    location = repo_location(root)
    pwsh = resolve_pwsh()[0] if normal == "powershell" and kind == "plain" else None
    route, reason, code = decide(raw_mode(cfg), cache, location, measured_verdict(cache, root), host_os(), kind, pwsh)
    distro = cache.get("distro")
    wsl_cwd = None
    if route == "wsl":
        wsl_cwd, why = to_wsl_path(root, distro)
        missing = why if wsl_cwd is None else _preflight(runner, distro, cmd)
        if missing and normal == "wsl":
            route, reason, code = "refuse", f"shellRoute.mode wsl but {missing} {REFUSED}, no fallback", 3
        elif missing:
            route, reason, code = fallback(kind, f"auto: WSL usable but {missing}")
    bash = None
    if route == "gitbash":
        bash, why = resolve_gitbash(runner)
        if bash is None:
            route, reason, code = "refuse", f"{reason}; but {why} {REFUSED}", 3
    if route in ("direct", "powershell"):
        reason += f" [{creason}]"
    print(f"crew-shell: {reason}", file=sys.stderr, flush=True)
    if code:
        return code
    job = {"wsl": lambda: wsl_argv(cmd, wsl_cwd, distro), "gitbash": lambda: gitbash_argv(cmd, bash),
           "direct": lambda: argv, "powershell": lambda: pwsh_argv(argv, pwsh)}[route]()
    return execute(job, root)


# --- measure --------------------------------------------------------------------------

FORKS, WRITES = 50, 200
_BASH_FORKS = f"i=0; while [ $i -lt {FORKS} ]; do /usr/bin/true; i=$((i+1)); done"
_BASH_WRITES = "i=0; while [ $i -lt " + str(WRITES) + " ]; do echo x > \"$d/f$i\"; i=$((i+1)); done"
_PWSH_FORKS = f"for ($i=0; $i -lt {FORKS}; $i++) {{ & $env:ComSpec /d /c rem }}"
_PWSH_WRITES = f"for ($i=0; $i -lt {WRITES}; $i++) {{ [IO.File]::WriteAllText(\"$d\\f$i\", 'x') }}"


def _timed(runner, timer, argv, timeout=120):
    start = timer()
    code, _, err = runner(argv, timeout)
    elapsed = timer() - start
    if code != 0:
        raise RuntimeError(f"exit {code}: {decode(err).strip()[:200]}")
    return elapsed


def _side(runner, timer, prefix, scripts):
    """`{"forks": s, "writes": s}` net of the shell's own start-up, or
    `{"error": ...}`. A side that failed is an error, never a number."""
    base, forks, writes = scripts
    try:
        startup = _timed(runner, timer, prefix + [base])
        return {"forks": round(max(0.0, _timed(runner, timer, prefix + [forks]) - startup), 4),
                "writes": round(max(0.0, _timed(runner, timer, prefix + [writes]) - startup), 4)}
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        return {"error": str(exc) or type(exc).__name__}


def _verdict(sides):
    gitbash, wsl = sides.get("gitbash", {}), sides.get("wsl", {})
    if not all(key in side for side in (gitbash, wsl) for key in ("forks", "writes")):
        return "unknown"
    faster = wsl["forks"] < gitbash["forks"] and wsl["writes"] < gitbash["writes"]
    return "wsl-faster" if faster else "gitbash-faster"


def measure(root, runner=None, timer=None, cache=None, cfg=None):
    """50 forks and 200 small writes for Git Bash, pwsh and WSL, at the repo's
    own location, plus WSL's ext4 as the in-WSL clone reference when the repo
    is on a Windows drive. Off native Windows: `n/a`, nothing run."""
    if not on_windows():
        return {"state": "n/a", "detail": "not native Windows"}
    import datetime
    import socket
    import tempfile
    runner = runner or capture
    timer = timer or time.perf_counter
    root = _absolute(root)
    cfg = settings(root) if cfg is None else cfg
    cache = effective_probe(load_cache() if cache is None else cache, cfg)
    location = repo_location(root)
    work = tempfile.mkdtemp(prefix=".crew-shell-measure-", dir=root)
    sides = {}
    try:
        bash, why = resolve_gitbash(runner)
        if bash:
            d_bash = os.path.join(work, "gitbash").replace("\\", "/")
            os.makedirs(d_bash)
            sides["gitbash"] = _side(runner, timer, [bash, "-c"],
                                     (":", _BASH_FORKS, f"d='{d_bash}'; " + _BASH_WRITES))
        else:
            sides["gitbash"] = {"error": why}
        pwsh, why = resolve_pwsh()
        if pwsh:
            d_pwsh = os.path.join(work, "pwsh")
            os.makedirs(d_pwsh)
            sides["pwsh"] = _side(runner, timer, [pwsh, "-NoProfile", "-NonInteractive", "-Command"],
                                  ("exit 0", _PWSH_FORKS, f"$d = '{d_pwsh}'; " + _PWSH_WRITES))
        else:
            sides["pwsh"] = {"error": why}
        distro = cache.get("distro")
        if cache.get("state") != "usable":
            sides["wsl"] = {"error": f"{_wsl_state(cache)} - run crew_shell.py probe --write first"}
        else:
            prefix = ["wsl.exe", "-d", distro, "-e", "bash", "-c"]
            d_wsl, why = to_wsl_path(os.path.join(work, "wsl"), distro)
            if d_wsl is None:
                sides["wsl"] = {"error": why}
            else:
                os.makedirs(os.path.join(work, "wsl"))
                sides["wsl"] = _side(runner, timer, prefix, (":", _BASH_FORKS, f"d='{d_wsl}'; " + _BASH_WRITES))
            if location == "windows-drive":
                sides["wsl-ext4"] = _side(runner, timer, prefix, (
                    'd=$(mktemp -d); rm -rf "$d"', _BASH_FORKS,
                    'd=$(mktemp -d); ' + _BASH_WRITES + '; rm -rf "$d"'))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return {"host": socket.gethostname(), "date": datetime.date.today().isoformat(), "root": root,
            "location": location, "distro": cache.get("distro"), "forks": FORKS, "writes": WRITES,
            "sides": sides, "verdict": _verdict(sides)}


def _clone_offer(result):
    ext4, here = result["sides"].get("wsl-ext4", {}), result["sides"].get("gitbash", {})
    if result.get("location") != "windows-drive" or "writes" not in ext4 or "writes" not in here:
        return None
    return (f"In-WSL clone (offered, never made by crew): WSL ext4 takes {ext4['forks']} s for {FORKS} forks "
            f"and {ext4['writes']} s for {WRITES} writes, against Git Bash's {here['forks']} s and "
            f"{here['writes']} s here. A clone inside WSL, opened from Windows through \\\\wsl.localhost\\, "
            "routes to WSL under auto. Moving a repo changes paths other tools use; the owner decides.")


def status_line(root):
    """The `/crew:status` `shell` line, or None off native Windows."""
    if not on_windows():
        return None
    return None


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


def _command_text(parts):
    """`run -- "<cmd>"` takes one argument; several are joined with spaces."""
    parts = list(parts)
    if parts[:1] == ["--"]:
        parts = parts[1:]
    return parts[0] if len(parts) == 1 else " ".join(parts)


def _cmd_measure(args):
    result = measure(args.root)
    if result.get("state") == "n/a":
        print("crew-shell: not native Windows - nothing to measure")
        return 0
    if args.write:
        cache = load_cache()
        measured = cache.get("measured") if isinstance(cache.get("measured"), dict) else {}
        measured[_repo_key(result["root"])] = result
        cache["measured"] = measured
        write_cache(cache)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    print(f"measured on {result['host']} {result['date']}, repo {result['root']} ({result['location']})")
    for side, numbers in result["sides"].items():
        if "error" in numbers:
            print(f"  {side:<9} error: {numbers['error']}")
        else:
            print(f"  {side:<9} {FORKS} forks {numbers['forks']} s, {WRITES} writes {numbers['writes']} s")
    print(f"verdict {result['verdict']}")
    offer = _clone_offer(result)
    if offer:
        print(offer)
    return 0


def _cmd_classify(args):
    kind, _, reason = classify(_command_text(args.command))
    print(f"{kind}: {reason}")
    return 0


def _cmd_run(args):
    return run(_command_text(args.command), root=args.root)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command_name", required=True)
    cmd = sub.add_parser("probe", help="is WSL2 usable from this Windows side")
    cmd.add_argument("--json", action="store_true")
    cmd.add_argument("--write", action="store_true", help="record the answer in the machine-local cache")
    cmd.add_argument("--root", default=".")
    cmd = sub.add_parser("measure", help="forks and small writes per shell, at this repo's location")
    cmd.add_argument("--json", action="store_true")
    cmd.add_argument("--write", action="store_true", help="record the result in the machine-local cache")
    cmd.add_argument("--root", default=".")
    cmd = sub.add_parser("classify", help="plain argv or bash syntax, and why")
    cmd.add_argument("command", nargs=argparse.REMAINDER)
    cmd = sub.add_parser("run", help="run one job on the resolved route")
    cmd.add_argument("--root", default=".")
    cmd.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    handlers = {"probe": _cmd_probe, "measure": _cmd_measure, "classify": _cmd_classify, "run": _cmd_run}
    return handlers[args.command_name](args)


if __name__ == "__main__":
    sys.exit(main())
