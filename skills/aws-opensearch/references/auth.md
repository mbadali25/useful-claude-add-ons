# Auth: SigV4 for Amazon OpenSearch Service

## The model in one line
Every request to a managed domain is signed with **SigV4** using an **IAM principal's** credentials, service name **`es`**, in the domain's **region**. The domain's **access policy** decides which principals may reach the endpoint at all; if **fine-grained access control (FGAC)** is on, the principal (or backend role) must *also* be mapped to an OpenSearch role with the right index/cluster permissions.

Two independent gates, both must pass:

| Gate | Where it lives | Failure looks like |
|---|---|---|
| Domain access policy (IAM) | AWS console → domain → Security config | `403` with `"User: arn:... is not authorized to perform: es:ESHttp..."` |
| Fine-grained access control | OpenSearch Security plugin (roles/role-mappings) | `403` with `security_exception` / `no permissions for [indices:...]` |

## Credential resolution
The client uses botocore's default chain, in order: env vars → shared config/credentials profile (`AWS_PROFILE`) → container/instance IAM role. Set exactly one clearly:

```bash
# Option A: named profile
export AWS_PROFILE=infra-readonly
export AWS_REGION=eu-west-1

# Option B: explicit keys (temporary creds need the session token too)
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_SESSION_TOKEN=...        # required for STS/assumed-role creds
export AWS_REGION=eu-west-1
```

Temporary credentials (assumed role, SSO) **must** include `AWS_SESSION_TOKEN` — SigV4 folds it into the signature. A missing/expired token is a common `403`/`security_exception`.

## Diagnosing a 403 (decision order)
1. Read the message body. `not authorized to perform: es:ESHttp*` → **access policy** problem (IAM side). `security_exception` / `no permissions for` → **FGAC** problem (OpenSearch role side).
2. Confirm the caller identity: `aws sts get-caller-identity`. Is that ARN actually in the access policy / mapped in FGAC?
3. Check region matches the domain's region (wrong region = signature won't validate → often `403`).
4. Assumed-role creds without `AWS_SESSION_TOKEN`? Add it.
5. Clock skew > 5 min on the calling host breaks SigV4 — sync time.

## Fine-grained access control mapping
If FGAC is enabled, being allowed by the IAM access policy is not enough. In OpenSearch Dashboards → Security → Roles → *Mapped users*, map the IAM role/user ARN (as a **backend role**) to a role such as a custom read/write role or `all_access` (avoid `all_access` for anything but break-glass). Programmatically this lives under `/_plugins/_security/api/rolesmapping/<role>` — reachable via `raw` if your principal has security-admin rights.

## Master-user (basic auth) variant
Some domains use FGAC with an **internal master user** (username/password) instead of IAM. If that's the setup, SigV4 is not used for the data plane — send HTTP Basic auth instead:

```python
import requests
resp = requests.get(f"{endpoint}/_cluster/health", auth=(user, password), timeout=30)
```

Keep the master password in an env var / secrets manager, never in code. Prefer IAM+FGAC role-mapping over sharing the master user.

## OpenSearch Serverless (`aoss`) — not this skill's default
Serverless *collections* (`*.aoss.amazonaws.com`) sign with service name **`aoss`**, require the `x-amz-content-sha256: UNSIGNED-PAYLOAD` header semantics botocore applies for that service, and use **data access policies** instead of a domain access policy. If the target is Serverless: `OpenSearchClient(service="aoss")`. Cluster-level APIs (`_cluster/*`, `_cat/*`, snapshots) largely don't exist on Serverless — much of the remediation surface here is managed-domain-only.

## Least privilege
For read-only work, an IAM policy allowing `es:ESHttpGet` / `es:ESHttpHead` on `arn:aws:es:<region>:<acct>:domain/<name>/*` plus a read-only FGAC role is enough. Add `es:ESHttpPost/Put/Delete` only for the remediation commands, and prefer a separate elevated profile you opt into for changes.
