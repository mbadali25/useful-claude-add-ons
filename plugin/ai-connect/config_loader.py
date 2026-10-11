# pylint: disable=logging-fstring-interpolation  # upstream AI-Connect style, kept to minimise the fork's diff
"""Reads the AI-Connect config for the Bridge Server and both MCP clients."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

CONFIG_PATH = Path.home() / ".config" / "ai-connect" / "config.yaml"
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
        max_message_bytes=_number(
            server.get("max_message_bytes", DEFAULT_MAX_MESSAGE_BYTES), "server.max_message_bytes", 1
        ),
        rate_per_second=rate,
        rate_burst=_number(server.get("rate_burst", max(1, int(rate))), "server.rate_burst", 1),
        max_stored_per_peer=_number(
            server.get("max_stored_per_peer", DEFAULT_MAX_STORED_PER_PEER), "server.max_stored_per_peer", 0
        ),
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


def client_settings(config: dict) -> ClientSettings:
    """client: {name, token, bridge_url, project_dir}; a pre-2.3 bridge: section is read with a warning."""
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
    return ClientSettings(
        name=client.get("name") or "",
        token=client["token"],
        host=bridge_target(url.hostname),
        port=port,
        project_dir=client.get("project_dir") or "",
    )
