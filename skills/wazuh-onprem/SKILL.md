---
name: wazuh-onprem
description: Work with a self-hosted / on-premises Wazuh deployment across all its surfaces — Server API :55000 (JWT; agents, rules, decoders, active response, RBAC), Indexer API :9200 (OpenSearch DSL; search/aggregate alerts), Dashboard saved-objects API :443 (export/import dashboards as ndjson), and the manager's ossec.conf over SSH (notification integrations like Slack/PagerDuty, active-response automation/runbooks, and onboarding new log feeds like Office 365 or Cloudflare). Use this skill whenever the user mentions Wazuh, a Wazuh manager/server/indexer/dashboard/agent, wazuh-alerts, rule levels/decoders, active response, or wants to query, report on, back up, migrate, or automate anything in their on-prem Wazuh estate — even without saying "API". Also use it to build/export/import dashboards, wire up Slack/PagerDuty/webhook alerting, write incident-response runbooks, onboard O365/Cloudflare/other feeds, or script against ports 55000/9200/443/22 on a Wazuh host.
---

# On-premises Wazuh

Wazuh is an open-source security platform (XDR + SIEM). A self-hosted install exposes **three separate APIs, each with its own port and credential set** — knowing which one a task needs is the whole game:

| API | Default port | Auth | Use it for |
|---|---|---|---|
| **Server / Manager API** | `55000` (HTTPS) | JWT (bearer) | Agents, rules, decoders, groups, active response, manager/cluster config, RBAC, agent enrollment/keys |
| **Indexer API** | `9200` (HTTPS) | Basic auth (OpenSearch user) | Searching and aggregating **alert & event data** (`wazuh-alerts-*` and, in 5.x, per-category data streams) |
| **Dashboard saved-objects API** | `443` (HTTPS) | Dashboard login (`osd-xsrf` header) | Export/import **visualizations & dashboards** as ndjson (dashboards-as-code) |
| **Manager config over SSH** | `22` (SSH) | SSH key | Editing `ossec.conf`: notification **integrations**, **active-response**/runbooks, new **log feeds** (O365, Cloudflare, etc.) — no API exists for most of this on-prem |

Rule of thumb: *"what is Wazuh configured to do / what agents exist / take an action"* → Server API. *"what did Wazuh detect / show me alerts / count events"* → Indexer API. *"back up / move / create a dashboard or visualization"* → Dashboard API (`references/dashboards.md`). *"notify me / add a runbook / onboard a new log source"* → SSH into the manager (`references/manager-config.md`, `integrations.md`, `runbooks.md`, `log-sources.md`).

## Connection setup — always establish this first

On-prem deployments vary in hostname, ports, and TLS, so confirm the target before making calls. All configuration comes from environment variables (never hardcode credentials or tokens):

```bash
# Server (Manager) API
export WAZUH_API_URL="https://wazuh.example.local:55000"
export WAZUH_API_USER="wazuh-wui"
export WAZUH_API_PASSWORD="..."

# Indexer API (separate credentials!)
export WAZUH_INDEXER_URL="https://wazuh.example.local:9200"
export WAZUH_INDEXER_USER="admin"
export WAZUH_INDEXER_PASSWORD="..."

# Dashboard API — only needed for dashboard export/import (a THIRD credential set)
export WAZUH_DASHBOARD_URL="https://wazuh.example.local:443"
export WAZUH_DASHBOARD_USER="admin"
export WAZUH_DASHBOARD_PASSWORD="..."

# TLS: on-prem is almost always self-signed. Point this at the deployment's
# root-ca.pem so verification stays ON. If unset, the client disables
# verification and warns — acceptable for a quick internal check, not for prod.
export WAZUH_CA_BUNDLE="/path/to/root-ca.pem"

# SSH to the manager — only needed for integrations/runbooks/log-feed work
# (editing ossec.conf; see references/manager-config.md)
export WAZUH_SSH_HOST="wazuh-manager.example.local"
export WAZUH_SSH_USER="ops"                     # needs sudo over /var/ossec/etc and the service
export WAZUH_SSH_KEY_PATH="/path/to/id_ed25519"  # key-based auth strongly preferred
```

