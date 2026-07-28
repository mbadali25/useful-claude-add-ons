---
name: checkpoint-email
description: Work with the Check Point Email Security API (formerly Harmony Email & Collaboration / Avanan) - authenticate via the Infinity Portal, resolve the regional CloudInfra host, search and inspect email entities and security events, triage phishing/malware/DLP/BEC detections, and remediate (quarantine, restore, dismiss, change severity) with a dry-run gate on every mutating action. Use this skill whenever the user mentions Check Point Email Security, Harmony Email & Collaboration, HEC, Avanan, a cloudinfra-gw.portal.checkpoint.com / hec-api endpoint, Office 365 or Gmail email protected by Check Point, quarantining or restoring a suspicious email, Check Point email events/entities/exceptions, or wants to query, triage, report on, or remediate anything in their Check Point email estate - even if they don't say "API" or "SMART API". Also use it when writing scripts or one-off queries against the hec-api, or when debugging 401/403/429 errors from a Check Point email gateway.
---

# Check Point Email Security API

Automate and query Check Point Email Security: search protected email entities, triage
security events (phishing, malware, DLP, BEC, spam), and remediate detections. All calls
are RESTful JSON over HTTPS against the regional CloudInfra gateway.

Note on names: the product is now **Check Point Email Security**. You will still see the
old names **Harmony Email & Collaboration (HEC)** and **Avanan** in the portal, in the API
host, and in the `hec-api` path. They are the same product.

## Quick start (the auth dance)

Every session follows the same pattern:

1. **Get a token** - `POST {host}/auth/external` with JSON body `{"clientId": ..., "accessKey": ...}`. The token is a bearer token, lives ~1 hour.
2. **Call the API** - send `Authorization: Bearer <token>`, `Accept: application/json`, and a **fresh `x-av-req-id` UUID on every request** (this header is required; omitting it fails the call) to `{host}/app/hec-api/v1.0/...`.
3. **Regions are isolated** - the `{host}` depends on the tenant's region, and credentials + data never cross regions. This tenant is **US**: `https://cloudinfra-gw-us.portal.checkpoint.com`.

The helper script does all three for you. Prefer it over hand-rolling calls.

## Credentials - handle with care

- Create an API key in the **Infinity Portal** under **Global Settings > API Keys**, with the service set to **Email Security**. You get a **Client ID** and a **Secret Key** (the secret is shown once - it cannot be retrieved later).
- Read credentials from env vars `CHECKPOINT_EMAIL_CLIENT_ID` / `CHECKPOINT_EMAIL_ACCESS_KEY` (or a secrets manager). Never hardcode them, never echo the secret or token to output, never commit them.
- Keys are **region-specific**. A US key only works against the US host. If auth 401s, check the region before anything else.

## Helper script

`scripts/checkpoint_email_client.py` is a self-contained client (stdlib + `requests`) that
handles auth, region resolution, the `x-av-req-id` header, `scrollId` pagination, 429/401
retry, async task polling, and the dry-run gate. Use it instead of re-writing boilerplate:

```bash
export CHECKPOINT_EMAIL_CLIENT_ID=... CHECKPOINT_EMAIL_ACCESS_KEY=...
export CHECKPOINT_EMAIL_REGION=us

# ALWAYS run this first against a live tenant - confirms auth AND access policy, read-only
python scripts/checkpoint_email_client.py check

python scripts/checkpoint_email_client.py entity <entityId>
python scripts/checkpoint_email_client.py search-entities --start 2026-07-01T00:00:00.000Z \
    --filter entityPayload.fromEmail is boss@evil.com
python scripts/checkpoint_email_client.py search-events --start 2026-07-20T00:00:00.000Z \
    --type phishing --severity High
python scripts/checkpoint_email_client.py action-entity --action quarantine --ids ID1 ID2          # dry-run
python scripts/checkpoint_email_client.py action-entity --action quarantine --ids ID1 ID2 --confirm # execute
python scripts/checkpoint_email_client.py task <taskId>
```

It can also be imported (`from checkpoint_email_client import CheckPointEmailClient`) when
building larger scripts for the user.

## API map - which reference to read

| Task | API path(s) | Reference file |
|---|---|---|
| Token, regions, required headers, credential setup | `/auth/external` | `references/auth.md` |
| Email entities: get one, search by sender/subject/attachment/etc., quarantine/restore | `/search/entity/{id}`, `/search/query`, `/action/entity` | `references/entities.md` |
| Security events: get one, search by type/severity/state, dismiss/severityChange/quarantine | `/event/{id}`, `/event/query`, `/action/event` | `references/events.md` |
| Allow/block lists (Whitelist/Blacklist) and per-engine exceptions | `/exceptions/{type}` | `references/exceptions.md` |

Read the relevant reference before writing calls - they contain the exact request bodies,
filter operators, `saasAttrName` fields, action names, and pagination details.

## Universal conventions

- **Entities vs events**: an **entity** is the object itself (an email); a **security event** is a detection about an entity (a phishing verdict). Actions exist on both surfaces - quarantining the *entity* removes the mail; acting on the *event* changes triage state (dismiss, severity). Pick the surface that matches the intent.
- **Pagination**: list endpoints return `responseEnvelope.scrollId`. To get the next page, resend the same query with that `scrollId` in the request body until it comes back empty. The helper's `search-*` commands do this automatically.
- **`responseData` shape**: single-item GETs sometimes return an object, searches return an array. The helper normalizes both to a list - do the same if hand-rolling.
- **Async actions**: `/action/entity` and `/action/event` return a `taskId` per target. The action is queued, not instant - poll `GET /task/{taskId}` (`status`: init | inprogress | completed | failed | stopped | paused).
- **Rate limits**: on `429`, honor `Retry-After` and back off. Anti-Phishing exceptions are limited to ~1 req/s; other exceptions ~10 req/s.
- **Timestamps**: ISO 8601 UTC with milliseconds, e.g. `2026-07-14T00:00:00.000Z`. `startDate` is required on both search endpoints.

## Safety rails for destructive actions

Quarantine, restore, delete, dismiss, severity changes, and allow/block-list edits change
production email security posture and what lands in users' mailboxes. This is why the
helper **defaults to dry-run** on `action-entity` / `action-event`:

- Without `--confirm`, the helper resolves each target ID, prints what it *is* (sender, subject, verdict/severity) and how many would be affected, and makes **no** change.
- Only with an explicit `--confirm` does it call the action endpoint.
- Before confirming a batch, show the user the resolved target list (subjects/senders), not just a count, so they can eyeball it.
- Never quarantine/delete or bulk-dismiss based only on an unreviewed search result. Restoring a wrongly-quarantined business email and deleting a real threat are both high-blast-radius - treat the confirm step as the real decision point.
- `restore` on a quarantined mail puts it back in the user's inbox: only do this on explicit instruction naming the specific message.
