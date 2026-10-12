#!/usr/bin/env python3
"""AI-Connect setup: from "plugin installed" to a working peer in one run.

  setup bridge  [--name N] [--peer P ...] [--enrol NAME=SHA256 ...] [--port N] [--vpn-subnet CIDR]
                [--no-install-tailscale] [--register-mcp] [--scope user|project] [--apply]
  setup peer    --name N --bridge HOST [--token-file F | --invite-file F] [--auth-key-file F] [--port N]
                [--no-install-tailscale] [--register-mcp] [--scope user|project] [--apply]
  setup session --name N [--apply]

One core behind the setup.sh / setup.ps1 pair, and a thin one: every change is made
by deploy.py's own steps (deploy bridge, peer, join, add-peer), so nothing is done
twice in two ways. What setup adds is the order, a plan by default, the checks deploy
leaves to the reader (is the firewall on, has the tailnet policy been set), and a
second peer name for a second session on one machine.

Without --apply nothing changes: every step prints what it would do (deploy's
--dry-run, which runs no tool at all). --apply does it. Either can be run again; a
step that is done says "already done".

setup never runs `deploy tailnet-setup`: that needs the owner's Tailscale API token
and replaces the tailnet policy. It says when that step looks outstanding.

Exit codes: deploy's. 0 done, 1 a step failed, 2 bad arguments, 3 Tailscale not installed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import sys

import deploy  # pylint: disable=import-error
import firewall_state  # pylint: disable=import-error
import tailnet_setup  # pylint: disable=import-error
from deploy_core import (CONFIG_DIR, DEFAULT_PORT, EXIT_FAILED, EXIT_OK, EXIT_USAGE, Failure, Run,  # pylint: disable=import-error
                         no_tools, out, tailscale_ip, ts_self, tsadmin)

# config_loader.SESSION_TOKEN_DIR: where the client looks for the token of AI_CONNECT_PEER_NAME
SESSION_TOKEN_DIR = CONFIG_DIR / "session-tokens"
SH, PS1 = "deploy/setup.sh", "deploy\\setup.ps1"
DONE, OUTSTANDING, UNKNOWN, NOT_CHECKED = "done", "outstanding", "could not tell", "not checked (plan)"
TAILNET_SETUP = (
    "  It is the owner's step, and setup never runs it: it needs a Tailscale API access token, and --apply\n"
    "  REPLACES the whole tailnet policy. On the Bridge machine, preview first, then apply:\n"
    "    deploy/deploy.sh tailnet-setup              (deploy\\deploy.ps1 on Windows)\n"
    "    deploy/deploy.sh tailnet-setup --apply\n"
    "  The runbook: deploy/README.md, \"Machine 1: the tailnet\".")


def section(title: str) -> None:
    out("")
    out(f"--- {title} ---")


def run_deploy(argv: list[str], dry: bool) -> int:
    """One deploy subcommand, in this process: deploy's own parser, steps and text."""
    args = deploy.build_parser().parse_args(argv + (["--dry-run"] if dry else []))
    return args.func(args)


def banner(what: str, dry: bool) -> None:
    out(f"=== AI-Connect setup: {what}{' (plan: nothing is changed; --apply does it)' if dry else ''} ===")


def closing(dry: bool, role: str) -> None:
    if dry:
        out(f"  This was the plan: nothing was changed. To do it, run the same command with --apply "
            f"({SH} {role} ... --apply, {PS1} on Windows).")


# ---------------------------------------------------------------- tailnet policy (read-only)


