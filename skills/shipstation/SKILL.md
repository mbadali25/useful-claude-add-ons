---
name: shipstation
description: Use when querying, exploring, or troubleshooting a ShipStation account through its API - shipments, labels, rates, carriers, warehouses, inventory, products, tracking, orders, batches, manifests, fulfillments, or stores. Also use when choosing between ShipStation API V2 and V1, when a ShipStation call returns 401/403/404/429, or when an expected endpoint appears to be missing.
---

# ShipStation API

## Overview

ShipStation exposes **three different APIs** under one docs site. Picking the wrong one is the
single most common failure, because the auth scheme, base URL, and available resources all differ.

**Core principle: confirm the resource exists in V2 *before* writing the call. V2 is not a superset of V1.**

| API | Base URL | Auth | Use for |
|---|---|---|---|
| **V2** (current, default) | `https://api.shipstation.com` | `API-Key: <key>` header | Shipments, labels, rates, carriers, warehouses, inventory, products, tracking, batches, manifests, fulfillments, purchase orders, suppliers, totes |
| **V1** (legacy, still supported) | `https://ssapi.shipstation.com` | Basic `base64(key:secret)` | **Orders, customers, stores** - and nothing else worth reaching for |
| ShipEngine (white-label lineage) | `api.shipengine.com` | `API-Key` header | Ignore unless explicitly on ShipEngine |

## The trap: V2 has no orders endpoint

There is **no `/v2/orders`, `/v2/stores`, or `/v2/customers`**. Verified against the V2 spec
(99 paths / 142 operations) and the published V2 reference - neither contains them.

The docs site makes this easy to get wrong: `/apis/openapi/orders/list_orders` looks like V2 but
lives under the **V1** namespace. Only `/apis/openapi/*` is V2; `/apis/shipstation-v1/openapi/*`
and `/apis/shipengine/openapi/*` are the other two.

So when the question is about **orders** ("how many awaiting shipment?", "what did customer X buy?"):

- Use **V1** `/orders` — the direct answer, or
- Approximate in V2 via `/v2/shipments` (has `sales_order_id`, `store_id`, `item_keyword`) or `/v2/fulfillments`.

Don't invent a V2 orders path. Don't report "no orders found" from a 404 — that's the wrong API, not an empty account.

## Credentials

Read from environment variables — never inline a key in a command (shell history) or a file:

| Variable | API |
|---|---|
| `SHIPSTATION_API_KEY` | V2 |
| `SHIPSTATION_V1_API_KEY` + `SHIPSTATION_V1_API_SECRET` | V1 |

Generate a V2 key in **ShipStation → Settings → Account → API Settings**; it's shown only once and
V2 allows **one active key at a time**. V1 keys are separate — a V2 key will not authenticate V1.

`ss.ps1` resolves each variable from **Process → User → Machine** scope, so persistent variables
(`setx`, System Properties) work even in an already-running shell or agent session. A long-lived
parent process captures its environment at launch, so variables created afterwards are invisible to
`$env:` until it restarts — reading the registry directly avoids that, and **no restart is needed**.

Run with `-Verbose` to see which scope a credential came from.

> If you call the API without `ss.ps1` (raw `curl`/`Invoke-RestMethod`) in a session started before
> the variables were set, `$env:` will be empty. Either use `ss.ps1`, or hydrate first:
> `$env:SHIPSTATION_API_KEY = [Environment]::GetEnvironmentVariable('SHIPSTATION_API_KEY','Machine')`

## Querying

`ss.ps1` (in this skill dir) handles auth per version, 429 backoff, and pagination:

```powershell
.\ss.ps1 /v2/carriers                                              # smoke-test the key
.\ss.ps1 /v2/shipments -Query @{ shipment_status='shipped' } -All   # follow all pages
.\ss.ps1 /v2/inventory -Query @{ group_by='warehouse' }
.\ss.ps1 -V1 /orders -Query @{ orderStatus='awaiting_shipment' } -All
.\ss.ps1 /v2/labels -Method POST -Body @{ shipment_id='se-123' }
```

