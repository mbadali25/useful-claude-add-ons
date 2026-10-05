"""In-flight markers (T-0049): one runner drives a ticket at a time.

    python3 crew_inflight.py claim   --root . --ticket <id> --runner <autopilot|lane|session>
    python3 crew_inflight.py release --root . --ticket <id>
    python3 crew_inflight.py holds   --root . --ticket <id> [--runner <r>] [--json]
    python3 crew_inflight.py clear   --root . --ticket <id> --by <who> --reason <text>
    python3 crew_inflight.py beat-loop --root <top> --ticket <id> --token <t>   (internal)

WHY. An `/crew:autopilot` session, a workflow lane and a person's session can
all drive one ticket, from one worktree or two. Nothing else in crew records
who is driving it right now, so two of them could double-drive it. This
module keeps that record and answers who holds it; `crew_autopilot.py next
--runner autopilot` reads the answer and stops (`in-flight`,
`handover-elsewhere`). It never notifies (T-0060 reads `holds()` for that) and
runs no timer: staleness is computed whenever a marker is read.

STATE. `<git-common-dir>/crew/inflight/`, shared by every worktree of one
clone (two CLONES share nothing; that case is out of scope):
  <ticket>.json        {"schema": 1, "ticket", "runner", "token", "session",
                        "pid", "pid_start", "pidns", "boot_id", "host",
                        "worktree", "branch", "since", "heartbeat_at"}
  <ticket>.json.lock   held for every rewrite and removal (crew_train's _Lock
                       shape: O_CREAT|O_EXCL, never removed for being old)
  events.jsonl         claim, release, clear
`claim` publishes a complete marker with `os.link`, which fails if one exists,
so two claimers cannot both win. Every rewrite is a temp file + `os.replace`.

HOLDER. `session` is `CLAUDE_CODE_SESSION_ID` when the environment has it.
`pid` is the long-lived process that holds the claim: `CLAUDE_PID` when it is
an ancestor of the claiming CLI that started before it (the chain is walked
with /proc, `ps`, or a Windows process snapshot; a hint that cannot be checked
is never trusted, since any environment - a project's settings included - can
set it), else the nearest ancestor named `claude` (`claude.exe`); with
neither, a Claude Code session (the session id is set) records no pid, and
anything else (a lane's script) records the CLI's parent, its own shell.
`pid_start` is that process's start time (Linux /proc, `ps -o lstart` on other
POSIX, the creation time on Windows); `pidns` and `boot_id` say which pid
space the number belongs to. `mine` needs the same worktree, host, session,
pid and pid start (and runner, when the reader names one): a session id alone
would let `claude --resume` take a working claim. Only where no pid could be
named on EITHER side (both None) does a non-empty session id decide alone.

STATES. `holds(root, ticket)` answers exactly one of STATES and writes nothing:
  unknown    anything that cannot be read, parsed, probed or trusted: the
             marker unreadable, not a regular file, not UTF-8, bad or
             duplicate-key JSON, a field of the wrong shape, an unknown schema
             or runner, a ticket that is not the file's, a heartbeat more than
             FUTURE_SKEW_SECONDS in the future, the lock held past its wait, the
             inflight path not a directory, git unable to name the common dir
             or the READER's own worktree (a reader outside git cannot tell
             mine from live)
  stale      heartbeat older than TTL_SECONDS, or the holder's pid measured
             gone (missing, a zombie, or reused: a different start time)
  mine       the reader is the holder
  elsewhere  a fresh holder in another worktree
  live       a fresh holder in this worktree that is not the reader
  free       no marker
in that order. The pid is probed only when host, boot_id and pidns all match
the reader's (an empty boot_id/pidns matches only an empty one: macOS,
Windows): /proc on Linux, `os.kill(pid, 0)` plus `ps -o stat=,lstart=` on
other POSIX, OpenProcess/GetExitCodeProcess/GetProcessTimes on Windows. A
probe that errors, or a pid that was never recorded, is unmeasured and the
heartbeat decides alone. Unmeasured is never gone.

NEVER CLEARED BY AGE. A stale or unknown marker is reported with the owner's
`clear` command (CLEAR_COMMAND); autopilot never runs it
(`crew_state.AUTONOMOUS_STOPS` `clear-inflight`). `clear` re-reads the state
under the lock and refuses anything but stale or unknown (unknown included:
a marker nothing can read is cleared only by the owner, never by age). Every
write logs its event to events.jsonl BEFORE the effect and refuses when the
log cannot be written; an effect that then fails takes its event back.

HEARTBEAT. `claim` starts one detached `beat-loop` keyed by the marker's
token. Every HEARTBEAT_SECONDS it rewrites `heartbeat_at`. Before taking the
lock it exits when the marker is gone, names another token (a refresh or a new
holder: an old loop never blocks a new one), cannot be read, or its holder pid
is measured gone, so a leftover lock never keeps a dead holder's loop alive.
A busy lock or a transient OSError (Windows refuses `os.replace` while a
reader has the file open) skips that beat. The loop also stops once its holder
has not been confirmed alive for more than TTL_SECONDS - an unmeasurable
holder, or beats that keep failing - so the marker then goes stale on its own:
the TTL decides whenever the pid cannot. The bound, where the holder cannot be
probed: the last beat lands at most TTL + one heartbeat after the last
confirmation (2400 s), and the marker reads stale a TTL after that, so a dead
holder reads stale within 2 x TTL + HEARTBEAT_SECONDS (4200 s, 70 minutes). Measured 2026-10-04 on Linux (Claude
Code 2.1.42, cloud container, no pid namespace): a child started this way
outlives the Bash tool call that started it, reparented to pid 1, beating for
2+ minutes across later calls. Not measured on Windows, macOS or a sandboxed
(bubblewrap) Linux session.

Exit codes: 0 done (and `holds` always, even for unknown), 2 bad arguments,
3 refused.
"""
import argparse
import datetime
import json
import os
import socket
import stat
import subprocess
import sys
import time
import uuid

