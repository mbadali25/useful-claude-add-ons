"""deploy.py's hands inside the venv: config.yaml through installer.py's own functions.

Run with the venv's Python (installer.py needs PyYAML, verify needs websockets).
Prints one JSON object on its last stdout line and never a secret: the peer
token comes in through AI_CONNECT_PEER_TOKEN, a new peer's token goes straight
to an owner-only file.

  config_tool.py inspect
  config_tool.py bridge --host IP --port N --name NAME
  config_tool.py add-peer NAME --out FILE
  config_tool.py client --name NAME --bridge HOST --port N     (token in AI_CONNECT_PEER_TOKEN)
  config_tool.py verify
"""
import argparse
import asyncio
import contextlib
import hashlib
import io
import json
import os
import sys
from http import HTTPStatus
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import installer  # noqa: E402  pylint: disable=wrong-import-position,import-error
from config_loader import CONFIG_PATH  # noqa: E402  pylint: disable=wrong-import-position,import-error


def emit(payload: dict) -> None:
    print(json.dumps(payload))


def load() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def quietly(fn, *args, **kwargs):
    """Call an installer.py function with its stdout swallowed: some of them print a token."""
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def answers(mapping: dict):
    """Stand-in for installer._ask: answer by question, and refuse one deploy does not know."""
    def ask(question: str, default: str | None = None) -> str:  # pylint: disable=unused-argument
        for needle, value in mapping.items():
            if needle in question:
                return value
        raise SystemExit(f"installer.py asked an unexpected question: {question!r}")
    return ask


def cmd_inspect(_args) -> dict:
    if not CONFIG_PATH.exists():
        return {"exists": False}
    config = load()
    server, client = config.get("server") or {}, config.get("client") or {}
    token = client.get("token") or ""
    return {"exists": True, "host": server.get("host"), "port": server.get("port"),
            "name": client.get("name"), "bridge_url": client.get("bridge_url"),
            "peers": sorted((config.get("auth") or {}).get("peers") or {}),
            "token_sha256": hashlib.sha256(token.encode()).hexdigest() if token else None}


def cmd_bridge(args) -> dict:
    url = installer._bridge_url(args.host, args.port)  # pylint: disable=protected-access
    if not CONFIG_PATH.exists():
        # installer.write_config itself: tokens, own peer, deny rules. Only the prompts are answered here.
        ask = answers({"Peer name": args.name, "listen address": args.host})
        installer._ask = ask  # pylint: disable=protected-access
        quietly(installer.write_config, server=True)
        action = "written"
    else:
        action = "updated"
    installer.check_config()
    config = load()
    config["server"]["host"], config["server"]["port"] = args.host, args.port
    config["client"]["bridge_url"] = url
    installer._save_config(config)  # pylint: disable=protected-access
    return {"action": action}


def cmd_add_peer(args) -> dict:
    token = installer._add_peer(args.name, CONFIG_PATH)  # pylint: disable=protected-access
    installer._write_private(Path(args.out), token + "\n")  # pylint: disable=protected-access
    return {"action": "added", "masked": "****" + token[-4:]}


def cmd_client(args) -> dict:
    token = os.environ.get("AI_CONNECT_PEER_TOKEN", "").strip()
    if not token:
        raise SystemExit("AI_CONNECT_PEER_TOKEN is not set")
    installer._reject_placeholder(token, "Peer token")  # pylint: disable=protected-access
    if not CONFIG_PATH.exists():
        ask = answers({"Peer name": args.name, "IP or hostname": args.bridge, "peer token": token})
        installer._ask = ask  # pylint: disable=protected-access
        quietly(installer.write_config, server=False)
    installer.check_config()
    config = load()
    url = installer._bridge_url(args.bridge, args.port)  # pylint: disable=protected-access
    config["client"].update(name=args.name, token=token, bridge_url=url)
    installer._save_config(config)  # pylint: disable=protected-access
    return {"action": "written"}


async def _handshake(url: str, token: str) -> dict:
    import websockets  # pylint: disable=import-outside-toplevel
    try:
        async with websockets.connect(url, additional_headers={"Authorization": f"Bearer {token}"},
                                      open_timeout=5):
            return {"result": "ok", "url": url}
    except websockets.exceptions.InvalidStatus as err:
        if err.response.status_code == HTTPStatus.UNAUTHORIZED:
            return {"result": "refused", "url": url, "detail": f"{url} refused this machine's token (client.token)"}
        return {"result": "unreachable", "url": url, "detail": f"{url} answered HTTP {err.response.status_code}"}
    except (OSError, asyncio.TimeoutError, websockets.exceptions.InvalidHandshake) as err:
        return {"result": "unreachable", "url": url, "detail": f"cannot reach {url}: {type(err).__name__}"}


def cmd_verify(_args) -> dict:
    """Open a WebSocket to client.bridge_url with client.token and close it: no register, no message."""
    if not CONFIG_PATH.exists():
        return {"result": "unknown", "detail": f"{CONFIG_PATH} missing"}
    client = load().get("client") or {}
    return asyncio.run(_handshake(client.get("bridge_url", ""), client.get("token") or ""))


def main() -> int:
    p = argparse.ArgumentParser(prog="config_tool")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("inspect").set_defaults(func=cmd_inspect)
    b = sub.add_parser("bridge")
    b.add_argument("--host", required=True)
    b.add_argument("--port", type=int, required=True)
    b.add_argument("--name", required=True)
    b.set_defaults(func=cmd_bridge)
    a = sub.add_parser("add-peer")
    a.add_argument("name")
    a.add_argument("--out", required=True)
    a.set_defaults(func=cmd_add_peer)
    c = sub.add_parser("client")
    c.add_argument("--name", required=True)
    c.add_argument("--bridge", required=True)
    c.add_argument("--port", type=int, required=True)
    c.set_defaults(func=cmd_client)
    sub.add_parser("verify").set_defaults(func=cmd_verify)
    args = p.parse_args()
    try:
        emit(args.func(args))
    except SystemExit as err:
        if err.code in (None, 0):
            raise
        # installer.py stops with sys.exit("message"); carry the message, never a token
        emit({"error": str(err.code)})
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
