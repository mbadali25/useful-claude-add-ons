"""Messages from a human user, sent through a tool with the user token.

The sender is always "User:<name>": the tool passes the name, the Bridge
sets the prefix, and peers may not take a name with it. So no agent can
pose as the user, and the instruction rule for agents can rely on it.
"""

import re

USER_PREFIX = "User:"
# Sender of the Bridge's own notices
BRIDGE_SENDER = "Bridge"
_USER_NAME = re.compile(r"[A-Za-z0-9_.-]+")


def is_user_name(peer_name: str) -> bool:
    return peer_name.startswith(USER_PREFIX)


def is_reserved_name(peer_name: str) -> bool:
    """Names only the Bridge and users have; no peer may register or watch them.

    Compared without case, so "bridge" or "user:x" cannot pass for them.
    """
    folded = peer_name.casefold()
    return folded == BRIDGE_SENDER.casefold() or folded.startswith(USER_PREFIX.casefold())


def is_user_recipient(peer_name: str) -> bool:
    """Whether a peer may send to this name: exactly "User:<valid name>".

    Registering or watching a user name stays refused; replying to one is
    the documented way an agent answers its user.
    """
    return peer_name.startswith(USER_PREFIX) and user_sender(peer_name[len(USER_PREFIX):]) == peer_name


def user_sender(as_name: object) -> str | None:
    """"User:<as_name>", or None if as_name is not a valid name."""
    if not isinstance(as_name, str) or not _USER_NAME.fullmatch(as_name):
        return None
    return USER_PREFIX + as_name


def valid_recipients(recipients: object) -> list[str] | None:
    """The recipient names, or None unless a non-empty list of peer names (or "*").

    Reserved names (Bridge, User:...) are not peer names.
    """
    if not isinstance(recipients, list) or not recipients:
        return None
    if not all(isinstance(name, str) and name and not is_reserved_name(name) for name in recipients):
        return None
    return recipients
