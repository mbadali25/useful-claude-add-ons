"""One tracker interface for every lifecycle transition (T-0021).

    python3 crew_tracker.py resolve [--root .] [--json]
    python3 crew_tracker.py create  --ticket T-0042 --title "..." [--root .] [--json]
    python3 crew_tracker.py move    --ticket T-0042 --to spec [--root .] [--json]
    python3 crew_tracker.py read    --ticket T-0042 [--root .] [--json]
    python3 crew_tracker.py archive --ticket L-0509 [--root .] [--json]

The lifecycle commands call this at their status transitions instead of each
restating, in prose, how a tracker is written. One line per backend is
printed; exit 0 updated/unchanged/not applicable, 1 could not update, 3
delegated (run the printed command), 2 usage.

## Which tracker

`resolve` reads BOTH config shapes: 1.0's `.crew/crew.json`
(`tracker: {"kind", "obsidian", "jira", "sdp"}`) and 0.20's
`.crew/config.json` (`tracker: "<kind>"`, the blocks at top level). When both
state a kind and the kinds differ, the answer is `could not tell`, naming both
files and both values -- never a pick. Picking either is the unknown that
collapses into a safe-looking value, and every write below refuses on it.

## Backends

- files: `.work/INDEX.md`, one row per ticket, `<id> | <status> | <risk> |
  <repo> | <title>`. `move` rewrites the status cell of the one row whose id
  cell matches exactly.
- obsidian: files, plus the Kanban board in the vault (below).
- jira, sdp: `delegated`, with the sync command to run, at the two boundaries
  only (`in-progress`, `done`) and naming the target status; every other move
  pushes nothing -- `needs-owner`, `cancelled` and `superseded` included
  (T-0037: the owner closes a cancelled Jira or SDP item by hand). A script
  cannot call an MCP tool; the model running the lifecycle command can.

Beside the lifecycle order sit T-0037's three words: `needs-owner` (open,
waiting on the owner, Backlog lane) and the closed words `cancelled` and
`superseded` (Done lane, checked). A move backwards by `STATUS_ORDER` --
`done` back to `in-progress` -- is refused unless `--reopen` is passed, and so
is any move out of `done`, `cancelled` or `superseded`, and a move from a
status crew does not know, because whether it goes backwards cannot be told.
`needs-owner` to or from any open word is never backwards.

## Writes

Every write builds its full text first, writes a temp file beside the target,
re-reads the target, and only then `os.replace`s -- recomputing, at most
`WRITE_TRIES` times, when the target changed underneath it (another session
appending to INDEX.md, Obsidian saving the board). The temp is created
exclusively (`O_EXCL`), so a link planted at its name is never followed, and it
carries the target's mode and owner before it replaces it: sessions here run as
root, and a board handed to root 0644 is one Obsidian can no longer save.
A vault write reaches its directory from the vault root one component at a
time without following a link (`dir_fd`), so a directory swapped for a link
after the checks is refused instead of written through, and repeats that walk
around the write, so a directory renamed out of the vault with the fd held is
refused too. A failed tracker write never
undoes the lifecycle transition that called it: it prints `could not update:
<reason>` and exits 1, and the command's prose tells the human.

## Archive (L-0509)

`archive --ticket <ID>` moves ONE done or merged ticket out of the way: its
folder `.work/tickets/<ID>/` to `.work/tickets/Complete/<ID>/`, under obsidian
its note `<boardDir>/<ID>.md` to `<boardDir>/Complete/<ID>.md` (only when the
note says the card is this repo's), and its card off the Done lane. Each half
is one line, idempotent (`unchanged` when already done, so a re-run after a
crash completes the rest), and a failed half stops the halves after it. It
refuses unless INDEX says `done` or `merged`, refuses a ticket any worktree's
active-ticket pointer names (or when that map cannot be read), never renames
over an existing destination, and never edits INDEX.md: the row keeps the id
taken. Every vault check runs before the folder moves. jira and sdp: the
folder only. An archived ticket is still found by `read` (lane `Complete/`);
`move` refuses it (un-archiving is by hand) and `create` treats its id as
taken. A note or folder present in both places is `could not tell`.
"""
import argparse
import contextlib
import datetime
import errno
import json
import ntpath
import os
import pathlib
import re
import secrets
import stat
import subprocess
import sys
import urllib.parse

import crew_common

KINDS = ("files", "obsidian", "jira", "sdp")
COULD_NOT_TELL = "could not tell"
NOT_CONFIGURED = "not configured"

UPDATED = "updated"
UNCHANGED = "unchanged"
FAILED = "could not update"
DELEGATED = "delegated"
NOT_APPLICABLE = "not applicable"
READ = "read"
UNREADABLE = "could not read"
# How `create` begins its reason when the id is someone else's -- held in INDEX
# or on the board. The lifecycle prose reads this phrase: that id is not the
# session's to write under, so it takes the next free one.
TAKEN = "id taken"

# The ticket statuses a lifecycle command moves a ticket to, in order, and the
# `obsidian.columns` key of the lane each one lands in. Table-driven on
# purpose: a new status is a row here, not a branch in the code. A status
# absent from this table maps to no lane and is refused with nothing written.
# T-0037 added three rows off the linear order: `needs-owner` is open and waits
# on the owner; `cancelled` and `superseded` are closed and terminal. This is
# the vocabulary's one owner -- every other closed list is held to
# CLOSED_STATUSES by test_status_vocabulary.py.
STATUS_ORDER = ("direction", "ready", "spec", "planned", "in-progress", "review", "done")
OWNER_STATUSES = ("needs-owner",)  # T-0037: open, the ticket waits on an owner decision
CLOSED_STATUSES = ("cancelled", "superseded")  # T-0037: closed; leaving one needs --reopen
LANE_FOR_STATUS = {
    "direction": "backlog",
    "ready": "backlog",
    "spec": "ready",
    "planned": "ready",
    "in-progress": "inProgress",
    "review": "review",
    "done": "done",
    "needs-owner": "backlog",
    "cancelled": "done",
    "superseded": "done",
}
DEFAULT_COLUMNS = {
    "backlog": "Backlog",
    "ready": "Ready",
    "inProgress": "In Progress",
    "review": "Review",
    "done": "Done",
}
DEFAULT_BOARD = "Board.md"
WRITE_TRIES = 3
INDEX_REL = ".work/INDEX.md"

_TICKET_ID = crew_common.TICKET_ID
_SYNC = {"jira": "/crew:jira-sync", "sdp": "/crew:sdp-sync"}
# Jira and SDP are pushed at pickup and completion, never mid-task (jira-sync.md).
_PUSH_AT = ("in-progress", "done")
_CREATE_DELEGATED = "create the tracker item through MCP, as brainstorm.md step 1 says"
_EXIT = {FAILED: 1, UNREADABLE: 1, DELEGATED: 3}


# --- resolve -----------------------------------------------------------------

def _load(root, name):
    """(dict or None, problem or None) for `.crew/<name>`; absent is (None, None)."""
    rel = f".crew/{name}"
    try:
        with open(crew_common.repo_config_file(root, name), encoding="utf-8-sig") as handle:
            text = handle.read()
    except FileNotFoundError:
        return None, None
    except (OSError, ValueError) as exc:
        return None, f"{rel} unreadable ({exc})"
    try:
        data = json.loads(text)
    except ValueError:
        return None, f"{rel} is not valid JSON"
    if not isinstance(data, dict):
        return None, f"{rel} is not a JSON object"
    return data, None


def _side(name, data):
    """What one config file says: its kind, the key it said it under, its blocks."""
    rel = f".crew/{name}"
    memory = data.get("memory") if isinstance(data.get("memory"), dict) else {}
    if name == "crew.json":
        tracker = data.get("tracker")
        if tracker is None:
            return {"file": rel, "kind": None}
        if not isinstance(tracker, dict):
            return {"file": rel, "problem": f"{rel} tracker is not an object"}
        kind, key, holder = tracker.get("kind"), "tracker.kind", tracker
    else:
        kind, key, holder = data.get("tracker"), "tracker", data
    if kind is None:
        return {"file": rel, "kind": None}
    if kind not in KINDS:
        return {"file": rel, "problem": f"{rel} names tracker kind {kind!r}, which crew does not know"}
    blocks = {k: holder[k] for k in KINDS if isinstance(holder.get(k), dict)}
    return {"file": rel, "kind": kind, "key": key, "blocks": blocks, "memory": memory}


def _settings(kind, side):
    block = dict(side["blocks"].get(kind) or {})
    if kind != "obsidian":
        return block
    settings = {"vaultPath": None, "boardDir": None, "board": DEFAULT_BOARD}
    settings.update(block)
    columns = dict(DEFAULT_COLUMNS)
    if isinstance(block.get("columns"), dict):
        columns.update(block["columns"])
    settings["columns"] = columns
    if not settings.get("vaultPath") and side["memory"].get("vaultPath"):
        settings["vaultPath"] = side["memory"]["vaultPath"]
        settings["vaultPathFrom"] = "memory.vaultPath"
    return settings


def _effective(side):
    """`{field: (value, where from)}` for the obsidian target a file yields --
    vault, boardDir, board and lane names, defaults applied.

    A value is None when the file yields none. An unset boardDir is the vault
    root, so it is `""` once the file yields a vault.
    """
    settings = _settings("obsidian", side)
    vault = settings.get("vaultPath")
    vault = os.path.normpath(os.path.expanduser(vault)) if isinstance(vault, str) and vault else None
    board_dir = settings.get("boardDir")
    if isinstance(board_dir, str):
        board_dir = board_dir.replace("\\", "/").strip("/")
    elif board_dir is None and vault is not None:
        board_dir = ""
    return {"vaultPath": (vault, settings.get("vaultPathFrom", "obsidian.vaultPath")),
            "boardDir": (board_dir, "obsidian.boardDir"),
            "board": (settings.get("board"), "obsidian.board"),
            "columns": (settings["columns"], "obsidian.columns")}


def _effective_disagreements(first, second):
    """What the two files' obsidian targets disagree on, fallbacks and
    defaults included. A value one file yields and the other does not is a
    disagreement too: resolve would otherwise pick whichever file came first."""
    problems, mine, theirs = [], _effective(first), _effective(second)
    for field in ("vaultPath", "boardDir", "board", "columns"):
        (one, one_from), (two, two_from) = mine[field], theirs[field]
        if one != two:
            problems.append(f"{first['file']} yields obsidian {field} {one!r} ({one_from}), "
                            f"{second['file']} yields {two!r} ({two_from})")
    return problems


