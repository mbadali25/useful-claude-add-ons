#!/usr/bin/env python3
"""Sophos Central API client + CLI.

Handles OAuth2 client-credentials auth, whoami/region resolution, tenant
headers, key- and offset-based pagination, and 429 retry.

Credentials come from env vars SOPHOS_CLIENT_ID / SOPHOS_CLIENT_SECRET
(or --client-id/--client-secret flags; env preferred).

CLI examples:
  python sophos_client.py whoami
  python sophos_client.py tenants                      # partner/org creds only
  python sophos_client.py get /endpoint/v1/endpoints --params healthStatus=bad view=summary
  python sophos_client.py get-all /endpoint/v1/endpoints
  python sophos_client.py post "/endpoint/v1/endpoints/{id}/scans" --json '{}'
  python sophos_client.py delete /endpoint/v1/endpoints/{id}
  python sophos_client.py siem-events --since 12h
  # Partner creds targeting one tenant:
  python sophos_client.py --tenant <tenant-uuid> get /common/v1/alerts

Library use:
  from sophos_client import SophosClient
  c = SophosClient()                      # tenant credential
  for ep in c.get_all("/endpoint/v1/endpoints", params={"healthStatus": "bad"}):
      print(ep["hostname"])
"""

import argparse
import json
import os
import sys
import time

import requests

AUTH_URL = "https://id.sophos.com/api/v2/oauth2/token"
GLOBAL_API = "https://api.central.sophos.com"


class SophosClient:
    def __init__(self, client_id=None, client_secret=None, tenant_id=None, timeout=30):
        self.client_id = client_id or os.environ.get("SOPHOS_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("SOPHOS_CLIENT_SECRET")
        if not self.client_id or not self.client_secret:
            raise SystemExit(
                "Missing credentials: set SOPHOS_CLIENT_ID and SOPHOS_CLIENT_SECRET"
            )
        self.timeout = timeout
        self._token = None
        self._token_expiry = 0
        self._whoami = None
        self._explicit_tenant = tenant_id
        self._tenant_id = None
        self._base_url = None

    # ---------- auth ----------

    def token(self):
        if self._token and time.time() < self._token_expiry - 300:
            return self._token
        r = requests.post(
            AUTH_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "token",
            },
            timeout=self.timeout,
        )
        r.raise_for_status()
        body = r.json()
        self._token = body["access_token"]
        self._token_expiry = time.time() + int(body.get("expires_in", 3600))
        return self._token

    def whoami(self):
        if self._whoami is None:
            r = requests.get(
                f"{GLOBAL_API}/whoami/v1",
                headers={"Authorization": f"Bearer {self.token()}"},
                timeout=self.timeout,
            )
            r.raise_for_status()
            self._whoami = r.json()
        return self._whoami

    def tenants(self):
        """Enumerate tenants (partner/organization credentials only)."""
        who = self.whoami()
        id_type = who["idType"]
        if id_type == "tenant":
            return [{"id": who["id"], "apiHost": who["apiHosts"]["dataRegion"]}]
        header = "X-Partner-ID" if id_type == "partner" else "X-Organization-ID"
        path = "partner" if id_type == "partner" else "organization"
        out, page = [], 1
        while True:
            r = self._request_raw(
                "GET",
                f"{GLOBAL_API}/{path}/v1/tenants",
                headers={header: who["id"]},
                params={"page": page, "pageSize": 100, "pageTotal": "true"},
            )
            body = r.json()
            out.extend(body.get("items", []))
            pages = body.get("pages", {})
            if page >= pages.get("total", 1):
                return out
            page += 1

    def _resolve_context(self):
        """Determine tenant id + regional base URL for tenant-level calls."""
        if self._tenant_id and self._base_url:
            return
        who = self.whoami()
        if who["idType"] == "tenant":
            self._tenant_id = who["id"]
            self._base_url = who["apiHosts"]["dataRegion"]
            return
        if not self._explicit_tenant:
            raise SystemExit(
                f"Credential is idType={who['idType']}; pass --tenant <tenant-id> "
                "(use the 'tenants' command to list them)"
            )
        for t in self.tenants():
            if t["id"] == self._explicit_tenant:
                self._tenant_id = t["id"]
                self._base_url = t.get("apiHost")
                if not self._base_url:
                    raise SystemExit(f"Tenant {t['id']} has no apiHost (inactive?)")
                return
        raise SystemExit(f"Tenant {self._explicit_tenant} not found for this credential")

    # ---------- http core ----------

    def _request_raw(self, method, url, headers=None, retries=4, **kwargs):
        hdrs = {"Authorization": f"Bearer {self.token()}", "Accept": "application/json"}
        if headers:
            hdrs.update(headers)
        for attempt in range(retries + 1):
            r = requests.request(method, url, headers=hdrs, timeout=self.timeout, **kwargs)
            if r.status_code == 429 and attempt < retries:
                wait = int(r.headers.get("Retry-After", 2 ** (attempt + 1)))
                time.sleep(wait)
                continue
            if r.status_code >= 400:
                cid = ""
                try:
                    cid = r.json().get("correlationId", "")
                except Exception:
                    pass
                raise SystemExit(
                    f"{method} {url} -> {r.status_code}: {r.text[:500]}"
                    + (f" (correlationId={cid})" if cid else "")
                )
            return r
        raise SystemExit(f"{method} {url}: exhausted retries on 429")

    def request(self, method, path, params=None, json_body=None):
        """Tenant-scoped request. `path` like /endpoint/v1/endpoints."""
        self._resolve_context()
        r = self._request_raw(
            method,
            f"{self._base_url}{path}",
            headers={"X-Tenant-ID": self._tenant_id},
            params=params,
            json=json_body,
        )
        if r.status_code == 204 or not r.content:
            return {"status": r.status_code}
        return r.json()

    def get(self, path, params=None):
        return self.request("GET", path, params=params)

    def get_all(self, path, params=None):
        """Iterate all items across pages (handles key- and offset-paging)."""
        params = dict(params or {})
        while True:
            body = self.get(path, params=params)
            items = body.get("items", [])
            for item in items:
                yield item
            pages = body.get("pages", {})
            next_key = pages.get("nextKey")
            if next_key:
                params["pageFromKey"] = next_key
                continue
            current, total = pages.get("current"), pages.get("total")
            if current and total and current < total:
                params["page"] = current + 1
                continue
            return

    def siem_events(self, since_seconds=None, kind="events"):
        """Yield SIEM events/alerts. kind: 'events' or 'alerts'."""
        params = {"limit": 1000}
        if since_seconds:
            params["from_date"] = int(time.time()) - since_seconds
        while True:
            body = self.get(f"/siem/v1/{kind}", params=params)
            for item in body.get("items", []):
                yield item
            if not body.get("has_more"):
                return
            params = {"limit": 1000, "cursor": body["next_cursor"]}


