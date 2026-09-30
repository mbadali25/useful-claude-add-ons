#!/usr/bin/env python3
"""
mg.py - Mailgun command-line tool (standard library only, Python 3.8+).

Credentials come from environment variables (never hard-code them):
  MAILGUN_API_KEY   required
  MAILGUN_DOMAIN    default sending/receiving domain (optional)
  MAILGUN_REGION    "us" (default) or "eu"
If they are not set, the file ~/.mailgun.env (KEY=value lines) is read.

Run `python3 mg.py -h` for the command list.
"""
import argparse, base64, json, mimetypes, os, re, sys, uuid
import urllib.parse, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

HERE = os.path.dirname(os.path.abspath(__file__))
OPS_FILE = os.path.join(HERE, "..", "references", "operations.json")


# ---------------------------------------------------------------- config
def load_env():
    path = os.path.expanduser("~/.mailgun.env")
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def cfg(name, required=True, default=None):
    v = os.environ.get(name, default)
    if required and not v:
        sys.exit(f"Missing {name}. Set it as an environment variable or in ~/.mailgun.env")
    return v


def base_url():
    region = (os.environ.get("MAILGUN_REGION") or "us").lower()
    return "https://api.eu.mailgun.net" if region == "eu" else "https://api.mailgun.net"


def domain(args):
    d = getattr(args, "domain", None) or os.environ.get("MAILGUN_DOMAIN")
    if not d:
        sys.exit("No domain given. Pass --domain or set MAILGUN_DOMAIN.")
    return d


# ---------------------------------------------------------------- http
def multipart(fields, files):
    boundary = uuid.uuid4().hex
    out = bytearray()
    for k, v in fields:
        out += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n".encode()
        out += str(v).encode() + b"\r\n"
    for k, path in files:
        name = os.path.basename(path)
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; "
                f"filename=\"{name}\"\r\nContent-Type: {ctype}\r\n\r\n").encode()
        out += open(path, "rb").read() + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def request(method, path_or_url, query=None, form=None, files=None, json_body=None,
            accept="application/json", raw=False):
    """form: list of (key, value) pairs (repeatable keys allowed); files: list of (field, path)."""
    key = cfg("MAILGUN_API_KEY")
    url = path_or_url if path_or_url.startswith("http") else base_url() + path_or_url
    if query:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(query, doseq=True)
    data, headers = None, {"Accept": accept}
    if json_body is not None:
        data = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json"
    elif files:
        data, headers["Content-Type"] = multipart(form or [], files)
    elif form:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    headers["Authorization"] = "Basic " + base64.b64encode(f"api:{key}".encode()).decode()
    req = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        hint = {401: "API key wrong, or wrong region (try MAILGUN_REGION=eu / us).",
                403: "Key lacks permission for this action (check key role).",
                404: "Wrong path, domain, or region.",
                429: "Rate limited - wait and retry."}.get(e.code, "")
        sys.exit(f"HTTP {e.code} {method} {url}\n{body}\n{hint}")
    if raw:
        return body
    text = body.decode(errors="replace")
    try:
        return json.loads(text)
    except ValueError:
        return text


def show(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False) if not isinstance(obj, str) else obj)


def kv_list(items):
    out = []
    for it in items or []:
        if "=" not in it:
            sys.exit(f"Expected key=value, got: {it}")
        k, v = it.split("=", 1)
        out.append((k, v))
    return out


def rfc2822(dt):
    return format_datetime(dt)


# ---------------------------------------------------------------- generic
def cmd_call(a):
    method = a.method.upper()
    if method == "DELETE" and not a.yes:
        sys.exit("DELETE is destructive. Re-run with --yes after the user confirms.")
    path = a.path
    for ph in ("{domain_name}", "{domain}", "{domainName}", "/domains/{name}"):
        if ph in path:
            path = path.replace(ph, ph.replace(ph.strip("/").split("/")[-1], domain(a)))
    if re.search(r"{[^}]+}", path):
        sys.exit(f"Fill in the placeholders in the path: {path}")
    jb = json.loads(a.json) if a.json else None
    show(request(method, path, query=kv_list(a.query), form=kv_list(a.form),
                 files=kv_list(a.file), json_body=jb))


def load_ops():
    return json.load(open(OPS_FILE))


