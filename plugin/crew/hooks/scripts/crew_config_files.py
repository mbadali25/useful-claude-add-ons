"""The one file layer under crew's config writers, delete and restore (T-0075).

Both config writers (`crew_config.write_global_config`,
`crew_config.write_repo_config`) and the menu's repo-config delete and restore
(`crew_config_menu.py`) stand on the constructions here, so each exists once:

  * `Lock` -- an `O_CREAT | O_EXCL` lock file beside the config, the
    `review_ledger._Lock` construction (portable: no `fcntl`, no `msvcrt`).
    It serialises crew's own writers against each other. A foreign writer (a
    hand edit, an editor's save) is not serialised by it.
  * `read_strict` -- the four-case read (absent, unparsable, empty or
    non-object, ok), never the `{}` collapse `crew_state.load_config` makes.
  * `restorable` -- the ONE predicate delete and restore share: a file delete
    backs up is a file restore takes back, by construction.
  * `read_restorable` -- `read_strict` on a REGULAR file only (never a
    symlink, FIFO or directory), the one read delete and restore share.
  * `digest` / `state_digest` -- sha256 of the bytes, what a compare-and-swap
    compares; `state_digest` names an absent file `ABSENT`, so a first write
    can be compared against absence too.
  * `replace_text` / `replace_bytes` -- sibling, fsync, `os.replace`, so an
    interrupted write leaves the original intact; `replace_text` keeps the
    file's CRLF and UTF-8 BOM.
  * `update_json` -- read, compare, merge and replace inside the lock, so two
    writers never merge against stale snapshots.
  * `move_aside` / `move_no_clobber` -- the backup IS the original inode,
    moved without ever replacing an existing destination and without ever
    removing a file that replaced the source mid-move (review round 3).
  * `create_bytes` -- a new file, atomically, refusing an existing one.

No crew imports, so `crew_config` and `crew_config_menu` can both import it.
"""
import copy
import hashlib
import json
import os
import re
import secrets
import stat
import time

# How long `Lock` waits for another crew writer before refusing. A module
# attribute read at acquire time, so a test can shorten it.
LOCK_WAIT_SECONDS = 3.0

_BOM = b"\xef\xbb\xbf"

# The expected-digest token for "the file does not exist". A digest is 64
# lowercase hex, so the two cannot collide. Printed by every dry run whose
# file is absent, and accepted by every `--expect*` flag.
ABSENT = "absent"


class Unreadable(Exception):
    """The file is absent, unparsable, empty or not a JSON object.

    `kind` is one of `absent`, `unparsable`, `empty`, `notobject`."""

    def __init__(self, message, kind):
        super().__init__(message)
        self.kind = kind


class Busy(Exception):
    """Another crew writer holds the lock past the wait."""


class Conflict(Exception):
    """The file changed since the caller read it (its digest differs)."""


class Displaced(OSError):
    """A move found a foreign file at its source. `parked` is a name that
    holds it, KEPT: crew never removes it, since it may be that file's last
    name (review round 4). The message says whether the file is also back at
    the source."""

    def __init__(self, message, parked):
        super().__init__(message)
        self.parked = parked


def os_error_text(exc):
    """`str(exc)` for an OSError, with its paths as written rather than repr()'d.

    `str(OSError)` quotes the filename with repr(), which doubles every
    backslash in a Windows path, so a refusal would name a path the user
    cannot paste and a test cannot find."""
    if not isinstance(exc, OSError) or exc.filename is None:
        return str(exc)
    code = getattr(exc, "winerror", None)
    tag = f"[WinError {code}] " if code else (f"[Errno {exc.errno}] " if exc.errno else "")
    text = f"{tag}{exc.strerror or type(exc).__name__}: {exc.filename}"
    return text + (f" -> {exc.filename2}" if exc.filename2 is not None else "")


def _holder(lock_path):
    try:
        with open(lock_path, "rb") as handle:
            return handle.read(32).decode("ascii", "replace").strip() or "unknown"
    except OSError:
        return "unknown"


