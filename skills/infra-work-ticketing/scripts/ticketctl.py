#!/usr/bin/env python3
"""
ticketctl - log infrastructure work to Zoho ServiceDesk Plus Cloud or Jira Cloud.

Standard library only. Works identically on Windows (PowerShell/cmd) and
Linux/macOS. Run `python ticketctl.py --help` or `... <command> --help`.

Design notes for anyone reading or extending this:
  * Every write command supports --dry-run, which prints the exact HTTP request
    that would be sent. Use it whenever you are unsure - it makes no network
    calls and needs no credentials.
  * Long text always comes from a file (--body-file) or stdin (--body-file -).
    Passing multi-line text as a shell argument is the single biggest source of
    cross-platform quoting pain, so we avoid it.
  * If a write fails for any reason, the payload is appended to a local pending
    queue instead of being lost. `ticketctl.py retry` flushes it.
  * Everything written is also appended to a local worklog so there is a record
    even when the service desk is unreachable.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.0.0"
USER_AGENT = f"ticketctl/{VERSION}"
HTTP_TIMEOUT = 45

# --------------------------------------------------------------------------
# paths
# --------------------------------------------------------------------------


def config_candidates() -> list[Path]:
    override = os.environ.get("INFRA_TICKET_CONFIG")
    if override:
        return [Path(override).expanduser()]
    out = [Path.cwd() / ".infra-ticket" / "config.json"]
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            out.append(Path(appdata) / "infra-ticket" / "config.json")
    out.append(Path.home() / ".config" / "infra-ticket" / "config.json")
    return out


def default_config_path() -> Path:
    override = os.environ.get("INFRA_TICKET_CONFIG")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "infra-ticket" / "config.json"


def state_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    d = base / "infra-ticket"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_private(path: Path, text: str) -> None:
    """Write a file and make it user-only where the OS supports it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if os.name != "nt":
        try:
            path.chmod(0o600)
        except OSError:
            pass


# --------------------------------------------------------------------------
# small utilities
# --------------------------------------------------------------------------


class TicketError(Exception):
    """Anything the user needs to read and act on."""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def deep_get(d, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur if cur is not None else default


def first_nonempty(*vals):
    for v in vals:
        if v not in (None, "", [], {}):
            return v
    return None


def split_list(value: str | None, whitespace: bool = False) -> list[str]:
    """Split a comma/semicolon list. Labels and component names may contain
    spaces, so whitespace is only a separator when the caller opts in (email
    addresses, which never contain spaces)."""
    if not value:
        return []
    pattern = r"[,;\s]+" if whitespace else r"[,;\n]+"
    parts = re.split(pattern, value.strip())
    return [p.strip() for p in parts if p.strip()]


def read_body(args) -> str:
    """Body text from --body-file (use '-' for stdin) or --body."""
    if getattr(args, "body_file", None):
        if args.body_file == "-":
            return sys.stdin.read()
        p = Path(args.body_file).expanduser()
        if not p.exists():
            raise TicketError(f"body file not found: {p}")
        return p.read_text(encoding="utf-8")
    if getattr(args, "body", None):
        return args.body
    raise TicketError("no body supplied - pass --body-file FILE (or - for stdin) or --body TEXT")


# --------------------------------------------------------------------------
# secret redaction
# --------------------------------------------------------------------------

REDACT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)),
    ("aws access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("aws secret access key", re.compile(r"(?i)\baws_secret_access_key\b\s*[:=]\s*\S+")),
    ("bearer token", re.compile(r"(?i)\b(?:authorization:\s*)?bearer\s+[A-Za-z0-9._\-]{20,}")),
    ("zoho oauth token", re.compile(r"\b1000\.[0-9a-f]{20,}\.[0-9a-f]{20,}\b")),
    ("atlassian api token", re.compile(r"\bATATT[A-Za-z0-9_\-=]{20,}\b")),
    ("github token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
    ("password assignment", re.compile(
        r"(?i)\b(?:password|passwd|pwd|secret|client_secret|api[_-]?key|apikey|token|access[_-]?key)\b"
        r"\s*[:=]\s*(?:\"[^\"\n]{3,}\"|'[^'\n]{3,}'|[^\s,;'\"]{3,})")),
    ("connection string credentials", re.compile(
        r"(?i)\b(?:Password|Pwd)\s*=\s*[^;\r\n]{3,}(?=;|$)")),
    ("url embedded credentials", re.compile(r"(?i)\b[a-z][a-z0-9+.\-]*://[^\s/:@]+:[^\s/@]+@")),
]


def redact_text(text: str) -> tuple[str, list[str]]:
    """Strip things that must never land in a ticket. Returns (clean, hits)."""
    hits: list[str] = []
    out = text
    for label, pattern in REDACT_PATTERNS:
        new, n = pattern.subn("[REDACTED]", out)
        if n:
            hits.append(f"{label} x{n}")
            out = new
    return out, hits


# --------------------------------------------------------------------------
# http
# --------------------------------------------------------------------------


def http_request(method, url, headers=None, body=None, params=None, timeout=HTTP_TIMEOUT):
    """Return (status, text). Raises TicketError on transport failure."""
    if params:
        sep = "&" if "?" in url else "?"
        url = url + sep + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method=method.upper(), data=body)
    req.add_header("User-Agent", USER_AGENT)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except urllib.error.URLError as e:
        raise TicketError(f"could not reach {urllib.parse.urlsplit(url).netloc}: {e.reason}") from e
    except TimeoutError as e:
        raise TicketError(f"request to {urllib.parse.urlsplit(url).netloc} timed out") from e


def parse_json(text, context="response"):
    try:
        return json.loads(text) if text.strip() else {}
    except json.JSONDecodeError:
        snippet = text[:400].replace("\n", " ")
        raise TicketError(f"{context} was not JSON: {snippet}") from None


def form_encode(mapping) -> bytes:
    return urllib.parse.urlencode(mapping).encode("utf-8")


# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------

CONFIG_TEMPLATE = {
    "provider": "zoho_sdp",
    "redact_secrets": True,
    # Routing metadata for the ServiceDesk Plus MCP connector. No credentials
    # belong here - the connector authenticates each person separately through
    # Claude Code. This block only records which transport to try first and
    # where to fall back when it refuses or is unauthenticated.
    "mcp": {
        "enabled": True,
        "prefer_mcp": True,
        "connector_name": "Solomon Service Desk Plus",
        "endpoint": "https://sdp-mcp.solomoninsight.com/mcp",
        "health_url": "https://sdp-mcp.solomoninsight.com/health",
        "tool_prefix": "sdp_",
        "fallback_provider": "zoho_sdp",
        "scrub_before_write": True,
    },
    "zoho_sdp": {
        "base_url": "https://ithelpdesk.solomoninsight.com",
        "portal": "",
        "accounts_url": "https://accounts.zoho.com",
        "client_id": "",
        "client_secret": "",
        "refresh_token": "",
        "defaults": {
            "request_type": "Incident",
            "mode": "Web Form",
            "priority": "Medium",
            "urgency": "",
            "impact": "",
            "category": "",
            "subcategory": "",
            "group": "",
            "site": "",
            "template": "",
            "requester_email": "",
            "technician_email": "",
            "assign_self": True,
        },
    },
    "jira": {
        "site_url": "https://solomondevteam.atlassian.net",
        "auth_method": "api_token",
        "email": "",
        "api_token": "",
        "oauth": {
            "client_id": "",
            "client_secret": "",
            "refresh_token": "",
            "cloud_id": "",
            "redirect_uri": "http://localhost:8723/callback",
        },
        "defaults": {
            "project_key": "",
            "issue_type": "Task",
            "priority": "",
            "labels": ["infrastructure"],
            "components": [],
            "assign_self": True,
        },
    },
}

ENV_OVERRIDES = {
    ("zoho_sdp", "client_id"): "ZOHO_SDP_CLIENT_ID",
    ("zoho_sdp", "client_secret"): "ZOHO_SDP_CLIENT_SECRET",
    ("zoho_sdp", "refresh_token"): "ZOHO_SDP_REFRESH_TOKEN",
    ("zoho_sdp", "portal"): "ZOHO_SDP_PORTAL",
    ("zoho_sdp", "base_url"): "ZOHO_SDP_BASE_URL",
    ("jira", "email"): "JIRA_EMAIL",
    ("jira", "api_token"): "JIRA_API_TOKEN",
    ("jira", "site_url"): "JIRA_SITE_URL",
}

ENV_OVERRIDES_NESTED = {
    ("jira", "oauth", "client_id"): "JIRA_OAUTH_CLIENT_ID",
    ("jira", "oauth", "client_secret"): "JIRA_OAUTH_CLIENT_SECRET",
    ("jira", "oauth", "refresh_token"): "JIRA_OAUTH_REFRESH_TOKEN",
    ("jira", "oauth", "cloud_id"): "JIRA_CLOUD_ID",
}


def as_bool(value, default=False):
    """Coerce a config or environment value to a real bool."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def merge_defaults(template, actual):
    """Fill in any key the user's config file is missing."""
    if not isinstance(actual, dict):
        return template
    out = dict(actual)
    for k, v in template.items():
        if k not in out:
            out[k] = v
        elif isinstance(v, dict):
            out[k] = merge_defaults(v, out[k])
    return out