def cmd_find(a):
    words = [w.lower() for w in a.words]
    for o in load_ops():
        hay = f"{o['method']} {o['path']} {o['tag']} {o['summary']}".lower()
        if all(w in hay for w in words):
            dep = "  [DEPRECATED]" if o["deprecated"] else ""
            print(f"{o['method']:6} {o['path']}  - {o['summary']}{dep}")


def cmd_describe(a):
    m, _, p = a.op.strip().partition(" ")
    for o in load_ops():
        if o["method"] == m.upper() and o["path"] == p.strip():
            show(o)
            return
    sys.exit("Not found. Use `find` to get the exact METHOD and path.")


# ---------------------------------------------------------------- send
def cmd_send(a):
    d = domain(a)
    form = [("from", a.sender or cfg("MAILGUN_FROM", required=False) or f"postmaster@{d}")]
    for t in a.to:
        form.append(("to", t))
    for c in a.cc or []:
        form.append(("cc", c))
    for b in a.bcc or []:
        form.append(("bcc", b))
    if a.subject:
        form.append(("subject", a.subject))
    if a.text:
        form.append(("text", a.text))
    if a.html:
        html = open(a.html[1:]).read() if a.html.startswith("@") else a.html
        form.append(("html", html))
    if a.template:
        form.append(("template", a.template))
        if a.var:
            form.append(("t:variables", json.dumps(dict(kv_list(a.var)))))
    for t in a.tag or []:
        form.append(("o:tag", t))
    if a.deliver_at:
        form.append(("o:deliverytime", a.deliver_at))
    if a.test:
        form.append(("o:testmode", "yes"))
    if a.reply_to:
        form.append(("h:Reply-To", a.reply_to))
    for k, v in kv_list(a.header):
        form.append((f"h:{k}", v))
    for k, v in kv_list(a.data):
        form.append((f"v:{k}", v))
    for k, v in kv_list(a.opt):
        form.append((k, v))
    files = [("attachment", p) for p in (a.attach or [])] + [("inline", p) for p in (a.inline or [])]
    if not (a.text or a.html or a.template):
        sys.exit("Need --text, --html, or --template.")
    show(request("POST", f"/v3/{d}/messages", form=form, files=files or None))


# ---------------------------------------------------------------- receive
def cmd_inbox_setup(a):
    d = domain(a)
    expr = a.expression or f'match_recipient(".*@{d}")'
    form = [("priority", str(a.priority)), ("description", a.description or f"Store inbound for {d}"),
            ("expression", expr), ("action", "store()" if not a.notify else f'store(notify="{a.notify}")')]
    if a.forward:
        form.append(("action", f'forward("{a.forward}")'))
    show(request("POST", "/v3/routes", form=form))


def cmd_inbox(a):
    d = domain(a)
    begin = datetime.now(timezone.utc) - timedelta(hours=a.hours)
    q = [("event", "stored"), ("begin", rfc2822(begin)), ("ascending", "no"), ("limit", str(a.limit))]
    res = request("GET", f"/v3/{d}/events", query=q)
    items = res.get("items", []) if isinstance(res, dict) else []
    if a.json_out:
        show(items)
        return
    if not items:
        print("No stored inbound messages in that window. (Is a store() route set up? Run inbox-setup.)")
        return
    print(f"{'#':>3}  {'received (UTC)':19}  {'from':32}  subject")
    for i, e in enumerate(items, 1):
        h = e.get("message", {}).get("headers", {})
        ts = datetime.fromtimestamp(e.get("timestamp", 0), timezone.utc).strftime("%Y-%m-%d %H:%M")
        print(f"{i:>3}  {ts:19}  {h.get('from','')[:32]:32}  {h.get('subject','')}")
        print(f"     url: {e.get('storage', {}).get('url','')}")


def cmd_read(a):
    ref = a.ref
    if not ref.startswith("http"):
        ref = f"/v3/domains/{domain(a)}/messages/{ref}"
    if a.mime:
        sys.stdout.write(request("GET", ref, accept="message/rfc2822", raw=True).decode(errors="replace"))
        return
    m = request("GET", ref)
    if a.full or not isinstance(m, dict):
        show(m)
        return
    for k in ("From", "To", "Subject", "Date"):
        print(f"{k}: {m.get(k) or m.get(k.lower(), '')}")
    atts = m.get("attachments") or []
    if atts:
        print("Attachments: " + ", ".join(f"{x.get('name')} ({x.get('size')} B)" for x in atts))
    print("-" * 60)
    print(m.get("stripped-text") or m.get("body-plain") or "")


