"""crew_holder.py: one liveness proof for every crew runner that holds something.

Who holds a claim or a marker, and whether that holder still lives. Moved
verbatim from T-0030's `crew_coord.py` (branch T-0030-coord a54117e8) so that
`crew_inflight.py` (T-0049) and `crew_coord.py` share ONE pid check instead of
two copies: the T-0030 one took six review rounds to get right, and a second
copy would have to earn every one of them again.

A holder is session id + bridge session + CLAUDE_PID (+ its start time and PID
namespace) + machine + worktree (`current_holder`). `probe_pid` reads a pid
`alive`, `gone` or `unknown`; where a measured check cannot tell, it reads
ALIVE, never gone. `probe_holder` lets `gone` stand only inside the PID
namespace recorded when the holder was taken (bubblewrap's --unshare-pid hides
a live pid). `processes_in` (new in T-0049) names the live processes whose
working directory is inside a path, on Linux only and only when this process
can see its own CLAUDE_PID; anywhere else it answers `unknown`.

`owner_signal` is True only outside Claude Code (CLAUDECODE and
CLAUDE_CODE_SESSION_ID both absent). It is spoofable with `env -u`, so it stops
an accidental owner-only action, not a determined agent: a prose control.

The file lock (`_locked`) and the private per-user directory (`private_dir`)
are the ones T-0030's heartbeat uses. Nothing here prints an environment value.
"""
import contextlib
import datetime
import os
import socket
import stat
import sys
import tempfile
import unicodedata
from collections import namedtuple

# Cc control (C0, C1), Cf format (bidi overrides and isolates, zero-width),
# Zl/Zp (U+2028/U+2029, which str.splitlines() breaks on), Cs surrogates.
_UNSAFE_CATEGORIES = frozenset(("Cc", "Cf", "Zl", "Zp", "Cs"))
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_ERROR_INVALID_PARAMETER = 87
_SECRET_NAMES = ("CLAUDE_CODE_MESSAGING_TOKEN",)

PidProbe = namedtuple("PidProbe", "state start measured")


# --- small helpers -------------------------------------------------------------

def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def stamp(when=None):
    return (when or utcnow()).isoformat(timespec="seconds")


def parse_stamp(text):
    if not isinstance(text, str):
        return None
    try:
        when = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    return when if when.tzinfo else None


def age_text(seconds):
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"
    return f"{seconds // 86400}d"


def safe(value, limit=200):
    """Peer-written text made printable: control, format (bidi) and line or
    paragraph separator characters -- newlines, ANSI escapes, U+2028, U+202E --
    become '?', and length is capped. For display only -- never used in a
    comparison."""
    text = "".join("?" if unicodedata.category(ch) in _UNSAFE_CATEGORIES else ch for ch in str(value))
    return text if len(text) <= limit else text[:limit] + "..."


def machine():
    return socket.gethostname()


# --- identity and processes ------------------------------------------------------

def _env_pid():
    raw = os.environ.get("CLAUDE_PID", "")
    return int(raw) if raw.isdigit() and int(raw) > 0 else None


