"""Builds the shared GraphClient for this server from MS_INTUNE_* env vars.

Separate env-var prefix from every other server in this workspace - see
mcp-servers/README.md's "structural, not a label" note on the user-scope vs
admin-scope split. A session only holding MS_INTUNE_* credentials cannot
reach Entra ID directory data, O365 mail, or SharePoint, because it never
constructs those servers' auth objects.
"""

from __future__ import annotations

import functools

from mcp_ms_core import ClientCredentialAuth, GraphClient

ENV_PREFIX = "MS_INTUNE"
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