**Reachability caveat**: `manager_config.py` shells out to local `ssh`/`scp`. If this session runs in a sandbox with no route to the on-prem network, those calls will fail to connect — that's expected, not a bug. Either run the script from a host that can reach the manager, or confirm this session has real network access before relying on it. Always verify with a trivial `ssh ... true` before building on top of it.

If the user hasn't told you the host/ports, ask — don't assume `localhost`. If they haven't set credentials, point them at where to get them (see `references/auth.md`).

## Helper script — use it instead of rewriting boilerplate

`scripts/wazuh_client.py` (stdlib + `requests`) handles JWT auth **with automatic renewal** (tokens live 900s and it re-auths on 401), the Server API response envelope, `limit`/`offset` pagination, self-signed TLS, and Indexer `_search`. Prefer it over hand-rolled curl:

```bash
python scripts/wazuh_client.py info                              # GET / (server info + version)
python scripts/wazuh_client.py agents-summary                   # agent status counts
python scripts/wazuh_client.py get /agents --params 'status=active&limit=100'
python scripts/wazuh_client.py get-all /agents                  # auto-paginate every agent
python scripts/wazuh_client.py put /active-response --json '{"command":"restart-wazuh0","agents_list":["001"]}'
python scripts/wazuh_client.py search wazuh-alerts-* --level 10 --since 24h   # high-sev alerts
python scripts/wazuh_client.py raw-search wazuh-alerts-* --body query.json    # full Query DSL
python scripts/wazuh_client.py indices                          # _cat/indices wazuh-alerts-*
python scripts/wazuh_client.py dash-list --type dashboard       # list saved dashboards (id+title)
python scripts/wazuh_client.py dash-export --out backup.ndjson  # export saved objects (as-code)
python scripts/wazuh_client.py dash-import backup.ndjson --overwrite   # import onto another box
```

It also imports cleanly for larger scripts: `from wazuh_client import WazuhClient`.

For integrations, runbooks, and new log feeds — anything that means editing `ossec.conf` — use `scripts/manager_config.py` instead (SSH-based, not HTTP):

```bash
python scripts/manager_config.py diff --block new_block.xml            # preview, touches nothing
python scripts/manager_config.py apply --block new_block.xml           # backup, validate, install — no restart
python scripts/manager_config.py apply --block new_block.xml --restart # ...and restart the manager
python scripts/manager_config.py list-backups
python scripts/manager_config.py rollback --backup /var/ossec/etc/ossec.conf.bak.<timestamp>
```

See `references/manager-config.md` for the full safe-edit flow before using this.

## Which reference to read

Read the relevant file **before** writing calls — each has the exact endpoints, parameters, and payloads:

| Task | Reference |
|---|---|
| Getting a JWT, credentials, RBAC, TLS/cert handling, where creds come from | `references/auth.md` |
| Server API: agents, rules, decoders, groups, active response, manager/cluster config, syscheck | `references/server-api.md` |
| Indexer API: OpenSearch Query DSL, alert fields, aggregations, time ranges, common queries | `references/indexer-api.md` |
| Dashboards: export/import saved objects (as-code) on port 443, or build an HTML report from alert data | `references/dashboards.md` |
| SSH mechanics for editing ossec.conf: backup/validate/install/restart/rollback flow | `references/manager-config.md` |
| Notification integrations: Slack, PagerDuty, custom webhook | `references/integrations.md` |
| Onboarding new log feeds: Office 365 / ms-graph (native), Cloudflare (custom bridge) | `references/log-sources.md` |
| Runbooks: static playbooks + persistent/ad-hoc active response | `references/runbooks.md` |
| Differences between Wazuh 4.x and 5.x (removed endpoints, data streams, no more Filebeat) | `references/version-notes.md` |

## Version matters — check it before assuming endpoints

