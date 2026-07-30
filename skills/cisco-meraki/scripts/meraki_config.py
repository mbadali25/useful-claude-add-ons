#!/usr/bin/env python3
"""
meraki_config.py -- the ONLY path that writes persistent Meraki configuration.

Meraki's collection endpoints are full-replacement PUTs: sending three firewall
rules does not add three rules, it deletes every rule absent from the payload.
So apply() is built so it CANNOT reach a PUT without first snapshotting current
state and rendering a diff for confirmation. That is control flow, not a rule
someone has to remember -- do not add a bare put() helper to this module.

Env:
    MERAKI_DASHBOARD_API_KEY   required

CLI examples:
    python meraki_config.py snapshot /networks/N1/appliance/firewall/l3FirewallRules
    python meraki_config.py diff /networks/N1/appliance/firewall/l3FirewallRules new.json
    python meraki_config.py apply /networks/N1/appliance/firewall/l3FirewallRules new.json
    python meraki_config.py rollback .meraki-snapshots/20260729-120000_....json
"""

import argparse
import datetime
import json
import os
import re
import sys
import time

from meraki_diff import (
    diff_rules,
    redact_secrets,
    render_diff,
    strip_default_rule,
)
from meraki_http import MerakiError, MerakiHTTP

SNAPSHOT_DIR = ".meraki-snapshots"

# Client-side caps so a too-large batch fails locally with a clear message
# rather than as an opaque server rejection. Verify against the live API.
MAX_BATCH_ACTIONS = 100
MAX_PENDING_BATCHES = 5


class HardBlocked(MerakiError):
    pass


# Operations refused outright regardless of confirmation, because a snapshot
# cannot restore them. These require the Dashboard UI.
HARD_BLOCKS = (
    ("DELETE", r"^/networks/[^/]+/?$",
     "Deleting a network destroys all of its configuration and history."),
    ("DELETE", r"^/organizations/[^/]+/?$",
     "Deleting an organization is irreversible."),
    ("POST", r"^/networks/[^/]+/devices/remove",
     "Removing a device from a network loses its per-network configuration."),
    ("POST", r"^/organizations/[^/]+/inventory/release",
     "Releasing a device from inventory unclaims it from the organization."),
    ("DELETE", r"^/organizations/[^/]+/admins/",
     "Revoking admin access can lock out the operator running this skill."),
    ("*", r"/identities/me/api/keys",
     "API key rotation or revocation must be done by a human in Dashboard."),
)


def check_hard_block(method, path):
    for blocked_method, pattern, reason in HARD_BLOCKS:
        if blocked_method not in ("*", method.upper()):
            continue
        if re.search(pattern, path):
            raise HardBlocked(
                0,
                [f"Refusing {method} {path}. {reason} Do this in the Meraki "
                 f"Dashboard UI if it is genuinely intended."],
            )


def extract_rules(payload):
    """Normalize a config payload into an ordered list for diffing."""
    if isinstance(payload, dict) and isinstance(payload.get("rules"), list):
        return payload["rules"]
    if isinstance(payload, list):
        return payload
    if payload is None:
        return []
    return [payload]


def _repack(original, rules):
    """Put a diffed rule list back into the shape the endpoint expects."""
    if isinstance(original, dict) and isinstance(original.get("rules"), list):
        out = dict(original)
        out["rules"] = rules
        return out
    if isinstance(original, list):
        return rules
    return original


def _default_now():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


