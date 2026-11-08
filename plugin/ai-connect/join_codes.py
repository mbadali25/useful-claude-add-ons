"""One-time join codes: the code format, the Bridge's invite store, and redemption.

A join code is what `ai-connect bridge invite --name N` prints on the Bridge
machine and `ai-connect join <code>` takes on the new one. It carries
everything the new machine needs to reach the Bridge and prove it was invited:

    version (1 byte)        CODE_VERSION
    expiry (4 bytes)        Unix seconds, big-endian
    port (2 bytes)          the Bridge's port
    fingerprint (32 bytes)  SHA-256 of the Bridge's TLS certificate; all zero
                            for a Bridge that serves plain ws:// only
    secret (16 bytes)       128 random bits, single use
    host (1 + n bytes)      length, then the Bridge's address (UTF-8)
    name (1 + n bytes)      length, then the peer name the code was made for
    checksum (4 bytes)      the first 4 bytes of SHA-256 over all the above

encoded as RFC 4648 base32 without padding (A-Z, 2-7: URL-safe and
case-insensitive), in dash-separated groups of five for copy and paste.

The Bridge keeps only the secret's SHA-256 (invites.json, next to
config.yaml). Redemption is one locked read-check-mark-write: the invite is
marked used (temp file + os.replace) before the peer's token goes into
config.yaml, so a crash between the two burns the code rather than leaving it
usable twice. Every refusal (unknown, expired, used, wrong name) is the same
generic one.

Peer tokens follow installer.py: 256 random bits, the Bridge keeps their
SHA-256 in auth.peers. Bridge-issued tokens do not expire; revoking the peer
(`ai-connect bridge revoke --name N`) ends them, and the running Bridge drops
the peer's live connections within AUTH_RELOAD_SECONDS (server/auth_reload.py).
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import json
import os
import re
import secrets
import struct
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import yaml

CODE_VERSION = 1
SECRET_BYTES = 16  # 128 bits
FINGERPRINT_BYTES = 32
NO_FINGERPRINT = bytes(FINGERPRINT_BYTES)
CHECKSUM_BYTES = 4
GROUP = 5
# The names `deploy` and the tailnet tooling accept (vpn/tsadmin.py PEER_NAME_RE)
PEER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,62}$")
HOST_RE = re.compile(r"^[A-Za-z0-9.:_-]{1,253}$")
DEFAULT_EXPIRY_SECONDS = 3600
MIN_EXPIRY_SECONDS = 60
MAX_EXPIRY_SECONDS = 7 * 86400
# The longest code `bridge invite` makes without --allow-long-expiry: the join is plain HTTP in this
# release, so a code that lives longer is longer to intercept and redeem
SAFE_MAX_EXPIRY_SECONDS = 86400
# Used and expired invites stay this long, so `bridge list` can show them, then go
KEEP_SECONDS = 7 * 86400
LOCK_TIMEOUT_SECONDS = 10.0
# The one answer to every failed redemption: it does not tell which check failed
GENERIC_REFUSAL = "invalid or expired join code"
JOIN_PATH = "/join"
SECRET_HEADER = "X-AI-Connect-Join"
NAME_HEADER = "X-AI-Connect-Name"
INVITES_FILE = "invites.json"
LOCK_FILE = ".auth.lock"


class CodeError(ValueError):
    """A join code that does not decode: mistyped, cut short, or of another version."""


class Refused(Exception):
    """A redemption refused; str() is always GENERIC_REFUSAL."""

    def __init__(self) -> None:
        super().__init__(GENERIC_REFUSAL)


@dataclass(frozen=True)
class JoinCode:
    host: str
    port: int
    fingerprint: bytes
    secret: bytes
    name: str
    expires: int
    version: int = CODE_VERSION

    @property
    def tls(self) -> bool:
        return self.fingerprint != NO_FINGERPRINT

    @property
    def fingerprint_hex(self) -> str:
        return self.fingerprint.hex() if self.tls else ""


def mask(secret: str) -> str:
    """A token as output may show it: its last 4 characters only."""
    return f"****{secret[-4:]}" if len(secret) >= 8 else "****"


def sha256_hex(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def parse_expiry(text: str) -> int:
    """'1h', '30m', '2d', '90s' or plain seconds, within MIN/MAX_EXPIRY_SECONDS."""
    match = re.fullmatch(r"\s*(\d+)\s*([smhd]?)\s*", text or "")
    if not match:
        raise ValueError(f"--expiry '{text}' is not a duration like 1h, 30m, 2d or 3600")
    seconds = int(match.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}[match.group(2)]
    if not MIN_EXPIRY_SECONDS <= seconds <= MAX_EXPIRY_SECONDS:
        raise ValueError(f"--expiry must be between {MIN_EXPIRY_SECONDS} seconds and 7 days, got {seconds}s")
    return seconds


# ---------------------------------------------------------------- the code


def _field(text: str, what: str) -> bytes:
    raw = text.encode("utf-8")
    if not 1 <= len(raw) <= 255:
        raise CodeError(f"{what} must be 1 to 255 bytes")
    return bytes([len(raw)]) + raw


def encode(code: JoinCode) -> str:
    if len(code.secret) != SECRET_BYTES or len(code.fingerprint) != FINGERPRINT_BYTES:
        raise CodeError("secret or fingerprint has the wrong length")
    if not 1 <= code.port <= 65535 or not 0 <= code.expires < 2**32:
        raise CodeError("port or expiry out of range")
    body = (bytes([code.version]) + struct.pack(">IH", code.expires, code.port) + code.fingerprint
            + code.secret + _field(code.host, "host") + _field(code.name, "name"))
    raw = body + hashlib.sha256(body).digest()[:CHECKSUM_BYTES]
    text = base64.b32encode(raw).decode("ascii").rstrip("=")
    return "-".join(text[i:i + GROUP] for i in range(0, len(text), GROUP))


def decode(text: str) -> JoinCode:
    """The code's fields; CodeError when it is mistyped, cut short or of an unknown version."""
    letters = re.sub(r"[\s-]", "", text or "").upper()
    if not letters or not re.fullmatch(r"[A-Z2-7]+", letters):
        raise CodeError("not a join code: it holds characters other than A-Z, 2-7 and dashes")
    try:
        raw = base64.b32decode(letters + "=" * (-len(letters) % 8))
    except ValueError:
        raise CodeError("not a join code: it does not decode (cut short?)") from None
    if len(raw) < CHECKSUM_BYTES + 1:
        raise CodeError("not a join code: too short")
    body, checksum = raw[:-CHECKSUM_BYTES], raw[-CHECKSUM_BYTES:]
    if not hmac.compare_digest(hashlib.sha256(body).digest()[:CHECKSUM_BYTES], checksum):
        raise CodeError("the join code's checksum does not match: a character is wrong or missing")
    if body[0] != CODE_VERSION:
        raise CodeError(f"join code version {body[0]} is not one this ai-connect reads (it reads {CODE_VERSION}); "
                        "update ai-connect on this machine")
    try:
        expires, port = struct.unpack(">IH", body[1:7])
        at = 7
        fingerprint = body[at:at + FINGERPRINT_BYTES]
        at += FINGERPRINT_BYTES
        secret = body[at:at + SECRET_BYTES]
        at += SECRET_BYTES
        fields = []
        for _ in range(2):
            size = body[at]
            fields.append(body[at + 1:at + 1 + size].decode("utf-8"))
            if len(fields[-1].encode("utf-8")) != size:
                raise IndexError
            at += 1 + size
        if at != len(body) or len(fingerprint) != FINGERPRINT_BYTES or len(secret) != SECRET_BYTES:
            raise IndexError
    except (IndexError, struct.error, UnicodeDecodeError):
        raise CodeError("the join code is malformed") from None
    host, name = fields[0], fields[1]
    if not HOST_RE.match(host) or not PEER_NAME_RE.match(name) or port == 0:
        raise CodeError("the join code carries an invalid host, name or port")
    return JoinCode(host=host, port=port, fingerprint=fingerprint, secret=secret, name=name, expires=expires)


