"""Shared plumbing for scanner adapters.

run_tool never raises on a non-zero exit and never infers success from one:
Trivy exits 0 with findings present unless --exit-code is passed, sqlmap
exits 0 whether or not it found an injection, and ZAP's documented 0/1/2/3
contract belongs to its Docker wrapper rather than the Automation Framework
we actually invoke. Every adapter decides from parsed output, not status.
"""
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class ParseError(Exception):
    """A tool's output could not be read as the format it should be in.

    Raise this from parse() for empty, truncated, malformed or wrongly-shaped
    output. Do NOT return [] instead: an empty finding list means "this tool
    ran and found nothing", and a scan whose output we could not read is not
    the same claim. Conflating them reports a broken scan as a clean target,
    which is the failure this whole tool exists to prevent.

    Do not let JSONDecodeError or xml ParseError escape uncaught either - that
    fails the entire run rather than the single cell that actually failed.
    routine catches this and records `error:parse:<detail>` for that cell.
    """


@dataclass
class ToolResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool


def tool_home():
    """The gizmoduck tool home as a Path, or None when there is none.

    GIZMODUCK_HOME when set and not empty; otherwise, off Windows,
    $XDG_DATA_HOME/gizmoduck, else ~/.local/share/gizmoduck. Windows has no
    default: its tools stay under %LOCALAPPDATA%\\Programs, each adapter's
    last lookup step. Read on every call, never at import, and never created
    here.
    """
    home = os.environ.get("GIZMODUCK_HOME")
    if home:
        return Path(home)
    if os.name == "nt":
        return None
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "gizmoduck"
    try:
        return Path.home() / ".local" / "share" / "gizmoduck"
    except RuntimeError:  # no HOME and no passwd entry: there is no default
        return None


def _windows():
    """Kept in one place so a test can ask for Windows lookup rules without
    patching os.name, which the rest of the process also reads."""
    return os.name == "nt"


def _pathext():
    return [e.lower() for e in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(os.pathsep)
            if e]


def is_executable(path):
    """A file this process may run: off Windows, a file with the execute bit;
    on Windows (where os.access X_OK is true for every file), a file whose
    extension is in PATHEXT - a `testssl.sh` there is not one."""
    try:
        if not Path(path).is_file():
            return False
        if _windows():
            return Path(path).suffix.lower() in _pathext()
        return os.access(path, os.X_OK)
    except OSError:
        return False


def _names(binary):
    """`binary`, and on Windows each PATHEXT extension of it when it has none,
    as shutil.which tries them: `dependency-check` is `dependency-check.bat`."""
    if not _windows() or Path(binary).suffix:
        return [binary]
    return [binary] + [binary + ext for ext in _pathext()]


def _in_tool_home(binary):
    home = tool_home()
    if home is not None:
        for name in _names(binary):
            candidate = home / "bin" / name
            if is_executable(candidate):
                return str(candidate)
    return None


def which(binary):
    """<tool home>/bin/<binary> when it is an executable file, else PATH."""
    return _in_tool_home(binary) or shutil.which(binary)


def which_any(*binaries):
    """The first of several names for one tool (zap.bat / zap.sh), with the
    tool home searched for EVERY name before PATH is searched for any, so a
    PATH copy under one name never beats the tool home's copy under another."""
    for binary in binaries:
        found = _in_tool_home(binary)
        if found:
            return found
    for binary in binaries:
        found = which(binary)
        if found:
            return found
    return None


UNSET, OK, BROKEN = "unset", "ok", "broken"


@dataclass
class Override:
    """One lookup variable's state. `found` is what `value` resolved to.

    BROKEN covers "empty", "points at nothing usable" and "could not be
    checked" (an OSError while looking): a variable that is set is never read as
    UNSET, so a broken override disables its tool instead of letting the
    lookup fall through to some other install.
    """
    var: str
    state: str
    value: str = ""
    found: object = None


def override(var, resolve):
    """Read `var` now and resolve it with `resolve(Path) -> found | None`."""
    if var not in os.environ:
        return Override(var, UNSET)
    value = os.environ[var]
    if not value.strip():
        # Exported but empty: set, and naming nothing - broken, never unset,
        # so the tool is disabled instead of found somewhere else.
        return Override(var, BROKEN, value)
    try:
        found = resolve(Path(value))
    except OSError:
        found = None
    return Override(var, OK if found else BROKEN, value, found)


def existing_file(path):
    """`resolve` for an override naming one file: the path when it is a file."""
    return str(path) if path.is_file() else None


def run_tool(argv, timeout, cwd=None):
    try:
        p = subprocess.run(argv, capture_output=True, text=True,
                           timeout=timeout, cwd=cwd, check=False)
        return ToolResult(p.returncode, p.stdout or "", p.stderr or "", False)
    except subprocess.TimeoutExpired as e:
        return ToolResult(-1, e.stdout or "", e.stderr or "", True)
    except FileNotFoundError as e:
        return ToolResult(-1, "", str(e), False)
