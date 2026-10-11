# pylint: disable=global-statement,line-too-long,logging-fstring-interpolation  # upstream AI-Connect style, kept to minimise the fork's diff
"""WebSocket client that connects an MCP server to the AI-Connect Bridge."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from http import HTTPStatus

import websockets
from websockets import ClientConnection

logger = logging.getLogger(__name__)

# How long a request to the Bridge (peer list, history) may take
REQUEST_TIMEOUT_SECONDS = 5.0
PING_INTERVAL_SECONDS = 25
# Sender of the client's own notices in the message queue, like the Bridge's
NOTICE_SENDER = "Bridge"


class BridgeClient:
    """Keeps the connection to the Bridge Server and queues incoming messages."""

    def __init__(self, host: str, port: int, peer_name: str, token: str):
        self.host = host
        self.port = port
        self.peer_name = peer_name
        self._token = token

        self._ws: ClientConnection | None = None
        # True only while registered under peer_name
        self._connected = False
        self._reconnecting = False
        self._should_reconnect = True
        # Another live session holds the name: wait until it is free (the
        # Bridge refuses a takeover with name_taken)
        self._standby = False
        # name_taken is answered with one standby register per connection;
        # a second one is not retried, so the two cannot loop
        self._standby_retried = False
        # The Bridge refused the token; retrying cannot help until the
        # config is fixed and the client restarted
        self._token_refused = False
        # Own state and status line; the Bridge forgets them with the
        # connection, so they are sent again after every registration
        self._state: tuple[str, str] | None = None
        self._status = ""
        self._message_queue: list[dict] = []
        # Answers to requests, keyed by the response type ("peer_list", "history")
        self._pending: dict[str, asyncio.Future] = {}
        self._receive_task: asyncio.Task | None = None
        self._ping_task: asyncio.Task | None = None
        self._reconnect_task: asyncio.Task | None = None

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def reconnecting(self) -> bool:
        return self._reconnecting

    @property
    def standby(self) -> bool:
        return self._standby

    @property
    def token_refused(self) -> bool:
        return self._token_refused

    async def connect(self) -> bool:
        """Connect to the Bridge and register under peer_name.

        On standby the Bridge registers the client only once the name is free.
        """
        uri = f"ws://{self.host}:{self.port}"
        try:
            self._ws = await websockets.connect(
                uri,
                ping_interval=60,
                ping_timeout=300,
                additional_headers={"Authorization": f"Bearer {self._token}"},
            )
        except websockets.exceptions.InvalidStatus as e:
            if e.response.status_code != HTTPStatus.UNAUTHORIZED:
                raise
            logger.error(f"Bridge at {uri} refused the token: check client.token in config.yaml")
            self._connected = False
            self._token_refused = True
            self._should_reconnect = False
            return False
        except (OSError, websockets.exceptions.InvalidHandshake) as e:
            logger.error(f"Cannot reach Bridge at {uri}: {e}")
            self._connected = False
            return False

        self._connected = not self._standby
        self._reconnecting = False
        self._standby_retried = False
        await self._register()

        for task in (self._receive_task, self._ping_task):
            if task and not task.done():
                task.cancel()
        self._receive_task = asyncio.create_task(self._receive_loop())
        self._ping_task = asyncio.create_task(self._ping_loop())

        state = "on standby for" if self._standby else "as"
        logger.info(f"Connected to Bridge at {uri} {state} '{self.peer_name}'")
        return True

    async def disconnect(self) -> None:
        """Close the connection and stop reconnecting."""
        self._connected = False
        self._should_reconnect = False
        for task in (self._reconnect_task, self._receive_task, self._ping_task):
            if task and not task.done():
                task.cancel()
        if self._ws:
            await self._ws.close()
            self._ws = None

    def start_reconnect(self) -> None:
        """Keep trying to reach the Bridge in the background."""
        if self._should_reconnect and not self._reconnecting:
            self._reconnect_task = asyncio.create_task(self._reconnect())

    async def send_message(self, to: str, content: str, context: dict | None = None) -> bool:
        """Send a message to a peer (or '*' for every online peer)."""
        if not self._connected:
            return False
        return await self._send({
            "type": "message",
            "to": to,
            "content": content,
            "context": context
        })

    async def list_peers(self) -> list[dict]:
        """Ask the Bridge for the peers that are online."""
        response = await self._request({"type": "list_peers"}, "peer_list")
        return response.get("peers", [])

    async def get_history(self, peer: str, limit: int) -> list[dict]:
        """Ask the Bridge for the conversation with a peer, oldest first."""
        response = await self._request({"type": "history", "peer": peer, "limit": limit}, "history")
        return response.get("messages", [])

    async def set_state(self, state: str, detail: str) -> bool:
        """Report this peer's state ("busy", "idle", "waiting"); unchanged states are not resent."""
        if self._state == (state, detail):
            return True
        self._state = (state, detail)
        return await self._send_state()

    async def set_status(self, status: str) -> bool:
        """Report what this peer is working on, shown in peer_list."""
        self._status = status
        return await self._send({"type": "set_status", "status": status})

    async def notify_when_idle(self, peer: str) -> bool:
        """Ask the Bridge for one message as soon as peer is done or waits for approval."""
        return await self._send({"type": "notify_when_idle", "peer": peer})

    async def _send_state(self) -> bool:
        if self._state is None:
            return True
        state, detail = self._state
        return await self._send({"type": "set_state", "state": state, "detail": detail})

    def pop_messages(self) -> list[dict]:
        """Return and clear the received messages."""
        messages = self._message_queue.copy()
        self._message_queue.clear()
        return messages

    async def _request(self, data: dict, response_type: str) -> dict:
        """Send a request and wait for the Bridge's answer of response_type."""
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[response_type] = future
        try:
            if not await self._send(data):
                raise ConnectionError("Not connected to the Bridge")
            return await asyncio.wait_for(future, timeout=REQUEST_TIMEOUT_SECONDS)
        finally:
            self._pending.pop(response_type, None)

    async def _register(self) -> bool:
        return await self._send({"type": "register", "name": self.peer_name, "standby": self._standby})

    def _queue_notice(self, content: str) -> None:
        """Put a notice of this client into the message queue, read by peer_read."""
        self._message_queue.append({
            "from": NOTICE_SENDER,
            "to": self.peer_name,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def _send(self, data: dict) -> bool:
        """Send JSON over the WebSocket; a lost connection starts a reconnect."""
        if not self._ws:
            self.start_reconnect()
            return False
        try:
            await self._ws.send(json.dumps(data))
            return True
        except websockets.exceptions.ConnectionClosed:
            logger.warning("Connection lost while sending")
            self._connected = False
            self._ws = None
            self.start_reconnect()
            return False

    async def _receive_loop(self) -> None:
        """Handle everything the Bridge sends."""
        ws = self._ws
        if ws is None:
            return
        try:
            async for raw in ws:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("Received invalid JSON from the Bridge")
                    continue
                await self._handle(data)
        except websockets.exceptions.ConnectionClosed:
            pass
        # A clean close by the Bridge ends the loop without an exception, so
        # the state is reset here for both cases.
        logger.warning("Connection to the Bridge lost")
        self._connected = False
        self._ws = None
        self.start_reconnect()

    async def _handle(self, data: dict) -> None:
        """Dispatch one message from the Bridge."""
        msg_type = data.get("type")

        if msg_type == "message":
            self._message_queue.append(data)

        elif msg_type == "unread":
            messages = data.get("messages", [])
            self._message_queue.extend(messages)

        elif msg_type in self._pending:
            future = self._pending[msg_type]
            if not future.done():
                future.set_result(data)

        elif msg_type == "peer_joined":
            logger.info(f"Peer joined: {data.get('peer', {}).get('name')}")

        elif msg_type == "peer_left":
            logger.info(f"Peer left: {data.get('peer')}")

        elif msg_type == "registered":
            if self._standby:
                self._standby = False
                self._connected = True
                logger.info(f"Peer name '{self.peer_name}' free again, registered")
                self._queue_notice(f"The other session has left; this session is online again as {self.peer_name}.")
            await self._send_state()
            if self._status:
                await self._send({"type": "set_status", "status": self._status})

        elif msg_type == "standby":
            logger.info(f"Peer name '{self.peer_name}' still taken, waiting on standby")

        elif msg_type == "name_free":
            await self._register()

        elif msg_type == "error" and data.get("code") == "name_taken":
            await self._on_name_taken()

        elif msg_type == "error":
            logger.error(f"Bridge reported an error ({data.get('code')}): {data.get('error')}")

    async def _on_name_taken(self) -> None:
        """Another live session holds the name: wait on standby once, never take it over."""
        self._connected = False
        if self._standby_retried:
            logger.error(f"Peer name '{self.peer_name}' refused again (name_taken) after the standby retry; not retrying")
            return
        self._standby_retried = True
        self._standby = True
        logger.warning(
            f"Peer name '{self.peer_name}' is held by another live session (name_taken); "
            "registering on standby until it is free"
        )
        self._queue_notice(
            f"Another session is online as {self.peer_name}. This session is on standby and cannot "
            "send or receive until the other one leaves. Sessions with the same client.name share it: "
            "close one, or start the second with AI_CONNECT_PEER_NAME set to a name with its own token."
        )
        await self._register()

    async def _ping_loop(self) -> None:
        """Tell the Bridge regularly that this peer is alive."""
        while self._ws is not None:
            await asyncio.sleep(PING_INTERVAL_SECONDS)
            if self._connected:
                await self._send({"type": "ping"})

    async def _reconnect(self) -> None:
        """Reconnect with exponential backoff, capped at 30 seconds."""
        self._reconnecting = True
        delay: float = 2
        attempt = 0
        while not self._connected and self._should_reconnect:
            attempt += 1
            logger.info(f"Reconnect attempt {attempt} in {delay:.0f} s")
            await asyncio.sleep(delay)
            if self._should_reconnect and await self.connect():
                logger.info(f"Reconnected after {attempt} attempts")
                break
            delay = min(delay * 1.5, 30)
        self._reconnecting = False


# The one client of this MCP server process, used by the tools
_client: BridgeClient | None = None


def get_client() -> BridgeClient | None:
    """Return this process's Bridge client."""
    return _client


async def init_client(host: str, port: int, peer_name: str, token: str) -> BridgeClient:
    """Create the Bridge client and connect; if the Bridge is unreachable,
    keep trying in the background."""
    global _client
    _client = BridgeClient(host=host, port=port, peer_name=peer_name, token=token)
    if not await _client.connect():
        _client.start_reconnect()
    return _client
