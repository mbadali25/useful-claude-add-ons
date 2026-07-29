#!/usr/bin/env python3
"""
meraki_client.py -- read-only client for the Cisco Meraki Dashboard API v1.

Handles every GET, plus live-tool jobs (which POST but create only ephemeral
diagnostics and mutate no stored configuration). This module contains no
persistent-config write path at all -- that lives in meraki_config.py, and
keeping the two apart is what makes the snapshot/diff gate structural rather
than a rule someone has to remember.

Env:
    MERAKI_DASHBOARD_API_KEY   required

CLI examples:
    python meraki_client.py orgs
    python meraki_client.py networks
    python meraki_client.py status
    python meraki_client.py inventory
    python meraki_client.py get /networks/N1/appliance/vlans
    python meraki_client.py get-all /organizations/O1/devices
"""

import argparse
import json
import os
import sys
import urllib.parse

from meraki_http import MerakiError, MerakiHTTP

CACHE_DIR = ".meraki-snapshots"

# Per-endpoint timespan ceilings, in seconds. Meraki rejects anything larger
# with an opaque 400, so validate client-side and quote the real limit.
_TIMESPAN_365_DAYS = 31536000
_TIMESPAN_31_DAYS = 2678400


def max_timespan_for(path):
    if "/configurationChanges" in path:
        return _TIMESPAN_365_DAYS
    return _TIMESPAN_31_DAYS


def validate_timespan(path, timespan):
    if timespan is None:
        return
    limit = max_timespan_for(path)
    if int(timespan) > limit:
        raise MerakiError(
            0,
            [f"timespan {timespan}s exceeds the {limit}s maximum for {path}. "
             f"Use t0/t1 to window a longer period, or lower --timespan."],
        )


def parse_link_next(link_header):
    """Pull the rel=next URL out of an RFC 5988 Link header."""
    if not link_header:
        return None
    for part in link_header.split(","):
        segments = part.split(";")
        if len(segments) < 2:
            continue
        url = segments[0].strip()
        if not (url.startswith("<") and url.endswith(">")):
            continue
        for attr in segments[1:]:
            key, _, value = attr.strip().partition("=")
            if key.strip() == "rel" and value.strip().strip('"') == "next":
                return url[1:-1]
    return None


class MerakiClient:
    def __init__(self, http, cache_dir=CACHE_DIR):
        self.http = http
        self.cache_dir = cache_dir
        self._org_id = None
        self._networks = None

    # ---- cache -----------------------------------------------------------

    def _cache_path(self, org_id):
        return os.path.join(self.cache_dir, f".cache-{org_id}.json")

    def _load_cache(self, org_id):
        path = self._cache_path(org_id)
        if not os.path.exists(path):
            return {}
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return {}

    def _save_cache(self, org_id, data):
        os.makedirs(self.cache_dir, exist_ok=True)
        with open(self._cache_path(org_id), "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)

    # ---- bootstrap -------------------------------------------------------

    def resolve_org(self):
        if self._org_id:
            return self._org_id
        orgs, _ = self.http.request("GET", "/organizations")
        if not orgs:
            raise MerakiError(
                0, ["This API key can see no organizations. Confirm the key is "
                    "valid and that Organization > Settings > Dashboard API "
                    "access is enabled."])
        if len(orgs) > 1:
            listed = ", ".join(f"{o.get('name')} ({o.get('id')})" for o in orgs)
            raise MerakiError(
                0, [f"This skill is scoped to a single organization but the key "
                    f"sees {len(orgs)}: {listed}. Re-run with the intended org "
                    f"confirmed by the user."])
        self._org_id = str(orgs[0]["id"])
        cache = self._load_cache(self._org_id)
        cache["org"] = {"id": self._org_id, "name": orgs[0].get("name")}
        self._save_cache(self._org_id, cache)
        return self._org_id

    def networks(self):
        if self._networks is not None:
            return self._networks
        org_id = self.resolve_org()
        cache = self._load_cache(org_id)
        if cache.get("networks"):
            self._networks = cache["networks"]
            return self._networks
        nets, _ = self.http.request("GET", f"/organizations/{org_id}/networks")
        self._networks = nets or []
        cache["networks"] = self._networks
        self._save_cache(org_id, cache)
        return self._networks

    def network(self, network_id):
        for net in self.networks():
            if str(net.get("id")) == str(network_id):
                return net
        known = ", ".join(str(n.get("id")) for n in self.networks()) or "(none)"
        raise MerakiError(0, [f"Network {network_id} is not in this org. "
                              f"Known network IDs: {known}"])

    def device_statuses(self):
        org_id = self.resolve_org()
        return self.get_all(f"/organizations/{org_id}/devices/statuses")

    def inventory(self):
        org_id = self.resolve_org()
        return self.get_all(f"/organizations/{org_id}/inventory/devices")

    # ---- generic reads ---------------------------------------------------

    def get(self, path, params=None):
        if params:
            validate_timespan(path, params.get("timespan"))
        data, _ = self.http.request("GET", path, params=params)
        return data

    def get_all(self, path, params=None):
        """Follow Link: rel=next. Never injects a perPage default -- the caps
        differ per endpoint (1000 on some, 50 or 5 on others), so the server's
        own default and Link header are treated as authoritative."""
        if params:
            validate_timespan(path, params.get("timespan"))
        items = []
        next_path = path
        next_params = params
        while next_path:
            data, headers = self.http.request("GET", next_path, params=next_params)
            if isinstance(data, list):
                items.extend(data)
            elif data is not None:
                items.append(data)
            next_url = parse_link_next(headers.get("Link"))
            if not next_url:
                break
            parsed = urllib.parse.urlsplit(next_url)
            next_path = parsed.path
            if next_path.startswith("/api/v1"):
                next_path = next_path[len("/api/v1"):]
            next_params = dict(urllib.parse.parse_qsl(parsed.query)) or None
        return items


def _emit(data):
    json.dump(data, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


def build_parser():
    parser = argparse.ArgumentParser(description="Meraki Dashboard API read client")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("orgs")
    sub.add_parser("networks")
    sub.add_parser("status")
    sub.add_parser("inventory")
    for name in ("get", "get-all"):
        p = sub.add_parser(name)
        p.add_argument("path")
        p.add_argument("--params", default=None,
                       help="URL-encoded query string, e.g. 'timespan=3600'")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    client = MerakiClient(MerakiHTTP())
    try:
        if args.command == "orgs":
            _emit(client.get("/organizations"))
        elif args.command == "networks":
            _emit(client.networks())
        elif args.command == "status":
            _emit(client.device_statuses())
        elif args.command == "inventory":
            _emit(client.inventory())
        else:
            params = dict(urllib.parse.parse_qsl(args.params)) if args.params else None
            fn = client.get if args.command == "get" else client.get_all
            _emit(fn(args.path, params))
    except MerakiError as exc:
        sys.exit(str(exc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
