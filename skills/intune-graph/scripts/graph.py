#!/usr/bin/env python3
"""Graph request helper for Intune: paging, throttle handling, readable errors.

Why this exists instead of calling requests directly:
  - Intune list endpoints page at 100-1000 items via @odata.nextLink
  - Intune throttles hard (429) and expects Retry-After to be honored
  - Intune buries its real error inside error.message as a JSON *string*,
    so the useful text is invisible unless you unwrap it

CLI:
    python graph.py GET  "deviceManagement/managedDevices" --filter "..." --select "..."
    python graph.py POST "deviceManagement/managedDevices/{id}/syncDevice"
    python graph.py PATCH "deviceManagement/managedDevices/{id}" --body '{"...":"..."}'

Library:
    from graph import GraphClient
    g = GraphClient()
    for d in g.get_all("deviceManagement/managedDevices", filter="..."):
        ...
"""
import argparse
import json
import os
import sys
import time

import requests

from auth import get_token, AuthError

V1 = "https://graph.microsoft.com/v1.0"
BETA = "https://graph.microsoft.com/beta"
MAX_RETRIES = 5


class GraphError(Exception):
    pass


def _explain(resp):
    """Pull the human-meaningful message out of a Graph/Intune error response."""
    try:
        err = resp.json().get("error", {})
    except ValueError:
        return f"HTTP {resp.status_code}: {resp.text[:400]}"

    code = err.get("code", "")
    msg = err.get("message", "")
    # Intune nests a JSON string inside .message - unwrap it if present.
    inner = ""
    if isinstance(msg, str) and msg.strip().startswith("{"):
        try:
            inner = json.loads(msg).get("Message", "")
        except ValueError:
            pass
    detail = inner or msg
    out = f"HTTP {resp.status_code} [{code}]: {detail}"

    if resp.status_code == 403:
        out += ("\n  -> Usually a missing scope or absent admin consent. App-only tokens need "
                "APPLICATION permissions, not delegated. Run: python scripts/auth.py --check")
    elif resp.status_code == 404:
        out += "\n  -> Check the resource exists in v1.0; some Intune resources are beta-only (--beta)."
    return out


