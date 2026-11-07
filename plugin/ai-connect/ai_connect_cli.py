"""ai-connect: enrol machines with one-time join codes and bridge-issued tokens.

    ai-connect bridge invite --name N [--expiry 1h] [--host H] [--out F]
                                        Bridge machine: a single-use join code for machine N
    ai-connect join [<code>]            the new machine: redeem the code, write its client config
    ai-connect join --token-file F --bridge HOST:PORT --name N
                                        the new machine, with a token from `bridge token`
    ai-connect bridge token --name N [--out F]
                                        Bridge machine: a long-lived token for N, into an owner-only file
    ai-connect bridge revoke --name N   Bridge machine: remove N; the running Bridge drops it within seconds
    ai-connect bridge list              Bridge machine: enrolled peers and the join codes made
    ai-connect status                   this machine's config, token (masked) and whether the Bridge answers

Every verb that changes something takes --dry-run: it prints what it would
do (`  would: ...`) and changes nothing, as `deploy` does.

This wraps installer.py (the config template, owner-only writes, add-peer)
and join_codes.py (the code format, the invite store, redemption); it does
not replace them. A token is never printed: output shows its last 4
characters, and the token itself goes into an owner-only file. A join code is
printed once, on purpose, by `bridge invite` (or written owner-only with
--out); it is single use and expires.

Bridge-issued tokens do not expire. `bridge revoke` ends one, and a running
Bridge closes the peer's live connections within a few seconds (it polls
config.yaml, server/auth_reload.py); no restart is needed.
"""

from __future__ import annotations

import argparse
import getpass
import http.client
import ipaddress
import json
import os
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import yaml

import installer
import join_codes
from config_loader import CONFIG_PATH

EXIT_OK, EXIT_FAILED, EXIT_USAGE = 0, 1, 2
ISSUED_DIR = "issued-tokens"
JOIN_TIMEOUT_SECONDS = 15.0
STATUS_TIMEOUT_SECONDS = 3.0


class Failure(Exception):
    def __init__(self, message: str, code: int = EXIT_FAILED):
        super().__init__(message)
        self.code = code


def out(message: str) -> None:
    print(message, flush=True)


def _tsadmin():
    sys.path.append(str(installer.REPO / "vpn"))
    import tsadmin  # pylint: disable=import-error,import-outside-toplevel
    return tsadmin


def write_owner_only(path: Path, text: str) -> None:
    """A secret file readable by its owner only: 0600, on Windows an ACL of the current user alone."""
    tsadmin = _tsadmin()
    try:
        tsadmin.write_owner_only(path, text)
    except tsadmin.Failure as err:
        raise Failure(str(err)) from None


def _config_path(args) -> Path:
    return Path(args.config) if args.config else CONFIG_PATH


def _load(config_path: Path) -> dict:
    if not config_path.exists():
        raise Failure(f"{config_path} not found: run the installer first (install.sh --server / install.cmd)")
    try:
        return join_codes.read_config(config_path)
    except (OSError, ValueError, yaml.YAMLError) as err:
        raise Failure(f"{config_path} could not be read: {err}") from None


def _check_name(name: str) -> None:
    if not join_codes.PEER_NAME_RE.match(name or ""):
        raise Failure(f"--name '{name}' must be 1-63 letters, digits or hyphens", EXIT_USAGE)


def _is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def _bridge_address(config: dict, host: str | None, port: int | None) -> tuple[str, int]:
    """The address a join code carries: --host/--port, else this Bridge's own client.bridge_url / server: keys."""
    server = config.get("server") or {}
    url = urlsplit((config.get("client") or {}).get("bridge_url") or "")
    if not host:
        candidates = [url.hostname, server.get("host")]
        host = next((c for c in candidates if c and not _is_loopback(c) and c not in ("0.0.0.0", "::")), None)
        if host is None:
            raise Failure("this Bridge listens on loopback only, so no other machine can use a code that "
                          "carries it: pass --host <this machine's VPN address>", EXIT_USAGE)
    if not port:
        port = server.get("port")
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise Failure("no Bridge port: set server.port in config.yaml or pass --port", EXIT_USAGE)
    if not join_codes.HOST_RE.match(host):
        raise Failure(f"--host '{host}' is not an IP address or host name", EXIT_USAGE)
    return host, port


def _when(seconds: int | None) -> str:
    if not seconds:
        return "-"
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# ---------------------------------------------------------------- bridge verbs


