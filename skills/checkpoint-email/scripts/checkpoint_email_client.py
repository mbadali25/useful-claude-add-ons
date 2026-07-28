#!/usr/bin/env python3
"""Check Point Email Security (formerly Harmony Email & Collaboration) API client + CLI.

Handles Infinity Portal token auth, region -> host resolution, the required
per-request x-av-req-id header, scrollId pagination, 429 retry, async task
polling, and a dry-run gate on every mutating action.

Credentials come from env vars CHECKPOINT_EMAIL_CLIENT_ID /
CHECKPOINT_EMAIL_ACCESS_KEY (or --client-id / --access-key flags; env preferred).
Region comes from CHECKPOINT_EMAIL_REGION or --region (default: us).

CLI examples:
  # confirm auth + API access policy BEFORE doing anything else
  python checkpoint_email_client.py check

  # look up one email entity / one security event by internal ID
  python checkpoint_email_client.py entity f05b74da3ee859eea41aeac40aaad3c2
  python checkpoint_email_client.py event  ebb3e4bc8a9b14d7a529bb54ea6991b6

  # search email entities (startDate required; auto-paginates via scrollId)
  python checkpoint_email_client.py search-entities \
      --start 2026-07-01T00:00:00.000Z \
      --filter entityPayload.fromEmail is boss@evil.com \
      --filter entityPayload.attachmentCount greaterThan 0

  # search security events
  python checkpoint_email_client.py search-events \
      --start 2026-07-20T00:00:00.000Z --type phishing malware --severity High

  # remediation: DRY-RUN by default (shows targets, does nothing), --confirm to execute
  python checkpoint_email_client.py action-entity --action quarantine --ids ID1 ID2
  python checkpoint_email_client.py action-entity --action quarantine --ids ID1 ID2 --confirm
  python checkpoint_email_client.py action-event  --action dismiss    --ids EV1 --confirm
  python checkpoint_email_client.py task 123445311234        # poll async action status

  # generic escape hatches for endpoints not wrapped above
  python checkpoint_email_client.py get  /exceptions/whitelist
  python checkpoint_email_client.py post /search/query --json '{"requestData": {...}}'

Library use:
  from checkpoint_email_client import CheckPointEmailClient
  c = CheckPointEmailClient(region="us")
  c.check()
  for ent in c.search_entities(start="2026-07-01T00:00:00.000Z",
                               filters=[("entityPayload.fromEmail", "is", "x@y.com")]):
      print(ent["entityInfo"]["entityId"])
"""

import argparse
import json
import os
import sys
import time
import uuid

import requests

# Region -> CloudInfra gateway host. Auth and API share the host; regions are
# fully isolated (credentials and data do not cross regions).
REGION_HOSTS = {
    "us": "https://cloudinfra-gw-us.portal.checkpoint.com",
    "eu": "https://cloudinfra-gw.portal.checkpoint.com",
    "ca": "https://cloudinfra-gw.ca.portal.checkpoint.com",
    "au": "https://cloudinfra-gw.ap.portal.checkpoint.com",
    "uk": "https://cloudinfra-gw.uk.portal.checkpoint.com",
    "uae": "https://cloudinfra-gw.me.portal.checkpoint.com",
    "in": "https://cloudinfra-gw.in.portal.checkpoint.com",
}
API_PREFIX = "/app/hec-api/v1.0"

# Mutating actions per surface. Used to size the dry-run summary and to reject
# obvious typos before a call is ever made.
ENTITY_ACTIONS = {"quarantine", "restore", "delete", "release", "reprocess"}
EVENT_ACTIONS = {"dismiss", "restore", "quarantine", "severityChange", "sendToAdmin"}


