#!/usr/bin/env python3
"""Token acquisition for Microsoft Graph / Intune.

Three modes, selected by INTUNE_AUTH_MODE or --mode:
  client_credentials  app registration + secret or certificate (unattended)
  device_code         interactive sign-in as a human (respects Intune RBAC)
  azure_cli           reuse an existing `az login` session

Tokens are cached in ~/.intune_graph_token.json (0600) and reused until they
expire, so repeated script runs don't re-prompt or re-mint needlessly.

Never hardcode a secret here. Read references/auth-setup.md.
"""
import argparse
import base64
import json
import os
import shutil
import stat
import sys
import time
import subprocess

import requests

AUTHORITY = "https://login.microsoftonline.com"
SCOPE_APP = "https://graph.microsoft.com/.default"
CACHE_PATH = os.path.expanduser("~/.intune_graph_token.json")

# Microsoft's well-known public client ID for Azure PowerShell. Usable for
# device code flow without registering your own app, which is handy for ad-hoc
# troubleshooting. For anything durable, register a real app instead.
DEFAULT_PUBLIC_CLIENT = "1950a258-227b-4e31-a9cf-717495945fc2"

DELEGATED_SCOPES = [
    "https://graph.microsoft.com/DeviceManagementManagedDevices.ReadWrite.All",
    "https://graph.microsoft.com/DeviceManagementConfiguration.ReadWrite.All",
    "https://graph.microsoft.com/DeviceManagementApps.ReadWrite.All",
    "https://graph.microsoft.com/DeviceManagementServiceConfig.ReadWrite.All",
    "https://graph.microsoft.com/Directory.Read.All",
    "offline_access",
]


class AuthError(Exception):
    pass


def _env(name, required=False):
    v = os.environ.get(name)
    if required and not v:
        raise AuthError(
            f"{name} is not set. See references/auth-setup.md for the variables "
            f"each auth mode needs."
        )
    return v


def _load_cache(key):
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            blob = json.load(f)
    except (OSError, ValueError):
        return None
    entry = blob.get(key)
    if not entry:
        return None
    # 5 min safety margin so a token doesn't expire mid-pagination
    if entry.get("expires_at", 0) < time.time() + 300:
        return None
    return entry


def _save_cache(key, token, expires_in):
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            blob = json.load(f)
    except (OSError, ValueError):
        blob = {}
    blob[key] = {"access_token": token, "expires_at": time.time() + int(expires_in)}
    # Create the file already private rather than writing it world-readable
    # and chmod'ing after - the gap between the two is a live bearer token on
    # disk at the default umask. On Windows this is cosmetic (ACLs, not mode
    # bits), so the cache still should not live on a shared machine.
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(CACHE_PATH, flags, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(blob, f)
    os.chmod(CACHE_PATH, stat.S_IRUSR | stat.S_IWUSR)  # 0600 - it's a bearer token


def _post_token(tenant, data):
    r = requests.post(f"{AUTHORITY}/{tenant}/oauth2/v2.0/token", data=data, timeout=30)
    if r.status_code != 200:
        raise AuthError(f"Token request failed ({r.status_code}): {r.text[:500]}")
    return r.json()


def _client_credentials():
    tenant = _env("INTUNE_TENANT_ID", required=True)
    client_id = _env("INTUNE_CLIENT_ID", required=True)
    secret = _env("INTUNE_CLIENT_SECRET")
    cert_thumb = _env("INTUNE_CERT_THUMBPRINT")

    if not secret and not cert_thumb:
        raise AuthError(
            "client_credentials needs INTUNE_CLIENT_SECRET, or certificate auth via "
            "INTUNE_CERT_THUMBPRINT + INTUNE_CERT_PATH. See references/auth-setup.md."
        )
    if cert_thumb:
        raise AuthError(
            "Certificate auth requires assembling a signed JWT assertion. Install msal "
            "(`pip install msal`) and use ConfidentialClientApplication with "
            "client_credential={'thumbprint':..., 'private_key':...} - see "
            "references/auth-setup.md, 'Certificate auth'."
        )

    tok = _post_token(tenant, {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": secret,
        "scope": SCOPE_APP,
    })
    return tok["access_token"], tok.get("expires_in", 3599), f"cc:{tenant}:{client_id}"


def _device_code(quiet=False):
    tenant = _env("INTUNE_TENANT_ID") or "organizations"
    client_id = _env("INTUNE_CLIENT_ID") or DEFAULT_PUBLIC_CLIENT

    r = requests.post(
        f"{AUTHORITY}/{tenant}/oauth2/v2.0/devicecode",
        data={"client_id": client_id, "scope": " ".join(DELEGATED_SCOPES)},
        timeout=30,
    )
    if r.status_code != 200:
        raise AuthError(f"Device code request failed ({r.status_code}): {r.text[:500]}")
    flow = r.json()

    # This must reach a human. Goes to stderr so stdout stays pipeable.
    print("\n" + flow["message"] + "\n", file=sys.stderr)

    interval = int(flow.get("interval", 5))
    deadline = time.time() + int(flow.get("expires_in", 900))
    while time.time() < deadline:
        time.sleep(interval)
        p = requests.post(
            f"{AUTHORITY}/{tenant}/oauth2/v2.0/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": client_id,
                "device_code": flow["device_code"],
            },
            timeout=30,
        )
        body = p.json()
        if p.status_code == 200:
            return body["access_token"], body.get("expires_in", 3599), f"dc:{tenant}:{client_id}"
        err = body.get("error")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            interval += 5
            continue
        raise AuthError(f"Device code auth failed: {err}: {body.get('error_description', '')[:300]}")
    raise AuthError("Device code flow timed out waiting for sign-in.")


