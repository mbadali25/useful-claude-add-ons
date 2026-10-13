"""deploy test: the end-to-end check, run on a peer after `deploy peer`.

  deploy test --bridge HOST --name NAME [--port N] [--token-file F]

Five checks, one PASS/FAIL line each: Tailscale is up here, the Bridge's port
answers, the Bridge accepts this machine's token, a message sent to NAME comes
back inside the untrusted frame, and a random token is refused. The exit code
is 1 when any check fails. Nothing on this machine changes; the Bridge keeps
the one test message in NAME's history and logs the refused token.
"""
from __future__ import annotations

import os
from pathlib import Path

from deploy_core import (DEFAULT_PORT, EXIT_FAILED, EXIT_OK, EXIT_USAGE, Failure, backend_state,  # pylint: disable=import-error
                         config_tool, out, tailscale_ip, tsadmin)

ROWS = (("vpn", "VPN up"), ("port", "Bridge port reachable"), ("auth", "Bridge accepts this token"),
        ("round_trip", "Message round trip, untrusted frame"), ("wrong_token", "Wrong token refused"))


def check_vpn() -> tuple[bool, str]:
    try:
        state = backend_state()
        if state != "Running":
            return False, f"Tailscale is not connected (state: {state or 'unknown'})"
        return True, f"Tailscale is running, this machine is {tailscale_ip()}"
    except (Failure, tsadmin.Failure) as err:
        return False, str(err)


def check_port(host: str, port: int) -> tuple[bool, str]:
    userspace = tsadmin.userspace_socket().exists()
    result = tsadmin.probe_tcp(host, port, socks_port=tsadmin.SOCKS_PORT if userspace else None)
    if result == "ok":
        return True, f"{host}:{port} accepts TCP connections"
    if result == "refused":
        return False, f"{host}:{port} refused the connection (Bridge not listening there?)"
    return False, f"{host}:{port} did not answer (timeout or name lookup failed); could not tell"


def read_token(path: str | None) -> str | None:
    """The token from --token-file, or None to let config_tool use the environment or client.token."""
    if not path:
        return None
    try:
        token = Path(path).read_text(encoding="utf-8").strip()
    except OSError as err:
        raise Failure(f"cannot read token file {path}: {err.strerror}", EXIT_USAGE) from None
    if not token:
        raise Failure(f"token file {path} is empty", EXIT_USAGE)
    tsadmin.remember_secret(token)
    return token


def cmd_test(args, check_name, check_host) -> int:
    check_name(args.name, "--name")
    check_host(args.bridge)
    token = read_token(args.token_file)
    tsadmin.remember_secret(os.environ.get("AI_CONNECT_PEER_TOKEN"))
    out(f"=== AI-Connect deploy: test '{args.name}' against {args.bridge}:{args.port} ===")
    results = {"vpn": check_vpn(), "port": check_port(args.bridge, args.port)}
    try:
        answer = config_tool("smoke", "--bridge", args.bridge, "--port", str(args.port), "--name", args.name,
                             env_extra={"AI_CONNECT_PEER_TOKEN": token} if token else None, timeout=120)
        for item in answer.get("checks") or []:
            results[item.get("check")] = (bool(item.get("ok")), str(item.get("detail") or ""))
    except Failure as err:
        for key in ("auth", "round_trip", "wrong_token"):
            results[key] = (False, f"not run: {err}")
    width = max(len(title) for _key, title in ROWS)
    out(f"  {'CHECK'.ljust(width)}  RESULT  DETAIL")
    failed = 0
    for key, title in ROWS:
        ok, detail = results.get(key, (False, "not run: the check gave no answer"))
        failed += not ok
        out(f"  {title.ljust(width)}  {'PASS' if ok else 'FAIL'}    {detail}")
    out("")
    out(f"{len(ROWS) - failed} of {len(ROWS)} checks passed" + ("" if not failed else f", {failed} FAILED"))
    return EXIT_FAILED if failed else EXIT_OK


def add_parser(sub, port_arg, check_name, check_host) -> None:
    t = sub.add_parser("test", help="end-to-end check of this peer against the Bridge")
    t.add_argument("--bridge", required=True, help="the Bridge's Tailscale IP or name")
    t.add_argument("--name", required=True, help="this peer's name, as provisioned on the Bridge")
    t.add_argument("--port", type=port_arg, default=DEFAULT_PORT, help="Bridge port (default 9999)")
    t.add_argument("--token-file", help="this peer's token file (default: AI_CONNECT_PEER_TOKEN, then client.token)")
    t.set_defaults(func=lambda args: cmd_test(args, check_name, check_host))
