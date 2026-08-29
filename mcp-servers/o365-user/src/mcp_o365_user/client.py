"""Builds the shared GraphClient for this server from MS_O365_USER_* env vars.

Delegated, not app-only - the one deliberate structural difference from the
other three servers in this workspace. DeviceCodeAuth never reads a client
secret, so this server cannot be pointed at tenant-wide data even by
misconfiguration: the token it acquires is scoped to whichever user ran the
device-code sign-in, and Graph enforces that server-side regardless of what
this code asks for.
"""

from __future__ import annotations

import functools

from mcp_ms_core import DeviceCodeAuth, GraphClient

ENV_PREFIX = "MS_O365_USER"
ALLOW_WRITES_ENV = f"{ENV_PREFIX}_ALLOW_WRITES"

# Delegated scopes only - no *.ReadWrite.All / tenant-wide permission belongs
# on this server. Add a scope here only when a tool needs it.
SCOPES = [
    "User.Read",
    "Mail.Read",
    "Mail.Send",
    "Calendars.ReadWrite",
    "Files.Read.All",
]


def build_auth() -> DeviceCodeAuth:
    return DeviceCodeAuth(
        tenant_env=f"{ENV_PREFIX}_TENANT_ID",
        client_id_env=f"{ENV_PREFIX}_CLIENT_ID",
        cache_path_env=f"{ENV_PREFIX}_TOKEN_CACHE_PATH",
        scopes=SCOPES,
        app_name="mcp-o365-user",
    )


@functools.lru_cache(maxsize=1)
def get_client() -> GraphClient:
    return GraphClient(build_auth().get_token)
