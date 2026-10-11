# pylint: disable=attribute-defined-outside-init  # upstream AI-Connect style, kept to minimise the fork's diff
"""The peer name of a STDIO client: one rule for the client and the watcher."""

import os
import socket
import sys
from collections.abc import Mapping
from pathlib import Path

# The STDIO client records its name here, one file per session process (see
# session_pid), so the session's watcher can look it up by CLAUDE_PID on every
# operating system
SESSIONS_DIR = Path.home() / ".config" / "ai-connect" / "sessions"


def peer_name(environ: Mapping[str, str], cwd: Path, configured: str = "") -> str:
    """AI_CONNECT_PEER_NAME if set, else client.name (configured), else
    "Host:Project", or "Host:Project-Suffix" with AI_CONNECT_PEER_SUFFIX.

    A per-peer token is bound to one name, client.name; Host:Project is
    accepted only through the legacy shared token.

    The project is CLAUDE_PROJECT_DIR when Claude Code sets it for its MCP
    servers, whatever directory it starts them in. Other harnesses start the
    STDIO client in the project itself, so there the working directory
    names it. The suffix lets a second session in the same project be
    reachable under its own name; a harness passes it without building the
    name itself.
    """
    if "AI_CONNECT_PEER_NAME" in environ:
        return environ["AI_CONNECT_PEER_NAME"]
    if configured:
        return configured
    project = Path(environ["CLAUDE_PROJECT_DIR"]) if "CLAUDE_PROJECT_DIR" in environ else cwd
    name = f"{socket.gethostname()}:{project.name}"
    suffix = environ.get("AI_CONNECT_PEER_SUFFIX")
    return f"{name}-{suffix}" if suffix else name


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
