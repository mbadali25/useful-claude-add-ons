"""Fixtures: no network, no real tailscale, nothing outside tmp_path."""
import importlib
import json
import os
import sys
from pathlib import Path

import pytest

VPN_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(VPN_DIR))

FAKE = Path(__file__).resolve().parent / "fake_tailscale.py"
AUTH_KEY = "tskey-auth-kTEST123CNTRL-SuperSecretKeyMaterial0123456789"
CLIENT_SECRET = "tskey-client-kOAUTH-ClientSecretValue9876543210"
ACCESS_TOKEN = "access-token-value-that-must-not-leak"


@pytest.fixture
def ts(tmp_path, monkeypatch):
    for var in ("TS_AUTHKEY", "TS_AUTHKEY_FILE", "AI_CONNECT_BRIDGE_HOST", "AI_CONNECT_INSTALLER",
                "TS_OAUTH_CLIENT_ID", "TS_OAUTH_CLIENT_SECRET"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AI_CONNECT_TS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("AI_CONNECT_TSD_WAIT", "0")
    # No real install dir or stored OAuth client on this machine may answer
    monkeypatch.setenv("AI_CONNECT_TAILSCALE_DIRS", str(tmp_path / "no-tailscale"))
    monkeypatch.setenv("AI_CONNECT_OAUTH_FILE", str(tmp_path / "tailscale-oauth.json"))
    import tsadmin
    mod = importlib.reload(tsadmin)
    # A keyring on the machine running the tests must not supply credentials.
    monkeypatch.setitem(sys.modules, "keyring", None)
    return mod


class FakeTailscale:
    def __init__(self, root: Path):
        self.bin = root / "bin"
        self.bin.mkdir()
        self.state = root / "ts-state.json"
        self.log = root / "ts-log.jsonl"
        self.log.write_text("", encoding="utf-8")
        if os.name == "nt":
            (self.bin / "tailscale.cmd").write_text(
                f'@"{sys.executable}" "{FAKE}" %*\r\n', encoding="utf-8")
        else:
            path = self.bin / "tailscale"
            path.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n',
                            encoding="utf-8", newline="\n")
            path.chmod(0o755)
        self.set(backend="Stopped")

    def set(self, **state):
        self.state.write_text(json.dumps(state), encoding="utf-8")

    def calls(self):
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines() if line]

    def up_calls(self):
        return [c for c in self.calls() if "up" in c]


@pytest.fixture
def fake_ts(tmp_path, monkeypatch, ts):
    fake = FakeTailscale(tmp_path)
    monkeypatch.setenv("FAKE_TS_STATE", str(fake.state))
    monkeypatch.setenv("FAKE_TS_LOG", str(fake.log))
    monkeypatch.setenv("PATH", str(fake.bin) + os.pathsep + os.environ.get("PATH", ""))
    return fake


class FakeAPI:
    """Replaces tsadmin.http. Routes are (METHOD, path-suffix) -> (status, payload)."""

    def __init__(self):
        self.calls = []
        self.routes = {
            ("POST", "/oauth/token"): (200, {"access_token": ACCESS_TOKEN, "token_type": "Bearer"}),
            ("POST", "/tailnet/-/keys"): (200, {"id": "kTEST", "key": AUTH_KEY,
                                                 "expires": "2026-10-12T00:00:00Z"}),
            ("GET", "/tailnet/-/devices"): (200, {"devices": []}),
        }

    def __call__(self, method, url, *, token=None, form=None, body=None, timeout=20.0):
        self.calls.append({"method": method, "url": url, "token": token, "form": form, "body": body})
        for (m, suffix), resp in self.routes.items():
            if m == method and url.endswith(suffix):
                return resp
        if method == "DELETE" and "/device/" in url:
            return 200, {}
        return 404, {"message": "no route in FakeAPI"}

    def find(self, method, suffix):
        return [c for c in self.calls if c["method"] == method and c["url"].endswith(suffix)]


@pytest.fixture
def api(ts, monkeypatch):
    fake = FakeAPI()
    monkeypatch.setattr(ts, "http", fake)
    monkeypatch.setenv("TS_OAUTH_CLIENT_ID", "kOAUTHCLIENTID")
    monkeypatch.setenv("TS_OAUTH_CLIENT_SECRET", CLIENT_SECRET)
    return fake
