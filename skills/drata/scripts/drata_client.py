#!/usr/bin/env python3
"""Drata Public API client + CLI.

Handles both auth methods (long-lived API key OR OAuth2 client-credentials),
region -> base-URL resolution, v1 (offset) and v2 (cursor) pagination,
429 retry with Retry-After, and a read-only / dry-run guard for mutations.

Credentials (read from environment, never hardcode):
  API key auth (simplest):
    DRATA_API_KEY          the Bearer key created in Settings > API Keys
  OAuth2 client-credentials auth (recommended for prod / CI):
    DRATA_OAUTH_TOKEN_URL  e.g. https://<auth-domain>/oauth/token
    DRATA_OAUTH_CLIENT_ID
    DRATA_OAUTH_CLIENT_SECRET
    DRATA_OAUTH_AUDIENCE
    DRATA_OAUTH_SCOPE      space-separated, e.g. "read:controls read:personnel"
  Region / host:
    DRATA_REGION           us | eu | apac   (default us)
    DRATA_BASE_URL         overrides region mapping entirely
  Safety:
    DRATA_READ_ONLY=1      block all POST/PUT/PATCH/DELETE

If both API key and OAuth env vars are present, OAuth is used.

CLI examples:
  python drata_client.py whoami
  python drata_client.py get /public/v2/controls --params 'workspaceId=1'
  python drata_client.py get-all /public/v2/users
  python drata_client.py get-all /public/personnel          # v1, offset-paged
  python drata_client.py post /public/personnel --json '{"email":"a@b.com","firstName":"A","lastName":"B"}'
  python drata_client.py put /public/personnel/{id}/employment-status --json '{"isActive":false}' --dry-run
  # target EU tenant, read-only:
  DRATA_REGION=eu DRATA_READ_ONLY=1 python drata_client.py get-all /public/v2/vendors

Library use:
  from drata_client import DrataClient
  c = DrataClient()
  for user in c.get_all("/public/v2/users"):
      print(user["email"])
"""

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

REGION_HOSTS = {
    "us": "https://public-api.drata.com",
    "eu": "https://public-api.eu.drata.com",
    "apac": "https://public-api.apac.drata.com",
}
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
# Drata sits behind Cloudflare, which returns 403 "Error 1010 browser_signature_banned"
# for the default urllib user-agent. Send an explicit one on every request.
USER_AGENT = "drata-client/1.0 (+https://developers.drata.com)"