if __name__ == "__main__":
    # Before the sibling import: the direct CLI writes no bytecode either.
    sys.dont_write_bytecode = True

import crew_ticket  # noqa: E402  pylint: disable=wrong-import-position
import crew_common  # noqa: E402  pylint: disable=wrong-import-position

SCHEMA = 1
TTL_SECONDS = 1800
HEARTBEAT_SECONDS = min(600, TTL_SECONDS // 3)
FUTURE_SKEW_SECONDS = 120
LOCK_WAIT_SECONDS = 5.0
MAX_MARKER_BYTES = 65536
STATES = ("free", "mine", "live", "stale", "elsewhere", "unknown")
RUNNERS = ("autopilot", "lane", "session")
HOLDER_NAMES = ("claude",)
CLEAR_COMMAND = ('python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_inflight.py" clear '
                 '--root . --ticket {ticket} --by <you> --reason "<why>"')
FIELDS = {"schema": (int,), "ticket": (str,), "runner": (str,), "token": (str,),
          "session": (str,), "pid": (int, type(None)), "pid_start": (int, type(None)),
          "pidns": (str,), "boot_id": (str,), "host": (str,), "worktree": (str,),
          "branch": (str,), "since": (str,), "heartbeat_at": (str,)}
EXIT_OK, EXIT_USAGE, EXIT_REFUSED = 0, 2, 3


class InflightError(Exception):
    """A write that could not be done; the message says why."""


class LockBusy(InflightError):
    """The per-ticket lock stayed held past its wait."""


class LogError(InflightError):
    """events.jsonl could not be written; the message names the recovery."""


# --- small helpers --------------------------------------------------------------------

def clean(value, limit=200):
    """One line, no control or separator characters (U+2028 included):
    whatever a peer wrote can never print a second line."""
    text = "".join(ch if ch.isprintable() else " " for ch in str(value))
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 3] + "..."


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(when):
    return when.isoformat(timespec="seconds")


def _parse_time(text):
    try:
        when = datetime.datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    return when if when.tzinfo is not None else None


def clear_command(ticket):
    return CLEAR_COMMAND.replace("{ticket}", ticket)


def inflight_dir(root):
    """`<git-common-dir>/crew/inflight`, or None when git cannot name it."""
    state = crew_ticket.state_dir(root)
    return os.path.join(state, "inflight") if state else None


def _marker_path(folder, ticket):
    return os.path.join(folder, crew_ticket.check_ticket(ticket) + ".json")


# --- identity and the pid probe ---------------------------------------------------------

def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def _platform():
    """`linux` (a /proc to read), `nt`, or `posix` (macOS, BSD: no /proc)."""
    if os.name == "nt":
        return "nt"
    return "linux" if os.path.isdir("/proc/self") else "posix"


def _proc_stat(pid):
    """(state, ppid, start, name) from /proc/<pid>/stat. Raises
    FileNotFoundError when the pid has no entry, OSError/ValueError when it
    cannot be read."""
    with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as handle:
        raw = handle.read()
    name = raw[raw.index("(") + 1:raw.rindex(")")]
    rest = raw[raw.rindex(")") + 1:].split()
    return rest[0], int(rest[1]), int(rest[19]), name


