# Dashboards — two distinct meanings, two mechanisms

"Create a dashboard" in Wazuh is ambiguous. Decide which one the user means *before* touching anything — they live on different hosts and have nothing in common.

| Meaning | Lives on | This skill's approach |
|---|---|---|
| **A dashboard inside the Wazuh web UI** (visualizations, saved searches, index patterns) | Dashboard host, port **443** (OpenSearch Dashboards saved objects) | Export/import ndjson via `dash-export` / `dash-import` — *dashboards-as-code* |
| **A standalone report** you send to someone (a file, no Wazuh login needed) | Anywhere — it's an HTML file | Pull data from the Indexer, then hand off to the `build-dashboard` skill |

## Part 1 — Web-UI dashboards (saved objects)

### Why export/import, not "generate from scratch"

Wazuh Dashboard objects reference each other by ID (a dashboard points at visualizations, which point at an index pattern). Hand-authoring that ndjson is brittle: a wrong or stale reference imports "successfully" but 404s when clicked. So the reliable pattern is **build once in the UI, then treat the exported ndjson as the source of truth**:

1. Build/curate the dashboard in the Wazuh UI on one box.
2. `dash-export` it to an `.ndjson` file.
3. Commit that file (version control = your rebuild path for legacy boxes).
4. `dash-import` it onto other boxes, or back onto the same box after a rebuild/upgrade.

This is the durable answer for legacy work: the ndjson *is* the dashboard, reproducible across environments.

### Connection — a THIRD credential set

The Dashboard is neither the Server API nor the Indexer. It needs its own login (a UI user with saved-objects permission — commonly `admin`, or a scoped user):

```bash
export WAZUH_DASHBOARD_URL="https://wazuh.example.local:443"
export WAZUH_DASHBOARD_USER="admin"
export WAZUH_DASHBOARD_PASSWORD="..."
# Multi-tenant deployments only: scope to a tenant (default = global)
export WAZUH_DASHBOARD_TENANT=""
```

If the deployment runs the Dashboard behind a reverse proxy with a `server.basePath` (see `/etc/wazuh-dashboard/opensearch_dashboards.yml`), include that base path in `WAZUH_DASHBOARD_URL` (e.g. `https://host/wazuh`).

### Commands

```bash
# See what exists, grab IDs
python scripts/wazuh_client.py dash-list --type dashboard
python scripts/wazuh_client.py dash-list --type visualization

# Full backup (dashboards + visualizations + searches + index-patterns, refs included)
python scripts/wazuh_client.py dash-export --out backup.ndjson

# Just specific types
python scripts/wazuh_client.py dash-export --out dashboards.ndjson --type dashboard --type visualization

# One specific dashboard by id (references pulled in automatically)
python scripts/wazuh_client.py dash-export --out one.ndjson --type dashboard --id <object-id>

# Import onto another box (overwrite resolves conflicts in place)
python scripts/wazuh_client.py dash-import backup.ndjson --overwrite

# Import as fresh copies instead (new IDs, no conflict resolution)
python scripts/wazuh_client.py dash-import backup.ndjson --new-copies
```

### API details (for hand-rolled calls or debugging)

- **Export**: `POST {dashboard}/api/saved_objects/_export`, JSON body `{"type": [...], "includeReferencesDeep": true}` or `{"objects":[{"type","id"}], ...}`. Returns ndjson (one object per line; the last line is an export-summary object).
- **Import**: `POST {dashboard}/api/saved_objects/_import` as `multipart/form-data` with a `file` field. Query: `overwrite=true` **or** `createNewCopies=true` (mutually exclusive).
- **Every write needs the `osd-xsrf: true` header** (renamed from `kbn-xsrf`). Missing it → `400 "Request must contain a osd-xsrf header"`. The helper adds it for you.
- `_import` returns `{"success":true/false,"successCount":N,"errors":[...]}`. **Always check `errors`** — a partial import is common and is where broken references surface.

### Gotchas

- **404 on an imported dashboard** = broken/stale object references, not a failed import. Re-export with references included (the helper defaults to `includeReferencesDeep`), or fix the reference IDs in the ndjson. Don't hand-edit IDs unless you know the target's index-pattern ID.
- **`wazuh-alerts-*` index-pattern conflict** on import is expected — the target usually already has it. `--overwrite` (or "Skip" in the UI) is safe here.
- **Version skew**: an ndjson exported from a newer Dashboard may not import cleanly into an older one. Match major.minor when moving objects between boxes (see `version-notes.md`).
- Saved objects are **per-tenant** on multi-tenant deployments — export and import against the same `WAZUH_DASHBOARD_TENANT`, or objects "vanish" (they're in a different tenant).

## Part 2 — Standalone HTML report from alert data

When the user wants something to *send* — a point-in-time report, not a login-gated UI dashboard — don't build UI objects. Pull the numbers from the Indexer and hand them to the `build-dashboard` skill.

### Pattern

1. **Aggregate in the Indexer** (use `"size": 0` + `aggs` so you get counts, not raw docs). Common cuts: alerts over time (`date_histogram` on `timestamp`), top rules (`terms` on `rule.description`), severity split (`terms`/`range` on `rule.level`), top agents (`terms` on `agent.name`), MITRE tactics (`rule.mitre.tactic`). See `indexer-api.md` for field names and aggregation shapes.

   ```bash
   python scripts/wazuh_client.py raw-search wazuh-alerts-* --body agg.json > result.json
   ```

2. **Reshape** the OpenSearch aggregation response into flat rows/series (pull `aggregations.<name>.buckets` → `{key, doc_count}` lists). Pre-aggregate; don't ship raw alerts into the browser.

3. **Hand off to `build-dashboard`**, passing the aggregated JSON as the data source. That skill owns the HTML/Chart.js/layout — this skill's job ends at delivering clean data. Don't reimplement charting here.

### Why the handoff, not a built-in report

Two skills each doing one job beats a SIEM client that also happens to render HTML. `build-dashboard` already handles KPI cards, filters, Chart.js, responsive/print layout, and data-size thresholds. Duplicating that inside a Wazuh client would rot independently and give a worse result. If `build-dashboard` isn't available, a minimal self-contained HTML file with embedded JSON is the fallback — but reach for the dedicated skill first.
