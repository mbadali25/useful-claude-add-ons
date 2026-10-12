"""Roles of the Bridge: which token may send which message types, and as whom.

A connection gets its identity from the token it shows in the handshake. The
Bridge knows every token only by its SHA-256, so the config does not give
any away:

- auth.peers maps each peer name to the hash of that peer's own token; the
  token may register (and watch) that name and no other.
- auth.token, the legacy token all peers shared, counts only with
  auth.allow_shared_token: true. It may register any name that has no token
  of its own, so names are not bound to it; the Bridge warns when it is used.
- The observer token (observer_token_sha256) reads all traffic; the user
  token (user_token_sha256) lets a person write to agents as User:<name>.
"""

import hashlib
import hmac
import re
from dataclasses import dataclass

from .user_send import is_reserved_name

PEER = "peer"
OBSERVER = "observer"
USER = "user"

SHARED_CREDENTIAL = "shared"

# The single truth on what each role may do; anything else is refused
ALLOWED_MESSAGE_TYPES: dict[str, frozenset[str]] = {
    PEER: frozenset({
        "register", "ping", "watch", "list_peers", "message",
        "set_state", "set_status", "notify_when_idle", "history",
    }),
    # Reads only: no register, so an observer can neither send nor hold a name
    OBSERVER: frozenset({"observe", "history_all", "list_peers", "ping"}),
    # Sends only; replies and everything else are read with the observer token
    USER: frozenset({"user_send", "ping"}),
}

_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


def token_sha256(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class Identity:
    """Who a connection is: its role and, for a per-peer token, its one name."""
    role: str
    peer_name: str | None = None
    shared: bool = False

    @property
    def credential(self) -> str:
        """Which token this is, without the token: decides who may reclaim a name."""
        if self.shared:
            return SHARED_CREDENTIAL
        return f"{self.role}:{self.peer_name or ''}"


def _bearer_token(authorization: str) -> str | None:
    scheme, _, token = authorization.partition(" ")
    if scheme != "Bearer" or not token:
        return None
    return token


class Roles:
    """Maps the token of a handshake to its identity."""

    def __init__(
        self,
        peer_token_sha256: dict[str, str],
        observer_token_sha256: str = "",
        user_token_sha256: str = "",
        shared_token: str | None = None,
        allow_shared_token: bool = False,
    ):
        entries: list[tuple[str, Identity]] = []
        for name, digest in peer_token_sha256.items():
            if is_reserved_name(name):
                raise ValueError(f"auth.peers: '{name}' is reserved for the Bridge and users")
            digest = digest.lower()
            if not _SHA256_HEX.fullmatch(digest):
                raise ValueError(f"auth.peers: the entry for '{name}' is not a SHA-256 hex digest")
            entries.append((digest, Identity(PEER, name)))
        for digest, role in ((observer_token_sha256, OBSERVER), (user_token_sha256, USER)):
            if digest:
                entries.append((digest.lower(), Identity(role)))
        self._shared_sha256 = token_sha256(shared_token) if shared_token else None
        if self._shared_sha256 and allow_shared_token:
            entries.append((self._shared_sha256, Identity(PEER, shared=True)))
        digests = [digest for digest, _ in entries]
        if len(set(digests)) != len(digests):
            raise ValueError("auth: the same token is configured for more than one peer or role")
        self._entries = entries
        self._bound_names = frozenset(peer_token_sha256)

    def identity_for(self, authorization: str) -> Identity | None:
        """The identity of an "Authorization: Bearer <token>" header, None if unknown."""
        token = _bearer_token(authorization)
        if token is None:
            return None
        sent = token_sha256(token)
        found = None
        # Compare against every entry, so the time taken does not tell which matched
        for known, identity in self._entries:
            if hmac.compare_digest(sent, known):
                found = identity
        return found

    def refusal_reason(self, authorization: str) -> str:
        """Why identity_for refused this header, for the log; never the token."""
        token = _bearer_token(authorization)
        if token is None:
            return "missing_token"
        if self._shared_sha256 and hmac.compare_digest(token_sha256(token), self._shared_sha256):
            return "shared_token_disabled"
        return "unknown_token"

    def register_refusal(self, identity: Identity, name: str) -> str | None:
        """Why identity may not register name, None if it may."""
        if is_reserved_name(name):
            return "reserved_name"
        if identity.peer_name is not None and name != identity.peer_name:
            return "name_not_bound_to_token"
        if identity.shared and name in self._bound_names:
            return "name_bound_to_other_token"
        return None

    def watch_refusal(self, identity: Identity, name: str) -> str | None:
        """Why identity may not watch name (read the messages to it), None if it may.

        A per-peer token watches only its own name. The shared token cannot
        be told apart from any other peer, so it keeps the old open watch:
        one more reason it is off unless allowed.
        """
        if is_reserved_name(name):
            return "reserved_name"
        if identity.peer_name is not None and name != identity.peer_name:
            return "watch_not_own_name"
        if identity.shared and name in self._bound_names:
            return "watch_not_own_name"
        return None

    @staticmethod
    def allows(role: str, message_type: str | None) -> bool:
        return message_type in ALLOWED_MESSAGE_TYPES[role]
