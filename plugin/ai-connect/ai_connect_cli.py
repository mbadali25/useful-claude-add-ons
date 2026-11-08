"""ai-connect: enrol machines with one-time join codes and bridge-issued tokens.

    ai-connect bridge invite --name N [--expiry 1h] [--allow-long-expiry] [--host H] [--out F]
                                        Bridge machine: a single-use join code for machine N
                                        (at most 24h; 7d with --allow-long-expiry)
    ai-connect join [<code>]            the new machine: redeem the code, write its client config
                                        (omit <code> to be asked, hidden: the command line is kept
                                        in shell history)
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

The join is plain HTTP in this release: the code's secret goes to the
Bridge, and the new peer's permanent token comes back, unencrypted. So
`bridge invite` warns when the address it puts in the code is not loopback
or Tailscale, and caps a code's life at 24h unless --allow-long-expiry.

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

import bridge_tls
import installer
import join_codes
from config_loader import CONFIG_PATH, bridge_endpoint, bridge_target, server_settings, ws_uri

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


def _reason(err: Exception) -> str:
    """An error as output may show it. A YAML error names its place only: PyYAML's message quotes the
    offending line, and config.yaml holds tokens."""
    if isinstance(err, yaml.YAMLError):
        return f"not valid YAML ({join_codes.yaml_error_place(err)})"
    return str(err)


def _load(config_path: Path) -> dict:
    if not config_path.exists():
        raise Failure(f"{config_path} not found: run the installer first (install.sh --server / install.cmd)")
    try:
        return join_codes.read_config(config_path)
    except (OSError, ValueError, yaml.YAMLError) as err:
        raise Failure(f"{config_path} could not be read: {_reason(err)}") from None


def _check_name(name: str) -> None:
    if not join_codes.PEER_NAME_RE.match(name or ""):
        raise Failure(f"--name '{name}' must be 1-63 letters, digits or hyphens", EXIT_USAGE)


def _is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


# Tailscale's address ranges: its CGNAT IPv4 block and its IPv6 ULA prefix
TAILSCALE_NETS = (ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("fd7a:115c:a1e0::/48"))
# RFC 1918 and IPv6 unique-local: a WireGuard tunnel's or the LAN's, which this cannot tell apart
PRIVATE_NETS = tuple(ipaddress.ip_network(net) for net in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
                                                           "fc00::/7"))


def join_exposure(host: str) -> str | None:
    """Why a plain-HTTP join to host may cross more than a VPN; None for loopback and Tailscale addresses.

    A private LAN address (RFC 1918, IPv6 ULA) is not exempt: it may be a
    WireGuard tunnel, or the LAN at large, and this cannot tell which. A host
    name is not exempt either (except Tailscale's *.ts.net): where it resolves
    is unknown here, and unknown is not safe.
    """
    if host.lower().rstrip(".").endswith(".ts.net"):
        return None
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if host == "localhost":
            return None
        return f"'{host}' is a host name, and whether it resolves to a VPN address cannot be told here"
    if address.is_loopback or any(address in net for net in TAILSCALE_NETS):
        return None
    if any(address in net for net in PRIVATE_NETS):
        return f"{host} is a private address: fine for a WireGuard tunnel, not for the LAN at large"
    return f"{host} is neither loopback nor a Tailscale address (100.64.0.0/10, fd7a:115c:a1e0::/48)"


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
    if expiry > join_codes.SAFE_MAX_EXPIRY_SECONDS and not args.allow_long_expiry:
        raise Failure(f"--expiry {args.expiry} is longer than 24h; the join is plain HTTP in this release, so a "
                      "code that lives longer is longer to intercept. Pass --allow-long-expiry to allow up to 7d",
                      EXIT_USAGE)
    config_path = _config_path(args)
    config = _load(config_path)
    settings = _tls_settings(config)
    # A TLS Bridge's code carries its wss:// port and certificate fingerprint; --plain (or TLS off) the old way
    tls = settings.tls_enabled and not args.plain
    if args.plain and settings.tls_required:
        raise Failure("--plain: this Bridge has no ws:// listener (server.tls.required), so a plain code could "
                      "not be redeemed", EXIT_USAGE)
    host, port = _bridge_address(config, args.host, args.port or (settings.tls_port if tls else None))
    if args.name in ((config.get("auth") or {}).get("peers") or {}):
        raise Failure(f"peer '{args.name}' already exists; revoke it first (ai-connect bridge revoke --name "
                      f"{args.name})")
    out(f"=== ai-connect bridge invite '{args.name}'{' (dry run)' if args.dry_run else ''} ===")
    exposure = join_exposure(host)
    if exposure:
        out(f"  WARNING: the join is plain HTTP in this release: the code's secret goes to {host}:{port}, and "
            f"the permanent token for '{args.name}' comes back, unencrypted. {exposure}. Hand out this code only "
            "where the path to the Bridge is a VPN.")
    if expiry > join_codes.SAFE_MAX_EXPIRY_SECONDS:
        out(f"  WARNING: --allow-long-expiry: this code works for {args.expiry}, longer than the 24h cap. Revoke "
            f"it with `ai-connect bridge revoke --name {args.name}` if it is not used soon.")
    where = f"write it owner-only to {args.out}" if args.out else "show it once"
    transport = "wss://, pinned to this Bridge's certificate" if tls else "plain ws://, deprecated"
    what = f"a single-use join code for '{args.name}' (Bridge {host}:{port}, {transport}, expires in {args.expiry})"
    if args.dry_run:
        out(f"  would: make {what}, keep only its secret's SHA-256 in {join_codes.invites_path(config_path)}, "
            f"and {where}")
        return EXIT_OK
    fingerprint = join_codes.NO_FINGERPRINT
    if tls:
        info, created = _ensure_cert(config_path, settings.tls_validity_days)
        if created:
            out(f"  done: made this Bridge's TLS certificate ({info.cert_path}); RESTART the Bridge so it serves "
                "it, or this code cannot be redeemed")
        fingerprint = bridge_tls.fingerprint_bytes(info.fingerprint)
    else:
        out("  WARNING: a code without a fingerprint: the new machine redeems it and joins over plain ws:// "
            "(deprecated since 0.2.9, gone in 0.3.1)")
    try:
        code = join_codes.create_invite(config_path, args.name, expiry, host, port, fingerprint)
    except (ValueError, TimeoutError, OSError, yaml.YAMLError) as err:
        raise Failure(_reason(err)) from None
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
        out(f"  On '{args.name}': ai-connect join, and paste it at the hidden prompt (or --code-file F, or "
            "AI_CONNECT_JOIN_CODE). Not on the command line: shell history and the process list keep it")
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
            raise Failure(_reason(err)) from None
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
    """Ask the Bridge the code names for this machine's token; Failure with the Bridge's reason otherwise.

    A code with a fingerprint is redeemed over TLS with that pin, checked in
    the handshake before the secret is sent; a mismatch fails closed, and
    nothing is ever retried over plain HTTP. A code without one (an older
    Bridge, or `bridge invite --plain`) goes over plain HTTP, with a warning.
    """
    if code.tls:
        connection = http.client.HTTPSConnection(code.host, code.port, timeout=timeout,
                                                 context=bridge_tls.client_context(code.fingerprint_hex))
    else:
        out("  WARNING: this join code carries no certificate fingerprint, so it is redeemed over plain HTTP and "
            "this machine joins over plain ws:// (deprecated since 0.2.9; ask for a new code to get wss://)")
        connection = http.client.HTTPConnection(code.host, code.port, timeout=timeout)
    try:
        connection.request("GET", join_codes.JOIN_PATH, headers={
            join_codes.SECRET_HEADER: code.secret.hex(), join_codes.NAME_HEADER: code.name})
        response = connection.getresponse()
        body = response.read(64 * 1024).decode("utf-8", "replace")
    except bridge_tls.PinMismatch as err:
        # Before the OSError below: a PinMismatch is one, and must not read as "unreachable"
        raise Failure(f"not joined: {err}") from None
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


def _bridge_url(host: str, port: int, tls: bool = False) -> str:
    return ws_uri(host, port, tls)


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


def _write_identity(config_path: Path, config: dict, name: str, host: str, port: int, token: str,
                    fingerprint: str = "") -> None:
    """client.name, token, bridge_url and the pin: wss:// with client.bridge_fingerprint, or ws:// without one."""
    client = config.setdefault("client", {})
    client["name"], client["token"] = name, token
    _set_endpoint(client, host, port, fingerprint)
    installer._save_config(config, config_path)  # pylint: disable=protected-access  # owner-only, atomic


def _set_endpoint(client: dict, host: str, port: int, fingerprint: str) -> None:
    client["bridge_url"] = _bridge_url(host, port, bool(fingerprint))
    if fingerprint:
        client["bridge_fingerprint"] = fingerprint
    else:
        client.pop("bridge_fingerprint", None)


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
    transport = (f"wss:// pinned to certificate SHA-256 {code.fingerprint_hex}" if code.tls
                 else "plain ws:// (the code carries no fingerprint; deprecated)")
    if args.dry_run:
        out(f"  would: redeem the code at {code.host}:{code.port} (single use) for this machine's token, "
            f"over {'TLS with that pin' if code.tls else 'plain HTTP'}")
        out(f"  would: write client.name '{code.name}', the token, bridge_url ({transport}) into {config_path} "
            "(owner-only)")
        return EXIT_OK
    token = redeem_remote(code)
    _write_identity(config_path, config, code.name, code.host, code.port, token, code.fingerprint_hex)
    if args.code_file:
        Path(args.code_file).unlink(missing_ok=True)
        out(f"  done: used code file {args.code_file} deleted")
    out(f"  done: joined as '{code.name}'; token {join_codes.mask(token)} written owner-only to {config_path}")
    out(f"  transport: {transport}")
    out(f"  Next: register with Claude Code: \"{sys.executable}\" \"{installer.REPO / 'installer.py'}\" claude")
    return EXIT_OK


def _join_with_token(args, config_path: Path) -> int:
    if not (args.bridge and args.name):
        raise Failure("--token-file needs --bridge HOST:PORT and --name N", EXIT_USAGE)
    _check_name(args.name)
    host, port = _parse_bridge(args.bridge)
    fingerprint = _fingerprint_arg(args.fingerprint) if args.fingerprint else ""
    out(f"=== ai-connect join '{args.name}' to {host}:{port} with a token file"
        f"{' (dry run)' if args.dry_run else ''} ===")
    if not fingerprint:
        out("  WARNING: no --fingerprint: this machine joins over plain ws:// (deprecated since 0.2.9). On the "
            "Bridge machine `ai-connect bridge cert show` prints the fingerprint and the wss:// port")
    config = _client_config(config_path, args.force)
    if args.dry_run:
        out(f"  would: write client.name '{args.name}', the token from {args.token_file} and bridge_url "
            f"{_bridge_url(host, port, bool(fingerprint))} into {config_path} (owner-only)")
        return EXIT_OK
    try:
        token = Path(args.token_file).read_text(encoding="utf-8").strip()
    except OSError as err:
        raise Failure(f"cannot read the token file {args.token_file}: {err.strerror}", EXIT_USAGE) from None
    if len(token) < 32 or any(c.isspace() for c in token):
        raise Failure(f"{args.token_file} does not hold one token", EXIT_USAGE)
    _write_identity(config_path, config, args.name, host, port, token, fingerprint)
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
        try:
            _host, _port, fingerprint = bridge_endpoint(client)
        except ValueError as err:
            out(f"  transport: NOT USABLE - {err}")
        else:
            if not fingerprint:
                out("  transport: plain ws:// (deprecated since 0.2.9; pin the Bridge: ai-connect pin <fingerprint>)")
            else:
                check = "not checked (--offline)" if args.offline else _pin_check(url.hostname, port, fingerprint)
                out(f"  transport: wss:// pinned to SHA-256 {fingerprint} - {check}")
    else:
        out("  bridge: client.bridge_url is not set")
    peers = (config.get("auth") or {}).get("peers") or {}
    if peers:
        try:
            pending = sum(1 for entry in join_codes.pending_names(config_path) if entry["state"] == "pending")
        except (ValueError, OSError):
            pending = "unknown (invites.json unreadable)"
        out(f"  this is a Bridge: {len(peers)} peer(s) enrolled, {pending} join code(s) pending")
        try:
            info = bridge_tls.load(config_path.parent)
        except bridge_tls.TlsError as err:
            out(f"  Bridge certificate: UNUSABLE - {err}")
        else:
            out(f"  Bridge certificate: {'none yet (made at the next Bridge start)' if info is None else _describe(info)}")
    return EXIT_OK


def _pin_check(host: str, port: int, fingerprint: str) -> str:
    """A pinned TLS handshake to host:port, no HTTP sent: whether the certificate there is the pinned one."""
    try:
        with socket.create_connection((host, port), timeout=STATUS_TIMEOUT_SECONDS) as raw:
            with bridge_tls.client_context(fingerprint).wrap_socket(raw, server_hostname=host):
                return "the certificate matches the pin"
    except bridge_tls.PinMismatch as err:
        return f"MISMATCH: the certificate there has SHA-256 {err.got} (not connecting; re-pin only if it was rotated)"
    except OSError as err:
        return f"not checked: {err.strerror or err}"


def _describe(info: bridge_tls.CertInfo) -> str:
    expired = " - EXPIRED: rotate it" if info.not_after <= datetime.now(timezone.utc) else ""
    return f"SHA-256 {info.fingerprint}, valid until {info.not_after:%Y-%m-%d}{expired}"


# ---------------------------------------------------------------- TLS: the certificate and the pin


def _fingerprint_arg(text: str) -> str:
    try:
        return bridge_tls.normalize_fingerprint(text)
    except ValueError as err:
        raise Failure(str(err), EXIT_USAGE) from None


def _ensure_cert(config_path: Path, validity_days: int) -> tuple[bridge_tls.CertInfo, bool]:
    """The Bridge's certificate, made now if there is none; under the auth lock, as the Bridge takes it at start."""
    try:
        with join_codes.auth_lock(config_path.parent):
            return bridge_tls.ensure(config_path.parent, validity_days)
    except bridge_tls.TlsError as err:
        raise Failure(str(err)) from None


def _tls_settings(config: dict):
    try:
        return server_settings(config)
    except ValueError as err:
        raise Failure(f"server: in config.yaml: {err}") from None


def cmd_bridge_cert_show(args) -> int:
    config_path = _config_path(args)
    settings = _tls_settings(_load(config_path))
    info, created = _ensure_cert(config_path, settings.tls_validity_days)
    out("=== ai-connect bridge cert show ===")
    if created:
        out(f"  done: made a new self-signed certificate (valid {settings.tls_validity_days} days); restart the "
            "Bridge so it serves it")
    out(f"  certificate: {info.cert_path}")
    out(f"  private key: {info.key_path} (owner-only; never copy it off this machine)")
    out(f"  fingerprint (SHA-256): {info.fingerprint}")
    out(f"  valid: {info.not_before:%Y-%m-%d} to {info.not_after:%Y-%m-%d}"
        + (" - EXPIRED: rotate it" if info.not_after <= datetime.now(timezone.utc) else ""))
    if settings.tls_enabled:
        out(f"  wss:// port: {settings.tls_port or '(any free port)'}; plain ws:// port: "
            f"{'closed (server.tls.required)' if settings.tls_required else settings.port}")
    else:
        out("  server.tls.enabled is false: the Bridge does not serve this certificate")
    out("  Join codes carry this fingerprint. A peer joined with a token file pins it with: "
        f"ai-connect pin {info.fingerprint} --port {settings.tls_port}")
    return EXIT_OK


def cmd_bridge_cert_rotate(args) -> int:
    config_path = _config_path(args)
    config = _load(config_path)
    settings = _tls_settings(config)
    validity = args.validity_days or settings.tls_validity_days
    try:
        old = bridge_tls.load(config_path.parent)
    except bridge_tls.TlsError:
        old = None  # unusable: rotation is exactly what replaces it
    out(f"=== ai-connect bridge cert rotate{' (dry run)' if args.dry_run else ''} ===")
    if args.dry_run:
        out(f"  would: replace {bridge_tls.cert_paths(config_path.parent)[0]} and its key with a new self-signed "
            f"pair valid {validity} days; the fingerprint changes")
        out("  would: end every pending join code (each carries the old fingerprint)")
        out("  then: every peer must re-pin (ai-connect pin <new fingerprint>) or join again; restart the Bridge")
        return EXIT_OK
    try:
        with join_codes.auth_lock(config_path.parent):
            info = bridge_tls.generate(config_path.parent, validity)
            ended = sum(join_codes.cancel_invites(config_path, entry["name"])
                        for entry in join_codes.pending_names(config_path) if entry["state"] == "pending")
            # This machine's own peer follows its own Bridge's new certificate
            config = join_codes.read_config(config_path)
            client = config.get("client") or {}
            own = bool(old and client.get("bridge_fingerprint") == old.fingerprint)
            if own:
                client["bridge_fingerprint"] = info.fingerprint
                installer._save_config(config, config_path)  # pylint: disable=protected-access
    except (bridge_tls.TlsError, ValueError, OSError) as err:
        raise Failure(str(err)) from None
    out(f"  done: new certificate, SHA-256 {info.fingerprint}, valid until {info.not_after:%Y-%m-%d}")
    if old:
        out(f"  the old fingerprint {old.fingerprint} is no longer this Bridge's")
    if ended:
        out(f"  done: ended {ended} pending join code(s): they carried the old fingerprint")
    if own:
        out("  done: this machine's own client.bridge_fingerprint now pins the new certificate")
    out("  NEXT: restart the Bridge so it serves the new certificate. Until each peer re-pins, it FAILS CLOSED "
        "(it refuses the new certificate and never falls back to ws://). On each peer:")
    out(f"    ai-connect pin {info.fingerprint}")
    out("  or make it a new join code (ai-connect bridge invite, after revoking the peer)")
    return EXIT_OK


def cmd_pin(args) -> int:
    """Pin this machine's peer to the Bridge's certificate: wss:// with client.bridge_fingerprint."""
    config_path = _config_path(args)
    fingerprint = _fingerprint_arg(args.fingerprint)
    config = _load(config_path)
    client = config.get("client") or {}
    url = urlsplit(client.get("bridge_url") or "")
    try:
        port = url.port
    except ValueError:
        port = None
    if not url.hostname or not port:
        raise Failure("client.bridge_url is not set: join a Bridge first (ai-connect join)")
    host = args.host or url.hostname
    if args.port:
        new_port = args.port
    elif url.scheme == "wss":
        new_port = port
    else:
        # The Bridge's default: server.tls.port = server.port + 1
        new_port = port + 1
    new_url = _bridge_url(host, new_port, True)
    out(f"=== ai-connect pin{' (dry run)' if args.dry_run else ''} ===")
    if args.dry_run:
        out(f"  would: set client.bridge_url to {new_url} and client.bridge_fingerprint to {fingerprint} in "
            f"{config_path}")
        return EXIT_OK
    if not args.offline:
        check = _pin_check(bridge_target(host), new_port, fingerprint)
        if check.startswith("MISMATCH"):
            raise Failure(f"not pinned: {new_url}: {check}")
        out(f"  {new_url}: {check}")
    _set_endpoint(client, host, new_port, fingerprint)
    config["client"] = client
    installer._save_config(config, config_path)  # pylint: disable=protected-access
    out(f"  done: client.bridge_url {new_url}, pinned to SHA-256 {fingerprint}")
    out("  Restart the Claude Code sessions on this machine so their AI-Connect clients reconnect over wss://")
    return EXIT_OK


# ---------------------------------------------------------------- entry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-connect", description=__doc__.split("\n\n", maxsplit=1)[0])
    parser.add_argument("--config", help=f"config.yaml to use (default {CONFIG_PATH})")
    verbs = parser.add_subparsers(dest="verb", required=True)

    bridge = verbs.add_parser("bridge", help="on the Bridge machine: invite, token, revoke, list")
    bridge_verbs = bridge.add_subparsers(dest="bridge_verb", required=True)
    invite = bridge_verbs.add_parser(
        "invite", help="a single-use join code for one new machine",
        description="A single-use join code for one new machine. Exposure in this release: the join is plain "
                    "HTTP. The new machine sends the code's secret to the Bridge (header X-AI-Connect-Join) and "
                    "the Bridge answers with that machine's permanent peer token, both unencrypted, so whoever "
                    "can watch the path between them can take the token. Put a VPN address in the code: this "
                    "warns when the address is not loopback or Tailscale (100.64.0.0/10, fd7a:115c:a1e0::/48, "
                    "*.ts.net), a private LAN address included. TLS with a pinned certificate follows.")
    invite.add_argument("--name", required=True, help="the new machine's peer name")
    invite.add_argument("--expiry", default="1h",
                        help="how long the code works: 1h (default), 30m, 2h; at most 24h, or 7d with "
                             "--allow-long-expiry")
    invite.add_argument("--allow-long-expiry", action="store_true",
                        help="allow an --expiry past 24h (up to 7d), with a warning")
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
    cert = bridge_verbs.add_parser("cert", help="the Bridge's TLS certificate: show its fingerprint, or rotate it")
    cert_verbs = cert.add_subparsers(dest="cert_verb", required=True)
    cert_show = cert_verbs.add_parser("show", help="path, SHA-256 fingerprint and validity (made if missing)")
    cert_show.set_defaults(func=cmd_bridge_cert_show, dry_run=False)
    rotate = cert_verbs.add_parser("rotate", help="a new key and certificate: every peer must re-pin")
    rotate.add_argument("--validity-days", type=int, help="days the new certificate is valid (default "
                        "server.tls.validity_days, 730)")
    rotate.set_defaults(func=cmd_bridge_cert_rotate)
    invite.add_argument("--plain", action="store_true", help="a code without the certificate fingerprint, redeemed "
                        "over plain ws:// (deprecated; only for a machine still on ai-connect 0.2.6 to 0.2.8)")

    pin = verbs.add_parser("pin", help="this machine: pin the Bridge's certificate and switch to wss://")
    pin.add_argument("fingerprint", help="the SHA-256 that `ai-connect bridge cert show` prints on the Bridge")
    pin.add_argument("--port", type=int, help="the Bridge's wss:// port (default: the current one for wss://, "
                     "else the ws:// port + 1, the Bridge's default)")
    pin.add_argument("--host", help="the Bridge's address (default: the one in client.bridge_url)")
    pin.add_argument("--offline", action="store_true", help="do not check the certificate at the Bridge first")
    pin.set_defaults(func=cmd_pin)

    join = verbs.add_parser("join", help="this machine: redeem a join code (or a token file) and write its config")
    join.add_argument("code", nargs="?",
                      help="the join code. The weakest form: shell history and the process list keep it. Prefer "
                           "omitting it (asked for, hidden), --code-file or AI_CONNECT_JOIN_CODE")
    join.add_argument("--code-file", help="read the code from this file (deleted once used)")
    join.add_argument("--token-file", help="use a token from `bridge token` instead of a code")
    join.add_argument("--bridge", help="with --token-file: the Bridge's HOST:PORT")
    join.add_argument("--name", help="with --token-file: this machine's peer name")
    join.add_argument("--fingerprint", help="with --token-file: the Bridge certificate's SHA-256 (`bridge cert "
                      "show`); --bridge is then its wss:// port. Without it: plain ws://, deprecated")
    join.add_argument("--force", action="store_true", help="replace a peer token this machine already has")
    join.set_defaults(func=cmd_join)

    status = verbs.add_parser("status", help="this machine's config, token (masked) and the Bridge's reachability")
    status.add_argument("--offline", action="store_true", help="do not try to reach the Bridge")
    status.set_defaults(func=cmd_status, dry_run=False)

    for verb in (invite, token, revoke, join, rotate, pin):
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
