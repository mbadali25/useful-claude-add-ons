#!/usr/bin/env python3
"""
AWS managed OpenSearch Service client (SigV4-signed).

Talks to an Amazon OpenSearch *Service* managed domain over its public HTTPS
endpoint using SigV4 request signing (service name "es"). Credentials are
resolved by botocore the normal way: env vars, shared profile, or an attached
IAM role. Nothing is ever hardcoded.

Read ops are unrestricted. Anything destructive (delete / close / restore /
delete_by_query, and DELETE via `raw`) is DRY-RUN by default: it prints exactly
what would be hit and refuses to act unless you pass --confirm.

Usage examples:
  export OPENSEARCH_ENDPOINT="https://search-mydomain-xxxx.eu-west-1.es.amazonaws.com"
  export AWS_REGION="eu-west-1"          # or rely on your profile/region
  # credentials: AWS_PROFILE=... or AWS_ACCESS_KEY_ID/SECRET (+ optional SESSION_TOKEN)

  python opensearch_client.py health
  python opensearch_client.py indices 'logs-*'
  python opensearch_client.py mapping my-index
  python opensearch_client.py search my-index --query '{"query":{"match_all":{}},"size":5}'
  python opensearch_client.py count my-index --since 24h --time-field @timestamp
  python opensearch_client.py allocation                 # why are shards unassigned?
  python opensearch_client.py reroute-retry              # retry failed allocations
  python opensearch_client.py reindex --source old-index --dest new-index
  python opensearch_client.py put-mapping my-index --body add_fields.json
  python opensearch_client.py ism-get
  python opensearch_client.py snapshot-list my-repo
  python opensearch_client.py snapshot-create my-repo snap-2026-07-23 --indices 'logs-*'
  python opensearch_client.py delete-index stale-index-2019 --confirm
  python opensearch_client.py raw GET /_cluster/settings

Import for larger scripts:
  from opensearch_client import OpenSearchClient
  c = OpenSearchClient()
  c.request("GET", "/_cluster/health")
"""
import argparse
import json
import os
import sys

try:
    import requests
    import botocore.session
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest
except ImportError:
    sys.stderr.write(
        "Missing deps. Install with:  pip install boto3 requests\n"
    )
    raise


class OpenSearchClient:
    def __init__(self, endpoint=None, region=None, service="es"):
        self.endpoint = (endpoint or os.environ.get("OPENSEARCH_ENDPOINT", "")).rstrip("/")
        if not self.endpoint:
            sys.exit("Set OPENSEARCH_ENDPOINT (e.g. https://search-xxx.<region>.es.amazonaws.com)")
        if not self.endpoint.startswith("https://"):
            sys.exit("OPENSEARCH_ENDPOINT must start with https://")

        self.session = botocore.session.get_session()
        self.credentials = self.session.get_credentials()
        if self.credentials is None:
            sys.exit(
                "No AWS credentials found. Set AWS_PROFILE, or "
                "AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY (+ AWS_SESSION_TOKEN), "
                "or run on a host with an IAM role."
            )
        self.region = (
            region
            or os.environ.get("AWS_REGION")
            or os.environ.get("AWS_DEFAULT_REGION")
            or self.session.get_config_variable("region")
        )
        if not self.region:
            sys.exit("No region. Set AWS_REGION or configure it in your AWS profile.")
        self.service = service  # "es" for managed domains; "aoss" for Serverless

    def request(self, method, path, body=None, params=None, timeout=60, extra_headers=None):
        method = method.upper()
        url = self.endpoint + (path if path.startswith("/") else "/" + path)
        data = None
        headers = dict(extra_headers or {})
        if isinstance(body, (bytes, bytearray)):
            # raw body (e.g. multipart) - caller supplies Content-Type via extra_headers
            data = bytes(body)
        elif body is not None:
            data = body if isinstance(body, str) else json.dumps(body)
            headers.setdefault("Content-Type", "application/json")

        # extra_headers (osd-xsrf, securitytenant, ...) are added BEFORE signing so
        # they become part of SignedHeaders and won't be rejected by the server.
        aws_req = AWSRequest(method=method, url=url, data=data, params=params, headers=headers)
        SigV4Auth(self.credentials.get_frozen_credentials(), self.service, self.region).add_auth(aws_req)
        prepared = aws_req.prepare()

        resp = requests.request(
            method, prepared.url, headers=dict(prepared.headers), data=data, timeout=timeout
        )
        return resp

    def json_request(self, method, path, body=None, params=None, extra_headers=None):
        resp = self.request(method, path, body=body, params=params, extra_headers=extra_headers)
        try:
            payload = resp.json()
        except ValueError:
            payload = resp.text
        if resp.status_code >= 400:
            _fail(resp.status_code, payload)
        return payload


