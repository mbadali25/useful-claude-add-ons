# Firewall Management API (`{dataRegion}/firewall/v1`)

Manage Sophos Firewalls that are **registered to Sophos Central** (Central management enabled on the firewall). This is distinct from the on-box XG/SFOS XML API — for direct firewall configuration (rules, objects) you either use the on-box API or Central's group policy sync; this API covers Central-side inventory and orchestration.

Headers: `Authorization: Bearer` + `X-Tenant-ID`.

## Inventory

```
GET /firewall/v1/firewalls
```

Item fields include: `id`, `hostname`, `name`, `serialNumber`, `firmwareVersion`, `model`, `status` (`connected`/`disconnected`, sync state), `group` (id/name), `cluster` (HA info), `capabilities`, `externalIpv4Addresses`.

Single firewall: `GET /firewall/v1/firewalls/{firewallId}`.

## Groups

- `GET|POST /firewall/v1/groups` — list/create firewall groups (groups can enforce shared config from Central).
- `GET|PATCH|DELETE /firewall/v1/groups/{groupId}`
- Assign a firewall to a group by PATCHing the firewall's `group`.

## Firmware upgrades

1. **Check available firmware**: `POST /firewall/v1/firewalls/actions/firmware-upgrade-check` with `{"firewalls": ["id1", "id2"]}` → returns upgradable versions per device.
2. **Trigger upgrade**: `POST /firewall/v1/firewalls/{firewallId}/action` with body like `{"action": "firmwareUpgrade", "upgradeToVersion": {"version": "..."}}` (schedule fields supported).

Firmware upgrades reboot the firewall — always confirm maintenance window with the user before triggering, and prefer upgrading the auxiliary node first in HA pairs.

## MDR threat feeds

Endpoints under `/firewall/v1` also expose threat-feed configuration used by MDR to push block/monitor indicators (IP/domain/URI) to firewalls. Relevant when automating IOC blocking at the firewall layer; list/apply threat-feed settings per firewall or group.

## Recipes

- **Estate firmware report**: `GET /firewalls`, table of name / model / serial / firmwareVersion / status, flag versions below target.
- **Disconnected firewall alarm**: filter `status` for disconnected, cross-reference `externalIpv4Addresses` for reachability checks.
- **Staged upgrade**: upgrade-check across the fleet → present per-device available versions → upgrade in user-approved batches.
