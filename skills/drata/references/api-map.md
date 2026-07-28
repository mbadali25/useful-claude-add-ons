# Drata API — Resource Map & Conventions

The API exposes ~29 resource groups. Below are the ones you'll touch most, with paths
for **v2** (`/public/v2/...`, cursor-paged, preferred) and notes where **v1**
(`/public/...`, offset-paged) is the practical path today. Always confirm the exact
operation and query params against the live reference at
`https://developers.drata.com/` — Drata adds and versions endpoints regularly, so
treat this map as a routing guide, not a frozen contract.

## Core resource groups

| Group | Typical path | What it holds |
|---|---|---|
| Company / Workspaces | `/public/v2/company`, `/public/v2/workspaces` | Tenant profile; workspace IDs for multi-workspace orgs |
| Controls | `/public/v2/controls` (v1: `/public/controls`) | Control library, mappings, owners, readiness |
| Monitoring Tests / Monitor Instances | `/public/v2/monitoring-tests`, monitor-instance search/detail/failed-results | Automated test results (`checkResultStatus`: `PASSED`/`FAILED`/…) |
| Frameworks | `/public/v2/frameworks` | SOC 2 / ISO / HIPAA etc.; requirement readiness counts |
| Personnel | `/public/personnel` (v1) | Employee compliance identity (see fields below) |
| Users & Roles | `/public/v2/users` | Drata app users, roles, get-by-email |
| Policies | `/public/v2/policies`; user assigned policies | Policy library, versions, published-PDF download URL |
| User Identities / HRIS User Identities | `/public/v2/user-identities` | Identity records ingested from IdP/HRIS |
| Evidence Library | `/public/v2/evidence-library` | Evidence records + versioned document download URLs |
| Risks / Risk Registers / Risk Library | `/public/v2/risks`, `/risk-registers`, `/risk-library` | Risk register entries, residual scores |
| Vendors / Vendor Security Reviews / Vendor Types | `/public/v2/vendors` | Vendor inventory + review status |
| Devices / Device Documents | `/public/v2/devices` | Endpoint inventory & compliance |
| Assets | `/public/v2/assets` | Inventory of policies, personnel, infra |
| Tickets | `/public/v2/tickets` | Linked ticketing records |
| Events | `/public/events` (v1) | Audit-log / event tracking export |
| Connections / Custom Connections | `/public/v2/connections`, custom-connections | Integrations & custom evidence sources |
| Background Check | background-check create/read | BGC evidence for personnel |
| Tasks / Audit Requests / Customer Request / Questionnaires | respective `/public/v2/...` | Workflow items, auditor requests, security questionnaires |
| Custom Data Records / Templates | `/public/v2/...` | Custom fields & Drata templates |

## Key object fields (frequently used)

**Personnel** (v1, the primary identity primitive):
`id` (UUID), `email`, `firstName`, `lastName`, `employmentType` (`FULL_TIME`|`CONTRACTOR`|`PART_TIME`),
`isActive` (bool), `externalId` (HRIS join key), `managerId`, and the **server-computed,
read-only** `complianceStatus` (`COMPLIANT`|`NON_COMPLIANT`|`PENDING`) and `trainingStatus`.
`complianceStatus` may sit at `PENDING` for a few minutes on new records while Drata
evaluates controls. Personnel operations include: find/search, get by id, get by email,
update contract dates, update employment status, reset sync status.

**Monitoring test**: `name`, `checkResultStatus` (`PASSED`/`FAILED`/`ERROR`/…) — filter for
`FAILED` to surface compliance gaps.

**Framework**: `name`, `isReady` (bool), `numReadyInScopeRequirements`,
`numInScopeRequirements` — compare the two counts for a readiness percentage.

## Pagination

- **v2 (cursor)**: response has `data: [...]` plus `pagination.cursor`. First call omits
  `cursor`; each response returns the next `cursor`; keep passing `?cursor=<value>` until
  it's absent/empty.
- **v1 (offset)**: response is `{ data, total, page, limit }`. Use `?page=1&limit=100`
  (max `limit` 100), loop while `page*limit < total`.

The helper's `get_all()` auto-detects both.

## Query params worth knowing

- `workspaceId` — required on scoped reads and all writes in multi-workspace orgs.
- `expand` (v2) — e.g. `?expand=owners,customFields` to inline related objects; omit for smaller/faster payloads.
- Resource-specific filters (status, dates, search terms) — check the operation page in the developer portal.

## Workspaces

Multi-workspace orgs must include the target workspace on writes (`POST`/`PUT`) and on
scoped reads. List workspaces to get IDs:

```bash
python scripts/drata_client.py get /public/v2/workspaces
```

## Document downloads (policies & evidence)

Download-style operations return a **short-lived signed URL**, not file bytes. Two steps:

```bash
# 1) get the signed URL from Drata
python scripts/drata_client.py get '/public/v2/evidence-library/{workspaceId}/{evidenceId}/{versionId}/download-url'
# 2) fetch that signedUrl separately (plain GET, no Drata auth header) to save the file
```

Policy PDFs work the same way (current-published-policy download URL by policy id).

## MCP option

Drata also publishes an official **MCP server** for AI-agent access to the same data.
If the user prefers connecting Drata through an MCP connector rather than scripting the
REST API directly, point them to the Drata Developer Portal's MCP Server docs — this
skill covers the direct-API path.
