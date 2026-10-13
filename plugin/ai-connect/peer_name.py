# pylint: disable=attribute-defined-outside-init  # upstream AI-Connect style, kept to minimise the fork's diff
"""The peer name of a STDIO client: one rule for the client and the watcher."""

import hashlib
import json
import os
import re
import socket
import sys
import unicodedata
from collections.abc import Mapping
from pathlib import Path

# The STDIO client records its name here, one file per session process (see
# session_pid), so the session's watcher can look it up by CLAUDE_PID on every
# operating system
SESSIONS_DIR = Path.home() / ".config" / "ai-connect" / "sessions"

# client.name_mode: "per-project" names each session <client.name>-<project>
PER_PROJECT = "per-project"
# vpn/tsadmin.py PEER_NAME_RE: the names deploy and setup enrol, and the only
# ones config_loader looks a session token up for
PEER_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,62}")
_NOT_IN_A_NAME = re.compile(r"[^A-Za-z0-9-]+")
# server/user_send.py is_reserved_name: the Bridge refuses these as peer names
_RESERVED_NAME = "bridge"
_RESERVED_PREFIX = "user:"


def is_reserved_name(name: str) -> bool:
    """Names only the Bridge and users have (server/user_send.py); compared without case."""
    folded = name.casefold()
    return folded == _RESERVED_NAME or folded.startswith(_RESERVED_PREFIX)


def project_dir(environ: Mapping[str, str], cwd: Path) -> Path:
    """The session's project: CLAUDE_PROJECT_DIR when set, else the working directory; absolute and resolved."""
    return Path(environ["CLAUDE_PROJECT_DIR"] if environ.get("CLAUDE_PROJECT_DIR") else cwd).resolve()


def project_peer_name(base: str, project: Path) -> str | None:
    """<base>-<project basename> for client.name_mode: per-project, or None if that is no usable peer name.

    The basename is cut down to what a peer name may hold (PEER_NAME_RE): every
    run of other characters becomes one hyphen and hyphens at either end go, so
    "My App.v2" gives "My-App-v2". The whole name is cut to 63 characters, again
    without a trailing hyphen. Two projects can so end up with one name; the
    <name>.dir file beside the token tells them apart (config_loader).
    """
    tail = _NOT_IN_A_NAME.sub("-", project.name).strip("-")
    if not base or not tail:
        return None
    name = f"{base}-{tail}"[:63].rstrip("-")
    if not PEER_NAME_RE.fullmatch(name) or is_reserved_name(name):
        return None
    return name


