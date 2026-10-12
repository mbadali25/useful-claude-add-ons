"""The platform-independent steps of the AI-Connect installation.

install.sh (Linux) and install.ps1 (Windows) create the venv, install the
dependencies and set up the services. Everything else happens here, run
with the venv's Python, so it is written once for both:

    installer.py config --server    # Bridge machine: write the config, generate its tokens
    installer.py config --client    # every other machine: write the config, ask for its token
    installer.py observer-token     # Bridge machine: (re)generate the observer token
    installer.py user-token         # Bridge machine: (re)generate the user token
    installer.py add-peer <name>    # Bridge machine: add a peer, print its new token once
    installer.py revoke-peer <name> # Bridge machine: remove a peer's token
    installer.py claude             # register the MCP server with Claude Code
    installer.py unregister         # remove it from Claude Code again

The plugin itself (the hooks) comes from the useful-claude-add-ons marketplace:
claude plugin install ai-connect@useful-claude-add-ons
"""

import argparse
import hashlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

from config_loader import CONFIG_PATH, OBSERVER_TOKEN_PATH, USER_TOKEN_PATH

REPO = Path(__file__).resolve().parent
CONFIG_EXAMPLE = REPO / "config.yaml.example"
MCP_SERVER = "ai-connect"
PLUGIN = "ai-connect@useful-claude-add-ons"
# What `claude mcp remove` says when there is nothing to remove
NOT_REGISTERED = "No MCP server named"
CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"
# Reading all traffic and writing as a user are the user's tools: agents run
# as the same user and could read the token files or run the observer
# program; these keep Claude Code from doing it by accident (not against an
# agent set on it). A peer's own client.token is not denied: an agent already
# acts as that peer, so reading it grants nothing new.
# In Claude Code rules "/path" is relative to the settings file, "~/path" to home
TOKEN_DENY_RULES = [
    rule
    for path in (OBSERVER_TOKEN_PATH, USER_TOKEN_PATH)
    for rule in (f"Read(~/{path.relative_to(Path.home()).as_posix()})", f"Bash(*{path.name}*)")
] + ["Bash(*observer_client*)"]


def _dotted_keys(tree: dict, prefix: str = "") -> set[str]:
    keys = set()
    for key, value in tree.items():
        path = f"{prefix}{key}"
        keys |= _dotted_keys(value, f"{path}.") if isinstance(value, dict) else {path}
    return keys


