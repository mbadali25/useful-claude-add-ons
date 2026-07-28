# Version notes — Wazuh 4.x vs 5.x

**Always detect the version first** — `GET /` on the Server API returns the manager/API version. The two lines differ enough that assuming 4.x behavior on a 5.x host (or vice-versa) causes 404s and confusing empty results.

## Detect the version
```bash
python scripts/wazuh_client.py info      # look at data.api_version / the manager version
# or:
curl -sk -H "Authorization: Bearer $TOKEN" "https://<HOST>:55000/?pretty"
```
The Server and Dashboard must run the **same major.minor**; a mismatch is itself a common failure the user may be hitting.

## What changed in 5.0 (the parts that affect API/scripting)

- **Filebeat removed.** Event forwarding server→indexer now uses the native **indexer-connector**, not Filebeat. So on 5.x, "check Filebeat" troubleshooting is obsolete — if `wazuh-alerts-*` is empty, look at the indexer-connector instead.
- **Inventory API endpoints removed.** The `/syscollector/...` endpoints (packages, OS, hardware, ports, processes, hotfixes) are gone in 5.0. Inventory is now indexed as findings/data streams in the Indexer — query it there.
- **Legacy security-config API endpoints removed** and **RBAC revamped**, with an upgrade mechanism that migrates existing 4.x RBAC configuration. Effective permissions after an upgrade may differ from before — re-check roles if writes start getting denied.
- **Rootcheck simplified** — its server-side database, sync path, and dedicated API surface were removed; findings now flow through the normal alert pipeline.
- **Data model reworked.** The Wazuh Common Schema was rebuilt on **ECS 9.1.0** with **per-category event and finding data streams**, managed by ISM (Index State Management) rolling indices. Practical effect: `wazuh-alerts-*` is still the alert stream, but other telemetry lives in category-specific data streams rather than a handful of monolithic indices. Discover current index/stream names with `_cat/indices` and `_data_stream` before hardcoding a pattern.
- **Deprecated daemons/tools removed** — e.g. `ossec-authd`, `wazuh-agentlessd`, `wazuh-maild`, `wazuh-dbd`, and the C CLIs `manage_agents` / `agent-auth`. Agent enrollment now goes through the Server API (`POST /agents`) rather than those binaries.
- **Vulnerability Detection** uses the Indexer as the authoritative CVE source; the agent-side detector no longer reaches out to CTI directly.

## What stayed the same

- Server API on **55000**, JWT via `POST /security/user/authenticate`, bearer token, 900s default lifetime, `{data, message, error}` envelope, `limit`/`offset`/`q`/`select`/`sort`.
- Indexer on **9200**, OpenSearch REST + Query DSL, `wazuh-alerts-*`, `rule.level` 0–15, `timestamp`, `agent.name`, `data.*`.
- Agent, rule, decoder, group, active-response, manager/cluster endpoints are broadly the same shape.

## Rule of thumb

Write against the shared surface (auth, agents, rules, alert search) and it works on both lines. When a task touches inventory/syscollector, RBAC internals, security-config endpoints, or exact index/stream names, branch on the detected version and check the deployment's own `_cat/indices` output rather than trusting a remembered pattern.
