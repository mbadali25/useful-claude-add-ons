#!/usr/bin/env python3
"""
wazuh_client.py — a self-contained client for an on-premises Wazuh deployment.

Two APIs live behind one Wazuh install and this client speaks both:

  * Server (Manager) API   — HTTPS, default port 55000, JWT auth.
      Manage agents, rules, decoders, groups, manager config, cluster, RBAC.
  * Indexer API            — HTTPS, default port 9200, OpenSearch REST + Query DSL.
      Search and aggregate alert/event data (wazuh-alerts-*, and in 5.x the
      per-category data streams).

Only stdlib + `requests` are required.

Configuration is read from environment variables so nothing sensitive is
hardcoded. Set what you need:

  Server API:
    WAZUH_API_URL         e.g. https://wazuh.example.local:55000  (default https://localhost:55000)
    WAZUH_API_USER        e.g. wazuh-wui
    WAZUH_API_PASSWORD

  Indexer API:
    WAZUH_INDEXER_URL     e.g. https://wazuh.example.local:9200    (default https://localhost:9200)
    WAZUH_INDEXER_USER    e.g. admin
    WAZUH_INDEXER_PASSWORD

  TLS (on-prem is usually self-signed):
    WAZUH_CA_BUNDLE       path to a CA/cert file to trust. If unset, TLS
                          verification is DISABLED and a warning is printed once.
                          Prefer setting this to the deployment's root-ca.pem.

CLI examples:
    python wazuh_client.py info
    python wazuh_client.py get /agents --params 'status=active&limit=100'
    python wazuh_client.py get-all /agents                       # auto-paginate
    python wazuh_client.py put  /active-response --json '{"command":"restart-wazuh0"}'
    python wazuh_client.py agents-summary
    python wazuh_client.py search wazuh-alerts-* --level 10 --since 24h
    python wazuh_client.py raw-search wazuh-alerts-* --body query.json

Import usage:
    from wazuh_client import WazuhClient
    c = WazuhClient()
    agents = c.get_all("/agents")
    hits   = c.indexer_search("wazuh-alerts-*", {"query": {...}})
"""

import argparse
import json
import os
import sys
import time
import warnings

try:
    import requests
    from requests.auth import HTTPBasicAuth
except ImportError:
    sys.exit("This client needs the 'requests' package: pip install requests")

# Wazuh on-prem is almost always self-signed. We manage verification explicitly
# below, so silence urllib3's own warning to keep output readable.
try:
    from urllib3.exceptions import InsecureRequestWarning
    warnings.simplefilter("ignore", InsecureRequestWarning)
except Exception:
    pass


def _verify_setting():
    """Return the `verify` value for requests: a CA path, or False (with a warning)."""
    ca = os.environ.get("WAZUH_CA_BUNDLE")
    if ca:
        return ca
    if not getattr(_verify_setting, "_warned", False):
        print(
            "WARNING: TLS verification is DISABLED (no WAZUH_CA_BUNDLE set). "
            "Set WAZUH_CA_BUNDLE to the deployment's root-ca.pem for production use.",
            file=sys.stderr,
        )
        _verify_setting._warned = True
    return False


class WazuhAPIError(Exception):
    """Raised when the Server API returns a non-zero `error` code or HTTP failure."""


