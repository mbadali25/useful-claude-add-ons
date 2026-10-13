# pylint: disable=logging-fstring-interpolation  # upstream AI-Connect style, kept to minimise the fork's diff
"""Reads the AI-Connect config for the Bridge Server and both MCP clients."""

import errno
import logging
import os
import re
import stat
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from peer_name import PER_PROJECT, is_reserved_name, project_dir, project_peer_name

CONFIG_PATH = Path.home() / ".config" / "ai-connect" / "config.yaml"
# One owner-only token per second peer name on this machine (session_token)
SESSION_TOKEN_DIR = CONFIG_PATH.parent / "session-tokens"
# vpn/tsadmin.py PEER_NAME_RE: the names deploy and setup accept
_SESSION_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,62}")
# Kept out of config.yaml, which every agent reads: the Claude Code settings
# deny reading these files (see installer.py observer-token, user-token)
OBSERVER_TOKEN_PATH = CONFIG_PATH.parent / "observer.token"
USER_TOKEN_PATH = CONFIG_PATH.parent / "user.token"


def load_config() -> dict:
    """Load ~/.config/ai-connect/config.yaml.

    No defaults: without a config the services would silently talk to
    some built-in address. Missing file or missing keys stop the start
    with a message instead.
    """
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"AI-Connect config not found: {CONFIG_PATH}\n"
            f"Run ./install.sh or create it from config.yaml.example."
        )
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


# Listening on these means "on every address of this machine"; as a target
# they mean this machine. Linux accepts 0.0.0.0 as a target, Windows refuses
# it (WinError 1214), so clients on the Bridge machine connect to loopback.
_LISTEN_ALL_TO_LOOPBACK = {"0.0.0.0": "127.0.0.1", "::": "::1"}


def bridge_target(host: str) -> str:
    """The address a client connects to for a Bridge listening on host."""
    return _LISTEN_ALL_TO_LOOPBACK.get(host, host)


# The Bridge Server's settings. Unlike the rest of the config these have
# defaults: each one is the safe choice, so a missing key closes, not opens.
DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_HISTORY_DAYS = 14
DEFAULT_MAX_MESSAGE_BYTES = 64 * 1024
DEFAULT_RATE_PER_SECOND = 10.0
DEFAULT_MAX_STORED_PER_PEER = 10_000
DEFAULT_MAX_UNREAD_PER_PEER = 500
DEFAULT_MAX_UNREAD_BYTES_PER_PEER = 8 * 1024 * 1024


@dataclass(frozen=True)
class ServerSettings:
    host: str
    port: int
    history_days: int
    # auth.peers: peer name -> SHA-256 hex of that peer's own token
    peer_token_sha256: dict[str, str]
    # auth.token, the legacy token every peer shared; used only if allowed
    shared_token: str | None
    allow_shared_token: bool
    observer_token_sha256: str
    user_token_sha256: str
    max_message_bytes: int
    rate_per_second: float
    rate_burst: int
    max_stored_per_peer: int
    max_unread_per_peer: int
    max_unread_bytes_per_peer: int


def _number(value: Any, key: str, minimum: float, kind: type = int) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or (kind is int and not isinstance(value, int)):
        raise ValueError(f"{key} must be a number, got {value!r}")
    if value < minimum:
        raise ValueError(f"{key} must be at least {minimum}, got {value!r}")
    return value


_deprecation_logger = logging.getLogger("ai_connect.config")


def _deprecated(old: str, new: str) -> None:
    _deprecation_logger.warning(f"config.yaml: {old} is deprecated, read as {new}; rename it")


def _setting(section: dict, key: str, bridge: dict, new_section: str, default: Any = None) -> Any:
    """section[key]; else the pre-2.3 bridge[key] with a deprecation warning; else default."""
    if key in section:
        return section[key]
    if key in bridge:
        _deprecated(f"bridge.{key}", f"{new_section}.{key}")
        return bridge[key]
    return default


