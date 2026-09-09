#!/usr/bin/env python3
"""
kb4.py - read-only client for the KnowBe4 KSAT Reporting API.

Handles the parts that are easy to get wrong by hand: offset pagination to
exhaustion, 429 backoff (KnowBe4 sends no Retry-After header), regional base
URLs, and tabular output.

This tool cannot write. KnowBe4's Reporting API is read-only; user and group
mutations go through SCIM, ADI, or the console. See references/writes.md.

Auth:
    export KB4_TOKEN='your-reporting-api-token'
    export KB4_REGION=us            # or: eu, ca, uk, de
    # or override entirely:
    export KB4_BASE_URL='https://us.api.knowbe4.com'

Stdlib only. No pip install required.
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_PER_PAGE = 500
MAX_PER_PAGE = 500
MAX_RETRIES = 6


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

def base_url():
    explicit = os.environ.get("KB4_BASE_URL")
    if explicit:
        return explicit.rstrip("/")
    region = os.environ.get("KB4_REGION", "us").strip().lower()
    return f"https://{region}.api.knowbe4.com"


def token():
    tok = os.environ.get("KB4_TOKEN") or os.environ.get("KB4_API_TOKEN")
    if not tok:
        die("KB4_TOKEN is not set. Create a Reporting API token in the KSAT "
            "console under Account Settings > Account Integrations > API.")
    return tok


def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def request(path, params=None, verbose=False):
    """One GET with retry/backoff. Returns parsed JSON."""
    if not path.startswith("/"):
        path = "/" + path
    url = base_url() + path
    if params:
        url += "?" + urllib.parse.urlencode(params)

    delay = 1.0
    for attempt in range(1, MAX_RETRIES + 1):
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token()}",
            "Accept": "application/json",
            "User-Agent": "kb4.py/1.0",
        })
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                remaining = resp.headers.get("X-RateLimit-Remaining")
                if verbose:
                    note = f" (rate limit remaining: {remaining})" if remaining else ""
                    print(f"  GET {url} -> {resp.status}{note}", file=sys.stderr)
                body = resp.read().decode("utf-8")
                return json.loads(body) if body.strip() else []

        except urllib.error.HTTPError as e:
            if e.code == 429:
                # No Retry-After header from KnowBe4 - back off manually.
                if verbose:
                    print(f"  429 throttled, sleeping {delay:.0f}s "
                          f"(attempt {attempt}/{MAX_RETRIES})", file=sys.stderr)
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            if e.code == 401:
                die("401 Unauthorized. Three usual causes, in order of likelihood:\n"
                    f"  1. Wrong region - currently using {base_url()}. "
                    "Match it to your KSAT console URL (set KB4_REGION).\n"
                    "  2. Subscription tier below Platinum/Diamond/SAT Foundations/"
                    "SAT Advanced - the Reporting API is gated.\n"
                    "  3. Token expired, revoked, or is a SCIM/User Event token "
                    "rather than a Reporting API token (they are not interchangeable).")
            if e.code >= 500 and attempt < MAX_RETRIES:
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            detail = e.read().decode("utf-8", "replace")[:400]
            die(f"HTTP {e.code} on {url}\n{detail}")

        except urllib.error.URLError as e:
            if attempt < MAX_RETRIES:
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            die(f"network error reaching {url}: {e.reason}")

    die(f"gave up after {MAX_RETRIES} attempts on {url}")


def paginate(path, params=None, per_page=DEFAULT_PER_PAGE, limit=None, verbose=False):
    """Walk offset pagination until an empty array. Returns a flat list."""
    per_page = min(per_page, MAX_PER_PAGE)
    params = dict(params or {})
    out, page = [], 1
    while True:
        params.update({"page": page, "per_page": per_page})
        batch = request(path, params, verbose=verbose)
        if isinstance(batch, dict):          # single-object endpoint
            return [batch]
        if not batch:                        # empty array = end of data
            break
        out.extend(batch)
        if verbose:
            print(f"  page {page}: {len(batch)} records "
                  f"({len(out)} total)", file=sys.stderr)
        if limit and len(out) >= limit:
            return out[:limit]
        if len(batch) < per_page:
            break
        page += 1
    return out


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def flatten(rec, prefix=""):
    flat = {}
    for k, v in rec.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            flat.update(flatten(v, prefix=f"{key}."))
        elif isinstance(v, list):
            flat[key] = "; ".join(
                str(i.get("name", i.get("id", i))) if isinstance(i, dict) else str(i)
                for i in v
            )
        else:
            flat[key] = v
    return flat


def select(rows, fields):
    if not fields:
        return rows
    keep = [f.strip() for f in fields.split(",")]
    return [{k: r.get(k, "") for k in keep} for r in rows]


def emit(rows, fmt, out_path=None, max_table_rows=25):
    if not rows:
        print("No records returned.", file=sys.stderr)
        return
    rows = [flatten(r) if isinstance(r, dict) else {"value": r} for r in rows]

    if fmt == "json":
        text = json.dumps(rows, indent=2)
        if out_path:
            open(out_path, "w").write(text)
            print(f"Wrote {len(rows)} records to {out_path}", file=sys.stderr)
        else:
            print(text)
        return

    cols = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)

    if fmt == "csv":
        if out_path:
            with open(out_path, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
                w.writeheader()
                w.writerows(rows)
            print(f"Wrote {len(rows)} records to {out_path}", file=sys.stderr)
        else:
            w = csv.DictWriter(sys.stdout, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        return

    # markdown table
    shown = rows[:max_table_rows]
    widths = {c: max(len(c), *(len(str(r.get(c, ""))) for r in shown)) for c in cols}
    print("| " + " | ".join(c.ljust(widths[c]) for c in cols) + " |")
    print("|" + "|".join("-" * (widths[c] + 2) for c in cols) + "|")
    for r in shown:
        print("| " + " | ".join(str(r.get(c, "")).ljust(widths[c]) for c in cols) + " |")
    if len(rows) > max_table_rows:
        print(f"\n... {len(rows) - max_table_rows} more rows "
              f"({len(rows)} total). Use --format csv --out file.csv for all of them.")


# --------------------------------------------------------------------------
# Reconciliation
# --------------------------------------------------------------------------

def load_emails(path, column=None):
    """Read a CSV/TXT of authoritative identities; return a set of lowercased emails."""
    emails = set()
    with open(path, newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        if "," in sample or "\t" in sample:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                die(f"{path} has no header row")
            col = column
            if not col:
                for cand in ("email", "mail", "userPrincipalName", "user_principal_name",
                             "EmailAddress", "primary_email", "Email"):
                    match = next((f for f in reader.fieldnames
                                  if f.strip().lower() == cand.lower()), None)
                    if match:
                        col = match
                        break
            if not col:
                die(f"could not find an email column in {path}. "
                    f"Columns present: {', '.join(reader.fieldnames)}. "
                    f"Specify one with --email-column.")
            if col not in reader.fieldnames:
                die(f"column '{col}' not in {path}. "
                    f"Columns present: {', '.join(reader.fieldnames)}")
            for row in reader:
                v = (row.get(col) or "").strip().lower()
                if v:
                    emails.add(v)
        else:
            for line in fh:
                v = line.strip().lower()
                if v and "@" in v:
                    emails.add(v)
    return emails


def cmd_reconcile(args):
    source = load_emails(args.source, args.email_column)
    if not source:
        die(f"no email addresses parsed from {args.source}")
    users = paginate("/v1/users", verbose=args.verbose)

    orphaned, matched = [], set()
    for u in users:
        email = (u.get("email") or "").strip().lower()
        if not email:
            continue
        if email in source:
            matched.add(email)
        elif (u.get("status") or "").lower() == "active":
            orphaned.append({
                "id": u.get("id"),
                "email": u.get("email"),
                "status": u.get("status"),
                "department": u.get("department", ""),
                "adi_manageable": u.get("adi_manageable", ""),
                "phish_prone_percentage": u.get("phish_prone_percentage", ""),
            })

    missing = sorted(source - {(u.get("email") or "").strip().lower() for u in users})
    active = sum(1 for u in users if (u.get("status") or "").lower() == "active")

    print(f"KnowBe4 users:            {len(users)} ({active} active)", file=sys.stderr)
    print(f"Source identities:        {len(source)}", file=sys.stderr)
    print(f"Active in KB4, not in source (orphaned): {len(orphaned)}", file=sys.stderr)
    print(f"In source, not in KB4 (unprovisioned):   {len(missing)}\n", file=sys.stderr)

    if args.show == "missing":
        rows = [{"email": e} for e in missing]
    else:
        rows = orphaned

    if args.limit:
        rows = rows[:args.limit]
    emit(select(rows, args.fields), args.format, args.out)

    if args.show == "orphaned" and any(o.get("adi_manageable") for o in orphaned):
        print("\nNote: some orphaned users are adi_manageable. Archiving them in the "
              "console will be reverted at the next AD sync - remove them upstream "
              "in AD instead.", file=sys.stderr)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def load_rows(path):
    """Read a CSV export into a list of dicts, preserving all columns."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            die(f"{path} has no header row")
        return [dict(r) for r in reader], list(reader.fieldnames)


