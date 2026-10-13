"""Roles of the Bridge: which token may send which message types, and as whom.

A connection gets its identity from the token it shows in the handshake. The
Bridge knows every token only by its SHA-256, so the config does not give
any away:

- auth.peers maps each peer name (one per machine) to the hash of that
  machine's own token; the token may register (and watch) that name and its
  sessions, "<name>:<label>", and nothing else.
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
# What may follow "<name>:" in a session's name. No colon, so a label cannot
# reach into a name enrolled below this one
SESSION_LABEL = re.compile(r"[A-Za-z0-9._-]{1,64}")


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

    def owner(self, name: str) -> str | None:
        """The enrolled name that name is, or is a session of ("<owner>:..."), None if nobody's.

        Compared with the separator, so "Mini" does not own "MiniOther:x". When
        auth.peers holds both "Host" and "Host:Alice", the longer one owns what
        is under it.
        """
        owners = [bound for bound in self._bound_names if name == bound or name.startswith(bound + ":")]
        return max(owners, key=len, default=None)

    def is_machine(self, name: str) -> bool:
        """Whether name is enrolled in auth.peers: a message to it reaches every session under it."""
        return name in self._bound_names

    def register_refusal(self, identity: Identity, name: str) -> str | None:
        """Why identity may not register name, None if it may.

        A per-peer token registers its own name and its sessions,
        "<name>:<label>": several Claude Code sessions on one machine, each
        reachable, with the one token the machine was enrolled with.
        """
        if is_reserved_name(name):
            return "reserved_name"
        if identity.peer_name is not None:
            if self.owner(name) != identity.peer_name:
                return "name_not_bound_to_token"
            if name != identity.peer_name and not SESSION_LABEL.fullmatch(name[len(identity.peer_name) + 1:]):
                return "invalid_session_label"
        if identity.shared and self.owner(name) is not None:
            return "name_bound_to_other_token"
        return None

    def watch_refusal(self, identity: Identity, name: str) -> str | None:
        """Why identity may not watch name (read the messages to it), None if it may.

        A per-peer token watches only its own name and its sessions. The
        shared token cannot be told apart from any other peer, so it keeps
        the old open watch: one more reason it is off unless allowed.
        """
        if is_reserved_name(name):
            return "reserved_name"
        if identity.peer_name is not None and self.owner(name) != identity.peer_name:
            return "watch_not_own_name"
        if identity.shared and self.owner(name) is not None:
            return "watch_not_own_name"
        return None

    @staticmethod
    def allows(role: str, message_type: str | None) -> bool:
        return message_type in ALLOWED_MESSAGE_TYPES[role]
