# Server (Manager) API reference — port 55000

Base URL: `https://<HOST>:55000`. Every call needs `Authorization: Bearer $TOKEN`.
Full interactive reference ships with the deployment at `https://<HOST>:55000/ui/` (Swagger) and online at documentation.wazuh.com under *User manual → Server API → Reference*. This file covers the endpoints you'll reach for most.

## Envelope & common query params (apply to most list endpoints)

Response: `{"data": {"affected_items": [...], "total_affected_items": N, "failed_items": [...], "total_failed_items": M}, "message": "...", "error": 0}`.

| Param | Meaning |
|---|---|
| `limit` | page size, **max 500** (default 500) |
| `offset` | skip N items |
| `select` | comma list of fields to return |
| `sort` | field to sort by; prefix `-` for descending |
| `search` | substring search across fields |
| `q` | Wazuh Query Language filter, e.g. `q=status=active;os.platform=windows` (`;`=AND, `,`=OR, operators `=,!=,<,>,~`) |
| `pretty` | pretty-print JSON |

## Server / manager

| Method & path | Purpose |
|---|---|
| `GET /` | API + manager version, hostname — **use to detect 4.x vs 5.x** |
| `GET /manager/status` | daemon status (wazuh-analysisd, remoted, etc.) |
| `GET /manager/info` | manager metadata |
| `GET /manager/configuration` | active `ossec.conf` (rendered) |
| `GET /manager/logs` | manager logs (filter with `q`, `level`) |
| `GET /manager/stats` | analysisd/remoted statistics |
| `PUT /manager/restart` | restart the manager (disruptive) |
| `GET /cluster/nodes`, `GET /cluster/healthcheck` | cluster topology & health |

## Agents

| Method & path | Purpose |
|---|---|
| `GET /agents` | list/search agents (`status=active,disconnected,never_connected,pending`) |
| `GET /agents/summary/status` | counts by status |
| `GET /agents/{id}` | single agent detail |
| `POST /agents` | register a new agent (returns key) |
| `GET /agents/{id}/key` | retrieve an agent's client key |
| `DELETE /agents?agents_list=001,002&status=...` | remove agents (destructive) |
| `PUT /agents/{id}/restart` or `PUT /agents/restart?agents_list=...` | restart agent(s) |
| `PUT /agents/{id}/upgrade` | remote upgrade |
| `GET /agents/{id}/group` / `PUT /agents/{id}/group/{group_id}` | group membership |
| `GET /agents/outdated` | agents on old versions |
| `GET /agents/no_group` | agents without a group |

Bulk agent operations return per-item results in `failed_items` — always check `total_failed_items`.

## Groups, rules, decoders, lists

| Method & path | Purpose |
|---|---|
| `GET /groups` / `POST /groups` / `DELETE /groups` | agent groups |
| `GET /groups/{id}/configuration` / `PUT /groups/{id}/configuration` | group agent.conf |
| `GET /rules` | list rules (`q=level>=10`, `group=`, `filename=`) |
| `GET /rules/files/{filename}` / `PUT /rules/files/{filename}` | read/write a rules file |
| `GET /decoders` / `GET /decoders/files/{filename}` | decoders |
| `GET /lists` / `GET /lists/files/{filename}` | CDB lists |

Editing rule/decoder files changes detection behavior for the whole deployment — treat as a change-managed action and confirm scope first.

## Active response (endpoint actions — high blast radius)

`PUT /active-response` runs a configured active-response command on agents:

```json
{ "command": "restart-wazuh0", "agents_list": ["001","002"], "arguments": [], "alert": {} }
```

Active-response commands can block IPs (firewall-drop), kill processes, or restart services **on the endpoints**. Never fire fleet-wide (`agents_list` omitted or `*`) without an explicit, scoped instruction. List available commands from the manager configuration.

## Syscheck (FIM)

| Method & path | Purpose |
|---|---|
| `GET /syscheck/{agent_id}` | file-integrity-monitoring results for an agent |
| `PUT /syscheck` | run a syscheck scan |
| `DELETE /syscheck/{agent_id}` | clear FIM DB for an agent |

## Syscollector / inventory — VERSION-DEPENDENT

`GET /syscollector/{agent_id}/{packages|os|hardware|ports|processes|hotfixes}` exists in **4.x**. Wazuh **5.0 removed these inventory API endpoints** — in 5.x, inventory lives in the Indexer as findings/data streams instead. Detect the version (`GET /`) before relying on syscollector; if 5.x, query the Indexer. See `version-notes.md`.