class GraphClient:
    def __init__(self, mode=None, beta=False):
        self.base = BETA if beta else V1
        self._token = get_token(mode=mode)
        self.session = requests.Session()

    def _headers(self):
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    def request(self, method, url, body=None, params=None):
        if not url.startswith("http"):
            url = f"{self.base}/{url.lstrip('/')}"

        for attempt in range(MAX_RETRIES):
            r = self.session.request(
                method, url, headers=self._headers(), params=params,
                json=body if body is not None else None, timeout=120,
            )
            if r.status_code == 429 or r.status_code >= 500:
                # Retry-After is authoritative for Intune; fall back to backoff.
                wait = int(r.headers.get("Retry-After", 2 ** attempt))
                if attempt == MAX_RETRIES - 1:
                    raise GraphError(_explain(r))
                print(f"  throttled ({r.status_code}), waiting {wait}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            if not r.ok:
                raise GraphError(_explain(r))
            if r.status_code == 204 or not r.content:
                return None
            return r.json()
        raise GraphError("Exhausted retries.")

    # `filter` shadows the builtin deliberately: it mirrors OData's $filter.
# pylint: disable-next=redefined-builtin
    def get_all(self, path, filter=None, select=None, expand=None, top=None, max_items=None):
        """GET a collection, following @odata.nextLink. Returns a list."""
        params = {}
        if filter:
            params["$filter"] = filter
        if select:
            params["$select"] = select
        if expand:
            params["$expand"] = expand
        if top:
            params["$top"] = top

        items, url, first = [], path, True
        while url:
            data = self.request("GET", url, params=params if first else None)
            first = False
            if data is None:
                break
            if "value" not in data:
                return [data]  # single entity, not a collection
            items.extend(data["value"])
            if max_items and len(items) >= max_items:
                return items[:max_items]
            url = data.get("@odata.nextLink")
        return items

    def get(self, path, **kw):
        return self.request("GET", path, params={f"${k}": v for k, v in kw.items() if v})

    def post(self, path, body=None):
        return self.request("POST", path, body=body)

    def patch(self, path, body):
        return self.request("PATCH", path, body=body)

    def delete(self, path):
        return self.request("DELETE", path)


# Actions with no undo. Intune queues these against real hardware: a wipe
# reimages a user's laptop, a retire strips corporate data, a deleted
# configuration policy stops applying to every device in its assignment. None
# of them can be reversed from this tool, so none of them run from a one-liner.
IRREVERSIBLE = (
    "/wipe", "/retire", "/deleteuserfromsharedappledevice",
    "/rebootnow", "/shutdown", "/resetpasscode", "/disable",
    "/recoverypasswordrotation", "/revokeapplevpplicenses",
    "/cleanwindowsdevice", "/windowsdefenderscan",
)


def check_mutation(method, path, assume_yes):
    """Refuse an unsafe write, or ask. Returns nothing; raises to refuse.

    Read-only by default is deliberate for a fleet-management API. The cost of
    an accidental GET is nothing; the cost of an accidental wipe is somebody's
    laptop.
    """
    if method == "GET":
        return
    if os.environ.get("INTUNE_READ_ONLY", "").lower() in ("1", "true", "yes"):
        raise GraphError(
            0, f"INTUNE_READ_ONLY is set - refusing {method} {path}. "
               f"Unset it to allow writes.")

    low = "/" + path.lower().lstrip("/")
    hit = next((a for a in IRREVERSIBLE if a in low), None)
    if hit:
        raise GraphError(
            0,
            f"Refusing {method} {path}.\n"
            f"'{hit.strip('/')}' cannot be undone from this tool - it acts on real "
            f"hardware or strips data from it. Run it from the Intune portal, "
            f"where the blast radius is shown and the action is logged against "
            f"your name.")

    if assume_yes:
        return
    if not sys.stdin.isatty():
        raise GraphError(
            0, f"Refusing {method} {path} - not a terminal, so there is nobody "
               f"to confirm. Pass --yes if this is deliberate automation.")
    print(f"\n{method} {path}", file=sys.stderr)
    print("This writes to Intune and affects real devices.", file=sys.stderr)
    if input("Type 'yes' to continue: ").strip().lower() != "yes":
        raise GraphError(0, "Declined. Nothing sent.")


def main():
    ap = argparse.ArgumentParser(description="Call a Microsoft Graph / Intune endpoint.")
    ap.add_argument("method", choices=["GET", "POST", "PATCH", "PUT", "DELETE"])
    ap.add_argument("path", help="e.g. deviceManagement/managedDevices")
    ap.add_argument("--filter", help="OData $filter")
    ap.add_argument("--select", help="OData $select (comma-separated)")
    ap.add_argument("--expand", help="OData $expand")
    ap.add_argument("--top", type=int, help="page size")
    ap.add_argument("--max", type=int, dest="max_items", help="stop after N items")
    ap.add_argument("--body", help="JSON request body")
    ap.add_argument("--beta", action="store_true", help="use the beta endpoint")
    ap.add_argument("--mode", choices=["client_credentials", "device_code", "azure_cli"])
    ap.add_argument("--count-only", action="store_true", help="print only the number of results")
    ap.add_argument("--yes", action="store_true",
                    help="skip the confirmation prompt on a write")
    a = ap.parse_args()

    try:
        g = GraphClient(mode=a.mode, beta=a.beta)
        if a.method == "GET":
            res = g.get_all(a.path, filter=a.filter, select=a.select, expand=a.expand,
                            top=a.top, max_items=a.max_items)
            if a.count_only:
                print(len(res))
                return
            print(json.dumps(res, indent=2))
        else:
            check_mutation(a.method, a.path, a.yes)
            body = json.loads(a.body) if a.body else None
            res = g.request(a.method, a.path, body=body)
            # 204 is the norm for Intune actions and means "queued", not "done".
            print(json.dumps(res, indent=2) if res else "204 No Content (action accepted / queued)")
    except (GraphError, AuthError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