def _posix_process(pid):
    """(status, start, ppid, name) without /proc: `os.kill(pid, 0)` says
    whether the pid exists, `ps` its state, parent, start and name. Raises
    OSError when it cannot tell."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return "missing", None, None, ""
    except PermissionError:
        pass  # it exists; another user owns it
    # require_tool: a ps that does not resolve raises ToolNotFound, an OSError,
    # which is this function's "cannot tell" (L-1508: never a bare name).
    done = subprocess.run([crew_common.require_tool("ps"), "-o", "stat=,ppid=,lstart=,comm=",
                           "-p", str(pid)],
                          capture_output=True, text=True, check=False, timeout=10,
                          stdin=subprocess.DEVNULL, env=dict(os.environ, LC_ALL="C", LANG="C"))
    parts = done.stdout.split()
    if done.returncode != 0 or len(parts) < 7:
        raise OSError(f"ps could not read pid {pid}")
    start = int(time.mktime(time.strptime(" ".join(parts[2:7]), "%a %b %d %H:%M:%S %Y")))
    name = os.path.basename(" ".join(parts[7:]))
    return ("zombie" if parts[0].startswith("Z") else "running"), start, int(parts[1]), name


def _win_process(pid):  # pragma: no cover - exercised on Windows only
    """(status, start) from OpenProcess, GetExitCodeProcess (259 STILL_ACTIVE)
    and GetProcessTimes' creation time, in seconds. Raises OSError when it
    cannot tell; a pid with no process (ERROR_INVALID_PARAMETER) is missing."""
    import ctypes  # pylint: disable=import-outside-toplevel
    from ctypes import wintypes  # pylint: disable=import-outside-toplevel
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        error = ctypes.get_last_error()
        if error == 87:
            return "missing", None
        raise OSError(error, f"OpenProcess({pid}) failed")
    try:
        code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
            raise OSError(ctypes.get_last_error(), "GetExitCodeProcess failed")
        if code.value != 259:
            return "missing", None
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            return "running", None
        created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        return "running", created // 10_000_000
    finally:
        kernel.CloseHandle(handle)


def _process(pid):
    """(status, start, ppid, name): status `running`, `zombie` or `missing`.
    Raises (OSError, ValueError, IndexError, SubprocessError) when it cannot tell."""
    where = _platform()
    if where == "nt":
        status, start = _win_process(pid)
        return status, start, None, ""
    if where == "posix":
        return _posix_process(pid)
    try:
        state, ppid, start, name = _proc_stat(pid)
    except FileNotFoundError:
        return "missing", None, None, ""
    return ("zombie" if state == "Z" else "running"), start, ppid, name


_PROBE_ERRORS = (OSError, ValueError, OverflowError, IndexError, subprocess.SubprocessError)
MAX_PID = 2 ** 32


def _win_ancestors():  # pragma: no cover - exercised on Windows only
    """[(pid, exe name)] from this process's parent upward, read from one
    CreateToolhelp32Snapshot (PROCESSENTRY32W.th32ParentProcessID), or None
    when the snapshot cannot be taken or read."""
    import ctypes  # pylint: disable=import-outside-toplevel
    from ctypes import wintypes  # pylint: disable=import-outside-toplevel

    class Entry(ctypes.Structure):  # PROCESSENTRY32W
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]
    try:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        # Every argument typed: an untyped HANDLE is passed as a C int, which
        # truncates a 64-bit handle value (review NIT carry).
        kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
        for walk in (kernel.Process32FirstW, kernel.Process32NextW):
            walk.restype = wintypes.BOOL
            walk.argtypes = (wintypes.HANDLE, ctypes.POINTER(Entry))
        kernel.CloseHandle.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        snap = kernel.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
        if not snap or snap == wintypes.HANDLE(-1).value:
            return None
        parents = {}
        try:
            entry = Entry(dwSize=ctypes.sizeof(Entry))
            ok = kernel.Process32FirstW(snap, ctypes.byref(entry))
            while ok:
                parents[entry.th32ProcessID] = (entry.th32ParentProcessID, entry.szExeFile)
                ok = kernel.Process32NextW(snap, ctypes.byref(entry))
        finally:
            kernel.CloseHandle(snap)
    except (OSError, AttributeError, ValueError):
        return None
    return walk_parents(parents, _pid_start, os.getppid(), os.getpid()) or None


def walk_parents(parents, starts, first, me):
    """[(pid, name)] from `first` upward through `parents` ({pid: (ppid,
    name)}, a Toolhelp snapshot), asking `starts(pid)` for creation times.
    th32ParentProcessID is the pid the parent HAD: once it exits, that pid
    can be reused by a later process, which then reads as the parent. A real
    parent started no later than its child, so the walk stops at a link whose
    process started after the one below it, or whose start (or `me`'s) cannot
    be read - could not tell is not "same process" (review NIT carry). Pure:
    no OS call but through `starts`."""
    chain, pid, below = [], first, starts(me)
    for _ in range(64):
        if pid not in parents or pid in (p for p, _ in chain):
            break
        start = starts(pid)
        if start is None or below is None or start > below:
            break
        ppid, name = parents[pid]
        chain.append((pid, name))
        pid, below = ppid, start
    return chain


def _name(raw):
    """A process name as HOLDER_NAMES compares it: no path, no `.exe`, lower case."""
    base = os.path.basename(str(raw)).lower()
    return base[:-4] if base.endswith(".exe") else base


def _ancestors():
    """[(pid, name)] from this process's parent upward, or None where the
    chain cannot be walked (a failed probe or snapshot)."""
    if _platform() == "nt":
        return _win_ancestors()
    chain, pid = [], os.getppid()
    for _ in range(64):
        if pid <= 1:
            break
        try:
            status, _, ppid, name = _process(pid)
        except _PROBE_ERRORS:
            return chain or None
        if status != "running" or ppid is None:
            break
        chain.append((pid, name))
        pid = ppid
    return chain


def _born_before_me(pid):
    """True when `pid` started no later than this process: a reused pid in
    an ancestor slot started after it. Could-not-tell is False."""
    theirs, mine = _pid_start(pid), _pid_start(os.getpid())
    return theirs is not None and mine is not None and theirs <= mine


def _holder_pid():
    """The long-lived process the claim belongs to, or None (see HOLDER).
    `CLAUDE_PID` is a hint any environment can set (a project's settings
    included), so it counts only when it is an ancestor of this process and
    started before it; when the chain cannot be walked it is never trusted."""
    try:
        hinted = int(os.environ.get("CLAUDE_PID", ""))
    except ValueError:
        hinted = None
    hinted = hinted if hinted and 1 < hinted < MAX_PID else None
    for pid, name in _ancestors() or []:
        if (pid == hinted or _name(name) in HOLDER_NAMES) and _born_before_me(pid):
            return pid
    if os.environ.get("CLAUDE_CODE_SESSION_ID"):
        return None
    return os.getppid()


def _pid_start(pid):
    if pid is None:
        return None
    try:
        return _process(pid)[1]
    except _PROBE_ERRORS:
        return None


def _git(root, *args):
    try:
        done = subprocess.run([crew_common.require_tool("git"), "-C", root, *args],
                              capture_output=True, text=True,
                              check=False, timeout=30, stdin=subprocess.DEVNULL,
                              env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"))
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def machine():
    """What says which pid space a pid number belongs to (empty where the OS
    has no such notion)."""
    try:
        pidns = os.readlink("/proc/self/ns/pid")
    except OSError:
        pidns = ""
    return {"host": socket.gethostname(), "boot_id": _read("/proc/sys/kernel/random/boot_id"),
            "pidns": pidns}


def identity(root, session=None):
    """The reader's (or claimer's) holder fields. `worktree` is None when git
    cannot name the top level."""
    pid = _holder_pid()
    me = dict(machine(), session=os.environ.get("CLAUDE_CODE_SESSION_ID", "")
              if session is None else session, pid=pid, pid_start=_pid_start(pid))
    me["worktree"] = crew_ticket.toplevel(root)
    return me


def probe(marker, me):
    """`alive`, `gone` or `unmeasured`. `gone` only when host, boot_id and
    pidns all equal the reader's and the pid is missing, a zombie, or started
    at another time (reused). Any error is `unmeasured`."""
    if not marker.get("host") or any(marker.get(k) != me.get(k)
                                     for k in ("host", "boot_id", "pidns")):
        return "unmeasured"
    pid = marker.get("pid")
    if pid is None or pid <= 0:
        return "unmeasured"
    try:
        status, start = _process(pid)[:2]
    except _PROBE_ERRORS:
        return "unmeasured"
    if status != "running":
        return "gone"
    if marker.get("pid_start") is not None and start is not None \
            and start != marker["pid_start"]:
        return "gone"
    return "alive"


# --- the read path ------------------------------------------------------------------------

def _no_duplicates(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate key {key!r}")
        seen[key] = value
    return seen


def _bad_constant(name):
    raise ValueError(f"non-JSON constant {name}")


def load_marker(path, ticket):
    """(marker, why): the marker dict, or None with why it is unknown. The
    entry is lstat'ed first, so a symlink, directory or FIFO is never opened."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return None, ""
    except OSError as exc:
        return None, f"marker cannot be examined: {exc}"
    if not stat.S_ISREG(info.st_mode):
        return None, "marker is not a regular file"
    if info.st_size > MAX_MARKER_BYTES:
        return None, f"marker is over {MAX_MARKER_BYTES} bytes"
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
        try:
            data = os.read(fd, MAX_MARKER_BYTES + 1)
        finally:
            os.close(fd)
    except OSError as exc:
        return None, f"marker unreadable: {exc}"
    try:
        marker = json.loads(data.decode("utf-8"), object_pairs_hook=_no_duplicates,
                            parse_constant=_bad_constant)
    except UnicodeDecodeError:
        return None, "marker is not UTF-8"
    except ValueError as exc:
        return None, f"marker is not valid JSON: {exc}"
    return _shape(marker, ticket)