def acl_bridge(r: Run) -> str:
    """Whether `deploy tailnet-setup --apply` has run here, by what it leaves on the Bridge machine: the
    tag on this node and the stored OAuth client. The policy itself is not read: that needs the API token."""
    r.step("Tailnet policy: has `deploy tailnet-setup --apply` run?")
    if r.dry_run:
        out("  would: read this machine's tags (tailscale status) and look for the stored OAuth client; "
            "it changes nothing")
        return NOT_CHECKED
    try:
        me = ts_self()
    except (Failure, tsadmin.Failure):
        me = {}
    if not me:
        out("  COULD NOT TELL: `tailscale status` gave no answer, so this machine's tags are unknown.")
        out(TAILNET_SETUP)
        return UNKNOWN
    tagged = tailnet_setup.BRIDGE_TAG in [str(tag) for tag in me.get("Tags") or []]
    cid, secret, _source = tsadmin.stored_oauth_credentials(use_env=False)
    tsadmin.remember_secret(secret)
    stored = bool(cid and secret)
    if tagged and stored:
        r.already(f"this machine is tagged {tailnet_setup.BRIDGE_TAG} and the OAuth client is stored: "
                  "tailnet-setup has run here (the policy itself is not read)")
        return DONE
    missing = ([] if tagged else [f"this machine is not tagged {tailnet_setup.BRIDGE_TAG}"]) + \
              ([] if stored else ["no OAuth client is stored here (invite and vpn/mint-key cannot make join keys)"])
    r.record("warning", "tailnet-setup looks outstanding: " + "; ".join(missing))
    out("  OUTSTANDING: `deploy tailnet-setup --apply` does not look done: " + "; ".join(missing) + ".")
    out(f"  Until the policy allows it, a peer tagged {tsadmin.DEFAULT_TAG} cannot reach this Bridge's port.")
    out(TAILNET_SETUP)
    return OUTSTANDING


def acl_peer(r: Run, bridge: str, port: int) -> str:
    """Whether this machine reaches the Bridge's port. A port that does not answer is the usual sign of a
    tailnet policy that does not let tag:ai-peer reach tag:bridge."""
    r.step("Tailnet policy: does this machine reach the Bridge port?")
    if r.dry_run:
        out(f"  would: open one TCP connection to {bridge}:{port} and close it; it changes nothing")
        return NOT_CHECKED
    try:
        userspace = tsadmin.userspace_socket().exists()
        result = tsadmin.probe_tcp(bridge, port, socks_port=tsadmin.SOCKS_PORT if userspace else None)
    except (Failure, tsadmin.Failure, OSError):
        result = "unknown"
    if result == "ok":
        r.already(f"{bridge}:{port} accepts TCP connections: the tailnet policy lets this machine reach the Bridge")
        return DONE
    if result == "refused":
        out(f"  {bridge}:{port} refused the connection: the tailnet lets this machine through, and nothing listens "
            "there. On the Bridge: deploy status, and its --port.")
        return DONE
    r.record("warning", f"{bridge}:{port} did not answer")
    out(f"  OUTSTANDING or COULD NOT TELL: {bridge}:{port} did not answer. If the Bridge is running and this "
        f"machine is on the tailnet, the policy does not let {tsadmin.DEFAULT_TAG} reach "
        f"{tailnet_setup.BRIDGE_TAG}:{port}.")
    out(TAILNET_SETUP)
    return OUTSTANDING


# ---------------------------------------------------------------- firewall summary


def firewall_line() -> str:
    """One line on what the firewall step of this run found (deploy.step_firewall, through firewall_state)."""
    report = firewall_state.REPORT
    if not report:
        return "not part of this run"
    kind, state = report.get("kind"), report.get("state")
    where = f"port {report.get('port')} from {report.get('subnet')}"
    if kind is None:
        return f"no ufw or firewalld here: nothing limits {where}; add the rule the step printed"
    name = {"ufw": "ufw", "firewall-cmd": "firewalld", "netsh": "Windows Firewall"}[kind]
    if state == firewall_state.ACTIVE:
        return f"{name} is on and allows {where} only"
    if state == firewall_state.INACTIVE:
        return f"NOT ENFORCED: {name} is off, so the rule for {where} filters nothing (see the firewall step)"
    if state == firewall_state.UNKNOWN:
        return f"NOT VERIFIED: could not tell whether {name} is on (see the firewall step)"
    return f"{name}: the rule for {where} is in the plan; whether {name} is on is checked by --apply"


# ---------------------------------------------------------------- bridge


def parse_enrol(text: str) -> tuple[str, str]:
    name, sep, digest = text.partition("=")
    if not sep:
        raise Failure(f"--enrol '{text}' must be NAME=SHA256, the name and token_sha256 a peer printed", EXIT_USAGE)
    deploy.check_name(name, "--enrol")
    deploy.check_sha256(digest)
    return name, digest


def mcp_args(args) -> list[str]:
    return ["--register-mcp", "--scope", args.scope] if args.register_mcp else []


