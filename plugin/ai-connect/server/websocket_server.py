# pylint: disable=logging-fstring-interpolation  # upstream AI-Connect style, kept to minimise the fork's diff
"""WebSocket server of the AI-Connect Bridge: routes messages between peers."""

import asyncio
import json
import logging
import time
from collections.abc import Callable
from http import HTTPStatus

import websockets
from websockets.asyncio.server import Server, ServerConnection
from websockets.http11 import Request, Response

from .limits import Limits, TokenBucket
from .message_store import DEFAULT_DB_PATH, MessageStore
from .observers import Observers
from .peer_registry import NameTakenError, Peer, PeerRegistry, utc_now
from .roles import Identity, Roles
from .user_send import (
    BRIDGE_SENDER,
    is_reserved_name,
    is_user_name,
    is_user_recipient,
    user_sender,
    valid_recipients,
)

logger = logging.getLogger(__name__)

HEARTBEAT_SECONDS = 60
HISTORY_CLEANUP_SECONDS = 24 * 60 * 60
# Messages in one history_all page; the contents often carry code and files
HISTORY_ALL_MAX_LIMIT = 1000
# Frames above this are closed by websockets itself (1009); between the
# app limit and this, the Bridge answers with an error frame instead
WEBSOCKET_MAX_SIZE_FLOOR = 1 << 20
# Largest unread frame: the client's receive limit (websockets' default
# max_size, 1 MiB); a bigger frame is closed with 1009 and its messages lost
UNREAD_FRAME_MAX_BYTES = 1 << 20
_UNREAD_ENVELOPE_BYTES = len(json.dumps({"type": "unread", "messages": []}))
RATE_LIMITED_ERROR = "Too many messages; slow down"
QUEUE_FULL_ERROR = "'{name}' is offline and has too many messages waiting; not sent"
PEER_STATES = ("busy", "idle", "waiting")
IDLE_NOTICE = "{name} is done and idle."
WAITING_NOTICE = "{name} is waiting for approval: {detail}"
NAME_TAKEN_ERROR = (
    "'{name}' is online in another session. Sessions with the same client.name share it: "
    "close one, give the second its own name and token (AI_CONNECT_PEER_NAME), or register "
    "with standby to take the name once it is free."
)


def log_refusal(reason: str, **fields: object) -> None:
    """One structured line per refusal: why, and who, never a token or a message body."""
    logger.warning(json.dumps({"event": "refused", "reason": reason, **fields}, sort_keys=True))


def _unread_chunks(messages: list[dict]) -> list[list[dict]]:
    """Split messages, in order, into lists whose unread frame fits UNREAD_FRAME_MAX_BYTES.

    json.dumps escapes non-ASCII, so a character is a byte; items are joined
    by ", ". A single message over the limit goes alone: it cannot be split.
    """
    chunks: list[list[dict]] = []
    current: list[dict] = []
    size = _UNREAD_ENVELOPE_BYTES
    for message in messages:
        item = len(json.dumps(message)) + (2 if current else 0)
        if current and size + item > UNREAD_FRAME_MAX_BYTES:
            chunks.append(current)
            current, size, item = [], _UNREAD_ENVELOPE_BYTES, item - 2
        current.append(message)
        size += item
    if current:
        chunks.append(current)
    return chunks


