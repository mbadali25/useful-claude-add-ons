"""MCP tool definitions for Entra ID (Azure AD) directory administration.

This is the "Azure gap-fill" server: the official @azure/mcp server covers
the ARM control plane (management.azure.com) - VMs, storage, AKS, Key Vault,
and so on - but nothing under graph.microsoft.com, which is where Entra ID
identity data (users, groups, app registrations, directory roles,
conditional access) actually lives. See mcp-servers/README.md for the full
reasoning. Every tool here is read-only except the four at the bottom, gated
by mcp_ms_core.write_gate.gate.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from mcp_ms_core import GRAPH_BETA, gate

from .client import ALLOW_WRITES_ENV, get_client

mcp = FastMCP("mcp-graph-admin")

_USER_LIST_FIELDS = "id,displayName,userPrincipalName,mail,accountEnabled,jobTitle,department,createdDateTime"


@mcp.tool()
def graph_admin_list_users(filter: str | None = None, top: int = 25) -> dict:
    """List directory users. ``filter`` is a raw OData $filter expression,
    e.g. "accountEnabled eq false" or "startswith(displayName,'A')"."""
    params: dict[str, str | int] = {"$select": _USER_LIST_FIELDS, "$top": top}
    if filter:
        params["$filter"] = filter
    items = get_client().get_all("users", params=params, limit=top)
    return {"count": len(items), "items": items}


@mcp.tool()
def graph_admin_get_user(user_id: str) -> dict:
    """Get one user by id or userPrincipalName, with the full property set."""
    return get_client().get(f"users/{user_id}")


@mcp.tool()
def graph_admin_list_groups(filter: str | None = None, top: int = 25) -> dict:
    """List directory groups. ``filter`` is a raw OData $filter expression."""
    params: dict[str, str | int] = {"$top": top}
    if filter:
        params["$filter"] = filter
    items = get_client().get_all("groups", params=params, limit=top)
    return {"count": len(items), "items": items}


@mcp.tool()
def graph_admin_list_group_members(group_id: str, top: int = 50) -> dict:
    """List the direct members of one group."""
    items = get_client().get_all(f"groups/{group_id}/members", params={"$top": top}, limit=top)
    return {"count": len(items), "items": items}


@mcp.tool()
def graph_admin_list_service_principals(filter: str | None = None, top: int = 25) -> dict:
    """List service principals (enterprise apps) in the tenant."""
    params: dict[str, str | int] = {"$top": top}
    if filter:
        params["$filter"] = filter
    items = get_client().get_all("servicePrincipals", params=params, limit=top)
    return {"count": len(items), "items": items}


@mcp.tool()
def graph_admin_list_app_registrations(filter: str | None = None, top: int = 25) -> dict:
    """List app registrations owned by this tenant."""
    params: dict[str, str | int] = {"$top": top}
    if filter:
        params["$filter"] = filter
    items = get_client().get_all("applications", params=params, limit=top)
    return {"count": len(items), "items": items}


@mcp.tool()
def graph_admin_list_directory_roles() -> dict:
    """List directory roles that are currently activated in this tenant
    (Global Administrator, User Administrator, ...)."""
    items = get_client().get_all("directoryRoles")
    return {"count": len(items), "items": items}


@mcp.tool()
def graph_admin_list_directory_role_members(role_id: str) -> dict:
    """List the members holding one activated directory role."""
    items = get_client().get_all(f"directoryRoles/{role_id}/members")
    return {"count": len(items), "items": items}


@mcp.tool()
def graph_admin_list_conditional_access_policies() -> dict:
    """List conditional access policies. Uses the beta endpoint for the
    fields Microsoft has not GA'd into v1.0 yet - beta can change without
    notice, so treat this as informational rather than automation-safe."""
    client = get_client()
    items = client.get_all(f"{GRAPH_BETA}/identity/conditionalAccess/policies")
    return {"count": len(items), "items": items}


def _group_membership_action(group_id: str, user_id: str, action: str, confirm: bool) -> dict:
    target = f"group:{group_id} user:{user_id}"
    blocked = gate(ALLOW_WRITES_ENV, confirm=confirm, action=action, targets=[target])
    if blocked is not None:
        return blocked
    client = get_client()
    if action == "add_group_member":
        client.post(
            f"groups/{group_id}/members/$ref",
            json_body={"@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{user_id}"},
        )
    else:
        client.delete(f"groups/{group_id}/members/{user_id}/$ref")
    return {"wouldExecute": True, "executed": True, "action": action, "target": target}


@mcp.tool()
def graph_admin_add_group_member(group_id: str, user_id: str, confirm: bool = False) -> dict:
    """Add a user to a group. Dry-run unless confirm=true AND
    MS_GRAPH_ADMIN_ALLOW_WRITES=1 is set on the server."""
    return _group_membership_action(group_id, user_id, "add_group_member", confirm)


@mcp.tool()
def graph_admin_remove_group_member(group_id: str, user_id: str, confirm: bool = False) -> dict:
    """Remove a user from a group. Dry-run unless confirm=true AND
    MS_GRAPH_ADMIN_ALLOW_WRITES=1 is set on the server."""
    return _group_membership_action(group_id, user_id, "remove_group_member", confirm)


@mcp.tool()
def graph_admin_disable_user(user_id: str, confirm: bool = False) -> dict:
    """Disable a user's account (accountEnabled=false), blocking sign-in.
    Reversible via graph_admin's own PATCH, but treated as a gated write
    since it immediately locks someone out. Dry-run unless confirm=true AND
    MS_GRAPH_ADMIN_ALLOW_WRITES=1 is set on the server."""
    blocked = gate(ALLOW_WRITES_ENV, confirm=confirm, action="disable_user", targets=[user_id])
    if blocked is not None:
        return blocked
    get_client().patch(f"users/{user_id}", json_body={"accountEnabled": False})
    return {"wouldExecute": True, "executed": True, "action": "disable_user", "userId": user_id}


@mcp.tool()
def graph_admin_delete_user(user_id: str, confirm: bool = False) -> dict:
    """Delete a user from the directory. Irreversible after the tenant's
    soft-delete retention window expires. Dry-run unless confirm=true AND
    MS_GRAPH_ADMIN_ALLOW_WRITES=1 is set on the server."""
    blocked = gate(ALLOW_WRITES_ENV, confirm=confirm, action="delete_user", targets=[user_id])
    if blocked is not None:
        return blocked
    get_client().delete(f"users/{user_id}")
    return {"wouldExecute": True, "executed": True, "action": "delete_user", "userId": user_id}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