def _shape(marker, ticket):
    if not isinstance(marker, dict):
        return None, "marker is not a JSON object"
    for key, kinds in FIELDS.items():
        if key not in marker:
            return None, f"marker lacks {key}"
        # bool is an int to isinstance; it is no pid.
        if isinstance(marker[key], bool) or not isinstance(marker[key], kinds):
            return None, f"marker field {key} has the wrong type"
    if marker["schema"] != SCHEMA:
        return None, f"marker schema {marker['schema']} is not {SCHEMA}"
    if marker["runner"] not in RUNNERS:
        return None, "marker names an unknown runner"
    if marker["ticket"] != ticket:
        return None, "marker names another ticket than its file"
    if not marker["token"] or not marker["worktree"]:
        return None, "marker has an empty token or worktree"
    if marker["pid"] is not None and not 0 < marker["pid"] < MAX_PID:
        return None, "marker pid is out of range"
    if marker["pid_start"] is not None and not 0 <= marker["pid_start"] < 2 ** 63:
        return None, "marker pid_start is out of range"
    for key in ("since", "heartbeat_at"):
        if _parse_time(marker[key]) is None:
            return None, f"marker field {key} is not an ISO 8601 time with a zone"
    return marker, ""


def _wait_unlocked(lock, wait):
    """True once `lock` is absent, False if it is still there after `wait`
    seconds. Only looks: the reader takes no lock."""
    deadline = time.monotonic() + wait
    while os.path.lexists(lock):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.02)
    return True