def server_settings(config: dict) -> ServerSettings:
    """The Bridge's settings from server: and auth:, with safe defaults.

    bridge.host is not a fallback for the listen address: it is also the
    address clients connected to, and an old "0.0.0.0" there would keep the
    Bridge open on every interface. bridge.port, bridge.history_days and the
    bridge.*_token_sha256 keys are still read, with a deprecation warning, so
    an existing config keeps working. bridge.token is not: it was what clients
    sent, now client.token.
    """
    server = config.get("server") or {}
    auth = config.get("auth") or {}
    bridge = config.get("bridge") or {}

    port = _setting(server, "port", bridge, "server")
    if port is None:
        raise ValueError("server.port is required")
    rate = _number(server.get("rate_per_second", DEFAULT_RATE_PER_SECOND), "server.rate_per_second", 0.001, float)
    max_message_bytes = _number(
        server.get("max_message_bytes", DEFAULT_MAX_MESSAGE_BYTES), "server.max_message_bytes", 1
    )
    # Minimum 1, not 0: the caps are compared as count + 1 <= cap, so 0 would
    # refuse every message to an offline peer rather than lift the cap
    max_unread_bytes = _number(
        server.get("max_unread_bytes_per_peer", DEFAULT_MAX_UNREAD_BYTES_PER_PEER),
        "server.max_unread_bytes_per_peer", 1,
    )
    if max_unread_bytes < max_message_bytes:
        raise ValueError(
            f"server.max_unread_bytes_per_peer ({max_unread_bytes}) must be at least "
            f"server.max_message_bytes ({max_message_bytes}), or an offline peer cannot be sent one large message"
        )

    peers = auth.get("peers") or {}
    if not isinstance(peers, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in peers.items()):
        raise ValueError("auth.peers must map peer names to SHA-256 hex strings")

    return ServerSettings(
        host=server.get("host") or DEFAULT_SERVER_HOST,
        port=_number(port, "server.port", 0),
        history_days=_number(
            _setting(server, "history_days", bridge, "server", DEFAULT_HISTORY_DAYS), "server.history_days", 1
        ),
        peer_token_sha256=dict(peers),
        shared_token=auth.get("token") or None,
        allow_shared_token=auth.get("allow_shared_token") is True,
        observer_token_sha256=_setting(auth, "observer_token_sha256", bridge, "auth", "") or "",
        user_token_sha256=_setting(auth, "user_token_sha256", bridge, "auth", "") or "",
        max_message_bytes=max_message_bytes,
        rate_per_second=rate,
        rate_burst=_number(server.get("rate_burst", max(1, int(rate))), "server.rate_burst", 1),
        max_stored_per_peer=_number(
            server.get("max_stored_per_peer", DEFAULT_MAX_STORED_PER_PEER), "server.max_stored_per_peer", 0
        ),
        max_unread_per_peer=_number(
            server.get("max_unread_per_peer", DEFAULT_MAX_UNREAD_PER_PEER), "server.max_unread_per_peer", 1
        ),
        max_unread_bytes_per_peer=max_unread_bytes,
    )


@dataclass(frozen=True)
class ClientSettings:
    """This machine's peer identity: kept apart from auth:, which is the Bridge's.

    A Bridge machine runs a peer of its own Bridge too, from the same
    config.yaml; with the client's token in auth.token the two would collide.
    """
    # "" = the STDIO client names itself Host:Project (see peer_name.py)
    name: str
    token: str
    host: str
    port: int
    # "" = the directory the MCP server started in
    project_dir: str

    @property
    def uri(self) -> str:
        return ws_uri(self.host, self.port)


def ws_uri(host: str, port: int) -> str:
    """The Bridge's WebSocket URI; an IPv6 literal is bracketed."""
    host = f"[{host}]" if ":" in host else host
    return f"ws://{host}:{port}"


MISSING = "missing"