class Lock:
    """`<path>.lock`, created with `O_CREAT | O_EXCL`, the PID written inside.

    Waits `wait` seconds (default `LOCK_WAIT_SECONDS`) for a holder to finish,
    then raises `Busy` naming the lock file and the PID in it. A process that
    died holding it leaves the file; the message says to remove it by hand,
    the same rule as the review ledger's lock. A failed PID write never leaves
    one behind: the file is removed before the error is raised.
    """

    def __init__(self, path, wait=None):
        self.path = path + ".lock"
        self.wait = wait

    def __enter__(self):
        wait = LOCK_WAIT_SECONDS if self.wait is None else self.wait
        deadline = time.monotonic() + wait
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError as exc:
                if time.monotonic() >= deadline:
                    raise Busy(
                        f"{self.path} is held by pid {_holder(self.path)} "
                        f"(waited {wait:.1f}s); another crew command is "
                        "writing this config. If no crew command is running, "
                        "a process died holding it -- remove that file by "
                        "hand") from exc
                time.sleep(0.02)
                continue
            try:
                os.write(fd, str(os.getpid()).encode("ascii"))
            except BaseException:
                os.close(fd)
                try:
                    os.remove(self.path)
                except OSError:
                    pass
                raise
            os.close(fd)
            return self

    def __exit__(self, *exc):
        try:
            os.remove(self.path)
        except OSError:
            pass


def _parse(data, allow_empty=False):
    """`(parsed, None, None)` or `(None, problem, kind)` for `data`."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        return None, f"is not UTF-8 ({exc})", "unparsable"
    try:
        parsed = json.loads(text)
    except ValueError as exc:
        return None, f"does not parse as JSON ({exc})", "unparsable"
    if not isinstance(parsed, dict):
        return None, (f"holds a JSON {type(parsed).__name__}, not an object"
                      ), "notobject"
    if not parsed and not allow_empty:
        return None, "is an empty object {}", "empty"
    return parsed, None, None


def restorable(data):
    """None when `data` is a config a restore may put back (a non-empty JSON
    object, UTF-8 with or without a BOM, any line ending); else why not.

    Delete refuses what this refuses, and restore accepts what this accepts,
    so every backup delete makes is one restore takes back."""
    _parsed, problem, _kind = _parse(data)
    return problem


def read_strict(path, allow_empty=False):
    """`(parsed, raw_bytes)`, or raise `Unreadable` with its `kind`.

    `allow_empty` admits `{}` (the machine-global file may legitimately be
    one); the repo file never passes it."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except FileNotFoundError as exc:
        raise Unreadable(f"no {path}", "absent") from exc
    except OSError as exc:
        raise Unreadable(f"{path} cannot be read ({exc})", "unparsable") from exc
    parsed, problem, kind = _parse(raw, allow_empty)
    if problem:
        raise Unreadable(f"{path} {problem}", kind)
    return parsed, raw


def read_restorable(path):
    """`(parsed, raw_bytes)` of a REGULAR file holding a restorable config,
    or `Unreadable` (`absent`, `notregular`, or `restorable`'s kinds).

    The one read delete and restore share, so a file delete moves aside is a
    file restore takes back: a symlink is refused here rather than moved
    into a backup restore's location rule then rejects (review round 3), and
    a FIFO is refused before anything blocks reading it. Opened with
    `O_NOFOLLOW` and judged by `fstat`, so a swap between the check and the
    read cannot hand it another file's bytes."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(
        os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    try:
        if os.path.islink(path):
            raise OSError(f"{path} is a symlink")
        fd = os.open(path, flags)
    except FileNotFoundError as exc:
        raise Unreadable(f"no {path}", "absent") from exc
    except OSError as exc:
        raise Unreadable(f"{path} is not a regular file ({exc})",
                         "notregular") from exc
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise Unreadable(f"{path} is not a regular file", "notregular")
        chunks = []
        while True:
            chunk = os.read(fd, 1 << 16)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        os.close(fd)
    raw = b"".join(chunks)
    parsed, problem, kind = _parse(raw)
    if problem:
        raise Unreadable(f"{path} {problem}", kind)
    return parsed, raw


def digest(data):
    """sha256 hex of `data` (bytes)."""
    return hashlib.sha256(data).hexdigest()


def state_digest(raw):
    """`digest(raw)`, or `ABSENT` when `raw` is None (no file)."""
    return ABSENT if raw is None else digest(raw)


def is_expectation(value):
    """True for a value an `--expect*` flag may carry: 64 lowercase hex or
    `ABSENT`."""
    return value == ABSENT or (isinstance(value, str) and len(value) == 64
                               and all(c in "0123456789abcdef" for c in value))


def read_tolerant(path):
    """`(parsed, state_digest)` from ONE read, never raising: `path` parsed
    the way `crew_config.read_global_config` parses it (absent, broken or not
    an object is `{}`), and the digest that binds a plan to those bytes."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except FileNotFoundError:
        return {}, ABSENT
    except OSError:
        raw = b""
    try:
        parsed = json.loads(raw.decode("utf-8-sig", errors="replace"))
    except ValueError:
        parsed = {}
    return (parsed if isinstance(parsed, dict) else {}), digest(raw)


