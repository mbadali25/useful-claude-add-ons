# Common API (`{dataRegion}/common/v1`)

Cross-product data: alerts, directory (users/groups), admins, and roles. Headers: `Authorization: Bearer` + `X-Tenant-ID`.

## Alerts

### List

```
GET /common/v1/alerts
```

Params: `product` (`endpoint`, `server`, `firewall`, `mobile`, `emailGateway`, `phishThreat`, `wireless`, `encryption`, ...), `category`, `severity` (`low`, `medium`, `high`), `from`/`to`? — prefer the search endpoint for date ranges. Pagination is by-key (`pageFromKey`).

### Search (richer filtering)

```
POST /common/v1/alerts/search
{
  "severity": ["high"],
  "product": ["endpoint", "server"],
  "category": ["malware", "runtimeDetections"],
  "groupKey": null,
  "from": "2026-07-01T00:00:00.000Z",
  "to": "2026-07-14T00:00:00.000Z"
}
```

Alert object highlights: `id`, `description`, `type` (e.g. `Event::Endpoint::Threat::Detected`), `groupKey`, `severity`, `category`, `product`, `raisedAt`, `managedAgent` (device), `person`, `allowedActions`.

### Take action on an alert

```
POST /common/v1/alerts/{alertId}/actions
{ "action": "acknowledge", "message": "Triaged - false positive" }
```

Valid actions depend on the alert's `allowedActions` field. Known values: `acknowledge`, `cleanPua`, `cleanVirus`, `authPua`, `clearThreat`, `clearHmpa`, `sandboxRelease`, `sendMsgPua`, `sendMsgThreat`. Only send an action listed in that alert's `allowedActions`; anything else returns 400. Bulk-acknowledging alerts hides them from the console — confirm scope with the user first.

## Directory

- **Users**: `GET|POST /common/v1/directory/users`, `GET|PATCH|DELETE /common/v1/directory/users/{userId}`. Search with `?search=` and `?searchFields=name,email`. User objects include `groups` and any `exchangeLogin`/AD sync source.
- **User groups**: `GET|POST /common/v1/directory/user-groups`, member management under `/common/v1/directory/user-groups/{groupId}/users` (GET/POST/DELETE).

Directory entries synced from AD/Entra ID are read-only via API — edits must happen at the source.

## Admins & roles

- `GET /common/v1/admins` — list Central admins; `GET /common/v1/admins/{adminId}`.
- `GET /common/v1/roles` — list roles (predefined + custom) with their permission sets; useful for access reviews.

## Recipes

- **Daily high-severity digest**: `POST /alerts/search` with `severity=["high"]` and yesterday's window; group by `category` and `managedAgent.name`.
- **Alert triage loop**: list alerts → show table (severity, description, device, raisedAt) → user picks ids → send `acknowledge`/`clearThreat` per `allowedActions`.
- **Admin access review**: join `/admins` with `/roles` to show who holds Super Admin.
