# Cases API (`{dataRegion}/cases/v1`) — MDR / Managed Detection findings

## Read this first: on a managed tenant, the alerts stream is empty

If the tenant is MDR / Managed Detection, Sophos does **not** populate the alert
feeds. Findings are raised as **cases** instead, and both `/siem/v1/alerts` and
`/common/v1/alerts` return **zero — forever**. Not an error, not a permissions
problem, not an empty page you can cursor past. Just zero.

This is the single most expensive misdiagnosis on this API, because a SIEM feed
collecting alerts only looks completely healthy in its own log while collecting
none of the findings. Symptom: "our Sophos integration is running fine but we
barely get any data."

Confirm it in two calls before concluding a collector is broken:

```bash
# If this is 0 of 0...
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TID" \
  "$REGION/common/v1/alerts?pageSize=1&pageTotal=true"

# ...and this is not, the findings are in cases, not alerts.
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TID" \
  "$REGION/cases/v1/cases?pageSize=50&pageTotal=true"
```

## The two operations

```
GET /cases/v1/cases
GET /cases/v1/cases/{caseId}/detections
```

### `GET /cases/v1/cases`

Returns `{"items": [...], "pages": {"current","size","total","items"}}`.

Case fields: `id`, `name`, `status`, `severity`, `type`, `assignee.name`,
`createdAt`, `updatedAt`, `resolvedAt`, `createdBy.name`, `detectionCount`,
`escalated`, `managedBy`, `overview`, `initialDetection`.

Notes:
- `severity` is **often absent** on cases raised straight from a detection. Absent
  is not "informational" — do not coerce it.
- `name` is `"(HOSTNAME) | RULE-NAME"` for detection-derived cases, so the endpoint
  can be lifted from it when there is no device field.
- `escalated: true` means a Sophos MDR analyst wants the customer to act. Treat it
  as the highest-priority signal this API produces.

### `GET /cases/v1/cases/{caseId}/detections`

**This is the call worth making.** The SIEM streams carry no detection rule, no
rule description and no MITRE mapping; this is the only endpoint that does.

Detection fields: `id`, `time`, `sensorGeneratedAt`, `type`, `attackType`,
`severity` (**1–10 integer**, not the low/medium/high string the SIEM streams
use), `detectionRule`, `ruleDescription`, `device{id,type,entity}`,
`sensor{version,source}`, `intelixFileReputation`, `geolocation`, `rawData`, and:

```json
"mitreAttacks": [
  {"tactic": {"id": "TA0002", "name": "Execution",
              "techniques": [{"id": "T1059.001", "name": "PowerShell"}]}}
]
```

Sibling sub-resources: `/activities` works (audit trail of status changes).
`/artifacts`, `/attachments`, `/comments` and `/audit` all return 404.

## Only three query parameters are honoured

Verified against the live API one parameter at a time, counting results:

| Parameter | Honoured? |
|---|---|
| `status` — repeatable: `?status=new&status=investigating` | **yes** |
| `severity` — repeatable | **yes** |
| `createdAfter` — ISO-8601 | **yes** |
| `priority` | no — accepted, ignored |
| `device`, `deviceId` | no — accepted, ignored |
| `updatedAfter` | no — accepted, ignored |
| `from` / `to`, `sort`, `search` | no — accepted, ignored |

**Every ignored parameter returns HTTP 200 with the full unfiltered set.** There
is no error to catch and nothing in the response says the filter was dropped, so
a caller that "filters by device" this way silently processes everything and
reports success. Never add a filter here without proving it changes the result
count. Filter by device client-side.

Valid `status`: `new`, `investigating`, `onhold`, `resolved`, `closed`.
Valid `severity`: `informational`, `low`, `medium`, `high`, `critical`.

## Pagination differs from the rest of Central

- `pageSize=200` is a **400**. The cap is lower than the SIEM streams'; use 50.
- `page=2` is **ignored**, not rejected — it silently re-returns page 1. This API
  pages by key: follow `pages.nextKey` with `?pageFromKey=`.
- `pages.total` is the number of **pages**, not items. `pages.items` is the count.

## Polling cases incrementally

There is no `updatedAfter`, so incremental polling by modification time is
impossible: **every run re-reads every case in scope.** Two consequences for
anything that forwards cases onward:

1. De-duplicate on `(case id, updatedAt)` so a status transition
   (`new` → `investigating` → `resolved`) is re-emitted exactly once per change.
2. Keep that de-dup memory in a **separate budget from any high-volume stream**.
   If case keys share one rolling window with SIEM event ids, a busy events feed
   evicts them within days and then every case re-emits on every poll, forever.
   That failure mode is a duplicate storm, not a gap, so it reads as the feed
   working harder rather than breaking.

Use `createdAfter` to bound the window; drop it entirely for a first backfill.

## Working example

```bash
python scripts/sophos_client.py get /cases/v1/cases \
  --params pageSize=50 pageTotal=true status=new

python scripts/sophos_client.py get /cases/v1/cases/2-1022196/detections \
  --params pageSize=50
```