def load_config(path_hint=None):
    paths = [Path(path_hint).expanduser()] if path_hint else config_candidates()
    for p in paths:
        if p.is_file():
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                raise TicketError(f"config at {p} is not valid JSON: {e}") from None
            cfg = merge_defaults(CONFIG_TEMPLATE, raw)
            cfg["_path"] = str(p)
            apply_env(cfg)
            return cfg
    looked = "\n  ".join(str(p) for p in paths)
    raise TicketError(
        "no config file found. Looked in:\n  " + looked +
        "\n\nRun:  python ticketctl.py init\nthen edit the file it creates."
    )


def apply_env(cfg):
    for (section, key), env in ENV_OVERRIDES.items():
        val = os.environ.get(env)
        if val:
            cfg.setdefault(section, {})[key] = val
    for (section, sub, key), env in ENV_OVERRIDES_NESTED.items():
        val = os.environ.get(env)
        if val:
            cfg.setdefault(section, {}).setdefault(sub, {})[key] = val
    prov = os.environ.get("INFRA_TICKET_PROVIDER")
    if prov:
        cfg["provider"] = prov
    # Booleans need explicit coercion: routing them through ENV_OVERRIDES would
    # make INFRA_TICKET_PREFER_MCP=false the truthy string "false".
    prefer = os.environ.get("INFRA_TICKET_PREFER_MCP")
    if prefer is not None and prefer.strip():
        cfg.setdefault("mcp", {})["prefer_mcp"] = as_bool(prefer)
    endpoint = os.environ.get("INFRA_TICKET_MCP_ENDPOINT")
    if endpoint:
        cfg.setdefault("mcp", {})["endpoint"] = endpoint


def save_config(cfg):
    """Persist config, dropping the runtime-only keys."""
    path = Path(cfg["_path"])
    clean = {k: v for k, v in cfg.items() if not k.startswith("_")}
    write_private(path, json.dumps(clean, indent=2) + "\n")


# --------------------------------------------------------------------------
# token cache
# --------------------------------------------------------------------------


def token_cache_path() -> Path:
    return state_dir() / "tokens.json"


def cache_get(key):
    p = token_cache_path()
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    entry = data.get(key)
    if not entry:
        return None
    if entry.get("expires_at", 0) - 90 < time.time():
        return None
    return entry.get("access_token")


def cache_put(key, access_token, expires_in):
    p = token_cache_path()
    data = {}
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    data[key] = {"access_token": access_token, "expires_at": time.time() + float(expires_in or 3600)}
    write_private(p, json.dumps(data, indent=2) + "\n")


# --------------------------------------------------------------------------
# text rendering
# --------------------------------------------------------------------------


def text_to_html(text: str) -> str:
    """Plain/markdown-ish text -> the simple HTML ServiceDesk Plus expects."""
    out: list[str] = []
    in_code = False
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.strip().startswith("```"):
            out.append("</pre>" if in_code else "<pre>")
            in_code = not in_code
            continue
        if in_code:
            out.append(html.escape(line))
            continue
        stripped = line.strip()
        if not stripped:
            out.append("<br>")
        elif stripped.startswith("### "):
            out.append(f"<b>{html.escape(stripped[4:])}</b><br>")
        elif stripped.startswith("## "):
            out.append(f"<b>{html.escape(stripped[3:])}</b><br>")
        elif stripped.startswith("# "):
            out.append(f"<b>{html.escape(stripped[2:])}</b><br>")
        elif stripped.startswith(("- ", "* ")):
            out.append(f"&bull; {html.escape(stripped[2:])}<br>")
        else:
            out.append(f"{html.escape(line)}<br>")
    if in_code:
        out.append("</pre>")
    return "\n".join(out)


def _adf_text_nodes(line: str) -> list[dict]:
    if not line:
        return []
    return [{"type": "text", "text": line}]


def text_to_adf(text: str) -> dict:
    """Plain/markdown-ish text -> Atlassian Document Format for Jira v3.

    Deliberately conservative: paragraphs, headings, bullet lists and code
    blocks only. Invalid ADF is rejected with an opaque 400, so simple wins.
    """
    content: list[dict] = []
    lines = text.replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            lang = stripped[3:].strip() or None
            i += 1
            buf: list[str] = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1  # closing fence
            node = {"type": "codeBlock", "content": _adf_text_nodes("\n".join(buf))}
            if lang:
                node["attrs"] = {"language": lang}
            content.append(node)
            continue

        if stripped.startswith(("- ", "* ")):
            items = []
            while i < len(lines) and lines[i].strip().startswith(("- ", "* ")):
                item_text = lines[i].strip()[2:]
                items.append({
                    "type": "listItem",
                    "content": [{"type": "paragraph", "content": _adf_text_nodes(item_text)}],
                })
                i += 1
            content.append({"type": "bulletList", "content": items})
            continue

        m = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if m:
            content.append({
                "type": "heading",
                "attrs": {"level": min(len(m.group(1)) + 1, 6)},
                "content": _adf_text_nodes(m.group(2)),
            })
            i += 1
            continue

        if not stripped:
            i += 1
            continue

        para: list[str] = []
        while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith(("```", "- ", "* ", "#")):
            para.append(lines[i].strip())
            i += 1
        content.append({"type": "paragraph", "content": _adf_text_nodes(" ".join(para))})

    if not content:
        content = [{"type": "paragraph", "content": []}]
    return {"type": "doc", "version": 1, "content": content}


def adf_to_text(node) -> str:
    """Best-effort flatten of ADF for display."""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(adf_to_text(n) for n in node)
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return node.get("text", "")
    inner = adf_to_text(node.get("content", []))
    if node.get("type") in ("paragraph", "heading", "codeBlock", "listItem"):
        return inner + "\n"
    return inner


def html_to_text(raw: str) -> str:
    if not raw:
        return ""
    txt = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    txt = re.sub(r"(?i)</(p|div|pre|li)>", "\n", txt)
    txt = re.sub(r"<[^>]+>", "", txt)
    return html.unescape(txt).strip()


# --------------------------------------------------------------------------
# local worklog + pending queue
# --------------------------------------------------------------------------


def worklog_append(record):
    path = state_dir() / "worklog.jsonl"
    record = dict(record)
    record.setdefault("at", now_iso())
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def pending_append(record):
    path = state_dir() / "pending.jsonl"
    record = dict(record)
    record.setdefault("queued_at", now_iso())
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    return path


def pending_load():
    path = state_dir() / "pending.jsonl"
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def pending_replace(records):
    path = state_dir() / "pending.jsonl"
    if not records:
        if path.is_file():
            path.unlink()
        return
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


# --------------------------------------------------------------------------
# provider: Zoho ServiceDesk Plus Cloud
# --------------------------------------------------------------------------

SDP_ACCEPT = "application/vnd.manageengine.sdp.v3+json"


