# Authentication, Whoami, and Tenant Resolution

## 1. Obtain a bearer token

```
POST https://id.sophos.com/api/v2/oauth2/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&client_id={CLIENT_ID}&client_secret={CLIENT_SECRET}&scope=token
```

Response:

```json
{
  "access_token": "eyJ...",
  "expires_in": 3600,
  "refresh_token": "...",
  "token_type": "bearer"
}
```

- Cache the token and reuse it until ~5 minutes before `expires_in`; don't request a new token per call (the token endpoint is rate limited).
- curl example:

```bash
curl -s -X POST https://id.sophos.com/api/v2/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&client_id=$SOPHOS_CLIENT_ID&client_secret=$SOPHOS_CLIENT_SECRET&scope=token"
```

## 2. Whoami — discover who the credential belongs to

```
GET https://api.central.sophos.com/whoami/v1
Authorization: Bearer {token}
```

Response (tenant credential):

```json
{
  "id": "57ca9a6b-885f-4e36-95ec-290548c26059",
  "idType": "tenant",
  "apiHosts": {
    "global": "https://api.central.sophos.com",
    "dataRegion": "https://api-us01.central.sophos.com"
  }
}
```

- `idType` is `tenant`, `organization`, or `partner`.
- **Tenant**: use `apiHosts.dataRegion` as the base URL for all tenant APIs, with headers `Authorization: Bearer {token}` and `X-Tenant-ID: {id}`.
- Data regions include us01, us02, us03, eu01, eu02, ca01, au01, in01, ja01, br01 — never guess; always take the host from whoami or the tenant listing.

## 3. Partner and organization credentials

Partner/org credentials can't call tenant APIs directly — first enumerate tenants from the **global** host:

```
# Partner
GET https://api.central.sophos.com/partner/v1/tenants?pageTotal=true
Authorization: Bearer {token}
X-Partner-ID: {id from whoami}

# Organization
GET https://api.central.sophos.com/organization/v1/tenants?pageTotal=true
Authorization: Bearer {token}
X-Organization-ID: {id from whoami}
```

Each tenant item includes `id`, `name`, `dataGeography`, `dataRegion`, and `apiHost`. Then call tenant APIs:

```
GET {tenant.apiHost}/endpoint/v1/endpoints
Authorization: Bearer {token}
X-Tenant-ID: {tenant.id}
```

Notes:
- Tenant listings paginate by offset (`page`, `pageSize` up to 100).
- Some tenants show `"status": "inactive"` or lack an `apiHost` — skip them gracefully.
- When iterating many tenants, throttle (e.g. a few requests/second) to avoid partner-level 429s.

## 4. Common auth failures

| Symptom | Likely cause |
|---|---|
| 401 on token endpoint | Wrong client id/secret, or secret regenerated in Central |
| `Unauthorized` on tenant API with valid token | Missing/wrong `X-Tenant-ID`, or calling the wrong regional host |
| 403 | Credential role too weak (e.g. ReadOnly attempting POST actions) |
| 451 | Data-geography restriction — call the tenant's own `apiHost` |

## 5. Credential roles (set at creation in Central Admin)

- **Service Principal ReadOnly** — GETs only.
- **Service Principal Management** — most endpoint/common management actions.
- **Service Principal Super Admin** — everything, including sensitive settings.
Recommend the least role that covers the task.