class ConfigTool:
    def __init__(self, http, snapshot_dir=SNAPSHOT_DIR, now=None):
        self.http = http
        self.snapshot_dir = snapshot_dir
        self.now = now or _default_now
        self._org_id = None

    # ---- snapshot --------------------------------------------------------

    def snapshot(self, path):
        """GET current state and write it verbatim (secrets included) to disk.

        Secrets are preserved here on purpose -- a rollback must be able to
        restore a working PSK. The directory is gitignored, and render_diff()
        redacts anything displayed.
        """
        check_hard_block("GET", path)
        payload, _ = self.http.request("GET", path)
        os.makedirs(self.snapshot_dir, exist_ok=True)
        slug = re.sub(r"[^A-Za-z0-9]+", "-", path).strip("-")[:90]
        filename = f"{self.now()}_{slug}.json"
        full = os.path.join(self.snapshot_dir, filename)
        with open(full, "w", encoding="utf-8") as fh:
            json.dump({"path": path, "captured": self.now(),
                       "payload": payload}, fh, indent=2, default=str)
        return full

    # ---- diff ------------------------------------------------------------

    def diff(self, path, proposed):
        check_hard_block("GET", path)
        current, _ = self.http.request("GET", path)
        return self._diff_payloads(current, proposed)

    def _diff_payloads(self, current, proposed):
        current_rules = strip_default_rule(extract_rules(current))
        proposed_rules = strip_default_rule(extract_rules(proposed))
        return diff_rules(current_rules, proposed_rules)

    # ---- apply -----------------------------------------------------------

    def apply(self, path, proposed, confirm):
        """Snapshot, diff, confirm, then PUT. There is no path to the PUT that
        skips the first three steps."""
        check_hard_block("PUT", path)

        snapshot_path = self.snapshot(path)
        with open(snapshot_path, encoding="utf-8") as fh:
            current = json.load(fh)["payload"]

        lines = self._diff_payloads(current, proposed)
        if not lines:
            raise MerakiError(
                0, [f"Proposed config for {path} is identical to live state "
                    f"(no change). Nothing written. "
                    f"Snapshot kept at {snapshot_path}"])

        rendered = render_diff(lines)
        if not confirm(rendered):
            raise MerakiError(
                0, [f"Change to {path} declined. Nothing written. "
                    f"Snapshot kept at {snapshot_path}"])

        body = _repack(proposed, strip_default_rule(extract_rules(proposed)))
        try:
            result, _ = self.http.request("PUT", path, body=body)
        except MerakiError as exc:
            raise MerakiError(
                exc.status,
                [f"Write to {path} failed: {exc}. Live config may be "
                 f"unchanged -- verify before retrying. Snapshot kept at "
                 f"{snapshot_path}; restore with:\n"
                 f"  python meraki_config.py rollback {snapshot_path}"],
                exc.request_id,
            ) from exc
        return {"path": path, "snapshot": snapshot_path,
                "changes": len(lines), "result": result}

    # ---- rollback --------------------------------------------------------

    def rollback(self, snapshot_path, confirm):
        if not os.path.exists(snapshot_path):
            raise MerakiError(0, [f"No snapshot at {snapshot_path}"])
        with open(snapshot_path, encoding="utf-8") as fh:
            saved = json.load(fh)
        path = saved["path"]
        return self.apply(path, saved["payload"], confirm)

    # ---- action batches --------------------------------------------------

    def resolve_org(self):
        if self._org_id:
            return self._org_id
        orgs, _ = self.http.request("GET", "/organizations")
        if not orgs:
            raise MerakiError(0, ["This API key can see no organizations."])
        if len(orgs) > 1:
            listed = ", ".join(f"{o.get('name')} ({o.get('id')})" for o in orgs)
            raise MerakiError(
                0, [f"This skill is scoped to a single organization but the key "
                    f"sees {len(orgs)}: {listed}."])
        self._org_id = str(orgs[0]["id"])
        return self._org_id

    def batch_stage(self, actions, org_id=None):
        """Stage a batch with confirmed:false so Meraki validates the whole
        payload server-side before anything commits. The returned batch's own
        error list is the dry-run result."""
        if not actions:
            raise MerakiError(0, ["No actions supplied; nothing to stage."])
        if len(actions) > MAX_BATCH_ACTIONS:
            raise MerakiError(
                0, [f"{len(actions)} actions exceeds the {MAX_BATCH_ACTIONS}-"
                    f"action limit per batch. Split into multiple batches."])

        # All network-free validation runs first so a hard-blocked action is
        # refused without contacting the API.
        valid_operations = {"create": "POST", "update": "PUT",
                            "destroy": "DELETE"}
        for item in actions:
            resource = item.get("resource")
            if not resource:
                raise MerakiError(
                    0, [f"Action is missing 'resource': {item}"])
            if not isinstance(resource, str):
                raise MerakiError(
                    0, [f"Action 'resource' must be a string, got "
                        f"{type(resource).__name__}: {item}"])
            operation = (item.get("operation") or "").lower()
            if operation not in valid_operations:
                raise MerakiError(
                    0, [f"Action has invalid operation "
                        f"{item.get('operation')!r} for resource "
                        f"{resource!r}. Must be one of: "
                        f"{', '.join(sorted(valid_operations))}."])
            method = valid_operations[operation]
            check_hard_block(method, resource)

        org = org_id or self.resolve_org()
        pending = self._pending_batches(org)
        if len(pending) >= MAX_PENDING_BATCHES:
            raise MerakiError(
                0, [f"{len(pending)} batches are already pending, at the "
                    f"{MAX_PENDING_BATCHES}-batch limit. Commit or delete one "
                    f"in Dashboard before staging another."])

        body = {"confirmed": False, "synchronous": False, "actions": actions}
        batch, _ = self.http.request(
            "POST", f"/organizations/{org}/actionBatches", body=body)
        return batch

    def _pending_batches(self, org_id):
        batches, _ = self.http.request(
            "GET", f"/organizations/{org_id}/actionBatches",
            params={"status": "pending"})
        return batches or []

    def batch_commit(self, batch_id, org_id=None, timeout=120.0,
                     poll_interval=2.0):
        org = org_id or self.resolve_org()
        path = f"/organizations/{org}/actionBatches/{batch_id}"
        self.http.request("PUT", path, body={"confirmed": True})

        deadline = time.monotonic() + float(timeout)
        while True:
            batch, _ = self.http.request("GET", path)
            status = (batch or {}).get("status") or {}
            if status.get("failed"):
                errors = status.get("errors") or ["(no detail returned)"]
                raise MerakiError(
                    0, [f"Action batch {batch_id} failed: "
                        f"{'; '.join(str(e) for e in errors)}"])
            if status.get("completed"):
                return batch
            if time.monotonic() >= deadline:
                raise MerakiError(
                    0, [f"Action batch {batch_id} did not complete within "
                        f"{timeout}s. It may still be running -- poll "
                        f"{path} to check."])
            if poll_interval:
                time.sleep(poll_interval)


