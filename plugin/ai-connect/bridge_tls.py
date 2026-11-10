"""The Bridge's TLS: a self-signed certificate, trusted by its pinned SHA-256 fingerprint.

There is no certificate authority. The Bridge makes its own certificate and
key on first start (or `ai-connect bridge cert show`), and the fingerprint,
the SHA-256 of the certificate's DER bytes, travels to each peer inside its
join code. A client checks that digest during the TLS handshake, before the
WebSocket upgrade carries its token: the fingerprint IS the trust anchor, so
no hostname or CA check is made, and a certificate with any other digest ends
the connection (PinMismatch). Nothing here falls back to plain ws://.

Files, in <config dir>/tls/ (0700; on Windows an ACL of the current user alone):

    bridge-cert.pem   the certificate (public; its fingerprint is in every join code)
    bridge-key.pem    the private key, 0600 / owner-only ACL, never leaves this machine

Rotation (`ai-connect bridge cert rotate`) makes a new key and certificate,
so the fingerprint changes: every existing peer must re-pin (`ai-connect pin
<new fingerprint>`, or a new join code) and every join code made before it
stops working. The Bridge serves the new certificate after a restart.

Certificate generation needs the `cryptography` package (pinned in
requirements.txt); the TLS contexts and the pin check use the standard ssl
module only, so a client never imports cryptography.
"""

from __future__ import annotations

import datetime
import hashlib
import os
import re
import secrets
import ssl
import sys
from dataclasses import dataclass
from pathlib import Path

TLS_DIR = "tls"
CERT_FILE = "bridge-cert.pem"
KEY_FILE = "bridge-key.pem"
DEFAULT_VALIDITY_DAYS = 730  # two years; `bridge cert rotate` before then
MIN_VALIDITY_DAYS = 1
MAX_VALIDITY_DAYS = 3650
COMMON_NAME = "ai-connect bridge"
FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")


class TlsError(Exception):
    """A certificate or key that cannot be made, read or used; the message says which file and why."""


class PinMismatch(ssl.SSLCertVerificationError):
    """The Bridge presented a certificate whose SHA-256 is not the pinned one."""

    def __init__(self, expected: str, got: str):
        super().__init__(
            f"the Bridge's TLS certificate has SHA-256 {got}, not the pinned {expected}: refusing to connect "
            "(never falling back to ws://). If the Bridge's certificate was rotated, re-pin with "
            "`ai-connect pin <new fingerprint>` or join again; otherwise something is impersonating the Bridge")
        self.expected = expected
        self.got = got


@dataclass(frozen=True)
class CertInfo:
    cert_path: Path
    key_path: Path
    fingerprint: str
    not_before: datetime.datetime
    not_after: datetime.datetime


def normalize_fingerprint(text: str) -> str:
    """64 lowercase hex digits; accepts 'sha256:' and the colon-separated form openssl prints. ValueError otherwise."""
    value = (text or "").strip().lower()
    value = value.removeprefix("sha256:").removeprefix("sha256=").replace(":", "")
    if not FINGERPRINT_RE.match(value):
        raise ValueError(f"{text!r} is not a SHA-256 fingerprint (64 hex digits)")
    return value


def fingerprint_of_der(der: bytes) -> str:
    return hashlib.sha256(der).hexdigest()


def fingerprint_bytes(fingerprint: str) -> bytes:
    """The 32 bytes a join code carries."""
    return bytes.fromhex(normalize_fingerprint(fingerprint))


def tls_dir(config_dir: Path) -> Path:
    return Path(config_dir) / TLS_DIR


def cert_paths(config_dir: Path) -> tuple[Path, Path]:
    directory = tls_dir(config_dir)
    return directory / CERT_FILE, directory / KEY_FILE


def _tsadmin():
    sys.path.append(str(Path(__file__).resolve().parent / "vpn"))
    import tsadmin  # pylint: disable=import-error,import-outside-toplevel
    return tsadmin


def _private_dir(directory: Path) -> None:
    tsadmin = _tsadmin()
    try:
        tsadmin.private_dir(directory)
    except tsadmin.Failure as err:
        raise TlsError(str(err)) from None


def _write_owner_only(path: Path, data: str) -> None:
    tsadmin = _tsadmin()
    try:
        tsadmin.write_owner_only(path, data)
    except tsadmin.Failure:
        raise TlsError(f"could not restrict {path} to the current user; no key was written") from None
    except OSError as err:
        raise TlsError(f"could not write {path}: {err.strerror or err}") from None