class ZohoSDP:
    name = "zoho_sdp"
    label = "Zoho ServiceDesk Plus Cloud"

    def __init__(self, cfg):
        self.cfg = cfg
        self.sec = cfg.get("zoho_sdp", {})
        self.defaults = self.sec.get("defaults", {}) or {}
        self.base_url = (self.sec.get("base_url") or "").rstrip("/")
        self.portal = (self.sec.get("portal") or "").strip("/")
        self.accounts_url = (self.sec.get("accounts_url") or "https://accounts.zoho.com").rstrip("/")

    # -- config / auth ----------------------------------------------------
    def check_config(self):
        problems = []
        if not self.base_url:
            problems.append("zoho_sdp.base_url is empty")
        if not self.portal:
            problems.append("zoho_sdp.portal is empty (the portal name in your ServiceDesk Plus URL)")
        for k in ("client_id", "client_secret", "refresh_token"):
            if not self.sec.get(k):
                problems.append(f"zoho_sdp.{k} is empty")
        return problems

    def api_root(self):
        return f"{self.base_url}/app/{self.portal}/api/v3"

    def access_token(self):
        key = f"zoho:{self.sec.get('client_id','')[:16]}"
        cached = cache_get(key)
        if cached:
            return cached
        missing = [k for k in ("client_id", "client_secret", "refresh_token") if not self.sec.get(k)]
        if missing:
            raise TicketError(
                "Zoho credentials incomplete: missing " + ", ".join(missing) +
                ".\nSee references/setup-zoho-sdp.md, then run: python ticketctl.py zoho-token --code <grant-code>"
            )
        status, text = http_request(
            "POST", f"{self.accounts_url}/oauth/v2/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            body=form_encode({
                "refresh_token": self.sec["refresh_token"],
                "client_id": self.sec["client_id"],
                "client_secret": self.sec["client_secret"],
                "grant_type": "refresh_token",
            }),
        )
        data = parse_json(text, "Zoho token response")
        if status >= 400 or "access_token" not in data:
            raise TicketError(
                f"Zoho token refresh failed (HTTP {status}): {data.get('error', text[:300])}\n"
                "A refresh token is invalidated if you change scopes or revoke it; regenerate with "
                "`python ticketctl.py zoho-token --code <new grant code>`."
            )
        cache_put(key, data["access_token"], data.get("expires_in", 3600))
        return data["access_token"]

    def headers(self):
        return {
            "Accept": SDP_ACCEPT,
            "Authorization": f"Zoho-oauthtoken {self.access_token()}",
        }

    def call(self, method, path, input_data=None):
        url = f"{self.api_root()}{path}"
        headers = self.headers()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        if method.upper() == "GET":
            params = {"input_data": json.dumps(input_data)} if input_data else None
            status, text = http_request("GET", url, headers=headers, params=params)
        else:
            body = form_encode({"input_data": json.dumps(input_data or {})})
            status, text = http_request(method, url, headers=headers, body=body)
        data = parse_json(text, f"ServiceDesk Plus {method} {path}")
        rs = data.get("response_status")
        if isinstance(rs, list):
            rs = rs[0] if rs else {}
        if status >= 400 or (isinstance(rs, dict) and rs.get("status") == "failed"):
            msgs = []
            for m in (rs or {}).get("messages", []) or []:
                bit = m.get("message") or m.get("status_code")
                field = m.get("field")
                msgs.append(f"{field}: {bit}" if field else str(bit))
            detail = "; ".join(msgs) or text[:400]
            raise TicketError(f"ServiceDesk Plus rejected {method} {path} (HTTP {status}): {detail}")
        return data

    # -- helpers ----------------------------------------------------------
    def ticket_url(self, internal_id):
        return f"{self.base_url}/app/{self.portal}/ui/requests/{internal_id}/details"

    @staticmethod
    def _named(value):
        return {"name": value} if value else None

    def resolve(self, ref, offline=False):
        """Accept a display id, an internal id, or a pasted URL -> internal id."""
        ref = str(ref).strip()
        m = re.search(r"/requests/(\d+)", ref)
        if m:
            ref = m.group(1)
        ref = ref.lstrip("#")
        if not ref.isdigit():
            raise TicketError(f"'{ref}' does not look like a ServiceDesk Plus request id")
        if offline:
            # --dry-run promises no request and no credentials. Turning a display id
            # into an internal id needs both, so planning takes the id at face value:
            # the printed path is then only right if the caller passed an internal id.
            return ref, {}
        # Long ids are internal ids and work directly.
        try:
            data = self.call("GET", f"/requests/{ref}")
            req = data.get("request") or {}
            if req.get("id"):
                return req["id"], req
        except TicketError:
            pass
        # Otherwise treat it as the display id users see in the UI.
        data = self.call("GET", "/requests", {
            "list_info": {
                "row_count": 2,
                "start_index": 1,
                "search_criteria": [{"field": "display_id", "condition": "is", "values": [ref]}],
            }
        })
        rows = data.get("requests") or []
        if not rows:
            raise TicketError(f"no ServiceDesk Plus request found for id {ref}")
        return rows[0]["id"], rows[0]

    # -- operations -------------------------------------------------------
    def build_create(self, title, body, args):
        d = self.defaults
        req = {"subject": title[:250], "description": text_to_html(body)}

        for key, val in (
            ("request_type", first_nonempty(args.type, d.get("request_type"))),
            ("mode", d.get("mode")),
            ("priority", first_nonempty(args.priority, d.get("priority"))),
            ("urgency", d.get("urgency")),
            ("impact", d.get("impact")),
            ("category", first_nonempty(args.category, d.get("category"))),
            ("subcategory", first_nonempty(getattr(args, "subcategory", None), d.get("subcategory"))),
            ("group", first_nonempty(args.group, d.get("group"))),
            ("site", d.get("site")),
            ("template", d.get("template")),
        ):
            named = self._named(val)
            if named:
                req[key] = named

        if d.get("requester_email"):
            req["requester"] = {"email_id": d["requester_email"]}

        assign = d.get("assign_self", True) if args.assign_self is None else args.assign_self
        if assign and d.get("technician_email"):
            req["technician"] = {"email_id": d["technician_email"]}

        emails = split_list(args.email, whitespace=True)
        if emails:
            req["email_ids_to_notify"] = emails

        return {"path": "/requests", "method": "POST", "input_data": {"request": req}}

    def create(self, plan):
        data = self.call("POST", plan["path"], plan["input_data"])
        req = data.get("request") or {}
        internal = req.get("id")
        display = req.get("display_id") or internal
        result = {
            "id": str(internal),
            "ref": str(display),
            "url": self.ticket_url(internal),
            "title": req.get("subject", ""),
        }
        notified = plan["input_data"]["request"].get("email_ids_to_notify")
        if notified:
            result["emailed"] = notified
        return result

    def build_note(self, ref, body, args):
        internal, _ = self.resolve(ref, offline=getattr(args, "dry_run", False))
        emails = split_list(args.email, whitespace=True)
        note = {
            "description": text_to_html(body),
            "show_to_requester": bool(args.public or emails),
            "notify_technician": bool(emails) or bool(args.notify_technician),
            "mark_first_response": False,
            "add_to_linked_requests": False,
        }
        plan = {
            "path": f"/requests/{internal}/notes",
            "method": "POST",
            "input_data": {"request_note": note},
            "_internal_id": internal,
            "_extra_emails": emails,
        }
        return plan

    def note(self, plan):
        # Extra recipients on SDP work by adding them to the request's notify
        # list first; the note then reaches them.
        if plan.get("_extra_emails"):
            try:
                self.call("PUT", f"/requests/{plan['_internal_id']}",
                          {"request": {"email_ids_to_notify": plan["_extra_emails"]}})
            except TicketError as e:
                eprint(f"warning: could not add notify recipients ({e}); posting the note anyway")
        data = self.call("POST", plan["path"], plan["input_data"])
        note = data.get("request_note") or {}
        internal = plan["_internal_id"]
        return {
            "id": str(note.get("id", "")),
            "ref": str(deep_get(note, "request", "display_id", default=internal)),
            "url": self.ticket_url(internal),
        }

    def _edit_fields(self, args):
        """The subset of request fields both update and close can set."""
        req = {}
        for key, val in (
            ("request_type", args.type),
            ("priority", args.priority),
            ("category", args.category),
            ("subcategory", args.subcategory),
            ("group", args.group),
            ("urgency", args.urgency),
            ("impact", args.impact),
            ("status", args.status),
        ):
            named = self._named(val)
            if named:
                req[key] = named
        if args.title:
            req["subject"] = args.title[:250]
        if args.technician:
            req["technician"] = {"email_id": args.technician}
        if getattr(args, "update_reason", None):
            req["update_reason"] = args.update_reason[:250]
        return req

    def build_update(self, ref, body, args):
        internal, _ = self.resolve(ref, offline=getattr(args, "dry_run", False))
        req = self._edit_fields(args)
        if body:
            # An update carries a resolution, not a note: notes have their own verb.
            req["resolution"] = {"content": text_to_html(body)}
        if not req:
            raise TicketError(
                "nothing to update - pass at least one of --title, --status, --priority, "
                "--category, --subcategory, --group, --technician, --urgency, --impact, "
                "--type, or a resolution with --body/--body-file")
        return {"path": f"/requests/{internal}", "method": "PUT",
                "input_data": {"request": req}, "_internal_id": internal}

    def update(self, plan):
        data = self.call("PUT", plan["path"], plan["input_data"])
        req = data.get("request") or {}
        internal = plan["_internal_id"]
        return {
            "id": str(internal),
            "ref": str(req.get("display_id") or internal),
            "url": self.ticket_url(internal),
            "title": req.get("subject", ""),
            "fields": sorted(plan["input_data"]["request"].keys()),
        }

    def build_close(self, ref, body, args):
        # SDP Cloud v3 has no dedicated /close sub-resource: closing is the edit
        # endpoint with a terminal status plus closure_info. That means the desk's
        # mandatory-closure rules are enforced by the server, not by us - if the desk
        # requires a closure code or comment, this PUT is rejected and the error names
        # the field. The MCP sdp_close applies those rules itself; this does not.
        internal, _ = self.resolve(ref, offline=getattr(args, "dry_run", False))
        req = self._edit_fields(args)
        req["status"] = self._named(args.status or "Closed")
        closure = {}
        if body:
            closure["closure_comments"] = html_to_text(text_to_html(body))[:8000]
        if args.closure_code:
            closure["closure_code"] = {"name": args.closure_code}
        if args.requester_ack:
            closure["requester_ack_resolution"] = True
        if closure:
            req["closure_info"] = closure
        return {"path": f"/requests/{internal}", "method": "PUT",
                "input_data": {"request": req}, "_internal_id": internal,
                "_closing": True}

    def close(self, plan):
        result = self.update(plan)
        result["status"] = deep_get(plan, "input_data", "request", "status", "name", default="Closed")
        return result

    def get(self, ref):
        internal, req = self.resolve(ref)
        if not req.get("subject"):
            req = (self.call("GET", f"/requests/{internal}").get("request") or {})
        notes = []
        try:
            nd = self.call("GET", f"/requests/{internal}/notes", {
                "list_info": {"row_count": 10, "start_index": 1,
                              "sort_field": "created_time", "sort_order": "desc"}})
            for n in nd.get("notes") or []:
                notes.append({
                    "at": deep_get(n, "created_time", "display_value", default=""),
                    "by": deep_get(n, "created_by", "name", default=""),
                    "text": html_to_text(n.get("description", ""))[:400],
                })
        except TicketError as e:
            eprint(f"warning: could not read notes ({e})")
        return {
            "ref": str(req.get("display_id") or internal),
            "id": str(internal),
            "title": req.get("subject", ""),
            "status": deep_get(req, "status", "name", default=""),
            "assignee": deep_get(req, "technician", "name", default=""),
            "requester": deep_get(req, "requester", "name", default=""),
            "created": deep_get(req, "created_time", "display_value", default=""),
            "url": self.ticket_url(internal),
            "description": html_to_text(req.get("description", ""))[:1200],
            "notes": notes,
        }

    def search(self, text, limit, open_only, mine):
        criteria = []
        if text:
            criteria.append({"field": "subject", "condition": "contains", "value": text})
        if open_only:
            criteria.append({"field": "status.internal_name", "condition": "is not",
                             "values": ["Closed", "Resolved", "Cancelled"], "logical_operator": "AND"})
        if mine and self.defaults.get("technician_email"):
            criteria.append({"field": "technician.email_id", "condition": "is",
                             "values": [self.defaults["technician_email"]], "logical_operator": "AND"})
        list_info = {"row_count": limit, "start_index": 1,
                     "sort_field": "last_updated_time", "sort_order": "desc"}
        if criteria:
            list_info["search_criteria"] = criteria
        data = self.call("GET", "/requests", {"list_info": list_info})
        out = []
        for r in data.get("requests") or []:
            out.append({
                "ref": str(r.get("display_id") or r.get("id")),
                "id": str(r.get("id")),
                "title": r.get("subject", ""),
                "status": deep_get(r, "status", "name", default=""),
                "assignee": deep_get(r, "technician", "name", default=""),
                "url": self.ticket_url(r.get("id")),
            })
        return out

    def notify(self, ref, subject, body, recipients):
        internal, _ = self.resolve(ref)
        if recipients:
            self.call("PUT", f"/requests/{internal}",
                      {"request": {"email_ids_to_notify": recipients}})
        note_body = (f"## {subject}\n\n" if subject else "") + body
        self.call("POST", f"/requests/{internal}/notes", {"request_note": {
            "description": text_to_html(note_body),
            "show_to_requester": True,
            "notify_technician": True,
            "mark_first_response": False,
            "add_to_linked_requests": False,
        }})
        return {"ref": str(ref), "id": str(internal), "url": self.ticket_url(internal),
                "recipients": recipients}

    def whoami(self):
        problems = self.check_config()
        if problems:
            raise TicketError("config incomplete:\n  - " + "\n  - ".join(problems))
        data = self.call("GET", "/requests", {"list_info": {"row_count": 1, "start_index": 1}})
        count = len(data.get("requests") or [])
        return (f"authenticated against {self.api_root()} "
                f"(read check returned {count} request row(s))")


