---
name: aws-opensearch
description: Connect to and work with an Amazon OpenSearch Service managed domain over its public HTTPS endpoint using SigV4 (IAM) request signing. Covers read/inspect (cluster health, indices, mappings, search, counts, unassigned-shard diagnosis) and remediation (reindex, add mapping fields, ISM/ILM policies, snapshots, shard-allocation retry, close/open/delete indices) with dry-run safety rails on anything destructive. Use this skill whenever the user mentions AWS OpenSearch, Amazon OpenSearch Service, an OpenSearch/Elasticsearch domain on AWS, an es.amazonaws.com endpoint, OpenSearch indices/mappings/ISM/snapshots, a red or yellow OpenSearch cluster, unassigned shards, reindexing a legacy index, or wants to query, diagnose, fix, or automate anything on their managed OpenSearch estate — even if they don't say "API" or "SigV4". Also use it when troubleshooting 403s from an OpenSearch domain or writing scripts against an es.amazonaws.com host.
---

# AWS managed OpenSearch (Amazon OpenSearch Service)

Talks to a **managed domain** (`*.es.amazonaws.com`) over its **public endpoint**, signing every request with **SigV4** (IAM). This is *not* the self-managed Wazuh indexer (basic auth) and *not* OpenSearch Serverless (`aoss`, different service name). If the target turns out to be Serverless, set `service="aoss"` on the client.

## What decides success — confirm before making calls

| Thing | This skill assumes | If different |
|---|---|---|
| Service | Managed domain (`es`) | Serverless → `OpenSearchClient(service="aoss")` |
| Network | Public endpoint | VPC-only → this environment can't reach it; run from a host inside the VPC, or use `opensearch-mcp-server-py` |
| Auth | SigV4 via IAM principal | Master-user basic auth → sign differently (see `references/auth.md`) |

## Connection setup — always establish first

Config comes from the environment; **never hardcode credentials**:

```bash
export OPENSEARCH_ENDPOINT="https://search-<domain>-<hash>.<region>.es.amazonaws.com"
export AWS_REGION="eu-west-1"          # or rely on the profile's region
# Credentials, pick one: AWS_PROFILE=...  |  AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY (+ AWS_SESSION_TOKEN)  |  attached IAM role
```

If the endpoint/region isn't known, ask — don't guess the domain hash. A `403` almost always means the IAM principal isn't in the domain access policy or isn't mapped in fine-grained access control — see `references/auth.md`.

## Helper script — use it instead of hand-signing curl

`scripts/opensearch_client.py` (needs `boto3` + `requests`) handles SigV4 signing, credential/region resolution, JSON handling, and **dry-run gating on every destructive op**. Prefer it over raw curl.

```bash
python scripts/opensearch_client.py health
python scripts/opensearch_client.py indices 'logs-*'
python scripts/opensearch_client.py mapping my-index
python scripts/opensearch_client.py search my-index --query '{"query":{"match_all":{}},"size":5}'
python scripts/opensearch_client.py count my-index --since 24h --time-field @timestamp
python scripts/opensearch_client.py allocation          # why are shards unassigned?
python scripts/opensearch_client.py reroute-retry       # retry failed allocations
python scripts/opensearch_client.py reindex --source old --dest new     # dry-run
python scripts/opensearch_client.py delete-index stale-2019 --confirm   # executes
python scripts/opensearch_client.py raw GET /_cluster/settings
```

It imports cleanly too: `from opensearch_client import OpenSearchClient`.

## Command map

| Need | Command |
|---|---|
| Cluster health / status | `health` |
| List indices (+pattern) | `indices [pattern]` |
| Mapping / settings | `mapping <index>` · `settings <index>` |
| Query / count | `search <index> [--query/--body/--size]` · `count <index> [--since]` |
| Diagnose red/yellow cluster | `allocation` then `reroute-retry` |
| Reindex legacy index | `reindex --source S --dest D [--wait]` |
| Add mapping fields | `put-mapping <index> --body add.json` |
| Retention / rollover | `ism-get [name]` · `ism-put <name> --body p.json` |
| Snapshots | `snapshot-list <repo>` · `snapshot-create <repo> <name>` · `snapshot-restore <repo> <name>` |
| Retire an index | `close <index>` · `open <index>` · `delete-index <index>` |
| **Edit index settings** | `put-settings <index> --set index.number_of_replicas=1` (or `--body f`) |
| **Aliases (atomic)** | `aliases --body actions.json` |
| **Edit documents** | `update-by-query <index> --body q.json` · `delete-by-query <index> --body q.json` (both show match count first) |
| **Export dashboards** | `dashboards-export [--type ... / --objects type:id] [--tenant T] --out f.ndjson` |
| **Import / edit dashboards** | `dashboards-import --body f.ndjson [--overwrite] [--tenant T]` |
| **Browse saved objects** | `saved-object-find [--type T]` · `saved-object-get <type> <id>` · `saved-object-delete <type> <id>` |
| Anything else | `raw <METHOD> <path> [--body f]` |

## Which reference to read (read it before writing calls)

| Task | Reference |
|---|---|
| SigV4 details, credential resolution, IAM access policy vs fine-grained access control, master-user/basic-auth variant, why a 403 happens, Serverless (`aoss`) differences | `references/auth.md` |
| Query DSL, time ranges, aggregations, pagination (`search_after`/PIT), `_cat`, common legacy queries | `references/search.md` |
| Fixing legacy issues: reindex patterns, why field types can't change in place, ISM/ILM, snapshots before destructive ops, red/yellow triage, shard sizing, **editing index settings/aliases, update/delete-by-query** | `references/remediation.md` |
| **Dashboards & saved objects: export→edit→import workflow, tenancy (`securitytenant`), the xsrf header, `_dashboards` vs `_plugin/kibana` path, index-pattern references** | `references/dashboards.md` |

## Safety rails — non-negotiable

Destructive/mutating ops — `delete-index`, `close`, `snapshot-restore`, `reindex`, `put-mapping`, `put-settings`, `aliases`, `cluster-setting`, `ism-put`, `update-by-query`, `delete-by-query`, `dashboards-import`, `saved-object-delete`, and `raw DELETE`/`_delete_by_query` — are **dry-run by default**: the tool prints the resolved target and does nothing unless you add `--confirm`.

- `update-by-query` and `delete-by-query` run a `_count` with your query and **show how many documents will change before you confirm** — always sanity-check that number against what you expect.
- `dashboards-import` shows the object count and type breakdown from the NDJSON first; `--overwrite` will replace existing objects with the same IDs.

- Confirm the exact target set out loud — for wildcards, show matched index names, not just a count. (`delete-index` already lists matches before acting.)
- **Snapshot before you reindex-and-drop or restore.** Restore and delete are unrecoverable.
- You **cannot change an existing field's type** in place — that needs a reindex into a new index with a corrected mapping. `put-mapping` only *adds* fields. See `references/remediation.md`.
- Never push cluster-wide settings or delete/close indices without an instruction that names the scope.