# ---------------------------------------------------------------- files and the lock


def atomic_write(path: Path, text: str) -> None:
    """Write path whole: a temp file in the same directory, then os.replace.

    Never open(path, "w"): that truncates at open time, so a crash or a
    concurrent reader sees an empty file. mkstemp makes the temp file 0600 on
    POSIX; on Windows it inherits the directory's ACL, which for
    ~/.config/ai-connect is the current user's alone (installer.py).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


_THREAD_LOCK = threading.Lock()
# The config directories this thread holds auth_lock for (realpath), for reentry
_HELD = threading.local()


@contextlib.contextmanager
def auth_lock(config_dir: Path, timeout: float = LOCK_TIMEOUT_SECONDS) -> Iterator[None]:
    """One writer at a time for config.yaml's auth: and invites.json, across processes and threads.

    The Bridge (redeeming a code), the CLI (invite, token, revoke) and every
    config.yaml writer in installer.py (add-peer, revoke-peer, the role
    tokens, config --server) take it: a read-modify-write outside it can
    write a revoked peer back or drop one just redeemed.

    An exclusive lock on a lock file: fcntl.flock on POSIX, msvcrt.locking on
    Windows; TimeoutError after timeout seconds. Reentrant within one thread,
    so a locked caller (the CLI's `bridge token`) can call a writer that
    locks for itself (installer._add_peer): the inner one holds nothing more.
    """
    config_dir.mkdir(parents=True, exist_ok=True)
    key = os.path.realpath(config_dir)
    held = _HELD.__dict__.setdefault("dirs", set())
    if key in held:
        yield
        return
    deadline = time.monotonic() + timeout
    if not _THREAD_LOCK.acquire(timeout=timeout):
        raise TimeoutError(f"{config_dir / LOCK_FILE} is held by another writer")
    try:
        fd = os.open(config_dir / LOCK_FILE, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            _lock_fd(fd, deadline, config_dir / LOCK_FILE)
            held.add(key)
            try:
                yield
            finally:
                held.discard(key)
                _unlock_fd(fd)
        finally:
            os.close(fd)
    finally:
        _THREAD_LOCK.release()


def _lock_fd(fd: int, deadline: float, path: Path) -> None:
    if os.name == "nt":
        import msvcrt  # pylint: disable=import-outside-toplevel,import-error
        os.lseek(fd, 0, os.SEEK_SET)
        while True:
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                if time.monotonic() > deadline:
                    raise TimeoutError(f"{path} is held by another writer") from None
                time.sleep(0.02)
    import fcntl  # pylint: disable=import-outside-toplevel,import-error
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            if time.monotonic() > deadline:
                raise TimeoutError(f"{path} is held by another writer") from None
            time.sleep(0.02)


def _unlock_fd(fd: int) -> None:
    if os.name == "nt":
        import msvcrt  # pylint: disable=import-outside-toplevel,import-error
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl  # pylint: disable=import-outside-toplevel,import-error
        fcntl.flock(fd, fcntl.LOCK_UN)


# ---------------------------------------------------------------- the Bridge's state


def yaml_error_place(err: Exception) -> str:
    """Where a YAML error is, never what: PyYAML's message quotes the offending text, and config.yaml holds tokens."""
    mark = getattr(err, "problem_mark", None)
    return f"line {mark.line + 1}, column {mark.column + 1}" if mark else "not valid YAML"


def read_config(config_path: Path) -> dict:
    with open(config_path, encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise ValueError(f"{config_path} is not a YAML mapping")
    return config


def write_config(config_path: Path, config: dict) -> None:
    atomic_write(config_path, yaml.safe_dump(config, sort_keys=False))


def peers_of(config: dict) -> dict:
    auth = config.get("auth")
    if auth is None:
        auth = config["auth"] = {}
    if not isinstance(auth, dict):
        raise ValueError("auth: is not a mapping")
    peers = auth.get("peers")
    if peers is None:
        peers = auth["peers"] = {}
    if not isinstance(peers, dict):
        raise ValueError("auth.peers is not a mapping")
    return peers


def new_token() -> str:
    return secrets.token_hex(32)  # 256 bits, as installer.py add-peer


def add_peer_locked(config_path: Path, name: str) -> str:
    """Under auth_lock: a new peer with a fresh token; returns the raw token. ValueError if the name is taken."""
    config = read_config(config_path)
    peers = peers_of(config)
    if name in peers:
        raise ValueError(f"peer '{name}' already exists; revoke it first to replace its token")
    token = new_token()
    peers[name] = sha256_hex(token)
    write_config(config_path, config)
    return token


def revoke_peer_locked(config_path: Path, name: str) -> bool:
    """Under auth_lock: remove the peer from auth.peers; False when it was not there."""
    config = read_config(config_path)
    peers = peers_of(config)
    if name not in peers:
        return False
    del peers[name]
    write_config(config_path, config)
    return True


def invites_path(config_path: Path) -> Path:
    return config_path.parent / INVITES_FILE


def read_invites(path: Path) -> list[dict]:
    """The invite store; [] when there is none. A broken file is an error, never 'no invites'."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get("invites"), list):
        raise ValueError(f"{path} is not an ai-connect invite store")
    return [entry for entry in data["invites"] if isinstance(entry, dict)]


def write_invites(path: Path, invites: list[dict], now: float) -> None:
    kept = [entry for entry in invites
            if max(entry.get("expires", 0), entry.get("used") or 0) + KEEP_SECONDS > now]
    atomic_write(path, json.dumps({"version": 1, "invites": kept}, indent=2) + "\n")


def invite_state(entry: dict, now: float) -> str:
    if entry.get("used"):
        return "used"
    if entry.get("expires", 0) <= now:
        return "expired"
    return "pending"


def create_invite(config_path: Path, name: str, expiry_seconds: int, host: str, port: int,
                  fingerprint: bytes = NO_FINGERPRINT, clock: Callable[[], float] = time.time) -> str:
    """Bridge machine: a new single-use code for name; returns the code. Older pending codes for name end."""
    if not PEER_NAME_RE.match(name):
        raise ValueError(f"--name '{name}' must be 1-63 letters, digits or hyphens")
    if not HOST_RE.match(host):
        raise ValueError(f"the Bridge address '{host}' is not an IP address or host name")
    secret = secrets.token_bytes(SECRET_BYTES)
    with auth_lock(config_path.parent):
        now = clock()
        if name in peers_of(read_config(config_path)):
            raise ValueError(f"peer '{name}' already exists; revoke it first (ai-connect bridge revoke --name {name})")
        path = invites_path(config_path)
        invites = read_invites(path)
        for entry in invites:
            if entry.get("name") == name and invite_state(entry, now) == "pending":
                entry["cancelled"] = int(now)
                entry["used"] = int(now)
        expires = int(now) + expiry_seconds
        invites.append({"name": name, "secret_sha256": sha256_hex(secret), "created": int(now),
                        "expires": expires, "used": None})
        write_invites(path, invites, now)
    return encode(JoinCode(host=host, port=port, fingerprint=fingerprint, secret=secret, name=name, expires=expires))


def cancel_invites(config_path: Path, name: str, clock: Callable[[], float] = time.time) -> int:
    """Under auth_lock: end every pending code for name; how many there were."""
    now = clock()
    path = invites_path(config_path)
    invites = read_invites(path)
    ended = 0
    for entry in invites:
        if entry.get("name") == name and invite_state(entry, now) == "pending":
            entry["cancelled"] = entry["used"] = int(now)
            ended += 1
    if ended:
        write_invites(path, invites, now)
    return ended


def redeem(config_path: Path, secret: bytes, name: str, clock: Callable[[], float] = time.time,
           add_peer: Callable[[Path, str], str] = add_peer_locked) -> str:
    """The Bridge: exchange a code's secret for the peer's token, exactly once; Refused otherwise.

    One locked read-check-mark-write. The invite is marked used and written
    before the peer is added: a crash between the two leaves the code spent
    and no peer, never a code that works twice.
    """
    if len(secret) != SECRET_BYTES:
        raise Refused()
    digest = sha256_hex(secret)
    with auth_lock(config_path.parent):
        now = clock()
        path = invites_path(config_path)
        try:
            invites = read_invites(path)
        except (ValueError, OSError):
            raise Refused() from None
        match = None
        # Compare with every entry, so the time taken does not tell which matched
        for entry in invites:
            if hmac.compare_digest(str(entry.get("secret_sha256", "")), digest):
                match = entry
        if match is None or match.get("name") != name or invite_state(match, now) != "pending":
            raise Refused()
        try:
            taken = name in peers_of(read_config(config_path))
        except (ValueError, OSError, yaml.YAMLError):
            raise Refused() from None
        match["used"] = int(now)
        write_invites(path, invites, now)
        if taken:
            raise Refused()
        return add_peer(config_path, name)


def pending_names(config_path: Path, now: float | None = None) -> list[dict]:
    """Every invite in the store with its state, for `bridge list`; never the hash."""
    now = time.time() if now is None else now
    return [{"name": entry.get("name"), "state": invite_state(entry, now), "expires": entry.get("expires")}
            for entry in read_invites(invites_path(config_path))]


class FailureLimiter:
    """Failed redemptions per client address, and in total, within a sliding window.

    128 random bits cannot be guessed, but each failure costs a locked file
    read: past the limit the Bridge answers 429 without looking.
    """

    def __init__(self, per_ip: int = 5, total: int = 30, window: float = 60.0,
                 clock: Callable[[], float] = time.monotonic):
        self.per_ip, self.total, self.window, self._clock = per_ip, total, window, clock
        self._failures: list[tuple[float, str]] = []

    def _prune(self) -> None:
        cutoff = self._clock() - self.window
        self._failures = [(at, ip) for at, ip in self._failures if at > cutoff]

    def blocked(self, ip: str) -> bool:
        self._prune()
        return (len(self._failures) >= self.total
                or sum(1 for _at, who in self._failures if who == ip) >= self.per_ip)

    def failed(self, ip: str) -> None:
        self._failures.append((self._clock(), ip))
