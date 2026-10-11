"""deploy tailnet-setup: the once-per-tailnet admin work, through the Tailscale API.

  deploy tailnet-setup [--apply] [--admin WHO] [--acl FILE] [--device NAME]
                       [--tailnet NAME] [--no-install-tailscale]

Five steps: Tailscale on this machine, the policy file validated, the tailnet
policy compared with it (and replaced only with --apply, after a backup), the
Bridge machine tagged tag:bridge, and the OAuth client that mint-key and revoke
use created and stored. Without --apply nothing is changed anywhere: it is the
preview. Every call is documented at https://tailscale.com/api.

The API access token is used for this run only and never stored or printed:
it comes from TS_API_TOKEN, or from a prompt when there is a terminal.
"""
from __future__ import annotations

import datetime
import difflib
import getpass
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import ts_install  # pylint: disable=import-error
from deploy_core import (CONFIG_DIR, EXIT_OK, EXIT_USAGE, PLUGIN, Failure, Run,  # pylint: disable=import-error
                         has_terminal, out, run, tsadmin)

API_DOCS = "https://tailscale.com/api"
OAUTH_CONSOLE = "https://login.tailscale.com/admin/settings/oauth"
ACL_TEMPLATE = PLUGIN / "vpn" / "acl-template.hujson"
ADMIN_PLACEHOLDER = "admin@example.com"
ADMIN_RE = re.compile(r"^(autogroup:[a-z-]+|group:[A-Za-z0-9_-]+|[^@\s\"\\]+@[^@\s\"\\]+)$")
TAILNET_RE = re.compile(r"^[A-Za-z0-9.@_-]+$")
BRIDGE_TAG = "tag:bridge"
# What mint-key (auth_keys) and revoke (devices:core) need, and nothing else
OAUTH_SCOPES = ["auth_keys", "devices:core"]
OAUTH_DESCRIPTION = "ai-connect mint-key and revoke"
BACKUP_DIR = CONFIG_DIR / "acl-backups"


# ---------------------------------------------------------------- API


def call(method: str, path: str, token: str, *, text: str | None = None, body: dict | None = None,
         accept: str = "application/json", if_match: str | None = None) -> tuple[int, dict, str]:
    """One Tailscale API call: (status, response headers, body text). text is sent as HuJSON, body as JSON."""
    headers = {"Accept": accept, "Authorization": f"Bearer {token}"}
    data = None
    if text is not None:
        data, headers["Content-Type"] = text.encode("utf-8"), "application/hujson"
    elif body is not None:
        data, headers["Content-Type"] = json.dumps(body).encode("utf-8"), "application/json"
    if if_match is not None:
        headers["If-Match"] = if_match
    url = f"{tsadmin.API_BASE}{path}"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, dict(resp.headers.items()), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, dict(err.headers.items()), err.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as err:
        raise Failure(f"could not reach {urllib.parse.urlsplit(url).netloc}: {getattr(err, 'reason', err)}") from None


def parsed(text: str) -> dict:
    try:
        value = json.loads(text) if text.strip() else {}
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def refusal(what: str, status: int, text: str) -> Failure:
    payload = parsed(text)
    message = str(payload.get("message") or payload.get("error") or text.strip()[:200] or "no message")
    hint = " (is the API access token valid, and may it do this?)" if status in (401, 403) else ""
    return Failure(f"{what} failed: HTTP {status}: {message}{hint}")


def api_token() -> str:
    token = os.environ.get("TS_API_TOKEN", "").strip()
    if not token and has_terminal():
        out("  A Tailscale API access token is needed once (admin console > Settings > Keys >")
        out("  Generate access token). It is used for this run and not stored.")
        token = getpass.getpass("  API access token: ").strip()
    if not token:
        raise Failure("no Tailscale API access token: set TS_API_TOKEN, or run this in a terminal to be asked",
                      EXIT_USAGE)
    tsadmin.remember_secret(token)
    return token


# ---------------------------------------------------------------- policy


