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

HOLDER. `session` is `CLAUDE_CODE_SESSION_ID` when the environment has it;
`pid` is the long-lived process that holds the claim: the nearest ancestor
whose name is `claude` or `node` (or `CLAUDE_PID`), else the claiming CLI's
parent (a lane's own shell); `pid_start` is its start time, `pidns` and
`boot_id` say which pid space the number belongs to. `mine` needs the same
worktree, host, session, pid and pid start (and runner, when the reader names
one): a session id alone would let `claude --resume` take a working claim.

STATES. `holds(root, ticket)` answers exactly one of STATES and writes nothing:
  unknown    anything that cannot be read, parsed, probed or trusted: the
             marker unreadable, not a regular file, not UTF-8, bad or
             duplicate-key JSON, a field of the wrong shape, an unknown schema
             or runner, a ticket that is not the file's, a heartbeat more than
             FUTURE_SKEW_SECONDS in the future, the lock held past its wait, the
             inflight path not a directory, git unable to name the common dir
  stale      heartbeat older than TTL_SECONDS, or the holder's pid measured
             gone (missing, a zombie, or reused: a different start time)
  mine       the reader is the holder
  elsewhere  a fresh holder in another worktree
  live       a fresh holder in this worktree that is not the reader
  free       no marker
in that order. The pid is probed only when host, boot_id and pidns all match
the reader's (Linux /proc); otherwise, or when the probe errors, it is
unmeasured and the heartbeat decides alone. Unmeasured is never gone.

NEVER CLEARED BY AGE. A stale or unknown marker is reported with the owner's
`clear` command (CLEAR_COMMAND); autopilot never runs it
(`crew_state.AUTONOMOUS_STOPS` `clear-inflight`). `clear` re-reads the state
under the lock, refuses anything but stale or unknown, and logs who and why.

HEARTBEAT. `claim` starts one detached `beat-loop` keyed by the marker's
token. Every HEARTBEAT_SECONDS it rewrites `heartbeat_at`; it exits when the
marker is gone, names another token (a refresh or a new holder: an old loop
never blocks a new one), cannot be read, or its holder pid is measured gone.
Measured 2026-10-04 on Linux (Claude Code 2.1.42, cloud container, no pid
namespace): a child started this way outlives the Bash tool call that started
it, reparented to pid 1, beating for 2+ minutes across later calls.

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

SCHEMA = 1
TTL_SECONDS = 1800
HEARTBEAT_SECONDS = min(600, TTL_SECONDS // 3)
FUTURE_SKEW_SECONDS = 120
LOCK_WAIT_SECONDS = 5.0
MAX_MARKER_BYTES = 65536
STATES = ("free", "mine", "live", "stale", "elsewhere", "unknown")
RUNNERS = ("autopilot", "lane", "session")
HOLDER_NAMES = ("claude", "node")
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


def _proc_stat(pid):
    """(state, ppid, start, name) from /proc/<pid>/stat. Raises
    FileNotFoundError when the pid has no entry, OSError/ValueError when it
    cannot be read."""
    with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as handle:
        raw = handle.read()
    name = raw[raw.index("(") + 1:raw.rindex(")")]
    rest = raw[raw.rindex(")") + 1:].split()
    return rest[0], int(rest[1]), int(rest[19]), name


def _holder_pid():
    """The long-lived process the claim belongs to: the nearest ancestor named
    `claude`/`node` or equal to CLAUDE_PID, else this process's parent."""
    parent = os.getppid()
    try:
        hinted = int(os.environ.get("CLAUDE_PID", ""))
    except ValueError:
        hinted = None
    if not os.path.isdir("/proc/self"):
        return hinted or parent
    pid = parent
    for _ in range(64):
        if pid <= 1:
            break
        try:
            _, ppid, _, name = _proc_stat(pid)
        except (OSError, ValueError, IndexError):
            break
        if name in HOLDER_NAMES or pid == hinted:
            return pid
        pid = ppid
    return parent


def _pid_start(pid):
    if pid is None or not os.path.isdir("/proc/self"):
        return None
    try:
        return _proc_stat(pid)[2]
    except (OSError, ValueError, IndexError):
        return None


def _git(root, *args):
    try:
        done = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                              check=False, timeout=30, stdin=subprocess.DEVNULL,
                              env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"))
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def machine():
    """What says which pid space a pid number belongs to."""
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
    pidns all match the reader's and /proc shows the pid missing, a zombie, or
    started at another time (reused). Any error is `unmeasured`."""
    same = all(marker.get(k) and marker.get(k) == me.get(k) for k in ("host", "boot_id", "pidns"))
    pid = marker.get("pid")
    if not same or pid is None or pid <= 0 or not os.path.isdir("/proc/self"):
        return "unmeasured"
    try:
        state, _, start, _ = _proc_stat(pid)
    except FileNotFoundError:
        return "gone"
    except (OSError, ValueError, IndexError):
        return "unmeasured"
    if state == "Z":
        return "gone"
    if marker.get("pid_start") is not None and start != marker["pid_start"]:
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
    line = json.dumps(dict({"at": _iso(_now()), "kind": kind, "ticket": ticket}, **fields),
                      sort_keys=True) + "\n"
    fd = os.open(os.path.join(folder, "events.jsonl"),
                 os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


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
    (new token, so the old heartbeat exits), refuses otherwise."""
    if runner not in RUNNERS:
        return EXIT_USAGE, f"refused: runner must be one of {', '.join(RUNNERS)}"
    top = crew_ticket.toplevel(root)
    folder = inflight_dir(root)
    if top is None or folder is None:
        return EXIT_REFUSED, "refused: unknown - git cannot name this worktree or its common dir"
    answer = holds(root, ticket, runner=runner, session=session)
    me = identity(root, session)
    path = _marker_path(folder, ticket)
    if answer["state"] == "free":
        _ensure_dir(folder)
        marker = _new_marker(top, ticket, runner, me)
        tmp = _write_temp(path, marker)
        try:
            os.link(tmp, path)
        except FileExistsError:
            return EXIT_REFUSED, _refusal(holds(root, ticket, runner=runner, session=session))
        finally:
            os.remove(tmp)
        word = "claimed"
    elif answer["state"] == "mine":
        with _Lock(path):
            current, marker_now, _ = _assess(root, ticket, runner, session, None)
            if current["state"] != "mine":
                return EXIT_REFUSED, _refusal(current)
            marker = _new_marker(top, ticket, runner, me, since=marker_now["since"])
            _replace(path, marker)
        word = "refreshed"
    else:
        return EXIT_REFUSED, _refusal(answer)
    _log(folder, "claim", ticket, runner=runner, worktree=top, session=me["session"],
         pid=me["pid"], refreshed=word == "refreshed")
    beat = spawn(top, ticket, marker["token"])
    tail = f"heartbeat pid {beat}" if beat else "heartbeat did not start; the TTL decides"
    return EXIT_OK, f"{word} {ticket} as {runner} ({tail})"


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
    with _Lock(path):
        current, marker, _ = _assess(root, ticket, runner, session, None)
        if current["state"] != "mine":
            return EXIT_REFUSED, _refusal(current)
        os.remove(path)
    _log(folder, "release", ticket, runner=marker["runner"], token=marker["token"])
    return EXIT_OK, f"released {ticket}"


def clear(root, ticket, by, reason):
    """(exit code, line): the owner's removal of a stale or unknown marker,
    re-read under the lock and logged with who and why."""
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
    with _Lock(path):
        current, marker, _ = _assess(root, ticket, None, None, None)
        if current["state"] not in ("stale", "unknown"):
            return EXIT_REFUSED, (f"refused: {current['state']} - clear removes only a stale "
                                  "or unknown marker")
        if os.path.isdir(path) and not os.path.islink(path):
            return EXIT_REFUSED, f"refused: {path} is a directory - remove it by hand"
        os.remove(path)
    _log(folder, "clear", ticket, by=clean(by), reason=clean(reason, 500),
         state=current["state"], why=current["why"],
         runner=clean((marker or {}).get("runner", "")))
    return EXIT_OK, f"cleared {ticket} ({current['state']}) by {clean(by)}"


# --- the heartbeat -----------------------------------------------------------------------

def beat_once(root, ticket, token):
    """`beat`, `skipped` (the lock was busy) or why the loop should exit."""
    folder = inflight_dir(root)
    if folder is None:
        return "exit: git cannot name <git-common-dir>"
    path = _marker_path(folder, ticket)
    if not os.path.lexists(path):
        return "exit: marker gone"
    try:
        with _Lock(path, wait=1.0):
            marker, why = load_marker(path, ticket)
            if marker is None:
                return f"exit: {why or 'marker gone'}"
            if marker["token"] != token:
                return "exit: superseded by another token"
            if probe(marker, machine()) == "gone":
                return "exit: holder pid gone"
            _replace(path, dict(marker, heartbeat_at=_iso(_now())))
    except LockBusy:
        return "skipped"
    except InflightError as exc:
        return f"exit: {exc}"
    return "beat"


def beat_loop(root, ticket, token, sleep=time.sleep):
    """Beat until beat_once says exit. Returns that reason."""
    while True:
        sleep(HEARTBEAT_SECONDS)
        try:
            result = beat_once(root, ticket, token)
        except Exception as exc:  # pylint: disable=broad-except
            return f"exit: {exc!r}"
        if result.startswith("exit"):
            return result


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