class WazuhClient:
    def __init__(
        self,
        api_url=None,
        api_user=None,
        api_password=None,
        indexer_url=None,
        indexer_user=None,
        indexer_password=None,
        dashboard_url=None,
        dashboard_user=None,
        dashboard_password=None,
        verify=None,
        timeout=30,
    ):
        self.api_url = (api_url or os.environ.get("WAZUH_API_URL", "https://localhost:55000")).rstrip("/")
        self.api_user = api_user or os.environ.get("WAZUH_API_USER")
        self.api_password = api_password or os.environ.get("WAZUH_API_PASSWORD")

        self.indexer_url = (indexer_url or os.environ.get("WAZUH_INDEXER_URL", "https://localhost:9200")).rstrip("/")
        self.indexer_user = indexer_user or os.environ.get("WAZUH_INDEXER_USER")
        self.indexer_password = indexer_password or os.environ.get("WAZUH_INDEXER_PASSWORD")

        # Dashboard (OpenSearch Dashboards) — saved-objects import/export lives here,
        # NOT on the Indexer. Port 443 by default. Credentials are a Dashboard *login*
        # (a UI user with saved-objects permission), distinct from the Indexer user.
        self.dashboard_url = (dashboard_url or os.environ.get(
            "WAZUH_DASHBOARD_URL", "https://localhost:443")).rstrip("/")
        self.dashboard_user = dashboard_user or os.environ.get("WAZUH_DASHBOARD_USER")
        self.dashboard_password = dashboard_password or os.environ.get("WAZUH_DASHBOARD_PASSWORD")
        # Multi-tenant deployments scope saved objects per tenant; default to the
        # global tenant unless told otherwise.
        self.dashboard_tenant = os.environ.get("WAZUH_DASHBOARD_TENANT", "")

        self.verify = verify if verify is not None else _verify_setting()
        self.timeout = timeout

        self._token = None
        self._token_ts = 0.0
        # JWT default lifetime is 900s; refresh a little early to avoid races.
        self._token_ttl = 900 - 60

    # ---------------------------------------------------------------- Server API

    def _authenticate(self):
        if not (self.api_user and self.api_password):
            raise WazuhAPIError(
                "Server API credentials missing. Set WAZUH_API_USER and WAZUH_API_PASSWORD."
            )
        resp = requests.post(
            f"{self.api_url}/security/user/authenticate",
            params={"raw": "true"},
            auth=HTTPBasicAuth(self.api_user, self.api_password),
            verify=self.verify,
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise WazuhAPIError(
                f"Authentication failed ({resp.status_code}): {resp.text[:300]}"
            )
        self._token = resp.text.strip()
        self._token_ts = time.time()
        return self._token

    def _get_token(self):
        if not self._token or (time.time() - self._token_ts) > self._token_ttl:
            self._authenticate()
        return self._token

    def request(self, method, endpoint, params=None, json_body=None, retry_auth=True):
        """Call a Server API endpoint. Returns the parsed JSON envelope.

        Raises WazuhAPIError if the envelope reports `error != 0` or there are
        failed_items, so callers see partial failures instead of silently
        succeeding.
        """
        url = f"{self.api_url}/{endpoint.lstrip('/')}"
        headers = {"Authorization": f"Bearer {self._get_token()}"}
        resp = requests.request(
            method.upper(),
            url,
            headers=headers,
            params=params,
            json=json_body,
            verify=self.verify,
            timeout=self.timeout,
        )
        # A 401 usually means the JWT expired mid-session; re-auth once and retry.
        if resp.status_code == 401 and retry_auth:
            self._authenticate()
            return self.request(method, endpoint, params, json_body, retry_auth=False)

        try:
            data = resp.json()
        except ValueError as exc:
            raise WazuhAPIError(
                f"Non-JSON response ({resp.status_code}): {resp.text[:300]}") from exc

        if resp.status_code >= 400:
            raise WazuhAPIError(
                f"{method.upper()} {endpoint} -> {resp.status_code}: "
                f"{data.get('title') or data.get('detail') or json.dumps(data)[:300]}"
            )

        # Server API envelope: {"data": {...}, "message": "...", "error": 0}
        if isinstance(data, dict) and data.get("error", 0) not in (0, None):
            raise WazuhAPIError(f"API error {data['error']}: {data.get('message')}")

        inner = data.get("data") if isinstance(data, dict) else None
        if isinstance(inner, dict) and inner.get("total_failed_items", 0):
            # Surface partial failures loudly — common on bulk agent operations.
            print(
                f"WARNING: {inner['total_failed_items']} item(s) failed: "
                f"{json.dumps(inner.get('failed_items'))[:400]}",
                file=sys.stderr,
            )
        return data

    def get(self, endpoint, params=None):
        return self.request("GET", endpoint, params=params)

    def get_all(self, endpoint, params=None, page_size=500):
        """Auto-paginate a list endpoint using limit/offset.

        The Server API caps `limit` at 500 and returns
        data.total_affected_items so we know when to stop.
        """
        params = dict(params or {})
        params["limit"] = page_size
        offset = 0
        items = []
        while True:
            params["offset"] = offset
            data = self.get(endpoint, params=params)
            inner = data.get("data", {})
            batch = inner.get("affected_items", [])
            items.extend(batch)
            total = inner.get("total_affected_items", len(items))
            offset += len(batch)
            if not batch or offset >= total:
                break
        return items

    # A few convenience helpers for the most common on-prem questions -----------

    def api_info(self):
        return self.get("/")

    def agents_summary(self):
        return self.get("/agents/summary/status")

    def list_agents(self, status=None, **params):
        if status:
            params["status"] = status
        return self.get_all("/agents", params=params)

    def manager_status(self):
        return self.get("/manager/status")

    # --------------------------------------------------------------- Indexer API

    def _indexer_auth(self):
        if not (self.indexer_user and self.indexer_password):
            raise WazuhAPIError(
                "Indexer credentials missing. Set WAZUH_INDEXER_USER and WAZUH_INDEXER_PASSWORD."
            )
        return HTTPBasicAuth(self.indexer_user, self.indexer_password)

    def indexer_search(self, index, body, params=None):
        """Run an OpenSearch _search against an index/pattern. Returns parsed JSON."""
        url = f"{self.indexer_url}/{index}/_search"
        resp = requests.post(
            url,
            auth=self._indexer_auth(),
            headers={"Content-Type": "application/json"},
            json=body,
            params=params,
            verify=self.verify,
            timeout=self.timeout,
        )
        if resp.status_code >= 400:
            raise WazuhAPIError(f"Indexer search -> {resp.status_code}: {resp.text[:400]}")
        return resp.json()

    def indexer_cat_indices(self, pattern="wazuh-alerts-*"):
        url = f"{self.indexer_url}/_cat/indices/{pattern}"
        resp = requests.get(
            url,
            auth=self._indexer_auth(),
            params={"v": "true", "s": "index"},
            verify=self.verify,
            timeout=self.timeout,
        )
        if resp.status_code >= 400:
            raise WazuhAPIError(f"_cat/indices -> {resp.status_code}: {resp.text[:300]}")
        return resp.text

    def recent_alerts(self, index="wazuh-alerts-*", min_level=None, since="24h",
                      agent_name=None, size=50):
        """Build and run a common 'recent high-severity alerts' query."""
        filters = [{"range": {"timestamp": {"gte": f"now-{since}"}}}]
        if min_level is not None:
            filters.append({"range": {"rule.level": {"gte": int(min_level)}}})
        if agent_name:
            filters.append({"term": {"agent.name": agent_name}})
        body = {
            "size": size,
            "query": {"bool": {"filter": filters}},
            "sort": [{"timestamp": {"order": "desc"}}],
        }
        return self.indexer_search(index, body)

    # ------------------------------------------------------- Dashboard (saved objects)
    #
    # Wazuh Dashboard is OpenSearch Dashboards. Visualizations/dashboards/index-patterns
    # are "saved objects" managed through the /api/saved_objects/* API on the DASHBOARD
    # host (port 443) — a different host, port, auth, and content model from the Indexer.
    # Every write needs the `osd-xsrf` header or the Dashboard rejects it with a 400.

    def _dashboard_auth(self):
        if not (self.dashboard_user and self.dashboard_password):
            raise WazuhAPIError(
                "Dashboard credentials missing. Set WAZUH_DASHBOARD_URL, "
                "WAZUH_DASHBOARD_USER and WAZUH_DASHBOARD_PASSWORD (a Dashboard login "
                "with saved-objects permission, e.g. admin or a scoped UI user)."
            )
        return HTTPBasicAuth(self.dashboard_user, self.dashboard_password)

    def _dashboard_headers(self, extra=None):
        # osd-xsrf: required on all Dashboard API writes (renamed from kbn-xsrf).
        headers = {"osd-xsrf": "true"}
        if self.dashboard_tenant:
            headers["securitytenant"] = self.dashboard_tenant
        if extra:
            headers.update(extra)
        return headers

    def dashboard_export(self, types=None, objects=None, include_references_deep=True):
        """Export saved objects to ndjson text.

        Pass either `types` (e.g. ["dashboard","visualization","index-pattern"])
        or an explicit `objects` list of {"type","id"} dicts. `types` exports every
        object of those types; use it for a full backup. Returns the raw ndjson so
        it can be written to a file verbatim and committed / re-imported.
        """
        body = {"includeReferencesDeep": bool(include_references_deep)}
        if objects:
            body["objects"] = objects
        else:
            body["type"] = types or ["dashboard", "visualization", "search", "index-pattern"]
        resp = requests.post(
            f"{self.dashboard_url}/api/saved_objects/_export",
            auth=self._dashboard_auth(),
            headers=self._dashboard_headers({"Content-Type": "application/json"}),
            json=body,
            verify=self.verify,
            timeout=self.timeout,
        )
        if resp.status_code >= 400:
            raise WazuhAPIError(
                f"Dashboard export -> {resp.status_code}: {resp.text[:400]}"
            )
        return resp.text  # ndjson (one JSON object per line)

    def dashboard_import(self, ndjson_path, overwrite=False, create_new_copies=False):
        """Import an ndjson bundle of saved objects.

        overwrite=True resolves conflicts by replacing existing objects (matches the
        UI's "Automatically overwrite conflicts"). create_new_copies generates fresh
        IDs instead — mutually exclusive with overwrite. Returns the import summary,
        which reports successCount and any per-object errors (broken references show
        up here, the usual cause of a 404 when you later click the dashboard).
        """
        params = {}
        if create_new_copies:
            params["createNewCopies"] = "true"
        elif overwrite:
            params["overwrite"] = "true"
        with open(ndjson_path, "rb") as fh:
            files = {"file": ("export.ndjson", fh, "application/ndjson")}
            resp = requests.post(
                f"{self.dashboard_url}/api/saved_objects/_import",
                auth=self._dashboard_auth(),
                headers=self._dashboard_headers(),  # requests sets multipart boundary
                params=params,
                files=files,
                verify=self.verify,
                timeout=self.timeout,
            )
        if resp.status_code >= 400:
            raise WazuhAPIError(
                f"Dashboard import -> {resp.status_code}: {resp.text[:400]}"
            )
        return resp.json()

    def dashboard_list(self, obj_type="dashboard", per_page=100):
        """List saved objects of a type (id + title) so you can pick IDs to export."""
        resp = requests.get(
            f"{self.dashboard_url}/api/saved_objects/_find",
            auth=self._dashboard_auth(),
            headers=self._dashboard_headers(),
            params={"type": obj_type, "per_page": per_page, "fields": "title"},
            verify=self.verify,
            timeout=self.timeout,
        )
        if resp.status_code >= 400:
            raise WazuhAPIError(
                f"Dashboard _find -> {resp.status_code}: {resp.text[:300]}"
            )
        data = resp.json()
        return [
            {"id": o.get("id"), "title": (o.get("attributes") or {}).get("title")}
            for o in data.get("saved_objects", [])
        ]


# ------------------------------------------------------------------------- CLI

def _print(obj):
    print(json.dumps(obj, indent=2, default=str) if not isinstance(obj, str) else obj)


def main():
    p = argparse.ArgumentParser(description="On-premises Wazuh client (Server API + Indexer API)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("info", help="Server API basic info (GET /)")
    sub.add_parser("agents-summary", help="Agent status summary")

    g = sub.add_parser("get", help="GET a Server API endpoint")
    g.add_argument("endpoint")
    g.add_argument("--params", help="URL query string, e.g. 'status=active&limit=100'")

    ga = sub.add_parser("get-all", help="GET and auto-paginate a list endpoint")
    ga.add_argument("endpoint")
    ga.add_argument("--params", help="URL query string (limit/offset are managed for you)")

    for verb in ("post", "put", "delete"):
        w = sub.add_parser(verb, help=f"{verb.upper()} a Server API endpoint")
        w.add_argument("endpoint")
        w.add_argument("--params", help="URL query string")
        w.add_argument("--json", dest="body", help="JSON request body (string)")

    s = sub.add_parser("search", help="Convenience alert search against the Indexer")
    s.add_argument("index", nargs="?", default="wazuh-alerts-*")
    s.add_argument("--level", type=int, help="minimum rule.level")
    s.add_argument("--since", default="24h", help="relative window, e.g. 24h, 7d")
    s.add_argument("--agent", help="filter by agent.name")
    s.add_argument("--size", type=int, default=50)

    rs = sub.add_parser("raw-search", help="Raw OpenSearch _search with a JSON body file")
    rs.add_argument("index")
    rs.add_argument("--body", required=True, help="path to a JSON query file")

    sub.add_parser("indices", help="_cat/indices for wazuh-alerts-*")

    dl = sub.add_parser("dash-list", help="List Dashboard saved objects (id + title)")
    dl.add_argument("--type", default="dashboard",
                    help="saved-object type: dashboard, visualization, search, index-pattern")

    de = sub.add_parser("dash-export", help="Export Dashboard saved objects to ndjson")
    de.add_argument("--out", required=True, help="output .ndjson path")
    de.add_argument("--type", action="append", dest="types",
                    help="object type to export (repeatable). Omit for a full backup.")
    de.add_argument("--id", action="append", dest="ids",
                    help="export specific object id(s); pair with a single --type")

    di = sub.add_parser("dash-import", help="Import a Dashboard saved-objects ndjson bundle")
    di.add_argument("file", help="path to the .ndjson bundle")
    grp = di.add_mutually_exclusive_group()
    grp.add_argument("--overwrite", action="store_true",
                     help="replace existing objects on conflict")
    grp.add_argument("--new-copies", action="store_true",
                     help="import with fresh IDs instead of resolving conflicts")

    args = p.parse_args()
    c = WazuhClient()

    def parse_params(raw):
        if not raw:
            return None
        return dict(kv.split("=", 1) for kv in raw.split("&") if "=" in kv)

    try:
        if args.cmd == "info":
            _print(c.api_info())
        elif args.cmd == "agents-summary":
            _print(c.agents_summary())
        elif args.cmd == "get":
            _print(c.get(args.endpoint, params=parse_params(args.params)))
        elif args.cmd == "get-all":
            _print(c.get_all(args.endpoint, params=parse_params(args.params)))
        elif args.cmd in ("post", "put", "delete"):
            body = json.loads(args.body) if args.body else None
            _print(c.request(args.cmd, args.endpoint, params=parse_params(args.params), json_body=body))
        elif args.cmd == "search":
            _print(c.recent_alerts(args.index, min_level=args.level, since=args.since,
                                   agent_name=args.agent, size=args.size))
        elif args.cmd == "raw-search":
            with open(args.body, encoding="utf-8") as f:
                body = json.load(f)
            _print(c.indexer_search(args.index, body))
        elif args.cmd == "indices":
            _print(c.indexer_cat_indices())
        elif args.cmd == "dash-list":
            _print(c.dashboard_list(obj_type=args.type))
        elif args.cmd == "dash-export":
            objects = None
            if args.ids:
                if not args.types or len(args.types) != 1:
                    sys.exit("ERROR: --id requires exactly one --type")
                objects = [{"type": args.types[0], "id": i} for i in args.ids]
            ndjson = c.dashboard_export(types=args.types, objects=objects)
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(ndjson)
            n = sum(1 for line in ndjson.splitlines() if line.strip())
            print(f"Wrote {n} saved object(s) to {args.out}", file=sys.stderr)
        elif args.cmd == "dash-import":
            _print(c.dashboard_import(args.file, overwrite=args.overwrite,
                                      create_new_copies=args.new_copies))
    except WazuhAPIError as e:
        sys.exit(f"ERROR: {e}")


if __name__ == "__main__":
    main()
