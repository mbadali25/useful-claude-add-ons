from __future__ import annotations

import pytest

import mcp_ms_core.auth as auth_module
from mcp_ms_core.auth import ClientCredentialAuth, DeviceCodeAuth
from mcp_ms_core.errors import AuthConfigError

TENANT_ENV = "TEST_TENANT_ID"
CLIENT_ENV = "TEST_CLIENT_ID"
SECRET_ENV = "TEST_CLIENT_SECRET"
CACHE_ENV = "TEST_TOKEN_CACHE_PATH"


class _FakeConfidentialApp:
    """Stands in for msal.ConfidentialClientApplication - real msal always
    does a network tenant-discovery call in __init__, which tests must not
    depend on."""

    def __init__(self, *args, **kwargs):
        self.acquire_token_for_client_result: dict = {"access_token": "app-only-token"}

    def acquire_token_for_client(self, scopes):
        return self.acquire_token_for_client_result


class _FakePublicApp:
    """Stands in for msal.PublicClientApplication, same reasoning."""

    def __init__(self, *args, **kwargs):
        self.accounts: list = []
        self.silent_result: dict | None = None
        self.device_flow: dict = {"user_code": "ABC-123", "message": "Go to https://microsoft.com/devicelogin"}
        self.device_flow_result: dict = {"access_token": "device-flow-token"}

    def get_accounts(self):
        return self.accounts

    def acquire_token_silent(self, scopes, account):
        return self.silent_result

    def initiate_device_flow(self, scopes):
        return self.device_flow

    def acquire_token_by_device_flow(self, flow):
        return self.device_flow_result


@pytest.fixture
def fake_confidential_app(monkeypatch):
    monkeypatch.setattr(auth_module.msal, "ConfidentialClientApplication", _FakeConfidentialApp)


@pytest.fixture
def fake_public_app(monkeypatch):
    monkeypatch.setattr(auth_module.msal, "PublicClientApplication", _FakePublicApp)


def _set_client_credential_env(monkeypatch):
    monkeypatch.setenv(TENANT_ENV, "tenant-123")
    monkeypatch.setenv(CLIENT_ENV, "client-abc")
    monkeypatch.setenv(SECRET_ENV, "super-secret")


def test_client_credential_auth_requires_tenant(monkeypatch):
    monkeypatch.delenv(TENANT_ENV, raising=False)
    monkeypatch.setenv(CLIENT_ENV, "client-abc")
    monkeypatch.setenv(SECRET_ENV, "super-secret")
    with pytest.raises(AuthConfigError, match=TENANT_ENV):
        ClientCredentialAuth(tenant_env=TENANT_ENV, client_id_env=CLIENT_ENV, secret_env=SECRET_ENV)


def test_client_credential_auth_requires_secret_when_no_cert(monkeypatch):
    monkeypatch.setenv(TENANT_ENV, "tenant-123")
    monkeypatch.setenv(CLIENT_ENV, "client-abc")
    monkeypatch.delenv(SECRET_ENV, raising=False)
    with pytest.raises(AuthConfigError, match=SECRET_ENV):
        ClientCredentialAuth(tenant_env=TENANT_ENV, client_id_env=CLIENT_ENV, secret_env=SECRET_ENV)


def test_client_credential_auth_get_token_uses_msal(monkeypatch, fake_confidential_app):
    _set_client_credential_env(monkeypatch)
    auth = ClientCredentialAuth(tenant_env=TENANT_ENV, client_id_env=CLIENT_ENV, secret_env=SECRET_ENV)
    assert auth.get_token() == "app-only-token"


def test_client_credential_auth_raises_on_msal_error(monkeypatch, fake_confidential_app):
    _set_client_credential_env(monkeypatch)
    auth = ClientCredentialAuth(tenant_env=TENANT_ENV, client_id_env=CLIENT_ENV, secret_env=SECRET_ENV)
    auth._app.acquire_token_for_client_result = {"error": "invalid_client", "error_description": "bad secret"}
    with pytest.raises(AuthConfigError, match="invalid_client"):
        auth.get_token()


def test_device_code_auth_requires_client_id(monkeypatch, tmp_path, fake_public_app):
    monkeypatch.setenv(TENANT_ENV, "tenant-123")
    monkeypatch.delenv(CLIENT_ENV, raising=False)
    monkeypatch.setenv(CACHE_ENV, str(tmp_path / "cache.json"))
    with pytest.raises(AuthConfigError, match=CLIENT_ENV):
        DeviceCodeAuth(
            tenant_env=TENANT_ENV,
            client_id_env=CLIENT_ENV,
            cache_path_env=CACHE_ENV,
            scopes=["Mail.Read"],
            app_name="mcp-o365-user-test",
        )


def test_device_code_auth_uses_silent_token_when_account_cached(monkeypatch, tmp_path, fake_public_app):
    monkeypatch.setenv(TENANT_ENV, "tenant-123")
    monkeypatch.setenv(CLIENT_ENV, "client-abc")
    monkeypatch.setenv(CACHE_ENV, str(tmp_path / "cache.json"))
    auth = DeviceCodeAuth(
        tenant_env=TENANT_ENV,
        client_id_env=CLIENT_ENV,
        cache_path_env=CACHE_ENV,
        scopes=["Mail.Read"],
        app_name="mcp-o365-user-test",
    )
    auth._app.accounts = [{"username": "user@example.com"}]
    auth._app.silent_result = {"access_token": "cached-token"}

    def _fail_device_flow(scopes):
        raise AssertionError("device flow should not start when a silent token is available")

    auth._app.initiate_device_flow = _fail_device_flow

    assert auth.get_token() == "cached-token"


def test_device_code_auth_falls_back_to_device_flow(monkeypatch, tmp_path, capsys, fake_public_app):
    monkeypatch.setenv(TENANT_ENV, "tenant-123")
    monkeypatch.setenv(CLIENT_ENV, "client-abc")
    monkeypatch.setenv(CACHE_ENV, str(tmp_path / "cache.json"))
    auth = DeviceCodeAuth(
        tenant_env=TENANT_ENV,
        client_id_env=CLIENT_ENV,
        cache_path_env=CACHE_ENV,
        scopes=["Mail.Read"],
        app_name="mcp-o365-user-test",
    )
    auth._app.accounts = []

    token = auth.get_token()

    assert token == "device-flow-token"
    captured = capsys.readouterr()
    # The device-code prompt MUST go to stderr, never stdout - stdout carries
    # the MCP JSON-RPC stream and printing there would corrupt the transport.
    assert captured.out == ""
    assert "devicelogin" in captured.err
