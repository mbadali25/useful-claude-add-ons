"""client/bridge_client.py: URI building, a bounded inbound queue, one request per
response type at a time, and refusals that reach the model instead of only the log."""

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "client") not in sys.path:
    sys.path.append(str(ROOT / "client"))  # last, so client/server.py shadows nothing

import bridge_client  # noqa: E402  # pylint: disable=import-error,wrong-import-position
from bridge_client import BridgeClient, MessageTooLarge  # noqa: E402  # pylint: disable=import-error,wrong-import-position


def _client() -> BridgeClient:
    return BridgeClient("127.0.0.1", 1, "Me:P", "t")


def _msg(i: int, size: int = 10) -> dict:
    return {"type": "message", "id": str(i), "from": "A:B", "content": "x" * size,
            "timestamp": "2026-10-11T00:00:00+00:00"}


# --- IPv6 -----------------------------------------------------------------


@pytest.mark.parametrize("host, uri", [("::1", "ws://[::1]:9999"), ("100.64.0.1", "ws://100.64.0.1:9999"),
                                       ("bridge.tailnet.ts.net", "ws://bridge.tailnet.ts.net:9999")])
def test_connect_brackets_an_ipv6_host(monkeypatch, host, uri):
    seen = []

    async def fake_connect(target, **_kwargs):
        seen.append(target)
        raise OSError("stop here")

    monkeypatch.setattr(bridge_client.websockets, "connect", fake_connect)
    client = BridgeClient(host, 9999, "Me:P", "t")
    assert asyncio.run(client.connect()) is False
    assert seen == [uri]


# --- bounded inbound queue -----------------------------------------------


def test_queue_stops_at_the_message_cap_with_one_notice(monkeypatch):
    monkeypatch.setattr(bridge_client, "MAX_QUEUED_MESSAGES", 3)
    client = _client()
    for i in range(10):
        asyncio.run(client._handle(_msg(i)))  # pylint: disable=protected-access
    queued = client.peek_messages()
    assert [m.get("id") for m in queued[:3]] == ["0", "1", "2"]
    notices = [m for m in queued if m.get("from") == bridge_client.NOTICE_SENDER]
    assert len(notices) == 1 and "peer_history" in notices[0]["content"]
    assert len(queued) == 4


def test_queue_stops_at_the_byte_cap(monkeypatch):
    monkeypatch.setattr(bridge_client, "MAX_QUEUED_BYTES", 3 * len(json.dumps(_msg(0, 300))) + 5)
    client = _client()
    asyncio.run(client._handle({"type": "unread", "messages": [_msg(i, 300) for i in range(5)]}))  # pylint: disable=protected-access
    queued = client.peek_messages()
    assert [m.get("id") for m in queued if "id" in m] == ["0", "1", "2"]
    assert sum(1 for m in queued if m.get("from") == bridge_client.NOTICE_SENDER) == 1


def test_queue_takes_messages_again_once_read(monkeypatch):
    monkeypatch.setattr(bridge_client, "MAX_QUEUED_MESSAGES", 2)
    client = _client()
    for i in range(4):
        asyncio.run(client._handle(_msg(i)))  # pylint: disable=protected-access
    client.drop_messages(len(client.peek_messages()))
    for i in range(4, 7):
        asyncio.run(client._handle(_msg(i)))  # pylint: disable=protected-access
    queued = client.peek_messages()
    assert [m.get("id") for m in queued if "id" in m] == ["4", "5"]
    assert sum(1 for m in queued if m.get("from") == bridge_client.NOTICE_SENDER) == 1  # a new run, a new notice


# --- one request per response type at a time -----------------------------


def test_concurrent_requests_of_one_type_get_their_own_answers():
    async def go():
        client = _client()
        sent = []

        async def fake_send(data):
            sent.append(data)
            return True

        client._send = fake_send  # pylint: disable=protected-access
        first = asyncio.create_task(client.get_history("A:B", 1))
        second = asyncio.create_task(client.get_history("C:D", 1))
        await asyncio.sleep(0.01)
        assert [d["peer"] for d in sent] == ["A:B"]  # the second waits for the first's answer
        await client._handle({"type": "history", "messages": ["for A:B"]})  # pylint: disable=protected-access
        await asyncio.sleep(0.01)
        assert [d["peer"] for d in sent] == ["A:B", "C:D"]
        await client._handle({"type": "history", "messages": ["for C:D"]})  # pylint: disable=protected-access
        return await first, await second

    assert asyncio.run(go()) == (["for A:B"], ["for C:D"])


# --- refusals reach the model --------------------------------------------


def test_send_over_the_frame_limit_is_refused_before_sending(monkeypatch):
    monkeypatch.setenv("AI_CONNECT_MAX_MESSAGE_BYTES", "1000")
    client = _client()
    client._connected = True  # pylint: disable=protected-access
    sent = []

    async def fake_send(data):
        sent.append(data)
        return True

    client._send = fake_send  # pylint: disable=protected-access
    # JSON escapes each non-ASCII character: 400 characters become far more than 1000 bytes
    with pytest.raises(MessageTooLarge) as refused:
        asyncio.run(client.send_message("A:B", "ü" * 400))
    assert refused.value.size > refused.value.limit == 1000
    assert sent == []
    assert asyncio.run(client.send_message("A:B", "small")) is True


@pytest.mark.parametrize("code", ["recipient_queue_full", "message_too_large", "rate_limited", "reserved_name"])
def test_a_refusal_from_the_bridge_is_queued_for_peer_read(code):
    client = _client()
    frame = {"type": "error", "code": code, "error": f"refused because {code}"}
    asyncio.run(client._handle(frame))  # pylint: disable=protected-access
    asyncio.run(client._handle(frame))  # pylint: disable=protected-access
    queued = client.peek_messages()
    assert len(queued) == 1  # the same refusal twice in a row is one notice
    assert queued[0]["from"] == bridge_client.NOTICE_SENDER
    assert code in queued[0]["content"] and f"refused because {code}" in queued[0]["content"]


def test_queue_bytes_are_counted_as_json():
    client = _client()
    message = _msg(1, 50)
    asyncio.run(client._handle(message))  # pylint: disable=protected-access
    assert client._queued_bytes == len(json.dumps(message))  # pylint: disable=protected-access
    client.drop_messages(1)
    assert client._queued_bytes == 0  # pylint: disable=protected-access
