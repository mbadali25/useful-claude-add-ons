---
name: cloudflare
description: Connect to and work with the Cloudflare v4 API - authenticate (scoped API token or legacy Global API Key), resolve zone/account scope, and read or manage DNS records, zones, cache (purge), firewall/WAF and rulesets, page rules, SSL/TLS settings, DNSSEC, Workers/KV/R2, Zero Trust (Access, Gateway, tunnels), account members, and analytics. Use this skill whenever the user mentions Cloudflare, cloudflare.com, a Cloudflare zone/account, DNS records on Cloudflare, purging Cloudflare cache, WAF/firewall rules, page rules, Workers/KV/R2, Cloudflare Tunnel/Zero Trust/Access/Gateway, or wants to script/report against api.cloudflare.com - even if they don't say "API". Also use it when writing integrations, Terraform-adjacent automation, CI tasks, or one-off queries against the Cloudflare API, and when debugging 400/403/429/9xxx errors from api.cloudflare.com.
---

# Cloudflare v4 API

Automate and query Cloudflare: DNS, zones, cache purge, firewall/WAF and rulesets, page rules, SSL/TLS, DNSSEC, Workers/KV/R2, Zero Trust (Access, Gateway, tunnels), members, and analytics. Everything is RESTful JSON over HTTPS against a single host: `https://api.cloudflare.com/client/v4`.

> There is no regional host and no "app" host to confuse - every call goes to `api.cloudflare.com/client/v4`. The dashboard at `dash.cloudflare.com` is not an API endpoint.

## Quick start

1. **Get credentials** (see `references/auth.md`). Strongly prefer a **scoped API token** (My Profile -> API Tokens -> Create Token) over the legacy **Global API Key**. A token carries only the permissions and zone/account scope you grant it; the Global API Key is root-equivalent over the whole account and can't be scoped.
2. **Verify** the token before doing anything else - this is the fastest way to catch a bad key or wrong scope:
   ```bash
   export CLOUDFLARE_API_TOKEN=xxxxx
   python scripts/cloudflare_client.py verify        # GET /user/tokens/verify
   ```
3. **Figure out scope.** Almost every resource hangs off one of two prefixes:
   - **Zone-scoped**: `/zones/{zone_id}/...` (DNS records, cache, page rules, most WAF, SSL settings, DNSSEC).
   - **Account-scoped**: `/accounts/{account_id}/...` (Workers, R2, KV, Zero Trust, account rulesets, members).
   Resolve a zone name -> `zone_id` and an account -> `account_id` with the helper (see below) before building calls.

## Helper script

`scripts/cloudflare_client.py` is a self-contained Python client (stdlib only - no third-party packages) that handles both auth methods, the standard `{success, errors, messages, result, result_info}` envelope, offset (`page`/`per_page`) pagination, 429 backoff (Cloudflare does **not** send `Retry-After`, so it uses exponential backoff), and a read-only / dry-run guard for mutations. Use it instead of re-writing boilerplate:

```bash
export CLOUDFLARE_API_TOKEN=xxxxx                 # scoped token (preferred), OR:
# export CLOUDFLARE_EMAIL=you@corp.com CLOUDFLARE_API_KEY=global_key   # legacy

python scripts/cloudflare_client.py verify                                   # token check
python scripts/cloudflare_client.py zone-id example.com                      # name -> zone_id
python scripts/cloudflare_client.py get     /zones/{zid}/dns_records --params 'type=A' 'name=www.example.com'
python scripts/cloudflare_client.py get-all /zones/{zid}/dns_records         # auto-paginate every page
python scripts/cloudflare_client.py post    /zones/{zid}/dns_records --json '{"type":"A","name":"www","content":"1.2.3.4","ttl":300,"proxied":true}'
python scripts/cloudflare_client.py put      /zones/{zid}/dns_records/{rid} --json '{"type":"A","name":"www","content":"5.6.7.8","proxied":true}' --dry-run
python scripts/cloudflare_client.py delete   /zones/{zid}/dns_records/{rid}
```