def wanted_policy(args) -> str:
    path = Path(args.acl) if args.acl else ACL_TEMPLATE
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as err:
        raise Failure(f"cannot read the policy file {path}: {err.strerror}", EXIT_USAGE) from None
    return text.replace(ADMIN_PLACEHOLDER, args.admin).replace("\r\n", "\n")


def step_validate(r: Run, token: str, tailnet: str, policy: str) -> None:
    r.step("Policy file")
    status, _headers, text = call("POST", f"/tailnet/{tailnet}/acl/validate", token, text=policy)
    # 200 with an empty body is a pass; a body with a message is a policy the tailnet would refuse
    message = parsed(text).get("message")
    if status != 200 or message:
        details = "; ".join(str(item.get("errors") or item) for item in parsed(text).get("data") or []
                            if isinstance(item, dict))
        if status == 200:
            raise Failure(f"Tailscale refuses the policy file: {message}{': ' + details if details else ''}")
        raise refusal("policy validation", status, text)
    out("  done: Tailscale validated the policy file and its tests")


def step_policy(r: Run, token: str, tailnet: str, policy: str) -> None:
    r.step("Tailnet policy")
    status, headers, current = call("GET", f"/tailnet/{tailnet}/acl", token, accept="application/hujson")
    if status != 200:
        raise refusal("reading the tailnet policy", status, current)
    current = current.replace("\r\n", "\n")
    if current.strip() == policy.strip():
        r.already("the tailnet policy is this policy file")
        return
    etag = next((value for key, value in headers.items() if key.lower() == "etag"), None)
    out("  the tailnet policy differs from the policy file (- now, + after):")
    for line in difflib.unified_diff(current.splitlines(), policy.splitlines(), "tailnet policy", "policy file",
                                     lineterm="", n=2):
        out(f"    {line}")
    out("  applying REPLACES the whole tailnet policy with the policy file.")

    def apply() -> None:
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = BACKUP_DIR / f"policy-{stamp}.hujson"
        tsadmin.write_owner_only(backup, current)
        out(f"  backup of the policy as it was: {backup}")
        status, _headers, text = call("POST", f"/tailnet/{tailnet}/acl", token, text=policy, if_match=etag)
        if status == 412:
            raise Failure("the tailnet policy changed while this ran (HTTP 412); nothing was applied, run it again")
        if status != 200:
            raise refusal("applying the policy", status, text)
    r.change("replace the tailnet policy with the policy file", apply)


# ---------------------------------------------------------------- bridge tag


def find_device(args, token: str, tailnet: str, joined: bool) -> tuple[str, str]:
    """(device id, what to call it) for --device, or for this machine."""
    if args.device:
        status, _headers, text = call("GET", f"/tailnet/{tailnet}/devices", token)
        if status != 200:
            raise refusal("device list", status, text)
        want = args.device.lower()
        matches = [d for d in parsed(text).get("devices") or []
                   if want in {str(d.get("hostname", "")).lower(), str(d.get("name", "")).lower(),
                               str(d.get("name", "")).split(".", maxsplit=1)[0].lower()}]
        if len(matches) != 1:
            raise Failure(f"{len(matches)} devices are named '{args.device}'; --device must name exactly one")
        return str(matches[0].get("nodeId") or matches[0].get("id")), f"device '{args.device}'"
    if not joined:
        return "", "this machine"
    res = run([tsadmin.tailscale_bin(), "status", "--json"], timeout=30)
    try:
        node_id = str((json.loads(res.stdout or "{}").get("Self") or {}).get("ID") or "")
    except ValueError:
        node_id = ""
    if not node_id:
        raise Failure("could not read this machine's node ID from `tailscale status --json`; "
                      "pass --device NAME to tag the Bridge machine by name")
    return node_id, "this machine"