# --------------------------------------------------------------------------
# provider: Jira Cloud
# --------------------------------------------------------------------------


class Jira:
    name = "jira"
    label = "Jira Cloud"

    AUTH_URL = "https://auth.atlassian.com/authorize"
    TOKEN_URL = "https://auth.atlassian.com/oauth/token"
    RESOURCES_URL = "https://api.atlassian.com/oauth/token/accessible-resources"
    SCOPES = "read:jira-work write:jira-work read:jira-user offline_access"

    def __init__(self, cfg):
        self.cfg = cfg
        self.sec = cfg.get("jira", {})
        self.defaults = self.sec.get("defaults", {}) or {}
        self.oauth = self.sec.get("oauth", {}) or {}
        self.site_url = (self.sec.get("site_url") or "").rstrip("/")
        self.auth_method = (self.sec.get("auth_method") or "api_token").lower()
        self._self_account_id = None

    # -- config / auth ----------------------------------------------------
    def check_config(self):
        problems = []
        if not self.site_url:
            problems.append("jira.site_url is empty")
        if self.auth_method == "api_token":
            if not self.sec.get("email"):
                problems.append("jira.email is empty (the Atlassian account the token belongs to)")
            if not self.sec.get("api_token"):
                problems.append("jira.api_token is empty")
        elif self.auth_method == "oauth":
            for k in ("client_id", "client_secret", "refresh_token"):
                if not self.oauth.get(k):
                    problems.append(f"jira.oauth.{k} is empty")
        else:
            problems.append(f"jira.auth_method '{self.auth_method}' is not one of: api_token, oauth")
        if not self.defaults.get("project_key"):
            problems.append("jira.defaults.project_key is empty (e.g. OPS) - needed to create issues")
        return problems

    def access_token(self):
        key = f"jira:{self.oauth.get('client_id','')[:16]}"
        cached = cache_get(key)
        if cached:
            return cached
        missing = [k for k in ("client_id", "client_secret", "refresh_token") if not self.oauth.get(k)]
        if missing:
            raise TicketError(
                "Jira OAuth credentials incomplete: missing " + ", ".join(missing) +
                ".\nSee references/setup-jira.md, or switch jira.auth_method to \"api_token\"."
            )
        status, text = http_request(
            "POST", self.TOKEN_URL,
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "grant_type": "refresh_token",
                "client_id": self.oauth["client_id"],
                "client_secret": self.oauth["client_secret"],
                "refresh_token": self.oauth["refresh_token"],
            }).encode(),
        )
        data = parse_json(text, "Jira token response")
        if status >= 400 or "access_token" not in data:
            raise TicketError(
                f"Jira token refresh failed (HTTP {status}): {data.get('error_description') or text[:300]}\n"
                "Atlassian rotates refresh tokens: each refresh returns a new one and the old one dies. "
                "Re-run `python ticketctl.py jira-auth-url` and `jira-token --code ...` to re-link."
            )
        # Rotating refresh tokens: persist the new one immediately or the next
        # run will fail with an opaque invalid_grant.
        if data.get("refresh_token") and data["refresh_token"] != self.oauth.get("refresh_token"):
            self.oauth["refresh_token"] = data["refresh_token"]
            self.cfg.setdefault("jira", {}).setdefault("oauth", {})["refresh_token"] = data["refresh_token"]
            try:
                save_config(self.cfg)
            except OSError as e:
                eprint(f"warning: could not persist rotated refresh token: {e}")
        cache_put(key, data["access_token"], data.get("expires_in", 3600))
        return data["access_token"]

    def cloud_id(self):
        cid = self.oauth.get("cloud_id")
        if cid:
            return cid
        status, text = http_request("GET", self.RESOURCES_URL, headers={
            "Authorization": f"Bearer {self.access_token()}", "Accept": "application/json"})
        rows = parse_json(text, "accessible-resources")
        if status >= 400 or not isinstance(rows, list) or not rows:
            raise TicketError(f"could not list accessible Atlassian sites (HTTP {status}): {text[:300]}")
        host = urllib.parse.urlsplit(self.site_url).netloc
        for r in rows:
            if urllib.parse.urlsplit(r.get("url", "")).netloc == host:
                return r["id"]
        names = ", ".join(r.get("url", "?") for r in rows)
        raise TicketError(f"{self.site_url} is not among the sites this token can access ({names})")

    def api_root(self):
        if self.auth_method == "oauth":
            return f"https://api.atlassian.com/ex/jira/{self.cloud_id()}/rest/api/3"
        return f"{self.site_url}/rest/api/3"

    def headers(self):
        h = {"Accept": "application/json"}
        if self.auth_method == "oauth":
            h["Authorization"] = f"Bearer {self.access_token()}"
        else:
            email = self.sec.get("email", "")
            token = self.sec.get("api_token", "")
            if not email or not token:
                raise TicketError("jira.email and jira.api_token are both required for api_token auth")
            blob = base64.b64encode(f"{email}:{token}".encode()).decode()
            h["Authorization"] = f"Basic {blob}"
        return h

    def call(self, method, path, payload=None, params=None):
        url = f"{self.api_root()}{path}"
        headers = self.headers()
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode()
        status, text = http_request(method, url, headers=headers, body=body, params=params)
        if status == 401:
            raise TicketError(
                f"Jira returned 401 for {method} {path}. For api_token auth this usually means the "
                "token expired or jira.email does not match the token owner; Atlassian API tokens now "
                "carry an expiry date. Check https://id.atlassian.com/manage-profile/security/api-tokens"
            )
        if status == 403:
            raise TicketError(f"Jira returned 403 for {method} {path} - the account lacks permission "
                              f"in that project. Response: {text[:300]}")
        if status >= 400:
            data = parse_json(text, f"Jira {method} {path}") if text.strip().startswith("{") else {}
            msgs = data.get("errorMessages") or []
            fields = data.get("errors") or {}
            detail = "; ".join(list(msgs) + [f"{k}: {v}" for k, v in fields.items()]) or text[:400]
            raise TicketError(f"Jira rejected {method} {path} (HTTP {status}): {detail}")
        return parse_json(text, f"Jira {method} {path}") if text.strip() else {}

    # -- helpers ----------------------------------------------------------
    def ticket_url(self, key):
        return f"{self.site_url}/browse/{key}"

    def self_account_id(self):
        if self._self_account_id is None:
            me = self.call("GET", "/myself")
            self._self_account_id = me.get("accountId")
        return self._self_account_id

    def find_account_id(self, email):
        try:
            rows = self.call("GET", "/user/search", params={"query": email, "maxResults": 5})
        except TicketError as e:
            eprint(f"warning: user lookup for {email} failed ({e})")
            return None
        for r in rows if isinstance(rows, list) else []:
            if (r.get("emailAddress") or "").lower() == email.lower():
                return r.get("accountId")
        if isinstance(rows, list) and len(rows) == 1:
            return rows[0].get("accountId")
        return None

    def resolve(self, ref):
        ref = str(ref).strip()
        m = re.search(r"/browse/([A-Za-z][A-Za-z0-9_]*-\d+)", ref)
        if m:
            return m.group(1).upper()
        ref = ref.lstrip("#").upper()
        if re.fullmatch(r"[A-Z][A-Z0-9_]*-\d+", ref):
            return ref
        if ref.isdigit():
            key = self.defaults.get("project_key", "")
            if key:
                return f"{key.upper()}-{ref}"
        raise TicketError(f"'{ref}' does not look like a Jira issue key (expected e.g. OPS-123)")

    # -- operations -------------------------------------------------------
    def build_create(self, title, body, args):
        d = self.defaults
        project = (args.project or d.get("project_key") or "").upper()
        if not project:
            raise TicketError("no Jira project key - pass --project KEY or set jira.defaults.project_key")
        fields = {
            "project": {"key": project},
            "summary": title[:255],
            "description": text_to_adf(body),
            "issuetype": {"name": first_nonempty(args.type, d.get("issue_type"), "Task")},
        }
        priority = first_nonempty(args.priority, d.get("priority"))
        if priority:
            fields["priority"] = {"name": priority}
        labels = list(d.get("labels") or []) + split_list(args.labels)
        if labels:
            # Jira rejects labels containing spaces.
            fields["labels"] = sorted({l.replace(" ", "-") for l in labels})
        components = list(d.get("components") or []) + split_list(getattr(args, "components", None))
        if components:
            fields["components"] = [{"name": c} for c in dict.fromkeys(components)]
        return {"path": "/issue", "method": "POST", "payload": {"fields": fields},
                "_assign_self": d.get("assign_self", True) if args.assign_self is None else args.assign_self,
                "_email": split_list(args.email, whitespace=True), "_summary": title}

    def create(self, plan):
        if plan.get("_assign_self"):
            acct = self.self_account_id()
            if acct:
                plan["payload"]["fields"]["assignee"] = {"accountId": acct}
        data = self.call("POST", plan["path"], plan["payload"])
        key = data.get("key")
        result = {"id": data.get("id", ""), "ref": key, "url": self.ticket_url(key),
                  "title": plan.get("_summary", "")}
        if plan.get("_email"):
            try:
                self.notify(key, f"[{key}] {plan.get('_summary','')}"[:255],
                            f"A ticket was opened for infrastructure work: {self.ticket_url(key)}",
                            plan["_email"])
                result["emailed"] = plan["_email"]
            except TicketError as e:
                eprint(f"warning: ticket created but email notification failed: {e}")
        return result

    def build_note(self, ref, body, args):
        key = self.resolve(ref)
        return {"path": f"/issue/{key}/comment", "method": "POST",
                "payload": {"body": text_to_adf(body)},
                "_key": key, "_email": split_list(args.email, whitespace=True), "_body": body}

    def note(self, plan):
        data = self.call("POST", plan["path"], plan["payload"])
        key = plan["_key"]
        result = {"id": str(data.get("id", "")), "ref": key, "url": self.ticket_url(key)}
        if plan.get("_email"):
            try:
                self.notify(key, f"[{key}] work update", plan["_body"], plan["_email"])
                result["emailed"] = plan["_email"]
            except TicketError as e:
                eprint(f"warning: comment added but email notification failed: {e}")
        return result

    def _edit_fields(self, args):
        """Jira's nearest equivalents to the SDP fields update accepts."""
        fields = {}
        if args.title:
            fields["summary"] = args.title[:255]
        if args.priority:
            fields["priority"] = {"name": args.priority}
        if args.type:
            fields["issuetype"] = {"name": args.type}
        labels = split_list(args.labels)
        if labels:
            fields["labels"] = sorted({l.replace(" ", "-") for l in labels})
        # Jira has no category. Components are the closest analogue, so --category
        # maps onto one rather than being silently dropped - documented in SKILL.md
        # so nobody reads this as parity with ServiceDesk Plus.
        components = split_list(getattr(args, "components", None)) + split_list(args.category)
        if components:
            fields["components"] = [{"name": c} for c in dict.fromkeys(components)]
        return fields

    def build_update(self, ref, body, args):
        key = self.resolve(ref)
        fields = self._edit_fields(args)
        if body:
            fields["description"] = text_to_adf(body)
        if not fields and not args.technician:
            raise TicketError(
                "nothing to update - pass at least one of --title, --priority, --type, "
                "--labels, --components, --category, --technician, or a new description "
                "with --body/--body-file")
        return {"path": f"/issue/{key}", "method": "PUT", "payload": {"fields": fields},
                "_key": key, "_assignee_email": args.technician}

    def update(self, plan):
        if plan.get("_assignee_email"):
            acct = self.find_account_id(plan["_assignee_email"])
            if not acct:
                raise TicketError(f"no Jira account found for {plan['_assignee_email']}")
            plan["payload"]["fields"]["assignee"] = {"accountId": acct}
        self.call("PUT", plan["path"], plan["payload"])
        key = plan["_key"]
        return {"id": key, "ref": key, "url": self.ticket_url(key), "title": "",
                "fields": sorted(plan["payload"]["fields"].keys())}

    def build_close(self, ref, body, args):
        # The transition id is looked up at execution time, not here: ids differ per
        # workflow, and --dry-run has to work without credentials.
        key = self.resolve(ref)
        want = args.status or "Done"
        fields = self._edit_fields(args)
        # The payload shown by --dry-run mirrors what close() sends, with the id left
        # symbolic: it is read from the issue's own transition list at send time.
        preview = {"transition": {"id": f"<id of the '{want}' transition, looked up at send>"}}
        if fields:
            preview["fields"] = fields
        if body:
            preview["update"] = {"comment": [{"add": {"body": "<the body, as ADF>"}}]}
        return {"path": f"/issue/{key}/transitions", "method": "POST",
                "payload": preview,
                "_key": key, "_status": want, "_comment": body,
                "_fields": fields, "_closing": True}

    def close(self, plan):
        key = plan["_key"]
        want = plan["_status"]
        data = self.call("GET", f"/issue/{key}/transitions")
        available = data.get("transitions") or []
        match = None
        for t in available:
            if t.get("name", "").lower() == want.lower() or \
                    deep_get(t, "to", "name", default="").lower() == want.lower():
                match = t
                break
        if not match:
            names = ", ".join(sorted({t.get("name", "") for t in available})) or "(none)"
            raise TicketError(
                f"no transition to '{want}' is available on {key} from its current status. "
                f"Available: {names}")
        payload = {"transition": {"id": match["id"]}}
        if plan.get("_fields"):
            payload["fields"] = plan["_fields"]
        if plan.get("_comment"):
            payload["update"] = {"comment": [{"add": {"body": text_to_adf(plan["_comment"])}}]}
        self.call("POST", plan["path"], payload)
        return {"id": key, "ref": key, "url": self.ticket_url(key), "title": "",
                "status": deep_get(match, "to", "name", default=match.get("name", want)),
                "fields": sorted(plan.get("_fields") or {})}

    def get(self, ref):
        key = self.resolve(ref)
        data = self.call("GET", f"/issue/{key}", params={
            "fields": "summary,status,assignee,reporter,created,description,comment"})
        f = data.get("fields") or {}
        comments = []
        for c in deep_get(f, "comment", "comments", default=[])[-10:]:
            comments.append({
                "at": c.get("created", "")[:19],
                "by": deep_get(c, "author", "displayName", default=""),
                "text": adf_to_text(c.get("body")).strip()[:400],
            })
        return {
            "ref": key,
            "id": data.get("id", ""),
            "title": f.get("summary", ""),
            "status": deep_get(f, "status", "name", default=""),
            "assignee": deep_get(f, "assignee", "displayName", default="") or "unassigned",
            "requester": deep_get(f, "reporter", "displayName", default=""),
            "created": (f.get("created") or "")[:19],
            "url": self.ticket_url(key),
            "description": adf_to_text(f.get("description")).strip()[:1200],
            "notes": list(reversed(comments)),
        }

    def search(self, text, limit, open_only, mine):
        clauses = []
        project = self.defaults.get("project_key")
        if project:
            clauses.append(f'project = "{project}"')
        if text:
            safe = text.replace('"', '\\"')
            clauses.append(f'(summary ~ "{safe}" OR description ~ "{safe}")')
        if open_only:
            clauses.append("statusCategory != Done")
        if mine:
            clauses.append("assignee = currentUser()")
        jql = " AND ".join(clauses) if clauses else "order by updated desc"
        if "order by" not in jql.lower():
            jql += " ORDER BY updated DESC"
        data = self.call("POST", "/search/jql", {
            "jql": jql, "maxResults": limit, "fields": ["summary", "status", "assignee"]})
        out = []
        for issue in data.get("issues") or []:
            f = issue.get("fields") or {}
            out.append({
                "ref": issue.get("key"),
                "id": issue.get("id", ""),
                "title": f.get("summary", ""),
                "status": deep_get(f, "status", "name", default=""),
                "assignee": deep_get(f, "assignee", "displayName", default="") or "unassigned",
                "url": self.ticket_url(issue.get("key")),
            })
        return out

    def notify(self, ref, subject, body, recipients):
        key = self.resolve(ref)
        to = {"reporter": True, "watchers": True}
        users = []
        unresolved = []
        for email in recipients:
            acct = self.find_account_id(email)
            if acct:
                users.append({"accountId": acct})
            else:
                unresolved.append(email)
        if users:
            to["users"] = users
        if unresolved:
            eprint("warning: could not resolve these addresses to Atlassian accounts, so they were "
                   "not emailed: " + ", ".join(unresolved) +
                   "\n  Jira can only email people who have an account on the site. Add them as a "
                   "watcher, or ask an admin to grant 'Browse users and groups'.")
        payload = {"subject": subject[:255], "textBody": body[:5000],
                   "htmlBody": text_to_html(body)[:20000], "to": to}
        self.call("POST", f"/issue/{key}/notify", payload)
        return {"ref": key, "id": "", "url": self.ticket_url(key),
                "recipients": [u for u in recipients if u not in unresolved]}

    def whoami(self):
        problems = self.check_config()
        if problems:
            raise TicketError("config incomplete:\n  - " + "\n  - ".join(problems))
        me = self.call("GET", "/myself")
        name = me.get("displayName") or me.get("emailAddress") or "unknown"
        return (f"authenticated to {self.api_root()} as {name} "
                f"({me.get('accountId','no account id')}) via {self.auth_method}")