def cmd_bridge(args) -> int:
    dry = not args.apply
    for peer in args.peer:
        deploy.check_name(peer, "--peer")
    enrol = [parse_enrol(text) for text in args.enrol]
    banner("bridge", dry)
    if deploy.TARGET == "windows":
        out("  note: run this from an elevated PowerShell: the scheduled task and the firewall rule need "
            "administrator rights, and setup raises no UAC prompt itself")

    section("Bridge: venv, Tailscale, config, peer tokens, service, firewall (deploy bridge)")
    argv = ["bridge", "--port", str(args.port), "--vpn-subnet", args.vpn_subnet]
    argv += ["--name", args.name] if args.name else []
    for peer in args.peer:
        argv += ["--peer", peer]
    argv += ["--no-install-tailscale"] if args.no_install_tailscale else []
    code = run_deploy(argv, dry)
    if code != EXIT_OK:
        return code
    for name, digest in enrol:
        section(f"Peer '{name}' by its token hash (deploy add-peer)")
        if dry and not (deploy.inspect_config() or {}).get("exists"):
            # deploy add-peer reads the Bridge's config, and a plan on a new machine has made none
            out(f"  would: enrol peer '{name}' by its token hash ****{digest[-4:]} once the Bridge config above "
                "exists, and restart the Bridge")
            continue
        code = run_deploy(["add-peer", "--name", name, "--token-sha256", digest], dry)
        if code != EXIT_OK:
            return code

    section("Checks deploy leaves to you")
    r = Run(dry, total=2)
    acl = acl_bridge(r)
    if args.register_mcp:
        deploy.step_claude(r, argparse.Namespace(install_hooks=False, register_mcp=True, scope=args.scope))
    else:
        r.step("Claude Code")
        out("  skipped: no MCP server registered (the default). --register-mcp registers it for this user "
            "(--scope project: only for the directory setup runs in)")

    section("Summary")
    out(f"  firewall: {firewall_line()}")
    out(f"  tailnet policy: {acl}")
    ip = "<this machine's Tailscale IPv4>" if dry else tailscale_ip()
    for peer in args.peer:
        out(f"  peer '{peer}': its token file is {deploy.TOKEN_DIR / (peer + '.token')}. It is a secret: carry it to "
            "that machine over a private channel, and run there:")
        out(f"    {SH} peer --name {peer} --bridge {ip} --token-file <file> --apply")
        out(f"    {PS1} peer --name {peer} --bridge {ip} --token-file <file> --apply")
    if not (args.peer or enrol):
        out(f"  no peer yet. Here: {SH} bridge --peer <name> --apply; or on the new machine "
            f"{SH} peer --name <name> --bridge {ip} --apply, which prints the --enrol NAME=SHA256 for here")
    closing(dry, "bridge")
    return EXIT_OK


# ---------------------------------------------------------------- peer


def configured_from_bridge(name: str, bridge: str, port: int) -> bool:
    """This machine already joins `bridge` as `name` with a token the Bridge made (no own token here)."""
    facts = deploy.inspect_config() or {}
    return bool(facts.get("exists") and facts.get("name") == name and facts.get("token_sha256")
                and facts.get("bridge_url") == deploy.bridge_url(bridge, port) and not deploy.OWN_TOKEN.is_file())


