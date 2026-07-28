# Indexer API reference — port 9200

The Wazuh Indexer is OpenSearch. You query it with the standard REST + Query DSL.
Base URL `https://<HOST>:9200`, basic auth with an indexer user. Alert data lands in `wazuh-alerts-*` (see `version-notes.md` for 5.x data streams).

## Discover what's there

```bash
# List alert indices with doc counts and sizes
curl -sk -u "$WAZUH_INDEXER_USER:$WAZUH_INDEXER_PASSWORD" \
  "https://<HOST>:9200/_cat/indices/wazuh-alerts-*?v&h=index,docs.count,store.size&s=index"

# Inspect the field mapping (what fields exist / their types)
curl -sk -u ... "https://<HOST>:9200/wazuh-alerts-*/_mapping?pretty"
```

## Key alert fields

| Field | Meaning |
|---|---|
| `timestamp` / `@timestamp` | event time (use `timestamp` for range filters) |
| `rule.level` | severity **0–15** (higher = worse; 12+ is critical) |
| `rule.id` | numeric rule id |
| `rule.description` | human-readable rule text |
| `rule.groups` | tags, e.g. `authentication_failed`, `sshd`, `web` |
| `rule.mitre.id` / `rule.mitre.tactic` / `rule.mitre.technique` | ATT&CK mapping |
| `agent.id` / `agent.name` / `agent.ip` | reporting agent |
| `location` | log source / decoder path |
| `full_log` | raw log line |
| `data.*` | decoded fields (`data.srcip`, `data.dstuser`, `data.win.*`, etc.) |

Use `.keyword` sub-fields for exact `term` matches and aggregations on text fields (e.g. `agent.name` is usually already keyword; `rule.description` needs `rule.description.keyword` for aggs).

## Query DSL patterns

**Recent high-severity alerts for one agent (last 24h):**
```json
{
  "size": 50,
  "query": { "bool": {
    "filter": [
      { "range": { "timestamp": { "gte": "now-24h" } } },
      { "range": { "rule.level": { "gte": 10 } } },
      { "term": { "agent.name": "web-server-01" } }
    ]
  }},
  "sort": [ { "timestamp": { "order": "desc" } } ]
}
```

**Absolute time window + severity floor:**
```json
{ "query": { "bool": { "filter": [
  { "range": { "timestamp": { "gte": "2026-07-01T00:00:00", "lte": "2026-07-31T23:59:59",
                              "format": "yyyy-MM-dd'T'HH:mm:ss" } } },
  { "range": { "rule.level": { "gte": 10 } } }
]}}}
```

**Full-text on rule description + exclude noise:**
```json
{ "query": { "bool": {
  "must":     [ { "match": { "rule.description": "authentication failure" } } ],
  "must_not": [ { "term":  { "rule.level": 3 } } ]
}}}
```

## Aggregations (counts / top-N without hauling documents)

Set `"size": 0` so you get only the aggregation, not the hits.

**Top agents by tactic, with max severity:**
```json
{ "size": 0, "aggs": {
  "by_agent": { "terms": { "field": "agent.name", "size": 10 },
    "aggs": {
      "by_tactic": { "terms": { "field": "rule.mitre.tactic", "size": 5 } },
      "max_level": { "max": { "field": "rule.level" } }
    }}
}}
```

**Failed logins by user (last 24h):**
```json
{ "size": 0,
  "query": { "bool": { "filter": [
    { "term": { "rule.groups": "authentication_failed" } },
    { "range": { "timestamp": { "gte": "now-24h" } } } ]}},
  "aggs": { "by_user": { "terms": { "field": "data.dstuser", "size": 10, "order": { "_count": "desc" } } } }
}
```

**Alert volume over time (histogram):**
```json
{ "size": 0, "aggs": {
  "over_time": { "date_histogram": { "field": "timestamp", "fixed_interval": "1h" } }
}}
```

## Practical notes

- Large `terms` aggregations can hit `search.max_buckets`. Raise it deliberately if needed: `PUT /_cluster/settings {"transient":{"search.max_buckets":75000}}`.
- For paging many results, prefer `search_after` (with a stable sort incl. a tiebreaker) or a Point-In-Time, not deep `from`/`size`.
- Reading is safe; `DELETE .../_delete_by_query` and dropping indices are **destructive and unrecoverable** — confirm index pattern and time range with the user before running.
- If no `wazuh-alerts-*` index exists, the pipeline from server→indexer may be broken (4.x: Filebeat; 5.x: indexer-connector) — that's a deployment issue, not a query bug.
