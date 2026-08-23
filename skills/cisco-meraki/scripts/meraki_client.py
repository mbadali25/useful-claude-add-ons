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
import time
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


# MX/MS/MR only. MV cameras, MT sensors, and SM are out of this skill's scope.
IN_SCOPE_PRODUCT_TYPES = ("appliance", "switch", "wireless")


def product_type_for(network, requested=None):
    """Resolve the productType the event-log endpoint requires.

    Combined networks need it explicitly; omitting it returns a 404 that reads
    like the network does not exist, which is the single most confusing error
    in this API.
    """
    available = list(network.get("productTypes") or [])
    if requested:
        if requested not in available:
            raise MerakiError(
                0, [f"Network {network.get('id')} has no '{requested}' product "
                    f"type. Available: {', '.join(available) or '(none)'}"])
        if requested not in IN_SCOPE_PRODUCT_TYPES:
            raise MerakiError(
                0, [f"Product type '{requested}' is outside this skill's scope "
                    f"(MX/MS/MR only)."])
        return requested

    usable = [p for p in available if p in IN_SCOPE_PRODUCT_TYPES]
    if not usable:
        raise MerakiError(
            0, [f"Network {network.get('id')} has no in-scope product types. "
                f"Found: {', '.join(available) or '(none)'}"])
    if len(usable) > 1:
        raise MerakiError(
            0, [f"Network {network.get('id')} is a combined network "
                f"({', '.join(usable)}). The event log requires one "
                f"productType -- pass --product-type with one of these."])
    return usable[0]


# Live-tool availability is platform-bound. Checking the model up front turns a
# bare 400 into an actionable refusal. Verify this table against the live API
# during implementation -- Meraki adds tools over time.
LIVE_TOOLS = {
    "ping": ("MX", "MS", "MR", "MG", "Z", "C9"),
    "pingDevice": ("MX", "MS", "MR", "MG", "Z", "C9"),
    "cableTest": ("MS", "C9"),
    "throughputTest": ("MX", "MR", "Z"),
    "arpTable": ("MX", "MS", "C9"),
    "macTable": ("MS", "C9"),
    "wakeOnLan": ("MX", "MS", "C9"),
}

TERMINAL_STATUSES = ("complete", "failed")

# Response key holding the job id, per tool. This is the primary,
# cheap-to-check path; run_live_tool() also has a *Id-scanning fallback for
# keys this table doesn't yet know about (Meraki adds tools/keys over time).
_JOB_ID_KEYS = ("pingId", "pingDeviceId", "cableTestId", "throughputTestId",
                "arpTableId", "macTableId", "wakeOnLanId", "id")

# Keys that end in "Id" but identify a resource, not a live-tool job. The
# fallback scan must never mistake one of these for a job id.
_NOT_JOB_ID_KEYS = frozenset({
    "networkId", "organizationId", "deviceId", "clientId", "serialId",
})


def check_tool_supported(tool, model):
    if tool not in LIVE_TOOLS:
        raise MerakiError(
            0, [f"Unknown live tool '{tool}'. Available: "
                f"{', '.join(sorted(LIVE_TOOLS))}"])
    prefixes = LIVE_TOOLS[tool]
    upper = (model or "").upper()
    if not any(upper.startswith(p) for p in prefixes):
        raise MerakiError(
            0, [f"Live tool '{tool}' is not available on {model}. "
                f"Supported platforms: {', '.join(prefixes)}"])


