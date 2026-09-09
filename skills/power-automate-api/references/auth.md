# Authentication

## The rule that generates the table

A v2.0 scope is **the resource identifier URI plus `/.default`**.

```
scope = <resource URI> + "/.default"
```

If the resource URI already ends in `/`, the scope contains a double slash.
That is correct and not a typo — `https://service.flow.microsoft.com//.default`
is right precisely because the audience is `https://service.flow.microsoft.com/`.
Getting this wrong is the single most common failure against these APIs.

Derive the scope from the audience. Do not recall it.

## What the server itself says

The authoritative list comes from the API when you present the wrong token.
BAP rejected an `https://api.powerplatform.com` token with:

> It should exactly match (including forward slash) with one of the allowed
> audiences `https://service.powerapps.com/`, `https://management.core.windows.net/`,
> `https://management.azure.com/`, `https://service.flow.microsoft.com/`,
> `https://web.powerapps.com`, `https://apps.powerapps.com`,
> `https://api.bap.microsoft.com/`

Note that three of those carry a trailing slash and three do not. **When you get
an audience error, read the allowed list out of the error and derive the scope
from it** — that is faster and more reliable than any table, including this one.

## Table

| Endpoint | Audience | Scope to request | Status |
|---|---|---|---|
| `<org>.crm.dynamics.com/api/data/v9.2` | `https://<org>.crm.dynamics.com` | `https://<org>.crm.dynamics.com/.default` | **Verified** |
| `api.bap.microsoft.com` | `https://api.bap.microsoft.com/` | `https://api.bap.microsoft.com//.default` | From server error list |
| `api.flow.microsoft.com` | `https://service.flow.microsoft.com/` | `https://service.flow.microsoft.com//.default` | From server error list |
| `api.powerapps.com` | `https://service.powerapps.com/` | `https://service.powerapps.com//.default` | From server error list |
| `api.powerplatform.com` | `https://api.powerplatform.com` | `https://api.powerplatform.com/.default` | Newer plane; **rejected by BAP** |

`api.powerplatform.com` is the newer admin plane. It is **not** interchangeable
with BAP: a token minted for it is refused by `api.bap.microsoft.com` with
`InvalidAuthenticationAudience`. If a tool or MCP server is failing that way,
its scope config is the bug — not the tenant.

## Device code

Interactive user auth, no Azure subscription required. This is the fallback
when `az account get-access-token --resource <org>` fails with
*"No subscription found"* — which happens in any tenant with no Azure
subscription, and has nothing to do with Power Platform licensing.

```
POST https://login.microsoftonline.com/<tenant-id>/oauth2/v2.0/devicecode
Content-Type: application/x-www-form-urlencoded

client_id=04b07795-8ddb-461a-bbee-02f9e1bf7b46
&scope=https://<org>.crm.dynamics.com/.default offline_access
```

Poll the token endpoint with the returned `device_code` until it stops
returning `authorization_pending`:

```
POST https://login.microsoftonline.com/<tenant-id>/oauth2/v2.0/token

grant_type=urn:ietf:params:oauth:grant-type:device_code
&client_id=04b07795-8ddb-461a-bbee-02f9e1bf7b46
&device_code=<device_code>
```

Include `offline_access` or you get no refresh token and re-authenticate every
hour.

### Public clients

| Client id | What it is | Status |
|---|---|---|
| `04b07795-8ddb-461a-bbee-02f9e1bf7b46` | Azure CLI | **Verified** for Dataverse device-code |
| `51f81489-12ee-4a9e-aaae-a2591f45987d` | Commonly cited Dataverse sample client | Unverified — test before relying on it |
| `9cee029c-6210-4654-90bb-7b3e37e3b8c8` | Power Platform CLI | Unverified |

Only the first is proven. If a client id is not consented in the tenant you get
`AADSTS7000218` (missing `client_assertion`/`client_secret` — usually means the
app is not a permitted public client) or `AADSTS650057` (invalid resource for
that app). Both mean *this app*, not *your account*.

### SharePoint REST rejects most public clients

A correct token is not enough. SharePoint Online refuses tokens from apps that
only hold the generic `user_impersonation` delegated scope, whatever the
audience says:

```
HTTP 401  {"error":"invalid_request"}
x-ms-diagnostics: 3001003;
  reason="App is not allowed to call SPO with user_impersonation scope"
```

The Azure CLI client (`04b07795-…`) hits this, so the client that works for
Dataverse does **not** work for SharePoint REST. Re-authenticating changes
nothing — the block is on the app, not the account or the consent.

**Always read `x-ms-diagnostics` on a SharePoint 401.** The body is only
`{"error":"invalid_request"}`, which says nothing; that header carries the
reason code and turns a guessing game into a one-line diagnosis. `urllib` and
most HTTP clients discard response headers on an error unless you ask for them.

Use a client holding granular SPO scopes (`AllSites.FullControl`,
`Sites.ReadWrite.All`) via `--client-id`, or a certificate app-only identity
with `Sites.FullControl.All`, which SPO does accept.

### Never run device code from a tool call

It blocks on a prompt the harness cannot see, burns the full timeout, and drops
the cached scopes when cancelled. Print the code and URL and have the user
complete it in their own shell. Same applies to `Connect-MgGraph` and any
`az login`.

Device codes expire in about 15 minutes. A code from a previous session is
always dead — mint a fresh one rather than retrying an old one.

## Service principal (app-only)

Unattended alternative. **Unverified for `clientdata` writes** — app-only
identities can be refused where a user is allowed, so prove it on a throwaway
flow before depending on it.

1. Register an app; add a client secret or certificate.
2. Create a **Dataverse application user** for it in the target environment
   (Power Platform admin centre → Environment → Settings → Users + permissions
   → Application users) and give it a role with write on the `workflow` table.
   Without this step every call returns 401 no matter how good the token is.
3. Client-credentials grant against the same scopes above.

Step 2 is the one people skip. An app registration alone is not a Dataverse
identity.

## Conditional Access

A CA policy scoped to the app can block the device-code flow even when
everything above is right, and the failure reads like a consent problem. If
`az` and the device code both fail for one account but work for another, look
at CA before the app registration.

**Sign-in frequency caps the refresh token, not just the access token.** With a
sign-in-frequency policy in force, refreshing fails with:

```
AADSTS70043: The refresh token has expired or is invalid due to sign-in
frequency checks by conditional access. The token was issued on <t> and the
maximum allowed lifetime for this request is 14400
```

14400 seconds is four hours. `offline_access` does not extend it — so a long
session needs a genuinely new device-code sign-in every few hours, and any
plan that assumes "log in once, refresh silently all day" is wrong in such a
tenant. Cache the *resource* you signed in for: signing in for SharePoint does
not refresh the Dataverse token, and the failure surfaces later as "no cached
token" on a resource you thought you had.