def _confirm_interactively(rendered):
    sys.stderr.write("\nProposed change:\n" + rendered + "\n\n")
    sys.stderr.write("Apply this change? [y/N] ")
    sys.stderr.flush()
    return sys.stdin.readline().strip().lower() in ("y", "yes")


def _load_json_file(filename):
    with open(filename, encoding="utf-8") as fh:
        return json.load(fh)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Meraki Dashboard API config write tool")
    sub = parser.add_subparsers(dest="command", required=True)

    snap = sub.add_parser("snapshot")
    snap.add_argument("path")

    diff_cmd = sub.add_parser("diff")
    diff_cmd.add_argument("path")
    diff_cmd.add_argument("proposed")

    apply_cmd = sub.add_parser("apply")
    apply_cmd.add_argument("path")
    apply_cmd.add_argument("proposed")
    apply_cmd.add_argument("--yes", action="store_true",
                           help="Skip the interactive prompt. The diff is "
                                "still rendered to stderr.")

    rb = sub.add_parser("rollback")
    rb.add_argument("snapshot")
    rb.add_argument("--yes", action="store_true")

    stage = sub.add_parser("batch-stage")
    stage.add_argument("actions", help="JSON file holding a list of actions")

    commit = sub.add_parser("batch-commit")
    commit.add_argument("batch_id")
    commit.add_argument("--timeout", type=float, default=120.0)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    tool = ConfigTool(MerakiHTTP())
    try:
        if args.command == "snapshot":
            print(tool.snapshot(args.path))
        elif args.command == "diff":
            print(render_diff(tool.diff(args.path,
                                        _load_json_file(args.proposed))))
        elif args.command == "apply":
            confirm = _auto_confirm if args.yes else _confirm_interactively
            result = tool.apply(args.path, _load_json_file(args.proposed),
                                confirm)
            json.dump(redact_secrets(result), sys.stdout, indent=2, default=str)
            sys.stdout.write("\n")
        elif args.command == "rollback":
            confirm = _auto_confirm if args.yes else _confirm_interactively
            result = tool.rollback(args.snapshot, confirm)
            json.dump(redact_secrets(result), sys.stdout, indent=2, default=str)
            sys.stdout.write("\n")
        elif args.command == "batch-stage":
            batch = tool.batch_stage(_load_json_file(args.actions))
            json.dump(redact_secrets(batch), sys.stdout, indent=2, default=str)
            sys.stdout.write("\n")
        elif args.command == "batch-commit":
            batch = tool.batch_commit(args.batch_id, timeout=args.timeout)
            json.dump(redact_secrets(batch), sys.stdout, indent=2, default=str)
            sys.stdout.write("\n")
    except MerakiError as exc:
        sys.exit(str(exc))
    return 0


def _auto_confirm(rendered):
    sys.stderr.write("\nApplying change:\n" + rendered + "\n")
    return True


if __name__ == "__main__":
    sys.exit(main())
