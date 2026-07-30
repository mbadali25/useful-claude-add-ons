# Authentication and bootstrap

Base URL: `https://api.meraki.com/api/v1`

## Getting a key

Dashboard → **My Profile** → **API access** → *Generate new API key*. The key is
shown once. Two consequences worth stating plainly:

- **The key inherits that Dashboard user's permissions.** There is no separate API
  RBAC layer. A key minted by a full-org admin is a full-org admin key.
- Therefore: create a **dedicated service account** with the least privilege the
  work needs (read-only where possible) and mint the key from that account, rather
  than from a human admin's profile.

A user may hold at most two keys, which is what makes rotation possible: generate
the second, cut over, revoke the first.

## Enabling org-level API access

Organization → **Settings** → **Dashboard API access** → *Enable access to the
Cisco Meraki Dashboard API*.

**This is the misdiagnosis trap.** When org API access is disabled, calls fail with
a `401`/`404` that reads exactly like a bad key. Before concluding the key is
wrong, confirm the org toggle is on. A valid key against an API-disabled org and an
invalid key against an API-enabled org are hard to tell apart from the response
alone.

## Headers

```
Authorization: Bearer <key>
Content-Type: application/json
Accept: application/json
```

Meraki also still accepts the legacy `X-Cisco-Meraki-API-Key: <key>` header. This
skill does **not** send it — `meraki_http.py` sends `Authorization: Bearer` only.
If you see the legacy header in an old runbook, it is not evidence this skill is
misconfigured.

The key is read from the `MERAKI_DASHBOARD_API_KEY` environment variable and from
nowhere else. There is deliberately no `--api-key` flag: a flag ends up in shell
history, in transcripts, and in chat logs.

## The bootstrap sequence

Four calls establish everything else:

| Call | Resolves |
|---|---|
| `GET /organizations` | validates the key; yields `organizationId` |
| `GET /organizations/{organizationId}/networks` | network id → name/productTypes map |
| `GET /organizations/{organizationId}/devices` | serial → model/network map |
| `GET /organizations/{organizationId}/devices/statuses` | online / offline / alerting / dormant |

`meraki_client.py` caches all four under `.meraki-snapshots/` so a working session
costs four calls total rather than four per question.

If `GET /organizations` returns more than one org, the client **refuses to guess**
and asks. This skill is scoped to one organization at a time; silently picking the
first would be the kind of error you only notice after writing to the wrong tenant.

## Rate limiting

**10 requests/second per organization**, enforced as a token bucket (short bursts
above the average are tolerated; sustained excess is not). There is a separate,
higher per-key ceiling across orgs.

Over the limit returns **`429 Too Many Requests`** with a **`Retry-After`** header
in seconds. `meraki_http.py` honors `Retry-After` and otherwise backs off
exponentially with jitter.

Do not defeat this by running several invocations in parallel — the limit is
server-side and per-org, so parallelism converts a slow success into a fast
failure.

## Redirects need a method-preserving handler

Meraki may answer with a **`308 Permanent Redirect`** to a region/shard host (for
example `api.meraki.com` → a shard endpoint). Python's default
`urllib` redirect handling is wrong for this in two ways:

1. It can downgrade a `POST` to a `GET` on redirect, which silently turns a write
   into a read that appears to succeed.
2. It can drop the `Authorization` header on a cross-host hop, producing a
   confusing `401` at the new host.

`meraki_http.py` installs a redirect handler that preserves both the method and the
body, and re-attaches the auth header for `*.meraki.com` hosts only.

## Errors

Error bodies are `{"errors": ["...", "..."]}` — a list, not a string. Render every
element; Meraki frequently puts the actionable part in the second entry.

Every response carries **`X-Request-Id`**. Capture it and quote it verbatim when
opening a case with Meraki support — without it they cannot trace the call.

Common statuses:

| Status | Usual cause |
|---|---|
| `400` | malformed payload, or a timespan beyond the endpoint ceiling |
| `401` | bad key — **or** org API access disabled (see above) |
| `403` | key valid but the underlying Dashboard account lacks permission |
| `404` | wrong id — **or** a missing `productType` on a combined network's event log |
| `429` | rate limited; honor `Retry-After` |
