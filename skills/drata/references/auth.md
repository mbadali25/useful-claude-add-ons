# Drata API — Authentication

Programmatic access requires the **Advanced plan or above**. Every request carries
`Authorization: Bearer <token>`, where the token is either a long-lived API key or a
short-lived OAuth2 access token.

## Regional hosts (get this right first)

Requests must go to the host for the customer's Drata data region:

| Region | Base URL |
|---|---|
| US (default) | `https://public-api.drata.com` |
| EU | `https://public-api.eu.drata.com` |
| APAC | `https://public-api.apac.drata.com` |

Using the wrong region host, or `app.drata.com`, produces confusing `401`/`403`/`404`
errors even with a valid key. The helper maps `DRATA_REGION=us|eu|apac` to these hosts,
or you can override with `DRATA_BASE_URL`.

## Option A — API key (simplest)

1. In Drata: click your account (bottom-left) → **Settings → API Keys → Create API Key**.
2. Set **Name** (immutable once active), **Expiration** (12 months / Never / Custom — prefer a bounded expiry), optional **Allowed IP Addresses**, and **Scopes**.
3. **Scopes / Access**: `All read`, `All read and write`, or `Custom` (pick specific per-resource read/create/update/delete scopes — prefer this, least privilege).
4. Copy the key **immediately** — it is shown only once and cannot be retrieved again.
5. Keys are **per-workspace**. A key made in workspace A cannot read workspace B.

Revoking a key is **irreversible** and instantly breaks any integration using it.

```bash
curl https://public-api.drata.com/public/v2/company \
  -H "Authorization: Bearer $DRATA_API_KEY"
```

## Option B — OAuth2 client credentials (recommended for prod / CI)

Short-lived tokens, cleaner secret rotation, per-integration identity.

1. In Drata: **Settings → OAuth Applications → Create OAuth Application**.
2. Name it, choose expiration, and select **least-privilege scopes** (Read/Create/Update/Delete per resource category — Policies, Personnel & Devices, Evidence, etc.).
3. On creation Drata shows the **Client ID**, **Client Secret**, and a ready-to-run token cURL (with your tenant's `audience` and auth domain pre-filled). Store the secret in a vault — it is shown only once.
4. Mint an access token:

```bash
curl --request POST \
  --url https://<auth-domain>/oauth/token \
  --header 'content-type: application/json' \
  --data '{
    "client_id":"<CLIENT_ID>",
    "client_secret":"<CLIENT_SECRET>",
    "audience":"<API_AUDIENCE>",
    "grant_type":"client_credentials",
    "scope":"read:controls read:personnel"
  }'
# -> { "access_token": "eyJ...", "token_type": "Bearer", "expires_in": 86400 }
```

5. Use the `access_token` as the Bearer token until `expires_in` elapses, then mint a new one.

Best practice Drata recommends: one OAuth app per integration, separate apps per
environment (dev/stage/prod), least-privilege scopes, secrets in a manager, rotate
regularly, never share secrets across laptops.

## Feeding credentials to the helper script

```bash
# API key auth
export DRATA_API_KEY=drata_xxx
export DRATA_REGION=us

# OR OAuth2 client-credentials auth (takes precedence if all three core vars are set)
export DRATA_OAUTH_TOKEN_URL='https://<auth-domain>/oauth/token'
export DRATA_OAUTH_CLIENT_ID=...
export DRATA_OAUTH_CLIENT_SECRET=...
export DRATA_OAUTH_AUDIENCE=...
export DRATA_OAUTH_SCOPE='read:controls read:personnel'
```

## Secret hygiene

- Read credentials from env vars or a secrets manager; never hardcode, echo, or commit them.
- Don't print the token/key or the raw `Authorization` header in logs or output.
- Prefer bounded key expiry and least-privilege scopes; call this out when helping a user create credentials.

## Auth troubleshooting

| Symptom | Likely cause |
|---|---|
| `401`/`403` with a key you believe is valid | Wrong region host, or key expired/revoked, or missing scope for the resource |
| `404` on a record that exists | Key is scoped to a different workspace, or you're on the wrong region host |
| Works for reads, `403` on writes | Key/app has read scopes only — add create/update scopes |
| `429` | Rate limited (500/min/IP) — honor `Retry-After`, back off |