class DrataClient:
    def __init__(self, api_key=None, base_url=None, region=None,
                 read_only=None, timeout=30):
        # --- base URL ---
        region = (region or os.environ.get("DRATA_REGION") or "us").lower()
        self.base_url = (
            base_url
            or os.environ.get("DRATA_BASE_URL")
            or REGION_HOSTS.get(region)
        )
        if not self.base_url:
            raise SystemExit(f"Unknown region '{region}'. Use one of: {', '.join(REGION_HOSTS)}")
        self.base_url = self.base_url.rstrip("/")

        # --- auth ---
        self._api_key = api_key or os.environ.get("DRATA_API_KEY")
        self._oauth = {
            "token_url": os.environ.get("DRATA_OAUTH_TOKEN_URL"),
            "client_id": os.environ.get("DRATA_OAUTH_CLIENT_ID"),
            "client_secret": os.environ.get("DRATA_OAUTH_CLIENT_SECRET"),
            "audience": os.environ.get("DRATA_OAUTH_AUDIENCE"),
            "scope": os.environ.get("DRATA_OAUTH_SCOPE", ""),
        }
        self._use_oauth = all(
            self._oauth[k] for k in ("token_url", "client_id", "client_secret")
        )
        if not self._use_oauth and not self._api_key:
            raise SystemExit(
                "No credentials. Set DRATA_API_KEY, or the DRATA_OAUTH_* variables "
                "(TOKEN_URL, CLIENT_ID, CLIENT_SECRET[, AUDIENCE, SCOPE])."
            )

        self.read_only = (
            read_only if read_only is not None
            else os.environ.get("DRATA_READ_ONLY", "") not in ("", "0", "false", "False")
        )
        self.timeout = timeout
        self._token = None
        self._token_expiry = 0

    # ---------- auth ----------

    def _bearer(self):
        if not self._use_oauth:
            return self._api_key
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        payload = json.dumps({
            "client_id": self._oauth["client_id"],
            "client_secret": self._oauth["client_secret"],
            "audience": self._oauth["audience"],
            "grant_type": "client_credentials",
            "scope": self._oauth["scope"],
        }).encode()
        req = urllib.request.Request(
            self._oauth["token_url"],
            data=payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "user-agent": USER_AGENT,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:600]
            raise SystemExit(f"OAuth token request -> {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise SystemExit(f"OAuth token request failed: {e.reason}") from e
        self._token = body["access_token"]
        self._token_expiry = time.time() + int(body.get("expires_in", 3600))
        return self._token

    # ---------- http core ----------

    def _request(self, method, path, params=None, json_body=None, retries=4):
        method = method.upper()
        if method in MUTATING and self.read_only:
            raise SystemExit(
                f"Refusing {method} {path}: client is read-only "
                "(unset DRATA_READ_ONLY / pass read_only=False to allow writes)."
            )
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        headers = {
            "Authorization": f"Bearer {self._bearer()}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        data = None
        if json_body is not None:
            data = json.dumps(json_body).encode()
            headers["Content-Type"] = "application/json"
        for attempt in range(retries + 1):
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    status = resp.status
                    content = resp.read()
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < retries:
                    wait = int(e.headers.get("Retry-After", 2 ** (attempt + 1)))
                    time.sleep(wait)
                    continue
                detail = e.read().decode(errors="replace")[:600]
                raise SystemExit(f"{method} {url} -> {e.code}: {detail}") from e
            except urllib.error.URLError as e:
                raise SystemExit(f"{method} {url} failed: {e.reason}") from e
            if status == 204 or not content:
                return {"status": status}
            return json.loads(content.decode())
        raise SystemExit(f"{method} {url}: exhausted retries on 429")

    # ---------- convenience verbs ----------

    def get(self, path, params=None):
        return self._request("GET", path, params=params)

    def post(self, path, json_body=None, params=None):
        return self._request("POST", path, params=params, json_body=json_body or {})

    def put(self, path, json_body=None, params=None):
        return self._request("PUT", path, params=params, json_body=json_body or {})

    def patch(self, path, json_body=None, params=None):
        return self._request("PATCH", path, params=params, json_body=json_body or {})

    def delete(self, path, params=None):
        return self._request("DELETE", path, params=params)

    def whoami(self):
        """Lightweight identity/connectivity check via the company endpoint."""
        for path in ("/public/v2/company", "/public/companies", "/public/v2/workspaces"):
            try:
                return {"endpoint": path, "result": self.get(path)}
            except SystemExit:
                continue
        raise SystemExit("Could not reach any identity endpoint — check key, scope, and region.")

    def get_all(self, path, params=None, max_pages=1000):
        """Yield every record across all pages.

        Auto-detects pagination style from the response:
          * v2 -> cursor in body['pagination']['cursor'] (or nextCursor)
          * v1 -> offset via total/page/limit
        Both versions return records under body['data'].
        """
        params = dict(params or {})
        pages = 0
        while pages < max_pages:
            pages += 1
            body = self.get(path, params=params)
            data = body.get("data", body if isinstance(body, list) else [])
            if isinstance(data, list):
                yield from data
            else:
                yield data
                return

            pg = body.get("pagination") or {}
            cursor = pg.get("cursor") or pg.get("nextCursor")
            if cursor:                                   # v2 cursor style
                params["cursor"] = cursor
                continue

            total = body.get("total")                    # v1 offset style
            page = body.get("page")
            limit = body.get("limit")
            if total is not None and page is not None and limit:
                if page * limit >= total:
                    return
                params["page"] = page + 1
                continue
            return  # single page / unknown shape


# ---------- CLI ----------

def _parse_params(pairs):
    out = {}
    for p in pairs or []:
        if "=" not in p:
            raise SystemExit(f"--params entries must be key=value (got '{p}')")
        k, v = p.split("=", 1)
        out[k] = v
    return out


def main():
    ap = argparse.ArgumentParser(description="Drata Public API CLI")
    ap.add_argument("--region", help="us | eu | apac (default us or $DRATA_REGION)")
    ap.add_argument("--base-url", help="override the region host entirely")
    ap.add_argument("--dry-run", action="store_true",
                    help="for mutations: print the request instead of sending it "
                         "(accepted before or after the verb)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("whoami")
    for verb in ("get", "get-all"):
        p = sub.add_parser(verb)
        p.add_argument("path", help="API path, e.g. /public/v2/controls")
        p.add_argument("--params", nargs="*", help="key=value query params")
    for verb in ("post", "put", "patch", "delete"):
        p = sub.add_parser(verb)
        p.add_argument("path")
        p.add_argument("--params", nargs="*", help="key=value query params")
        p.add_argument("--dry-run", action="store_true", default=argparse.SUPPRESS,
                       help="print the request instead of sending it")
        if verb != "delete":
            p.add_argument("--json", dest="json_body", default="{}", help="JSON body")

    args = ap.parse_args()
    c = DrataClient(base_url=args.base_url, region=args.region)

    if args.cmd == "whoami":
        print(json.dumps(c.whoami(), indent=2))
        return
    params = _parse_params(getattr(args, "params", None))

    if args.cmd == "get":
        print(json.dumps(c.get(args.path, params), indent=2))
    elif args.cmd == "get-all":
        print(json.dumps(list(c.get_all(args.path, params)), indent=2))
    else:  # mutating verbs
        body = None
        if args.cmd != "delete":
            body = json.loads(args.json_body)
        if args.dry_run:
            print(json.dumps({
                "dry_run": True, "method": args.cmd.upper(),
                "url": f"{c.base_url}{args.path}", "params": params, "body": body,
            }, indent=2))
            return
        method = getattr(c, args.cmd)
        result = method(args.path, params=params) if args.cmd == "delete" \
            else method(args.path, json_body=body, params=params)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