def cmd_drift(args):
    """Compare per-field values in an IdP export against what KnowBe4 holds.

    Answers the question SCIM logs cannot: the cycle reported success, but did
    the attribute values actually land?
    """
    rows, columns = load_rows(args.source)
    if not rows:
        die(f"no rows parsed from {args.source}")

    email_col = args.email_column
    if not email_col:
        for cand in ("userPrincipalName", "email", "mail", "user_principal_name",
                     "EmailAddress", "Email"):
            match = next((c for c in columns if c.strip().lower() == cand.lower()), None)
            if match:
                email_col = match
                break
    if not email_col:
        die(f"could not find an email column in {args.source}. "
            f"Columns present: {', '.join(columns)}. Use --email-column.")

    pairs = []
    for chunk in args.map.split(","):
        if "=" not in chunk:
            die(f"--map entries must look like sourceColumn=kb4_field, got '{chunk}'")
        src, dst = chunk.split("=", 1)
        src, dst = src.strip(), dst.strip()
        if src not in columns:
            die(f"column '{src}' not in {args.source}. "
                f"Columns present: {', '.join(columns)}")
        pairs.append((src, dst))

    source = {}
    for r in rows:
        e = (r.get(email_col) or "").strip().lower()
        if e:
            source[e] = r

    users = paginate("/v1/users", verbose=args.verbose)
    kb4 = {(u.get("email") or "").strip().lower(): u for u in users
           if (u.get("email") or "").strip()}

    findings, absent, compared = [], 0, 0
    for email, srow in source.items():
        u = kb4.get(email)
        if u is None:
            absent += 1
            continue
        compared += 1
        for src, dst in pairs:
            want = (srow.get(src) or "").strip()
            got = u.get(dst)
            got = "" if got is None else str(got).strip()
            if args.ignore_blank_source and not want:
                continue
            if want.lower() != got.lower():
                findings.append({
                    "email": u.get("email"),
                    "field": dst,
                    "idp_value": want or "(blank)",
                    "knowbe4_value": got or "(blank)",
                    "adi_manageable": u.get("adi_manageable", ""),
                })

    print(f"Compared:                 {compared} users across "
          f"{len(pairs)} field(s)", file=sys.stderr)
    print(f"In export, absent in KB4: {absent}", file=sys.stderr)
    print(f"Field mismatches:         {len(findings)}\n", file=sys.stderr)

    if not findings:
        print("No drift. Every compared field matches - if the sync still looks wrong, "
              "the field in question is probably unmapped in the provisioning config "
              "rather than failing to sync.", file=sys.stderr)
        return

    by_field = {}
    for f in findings:
        by_field[f["field"]] = by_field.get(f["field"], 0) + 1
    print("Mismatches by field: " + ", ".join(
        f"{k}={v}" for k, v in sorted(by_field.items(), key=lambda x: -x[1])),
        file=sys.stderr)

    for field, count in by_field.items():
        if count == compared:
            print(f"\nEvery compared user differs on '{field}'. That pattern means an "
                  f"unmapped or mis-mapped attribute in the Entra provisioning config, "
                  f"not a sync failure.", file=sys.stderr)
    print("", file=sys.stderr)

    rows_out = findings[:args.limit] if args.limit else findings
    emit(select(rows_out, args.fields), args.format, args.out)

    if any(f.get("adi_manageable") for f in findings):
        print("\nNote: some drifting users are adi_manageable. ADI and SCIM are both "
              "writing to these records - resolve that conflict before chasing the "
              "mapping.", file=sys.stderr)