def generate(config_dir: Path, validity_days: int = DEFAULT_VALIDITY_DAYS,
             now: datetime.datetime | None = None) -> CertInfo:
    """A new EC P-256 key and self-signed certificate in <config_dir>/tls/, replacing any there; returns its info.

    The key is written first and the certificate last, each whole (temp file +
    os.replace), so a reader never sees a half-written file.
    """
    # pylint: disable=import-outside-toplevel  # only the Bridge machine needs cryptography
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    if not MIN_VALIDITY_DAYS <= validity_days <= MAX_VALIDITY_DAYS:
        raise TlsError(f"certificate validity must be {MIN_VALIDITY_DAYS} to {MAX_VALIDITY_DAYS} days, "
                       f"got {validity_days}")
    now = now or datetime.datetime.now(datetime.timezone.utc)
    directory = tls_dir(config_dir)
    _private_dir(directory)
    cert_path, key_path = cert_paths(config_dir)
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, COMMON_NAME)])
    not_before = (now - datetime.timedelta(minutes=5)).replace(microsecond=0)
    not_after = (now + datetime.timedelta(days=validity_days)).replace(microsecond=0)
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name)
            .public_key(key.public_key())
            .serial_number(int.from_bytes(secrets.token_bytes(16), "big") >> 1)
            .not_valid_before(not_before).not_valid_after(not_after)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode("ascii")
    _write_owner_only(key_path, key_pem)
    _write_owner_only(cert_path, cert.public_bytes(serialization.Encoding.PEM).decode("ascii"))
    return CertInfo(cert_path, key_path, fingerprint_of_der(cert.public_bytes(serialization.Encoding.DER)),
                    not_before, not_after)


def load(config_dir: Path) -> CertInfo | None:
    """The certificate in <config_dir>/tls/, or None when there is none. TlsError when it is there but unusable."""
    cert_path, key_path = cert_paths(config_dir)
    if not cert_path.exists() and not key_path.exists():
        return None
    if not cert_path.is_file() or not key_path.is_file():
        raise TlsError(f"{tls_dir(config_dir)} holds only one of {CERT_FILE} and {KEY_FILE}: "
                       "run `ai-connect bridge cert rotate` to make a new pair")
    try:
        der = ssl.PEM_cert_to_DER_cert(cert_path.read_text(encoding="ascii"))
    except (OSError, ValueError, UnicodeDecodeError) as err:
        raise TlsError(f"{cert_path} is not a PEM certificate ({err})") from None
    # pylint: disable=import-outside-toplevel
    from cryptography import x509
    cert = x509.load_der_x509_certificate(der)
    return CertInfo(cert_path, key_path, fingerprint_of_der(der),
                    cert.not_valid_before_utc, cert.not_valid_after_utc)


def ensure(config_dir: Path, validity_days: int = DEFAULT_VALIDITY_DAYS) -> tuple[CertInfo, bool]:
    """(the certificate, whether it was made now): the existing one, else a new one. Never replaces one."""
    info = load(config_dir)
    if info is not None:
        return info, False
    return generate(config_dir, validity_days), True


def check_key_mode(key_path: Path) -> str:
    """'' when the key is owner-only (POSIX: no group/other bit), else why not. Windows: not checked here."""
    if os.name == "nt":
        return ""
    mode = key_path.stat().st_mode & 0o777
    return "" if not mode & 0o077 else f"{key_path} has mode {mode:o}, not 600 (owner-only)"


def server_context(info: CertInfo) -> ssl.SSLContext:
    """The Bridge's listening context: TLS 1.2 or later, this certificate, no client certificates."""
    why = check_key_mode(info.key_path)
    if why:
        raise TlsError(why)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        context.load_cert_chain(info.cert_path, info.key_path)
    except (OSError, ssl.SSLError) as err:
        raise TlsError(f"cannot load {info.cert_path} with {info.key_path}: {err}") from None
    return context


def check_pin(der: bytes | None, pin: str) -> None:
    """PinMismatch unless der (the peer's certificate) has the SHA-256 pin."""
    got = fingerprint_of_der(der) if der else "(no certificate)"
    if got != pin:
        raise PinMismatch(pin, got)


def client_context(fingerprint: str) -> ssl.SSLContext:
    """A client context that trusts exactly one certificate: the one with this SHA-256.

    No CA store and no hostname check: the pin replaces both. The digest is
    compared inside the handshake itself (the SSLObject/SSLSocket classes
    below), so a wrong certificate ends the connection before one byte of
    the WebSocket upgrade, and with it the token, is sent.
    """
    pin = normalize_fingerprint(fingerprint)

    class PinnedObject(ssl.SSLObject):  # asyncio (websockets) wraps through SSLObject
        def do_handshake(self) -> None:
            super().do_handshake()
            check_pin(self.getpeercert(binary_form=True), pin)

    # pylint: disable-next=abstract-method  # SSLSocket's dup/recvmsg/sendmsg are abstract by design; never called here
    class PinnedSocket(ssl.SSLSocket):  # http.client (join code redemption) wraps through SSLSocket
        def do_handshake(self, block: bool = False) -> None:
            super().do_handshake(block)
            check_pin(self.getpeercert(binary_form=True), pin)

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.sslobject_class = PinnedObject
    context.sslsocket_class = PinnedSocket
    return context


def connect_options(fingerprint: str) -> dict:
    """websockets.connect() keyword arguments for a Bridge URI: the pinned context for wss://, nothing for ws://."""
    return {"ssl": client_context(fingerprint)} if fingerprint else {}
