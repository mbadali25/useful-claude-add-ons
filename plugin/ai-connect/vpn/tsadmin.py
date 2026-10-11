#!/usr/bin/env python3
"""Tailscale self-join tooling for ai-connect: one core behind the .sh/.ps1 shims.

Subcommands:
  mint-key  ADMIN  create ONE single-use, ephemeral, pre-authorised, tagged auth key
  revoke    ADMIN  delete a joined node by name (revoking a key does not drop a node)
  vpn-up    AGENT  join the tailnet with a key, idempotently, and probe the Bridge
  vpn-down  AGENT  leave the tailnet (and stop a userspace tailscaled we started)

Exit codes (every subcommand):
  0  done / connected
  1  failed
  2  could not tell (a probe timed out or had nothing to probe)
  3  tailscale is not installed

Secrets (OAuth client secret, access token, auth key, peer token) are never
written to stdout/stderr by this script. Any text that came back from Tailscale
or from the tailscale CLI passes through redact() before it is printed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

EXIT_OK, EXIT_FAILED, EXIT_UNKNOWN, EXIT_NO_TAILSCALE = 0, 1, 2, 3

API_BASE = os.environ.get("TS_API_BASE", "https://api.tailscale.com/api/v2")
DEFAULT_TAG = "tag:ai-peer"
BRIDGE_PORT = 9999
SOCKS_PORT = 1055
KEYRING_SERVICE = "ai-connect-tailscale"
IS_WINDOWS = os.name == "nt"
PEER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,62}$")
SECRET_RE = re.compile(r"tskey-[A-Za-z0-9_-]+")

INSTALL_HINT = {
    "win32": "winget install --id Tailscale.Tailscale -e",
    "darwin": "brew install --cask tailscale",
    "linux": "curl -fsSL https://tailscale.com/install.sh | sh",
}


class Failure(Exception):
    """A refusal with a one-line reason and an exit code."""

    def __init__(self, message: str, code: int = EXIT_FAILED):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------- output


_SECRETS: set[str] = set()


def remember_secret(value: str | None) -> None:
    if value and len(value) >= 6:
        _SECRETS.add(value)


def redact(text: str) -> str:
    for secret in sorted(_SECRETS, key=len, reverse=True):
        text = text.replace(secret, "<redacted>")
    return SECRET_RE.sub("tskey-<redacted>", text)


def say(msg: str) -> None:
    print(redact(msg), flush=True)


def warn(msg: str) -> None:
    print(redact(msg), file=sys.stderr, flush=True)


# ---------------------------------------------------------------- admin: API


def http(method: str, url: str, *, token: str | None = None, form: dict | None = None,
         body: dict | None = None, timeout: float = 20.0) -> tuple[int, dict]:
    """One HTTP call. Returns (status, parsed JSON or {}). Tests replace this."""
    data, headers = None, {"Accept": "application/json"}
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = resp.status
    except urllib.error.HTTPError as err:
        raw, status = err.read(), err.code
    except (urllib.error.URLError, OSError) as err:
        raise Failure(f"could not reach {urllib.parse.urlsplit(url).netloc}: {err}") from None
    try:
        return status, json.loads(raw or b"{}")
    except ValueError:
        return status, {}


def api_error(what: str, status: int, payload: dict) -> Failure:
    message = str(payload.get("message") or payload.get("error") or "no message")
    return Failure(f"{what} failed: HTTP {status}: {message}")


def oauth_file() -> Path:
    """Where `deploy tailnet-setup` keeps the OAuth client when no credential store takes it."""
    return Path(os.environ.get("AI_CONNECT_OAUTH_FILE")
                or Path.home() / ".config" / "ai-connect" / "tailscale-oauth.json")


def stored_oauth_credentials(use_env: bool = True) -> tuple[str, str, str | None]:
    """(client id, secret, where from) out of the environment, the OS credential store, then the
    owner-only file; ("", "", None) when no source holds both. use_env=False asks only what is stored."""
    # A whole pair from one place: an ID from here and a secret from there is not a client
    cid = os.environ.get("TS_OAUTH_CLIENT_ID", "") if use_env else ""
    secret = os.environ.get("TS_OAUTH_CLIENT_SECRET", "") if use_env else ""
    source = "environment" if cid and secret else None
    if source is None:
        try:
            import keyring  # pylint: disable=import-error,import-outside-toplevel  # optional; the OS credential store
            cid = keyring.get_password(KEYRING_SERVICE, "oauth_client_id") or ""
            secret = keyring.get_password(KEYRING_SERVICE, "oauth_client_secret") or ""
            source = "credential store" if cid and secret else None
        except Exception:  # keyring absent or its backend broken: the other sources still count
            pass
    if source is None:
        try:
            saved = json.loads(oauth_file().read_text(encoding="utf-8"))
            cid = str(saved.get("oauth_client_id") or "")
            secret = str(saved.get("oauth_client_secret") or "")
            source = f"file {oauth_file()}" if cid and secret else None
        except (OSError, ValueError, AttributeError):
            pass
    if source is None:
        return "", "", None
    remember_secret(secret)
    return cid, secret, source


def oauth_credentials() -> tuple[str, str]:
    cid, secret, _source = stored_oauth_credentials()
    if not (cid and secret):
        raise Failure(
            "no Tailscale OAuth client: run `deploy tailnet-setup --apply`, or set TS_OAUTH_CLIENT_ID and "
            f"TS_OAUTH_CLIENT_SECRET, or store them with `keyring set {KEYRING_SERVICE} oauth_client_id` "
            "/ `oauth_client_secret`"
        )
    return cid, secret


def access_token() -> str:
    cid, secret = oauth_credentials()
    status, payload = http("POST", f"{API_BASE}/oauth/token", form={
        "client_id": cid, "client_secret": secret, "grant_type": "client_credentials"})
    token = payload.get("access_token") if status == 200 else None
    if not token:
        raise api_error("OAuth token exchange", status, payload)
    remember_secret(token)
    return token


def parse_expiry(text: str) -> int:
    m = re.fullmatch(r"\s*(\d+)\s*([smhd]?)\s*", text or "")
    if not m:
        raise Failure(f"--expiry '{text}' is not a duration like 1d, 12h, 30m or 3600")
    seconds = int(m.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)]
    if not 60 <= seconds <= 90 * 86400:
        raise Failure(f"--expiry must be between 60 seconds and 90 days, got {seconds}s")
    return seconds


def key_request_body(name: str, tag: str, expiry_seconds: int) -> dict:
    # Tailscale allows at most 50 alphanumerics, hyphens and spaces here.
    description = re.sub(r"[^A-Za-z0-9 -]", "-", f"ai-connect peer {name}")[:50]
    return {
        "capabilities": {"devices": {"create": {
            "reusable": False, "ephemeral": True, "preauthorized": True, "tags": [tag]}}},
        "expirySeconds": expiry_seconds,
        "description": description,
    }


def write_owner_only(path: Path, text: str) -> None:
    """Write via temp file + os.replace, readable by the current user only."""
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tskey-")  # mkstemp is 0600 on POSIX
    try:
        if IS_WINDOWS:
            # Fails closed: a secret is never written where others may read it
            user = os.environ.get("USERNAME", "")
            icacls = shutil.which("icacls")
            res = subprocess.run([icacls, tmp, "/inheritance:r", "/grant:r", f"{user}:F"],
                                 capture_output=True, text=True, check=False) if user and icacls else None
            if res is None or res.returncode != 0:
                why = ("USERNAME is not set" if not user else "icacls was not found" if not icacls
                       else f"icacls exited {res.returncode}")
                raise Failure(f"could not restrict {path} to the current user ({why}); nothing was "
                              "written. The minted key was not shown and expires unused; retry with "
                              "--out on a local NTFS path, or without --out to print it")
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        fd = -1
        os.replace(tmp, path)
    finally:
        if fd != -1:
            os.close(fd)
        if os.path.exists(tmp):
            os.unlink(tmp)


def find_installer(explicit: str | None) -> Path | None:
    here = Path(__file__).resolve().parent
    candidates = [explicit, os.environ.get("AI_CONNECT_INSTALLER"), here.parent / "installer.py"]
    for cand in candidates:
        if cand and Path(cand).is_file():
            return Path(cand)
    return None


def cmd_mint_key(args) -> int:
    if not PEER_NAME_RE.match(args.name):
        raise Failure(f"peer name '{args.name}' must be 1-63 letters, digits or hyphens")
    expiry = parse_expiry(args.expiry)
    token = access_token()
    status, payload = http("POST", f"{API_BASE}/tailnet/-/keys", token=token,
                           body=key_request_body(args.name, args.tag, expiry))
    key = payload.get("key") if status == 200 else None
    if not key:
        raise api_error("auth key creation", status, payload)
    remember_secret(key)
    expires = payload.get("expires", f"in {expiry}s")
    if args.out:
        write_owner_only(Path(args.out), key + "\n")
        say(f"Auth key for peer '{args.name}' written to {Path(args.out).resolve()} "
            f"(single use, ephemeral, {args.tag}, expires {expires}).")
        say(f"Hand that file to the peer; it runs: vpn-up --auth-key-file <file> --hostname {args.name}")
    else:
        # The one deliberate secret on stdout: the admin asked for it, shown once.
        print(f"Auth key for peer '{args.name}' (single use, ephemeral, {args.tag}, "
              f"expires {expires}) -- shown once:")
        print(f"  {key}")
        say(f"The peer runs: TS_AUTHKEY=<key> vpn-up --hostname {args.name}")
    if args.peer_token:
        provision_peer_token(args.name, args.installer)
    return EXIT_OK


def installer_python(installer: Path) -> str:
    """The interpreter for installer.py: the venv install.sh / install.ps1 built beside it.

    installer.py imports PyYAML and the plugin's own modules, which the bare system
    Python running this stdlib-only script usually lacks. With no venv there (a dev
    checkout), fall back to this interpreter.
    """
    for parts in (("venv", "Scripts", "python.exe"), ("venv", "bin", "python")):
        cand = installer.parent.joinpath(*parts)
        if cand.is_file():
            return str(cand)
    return sys.executable


def provision_peer_token(name: str, installer: str | None) -> None:
    path = find_installer(installer)
    if path is None:
        say("ai-connect peer token: skipped (installer.py not found; set AI_CONNECT_INSTALLER "
            f"or run `installer.py add-peer {name}` on the Bridge machine yourself).")
        return
    python = installer_python(path)
    say(f"ai-connect peer token: running {path.name} add-peer {name} (it prints the token once)")
    # Inherit stdio: the token goes to the admin's terminal only, never through this process.
    res = subprocess.run([python, str(path), "add-peer", name], check=False)
    if res.returncode != 0:
        warn(f"ai-connect peer token: installer exited {res.returncode}; the auth key above is still valid")


def cmd_revoke(args) -> int:
    token = access_token()
    status, payload = http("GET", f"{API_BASE}/tailnet/-/devices", token=token)
    if status != 200:
        raise api_error("device list", status, payload)
    want = args.name.lower()
    matches = []
    for dev in payload.get("devices", []):
        names = {str(dev.get("hostname", "")).lower(), str(dev.get("name", "")).lower(),
                 str(dev.get("name", "")).split(".", maxsplit=1)[0].lower()}
        if want in names and (args.any_tag or args.tag in (dev.get("tags") or [])):
            matches.append(dev)
    if not matches:
        raise Failure(f"no node named '{args.name}'"
                      + ("" if args.any_tag else f" tagged {args.tag} (pass --any-tag to widen)"))
    if len(matches) > 1 and not args.all:
        ids = ", ".join(str(d.get("nodeId") or d.get("id")) for d in matches)
        raise Failure(f"{len(matches)} nodes match '{args.name}' ({ids}); pass --all to delete every one")
    for dev in matches:
        dev_id = dev.get("nodeId") or dev.get("id")
        status, payload = http("DELETE", f"{API_BASE}/device/{urllib.parse.quote(str(dev_id))}",
                               token=token)
        if status not in (200, 204):
            raise api_error(f"delete node {dev_id}", status, payload)
        say(f"Deleted node {dev.get('name') or dev.get('hostname')} ({dev_id}); it is off the tailnet now.")
    return EXIT_OK


# ---------------------------------------------------------------- agent: CLI


def state_dir() -> Path:
    return Path(os.environ.get("AI_CONNECT_TS_STATE_DIR")
                or Path.home() / ".config" / "ai-connect" / "tailscale-userspace")


def userspace_socket() -> Path:
    return state_dir() / "tailscaled.sock"


def tailscale_dirs() -> list[str]:
    """Where a fresh install puts the CLI before a new shell has it on PATH."""
    override = os.environ.get("AI_CONNECT_TAILSCALE_DIRS")
    if override is not None:
        return [d for d in override.split(os.pathsep) if d]
    if IS_WINDOWS:
        return [str(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tailscale")]
    return ["/usr/bin", "/usr/sbin", "/usr/local/bin", "/opt/homebrew/bin",
            "/Applications/Tailscale.app/Contents/MacOS"]


def tailscale_bin() -> str:
    found = shutil.which("tailscale") or next(
        (hit for d in tailscale_dirs() for hit in [shutil.which("tailscale", path=d)] if hit), None)
    if not found:
        hint = INSTALL_HINT.get(sys.platform, INSTALL_HINT["linux"])
        raise Failure(f"tailscale is not installed. Install it: {hint}", EXIT_NO_TAILSCALE)
    return found


def run_ts(ts: str, args: list[str], *, userspace: bool = False, timeout: float = 60.0):
    argv = [ts] + ([f"--socket={userspace_socket()}"] if userspace else []) + args
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argv, 124, "", f"tailscale {args[0]} timed out")


def backend_state(ts: str, userspace: bool) -> str | None:
    """'Running', 'Stopped', 'NeedsLogin', ... or None when tailscaled could not be asked."""
    res = run_ts(ts, ["status", "--json"], userspace=userspace, timeout=15)
    try:
        return json.loads(res.stdout or "{}").get("BackendState") or None
    except ValueError:
        return None


def probe_tcp(host: str, port: int, timeout: float = 5.0, socks_port: int | None = None) -> str:
    """'ok', 'refused' (reached, nothing listening) or 'unknown' (timeout, DNS, anything else)."""
    try:
        if socks_port is None:
            with socket.create_connection((host, port), timeout=timeout):
                return "ok"
        with socket.create_connection(("127.0.0.1", socks_port), timeout=timeout) as s:
            s.settimeout(timeout)
            s.sendall(b"\x05\x01\x00")
            if s.recv(2) != b"\x05\x00":
                return "unknown"
            h = host.encode()
            s.sendall(b"\x05\x01\x00\x03" + bytes([len(h)]) + h + port.to_bytes(2, "big"))
            reply = s.recv(10)
            if len(reply) >= 2 and reply[1] == 0:
                return "ok"
            return "refused" if len(reply) >= 2 and reply[1] == 5 else "unknown"
    except ConnectionRefusedError:
        return "refused"
    except OSError:
        return "unknown"


def bridge_verdict(bridge: str | None, userspace: bool) -> tuple[int, str]:
    if not bridge:
        return EXIT_UNKNOWN, ("tailnet is up, but no Bridge host given (--bridge / AI_CONNECT_BRIDGE_HOST), "
                              "so reachability is unknown")
    result = probe_tcp(bridge, BRIDGE_PORT, socks_port=SOCKS_PORT if userspace else None)
    if result == "ok":
        return EXIT_OK, f"Bridge {bridge}:{BRIDGE_PORT} reachable"
    if result == "refused":
        return EXIT_FAILED, (f"tailnet is up but {bridge}:{BRIDGE_PORT} refused the connection "
                             "(Bridge not listening?)")
    return EXIT_UNKNOWN, (f"tailnet is up but {bridge}:{BRIDGE_PORT} did not answer "
                          "(timeout or name lookup failed); could not tell")


def read_key(args) -> tuple[str, Path | None]:
    key_file = args.auth_key_file or os.environ.get("TS_AUTHKEY_FILE")
    if key_file:
        path = Path(key_file)
        try:
            lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()]
        except OSError as err:
            raise Failure(f"cannot read key file {path}: {err.strerror}") from None
        key = next((ln for ln in lines if ln), "")
        if not key:
            raise Failure(f"key file {path} is empty")
        remember_secret(key)
        return key, path
    key = os.environ.get("TS_AUTHKEY", "").strip()
    if not key:
        raise Failure("not connected and no auth key: set TS_AUTHKEY or pass --auth-key-file "
                      "(ask the admin to run mint-key)")
    remember_secret(key)
    return key, None


def userspace_hint() -> str:
    proxy = f"socks5h://localhost:{SOCKS_PORT}"
    return (f"Userspace mode: no tun device, so reach the Bridge through the SOCKS5 proxy {proxy} "
            f"(e.g. ALL_PROXY={proxy}, or the ai-connect client's proxy setting).")


def start_userspace_tailscaled() -> None:
    daemon = shutil.which("tailscaled")
    if not daemon:
        raise Failure("userspace fallback needs the tailscaled binary on PATH, and it is not there")
    sdir = state_dir()
    sdir.mkdir(parents=True, exist_ok=True)
    # Both outlive this function on purpose: the log is handed to the detached daemon.
    log = open(sdir / "tailscaled.log", "ab")  # noqa: SIM115  # pylint: disable=consider-using-with
    flags = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if IS_WINDOWS else {"start_new_session": True}
    proc = subprocess.Popen(  # pylint: disable=consider-using-with
        [daemon, "--tun=userspace-networking", f"--socks5-server=localhost:{SOCKS_PORT}",
         f"--state={sdir / 'tailscaled.state'}", f"--socket={userspace_socket()}"],
        stdout=log, stderr=log, stdin=subprocess.DEVNULL, **flags)
    (sdir / "tailscaled.pid").write_text(f"{proc.pid}\n", encoding="utf-8")
    time.sleep(float(os.environ.get("AI_CONNECT_TSD_WAIT", "2")))


def looks_like_no_tun(text: str) -> bool:
    return bool(re.search(r"permission denied|access is denied|operation not permitted|"
                          r"/dev/net/tun|wintun|failed to connect to local tailscale|"
                          r"is tailscaled running", text, re.I))


def tailscale_up(ts: str, key: str, args, userspace: bool):
    # MagicDNS stays off unless asked for: it rewrites the resolver, which collides with a VPN client's DNS hook
    up = ["up", f"--auth-key={key}", f"--advertise-tags={args.tag}",
          f"--accept-dns={'true' if getattr(args, 'accept_dns', False) else 'false'}"]
    if args.hostname:
        up.append(f"--hostname={args.hostname}")
    if IS_WINDOWS and not userspace:
        up.append("--unattended")
    return run_ts(ts, up, userspace=userspace, timeout=120)


def cmd_vpn_up(args) -> int:
    ts = tailscale_bin()
    bridge = args.bridge or os.environ.get("AI_CONNECT_BRIDGE_HOST")
    userspace = args.userspace or userspace_socket().exists()

    if backend_state(ts, userspace) == "Running":
        code, why = bridge_verdict(bridge, userspace)
        say(("already connected: " if code == EXIT_OK else "") + why)
        if userspace:
            say(userspace_hint())
        return code

    key, key_path = read_key(args)
    if args.userspace:
        start_userspace_tailscaled()
    res = tailscale_up(ts, key, args, userspace)
    if res.returncode != 0 and not userspace and looks_like_no_tun(res.stderr + res.stdout):
        warn("tailscale up could not use a tun device here: " + (res.stderr or res.stdout).strip())
        warn("falling back to userspace networking")
        userspace = True
        start_userspace_tailscaled()
        res = tailscale_up(ts, key, args, userspace)
    if res.returncode != 0:
        kept = f"; key file {key_path} kept" if key_path else ""
        raise Failure(f"tailscale up failed (exit {res.returncode}): "
                      f"{(res.stderr or res.stdout).strip() or 'no output'}{kept}")

    if key_path is not None:
        try:
            key_path.unlink()
            say(f"used key file {key_path} deleted")
        except OSError as err:
            warn(f"warning: could not delete used key file {key_path}: {err.strerror}")

    state = backend_state(ts, userspace)
    if state != "Running":
        say(f"tailscale up returned 0 but the backend reports {state or 'nothing'}; could not tell")
        return EXIT_UNKNOWN
    code, why = bridge_verdict(bridge, userspace)
    say(("connected: " if code == EXIT_OK else "") + why)
    if userspace:
        say(userspace_hint())
    return code


def cmd_vpn_down(args) -> int:
    ts = tailscale_bin()
    userspace = userspace_socket().exists()
    res = run_ts(ts, ["logout" if args.logout else "down"], userspace=userspace)
    if res.returncode != 0:
        raise Failure(f"tailscale {'logout' if args.logout else 'down'} failed (exit "
                      f"{res.returncode}): {(res.stderr or res.stdout).strip() or 'no output'}")
    pid_file = state_dir() / "tailscaled.pid"
    if userspace and pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            taskkill = shutil.which("taskkill") if IS_WINDOWS else None
            if taskkill:
                subprocess.run([taskkill, "/PID", str(pid), "/T", "/F"], capture_output=True, check=False)
            else:
                # POSIX; on Windows without taskkill, os.kill terminates the process (not its tree)
                os.kill(pid, 15)
        except (ValueError, OSError) as err:
            warn(f"warning: could not stop userspace tailscaled: {err}")
        pid_file.unlink(missing_ok=True)
        userspace_socket().unlink(missing_ok=True)
    say("disconnected" + (" and logged out (an ephemeral node is removed)" if args.logout else ""))
    return EXIT_OK


# ---------------------------------------------------------------- entry


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tsadmin", description=__doc__.split("\n\n", maxsplit=1)[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("mint-key", help="ADMIN: create one single-use auth key for a peer")
    m.add_argument("--name", required=True, help="peer name (becomes its tailnet hostname)")
    m.add_argument("--expiry", default="1d", help="key lifetime: 1d (default), 12h, 30m, 3600")
    m.add_argument("--tag", default=DEFAULT_TAG)
    m.add_argument("--out", help="write the key to this file (owner-only) instead of printing it")
    m.add_argument("--peer-token", action="store_true",
                   help="also run ai-connect's `installer.py add-peer <name>` if it can be found")
    m.add_argument("--installer", help="path to ai-connect's installer.py")
    m.set_defaults(func=cmd_mint_key)

    r = sub.add_parser("revoke", help="ADMIN: delete a node by name")
    r.add_argument("--name", required=True)
    r.add_argument("--tag", default=DEFAULT_TAG, help="only nodes carrying this tag (default tag:ai-peer)")
    r.add_argument("--any-tag", action="store_true", help="match nodes whatever their tags")
    r.add_argument("--all", action="store_true", help="delete every match when several share the name")
    r.set_defaults(func=cmd_revoke)

    u = sub.add_parser("vpn-up", help="AGENT: join the tailnet and probe the Bridge")
    u.add_argument("--auth-key-file", help="file holding the key (deleted after a successful join)")
    u.add_argument("--bridge", help="Bridge host on the tailnet (or AI_CONNECT_BRIDGE_HOST)")
    u.add_argument("--hostname", help="this node's tailnet name (the peer name from mint-key)")
    u.add_argument("--tag", default=DEFAULT_TAG)
    u.add_argument("--accept-dns", action="store_true",
                   help="let Tailscale manage this machine's DNS (MagicDNS); off by default")
    u.add_argument("--userspace", action="store_true",
                   help="no admin rights / no tun: run tailscaled in userspace with a SOCKS5 proxy")
    u.set_defaults(func=cmd_vpn_up)

    d = sub.add_parser("vpn-down", help="AGENT: leave the tailnet")
    d.add_argument("--logout", action="store_true", help="log out too, removing the ephemeral node")
    d.set_defaults(func=cmd_vpn_down)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except Failure as err:
        warn(f"{args.cmd}: {err}")
        return err.code
    except Exception as err:  # never let a traceback carry a secret to the terminal
        warn(f"{args.cmd}: unexpected {type(err).__name__}: {err}")
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