def cmd_bridge_invite(args) -> int:
    _check_name(args.name)
    try:
        expiry = join_codes.parse_expiry(args.expiry)
    except ValueError as err:
        raise Failure(str(err), EXIT_USAGE) from None
    config_path = _config_path(args)
    config = _load(config_path)
    host, port = _bridge_address(config, args.host, args.port)
    if args.name in ((config.get("auth") or {}).get("peers") or {}):
        raise Failure(f"peer '{args.name}' already exists; revoke it first (ai-connect bridge revoke --name "
                      f"{args.name})")
    out(f"=== ai-connect bridge invite '{args.name}'{' (dry run)' if args.dry_run else ''} ===")
    where = f"write it owner-only to {args.out}" if args.out else "show it once"
    what = f"a single-use join code for '{args.name}' (Bridge {host}:{port}, expires in {args.expiry})"
    if args.dry_run:
        out(f"  would: make {what}, keep only its secret's SHA-256 in {join_codes.invites_path(config_path)}, "
            f"and {where}")
        return EXIT_OK
    try:
        code = join_codes.create_invite(config_path, args.name, expiry, host, port)
    except (ValueError, TimeoutError, OSError) as err:
        raise Failure(str(err)) from None
    out(f"  done: {what}")
    out("  WARNING: until it is used or expires, whoever holds this code can join as "
        f"'{args.name}'. Hand it over a private channel.")
    if args.out:
        write_owner_only(Path(args.out), code + "\n")
        out(f"  written owner-only to {Path(args.out).resolve()}")
        out(f"  On '{args.name}': ai-connect join --code-file <that file>")
    else:
        out("  The code, shown once:")
        print(f"  {code}", flush=True)  # the one deliberate secret on stdout: the admin asked for it
        out(f"  On '{args.name}': ai-connect join, and paste it at the prompt (or pass it as the argument)")
    return EXIT_OK


def _issued_path(config_path: Path, name: str) -> Path:
    return config_path.parent / ISSUED_DIR / f"{name}.token"


def cmd_bridge_token(args) -> int:
    _check_name(args.name)
    config_path = _config_path(args)
    config = _load(config_path)
    target = Path(args.out) if args.out else _issued_path(config_path, args.name)
    out(f"=== ai-connect bridge token '{args.name}'{' (dry run)' if args.dry_run else ''} ===")
    if args.name in ((config.get("auth") or {}).get("peers") or {}):
        raise Failure(f"peer '{args.name}' already exists; revoke it first to replace its token")
    if args.dry_run:
        out(f"  would: make a long-lived token for '{args.name}' (no expiry; revocable), keep its SHA-256 in "
            f"auth.peers of {config_path}, and write the token owner-only to {target}")
        return EXIT_OK
    with join_codes.auth_lock(config_path.parent):
        try:
            # installer.py's own add-peer: 256 random bits, the SHA-256 into auth.peers
            token = installer._add_peer(args.name, config_path)  # pylint: disable=protected-access
        except SystemExit as err:
            raise Failure(str(err.code)) from None
        try:
            write_owner_only(target, token + "\n")
        except Failure:
            # A token nobody holds must not stay valid
            join_codes.revoke_peer_locked(config_path, args.name)
            raise
        join_codes.cancel_invites(config_path, args.name)
    out(f"  done: token {join_codes.mask(token)} for '{args.name}' written owner-only to {target.resolve()}")
    out("  It does not expire; `ai-connect bridge revoke --name "
        f"{args.name}` ends it. A running Bridge accepts it within seconds.")
    out(f"  Carry that file to '{args.name}' privately, then there: ai-connect join --token-file <file> "
        f"--bridge <this Bridge's address:port> --name {args.name}")
    return EXIT_OK


