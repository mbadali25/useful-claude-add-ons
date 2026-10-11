# pylint: disable=global-statement,line-too-long,logging-fstring-interpolation  # upstream AI-Connect style, kept to minimise the fork's diff
"""WebSocket client that connects an MCP server to the AI-Connect Bridge."""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from http import HTTPStatus

import websockets
from websockets import ClientConnection

from config_loader import DEFAULT_MAX_MESSAGE_BYTES, ws_uri

logger = logging.getLogger(__name__)

# How long a request to the Bridge (peer list, history) may take
REQUEST_TIMEOUT_SECONDS = 5.0
PING_INTERVAL_SECONDS = 25
# Sender of the client's own notices in the message queue, like the Bridge's
NOTICE_SENDER = "Bridge"
# The inbound queue, emptied by peer_read. An authenticated peer can send
# faster than this session reads; past either cap newer messages are not
# queued (the Bridge keeps them in its history) and one notice says so
MAX_QUEUED_MESSAGES = 500
MAX_QUEUED_BYTES = 8 * 1024 * 1024
QUEUE_FULL_NOTICE = (
    "This session's message queue is full, so newer messages are not queued until peer_read "
    "empties it. Direct messages stay in the Bridge's history: read a missed conversation with "
    "peer_history. Broadcasts missed meanwhile are not in it."
)
REFUSED_NOTICE = "The Bridge refused something this session sent ({code}): {error}"


class MessageTooLarge(ValueError):
    """A message whose frame is over the Bridge's server.max_message_bytes; it is not sent."""

    def __init__(self, size: int, limit: int):
        super().__init__(f"message frame of {size} bytes is over the Bridge's limit of {limit}")
        self.size = size
        self.limit = limit


def max_message_bytes() -> int:
    """The Bridge's frame limit as this client knows it: AI_CONNECT_MAX_MESSAGE_BYTES or the default."""
    return int(os.environ.get("AI_CONNECT_MAX_MESSAGE_BYTES") or DEFAULT_MAX_MESSAGE_BYTES)


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
        # JSON size of the queue, against MAX_QUEUED_BYTES
        self._queued_bytes = 0
        # Set at the first message the full queue refused, until it is read
        self._overflowing = False
        self._dropped = 0
        # Answers to requests, keyed by the response type ("peer_list", "history")
        self._pending: dict[str, asyncio.Future] = {}
        # One request per response type at a time, and the request_id each waits for
        self._request_locks: dict[str, asyncio.Lock] = {}
        self._pending_ids: dict[str, str] = {}
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
        uri = ws_uri(self.host, self.port)
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
        """Send a message to a peer (or '*' for every online peer).

        Raises MessageTooLarge, before sending, when the frame is over the
        Bridge's limit: the Bridge would refuse it after this returned True.
        """
        if not self._connected:
            return False
        data = {"type": "message", "to": to, "content": content, "context": context}
        size, limit = len(json.dumps(data).encode()), max_message_bytes()
        if size > limit:
            logger.warning(f"Message to {to} not sent: frame of {size} bytes is over the Bridge's limit of {limit}")
            raise MessageTooLarge(size, limit)
        return await self._send(data)

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
        self.drop_messages(len(messages))
        return messages

    def peek_messages(self) -> list[dict]:
        """The received messages, left queued until drop_messages."""
        return self._message_queue.copy()

    def drop_messages(self, count: int) -> None:
        """Clear the first count messages, once they were shown; the queue takes messages again."""
        del self._message_queue[:count]
        self._queued_bytes = sum(len(json.dumps(m)) for m in self._message_queue)
        if self._overflowing:
            logger.warning(f"Inbound queue was full: {self._dropped} messages not queued (they are in the history)")
            self._overflowing, self._dropped = False, 0

    def _enqueue(self, message: object) -> None:
        """Queue one message unless the queue is full; the first refusal of a run queues a notice."""
        size = len(json.dumps(message))
        if len(self._message_queue) < MAX_QUEUED_MESSAGES and self._queued_bytes + size <= MAX_QUEUED_BYTES:
            self._message_queue.append(message)  # type: ignore[arg-type]
            self._queued_bytes += size
            return
        self._dropped += 1
        if not self._overflowing:
            self._overflowing = True
            # Past the caps on purpose: one notice per run of refusals
            self._message_queue.append(self._notice(QUEUE_FULL_NOTICE))

    async def _request(self, data: dict, response_type: str) -> dict:
        """Send a request and wait for the Bridge's answer of response_type."""
        async with self._request_locks.setdefault(response_type, asyncio.Lock()):
            future: asyncio.Future = asyncio.get_running_loop().create_future()
            # The Bridge echoes it: a late answer to a request that timed out
            # is told apart from the answer to this one
            request_id = uuid.uuid4().hex
            self._pending[response_type] = future
            self._pending_ids[response_type] = request_id
            try:
                if not await self._send({**data, "request_id": request_id}):
                    raise ConnectionError("Not connected to the Bridge")
                return await asyncio.wait_for(future, timeout=REQUEST_TIMEOUT_SECONDS)
            finally:
                self._pending.pop(response_type, None)
                self._pending_ids.pop(response_type, None)

    async def _register(self) -> bool:
        return await self._send({"type": "register", "name": self.peer_name, "standby": self._standby})

    def _notice(self, content: str) -> dict:
        return {
            "from": NOTICE_SENDER,
            "to": self.peer_name,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _queue_notice(self, content: str) -> None:
        """Put a notice of this client into the message queue, read by peer_read.

        The same notice twice in a row is queued once (a rate-limit flood).
        Notices carry no id, which tells them from the Bridge's own messages.
        """
        last: object = self._message_queue[-1] if self._message_queue else {}
        if isinstance(last, dict) and last.get("id") is None and last.get("from") == NOTICE_SENDER \
                and last.get("content") == content:
            return
        self._enqueue(self._notice(content))

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
            self._enqueue(data)

        elif msg_type == "unread":
            messages = data.get("messages", [])
            for message in messages if isinstance(messages, list) else [messages]:
                self._enqueue(message)

        elif msg_type in self._pending:
            future = self._pending[msg_type]
            answered = data.get("request_id")
            # No request_id: a Bridge from before it was echoed, matched by type alone
            if answered is not None and answered != self._pending_ids.get(msg_type):
                logger.info(f"Dropped a late '{msg_type}' answer to an abandoned request")
            elif not future.done():
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
            if data.get("code"):
                # A send the Bridge refused was reported as sent: say so where the model reads
                self._queue_notice(REFUSED_NOTICE.format(code=data.get("code"), error=data.get("error")))

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
