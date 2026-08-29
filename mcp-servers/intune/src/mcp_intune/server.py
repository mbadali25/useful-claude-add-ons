"""MCP tool definitions for Intune device/compliance/app management.

Endpoints live under deviceManagement/* and deviceAppManagement/* in
Microsoft Graph v1.0. Every tool here is read-only except the four device
actions at the bottom, which are gated by ``mcp_ms_core.write_gate.gate`` -
each needs both ``MS_INTUNE_ALLOW_WRITES=1`` in the server's environment and
``confirm=true`` on the call itself. ``wipe`` and ``retire`` are irreversible
and hit real hardware; ``sync`` and ``reboot`` are lower-stakes but still
gated for consistency and because a queued action is not a completed one.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from mcp_ms_core import gate

from .client import ALLOW_WRITES_ENV, get_client

mcp = FastMCP("mcp-intune")

# managedDevice list responses leave several fields (ethernetMacAddress,
# physicalMemoryInBytes, totalStorageSpaceInBytes, ...) null even with an
# explicit $select - they only populate on a single-device GET. Don't read a
# null here as "this tenant has no data for this device"; re-fetch with
# intune_get_device instead.
_DEVICE_LIST_FIELDS = (
    "id,deviceName,userPrincipalName,operatingSystem,osVersion,"
    "complianceState,managementState,lastSyncDateTime,enrolledDateTime,"
    "deviceEnrollmentType,manufacturer,model,serialNumber"
)


@mcp.tool()
def intune_list_devices(filter: str | None = None, top: int = 25) -> dict:
    """List managed devices. ``filter`` is a raw OData $filter expression,
    e.g. "operatingSystem eq 'Windows'" or "complianceState eq 'noncompliant'".
    """
    params: dict[str, str | int] = {"$select": _DEVICE_LIST_FIELDS, "$top": top}
    if filter:
        params["$filter"] = filter
    items = get_client().get_all("deviceManagement/managedDevices", params=params, limit=top)
    return {"count": len(items), "items": items}


@mcp.tool()
def intune_get_device(device_id: str) -> dict:
    """Get one managed device by id, with the full property set (not just
    the list-view fields, which leave several columns null)."""
    return get_client().get(f"deviceManagement/managedDevices/{device_id}")


@mcp.tool()
def intune_list_noncompliant_devices(top: int = 50) -> dict:
    """List devices currently in a noncompliant complianceState."""
    return intune_list_devices(filter="complianceState eq 'noncompliant'", top=top)


@mcp.tool()
def intune_list_compliance_policies() -> dict:
    """List device compliance policies (deviceManagement/deviceCompliancePolicies)."""
    items = get_client().get_all("deviceManagement/deviceCompliancePolicies")
    return {"count": len(items), "items": items}


@mcp.tool()
def intune_list_configuration_profiles() -> dict:
    """List device configuration profiles (deviceManagement/deviceConfigurations).
    Settings-catalog profiles live under the beta-only configurationPolicies
    endpoint and are not covered here."""
    items = get_client().get_all("deviceManagement/deviceConfigurations")
    return {"count": len(items), "items": items}


@mcp.tool()
def intune_list_apps(top: int = 50) -> dict:
    """List apps registered in Intune app management (deviceAppManagement/mobileApps)."""
    items = get_client().get_all("deviceAppManagement/mobileApps", params={"$top": top}, limit=top)
    return {"count": len(items), "items": items}


def _device_action(device_id: str, action: str, confirm: bool) -> dict:
    blocked = gate(ALLOW_WRITES_ENV, confirm=confirm, action=action, targets=[device_id])
    if blocked is not None:
        return blocked
    get_client().post(f"deviceManagement/managedDevices/{device_id}/{action}")
    return {
        "wouldExecute": True,
        "executed": True,
        "action": action,
        "deviceId": device_id,
        "note": (
            "Graph queued the action (HTTP 204). This does not mean the "
            "device has completed it - check deviceActionResults on the "
            "device for real status; a queued syncDevice can take hours."
        ),
    }


@mcp.tool()
def intune_sync_device(device_id: str, confirm: bool = False) -> dict:
    """Queue an immediate policy/inventory sync on one device. Dry-run unless
    confirm=true AND MS_INTUNE_ALLOW_WRITES=1 is set on the server."""
    return _device_action(device_id, "syncDevice", confirm)


@mcp.tool()
def intune_reboot_device(device_id: str, confirm: bool = False) -> dict:
    """Queue an immediate reboot on one device. Dry-run unless confirm=true
    AND MS_INTUNE_ALLOW_WRITES=1 is set on the server."""
    return _device_action(device_id, "rebootNow", confirm)


@mcp.tool()
def intune_retire_device(device_id: str, confirm: bool = False) -> dict:
    """Retire one device: removes company data and the MDM management
    relationship. Irreversible. Dry-run unless confirm=true AND
    MS_INTUNE_ALLOW_WRITES=1 is set on the server."""
    return _device_action(device_id, "retire", confirm)


@mcp.tool()
def intune_wipe_device(device_id: str, confirm: bool = False) -> dict:
    """Factory-reset one device. Irreversible and destroys all data on the
    device. Dry-run unless confirm=true AND MS_INTUNE_ALLOW_WRITES=1 is set
    on the server."""
    return _device_action(device_id, "wipe", confirm)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
