"""Timestamped backups of crew's config files, taken before every crew write (T-0050).

The owner's crew settings live in two untracked files, `~/.claude/crew/config.json`
and a repo's `.crew/config.json`. A crew writer that replaces either one keeps
the bytes it is about to replace here first, so a write that went wrong -- or a
defaults rewrite the owner did not expect -- can be put back with
`/crew:config --restore <stamp>`.

Layout, under `backup_root()` (`$CREW_BACKUP_DIR`, else
`~/.claude/crew/backups`, beside `crew_state.GLOBAL_CONFIG_PATH`):

    global/<stamp>.json                        the machine-global file
    profile/<stamp>.json                       ~/.claude/crew/profile.json
    repo/<name>-<sha256(realpath)[:10]>/<stamp>.json   a repo's .crew/config.json
                                     .../source        the absolute path it backs up
    file/<basename>-<sha256(realpath)[:10]>/...        anything else (the vault copy)

A stamp is UTC `YYYYMMDDTHHMMSSZ`, `-2`, `-3` on a same-second collision.
Directories are 0700 and files 0600. The newest `KEEP` per file are kept.

THE RULE for every writer: `backup(path)` runs immediately before the write
replaces `path`, and when it raises `BackupError` the write is refused and the
file is left exactly as it was. A file that does not exist has nothing to lose:
`backup` returns None without touching the backup root. The writers that call
it, by function:

  * `crew_config.write_global_config` and `crew_config.write_repo_config`,
    inside the `mutate` they hand `crew_config_files.update_json`, under its
    lock, once the write is planned -- every
    `/crew:config --set` / `--unset` and the menu's Save;
  * `crew_config.apply_rebuild` and `crew_config.apply_restore`;
  * `crew_config.write_profile`, for `profile.json` and its vault copy;
  * `crew_config_menu.restore_repo_config`, before it moves the current file
    aside;
  * `crew_platform.heal_config` and `crew_platform.apply_changes`;
  * `crew_autoclear_setup._atomic_write_json`, and
    `crew_autoclear_setup.apply_migrate_to_repo` for its `config.json` entry;
  * `crew_upgrade.run`, after its one-time `config.json.v1.bak`.

Standard library plus `crew_config_files` (itself standard library only) and a
lazy `crew_state`, so a SessionStart hook can import it cheaply.
"""
import datetime
import hashlib
import os
import re

import crew_config_files

KEEP = 20
STAMP_RE = re.compile(r"^\d{8}T\d{6}Z(-\d+)?$")
SOURCE_NAME = "source"


class BackupError(Exception):
    """The backup could not be taken (or read back); nothing was written."""


def _global_config_path():
    import crew_state  # pylint: disable=import-outside-toplevel
    return crew_state.GLOBAL_CONFIG_PATH


def backup_root():
    """`$CREW_BACKUP_DIR`, else `<dir of the machine-global config>/backups`."""
    override = os.environ.get("CREW_BACKUP_DIR")
    if override:
        return os.path.abspath(override)
    return os.path.join(os.path.dirname(os.path.abspath(_global_config_path())),
                        "backups")


def profile_path():
    """`~/.claude/crew/profile.json`, beside the machine-global config."""
    return os.path.join(os.path.dirname(os.path.abspath(_global_config_path())),
                        "profile.json")


def _real(path):
    return os.path.realpath(os.path.abspath(path))


def target_dir(path):
    """The directory `path`'s backups live in, under `backup_root()`."""
    real = _real(path)
    if real == _real(_global_config_path()):
        return os.path.join(backup_root(), "global")
    if real == _real(profile_path()):
        return os.path.join(backup_root(), "profile")
    digest = hashlib.sha256(real.encode("utf-8", "surrogateescape")).hexdigest()[:10]
    parent = os.path.dirname(real)
    if os.path.basename(parent) == ".crew":
        name = os.path.basename(os.path.dirname(parent)) or "root"
        return os.path.join(backup_root(), "repo", f"{name}-{digest}")
    return os.path.join(backup_root(), "file", f"{os.path.basename(real)}-{digest}")


