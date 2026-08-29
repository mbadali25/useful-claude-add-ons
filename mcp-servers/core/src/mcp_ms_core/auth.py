"""Authentication for Microsoft Graph.

Two auth modes, matching the user-scope / admin-scope boundary described in
mcp-servers/README.md. Each is a separate class reading a separate, explicit
set of environment variable names passed in by the caller - a server built on
``DeviceCodeAuth`` has no code path into ``ClientCredentialAuth`` and vice
versa, so the delegated/app-only split is structural, not a convention.

- ``ClientCredentialAuth`` - app-only, tenant-wide (OAuth2 client_credentials
  grant). Used by every admin-scoped server (Intune, Graph-Admin, O365-Admin).
  Needs an app registration with application permissions and admin consent.
- ``DeviceCodeAuth`` - delegated, signed-in user (OAuth2 device-code flow).
  Used only by the user-scoped O365 server. Needs a public-client app
  registration; no client secret is ever read or required.

Credentials are read from environment variables at call time only - never
written to disk, never logged. The one thing that IS persisted is the
delegated token cache (refresh tokens, not the user's password), and only
when ``DeviceCodeAuth`` is used, to a file under the current user's profile.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import msal

from .errors import AuthConfigError

GRAPH_SCOPE_DEFAULT = "https://graph.microsoft.com/.default"


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise AuthConfigError(
            f"{name} is not set. See mcp-servers/README.md for the exact "
            "environment variables this server needs."
        )
    return value


class ClientCredentialAuth:
    """App-only auth via a confidential client (client secret or certificate).

    Certificate auth is used when ``cert_path_env`` is set and points at a
    PEM private key; otherwise ``secret_env`` (a client secret) is required.
    Prefer certificate auth for anything long-lived - a secret expires and
    is a bearer credential on disk either way, but a certificate is easier
    to rotate without touching the app registration's password list.
    """

    def __init__(
        self,
        *,
        tenant_env: str,
        client_id_env: str,
        secret_env: str,
        cert_path_env: str | None = None,
        cert_thumbprint_env: str | None = None,
    ) -> None:
        self.tenant_id = _require_env(tenant_env)
        self.client_id = _require_env(client_id_env)

        cert_path = os.environ.get(cert_path_env, "").strip() if cert_path_env else ""
        if cert_path:
            thumbprint = _require_env(cert_thumbprint_env) if cert_thumbprint_env else ""
            if not thumbprint:
                raise AuthConfigError(
                    f"{cert_path_env} is set but {cert_thumbprint_env} is not - "
                    "certificate auth needs both."
                )
            try:
                private_key = Path(cert_path).read_text(encoding="utf-8")
            except OSError as exc:
                raise AuthConfigError(f"Could not read {cert_path_env}={cert_path!r}: {exc}") from exc
            credential: str | dict[str, str] = {
                "private_key": private_key,
                "thumbprint": thumbprint,
            }
        else:
            credential = _require_env(secret_env)

        self._app = msal.ConfidentialClientApplication(
            client_id=self.client_id,
            client_credential=credential,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
        )

    def get_token(self, scope: str = GRAPH_SCOPE_DEFAULT) -> str:
        result = self._app.acquire_token_for_client(scopes=[scope])
        if "access_token" not in result:
            raise AuthConfigError(
                "App-only token acquisition failed: "
                f"{result.get('error')}: {result.get('error_description')}"
            )
        return result["access_token"]


def _default_cache_path(app_name: str) -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / app_name / "token-cache.json"


class DeviceCodeAuth:
    """Delegated auth via the device-code flow, for one signed-in user.

    Reaches only what that user can see - their own mailbox, calendar, and
    files - never tenant-wide data, because the token is issued with
    delegated scopes tied to the signed-in account, not application
    permissions.

    Tokens are cached under ``cache_path_env`` (default a per-app path under
    the platform's local cache/app-data directory) so a device-code prompt is
    needed once per machine, not once per Claude session. The cache holds
    refresh tokens, not the password; delete the file to force a fresh
    sign-in.
    """

    def __init__(
        self,
        *,
        tenant_env: str,
        client_id_env: str,
        cache_path_env: str,
        scopes: list[str],
        app_name: str,
    ) -> None:
        self.tenant_id = _require_env(tenant_env)
        self.client_id = _require_env(client_id_env)
        self._scopes = scopes
        cache_override = os.environ.get(cache_path_env, "").strip()
        self._cache_path = Path(cache_override) if cache_override else _default_cache_path(app_name)

        self._cache = msal.SerializableTokenCache()
        if self._cache_path.exists():
            self._cache.deserialize(self._cache_path.read_text(encoding="utf-8"))

        self._app = msal.PublicClientApplication(
            client_id=self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            token_cache=self._cache,
        )

    def _persist_cache(self) -> None:
        if not self._cache.has_state_changed:
            return
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(self._cache.serialize(), encoding="utf-8")
        try:
            os.chmod(self._cache_path, 0o600)
        except OSError:
            pass  # best-effort; platforms without POSIX permission bits (Windows) skip this

    def get_token(self) -> str:
        accounts = self._app.get_accounts()
        result = None
        if accounts:
            result = self._app.acquire_token_silent(self._scopes, account=accounts[0])
        if not result:
            flow = self._app.initiate_device_flow(scopes=self._scopes)
            if "user_code" not in flow:
                raise AuthConfigError(
                    f"Could not start the device-code flow: {flow.get('error_description', flow)}"
                )
            # stdio MCP servers use stdout for the JSON-RPC protocol - the
            # sign-in prompt MUST go to stderr or it corrupts the transport.
            print(flow["message"], file=sys.stderr)
            result = self._app.acquire_token_by_device_flow(flow)
        self._persist_cache()
        if "access_token" not in result:
            raise AuthConfigError(
                f"Delegated sign-in failed: {result.get('error')}: {result.get('error_description')}"
            )
        return result["access_token"]