def cmd_bridge_revoke(args) -> int:
    _check_name(args.name)
    config_path = _config_path(args)
    config = _load(config_path)
    known = args.name in ((config.get("auth") or {}).get("peers") or {})
    issued = _issued_path(config_path, args.name)
    out(f"=== ai-connect bridge revoke '{args.name}'{' (dry run)' if args.dry_run else ''} ===")
    if args.dry_run:
        out(f"  would: remove '{args.name}' from auth.peers of {config_path}" if known
            else f"  already done: '{args.name}' is not in auth.peers")
        out(f"  would: end any pending join code for '{args.name}'")
        if issued.exists():
            out(f"  would: delete {issued}")
        return EXIT_OK
    with join_codes.auth_lock(config_path.parent):
        try:
            removed = join_codes.revoke_peer_locked(config_path, args.name)
            ended = join_codes.cancel_invites(config_path, args.name)
        except (ValueError, OSError, yaml.YAMLError) as err:
            raise Failure(str(err)) from None
    if issued.exists():
        issued.unlink()
        out(f"  done: deleted {issued}")
    if ended:
        out(f"  done: ended {ended} pending join code(s) for '{args.name}'")
    if not removed:
        if not ended:
            raise Failure(f"no such peer: '{args.name}'")
        return EXIT_OK
    out(f"  done: '{args.name}' removed from auth.peers. A running Bridge closes its connections within "
        "a few seconds; no restart needed")
    return EXIT_OK


def cmd_bridge_list(args) -> int:
    config_path = _config_path(args)
    config = _load(config_path)
    peers = sorted(((config.get("auth") or {}).get("peers") or {}))
    out(f"Peers enrolled in {config_path}: {len(peers)}")
    for name in peers:
        note = " (token file in issued-tokens)" if _issued_path(config_path, name).exists() else ""
        out(f"  {name}{note}")
    try:
        invites = join_codes.pending_names(config_path)
    except (ValueError, OSError) as err:
        raise Failure(f"{join_codes.invites_path(config_path)} could not be read: {err}") from None
    out(f"Join codes: {len(invites)}")
    for entry in invites:
        out(f"  {entry['name']}: {entry['state']} (expires {_when(entry['expires'])})")
    return EXIT_OK


# ---------------------------------------------------------------- join


def _read_code(args) -> str:
    if args.code:
        return args.code
    if args.code_file:
        try:
            return Path(args.code_file).read_text(encoding="utf-8")
        except OSError as err:
            raise Failure(f"cannot read the code file {args.code_file}: {err.strerror}", EXIT_USAGE) from None
    if os.environ.get("AI_CONNECT_JOIN_CODE", "").strip():
        return os.environ["AI_CONNECT_JOIN_CODE"]
    if not sys.stdin.isatty():
        raise Failure("no join code: pass it, --code-file F, or AI_CONNECT_JOIN_CODE", EXIT_USAGE)
    return getpass.getpass("  Join code (not shown): ")


def redeem_remote(code: join_codes.JoinCode, timeout: float = JOIN_TIMEOUT_SECONDS) -> str:
    """Ask the Bridge the code names for this machine's token; Failure with the Bridge's reason otherwise."""
    if code.tls:
        # Fail closed: a code that pins a certificate is never redeemed over plain ws://
        raise Failure("this join code is for a Bridge that serves TLS (it pins the Bridge's certificate), and this "
                      "ai-connect cannot check that yet: update ai-connect on this machine and run join again")
    connection = http.client.HTTPConnection(code.host, code.port, timeout=timeout)
    try:
        connection.request("GET", join_codes.JOIN_PATH, headers={
            join_codes.SECRET_HEADER: code.secret.hex(), join_codes.NAME_HEADER: code.name})
        response = connection.getresponse()
        body = response.read(64 * 1024).decode("utf-8", "replace")
    except (OSError, http.client.HTTPException) as err:
        raise Failure(f"could not reach the Bridge at {code.host}:{code.port}: {err} (is the VPN up?)") from None
    finally:
        connection.close()
    if response.status == 403:
        raise Failure(f"the Bridge refused the code: {join_codes.GENERIC_REFUSAL}. Ask for a new one")
    if response.status == 429:
        raise Failure("the Bridge refused: too many failed join attempts from here; wait a minute")
    if response.status != 200:
        raise Failure(f"the Bridge answered {response.status}: {body.strip()[:200]}")
    try:
        answer = json.loads(body)
        token = answer["token"]
        if answer.get("name") != code.name or not isinstance(token, str) or len(token) < 32:
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise Failure("the Bridge's answer is not a token for this name") from None
    return token


def _bridge_url(host: str, port: int) -> str:
    return f"ws://[{host}]:{port}" if ":" in host else f"ws://{host}:{port}"