def cmd_peer(args) -> int:
    dry = not args.apply
    if args.token_file and args.invite_file:
        raise Failure("--token-file and --invite-file are two ways in: pass one", EXIT_USAGE)
    if not args.invite_file and not (args.name and args.bridge):
        raise Failure("peer needs --name and --bridge, or --invite-file (an invite carries both)", EXIT_USAGE)
    if args.name:
        deploy.check_name(args.name, "--name")
    if args.bridge:
        deploy.check_host(args.bridge)
    banner(f"peer '{args.name or '<the invite names it>'}'", dry)
    common = (["--no-install-tailscale"] if args.no_install_tailscale else []) + mcp_args(args)
    named = (["--name", args.name] if args.name else []) + (["--bridge", args.bridge] if args.bridge else [])
    step = None
    if args.token_file:
        section("Peer with the token file from the Bridge (deploy peer)")
        argv = ["peer", *named, "--port", str(args.port), "--token-file", args.token_file, *common]
        argv += ["--auth-key-file", args.auth_key_file] if args.auth_key_file else []
    elif args.invite_file:
        section("Peer with an invite (deploy join)")
        argv = ["join", "--invite-file", args.invite_file, *named, *common]
    elif configured_from_bridge(args.name, args.bridge, args.port):
        section("Peer already set up with a token from the Bridge")
        argv, step = None, Run(dry, total=2 if args.register_mcp else 1)
    else:
        section("Peer with its own token: only the hash goes to the Bridge (deploy join)")
        argv = ["join", *named, "--port", str(args.port), *common]

    failed = None
    try:
        if argv is not None:
            code = run_deploy(argv, dry)
        else:
            step.step("Client configuration")
            step.already(f"{deploy.CONFIG_FILE} points at {args.bridge} as '{args.name}' (pass --token-file to "
                         "replace the token)")
            if args.register_mcp:
                deploy.step_claude(step, argparse.Namespace(install_hooks=False, register_mcp=True, scope=args.scope))
            deploy.verify(step, "Bridge connection")
            code = EXIT_OK
    except (Failure, tsadmin.Failure) as err:
        # Said here and not lost: the check below is what tells a closed policy from a wrong token
        failed, code = err, err.code
        print(tsadmin.redact(f"setup peer: {err}"), file=sys.stderr, flush=True)

    acl = NOT_CHECKED
    if args.bridge:
        section("Checks deploy leaves to you")
        acl = acl_peer(Run(dry, total=1), args.bridge, args.port)
    section("Summary")
    out("  firewall: a peer's firewall is never touched; only the Bridge gets a rule")
    out(f"  tailnet policy: {acl}")
    if failed is None and code == EXIT_OK and not dry and not args.token_file \
            and deploy.config_tool("verify").get("result") == "refused":
        out(f"  Not approved yet. On the Bridge: {SH} bridge --enrol NAME=SHA256 --apply with the "
            "{name, token_sha256} printed above (the hash is not a secret; the token never leaves this machine)")
    if not args.register_mcp:
        out("  Claude Code: no MCP server registered (the default); --register-mcp registers it for this user")
    closing(dry, "peer")
    return code


# ---------------------------------------------------------------- a second session


def cmd_session(args) -> int:
    """A second peer name on this machine, with a token of its own, for a session started with
    AI_CONNECT_PEER_NAME: every session shares client.name otherwise, and only one of them is online."""
    dry = not args.apply
    name = args.name
    deploy.check_name(name, "--name")
    facts = deploy.inspect_config()
    if not (facts and facts.get("exists") and facts.get("bridge_url")):
        raise Failure(f"{deploy.CONFIG_FILE} is missing or has no client section: set this machine up first "
                      f"({SH} bridge or {SH} peer)")
    if name == facts.get("name"):
        raise Failure(f"'{name}' is this machine's own peer name (client.name): a second session needs another "
                      "name", EXIT_USAGE)
    banner(f"session '{name}'", dry)
    here = deploy.bridge_here()
    r = Run(dry, total=3 if here else 2)

    r.step(f"Token for '{name}'")
    target = SESSION_TOKEN_DIR / f"{name}.token"
    try:
        token = target.read_text(encoding="utf-8").strip()
    except OSError:
        token = ""
    if token:
        tsadmin.remember_secret(token)
        r.already(f"'{name}' has its own token in {target}")
    else:
        made = secrets.token_hex(32)
        tsadmin.remember_secret(made)

        def write() -> None:
            tsadmin.private_dir(CONFIG_DIR)
            tsadmin.private_dir(SESSION_TOKEN_DIR)
            tsadmin.write_owner_only(target, made + "\n")
        r.change(f"make a token for '{name}', owner-only in {target}", write)
        token = "" if dry else made
    digest = hashlib.sha256(token.encode()).hexdigest() if token else None

    if here:
        if digest:
            deploy.step_enrol(r, name, digest)
        else:
            r.step("Peer enrolment by token hash")
            r.change(f"enrol peer '{name}' by the hash of that token in {deploy.CONFIG_FILE}", lambda: None)
            deploy.owe_restart(r)
        if r.config_changed:
            out("  note: the Bridge restart below disconnects every peer that is online, for a moment")
        deploy.step_service(r)
    else:
        r.step("Installed files")
        if deploy.APP.is_dir():
            # The MCP server runs from this copy: an older one does not know session tokens
            deploy.step_app(r, restart_on_change=False)
        else:
            r.already(f"no installed copy at {deploy.APP}: the MCP server runs from this directory")
        if digest:
            out("")
            print(json.dumps({"name": name, "token_sha256": digest}), flush=True)
            out(f"  The token stays here. On the Bridge: {SH} bridge --enrol {name}={digest} --apply "
                f"(or deploy add-peer --name {name} --token-sha256 {digest})")
        else:
            out("  would: print {name, token_sha256} for the Bridge to let it in (deploy add-peer)")

    section("Summary")
    out(f"  Start the second session with the name in the environment of the `claude` command itself: the "
        f"MCP server and the watcher both read it there, and send the token of '{name}' instead of client.token.")
    out(f"    bash:        AI_CONNECT_PEER_NAME={name} claude")
    out(f"    PowerShell:  $env:AI_CONNECT_PEER_NAME = '{name}'; claude")
    out(f"  To take it back, on the Bridge: deploy remove --name {name} --yes (needs the stored OAuth client), or "
        f"installer.py revoke-peer {name} and a Bridge restart; then delete {target}.")
    closing(dry, "session")
    return EXIT_OK


