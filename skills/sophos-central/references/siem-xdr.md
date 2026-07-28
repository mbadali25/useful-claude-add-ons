# SIEM, XDR Query, and Live Discover APIs

## SIEM API (`{dataRegion}/siem/v1`) — event/alert export

Designed for pulling a rolling feed into a SIEM (Splunk, Sentinel, etc.).

```
GET /siem/v1/events?limit=1000&from_date={unix_epoch_seconds}
GET /siem/v1/alerts?limit=1000&cursor={cursor}
```

Rules that trip people up:
- Data availability window is **24 hours** — poll at least every few hours; for history beyond 24h use the XDR Data Lake or Common API alerts instead.
- `from_date` is a **Unix epoch in seconds** (unlike the ISO timestamps elsewhere), and only for the first call. After that, persist and pass the returned `next_cursor` — cursors encode position and expire after 24h.
- `limit` max 1000. Response: `{"items": [...], "next_cursor": "...", "has_more": true}` — keep calling while `has_more`.
- Legacy note: SIEM previously used per-tenant API tokens; the current scheme is the same Bearer + `X-Tenant-ID` as everything else.

Event items include `type` (e.g. `Event::Endpoint::Threat::Detected`), `severity`, `endpoint_id`, `source`, `name`, `when`, `location`.

## XDR Query API (`{dataRegion}/xdr-query/v1`) — Data Lake SQL

Run SQL against the Sophos Data Lake (up to 30 days of telemetry, multi-tenant capable for partners).

1. **Submit**:
```
POST /xdr-query/v1/queries/runs
{
  "adHocQuery": {
    "template": "SELECT meta_hostname, query_name, COUNT(*) c FROM xdr_data GROUP BY 1,2 ORDER BY c DESC LIMIT 100"
  },
  "name": "process summary",
  "from": "2026-07-07T00:00:00.000Z",
  "to": "2026-07-14T00:00:00.000Z"
}
```
2. **Poll**: `GET /xdr-query/v1/queries/runs/{runId}` until `status` is `finished` (`result`: `succeeded`/`failed`/`canceled`/`timedOut`).
3. **Fetch results**: `GET /xdr-query/v1/queries/runs/{runId}/results?maxSize=1000` — paginated by key.

Also available: saved query templates under `/xdr-query/v1/queries`. Main tables include `xdr_data` (endpoint telemetry) and product-specific ingest tables. Queries use Presto/Athena-style SQL.

## Live Discover API (`{dataRegion}/live-discover/v1`) — osquery on live devices

Runs osquery SQL **on the endpoints themselves** (devices must be online), unlike XDR which queries the cloud lake.

1. **Submit**:
```
POST /live-discover/v1/queries/runs
{
  "adHocQuery": {
    "template": "SELECT name, path, pid FROM processes LIMIT 200",
    "name": "running processes"
  },
  "matchEndpoints": {
    "filters": [ { "ids": ["endpoint-uuid-1", "endpoint-uuid-2"] } ]
  }
}
```
   (`matchEndpoints` also supports `all: true` — be careful, that fans out to the whole estate.)
2. **Poll run**: `GET /live-discover/v1/queries/runs/{runId}` — watch `status` and per-endpoint progress under `.../runs/{runId}/endpoints`.
3. **Results**: `GET /live-discover/v1/queries/runs/{runId}/results` — rows keyed by endpoint.

Tables are standard osquery (`processes`, `users`, `listening_ports`, `services`, `registry`, etc.) plus Sophos-specific tables. Devices that are offline simply never report — set user expectations.

## Choosing between them

| Need | Use |
|---|---|
| Continuous export to SIEM (last 24h) | SIEM API |
| Historical hunt across estate (≤30 days) | XDR Query |
| Interrogate live devices right now (files, processes, registry) | Live Discover |
| Console-style alert triage with actions | Common API alerts |
