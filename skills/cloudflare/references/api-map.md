# API map

Base URL for everything: `https://api.cloudflare.com/client/v4`. No regional host.

## Scope: zone vs account

Almost every resource hangs off one of two prefixes. Resolve the ID first.

| Prefix | Holds | Resolve with |
|---|---|---|
| `/zones/{zone_id}/...` | DNS records, cache, page rules, most WAF, SSL/TLS, DNSSEC | `zone-id example.com` |
| `/accounts/{account_id}/...` | Workers, R2, KV, Zero Trust, account rulesets, members | `account-id "My Org"` |

```bash
python scripts/cloudflare_client.py zone-id example.com        # -> 32-char hex
python scripts/cloudflare_client.py account-id "My Org"        # -> 32-char hex
```

IDs are opaque 32-char hex strings. A zone id is **not** the domain name; a member
id is the membership id, **not** the user id. Always resolve names to IDs first.

## Key resource paths

| Resource | Method + path | Notes |
|---|---|---|
| List zones | `GET /zones` | `?name=`, `?account.id=`, `?status=` filters |
| DNS records | `GET/POST /zones/{zid}/dns_records` | `PUT`=full replace, `PATCH`=partial, `DELETE /.../{rid}` |
| Cache purge | `POST /zones/{zid}/purge_cache` | body `{"files":[...]}` / `{"tags":[...]}` / `{"hosts":[...]}` / `{"purge_everything":true}` |
| Page rules | `GET/POST /zones/{zid}/pagerules` | legacy; new work should use Rulesets/Redirect Rules |
| SSL/TLS mode | `GET/PATCH /zones/{zid}/settings/ssl` | value: off / flexible / full / strict |
| Zone settings | `GET /zones/{zid}/settings` | one setting: `/settings/{name}` |
| DNSSEC | `GET/PATCH /zones/{zid}/dnssec` | `PATCH {"status":"active"}` then sync DS at registrar |
| WAF custom rules | Rulesets engine (see below) | **not** the old Firewall Rules API |
| Rulesets | `GET /zones/{zid}/rulesets`, `GET /accounts/{aid}/rulesets` | list all rulesets in scope |
| Phase entrypoint | `GET/PUT /zones/{zid}/rulesets/phases/{phase}/entrypoint` | edit the whole phase ruleset atomically |
| Workers script | `PUT /accounts/{aid}/workers/scripts/{name}` | multipart upload |
| KV namespaces | `GET/POST /accounts/{aid}/storage/kv/namespaces` | keys: `/.../{ns_id}/keys` |
| R2 buckets | `GET/POST /accounts/{aid}/r2/buckets` | data plane is S3-compatible, separate endpoint |
| Zero Trust Access apps | `GET/POST /accounts/{aid}/access/apps` | |
| Gateway rules | `GET/POST /accounts/{aid}/gateway/rules` | |
| Tunnels (cloudflared) | `GET/POST /accounts/{aid}/cfd_tunnel` | |
| Account members | `GET/POST /accounts/{aid}/members` | member id != user id |
| Analytics (GraphQL) | `POST /graphql` | separate GraphQL API, not REST paths above |

## WAF / firewall: use the Rulesets engine

The legacy **Firewall Rules API and Filters API were sunset on 2025-06-15** and no
longer accept modifications. WAF custom rules are now managed exclusively through the
Rulesets engine. The custom-rules phase is `http_request_firewall_custom`.

Typical flow to edit custom rules for a zone:

1. `GET /zones/{zid}/rulesets/phases/http_request_firewall_custom/entrypoint`
   - returns the phase ruleset (may 404 if none exists yet -> create with `PUT`).
2. Modify the `rules` array (each rule = `expression` + `action`).
3. `PUT` the whole entrypoint back. This is atomic - the full rule list replaces the
   old one, so read-modify-write; never PUT a partial list.

Terraform users manage this via the `cloudflare_ruleset` resource with the
`http_request_firewall_custom` phase, not `cloudflare_firewall_rule`.

## Pagination

Offset-based: `?page=1&per_page=N`. The **per-page cap varies by resource**:

| Resource | `per_page` max |
|---|---|
| DNS records | 5000 |
| Zones | 50 |
| Most list endpoints | 50 or 100 |
| Some Zero Trust / Workers endpoints | cursor-based, not offset |

Read `result_info.total_pages` and loop; `get-all` does this for you. For cursor
endpoints, pass a `cursor` param and `get-all` follows `result_info.cursors.after`.

## Response envelope

```json
{ "success": true, "errors": [], "messages": [],
  "result": {...} | [...],
  "result_info": { "page": 1, "per_page": 100, "count": 100,
                   "total_count": 342, "total_pages": 4 } }
```

Check `success` before trusting `result`. On failure, `errors` holds
`[{"code": 81044, "message": "..."}]` - error codes are numeric and product-specific.
Surface the code and message verbatim; do not guess at meaning.