def _answer(state, ticket, why="", marker=None):
    marker = marker or {}
    return {"state": state, "ticket": ticket, "runner": clean(marker.get("runner", "")),
            "since": clean(marker.get("since", "")),
            "heartbeat_at": clean(marker.get("heartbeat_at", "")),
            "worktree": clean(marker.get("worktree", "")), "why": clean(why),
            "clear": clear_command(ticket) if state in ("stale", "unknown") else ""}


def holds(root, ticket, runner=None, session=None, wait=None):
    """Who holds `ticket`: a dict whose `state` is always one of STATES.
    Raises only for an invalid ticket id; every other failure is `unknown`
    with `why`. Writes nothing and creates no directory."""
    crew_ticket.check_ticket(ticket)
    try:
        return _assess(root, ticket, runner, session,
                       LOCK_WAIT_SECONDS if wait is None else wait)[0]
    except Exception as exc:  # pylint: disable=broad-except
        return _answer("unknown", ticket, f"could not tell: {exc!r}")


def next_stop(root, ticket, runner):
    """`crew_autopilot.py next --runner`'s stop (T-0049): None when `holds`
    says the ticket is free or `runner`'s, else `{phase, command, reason}`:
    `elsewhere` is `handover-elsewhere`; `live`, `stale`, `unknown` and any
    other state are `in-flight`, with the owner's clear command as the
    command when `holds` names one. A raise propagates: the caller stops."""
    answer = holds(root, ticket, runner=runner)
    state = answer["state"]
    if state in ("free", "mine"):
        return None
    who = (f"{answer.get('runner') or 'a runner'} holds {ticket} since "
           f"{answer.get('since') or '?'} in {answer.get('worktree') or '?'}")
    if state == "elsewhere":
        return {"phase": "handover-elsewhere", "command": "", "reason": (
            f"handover-elsewhere: {who} - drive it from {answer.get('worktree') or '?'}")}
    clear = answer.get("clear") or ""
    reason = f"in-flight: {state} - {who}"
    reason += f": {answer['why']}" if answer.get("why") else ""
    reason += f" - the owner clears it: {clear}" if clear else ""
    return {"phase": "in-flight", "command": clear, "reason": reason}


def _assess(root, ticket, runner, session, wait):
    """(answer, marker, path). `wait` None means the caller holds the lock."""
    folder = inflight_dir(root)
    if folder is None:
        return _answer("unknown", ticket, "git cannot name <git-common-dir>"), None, None
    path = _marker_path(folder, ticket)
    try:
        info = os.lstat(folder)
    except FileNotFoundError:
        return _answer("free", ticket), None, path
    except OSError as exc:
        return _answer("unknown", ticket, f"inflight directory: {exc}"), None, path
    if not stat.S_ISDIR(info.st_mode):
        return _answer("unknown", ticket, f"{folder} is not a directory"), None, path
    if wait is not None and not _wait_unlocked(path + ".lock", wait):
        return _answer("unknown", ticket, f"lock {path}.lock held for over {wait:g}s; if no "
                       "crew_inflight.py is running, a process died holding it"), None, path
    marker, why = load_marker(path, ticket)
    if marker is None:
        return _answer("unknown" if why else "free", ticket, why), None, path
    return _judge(root, ticket, marker, runner, session), marker, path


def _judge(root, ticket, marker, runner, session):
    me = identity(root, session)
    if me["worktree"] is None:
        return _answer("unknown", ticket, "git cannot name this worktree", marker)
    beat = _parse_time(marker["heartbeat_at"])
    age = (_now() - beat).total_seconds()
    if age < -FUTURE_SKEW_SECONDS:
        return _answer("unknown", ticket, f"heartbeat in the future by {-age:.0f}s", marker)
    if age > TTL_SECONDS:
        return _answer("stale", ticket, f"no heartbeat for {age:.0f}s (TTL {TTL_SECONDS}s)",
                       marker)
    if probe(marker, me) == "gone":
        return _answer("stale", ticket, f"holder pid {marker['pid']} is gone", marker)
    if _is_mine(marker, me, runner):
        return _answer("mine", ticket, "", marker)
    if os.path.normcase(marker["worktree"]) != os.path.normcase(me["worktree"]):
        return _answer("elsewhere", ticket, f"held from {marker['worktree']}", marker)
    return _answer("live", ticket, f"{marker['runner']} holds it in this worktree", marker)


def _is_mine(marker, me, runner):
    if runner is not None and marker["runner"] != runner:
        return False
    if os.path.normcase(marker["worktree"]) != os.path.normcase(me["worktree"]):
        return False
    if marker["host"] != me["host"] or marker["session"] != me["session"]:
        return False
    if marker["pid"] is None and me["pid"] is None:
        # Neither side could name a long-lived process: the session decides.
        return bool(me["session"])
    if marker["pid"] is None or marker["pid"] != me["pid"]:
        return False
    return marker["pid_start"] == me["pid_start"]