def machine_lock(path, wait=None):
    """`Lock(path)` on the machine-global file, creating its directory first
    (never the file): the lock is always taken, so a machine write cannot
    slip between a repo write's or a delete's read of it and their own write
    (review round 4). Take it before the repo lock -- crew's one order."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    return Lock(path, wait)


_DOTTED_RE = re.compile(r"^[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+)*$")


def is_dotted(path):
    """True for a dotted config path (`a.b.c`): no empty segment."""
    return isinstance(path, str) and bool(_DOTTED_RE.match(path))


def expectation_problem(flag, value):
    """Why `value` cannot be an `--expect*` flag's value, or None."""
    if value is None or is_expectation(value):
        return None
    return (f"{flag} must be a sha256 digest (64 lowercase hex) or "
            f"`{ABSENT}`, not {value!r}")


def parse_assignments(items):
    """`({PATH: value}, None)` from `PATH=JSON` strings, or `(None, why)`."""
    updates = {}
    for item in items:
        if "=" not in item:
            return None, f"--set expects PATH=JSON, got: {item}"
        key, raw = item.split("=", 1)
        key = key.strip()
        if not is_dotted(key):
            return None, f"--set: {key!r} is not a dotted path (a.b.c)"
        try:
            updates[key] = json.loads(raw)
        except ValueError:
            return None, (f"--set {key}: {raw!r} is not JSON; a string needs "
                          f"its quotes ({key}='\"{raw}\"')")
    return updates, None


