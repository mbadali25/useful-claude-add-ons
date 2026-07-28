# Endpoint API (`{dataRegion}/endpoint/v1`)

Manage protected endpoints and servers. All calls need `Authorization: Bearer` + `X-Tenant-ID`.

## List / search endpoints

```
GET /endpoint/v1/endpoints
```

Useful query parameters (combine freely):

| Param | Values / notes |
|---|---|
| `healthStatus` | `good`, `suspicious`, `bad`, `unknown` (repeatable) |
| `type` | `computer`, `server`, `securityVm` |
| `hostnameContains` | substring match |
| `ipAddresses` | comma-separated exact IPs |
| `macAddresses` | comma-separated |
| `lastSeenBefore` / `lastSeenAfter` | ISO 8601 timestamp **or** duration like `-P30D` (not seen in 30 days) / `PT2H` |
| `tamperProtectionEnabled` | `true` / `false` |
| `isolationStatus` | `isolated`, `notIsolated` |
| `lockdownStatus` | server lockdown state |
| `ids` | comma-separated endpoint UUIDs |
| `search` + `searchFields` | free-text over hostname, IPs, associated person, etc. |
| `view` | `basic`, `summary`, `full` |
| `sort` | e.g. `hostname`, `healthStatus`, with `:asc`/`:desc` |
| `fields` | trim the response |

Pagination is **by-key**: follow `pages.nextKey` via `?pageFromKey=`. `pageSize` up to 500.

Item highlights: `id`, `hostname`, `type`, `health.overall`, `os`, `ipv4Addresses`, `associatedPerson`, `tamperProtectionEnabled`, `lastSeenAt`, `isolation`, `assignedProducts`, `cloud` (provider metadata for cloud instances), `lockdown`.

Single device: `GET /endpoint/v1/endpoints/{endpointId}`
Delete (remove from Central after uninstall/decommission): `DELETE /endpoint/v1/endpoints/{endpointId}` — destructive, confirm first.

## Actions on a device

| Action | Call |
|---|---|
| Scan now | `POST /endpoint/v1/endpoints/{id}/scans` body `{}` |
| Update check | `POST /endpoint/v1/endpoints/{id}/update-checks` body `{}` |
| Get tamper protection (incl. password) | `GET /endpoint/v1/endpoints/{id}/tamper-protection` |
| Set tamper protection | `POST /endpoint/v1/endpoints/{id}/tamper-protection` body `{"enabled": true}` (add `"regeneratePassword": true` to rotate) |

Global tamper-protection default: `GET|POST /endpoint/v1/settings/tamper-protection`.

## Isolation

Bulk isolate / de-isolate (up to ~50 ids per call):

```
POST /endpoint/v1/endpoints/isolation
{
  "enabled": true,
  "comment": "Isolated during IR ticket #1234",
  "ids": ["uuid1", "uuid2"]
}
```

Single device also supports `PATCH /endpoint/v1/endpoints/{id}/isolation` with `{"enabled": false, "comment": "..."}`. Isolation state appears on the endpoint object under `isolation` (`status`, `adminIsolated`, `selfIsolated`). Always confirm target list with the user before isolating or releasing.

## Endpoint groups

- `GET /endpoint/v1/endpoint-groups` — list groups
- `POST /endpoint/v1/endpoint-groups` — create (`name`, `description`, `type`)
- `GET|PATCH|DELETE /endpoint/v1/endpoint-groups/{groupId}`
- `GET|POST /endpoint/v1/endpoint-groups/{groupId}/endpoints` — list/add members; `DELETE .../endpoints/{endpointId}` to remove

## Global settings (allow/block lists, exclusions, web control)

- **Allowed items**: `GET|POST /endpoint/v1/settings/allowed-items`, then `GET|PATCH|DELETE .../allowed-items/{itemId}`. POST body uses `type` (`path`, `sha256`, `certificateSigner`), `properties`, `comment`, `originPersonName`.
- **Blocked items**: `GET|POST /endpoint/v1/settings/blocked-items`, `DELETE .../blocked-items/{itemId}` (blocking is by `sha256`).
- **Scanning exclusions**: `GET|POST /endpoint/v1/settings/exclusions/scanning`, then `GET|PATCH|DELETE .../scanning/{exclusionId}`. Body: `{"type": "path|posixPath|virtualPath|process|web|pua|amsi", "value": "...", "scanMode": "onDemandAndOnAccess"}`.
- **Intrusion-prevention exclusions**: `/endpoint/v1/settings/exclusions/intrusion-prevention`.
- **Web control local sites**: `GET|POST /endpoint/v1/settings/web-control/local-sites`, `DELETE .../local-sites/{id}` — tag or allow/block URLs.

Adding exclusions weakens protection — flag the risk and keep entries as narrow as possible.

## Migrations & software

- Endpoint migration between tenants: `/endpoint/v1/migrations` (sender/receiver flow).
- Installer download links: `GET /endpoint/v1/downloads` — returns platform installer URLs for the tenant.

## Typical recipes

- **Unhealthy devices report**: `get-all /endpoint/v1/endpoints?healthStatus=bad&healthStatus=suspicious&view=summary`, tabulate hostname / health / lastSeenAt / associatedPerson.
- **Stale device cleanup**: filter `lastSeenBefore=-P90D`, review list with user, then DELETE each id.
- **IR containment**: resolve hostnames → ids via `hostnameContains` or `search`, bulk-isolate with a comment referencing the ticket, verify `isolation.status`.
