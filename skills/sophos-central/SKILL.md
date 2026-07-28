---
name: sophos-central
description: Work with the Sophos Central API — authenticate, resolve tenants/regions, manage endpoints (list, isolate, scan, tamper protection), triage alerts, pull SIEM events, run XDR/Live Discover queries, and manage firewalls. Use this skill whenever the user mentions Sophos, Sophos Central, Sophos endpoints/agents, Intercept X, Sophos alerts or SIEM export, Sophos firewall management via Central, or wants to automate/report on anything in their Sophos estate — even if they don't say "API". Also use it when writing scripts, integrations, or one-off queries against api.central.sophos.com or id.sophos.com.
---

# Sophos Central API

Automate and query Sophos Central: endpoint protection, alerts, SIEM events, XDR queries, and firewall management. All APIs are RESTful JSON over HTTPS.

## Quick start (the 3-step dance)

Every Sophos Central session follows the same pattern. Do these in order:

1. **Get a token** — `POST https://id.sophos.com/api/v2/oauth2/token` (form-encoded) with `grant_type=client_credentials`, `client_id`, `client_secret`, `scope=token`. Token lives ~1 hour.
2. **Whoami** — `GET https://api.central.sophos.com/whoami/v1` with `Authorization: Bearer <token>`. Returns your `id`, `idType` (`tenant`, `organization`, or `partner`), and `apiHosts`. For tenants, `apiHosts.dataRegion` is the regional base URL (e.g. `https://api-us01.central.sophos.com`) — all tenant API calls go there.
3. **Call tenant APIs** — send `Authorization: Bearer <token>` plus `X-Tenant-ID: <tenantId>` to `{dataRegion}/endpoint/v1/...`, `{dataRegion}/common/v1/...`, etc.

Partners/organizations: whoami returns `idType: partner` or `organization`. Use `X-Partner-ID` / `X-Organization-ID` against the **global** host to enumerate tenants (`GET https://api.central.sophos.com/partner/v1/tenants?pageTotal=true`), then call each tenant's own `apiHost` with `X-Tenant-ID`. Details in `references/auth.md`.

## Credentials — handle with care

- Credentials are created in Sophos Central Admin under **Global Settings > API Credential Management** (client ID + client secret, with a role such as Service Principal ReadOnly / Management / Super Admin).
- Read credentials from environment variables (`SOPHOS_CLIENT_ID`, `SOPHOS_CLIENT_SECRET`) or a secrets manager. Never hardcode them in scripts, never echo the secret or token to output, and never commit them.
- Prefer the least-privileged role that can do the job; call this out when helping a user create credentials.

## Helper script

`scripts/sophos_client.py` is a self-contained Python client (stdlib + `requests`) that handles auth, whoami, region resolution, tenant headers, pagination, and 429 retry. Use it instead of re-writing boilerplate:

```bash
export SOPHOS_CLIENT_ID=... SOPHOS_CLIENT_SECRET=...
python scripts/sophos_client.py whoami
python scripts/sophos_client.py get /endpoint/v1/endpoints --params healthStatus=bad
python scripts/sophos_client.py get-all /endpoint/v1/endpoints          # auto-paginate
python scripts/sophos_client.py post /endpoint/v1/endpoints/{id}/scans --json '{}'
python scripts/sophos_client.py siem-events --since 12h                 # SIEM export
```

It can also be imported (`from sophos_client import SophosClient`) when building larger scripts for the user.

## API map — which reference to read

| Task | API base path | Reference file |
|---|---|---|
| Auth, whoami, partner/org tenant enumeration | `id.sophos.com`, `/whoami/v1`, `/partner/v1`, `/organization/v1` | `references/auth.md` |
| Endpoints: list/search, isolate, scan, tamper protection, delete, groups, allowed/blocked items, exclusions | `/endpoint/v1` | `references/endpoint-api.md` |
| Alerts (list, search, take actions), directory users/groups, admins, roles | `/common/v1` | `references/common-api.md` |
| SIEM event/alert export, XDR Data Lake queries, Live Discover (EDR queries on live devices) | `/siem/v1`, `/xdr-query/v1`, `/live-discover/v1` | `references/siem-xdr.md` |
| Firewalls managed by Central: inventory, groups, firmware, actions | `/firewall/v1` | `references/firewall-api.md` |

Read the relevant reference file before writing calls — they contain the exact endpoints, filters, action enums, and pagination style for each API.

## Universal conventions

- **Pagination**: most list endpoints wrap results in `items` + `pages`. Two styles: **by-offset** (`?page=2&pageSize=50`, add `pageTotal=true` to get counts) and **by-key** (`?pageFromKey=<nextKey>`, follow `pages.nextKey` until absent). Default page size 50. The SIEM API uses its own `cursor`/`has_more` scheme.
- **Partial responses**: add `?fields=id,hostname,health` to trim payloads.
- **Rate limits**: on `429`, honor `Retry-After` and back off exponentially. Batch/sleep when iterating many tenants.
- **Errors**: non-2xx returns JSON with `error`, `message`, `correlationId` — surface `correlationId` when reporting failures, Sophos support asks for it.
- **Timestamps**: ISO 8601 UTC (e.g. `2026-07-14T00:00:00.000Z`).

## Safety rails for destructive actions

Isolation, endpoint deletion, tamper-protection changes, alert actions, and firewall changes affect production security posture. Before executing:
- Confirm the exact target set with the user (show the device names/IDs the filter matched, not just the count, when feasible).
- Default to dry-run style: list what *would* be affected first, then act on explicit confirmation.
- Never disable tamper protection fleet-wide or de-isolate machines without an explicit user instruction naming the scope.
