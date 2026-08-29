"""MCP tool definitions for tenant-wide Office 365 administration: SharePoint
sites, Teams, licenses, and any user's mailbox. This is deliberately a
different surface from mcp-graph-admin (directory/identity) - this server is
about the M365 workloads on top of the directory, not the directory itself.
Every tool here is read-only except the four at the bottom, gated by
mcp_ms_core.write_gate.gate.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from mcp_ms_core import gate

from .client import ALLOW_WRITES_ENV, get_client

mcp = FastMCP("mcp-o365-admin")


@mcp.tool()
def o365_admin_list_sharepoint_sites(search: str = "*", top: int = 25) -> dict:
    """Search SharePoint sites across the tenant. ``search`` defaults to '*'
    (everything); pass a keyword to narrow it."""
    items = get_client().get_all("sites", params={"search": search, "$top": top}, limit=top)
    return {"count": len(items), "items": items}


@mcp.tool()
def o365_admin_get_site(site_id: str) -> dict:
    """Get one SharePoint site's metadata by id."""
    return get_client().get(f"sites/{site_id}")


@mcp.tool()
def o365_admin_list_site_drive_items(site_id: str, path: str = "/", top: int = 50) -> dict:
    """List files/folders in a SharePoint site's default document library at
    ``path`` (default the drive root)."""
    client = get_client()
    root = f"sites/{site_id}/drive/root" if path in ("/", "") else f"sites/{site_id}/drive/root:/{path.strip('/')}:"
    items = client.get_all(f"{root}/children", params={"$top": top}, limit=top)
    return {"count": len(items), "items": items}


@mcp.tool()
def o365_admin_list_teams(top: int = 25) -> dict:
    """List Microsoft Teams teams in the tenant (groups provisioned as a Team)."""
    items = get_client().get_all(
        "groups",
        params={"$filter": "resourceProvisioningOptions/Any(x:x eq 'Team')", "$top": top},
        limit=top,
    )
    return {"count": len(items), "items": items}


@mcp.tool()
def o365_admin_list_team_channels(team_id: str) -> dict:
    """List the channels in one team."""
    items = get_client().get_all(f"teams/{team_id}/channels")
    return {"count": len(items), "items": items}


@mcp.tool()
def o365_admin_list_user_licenses(user_id: str) -> dict:
    """List the license SKUs currently assigned to one user."""
    result = get_client().get(f"users/{user_id}", params={"$select": "assignedLicenses,userPrincipalName"})
    return result


@mcp.tool()
def o365_admin_search_mailbox(user_id: str, query: str, top: int = 25) -> dict:
    """Search one user's mailbox by keyword - the tenant-wide capability
    that draws the line between this server and mcp-o365-user, which can
    only ever search the signed-in user's own mail."""
    items = get_client().get_all(
        f"users/{user_id}/messages", params={"$search": f'"{query}"', "$top": top}, limit=top
    )
    return {"count": len(items), "items": items}


@mcp.tool()
def o365_admin_assign_license(user_id: str, sku_id: str, confirm: bool = False) -> dict:
    """Assign a license SKU to a user. Dry-run unless confirm=true AND
    MS_O365_ADMIN_ALLOW_WRITES=1 is set on the server."""
    target = f"user:{user_id} sku:{sku_id}"
    blocked = gate(ALLOW_WRITES_ENV, confirm=confirm, action="assign_license", targets=[target])
    if blocked is not None:
        return blocked
    get_client().post(
        f"users/{user_id}/assignLicense",
        json_body={"addLicenses": [{"skuId": sku_id}], "removeLicenses": []},
    )
    return {"wouldExecute": True, "executed": True, "action": "assign_license", "target": target}


@mcp.tool()
def o365_admin_remove_license(user_id: str, sku_id: str, confirm: bool = False) -> dict:
    """Remove a license SKU from a user. Dry-run unless confirm=true AND
    MS_O365_ADMIN_ALLOW_WRITES=1 is set on the server."""
    target = f"user:{user_id} sku:{sku_id}"
    blocked = gate(ALLOW_WRITES_ENV, confirm=confirm, action="remove_license", targets=[target])
    if blocked is not None:
        return blocked
    get_client().post(
        f"users/{user_id}/assignLicense",
        json_body={"addLicenses": [], "removeLicenses": [sku_id]},
    )
    return {"wouldExecute": True, "executed": True, "action": "remove_license", "target": target}


@mcp.tool()
def o365_admin_remove_team_member(team_id: str, membership_id: str, confirm: bool = False) -> dict:
    """Remove a member from a team (``membership_id`` is the conversationMember
    id, not the user id - list channel/team members first to get it). Dry-run
    unless confirm=true AND MS_O365_ADMIN_ALLOW_WRITES=1 is set on the server."""
    target = f"team:{team_id} membership:{membership_id}"
    blocked = gate(ALLOW_WRITES_ENV, confirm=confirm, action="remove_team_member", targets=[target])
    if blocked is not None:
        return blocked
    get_client().delete(f"teams/{team_id}/members/{membership_id}")
    return {"wouldExecute": True, "executed": True, "action": "remove_team_member", "target": target}


@mcp.tool()
def o365_admin_delete_drive_item(site_id: str, item_id: str, confirm: bool = False) -> dict:
    """Delete one file/folder from a SharePoint site's document library.
    Dry-run unless confirm=true AND MS_O365_ADMIN_ALLOW_WRITES=1 is set on
    the server."""
    target = f"site:{site_id} item:{item_id}"
    blocked = gate(ALLOW_WRITES_ENV, confirm=confirm, action="delete_drive_item", targets=[target])
    if blocked is not None:
        return blocked
    get_client().delete(f"sites/{site_id}/drive/items/{item_id}")
    return {"wouldExecute": True, "executed": True, "action": "delete_drive_item", "target": target}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
