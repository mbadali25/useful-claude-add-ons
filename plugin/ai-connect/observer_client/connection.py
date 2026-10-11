# pylint: disable=line-too-long  # upstream AI-Connect style, kept to minimise the fork's diff
"""Connections to the Bridge for a person: read all traffic, write to agents as a user.

Reading, with the observer token:

    async with ObserverConnection.from_config() as bridge:
        await bridge.start_observing()     # first, so nothing falls between history and live
        history = await bridge.history(since, limit=200)
        async for event in bridge.events():
            ...

Messages are dicts with id, from, to, content, context and timestamp (see
bridge_time). Live events are {"event": "message", ...message} or, when a
peer joins or leaves, {"event": "peers", "peers": [...]}; a live message can
also be in the history, compare the ids.

Writing, with the user token:

    sent = await UserConnection.from_config().send("Peuqui", ["Mini:A", "Mini:B"], "text")

The agents see the sender as User:Peuqui; their replies are read along
with the observer token.
"""

import json
from collections.abc import AsyncIterator
from datetime import datetime
from http import HTTPStatus
from pathlib import Path
from types import TracebackType
from typing import final

import websockets
from websockets import ClientConnection

from bridge_time import bridge_timestamp
from config_loader import (
    OBSERVER_TOKEN_PATH,
    USER_TOKEN_PATH,
    client_settings,
    load_config,
)


class BridgeError(Exception):
    """The Bridge refused a request."""


class TokenRefused(Exception):
    """The Bridge refused the token (unknown, or a new one replaced it)."""


def bridge_uri() -> str:
    """The Bridge's address: client.bridge_url from config.yaml."""
    return client_settings(load_config()).uri


def _read_token(path: Path, step: str) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Token not found: {path}\nRun installer.py {step} on the Bridge machine.")
    return path.read_text(encoding="utf-8").strip()


async def _connect(uri: str, token: str) -> ClientConnection:
    try:
        return await websockets.connect(uri, additional_headers={"Authorization": f"Bearer {token}"})
    except websockets.exceptions.InvalidStatus as e:
        if e.response.status_code == HTTPStatus.UNAUTHORIZED:
            raise TokenRefused("The Bridge refused the token") from e
        raise


async def _answer(connection: ClientConnection, answer_type: str, pending: list[dict]) -> dict:
    """Read until the answer of a request; live events in between go to pending."""
    async for raw in connection:
        data = json.loads(raw)
        if data["type"] == answer_type:
            return data
        if data["type"] == "error":
            raise BridgeError(data["error"])
        event = _live_event(data)
        if event:
            pending.append(event)
    raise ConnectionError("The Bridge closed the connection")


def _live_event(data: dict) -> dict | None:
    """A message or peer list the Bridge pushed to observers, as a live event."""
    if data["type"] == "observed":
        return {"event": "message", **{key: value for key, value in data.items() if key != "type"}}
    if data["type"] == "peers_changed":
        return {"event": "peers", "peers": data["peers"]}
    return None


# final: Python 3.10 has no typing.Self for __aenter__
@final
class ObserverConnection:
    """One connection with the observer token; requests and live messages share it."""

    def __init__(self, uri: str, token: str):
        self._uri = uri
        self._token = token
        self._ws: ClientConnection | None = None
        # Live events that arrived while a request waited for its answer
        self._pending: list[dict] = []

    @classmethod
    def from_config(cls) -> "ObserverConnection":
        """Bridge address from config.yaml, token from the observer token file."""
        return cls(bridge_uri(), _read_token(OBSERVER_TOKEN_PATH, "observer-token"))

    async def __aenter__(self) -> "ObserverConnection":
        self._ws = await _connect(self._uri, self._token)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._connection.close()

    @property
    def _connection(self) -> ClientConnection:
        if self._ws is None:
            raise RuntimeError("ObserverConnection not open, use it with 'async with'")
        return self._ws

    async def start_observing(self) -> None:
        """From now on the Bridge sends a copy of every message it stores."""
        await self._request({"type": "observe"}, "observing")

    async def history(self, since: datetime, limit: int, before: str | None = None) -> list[dict]:
        """The latest messages after since, at most limit, oldest first.

        before (a Bridge timestamp, exclusive) pages further back: pass the
        timestamp of the oldest message of the previous page.
        """
        answer = await self._request(
            {"type": "history_all", "since": bridge_timestamp(since), "before": before, "limit": limit},
            "history_all",
        )
        return answer["messages"]

    async def peers(self) -> list[dict]:
        """The peers online right now, with state and status line."""
        answer = await self._request({"type": "list_peers"}, "peer_list")
        return answer["peers"]

    async def events(self) -> AsyncIterator[dict]:
        """Every stored message and peer list change, as it comes; ends when the connection closes."""
        while self._pending:
            yield self._pending.pop(0)
        async for raw in self._connection:
            event = _live_event(json.loads(raw))
            if event:
                yield event

    async def _request(self, payload: dict, answer_type: str) -> dict:
        await self._connection.send(json.dumps(payload))
        return await _answer(self._connection, answer_type, self._pending)


@final
class UserConnection:
    """Sends as a user with the user token; one connection per send, sending is rare."""

    def __init__(self, uri: str, token: str):
        self._uri = uri
        self._token = token

    @classmethod
    def from_config(cls) -> "UserConnection":
        """Bridge address from config.yaml, token from the user token file."""
        return cls(bridge_uri(), _read_token(USER_TOKEN_PATH, "user-token"))

    async def send(self, as_name: str, recipients: list[str], content: str) -> list[dict]:
        """Send content to each recipient (a peer name or "*") as User:<as_name>.

        Returns {"to", "id", "online"} per recipient; a peer that is offline
        gets the message when it comes back, a broadcast reaches only the
        peers online now.
        """
        connection = await _connect(self._uri, self._token)
        try:
            await connection.send(json.dumps({"type": "user_send", "as": as_name, "to": recipients, "content": content}))
            answer = await _answer(connection, "user_sent", [])
        finally:
            await connection.close()
        return answer["sent"]