def step_tag(r: Run, args, token: str, tailnet: str, joined: bool) -> None:
    r.step(f"Bridge machine tagged {BRIDGE_TAG}")
    device, label = find_device(args, token, tailnet, joined)
    if not device:
        out(f"  would: tag this machine {BRIDGE_TAG} once it is on the tailnet")
        return
    path = f"/device/{urllib.parse.quote(device, safe='')}"
    status, _headers, text = call("GET", path, token)
    if status != 200:
        raise refusal(f"reading {label} from the tailnet", status, text)
    tags = [str(tag) for tag in parsed(text).get("tags") or []]
    if BRIDGE_TAG in tags:
        r.already(f"{label} ({device}) is tagged {BRIDGE_TAG}")
        return

    def tag() -> None:
        status, _headers, text = call("POST", f"{path}/tags", token, body={"tags": [*tags, BRIDGE_TAG]})
        if status != 200:
            raise refusal(f"tagging {label}", status, text)
    r.change(f"tag {label} ({device}) {BRIDGE_TAG}", tag)


# ---------------------------------------------------------------- OAuth client


def store_oauth(cid: str, secret: str) -> str:
    """Keep the OAuth client where mint-key finds it. Returns where it went."""
    try:
        import keyring  # pylint: disable=import-error,import-outside-toplevel  # optional; the OS credential store
        keyring.set_password(tsadmin.KEYRING_SERVICE, "oauth_client_id", cid)
        keyring.set_password(tsadmin.KEYRING_SERVICE, "oauth_client_secret", secret)
        if keyring.get_password(tsadmin.KEYRING_SERVICE, "oauth_client_secret") != secret:
            raise RuntimeError("the credential store did not return what was stored")
        tsadmin.oauth_file().unlink(missing_ok=True)
        return "the OS credential store"
    except Exception as err:  # pylint: disable=broad-exception-caught  # no keyring, or no backend: the file takes it
        why = ("Python keyring is not installed" if isinstance(err, ImportError)
               else f"keyring failed: {type(err).__name__}")
    target = tsadmin.oauth_file()
    tsadmin.write_owner_only(target, json.dumps({"oauth_client_id": cid, "oauth_client_secret": secret}) + "\n")
    return (f"the owner-only file {target} ({why}; `pip install keyring` and run this again to move it "
            "into the OS credential store)")


def keyring_usable() -> bool:
    try:
        import keyring  # pylint: disable=import-error,import-outside-toplevel
        keyring.get_password(tsadmin.KEYRING_SERVICE, "oauth_client_id")
        return True
    except Exception:  # pylint: disable=broad-exception-caught  # absent, or no backend on this machine
        return False


def oauth_works(cid: str, secret: str) -> tuple[bool, int]:
    status, payload = tsadmin.http("POST", f"{tsadmin.API_BASE}/oauth/token", form={
        "client_id": cid, "client_secret": secret, "grant_type": "client_credentials"})
    tsadmin.remember_secret(payload.get("access_token"))
    return status == 200 and bool(payload.get("access_token")), status


def console_steps(why: str) -> list[str]:
    return [f"  the API did not create the OAuth client ({why}). Create it by hand:",
            f"    1. open {OAUTH_CONSOLE} and choose Generate OAuth client",
            "    2. scopes: Keys > Auth Keys (write) and Devices > Core (write), both with tag:ai-peer",
            "    3. copy the client ID and the secret (shown once)"]


def ask_for_client() -> tuple[str, str]:
    cid = os.environ.get("TS_OAUTH_CLIENT_ID", "").strip()
    secret = os.environ.get("TS_OAUTH_CLIENT_SECRET", "").strip()
    if not (cid and secret) and has_terminal():
        cid = input("  OAuth client ID: ").strip()
        secret = getpass.getpass("  OAuth client secret: ").strip()
    if not (cid and secret):
        raise Failure("the OAuth client is not set up yet: create it as described above, then run this again "
                      "with TS_OAUTH_CLIENT_ID and TS_OAUTH_CLIENT_SECRET set (or in a terminal, to be asked)")
    tsadmin.remember_secret(secret)
    return cid, secret


