# Remediation & fixing legacy issues

The playbook for the write side. **Golden rule: snapshot before anything destructive**, and default to dry-run (omit `--confirm`) to see the target first.

## 1. Field type is wrong / mapping conflict → reindex
You **cannot change an existing field's type in place**. Mappings are largely immutable; `put-mapping` only *adds* new fields. To fix a bad type (e.g. a field mapped as `text` that should be `keyword`, or `long` vs `float`):

1. Create a target index with the corrected mapping:
   `raw PUT /myindex-v2 --body corrected_mapping.json`
2. Copy data across (dry-run first):
   `reindex --source myindex --dest myindex-v2` → review → add `--confirm`
   Large indices: run async (drop `--wait`), then poll `raw GET /_tasks/<task_id>`.
3. Validate counts match: `count myindex` vs `count myindex-v2`.
4. Cut over with an alias so clients don't change:
   `raw POST /_aliases --body '{"actions":[{"remove":{"index":"myindex","alias":"myindex-live"}},{"add":{"index":"myindex-v2","alias":"myindex-live"}}]}'`
5. Only then retire the old one: `delete-index myindex --confirm` (snapshot first).

Reindex tips: add `"conflicts":"proceed"` to skip version conflicts; use `"query"` in the source to reindex a subset; `"script"` to transform fields during copy.

## 2. Add fields to a mapping (safe, in place)
```json
{ "properties": { "new_field": { "type": "keyword" } } }
```
`put-mapping <index> --body add_fields.json` (dry-run → `--confirm`). Adding fields is safe; you can't retype or remove existing ones this way.

## 3. Retention / rollover with ISM (Index State Management)
ISM is how you stop legacy indices growing forever. A policy transitions indices through states by age/size and can delete or snapshot them. Skeleton:

```json
{ "policy": { "description": "logs retention",
  "default_state": "hot",
  "states": [
    { "name": "hot",    "actions": [], "transitions": [{ "state_name": "delete", "conditions": { "min_index_age": "30d" } }] },
    { "name": "delete", "actions": [{ "delete": {} }], "transitions": [] }
  ],
  "ism_template": [{ "index_patterns": ["logs-*"], "priority": 100 }] } }
```
`ism-put logs-retention --body policy.json` (dry-run → `--confirm`). Existing indices may need the policy attached explicitly: `raw POST /_plugins/_ism/add/<index> --body '{"policy_id":"logs-retention"}'`. Inspect status with `raw GET /_plugins/_ism/explain/<index>`.

Prefer rollover (write alias + `rollover` action) for new pipelines rather than daily-dated indices, but for *legacy* daily indices an age-based delete transition is the quick win.

## 4. Snapshots (backup / restore)
Managed domains snapshot to an S3 repo (registered once with an IAM role that can write the bucket). Then:

- List: `snapshot-list <repo>`
- Create: `snapshot-create <repo> snap-YYYY-MM-DD --indices 'logs-*'` (dry-run → `--confirm`; `--wait` to block)
- Restore: `snapshot-restore <repo> <name> --indices 'logs-2019-*' --confirm`

You **cannot restore over an open index** with the same name — close or rename it first (`rename_pattern`/`rename_replacement` in the restore body), or restore into new names. Restore is unrecoverable if it clobbers current data — confirm scope out loud.

## 5. Red / yellow cluster triage
**Yellow** = replicas unassigned (data safe, resilience reduced). **Red** = a *primary* is unassigned (data unavailable). Work the ladder:

1. `health` — note `status`, `unassigned_shards`, `number_of_nodes`.
2. `allocation` — the explain output names the reason per shard.
3. Match the reason:

| Reason in explain | Typical fix |
|---|---|
| `ALLOCATION_FAILED` (transient, retries exhausted) | `reroute-retry` |
| Disk watermark exceeded (`the node is above the high watermark`) | Free disk / expand storage; watermarks: `cluster.routing.allocation.disk.watermark.*` via `cluster-setting` |
| `NODE_LEFT` / not enough nodes for replica count | Add nodes, or reduce replicas: `raw PUT /<index>/_settings --body '{"index":{"number_of_replicas":1}}'` |
| Shard data corrupt / lost, no replica (red) | Restore that index from snapshot; last resort `raw POST /_cluster/reroute` with `allocate_stale_primary` (data-loss — snapshot & confirm first) |

Never blindly force-allocate a stale/empty primary to clear red — that discards data. Exhaust reroute-retry, disk, and snapshot-restore first.

## 6. Shard sizing (why legacy clusters get slow)
Aim for **10–50 GB per shard** and keep total shard *count* modest (rough guide: ≤ ~20 shards per GB of JVM heap per node). Legacy symptoms — thousands of tiny daily indices, hundreds of near-empty shards — bloat cluster state and slow everything. Fix by reindexing many small indices into fewer larger ones (monthly instead of daily) and setting a sane `number_of_shards` on the target. Check current spread: `raw GET '/_cat/shards?v&s=store:desc'`.

## 7. Editing index settings, aliases & documents

**Settings** — `put-settings`. Dynamic settings apply live; static ones need the index closed first.

| Common change | How | Note |
|---|---|---|
| Replicas | `put-settings idx --set index.number_of_replicas=1` | Dynamic. On a single-node/dev domain set to `0` to clear yellow |
| Refresh interval | `put-settings idx --set index.refresh_interval=30s` | Dynamic. `-1` during a big bulk/reindex, then restore, to speed ingest |
| Result window | `put-settings idx --set index.max_result_window=20000` | Prefer `search_after`/PIT over raising this |
| `number_of_shards` | — | **Static** — cannot change on a live index; set it on a new index and reindex |

**Aliases** — `aliases --body actions.json`. Use the atomic form so a cutover has no gap:
```json
{ "actions": [
  { "remove": { "index": "logs-v1", "alias": "logs" } },
  { "add":    { "index": "logs-v2", "alias": "logs" } }
] }
```

**Documents (`update-by-query` / `delete-by-query`)** — for cleaning legacy data in place. Both run a `_count` with your query and print the match count before the `--confirm` gate — treat that number as the safety check.

- Purge old docs (unrecoverable — snapshot first):
  `delete-by-query old-logs --body '{"query":{"range":{"@timestamp":{"lt":"now-365d"}}}}'`
- Backfill/normalize a field with a script:
  ```json
  { "query": { "bool": { "must_not": { "exists": { "field": "env" } } } },
    "script": { "source": "ctx._source.env='prod'" } }
  ```
  `update-by-query my-index --body backfill.json`
- Add `--conflicts-proceed` for large jobs where concurrent writes cause version conflicts; run async (omit `--wait`) and poll `raw GET /_tasks/<task_id>`.
- **Caveat:** an update-by-query cannot change a field's *mapped type* — if you're fixing a type, that's a reindex (section 1), not an in-place script.

## Order of operations for any risky change
1. `health` + relevant `_cat` view — capture the before-state.
2. Dry-run the command (no `--confirm`) — read the resolved target.
3. Snapshot if data could be lost.
4. Re-run with `--confirm`.
5. Verify (counts, health, a sample query) and record what changed.