Raw `curl` equivalent — note the header name, which is neither Bearer nor Basic:

```bash
curl -H "API-Key: $SHIPSTATION_API_KEY" \
     "https://api.shipstation.com/v2/shipments?page_size=100"
```

### Pagination and filtering

V2 list responses wrap results in `{ <resource>: [...], total, page, pages, links{first,last,prev,next} }`.
Query params: `page` (default 1), `page_size` (default **25** — raise it), `sort_by`, `sort_dir` (default `desc`).

Most list endpoints filter on `created_at_start`/`created_at_end` and `modified_at_start`/`modified_at_end`.
`/v2/shipments` adds `shipment_status`, `store_id`, `sales_order_id`, `ship_to_name`, `item_keyword`,
`batch_id`, `payment_date_start`/`_end`. Full per-endpoint param list: **endpoints.md**.

**V1 uses camelCase** query params (`pageSize`, `orderStatus`, `createDateStart`) — not V2's snake_case.

**Filter before you page.** Order and shipment collections here run into the hundreds of thousands,
so `-All` on an unfiltered list is a many-hour crawl that will hit the rate limit long before it
finishes. Narrow by date/status/store first, and read `total` from a single `pageSize=1` call when all
you need is a count. `-All` stops at `-MaxPages 50` and warns that results are truncated — treat that
warning as "re-scope the query", not "raise the cap".

### Rate limits

**~200 requests/minute** by default; exceeding it returns **429** with a `Retry-After` header (seconds).
Prefer bulk endpoints (`/v2/rates/bulk`, batches) over loops. `ss.ps1` already honours `Retry-After`.

## Endpoint reference

**endpoints.md** in this skill dir lists all 142 V2 operations with methods, paths, operation IDs,
and query params — grouped by resource. Consult it instead of guessing paths.

Resource roots: `account`, `addresses`, `batches`, `carriers`, `connections`, `documents`, `downloads`,
`environment` (webhooks live at `/v2/environment/webhooks`), `fulfillments`, `inventory`,
`inventory_locations`, `inventory_warehouses`, `labels`, `mailing`, `manifests`, `packages`, `pickups`,
`products`, `purchase_orders`, `rate_shoppers`, `rates`, `service_points`, `shipments`, `suppliers`,
`tags`, `tokens`, `totes`, `tracking`, `users`, `warehouses`.

## Verifying against the live spec

ShipStation ships new V2 endpoints regularly, so treat endpoints.md as a snapshot. To check whether a
path exists before claiming it doesn't, fetch the authoritative spec:

```powershell
Invoke-WebRequest 'https://docs.shipstation.com/_spec/apis/@shipstation-v2/openapi.yaml' -OutFile spec.yaml
Select-String -Path spec.yaml -Pattern '^  /v2/' | ForEach-Object { $_.Line.Trim() }
```

Also useful: `https://docs.shipstation.com/llms.txt` (LLM-oriented index of all docs pages) and an
official **documentation** MCP server, `https://docs.shipstation.com/mcp`
(`claude mcp add --transport http shipstation-api https://docs.shipstation.com/mcp`).
That MCP serves docs only — it cannot read account data, so it does not replace the API calls above.

## Common mistakes

| Mistake | Correct |
|---|---|
| `Authorization: Bearer <key>` or Basic auth on V2 | V2 uses the `API-Key` header |
| Calling `/v2/orders` | No such path — use V1 `/orders`, or V2 `/v2/shipments` |
| Base `ssapi.shipstation.com` with an `API-Key` header | `ssapi` is V1/Basic; V2 is `api.shipstation.com` |
| Accepting the default `page_size=25` and reporting a partial count as a total | Raise `page_size`, follow `pages`, or use `-All` |
| Reading `total` as "count returned" | `total` is the full match count; the array is one page |
| Looping single requests for bulk work | Use bulk/batch endpoints; respect 200/min |
| Treating a 403 as a bad key | 403 usually means the endpoint is gated by account plan |
| Pasting the API key into a command or script | Env var only; V2 shows the key once and allows one active key |
