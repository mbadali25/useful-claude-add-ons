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


def _is_executable(path):
    try:
        return path.is_file() and os.access(path, os.X_OK)
    except OSError:
        return False


def which(binary):
    """<tool home>/bin/<binary> when it is an executable file, else PATH."""
    home = tool_home()
    if home is not None:
        candidate = home / "bin" / binary
        if _is_executable(candidate):
            return str(candidate)
    return shutil.which(binary)


UNSET, OK, BROKEN = "unset", "ok", "broken"


@dataclass
class Override:
    """One lookup variable's state. `found` is what `value` resolved to.

    BROKEN covers both "points at nothing usable" and "could not be checked"
    (an OSError while looking): a variable that is set is never read as
    UNSET, so a broken override disables its tool instead of letting the
    lookup fall through to some other install.
    """
    var: str
    state: str
    value: str = ""
    found: object = None


def override(var, resolve):
    """Read `var` now and resolve it with `resolve(Path) -> found | None`."""
    value = os.environ.get(var)
    if not value:
        return Override(var, UNSET)
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