def _example() -> dict:
    with open(CONFIG_EXAMPLE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _token_sha256(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _placeholder_token() -> str:
    """The example's own client.token value -- public, since it ships in the repo."""
    return _example()["client"]["token"]


def _reject_placeholder(token: str, what: str) -> None:
    if token == _placeholder_token():
        sys.exit(f"{what} is still the example placeholder, not a real token. Generate one and use that instead.")


def check_config(config_path: Path = CONFIG_PATH) -> None:
    """Stop if config.yaml lacks keys the template has, or still trusts the example token."""
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    missing = _dotted_keys(_example()) - _dotted_keys(config)
    if missing:
        sys.exit(
            f"{config_path} lacks: {', '.join(sorted(missing))}\n"
            f"Add them as in {CONFIG_EXAMPLE} and run the installer again."
        )
    auth = config.get("auth") or {}
    if auth.get("allow_shared_token") and auth.get("token") in (None, "", _placeholder_token()):
        sys.exit(
            f"{config_path}: auth.allow_shared_token is true but auth.token is unset or the example "
            "placeholder -- that value is public (it ships in the repo), so anyone who finds it could "
            "connect as any peer. Generate a real token (openssl rand -hex 32) or turn allow_shared_token off."
        )


def _ask(question: str, default: str | None = None) -> str:
    answer = input(f"  {question}" + (f" [{default}]" if default else "") + ": ").strip()
    if answer:
        return answer
    if default is None:
        sys.exit(f"No answer to '{question}'. Aborted.")
    return default


def write_config(server: bool, config_path: Path = CONFIG_PATH) -> None:
    """Write config.yaml from the template; an existing one is only checked."""
    if config_path.exists():
        check_config(config_path)
        print(f"  Config kept: {config_path}")
        return

    config = _example()
    # The name this machine's token is bound to on the Bridge
    config["client"]["name"] = _ask("Peer name of this machine", socket.gethostname())
    port = config["server"]["port"]
    if server:
        # Never 0.0.0.0: that listens on every interface this machine has,
        # including any public one, and AI-Connect has no TLS of its own --
        # only a VPN interface should ever be able to reach this port
        config["server"]["host"] = _ask(
            "Bridge listen address (this machine's Tailscale/WireGuard IP)", "127.0.0.1"
        )
        config["client"]["bridge_url"] = _bridge_url(config["server"]["host"], port)
    else:
        config["client"]["bridge_url"] = _bridge_url(
            _ask("IP or hostname of the Bridge machine (its VPN address)"), port
        )
        token = _ask("This machine's peer token (from `installer.py add-peer <name>` on the Bridge machine)")
        _reject_placeholder(token, "Peer token")
        config["client"]["token"] = token

    _save_config(config, config_path)
    print(f"  Config written: {config_path}")

    if server:
        for role in TOKEN_PATHS:
            create_token(role, config_path)
        # The Bridge machine runs a peer of its own Bridge too
        peer_name = config["client"]["name"]
        own_token = _add_peer(peer_name, config_path)
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        config["client"]["token"] = own_token
        _save_config(config, config_path)
        print(f"  This machine's own peer token ('{peer_name}') generated and filled in")


def _bridge_url(host: str, port: int) -> str:
    host = f"[{host}]" if ":" in host else host
    return f"ws://{host}:{port}"


def _private_dir(path: Path) -> None:
    """The directory a secret file goes in. AI-Connect's own config directory is closed to everyone but its
    owner, new or already there (vpn/tsadmin.py private_dir: 0700, on Windows an ACL of this user alone);
    any other directory is the caller's, and is only made when missing."""
    if path != CONFIG_PATH.parent:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        return
    sys.path.append(str(REPO / "vpn"))
    import tsadmin  # pylint: disable=import-error,import-outside-toplevel
    try:
        tsadmin.private_dir(path)
    except tsadmin.Failure as err:
        sys.exit(str(err))


def _write_private(path: Path, text: str) -> None:
    """Write a secret file whole, readable by its owner only from the first byte.

    mkstemp creates the temp file 0600 on POSIX whatever the umask, and
    os.replace moves it into place atomically, so the secret never sits in a
    file others may open (a reader that opens it early keeps its descriptor
    after a later chmod). On Windows the file inherits the directory's ACL,
    and the config directory's is the user's alone.
    """
    _private_dir(path.parent)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _save_config(config: dict, config_path: Path = CONFIG_PATH) -> None:
    # The config holds a token: it is a secret file
    _write_private(config_path, yaml.safe_dump(config, sort_keys=False))


# Role -> token file; the config key of its hash is auth.<role>_token_sha256
TOKEN_PATHS = {"observer": OBSERVER_TOKEN_PATH, "user": USER_TOKEN_PATH}


def create_token(role: str, config_path: Path = CONFIG_PATH) -> None:
    """Write a new token of the role to its file, its hash into the config, and deny agents reading it.

    The Bridge only learns the hash; the token stays in its own file for the
    person's tools (reading all traffic, writing as a user). A new token
    locks out the old one once the Bridge restarts.
    """
    path = TOKEN_PATHS[role]
    token = secrets.token_hex(32)
    _write_private(path, token + "\n")
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    config.setdefault("auth", {})[f"{role}_token_sha256"] = _token_sha256(token)
    _save_config(config, config_path)
    print(f"  {role.capitalize()} token written: {path} (restart the Bridge to use it)")
    _deny_tokens_to_claude()


def _add_peer(name: str, config_path: Path) -> str:
    """Create a peer, store its token's SHA-256, return the raw token (caller shows/uses it once)."""
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    peers = config.setdefault("auth", {}).setdefault("peers", {})
    if name in peers:
        sys.exit(f"Peer '{name}' already exists. Run `revoke-peer {name}` first to replace its token.")
    token = secrets.token_hex(32)  # 256 bits
    peers[name] = _token_sha256(token)
    _save_config(config, config_path)
    return token


def add_peer(name: str, config_path: Path = CONFIG_PATH) -> None:
    """Bridge machine: generate a new peer's token, print it once."""
    token = _add_peer(name, config_path)
    print(f"  Peer '{name}' added. On that machine set client.name: '{name}' and client.token to this (shown once):")
    print(f"    {token}")
    print("  Restart the Bridge to use it.")


def revoke_peer(name: str, config_path: Path = CONFIG_PATH) -> None:
    """Bridge machine: remove a peer so its token no longer authenticates."""
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    peers = config.get("auth", {}).get("peers", {})
    if name not in peers:
        sys.exit(f"No such peer: '{name}'")
    del peers[name]
    _save_config(config, config_path)
    print(f"  Peer '{name}' revoked (restart the Bridge to use it)")


def _deny_tokens_to_claude() -> None:
    if not CLAUDE_SETTINGS.exists():
        print(f"  {CLAUDE_SETTINGS} not found; add these deny rules once Claude Code is installed:")
        print("    " + ", ".join(TOKEN_DENY_RULES))
        return
    with open(CLAUDE_SETTINGS, encoding="utf-8") as f:
        settings = json.load(f)
    deny = settings.setdefault("permissions", {}).setdefault("deny", [])
    added = [rule for rule in TOKEN_DENY_RULES if rule not in deny]
    if not added:
        return
    deny.extend(added)
    with open(CLAUDE_SETTINGS, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"  Claude Code may not read the token files or run observer_client: {', '.join(added)} in {CLAUDE_SETTINGS}")


def _find_claude() -> str | None:
    """Claude Code's CLI: from PATH, else where its native installer puts it.

    On Windows the native installer does not add ~/.local/bin to PATH.
    """
    found = shutil.which("claude")
    if found:
        return found
    native = Path.home() / ".local" / "bin" / ("claude.exe" if sys.platform == "win32" else "claude")
    if native.exists():
        print(f"  {native} is not in PATH; using it directly. Add {native.parent} to PATH for the terminal.")
        return str(native)
    return None


def _claude(claude: str, *args: str) -> subprocess.CompletedProcess:
    # check=False: the callers judge the return code themselves (see _check)
    return subprocess.run([claude, *args], capture_output=True, text=True, check=False)


def _check(result: subprocess.CompletedProcess, what: str) -> None:
    if result.returncode != 0:
        sys.exit(f"{what} failed:\n{result.stdout}{result.stderr}")


def register_claude() -> None:
    """Register the MCP server (with this venv's Python) with Claude Code.

    The hooks plugin is not installed here: it ships in the
    useful-claude-add-ons marketplace, and this directory is that plugin.
    """
    claude = _find_claude()
    if claude is None:
        print(
            "  Claude Code not found in PATH. Once it is installed, run:\n"
            f'    "{os.path.abspath(sys.executable)}" "{REPO / "installer.py"}" claude'
        )
        return

    # Replace an existing registration, so a moved repository or a new venv
    # takes effect
    removed = _claude(claude, "mcp", "remove", "-s", "user", MCP_SERVER)
    if removed.returncode != 0 and NOT_REGISTERED not in removed.stdout + removed.stderr:
        _check(removed, "claude mcp remove")
    # abspath, not resolve(): resolving follows the venv's symlink to the system Python
    python = os.path.abspath(sys.executable)
    _check(
        _claude(claude, "mcp", "add", "-s", "user", MCP_SERVER, "--", python, str(REPO / "client" / "server.py")),
        "claude mcp add",
    )
    print(f"  MCP server '{MCP_SERVER}' registered: {python}")
    print(f"  Hooks: claude plugin install {PLUGIN} (if not already installed)")


def unregister_claude() -> None:
    """Remove the MCP server from Claude Code; the plugin is uninstalled separately."""
    claude = _find_claude()
    if claude is None:
        print("  Claude Code not found in PATH, nothing to remove there")
        return
    removed = _claude(claude, "mcp", "remove", "-s", "user", MCP_SERVER)
    if removed.returncode != 0 and NOT_REGISTERED not in removed.stdout + removed.stderr:
        _check(removed, "claude mcp remove")
    print("  AI-Connect MCP server removed from Claude Code")
    print(f"  Hooks: claude plugin uninstall {PLUGIN}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    steps = parser.add_subparsers(dest="step", required=True)
    config = steps.add_parser("config", help="write or check ~/.config/ai-connect/config.yaml")
    mode = config.add_mutually_exclusive_group(required=True)
    mode.add_argument("--server", action="store_true", help="Bridge machine: generate its tokens")
    mode.add_argument("--client", action="store_true", help="other machines: ask for the peer token")
    steps.add_parser("observer-token", help="Bridge machine: generate the token for reading all traffic")
    steps.add_parser("user-token", help="Bridge machine: generate the token for writing to agents as a user")
    add_peer_parser = steps.add_parser("add-peer", help="Bridge machine: add a peer, print its new token once")
    add_peer_parser.add_argument("name", help="peer name, as used in auth.peers and that machine's client.name")
    revoke_peer_parser = steps.add_parser("revoke-peer", help="Bridge machine: remove a peer's token")
    revoke_peer_parser.add_argument("name", help="peer name to remove from auth.peers")
    steps.add_parser("claude", help="register the MCP server with Claude Code")
    steps.add_parser("unregister", help="remove the MCP server from Claude Code")
    args = parser.parse_args()

    if args.step == "config":
        write_config(server=args.server)
    elif args.step in ("observer-token", "user-token"):
        create_token(args.step.removesuffix("-token"))
    elif args.step == "add-peer":
        add_peer(args.name)
    elif args.step == "revoke-peer":
        revoke_peer(args.name)
    elif args.step == "claude":
        register_claude()
    else:
        unregister_claude()


if __name__ == "__main__":
    main()