class MerakiClient:
    def __init__(self, http, cache_dir=CACHE_DIR):
        self.http = http
        self.cache_dir = cache_dir
        self._org_id = None
        self._networks = None
        self._devices = None

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

    def networks(self, force=False):
        if not force and self._networks is not None:
            return self._networks
        org_id = self.resolve_org()
        cache = self._load_cache(org_id)
        if not force and cache.get("networks"):
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
        # Stale cache: a network created after this cache was written would
        # otherwise look like a false "not in this org" -- refetch once and
        # look again before concluding it's genuinely absent. No recursion:
        # a genuinely missing ID costs exactly one refetch, never a loop.
        for net in self.networks(force=True):
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

    # ---- log surfaces ----------------------------------------------------

    def events(self, network_id, product_type=None, timespan=None, per_page=None):
        net = self.network(network_id)
        resolved = product_type_for(net, product_type)
        path = f"/networks/{network_id}/events"
        validate_timespan(path, timespan)
        params = {"productType": resolved, "timespan": timespan,
                  "perPage": per_page}
        return self.get(path, params)

    def config_changes(self, timespan=None):
        org_id = self.resolve_org()
        path = f"/organizations/{org_id}/configurationChanges"
        validate_timespan(path, timespan)
        return self.get_all(path, {"timespan": timespan})

    def security_events(self, network_id=None, timespan=None):
        if network_id:
            net = self.network(network_id)
            if "appliance" not in (net.get("productTypes") or []):
                raise MerakiError(
                    0, [f"Network {network_id} has no MX appliance, so it has no "
                        f"security events."])
            path = f"/networks/{network_id}/appliance/security/events"
        else:
            org_id = self.resolve_org()
            path = f"/organizations/{org_id}/appliance/security/events"
        validate_timespan(path, timespan)
        return self.get_all(path, {"timespan": timespan})

    def air_marshal(self, network_id, timespan=None):
        net = self.network(network_id)
        if "wireless" not in (net.get("productTypes") or []):
            raise MerakiError(
                0, [f"Network {network_id} has no wireless product type, so "
                    f"Air Marshal is unavailable."])
        path = f"/networks/{network_id}/wireless/airMarshal"
        validate_timespan(path, timespan)
        return self.get_all(path, {"timespan": timespan})

    # ---- live tools (ephemeral jobs; no persistent config change) --------

    def devices(self, force=False):
        if not force and self._devices is not None:
            return self._devices
        org_id = self.resolve_org()
        cache = self._load_cache(org_id)
        if not force and cache.get("devices"):
            self._devices = cache["devices"]
            return self._devices
        devs = self.get_all(f"/organizations/{org_id}/devices")
        self._devices = devs or []
        cache["devices"] = self._devices
        self._save_cache(org_id, cache)
        return self._devices

    def device(self, serial):
        for dev in self.devices():
            if str(dev.get("serial")) == str(serial):
                return dev
        # Stale cache: a device added after this cache was written would
        # otherwise look like a false "not in this org" -- refetch once and
        # look again before concluding it's genuinely absent. No recursion:
        # a genuinely missing serial costs exactly one refetch, never a loop.
        for dev in self.devices(force=True):
            if str(dev.get("serial")) == str(serial):
                return dev
        known = ", ".join(str(d.get("serial")) for d in self.devices()) or "(none)"
        raise MerakiError(0, [f"Serial {serial} is not in this org's device "
                              f"list. Known serials: {known}"])

    def run_live_tool(self, tool, serial, body=None, timeout=60.0,
                      poll_interval=2.0):
        """Create a live-tool job on `serial` and poll it to completion.

        `timeout` bounds only the polling loop's own waiting: it guarantees
        at least one poll happens, and clamps each subsequent sleep so the
        loop never sleeps past the deadline. It does NOT bound the wall
        clock of the whole call. Each individual GET/POST this method issues
        is separately subject to the transport's own socket timeout (60s in
        meraki_http.py) plus its 429 retry-and-backoff policy, and neither is
        coordinated with `timeout` -- so a caller passing timeout=5 can still
        see this call take noticeably longer than 5s if a single request is
        slow or rate-limited. The timeout error names the job id so it can
        still be polled by hand once the underlying request returns.
        """
        dev = self.device(serial)
        check_tool_supported(tool, dev.get("model", ""))

        base = f"/devices/{serial}/liveTools/{tool}"
        created, _ = self.http.request("POST", base, body=body or {})
        job_id = None
        if isinstance(created, dict):
            # Try convention first: {tool}Id
            job_id = created.get(f"{tool}Id")

            # Then try the known-key table
            if not job_id:
                for key in _JOB_ID_KEYS:
                    if created.get(key):
                        job_id = created[key]
                        break

            # Then scan for unknown *Id keys, excluding resource identifiers
            if not job_id:
                # Meraki names a job id after its tool, and the known-key table
                # covers all current tools. This fallback is for future tools
                # Meraki adds -- scan for *Id keys that aren't resource
                # identifiers, then refuse to guess if more than one is found.
                candidates = {}
                for key, value in created.items():
                    if (key.endswith("Id") and value and
                            key not in _NOT_JOB_ID_KEYS):
                        candidates[key] = value

                if len(candidates) > 1:
                    # Ambiguous: refuse to guess which is the job id.
                    listed = ", ".join(sorted(candidates.keys()))
                    raise MerakiError(
                        0, [f"Live tool '{tool}' on {serial} returned multiple "
                            f"candidate job id keys; cannot determine which to "
                            f"poll. Candidates: {listed}"])
                if len(candidates) == 1:
                    key = next(iter(candidates.keys()))
                    job_id = candidates[key]

        if not job_id:
            present = (", ".join(sorted(created)) if isinstance(created, dict)
                       else "(non-dict response)")
            raise MerakiError(
                0, [f"Live tool '{tool}' on {serial} returned no recognizable "
                    f"job id, so it cannot be polled. Keys present in the "
                    f"creation response: {present or '(none)'}"])

        deadline = time.monotonic() + float(timeout)
        while True:
            latest, _ = self.http.request("GET", f"{base}/{job_id}")
            status = (latest or {}).get("status")
            if status in TERMINAL_STATUSES:
                return latest
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MerakiError(
                    0, [f"Live tool '{tool}' on {serial} timed out after "
                        f"{timeout}s; last status was '{status}'. "
                        f"Job id {job_id} can still be polled manually."])
            if poll_interval:
                time.sleep(min(poll_interval, remaining))

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
        # A malformed or self-referential Link header pages forever, and a busy
        # org's events feed is effectively unbounded. Stop and say so rather
        # than filling memory silently.
        pages = 0
        max_pages = int(os.environ.get("MERAKI_MAX_PAGES", "500"))
        while next_path:
            pages += 1
            if pages > max_pages:
                raise MerakiError(
                    0, [f"Stopped after {max_pages} pages of {path} with "
                        f"{len(items)} items - the Link header never "
                        f"terminated. Narrow the query (timespan, perPage), or "
                        f"raise MERAKI_MAX_PAGES if the result really is this "
                        f"large."])
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
    networks_parser = sub.add_parser("networks")
    networks_parser.add_argument("--refresh", action="store_true",
                                  help="Bypass the cache and re-fetch networks "
                                       "from the Dashboard API.")
    sub.add_parser("status")
    sub.add_parser("inventory")
    for name in ("get", "get-all"):
        p = sub.add_parser(name)
        p.add_argument("path")
        p.add_argument("--params", default=None,
                       help="URL-encoded query string, e.g. 'timespan=3600'")
    events = sub.add_parser("events")
    events.add_argument("--network", required=True)
    events.add_argument("--product-type", default=None,
                        choices=list(IN_SCOPE_PRODUCT_TYPES))
    events.add_argument("--timespan", type=int, default=None)
    events.add_argument("--per-page", type=int, default=None)

    changes = sub.add_parser("changes")
    changes.add_argument("--timespan", type=int, default=None)

    secev = sub.add_parser("security-events")
    secev.add_argument("--network", default=None)
    secev.add_argument("--timespan", type=int, default=None)

    marshal = sub.add_parser("air-marshal")
    marshal.add_argument("--network", required=True)
    marshal.add_argument("--timespan", type=int, default=None)

    live = sub.add_parser("live")
    live.add_argument("tool", choices=sorted(LIVE_TOOLS))
    live.add_argument("serial")
    live.add_argument("--json", dest="body", default=None,
                     help='Tool body, e.g. \'{"target": "8.8.8.8"}\'')
    live.add_argument("--timeout", type=float, default=60.0)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    client = MerakiClient(MerakiHTTP())
    try:
        if args.command == "orgs":
            _emit(client.get("/organizations"))
        elif args.command == "networks":
            _emit(client.networks(force=args.refresh))
        elif args.command == "status":
            _emit(client.device_statuses())
        elif args.command == "inventory":
            _emit(client.inventory())
        elif args.command == "events":
            _emit(client.events(args.network, args.product_type,
                                args.timespan, args.per_page))
        elif args.command == "changes":
            _emit(client.config_changes(args.timespan))
        elif args.command == "security-events":
            _emit(client.security_events(args.network, args.timespan))
        elif args.command == "air-marshal":
            _emit(client.air_marshal(args.network, args.timespan))
        elif args.command == "live":
            body = json.loads(args.body) if args.body else None
            _emit(client.run_live_tool(args.tool, args.serial, body,
                                       timeout=args.timeout))
        else:
            params = dict(urllib.parse.parse_qsl(args.params)) if args.params else None
            fn = client.get if args.command == "get" else client.get_all
            _emit(fn(args.path, params))
    except MerakiError as exc:
        sys.exit(str(exc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
