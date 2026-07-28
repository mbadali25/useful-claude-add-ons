# Authentication, credentials, RBAC & TLS

## Server (Manager) API — JWT

All Server API endpoints except the login endpoint require a JSON Web Token (JWT).

### Get a token

```bash
TOKEN=$(curl -sk -u "$WAZUH_API_USER:$WAZUH_API_PASSWORD" \
  -X POST "https://<HOST>:55000/security/user/authenticate?raw=true")
```

- `?raw=true` returns the bare token string (no JSON wrapper) — convenient for shell.
- Without `raw`, the token is at `.data.token` in the JSON response.
- Use it on every subsequent call: `-H "Authorization: Bearer $TOKEN"`.

### Token lifetime

- Default **900 seconds (15 minutes)**. When it expires you get `401`; re-authenticate.
- The helper (`wazuh_client.py`) caches the token, refreshes ~60s early, and re-auths automatically on a 401 — so long-running scripts don't need to manage this.
- Change the lifetime with `PUT /security/config` `{"auth_token_exp_timeout": <seconds>}`.
  **Any change to security config immediately revokes all outstanding tokens** — every session must re-authenticate afterward.

### Credentials — where they come from

- The Server API user is **not** the same as the Indexer user. The dashboard connects with a Server API user (commonly `wazuh-wui`) defined in the API users list.
- Default install credentials are `wazuh:wazuh` (and `wazuh-wui:wazuh-wui` for the dashboard user) — these should have been changed on any real deployment. If a user is stuck, that's a common cause.
- API users and roles are managed under `/security/users`, `/security/roles`, `/security/policies`, `/security/rules` (Server API) or in the dashboard under **Security**.
- Read credentials from environment variables or a secrets manager. Never hardcode, echo the token/secret, or commit them.

### RBAC

Wazuh enforces role-based access control on the Server API. A call can return `4000`-series errors when the user's role lacks the action/resource permission. If a read works but a write is denied, it's almost certainly RBAC — check the user's roles/policies rather than assuming the endpoint is wrong. Wazuh 5.0 revamped RBAC and includes an upgrade path for 4.x policies, so a freshly upgraded cluster may have different effective permissions than before.

## Indexer API — basic auth

The Indexer is OpenSearch under the hood. Authenticate with an OpenSearch user (commonly `admin`, or a scoped role) via HTTP basic auth:

```bash
curl -sk -u "$WAZUH_INDEXER_USER:$WAZUH_INDEXER_PASSWORD" \
  "https://<HOST>:9200/wazuh-alerts-*/_search" -H 'Content-Type: application/json' -d @query.json
```

The Indexer can also be configured to accept the Server API's JWT (the `authc` JWT domain in `/etc/wazuh-indexer/opensearch-security/config.yml`), but basic auth with an indexer user is the reliable default for scripting. Indexer users/roles are separate from Server API RBAC.

## TLS on-prem

On-prem Wazuh ships with a self-signed internal CA (`root-ca.pem`) generated at install. Options, best first:

1. **Trust the CA** — point `WAZUH_CA_BUNDLE` (or `curl --cacert`) at the deployment's `root-ca.pem`. Verification stays on.
2. **Disable verification** (`curl -k`, `requests verify=False`) — fine for a quick internal diagnostic, but say so; don't leave it in a durable script for production.

If the user hits `SSL: CERTIFICATE_VERIFY_FAILED`, it's the self-signed cert — get them the CA bundle rather than reflexively disabling verification.