def _stamp_key(stamp):
    base, _, suffix = stamp.partition("-")
    return (base, int(suffix) if suffix else 1)


def _stamps_in(directory):
    try:
        names = os.listdir(directory)
    except FileNotFoundError:
        return []
    stamps = [name[:-5] for name in names
              if name.endswith(".json") and STAMP_RE.match(name[:-5])]
    return sorted(stamps, key=_stamp_key, reverse=True)


def list_backups(path):
    """The stamps backed up for `path`, newest first."""
    return _stamps_in(target_dir(path))


def check_stamp(stamp):
    """None when `stamp` is a well-formed stamp, else why not."""
    if not isinstance(stamp, str) or not STAMP_RE.match(stamp):
        return (f"{stamp!r} is not a backup stamp (YYYYMMDDTHHMMSSZ, or with "
                "-2, -3 for a same-second collision)")
    return None


def read_backup(path, stamp):
    """The bytes backed up for `path` at `stamp`, or `BackupError`."""
    problem = check_stamp(stamp)
    if problem:
        raise BackupError(problem)
    where = os.path.join(target_dir(path), f"{stamp}.json")
    try:
        with open(where, "rb") as handle:
            return handle.read()
    except FileNotFoundError as exc:
        raise BackupError(f"no backup {stamp} for {path} (looked in "
                          f"{os.path.dirname(where)}); --backups lists them") from exc
    except OSError as exc:
        raise BackupError(f"backup {where} cannot be read "
                          f"({crew_config_files.os_error_text(exc)})") from exc


def _private_dir(directory):
    os.makedirs(directory, mode=0o700, exist_ok=True)
    if os.name != "nt":
        os.chmod(directory, 0o700)


def _write_private(where, data):
    """`data` as a new 0600 file at `where` via a sibling and a no-clobber
    move; `FileExistsError` when `where` already exists."""
    tmp = f"{where}.{os.getpid()}.tmp"
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0),
                 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        crew_config_files.move_no_clobber(tmp, where)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _rotate(directory):
    """Keep the newest `KEEP` stamps in `directory`; remove the rest. A
    removal that fails is left for the next backup to retry: the backup this
    run took is already safe."""
    for stamp in _stamps_in(directory)[KEEP:]:
        try:
            os.remove(os.path.join(directory, f"{stamp}.json"))
        except OSError:
            pass


def backup(path, now=None):
    """Copy `path`'s raw bytes (corrupt ones included) to its backup
    directory before a crew write replaces it. Returns the stamp, or None
    when `path` does not exist. Raises `BackupError` on any failure, and the
    caller then refuses its write."""
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise BackupError(f"{path} could not be read to back it up "
                          f"({crew_config_files.os_error_text(exc)}); nothing written") from exc
    directory = target_dir(path)
    moment = now or datetime.datetime.now(datetime.timezone.utc)
    base = moment.strftime("%Y%m%dT%H%M%SZ")
    try:
        _private_dir(backup_root())
        _private_dir(os.path.dirname(directory))
        _private_dir(directory)
        stamp = None
        for attempt in range(1, 1000):
            candidate = base if attempt == 1 else f"{base}-{attempt}"
            try:
                _write_private(os.path.join(directory, f"{candidate}.json"), data)
            except FileExistsError:
                continue
            stamp = candidate
            break
        if stamp is None:
            raise BackupError(f"999 backups of {path} in one second; nothing written")
        source = os.path.join(directory, SOURCE_NAME)
        if not os.path.exists(source):
            try:
                _write_private(source, (_real(path) + "\n").encode("utf-8", "surrogateescape"))
            except FileExistsError:
                pass
    except OSError as exc:
        raise BackupError(f"could not back up {path} under {directory} "
                          f"({crew_config_files.os_error_text(exc)}); nothing written") from exc
    _rotate(directory)
    return stamp