def _client_config(config_path: Path, force: bool) -> dict:
    """This machine's config to put the new identity into: the existing one, or the template."""
    if not config_path.exists():
        return installer._example()  # pylint: disable=protected-access
    config = _load(config_path)
    token = (config.get("client") or {}).get("token")
    if token and token != installer._placeholder_token() and not force:  # pylint: disable=protected-access
        raise Failure(f"{config_path} already holds a peer token ({join_codes.mask(token)}): pass --force to "
                      "replace this machine's identity", EXIT_USAGE)
    return config


def _write_identity(config_path: Path, config: dict, name: str, host: str, port: int, token: str) -> None:
    client = config.setdefault("client", {})
    client["name"], client["token"], client["bridge_url"] = name, token, _bridge_url(host, port)
    installer._save_config(config, config_path)  # pylint: disable=protected-access  # owner-only, atomic


def _parse_bridge(text: str) -> tuple[str, int]:
    url = urlsplit(text if "//" in text else f"//{text}")
    try:
        port = url.port
    except ValueError:
        port = None
    if not url.hostname or not port or not join_codes.HOST_RE.match(url.hostname):
        raise Failure(f"--bridge '{text}' must look like HOST:PORT", EXIT_USAGE)
    return url.hostname, port


def cmd_join(args) -> int:
    config_path = _config_path(args)
    if args.token_file:
        return _join_with_token(args, config_path)
    if args.dry_run and not (args.code or args.code_file or os.environ.get("AI_CONNECT_JOIN_CODE")):
        out("=== ai-connect join (dry run) ===")
        out("  would: ask for the join code, redeem it at the Bridge it names for this machine's token, and "
            f"write name, token and bridge_url into {config_path} (owner-only)")
        return EXIT_OK
    try:
        code = join_codes.decode(_read_code(args))
    except join_codes.CodeError as err:
        raise Failure(str(err), EXIT_USAGE) from None
    out(f"=== ai-connect join '{code.name}' to {code.host}:{code.port}{' (dry run)' if args.dry_run else ''} ===")
    if code.expires <= time.time():
        raise Failure(f"this join code expired at {_when(code.expires)}: ask for a new one")
    config = _client_config(config_path, args.force)
    if args.dry_run:
        out(f"  would: redeem the code at {code.host}:{code.port} (single use) for this machine's token")
        out(f"  would: write client.name '{code.name}', the token and bridge_url into {config_path} (owner-only)")
        return EXIT_OK
    token = redeem_remote(code)
    _write_identity(config_path, config, code.name, code.host, code.port, token)
    if args.code_file:
        Path(args.code_file).unlink(missing_ok=True)
        out(f"  done: used code file {args.code_file} deleted")
    out(f"  done: joined as '{code.name}'; token {join_codes.mask(token)} written owner-only to {config_path}")
    out(f"  Next: register with Claude Code: \"{sys.executable}\" \"{installer.REPO / 'installer.py'}\" claude")
    return EXIT_OK


def _join_with_token(args, config_path: Path) -> int:
    if not (args.bridge and args.name):
        raise Failure("--token-file needs --bridge HOST:PORT and --name N", EXIT_USAGE)
    _check_name(args.name)
    host, port = _parse_bridge(args.bridge)
    out(f"=== ai-connect join '{args.name}' to {host}:{port} with a token file"
        f"{' (dry run)' if args.dry_run else ''} ===")
    config = _client_config(config_path, args.force)
    if args.dry_run:
        out(f"  would: write client.name '{args.name}', the token from {args.token_file} and bridge_url into "
            f"{config_path} (owner-only)")
        return EXIT_OK
    try:
        token = Path(args.token_file).read_text(encoding="utf-8").strip()
    except OSError as err:
        raise Failure(f"cannot read the token file {args.token_file}: {err.strerror}", EXIT_USAGE) from None
    if len(token) < 32 or any(c.isspace() for c in token):
        raise Failure(f"{args.token_file} does not hold one token", EXIT_USAGE)
    _write_identity(config_path, config, args.name, host, port, token)
    out(f"  done: token {join_codes.mask(token)} for '{args.name}' written owner-only to {config_path}")
    out(f"  Delete {args.token_file} once the Bridge accepts this machine (ai-connect status)")
    return EXIT_OK


# ---------------------------------------------------------------- status


def _reachable(host: str, port: int) -> str:
    try:
        with socket.create_connection((host, port), timeout=STATUS_TIMEOUT_SECONDS):
            return "reachable"
    except OSError as err:
        return f"NOT reachable ({err.strerror or err})"


