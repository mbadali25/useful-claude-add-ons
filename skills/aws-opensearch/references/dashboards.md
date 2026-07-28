# Dashboards & saved objects

OpenSearch Dashboards objects — dashboards, visualizations, index-patterns, saved searches — are managed through the **saved-objects API** on the *same domain endpoint*, under a path prefix (SigV4-signed like everything else).

## Path & headers — the three things people get wrong
| Thing | Value | Why |
|---|---|---|
| Path prefix | `/_dashboards/api/saved_objects/...` | OpenSearch domains. **Legacy Elasticsearch domains** use `/_plugin/kibana/...` + `kbn-xsrf` — set `OPENSEARCH_DASHBOARDS_PATH=/_plugin/kibana` if so |
| `osd-xsrf: true` header | **mandatory** on every saved-objects call | without it you get `400 Bad Request` |
| `securitytenant: <name>` header | targets a tenant | omit → **global** tenant. Objects created in the wrong tenant "vanish" (they're just in another tenant) |

The client sends `osd-xsrf` automatically and adds `securitytenant` when you pass `--tenant`. All three are signed as part of SigV4 `SignedHeaders`.

## The workflow that keeps you sane: export → edit → import
Do **not** hand-author dashboard saved-object JSON from scratch — the panelsJSON/references structure is fiddly and easy to corrupt. Instead:

1. Build or tweak the dashboard once in the UI (or start from an existing one).
2. Export it as NDJSON:
   `dashboards-export --objects dashboard:<id> --out ops.ndjson`
   (or by type: `dashboards-export --type dashboard visualization index-pattern --out all.ndjson`). `includeReferencesDeep` is on, so dependencies (visualizations, index-patterns) come along.
3. Edit the NDJSON in version control — titles, queries, filters, colors, saved-search DSL. Keep it in git; this is your source of truth and your backup.
4. Import into the same or another domain/tenant:
   `dashboards-import --body ops.ndjson --overwrite --tenant team-a` (dry-run first — it shows the object count and type breakdown).

This also covers **copying dashboards between domains** and **CI/CD** promotion (dev → prod domain).

## Editing individual objects
- Find IDs: `saved-object-find --type dashboard` (or `--search "title fragment"`).
- Inspect one: `saved-object-get dashboard <id>`.
- Small programmatic edits: pull with `saved-object-get`, change the `attributes`, and re-apply via an `_import` of a one-line NDJSON (with `--overwrite`). Prefer this over a raw `PUT` so references stay consistent.
- Remove: `saved-object-delete visualization <id> --confirm` (deleting an object that others reference will break those dashboards — check references first).

## Index-pattern references are the usual gotcha
A dashboard references visualizations, which reference an **index-pattern by its saved-object id**. When importing into a *different* domain, that index-pattern id must exist there (or be in the same NDJSON). If panels show "index pattern not found", export **with** the index-pattern object, or recreate/remap it, then re-import.

## When direct API signing won't work
If the domain gates Dashboards behind **Cognito or SAML**, a SigV4-signed call to `/_dashboards/api/...` may bounce to a login/redirect instead of the API. In that case use the **master-user basic-auth** path (log in to get a cookie, then send the cookie) — see `references/auth.md` — or drive the export/import from a session that already holds the Dashboards cookie.