# ---------- CLI ----------

def _parse_params(pairs):
    out = {}
    for p in pairs or []:
        if "=" not in p:
            raise SystemExit(f"--params entries must be key=value (got '{p}')")
        k, v = p.split("=", 1)
        if k in out:  # repeatable params -> list
            out[k] = (out[k] if isinstance(out[k], list) else [out[k]]) + [v]
        else:
            out[k] = v
    return out


def _duration_to_seconds(s):
    units = {"m": 60, "h": 3600, "d": 86400}
    if s and s[-1] in units:
        return int(float(s[:-1]) * units[s[-1]])
    return int(s)


def main():
    ap = argparse.ArgumentParser(description="Sophos Central API CLI")
    ap.add_argument("--client-id")
    ap.add_argument("--client-secret")
    ap.add_argument("--tenant", help="Tenant ID (required for partner/org credentials)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("whoami")
    sub.add_parser("tenants")

    for verb in ("get", "get-all", "post", "patch", "delete"):
        p = sub.add_parser(verb)
        p.add_argument("path", help="API path, e.g. /endpoint/v1/endpoints")
        p.add_argument("--params", nargs="*", help="key=value query params")
        if verb in ("post", "patch"):
            p.add_argument("--json", dest="json_body", default="{}", help="JSON body")

    p = sub.add_parser("siem-events")
    p.add_argument("--since", default="24h", help="e.g. 30m, 12h, 1d (max 24h window)")
    p.add_argument("--alerts", action="store_true", help="pull /siem/v1/alerts instead")

    args = ap.parse_args()
    c = SophosClient(args.client_id, args.client_secret, tenant_id=args.tenant)

    if args.cmd == "whoami":
        print(json.dumps(c.whoami(), indent=2))
    elif args.cmd == "tenants":
        print(json.dumps(c.tenants(), indent=2))
    elif args.cmd == "get":
        print(json.dumps(c.get(args.path, _parse_params(args.params)), indent=2))
    elif args.cmd == "get-all":
        print(json.dumps(list(c.get_all(args.path, _parse_params(args.params))), indent=2))
    elif args.cmd in ("post", "patch"):
        body = json.loads(args.json_body)
        print(json.dumps(c.request(args.cmd.upper(), args.path,
                                   params=_parse_params(args.params),
                                   json_body=body), indent=2))
    elif args.cmd == "delete":
        print(json.dumps(c.request("DELETE", args.path,
                                   params=_parse_params(args.params)), indent=2))
    elif args.cmd == "siem-events":
        kind = "alerts" if args.alerts else "events"
        for item in c.siem_events(_duration_to_seconds(args.since), kind=kind):
            print(json.dumps(item))


if __name__ == "__main__":
    main()