# ---------- helpers ----------

def _fail(status, payload):
    sys.stderr.write(f"HTTP {status}\n")
    sys.stderr.write(_pretty(payload) + "\n")
    if status == 403:
        sys.stderr.write(
            "\n403 usually means the IAM principal is not allowed by the domain "
            "access policy, OR fine-grained access control hasn't mapped this role. "
            "See references/auth.md.\n"
        )
    sys.exit(1)


def _pretty(obj):
    if isinstance(obj, (dict, list)):
        return json.dumps(obj, indent=2, sort_keys=False)
    return str(obj)


def _load_body(args):
    if getattr(args, "body", None):
        with open(args.body) as fh:
            return fh.read()
    if getattr(args, "query", None):
        return args.query
    return None


def _since_to_range(since, time_field):
    # since like "24h", "7d", "30m" -> range filter dict
    return {"range": {time_field: {"gte": f"now-{since}"}}}


def _confirm_or_dry(args, action_desc, target_preview):
    print(f"TARGET: {action_desc}")
    print(_pretty(target_preview))
    if not getattr(args, "confirm", False):
        print("\nDRY RUN - nothing changed. Re-run with --confirm to execute.")
        return False
    return True


# Dashboards saved-objects live under this path prefix. OpenSearch domains use
# /_dashboards; legacy Elasticsearch-based domains use /_plugin/kibana.
DASHBOARDS_PATH = os.environ.get("OPENSEARCH_DASHBOARDS_PATH", "/_dashboards").rstrip("/")


def _saved_objects_headers(tenant=None):
    # osd-xsrf is mandatory for the saved-objects API; securitytenant targets a tenant.
    headers = {"osd-xsrf": "true"}
    if tenant:
        headers["securitytenant"] = tenant
    return headers


def _multipart_ndjson(ndjson_text, filename="import.ndjson"):
    import uuid
    boundary = "----osd" + uuid.uuid4().hex
    if isinstance(ndjson_text, str):
        ndjson_text = ndjson_text.encode("utf-8")
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
        b"Content-Type: application/ndjson\r\n\r\n",
        ndjson_text,
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    return body, f"multipart/form-data; boundary={boundary}"


def _summarize_ndjson(text):
    # count objects by type without choking on a trailing summary line
    counts = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        t = obj.get("type")
        if t:
            counts[t] = counts.get(t, 0) + 1
    return counts


def _kv_to_settings(pairs):
    # ["index.number_of_replicas=2", "index.refresh_interval=30s"] -> nested dict
    root = {}
    for pair in pairs:
        if "=" not in pair:
            sys.exit(f"--set expects key=value, got: {pair}")
        key, _, val = pair.partition("=")
        # coerce ints so number_of_replicas etc. aren't sent as strings
        try:
            val = int(val)
        except ValueError:
            pass
        node = root
        parts = key.strip().split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = val
    return root


# ---------- command implementations ----------

def cmd_health(c, args):
    print(_pretty(c.json_request("GET", "/_cluster/health")))


def cmd_indices(c, args):
    pattern = args.pattern or ""
    path = f"/_cat/indices/{pattern}" if pattern else "/_cat/indices"
    resp = c.request("GET", path, params={"v": "true", "s": "index", "h":
        "health,status,index,pri,rep,docs.count,store.size"})
    if resp.status_code >= 400:
        _fail(resp.status_code, resp.text)
    print(resp.text.rstrip())


def cmd_mapping(c, args):
    print(_pretty(c.json_request("GET", f"/{args.index}/_mapping")))


def cmd_settings(c, args):
    print(_pretty(c.json_request("GET", f"/{args.index}/_settings")))


def cmd_search(c, args):
    body = _load_body(args)
    if body is None:
        body = json.dumps({"query": {"match_all": {}}, "size": args.size})
    print(_pretty(c.json_request("POST", f"/{args.index}/_search", body=body)))


def cmd_count(c, args):
    if args.since:
        body = json.dumps({"query": {"bool": {"filter": [
            _since_to_range(args.since, args.time_field)]}}})
    else:
        body = _load_body(args)
    path = f"/{args.index}/_count"
    print(_pretty(c.json_request("POST", path, body=body) if body else c.json_request("GET", path)))


