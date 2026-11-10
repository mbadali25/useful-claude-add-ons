"""Entry point of the AI-Connect Bridge Server."""

import asyncio
import json
import logging
import signal
import ssl
from datetime import datetime, timezone
from pathlib import Path

import bridge_tls
import join_codes
from config_loader import CONFIG_PATH, ServerSettings, load_config, server_settings
from log_setup import setup_logging

from .auth_reload import roles_from
from .limits import Limits
from .message_store import DEFAULT_DB_PATH
from .websocket_server import BridgeServer

logger = logging.getLogger(__name__)


def tls_context(settings: ServerSettings, config_dir: Path | None) -> ssl.SSLContext | None:
    """The wss:// listener's context: the certificate in <config_dir>/tls/, made on the first start.

    None when server.tls.enabled is false, or when there is no config
    directory to keep a certificate in (a Bridge built without a config file:
    some tests). bridge_tls.TlsError when TLS is on and the certificate is
    unusable: the Bridge then does not start rather than serve ws:// alone.
    """
    if not settings.tls_enabled:
        logger.warning("server.tls.enabled is false: this Bridge serves plain ws:// only")
        return None
    if config_dir is None:
        if settings.tls_required:
            raise bridge_tls.TlsError("server.tls.required is true, but there is no config directory for the "
                                      "certificate")
        return None
    # Under the lock `ai-connect bridge invite` and `cert` take: one certificate, never two racing
    with join_codes.auth_lock(Path(config_dir)):
        info, created = bridge_tls.ensure(config_dir, settings.tls_validity_days)
    if created:
        logger.warning(json.dumps({"event": "tls_certificate_created", "path": str(info.cert_path),
                                   "fingerprint": info.fingerprint, "expires": info.not_after.isoformat()}))
    else:
        logger.info(json.dumps({"event": "tls_certificate", "fingerprint": info.fingerprint,
                                "expires": info.not_after.isoformat()}))
    if info.not_after <= datetime.now(timezone.utc):
        # A pin trusts the exact certificate, dates included: an expired one is still the pinned one, so it
        # still connects. Said loudly so that it gets rotated
        logger.error(json.dumps({"event": "tls_certificate_expired", "expired": info.not_after.isoformat(),
                                 "detail": "run `ai-connect bridge cert rotate` and re-pin the peers"}))
    return bridge_tls.server_context(info)


def build_server(settings: ServerSettings, db_path: str = DEFAULT_DB_PATH,
                 config_path: Path | None = None, tls_dir: Path | None = None) -> BridgeServer:
    """The Bridge as config.yaml describes it; the one wiring for the service and the tests.

    config_path: the file settings came from. With it the Bridge hot-reloads
    its auth table from that file (revocation and new peers need no restart)
    and redeems join codes into it. tls_dir: the directory whose tls/ holds
    the certificate; default config_path's directory.
    """
    roles = roles_from(settings)
    if settings.allow_shared_token and settings.shared_token:
        logger.warning("auth.allow_shared_token is on: any holder of auth.token can register unbound names")
    elif not settings.peer_token_sha256:
        logger.error("auth.peers is empty and the shared token is off: no peer can connect")
    config_dir = tls_dir or (Path(config_path).parent if config_path else None)
    context = tls_context(settings, config_dir)
    return BridgeServer(
        ssl_context=context,
        tls_port=settings.tls_port,
        plain=settings.plain_enabled or context is None,
        host=settings.host,
        port=settings.port,
        history_days=settings.history_days,
        roles=roles,
        db_path=db_path,
        config_path=config_path,
        limits=Limits(
            max_message_bytes=settings.max_message_bytes,
            rate_per_second=settings.rate_per_second,
            rate_burst=settings.rate_burst,
            max_stored_per_peer=settings.max_stored_per_peer,
            max_unread_per_peer=settings.max_unread_per_peer,
            max_unread_bytes_per_peer=settings.max_unread_bytes_per_peer,
        ),
    )


async def run_server() -> None:
    server = build_server(server_settings(load_config()), config_path=CONFIG_PATH)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def request_stop(*_: object) -> None:
        loop.call_soon_threadsafe(stop_event.set)

    # signal.signal instead of loop.add_signal_handler: the latter does not
    # exist on Windows
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, request_stop)

    await server.start()
    await stop_event.wait()
    logger.info("Shutting down")
    await server.stop()


def main() -> None:
    # A file as well as stdout: under systemd stdout goes to the journal, but a
    # Windows task without a console has nowhere else to log
    setup_logging("bridge.log", logging.StreamHandler())
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
