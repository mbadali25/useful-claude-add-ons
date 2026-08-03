#!/usr/bin/env python3
"""Cloudflare v4 API client + CLI.

Self-contained, standard library only (urllib) - no third-party packages.

Handles both auth methods (scoped API token, preferred; or legacy Global API
Key), the standard {success, errors, messages, result, result_info} envelope,
offset pagination (page/per_page) with a cursor pass-through for the newer
endpoints, exponential 429 backoff (Cloudflare sends no Retry-After), and a
read-only / dry-run guard for every mutating call.

Credentials come from env vars (flags override):
  CLOUDFLARE_API_TOKEN                     scoped token  -> Authorization: Bearer
  CLOUDFLARE_EMAIL + CLOUDFLARE_API_KEY    legacy global -> X-Auth-Email/X-Auth-Key
Token wins if both are set. Set CLOUDFLARE_READ_ONLY=1 to block all mutations.

CLI examples:
  python cloudflare_client.py verify
  python cloudflare_client.py zone-id example.com
  python cloudflare_client.py account-id "My Org"
  python cloudflare_client.py get     /zones/{zid}/dns_records --params type=A name=www.example.com
  python cloudflare_client.py get-all /zones/{zid}/dns_records
  python cloudflare_client.py post    /zones/{zid}/dns_records \
      --json '{"type":"A","name":"www","content":"1.2.3.4","ttl":300,"proxied":true}'
  python cloudflare_client.py put     /zones/{zid}/dns_records/{rid} \
      --json '{"type":"A","name":"www","content":"5.6.7.8","proxied":true}' --dry-run
  python cloudflare_client.py delete   /zones/{zid}/dns_records/{rid}

Library use:
  from cloudflare_client import CloudflareClient
  c = CloudflareClient()
  zid = c.zone_id("example.com")
  for rec in c.get_all(f"/zones/{zid}/dns_records", params={"type": "A"}):
      print(rec["name"], rec["content"])
"""

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://api.cloudflare.com/client/v4"
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


class CloudflareError(SystemExit):
    """Raised with the Cloudflare error code + message surfaced verbatim."""