Wazuh 4.x and 5.x differ enough that guessing breaks things. **Detect the version first** with `python scripts/wazuh_client.py info` (the `data.api_version` / manager version tells you the line), then consult `references/version-notes.md`. Key gotchas: 5.0 removed the inventory (`/syscollector`) and legacy security-config API endpoints, dropped Filebeat in favor of the indexer-connector, revamped RBAC, and moved to per-category data streams (so `wazuh-alerts-*` is no longer the only index pattern that matters).

## Server API conventions

- **Response envelope**: `{"data": {"affected_items": [...], "total_affected_items": N, "failed_items": [...], "total_failed_items": M}, "message": "...", "error": 0}`. Always check `error` and `total_failed_items` — bulk agent operations routinely succeed for some IDs and fail for others. The helper surfaces `failed_items` as a warning.
- **Pagination**: `limit` (max **500**) + `offset`. Use `get-all` to iterate.
- **Filtering**: `q=` accepts Wazuh Query Language (e.g. `q=status=active;os.platform=windows`); `search=` does substring search; `select=` trims returned fields; `sort=` orders (prefix `-` for descending).
- **Token lifetime**: 900s default. Changing any security config **revokes all existing tokens** — re-auth after such a change.

## Indexer API conventions

- Standard OpenSearch: `POST /{index}/_search` with Query DSL. Time field is `timestamp`; severity is `rule.level` (0–15, higher = more severe); `rule.groups`, `rule.mitre.*`, `agent.name`, `data.*` are the common filter fields.
- Use `"size": 0` with `aggs` for counts/top-N without hauling back documents.
- Respect `search.max_buckets` on large aggregations; page large result sets with `search_after` or the scroll/PIT API rather than deep `from`/`size`.

## Dashboards — disambiguate first

"Create/build a dashboard" means one of two unrelated things. Ask (or infer from context) which before acting — full detail in `references/dashboards.md`:

- **A dashboard in the Wazuh web UI** → it's a *saved object* on the Dashboard host (443). Don't hand-author the ndjson (inter-object references break → 404s). Build it once in the UI, `dash-export` to ndjson, version-control it, `dash-import` onto other boxes. That ndjson is the reproducible artifact — the right answer for legacy rebuilds and migrations.
- **A standalone HTML report to send someone** → aggregate the numbers from the Indexer (`"size":0` + `aggs`), then hand the JSON to the `build-dashboard` skill, which owns the rendering. Don't build charting into this skill.

## Integrations, runbooks, and new log feeds — disambiguate, then go SSH

These three all share one mechanism (SSH-edit `ossec.conf`, see `references/manager-config.md`) but need different content:

- **"Notify me when X happens"** → `references/integrations.md` (Slack/PagerDuty/webhook `<integration>` blocks)
- **"Write a runbook for X"** → `references/runbooks.md` — build the static playbook first; only add automated active-response if the user confirms specific rule IDs and an action safe to run unattended
- **"Add O365/Cloudflare/[new source] as a feed"** → `references/log-sources.md` — O365 is a native module (config + Azure app registration); Cloudflare has no native module and needs a custom collector script — say so, don't imply parity

## Safety rails for actions that change security posture

The Server API can restart agents, run active-response commands (which may block IPs or kill processes on endpoints), delete agents, edit rules/decoders, and change manager config. Before executing any write/action:

- Confirm the exact target set with the user — show the matched agent names/IDs, not just a count, when feasible.
- Default to dry-run: list what *would* be affected first, then act only on explicit confirmation.
- Never run fleet-wide active response, delete agents, or push rule/config changes without an explicit instruction that names the scope.
- Deleting Indexer documents/indices is destructive and unrecoverable — confirm the index pattern and time range out loud first.
- `dash-import --overwrite` replaces existing saved objects in place — on a live box this can clobber curated dashboards. Confirm the target and prefer exporting a backup of the destination first; use `--new-copies` when unsure.
- Any `manager_config.py apply` touches production `ossec.conf`. Always `diff` and show the user the exact XML before applying. Never pass `--restart` without the user's explicit go-ahead — a passing config test is not permission to interrupt live alert processing.
- Never wire a new persistent active-response (rule-bound, in `ossec.conf`) without the user confirming the exact rule IDs and the exact command — test ad hoc via the Server API on one known agent first (see `references/runbooks.md`).