def cmd_duplicates(args):
    """Find probable duplicate people - the signature of an identity-match
    failure during an ADI -> SCIM migration.

    SCIM matches on userName (default source: userPrincipalName). ADI commonly
    populated records from a different attribute (usually primary SMTP). Where
    UPN != mail, SCIM cannot match the existing record and creates a second one
    instead, so the account population roughly doubles.
    """
    users = paginate("/v1/users", verbose=args.verbose)

    def norm(v):
        return (str(v).strip().lower() if v not in (None, "") else "")

    clusters = {}

    def add(key, kind, u):
        if not key:
            return
        clusters.setdefault((kind, key), []).append(u)

    for u in users:
        email = norm(u.get("email"))
        local = email.split("@")[0] if "@" in email else ""
        add(norm(u.get("employee_number")), "employee_number", u)
        add(local, "email_local_part", u)
        name = f"{norm(u.get('first_name'))} {norm(u.get('last_name'))}".strip()
        if name and name != "":
            add(name, "name", u)

    seen_pairs, rows = set(), []
    # A single person can match on several keys at once. Merge those into one
    # cluster - reporting the same pair three times inflates the count and
    # hides how many real people are affected.
    merged = {}
    for (kind, key), members in clusters.items():
        if len(members) < 2:
            continue
        ids = frozenset(m.get("id") for m in members)
        emails = {norm(m.get("email")) for m in members}
        if len(emails) < 2:          # same record matched twice, not a duplicate
            continue
        entry = merged.setdefault(ids, {"members": members, "methods": set()})
        entry["methods"].add(kind)

    for ids, entry in sorted(merged.items(), key=lambda x: sorted(
            norm(m.get("email")) for m in x[1]["members"])):
        seen_pairs.add((tuple(sorted(entry["methods"])),
                        tuple(sorted(norm(m.get("email")) for m in entry["members"]))))
        methods = "+".join(sorted(entry["methods"]))
        for m in sorted(entry["members"], key=lambda x: norm(x.get("email"))):
            rows.append({
                "matched_on": methods,
                "id": m.get("id"),
                "email": m.get("email"),
                "status": m.get("status"),
                "adi_manageable": m.get("adi_manageable", ""),
                "phish_prone_percentage": m.get("phish_prone_percentage", ""),
            })

    groups_found = len(merged)
    active = sum(1 for u in users if norm(u.get("status")) == "active")
    print(f"Total users:              {len(users)} ({active} active)", file=sys.stderr)
    print(f"Probable duplicate sets:  {groups_found}", file=sys.stderr)

    if not rows:
        print("\nNo duplicate identities detected. If the account total is still "
              "higher than expected, the extras are more likely un-archived "
              "leftovers than duplicates - compare against the in-scope group "
              "with 'reconcile'.", file=sys.stderr)
        return

    # Domain-mismatch pattern is the tell for a UPN vs mail matching failure.
    domains = {}
    for r in rows:
        e = norm(r["email"])
        if "@" in e:
            domains[e.split("@")[1]] = domains.get(e.split("@")[1], 0) + 1
    if len(domains) > 1:
        top = sorted(domains.items(), key=lambda x: -x[1])
        print("\nDuplicates span multiple email domains: " +
              ", ".join(f"{d} ({n})" for d, n in top) +
              "\nThat is the signature of SCIM matching on userPrincipalName while "
              "the existing ADI records used a different address. Align the SCIM "
              "userName source attribute with what ADI populated before syncing "
              "again.", file=sys.stderr)

    mixed = sum(1 for entry in merged.values()
                if "employee_number" in entry["methods"])
    if mixed:
        print(f"\n{mixed} of {groups_found} set(s) matched on employee_number - a strong "
              f"signal these are the same person, not a name coincidence.", file=sys.stderr)

    split = sum(1 for entry in merged.values()
                if any(m.get("adi_manageable") for m in entry["members"])
                and any(not m.get("adi_manageable") for m in entry["members"]))
    if split:
        print(f"{split} set(s) pair an adi_manageable record with a non-ADI one - "
              f"i.e. an old ADI record and a new SCIM record for the same person. "
              f"Historic phishing and training results sit on the ADI record and do "
              f"not follow the user to the new one.", file=sys.stderr)
    print("", file=sys.stderr)

    out_rows = rows[:args.limit] if args.limit else rows
    emit(select(out_rows, args.fields), args.format, args.out)


