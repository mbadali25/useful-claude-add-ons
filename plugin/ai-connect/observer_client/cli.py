# pylint: disable=line-too-long  # upstream AI-Connect style, kept to minimise the fork's diff
"""Read along with the AI-Connect Bridge in the terminal, and write to agents as a user.

    venv/bin/python -m observer_client.cli tree          # conversations of the last 24 h
    venv/bin/python -m observer_client.cli tree --full   # with the full text of every message
    venv/bin/python -m observer_client.cli live          # the last hour, then every new message
    venv/bin/python -m observer_client.cli send --as Peuqui --to Mini:A --to Mini:B "text"

Run it in the AI-Connect directory. Reading needs the observer token
(installer.py observer-token on the Bridge machine), send the user token
(installer.py user-token).
"""

import argparse
import asyncio
import shutil
import sys
import textwrap
from datetime import datetime, timedelta, timezone

from bridge_time import parse_bridge_timestamp
from server.user_send import is_user_name

from .connection import ObserverConnection, TokenRefused, UserConnection
from .tree import build_conversations, preview

DEFAULT_TREE_HOURS = 24
DEFAULT_LIVE_HOURS = 1
DEFAULT_LIMIT = 200

AMBER = "\033[38;5;214m"
NAME_COLOR = "\033[36m"
DIM = "\033[2m"
RESET = "\033[0m"
# Only into a terminal: piped into a file or grep, escape codes are noise
COLORED = sys.stdout.isatty()


def _paint(text: str, color: str) -> str:
    return f"{color}{text}{RESET}" if COLORED else text


def _local_time(timestamp: str) -> str:
    moment = parse_bridge_timestamp(timestamp).astimezone()
    today = datetime.now().astimezone().date()
    return moment.strftime("%H:%M:%S" if moment.date() == today else "%d.%m. %H:%M:%S")


def _width() -> int:
    return shutil.get_terminal_size().columns


def _print_message_line(prefix: str, message: dict, names: list[str], full: bool) -> None:
    time = f"[{_local_time(message['timestamp'])}]"
    plain_head = f"{prefix}{time} {' -> '.join(names)}:"
    head = f"{prefix}{_paint(time, DIM)} {_paint(' -> ', DIM).join(_paint(name, NAME_COLOR) for name in names)}:"
    if not full:
        print(f"{head} {preview(message['content'], max(_width() - len(plain_head) - 1, 20))}")
        return
    print(head)
    indent = " " * (len(prefix) + 2)
    for line in message["content"].splitlines():
        print(textwrap.indent(line, indent))


def _short_names(peers: tuple[str, str]) -> dict[str, str]:
    """Peer names without the host, unless that makes the two alike (Mini:X and Aragon:X).

    User:<name> stays whole: it marks a person, not a host.
    """
    short = {peer: peer if is_user_name(peer) else peer.split(":", 1)[-1] for peer in peers}
    return short if len(set(short.values())) == len(peers) else {peer: peer for peer in peers}


def _print_tree(messages: list[dict], online: set[str], full: bool) -> None:
    for conversation in build_conversations(messages):
        names = " <-> ".join(f"{peer} (online)" if peer in online else peer for peer in conversation.peers)
        count = len(conversation.messages)
        print(_paint(f"{names}  [{count} message{'s' if count != 1 else ''}, last {_local_time(conversation.last_timestamp)}]", AMBER))
        # The heading names both; each line shows only its sender
        short = _short_names(conversation.peers)
        for message in reversed(conversation.messages):
            _print_message_line("  ", message, [short[message["from"]]], full)
        print()


async def _tree(hours: float, limit: int, full: bool) -> None:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    async with ObserverConnection.from_config() as bridge:
        messages = await bridge.history(since, limit)
        online = {peer["name"] for peer in await bridge.peers()}
    if not messages:
        print(f"No messages in the last {hours:g} h.")
        return
    if len(messages) == limit:
        print(f"Only the latest {limit} messages; --limit shows more.\n")
    _print_tree(messages, online, full)


async def _live(hours: float, limit: int, full: bool) -> None:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    async with ObserverConnection.from_config() as bridge:
        await bridge.start_observing()
        history = await bridge.history(since, limit)
        for message in history:
            _print_message_line("", message, [message["from"], message["to"]], full)
        print(_paint("--- live (Ctrl+C ends) ---", AMBER))
        shown = {message["id"] for message in history}
        async for event in bridge.events():
            if event["event"] == "message" and event["id"] not in shown:
                _print_message_line("", event, [event["from"], event["to"]], full)
    sys.exit("The Bridge closed the connection.")


async def _send(as_name: str, recipients: list[str], text: str) -> None:
    try:
        sent = await UserConnection.from_config().send(as_name, recipients, text)
    except FileNotFoundError as e:
        sys.exit(str(e))
    except TokenRefused:
        sys.exit("The Bridge refused the user token.")
    for recipient in sent:
        state = "delivered" if recipient["online"] else "waits until it is online"
        print(f"User:{as_name} -> {recipient['to']}: {state}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    views = parser.add_subparsers(dest="view", required=True)
    send = views.add_parser("send", help="write to one or more peers as User:<name>")
    send.add_argument("--as", dest="as_name", required=True, help="your name; the peers see User:<name>")
    send.add_argument("--to", action="append", required=True, help="a peer name or *, repeat for several")
    send.add_argument("text")
    tree = views.add_parser("tree", help="conversations, the latest active first")
    tree.add_argument("--hours", type=float, default=DEFAULT_TREE_HOURS, help=f"how far back (default {DEFAULT_TREE_HOURS})")
    live = views.add_parser("live", help="every message in order, then the new ones as they come")
    live.add_argument("--hours", type=float, default=DEFAULT_LIVE_HOURS, help=f"how far back to start (default {DEFAULT_LIVE_HOURS})")
    for view in (tree, live):
        view.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help=f"at most this many past messages (default {DEFAULT_LIMIT})")
        view.add_argument("--full", action="store_true", help="the full text instead of the first line")
    args = parser.parse_args()

    if args.view == "send":
        run = _send(args.as_name, args.to, args.text)
    else:
        run = (_tree if args.view == "tree" else _live)(args.hours, args.limit, args.full)
    try:
        asyncio.run(run)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
