"""Shared Microsoft Graph auth + HTTP core for the mcp-servers/ MCP servers.

Every server in this workspace (mcp-intune, mcp-graph-admin, mcp-o365-user,
mcp-o365-admin) imports this package rather than re-implementing auth, paging,
retry, or error handling. See mcp-servers/README.md for the auth model and
the user-scope vs admin-scope boundary this package enforces structurally:
``ClientCredentialAuth`` and ``DeviceCodeAuth`` are separate classes reading
separate environment variables, so a server built on one cannot silently gain
the other's reach.
"""

from .auth import ClientCredentialAuth, DeviceCodeAuth
from .errors import AuthConfigError, GraphError
from .graph_client import GRAPH_BETA, GRAPH_V1, GraphClient
from .write_gate import gate, writes_enabled

__all__ = [
    "ClientCredentialAuth",
    "DeviceCodeAuth",
    "AuthConfigError",
    "GraphError",
    "GraphClient",
    "GRAPH_V1",
    "GRAPH_BETA",
    "gate",
    "writes_enabled",
]