def step_oauth(r: Run, token: str, tailnet: str) -> None:
    r.step("OAuth client for mint-key and revoke")
    cid, secret, source = tsadmin.stored_oauth_credentials(use_env=False)
    if cid:
        works, status = oauth_works(cid, secret)
        if not works:
            raise Failure(f"the stored OAuth client {cid} ({source}) was refused (HTTP {status}); delete it "
                          f"there, revoke it at {OAUTH_CONSOLE}, and run this again to create a new one")
        if source and source.startswith("file") and keyring_usable():
            # A rerun after `pip install keyring` moves it out of the file
            r.change(f"move OAuth client {cid} from the owner-only file into the OS credential store",
                     lambda: store_oauth(cid, secret))
            return
        r.already(f"OAuth client {cid} is in the {source} and Tailscale accepts it")
        return

    def create() -> None:
        status, _headers, text = call("POST", f"/tailnet/{tailnet}/keys", token, body={
            "keyType": "client", "scopes": OAUTH_SCOPES, "tags": [tsadmin.DEFAULT_TAG],
            "description": OAUTH_DESCRIPTION})
        payload = parsed(text)
        new_id, new_secret = str(payload.get("id") or ""), str(payload.get("key") or "")
        tsadmin.remember_secret(new_secret)
        if status != 200 or not (new_id and new_secret):
            why = f"HTTP {status}: {payload.get('message') or 'no client in the answer'}"
            for line in console_steps(why):
                out(line)
            new_id, new_secret = ask_for_client()
            works, exchange = oauth_works(new_id, new_secret)
            if not works:
                raise Failure(f"Tailscale refused OAuth client {new_id} (HTTP {exchange}); nothing was stored")
        out(f"  OAuth client {new_id} stored in {store_oauth(new_id, new_secret)}")
    r.change(f"create an OAuth client ({', '.join(OAUTH_SCOPES)}; {tsadmin.DEFAULT_TAG}) and store it", create)


# ---------------------------------------------------------------- command


def cmd_tailnet_setup(args) -> int:
    if not ADMIN_RE.match(args.admin):
        raise Failure(f"--admin '{args.admin}' is not an email address, group:name or autogroup:name", EXIT_USAGE)
    if not TAILNET_RE.match(args.tailnet):
        raise Failure(f"--tailnet '{args.tailnet}' is not a tailnet name", EXIT_USAGE)
    policy = wanted_policy(args)
    tailnet = urllib.parse.quote(args.tailnet, safe="")
    r = Run(dry_run=not args.apply, total=5)
    mode = "" if args.apply else " (preview: nothing changes without --apply)"
    out(f"=== AI-Connect deploy: tailnet-setup{mode} ===")
    token = api_token()
    r.step("Tailscale on this machine")
    joined = bool(args.device)
    if not args.device:
        joined = ts_install.step_install(r, not args.no_install_tailscale) and ts_install.step_login(r)
    else:
        out(f"  not needed here: --device {args.device} names the Bridge machine")
    step_validate(r, token, tailnet, policy)
    step_policy(r, token, tailnet, policy)
    step_tag(r, args, token, tailnet, joined)
    step_oauth(r, token, tailnet)
    out("")
    if args.apply:
        out("The tailnet is set up. Next on this machine: deploy bridge --peer <name>")
    else:
        out("Preview only. Run it again with --apply to make these changes.")
    return EXIT_OK


def add_parser(sub) -> None:
    t = sub.add_parser("tailnet-setup", help="ADMIN, once per tailnet: policy, Bridge tag and OAuth client")
    t.add_argument("--apply", action="store_true", help="make the changes (without it: a preview)")
    t.add_argument("--admin", default="autogroup:admin",
                   help=f"who owns the tags and keeps access to the Bridge; replaces {ADMIN_PLACEHOLDER} in the "
                        "policy file (default: autogroup:admin)")
    t.add_argument("--acl", help="policy file to apply (default: vpn/acl-template.hujson)")
    t.add_argument("--device", help="the Bridge machine's tailnet name, when it is not this machine")
    t.add_argument("--tailnet", default="-", help="tailnet to configure (default: the API token's own)")
    t.add_argument("--no-install-tailscale", action="store_true", help="fail instead of installing Tailscale")
    t.set_defaults(func=cmd_tailnet_setup)