# A session's label is what the Bridge accepts after "<client.name>:" (SESSION_LABEL in
# server/roles.py: letters, digits, . _ -, at most 64). The label stays shorter, so the
# collision suffix ("-<process id>") still fits
LABEL_MAX = 40
SUFFIX_MAX = 16
_LABEL_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _plain(text: str, limit: int) -> str:
    """text with accents dropped and every run of other characters as one hyphen."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return _LABEL_UNSAFE.sub("-", ascii_text).strip("-.")[:limit].strip("-.")


def _project(environ: Mapping[str, str], cwd: Path) -> str:
    """The project's directory name: CLAUDE_PROJECT_DIR when Claude Code sets it for its
    MCP servers, whatever directory it starts them in. Other harnesses start the STDIO
    client in the project itself, so there the working directory names it."""
    return (Path(environ["CLAUDE_PROJECT_DIR"]) if "CLAUDE_PROJECT_DIR" in environ else cwd).name


# Claude Code keeps one <process id>.json per running session in its sessions directory,
# with the name the session was given ("name"). The file is an internal of Claude Code,
# not a documented interface: whatever goes wrong reading it, the label is the project's.
# A real one is a few hundred bytes; nothing larger is parsed
_SESSION_FILE_MAX = 64 * 1024


def claude_sessions_dir(environ: Mapping[str, str]) -> Path:
    """Where Claude Code keeps its session files: under CLAUDE_CONFIG_DIR when set, else ~/.claude."""
    config_dir = Path(environ["CLAUDE_CONFIG_DIR"]) if environ.get("CLAUDE_CONFIG_DIR") else Path.home() / ".claude"
    return config_dir / "sessions"


def claude_session_title(pid: int, sessions_dir: Path) -> str:
    """The name Claude Code holds for the session with this process id, or "" for any reason
    there is none to read: no such file (another harness), unreadable, no JSON object, no
    text under "name". Never raises.

    Exactly one file is opened, <sessions_dir>/<pid>.json, and the directory is not
    listed: the <pid>.<hash>.key files beside it hold a secret.
    """
    try:
        with (sessions_dir / f"{int(pid)}.json").open("rb") as handle:
            raw = handle.read(_SESSION_FILE_MAX + 1)
        if len(raw) > _SESSION_FILE_MAX:
            return ""
        data = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, TypeError, RecursionError):
        # ValueError: not UTF-8, not JSON (json.JSONDecodeError), or a pid that is no number
        return ""
    title = data.get("name") if isinstance(data, dict) else None
    return title if isinstance(title, str) else ""


def session_label(environ: Mapping[str, str], cwd: Path, title: str = "") -> str:
    """What tells this session from the others on its machine: the session's own name
    (title, see claude_session_title) when it has one, else its project's name; made
    plain, with AI_CONNECT_PEER_SUFFIX appended if set.

    A session name with nothing plain in it counts as none. A project name with
    nothing plain in it (another script, an emoji) gets a short hash of itself
    instead, so two such projects still differ.
    """
    suffix = _plain(environ.get("AI_CONNECT_PEER_SUFFIX", ""), SUFFIX_MAX)
    room = LABEL_MAX - (len(suffix) + 1 if suffix else 0)
    label = _plain(title, room)
    if not label:
        project = _project(environ, cwd)
        digest = hashlib.sha256(project.encode(errors="backslashreplace")).hexdigest()[:8]
        label = _plain(project, room) or "p-" + digest
    return f"{label}-{suffix}" if suffix else label


def peer_name(environ: Mapping[str, str], cwd: Path, configured: str = "", title: str = "") -> str:
    """AI_CONNECT_PEER_NAME if set, else "<client.name>:<label>" (configured is
    client.name, title the session's own name, see session_label), else the legacy
    "Host:Project", or "Host:Project-Suffix" with AI_CONNECT_PEER_SUFFIX.

    client.name is the machine: its token registers that name and every
    "<client.name>:<label>", so each session on the machine has a name of
    its own. Host:Project is accepted only through the legacy shared token,
    and is never the session's name.

    The suffix lets a harness give a second session in the same project a
    name it knows beforehand, without building the name itself.
    """
    if "AI_CONNECT_PEER_NAME" in environ:
        return environ["AI_CONNECT_PEER_NAME"]
    if configured:
        return f"{configured}:{session_label(environ, cwd, title)}"
    name = f"{socket.gethostname()}:{_project(environ, cwd)}"
    suffix = environ.get("AI_CONNECT_PEER_SUFFIX")
    return f"{name}-{suffix}" if suffix else name


def session_identity(
    environ: Mapping[str, str], cwd: Path, chosen: str, configured: str, title: str = "",
) -> tuple[str, dict[str, str]]:
    """(name, BridgeClient's machine_name argument) of a STDIO session.

    chosen is the name config_loader settled on, configured is client.name,
    title the session's own name (claude_session_title), "" when it has none.
    chosen and configured differ when client.name_mode: per-project found the
    project's own token: "<client.name>-<project>" is bound to that token and
    registered as it is, with no fallback, no suffix and no session name.
    Otherwise, also when that mode fell back to client.token, the session is
    "<client.name>:<label>" on the machine's token (peer_name).
    """
    if "AI_CONNECT_PEER_NAME" not in environ and chosen != configured:
        return chosen, {}
    return peer_name(environ, cwd, configured, title), {"machine_name": machine_name(environ, configured)}


def machine_name(environ: Mapping[str, str], configured: str = "") -> str:
    """The name a session falls back to on a Bridge from before session names (0.1.8):
    client.name, or "" when the session's name was not derived from it."""
    return "" if "AI_CONNECT_PEER_NAME" in environ else configured


def record_session_name(session_pid: int, name: str) -> Path:
    """Note which peer name the session with this process id uses."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = SESSIONS_DIR / str(session_pid)
    path.write_text(name, encoding="utf-8")
    return path


def session_name(session_pid: str) -> str | None:
    """The peer name the session with this process id recorded, if any."""
    path = SESSIONS_DIR / session_pid
    return path.read_text(encoding="utf-8") if path.exists() else None


def record_seen(session_pid: int | str, timestamp: str) -> None:
    """Note up to which Bridge timestamp the session has seen its messages."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    (SESSIONS_DIR / f"{session_pid}.seen").write_text(timestamp, encoding="utf-8")


def seen_since(session_pid: int | str) -> str | None:
    """The Bridge timestamp the session has seen its messages up to, if any."""
    path = SESSIONS_DIR / f"{session_pid}.seen"
    return path.read_text(encoding="utf-8") if path.exists() else None


def process_alive(pid: int) -> bool:
    """Whether a process with this id is running.

    Not os.kill(pid, 0) on Windows: there os.kill terminates the process.
    """
    if sys.platform == "win32":
        return pid in _windows_processes()
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def remove_dead_sessions() -> None:
    """Delete the name and read-state files of sessions that no longer run.

    Windows ends a session's MCP client hard, so its files stay behind.
    """
    if not SESSIONS_DIR.exists():
        return
    for path in SESSIONS_DIR.iterdir():
        pid = path.name.split(".")[0]
        if pid.isdigit() and not process_alive(int(pid)):
            path.unlink(missing_ok=True)


def session_pid() -> int:
    """Process id of the session (Claude Code) that started this MCP client.

    That is the parent, except on Windows: there a venv's python.exe is a
    launcher that starts the real interpreter as its child, so when the
    parent is itself a python.exe, the session is the launcher's parent.
    (The launcher's __PYVENV_LAUNCHER__ is gone by the time Python runs.)
    """
    parent = os.getppid()
    if sys.platform == "win32":
        launcher_parent, exe = _windows_processes()[parent]
        if exe.lower() in ("python.exe", "pythonw.exe"):
            return launcher_parent
    return parent


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _ProcessEntry(ctypes.Structure):
        # PROCESSENTRY32W from the Toolhelp API
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    def _windows_processes() -> dict[int, tuple[int, str]]:
        """Every running process: id -> (parent id, executable name), from a Toolhelp snapshot."""
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
        entry = _ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        processes = {}
        try:
            found = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
            while found:
                processes[int(entry.th32ProcessID)] = (int(entry.th32ParentProcessID), entry.szExeFile)
                found = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            kernel32.CloseHandle(snapshot)
        return processes
