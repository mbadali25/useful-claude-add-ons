"""Builds the shared GraphClient for this server from MS_O365_ADMIN_* env vars.

Separate env-var prefix from every other server in this workspace - see
mcp-servers/README.md's "structural, not a label" note on the user-scope vs
admin-scope split. This is the highest-blast-radius server in the workspace:
app-only credentials with tenant-wide Mail/Sites/Teams/licensing reach. Grant
its app registration only the permissions the tools below actually use.
"""

from __future__ import annotations

import functools

from mcp_ms_core import ClientCredentialAuth, GraphClient

ENV_PREFIX = "MS_O365_ADMIN"
ALLOW_WRITES_ENV = f"{ENV_PREFIX}_ALLOW_WRITES"


def build_auth() -> ClientCredentialAuth:
    return ClientCredentialAuth(
        tenant_env=f"{ENV_PREFIX}_TENANT_ID",
        client_id_env=f"{ENV_PREFIX}_CLIENT_ID",
        secret_env=f"{ENV_PREFIX}_CLIENT_SECRET",
        cert_path_env=f"{ENV_PREFIX}_CLIENT_CERT_PATH",
        cert_thumbprint_env=f"{ENV_PREFIX}_CLIENT_CERT_THUMBPRINT",
    )


@functools.lru_cache(maxsize=1)
def get_client() -> GraphClient:
    return GraphClient(build_auth().get_token)
