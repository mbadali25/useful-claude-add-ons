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
  * `digest` -- sha256 of the bytes, what a compare-and-swap compares.
  * `replace_text` / `replace_bytes` -- sibling, fsync, `os.replace`, so an
    interrupted write leaves the original intact; `replace_text` keeps the
    file's CRLF and UTF-8 BOM.
  * `update_json` -- read, compare, merge and replace inside the lock, so two
    writers never merge against stale snapshots.
  * `move_aside` -- one atomic rename: the backup IS the original inode, so
    there is no window in which the bytes exist nowhere.

No crew imports, so `crew_config` and `crew_config_menu` can both import it.
"""
import copy
import hashlib
import json
import os
import time

# How long `Lock` waits for another crew writer before refusing. A module
# attribute read at acquire time, so a test can shorten it.
LOCK_WAIT_SECONDS = 3.0

_BOM = b"\xef\xbb\xbf"


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
    the same rule as the review ledger's lock.
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
            finally:
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


def digest(data):
    """sha256 hex of `data` (bytes)."""
    return hashlib.sha256(data).hexdigest()


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
    when the file's current digest differs, `Conflict` is raised and nothing
    is written -- a changed file is refused, never merged over. Without
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
        current = None if raw is None else digest(raw)
        if expect is not None and expect != current:
            raise Conflict(
                f"{path} changed since it was read (digest "
                f"{current or 'none: the file is absent'}, expected {expect}); "
                "nothing written. Re-run to plan against the current file")
        result = mutate(copy.deepcopy(parsed))
        if result is None:
            return None, raw
        text = json.dumps(result, indent=2) + "\n"
        replace_text(path, text, raw)
        return result, raw


def move_aside(src, dest):
    """Rename `src` to `dest` in one `os.replace` and return `dest`'s bytes.

    Refuses (`FileExistsError`) when `dest` exists. The caller holds `src`'s
    `Lock`. The backup is the original inode: no copy, no moment in which the
    bytes are at neither name."""
    if os.path.lexists(dest):
        raise FileExistsError(f"{dest} already exists; nothing moved")
    os.replace(src, dest)
    _fsync_dir(dest)
    with open(dest, "rb") as handle:
        return handle.read()