def cmd_allocation(c, args):
    # Explain why shards are unassigned (top reason for yellow/red legacy clusters)
    resp = c.request("GET", "/_cluster/allocation/explain")
    payload = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
    if resp.status_code == 400 and isinstance(payload, dict) and "unable to find any unassigned shards" in json.dumps(payload):
        print("No unassigned shards to explain - allocation looks healthy.")
        return
    print(_pretty(payload))


def cmd_reroute_retry(c, args):
    print(_pretty(c.json_request("POST", "/_cluster/reroute", params={"retry_failed": "true"})))


def cmd_reindex(c, args):
    body = {"source": {"index": args.source}, "dest": {"index": args.dest}}
    params = {"wait_for_completion": "true" if args.wait else "false"}
    if not _confirm_or_dry(args, f"reindex {args.source} -> {args.dest} (wait={args.wait})", body):
        return
    print(_pretty(c.json_request("POST", "/_reindex", body=json.dumps(body), params=params)))
    if not args.wait:
        print("\nStarted async. Check progress with:  raw GET /_tasks/<task_id>")


def cmd_put_mapping(c, args):
    body = _load_body(args)
    if body is None:
        sys.exit("put-mapping needs --body <file.json> (you can only ADD fields, not retype existing ones)")
    if not _confirm_or_dry(args, f"PUT mapping on {args.index}", json.loads(body)):
        return
    print(_pretty(c.json_request("PUT", f"/{args.index}/_mapping", body=body)))


def cmd_ism_get(c, args):
    path = f"/_plugins/_ism/policies/{args.policy}" if args.policy else "/_plugins/_ism/policies"
    print(_pretty(c.json_request("GET", path)))


def cmd_ism_put(c, args):
    body = _load_body(args)
    if body is None:
        sys.exit("ism-put needs --body <policy.json>")
    if not _confirm_or_dry(args, f"PUT ISM policy {args.policy}", json.loads(body)):
        return
    print(_pretty(c.json_request("PUT", f"/_plugins/_ism/policies/{args.policy}", body=body)))


def cmd_snapshot_list(c, args):
    print(_pretty(c.json_request("GET", f"/_snapshot/{args.repo}/_all")))


def cmd_snapshot_create(c, args):
    body = {}
    if args.indices:
        body = {"indices": args.indices, "include_global_state": False}
    if not _confirm_or_dry(args, f"create snapshot {args.name} in repo {args.repo}", body or "all indices"):
        return
    print(_pretty(c.json_request("PUT", f"/_snapshot/{args.repo}/{args.name}",
                                 body=json.dumps(body) if body else None,
                                 params={"wait_for_completion": "true" if args.wait else "false"})))


def cmd_snapshot_restore(c, args):
    body = {}
    if args.indices:
        body = {"indices": args.indices}
    if not _confirm_or_dry(args, f"RESTORE snapshot {args.name} from repo {args.repo}", body or "all indices in snapshot"):
        return
    print(_pretty(c.json_request("POST", f"/_snapshot/{args.repo}/{args.name}/_restore",
                                 body=json.dumps(body) if body else None)))


def cmd_delete_index(c, args):
    # Show what matches BEFORE deleting so a wildcard can't silently nuke extra indices
    resp = c.request("GET", f"/_cat/indices/{args.index}", params={"h": "index"})
    matched = resp.text.strip() or "(no matching indices found)"
    if not _confirm_or_dry(args, f"DELETE index/pattern '{args.index}' - matches:", matched):
        return
    print(_pretty(c.json_request("DELETE", f"/{args.index}")))


def cmd_close(c, args):
    if not _confirm_or_dry(args, f"CLOSE index '{args.index}' (makes it unsearchable until reopened)", args.index):
        return
    print(_pretty(c.json_request("POST", f"/{args.index}/_close")))


def cmd_open(c, args):
    print(_pretty(c.json_request("POST", f"/{args.index}/_open")))


def cmd_cluster_setting(c, args):
    body = _load_body(args)
    if body is None:
        sys.exit("cluster-setting needs --body <file.json>")
    if not _confirm_or_dry(args, "PUT _cluster/settings", json.loads(body)):
        return
    print(_pretty(c.json_request("PUT", "/_cluster/settings", body=body)))


