#!/usr/bin/env python3
"""Read, validate and edit Power Automate flow definitions via API.

Solution-aware flows live in the Dataverse `workflow` table's `clientdata`
column. There is no version history on that column, so every write here is
preceded by a snapshot written to disk, and every PATCH is preceded by
validation. Both are enforced in code rather than left to discipline.

Standard library only. Python 3.8+.

    python pa.py login    --org https://contoso.crm.dynamics.com
    python pa.py get      --org https://contoso.crm.dynamics.com --flow <guid>
    python pa.py validate --clientdata flow.json
    python pa.py patch    --org https://contoso.crm.dynamics.com --flow <guid> \
                          --clientdata flow.json
    python pa.py runs     --env <env-guid> --flow <guid>
    python pa.py list     --env <env-guid>
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Azure CLI public client. The only one verified for Dataverse device-code.
# See references/auth.md before substituting another.
DEFAULT_CLIENT_ID = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"

CACHE_DIR = Path(os.path.expanduser("~")) / ".pa-api-cache"
SNAPSHOT_DIR = Path("pa-snapshots")

# scope = resource URI + "/.default". A resource URI that already ends in "/"
# therefore yields a double slash, which is correct. See references/auth.md.
RESOURCES = {
    "bap": "https://api.bap.microsoft.com/",
    "flow": "https://service.flow.microsoft.com/",
    "powerapps": "https://service.powerapps.com/",
}


def scope_for(resource_uri):
    """Derive a v2.0 scope from a resource identifier URI."""
    return resource_uri + "/.default"


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

def request(method, url, token=None, body=None, headers=None, form=False):
    hdrs = dict(headers or {})
    if token:
        hdrs["Authorization"] = "Bearer " + token
    data = None
    if body is not None:
        if form:
            data = urllib.parse.urlencode(body).encode()
            hdrs["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(body).encode()
            hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            return resp.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = {"raw": raw}
        return exc.code, parsed


def die(msg, detail=None):
    print("ERROR: " + msg, file=sys.stderr)
    if detail:
        print(json.dumps(detail, indent=2)[:2000], file=sys.stderr)
    sys.exit(1)


def explain_auth_failure(payload):
    """Audience errors name the allowed list. Surface it rather than guessing."""
    blob = json.dumps(payload)
    if "InvalidAuthenticationAudience" in blob or "wrong audience" in blob:
        print(
            "\nThe token audience is wrong. The error above lists the audiences\n"
            "this endpoint accepts -- take one and request scope = <audience> +\n"
            '"/.default". If the audience ends in "/", the scope contains a\n'
            "double slash and that is correct.\n",
            file=sys.stderr,
        )


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------

def cache_path(resource):
    safe = urllib.parse.quote(resource, safe="")
    return CACHE_DIR / (safe + ".json")


def load_cached(resource):
    path = cache_path(resource)
    if not path.exists():
        return None
    try:
        blob = json.loads(path.read_text())
    except ValueError:
        return None
    if blob.get("expires_at", 0) > time.time() + 120:
        return blob["access_token"]
    if blob.get("refresh_token"):
        return refresh(resource, blob["refresh_token"], blob.get("tenant", "organizations"))
    return None


def save_cached(resource, payload, tenant):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    blob = {
        "access_token": payload["access_token"],
        "refresh_token": payload.get("refresh_token"),
        "expires_at": time.time() + int(payload.get("expires_in", 3600)),
        "tenant": tenant,
    }
    path = cache_path(resource)
    path.write_text(json.dumps(blob))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # Windows without POSIX ACL support
    return blob["access_token"]


def refresh(resource, refresh_token, tenant):
    status, payload = request(
        "POST",
        "https://login.microsoftonline.com/%s/oauth2/v2.0/token" % tenant,
        body={
            "grant_type": "refresh_token",
            "client_id": DEFAULT_CLIENT_ID,
            "refresh_token": refresh_token,
            "scope": scope_for(resource) + " offline_access",
        },
        form=True,
    )
    if status != 200:
        return None
    return save_cached(resource, payload, tenant)


def device_code_login(resource, tenant, client_id=DEFAULT_CLIENT_ID):
    status, payload = request(
        "POST",
        "https://login.microsoftonline.com/%s/oauth2/v2.0/devicecode" % tenant,
        body={"client_id": client_id, "scope": scope_for(resource) + " offline_access"},
        form=True,
    )
    if status != 200:
        die("device code request refused -- usually the client id is not a "
            "permitted public client in this tenant", payload)

    print("\n" + payload["message"] + "\n", flush=True)
    print("Waiting for you to complete sign-in (codes expire in ~15 minutes)...",
          flush=True)

    interval = int(payload.get("interval", 5))
    deadline = time.time() + int(payload.get("expires_in", 900))
    while time.time() < deadline:
        time.sleep(interval)
        status, tok = request(
            "POST",
            "https://login.microsoftonline.com/%s/oauth2/v2.0/token" % tenant,
            body={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": client_id,
                "device_code": payload["device_code"],
            },
            form=True,
        )
        if status == 200:
            print("Signed in. Token cached.")
            return save_cached(resource, tok, tenant)
        err = tok.get("error")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            interval += 5
            continue
        die("sign-in failed: " + str(err), tok)
    die("device code expired before sign-in completed")


def token_for(resource, tenant, interactive=True):
    cached = load_cached(resource)
    if cached:
        return cached
    if not interactive:
        die("no cached token for %s -- run 'pa.py login' first" % resource)
    return device_code_login(resource, tenant)


# --------------------------------------------------------------------------
# Validation -- the structural enforcement
# --------------------------------------------------------------------------

def _walk(container, container_id, out, inside_foreach=False):
    """Collect (container_id, name, action, inside_foreach) for every action.

    Actions nest through several shapes: a Scope/If/Foreach carries `actions`,
    an If also carries `else.actions`, a Switch carries `cases.<name>.actions`
    and `default.actions`. runAfter is scoped to one container, so each is
    tracked separately.
    """
    if not isinstance(container, dict):
        return
    for name, action in container.items():
        if not isinstance(action, dict):
            continue
        out.append((container_id, name, action, inside_foreach))
        nested = inside_foreach or action.get("type") == "Foreach"
        base = (container_id + " > " if container_id else "") + name
        _walk(action.get("actions"), base, out, nested)
        for branch in ("else", "default"):
            node = action.get(branch)
            if isinstance(node, dict):
                _walk(node.get("actions"), base + " > " + branch, out, nested)
        cases = action.get("cases")
        if isinstance(cases, dict):
            for case_name, case in cases.items():
                if isinstance(case, dict):
                    _walk(case.get("actions"), base + " > " + case_name,
                          out, nested)


def _schema_nodes(node, path):
    """Yield (path, node) for every JSON-schema object carrying 'properties'.

    Trigger inputs nest: a "For a selected file" trigger puts the user's fields
    under properties.rows.items.properties with their own sibling 'required',
    so a top-level-only check never sees them.
    """
    if not isinstance(node, dict):
        return
    if isinstance(node.get("properties"), dict):
        yield path, node
        for key, child in node["properties"].items():
            yield from _schema_nodes(child, "%s.%s" % (path, key))
    if isinstance(node.get("items"), dict):
        yield from _schema_nodes(node["items"], path + "[]")


def validate(clientdata):
    """Return a list of problem strings. Empty means it passed."""
    problems = []

    props = clientdata.get("properties")
    if not isinstance(props, dict):
        return ["clientdata has no 'properties' object -- is this a flow definition?"]

    definition = props.get("definition")
    if not isinstance(definition, dict):
        return ["clientdata.properties has no 'definition' object"]

    refs = props.get("connectionReferences") or {}

    # 1. Orphaned trigger-schema 'required' entries, at EVERY level.
    #    Removing a dynamically-added input from 'properties' but not from
    #    'required' blocks every launch and creates NO run to diagnose from.
    #    The user inputs of a "For a selected file" trigger are not at the top
    #    level: they sit under properties.rows.items.properties, with their own
    #    sibling 'required'. A top-level-only check passes such a trigger
    #    vacuously, so every nested schema object is walked.
    for tname, trigger in (definition.get("triggers") or {}).items():
        schema = ((trigger.get("inputs") or {}).get("schema")) or {}
        for where, node in _schema_nodes(schema, "schema"):
            declared = set((node.get("properties") or {}).keys())
            for req in node.get("required") or []:
                if req not in declared:
                    problems.append(
                        "trigger '%s': '%s' is in %s.required but not in "
                        "%s.properties -- every launch will fail validation "
                        "before a run is created, so run history shows "
                        "nothing" % (tname, req, where, where)
                    )

    actions = []
    _walk(definition.get("actions") or {}, "", actions)

    for container_id, name, action, inside_foreach in actions:
        where = (container_id + " > " if container_id else "") + name

        # 2. Terminate nested in Apply to each -- rejected as
        #    InvalidWorkflowRunAction at save time.
        if action.get("type") == "Terminate" and inside_foreach:
            problems.append(
                "action '%s': Terminate is nested inside an Apply to each. The "
                "service rejects this with InvalidWorkflowRunAction. Set a "
                "variable in the loop and terminate after it." % where
            )

        # 3. host.connectionName must resolve to a connection reference.
        #    `inputs` is not always an object -- a Compose's inputs is often a
        #    bare string or array -- so guard the type before reading it.
        inputs = action.get("inputs")
        host = inputs.get("host") if isinstance(inputs, dict) else None
        cname = host.get("connectionName") if isinstance(host, dict) else None
        if cname and cname not in refs:
            problems.append(
                "action '%s': host.connectionName '%s' is not in "
                "properties.connectionReferences. The flow will not save. A "
                "connector the flow has never used needs one designer save "
                "first -- the API cannot mint a connection reference."
                % (where, cname)
            )

    # 4. runAfter must name an action in the same container.
    by_container = {}
    for container_id, name, _, _ in actions:
        by_container.setdefault(container_id, set()).add(name)
    for container_id, name, action, _ in actions:
        siblings = by_container.get(container_id, set())
        where = (container_id + " > " if container_id else "") + name
        for dep in (action.get("runAfter") or {}):
            if dep not in siblings:
                problems.append(
                    "action '%s': runAfter names '%s', which is not an action "
                    "in the same container" % (where, dep)
                )

    return problems


def load_clientdata_file(path):
    text = Path(path).read_text(encoding="utf-8")
    try:
        blob = json.loads(text)
    except ValueError as exc:
        die("%s is not valid JSON: %s" % (path, exc))
    # Accept either the parsed definition or a raw JSON-string-in-JSON.
    if isinstance(blob, str):
        blob = json.loads(blob)
    if "properties" not in blob and "clientdata" in blob:
        inner = blob["clientdata"]
        blob = json.loads(inner) if isinstance(inner, str) else inner
    return blob


def snapshot(name, content):
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = SNAPSHOT_DIR / ("%s.%s.json" % (name, stamp))
    path.write_text(content, encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

SELECT = ("name,clientdata,statecode,statuscode,ismanaged,category,"
          "solutionid,workflowidunique,modifiedon")

DV_HEADERS = {
    "Accept": "application/json",
    "OData-MaxVersion": "4.0",
    "OData-Version": "4.0",
}


def dataverse_get(org, flow_id, tenant):
    token = token_for(org.rstrip("/"), tenant, interactive=False)
    url = "%s/api/data/v9.2/workflows(%s)?$select=%s" % (org.rstrip("/"), flow_id, SELECT)
    status, payload = request("GET", url, token=token, headers=DV_HEADERS)
    if status != 200:
        explain_auth_failure(payload)
        die("GET returned %d" % status, payload)
    return payload


def cmd_login(args):
    resource = args.org.rstrip("/") if args.org else RESOURCES[args.resource]
    device_code_login(resource, args.tenant,
                      client_id=getattr(args, "client_id", DEFAULT_CLIENT_ID))


def cmd_get(args):
    row = dataverse_get(args.org, args.flow, args.tenant)
    raw = row.get("clientdata") or ""
    path = snapshot("flow-%s" % args.flow, raw)

    print("name        : %s" % row.get("name"))
    print("statecode   : %s (1 = On)" % row.get("statecode"))
    print("ismanaged   : %s" % row.get("ismanaged"))
    print("modifiedon  : %s" % row.get("modifiedon"))
    print("clientdata  : %d bytes" % len(raw))
    print("snapshot    : %s" % path)

    if row.get("ismanaged"):
        print("\nWARNING: this flow is managed. Patching clientdata directly "
              "creates an unmanaged layer that future solution imports will "
              "not overwrite. The change usually belongs in the unmanaged "
              "source solution instead.")

    if args.out:
        parsed = json.loads(raw) if raw else {}
        Path(args.out).write_text(json.dumps(parsed, indent=2), encoding="utf-8")
        print("editable    : %s" % args.out)

    problems = validate(json.loads(raw)) if raw else []
    if problems:
        print("\nThe CURRENT definition already has %d problem(s):" % len(problems))
        for p in problems:
            print("  - " + p)


def cmd_validate(args):
    problems = validate(load_clientdata_file(args.clientdata))
    if not problems:
        print("OK -- %d checks passed." % 4)
        return
    print("%d problem(s):" % len(problems))
    for p in problems:
        print("  - " + p)
    sys.exit(2)


def cmd_patch(args):
    blob = load_clientdata_file(args.clientdata)

    problems = validate(blob)
    if problems and not args.force:
        print("Refusing to PATCH -- %d problem(s):" % len(problems))
        for p in problems:
            print("  - " + p)
        print("\nFix them, or pass --force if you are certain they are wrong.")
        sys.exit(2)
    if problems and args.force:
        print("WARNING: patching despite %d problem(s) because --force was "
              "given." % len(problems))

    # Snapshot the LIVE definition immediately before overwriting it. This is
    # the rollback; clientdata has no version history.
    row = dataverse_get(args.org, args.flow, args.tenant)
    before = snapshot("flow-%s.before" % args.flow, row.get("clientdata") or "")
    print("rollback snapshot: %s" % before)

    token = token_for(args.org.rstrip("/"), args.tenant, interactive=False)
    headers = dict(DV_HEADERS)
    headers["If-Match"] = row.get("@odata.etag") if args.etag else "*"

    url = "%s/api/data/v9.2/workflows(%s)" % (args.org.rstrip("/"), args.flow)
    status, payload = request(
        "PATCH", url, token=token, headers=headers,
        body={"clientdata": json.dumps(blob, separators=(",", ":"))},
    )
    if status not in (200, 204):
        explain_auth_failure(payload)
        die("PATCH returned %d -- flow unchanged" % status, payload)

    print("PATCH %d -- written." % status)
    print("\n204 means stored, not runnable. Reload the designer to confirm the "
          "flow checker is clean, then launch it once.")
    print("Rollback: pa.py patch --clientdata %s" % before)


def cmd_runs(args):
    token = token_for(RESOURCES["flow"], args.tenant, interactive=False)
    url = ("https://api.flow.microsoft.com/providers/Microsoft.ProcessSimple"
           "/environments/%s/flows/%s/runs?api-version=2016-11-01&$top=%d"
           % (args.env, args.flow, args.top))
    status, payload = request("GET", url, token=token)
    if status != 200:
        explain_auth_failure(payload)
        die("GET runs returned %d" % status, payload)
    runs = payload.get("value", [])
    if not runs:
        print("No runs. Retention is 28 days -- and a launch blocked by trigger "
              "schema validation creates no run at all.")
        return
    for run in runs:
        p = run.get("properties", {})
        print("%-34s %-10s %s  %s" % (
            run.get("name"), p.get("status"), p.get("startTime", "")[:19],
            (p.get("error") or {}).get("message", "")[:60]))


def cmd_list(args):
    token = token_for(RESOURCES["flow"], args.tenant, interactive=False)
    url = ("https://api.flow.microsoft.com/providers/Microsoft.ProcessSimple"
           "/environments/%s/flows?api-version=2016-11-01" % args.env)
    status, payload = request("GET", url, token=token)
    if status != 200:
        explain_auth_failure(payload)
        die("GET flows returned %d" % status, payload)
    for flow in payload.get("value", []):
        p = flow.get("properties", {})
        print("%s  %-8s %s" % (flow.get("name"), p.get("state"),
                               p.get("displayName")))


def main():
    # --tenant is accepted both before and after the subcommand, because both
    # read naturally and getting it wrong is an unhelpful argparse error. The
    # subcommand copy uses SUPPRESS so that omitting it does not clobber a
    # value given at the top level.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--tenant", default=argparse.SUPPRESS,
                        help="tenant id or domain (env: PA_TENANT)")

    parser = argparse.ArgumentParser(
        description="Power Automate flow definitions via API.",
        epilog="Read references/auth.md before overriding any scope.")
    parser.add_argument("--tenant", default=os.environ.get("PA_TENANT", "organizations"),
                        help="tenant id or domain (env: PA_TENANT)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("login", parents=[common],
                       help="device-code sign-in, caches the token")
    p.add_argument("--org", help="resource URI, e.g. https://x.crm.dynamics.com "
                                 "or https://tenant.sharepoint.com")
    p.add_argument("--resource", choices=sorted(RESOURCES), default="flow")
    p.add_argument("--client-id", dest="client_id", default=DEFAULT_CLIENT_ID,
                   help="public client to authenticate as. SharePoint REST "
                        "refuses the Azure CLI default with 3001003 'App is not "
                        "allowed to call SPO with user_impersonation scope' -- "
                        "use a client holding granular SPO scopes instead.")
    p.set_defaults(func=cmd_login)

    p = sub.add_parser("get", parents=[common], help="read a flow and snapshot its definition")
    p.add_argument("--org", required=True)
    p.add_argument("--flow", required=True)
    p.add_argument("--out", help="also write the parsed definition here, for editing")
    p.set_defaults(func=cmd_get)

    p = sub.add_parser("validate", parents=[common], help="check a definition offline, no token needed")
    p.add_argument("--clientdata", required=True)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("patch", parents=[common], help="validate, snapshot, then write a definition")
    p.add_argument("--org", required=True)
    p.add_argument("--flow", required=True)
    p.add_argument("--clientdata", required=True)
    p.add_argument("--etag", action="store_true",
                   help="fail if the flow changed since the read (multi-owner flows)")
    p.add_argument("--force", action="store_true",
                   help="patch despite validation problems")
    p.set_defaults(func=cmd_patch)

    p = sub.add_parser("runs", parents=[common], help="run history for a flow")
    p.add_argument("--env", required=True)
    p.add_argument("--flow", required=True)
    p.add_argument("--top", type=int, default=20)
    p.set_defaults(func=cmd_runs)

    p = sub.add_parser("list", parents=[common], help="flows in an environment")
    p.add_argument("--env", required=True)
    p.set_defaults(func=cmd_list)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