def survey(root):
    """Every marker's answer, for `/crew:status`: {"state": "ok"|"unknown",
    "why", "entries"}. Reads only."""
    folder = inflight_dir(root)
    if folder is None:
        return {"state": "unknown", "why": "git cannot name <git-common-dir>", "entries": []}
    try:
        names = sorted(os.listdir(folder))
    except FileNotFoundError:
        return {"state": "ok", "why": "", "entries": []}
    except OSError as exc:
        return {"state": "unknown", "why": clean(f"inflight directory: {exc}"), "entries": []}
    entries = []
    for name in names:
        ticket = name[:-5] if name.endswith(".json") else ""
        try:
            crew_ticket.check_ticket(ticket)
        except crew_ticket.TicketError:
            continue
        entries.append(holds(root, ticket))
    return {"state": "ok", "why": "", "entries": entries}


# --- the write path ----------------------------------------------------------------------

class _Lock:
    """O_CREAT|O_EXCL lock beside the marker (crew_train._Lock's shape): pid and
    a uuid inside, waits LOCK_WAIT_SECONDS then refuses naming the path. Never
    removed for being old; removed only while it holds this token."""

    def __init__(self, path, wait=None):
        self.path = path + ".lock"
        self.wait = LOCK_WAIT_SECONDS if wait is None else wait
        self.token = f"{os.getpid()} {uuid.uuid4().hex}"

    def __enter__(self):
        deadline = time.monotonic() + self.wait
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError as exc:
                if time.monotonic() > deadline:
                    raise LockBusy(
                        f"lock {self.path} held for over {self.wait:g}s; if no "
                        "crew_inflight.py is running, a process died holding it -- remove "
                        "that file by hand") from exc
                time.sleep(0.02)
                continue
            except OSError as exc:
                raise InflightError(f"lock {self.path}: {exc}") from exc
            try:
                os.write(fd, self.token.encode())
            finally:
                os.close(fd)
            return self

    def __exit__(self, *exc):
        try:
            with open(self.path, encoding="utf-8") as handle:
                mine = handle.read() == self.token
            if mine:
                os.remove(self.path)
        except OSError:
            pass


def _temp_for(path):
    return f"{path}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"


def _write_temp(path, marker):
    """A complete temp file beside `path`, its name returned. The payload is
    serialised before any file is opened (CLAUDE.md, Landmines)."""
    text = json.dumps(marker, indent=1, sort_keys=True) + "\n"
    tmp = _temp_for(path)
    with open(tmp, "x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    return tmp


def _replace(path, marker):
    tmp = _write_temp(path, marker)
    try:
        os.replace(tmp, path)
    finally:
        if os.path.lexists(tmp):
            os.remove(tmp)


def _log(folder, kind, ticket, **fields):
    """Append one event; returns what `_unlog` needs to take it back. Raises
    OSError when it cannot be written (nothing is then half-written)."""
    line = (json.dumps(dict({"at": _iso(_now()), "kind": kind, "ticket": ticket}, **fields),
                       sort_keys=True) + "\n").encode("utf-8")
    path = os.path.join(folder, "events.jsonl")
    created = not os.path.lexists(path)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0),
                     0o644)
        try:
            size = os.fstat(fd).st_size
            if os.write(fd, line) != len(line):
                os.ftruncate(fd, size)
                raise OSError(f"short write to {path}")
        finally:
            os.close(fd)
    except OSError as exc:
        raise LogError(f"{path} could not be written ({exc}); nothing was changed - fix it, or "
                       "move it aside, by hand, then retry") from exc
    return {"path": path, "size": size, "end": size + len(line), "created": created,
            "kind": kind, "ticket": ticket}


def _unlog(entry):
    """Take back an event whose effect failed: truncate it away while it is
    still the last line, else append an `undone` record. Best effort."""
    try:
        if os.path.getsize(entry["path"]) == entry["end"]:
            if entry["created"]:
                os.remove(entry["path"])
            else:
                os.truncate(entry["path"], entry["size"])
            return
        _log(os.path.dirname(entry["path"]), "undone", entry["ticket"], of=entry["kind"])
    except (OSError, LogError):
        pass


def _ensure_dir(folder):
    os.makedirs(folder, exist_ok=True)
    info = os.lstat(folder)
    if not stat.S_ISDIR(info.st_mode):
        raise InflightError(f"{folder} is not a directory")


def _new_marker(root, ticket, runner, me, since=None):
    now = _iso(_now())
    return {"schema": SCHEMA, "ticket": ticket, "runner": runner,
            "token": uuid.uuid4().hex, "session": me["session"], "pid": me["pid"],
            "pid_start": me["pid_start"], "pidns": me["pidns"], "boot_id": me["boot_id"],
            "host": me["host"], "worktree": me["worktree"],
            "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD") or "",
            "since": since or now, "heartbeat_at": now}