class CloudflareClient:
    def __init__(self, token=None, email=None, api_key=None,
                 read_only=None, timeout=30):
        self.token = token or os.environ.get("CLOUDFLARE_API_TOKEN")
        self.email = email or os.environ.get("CLOUDFLARE_EMAIL")
        self.api_key = api_key or os.environ.get("CLOUDFLARE_API_KEY")
        if not self.token and not (self.email and self.api_key):
            raise CloudflareError(
                "Missing credentials: set CLOUDFLARE_API_TOKEN (preferred), "
                "or CLOUDFLARE_EMAIL + CLOUDFLARE_API_KEY (legacy)."
            )
        if read_only is None:
            read_only = os.environ.get("CLOUDFLARE_READ_ONLY", "") not in ("", "0", "false", "False")
        self.read_only = read_only
        self.timeout = timeout

    # ---------- auth ----------

    def _auth_headers(self):
        if self.token:                       # token wins if both are set
            return {"Authorization": f"Bearer {self.token}"}
        return {"X-Auth-Email": self.email, "X-Auth-Key": self.api_key}

    # ---------- http core ----------

    def _request(self, method, path, params=None, json_body=None,
                 dry_run=False, retries=4):
        method = method.upper()
        url = f"{BASE_URL}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params, doseq=True)

        # Mutation guard: never send when read-only or dry-run; return a preview.
        if method in MUTATING and (self.read_only or dry_run):
            reason = "read-only mode" if self.read_only else "dry-run"
            return {
                "dry_run": True,
                "reason": reason,
                "would_send": {"method": method, "url": url, "body": json_body},
            }

        headers = self._auth_headers()
        headers["Accept"] = "application/json"
        data = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        for attempt in range(retries + 1):
            req = urllib.request.Request(url, data=data, method=method, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    status = resp.status
                    raw = resp.read()
            except urllib.error.HTTPError as e:
                status = e.code
                raw = e.read()
            except urllib.error.URLError as e:
                raise CloudflareError(f"{method} {path}: network error: {e.reason}") from e

            # 429: no Retry-After from Cloudflare -> exponential backoff.
            if status == 429 and attempt < retries:
                time.sleep(2 ** (attempt + 1))
                continue

            body = json.loads(raw) if raw else {}
            if status >= 400 or (isinstance(body, dict) and body.get("success") is False):
                errs = body.get("errors") if isinstance(body, dict) else None
                detail = "; ".join(
                    f"[{e.get('code')}] {e.get('message')}" for e in (errs or [])
                ) or (raw.decode("utf-8", "replace")[:500] if raw else "no body")
                raise CloudflareError(f"{method} {path} -> HTTP {status}: {detail}")
            return body

        raise CloudflareError(f"{method} {path}: exhausted retries on 429")

    # ---------- convenience ----------

    def verify(self):
        """GET /user/tokens/verify - fastest way to confirm the token is good."""
        return self._request("GET", "/user/tokens/verify")

    def zone_id(self, name):
        body = self._request("GET", "/zones", params={"name": name})
        result = body.get("result") or []
        if not result:
            raise CloudflareError(f"No zone found matching name '{name}'")
        if len(result) > 1:
            names = ", ".join(z.get("name", "?") for z in result)
            raise CloudflareError(f"Ambiguous zone name '{name}' matched: {names}")
        return result[0]["id"]

    def account_id(self, name):
        body = self._request("GET", "/accounts", params={"name": name})
        result = body.get("result") or []
        if not result:
            raise CloudflareError(f"No account found matching name '{name}'")
        if len(result) > 1:
            names = ", ".join(a.get("name", "?") for a in result)
            raise CloudflareError(f"Ambiguous account name '{name}' matched: {names}")
        return result[0]["id"]

    def get(self, path, params=None):
        return self._request("GET", path, params=params)

    def get_all(self, path, params=None):
        """Yield every item across all pages.

        Offset pagination via result_info.total_pages. If the caller supplies a
        'cursor' param (some Zero Trust / Workers endpoints), it is passed
        through and cursor paging is followed via result_info.cursors.after.
        """
        params = dict(params or {})
        cursor_mode = "cursor" in params
        page = int(params.get("page", 1))
        while True:
            if not cursor_mode:
                params["page"] = page
            body = self.get(path, params=params)
            result = body.get("result") or []
            yield from result
            info = body.get("result_info") or {}
            if cursor_mode:
                after = (info.get("cursors") or {}).get("after")
                if not after:
                    return
                params["cursor"] = after
                continue
            total_pages = info.get("total_pages")
            if not total_pages or page >= total_pages:
                return
            page += 1

    def post(self, path, json_body, params=None, dry_run=False):
        return self._request("POST", path, params=params, json_body=json_body, dry_run=dry_run)

    def put(self, path, json_body, params=None, dry_run=False):
        return self._request("PUT", path, params=params, json_body=json_body, dry_run=dry_run)

    def patch(self, path, json_body, params=None, dry_run=False):
        return self._request("PATCH", path, params=params, json_body=json_body, dry_run=dry_run)

    def delete(self, path, params=None, dry_run=False):
        return self._request("DELETE", path, params=params, dry_run=dry_run)


# ---------- CLI ----------

def _parse_params(pairs):
    out = {}
    for p in pairs or []:
        if "=" not in p:
            raise CloudflareError(f"--params entries must be key=value (got '{p}')")
        k, v = p.split("=", 1)
        if k in out:                          # repeatable -> list (doseq encodes it)
            out[k] = (out[k] if isinstance(out[k], list) else [out[k]]) + [v]
        else:
            out[k] = v
    return out


def main():
    ap = argparse.ArgumentParser(description="Cloudflare v4 API CLI (stdlib only)")
    ap.add_argument("--token", help="scoped API token (else $CLOUDFLARE_API_TOKEN)")
    ap.add_argument("--email", help="legacy account email (else $CLOUDFLARE_EMAIL)")
    ap.add_argument("--api-key", help="legacy Global API Key (else $CLOUDFLARE_API_KEY)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("verify", help="GET /user/tokens/verify")

    p = sub.add_parser("zone-id", help="resolve a zone name to its 32-char id")
    p.add_argument("name")
    p = sub.add_parser("account-id", help="resolve an account name to its id")
    p.add_argument("name")

    for verb in ("get", "get-all"):
        p = sub.add_parser(verb)
        p.add_argument("path", help="API path, e.g. /zones/{zid}/dns_records")
        p.add_argument("--params", nargs="*", help="key=value query params (repeatable)")

    for verb in ("post", "put", "patch"):
        p = sub.add_parser(verb)
        p.add_argument("path")
        p.add_argument("--json", dest="json_body", default="{}", help="JSON request body")
        p.add_argument("--params", nargs="*", help="key=value query params")
        p.add_argument("--dry-run", action="store_true", help="print request, do not send")

    p = sub.add_parser("delete")
    p.add_argument("path")
    p.add_argument("--params", nargs="*", help="key=value query params")
    p.add_argument("--dry-run", action="store_true", help="print request, do not send")

    args = ap.parse_args()
    c = CloudflareClient(token=args.token, email=args.email, api_key=args.api_key)

    if args.cmd == "verify":
        out = c.verify()
    elif args.cmd == "zone-id":
        out = c.zone_id(args.name)
    elif args.cmd == "account-id":
        out = c.account_id(args.name)
    elif args.cmd == "get":
        out = c.get(args.path, _parse_params(args.params))
    elif args.cmd == "get-all":
        out = list(c.get_all(args.path, _parse_params(args.params)))
    elif args.cmd in ("post", "put", "patch"):
        body = json.loads(args.json_body)
        out = getattr(c, args.cmd)(args.path, body,
                                   params=_parse_params(args.params),
                                   dry_run=args.dry_run)
    elif args.cmd == "delete":
        out = c.delete(args.path, params=_parse_params(args.params), dry_run=args.dry_run)
    else:
        ap.error(f"unknown command {args.cmd}")
        return

    print(json.dumps(out, indent=2) if not isinstance(out, str) else out)


if __name__ == "__main__":
    main()