# ---------------------------------------------------------------- entry


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="setup", description=__doc__.split("\n\n", maxsplit=1)[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("bridge", help="this machine runs the Bridge; also prepares peers on it")
    b.add_argument("--name", help="this machine's own peer name (default: host name)")
    b.add_argument("--peer", action="append", default=[], metavar="NAME",
                   help="make a token file for this peer, to carry to its machine (repeatable)")
    b.add_argument("--enrol", action="append", default=[], metavar="NAME=SHA256",
                   help="let in a peer that made its own token, by the hash it printed (repeatable)")
    b.add_argument("--vpn-subnet", type=deploy.subnet_arg, default=deploy.DEFAULT_SUBNET,
                   help="only this range may reach the port (default Tailscale's 100.64.0.0/10)")
    b.set_defaults(func=cmd_bridge)

    pe = sub.add_parser("peer", help="this machine joins a Bridge")
    pe.add_argument("--name", help="this peer's name")
    pe.add_argument("--bridge", help="the Bridge's Tailscale IP")
    pe.add_argument("--token-file", help="the token file `setup bridge --peer` made on the Bridge")
    pe.add_argument("--invite-file", help="the invite `deploy invite --out` made on the Bridge")
    pe.add_argument("--auth-key-file", help="with --token-file: a one-off Tailscale auth key, when this machine "
                                            "is not on the tailnet yet")
    pe.set_defaults(func=cmd_peer)

    s = sub.add_parser("session", help="a second peer name on this machine, for a second Claude Code session")
    s.add_argument("--name", required=True, help="the second session's peer name")
    s.set_defaults(func=cmd_session)

    for cmd in (b, pe):
        cmd.add_argument("--port", type=deploy.port_arg, default=DEFAULT_PORT, help="Bridge port (default 9999)")
        cmd.add_argument("--no-install-tailscale", action="store_true",
                         help="fail (exit 3) instead of installing Tailscale when it is missing")
        cmd.add_argument("--register-mcp", action="store_true",
                         help="also register the ai-connect MCP server with Claude Code (off by default)")
        cmd.add_argument("--scope", choices=("user", "project"), default="user",
                         help="where --register-mcp registers it: every project of this user (user, the default) "
                              "or the directory setup runs in (project)")
    for cmd in (b, pe, s):
        cmd.add_argument("--apply", action="store_true",
                         help="make the changes; without it setup prints the plan and changes nothing")
    return p


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 10):
        print("setup: Python 3.10 or newer is required", file=sys.stderr)
        return EXIT_FAILED
    if deploy.TARGET not in ("linux", "windows"):
        print(f"setup: AI_CONNECT_DEPLOY_OS must be linux or windows, not {deploy.TARGET}", file=sys.stderr)
        return EXIT_USAGE
    args = build_parser().parse_args(argv)
    if not args.apply:
        no_tools()
    try:
        return args.func(args)
    except (Failure, tsadmin.Failure) as err:
        print(tsadmin.redact(f"setup {args.cmd}: {err}"), file=sys.stderr, flush=True)
        return err.code
    except Exception as err:  # pylint: disable=broad-exception-caught  # never let a traceback carry a secret
        print(tsadmin.redact(f"setup {args.cmd}: unexpected {type(err).__name__}: {err}"), file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