def read_session_token(name: str, directory: Path | None = None) -> tuple[str | None, str]:
    """(token, "") for session-tokens/<name>.token, else (None, why); why is MISSING when there is no file.

    The file must be a regular file (a symbolic link is not followed), and on
    Linux and macOS owned by this user with no group or other permission bit
    (mode 600, or stricter). On Windows only the regular-file part is checked:
    setup writes the file with an ACL of the current user alone
    (vpn/tsadmin.py write_owner_only), and nothing here reads that ACL back.
    """
    path = (directory or SESSION_TOKEN_DIR) / f"{name}.token"
    # O_NONBLOCK: a FIFO put there must not hang the client; a regular file reads as usual
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        if os.name == "nt" and path.is_symlink():
            return None, f"{path} is not a regular file"
        fd = os.open(path, flags)
    except FileNotFoundError:
        return None, MISSING
    except OSError as err:
        if err.errno == errno.ELOOP:
            return None, f"{path} is not a regular file (a symbolic link)"
        return None, f"{path} could not be read ({err.strerror})"
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return None, f"{path} is not a regular file"
        if os.name != "nt":
            if st.st_uid != os.getuid():
                return None, f"{path} is not owned by this user"
            if st.st_mode & 0o077:
                return None, f"{path} has mode {stat.S_IMODE(st.st_mode):o}, not 600 (owner-only)"
        chunks = []
        while chunk := os.read(fd, 4096):
            chunks.append(chunk)
        token = b"".join(chunks).decode("utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None, f"{path} could not be read"
    finally:
        os.close(fd)
    return (token, "") if token else (None, f"{path} is empty")


def recorded_project(name: str, directory: Path | None = None) -> tuple[str | None, str]:
    """(path, "") from session-tokens/<name>.dir, (None, "") when there is none, else (None, why).

    The format: UTF-8 text, one line, the project's absolute resolved path
    (Path(dir).resolve()); one trailing newline is allowed, nothing else.
    """
    path = (directory or SESSION_TOKEN_DIR) / f"{name}.dir"
    try:
        if path.is_symlink() or (path.exists() and not path.is_file()):
            return None, f"{path} is not a regular file"
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, ""
    except (OSError, UnicodeDecodeError):
        return None, f"{path} could not be read"
    recorded = text[:-1] if text.endswith("\n") else text
    recorded = recorded[:-1] if recorded.endswith("\r") else recorded
    if not recorded or "\n" in recorded or not Path(recorded).is_absolute():
        return None, f"{path} does not hold one absolute directory"
    return recorded, ""


def session_token(name: str | None, configured: str = "", directory: Path | None = None) -> str | None:
    """The token of a second peer name on this machine, or None.

    Every session here joins as client.name with client.token, and a live name
    cannot be taken over, so only one is online at a time. A second session
    started with AI_CONNECT_PEER_NAME=<name> needs a token bound to that name:
    `deploy/setup.sh session --name <name>` makes it, owner-only, in
    session-tokens/<name>.token. Without that file the session sends
    client.token, as before, and the Bridge refuses the name.

    The name becomes a file name, so only a plain peer name is looked up, and
    never a name the Bridge reserves. The file is read_session_token()'s.
    """
    if not name or name == configured or not _SESSION_NAME.fullmatch(name) or is_reserved_name(name):
        return None
    return read_session_token(name, directory)[0]


def _fall_back(why: str, configured: str) -> None:
    """The one line per-project mode says when it joins as client.name: stderr, as stdout is the MCP protocol."""
    print(f"ai-connect: client.name_mode per-project: {why}; joining as client.name "
          f"'{configured}' with client.token", file=sys.stderr, flush=True)


def per_project_identity(configured: str, environ: Mapping[str, str], cwd: Path,
                         directory: Path | None = None) -> tuple[str, str | None, str]:
    """(name, token, "") for client.name_mode: per-project, or (configured, None, why) to fall back.

    The name is project_peer_name(client.name, the project); the token is that
    name's session-tokens/<name>.token, and a <name>.dir beside it, if there,
    must record this very project.
    """
    project = project_dir(environ, cwd)
    if not configured:
        return configured, None, "it needs client.name"
    name = project_peer_name(configured, project)
    if name is None:
        return configured, None, f"'{project.name}' gives no usable peer name"
    token, why = read_session_token(name, directory)
    if token is None:
        if why == MISSING:
            why = (f"no token for '{name}' in {(directory or SESSION_TOKEN_DIR) / (name + '.token')} "
                   f"(deploy/setup.sh session --project {project})")
        return configured, None, why
    recorded, why = recorded_project(name, directory)
    if why:
        return configured, None, why
    if recorded is not None and os.path.normcase(recorded) != os.path.normcase(str(project)):
        return configured, None, f"'{name}' belongs to {recorded}, not {project}"
    return name, token, ""


def client_settings(config: dict, environ: Mapping[str, str] | None = None, cwd: Path | None = None,
                    name: str | None = None) -> ClientSettings:
    """client: {name, name_mode, token, bridge_url, project_dir}; a pre-2.3 bridge: section is read with a warning.

    The token is session_token()'s when AI_CONNECT_PEER_NAME names a second
    peer that has one, else client.token. With client.name_mode: per-project
    and no AI_CONNECT_PEER_NAME, name and token are per_project_identity()'s,
    or client.name and client.token with one line on stderr.

    name: a peer name already chosen, by the session's client (the watcher
    passes the one it recorded): only its token is looked up.
    """
    environ = os.environ if environ is None else environ
    client = config.get("client")
    if not client and config.get("bridge"):
        bridge = config["bridge"]
        _deprecated("bridge.host/port/token", "client.bridge_url/token")
        client = {
            "name": (config.get("peer") or {}).get("name", ""),
            "token": bridge.get("token", ""),
            "bridge_url": f"ws://{bridge.get('host', '')}:{bridge.get('port', '')}",
        }
    client = client or {}
    url = urlsplit(client.get("bridge_url") or "")
    try:
        port = url.port
    except ValueError:
        port = None
    if url.scheme != "ws" or not url.hostname or port is None:
        raise ValueError(f"client.bridge_url must look like ws://<bridge VPN address>:<port>, got {url.geturl()!r}")
    if not client.get("token"):
        raise ValueError("client.token is required (installer.py add-peer <name> on the Bridge machine prints one)")
    mode = client.get("name_mode") or ""
    if mode not in ("", PER_PROJECT):
        raise ValueError(f"client.name_mode must be {PER_PROJECT!r} or left out, got {mode!r}")
    configured = client.get("name") or ""
    chosen, token = configured, None
    if name is not None:
        token = session_token(name, configured)
    elif "AI_CONNECT_PEER_NAME" in environ:
        token = session_token(environ.get("AI_CONNECT_PEER_NAME"), configured)
    elif mode == PER_PROJECT:
        chosen, token, why = per_project_identity(configured, environ, Path.cwd() if cwd is None else cwd)
        if why:
            _fall_back(why, configured)
    return ClientSettings(
        name=chosen,
        token=token or client["token"],
        host=bridge_target(url.hostname),
        port=port,
        project_dir=client.get("project_dir") or "",
    )