def graphql_request(query, verbose=False):
    """POST a GraphQL query using the Product API token. Read-only by intent -
    this is used for schema introspection, not mutations."""
    tok = os.environ.get("KB4_PRODUCT_TOKEN")
    if not tok:
        die("KB4_PRODUCT_TOKEN is not set. The Graph API uses a Product API token, "
            "not the Reporting API token. Create one in the KSAT console under "
            "Account Settings > Account Integrations > Product API. Read Only scope "
            "is sufficient for schema introspection.")
    path = os.environ.get("KB4_GRAPHQL_PATH", "/graphql")
    url = base_url() + path
    body = json.dumps({"query": query}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {tok}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "kb4.py/1.0",
    })
    if verbose:
        print(f"  POST {url}", file=sys.stderr)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        if e.code in (401, 403):
            die(f"HTTP {e.code} on {url}\n{detail}\n"
                "Check: the token is a Product API token (not Reporting), the account "
                "is Diamond tier, and the region matches your console.")
        if e.code == 404:
            die(f"HTTP 404 on {url}\n"
                "The GraphQL path may differ for your account. Override it with "
                "KB4_GRAPHQL_PATH and confirm against developer.knowbe4.com.")
        die(f"HTTP {e.code} on {url}\n{detail}")
    except urllib.error.URLError as e:
        die(f"network error reaching {url}: {e.reason}")

    if data.get("errors"):
        die("GraphQL returned errors:\n" +
            json.dumps(data["errors"], indent=2)[:800])
    return data.get("data", {})