def spawn_beat(root, ticket, token):
    """Start the detached heartbeat; its pid, or None when it could not start."""
    args = [sys.executable, "-B", os.path.abspath(__file__), "beat-loop", "--root", root,
            "--ticket", ticket, "--token", token]
    kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
              "stderr": subprocess.DEVNULL, "close_fds": True, "cwd": root}
    if os.name == "nt":
        kwargs["creationflags"] = (getattr(subprocess, "DETACHED_PROCESS", 0)
                                   | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    else:
        kwargs["start_new_session"] = True
    try:
        return subprocess.Popen(args, **kwargs).pid  # pylint: disable=consider-using-with
    except OSError:
        return None


def _refusal(answer):
    text = f"refused: {answer['state']}"
    if answer["runner"]:
        text += f" {answer['runner']} since {answer['since']} in {answer['worktree']}"
    if answer["why"]:
        text += f" - {answer['why']}"
    if answer["clear"]:
        text += f" - the owner clears it: {answer['clear']}"
    return text


def claim(root, ticket, runner, session=None, spawn=spawn_beat):
    """(exit code, line). Claims when `holds` is free, refreshes when mine
    (new token, so the old heartbeat exits), refuses otherwise. Under the
    lock: re-read, log the event, then publish; no log, no claim."""
    if runner not in RUNNERS:
        return EXIT_USAGE, f"refused: runner must be one of {', '.join(RUNNERS)}"
    top = crew_ticket.toplevel(root)
    folder = inflight_dir(root)
    if top is None or folder is None:
        return EXIT_REFUSED, "refused: unknown - git cannot name this worktree or its common dir"
    answer = holds(root, ticket, runner=runner, session=session)
    if answer["state"] not in ("free", "mine"):
        return EXIT_REFUSED, _refusal(answer)
    me = identity(root, session)
    path = _marker_path(folder, ticket)
    try:
        _ensure_dir(folder)
        with _Lock(path):
            current, marker_now, _ = _assess(root, ticket, runner, session, None)
            if current["state"] not in ("free", "mine"):
                return EXIT_REFUSED, _refusal(current)
            word = "claimed" if current["state"] == "free" else "refreshed"
            marker = _new_marker(top, ticket, runner, me,
                                 since=marker_now["since"] if marker_now else None)
            entry = _log(folder, "claim", ticket, runner=runner, worktree=top,
                         session=me["session"], pid=me["pid"], refreshed=word == "refreshed")
            try:
                _publish(path, marker, word == "claimed")
            except OSError:
                _unlog(entry)
                raise
    except (InflightError, OSError) as exc:
        return EXIT_REFUSED, clean(f"refused: unknown - {exc}; nothing claimed", 600)
    beat = spawn(top, ticket, marker["token"])
    tail = f"heartbeat pid {beat}" if beat else "heartbeat did not start; the TTL decides"
    return EXIT_OK, f"{word} {ticket} as {runner} ({tail})"


def _publish(path, marker, new):
    """A new marker by `os.link` (fails if one exists), a refresh by replace."""
    if not new:
        _replace(path, marker)
        return
    tmp = _write_temp(path, marker)
    try:
        os.link(tmp, path)
    finally:
        os.remove(tmp)


def _remove_logged(folder, path, kind, ticket, **fields):
    entry = _log(folder, kind, ticket, **fields)
    try:
        os.remove(path)
    except OSError:
        _unlog(entry)
        raise


def release(root, ticket, runner=None, session=None):
    """(exit code, line): only the holder releases; nothing held is a no-op."""
    folder = inflight_dir(root)
    if folder is None:
        return EXIT_REFUSED, "refused: unknown - git cannot name <git-common-dir>"
    answer = holds(root, ticket, runner=runner, session=session)
    if answer["state"] == "free":
        return EXIT_OK, f"released: {ticket} was not held"
    if answer["state"] != "mine":
        return EXIT_REFUSED, _refusal(answer)
    path = _marker_path(folder, ticket)
    try:
        with _Lock(path):
            current, marker, _ = _assess(root, ticket, runner, session, None)
            if current["state"] != "mine":
                return EXIT_REFUSED, _refusal(current)
            _remove_logged(folder, path, "release", ticket, runner=marker["runner"],
                           token=marker["token"])
    except (InflightError, OSError) as exc:
        return EXIT_REFUSED, clean(f"refused: unknown - {exc}; nothing released", 600)
    return EXIT_OK, f"released {ticket}"


def clear(root, ticket, by, reason):
    """(exit code, line): the owner's removal of a stale or unknown marker,
    re-read under the lock, logged with who and why before it is removed."""
    if not clean(by) or not clean(reason):
        return EXIT_USAGE, "refused: clear needs --by <who> and --reason <text>"
    folder = inflight_dir(root)
    if folder is None:
        return EXIT_REFUSED, "refused: unknown - git cannot name <git-common-dir>"
    try:
        info = os.lstat(folder)
    except FileNotFoundError:
        return EXIT_REFUSED, "refused: free - nothing to clear"
    except OSError as exc:
        return EXIT_REFUSED, clean(f"refused: unknown - {exc}")
    if not stat.S_ISDIR(info.st_mode):
        return EXIT_REFUSED, f"refused: {folder} is not a directory - fix it by hand"
    path = _marker_path(folder, ticket)
    try:
        with _Lock(path):
            current, marker, _ = _assess(root, ticket, None, None, None)
            if current["state"] not in ("stale", "unknown"):
                return EXIT_REFUSED, (f"refused: {current['state']} - clear removes only a "
                                      "stale or unknown marker")
            if os.path.isdir(path) and not os.path.islink(path):
                return EXIT_REFUSED, f"refused: {path} is a directory - remove it by hand"
            _remove_logged(folder, path, "clear", ticket, by=clean(by),
                           reason=clean(reason, 500), state=current["state"],
                           why=current["why"], runner=clean((marker or {}).get("runner", "")))
    except (InflightError, OSError) as exc:
        return EXIT_REFUSED, clean(f"refused: unknown - {exc}; nothing cleared", 600)
    return EXIT_OK, f"cleared {ticket} ({current['state']}) by {clean(by)}"


# --- the heartbeat -----------------------------------------------------------------------

def _beat_check(path, ticket, token):
    """(marker, probe, exit_reason): read without the lock."""
    if not os.path.lexists(path):
        return None, "", "exit: marker gone"
    marker, why = load_marker(path, ticket)
    if marker is None:
        return None, "", f"exit: {why or 'marker gone'}"
    if marker["token"] != token:
        return None, "", "exit: superseded by another token"
    seen = probe(marker, machine())
    if seen == "gone":
        return None, "", "exit: holder pid gone"
    return marker, seen, ""


def beat_once(root, ticket, token):
    """`beat` (holder confirmed alive), `beat (holder unconfirmed)`,
    `skipped` (a busy lock or a transient OSError) or why the loop exits.
    Marker, token and holder are checked BEFORE the lock, so a leftover lock
    never keeps a dead holder's loop alive, and again under it."""
    folder = inflight_dir(root)
    if folder is None:
        return "exit: git cannot name <git-common-dir>"
    path = _marker_path(folder, ticket)
    _, seen, stop = _beat_check(path, ticket, token)
    if stop:
        return stop
    try:
        with _Lock(path, wait=1.0):
            marker, seen, stop = _beat_check(path, ticket, token)
            if stop:
                return stop
            _replace(path, dict(marker, heartbeat_at=_iso(_now())))
    except (InflightError, OSError):
        return "skipped"
    return "beat" if seen == "alive" else "beat (holder unconfirmed)"


def beat_loop(root, ticket, token, sleep=time.sleep, clock=time.monotonic):
    """Beat until beat_once says exit, or until the holder has gone more than
    TTL_SECONDS without being confirmed alive by a successful beat. Returns why."""
    confirmed = clock()
    while True:
        sleep(HEARTBEAT_SECONDS)
        try:
            result = beat_once(root, ticket, token)
        except Exception as exc:  # pylint: disable=broad-except
            return f"exit: {exc!r}"
        if result.startswith("exit"):
            return result
        if result == "beat":
            confirmed = clock()
        elif clock() - confirmed > TTL_SECONDS:
            return (f"exit: holder unconfirmed for over {TTL_SECONDS}s "
                    f"(last: {result}); the TTL decides")


# --- CLI ---------------------------------------------------------------------------------

def _line(answer):
    return " ".join(f"{key}={answer[key]}" for key in
                    ("state", "runner", "since", "worktree", "why", "clear"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("claim", "release", "holds", "clear", "beat-loop"):
        action = sub.add_parser(name)
        action.add_argument("--root", default=".")
        action.add_argument("--ticket", required=True)
    sub.choices["claim"].add_argument("--runner", required=True)
    sub.choices["holds"].add_argument("--runner", default=None)
    sub.choices["holds"].add_argument("--json", action="store_true")
    sub.choices["clear"].add_argument("--by", required=True)
    sub.choices["clear"].add_argument("--reason", required=True)
    sub.choices["beat-loop"].add_argument("--token", required=True)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return EXIT_OK if exc.code == 0 else EXIT_USAGE
    values = [v for v in vars(args).values() if isinstance(v, str)]
    if any(not v.isprintable() for v in values):
        sys.stderr.write("refused: an argument holds a control character\n")
        return EXIT_USAGE
    try:
        crew_ticket.check_ticket(args.ticket)
    except crew_ticket.TicketError as exc:
        sys.stderr.write(f"refused: {exc}\n")
        return EXIT_USAGE
    if args.action == "beat-loop":
        beat_loop(args.root, args.ticket, args.token)
        return EXIT_OK
    if args.action == "holds":
        if args.runner is not None and args.runner not in RUNNERS:
            sys.stderr.write(f"refused: runner must be one of {', '.join(RUNNERS)}\n")
            return EXIT_USAGE
        answer = holds(args.root, args.ticket, runner=args.runner)
        sys.stdout.write((json.dumps(answer) if args.json else _line(answer)) + "\n")
        return EXIT_OK
    try:
        if args.action == "claim":
            code, text = claim(args.root, args.ticket, args.runner)
        elif args.action == "release":
            code, text = release(args.root, args.ticket)
        else:
            code, text = clear(args.root, args.ticket, args.by, args.reason)
    except (InflightError, OSError) as exc:
        code, text = EXIT_REFUSED, clean(f"refused: unknown - {exc}")
    sys.stdout.write(text + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