Set `CLOUDFLARE_READ_ONLY=1` to block every mutating call, or pass `--dry-run` on a single mutation to print the exact request without sending it. Importable too: `from cloudflare_client import CloudflareClient`.

## Response envelope

Every response uses the same wrapper - check `success` before trusting `result`:

```json
{ "success": true, "errors": [], "messages": [],
  "result": { ... } or [ ... ],
  "result_info": { "page": 1, "per_page": 100, "count": 100, "total_count": 342, "total_pages": 4 } }
```

On failure `success` is `false` and `errors` holds `[{ "code": 81044, "message": "..." }]`. Cloudflare error codes are numeric and product-specific - surface the code and message verbatim to the user; don't guess. `result_info` is present only on list endpoints, and that's what `get-all` keys off to know when to stop.

## API map - which reference to read

| Task | Reference file |
|---|---|
| Token vs Global Key, creating/scoping tokens, `verify`, permission groups, secret handling | `references/auth.md` |
| Zone vs account scoping, resolving IDs, key resource paths (DNS, cache purge, firewall/rulesets, page rules, SSL/TLS, DNSSEC, Workers/KV/R2, Zero Trust, members), pagination limits per resource | `references/api-map.md` |
| Recipes: bulk DNS export/import, targeted vs full cache purge, DNS upsert, mint a least-privilege token, list all zones in an account, find a proxied record's real origin | `references/common-tasks.md` |

Read the relevant reference before writing calls - they carry the exact paths, per-page caps, and object shapes.

## Universal conventions

- **Auth header**: scoped token -> `Authorization: Bearer <token>`. Legacy -> `X-Auth-Email: <email>` + `X-Auth-Key: <global_key>`. Never mix the two on one request. The helper picks based on which env vars are set (token wins if both present).
- **Rate limit**: **1,200 requests per 5-minute rolling window** per token/user, across all endpoints. There is **no** `Retry-After` header on `429` - back off exponentially (the helper does this). Throttle bulk exports and batch DNS work.
- **Pagination**: offset-based `?page=1&per_page=N`. The per-page **cap varies by resource** (DNS records allow up to 5,000 with `per_page`; many endpoints cap at 50 or 100). Read `result_info.total_pages` and loop - `get-all` handles this. A few newer endpoints (some Zero Trust, Workers) use `cursor`; the helper passes a `cursor` param straight through if you supply one.
- **IDs are opaque 32-char hex** strings. A "zone id" is not the domain name; a member id is the membership id, not the user id. Always resolve names to IDs first.
- **Timestamps**: ISO 8601 UTC.
- **Proxied vs DNS-only**: for DNS records, `"proxied": true` routes traffic through Cloudflare (orange cloud) and hides the origin IP; `false` is DNS-only (grey cloud). Changing this flag changes production traffic behaviour - treat it as a mutation that matters.

## Safety rails for writes

Cloudflare changes take effect on live production traffic within seconds - a bad DNS edit, an over-broad cache purge, or a firewall rule change can cause an outage. Before any `POST`/`PUT`/`PATCH`/`DELETE`:

- Confirm the exact zone/account and the exact record with the user; show the record(s) the filter matched, not just a count, when feasible.
- Default to dry-run: use `--dry-run` (or `CLOUDFLARE_READ_ONLY=1`) to preview, then act only on explicit confirmation.
- Be especially careful with: **DNS record edits/deletes** (can take a site offline or misroute mail - check `MX`/`TXT`/`SPF` before touching), **`proxied` flips** (exposes origin IP or breaks WAF coverage), **full cache purge** (`purge_everything` - prefer purging specific URLs/tags/hosts to avoid an origin load spike), **firewall/WAF rule and ruleset changes** (can lock out real users or open a hole), and **DNSSEC** toggles (can break resolution if the registrar DS record isn't kept in sync).
- Prefer least-privilege when helping create a token: grant only the specific permission groups and the specific zones/account the task needs (see `references/auth.md`), never the Global API Key for automation.