PROVIDERS = {"zoho_sdp": ZohoSDP, "jira": Jira}


def get_provider(cfg, override=None):
    name = (override or cfg.get("provider") or "").lower()
    aliases = {"zoho": "zoho_sdp", "sdp": "zoho_sdp", "servicedesk": "zoho_sdp",
               "servicedeskplus": "zoho_sdp", "atlassian": "jira"}
    name = aliases.get(name, name)
    if name not in PROVIDERS:
        raise TicketError(
            f"provider '{name or '(unset)'}' is not supported. "
            f"Set \"provider\" to one of: {', '.join(PROVIDERS)}")
    return PROVIDERS[name](cfg)


# --------------------------------------------------------------------------
# output helpers
# --------------------------------------------------------------------------


def emit(args, human, payload):
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2))
    else:
        print(human)


def show_plan(provider, plan):
    print(f"DRY RUN - nothing was sent to {provider.label}.")
    print(f"  {plan.get('method','POST')} {plan.get('path')}")
    doc = plan.get("input_data", plan.get("payload"))
    print(json.dumps(doc, indent=2))
    for k in ("_extra_emails", "_email"):
        if plan.get(k):
            print(f"  would also notify: {', '.join(plan[k])}")


def prepare_body(cfg, body, force_redact=None):
    do_redact = cfg.get("redact_secrets", True) if force_redact is None else force_redact
    if not do_redact:
        return body
    clean, hits = redact_text(body)
    if hits:
        eprint("NOTE: possible secrets were replaced with [REDACTED] before sending: "
               + ", ".join(hits))
        eprint("      Re-run with --no-redact if a match was a false positive.")
    return clean


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def cmd_init(args):
    path = Path(args.path).expanduser() if args.path else default_config_path()
    if path.exists() and not args.force:
        raise TicketError(f"{path} already exists. Pass --force to overwrite, or edit it in place.")
    template = json.loads(json.dumps(CONFIG_TEMPLATE))
    if args.provider:
        template["provider"] = args.provider
    write_private(path, json.dumps(template, indent=2) + "\n")
    print(f"Wrote config template to {path}")
    print("Next steps:")
    print("  1. Set \"provider\" to \"zoho_sdp\" or \"jira\".")
    print("  2. Fill in credentials - see references/setup-zoho-sdp.md or references/setup-jira.md.")
    print("  3. Run: python ticketctl.py doctor")
    if os.name == "nt":
        print("\nOn Windows this file is not permission-restricted automatically. Consider:")
        print(f'  icacls "{path}" /inheritance:r /grant:r "%USERNAME%:F"')
    return 0


