# pylint: disable=attribute-defined-outside-init  # upstream AI-Connect style, kept to minimise the fork's diff
"""The peer name of a STDIO client: one rule for the client and the watcher."""

import hashlib
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


def session_label(environ: Mapping[str, str], cwd: Path) -> str:
    """What tells this session from the others on its machine: its project's name,
    made plain, with AI_CONNECT_PEER_SUFFIX appended if set.

    A name with nothing plain in it (another script, an emoji) gets a short
    hash of itself instead, so two such projects still differ.
    """
    project = _project(environ, cwd)
    suffix = _plain(environ.get("AI_CONNECT_PEER_SUFFIX", ""), SUFFIX_MAX)
    room = LABEL_MAX - (len(suffix) + 1 if suffix else 0)
    label = _plain(project, room) or "p-" + hashlib.sha256(project.encode(errors="backslashreplace")).hexdigest()[:8]
    return f"{label}-{suffix}" if suffix else label


def peer_name(environ: Mapping[str, str], cwd: Path, configured: str = "") -> str:
    """AI_CONNECT_PEER_NAME if set, else "<client.name>:<label>" (configured is
    client.name, see session_label), else the legacy "Host:Project", or
    "Host:Project-Suffix" with AI_CONNECT_PEER_SUFFIX.

    client.name is the machine: its token registers that name and every
    "<client.name>:<label>", so each session on the machine has a name of
    its own. Host:Project is accepted only through the legacy shared token.

    The suffix lets a harness give a second session in the same project a
    name it knows beforehand, without building the name itself.
    """
    if "AI_CONNECT_PEER_NAME" in environ:
        return environ["AI_CONNECT_PEER_NAME"]
    if configured:
        return f"{configured}:{session_label(environ, cwd)}"
    name = f"{socket.gethostname()}:{_project(environ, cwd)}"
    suffix = environ.get("AI_CONNECT_PEER_SUFFIX")
    return f"{name}-{suffix}" if suffix else name


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
