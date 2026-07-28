---
name: drata
description: Connect to and work with the Drata compliance-automation platform via its Public API — authenticate (API key or OAuth2), resolve the right regional host (US/EU/APAC), and pull or push controls, monitoring tests, personnel, users, policies, evidence, frameworks, risks, vendors, devices, assets, tickets, and audit-request data. Use this skill whenever the user mentions Drata, SOC 2 / ISO 27001 / HIPAA compliance automation in Drata, Drata monitors or controls, exporting evidence or personnel from Drata, framework readiness, or wants to script/report against public-api.drata.com — even if they don't say "API". Also use it when writing integrations, CI compliance gates, or one-off queries against the Drata API.
---

# Drata Public API

Automate and query Drata: compliance controls, monitoring tests, evidence, personnel/users, policies, frameworks, risks, vendors, devices, and assets. Everything is RESTful JSON over HTTPS against a regional `public-api.*.drata.com` host.

> Programmatic API access requires Drata's **Advanced plan or above** (Foundation tier has no API). Keys are **workspace-scoped** — a key made in one workspace can't read another.

## Quick start

1. **Pick the region host** — this is the #1 cause of silent auth failures. Match the customer's Drata data region:
   - US: `https://public-api.drata.com`
   - EU: `https://public-api.eu.drata.com`
   - APAC: `https://public-api.apac.drata.com`

   Never point at `app.drata.com` — that's the web app, not the API.
2. **Get credentials** (see `references/auth.md`) — either a long-lived **API key** (Settings → API Keys) or **OAuth2 client credentials** (Settings → OAuth Applications; recommended for prod/CI because tokens are short-lived and secrets rotate cleanly).
3. **Call the API** with `Authorization: Bearer <token>`.

## Helper script

`scripts/drata_client.py` is a self-contained Python client (stdlib only — no third-party packages) that handles both auth methods, region→host mapping, v1 **and** v2 pagination, `429` retry with `Retry-After`, and a read-only/dry-run guard. Use it instead of re-writing boilerplate:

```bash
export DRATA_API_KEY=drata_xxx            # or the DRATA_OAUTH_* vars
export DRATA_REGION=us                    # us | eu | apac (default us)

python scripts/drata_client.py whoami                                   # connectivity check
python scripts/drata_client.py get     /public/v2/controls --params 'workspaceId=1'
python scripts/drata_client.py get-all /public/v2/users                 # auto-paginate (cursor)
python scripts/drata_client.py get-all /public/personnel                # auto-paginate (offset/v1)
python scripts/drata_client.py post    /public/personnel --json '{"email":"a@b.com","firstName":"A","lastName":"B"}'
python scripts/drata_client.py put      /public/personnel/{id}/employment-status --json '{"isActive":false}' --dry-run
```

Set `DRATA_READ_ONLY=1` to block every mutating call, or pass `--dry-run` on a single mutation to print the exact request without sending it. Importable too: `from drata_client import DrataClient`.

## API versions — v2 vs v1

Drata runs two API versions side by side; **prefer v2** for new work (faster, richer objects, `expand` support).

| | Path prefix | Pagination | Notes |
|---|---|---|---|
| **v2** | `/public/v2/...` | **cursor**: read `pagination.cursor`, pass it back as `?cursor=`; stop when absent | Use `?expand=owners,customFields` to inline related objects. Resource names: `users`, `controls`, `vendors`, `risks`, `assets`, etc. |
| **v1** | `/public/...` | **offset**: `?page=1&limit=100` (max 100), loop until `page*limit >= total` | Response is `{ data, total, page, limit }`. Some resources use v1 names (e.g. `personnel`). |

`get_all` in the helper auto-detects which style the response uses, so you don't have to.

## API map — which reference to read

| Task | Reference file |
|---|---|
| Auth (API key + OAuth), regions, scopes, plan gate, secret handling | `references/auth.md` |
| Resource groups → endpoint paths, common query params, key object fields, workspace handling, evidence/document downloads | `references/api-map.md` |
| Recipes: framework readiness, failing monitor tests, personnel/evidence export, upload training evidence, CI compliance gate | `references/common-tasks.md` |

Read the relevant reference before writing calls — they carry the exact paths, filters, and object shapes.

## Universal conventions

- **Auth header**: `Authorization: Bearer <api_key_or_oauth_token>` on every request.
- **Rate limit**: 500 requests/minute per source IP. On `429`, honor `Retry-After` and back off (the helper does this). Throttle bulk exports.
- **Workspaces**: multi-workspace orgs must pass the target `workspaceId` on scoped reads and on all `POST`/`PUT` writes. Find it via the workspaces endpoint (see `references/api-map.md`).
- **Timestamps**: ISO 8601 UTC.
- **Document downloads** (policies, evidence): the endpoint returns a short-lived **signed URL**, not the file bytes. Fetch that URL separately to save the document.
- **Audit trail**: every write is recorded as its own event/entity in Drata, which is itself part of the customer's compliance record — so writes are visible to auditors.

## Safety rails for writes

Drata data *is* the customer's audit evidence, so mistaken writes have compliance consequences. Before any `POST`/`PUT`/`PATCH`/`DELETE`:
- Confirm the exact target and workspace with the user; show the records the filter matched, not just a count, when feasible.
- Default to dry-run: use `--dry-run` (or `DRATA_READ_ONLY=1`) to preview, then act only on explicit confirmation.
- Be especially careful with personnel employment-status changes, evidence deletion, and anything that flips a control/monitor state — these move compliance posture and are auditor-visible.
- Prefer least-privilege scopes when helping create a key or OAuth app: request only the read/write scopes the task needs.