def resolve(root):
    """`{"kind", "source", "settings", "problems"}` from both config shapes.

    kind is one of KINDS, `could not tell` or `not configured`; source is the
    config file's name the kind came from, or None.
    """
    problems, sides = [], []
    for name in ("crew.json", "config.json"):
        data, problem = _load(root, name)
        if problem:
            problems.append(problem)
        elif data is not None:
            side = _side(name, data)
            if "problem" in side:
                problems.append(side["problem"])
            elif side["kind"] is not None:
                sides.append(side)
    if len(sides) == 2:
        first, second = sides[0], sides[1]
        if first["kind"] != second["kind"]:
            problems.append(f"{first['file']} says {first['key']} {first['kind']!r}, "
                            f"{second['file']} says {second['key']} {second['kind']!r}")
        else:
            kind = first["kind"]
            # Obsidian field by field, defaults and fallbacks applied: the
            # same target spelled two ways (`/v`, `/v/`) is not a disagreement.
            # Any other kind's block whole -- a block only one file carries
            # included, since resolve would otherwise take the first file's.
            if kind == "obsidian":
                problems += _effective_disagreements(first, second)
            elif first["blocks"].get(kind) != second["blocks"].get(kind):
                problems.append(f"{first['file']} and {second['file']} both say {kind!r} "
                                f"but disagree on its {kind} settings")
    if problems:
        return {"kind": COULD_NOT_TELL, "source": None, "settings": {}, "problems": problems}
    if not sides:
        return {"kind": NOT_CONFIGURED, "source": None, "settings": {}, "problems": []}
    side = sides[0]
    return {"kind": side["kind"], "source": os.path.basename(side["file"]),
            "settings": _settings(side["kind"], side), "problems": []}


# --- results -----------------------------------------------------------------

def _result(backend, state, reason=None, command=None, **extra):
    out = {"backend": backend, "state": state, "reason": reason, "command": command}
    out.update(extra)
    return out


def _report(info, results):
    return {"kind": info["kind"], "source": info["source"], "results": results}


def exit_code(report):
    """1 if any backend could not update, else 3 if any delegated, else 0."""
    codes = [_EXIT.get(r["state"], 0) for r in report["results"]]
    return 1 if 1 in codes else (3 if 3 in codes else 0)


def _gate(info):
    """A result that stops the call before anything is written, or None."""
    kind = info["kind"]
    if kind == COULD_NOT_TELL:
        return _result("tracker", FAILED, "tracker kind could not tell: " + "; ".join(info["problems"]))
    if kind == NOT_CONFIGURED:
        return _result("tracker", NOT_APPLICABLE,
                       "no tracker configured in .crew/crew.json or .crew/config.json")
    return None


# --- atomic replace ------------------------------------------------------------

# O_EXCL is the guard: with O_CREAT it refuses anything already at the name,
# a symlink included (dangling or not), so a link planted at a temp name is
# never followed. O_NOFOLLOW is belt and braces; O_BINARY stops Windows' CRT
# turning each LF into CRLF underneath `os.fdopen(fd, "wb")`.
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_BINARY = getattr(os, "O_BINARY", 0)
_TEMP_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW | _BINARY
_NOTE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW | _BINARY
_DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | _NOFOLLOW

# Whether a vault write can be pinned to its directory: open, stat, unlink and
# rename (`os.replace` is the same call) relative to a directory fd, and a
# no-follow directory open. POSIX has all of it; Windows has none of it.
_DIR_FD = (hasattr(os, "O_DIRECTORY") and bool(_NOFOLLOW)
           and all(call in os.supports_dir_fd for call in (os.open, os.stat, os.unlink, os.rename)))

# Windows pins differently (T-0077): a handle on each directory from the vault
# down, opened with data access and WITHOUT FILE_SHARE_DELETE, makes the OS
# refuse to rename that directory or any directory above it for as long as it
# is held, while files inside it are still written and replaced. Measured: a
# handle with FILE_READ_ATTRIBUTES alone does not block the rename, which is
# why the access mask below is part of the contract and a test pins it.
_FILE_LIST_DIRECTORY = 0x0001
_FILE_READ_ATTRIBUTES = 0x0080
_FILE_SHARE_READ, _FILE_SHARE_WRITE, _FILE_SHARE_DELETE = 0x1, 0x2, 0x4
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000  # required to open a directory at all
_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000  # open a link itself, never its target
_OPEN_EXISTING = 3
_PIN_ACCESS = _FILE_LIST_DIRECTORY | _FILE_READ_ATTRIBUTES
_PIN_SHARE = _FILE_SHARE_READ | _FILE_SHARE_WRITE
_PIN_FLAGS = _FILE_FLAG_BACKUP_SEMANTICS | _FILE_FLAG_OPEN_REPARSE_POINT
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _win_pin_available():
    if os.name != "nt":
        return False
    try:
        import ctypes  # pylint: disable=import-outside-toplevel
        import msvcrt  # pylint: disable=import-outside-toplevel
    except ImportError:
        return False
    return hasattr(ctypes, "WinDLL") and hasattr(msvcrt, "open_osfhandle")


_WIN_PIN = _win_pin_available()


def _win_open_dir(path):
    """`(stat, close)` for a held handle on directory `path` (Windows only).

    The handle denies FILE_SHARE_DELETE, so while it is open `path` and every
    directory above it cannot be renamed. It is wrapped in a CRT fd so
    `os.fstat` reports the same `(st_dev, st_ino)` `os.stat` does, and `close`
    closes both. Any failure raises OSError: the caller refuses the write."""
    import ctypes  # pylint: disable=import-outside-toplevel
    import msvcrt  # pylint: disable=import-outside-toplevel
    from ctypes import wintypes  # pylint: disable=import-outside-toplevel
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel32.CreateFileW
    create.restype = wintypes.HANDLE
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    handle = create(path, _PIN_ACCESS, _PIN_SHARE, None, _OPEN_EXISTING, _PIN_FLAGS, None)
    if handle is None or handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY)
    except BaseException:
        kernel32.CloseHandle(wintypes.HANDLE(handle))
        raise
    try:
        seen = os.fstat(fd)
    except BaseException:
        os.close(fd)
        raise
    return seen, lambda: os.close(fd)


def _read_bytes(path, dir_fd=None):
    """The file's bytes, or None when it does not exist. With `dir_fd`, `path`
    is a name in that directory and a link at it is refused, not followed."""
    flags = os.O_RDONLY | _BINARY | (_NOFOLLOW if dir_fd is not None else 0)
    try:
        fd = os.open(path, flags, dir_fd=dir_fd)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, "rb") as handle:
        return handle.read()


def _discard(path, dir_fd=None):
    try:
        os.unlink(path, dir_fd=dir_fd)
    except OSError:
        pass


def _temp_name(name):
    return f".{name}.crew-{os.getpid()}-{secrets.token_hex(6)}.tmp"


def _is_root():
    return hasattr(os, "geteuid") and os.geteuid() == 0


def _ownership(path, dir_fd=None):
    """What a file written at `path` must carry: `(mode, uid, gid, replaces)`.

    An existing target's own mode and owner. A new file keeps the umask's mode
    and, only when running as root, takes its directory's owner -- a user who
    is not root cannot give a file away and creates it as themselves, which is
    what every other file they create does.
    """
    try:
        found = os.stat(path, dir_fd=dir_fd, follow_symlinks=dir_fd is None)
        return stat.S_IMODE(found.st_mode), found.st_uid, found.st_gid, True
    except FileNotFoundError:
        found = os.fstat(dir_fd) if dir_fd is not None else os.stat(os.path.dirname(path) or ".")
        return None, found.st_uid, found.st_gid, False


def _carry(fd, ownership):
    """Give the open file `ownership`'s owner, then its mode. A replacement
    that cannot keep the old owner is refused rather than handed to whoever
    ran crew; os.error's strerror carries why."""
    mode, uid, gid, replaces = ownership
    if hasattr(os, "fchown") and (replaces or _is_root()):
        now = os.fstat(fd)
        if (now.st_uid, now.st_gid) != (uid, gid):
            try:
                os.fchown(fd, uid, gid)
            except PermissionError as exc:
                raise OSError(exc.errno, f"cannot keep its owner {uid}:{gid} ({exc.strerror})") from exc
    if mode is not None and hasattr(os, "fchmod"):
        os.fchmod(fd, mode)


def _write_new(path, flags, data, ownership, dir_fd=None):
    """Create `path` with `flags` (exclusive) and write `data`; a file this call
    made and could not finish is removed, never left half-written."""
    fd = os.open(path, flags, 0o666, dir_fd=dir_fd)
    try:
        with os.fdopen(fd, "wb") as handle:
            _carry(handle.fileno(), ownership)
            handle.write(data)
    except BaseException:
        _discard(path, dir_fd)
        raise


def _write_temp(path, data, ownership, dir_fd=None):
    """A new temp file beside `path` holding `data`, created exclusively."""
    folder, name = os.path.split(path)
    for _ in range(WRITE_TRIES):
        tmp = os.path.join(folder, _temp_name(name))
        try:
            _write_new(tmp, _TEMP_FLAGS, data, ownership, dir_fd)
        except FileExistsError:
            continue
        return tmp
    raise OSError(errno.EEXIST, f"no free temp file name beside it after {WRITE_TRIES} tries")