def _find_az():
    """Locate the az launcher.

    On Windows az ships as az.cmd, and CreateProcess does not apply PATHEXT -
    so subprocess.run(["az", ...]) raises FileNotFoundError even when az is
    installed and on PATH. shutil.which does apply PATHEXT. Without this the
    error below blames PATH for a problem that is not PATH, and you go looking
    for an install that is already there.
    """
    for name in ("az", "az.cmd", "az.bat", "az.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _azure_cli():
    az = _find_az()
    if not az:
        raise AuthError(
            "azure_cli mode needs the `az` CLI. It was not found via PATH "
            "(including PATHEXT on Windows, where az is az.cmd). Install it, or "
            "use --mode client_credentials / device_code.")
    try:
        out = subprocess.run(
            [az, "account", "get-access-token", "--resource", "https://graph.microsoft.com", "-o", "json"],
            capture_output=True, text=True, timeout=60, check=False,
        )
    except OSError as exc:
        raise AuthError(f"Could not run {az}: {exc}") from exc
    if out.returncode != 0:
        raise AuthError(f"az get-access-token failed - run `az login` first.\n{out.stderr[:400]}")
    tok = json.loads(out.stdout)
    return tok["accessToken"], 3599, "azcli"


def get_token(mode=None, use_cache=True):
    """Return a Graph bearer token for the configured auth mode."""
    mode = mode or os.environ.get("INTUNE_AUTH_MODE") or "client_credentials"
    handlers = {
        "client_credentials": _client_credentials,
        "device_code": _device_code,
        "azure_cli": _azure_cli,
    }
    if mode not in handlers:
        raise AuthError(f"Unknown auth mode '{mode}'. Options: {', '.join(handlers)}")

    # Probe cache before doing work, using the same key the handler will produce.
    if use_cache:
        try:
            probe = {
                "client_credentials": lambda: f"cc:{_env('INTUNE_TENANT_ID')}:{_env('INTUNE_CLIENT_ID')}",
                "device_code": lambda: f"dc:{_env('INTUNE_TENANT_ID') or 'organizations'}:"
                                       f"{_env('INTUNE_CLIENT_ID') or DEFAULT_PUBLIC_CLIENT}",
                "azure_cli": lambda: "azcli",
            }[mode]()
            hit = _load_cache(probe)
            if hit:
                return hit["access_token"]
        except AuthError:
            pass  # missing env vars - let the handler raise the useful message

    token, expires_in, key = handlers[mode]()
    if use_cache:
        _save_cache(key, token, expires_in)
    return token


def decode_claims(token):
    """Decode the JWT payload. Inspection only - no signature verification."""
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def _check(mode):
    token = get_token(mode=mode)
    c = decode_claims(token)
    print(f"Tenant:    {c.get('tid')}")
    print(f"Identity:  {c.get('upn') or c.get('app_displayname') or c.get('appid')}")
    print(f"Type:      {'application (app-only)' if not c.get('upn') else 'delegated (user)'}")
    print(f"Expires:   {time.strftime('%H:%M:%S', time.localtime(c.get('exp', 0)))}")
    scopes = c.get("roles") or (c.get("scp", "").split() if c.get("scp") else [])
    print(f"Scopes:    {', '.join(sorted(scopes)) if scopes else '(none - this token can do nothing)'}")

    r = requests.get(
        "https://graph.microsoft.com/v1.0/deviceManagement/managedDevices?$top=1",
        headers={"Authorization": f"Bearer {token}"}, timeout=30,
    )
    if r.status_code == 200:
        print("Intune:    OK - managedDevices readable")
    elif r.status_code == 403:
        print("Intune:    403 - token is valid but lacks DeviceManagementManagedDevices.*")
        print("           App-only tokens need APPLICATION permissions, not delegated ones,")
        print("           plus admin consent. See references/auth-setup.md.")
    else:
        print(f"Intune:    {r.status_code} - {r.text[:200]}")
    return 0 if r.status_code == 200 else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Acquire/inspect a Graph token for Intune.")
    ap.add_argument("--mode", choices=["client_credentials", "device_code", "azure_cli"])
    ap.add_argument("--check", action="store_true", help="Print token identity + scopes and test Intune access")
    ap.add_argument("--print-token", action="store_true", help="Print raw token (avoid - it's a live credential)")
    a = ap.parse_args()
    try:
        if a.check:
            sys.exit(_check(a.mode))
        elif a.print_token:
            print(get_token(mode=a.mode))
        else:
            get_token(mode=a.mode)
            print("Token acquired and cached. Use --check to inspect it.", file=sys.stderr)
    except AuthError as e:
        print(f"Auth error: {e}", file=sys.stderr)
        sys.exit(1)
