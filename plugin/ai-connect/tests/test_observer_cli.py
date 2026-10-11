"""observer_client.cli send: what the user sees for each recipient the Bridge answered for."""
import asyncio

import pytest

from observer_client import cli


def _bridge_answers(monkeypatch, sent):
    class FakeUserConnection:
        @classmethod
        def from_config(cls):
            return cls()

        async def send(self, as_name, recipients, content):
            return sent

    monkeypatch.setattr(cli, "UserConnection", FakeUserConnection)


def test_send_reports_delivered_and_waiting(monkeypatch, capsys):
    _bridge_answers(monkeypatch, [{"to": "A:x", "id": 1, "online": True},
                                  {"to": "B:y", "id": 2, "online": False}])
    asyncio.run(cli._send("Ann", ["A:x", "B:y"], "hi"))
    out = capsys.readouterr().out
    assert "User:Ann -> A:x: delivered" in out
    assert "User:Ann -> B:y: waits until it is online" in out


def test_send_prints_the_bridge_error_for_a_refused_recipient_and_exits_1(monkeypatch, capsys):
    error = "B:y has too many unread messages"
    _bridge_answers(monkeypatch, [
        {"to": "A:x", "id": 1, "online": True},
        {"to": "B:y", "id": None, "online": False, "code": "recipient_queue_full", "error": error},
    ])
    with pytest.raises(SystemExit) as exc:
        asyncio.run(cli._send("Ann", ["A:x", "B:y"], "hi"))
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "User:Ann -> A:x: delivered" in out
    assert f"User:Ann -> B:y: refused: {error}" in out
    assert "waits until it is online" not in out
