"""The `localgpu` command. Mainly: `localgpu shell`.

`localgpu shell` launches a **separate** Claude Code session pointed at the
local 7B, by starting :mod:`anthropic_proxy` on a loopback port and setting
`ANTHROPIC_BASE_URL` for the child process only. Your current session is
untouched, and so is crew's config - which is the whole point. See
`/localgpu:crew` for why a config edit is the wrong way to do this.

The catch, stated on every launch because nothing enforces it: *everything* in
that session is the 7B, including any `/crew:*` command run inside it. Use it
for exploring and drafting, not for gates.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent

# config.py lives in the sibling `mcp/` directory, which is deliberately not a
# package - the name would shadow the MCP SDK. Same flat sys.path entry the
# MCP server uses.
_MCP_DIR = PLUGIN_ROOT / "mcp"
if not (_MCP_DIR / "config.py").is_file():
    # Almost always a non-editable install: the modules were copied into
    # site-packages and left mcp/ behind. Say which fix applies rather than
    # letting the next line raise a bare ImportError.
    raise SystemExit(
        f"localgpu: cannot find {_MCP_DIR}.\n"
        "This happens when localgpu was installed non-editable. Reinstall with:\n"
        "  pip install -e <plugin>/localgpu\n"
        "or re-run the bootstrap, which does it correctly."
    )
sys.path.insert(0, str(_MCP_DIR))

import anthropic_proxy  # noqa: E402
import config as localgpu_config  # noqa: E402
import ollama as ollama_client  # noqa: E402

from _version import VERSION as __version__  # noqa: E402

BANNER = """\
localgpu shell - a separate Claude Code session on a local model

  model     {model}
  proxy     {base_url}
  ollama    {ollama_url}

Everything in this session runs on the local {model}, including any /crew:*
command. It is for exploring and drafting. Do not run gate commands here -
a 7B review is labelled exactly like a real one, and nothing enforces this.

