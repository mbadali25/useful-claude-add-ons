"""The `localgpu` command: `shell`, `proxy`, `prompt`, `models`.

`localgpu prompt` is the small one - a single question straight to Ollama's
`/api/generate`, answer on stdout, nothing retrieved first. It is the developer
and research path: try a model, draft something, get a throwaway second reading,
pipe an answer into a script. Because nothing was retrieved, nothing can be
checked against sources, so it is the wrong tool for a claim about this
repository that will be acted on - `/localgpu:ask` retrieves excerpts and
reports them beside the answer, and that is what makes it checkable.
`localgpu models` says what is actually on disk to point `--model` at.

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
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import time
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
        # `from exc` keeps the OllamaError in the chain. The message alone is
        # what a user sees, but when this fires inside a traceback - a wrapper
        # script, a test, a CI run - the cause is the difference between
        # "localgpu: model not found" and knowing which HTTP call produced it.
        raise SystemExit(f"localgpu: {exc}") from exc


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
            # Explicitly false: this is a shell wrapper, so the child's exit
            # code IS our exit code and is returned below. check=True would
            # raise CalledProcessError on any non-zero, turning "the user
            # quit Claude Code with an error" into a traceback from localgpu.
            check=False,
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


def _read_prompt(text: str | None) -> str:
    """The prompt, from the argument or from stdin.

    `-` means stdin explicitly; a missing positional means stdin only when
    something is actually piped in. A bare `localgpu prompt` on a terminal is a
    mistake, not a request to sit and read - saying so beats hanging with no
    output while the user wonders whether the model is loading.
    """
    if text is not None and text != "-":
        # An empty argument is the same nothing an empty pipe is, and it must
        # be refused the same way. `localgpu prompt ""` used to reach
        # /api/generate and bill a model load to answer nothing, while
        # `printf " " | localgpu prompt -` was rejected two lines below - the
        # same input treated as a mistake through one door and a request
        # through the other.
        if not text.strip():
            raise SystemExit("localgpu: the prompt was empty.")
        return text
    if text is None and sys.stdin.isatty():
        raise SystemExit(
            "localgpu: no prompt. Pass one as an argument, pipe it in, or use `-` "
            "to read stdin:\n"
            '  localgpu prompt "explain this error"\n'
            "  localgpu prompt - < question.txt"
        )
    body = sys.stdin.read()
    if not body.strip():
        raise SystemExit("localgpu: the prompt on stdin was empty.")
    return body


def cmd_prompt(args: argparse.Namespace) -> int:
    """One question to a local model, with no retrieval in front of it.

    This is the raw path, and the difference from `/localgpu:ask` is the whole
    reason it exists: `ask` retrieves repository excerpts first and reports them
    beside the answer, so a claim can be checked against what the model was
    given. Here there is nothing to check against. That makes it the right tool
    for exploring, drafting and throwaway research, and the wrong one for any
    answer about this codebase that will be acted on.
    """
    cfg = localgpu_config.load_config()
    model = args.model or cfg["chat_model"]
    prompt = _read_prompt(args.prompt)

    client = ollama_client.OllamaClient(cfg["ollama_url"], keep_alive=args.keep_alive)
    try:
        client.require_models([model])
    except ollama_client.OllamaError as exc:
        raise SystemExit(f"localgpu: {exc}") from exc

    options: dict[str, object] = {}
    if args.temperature is not None:
        options["temperature"] = args.temperature
    if args.num_predict is not None:
        options["num_predict"] = args.num_predict

    started = time.monotonic()
    try:
        answer = client.generate(
            prompt,
            model,
            system=args.system,
            options=options or None,
            timeout=args.timeout,
        )
    except ollama_client.OllamaError as exc:
        raise SystemExit(f"localgpu: {exc}") from exc
    elapsed = time.monotonic() - started

    if args.json:
        print(json.dumps({
            "model": model,
            "ollama_url": cfg["ollama_url"],
            "prompt": prompt,
            "response": answer,
            "elapsed_s": round(elapsed, 2),
            "grounded": False,
        }, indent=2))
    else:
        print(answer.rstrip())
        # On stderr so a pipeline gets the answer alone, and a person still gets
        # told which model produced it. An unlabelled local answer read later as
        # a frontier one is the failure this line exists to prevent.
        print(f"\n-- {model} (local, ungrounded, {elapsed:.1f}s)", file=sys.stderr)
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    """What this Ollama actually has, so `--model` is a choice and not a guess."""
    cfg = localgpu_config.load_config()
    client = ollama_client.OllamaClient(cfg["ollama_url"])
    try:
        names = client.list_models()
    except ollama_client.OllamaError as exc:
        raise SystemExit(f"localgpu: {exc}") from exc
    if args.json:
        print(json.dumps({"ollama_url": cfg["ollama_url"],
                          "chat_model": cfg["chat_model"],
                          "embed_model": cfg["embed_model"],
                          "models": names}, indent=2))
        return 0
    if not names:
        print(f"No models on {cfg['ollama_url']}. Pull one with:  ollama pull <name>")
        return 0
    configured = {cfg["chat_model"], cfg["embed_model"]}
    bare = {n.split(":", 1)[0] for n in names}
    for name in names:
        marks = []
        if name == cfg["chat_model"] or name.split(":", 1)[0] == cfg["chat_model"]:
            marks.append("chat_model")
        if name == cfg["embed_model"] or name.split(":", 1)[0] == cfg["embed_model"]:
            marks.append("embed_model")
        print(f"  {name}" + (f"   <- {', '.join(marks)}" if marks else ""))
    # A configured model that is not on disk is the error every other command
    # hits at the worst moment; report it here where it costs nothing.
    for want in sorted(configured):
        if want not in names and want not in bare:
            print(f"\nConfigured but not pulled: {want}\n  ollama pull {want}",
                  file=sys.stderr)
    return 0
SERVER_NAME = "localgpu"


def _entry(home) -> dict:
    """The `.mcp.json` entry for this machine, with every path already literal.

    Nothing here is a placeholder. `.mcp.json` is read by Claude Code, not by a
    shell, so a `~` or a `${VAR}` left in it is a string that resolves to
    nothing and produces a server that fails to spawn with no useful error.
    That is precisely the failure this subcommand exists to remove: the paths
    are resolved by the process that already knows them, rather than
    substituted by hand into a template.

    `LOCALGPU_HOME` goes in `env` deliberately - an MCP server is spawned by
    Claude Code, not by a login shell, so it inherits no profile that exports
    it.
    """
    return {
        "type": "stdio",
        "command": str(localgpu_config.venv_python(home)).replace("\\", "/"),
        "args": [str(PLUGIN_ROOT / "mcp" / "server.py").replace("\\", "/")],
        "env": {"LOCALGPU_HOME": str(home).replace("\\", "/")},
    }


def cmd_mcp_init(args: argparse.Namespace) -> int:
    """Write (or update) `<repo>/.mcp.json` so this repo can reach the server.

    Idempotent by contract: an entry that already matches is reported as
    already registered and nothing is written. An entry that differs is
    reported as a diff and left alone unless `--force`, because the difference
    is usually a version-pinned plugin path from an older localgpu and
    silently rewriting it hides that an upgrade happened.
    """
    home = localgpu_config.localgpu_home()
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print(f"localgpu: not a directory: {repo}", file=sys.stderr)
        return 1

    entry = _entry(home)

    # Verify before writing. A correct-looking path to a file that is not
    # there produces a dead server and no error anyone can read, so the check
    # belongs here rather than in whatever discovers it later.
    missing = [p for p in (entry["command"], entry["args"][0]) if not Path(p).is_file()]
    if missing:
        print("localgpu: refusing to write a registration that cannot spawn.",
              file=sys.stderr)
        for p in missing:
            print(f"  missing: {p}", file=sys.stderr)
        print("Run the bootstrap first:\n"
              f"  {'pwsh -File' if os.name == 'nt' else 'bash'} "
              f"{PLUGIN_ROOT / ('bootstrap.ps1' if os.name == 'nt' else 'bootstrap.sh')}",
              file=sys.stderr)
        return 1

    target = repo / ".mcp.json"
    doc = {}
    if target.is_file():
        try:
            doc = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"localgpu: {target} is not valid JSON ({exc}). "
                  "Fix or remove it; refusing to overwrite.", file=sys.stderr)
            return 1
        if not isinstance(doc, dict):
            print(f"localgpu: {target} is not a JSON object. Refusing to "
                  "overwrite.", file=sys.stderr)
            return 1

    servers = doc.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        print(f"localgpu: {target} has a non-object `mcpServers`. Refusing to "
              "overwrite.", file=sys.stderr)
        return 1

    existing = servers.get(SERVER_NAME)
    if existing == entry:
        print(f"already registered: {target}")
        print("  (unchanged - nothing written)")
        return 0
    if existing is not None and not args.force:
        print(f"localgpu: {SERVER_NAME} is already in {target}, but differs:",
              file=sys.stderr)
        print(f"  on disk: {json.dumps(existing, sort_keys=True)}", file=sys.stderr)
        print(f"  correct: {json.dumps(entry, sort_keys=True)}", file=sys.stderr)
        print("This is usually a plugin path pinned to an older localgpu "
              "version. Re-run with --force to update it.", file=sys.stderr)
        return 1

    servers[SERVER_NAME] = entry
    # Serialise BEFORE opening. `open(..., "w")` truncates at open time, so a
    # write whose argument raises leaves a zero-byte file behind - and `doc`
    # here is the user's whole `.mcp.json`, every other server in it included.
    # Nothing that reaches this line can make `json.dumps` raise TODAY (`doc`
    # came out of `json.loads`, `entry` is str-only), so this is not a fix for
    # a live bug. It is the ordering that MAKES that a fact about today rather
    # than something the next editor has to re-derive: with the call inside the
    # `with`, adding one non-JSON value anywhere upstream turns "localgpu could
    # not register itself" into "every MCP server in this repo is gone", and
    # that failure looks like nothing happened. `_test/test_cli.py` pins the
    # order by making the serialisation raise and checking the file survives.
    #
    # newline="\n" is not cosmetic either: Python text mode rewrites every
    # \n to \r\n on Windows, and the damage lands in the working tree after any
    # checkout that might have fixed it.
    body = json.dumps(doc, indent=2) + "\n"
    with io.open(target, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)
    print(f"{'updated' if existing else 'wrote'}: {target}")

    if args.gitignore:
        _ignore(repo)

    print()
    print("Run /mcp in Claude Code and approve `localgpu`. A project-scope "
          ".mcp.json needs explicit approval and will not connect on its own.")
    return 0


_IGNORE_NOTE = """
# Project-scope MCP registration, written by `localgpu mcp-init`. It holds
# LITERAL absolute paths - the venv interpreter, the plugin directory, and
# LOCALGPU_HOME - because Claude Code reads this file directly and expands
# neither `~` nor a variable. All three are machine-specific, so a committed
# copy spawns a server pointing at paths that exist on exactly one box.
# Everyone else runs `localgpu mcp-init` and gets their own.
.mcp.json
"""


def _ignore(repo: Path) -> None:
    """Add `.mcp.json` to the repo's `.gitignore`, once."""
    gi = repo / ".gitignore"
    text = gi.read_text(encoding="utf-8") if gi.is_file() else ""
    if any(line.strip() == ".mcp.json" for line in text.splitlines()):
        print("  .gitignore: already ignores .mcp.json")
        return
    with io.open(gi, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(("" if text.endswith("\n") or not text else "\n") + _IGNORE_NOTE)
    print("  .gitignore: added .mcp.json")


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

    prompt = sub.add_parser(
        "prompt",
        help="ask a local model one question directly, with no retrieval",
        description="One question to Ollama's /api/generate and the answer on stdout. "
                    "Nothing is retrieved first, so the answer cannot be checked against "
                    "sources - use /localgpu:ask when it needs to be.",
    )
    prompt.add_argument("prompt", nargs="?",
                        help="the prompt; `-` or omitted-with-a-pipe reads stdin")
    prompt.add_argument("--model", help="override the configured chat_model")
    prompt.add_argument("--system", help="system prompt")
    prompt.add_argument("--temperature", type=float, default=None)
    prompt.add_argument("--num-predict", type=int, default=None,
                        help="cap the answer length in tokens")
    prompt.add_argument("--timeout", type=float,
                        default=ollama_client.DEFAULT_GENERATE_TIMEOUT,
                        help="seconds to wait for the answer (default: %(default)g)")
    # 30s, not the shell's 5m lease. A one-shot that pins 4.7 GB for five
    # minutes costs the next index run a reload for a single answer.
    prompt.add_argument("--keep-alive", default=ollama_client.DEFAULT_KEEP_ALIVE,
                        help="how long Ollama holds the model afterwards "
                             "(default: %(default)s)")
    prompt.add_argument("--json", action="store_true",
                        help="emit the answer with its model and timing as JSON")
    prompt.set_defaults(func=cmd_prompt)

    models = sub.add_parser("models", help="list the models this Ollama has pulled")
    models.add_argument("--json", action="store_true")
    models.set_defaults(func=cmd_models)
    mcp_init = sub.add_parser(
        "mcp-init",
        help="write <repo>/.mcp.json so Claude Code can reach the server",
    )
    mcp_init.add_argument(
        "repo", nargs="?", default=".",
        help="repository to register in (default: current directory)")
    mcp_init.add_argument(
        "--force", action="store_true",
        help="overwrite an existing localgpu entry that differs")
    mcp_init.add_argument(
        "--gitignore", action=argparse.BooleanOptionalAction, default=True,
        help="also add .mcp.json to the repo's .gitignore (default: yes)")
    mcp_init.set_defaults(func=cmd_mcp_init)

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