INTROSPECT = """
query {
  __schema {
    mutationType { fields { name description
      args { name type { name kind ofType { name kind } } } } }
    queryType { fields { name description } }
  }
}
"""


def cmd_schema(args):
    """List what the Graph API actually exposes.

    "Most functions" in the docs is not a specification. Introspect before
    planning any bulk operation around a mutation that may not exist.
    """
    data = graphql_request(INTROSPECT, verbose=args.verbose)
    schema = data.get("__schema") or {}
    mutations = ((schema.get("mutationType") or {}).get("fields")) or []
    queries = ((schema.get("queryType") or {}).get("fields")) or []

    which = args.show
    pool = mutations if which == "mutations" else queries
    label = which

    if args.grep:
        needle = args.grep.lower()
        pool = [f for f in pool
                if needle in (f.get("name") or "").lower()
                or needle in (f.get("description") or "").lower()]

    print(f"Schema exposes {len(mutations)} mutation(s) and {len(queries)} query field(s).",
          file=sys.stderr)
    if args.grep:
        print(f"Showing {label} matching '{args.grep}': {len(pool)}\n", file=sys.stderr)
    else:
        print(f"Showing all {label}: {len(pool)}\n", file=sys.stderr)

    rows = []
    for f in sorted(pool, key=lambda x: x.get("name") or ""):
        desc = (f.get("description") or "").replace("\n", " ").strip()
        row = {"name": f.get("name"), "description": desc[:110]}
        if which == "mutations":
            row["args"] = ", ".join(a.get("name") for a in (f.get("args") or []))
        rows.append(row)

    if not rows:
        print("Nothing matched. If you were looking for a bulk merge or archive "
              "operation and it is absent, that work has to happen in the console - "
              "plan the manual effort rather than assuming an endpoint exists.",
              file=sys.stderr)
        return

    out_rows = rows[:args.limit] if args.limit else rows
    emit(select(out_rows, args.fields), args.format, args.out)

    if which == "mutations":
        print("\nReminder: running a mutation while SCIM provisioning is live adds a "
              "second writer to the same records. Pause the sync (KSAT Test Mode) "
              "before any bulk write.", file=sys.stderr)