def _linux_probe(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return PidProbe("gone", None, True)
    except PermissionError:
        pass
    except OSError:
        return PidProbe("unknown", None, False)
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as handle:
            data = handle.read()
    except OSError:
        # os.kill has just shown the pid exists (it returned, or refused with
        # PermissionError), so an unreadable /proc -- not mounted in a sandbox,
        # hidepid hiding another user -- cannot tell: ALIVE, never gone.
        return PidProbe("alive", None, True)
    try:
        rest = data[data.rindex(")") + 2:].split()
        state, start = rest[0], rest[19]
    except (ValueError, IndexError):
        return PidProbe("alive", None, True)
    if state == "Z":
        return PidProbe("gone", None, True)
    return PidProbe("alive", start if start.isdigit() else None, True)


def _filetime(value):
    return (value.dwHighDateTime << 32) | value.dwLowDateTime


def _kernel32():
    import ctypes  # pylint: disable=import-outside-toplevel
    from ctypes import wintypes  # pylint: disable=import-outside-toplevel
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    return kernel, ctypes.get_last_error


def _windows_probe(pid, kernel=None, last_error=None):
    """Measured in the T-0030 spike (section "4-5 (Windows)": Python 3.14.6,
    elevated, one host). Open with PROCESS_QUERY_LIMITED_INFORMATION: a NULL
    handle with error 87 is the only DEAD; any other error (5, access denied,
    included) cannot tell and reads ALIVE. A handle that opens is not proof of
    life -- a dead process whose handle someone still holds opens too -- so it
    is DEAD only when GetProcessTimes gives a nonzero exit FILETIME; exit code
    259 is not used, because 259 is a legal exit code. The creation FILETIME is
    the start that assess_recovery compares with the recorded pid_start.
    `kernel` and `last_error` are the ctypes seam the tests stub. NOT measured:
    a non-elevated OpenProcess on another user's process; it can only fail,
    and a failure other than 87 reads alive."""
    import ctypes  # pylint: disable=import-outside-toplevel
    from ctypes import wintypes  # pylint: disable=import-outside-toplevel
    try:
        if kernel is None:
            kernel, last_error = _kernel32()
        handle = kernel.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            if last_error() == _ERROR_INVALID_PARAMETER:
                return PidProbe("gone", None, True)
            return PidProbe("alive", None, True)  # any other OpenProcess error cannot tell
        try:
            times = [wintypes.FILETIME() for _ in range(4)]
            if not kernel.GetProcessTimes(handle, *[ctypes.byref(t) for t in times]):
                return PidProbe("alive", None, True)
            created, exited = _filetime(times[0]), _filetime(times[1])
            if exited:
                return PidProbe("gone", None, True)
            return PidProbe("alive", str(created) if created else None, True)
        finally:
            kernel.CloseHandle(handle)
    except (OSError, AttributeError, ValueError, TypeError):
        return PidProbe("unknown", None, False)


def probe_pid(pid):
    """PidProbe(state, start, measured): state is 'alive', 'gone' or 'unknown';
    `measured` is True only where this method was measured (Linux, Windows).
    Where a measured check cannot tell, it reads 'alive'."""
    if not isinstance(pid, int) or pid <= 0:
        return PidProbe("unknown", None, False)
    if sys.platform.startswith("linux"):
        return _linux_probe(pid)
    if os.name == "nt":
        return _windows_probe(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return PidProbe("gone", None, False)
    except OSError:
        return PidProbe("alive", None, False)
    return PidProbe("alive", None, False)


def process_start(pid):
    return probe_pid(pid).start if pid else None


def pid_namespace():
    """This process's PID namespace (`pid:[4026531836]`), or None where there
    is none to read: not Linux, or /proc not mounted."""
    if not sys.platform.startswith("linux"):
        return None
    try:
        return os.readlink("/proc/self/ns/pid")
    except OSError:
        return None


def holder_pidns(pid):
    """The PID namespace to record for a holder whose pid is `pid`: this
    process's, but only when `pid` is visible from it (probe_pid reads it
    alive). Inside bubblewrap's --unshare-pid a live CLAUDE_PID is invisible and
    reads gone, and bubblewrap reuses namespace ids, so a later sandbox would
    match a namespace recorded there and vouch for a `gone` that means nothing.
    None then, and every later `gone` for this holder cannot tell."""
    if probe_pid(pid).state != "alive":
        return None
    return pid_namespace()


def probe_holder(holder):
    """probe_pid for a recorded holder's pid. On Linux, `gone` stands only when
    this process is in the PID namespace the holder recorded at claim time
    (`holder.pidns`, recorded only when the pid was visible then -- see
    holder_pidns). From another namespace a live pid is simply invisible:
    Claude Code's sandbox runs each command under bubblewrap's --unshare-pid,
    where os.kill(pid, 0) raises ESRCH for a process that is running. A
    namespace that differs, or that either side cannot read, cannot tell:
    `unknown`, never gone -- presented, never adopted."""
    probe = probe_pid(holder.get("pid"))
    if probe.state == "gone" and sys.platform.startswith("linux"):
        here = pid_namespace()
        if here is None or here != holder.get("pidns"):
            return PidProbe("unknown", None, False)
    return probe


def current_holder(top):
    """This session's identity, or None when CLAUDE_CODE_SESSION_ID is absent
    (then who is asking cannot be told). Reads exactly CLAUDE_CODE_SESSION_ID,
    CLAUDE_CODE_BRIDGE_SESSION_ID and CLAUDE_PID."""
    session = os.environ.get("CLAUDE_CODE_SESSION_ID") or None
    if not session:
        return None
    pid = _env_pid()
    return {"session": session,
            "bridge_session": os.environ.get("CLAUDE_CODE_BRIDGE_SESSION_ID") or None,
            "pid": pid, "pid_start": process_start(pid), "pidns": holder_pidns(pid),
            "machine": machine(), "worktree": top}


def same_holder(a, b):
    """One holder is one session id in one process, on one machine and in one
    worktree: session, machine, worktree and pid all equal, and the pid's start
    time equal wherever both sides recorded one. The same session id from
    another process or worktree -- `claude --resume <id>` while the original
    still runs -- is ANOTHER holder: refused, never silently reclaimed."""
    if not (a and b):
        return False
    if (a["session"], a["machine"], a.get("pid")) != (b["session"], b["machine"], b.get("pid")):
        return False
    if a.get("bridge_session") != b.get("bridge_session"):
        return False
    if os.path.normcase(a["worktree"]) != os.path.normcase(b["worktree"]):
        return False
    return not (a.get("pid_start") and b.get("pid_start") and a["pid_start"] != b["pid_start"])


def owner_signal():
    """True when run from a terminal outside Claude Code. Spoofable."""
    return "CLAUDECODE" not in os.environ and "CLAUDE_CODE_SESSION_ID" not in os.environ


def child_env():
    return {k: v for k, v in os.environ.items() if k not in _SECRET_NAMES}


def _lock_fd(fd, wait):
    """Exclusive lock on an open fd; OSError when it cannot be had."""
    if os.name == "nt":
        import msvcrt  # pylint: disable=import-outside-toplevel,import-error
        msvcrt.locking(fd, msvcrt.LK_LOCK if wait else msvcrt.LK_NBLCK, 1)
    else:
        import fcntl  # pylint: disable=import-outside-toplevel
        fcntl.flock(fd, fcntl.LOCK_EX if wait else fcntl.LOCK_EX | fcntl.LOCK_NB)


def _open_private(path, flags):
    return os.open(path, flags | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)


@contextlib.contextmanager
def _locked(path):
    """Hold an exclusive lock on `path` (created 0600) for the block. Every
    worktree of a repo shares the identity file, so its read-modify-write runs
    under this lock or two worktrees lose each other's entries."""
    fd = _open_private(path, os.O_RDWR)
    try:
        _lock_fd(fd, wait=True)
        yield
    finally:
        if os.name == "nt":
            import msvcrt  # pylint: disable=import-outside-toplevel,import-error
            with contextlib.suppress(OSError):
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        os.close(fd)



def private_dir(prefix):
    """The private per-user directory `<tempdir>/<prefix>-<uid>`, created 0700.
    OSError when what is there is a symlink, not a directory, another user's,
    or open to group or others -- a shared temp directory is where a planted
    path would redirect a log. T-0030's `heartbeat_dir` check, with the prefix
    made a parameter (`crew-coord`, `crew-inflight`)."""
    uid = os.getuid() if hasattr(os, "getuid") else None
    base = os.path.join(tempfile.gettempdir(), prefix if uid is None else f"{prefix}-{uid}")
    try:
        os.mkdir(base, 0o700)
    except FileExistsError:
        pass
    info = os.lstat(base)
    if not stat.S_ISDIR(info.st_mode):
        raise OSError(f"{base} is not a directory")
    if uid is not None and (info.st_uid != uid or info.st_mode & 0o077):
        raise OSError(f"{base} is not private to this user")
    return base


def processes_in(path):
    """Which live processes have their working directory at or under `path`.

    ("live", [pids]) when one or more do, ("none", []) when none does, and
    ("unknown", reason) whenever that cannot be told: not Linux, CLAUDE_PID
    absent, CLAUDE_PID not visible from here (a PID namespace such as
    bubblewrap's --unshare-pid hides other processes too, so "none seen" would
    mean nothing), or /proc not listable. A process whose cwd cannot be read
    (another user's, or gone mid-scan) is skipped: the own-pid check above is
    what makes a scan that sees nothing trustworthy. A process whose cwd cannot
    be read for any other reason (another user's) makes a scan that found none
    unknown: that process may be the one in the worktree. One gone mid-scan is
    skipped."""
    if not sys.platform.startswith("linux"):
        return "unknown", f"process working directories are read on Linux only, not {sys.platform}"
    own = _env_pid()
    if own is None:
        return "unknown", "CLAUDE_PID is absent, so whether this process sees the others cannot be told"
    if probe_pid(own).state != "alive":
        return "unknown", (f"CLAUDE_PID {own} is not visible from here (a PID namespace?), so a scan "
                           "that sees no process proves nothing")
    target = os.path.realpath(path)
    prefix = target.rstrip(os.sep) + os.sep
    try:
        entries = os.listdir("/proc")
    except OSError as exc:
        return "unknown", f"/proc cannot be listed ({type(exc).__name__})"
    pids, unreadable = [], 0
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            cwd = os.readlink(f"/proc/{entry}/cwd")
        except (FileNotFoundError, ProcessLookupError):
            continue
        except OSError:
            unreadable += 1
            continue
        if cwd == target or cwd.startswith(prefix):
            pids.append(int(entry))
    if pids:
        return "live", sorted(pids)
    if unreadable:
        return "unknown", (f"{unreadable} process(es)' working directory cannot be read (another user's?), "
                           "so none seen proves nothing")
    return "none", []