def report_mcp_routing(cfg, probe=True):
    """Print how ticket writes should be routed, and optionally probe /health.

    ticketctl itself cannot call MCP tools; it owns the routing decision so that
    the skill and the script read it from one place.
    """
    mcp = cfg.get("mcp") or {}
    enabled = as_bool(mcp.get("enabled"), True)
    prefer = enabled and as_bool(mcp.get("prefer_mcp"), True)
    print("\nMCP routing")
    print(f"  connector : {mcp.get('connector_name') or '(unset)'}")
    print(f"  endpoint  : {mcp.get('endpoint') or '(unset)'}")
    print(f"  tools     : {mcp.get('tool_prefix') or 'sdp_'}*")
    print(f"  preferred : {'yes - try MCP first' if prefer else 'no - ticketctl is the primary path'}")
    print(f"  fallback  : ticketctl --provider {mcp.get('fallback_provider') or cfg.get('provider')}")
    scrub = "yes - redact-check --emit before every MCP write" \
        if as_bool(mcp.get("scrub_before_write"), True) else "no"
    print(f"  scrub     : {scrub}")
    health = mcp.get("health_url")
    if not (probe and enabled and health):
        return
    # Short timeout on purpose: HTTP_TIMEOUT would hang doctor for 45s if the
    # server is unreachable, and the probe is informational either way.
    try:
        status, body = http_request("GET", health, timeout=5)
        detail = body.strip().replace("\n", " ")[:200]
        print(f"  health    : HTTP {status} {detail}")
    except Exception as e:  # noqa: BLE001 - never let a probe fail doctor
        print(f"  health    : unreachable ({e}) - use ticketctl for now")


def cmd_doctor(args):
    cfg = load_config(args.config)
    print(f"config file : {cfg['_path']}")
    print(f"state dir   : {state_dir()}")
    print(f"provider    : {cfg.get('provider')}")
    report_mcp_routing(cfg, probe=not args.no_mcp_probe)
    provider = get_provider(cfg, args.provider)
    problems = provider.check_config()
    if problems:
        print("\nProblems found:")
        for p in problems:
            print(f"  - {p}")
        print("\nFix these, then run doctor again.")
        return 1
    print("config looks complete; testing the connection...")
    print("  " + provider.whoami())
    pend = pending_load()
    if pend:
        print(f"\n{len(pend)} queued write(s) waiting - run: python ticketctl.py retry")
    print("\nAll good.")
    return 0


def cmd_create(args):
    cfg = load_config(args.config)
    provider = get_provider(cfg, args.provider)
    body = prepare_body(cfg, read_body(args), False if args.no_redact else None)
    title = args.title.strip().replace("\n", " ")
    if not title:
        raise TicketError("--title is required and cannot be blank")
    plan = provider.build_create(title, body, args)
    if args.dry_run:
        show_plan(provider, plan)
        return 0
    try:
        result = provider.create(plan)
    except TicketError as e:
        queue = {"op": "create", "provider": provider.name, "title": title,
                 "body": body, "args": vars_for_queue(args), "error": str(e)}
        path = pending_append(queue)
        raise TicketError(f"{e}\n\nThe ticket text was saved to {path} - "
                          f"run `python ticketctl.py retry` once the problem is fixed.") from None
    worklog_append({"op": "create", "provider": provider.name, "ref": result["ref"],
                    "title": title, "url": result["url"]})
    extra = f"\nnotifying: {', '.join(result['emailed'])}" if result.get("emailed") else ""
    emit(args, f"Created {result['ref']}: {title}\n{result['url']}{extra}", result)
    return 0


def cmd_note(args):
    cfg = load_config(args.config)
    provider = get_provider(cfg, args.provider)
    body = prepare_body(cfg, read_body(args), False if args.no_redact else None)
    result, plan = _write_with_queue(
        args, provider, "note", body,
        lambda: provider.build_note(args.ticket, body, args), provider.note)
    if args.dry_run:
        show_plan(provider, plan)
        return 0
    worklog_append({"op": "note", "provider": provider.name, "ref": result["ref"],
                    "url": result["url"], "chars": len(body)})
    extra = f"  (emailed: {', '.join(result['emailed'])})" if result.get("emailed") else ""
    emit(args, f"Added note to {result['ref']}{extra}\n{result['url']}", result)
    return 0


def _write_with_queue(args, provider, op, body, build, run):
    """Plan and execute a ticket-scoped write, queueing the intent if either step fails.

    Building is inside the guarded region on purpose: turning '#40219' into an internal
    id is itself an API call, so a desk that is down fails during *planning*. Queueing
    only around the send would lose exactly the text the queue exists to protect.

    Returns (result, plan). On --dry-run, result is None and nothing is queued - a
    rehearsal that fails should say so, not leave a record behind to replay.
    """
    try:
        plan = build()
        if getattr(args, "dry_run", False):
            return None, plan
        return run(plan), plan
    except TicketError as e:
        if getattr(args, "dry_run", False):
            raise
        queue = {"op": op, "provider": provider.name, "ticket": args.ticket,
                 "body": body, "args": vars_for_queue(args), "error": str(e)}
        path = pending_append(queue)
        raise TicketError(f"{e}\n\nThe {op} was saved to {path} - "
                          f"run `python ticketctl.py retry` once the problem is fixed.") from None


def cmd_update(args):
    cfg = load_config(args.config)
    provider = get_provider(cfg, args.provider)
    raw = read_body(args) if (args.body or args.body_file) else ""
    body = prepare_body(cfg, raw, False if args.no_redact else None) if raw else ""
    result, plan = _write_with_queue(
        args, provider, "update", body,
        lambda: provider.build_update(args.ticket, body, args), provider.update)
    if args.dry_run:
        show_plan(provider, plan)
        return 0
    worklog_append({"op": "update", "provider": provider.name, "ref": result["ref"],
                    "url": result["url"], "fields": result.get("fields", [])})
    changed = ", ".join(result.get("fields") or []) or "nothing"
    emit(args, f"Updated {result['ref']} ({changed})\n{result['url']}", result)
    return 0


def cmd_close(args):
    cfg = load_config(args.config)
    provider = get_provider(cfg, args.provider)
    raw = read_body(args) if (args.body or args.body_file) else ""
    body = prepare_body(cfg, raw, False if args.no_redact else None) if raw else ""
    result, plan = _write_with_queue(
        args, provider, "close", body,
        lambda: provider.build_close(args.ticket, body, args), provider.close)
    if args.dry_run:
        show_plan(provider, plan)
        return 0
    worklog_append({"op": "close", "provider": provider.name, "ref": result["ref"],
                    "url": result["url"], "status": result.get("status", "")})
    emit(args, f"Closed {result['ref']} -> {result.get('status', 'Closed')}\n{result['url']}", result)
    return 0