def _atomic_update(path, label, backend, compute, dir_fd=None, check=None):
    """Replace `path` with `compute(old_bytes)`'s text, re-reading before replace.

    `compute` returns `(new_bytes or None, result)`; None means nothing to
    write and the result is returned as-is. When the file changed between
    the read and the replace, the temp is dropped and the text recomputed from
    the new bytes, at most WRITE_TRIES times. With `dir_fd`, `path` is a name
    in that pinned directory. `check`, for a vault write, returns why the
    directory moved (or None) and runs before the temp is written, before the
    replace and after it.
    """
    for _ in range(WRITE_TRIES):
        try:
            before = _read_bytes(path, dir_fd=dir_fd)
            ownership = _ownership(path, dir_fd)
        except OSError as exc:
            return _result(backend, FAILED, f"{label}: {exc.strerror or exc}")
        new, result = compute(before)
        if new is None:
            return result
        tmp = None
        try:
            moved = check() if check is not None else None
            if moved:
                return _result(backend, FAILED, moved)
            tmp = _write_temp(path, new, ownership, dir_fd)
            if _read_bytes(path, dir_fd=dir_fd) != before:
                _discard(tmp, dir_fd)
                continue
            moved = check() if check is not None else None
            if moved:
                _discard(tmp, dir_fd)
                return _result(backend, FAILED, moved)
            os.replace(tmp, path, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        except OSError as exc:
            if tmp:
                _discard(tmp, dir_fd)
            return _result(backend, FAILED, f"{label}: {exc.strerror or exc}")
        moved = check() if check is not None else None
        if moved:
            return _result(backend, FAILED, f"{moved}; the write may have landed there")
        return result
    return _result(backend, FAILED, f"{label} changed during write")


# --- files backend -------------------------------------------------------------

def _cells(line):
    body = line.strip()
    if "|" not in body:
        return []
    return [c.strip() for c in body.strip("|").split("|")]


def _rows(lines, ticket):
    return [i for i, line in enumerate(lines) if (_cells(line) or [None])[0] == ticket]


def _no_status_cell(ticket):
    return f"{INDEX_REL} row for {ticket} has no status cell"


def _set_status(line, status):
    """`line` with only its status cell's text replaced; padding and pipes kept.
    The caller has checked `_cells(line)` has a status cell."""
    body = line.rstrip("\r\n")
    ending = line[len(body):]
    parts = body.split("|")
    index = 2 if body.lstrip().startswith("|") else 1
    cell = parts[index]
    if cell.strip():
        lead = cell[:len(cell) - len(cell.lstrip())]
        trail = cell[len(cell.rstrip()):]
    else:
        lead, trail = cell, ""
    parts[index] = lead + status + trail
    return "|".join(parts) + ending


def _decode(data, label):
    if data is None:
        return "", None
    try:
        return data.decode("utf-8"), None
    except UnicodeDecodeError:
        return None, f"{label} is not UTF-8"


def _git_out(root, *args):
    """`(returncode, stdout stripped)`, or `(None, "")` when git could not run."""
    try:
        done = subprocess.run([crew_common.require_tool("git"), *args], cwd=root, capture_output=True,
                              text=True, check=False,
                              stdin=subprocess.DEVNULL, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None, ""
    return done.returncode, done.stdout.strip()


def _common_dir(root):
    code, common = _git_out(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return common if code == 0 and common else None


_SSH_SCHEMES = ("ssh", "git+ssh", "ssh+git")


def normal_url(url):
    """An origin URL as an identity: lowercased, `.git` and secrets dropped.

    The identity is written into a vault note a human reads, so no password
    reaches it. Over ssh the username stays: `alice@host:repo.git` and
    `bob@host:repo.git` are two users' home-relative repositories, so the name
    is part of which repository it is; only a `:password` after it goes. Every
    other scheme drops the whole userinfo: the path names the repository
    there, and `https://<token>@host/...` puts a token where a username goes.
    """
    url = url.strip().lower()
    # scp-style `user@host:path` is ssh and has no password field: it is kept.
    if "://" in url:
        scheme, rest = url.split("://", 1)
        host, slash, path = rest.partition("/")
        user = host.rpartition("@")[0].partition(":")[0]
        keep = f"{user}@" if user and scheme in _SSH_SCHEMES else ""
        url = f"{scheme}://{keep}{host.rpartition('@')[2]}{slash}{path}"
    url = url.rstrip("/")
    return url[:-4] if url.endswith(".git") else url


def _local_path(url):
    """The filesystem path an origin URL names, or None for a remote URL.

    Git's own rule: `scheme://` is a URL (`file://` a local one, its path
    percent-decoded), and a colon before the first slash is scp-style
    `host:path`; anything else is a path.
    """
    if "://" in url:
        # Git percent-decodes a file:// path: `file:///srv/a%20b.git` is
        # `/srv/a b.git`, while the bare path `/srv/a%20b.git` is itself.
        return urllib.parse.unquote(url[len("file://"):]) if url.lower().startswith("file://") else None
    head = url.split("/", 1)[0]
    if ":" in head and not ntpath.splitdrive(url)[0]:
        return None
    return url


def repo_id(root):
    """This repository's identity, the same in every worktree of it, or None
    when git could not say.

    The origin URL (see `normal_url`), else the real path of the git common
    dir. Never the directory's name: `a/app` and `b/app` share that. An origin
    that is a relative path is not an identity either -- `../origin/app.git`
    from `a/app` and from `b/app` is one string naming two repositories -- so
    it is the common dir too; an absolute one is its real path.
    """
    common = _common_dir(root)
    if common is None:
        return None
    code, url = _git_out(root, "remote", "get-url", "origin")
    if code == 0 and url:
        local = _local_path(url)
        if local is None:
            return normal_url(url)
        if os.path.isabs(local) or ntpath.isabs(local):
            return os.path.realpath(local)
        return os.path.realpath(common)
    if code == 2:
        return os.path.realpath(common)
    return None


def repo_name(root):
    """The repository's name, the same in every worktree of it. A label for
    humans only; ownership is `repo_id`."""
    common = _common_dir(root)
    if common:
        common = os.path.normpath(common)
        if os.path.basename(common) == ".git":
            return os.path.basename(os.path.dirname(common))
        return os.path.basename(common)[:-4] if common.endswith(".git") else os.path.basename(common)
    return os.path.basename(os.path.realpath(root))


def title_ok(title):
    """A title fits one INDEX cell and one card line.

    One line by `str.splitlines`' own rule, which also splits on \x0b, \x0c,
    \x1c-\x1e, \x85, U+2028 and U+2029 -- every INDEX reader in crew splits
    that way, so a title holding one of them is two rows to them.
    """
    return bool(title) and "|" not in title and title.splitlines() == [title]


def _held(ticket, held):
    """Why `create` refuses an id INDEX already holds, whatever its title: a
    second session minting the same id under the same title is still a second
    session, and nothing in INDEX tells the two apart."""
    if len(held) > 1:
        return f"{TAKEN}: {INDEX_REL} has {len(held)} rows for {ticket}"
    cells = held[0]
    status = cells[1] if len(cells) > 1 and cells[1] else "(no status)"
    title = cells[4] if len(cells) > 4 else ""
    return f'{TAKEN}: {ticket} is already {status} "{title}"'


def _backwards(ticket, current, status):
    """Why moving from `current` to `status` needs --reopen, or None."""
    if current == status:
        return None
    if current in CLOSED_STATUSES or (current == "done" and status not in STATUS_ORDER):
        return f"{ticket} is {current}; moving it to {status} needs --reopen"
    if current in OWNER_STATUSES:
        return None
    if current not in STATUS_ORDER:
        return (f"could not tell whether {current} -> {status} goes backwards ({current!r} is not a "
                f"status crew knows); pass --reopen if the move is meant")
    if status not in STATUS_ORDER:
        return None
    if STATUS_ORDER.index(status) < STATUS_ORDER.index(current):
        return f"{ticket} is {current}; moving it back to {status} needs --reopen"
    return None


def _files_create(root, ticket, title):
    backend = "files"
    if not title_ok(title):
        return _result(backend, FAILED, "title must be one line with no '|'")
    row = f"{ticket} | direction | - | {repo_name(root)} | {title}\n"

    def compute(old):
        text, problem = _decode(old, INDEX_REL)
        if problem:
            return None, _result(backend, FAILED, problem)
        lines = text.splitlines()
        held = [_cells(lines[i]) for i in _rows(lines, ticket)]
        if held:
            return None, _result(backend, FAILED, _held(ticket, held))
        if text and not text.endswith("\n"):
            text += "\n"
        return (text + row).encode("utf-8"), _result(backend, UPDATED, f"{INDEX_REL} row added")

    path = os.path.join(root, ".work", "INDEX.md")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError as exc:
        return _result(backend, FAILED, f".work: {exc.strerror or exc}")
    return _atomic_update(path, INDEX_REL, backend, compute)


def _files_move(root, ticket, status, reopen=False):
    backend = "files"

    def compute(old):
        text, problem = _decode(old, INDEX_REL)
        if problem:
            return None, _result(backend, FAILED, problem)
        lines = text.splitlines(keepends=True)
        found = _rows(lines, ticket)
        if not found:
            return None, _result(backend, FAILED, f"no {INDEX_REL} row for {ticket}")
        if len(found) > 1:
            return None, _result(backend, FAILED, f"{INDEX_REL} has {len(found)} rows for {ticket}")
        cells = _cells(lines[found[0]])
        if len(cells) < 2:
            return None, _result(backend, FAILED, _no_status_cell(ticket))
        current = cells[1]
        if current == status:
            return None, _result(backend, UNCHANGED, f"{INDEX_REL} already {status}")
        backwards = None if reopen else _backwards(ticket, current, status)
        if backwards:
            return None, _result(backend, FAILED, backwards)
        lines[found[0]] = _set_status(lines[found[0]], status)
        return "".join(lines).encode("utf-8"), _result(backend, UPDATED, f"{INDEX_REL} {current} -> {status}")

    return _atomic_update(os.path.join(root, ".work", "INDEX.md"), INDEX_REL, backend, compute)


def _files_read(root, ticket):
    try:
        raw = _read_bytes(os.path.join(root, ".work", "INDEX.md"))
    except OSError as exc:
        return _result("files", UNREADABLE, f"{INDEX_REL}: {exc.strerror or exc}")
    text, problem = _decode(raw, INDEX_REL)
    if problem:
        return _result("files", UNREADABLE, problem)
    found = _rows(text.splitlines(), ticket)
    if len(found) != 1:
        why = f"no {INDEX_REL} row for {ticket}" if not found else f"{len(found)} rows for {ticket}"
        return _result("files", UNREADABLE, why)
    cells = _cells(text.splitlines()[found[0]])
    if len(cells) < 2:
        return _result("files", UNREADABLE, _no_status_cell(ticket))
    return _result("files", READ, None, status=cells[1], title=cells[4] if len(cells) > 4 else None)


# --- the Kanban board ------------------------------------------------------------
#
# An Obsidian Kanban board is markdown the plugin round-trips, and three parts
# of it are load-bearing: `kanban-plugin: board` in the frontmatter, the
# trailing `%% kanban:settings` block, and `**Complete**` in the done lane. An
# archive is a `***` break followed by `## Archive`. A board that stops
# parsing opens as plain text in the human's window, so nothing here
# regenerates a board: it cuts one card's lines and inserts them elsewhere,
# and every other byte is the byte it read.

_HEADING = re.compile(r"## (.+?)[ \t]*\Z")
_KANBAN_KEY = re.compile(r"kanban-plugin:\s*['\"]?board['\"]?\s*\Z")
_CARD_START = re.compile(r"- ")
_CHECKED = re.compile(r"- \[[xX]\]")
_FIRST_ID = re.compile(rf"\[\[({crew_common.TICKET_ID_CORE})(?:[|#][^\]]*)?\]\]"
                       rf"|(?<![A-Za-z0-9-])({crew_common.TICKET_ID_CORE})(?![A-Za-z0-9])")
_COMPLETE = "**Complete**"


def _bare(line):
    return line.rstrip("\r\n")


def _board_lines(text):
    """The board's lines with their endings, split on LF alone.

    Not `str.splitlines`: it also splits on \x0b, \x0c, \x1c-\x1e, \x85,
    U+2028 and U+2029, which a Markdown editor keeps inside a line, so a card a
    human typed one of them into would be cut in two and moved by halves.
    """
    parts = text.split("\n")
    lines = [part + "\n" for part in parts[:-1]]
    return lines + [parts[-1]] if parts[-1] else lines


def _frontmatter_end(lines):
    """Index of the closing `---`, or a problem."""
    if not lines or _bare(lines[0]) != "---":
        return None, "not a Kanban board: no 'kanban-plugin: board' in its frontmatter"
    for index in range(1, len(lines)):
        if _bare(lines[index]) == "---":
            if any(_KANBAN_KEY.match(_bare(line)) for line in lines[1:index]):
                return index, None
            break
    return None, "not a Kanban board: no 'kanban-plugin: board' in its frontmatter"


def _region_end(lines, start):
    """(end of the lanes region, problem): the archive break or the settings block."""
    settings = next((i for i in range(start, len(lines))
                     if _bare(lines[i]).startswith("%% kanban:settings")), None)
    if settings is not None:
        close = next((i for i in range(settings + 1, len(lines)) if _bare(lines[i]) == "%%"), None)
        if close is None or any(_bare(line).strip() for line in lines[close + 1:]):
            return None, "the %% kanban:settings block is not the last thing on the board"
    end = len(lines) if settings is None else settings
    for index in range(start, end):
        if _bare(lines[index]).strip() == "***":
            following = next((_bare(line) for line in lines[index + 1:end] if _bare(line).strip()), "")
            if following == "## Archive":
                return index, None
    return end, None


def parse_board(text, columns):
    """`(board, None)` or `(None, problem)`. Never raises.

    The board is its lines (endings kept), the lanes above any archive break
    in order, and the configured lane names every lifecycle status needs.
    """
    lines = _board_lines(text)
    top, problem = _frontmatter_end(lines)
    if problem:
        return None, problem
    end, problem = _region_end(lines, top + 1)
    if problem:
        return None, problem
    headings = []
    for index in range(top + 1, end):
        found = _HEADING.match(_bare(lines[index]))
        if found:
            headings.append((found.group(1), index))
    lanes = []
    for position, (name, index) in enumerate(headings):
        stop = headings[position + 1][1] if position + 1 < len(headings) else end
        lanes.append({"name": name, "heading": index, "end": stop})
    for key in sorted(set(LANE_FOR_STATUS.values()), key=list(DEFAULT_COLUMNS).index):
        name = columns.get(key)
        count = sum(1 for lane in lanes if lane["name"] == name)
        if count == 0:
            return None, f"lane {name!r} (obsidian.columns.{key}) is not on the board"
        if count > 1:
            return None, f"lane {name!r} appears {count} times on the board"
    board = {"lines": lines, "lanes": lanes, "columns": dict(columns)}
    # Done is where a card is complete, and the plugin says so with one marker;
    # a checked card in a lane without it is a completed card on no Done lane.
    markers = len(_complete_markers(board))
    if markers != 1:
        what = "no **Complete** marker" if not markers else f"{markers} **Complete** markers"
        return None, f"lane {columns['done']!r} (obsidian.columns.done) has {what}"
    return board, None


def _complete_markers(board):
    lane = _lane(board, "done")
    return [i for i in range(lane["heading"] + 1, lane["end"]) if _bare(board["lines"][i]).strip() == _COMPLETE]


def _cards(board):
    """Every card above the archive: `{"start", "end", "lane", "id"}`."""
    lines, found = board["lines"], []
    for lane in board["lanes"]:
        index = lane["heading"] + 1
        while index < lane["end"]:
            if not _CARD_START.match(lines[index]):
                index += 1
                continue
            stop = index + 1
            while stop < lane["end"] and lines[stop][:1] in (" ", "\t") and _bare(lines[stop]).strip():
                stop += 1
            ident = _FIRST_ID.search(_bare(lines[index]))
            found.append({"start": index, "end": stop, "lane": lane["name"],
                          "id": (ident.group(1) or ident.group(2)) if ident else None})
            index = stop
    return found


def find_card(board, ticket):
    """`(card, None)` or `(None, problem)`. A card is the ticket's when the first
    id on its first line is the ticket's: `[[T-0009]] ... (depends on T-0005)` is
    T-0009's card, not a second T-0005 card."""
    matches = [card for card in _cards(board) if card["id"] == ticket]
    if not matches:
        return None, f"no card for {ticket} on the board"
    if len(matches) > 1:
        return None, (f"{len(matches)} cards for {ticket} on the board "
                      f"({', '.join(card['lane'] for card in matches)})")
    return matches[0], None


def _lane(board, key):
    name = board["columns"][key]
    return next(lane for lane in board["lanes"] if lane["name"] == name)


def _insertion(board, key):
    """Where a card becomes the first item of lane `key` (after `**Complete**` in done)."""
    lines, lane = board["lines"], _lane(board, key)
    anchor = _complete_markers(board)[0] if key == "done" else lane["heading"]
    for index in range(anchor + 1, lane["end"]):
        if _CARD_START.match(lines[index]):
            return index
    index = anchor + 1
    if index < lane["end"] and not _bare(lines[index]).strip():
        index += 1
    return index


def _ending(lines):
    return "\r\n" if lines and lines[0].endswith("\r\n") else "\n"


def _place(board, key, card_lines):
    """The board text with `card_lines` inserted as lane `key`'s first item."""
    lines = list(board["lines"])
    at = _insertion(board, key)
    if at > 0 and not lines[at - 1].endswith("\n"):
        lines[at - 1] += _ending(lines)
    lines[at:at] = card_lines
    return "".join(lines)


_BOX = re.compile(r"- \[[ xX]\]")


def _checkbox(line, key):
    """A card's first line checked for lane `key` done, unchecked for any other.
    A card with no box (`- T-0042`) gets one, so a Done card always reads done."""
    box = "- [x]" if key == "done" else "- [ ]"
    if not _BOX.match(line):
        return f"{box} {line[2:]}"
    if key == "done" and line.startswith("- [ ]"):
        return "- [x]" + line[5:]
    if key != "done" and _CHECKED.match(line):
        return "- [ ]" + line[5:]
    return line


def move_card(board, ticket, key):
    """`(new_text, lane_it_was_in, None)` or `(None, None, problem)`.

    A card already in lane `key` stays where it is with its checkbox set for
    that lane -- unless the lane is done and the card sits above `**Complete**`,
    which is not done; that card is moved below the marker like any other.
    """
    card, problem = find_card(board, ticket)
    if problem:
        return None, None, problem
    target = board["columns"][key]
    lines = board["lines"]
    if card["lane"] == target and (key != "done" or card["start"] > _complete_markers(board)[0]):
        fixed = list(lines)
        fixed[card["start"]] = _checkbox(lines[card["start"]], key)
        return "".join(fixed), card["lane"], None
    moved = list(lines[card["start"]:card["end"]])
    ending = _ending(lines)
    moved = [line if line.endswith("\n") else line + ending for line in moved]
    moved[0] = _checkbox(moved[0], key)
    remaining = lines[:card["start"]] + lines[card["end"]:]
    rest, problem = parse_board("".join(remaining), board["columns"])
    if problem:
        return None, None, problem
    return _place(rest, key, moved), card["lane"], None


def remove_card(board, ticket):
    """`(new_text, None)`, `(None, "absent")` when no card for `ticket` is on the
    lanes, or `(None, problem)`. Cuts the card's whole span -- first line and
    continuation lines -- only from the done lane; every other byte is kept."""
    card, problem = find_card(board, ticket)
    if problem and not _cards_for(board, ticket):
        return None, "absent"
    if problem:
        return None, problem
    done = board["columns"]["done"]
    if card["lane"] != done:
        return None, f"card is in {card['lane']}, not {done}"
    lines = board["lines"]
    remaining = lines[:card["start"]] + lines[card["end"]:]
    rest, problem = parse_board("".join(remaining), board["columns"])
    if problem:
        return None, problem
    return "".join(rest["lines"]), None


def _cards_for(board, ticket):
    return [card for card in _cards(board) if card["id"] == ticket]


def add_card(board, ticket, title, key):
    """`(new_text, None)`: `- [ ] [[<id>]] <title>` first in lane `key`; unchanged
    when the ticket already has a card anywhere above the archive."""
    if any(card["id"] == ticket for card in _cards(board)):
        return "".join(board["lines"]), None
    return _place(board, key, [f"- [ ] [[{ticket}]] {title}{_ending(board['lines'])}"]), None


# --- the Obsidian backend --------------------------------------------------------
#
# The only crew code that writes outside the repository. Every path is
# resolved and confined before anything is written anywhere -- the INDEX half
# included -- so a refusal leaves the vault and the repo byte-identical. Once
# the checks pass, the INDEX half and the board half are written and reported
# separately, and a board write that fails does not roll the INDEX half back.

def _inside(parent, path):
    try:
        return os.path.commonpath([parent, path]) == parent
    except ValueError:
        return False


def _git_ignored(repo, path):
    """True/False from `git check-ignore`, None when git could not say."""
    try:
        done = subprocess.run([crew_common.require_tool("git"), "check-ignore", "-q", "--", path], cwd=repo,
                              capture_output=True, text=True, check=False,
                              stdin=subprocess.DEVNULL, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return {0: True, 1: False}.get(done.returncode)


def _vault_paths(root, settings, names):
    """`({"vault", "dir", <label>: real path}, None)` or `(None, problem)`.

    `names` is `[(label, file name)]` or `[(label, file name, sub)]`, each
    placed at `<vault>/<boardDir>/` or `<vault>/<boardDir>/<sub>/`, where `sub`
    may only be the archive folder (`crew_common.ARCHIVE_DIR`, L-0509). Every
    file gets the same confinement, regular-file and git-ignore checks.
    `<label>DirIds` records the identity of every directory between the vault
    and that file (`_component_ids`), for the pinned walks to match.
    """
    raw = settings.get("vaultPath")
    if not raw or not isinstance(raw, str):
        return None, "obsidian.vaultPath is not set"
    vault = os.path.realpath(os.path.expanduser(raw))
    if not os.path.isdir(vault):
        return None, f"vault missing: {raw}"
    if not os.path.isdir(os.path.join(vault, ".obsidian")):
        return None, f"{raw} has no .obsidian/ - not an Obsidian vault"
    board_dir = settings.get("boardDir") or ""
    if not isinstance(board_dir, str):
        return None, "obsidian.boardDir must be a string"
    if os.path.isabs(board_dir) or ntpath.isabs(board_dir) or board_dir.startswith(("/", "\\")):
        return None, f"obsidian.boardDir {board_dir!r} must be relative to the vault"
    if ".." in re.split(r"[\\/]", board_dir):
        return None, f"obsidian.boardDir {board_dir!r} may not contain '..'"
    found = {"vault": vault, "dir": board_dir.replace("\\", "/").strip("/")}
    try:
        seen = os.stat(vault)
    except OSError as exc:
        return None, f"vault {raw}: {exc.strerror or exc}"
    found["vaultId"] = (seen.st_dev, seen.st_ino)
    for label, name, *sub in names:
        if not isinstance(name, str):
            return None, f"obsidian.{label} {name!r} must be a bare file name"
        if not name or name in (".", "..") or any(sep in name for sep in "/\\"):
            return None, f"obsidian.{label} {name!r} must be a bare file name"
        if sub and sub != [crew_common.ARCHIVE_DIR]:
            return None, f"{label}: {sub!r} is not a folder crew writes; only the archive folder is"
        name = "/".join(sub + [name])
        shown = f"{found['dir']}/{name}" if found["dir"] else name
        real = os.path.realpath(os.path.join(vault, board_dir, *name.split("/")))
        if not _inside(vault, real):
            return None, f"{label} {shown} resolves outside the vault"
        if os.path.lexists(real) and not os.path.isfile(real):
            return None, f"{label} {shown} is not a regular file"
        found[label], found[label + "Shown"] = real, shown
        found[label + "DirIds"] = _component_ids(found, label)
    # Each file, not the vault: a vault that CONTAINS the repo, with boardDir
    # pointing into it, puts the board in the worktree while the vault is not.
    repo = os.path.realpath(root)
    for label, *_ in names:
        if not _inside(repo, found[label]):
            continue
        ignored = _git_ignored(repo, found[label])
        if ignored is None:
            return None, f"could not tell whether git ignores {found[label + 'Shown']} in this worktree"
        if not ignored:
            return None, (f"{found[label + 'Shown']} is inside this worktree and git does not ignore "
                          f"it: the board would enter the review bundle")
    return found, None


def _load_board(paths, columns):
    """`(board, None)` or `(None, problem)` for the board at `paths["board"]`."""
    try:
        raw = _read_bytes(paths["board"])
    except OSError as exc:
        return None, f"{paths['boardShown']}: {exc.strerror or exc}"
    if raw is None:
        return None, f"no board at {paths['boardShown']}"
    text, problem = _decode(raw, paths["boardShown"])
    if problem:
        return None, problem
    return parse_board(text, columns)


def _moved(shown, exc):
    """A pinned walk's OSError as a reason: a link or a non-directory where a
    checked directory was is the swap this walk exists to refuse."""
    if exc.errno in (errno.ELOOP, errno.ENOTDIR, errno.ESTALE):
        return (f"{shown}: a directory on its path changed after the vault checks "
                f"({exc.strerror}); nothing written through it")
    return f"{shown}: {exc.strerror or exc}"


def _components(paths, label):
    rel = os.path.relpath(os.path.dirname(paths[label]), paths["vault"])
    return [part for part in rel.split(os.sep) if part not in ("", ".")]


def _component_ids(paths, label):
    """`(st_dev, st_ino)` of each real component `_components` names, outermost
    first, read with `os.lstat` so it is the object a no-follow open reaches;
    None for one absent, not a directory, or unreadable."""
    ids, path = [], paths["vault"]
    for part in _components(paths, label):
        path = os.path.join(path, part)
        try:
            info = os.lstat(path)
        except OSError:
            ids.append(None)
            continue
        ids.append((info.st_dev, info.st_ino) if stat.S_ISDIR(info.st_mode) else None)
    return ids


def _could_not_tell(found, want, where):
    """Raise unless both identities of `where` (a vault-relative directory, or
    "the vault") can be told: a recorded `want` that is None, or an inode / file
    id of 0 on either side, is no evidence -- never "the same"."""
    if want is None:
        raise OSError(errno.EIO, f"could not tell whether {where} is the directory the vault checks found: "
                                 f"no identity was recorded for it; nothing written")
    if not found.st_ino or not want[1]:
        kind = "inode" if _DIR_FD else "file id"
        raise OSError(errno.EIO, f"could not tell whether {where} is the directory the vault checks found: "
                                 f"the file system reports {kind} 0; nothing written")


def _recorded_ids(paths, label, parts):
    """The `_vault_paths` identities for `parts`, refused as "could not tell"
    when they do not line up with the components being walked."""
    ids = paths.get(label + "DirIds")
    if not isinstance(ids, list) or len(ids) != len(parts):
        raise OSError(errno.EIO, "could not tell whether the directories on its path are the ones the "
                                 "vault checks found: no identity was recorded for each; nothing written")
    return ids


def _match_component(found, want, where):
    """Raise unless `found` (the stat of component `where` the walk opened) is
    the directory `_vault_paths` recorded there as `want`: EIO when either
    cannot be told, ESTALE (`_moved`'s "changed after the vault checks") when
    they differ."""
    _could_not_tell(found, want, where)
    if (found.st_dev, found.st_ino) != tuple(want):
        raise OSError(errno.ESTALE, f"{where} is not the directory the vault checks found (or its file system "
                                    f"does not keep inodes stable, as some FUSE and network mounts do not)")


def _hold_dirs(paths, label):
    """Windows: `[(stat, close)]`, a held handle on the vault and on every real
    component down to the directory holding `paths[label]`, outermost first.

    Held together they make every one of those directories un-renameable until
    `_release`. Each is refused rather than trusted when it is a reparse point
    (a link planted where a checked directory was), not a directory, or has no
    file id to compare -- no id is "could not tell", never "the same". The
    vault, and every component below it, is matched by device and file id
    against the one checked (T-0081).
    """
    held = []
    try:
        parts = _components(paths, label)
        ids = _recorded_ids(paths, label, parts)
        path = paths["vault"]
        for index, part in enumerate([None] + parts):
            if part is not None:
                path = os.path.join(path, part)
            held.append(_win_open_dir(path))
            seen = held[-1][0]
            if getattr(seen, "st_file_attributes", 0) & _REPARSE_POINT:
                raise OSError(errno.ELOOP, "a link sits where a checked directory was")
            if not stat.S_ISDIR(seen.st_mode):
                raise OSError(errno.ENOTDIR, "something other than a directory sits where one was checked")
            if not seen.st_ino:
                raise OSError(errno.EIO, "could not tell whether this is the directory the vault checks found: "
                                         "the file system reports no file id; nothing written")
            if index == 0 and (seen.st_dev, seen.st_ino) != paths["vaultId"]:
                raise OSError(errno.ESTALE, "the vault is not the directory that was checked")
            if index:
                _match_component(seen, ids[index - 1], "/".join(parts[:index]))
    except BaseException:
        _release(held)
        raise
    return held


def _release(held):
    for _seen, close in reversed(held):
        close()


def _open_pinned(paths, label):
    """What holds the directory for `paths[label]` in place: on POSIX an fd on
    it, reached from the vault it checked one real component at a time, never
    through a link; on Windows the `_hold_dirs` handles.

    The components are the REAL path's, so a boardDir that is a link inside the
    vault still works; what cannot happen is a component that became a link
    after `_vault_paths` resolved it. The vault and each component are matched
    by device and inode against the ones checked, so a real directory renamed
    away and replaced by another is refused too (T-0081).
    """
    if not _DIR_FD:
        return _hold_dirs(paths, label)
    parts = _components(paths, label)
    ids = _recorded_ids(paths, label, parts)
    fd = os.open(paths["vault"], _DIR_FLAGS)
    try:
        seen = os.fstat(fd)
        _could_not_tell(seen, paths["vaultId"], "the vault")
        if (seen.st_dev, seen.st_ino) != paths["vaultId"]:
            raise OSError(errno.ESTALE, "the vault is not the directory that was checked")
        for depth, (part, want) in enumerate(zip(parts, ids), 1):
            inner = os.open(part, _DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = inner
            _match_component(os.fstat(fd), want, "/".join(parts[:depth]))
    except BaseException:
        os.close(fd)
        raise
    return fd


def _pinned_check(paths, label, fd):
    """Where the directory is pinned (POSIX): why the directory `fd` holds is no
    longer the one a fresh walk from the checked vault reaches, or None.

    The fd follows its directory wherever it goes: renamed out of the vault
    after the walk, it would take the write with it. So the walk is repeated
    and the two compared by device and inode, before the temp is written,
    before the replace and after it. A move between the last check and the
    replace is the residual race README names, as on Windows.
    """
    shown = paths[label + "Shown"]
    held = os.fstat(fd)

    def check():
        try:
            again = _open_pinned(paths, label)
        except OSError as exc:
            return (f"{shown}: its directory is no longer where the vault checks found it "
                    f"({exc.strerror or exc}); nothing written through it")
        try:
            seen = os.fstat(again)
        finally:
            os.close(again)
        if (seen.st_dev, seen.st_ino) != (held.st_dev, held.st_ino):
            return f"{shown}: its directory left the vault after the checks; nothing written through it"
        return None
    return check


def _held_check(paths, label, held):
    """Where the directories are held by handle (Windows): why the path no
    longer reaches the held directory, or None. Held, it cannot have moved; this
    is the belt to that pair of braces, and runs at the same three points."""
    shown = paths[label + "Shown"]
    folder = os.path.dirname(paths[label])
    want = (held[-1][0].st_dev, held[-1][0].st_ino)

    def check():
        try:
            seen = os.stat(folder)
        except OSError as exc:
            return (f"{shown}: its directory is no longer where the vault checks found it "
                    f"({exc.strerror or exc}); nothing written through it")
        if (seen.st_dev, seen.st_ino) != want:
            return f"{shown}: its directory left the vault after the checks; nothing written through it"
        return None
    return check


@contextlib.contextmanager
def _pinned(paths, label):
    """`(name, dir_fd, check)` to write `paths[label]` with, `check` running
    around every write: on POSIX a name in a pinned directory fd and a re-walk;
    on Windows the path, its directories held un-renameable by handle, and a
    re-check. A platform with neither is refused -- a path-only re-check is
    passed by a directory renamed away and replaced, so it is no guard."""
    if not _DIR_FD:
        if not _WIN_PIN:
            raise OSError(errno.EOPNOTSUPP, "could not tell whether its directory stays in the vault: this "
                                            "platform can neither pin a directory fd nor hold one by handle; "
                                            "nothing written")
        held = _open_pinned(paths, label)
        try:
            yield paths[label], None, _held_check(paths, label, held)
        finally:
            _release(held)
        return
    fd = _open_pinned(paths, label)
    try:
        yield os.path.basename(paths[label]), fd, _pinned_check(paths, label, fd)
    finally:
        os.close(fd)


def _board_write(paths, columns, edit):
    """Atomic board update: `edit(board) -> (text, result)`, recomputed per try."""
    def compute(old):
        text, problem = _decode(old, paths["boardShown"])
        board, problem = (None, problem) if problem else parse_board(text or "", columns)
        if problem:
            return None, _result("obsidian", FAILED, problem)
        new, result = edit(board)
        if new is None or new == text:
            return None, result
        return new.encode("utf-8"), result

    try:
        with _pinned(paths, "board") as (name, fd, check):
            return _atomic_update(name, paths["boardShown"], "obsidian", compute, dir_fd=fd, check=check)
    except OSError as exc:
        return _result("obsidian", FAILED, _moved(paths["boardShown"], exc))


def _note_text(root, ticket, title, ident):
    folder = os.path.join(os.path.realpath(root), ".work", "tickets", ticket)
    return (f"---\ntitle: {json.dumps(title)}\ncreated: {datetime.date.today().isoformat()}\n---\n\n"
            f"# {ticket} {title}\n\n"
            f"- repo: {repo_name(root)}\n"
            f"- repo-id: {ident}\n"
            f"- ticket: [.work/tickets/{ticket}/]({pathlib.Path(folder).as_uri()}/)\n")


def _create_note_once(paths, text):
    """The ticket note, written once and never rewritten. Exclusive create is the
    whole guard: the text is built before the open, and O_EXCL refuses an
    existing note (or a dangling link) instead of truncating it."""
    data = text.encode("utf-8")
    try:
        with _pinned(paths, "note") as (name, fd, check):
            moved = check()
            if moved:
                return _result("obsidian-note", FAILED, moved)
            _write_new(name, _NOTE_FLAGS, data, _ownership(name, fd), fd)
            moved = check()
            if moved and fd is None:
                return _result("obsidian-note", FAILED, f"{moved}; the note may have landed there")
            if moved:
                # Through the fd, so it is the file this call made, wherever its
                # directory went; by path it could be someone else's.
                _discard(name, fd)
                return _result("obsidian-note", FAILED, f"{moved}; the note written there is removed")
    except FileExistsError:
        return _result("obsidian-note", UNCHANGED, f"{paths['noteShown']} exists; never rewritten")
    except OSError as exc:
        return _result("obsidian-note", FAILED, _moved(paths["noteShown"], exc))
    return _result("obsidian-note", UPDATED, f"{paths['noteShown']} created")


# A card is `- [ ] [[T-0042]] <title>` and says nothing about which repo made
# it, and with boardDir unset every repo writes one `<vault>/Board.md`. The
# ticket note does say: `create` writes `- repo-id: <repo_id>` into it -- the
# origin URL or the git common dir, never the directory's name, which `a/app`
# and `b/app` share. So the note is the card's owner:
#
#   ours     the note's repo-id is this repo's          create, move, read go ahead
#   foreign  it names another                           all three refuse
#   unknown  no note, a note with no repo-id, unreadable create and move refuse;
#                                                       read says so on its line
#
# Unknown is never "ours", and nothing on a shared board can make it so: ids
# start over in every repo and titles repeat ("Fix tests"), so a card's text
# matching this repo's INDEX row is not evidence (review round 3). The human
# puts `repo-id:` in the note; an existing note is never rewritten.
# `\r` is trailing space here: `$` under re.M stops before `\n` only, so a
# CRLF note would otherwise carry the `\r` into the id and read as foreign.
_NOTE_REPO_ID = re.compile(r"^(?:- )?repo-id:[ \t]*['\"]?(.+?)['\"]?[ \t\r]*$", re.M)
OURS, FOREIGN, UNKNOWN = "ours", "foreign", "unknown"


def _card_owner(paths, here, label="note"):
    """`(OURS|FOREIGN|UNKNOWN, detail, note_exists)`; detail is the note's
    repo-id for FOREIGN and why it cannot be told for UNKNOWN. `label` is the
    note `_note_where` found: the live one, or `archivedNote` (L-0509)."""
    shown = paths[label + "Shown"]
    try:
        raw = _read_bytes(paths[label])
    except OSError as exc:
        return UNKNOWN, f"{shown}: {exc.strerror or exc}", True
    if raw is None:
        return UNKNOWN, f"no {shown} note names its repo-id", False
    text, problem = _decode(raw, shown)
    found = set() if problem else set(_NOTE_REPO_ID.findall(text))
    if len(found) != 1:
        why = problem or (f"{shown} names no repo-id" if not found
                          else f"{shown} names {len(found)} repo-ids")
        return UNKNOWN, why, True
    owner = found.pop()
    return (OURS, owner, True) if owner == here else (FOREIGN, owner, True)


def _note_names(settings, ticket):
    """The board, the live note and the archived note, for `_vault_paths`."""
    return [("board", settings["board"]), ("note", f"{ticket}.md"),
            ("archivedNote", f"{ticket}.md", crew_common.ARCHIVE_DIR)]


def _note_where(paths):
    """`(where, why)`: the ticket note live (`<boardDir>/<ID>.md`), archived
    (`<boardDir>/Complete/<ID>.md`), absent, or could not tell -- both present,
    or an `lstat` that failed with anything but not-found (L-0509). An unknown
    never reads as absent."""
    seen = {}
    for label in ("note", "archivedNote"):
        try:
            os.lstat(paths[label])
            seen[label] = True
        except (FileNotFoundError, NotADirectoryError):
            seen[label] = False
        except OSError as exc:
            return crew_common.COULD_NOT_TELL, f"{paths[label + 'Shown']}: {exc.strerror or exc}"
    if seen["note"] and seen["archivedNote"]:
        return crew_common.COULD_NOT_TELL, (f"both {paths['noteShown']} and "
                                            f"{paths['archivedNoteShown']} exist")
    if seen["archivedNote"]:
        return crew_common.COMPLETE, None
    return (crew_common.LIVE if seen["note"] else crew_common.ABSENT), None


def _archived(ticket):
    return (f"{ticket} is archived in {crew_common.ARCHIVE_DIR}/; move its folder and note "
            "back by hand to reopen it")


def _foreign(paths, ticket, owner, here):
    return (f"{ticket} on {paths['boardShown']} belongs to another repo ({owner}, per "
            f"{paths['noteShown']}), not this one ({here}): give this repo its own obsidian.boardDir")


def _unclaimed(paths, ticket, why, here):
    return (f"could not tell whose card {ticket} is ({why}); if it is this repo's, "
            f"put 'repo-id: {here}' in {paths['noteShown']}")


def _no_identity(root):
    return (f"could not tell this repo's identity: git gave neither an origin URL nor a common dir "
            f"for {os.path.realpath(root)}")


def _index_holds(root, ticket):
    """Why INDEX refuses `ticket` to `create` right now, or None. Read before the
    vault is resolved, so a vault failure never hides a held id (review round
    4); `_files_create` checks again under its atomic update."""
    try:
        raw = _read_bytes(os.path.join(root, ".work", "INDEX.md"))
    except OSError as exc:
        return f"{INDEX_REL}: {exc.strerror or exc}"
    text, problem = _decode(raw, INDEX_REL)
    if problem:
        return problem
    lines = text.splitlines()
    held = [_cells(lines[i]) for i in _rows(lines, ticket)]
    return _held(ticket, held) if held else None


def _lost_claim(paths, ticket, here):
    """Why a note that appeared after the owner check makes the id taken."""
    owner, detail, _ = _card_owner(paths, here)
    if owner == FOREIGN:
        return _foreign(paths, ticket, detail, here)
    if owner == UNKNOWN:
        return _unclaimed(paths, ticket, detail, here)
    return f"{paths['noteShown']} was created by another session after this one checked"


def _obsidian_create(root, settings, ticket, title):
    columns = settings["columns"]
    held = _index_holds(root, ticket)
    if held:
        return [_result("files", FAILED, held)]
    here = repo_id(root)
    paths, problem = _vault_paths(root, settings, _note_names(settings, ticket))
    if not problem and here is None:
        problem = _no_identity(root)
    board, problem = (None, problem) if problem else _load_board(paths, columns)
    note = False
    where, why = (None, None) if problem else _note_where(paths)
    if where == crew_common.COMPLETE:
        problem = f"{TAKEN}: {ticket}'s note is archived at {paths['archivedNoteShown']}"
    elif where == crew_common.COULD_NOT_TELL:
        problem = f"{TAKEN}: could not tell where {ticket}'s note lives: {why}"
    if not problem:
        owner, detail, note = _card_owner(paths, here)
        if owner == FOREIGN:
            problem = f"{TAKEN}: " + _foreign(paths, ticket, detail, here)
        elif owner == UNKNOWN and (note or any(card["id"] == ticket for card in _cards(board))):
            problem = f"{TAKEN}: " + _unclaimed(paths, ticket, detail, here)
    if problem:
        return [_result("obsidian", FAILED, problem)]
    # The claim is the note's exclusive creation, before anything else is
    # written (review round 4): another repo's create between the owner check
    # above and this open makes it fail, so the id is taken and nothing follows.
    # A note that was already this repo's is not claimed again -- it is never
    # rewritten -- and the INDEX row decides, under its atomic update.
    if note:
        claim = _result("obsidian-note", UNCHANGED, f"{paths['noteShown']} exists; never rewritten")
    else:
        claim = _create_note_once(paths, _note_text(root, ticket, title, here))
        if claim["state"] == UNCHANGED:
            return [_result("obsidian", FAILED, f"{TAKEN}: " + _lost_claim(paths, ticket, here))]
        if claim["state"] == FAILED:
            return [claim]
    files = _files_create(root, ticket, title)
    if files["state"] == FAILED:
        return [files, claim]

    def edit(current):
        new, _ = add_card(current, ticket, title, LANE_FOR_STATUS["direction"])
        if new == "".join(current["lines"]):
            return None, _result("obsidian", UNCHANGED, f"{paths['boardShown']} already has {ticket}")
        return new, _result("obsidian", UPDATED, f"{paths['boardShown']} card added to {columns['backlog']}")

    return [files, _board_write(paths, columns, edit), claim]


def _obsidian_move(root, settings, ticket, status, reopen=False):
    columns, key = settings["columns"], LANE_FOR_STATUS[status]
    here = repo_id(root)
    paths, problem = _vault_paths(root, settings, _note_names(settings, ticket))
    where, why = (None, None) if problem else _note_where(paths)
    if where == crew_common.COMPLETE:
        problem = _archived(ticket)
    elif where == crew_common.COULD_NOT_TELL:
        problem = f"could not tell where {ticket}'s note lives: {why}"
    row = None if problem else _files_read(root, ticket)
    if not problem and row["state"] != READ:
        problem = f"no {INDEX_REL} row for {ticket} in this repo"
    if not problem and here is None:
        problem = _no_identity(root)
    board, problem = (None, problem) if problem else _load_board(paths, columns)
    if not problem:
        _, problem = find_card(board, ticket)
    if not problem:
        owner, detail, _ = _card_owner(paths, here)
        if owner == FOREIGN:
            problem = _foreign(paths, ticket, detail, here)
        elif owner == UNKNOWN:
            problem = _unclaimed(paths, ticket, detail, here)
    if problem:
        return [_result("obsidian", FAILED, problem)]

    def edit(current):
        new, moved_from, why = move_card(current, ticket, key)
        if why:
            return None, _result("obsidian", FAILED, why)
        if moved_from == columns[key] and new == "".join(current["lines"]):
            return None, _result("obsidian", UNCHANGED, f"{paths['boardShown']} already in {moved_from}")
        if moved_from == columns[key]:
            return new, _result("obsidian", UPDATED, f"{paths['boardShown']} card repaired in {moved_from}")
        return new, _result("obsidian", UPDATED, f"{paths['boardShown']} {moved_from} -> {columns[key]}")

    # The board follows INDEX: when the INDEX half refuses -- another session
    # moved the ticket on after the read above -- the board is not moved either.
    files = _files_move(root, ticket, status, reopen)
    if files["state"] == FAILED:
        return [files]
    return [files, _board_write(paths, columns, edit)]


def _obsidian_read(root, settings, ticket):
    files = _files_read(root, ticket)
    here = repo_id(root)
    paths, problem = _vault_paths(root, settings, _note_names(settings, ticket))
    if not problem and here is None:
        problem = _no_identity(root)
    where, why = (None, None) if problem else _note_where(paths)
    if where == crew_common.COULD_NOT_TELL:
        problem = f"could not tell where {ticket}'s note lives: {why}"
    board, problem = (None, problem) if problem else _load_board(paths, settings["columns"])
    card, problem = (None, problem) if problem else find_card(board, ticket)
    label = "archivedNote" if where == crew_common.COMPLETE else "note"
    if where == crew_common.COMPLETE and problem == f"no card for {ticket} on the board":
        owner, detail, _ = _card_owner(paths, here, label)
        if owner == FOREIGN:
            return [files, _result("obsidian", UNREADABLE, _foreign(paths, ticket, detail, here))]
        # UNKNOWN keeps its doubt in the result, as the live branch below does.
        doubt = f"; whose note could not tell: {detail}" if owner == UNKNOWN else ""
        return [files, _result("obsidian", READ,
                               f"archived; INDEX status {files.get('status')}{doubt}",
                               lane=f"{crew_common.ARCHIVE_DIR}/", archived=True, disagree=False)]
    owner, detail = None, None
    if not problem:
        owner, detail, _ = _card_owner(paths, here, label)
        if owner == FOREIGN:
            problem = _foreign(paths, ticket, detail, here)
    if problem:
        return [files, _result("obsidian", UNREADABLE, problem)]
    status = files.get("status")
    expected = settings["columns"].get(LANE_FOR_STATUS.get(status, ""), None)
    disagree = card["lane"] != expected
    notes = [f"INDEX status {status} expects {expected}"] if disagree else []
    notes += [f"whose card could not tell: {detail}"] if owner == UNKNOWN else []
    return [files, _result("obsidian", READ, "; ".join(notes) or None, lane=card["lane"], disagree=disagree)]


# --- archive (L-0509) ------------------------------------------------------------

ARCHIVE_STATUSES = ("done", "merged")
_TICKETS_REL = ".work/tickets"


def _active_holder(root, ticket):
    """Why `ticket` may not be archived because a worktree has it active, or
    None. The map is `<git-common-dir>/crew/active-ticket`, worktree -> id; one
    that cannot be read is could-not-tell, never "no pointer"."""
    common = _common_dir(root)
    if common is None:
        return f"could not tell whether a worktree has {ticket} active: git named no common dir"
    path = os.path.join(common, "crew", "active-ticket")
    try:
        raw = _read_bytes(path)
    except OSError as exc:
        return f"could not tell whether a worktree has {ticket} active: {path}: {exc.strerror or exc}"
    if raw is None:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError:
        data = None
    if not isinstance(data, dict):
        return f"could not tell whether a worktree has {ticket} active: {path} does not parse"
    holders = sorted(str(top) for top, held in data.items() if held == ticket)
    if holders:
        return (f"{ticket} is the active ticket of the worktree at {', '.join(holders)}; "
                "deactivate it there first")
    return None


def _files_archive(root, ticket):
    """The folder half: `.work/tickets/<ID>` -> `.work/tickets/Complete/<ID>`."""
    backend = "folder"
    live_rel = f"{_TICKETS_REL}/{ticket}"
    done_rel = f"{_TICKETS_REL}/{crew_common.ARCHIVE_DIR}/{ticket}"
    folder, where, why = crew_common.locate_ticket(root, ticket)
    if where == crew_common.COMPLETE:
        return _result(backend, UNCHANGED, f"{done_rel} already archived")
    if where == crew_common.COULD_NOT_TELL:
        return _result(backend, FAILED, f"could not tell where {ticket} lives: {why}")
    if where == crew_common.ABSENT:
        return _result(backend, FAILED, f"no folder for {ticket} at {live_rel}")
    archive = os.path.join(crew_common.tickets_root(root), crew_common.ARCHIVE_DIR)
    try:
        os.makedirs(archive, exist_ok=True)
        # Never shutil.move: a cross-device move would copy. And never a bare
        # os.rename on POSIX: it replaces an empty directory that appeared
        # since the check. `_rename_dir_no_replace` claims the name first.
        _rename_dir_no_replace(folder, os.path.join(archive, ticket))
    except FileExistsError:
        return _result(backend, FAILED, f"{done_rel} already exists; nothing moved")
    except OSError as exc:
        return _result(backend, FAILED, f"{live_rel}: {exc.strerror or exc}; nothing moved")
    return _result(backend, UPDATED, f"{live_rel} -> {done_rel}")


def _rename_dir_no_replace(src, dst):
    """Rename directory `src` to `dst`, raising FileExistsError when `dst`
    exists, with no window in which another process's `dst` is replaced.
    Windows' rename never replaces. On POSIX the name is claimed with an
    atomic `mkdir` first and the rename then replaces only that empty
    directory we made; if anything was put inside it meanwhile the rename
    fails (ENOTEMPTY) and the claim is released."""
    if os.name == "nt":
        os.rename(src, dst)
        return
    os.mkdir(dst)
    try:
        os.rename(src, dst)
    except OSError:
        with contextlib.suppress(OSError):
            os.rmdir(dst)
        raise


def _rename_file_no_replace(src, dst, src_dir_fd=None, dst_dir_fd=None):
    """Rename file `src` to `dst`, raising FileExistsError when `dst` exists,
    atomically: a hard link cannot replace (EEXIST), then the old name goes.
    Windows' rename never replaces. A filesystem with no hard links falls
    back to a re-check and rename, the one remaining window."""
    if os.name == "nt":
        os.rename(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)
        return
    try:
        os.link(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd,
                follow_symlinks=False)
    except OSError as exc:
        no_links = (errno.EPERM, errno.EOPNOTSUPP, errno.ENOTSUP, errno.EMLINK, errno.EXDEV)
        if isinstance(exc, FileExistsError) or exc.errno not in no_links:
            raise
        try:
            os.stat(dst, dir_fd=dst_dir_fd, follow_symlinks=False)
        except FileNotFoundError:
            os.rename(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)
            return
        raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), dst) from exc
    os.unlink(src, dir_fd=src_dir_fd)


def _rename_note(paths):
    """Move the live note into `<boardDir>/Complete/` through the pinned
    directory walk; the archive folder is created and entered without
    following a link, and an existing destination is refused."""
    shown, dest = paths["noteShown"], paths["archivedNoteShown"]
    try:
        with _pinned(paths, "note") as (name, fd, check):
            stale = check()
            if stale:
                return _result("obsidian-note", FAILED, stale)
            if fd is not None:
                with contextlib.suppress(FileExistsError):
                    os.mkdir(crew_common.ARCHIVE_DIR, dir_fd=fd)
                inner = os.open(crew_common.ARCHIVE_DIR, _DIR_FLAGS, dir_fd=fd)
                try:
                    if _exists_at(name, inner):
                        return _result("obsidian-note", FAILED, f"could not tell which note is "
                                       f"{os.path.basename(name)[:-3]}'s: {dest} already exists")
                    try:
                        _rename_file_no_replace(name, name, src_dir_fd=fd, dst_dir_fd=inner)
                    except FileExistsError:
                        return _result("obsidian-note", FAILED, f"could not tell which note is "
                                       f"{os.path.basename(name)[:-3]}'s: {dest} already exists")
                finally:
                    os.close(inner)
            else:
                folder = os.path.join(os.path.dirname(name), crew_common.ARCHIVE_DIR)
                with contextlib.suppress(FileExistsError):
                    os.mkdir(folder)
                if os.path.islink(folder) or not os.path.isdir(folder):
                    return _result("obsidian-note", FAILED, f"{dest}: its folder is not a directory")
                if os.path.lexists(paths["archivedNote"]):
                    return _result("obsidian-note", FAILED, f"could not tell which note is the "
                                   f"ticket's: {dest} already exists")
                try:
                    _rename_file_no_replace(name, paths["archivedNote"])
                except FileExistsError:
                    return _result("obsidian-note", FAILED, f"could not tell which note is the "
                                   f"ticket's: {dest} already exists")
            stale = check()
            if stale:
                return _result("obsidian-note", FAILED, f"{stale}; the note may have moved")
    except OSError as exc:
        return _result("obsidian-note", FAILED, _moved(shown, exc))
    return _result("obsidian-note", UPDATED, f"{shown} -> {dest}")


def _exists_at(name, dir_fd):
    try:
        os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def _obsidian_archive_checks(root, settings, ticket):
    """`(paths, where, None)` or `(None, None, problem)`: every vault check the
    note and board halves need, run before the folder half moves anything."""
    here = repo_id(root)
    paths, problem = _vault_paths(root, settings, _note_names(settings, ticket))
    if not problem and here is None:
        problem = _no_identity(root)
    board, problem = (None, problem) if problem else _load_board(paths, settings["columns"])
    if not problem:
        _, why = remove_card(board, ticket)
        problem = None if why == "absent" else why
    where, why = (None, None) if problem else _note_where(paths)
    if where == crew_common.COULD_NOT_TELL:
        problem = f"could not tell where {ticket}'s note lives: {why}"
    if not problem:
        label = "archivedNote" if where == crew_common.COMPLETE else "note"
        owner, detail, _ = _card_owner(paths, here, label)
        if owner != OURS:
            problem = (_foreign if owner == FOREIGN else _unclaimed)(paths, ticket, detail, here)
    return (None, None, problem) if problem else (paths, where, None)


def _obsidian_archive(settings, ticket, paths, where):
    """The note half, then the card half; a failed note half stops the card."""
    columns = settings["columns"]
    if where == crew_common.COMPLETE:
        note = _result("obsidian-note", UNCHANGED, f"{paths['archivedNoteShown']} already archived")
    else:
        note = _rename_note(paths)
        if note["state"] == FAILED:
            return [note]

    def edit(current):
        new, why = remove_card(current, ticket)
        if why == "absent":
            return None, _result("obsidian", UNCHANGED, f"{paths['boardShown']} has no card for {ticket}")
        if why:
            return None, _result("obsidian", FAILED, why)
        return new, _result("obsidian", UPDATED, f"{paths['boardShown']} card removed from {columns['done']}")

    return [note, _board_write(paths, columns, edit)]


def archive(root, ticket):
    """Archive ONE done or merged ticket: folder, then note, then card (module
    docstring, "Archive"). Never edits INDEX.md."""
    info = resolve(root)
    stop = _gate(info)
    if stop:
        return _report(info, [stop])
    kind = info["kind"]
    row = _files_read(root, ticket)
    if row["state"] != READ:
        return _report(info, [_result("files", FAILED, row["reason"])])
    if row["status"] not in ARCHIVE_STATUSES:
        return _report(info, [_result("files", FAILED, f"{ticket} is {row['status']}; only a done or "
                                      "merged ticket is archived")])
    held = _active_holder(root, ticket)
    if held:
        return _report(info, [_result("files", FAILED, held)])
    paths = where = None
    if kind == "obsidian":
        paths, where, problem = _obsidian_archive_checks(root, info["settings"], ticket)
        if problem:
            return _report(info, [_result("obsidian", FAILED, problem)])
    results = [_files_archive(root, ticket)]
    if results[0]["state"] == FAILED:
        return _report(info, results)
    if kind == "obsidian":
        results += _obsidian_archive(info["settings"], ticket, paths, where)
    elif kind in _SYNC:
        results.append(_result("tracker", NOT_APPLICABLE, None, line=(
            f"tracker: not applicable: {kind} has no board to archive from; the folder only")))
    return _report(info, results)


def _folder_refusal(root, ticket):
    """Why `move` refuses `ticket` because of where its folder is, or None."""
    _, where, why = crew_common.locate_ticket(root, ticket)
    if where == crew_common.COMPLETE:
        return _archived(ticket)
    if where == crew_common.COULD_NOT_TELL:
        return f"could not tell where {ticket} lives: {why}"
    return None


# --- the interface -------------------------------------------------------------

def _delegated(kind, ticket, to=None):
    command = f"{_SYNC[kind]} {ticket}" + (f" --push --to {to}" if to else "")
    return _result(kind, DELEGATED, f"run {command}", command)


def _push(kind, ticket, status):
    """Jira and SDP push at the boundaries only, naming the target status."""
    if status in _PUSH_AT:
        return _delegated(kind, ticket, status)
    return _result("tracker", NOT_APPLICABLE, None, line=(
        f"tracker: {kind} syncs at boundaries only ({', '.join(_PUSH_AT)}); nothing to push"))


def create(root, ticket, title):
    """Mint the ticket in the tracker: the INDEX row, and for obsidian the card and note."""
    info = resolve(root)
    stop = _gate(info)
    if stop:
        return _report(info, [stop])
    kind = info["kind"]
    # Before the Jira/SDP delegation too: an archived id is taken whatever
    # the tracker (port review of L-0509).
    _, where, why = crew_common.locate_ticket(root, ticket)
    if where == crew_common.COMPLETE:
        return _report(info, [_result(kind, FAILED, f"{TAKEN}: {ticket} is archived in "
                                      f"{crew_common.ARCHIVE_DIR}/")])
    if where == crew_common.COULD_NOT_TELL:
        return _report(info, [_result(kind, FAILED, f"{TAKEN}: could not tell where {ticket} lives: {why}")])
    if kind in _SYNC:
        return _report(info, [_result(kind, DELEGATED, _CREATE_DELEGATED)])
    if not title_ok(title):
        return _report(info, [_result(kind, FAILED, "title must be one line with no '|'")])
    if kind == "obsidian":
        return _report(info, _obsidian_create(root, info["settings"], ticket, title))
    return _report(info, [_files_create(root, ticket, title)])


def move(root, ticket, status, reopen=False):
    """Move the ticket to `status` in every half of the configured tracker.
    A move backwards by STATUS_ORDER, or out of a closed word, needs `reopen`."""
    info = resolve(root)
    stop = _gate(info)
    if stop:
        return _report(info, [stop])
    kind = info["kind"]
    if status not in LANE_FOR_STATUS:
        return _report(info, [_result(kind, FAILED, f"status {status} maps to no lane")])
    # Before the Jira/SDP push too: an archived ticket is closed whatever the
    # tracker (port review of L-0509).
    refused = _folder_refusal(root, ticket)
    if refused:
        return _report(info, [_result(kind, FAILED, refused)])
    if kind in _SYNC:
        return _report(info, [_push(kind, ticket, status)])
    if kind == "obsidian":
        return _report(info, _obsidian_move(root, info["settings"], ticket, status, reopen))
    return _report(info, [_files_move(root, ticket, status, reopen)])


def read(root, ticket):
    """The ticket's status in every half of the configured tracker."""
    info = resolve(root)
    kind = info["kind"]
    if kind == COULD_NOT_TELL:
        return _report(info, [_result("tracker", UNREADABLE, "tracker kind could not tell: "
                                      + "; ".join(info["problems"]))])
    if kind == NOT_CONFIGURED:
        return _report(info, [_gate(info)])
    if kind in _SYNC:
        return _report(info, [_delegated(kind, ticket)])
    if kind == "obsidian":
        return _report(info, _obsidian_read(root, info["settings"], ticket))
    return _report(info, [_files_read(root, ticket)])


# --- CLI -------------------------------------------------------------------------

def _line(result):
    if result.get("line"):
        return result["line"]
    if result["state"] == READ:
        extra = result.get("status") if "status" in result else result.get("lane")
        return f"{result['backend']}: {extra}" + (f" ({result['reason']})" if result["reason"] else "")
    text = f"{result['backend']}: {result['state']}"
    return text + (f": {result['reason']}" if result["reason"] else "")


def describe(info):
    """One human line for a resolve() answer."""
    if info["kind"] == COULD_NOT_TELL:
        return "could not tell - " + "; ".join(info["problems"])
    if info["kind"] == NOT_CONFIGURED:
        return "not configured (no tracker in .crew/crew.json or .crew/config.json)"
    return f"{info['kind']} (from .crew/{info['source']})"


def main(argv=None):
    parser = argparse.ArgumentParser(description="crew's one tracker interface")
    parser.add_argument("action", choices=("resolve", "create", "move", "read", "archive"))
    parser.add_argument("--root", default=".")
    parser.add_argument("--ticket")
    parser.add_argument("--title")
    parser.add_argument("--to", dest="status")
    parser.add_argument("--reopen", action="store_true",
                        help="allow a move backwards by STATUS_ORDER (done -> in-progress), "
                             "or out of done, cancelled or superseded")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    if args.action == "resolve":
        info = resolve(root)
        print(json.dumps(info, indent=2, sort_keys=True) if args.json else "tracker " + describe(info))
        return 1 if info["kind"] == COULD_NOT_TELL else 0
    if not args.ticket or not _TICKET_ID.match(args.ticket):
        parser.error("--ticket must be a ticket id like T-0042 or L-0509")
    if args.action == "create":
        if not args.title:
            parser.error("create needs --title")
        report = create(root, args.ticket, args.title)
    elif args.action == "move":
        if not args.status:
            parser.error("move needs --to <status>")
        report = move(root, args.ticket, args.status, args.reopen)
    elif args.action == "archive":
        report = archive(root, args.ticket)
    else:
        report = read(root, args.ticket)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for result in report["results"]:
            print(_line(result))
    return exit_code(report)


if __name__ == "__main__":
    sys.exit(main())