def cmd_raw(c, args):
    method = args.method.upper()
    body = _load_body(args)
    destructive = method in ("DELETE",) or (method == "POST" and "_delete_by_query" in args.path)
    if destructive and not args.confirm:
        print(f"TARGET: {method} {args.path}")
        print("\nDRY RUN - destructive method. Re-run with --confirm to execute.")
        return
    resp = c.request(method, args.path, body=body)
    try:
        print(_pretty(resp.json()))
    except ValueError:
        print(resp.text.rstrip())
    if resp.status_code >= 400:
        sys.exit(1)


# ----- Dashboards saved objects (dashboards, visualizations, index-patterns) -----

def cmd_dashboards_export(c, args):
    body = {}
    if args.objects:  # explicit "type:id" pairs
        body["objects"] = []
        for spec in args.objects:
            t, _, i = spec.partition(":")
            if not i:
                sys.exit(f"--objects wants type:id, got: {spec}")
            body["objects"].append({"type": t, "id": i})
    else:
        body["type"] = args.type or ["dashboard", "visualization", "index-pattern", "search"]
    body["includeReferencesDeep"] = True
    resp = c.request("POST", f"{DASHBOARDS_PATH}/api/saved_objects/_export",
                     body=json.dumps(body), extra_headers=_saved_objects_headers(args.tenant))
    if resp.status_code >= 400:
        _fail(resp.status_code, _safe_json(resp))
    counts = _summarize_ndjson(resp.text)
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(resp.text)
        print(f"Exported {sum(counts.values())} objects -> {args.out}")
        print("By type: " + (", ".join(f"{k}={v}" for k, v in counts.items()) or "(none)"))
    else:
        print(resp.text.rstrip())


def cmd_dashboards_import(c, args):
    with open(args.body) as fh:
        ndjson = fh.read()
    counts = _summarize_ndjson(ndjson)
    preview = {"file": args.body, "objects": sum(counts.values()), "by_type": counts,
               "overwrite": bool(args.overwrite), "tenant": args.tenant or "(global)"}
    if not _confirm_or_dry(args, f"IMPORT saved objects into {DASHBOARDS_PATH}", preview):
        return
    data, content_type = _multipart_ndjson(ndjson, filename=os.path.basename(args.body))
    headers = _saved_objects_headers(args.tenant)
    headers["Content-Type"] = content_type
    params = {"overwrite": "true"} if args.overwrite else None
    resp = c.request("POST", f"{DASHBOARDS_PATH}/api/saved_objects/_import",
                     body=data, params=params, extra_headers=headers)
    print(_pretty(_safe_json(resp)))
    if resp.status_code >= 400:
        sys.exit(1)


def cmd_saved_object_find(c, args):
    params = {"per_page": str(args.limit)}
    if args.type:
        params["type"] = args.type
    if args.search:
        params["search"] = args.search
    print(_pretty(c.json_request("GET", f"{DASHBOARDS_PATH}/api/saved_objects/_find",
                                 params=params, extra_headers=_saved_objects_headers(args.tenant))))


def cmd_saved_object_get(c, args):
    print(_pretty(c.json_request("GET", f"{DASHBOARDS_PATH}/api/saved_objects/{args.type}/{args.id}",
                                 extra_headers=_saved_objects_headers(args.tenant))))


def cmd_saved_object_delete(c, args):
    if not _confirm_or_dry(args, f"DELETE saved object {args.type}/{args.id} (tenant={args.tenant or 'global'})",
                           f"{args.type}/{args.id}"):
        return
    print(_pretty(c.json_request("DELETE", f"{DASHBOARDS_PATH}/api/saved_objects/{args.type}/{args.id}",
                                 extra_headers=_saved_objects_headers(args.tenant))))


# ----- Index editing: settings, aliases, by-query document changes -----

def cmd_put_settings(c, args):
    if args.body:
        with open(args.body) as fh:
            body = json.loads(fh.read())
    elif args.set:
        body = _kv_to_settings(args.set)
    else:
        sys.exit("put-settings needs --body <file.json> or --set key=value ...")
    if not _confirm_or_dry(args, f"PUT settings on {args.index}", body):
        return
    print(_pretty(c.json_request("PUT", f"/{args.index}/_settings", body=json.dumps(body))))


def cmd_aliases(c, args):
    with open(args.body) as fh:
        body = fh.read()
    if not _confirm_or_dry(args, "POST /_aliases (atomic alias actions)", json.loads(body)):
        return
    print(_pretty(c.json_request("POST", "/_aliases", body=body)))


