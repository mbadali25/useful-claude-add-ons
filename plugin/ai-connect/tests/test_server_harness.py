"""Shared helpers for the server tests: import path, tokens, a live Bridge.

Named test_server_* so it stays inside the server lane's files; it holds no
tests itself. Import it before any repo module: it puts the repo root on
sys.path, which plain `pytest` (unlike `python -m pytest`) does not.
"""

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import websockets  # noqa: E402

from server.limits import Limits  # noqa: E402
from server.roles import Roles, token_sha256  # noqa: E402
from server.websocket_server import BridgeServer  # noqa: E402

ALICE_TOKEN = "alice-token-0123456789"
BOB_TOKEN = "bob-token-0123456789"
OBSERVER_TOKEN = "observer-token-0123456789"
USER_TOKEN = "user-token-0123456789"
SHARED_TOKEN = "shared-token-0123456789"
ALICE = "Host:Alice"
BOB = "Host:Bob"


def make_roles(allow_shared_token: bool = False, shared_token: str | None = SHARED_TOKEN) -> Roles:
    return Roles(
        peer_token_sha256={ALICE: token_sha256(ALICE_TOKEN), BOB: token_sha256(BOB_TOKEN)},
        observer_token_sha256=token_sha256(OBSERVER_TOKEN),
        user_token_sha256=token_sha256(USER_TOKEN),
        shared_token=shared_token,
        allow_shared_token=allow_shared_token,
    )


class FrozenClock:
    """A monotonic clock that moves only when told to."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@asynccontextmanager
async def running_bridge(tmp_path: Path, limits: Limits | None = None, clock=None, allow_shared_token=False):
    kwargs = {"clock": clock} if clock else {}
    server = BridgeServer(
        host="127.0.0.1",
        port=0,
        history_days=14,
        roles=make_roles(allow_shared_token=allow_shared_token),
        db_path=str(tmp_path / "messages.db"),
        limits=limits or Limits(),
        **kwargs,
    )
    await server.start()
    try:
        yield server
    finally:
        await server.stop()


def connect(server: BridgeServer, token: str):
    return websockets.connect(
        f"ws://127.0.0.1:{server.bound_port}", additional_headers={"Authorization": f"Bearer {token}"}
    )


async def send(ws, **message) -> None:
    await ws.send(json.dumps(message))


async def recv(ws, timeout: float = 2.0) -> dict:
    return json.loads(await asyncio.wait_for(ws.recv(), timeout))


async def recv_type(ws, wanted: str, timeout: float = 2.0) -> dict:
    """The next frame of type wanted, skipping peer_joined and the like."""
    while True:
        frame = await recv(ws, timeout)
        if frame.get("type") == wanted:
            return frame


async def register(ws, name: str, **extra) -> dict:
    await send(ws, type="register", name=name, **extra)
    return await recv(ws)


async def nothing_arrives(ws, timeout: float = 0.3) -> bool:
    try:
        await asyncio.wait_for(ws.recv(), timeout)
    except asyncio.TimeoutError:
        return True
    return False
