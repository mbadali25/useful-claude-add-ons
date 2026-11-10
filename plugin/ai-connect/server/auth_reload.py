"""Hot reload of the Bridge's auth table: revocation and new peers without a restart.

The Bridge polls config.yaml every AUTH_RELOAD_SECONDS (polling, not a file
watcher: it works the same on Windows and Linux and needs no dependency). Each
poll hashes the file's bytes; when the hash moved, the auth: section is read
and a new Roles built. Only a table that builds whole is
swapped in: a config that does not parse, or whose auth: is invalid, is logged
and the old table stays. The swap itself is one attribute assignment on the
event loop, so no handshake ever sees half a table.

What changes in the swap: every peer, the observer and user tokens, and the
shared-token switch. The listen address, port and limits are read once at
start; a change to them still needs a restart, and the reload says so.
"""

import hashlib
import json
import logging
from collections.abc import Callable
from pathlib import Path

import yaml

from config_loader import server_settings

from .roles import Roles

logger = logging.getLogger(__name__)

AUTH_RELOAD_SECONDS = 2.0


def _safe_detail(err: Exception) -> str:
    """What a reload failure may log. A YAML error's message quotes the offending text, and config.yaml holds
    tokens and hashes: only its line and column. Other errors are this code's own messages."""
    if isinstance(err, yaml.YAMLError):
        mark = getattr(err, "problem_mark", None)
        return f"line {mark.line + 1}, column {mark.column + 1}" if mark else "not valid YAML"
    return str(err)[:200]


def roles_from(settings) -> Roles:
    """The auth table of a ServerSettings; the one place both start and reload build it."""
    return Roles(
        peer_token_sha256=settings.peer_token_sha256,
        observer_token_sha256=settings.observer_token_sha256,
        user_token_sha256=settings.user_token_sha256,
        shared_token=settings.shared_token,
        allow_shared_token=settings.allow_shared_token,
    )


class AuthReloader:
    """Watches one config file; check() returns a new Roles when its auth changed and builds."""

    def __init__(self, path: Path, on_static_change: Callable[[str], None] | None = None):
        self.path = Path(path)
        self._readable = True
        self._digest: str | None = None
        # The digest of a file that failed to build, so a broken config is logged once, not every poll
        self._failed_digest: str | None = None
        self._static: tuple | None = None
        self._on_static_change = on_static_change
        self.prime()

    def prime(self) -> None:
        """Note the server: settings as they are now, to warn when one changes.

        The digest is deliberately not taken: the Bridge built its table from a
        read made earlier, and an edit in between must not be mistaken for the
        baseline. The first poll rebuilds the same table from the file, which
        closes nobody whose token is still in it.
        """
        try:
            data = self.path.read_bytes()
        except OSError:
            return
        try:
            self._static = self._static_part(server_settings(yaml.safe_load(data) or {}))
        except (ValueError, yaml.YAMLError, AttributeError, TypeError):
            self._static = None

    @staticmethod
    def _static_part(settings) -> tuple:
        return (settings.host, settings.port, settings.history_days, settings.max_message_bytes,
                settings.rate_per_second, settings.rate_burst, settings.max_stored_per_peer,
                settings.max_unread_per_peer, settings.max_unread_bytes_per_peer,
                settings.tls_enabled, settings.tls_port, settings.tls_required, settings.tls_validity_days)

    def check(self) -> Roles | None:
        """A new table when the file's auth changed and is valid; None when unchanged or broken (logged)."""
        try:
            data = self.path.read_bytes()
        except OSError:
            if self._readable:
                logger.error(json.dumps({"event": "auth_reload_failed", "reason": "config_unreadable",
                                         "path": str(self.path), "kept": "previous auth table"}))
                self._readable = False
            return None
        self._readable = True
        # Hashed on every poll, not only when mtime moves: a rewrite of the same
        # size within one timestamp tick (coarse file systems) must not be missed,
        # and config.yaml is a few kilobytes
        digest = hashlib.sha256(data).hexdigest()
        if digest in (self._digest, self._failed_digest):
            # Unchanged, or the same broken file again: logged once, at its first poll
            return None
        try:
            config = yaml.safe_load(data)
            if not isinstance(config, dict):
                raise ValueError("config.yaml is not a mapping")
            settings = server_settings(config)
            roles = roles_from(settings)
        except (ValueError, yaml.YAMLError, AttributeError, TypeError) as err:
            # The digest is not taken: the next edit that fixes the file is tried again
            self._failed_digest = digest
            logger.error(json.dumps({"event": "auth_reload_failed", "reason": type(err).__name__,
                                     "detail": _safe_detail(err), "kept": "previous auth table"}))
            return None
        self._failed_digest = None
        self._digest = digest
        static = self._static_part(settings)
        if self._static is not None and static != self._static and self._on_static_change:
            self._on_static_change("server: settings changed; they take effect on the next restart")
        self._static = static
        return roles