def _count_matches(c, index, query_body):
    # query_body is a dict that may contain "query"; count just the query part
    q = {"query": query_body.get("query")} if query_body.get("query") else None
    payload = c.json_request("POST", f"/{index}/_count", body=json.dumps(q)) if q \
        else c.json_request("GET", f"/{index}/_count")
    return payload.get("count")


def cmd_update_by_query(c, args):
    with open(args.body) as fh:
        body = json.loads(fh.read())
    matched = _count_matches(c, args.index, body)
    preview = {"index": args.index, "matches": matched,
               "script": body.get("script", "(none - reindexing in place)")}
    if not _confirm_or_dry(args, f"UPDATE-BY-QUERY on {args.index} - will modify {matched} docs", preview):
        return
    params = {"conflicts": "proceed"} if args.conflicts_proceed else None
    params = params or {}
    params["wait_for_completion"] = "true" if args.wait else "false"
    print(_pretty(c.json_request("POST", f"/{args.index}/_update_by_query",
                                 body=json.dumps(body), params=params)))


def cmd_delete_by_query(c, args):
    with open(args.body) as fh:
        body = json.loads(fh.read())
    matched = _count_matches(c, args.index, body)
    if not _confirm_or_dry(args, f"DELETE-BY-QUERY on {args.index} - will DELETE {matched} docs (unrecoverable)",
                           {"index": args.index, "matches": matched, "query": body.get("query")}):
        return
    params = {"conflicts": "proceed"} if args.conflicts_proceed else {}
    params["wait_for_completion"] = "true" if args.wait else "false"
    print(_pretty(c.json_request("POST", f"/{args.index}/_delete_by_query",
                                 body=json.dumps(body), params=params)))


def _safe_json(resp):
    try:
        return resp.json()
    except ValueError:
        return resp.text


