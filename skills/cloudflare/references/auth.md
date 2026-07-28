# Authentication

Cloudflare v4 accepts two auth methods. **Always prefer a scoped API token.**

| | Scoped API Token | Legacy Global API Key |
|---|---|---|
| Header(s) | `Authorization: Bearer <token>` | `X-Auth-Email: <email>` + `X-Auth-Key: <key>` |
| Scope | Only the permissions + zones/accounts you grant | Root-equivalent over the entire account |
| Revocable individually | Yes | No (rotating it breaks everything) |
| Env var(s) | `CLOUDFLARE_API_TOKEN` | `CLOUDFLARE_EMAIL` + `CLOUDFLARE_API_KEY` |
| Use for automation | **Yes** | Avoid |

Never send both on one request. The client picks the token if both are set.

## Verify before doing anything

The single fastest way to catch a bad key, expired token, or wrong scope:

```bash
export CLOUDFLARE_API_TOKEN=xxxxx
python scripts/cloudflare_client.py verify        # GET /user/tokens/verify
```

A healthy token returns `{"result": {"id": "...", "status": "active"}, "success": true}`.
The Global API Key has no `verify` endpoint; test it with a cheap read such as
`get /zones --params per_page=1` instead.

## Creating and scoping a token

Dashboard: **My Profile -> API Tokens -> Create Token** (or use the "Create Custom
Token" template). A token is built from:

- **Permission groups** - `(scope, resource, level)` triples, e.g. `Zone / DNS / Edit`,
  `Zone / Zone Settings / Read`, `Account / Workers Scripts / Edit`. Grant only what
  the task needs.
- **Zone/account resources** - restrict to specific zones or one account, not "all
  zones from all accounts".
- **Optional guards** - client IP filtering and a TTL (expiry). Use both for CI tokens.

Permission group IDs can be listed programmatically:

```bash
python scripts/cloudflare_client.py get /user/tokens/permission_groups --params per_page=100
```

Minting a least-privilege token via API is a `POST /user/tokens` - see
`common-tasks.md` for a worked "read-only DNS auditor" example.

## Least-privilege quick picks

| Task | Grant (nothing more) |
|---|---|
| Read DNS for reporting | Zone / DNS / Read on the target zones |
| Manage DNS records | Zone / DNS / Edit on the target zones |
| Purge cache | Zone / Cache Purge / Purge on the target zones |
| WAF custom rules | Zone / Zone WAF / Edit (or account-level Rulesets) |
| Workers deploy | Account / Workers Scripts / Edit on the one account |

## Secret handling

- Pass credentials via **environment variables**, never as CLI flags in shared shells
  or committed scripts (flags land in shell history and `ps` output).
- Never print the token; the client never echoes it.
- Rotate CI tokens on a schedule and scope them to a client IP where possible.
- The Global API Key cannot be scoped - if you find automation using it, treat
  replacing it with a scoped token as the fix, not a nice-to-have.
