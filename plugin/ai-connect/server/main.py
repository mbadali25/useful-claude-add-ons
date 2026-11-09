"""Entry point of the AI-Connect Bridge Server."""

import asyncio
import logging
import signal
from pathlib import Path

from config_loader import CONFIG_PATH, ServerSettings, load_config, server_settings
from log_setup import setup_logging

from .auth_reload import roles_from
from .limits import Limits
from .message_store import DEFAULT_DB_PATH
from .websocket_server import BridgeServer

logger = logging.getLogger(__name__)


def build_server(settings: ServerSettings, db_path: str = DEFAULT_DB_PATH,
                 config_path: Path | None = None) -> BridgeServer:
    """The Bridge as config.yaml describes it; the one wiring for the service and the tests.

    config_path: the file settings came from. With it the Bridge hot-reloads
    its auth table from that file (revocation and new peers need no restart)
    and redeems join codes into it.
    """
    roles = roles_from(settings)
    if settings.allow_shared_token and settings.shared_token:
        logger.warning("auth.allow_shared_token is on: any holder of auth.token can register unbound names")
    elif not settings.peer_token_sha256:
        logger.error("auth.peers is empty and the shared token is off: no peer can connect")
    return BridgeServer(
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
