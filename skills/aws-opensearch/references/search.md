# Searching & inspecting

OpenSearch is Query-DSL over HTTP, near-identical to Elasticsearch 7.x. Use `search`/`count` for data, `_cat` for operator views.

## Query DSL essentials
`POST /<index>/_search` with a JSON body:

```json
{ "query": { "bool": {
    "must":   [{ "match": { "message": "timeout" } }],
    "filter": [{ "range": { "@timestamp": { "gte": "now-24h" } } }],
    "must_not":[{ "term": { "level": "debug" } }]
} }, "size": 20, "sort": [{ "@timestamp": "desc" }] }
```

- `filter` = yes/no, cached, no scoring → use it for ranges/terms. `must` = scored full-text.
- `term` for exact (keyword) fields; `match` for analyzed text. Matching a `text` field exactly usually needs its `.keyword` sub-field.
- Discover field names/types first: `mapping <index>`.

## Time ranges
Time field is whatever the index uses — commonly `@timestamp` or `timestamp`. Date math: `now-24h`, `now-7d/d` (rounded to day). The `count --since 24h --time-field @timestamp` shortcut builds the range filter for you.

## Aggregations without hauling documents
Set `"size": 0` and let `aggs` do the work:

```json
{ "size": 0, "aggs": {
    "by_status": { "terms": { "field": "response.keyword", "size": 10 } },
    "over_time": { "date_histogram": { "field": "@timestamp", "fixed_interval": "1h" } }
} }
```

Large/high-cardinality aggregations can hit `search.max_buckets` (default 65536) — narrow the time range or raise the limit deliberately, don't just retry.

## Pagination — don't deep-page
`from`/`size` is fine for the first few pages only; deep `from` is expensive and capped by `index.max_result_window` (10000). For full scans use **`search_after`** with a stable sort, or a **PIT** (point-in-time):

```
raw POST /<index>/_search/point_in_time?keep_alive=1m   # returns pit_id
# then _search with {"pit":{"id":...,"keep_alive":"1m"},"search_after":[...],"sort":[...]}
```

PITs hold resources — close them (`raw DELETE /_search/point_in_time`) when done.

## `_cat` — the operator's friend
Plain-text, human-scannable:

| View | Path |
|---|---|
| Indices (health, docs, size) | `indices [pattern]` (adds `?v` + useful columns) |
| Shards + node placement | `raw GET /_cat/shards?v` |
| Node stats | `raw GET /_cat/nodes?v` |
| Pending tasks | `raw GET /_cat/pending_tasks?v` |
| Thread-pool rejections | `raw GET /_cat/thread_pool?v&h=node_name,name,active,queue,rejected` |

Add `&s=<col>` to sort, `&h=<cols>` to pick columns.

## Common legacy-triage queries
- Biggest indices: `raw GET '/_cat/indices?v&s=store.size:desc&bytes=gb'`
- Old indices by name pattern: `indices 'logs-2019*'`
- Doc count spike check: `count <index> --since 1h` vs `--since 24h`
- Field exists / mapping drift: search with `{"query":{"exists":{"field":"suspect_field"}}}`
- Mapping conflicts across a pattern: compare `mapping index-a` vs `mapping index-b` (differing types for the same field is a classic cause of search/reindex failures → see remediation.md).