Type /exit to come back.
"""


def _preflight(cfg: dict) -> None:
    """Fail before launching Claude Code, not three prompts into it."""
    client = ollama_client.OllamaClient(cfg["ollama_url"])
    try:
        client.require_models([cfg["chat_model"]])
    except ollama_client.OllamaError as exc:
        raise SystemExit(f"localgpu: {exc}")


def _find_claude() -> str:
    found = shutil.which("claude")
    if not found:
        raise SystemExit(
            "localgpu: `claude` is not on PATH, so there is no session to launch.\n"
            "Install Claude Code, or run `localgpu proxy` and point a client at it yourself."
        )
    return found


def _child_env(base_url: str) -> dict[str, str]:
    env = dict(os.environ)
    env["ANTHROPIC_BASE_URL"] = base_url
    # The proxy ignores credentials, but the client insists on having one.
    env["ANTHROPIC_API_KEY"] = "localgpu-local"
    # An OAuth profile or auth token would otherwise outrank the API key and
    # send the session back to the real API - silently, which is the worst way
    # to discover you were not on the local model at all.
    for shadowing in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"):
        env.pop(shadowing, None)
    env["LOCALGPU_SHELL"] = "1"
    return env


def cmd_shell(args: argparse.Namespace) -> int:
    cfg = localgpu_config.load_config()
    if args.model:
        cfg["chat_model"] = args.model
    _preflight(cfg)
    claude = _find_claude()

    server = anthropic_proxy.make_server(
        "127.0.0.1",
        args.port,
        cfg["ollama_url"],
        cfg["chat_model"],
        keep_alive=args.keep_alive,
        verbose=args.verbose,
    )
    host, port = server.server_address[0], server.server_address[1]
    base_url = f"http://{host}:{port}"

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    print(
        BANNER.format(
            model=cfg["chat_model"],
            base_url=base_url,
            ollama_url=cfg["ollama_url"],
        )
    )
    try:
        completed = subprocess.run(
            [claude, *args.claude_args],
            env=_child_env(base_url),
        )
        return completed.returncode
    except KeyboardInterrupt:
        return 130
    finally:
        server.shutdown()
        server.server_close()


def cmd_proxy(args: argparse.Namespace) -> int:
    """Run the proxy in the foreground. For debugging it, or for pointing
    something other than Claude Code at the local model."""
    cfg = localgpu_config.load_config()
    if args.model:
        cfg["chat_model"] = args.model
    _preflight(cfg)

    server = anthropic_proxy.make_server(
        args.host,
        args.port,
        cfg["ollama_url"],
        cfg["chat_model"],
        keep_alive=args.keep_alive,
        verbose=True,
    )
    host, port = server.server_address[0], server.server_address[1]
    print(f"localgpu proxy on http://{host}:{port} -> {cfg['ollama_url']} ({cfg['chat_model']})")
    print(f"Point a client at it with:  ANTHROPIC_BASE_URL=http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        # Unlike cmd_shell, serve_forever() runs on *this* thread, not a
        # background one - by the time we reach here it has already
        # returned. server.shutdown() is documented to deadlock unless
        # serve_forever() is still running on a different thread
        # (https://docs.python.org/3/library/socketserver.html#socketserver.BaseServer.shutdown),
        # so it has nothing to signal here and must not be called - only the
        # socket needs closing.
        server.server_close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="localgpu",
        description="Local models on your own GPU, for Claude Code.",
    )
    parser.add_argument("--version", action="version", version=f"localgpu {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    shell = sub.add_parser(
        "shell",
        help="launch a separate Claude Code session on the local chat model",
    )
    shell.add_argument("--model", help="override the configured chat_model")
    shell.add_argument("--port", type=int, default=0, help="proxy port (default: free port)")
    shell.add_argument(
        "--keep-alive",
        default=anthropic_proxy.DEFAULT_KEEP_ALIVE,
        help="how long Ollama holds the model between turns",
    )
    shell.add_argument("--verbose", action="store_true", help="log each proxied request")
    # No positional here on purpose - see parse_args() below. A REMAINDER
    # positional keeps a leading `--` verbatim (so it gets forwarded to
    # `claude` instead of being consumed) and greedily swallows the *first*
    # unrecognized flag as a parse error instead of passthrough, which broke
    # both `localgpu shell -p hi` and `localgpu shell -- -p hi`.
    shell.set_defaults(claude_args=[], func=cmd_shell)

    proxy = sub.add_parser("proxy", help="run the translating proxy in the foreground")
    proxy.add_argument("--model", help="override the configured chat_model")
    proxy.add_argument("--host", default="127.0.0.1")
    proxy.add_argument("--port", type=int, default=8817)
    proxy.add_argument("--keep-alive", default=anthropic_proxy.DEFAULT_KEEP_ALIVE)
    proxy.set_defaults(func=cmd_proxy)

    return parser


def _split_claude_args(extra: list[str]) -> list[str]:
    """Turn argparse's leftovers into what actually gets forwarded to `claude`.

    A leading `--` is the conventional "everything after this is not mine"
    separator - it is consumed here, not forwarded, so `claude` never sees it.
    Anything after that (or everything, if there was no `--` at all) goes
    through untouched, including flags that look like they belong to
    `localgpu` itself - once a token has fallen through to `extra` it was not
    matched to one of `localgpu`'s own options, so there is nothing left to
    strip.
    """
    if extra and extra[0] == "--":
        return extra[1:]
    return extra


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """`parse_args`, but `shell`'s unrecognized arguments are a passthrough to
    `claude` instead of a parse error - every other subcommand still rejects
    them the way `argparse.ArgumentParser.parse_args` normally would."""
    parser = build_parser()
    args, extra = parser.parse_known_args(argv)
    if args.command == "shell":
        args.claude_args = _split_claude_args(extra)
    elif extra:
        parser.error(f"unrecognized arguments: {' '.join(extra)}")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