class CheckPointEmailClient:
    def __init__(self, client_id=None, access_key=None, region=None, timeout=30):
        self.client_id = client_id or os.environ.get("CHECKPOINT_EMAIL_CLIENT_ID")
        self.access_key = (
            access_key
            or os.environ.get("CHECKPOINT_EMAIL_ACCESS_KEY")
            or os.environ.get("CHECKPOINT_EMAIL_CLIENT_SECRET")
        )
        if not self.client_id or not self.access_key:
            raise SystemExit(
                "Missing credentials: set CHECKPOINT_EMAIL_CLIENT_ID and "
                "CHECKPOINT_EMAIL_ACCESS_KEY (create an API key in the Infinity "
                "Portal under Global Settings > API Keys, service = Email Security)."
            )
        region = (region or os.environ.get("CHECKPOINT_EMAIL_REGION") or "us").lower()
        if region not in REGION_HOSTS:
            raise SystemExit(
                f"Unknown region '{region}'. Choose one of: {', '.join(REGION_HOSTS)}"
            )
        self.region = region
        self.host = REGION_HOSTS[region]
        self.base = self.host + API_PREFIX
        self.timeout = timeout
        self._token = None
        self._token_expiry = 0

    # ---------- auth ----------

    def token(self):
        if self._token and time.time() < self._token_expiry - 120:
            return self._token
        r = requests.post(
            f"{self.host}/auth/external",
            json={"clientId": self.client_id, "accessKey": self.access_key},
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=self.timeout,
        )
        if r.status_code >= 400:
            raise SystemExit(
                f"Auth failed ({r.status_code}) against {self.host}/auth/external: "
                f"{r.text[:400]}\nCheck the credentials and that --region matches the "
                "region the API key was created in (keys are region-specific)."
            )
        body = r.json()
        data = body.get("data", body) if isinstance(body, dict) else {}
        token = (
            data.get("token")
            or data.get("access_token")
            or body.get("token")
            or body.get("access_token")
        )
        if not token:
            raise SystemExit(f"Auth response had no token field: {json.dumps(body)[:400]}")
        expires_in = int(data.get("expiresIn") or body.get("expires_in") or 3600)
        self._token = token
        self._token_expiry = time.time() + expires_in
        return self._token

    # ---------- http core ----------

    def _request_raw(self, method, url, json_body=None, params=None, retries=4):
        for attempt in range(retries + 1):
            headers = {
                "Authorization": f"Bearer {self.token()}",
                "Accept": "application/json",
                "x-av-req-id": str(uuid.uuid4()),  # required on every call
            }
            if json_body is not None:
                headers["Content-Type"] = "application/json"
            r = requests.request(
                method, url, headers=headers, json=json_body, params=params,
                timeout=self.timeout,
            )
            if r.status_code == 429 and attempt < retries:
                time.sleep(int(r.headers.get("Retry-After", 2 ** (attempt + 1))))
                continue
            if r.status_code == 401 and attempt < retries:
                self._token = None  # force refresh once, then retry
                continue
            if r.status_code >= 400:
                raise SystemExit(f"{method} {url} -> {r.status_code}: {r.text[:600]}")
            if r.status_code == 204 or not r.content:
                return {}
            return r.json()
        raise SystemExit(f"{method} {url}: exhausted retries")

    def request(self, method, path, json_body=None, params=None):
        """`path` is relative to the hec-api/v1.0 base, e.g. /search/query."""
        if not path.startswith("/"):
            path = "/" + path
        return self._request_raw(method, self.base + path, json_body=json_body, params=params)

    def get(self, path, params=None):
        return self.request("GET", path, params=params)

    def post(self, path, json_body):
        return self.request("POST", path, json_body=json_body)

    # ---------- helpers ----------

    @staticmethod
    def _records(resp):
        """responseData is sometimes an object, sometimes an array. Normalize to list."""
        rd = resp.get("responseData") if isinstance(resp, dict) else None
        if rd is None:
            return []
        return rd if isinstance(rd, list) else [rd]

    @staticmethod
    def _scroll_id(resp):
        env = resp.get("responseEnvelope", {}) if isinstance(resp, dict) else {}
        sid = env.get("scrollId")
        return sid or None

    # ---------- reads ----------

    def check(self):
        """Auth + minimal read to confirm both credentials AND access policy.

        Runs a narrow event query (last hour) rather than a write, so it is safe
        to run first against a live tenant."""
        now = time.time()
        start = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(now - 3600))
        end = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(now))
        resp = self.post("/event/query", {"requestData": {"startDate": start, "endDate": end}})
        env = resp.get("responseEnvelope", {})
        return {
            "region": self.region,
            "host": self.host,
            "auth": "ok",
            "responseCode": env.get("responseCode"),
            "recordsInLastHour": env.get("recordsNumber"),
        }

    def entity(self, entity_id):
        return self._records(self.get(f"/search/entity/{entity_id}"))

    def event(self, event_id):
        return self._records(self.get(f"/event/{event_id}"))

    def search_entities(self, start, end="", saas="office365_emails",
                        saas_entity="office365_emails_email", filters=None, max_records=None):
        """Yield email entities. `filters` is a list of (attr, op, value) tuples."""
        ext = [{"saasAttrName": a, "saasAttrOp": o, "saasAttrValue": v}
               for (a, o, v) in (filters or [])]
        scroll = ""
        yielded = 0
        while True:
            body = {"requestData": {
                "entityFilter": {"saas": saas, "saasEntity": saas_entity,
                                 "startDate": start, "endDate": end},
                "entityExtendedFilter": ext,
                "scrollId": scroll,
            }}
            resp = self.post("/search/query", body)
            recs = self._records(resp)
            for rec in recs:
                yield rec
                yielded += 1
                if max_records and yielded >= max_records:
                    return
            scroll = self._scroll_id(resp)
            if not scroll or not recs:
                return

    def search_events(self, start, end="", types=None, states=None, severities=None,
                      saas=None, confidence=None, description=None, max_records=None):
        scroll = ""
        yielded = 0
        while True:
            rd = {"startDate": start, "endDate": end, "scrollId": scroll}
            if types:        rd["eventTypes"] = types
            if states:       rd["eventStates"] = states
            if severities:   rd["severities"] = severities
            if saas:         rd["saas"] = saas
            if confidence:   rd["confidenceIndicator"] = confidence
            if description:  rd["description"] = description
            resp = self.post("/event/query", {"requestData": rd})
            recs = self._records(resp)
            for rec in recs:
                yield rec
                yielded += 1
                if max_records and yielded >= max_records:
                    return
            scroll = self._scroll_id(resp)
            if not scroll or not recs:
                return

    def task(self, task_id):
        return self.get(f"/task/{task_id}")

    # ---------- mutations (dry-run gated) ----------

    def _entity_summary(self, entity_id):
        try:
            recs = self.entity(entity_id)
        except SystemExit:
            return {"entityId": entity_id, "summary": "(could not resolve)"}
        if not recs:
            return {"entityId": entity_id, "summary": "(not found)"}
        p = recs[0].get("entityPayload", {}) or {}
        state = (recs[0].get("entityInfo", {}) or {}).get("entityActionState", "")
        return {
            "entityId": entity_id,
            "from": p.get("fromEmail", ""),
            "to": p.get("to", ""),
            "subject": p.get("subject", ""),
            "received": p.get("received", ""),
            "state": state,
        }

    def _event_summary(self, event_id):
        try:
            recs = self.event(event_id)
        except SystemExit:
            return {"eventId": event_id, "summary": "(could not resolve)"}
        if not recs:
            return {"eventId": event_id, "summary": "(not found)"}
        e = recs[0]
        return {
            "eventId": event_id,
            "type": e.get("type", ""),
            "severity": e.get("severity", ""),
            "state": e.get("state", ""),
            "description": (e.get("description", "") or "")[:120],
        }

    def action_entity(self, entity_ids, action, param="", confirm=False):
        """Quarantine/restore/etc on email entities. Dry-run unless confirm=True."""
        if action not in ENTITY_ACTIONS:
            print(f"WARNING: '{action}' is not a known entity action "
                  f"({', '.join(sorted(ENTITY_ACTIONS))}). Proceeding anyway.",
                  file=sys.stderr)
        targets = [self._entity_summary(i) for i in entity_ids]
        if not confirm:
            return {"dryRun": True, "action": action, "param": param,
                    "wouldAffect": len(targets), "targets": targets,
                    "note": "No changes made. Re-run with --confirm to execute."}
        body = {"requestData": {"entityIds": entity_ids,
                                "entityActionName": [action],
                                "entityActionParam": [param]}}
        resp = self.post("/action/entity", body)
        return {"dryRun": False, "action": action, "targets": targets,
                "result": self._records(resp)}

    def action_event(self, event_ids, action, param="", confirm=False):
        if action not in EVENT_ACTIONS:
            print(f"WARNING: '{action}' is not a known event action "
                  f"({', '.join(sorted(EVENT_ACTIONS))}). Proceeding anyway.",
                  file=sys.stderr)
        targets = [self._event_summary(i) for i in event_ids]
        if not confirm:
            return {"dryRun": True, "action": action, "param": param,
                    "wouldAffect": len(targets), "targets": targets,
                    "note": "No changes made. Re-run with --confirm to execute."}
        body = {"requestData": {"eventIds": event_ids,
                                "eventActionName": [action],
                                "eventActionParam": [param]}}
        resp = self.post("/action/event", body)
        return {"dryRun": False, "action": action, "targets": targets,
                "result": self._records(resp)}