def build_parser():
    p = argparse.ArgumentParser(description="AWS managed OpenSearch (SigV4) client")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        sp = sub.add_parser(name, help=help_)
        sp.set_defaults(func=fn)
        return sp

    add("health", cmd_health, "cluster health")

    sp = add("indices", cmd_indices, "list indices (_cat), optional pattern")
    sp.add_argument("pattern", nargs="?", default="")

    sp = add("mapping", cmd_mapping, "show index mapping")
    sp.add_argument("index")

    sp = add("settings", cmd_settings, "show index settings")
    sp.add_argument("index")

    sp = add("search", cmd_search, "run a search")
    sp.add_argument("index")
    sp.add_argument("--query", help="inline JSON query body")
    sp.add_argument("--body", help="path to JSON query body")
    sp.add_argument("--size", type=int, default=10)

    sp = add("count", cmd_count, "count docs (optionally --since 24h)")
    sp.add_argument("index")
    sp.add_argument("--since", help="e.g. 24h, 7d, 30m")
    sp.add_argument("--time-field", default="@timestamp")
    sp.add_argument("--body")
    sp.add_argument("--query")

    add("allocation", cmd_allocation, "explain unassigned shards")
    add("reroute-retry", cmd_reroute_retry, "retry failed shard allocations")

    sp = add("reindex", cmd_reindex, "reindex source -> dest (dry-run unless --confirm)")
    sp.add_argument("--source", required=True)
    sp.add_argument("--dest", required=True)
    sp.add_argument("--wait", action="store_true")
    sp.add_argument("--confirm", action="store_true")

    sp = add("put-mapping", cmd_put_mapping, "add fields to a mapping (dry-run unless --confirm)")
    sp.add_argument("index")
    sp.add_argument("--body", required=True)
    sp.add_argument("--confirm", action="store_true")

    sp = add("ism-get", cmd_ism_get, "get ISM policies (all, or one by name)")
    sp.add_argument("policy", nargs="?", default="")

    sp = add("ism-put", cmd_ism_put, "create/update ISM policy (dry-run unless --confirm)")
    sp.add_argument("policy")
    sp.add_argument("--body", required=True)
    sp.add_argument("--confirm", action="store_true")

    sp = add("snapshot-list", cmd_snapshot_list, "list snapshots in a repo")
    sp.add_argument("repo")

    sp = add("snapshot-create", cmd_snapshot_create, "create snapshot (dry-run unless --confirm)")
    sp.add_argument("repo")
    sp.add_argument("name")
    sp.add_argument("--indices", help="comma/pattern list; default all")
    sp.add_argument("--wait", action="store_true")
    sp.add_argument("--confirm", action="store_true")

    sp = add("snapshot-restore", cmd_snapshot_restore, "restore snapshot (dry-run unless --confirm)")
    sp.add_argument("repo")
    sp.add_argument("name")
    sp.add_argument("--indices")
    sp.add_argument("--confirm", action="store_true")

    sp = add("delete-index", cmd_delete_index, "delete index/pattern (dry-run unless --confirm)")
    sp.add_argument("index")
    sp.add_argument("--confirm", action="store_true")

    sp = add("close", cmd_close, "close index (dry-run unless --confirm)")
    sp.add_argument("index")
    sp.add_argument("--confirm", action="store_true")

    sp = add("open", cmd_open, "open a closed index")
    sp.add_argument("index")

    sp = add("cluster-setting", cmd_cluster_setting, "PUT _cluster/settings (dry-run unless --confirm)")
    sp.add_argument("--body", required=True)
    sp.add_argument("--confirm", action="store_true")

    # --- Dashboards saved objects ---
    sp = add("dashboards-export", cmd_dashboards_export,
             "export dashboards/visualizations/index-patterns to NDJSON")
    sp.add_argument("--type", nargs="+", help="object types (default: dashboard visualization index-pattern search)")
    sp.add_argument("--objects", nargs="+", help="specific objects as type:id (e.g. dashboard:abc123)")
    sp.add_argument("--tenant", help="securitytenant header (default: global)")
    sp.add_argument("--out", help="write NDJSON to this file (else stdout)")

    sp = add("dashboards-import", cmd_dashboards_import,
             "import saved objects from NDJSON (dry-run unless --confirm)")
    sp.add_argument("--body", required=True, help="path to NDJSON file")
    sp.add_argument("--overwrite", action="store_true", help="overwrite existing objects")
    sp.add_argument("--tenant")
    sp.add_argument("--confirm", action="store_true")

    sp = add("saved-object-find", cmd_saved_object_find, "list saved objects")
    sp.add_argument("--type", help="filter by type")
    sp.add_argument("--search", help="search term")
    sp.add_argument("--limit", type=int, default=50)
    sp.add_argument("--tenant")

    sp = add("saved-object-get", cmd_saved_object_get, "fetch one saved object")
    sp.add_argument("type")
    sp.add_argument("id")
    sp.add_argument("--tenant")

    sp = add("saved-object-delete", cmd_saved_object_delete,
             "delete a saved object (dry-run unless --confirm)")
    sp.add_argument("type")
    sp.add_argument("id")
    sp.add_argument("--tenant")
    sp.add_argument("--confirm", action="store_true")

    # --- Index editing ---
    sp = add("put-settings", cmd_put_settings,
             "edit index settings (dry-run unless --confirm)")
    sp.add_argument("index")
    sp.add_argument("--body", help="JSON settings file")
    sp.add_argument("--set", nargs="+", help="key=value pairs, e.g. index.number_of_replicas=2")
    sp.add_argument("--confirm", action="store_true")

    sp = add("aliases", cmd_aliases, "atomic alias actions via _aliases (dry-run unless --confirm)")
    sp.add_argument("--body", required=True, help="JSON with actions[]")
    sp.add_argument("--confirm", action="store_true")

    sp = add("update-by-query", cmd_update_by_query,
             "update docs matching a query (shows match count; dry-run unless --confirm)")
    sp.add_argument("index")
    sp.add_argument("--body", required=True, help="JSON with query + optional script")
    sp.add_argument("--conflicts-proceed", action="store_true")
    sp.add_argument("--wait", action="store_true")
    sp.add_argument("--confirm", action="store_true")

    sp = add("delete-by-query", cmd_delete_by_query,
             "delete docs matching a query (shows match count; dry-run unless --confirm)")
    sp.add_argument("index")
    sp.add_argument("--body", required=True, help="JSON with query")
    sp.add_argument("--conflicts-proceed", action="store_true")
    sp.add_argument("--wait", action="store_true")
    sp.add_argument("--confirm", action="store_true")

    sp = add("raw", cmd_raw, "raw signed request: raw <METHOD> <path> [--body f]")
    sp.add_argument("method")
    sp.add_argument("path")
    sp.add_argument("--body")
    sp.add_argument("--confirm", action="store_true")

    return p


def main():
    args = build_parser().parse_args()
    client = OpenSearchClient()
    args.func(client, args)


if __name__ == "__main__":
    main()