def main():
    # Shared flags live on a parent parser so they are accepted either before
    # or after the subcommand - "kb4.py users --format csv" is what people
    # actually type, and argparse rejects it otherwise.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--format", choices=["table", "csv", "json"], default="table")
    common.add_argument("--out", help="write output to this file instead of stdout")
    common.add_argument("--fields", help="comma-separated list of fields to keep")
    common.add_argument("--limit", type=int, help="stop after N records")
    common.add_argument("-v", "--verbose", action="store_true",
                        help="log each request and pagination progress to stderr")

    p = argparse.ArgumentParser(
        description="Read-only KnowBe4 KSAT Reporting API client.",
        parents=[common],
        epilog="This tool cannot create, update, or archive users. "
               "Those go through SCIM, ADI, or the console.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("account", parents=[common],
                   help="account metadata and subscription level")

    u = sub.add_parser("users", parents=[common], help="list all users")
    u.add_argument("--status", choices=["active", "archived"])

    sub.add_parser("groups", parents=[common], help="list groups")

    m = sub.add_parser("members", parents=[common], help="list members of a group")
    m.add_argument("group_id")

    sub.add_parser("campaigns", parents=[common], help="list phishing campaigns")
    sub.add_parser("security-tests", parents=[common],
                   help="list individual phishing security tests")

    r = sub.add_parser("recipients", parents=[common],
                       help="per-user results for one security test")
    r.add_argument("pst_id")

    sub.add_parser("enrollments", parents=[common], help="list training enrollments")
    sub.add_parser("training", parents=[common], help="list training campaigns")

    g = sub.add_parser("get", parents=[common],
                       help="raw GET against any path, e.g. /v1/users/123")
    g.add_argument("path")

    rc = sub.add_parser(
        "reconcile", parents=[common],
        help="compare KnowBe4 users against an IdP/HR export to find orphans")
    rc.add_argument("--source", required=True,
                    help="CSV or newline-delimited file of authoritative emails")
    rc.add_argument("--email-column",
                    help="column name holding email (auto-detected if omitted)")
    rc.add_argument("--show", choices=["orphaned", "missing"], default="orphaned",
                    help="orphaned = active in KB4 but not in source (default); "
                         "missing = in source but absent from KB4")

    df = sub.add_parser(
        "drift", parents=[common],
        help="compare field values in an IdP export against KnowBe4 "
             "(did the SCIM sync actually land?)")
    df.add_argument("--source", required=True,
                    help="CSV export from Entra/Okta with the mapped attributes")
    df.add_argument("--email-column",
                    help="column holding the email/UPN (auto-detected if omitted)")
    df.add_argument("--map", required=True,
                    help="comma-separated sourceColumn=kb4_field pairs, e.g. "
                         "department=department,jobTitle=job_title")
    df.add_argument("--ignore-blank-source", action="store_true",
                    help="skip rows where the IdP value is empty, to avoid "
                         "flagging attributes the export simply did not include")

    sub.add_parser(
        "duplicates", parents=[common],
        help="find probable duplicate people (the ADI -> SCIM identity-match "
             "failure signature)")

    sc = sub.add_parser(
        "schema", parents=[common],
        help="introspect the Graph API (GraphQL) schema - list available "
             "mutations and queries. Diamond tier, Product API token")
    sc.add_argument("--show", choices=["mutations", "queries"], default="mutations")
    sc.add_argument("--grep", help="filter by substring in the name or description")

    args = p.parse_args()

    if args.cmd == "schema":
        cmd_schema(args)
        return
    if args.cmd == "reconcile":
        cmd_reconcile(args)
        return
    if args.cmd == "drift":
        cmd_drift(args)
        return
    if args.cmd == "duplicates":
        cmd_duplicates(args)
        return

    routes = {
        "account":        ("/v1/account", {}),
        "users":          ("/v1/users", {}),
        "groups":         ("/v1/groups", {}),
        "campaigns":      ("/v1/phishing/campaigns", {}),
        "security-tests": ("/v1/phishing/security_tests", {}),
        "enrollments":    ("/v1/training/enrollments", {}),
        "training":       ("/v1/training/campaigns", {}),
    }

    if args.cmd in routes:
        path, params = routes[args.cmd]
        if args.cmd == "users" and getattr(args, "status", None):
            params["status"] = args.status
    elif args.cmd == "members":
        path, params = f"/v1/groups/{args.group_id}/members", {}
    elif args.cmd == "recipients":
        path, params = f"/v1/phishing/security_tests/{args.pst_id}/recipients", {}
    elif args.cmd == "get":
        path, params = args.path, {}
    else:
        die(f"unhandled command {args.cmd}")

    rows = paginate(path, params, limit=args.limit, verbose=args.verbose)
    emit(select(rows, args.fields), args.format, args.out)


if __name__ == "__main__":
    main()
