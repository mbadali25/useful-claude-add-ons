# Authentication, regions, and headers

## Generating an API key

In the **Infinity Portal**: **Global Settings > API Keys > New**. Set the service to
**Email Security**. Copy the **Client ID** and **Secret Key** immediately - the secret is
shown only once and cannot be retrieved afterward. Keys are tied to one region.

## Getting a token

```
POST {host}/auth/external
Content-Type: application/json

{"clientId": "<CLIENT_ID>", "accessKey": "<SECRET_KEY>"}
```

The response wraps the bearer token (typically under `data.token`, with `data.expiresIn`
in seconds). The token lasts ~1 hour; cache it and refresh shortly before expiry. The
helper parses the token defensively and caches it.

## Regional hosts

All regions operate independently - you cannot reach one region's data via another's host,
and credentials are region-specific.

| Region | Host |
|---|---|
| USA | `https://cloudinfra-gw-us.portal.checkpoint.com` |
| Europe | `https://cloudinfra-gw.portal.checkpoint.com` |
| Canada | `https://cloudinfra-gw.ca.portal.checkpoint.com` |
| Australia | `https://cloudinfra-gw.ap.portal.checkpoint.com` |
| UK | `https://cloudinfra-gw.uk.portal.checkpoint.com` |
| UAE | `https://cloudinfra-gw.me.portal.checkpoint.com` |
| India | `https://cloudinfra-gw.in.portal.checkpoint.com` |

API base for every call: `{host}/app/hec-api/v1.0`. **This tenant is US.**

## Required headers on every API call

| Header | Value | Notes |
|---|---|---|
| `Authorization` | `Bearer <token>` | from `/auth/external` |
| `x-av-req-id` | a fresh UUID per request | **required** - calls fail without it |
| `Accept` | `application/json` | |
| `Content-Type` | `application/json` | on POST/PUT only |

## Response envelope

Most responses share this shape:

```
{
  "responseEnvelope": {
    "requestId": "...", "responseCode": 0, "responseText": "...",
    "recordsNumber": 1, "totalRecordsNumber": 1, "scrollId": "..."
  },
  "responseData": [ ... ]   // object on single GETs, array on searches
}
```

`responseCode` 0 = success. `scrollId` drives pagination (see the entity/event refs).

## Troubleshooting auth

- **401 on /auth/external** - wrong Client ID/Secret, or the key is from a different region than the host you are calling. Check `--region` first.
- **401 on an API call after a good token** - token expired; refresh and retry once (the helper does this automatically).
- **403** - the key's role lacks permission for that operation. Read operations may work while actions do not; validate with `check` (read-only) before attempting remediation.
