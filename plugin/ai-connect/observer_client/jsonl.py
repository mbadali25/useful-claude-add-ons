"""JSON lines for other programs (Agent-Orc), which start this with the AI-Connect venv.

    venv/bin/python -m observer_client.jsonl observe --hours 24 --limit 200
        One line per event on stdout until the process is ended:
        {"event": "peers", "peers": [...]}         at start and whenever a peer joins or leaves
        {"event": "message", "id": ..., "from": ..., "to": ..., "content": ..., "context": ..., "timestamp": ...}
        {"event": "history_end"}                   after the past messages, live ones follow
        {"event": "error", "kind": "token_refused" | "token_missing" | "unreachable" | "closed", ...}
            last line, exit code 1

    venv/bin/python -m observer_client.jsonl send < request.json
        stdin: {"as": "Peuqui", "to": ["Mini:A"], "content": "..."}
        (the user token comes from its file, see installer.py user-token)
        stdout: {"sent": [{"to", "id", "online"}, ...]}, exit code 0, or
        {"error": "token_missing" | "token_refused" | "bridge" | "unreachable", "message": ...}, exit code 1
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone

import websockets

from .connection import BridgeError, ObserverConnection, TokenRefused, UserConnection


def _emit(line: dict) -> None:
    print(json.dumps(line, ensure_ascii=False), flush=True)


async def _observe(hours: float, limit: int) -> int:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    try:
        async with ObserverConnection.from_config() as bridge:
            # First, so nothing falls between history and live
            await bridge.start_observing()
            _emit({"event": "peers", "peers": await bridge.peers()})
            history = await bridge.history(since, limit)
            for message in history:
                _emit({"event": "message", **message})
            _emit({"event": "history_end"})
            shown = {message["id"] for message in history}
            async for event in bridge.events():
                if event["event"] == "message" and event["id"] in shown:
                    continue
                _emit(event)
    except FileNotFoundError as e:
        _emit({"event": "error", "kind": "token_missing", "message": str(e)})
        return 1
    except TokenRefused:
        _emit({"event": "error", "kind": "token_refused"})
        return 1
    except websockets.exceptions.ConnectionClosed:
        pass
    except OSError as e:
        _emit({"event": "error", "kind": "unreachable", "message": str(e)})
        return 1
    _emit({"event": "error", "kind": "closed"})
    return 1


async def _send() -> int:
    request = json.loads(sys.stdin.read())
    try:
        sent = await UserConnection.from_config().send(request["as"], request["to"], request["content"])
    except FileNotFoundError as e:
        _emit({"error": "token_missing", "message": str(e)})
        return 1
    except TokenRefused:
        _emit({"error": "token_refused"})
        return 1
    except BridgeError as e:
        _emit({"error": "bridge", "message": str(e)})
        return 1
    except OSError as e:
        _emit({"error": "unreachable", "message": str(e)})
        return 1
    _emit({"sent": sent})
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    observe = commands.add_parser("observe", help="peers, past messages, then every new event")
    observe.add_argument("--hours", type=float, required=True, help="how far back the past messages go")
    observe.add_argument("--limit", type=int, required=True, help="at most this many past messages")
    commands.add_parser("send", help="send as a user, request as JSON on stdin")
    args = parser.parse_args()
    sys.exit(asyncio.run(_observe(args.hours, args.limit) if args.command == "observe" else _send()))


if __name__ == "__main__":
    main()