def _fsync_dir(path):
    if os.name == "nt":
        return
    try:
        fd = os.open(os.path.dirname(os.path.abspath(path)), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def replace_bytes(path, data):
    """Write `data` to a PID-suffixed sibling, fsync it, `os.replace` it over
    `path`, then fsync the directory. The sibling is removed on any failure,
    so an interrupted write leaves the original intact."""
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass                # a stray temp is the lesser problem
        raise
    _fsync_dir(path)


def replace_text(path, text, raw_before):
    """`text` (LF line endings) written atomically, keeping `raw_before`'s
    CRLF and UTF-8 BOM, as platform-sync keeps them."""
    raw_before = raw_before or b""
    if b"\r\n" in raw_before:
        text = text.replace("\r\n", "\n").replace("\n", "\r\n")
    data = text.encode("utf-8")
    if raw_before.startswith(_BOM):
        data = _BOM + data
    replace_bytes(path, data)


def update_json(path, mutate, *, expect=None, create=False, wait=None):
    """Read, compare, merge and replace `path` inside its `Lock`.

    `mutate(parsed_copy)` returns the object to write, or None to write
    nothing. `expect` is the digest of the bytes the caller planned against;
    when the file's current `state_digest` differs, `Conflict` is raised and
    nothing is written -- a changed file is refused, never merged over.
    `expect=ABSENT` plans against a file that does not exist, so a first
    write refuses a file created since (review round 3). Without
    `expect` the merge is onto the bytes read under the lock. `create` lets
    an absent file be written from `{}` (the machine file's first write) and
    admits a `{}` file; the repo file never passes it.

    Returns `(result, raw_before)`, `result` being what `mutate` returned.
    Raises `Unreadable`, `Busy`, `Conflict`, or the OS error of the write.
    """
    parent = os.path.dirname(os.path.abspath(path))
    if create:
        os.makedirs(parent, exist_ok=True)
    elif not os.path.isdir(parent):
        raise Unreadable(f"no {path}", "absent")
    with Lock(path, wait):
        try:
            parsed, raw = read_strict(path, allow_empty=create)
        except Unreadable as exc:
            if not (create and exc.kind == "absent"):
                raise
            parsed, raw = {}, None
        current = state_digest(raw)
        if expect is not None and expect != current:
            raise Conflict(
                f"{path} changed since it was read (digest {current}, "
                f"expected {expect}); nothing written. Re-run to plan against "
                "the current file")
        result = mutate(copy.deepcopy(parsed))
        if result is None:
            return None, raw
        text = json.dumps(result, indent=2) + "\n"
        replace_text(path, text, raw)
        return result, raw


def _reserve(near):
    """A fresh empty file beside `near`, created `O_EXCL`: a name nobody else
    holds, which only this process's own rename may then replace."""
    while True:
        name = f"{near}.{os.getpid()}.{secrets.token_hex(4)}.moving"
        try:
            os.close(os.open(name, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return name
        except FileExistsError:
            continue


def _unlink_source(src, dest):
    """Remove the name `src` only if it still names `dest`'s inode (POSIX).

    There is no "unlink if this inode" call, so `src` is renamed onto a
    reserved name (replacing only this process's own placeholder) and
    compared there. The one unlink after that rename is of the reserved name
    when it IS the moved inode: `dest` names it too, so no bytes can go. A
    foreign file found there is put back with a no-clobber link and its
    reserved name is KEPT, never removed -- another writer may replace `src`
    again at any moment, making that name the file's last (review round 4).
    Once `src` is renamed, every failure is `Displaced`, so the caller never
    undoes its link to `dest`: the original may have no other name."""
    parked = _reserve(src)
    try:
        os.rename(src, parked)
    except FileNotFoundError:
        os.remove(parked)               # already gone: dest holds the inode
        return
    except BaseException:
        os.remove(parked)
        raise
    try:
        same = os.path.samestat(os.lstat(parked), os.lstat(dest))
    except OSError as exc:
        raise Displaced(
            f"{src} was moved to {parked} and could not be compared with "
            f"{dest} ({exc}); both are kept", parked) from exc
    if same:
        os.remove(parked)               # the second name of the moved inode
        return
    try:
        os.link(parked, src, follow_symlinks=False)
    except FileExistsError as exc:
        raise Displaced(
            f"a file replaced {src} during the move and another took its "
            f"place after; the first is kept at {parked}", parked) from exc
    except OSError as exc:
        raise Displaced(
            f"a file replaced {src} during the move and could not be put "
            f"back ({exc}); it is at {parked}, and the moved original is at "
            f"{dest}", parked) from exc
    raise Displaced(
        f"a file replaced {src} during the move; it is back at {src}, and a "
        f"second name for it is kept at {parked} (crew never removes a name "
        f"that may be another writer's last copy; delete it after checking "
        f"{src})", parked)


def move_no_clobber(src, dest):
    """Rename `src` to `dest` in one step that NEVER replaces `dest`.

    `FileExistsError` when `dest` exists, with `src` untouched -- by the
    rename itself, never by a check before it (review round 3: `lexists`
    then `os.replace` overwrote a file created in between). Windows'
    `os.rename` already refuses an existing destination. POSIX's replaces,
    so there it is `os.link` (which refuses) and then `_unlink_source`,
    which removes `src` only while it still names the linked inode. A
    filesystem without hard links refuses with its `OSError`; nothing moved.
    The link is undone only for a failure before `src` was renamed:
    `Displaced` (every failure after it) passes through with `dest` kept.
    """
    if os.name == "nt":
        os.rename(src, dest)
    else:
        os.link(src, dest, follow_symlinks=False)
        try:
            _unlink_source(src, dest)
        except Displaced:
            raise
        except BaseException:
            try:
                os.remove(dest)         # undo the link: src still names it
            except OSError:
                pass
            raise
    _fsync_dir(dest)


def _regular_bytes(path):
    """The bytes of `path` if it is a regular file, else None (a symlink, a
    FIFO or a directory is never read through)."""
    try:
        return read_restorable(path)[1]
    except Unreadable as exc:
        if exc.kind in ("absent", "notregular"):
            return None
        with open(path, "rb") as handle:
            return handle.read()


def move_aside(src, dest):
    """`move_no_clobber(src, dest)`, then `dest`'s bytes (None when what
    moved is not a regular file). The caller holds `src`'s `Lock`. The
    backup is the original inode: no copy, no moment in which the bytes are
    at neither name, and never a replaced destination."""
    move_no_clobber(src, dest)
    return _regular_bytes(dest)


def create_bytes(path, data):
    """Write `data` as a NEW file at `path`: a fsynced sibling, then
    `move_no_clobber`, so `path` never holds a partial file and a file that
    appeared at `path` meanwhile is never replaced (`FileExistsError`, the
    sibling removed). Restore's write (review round 3's neighbouring case:
    it replaced whatever platform-sync healed in between)."""
    tmp = f"{path}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
    try:
        with open(tmp, "xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        move_no_clobber(tmp, path)
    finally:
        try:
            os.remove(tmp)
        except FileNotFoundError:
            pass
        except OSError:
            pass                # a stray temp is the lesser problem