class BridgeServer:
    """Routes messages between peers and keeps them in the message store."""

    def __init__(
        self,
        host: str,
        port: int,
        history_days: int,
        roles: Roles,
        db_path: str = DEFAULT_DB_PATH,
        limits: Limits | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.host = host
        self.port = port
        self.history_days = history_days
        self.roles = roles
        self.limits = limits or Limits()
        self._clock = clock
        self.registry = PeerRegistry()
        self.store = MessageStore(db_path, max_stored_per_peer=self.limits.max_stored_per_peer)
        self.observers = Observers()
        self._server: Server | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._history_cleanup_task: asyncio.Task | None = None
        # Watchers per peer name: connections that want to hear about new
        # messages for that peer without registering as it
        self._watchers: dict[str, set[ServerConnection]] = {}
        # The Claude Code session each watcher belongs to: one watcher per
        # session, because its hooks start one at every turn end
        self._watcher_sessions: dict[ServerConnection, str] = {}
        # Standby connections per peer name: replaced sessions that wait for
        # the name to become free again
        self._standby: dict[str, set[ServerConnection]] = {}
        # Who wants to hear when a peer is done: peer name -> subscriber
        # names; each subscription fires once
        self._idle_subscribers: dict[str, set[str]] = {}

        self.registry.on_join(self._announce_joined)
        self.registry.on_leave(self._handle_left)
        self.store.on_stored(self.observers.broadcast)

    async def start(self) -> None:
        await self.store.connect()
        self._server = await websockets.serve(
            self._handle_connection,
            self.host,
            self.port,
            process_request=self._check_token,
            max_size=max(2 * self.limits.max_message_bytes, WEBSOCKET_MAX_SIZE_FLOOR),
        )
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._history_cleanup_task = asyncio.create_task(self._history_cleanup_loop())
        logger.info(f"Bridge Server listening on ws://{self.host}:{self.bound_port}")

    @property
    def bound_port(self) -> int:
        """The port listened on; differs from port when port is 0."""
        if self._server is None:
            return self.port
        return self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        for task in (self._heartbeat_task, self._history_cleanup_task):
            if task:
                task.cancel()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        await self.store.close()

    def _identity(self, request: Request) -> Identity | None:
        return self.roles.identity_for(request.headers.get("Authorization", ""))

    def _check_token(self, connection: ServerConnection, request: Request) -> Response | None:
        """Refuse the handshake unless it carries a known token.

        Checked once per connection, so every message type, the watchers
        and list_peers are covered alike; the token's role decides which
        message types the connection may send.
        """
        if self._identity(request) is not None:
            return None
        client_ip = connection.remote_address[0] if connection.remote_address else "unknown"
        log_refusal(self.roles.refusal_reason(request.headers.get("Authorization", "")), ip=client_ip)
        return connection.respond(HTTPStatus.UNAUTHORIZED, "Missing or wrong AI-Connect token\n")

    async def _handle_connection(self, websocket: ServerConnection) -> None:
        """Serve one peer connection until it closes."""
        peer_name: str | None = None
        client_ip = websocket.remote_address[0] if websocket.remote_address else "unknown"
        # The handshake passed _check_token: the request is there and its token known
        assert websocket.request is not None
        identity = self._identity(websocket.request)
        assert identity is not None
        role = identity.role
        if identity.shared:
            logger.warning(json.dumps({"event": "shared_token_used", "ip": client_ip}))
        bucket = TokenBucket(self.limits.rate_per_second, self.limits.rate_burst, self._clock)
        # Only the first refusal of a run is logged, so a flood does not flood the log
        rate_limited = False

        async def refuse(reason: str, error: str, msg_type: object = None, log: bool = True, **fields: object) -> None:
            await websocket.send(json.dumps({"type": "error", "error": error, "code": reason}))
            if log:
                log_refusal(reason, ip=client_ip, peer=peer_name, role=role, msg_type=msg_type, **fields)

        try:
            async for raw_message in websocket:
                if not bucket.allow():
                    await refuse("rate_limited", RATE_LIMITED_ERROR, log=not rate_limited)
                    rate_limited = True
                    continue
                rate_limited = False
                size = len(raw_message.encode()) if isinstance(raw_message, str) else len(raw_message)
                if size > self.limits.max_message_bytes:
                    await refuse(
                        "message_too_large",
                        f"Message of {size} bytes is over the limit of {self.limits.max_message_bytes}",
                        bytes=size,
                        limit=self.limits.max_message_bytes,
                    )
                    continue
                try:
                    message = json.loads(raw_message)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from {client_ip}")
                    continue
                if not isinstance(message, dict):
                    await self._send_error(websocket, "A message must be a JSON object")
                    continue
                msg_type = message.get("type")
                if not self.roles.allows(role, msg_type):
                    await refuse("role_not_allowed", f"'{msg_type}' is not allowed for the role {role}", msg_type)
                    continue

                if msg_type == "register":
                    name = message.get("name")
                    if not isinstance(name, str) or not name:
                        await self._send_error(websocket, "'register' needs a 'name'")
                        continue
                    reason = self.roles.register_refusal(identity, name)
                    if reason:
                        await refuse(reason, f"'{name}' may not be registered with this token", msg_type, name=name)
                        continue
                    holder = self.registry.get(name)
                    if holder is not None and holder.websocket is websocket:
                        await websocket.send(json.dumps({"type": "registered", "name": name}))
                        continue
                    if holder is not None and self.registry.is_live(holder) and message.get("standby"):
                        # Waits for the name instead of being refused
                        self._standby.setdefault(name, set()).add(websocket)
                        await websocket.send(json.dumps({"type": "standby", "name": name}))
                        logger.info(f"Peer on standby: {name} ({client_ip})")
                        continue
                    try:
                        await self.registry.register(name, client_ip, websocket, identity.credential)
                    except NameTakenError:
                        await refuse("name_taken", NAME_TAKEN_ERROR.format(name=name), msg_type, name=name)
                        continue
                    self._standby.get(name, set()).discard(websocket)
                    if peer_name and peer_name != name:
                        # One name per connection: the old one is let go
                        await self._release(peer_name, websocket)
                    peer_name = name
                    await websocket.send(json.dumps({"type": "registered", "name": name}))
                    logger.info(f"Peer registered: {name} ({client_ip})")

                    await self._deliver_unread(websocket, name)

                elif msg_type == "ping":
                    if peer_name:
                        self.registry.update_ping(peer_name)
                    await websocket.send(json.dumps({"type": "pong"}))

                elif msg_type == "watch":
                    watched = message.get("peer")
                    if not isinstance(watched, str) or not watched:
                        await self._send_error(websocket, "'watch' needs a 'peer'")
                        continue
                    # Watching a name reads its messages: only one's own.
                    # Replies to the user are read with the observer token
                    reason = self.roles.watch_refusal(identity, watched)
                    if reason:
                        await refuse(reason, f"'{watched}' may not be watched with this token", msg_type, name=watched)
                        continue
                    session = message.get("session")
                    if session and session in self._watcher_sessions.values():
                        await websocket.send(json.dumps({"type": "already_watching", "peer": watched}))
                        continue
                    self._watchers.setdefault(watched, set()).add(websocket)
                    if session:
                        self._watcher_sessions[websocket] = session
                    await websocket.send(json.dumps({"type": "watching", "peer": watched}))
                    # A message that came after the session last read, while
                    # no watcher ran, wakes the session at once
                    since = message.get("since")
                    missed = await self.store.latest_to_since(watched, since) if since else None
                    if missed:
                        await websocket.send(json.dumps({**missed, "type": "message"}))

                elif msg_type == "list_peers":
                    await websocket.send(json.dumps({"type": "peer_list", "peers": self._peer_list()}))

                elif msg_type == "observe":
                    self.observers.add(websocket)
                    await websocket.send(json.dumps({"type": "observing"}))
                    logger.info(f"Observer connected ({client_ip})")

                elif msg_type == "history_all":
                    since, limit = message.get("since"), message.get("limit")
                    if not since or not isinstance(limit, int) or not 0 < limit <= HISTORY_ALL_MAX_LIMIT:
                        await self._send_error(
                            websocket, f"'history_all' needs 'since' and a 'limit' of 1 to {HISTORY_ALL_MAX_LIMIT}"
                        )
                        continue
                    history = await self.store.history_all(since, message.get("before"), limit)
                    await websocket.send(json.dumps({"type": "history_all", "messages": history}))

                elif msg_type == "user_send":
                    sender = user_sender(message.get("as"))
                    recipients = valid_recipients(message.get("to"))
                    if sender is None or recipients is None:
                        await self._send_error(
                            websocket,
                            "'user_send' needs 'as' (letters, digits, . _ -) and 'to' (a list of peer names or \"*\")",
                        )
                        continue
                    sent = []
                    for recipient in recipients:
                        routed = await self._route_message(
                            {"to": recipient, "content": message.get("content", "")}, sender
                        )
                        if routed is None:
                            sent.append({
                                "to": recipient, "id": None, "online": False,
                                "code": "recipient_queue_full", "error": QUEUE_FULL_ERROR.format(name=recipient),
                            })
                            continue
                        stored, online = routed
                        sent.append({"to": recipient, "id": stored["id"], "online": online})
                    await websocket.send(json.dumps({"type": "user_sent", "sent": sent}))
                    logger.info(f"{sender} sent to {', '.join(recipients)} ({client_ip})")

                elif peer_name is None:
                    await self._send_error(websocket, f"'{msg_type}' needs 'register' first")

                elif msg_type == "message":
                    to_peer = message.get("to")
                    if not isinstance(to_peer, str) or not to_peer:
                        await self._send_error(websocket, "'message' needs a 'to'")
                        continue
                    if is_reserved_name(to_peer) and not is_user_recipient(to_peer):
                        await refuse("reserved_name", f"'{to_peer}' is not a peer", msg_type, name=to_peer)
                        continue
                    if await self._route_message(message, peer_name) is None:
                        # _route_message logged the refusal with its sizes
                        await refuse(
                            "recipient_queue_full", QUEUE_FULL_ERROR.format(name=to_peer), msg_type, log=False
                        )

                elif msg_type == "set_state":
                    state = message.get("state")
                    if state not in PEER_STATES:
                        await self._send_error(websocket, f"'set_state' needs a state out of {PEER_STATES}")
                        continue
                    await self._set_state(peer_name, state, message.get("detail", ""))

                elif msg_type == "set_status":
                    peer = self.registry.get(peer_name)
                    if peer:
                        peer.status = message.get("status", "")

                elif msg_type == "notify_when_idle":
                    watched = message.get("peer")
                    if not watched:
                        await self._send_error(websocket, "'notify_when_idle' needs a 'peer'")
                        continue
                    await self._subscribe_idle(peer_name, watched)

                elif msg_type == "history":
                    history = await self.store.get_history(
                        peer_name, message.get("peer", ""), message.get("limit", 50)
                    )
                    await websocket.send(json.dumps({
                        "type": "history",
                        "peer": message.get("peer", ""),
                        "messages": history
                    }))

        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            for connections in (*self._watchers.values(), *self._standby.values()):
                connections.discard(websocket)
            self._watcher_sessions.pop(websocket, None)
            self.observers.discard(websocket)
            logger.info(f"Connection closed: {peer_name or client_ip}")
            if peer_name:
                await self._release(peer_name, websocket)

    async def _release(self, name: str, websocket: ServerConnection) -> None:
        """Unregister name if this connection still holds it."""
        current = self.registry.get(name)
        if current and current.websocket is websocket:
            await self.registry.unregister(name)

    async def _send_error(self, websocket: ServerConnection, error: str) -> None:
        await websocket.send(json.dumps({"type": "error", "error": error}))

    async def _set_state(self, name: str, state: str, detail: str) -> None:
        """Record a peer's state; done or waiting fires its subscriptions."""
        peer = self.registry.get(name)
        if peer is None:
            return
        peer.state, peer.state_detail, peer.state_since = state, detail, utc_now().isoformat()
        if state == "busy":
            return
        notice = IDLE_NOTICE.format(name=name) if state == "idle" else WAITING_NOTICE.format(name=name, detail=detail)
        for subscriber in self._idle_subscribers.pop(name, set()):
            await self._route_message({"to": subscriber, "content": notice}, BRIDGE_SENDER)

    async def _subscribe_idle(self, subscriber: str, watched: str) -> None:
        """Notify subscriber once when watched is done; at once if it already is."""
        peer = self.registry.get(watched)
        if peer and peer.state == "idle":
            await self._route_message({"to": subscriber, "content": IDLE_NOTICE.format(name=watched)}, BRIDGE_SENDER)
            return
        self._idle_subscribers.setdefault(watched, set()).add(subscriber)

    async def _route_message(self, message: dict, from_peer: str) -> tuple[dict, bool] | None:
        """Deliver a message; direct messages to offline peers wait in the store.

        A broadcast ("*") reaches the peers online right now. Waiting for
        offline peers would need delivery tracking per recipient, and a
        broadcast is about the present ("is anyone using GPU 2?"). A message
        to a user counts as delivered at once: users read along as
        observers and never register, so it must not pile up as unread.

        Returns the stored message and whether a recipient was online, or
        None (logged) when the offline recipient's queue is full.
        """
        to_peer = message["to"]

        if to_peer == "*":
            recipients = [p for p in self.registry.all() if p.name != from_peer]
        else:
            target = self.registry.get(to_peer)
            recipients = [target] if target else []

        delivered = to_peer == "*" or bool(recipients) or is_user_name(to_peer)
        if not delivered and await self._queue_full(to_peer, from_peer, message):
            return None
        outgoing = await self.store.store(
            from_peer,
            to_peer,
            message.get("content", ""),
            message.get("context"),
            delivered=delivered
        )
        payload = json.dumps({**outgoing, "type": "message"})
        for peer in recipients:
            await self._send_to(peer, payload)
        await self._notify_watchers(to_peer, from_peer, payload)
        return outgoing, bool(recipients)

    async def _queue_full(self, to_peer: str, from_peer: str, message: dict) -> bool:
        """Whether one more message would push the offline recipient past its queue caps."""
        context = message.get("context")
        size = len(str(message.get("content", "")).encode()) + (len(json.dumps(context).encode()) if context else 0)
        count, queued = await self.store.unread_size(to_peer)
        if count + 1 <= self.limits.max_unread_per_peer and queued + size <= self.limits.max_unread_bytes_per_peer:
            return False
        log_refusal(
            "recipient_queue_full", peer=from_peer, recipient=to_peer, queued=count, queued_bytes=queued,
            bytes=size, max_count=self.limits.max_unread_per_peer, max_bytes=self.limits.max_unread_bytes_per_peer,
        )
        return True

    async def _deliver_unread(self, websocket: ServerConnection, name: str) -> None:
        """Send what waited for name in frames the client accepts, each marked once it is sent.

        A send that fails leaves the rest unread for the next registration.
        """
        for chunk in _unread_chunks(await self.store.get_unread(name)):
            await websocket.send(json.dumps({"type": "unread", "messages": chunk}))
            await self.store.mark_delivered([m["id"] for m in chunk])

    async def _notify_watchers(self, to_peer: str, from_peer: str, payload: str) -> None:
        """Tell the watchers of every recipient that a message arrived."""
        if to_peer == "*":
            watched = [name for name in self._watchers if name != from_peer]
        else:
            watched = [to_peer]
        for name in watched:
            for watcher in list(self._watchers.get(name, ())):
                try:
                    await watcher.send(payload)
                except websockets.exceptions.ConnectionClosed:
                    self._watchers[name].discard(watcher)

    async def _send_to(self, peer: Peer, payload: str) -> None:
        try:
            await peer.websocket.send(payload)
        except websockets.exceptions.ConnectionClosed:
            logger.warning(f"Could not deliver to {peer.name}: connection closed")

    def _peer_list(self) -> list[dict]:
        return [
            {
                "name": p.name,
                "ip": p.ip,
                "connected_at": p.connected_at,
                "state": p.state,
                "state_detail": p.state_detail,
                "state_since": p.state_since,
                "status": p.status,
            }
            for p in self.registry.all()
        ]

    async def _announce_joined(self, peer: Peer) -> None:
        payload = json.dumps({"type": "peer_joined", "peer": {"name": peer.name, "ip": peer.ip}})
        for other in self.registry.all():
            if other.name != peer.name:
                await self._send_to(other, payload)
        await self.observers.peers_changed(self._peer_list())

    async def _handle_left(self, peer: Peer) -> None:
        await self._announce_left(peer)
        await self._offer_name(peer.name)

    async def _announce_left(self, peer: Peer) -> None:
        payload = json.dumps({"type": "peer_left", "peer": peer.name})
        for other in self.registry.all():
            await self._send_to(other, payload)
        await self.observers.peers_changed(self._peer_list())

    async def _offer_name(self, name: str) -> None:
        """Tell the standby connections of a name that it is free.

        Each answers with a standby register; the first one gets the name,
        the others stay on standby.
        """
        payload = json.dumps({"type": "name_free", "name": name})
        for connection in list(self._standby.get(name, ())):
            try:
                await connection.send(payload)
            except websockets.exceptions.ConnectionClosed:
                self._standby[name].discard(connection)

    async def _heartbeat_loop(self) -> None:
        """Drop peers whose connection is dead or that stopped pinging."""
        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            for peer in self.registry.all():
                try:
                    await peer.websocket.send(json.dumps({"type": "ping"}))
                except websockets.exceptions.ConnectionClosed:
                    logger.info(f"Connection dead: {peer.name}")
                    await self.registry.unregister(peer.name)
            for name in await self.registry.cleanup_stale():
                logger.info(f"Peer timed out: {name}")

    async def _history_cleanup_loop(self) -> None:
        """Delete messages older than history_days, at start and then daily."""
        while True:
            deleted = await self.store.delete_older_than(self.history_days)
            logger.info(f"History cleanup: {deleted} messages older than {self.history_days} days deleted")
            await asyncio.sleep(HISTORY_CLEANUP_SECONDS)