def cmd_attachment(a):
    """Download an attachment URL (from `read --full`) to a file."""
    data = request("GET", a.url, accept="*/*", raw=True)
    open(a.out, "wb").write(data)
    print(f"Saved {len(data)} bytes to {a.out}")


# ---------------------------------------------------------------- reports
def filt(attr, values):
    return {"attribute": attr, "comparator": "=", "values": [{"label": v, "value": v} for v in values]}


def cmd_logs(a):
    body = {"duration": a.duration, "pagination": {"sort": "timestamp:desc", "limit": a.limit},
            "include_totals": True}
    conds = []
    if a.domain or os.environ.get("MAILGUN_DOMAIN"):
        conds.append(filt("domain", [domain(a)]))
    if a.recipient:
        conds.append(filt("recipient", [a.recipient]))
    if a.message_id:
        conds.append(filt("message_id", [a.message_id]))
    if a.tag:
        conds.append(filt("tag", [a.tag]))
    if conds:
        body["filter"] = {"AND": conds}
    if a.event:
        body["events"] = a.event
    res = request("POST", "/v1/analytics/logs", json_body=body)
    if a.json_out or not isinstance(res, dict):
        show(res)
        return
    items = res.get("items", [])
    print(f"{len(items)} events shown (total: {res.get('aggregates', {}).get('all', res.get('total', '?'))})")
    print(f"{'time':20} {'event':14} {'recipient':34} status")
    for e in items:
        ds = e.get("delivery-status") or {}
        status = f"{ds.get('code','')} {ds.get('message') or ds.get('description') or ''}".strip()
        print(f"{e.get('@timestamp','')[:19]:20} {e.get('event',''):14} {str(e.get('recipient',''))[:34]:34} {status[:60]}")


DEFAULT_METRICS = ["accepted_count", "delivered_count", "failed_count", "permanent_failed_count",
                   "temporary_failed_count", "opened_count", "unique_opened_count", "clicked_count",
                   "unique_clicked_count", "unsubscribed_count", "complained_count",
                   "delivered_rate", "opened_rate", "clicked_rate", "bounced_rate", "complained_rate"]


def cmd_metrics(a):
    body = {"duration": a.duration, "resolution": a.resolution, "dimensions": a.dimension or [],
            "metrics": a.metric or DEFAULT_METRICS, "include_aggregates": True}
    conds = []
    if a.domain or os.environ.get("MAILGUN_DOMAIN"):
        conds.append(filt("domain", [domain(a)]))
    if a.tag:
        conds.append(filt("tag", [a.tag]))
    if conds:
        body["filter"] = {"AND": conds}
    res = request("POST", "/v1/analytics/metrics", json_body=body)
    if a.json_out or not isinstance(res, dict):
        show(res)
        return
    agg = (res.get("aggregates") or {}).get("metrics", {})
    if agg:
        print(f"Totals over {a.duration}:")
        for k in body["metrics"]:
            if k in agg:
                print(f"  {k:28} {agg[k]}")
    rows = res.get("items") or []
    if rows and body["dimensions"]:
        print(f"\nBreakdown by {', '.join(body['dimensions'])}: {len(rows)} rows (use --json for full data)")
        for r in rows[:50]:
            dims = " / ".join(str(x.get("display_value") or x.get("value")) for x in r.get("dimensions", []))
            m = r.get("metrics", {})
            print(f"  {dims:30} delivered={m.get('delivered_count','-')} opened={m.get('opened_count','-')} "
                  f"clicked={m.get('clicked_count','-')} failed={m.get('failed_count','-')}")


# ---------------------------------------------------------------- config shortcuts
def cmd_domains(a):
    res = request("GET", "/v4/domains", query=[("limit", "100")])
    for it in res.get("items", []):
        print(f"{it.get('name'):40} state={it.get('state'):10} type={it.get('type')}")