def cmd_status(args) -> int:
    config_path = _config_path(args)
    out("=== ai-connect status ===")
    if not config_path.exists():
        out(f"  config: missing ({config_path}); join a Bridge with `ai-connect join`")
        return EXIT_FAILED
    config = _load(config_path)
    client = config.get("client") or {}
    token = client.get("token") or ""
    placeholder = token == installer._placeholder_token()  # pylint: disable=protected-access
    out(f"  config: {config_path}")
    out(f"  peer name: {client.get('name') or '(not set)'}")
    out(f"  token: {'NOT SET (the example placeholder)' if placeholder or not token else join_codes.mask(token)}")
    url = urlsplit(client.get("bridge_url") or "")
    try:
        port = url.port
    except ValueError:
        port = None
    if url.hostname and port:
        out(f"  bridge: {client.get('bridge_url')} - "
            f"{'not checked (--offline)' if args.offline else _reachable(url.hostname, port)}")
    else:
        out("  bridge: client.bridge_url is not set")
    peers = (config.get("auth") or {}).get("peers") or {}
    if peers:
        try:
            pending = sum(1 for entry in join_codes.pending_names(config_path) if entry["state"] == "pending")
        except (ValueError, OSError):
            pending = "unknown (invites.json unreadable)"
        out(f"  this is a Bridge: {len(peers)} peer(s) enrolled, {pending} join code(s) pending")
    return EXIT_OK


# ---------------------------------------------------------------- entry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-connect", description=__doc__.split("\n\n", maxsplit=1)[0])
    parser.add_argument("--config", help=f"config.yaml to use (default {CONFIG_PATH})")
    verbs = parser.add_subparsers(dest="verb", required=True)

    bridge = verbs.add_parser("bridge", help="on the Bridge machine: invite, token, revoke, list")
    bridge_verbs = bridge.add_subparsers(dest="bridge_verb", required=True)
    invite = bridge_verbs.add_parser("invite", help="a single-use join code for one new machine")
    invite.add_argument("--name", required=True, help="the new machine's peer name")
    invite.add_argument("--expiry", default="1h", help="how long the code works: 1h (default), 30m, 2d; at most 7d")
    invite.add_argument("--host", help="the Bridge address the code carries (default: from config.yaml)")
    invite.add_argument("--port", type=int, help="the Bridge port the code carries (default: server.port)")
    invite.add_argument("--out", help="write the code owner-only to this file instead of showing it")
    invite.set_defaults(func=cmd_bridge_invite)
    token = bridge_verbs.add_parser("token", help="a long-lived token for a peer, into an owner-only file")
    token.add_argument("--name", required=True, help="the peer's name")
    token.add_argument("--out", help=f"the token file (default: <config dir>/{ISSUED_DIR}/<name>.token)")
    token.set_defaults(func=cmd_bridge_token)
    revoke = bridge_verbs.add_parser("revoke", help="remove a peer; a running Bridge drops it within seconds")
    revoke.add_argument("--name", required=True, help="the peer's name")
    revoke.set_defaults(func=cmd_bridge_revoke)
    listing = bridge_verbs.add_parser("list", help="enrolled peers and the join codes made")
    listing.set_defaults(func=cmd_bridge_list, dry_run=False)

    join = verbs.add_parser("join", help="this machine: redeem a join code (or a token file) and write its config")
    join.add_argument("code", nargs="?", help="the join code (omit to be asked for it, hidden)")
    join.add_argument("--code-file", help="read the code from this file (deleted once used)")
    join.add_argument("--token-file", help="use a token from `bridge token` instead of a code")
    join.add_argument("--bridge", help="with --token-file: the Bridge's HOST:PORT")
    join.add_argument("--name", help="with --token-file: this machine's peer name")
    join.add_argument("--force", action="store_true", help="replace a peer token this machine already has")
    join.set_defaults(func=cmd_join)

    status = verbs.add_parser("status", help="this machine's config, token (masked) and the Bridge's reachability")
    status.add_argument("--offline", action="store_true", help="do not try to reach the Bridge")
    status.set_defaults(func=cmd_status, dry_run=False)

    for verb in (invite, token, revoke, join):
        verb.add_argument("--dry-run", action="store_true", help="print what would change, change nothing")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except Failure as err:
        print(f"ai-connect: {err}", file=sys.stderr, flush=True)
        return err.code
    except TimeoutError as err:
        print(f"ai-connect: {err}", file=sys.stderr, flush=True)
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