# ---------- CLI ----------

def _print(obj):
    print(json.dumps(obj, indent=2, default=str))


def main():
    ap = argparse.ArgumentParser(description="Check Point Email Security API CLI")
    ap.add_argument("--client-id")
    ap.add_argument("--access-key")
    ap.add_argument("--region", help="us (default), eu, ca, au, uk, uae, in")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="auth + minimal read smoke test")

    p = sub.add_parser("entity", help="GET /search/entity/{id}")
    p.add_argument("entity_id")
    p = sub.add_parser("event", help="GET /event/{id}")
    p.add_argument("event_id")
    p = sub.add_parser("task", help="GET /task/{id} (async action status)")
    p.add_argument("task_id")

    p = sub.add_parser("search-entities", help="POST /search/query")
    p.add_argument("--start", required=True, help="ISO8601, e.g. 2026-07-01T00:00:00.000Z")
    p.add_argument("--end", default="")
    p.add_argument("--saas", default="office365_emails")
    p.add_argument("--saas-entity", default="office365_emails_email")
    p.add_argument("--filter", nargs=3, action="append", metavar=("ATTR", "OP", "VALUE"),
                   help="repeatable; e.g. --filter entityPayload.fromEmail is x@y.com")
    p.add_argument("--max", type=int, dest="max_records")

    p = sub.add_parser("search-events", help="POST /event/query")
    p.add_argument("--start", required=True)
    p.add_argument("--end", default="")
    p.add_argument("--type", nargs="*", dest="types")
    p.add_argument("--state", nargs="*", dest="states")
    p.add_argument("--severity", nargs="*", dest="severities")
    p.add_argument("--saas", nargs="*")
    p.add_argument("--confidence")
    p.add_argument("--description")
    p.add_argument("--max", type=int, dest="max_records")

    p = sub.add_parser("action-entity", help="POST /action/entity (dry-run unless --confirm)")
    p.add_argument("--ids", nargs="+", required=True)
    p.add_argument("--action", required=True, help="quarantine | restore | delete | ...")
    p.add_argument("--param", default="")
    p.add_argument("--confirm", action="store_true", help="actually execute the action")

    p = sub.add_parser("action-event", help="POST /action/event (dry-run unless --confirm)")
    p.add_argument("--ids", nargs="+", required=True)
    p.add_argument("--action", required=True, help="dismiss | restore | quarantine | severityChange | ...")
    p.add_argument("--param", default="", help="e.g. for severityChange: Low|Medium|High|Highest")
    p.add_argument("--confirm", action="store_true")

    p = sub.add_parser("get", help="raw GET on a hec-api path")
    p.add_argument("path")
    p = sub.add_parser("post", help="raw POST on a hec-api path")
    p.add_argument("path")
    p.add_argument("--json", dest="json_body", default="{}")

    args = ap.parse_args()
    c = CheckPointEmailClient(args.client_id, args.access_key, region=args.region)

    if args.cmd == "check":
        _print(c.check())
    elif args.cmd == "entity":
        _print(c.entity(args.entity_id))
    elif args.cmd == "event":
        _print(c.event(args.event_id))
    elif args.cmd == "task":
        _print(c.task(args.task_id))
    elif args.cmd == "search-entities":
        _print(list(c.search_entities(
            args.start, args.end, saas=args.saas, saas_entity=args.saas_entity,
            filters=args.filter, max_records=args.max_records)))
    elif args.cmd == "search-events":
        _print(list(c.search_events(
            args.start, args.end, types=args.types, states=args.states,
            severities=args.severities, saas=args.saas, confidence=args.confidence,
            description=args.description, max_records=args.max_records)))
    elif args.cmd == "action-entity":
        _print(c.action_entity(args.ids, args.action, args.param, confirm=args.confirm))
    elif args.cmd == "action-event":
        _print(c.action_event(args.ids, args.action, args.param, confirm=args.confirm))
    elif args.cmd == "get":
        _print(c.get(args.path))
    elif args.cmd == "post":
        _print(c.post(args.path, json.loads(args.json_body)))


if __name__ == "__main__":
    main()