def cmd_domain_check(a):
    d = domain(a)
    res = request("PUT", f"/v4/domains/{d}/verify")
    dom = res.get("domain", {})
    print(f"{d}: state={dom.get('state')}")
    for group in ("sending_dns_records", "receiving_dns_records"):
        print(f"\n{group.replace('_', ' ')}:")
        for r in res.get(group, []):
            ok = "OK " if r.get("valid") == "valid" else "FIX"
            print(f"  [{ok}] {r.get('record_type'):5} {r.get('name','')}  ->  {r.get('value','')[:70]}")


def main():
    import signal
    if hasattr(signal, 'SIGPIPE'):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    load_env()
    p = argparse.ArgumentParser(description="Mailgun CLI. Every API endpoint is reachable via `call`.")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        s = sub.add_parser(name, help=help_)
        s.set_defaults(fn=fn)
        s.add_argument("--domain")
        return s

    s = add("call", cmd_call, "Call ANY endpoint: call GET /v3/routes")
    s.add_argument("method"); s.add_argument("path")
    s.add_argument("--query", "-q", action="append", help="key=value (repeatable)")
    s.add_argument("--form", "-f", action="append", help="key=value form field (repeatable)")
    s.add_argument("--file", action="append", help="field=path to upload")
    s.add_argument("--json", help="raw JSON body")
    s.add_argument("--yes", action="store_true", help="confirm DELETE")

    s = sub.add_parser("find", help="Search the endpoint index: find suppress bounce")
    s.set_defaults(fn=cmd_find); s.add_argument("words", nargs="+")
    s = sub.add_parser("describe", help='Show params: describe "POST /v3/routes"')
    s.set_defaults(fn=cmd_describe); s.add_argument("op")

    s = add("send", cmd_send, "Send an email")
    s.add_argument("--from", dest="sender"); s.add_argument("--to", action="append", required=True)
    s.add_argument("--cc", action="append"); s.add_argument("--bcc", action="append")
    s.add_argument("--subject"); s.add_argument("--text"); s.add_argument("--html", help="HTML or @file.html")
    s.add_argument("--template"); s.add_argument("--var", action="append", help="template var key=value")
    s.add_argument("--attach", action="append"); s.add_argument("--inline", action="append")
    s.add_argument("--tag", action="append"); s.add_argument("--deliver-at", help="RFC 2822 date to schedule")
    s.add_argument("--reply-to"); s.add_argument("--header", action="append", help="Name=value")
    s.add_argument("--data", action="append", help="custom v: variable key=value")
    s.add_argument("--opt", action="append", help="any raw field, e.g. o:tracking=no")
    s.add_argument("--test", action="store_true", help="test mode: accepted but not delivered")

    s = add("inbox-setup", cmd_inbox_setup, "Create a route that stores inbound mail (so `inbox` can read it)")
    s.add_argument("--expression"); s.add_argument("--priority", type=int, default=10)
    s.add_argument("--description"); s.add_argument("--notify", help="URL to POST each message to")
    s.add_argument("--forward", help="also forward to this address/URL")
    s = add("inbox", cmd_inbox, "List inbound messages stored in the last N hours (kept ~3 days)")
    s.add_argument("--hours", type=int, default=72); s.add_argument("--limit", type=int, default=50)
    s.add_argument("--json", dest="json_out", action="store_true")
    s = add("read", cmd_read, "Read a stored message by storage URL or key")
    s.add_argument("ref"); s.add_argument("--full", action="store_true"); s.add_argument("--mime", action="store_true")
    s = add("attachment", cmd_attachment, "Download an attachment URL")
    s.add_argument("url"); s.add_argument("out")

    s = add("logs", cmd_logs, "Event log report (delivered, failed, opened...)")
    s.add_argument("--duration", default="1d"); s.add_argument("--event", action="append")
    s.add_argument("--recipient"); s.add_argument("--message-id"); s.add_argument("--tag")
    s.add_argument("--limit", type=int, default=50); s.add_argument("--json", dest="json_out", action="store_true")
    s = add("metrics", cmd_metrics, "Statistics: totals and breakdowns")
    s.add_argument("--duration", default="7d"); s.add_argument("--resolution", default="day")
    s.add_argument("--metric", action="append"); s.add_argument("--dimension", action="append",
                   help="time, domain, tag, recipient_provider, country, device, ip, ...")
    s.add_argument("--tag"); s.add_argument("--json", dest="json_out", action="store_true")

    add("domains", cmd_domains, "List domains")
    add("domain-check", cmd_domain_check, "Verify DNS for a domain and show what to fix")

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