def cmd_get(args):
    cfg = load_config(args.config)
    provider = get_provider(cfg, args.provider)
    info = provider.get(args.ticket)
    if args.json:
        print(json.dumps(info, indent=2))
        return 0
    print(f"{info['ref']}  {info['title']}")
    print(f"  status    : {info['status']}")
    print(f"  assignee  : {info['assignee']}")
    print(f"  requester : {info['requester']}")
    print(f"  created   : {info['created']}")
    print(f"  url       : {info['url']}")
    if info["description"]:
        print("\n--- description ---")
        print(info["description"])
    if info["notes"]:
        print("\n--- recent notes ---")
        for n in info["notes"]:
            print(f"[{n['at']}] {n['by']}: {n['text']}")
    return 0


def cmd_search(args):
    cfg = load_config(args.config)
    provider = get_provider(cfg, args.provider)
    rows = provider.search(args.text, args.limit, args.open_only, args.mine)
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    if not rows:
        print("No matching tickets.")
        return 0
    for r in rows:
        print(f"{r['ref']:<14} {r['status']:<14} {r['assignee']:<22} {r['title'][:70]}")
        print(f"{'':<14} {r['url']}")
    return 0


def cmd_notify(args):
    cfg = load_config(args.config)
    provider = get_provider(cfg, args.provider)
    body = prepare_body(cfg, read_body(args), False if args.no_redact else None)
    recipients = split_list(args.to, whitespace=True)
    if args.dry_run:
        print(f"DRY RUN - would email {', '.join(recipients) or '(default watchers)'} "
              f"about {args.ticket} via {provider.label}")
        print(f"subject: {args.subject}")
        print(body)
        return 0
    result = provider.notify(args.ticket, args.subject or f"Update on {args.ticket}", body, recipients)
    worklog_append({"op": "notify", "provider": provider.name, "ref": result["ref"],
                    "recipients": result.get("recipients", [])})
    emit(args, f"Notification sent for {result['ref']} "
               f"({', '.join(result.get('recipients') or ['watchers'])})", result)
    return 0


def cmd_worklog(args):
    path = state_dir() / "worklog.jsonl"
    if not path.is_file():
        print("No local worklog yet.")
        return 0
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = []
    for line in lines[-args.limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    for r in rows:
        print(f"{r.get('at','')}  {r.get('op',''):<7} {r.get('ref',''):<14} "
              f"{r.get('title') or r.get('url','')}")
    return 0


def cmd_retry(args):
    cfg = load_config(args.config)
    pend = pending_load()
    if not pend:
        print("Nothing queued.")
        return 0
    kept = []
    for rec in pend:
        provider = get_provider(cfg, rec.get("provider"))
        fake = FakeArgs(rec.get("args", {}))
        try:
            body = rec.get("body", "")
            if rec["op"] == "create":
                plan = provider.build_create(rec["title"], body, fake)
                result = provider.create(plan)
            elif rec["op"] == "note":
                plan = provider.build_note(rec["ticket"], body, fake)
                result = provider.note(plan)
            elif rec["op"] == "update":
                plan = provider.build_update(rec["ticket"], body, fake)
                result = provider.update(plan)
            elif rec["op"] == "close":
                plan = provider.build_close(rec["ticket"], body, fake)
                result = provider.close(plan)
            else:
                eprint(f"skipping unknown queued op {rec.get('op')!r}")
                kept.append(rec)
                continue
        except TicketError as e:
            eprint(f"still failing ({rec['op']}): {e}")
            kept.append(rec)
            continue
        worklog_append({"op": rec["op"], "provider": provider.name, "ref": result["ref"],
                        "url": result["url"], "replayed": True})
        print(f"replayed {rec['op']} -> {result['ref']}  {result['url']}")
    pending_replace(kept)
    print(f"{len(pend) - len(kept)} replayed, {len(kept)} still queued.")
    return 0 if not kept else 1


# The flags every builder may read. FakeArgs and vars_for_queue share this list so a
# flag added to one is never missing from the other on replay - a mismatch there
# silently drops a field from a retried write.
QUEUED_FLAGS = {
    "type": None, "priority": None, "category": None, "subcategory": None,
    "group": None, "project": None, "labels": None, "components": None,
    "email": None, "assign_self": None, "public": False, "notify_technician": False,
    "title": None, "status": None, "technician": None, "urgency": None,
    "impact": None, "update_reason": None, "closure_code": None,
    "requester_ack": False,
}


class FakeArgs:
    """Rehydrate the flags the builders read, for queue replay."""

    def __init__(self, data):
        for k, v in QUEUED_FLAGS.items():
            setattr(self, k, data.get(k, v))


def vars_for_queue(args):
    # Fall back to the catalog default, not None: a flag the current subcommand does
    # not define would otherwise be replayed as None where the builder expects False.
    return {k: getattr(args, k, default) for k, default in QUEUED_FLAGS.items()}


def cmd_zoho_token(args):
    cfg = load_config(args.config)
    sec = cfg.setdefault("zoho_sdp", {})
    client_id = args.client_id or sec.get("client_id")
    client_secret = args.client_secret or sec.get("client_secret")
    accounts = (args.accounts_url or sec.get("accounts_url") or "https://accounts.zoho.com").rstrip("/")
    if not client_id or not client_secret:
        raise TicketError("client id and secret required - put them in the config or pass "
                          "--client-id/--client-secret")
    status, text = http_request(
        "POST", f"{accounts}/oauth/v2/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=form_encode({
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": args.code.strip(),
            "redirect_uri": args.redirect_uri or "",
        }),
    )
    data = parse_json(text, "Zoho token exchange")
    if status >= 400 or "refresh_token" not in data:
        raise TicketError(
            f"exchange failed (HTTP {status}): {data.get('error') or text[:300]}\n"
            "Common causes: the grant code already expired (they last 3-10 minutes and are "
            "single use), the wrong data-centre accounts URL, or 'Generate Code' was run "
            "without the SDPOnDemand scopes."
        )
    sec["client_id"] = client_id
    sec["client_secret"] = client_secret
    sec["refresh_token"] = data["refresh_token"]
    sec["accounts_url"] = accounts
    save_config(cfg)
    print(f"Refresh token stored in {cfg['_path']}")
    if data.get("api_domain"):
        print(f"Zoho reports api_domain = {data['api_domain']} (informational; "
              f"ServiceDesk Plus calls use your zoho_sdp.base_url)")
    print("Run: python ticketctl.py doctor")
    return 0


def cmd_jira_auth_url(args):
    cfg = load_config(args.config)
    oauth = cfg.get("jira", {}).get("oauth", {}) or {}
    client_id = args.client_id or oauth.get("client_id")
    if not client_id:
        raise TicketError("set jira.oauth.client_id in the config (or pass --client-id) first")
    redirect = args.redirect_uri or oauth.get("redirect_uri") or "http://localhost:8723/callback"
    params = {
        "audience": "api.atlassian.com",
        "client_id": client_id,
        "scope": args.scopes or Jira.SCOPES,
        "redirect_uri": redirect,
        "state": base64.urlsafe_b64encode(os.urandom(12)).decode().rstrip("="),
        "response_type": "code",
        "prompt": "consent",
    }
    print(Jira.AUTH_URL + "?" + urllib.parse.urlencode(params))
    print("\nOpen that URL, approve, then copy the `code` query parameter from the address bar")
    print("you land on and run:  python ticketctl.py jira-token --code <code>")
    print(f"(the redirect URI above must exactly match the callback registered on the app: {redirect})")
    return 0


def cmd_jira_token(args):
    cfg = load_config(args.config)
    sec = cfg.setdefault("jira", {})
    oauth = sec.setdefault("oauth", {})
    client_id = args.client_id or oauth.get("client_id")
    client_secret = args.client_secret or oauth.get("client_secret")
    redirect = args.redirect_uri or oauth.get("redirect_uri") or "http://localhost:8723/callback"
    if not client_id or not client_secret:
        raise TicketError("jira.oauth.client_id and client_secret are required")
    status, text = http_request(
        "POST", Jira.TOKEN_URL,
        headers={"Content-Type": "application/json"},
        body=json.dumps({
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": args.code.strip(),
            "redirect_uri": redirect,
        }).encode(),
    )
    data = parse_json(text, "Jira token exchange")
    if status >= 400 or "access_token" not in data:
        raise TicketError(
            f"exchange failed (HTTP {status}): {data.get('error_description') or text[:300]}\n"
            "Authorization codes are single-use and short-lived, and redirect_uri must match "
            "the app registration exactly."
        )
    if "refresh_token" not in data:
        raise TicketError("Atlassian did not return a refresh token. Add `offline_access` to the "
                          "scopes in the authorize URL and try again.")
    oauth["client_id"] = client_id
    oauth["client_secret"] = client_secret
    oauth["refresh_token"] = data["refresh_token"]
    oauth["redirect_uri"] = redirect
    sec["auth_method"] = "oauth"
    # Resolve and cache the cloud id now so normal runs need one fewer call.
    cache_put(f"jira:{client_id[:16]}", data["access_token"], data.get("expires_in", 3600))
    try:
        oauth["cloud_id"] = Jira(cfg).cloud_id()
        print(f"cloud id resolved: {oauth['cloud_id']}")
    except TicketError as e:
        eprint(f"warning: could not resolve cloud id now ({e}); it will be looked up per run")
    save_config(cfg)
    print(f"Refresh token stored in {cfg['_path']}")
    print("Run: python ticketctl.py doctor")
    return 0


