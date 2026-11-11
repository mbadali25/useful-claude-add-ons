"""The state hooks must never block, slow or visibly break a session.

The hooks are `mcp_tool` hooks (state_hooks.py): Claude Code calls the session's own `peer_set_state` tool.
An mcp_tool hook that fails is a non-blocking error, but an error in the user's transcript on every prompt, so
the tool must answer with text for every failure: Bridge down, connection lost mid-send, a client that raises,
a huge detail. There is no helper script and no shell, so no argv and no per-OS flavour to get wrong.
"""

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "client") not in sys.path:
    sys.path.append(str(ROOT / "client"))

import state_hooks  # noqa: E402  # pylint: disable=import-error
import tools  # noqa: E402  # pylint: disable=import-error

STATES = ("busy", "idle", "waiting")


class StateClient:
    """A client stand-in whose set_state does what the test says."""

    def __init__(self, connected=True, result=True, error=None):
        self.connected, self.result, self.error, self.seen = connected, result, error, []

    async def set_state(self, state, detail):
        self.seen.append((state, detail))
        if self.error:
            raise self.error
        return self.result


def call(monkeypatch, client, state="busy", detail=""):
    monkeypatch.setattr(tools, "get_client", lambda: client)
    return asyncio.run(tools.peer_set_state(state, detail))


@pytest.mark.parametrize("client", [
    None,                                    # no client at all: the Bridge never answered
    StateClient(connected=False),            # Bridge down
    StateClient(result=False),               # connection lost while sending
    StateClient(error=ConnectionResetError("reset")),
    StateClient(error=OSError("network unreachable")),
    StateClient(error=RuntimeError("anything")),
    StateClient(error=TimeoutError()),
], ids=["no-client", "bridge-down", "send-failed", "reset", "oserror", "runtimeerror", "timeout"])
@pytest.mark.parametrize("state", STATES)
def test_every_failure_is_an_answer_never_an_exception(monkeypatch, client, state):
    answer = call(monkeypatch, client, state)
    assert isinstance(answer, str) and answer


def test_a_working_client_is_told_the_state(monkeypatch):
    client = StateClient()
    assert call(monkeypatch, client, "idle") == "State: idle"
    assert client.seen == [("idle", "")]


def test_a_huge_detail_is_cut_before_it_is_sent(monkeypatch):
    client = StateClient()
    call(monkeypatch, client, "waiting", "x" * 1_000_000)
    assert len(client.seen[0][1]) == tools.FIELD_MAX


def test_the_hooks_send_a_state_and_nothing_else():
    """No prompt text, no token, no argv: a literal state per event, a short timeout, no substitution."""
    for event, group in state_hooks.STATE_HOOKS.items():
        for hook in group["hooks"]:
            assert hook["type"] == "mcp_tool" and hook["input"]["state"] in STATES, event
            assert 0 < hook["timeout"] <= 10, event
            text = json.dumps(hook)
            assert "${" not in text and "token" not in text.lower() and "command" not in hook


def test_the_plugin_itself_ships_no_state_hook():
    """In hooks.json an mcp_tool hook would error on every event where the server is not registered."""
    text = (ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8")
    assert "mcp_tool" not in text and "peer_set_state" not in text