def cmd_redact_check(args):
    text = read_body(args)
    clean, hits = redact_text(text)

    # --emit puts the scrubbed body on stdout and NOTHING else, so it can be
    # piped or redirected. This is the path for writing through a client that
    # has no scrubber of its own -- the MCP server, for one. --show is for a
    # human reading the diff and interleaves headings that would corrupt a
    # redirected file.
    if args.emit:
        if hits:
            eprint("Found and masked: " + ", ".join(hits))
        sys.stdout.write(clean)
        if not clean.endswith("\n"):
            sys.stdout.write("\n")
        return 1 if hits and args.strict else 0

    if hits:
        print("Found and masked: " + ", ".join(hits))
    else:
        print("No obvious secrets found.")
    if args.show:
        print("\n--- text as it would be sent ---")
        print(clean)
    return 1 if hits and args.strict else 0


# --------------------------------------------------------------------------
# argument parsing
# --------------------------------------------------------------------------


def add_common(p):
    p.add_argument("--config", help="path to config.json (overrides discovery)")
    p.add_argument("--provider", help="override the configured provider: zoho_sdp or jira")
    p.add_argument("--json", action="store_true", help="machine-readable output")


def add_body_args(p):
    p.add_argument("--body-file", help="file holding the text; use - for stdin")
    p.add_argument("--body", help="short inline text (prefer --body-file for anything multi-line)")
    p.add_argument("--no-redact", action="store_true",
                   help="skip the secret scrubber (only if it flagged a false positive)")


def build_parser():
    p = argparse.ArgumentParser(
        prog="ticketctl.py",
        description="Log infrastructure work to Zoho ServiceDesk Plus Cloud or Jira Cloud.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Every write command accepts --dry-run, which prints the exact request "
               "without sending it or needing credentials.",
    )
    p.add_argument("--version", action="version", version=f"ticketctl {VERSION}")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("init", help="write a config template")
    s.add_argument("--path", help="where to write it")
    s.add_argument("--provider", choices=sorted(PROVIDERS), help="preselect the provider")
    s.add_argument("--force", action="store_true", help="overwrite an existing file")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("doctor", help="validate config and test authentication")
    s.add_argument("--no-mcp-probe", action="store_true",
                   help="skip the MCP connector health check")
    add_common(s)
    s.set_defaults(func=cmd_doctor)

    s = sub.add_parser("create", help="open a new ticket")
    add_common(s)
    add_body_args(s)
    s.add_argument("--title", required=True, help="one-line summary")
    s.add_argument("--type", help="request/issue type, e.g. Incident, Task, Change")
    s.add_argument("--priority", help="priority name as it appears in the tool")
    s.add_argument("--category", help="ServiceDesk Plus category (Jira: mapped to a component)")
    s.add_argument("--subcategory", help="ServiceDesk Plus subcategory")
    s.add_argument("--group", help="ServiceDesk Plus support group")
    s.add_argument("--project", help="Jira project key, e.g. OPS")
    s.add_argument("--labels", help="Jira labels, comma separated")
    s.add_argument("--components", help="Jira components, comma separated")
    s.add_argument("--email", help="addresses to notify, comma separated")
    s.add_argument("--assign-self", dest="assign_self", action="store_true", default=None,
                   help="assign the ticket to the authenticated user")
    s.add_argument("--no-assign-self", dest="assign_self", action="store_false",
                   help="leave the ticket unassigned")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_create)

    s = sub.add_parser("note", help="add a note/comment to an existing ticket")
    add_common(s)
    add_body_args(s)
    s.add_argument("--ticket", required=True, help="ticket id, key, or pasted URL")
    s.add_argument("--email", help="addresses to notify, comma separated")
    s.add_argument("--public", action="store_true",
                   help="ServiceDesk Plus: make the note visible to the requester")
    s.add_argument("--notify-technician", dest="notify_technician", action="store_true",
                   help="ServiceDesk Plus: notify the assigned technician")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_note)

    s = sub.add_parser("update", help="change fields on an existing ticket")
    add_common(s)
    add_body_args(s)
    s.add_argument("--ticket", required=True, help="ticket id, key, or pasted URL")
    s.add_argument("--title", help="new one-line summary")
    s.add_argument("--status", help="new status name, e.g. 'In Progress'")
    s.add_argument("--priority", help="priority name as it appears in the tool")
    s.add_argument("--category", help="ServiceDesk Plus category (Jira: mapped to a component)")
    s.add_argument("--subcategory", help="ServiceDesk Plus subcategory")
    s.add_argument("--group", help="ServiceDesk Plus support group")
    s.add_argument("--technician", help="email of the technician/assignee to hand it to")
    s.add_argument("--urgency", help="ServiceDesk Plus urgency")
    s.add_argument("--impact", help="ServiceDesk Plus impact")
    s.add_argument("--type", help="request/issue type, e.g. Incident, Task, Change")
    s.add_argument("--labels", help="Jira labels, comma separated (replaces the existing set)")
    s.add_argument("--components", help="Jira components, comma separated (replaces the existing set)")
    s.add_argument("--update-reason", dest="update_reason",
                   help="ServiceDesk Plus: why this edit was made (audit trail)")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_update)

    s = sub.add_parser("close", help="close a ticket, with a closure comment")
    add_common(s)
    add_body_args(s)
    s.add_argument("--ticket", required=True, help="ticket id, key, or pasted URL")
    s.add_argument("--status", help="terminal status to move to (SDP default 'Closed', "
                                    "Jira default the 'Done' transition)")
    s.add_argument("--closure-code", dest="closure_code",
                   help="ServiceDesk Plus closure code name, e.g. Success")
    s.add_argument("--requester-ack", dest="requester_ack", action="store_true",
                   help="ServiceDesk Plus: mark the resolution as acknowledged by the requester")
    s.add_argument("--title", help="also correct the summary while closing")
    s.add_argument("--priority", help="also set the priority while closing")
    s.add_argument("--category", help="also set the category while closing")
    s.add_argument("--subcategory", help="also set the subcategory while closing")
    s.add_argument("--group", help="also set the support group while closing")
    s.add_argument("--technician", help="also set the technician/assignee while closing")
    s.add_argument("--urgency", help="also set urgency while closing")
    s.add_argument("--impact", help="also set impact while closing")
    s.add_argument("--type", help="also set the request/issue type while closing")
    s.add_argument("--labels", help="Jira labels, comma separated")
    s.add_argument("--components", help="Jira components, comma separated")
    s.add_argument("--update-reason", dest="update_reason", help="ServiceDesk Plus audit note")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_close)

    s = sub.add_parser("get", help="show a ticket and its recent notes")
    add_common(s)
    s.add_argument("--ticket", required=True)
    s.set_defaults(func=cmd_get)

    s = sub.add_parser("search", help="find tickets (useful before creating a duplicate)")
    add_common(s)
    s.add_argument("--text", help="words to look for in the summary/description")
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--open-only", action="store_true", help="exclude closed/resolved")
    s.add_argument("--mine", action="store_true", help="only tickets assigned to me")
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("notify", help="send an email about a ticket")
    add_common(s)
    add_body_args(s)
    s.add_argument("--ticket", required=True)
    s.add_argument("--subject")
    s.add_argument("--to", help="addresses, comma separated")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_notify)

    s = sub.add_parser("worklog", help="show what this tool has logged locally")
    add_common(s)
    s.add_argument("--limit", type=int, default=25)
    s.set_defaults(func=cmd_worklog)

    s = sub.add_parser("retry", help="replay writes that failed earlier")
    add_common(s)
    s.set_defaults(func=cmd_retry)

    s = sub.add_parser("zoho-token", help="exchange a Zoho self-client grant code for a refresh token")
    add_common(s)
    s.add_argument("--code", required=True)
    s.add_argument("--client-id")
    s.add_argument("--client-secret")
    s.add_argument("--accounts-url", help="e.g. https://accounts.zoho.com (US) or .eu / .in")
    s.add_argument("--redirect-uri", default="")
    s.set_defaults(func=cmd_zoho_token)

    s = sub.add_parser("jira-auth-url", help="print the Atlassian OAuth consent URL")
    add_common(s)
    s.add_argument("--client-id")
    s.add_argument("--redirect-uri")
    s.add_argument("--scopes", help="space separated; must include offline_access")
    s.set_defaults(func=cmd_jira_auth_url)

    s = sub.add_parser("jira-token", help="exchange an Atlassian authorization code for a refresh token")
    add_common(s)
    s.add_argument("--code", required=True)
    s.add_argument("--client-id")
    s.add_argument("--client-secret")
    s.add_argument("--redirect-uri")
    s.set_defaults(func=cmd_jira_token)

    s = sub.add_parser("redact-check", help="preview the secret scrubber on some text")
    add_body_args(s)
    s.add_argument("--show", action="store_true", help="print the scrubbed text after a summary")
    s.add_argument("--emit", action="store_true",
                   help="print ONLY the scrubbed text to stdout, findings to stderr; for piping")
    s.add_argument("--strict", action="store_true", help="exit non-zero if anything was found")
    s.set_defaults(func=cmd_redact_check)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args) or 0
    except TicketError as e:
        eprint(f"error: {e}")
        return 2
    except KeyboardInterrupt:
        eprint("interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
