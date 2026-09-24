"""ci_detect.py - endpoint and staging-URL autodetection for `/gizmoduck:ci`.

Setup (`gizmoduck_ci.py detect`) and every endpoint-scan run (`gizmoduck_ci.py
endpoints`) call `detect(root, subdir)`. It reads files and nothing else: no
network, no subprocess, no writes. Sources, in the order they are consulted:

  1. `.crew/endpoints.json`                     crew's endpoint ledger
  2. OpenAPI / Swagger documents in the repo     `openapi.*`, `swagger.*`,
     `*.openapi.*`, and any JSON document that sniffs as OpenAPI - which is
     how the build-time outputs are found wherever they land: Swashbuckle CLI
     output, Microsoft.AspNetCore.OpenApi's `obj/` (or
     `OpenApiDocumentsDirectory`) document, a checked-in `wwwroot/swagger/`.
     The *runtime* paths those libraries serve (`/swagger/v1/swagger.json`,
     `/openapi/v1.json`, FastAPI's `/openapi.json`) become `openapi_url`
     findings, fetched live per run only when the owner configures one.
  3. Route sources: ASP.NET controllers (attribute routing) and minimal-API
     `Map*` calls, Angular router configs, FastAPI, Flask, Express.
  4. Staging base URL: appsettings / Angular environment files,
     `.env.example`-style templates (never a real `.env`), Terraform outputs,
     GitHub Actions `environment:` blocks, Bitbucket `deployment:` steps.

Every finding carries its source as `path:line` and one confidence level:

  high    The value is DECLARED, not inferred: a crew-declared ledger record, a
          path in an OpenAPI document, or a framework route whose literal path
          AND whole prefix are resolved in the same file (a controller route
          including its class-level [Route]; Map* on the app or on a MapGroup
          declared in the file; a FastAPI/Flask/Express route on the app, or
          on a router/blueprint whose mount is in the same file).
  medium  A literal value whose context is partly inferred: a route on a
          router, blueprint or group mounted in another file (the prefix may
          be missing), an Angular route in a root route config (client-side,
          served by the SPA), a framework-default live OpenAPI URL, a staging
          URL literal in a file or key named for staging.
  low     A lead, not a value: an Angular route in a lazily-loaded child
          config (its parent prefix lives elsewhere), a staging URL that is an
          expression resolved only at deploy time, a URL on a placeholder
          domain, a Bitbucket deployment named staging (its variables live in
          the Bitbucket UI), a staging-looking host in a non-staging file.

Nothing here decides anything. Setup shows the findings and turns what is not
settled into `**Decision needed:**` blocks (`decisions`); no staging URL at any
confidence is persisted unless the owner names it, and no endpoint below the
confidence the owner accepts is committed. Section C (monorepo inventory) calls
`detect(root, module_dir)` once per module; paths stay relative to `root`.
"""
import fnmatch
import json
import os
import re
import urllib.parse
from dataclasses import dataclass, field

HIGH, MEDIUM, LOW = "high", "medium", "low"
_RANK = {HIGH: 3, MEDIUM: 2, LOW: 1}
CONFIG_NAME = "gizmoduck-ci.json"
CONFIG_SCHEMA = "gizmoduck-ci/1"
LEDGER_REL = ".crew/endpoints.json"
DETECT_HINT = "run /gizmoduck:ci --detect"
AUTH_SECRET = "GIZMODUCK_AUTH_HEADER_VALUE"
AUTH_MODES = ("none", "header", "exclude-protected")

_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".terraform", "bin",
              "vendor", "dist", "build", "target", "coverage", ".angular", ".next", ".nuxt",
              "gizmoduck-out", ".idea", ".vs", ".tox", ".mypy_cache", ".pytest_cache",
              "site-packages"}
_MAX_BYTES = 1_000_000
_HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
_URL_RE = re.compile(r"https?://[^\s\"'<>\\)\]},;`]+")
_PLACEHOLDER_HOSTS = ("example.com", "example.org", "example.net")
_AUTHISH = re.compile(r"(?i)(auth|login|token|current_?user|security|oauth|jwt|verify|permission|"
                      r"admin|require_?user|get_?user)")


@dataclass(frozen=True)
class Finding:
    kind: str           # endpoint | staging_url | openapi_url | auth
    value: str          # a path for endpoint/openapi_url, a URL (or "") for staging_url
    source: str         # repo-relative path:line
    confidence: str
    detector: str
    method: str = ""
    protected: bool = False
    note: str = ""

    def to_dict(self):
        d = {"kind": self.kind, "value": self.value, "source": self.source,
             "confidence": self.confidence, "detector": self.detector}
        if self.method:
            d["method"] = self.method
        if self.protected:
            d["protected"] = True
        if self.note:
            d["note"] = self.note
        return d


@dataclass
class Detection:
    root: str
    subdir: str
    crew_present: bool
    findings: list = field(default_factory=list)
    checked: list = field(default_factory=list)

    def of(self, kind):
        return [f for f in self.findings if f.kind == kind]

    def to_dict(self):
        return {"subdir": self.subdir, "crew_present": self.crew_present,
                "findings": [f.to_dict() for f in self.findings], "checked": list(self.checked)}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _line_of(text, index):
    return text.count("\n", 0, max(index, 0)) + 1


def _read(path):
    try:
        if os.path.getsize(path) > _MAX_BYTES:
            return None
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def _walk(root, subdir):
    """(rel, full) for every candidate file under root/subdir, in sorted order.
    Files inside an `obj/` directory are kept only when they are JSON - that is
    where Microsoft.AspNetCore.OpenApi writes its build-time document."""
    base = os.path.normpath(os.path.join(root, subdir))
    out = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
        rel_dir = os.path.relpath(dirpath, root)
        in_obj = "obj" in rel_dir.replace("\\", "/").split("/")
        for name in sorted(filenames):
            if in_obj and not name.endswith(".json"):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace("\\", "/")
            out.append((rel, full))
    return out


_PARAM_RE = re.compile(r"\{\*{0,2}([A-Za-z_][\w-]*)(?::[^{}]*)?\??\}"   # {id} {id:int} {id?} {*rest}
                       r"|<(?:[\w]+:)?([A-Za-z_]\w*)>"                   # <id> <int:id>
                       r"|(?<![\w}]):([A-Za-z_]\w*)\??")                 # :id :id?


def normalise_path(path):
    """Canonical display/identity form: leading slash, no duplicate or trailing
    slashes, and every parameter spelling (`{id:int}`, `{id?}`, `<int:id>`,
    `:id`) written `{id}`, so the same route declared by two sources is one."""
    p = str(path or "").strip()
    if not p.startswith("/"):
        p = "/" + p
    p = re.sub(r"/{2,}", "/", p)
    p = _PARAM_RE.sub(lambda m: "{" + (m.group(1) or m.group(2) or m.group(3)) + "}", p)
    if len(p) > 1:
        p = p.rstrip("/")
    return p


def scan_path(path):
    """The part of a route that can be requested without inventing a value: the
    static prefix up to the first parameter or wildcard segment."""
    kept = []
    for seg in normalise_path(path).split("/")[1:]:
        if not seg or "{" in seg or "*" in seg or "(" in seg:
            break
        kept.append(seg)
    return "/" + "/".join(kept)


def _join(*parts):
    return normalise_path("/".join(p.strip("/") for p in parts if p and p.strip("/")))


def _is_placeholder(url):
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    if host in ("localhost",) or host.startswith("127.") or host == "0.0.0.0":
        return True
    if any(host == h or host.endswith("." + h) for h in _PLACEHOLDER_HOSTS):
        return True
    return any(tok in url.lower() for tok in ("<", "{", "$", "your-", "changeme", "xxx"))


def _is_local(url):
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return host in ("localhost", "0.0.0.0") or host.startswith("127.") or host.endswith(".localhost")


def _call_args(text, open_idx, limit=2000):
    """The argument text of the call whose "(" is at open_idx, up to its
    matching ")" - so one constructor's keywords never leak into the next
    statement's."""
    depth, quote, i = 0, None, open_idx
    end = min(len(text), open_idx + limit)
    while i < end:
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1:i]
        i += 1
    return text[open_idx + 1:end]


def _yaml():
    try:
        import yaml
        return yaml
    except ImportError:
        return None


# --------------------------------------------------------------------------
# 1. crew ledger
# --------------------------------------------------------------------------

def _detect_crew(rel, text, out, checked):
    try:
        doc = json.loads(text)
    except ValueError as exc:
        checked.append(f"{rel}: unreadable JSON ({exc}) - no endpoints taken from it")
        return
    records = doc.get("records") if isinstance(doc, dict) else None
    if not isinstance(records, list):
        checked.append(f"{rel}: no 'records' list - no endpoints taken from it")
        return
    n = 0
    for rec in records:
        if not isinstance(rec, dict) or str(rec.get("status", "")).lower() == "closed":
            continue
        value = rec.get("endpoint")
        if not isinstance(value, str) or not value.strip() or any(c.isspace() for c in value.strip()):
            continue
        idx = text.find(f'"{rec.get("id")}"') if rec.get("id") else -1
        conf = HIGH if rec.get("source") == "declared" else MEDIUM
        value = value.strip()
        out.append(Finding("endpoint", normalise_path(value) if value.startswith("/") else value,
                           f"{rel}:{_line_of(text, idx) if idx >= 0 else 1}", conf, "crew-ledger"))
        n += 1
    checked.append(f"{rel}: {n} open record(s)")


# --------------------------------------------------------------------------
# 2. OpenAPI / Swagger documents
# --------------------------------------------------------------------------

_OPENAPI_NAME = re.compile(r"^(?:(?:openapi|swagger)(?:[._-][\w.-]*)?|[\w.-]+\.openapi)\.(?:json|ya?ml)$", re.I)
_JSON_SNIFF = re.compile(r'"(?:openapi|swagger)"\s*:\s*"\d')
_YAML_SNIFF = re.compile(r"^(?:openapi|swagger)\s*:\s*['\"]?\d", re.M)


def parse_openapi(doc):
    """[(METHOD, path, protected)] plus the path prefix its first server (or
    Swagger 2 basePath) implies, from a parsed OpenAPI 2/3 document. Raises
    ValueError on anything that is not one."""
    if not isinstance(doc, dict) or not ("openapi" in doc or "swagger" in doc) \
            or not isinstance(doc.get("paths"), dict):
        raise ValueError("not an OpenAPI/Swagger document (no openapi/swagger key or no paths)")
    prefix = ""
    servers = doc.get("servers")
    if isinstance(servers, list) and servers and isinstance(servers[0], dict):
        prefix = urllib.parse.urlsplit(str(servers[0].get("url") or "")).path
    elif isinstance(doc.get("basePath"), str):
        prefix = doc["basePath"]
    global_sec = bool(doc.get("security"))
    ops = []
    for path, item in doc["paths"].items():
        if not isinstance(item, dict):
            continue
        for method in _HTTP_METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            sec = op.get("security")
            protected = bool(sec) if isinstance(sec, list) else global_sec
            ops.append((method.upper(), _join(prefix, str(path)), protected))
    return ops, prefix


def _detect_openapi(rel, text, out, checked):
    name = rel.rsplit("/", 1)[-1]
    is_json = name.lower().endswith(".json")
    if not _OPENAPI_NAME.match(name):
        if not (is_json and _JSON_SNIFF.search(text[:4096])) and \
                not (not is_json and _YAML_SNIFF.search(text[:4096])):
            return
    try:
        if is_json:
            doc = json.loads(text)
        else:
            yaml = _yaml()
            if yaml is None:
                checked.append(f"{rel}: looks like OpenAPI YAML but PyYAML is not installed - not read")
                return
            doc = yaml.safe_load(text)
        ops, _prefix = parse_openapi(doc)
    except ValueError as exc:
        if _OPENAPI_NAME.match(name):
            checked.append(f"{rel}: named like OpenAPI but not readable as one ({exc})")
        return
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # yaml.YAMLError has no common base with ValueError; a malformed file
        # is reported and skipped, never allowed to abort detection.
        checked.append(f"{rel}: not readable ({type(exc).__name__})")
        return
    for method, path, protected in ops:
        raw = path.rsplit("/", 1)[-1] if path != "/" else "/"
        idx = text.find(raw) if raw else -1
        out.append(Finding("endpoint", path, f"{rel}:{_line_of(text, idx) if idx >= 0 else 1}", HIGH,
                           "openapi", method=method, protected=protected))
    for m in _URL_RE.finditer(text[:20000]):
        url = m.group(0)
        if "stag" in (urllib.parse.urlsplit(url).hostname or "") and not _is_local(url):
            out.append(Finding("staging_url", url.rstrip("/"), f"{rel}:{_line_of(text, m.start())}",
                               LOW if _is_placeholder(url) else MEDIUM, "openapi-servers",
                               note="server URL declared in the OpenAPI document"))
    checked.append(f"{rel}: OpenAPI document, {len(ops)} operation(s)")


# --------------------------------------------------------------------------
# 3a. ASP.NET controllers and minimal APIs
# --------------------------------------------------------------------------

_CS_ATTR = re.compile(r"\b(Route|Http(?:Get|Post|Put|Delete|Patch|Head|Options)|Authorize|AllowAnonymous|"
                      r"ApiController)(?:Attribute)?\b(?:\s*\(\s*(?:template\s*:\s*)?@?\"([^\"]*)\")?")
_CS_CLASS = re.compile(r"\bclass\s+(\w+)(?:\s*<[^>]*>)?(?:\s*\([^)]*\))?\s*(?::\s*([^{]+))?")
_CS_METHOD = re.compile(r"^\s*(?:\[[^\]]*\]\s*)*(?:public|internal)\s+[^=;(]*?\b(\w+)\s*\(")
_CS_BUILD = re.compile(r"\b(?:var|WebApplication)\s+(\w+)\s*=\s*\w+\s*\.\s*Build\s*\(\s*\)")
_CS_GROUP = re.compile(r"\b(?:var|RouteGroupBuilder)\s+(\w+)\s*=\s*(\w+)\s*\.\s*MapGroup\s*\(\s*@?\"([^\"]*)\"")
_CS_MAP = re.compile(r"\b(\w+)\s*\.\s*Map(Get|Post|Put|Delete|Patch|Methods)\s*\(\s*(?:pattern\s*:\s*)?@?\"([^\"]*)\"")


def _cs_controllers(rel, text, out):
    pending, cls = [], None
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        if stripped.startswith("["):
            pending += [(m.group(1), m.group(2)) for m in _CS_ATTR.finditer(stripped)]
            if stripped.endswith("]"):
                continue
        cm = _CS_CLASS.search(stripped)
        if cm and not stripped.startswith("["):
            bases = cm.group(2) or ""
            name = cm.group(1)
            is_ctrl = name.endswith("Controller") or re.search(r"\bController(Base)?\b", bases) \
                or any(a == "ApiController" for a, _ in pending)
            routes = [t for a, t in pending if a == "Route" and t is not None]
            cls = {"name": name, "ctrl": bool(is_ctrl), "route": routes[0] if routes else None,
                   "auth": any(a == "Authorize" for a, _ in pending)}
            pending = []
            continue
        mm = _CS_METHOD.match(line)
        verbs = [(a[4:].upper(), t) for a, t in pending if a.startswith("Http")]
        mroutes = [t for a, t in pending if a == "Route" and t is not None]
        if mm and cls and cls["ctrl"] and (verbs or mroutes):
            action = mm.group(1)
            protected = (cls["auth"] or any(a == "Authorize" for a, _ in pending)) and \
                not any(a == "AllowAnonymous" for a, _ in pending)
            for verb, tmpl in verbs or [("", None)]:
                tmpl = tmpl if tmpl is not None else (mroutes[0] if mroutes else None)
                if tmpl is not None and (tmpl.startswith("/") or tmpl.startswith("~/")):
                    path = tmpl.lstrip("~")
                else:
                    path = _join(cls["route"] or "", tmpl or "")
                ctrl = cls["name"][:-len("Controller")] if cls["name"].endswith("Controller") else cls["name"]
                path = path.replace("[controller]", ctrl).replace("[action]", action)
                conf = MEDIUM if "[" in path or (cls["route"] is None and tmpl is None) else HIGH
                note = "unresolved route token" if "[" in path else ""
                out.append(Finding("endpoint", normalise_path(path), f"{rel}:{lineno}", conf,
                                   "aspnet-controller", method=verb, protected=protected, note=note))
        pending = []


def _cs_minimal(rel, text, out):
    apps = {m.group(1) for m in _CS_BUILD.finditer(text)} | {"app"}
    groups = {}
    for m in _CS_GROUP.finditer(text):
        stmt = text[m.end():text.find(";", m.end()) if text.find(";", m.end()) >= 0 else len(text)]
        groups[m.group(1)] = (m.group(2), m.group(3), ".RequireAuthorization(" in stmt)

    def resolve(recv, depth=0):
        if recv in apps:
            return "", False, True
        if recv in groups and depth < 10:
            parent, prefix, auth = groups[recv]
            p_prefix, p_auth, known = resolve(parent, depth + 1)
            return _join(p_prefix, prefix), auth or p_auth, known
        return "", False, False

    for m in _CS_MAP.finditer(text):
        recv, verb, pattern = m.group(1), m.group(2), m.group(3)
        prefix, auth, known = resolve(recv)
        end = text.find(";", m.end())
        stmt = text[m.end():end if end >= 0 else len(text)]
        protected = (auth or ".RequireAuthorization(" in stmt) and ".AllowAnonymous(" not in stmt
        out.append(Finding("endpoint", _join(prefix, pattern), f"{rel}:{_line_of(text, m.start())}",
                           HIGH if known else MEDIUM, "aspnet-minimal-api",
                           method="" if verb == "Methods" else verb.upper(), protected=protected,
                           note="" if known else f"receiver '{recv}' is a group or builder declared "
                                                 f"elsewhere; its prefix may be missing"))


def _cs_openapi_urls(rel, text, out):
    m = re.search(r"\bAddSwaggerGen\s*\(", text)
    if m:
        doc = re.search(r"\bSwaggerDoc\s*\(\s*\"([^\"]+)\"", text)
        out.append(Finding("openapi_url", f"/swagger/{doc.group(1) if doc else 'v1'}/swagger.json",
                           f"{rel}:{_line_of(text, m.start())}", MEDIUM, "swashbuckle",
                           note="Swashbuckle's default route; a custom RouteTemplate changes it"))
    m = re.search(r"\bMapOpenApi\s*\(\s*(?:@?\"([^\"]*)\")?", text)
    if m:
        name = re.search(r"\bAddOpenApi\s*\(\s*\"([^\"]+)\"", text)
        pattern = m.group(1) or "/openapi/{documentName}.json"
        out.append(Finding("openapi_url", normalise_path(pattern.replace("{documentName}",
                                                                           name.group(1) if name else "v1")),
                           f"{rel}:{_line_of(text, m.start())}", MEDIUM, "aspnetcore-openapi",
                           note="Microsoft.AspNetCore.OpenApi MapOpenApi route"))
    for pat in (r"\bAddAuthentication\s*\(", r"\bAddJwtBearer\s*\(", r"\bUseAuthorization\s*\("):
        m = re.search(pat, text)
        if m:
            out.append(Finding("auth", m.group(0).split("(")[0].strip().lstrip("."),
                               f"{rel}:{_line_of(text, m.start())}", MEDIUM, "aspnet-auth"))
            break


# --------------------------------------------------------------------------
# 3b. FastAPI and Flask
# --------------------------------------------------------------------------

_PY_CTOR = re.compile(r"^[ \t]*(\w+)\s*(?::\s*[\w.]+)?\s*=\s*(?:fastapi\.|flask\.)?(FastAPI|APIRouter|Flask|Blueprint)"
                      r"\s*\(", re.M)
_PY_ROUTE = re.compile(r"^[ \t]*@\s*(\w+)\s*\.\s*(get|post|put|delete|patch|options|head|api_route|route)\s*\(\s*"
                       r"(?:path\s*=\s*|rule\s*=\s*)?[rbu]?(['\"])(.*?)\3([^\n]*)", re.M)
_PY_MOUNT = re.compile(r"\b(\w+)\s*\.\s*(include_router|register_blueprint)\s*\(")
_PY_KW = r"\b{}\s*=\s*[rbu]?['\"]([^'\"]*)['\"]"
_PY_METHODS = re.compile(r"\bmethods\s*=\s*[\[(]([^\])]*)[\])]")


def _detect_python(rel, text, out):
    if "fastapi" not in text and "flask" not in text.lower():
        return
    ctors = {}
    for m in _PY_CTOR.finditer(text):
        window = _call_args(text, m.end() - 1)
        kind = m.group(2)
        kw = "url_prefix" if kind == "Blueprint" else "prefix"
        pm = re.search(_PY_KW.format(kw), window)
        entry = {"kind": kind, "prefix": pm.group(1) if pm else "", "mount": None,
                 "line": _line_of(text, m.start())}
        if kind == "FastAPI":
            if re.search(r"\bopenapi_url\s*=\s*None\b", window):
                entry["openapi"] = None
            else:
                om = re.search(_PY_KW.format("openapi_url"), window)
                entry["openapi"] = om.group(1) if om else "/openapi.json"
        ctors[m.group(1)] = entry
    for m in _PY_MOUNT.finditer(text):
        args = _call_args(text, m.end() - 1)
        first = re.match(r"\s*(\w+)", args)
        child = ctors.get(first.group(1)) if first else None
        if child is not None:
            kw = "url_prefix" if m.group(2) == "register_blueprint" else "prefix"
            pm = re.search(_PY_KW.format(kw), args)
            child["mount"] = pm.group(1) if pm else ""
            if pm and kw == "url_prefix":
                child["prefix"], child["mount"] = "", pm.group(1)
    for name, c in ctors.items():
        if c["kind"] == "FastAPI" and c.get("openapi"):
            out.append(Finding("openapi_url", normalise_path(c["openapi"]), f"{rel}:{c['line']}", MEDIUM,
                               "fastapi", note=f"FastAPI app '{name}' serves its OpenAPI document here"))
    lines = text.splitlines()
    for m in _PY_ROUTE.finditer(text):
        recv, verb, path, rest = m.group(1), m.group(2), m.group(4), m.group(5)
        if not path.startswith("/") and path != "":
            continue
        c = ctors.get(recv)
        framework = ("flask" if c["kind"] in ("Flask", "Blueprint") else "fastapi") if c else \
            ("fastapi" if "fastapi" in text else "flask")
        if c is None:
            prefix, conf, note = "", MEDIUM, f"'{recv}' is imported from another module; its prefix may be missing"
        elif c["kind"] in ("FastAPI", "Flask"):
            prefix, conf, note = "", HIGH, ""
        elif c["mount"] is not None:
            prefix, conf, note = _join(c["mount"], c["prefix"]), HIGH, ""
        else:
            prefix, conf, note = c["prefix"], MEDIUM, f"'{recv}' is mounted in another file; that prefix is missing"
        if verb in ("route", "api_route"):
            mm = _PY_METHODS.search(rest)
            methods = [x.strip(" '\"").upper() for x in mm.group(1).split(",") if x.strip(" '\"")] if mm \
                else (["GET"] if verb == "route" else [""])
        else:
            methods = [verb.upper()]
        lineno = _line_of(text, m.start())
        protected = False
        for follow in lines[lineno - 1:lineno + 8]:
            if re.search(r"@\s*\w*(login_required|auth_required|jwt_required|roles_required|requires_auth)", follow):
                protected = True
            dep = re.findall(r"\b(?:Depends|Security)\s*\(\s*([\w.]+)", follow)
            if any(_AUTHISH.search(d) for d in dep) or ("dependencies" in follow and _AUTHISH.search(follow)):
                protected = True
            if follow.rstrip().endswith(":") and follow.lstrip().startswith(("def ", "async def ")):
                break
        for method in methods:
            out.append(Finding("endpoint", _join(prefix, path), f"{rel}:{lineno}", conf, framework,
                               method=method, protected=protected, note=note))
    for pat in (r"\bfrom\s+fastapi\.security\b", r"\bflask_login\b", r"\bflask_jwt\w*\b"):
        m = re.search(pat, text)
        if m:
            out.append(Finding("auth", m.group(0), f"{rel}:{_line_of(text, m.start())}", MEDIUM, "python-auth"))
            break


# --------------------------------------------------------------------------
# 3c. Express
# --------------------------------------------------------------------------

_JS_CTOR = re.compile(r"\b(?:const|let|var)\s+(\w+)\s*(?::\s*[\w.]+)?\s*=\s*(express\s*\(\s*\)|"
                      r"(?:express\s*\.\s*)?Router\s*\([^)]*\))")
_JS_ROUTE = re.compile(r"\b(\w+)\s*\.\s*(get|post|put|delete|patch|all|options|head)\s*\(\s*(['\"`])([^'\"`]*)\3"
                       r"([^\n]*)")
_JS_USE = re.compile(r"\b(\w+)\s*\.\s*use\s*\(\s*(['\"`])([^'\"`]*)\2\s*,([^\n]*)")
_JS_AUTH = re.compile(r"(?i)\b(auth\w*|authenticate\w*|requireAuth\w*|passport\.authenticate|jwt\w*|ensure\w*|"
                      r"isAuthenticated|protect\w*|verifyToken\w*|requireLogin|checkJwt|requireUser)\b")


def _detect_express(rel, text, out):
    if not re.search(r"""(?:require\(\s*['"]express['"]\s*\)|from\s+['"]express['"])""", text):
        return
    recvs = {}
    for m in _JS_CTOR.finditer(text):
        recvs[m.group(1)] = {"app": bool(re.fullmatch(r"express\s*\(\s*\)", m.group(2))), "mount": None}
    for m in _JS_USE.finditer(text):
        for name in re.findall(r"\b(\w+)\b", m.group(4)):
            if name in recvs and not recvs[name]["app"]:
                recvs[name]["mount"] = m.group(3)
    for m in _JS_ROUTE.finditer(text):
        recv, verb, path, rest = m.group(1), m.group(2), m.group(4), m.group(5)
        r = recvs.get(recv)
        if r is None or not path.startswith("/") or "${" in path:
            continue
        if r["app"]:
            prefix, conf, note = "", HIGH, ""
        elif r["mount"] is not None:
            prefix, conf, note = r["mount"], HIGH, ""
        else:
            prefix, conf, note = "", MEDIUM, f"router '{recv}' is mounted in another file; that prefix is missing"
        handler_at = min([i for i in (rest.find("=>"), rest.find("function")) if i >= 0] or [len(rest)])
        protected = bool(_JS_AUTH.search(rest[:handler_at]))
        out.append(Finding("endpoint", _join(prefix, path), f"{rel}:{_line_of(text, m.start())}", conf,
                           "express", method="" if verb == "all" else verb.upper(), protected=protected,
                           note=note))


# --------------------------------------------------------------------------
# 3d. Angular router
# --------------------------------------------------------------------------

_NG_TOKEN = re.compile(r"(?P<comment>//[^\n]*|/\*.*?\*/)|(?P<string>'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|"
                       r"`(?:\\.|[^`\\])*`)|(?P<children>\bchildren\s*:\s*\[)|(?P<key>\b(?:path|redirectTo|"
                       r"canActivate|canActivateChild|canMatch|canLoad)\s*:)|(?P<lb>\{)|(?P<rb>\})|"
                       r"(?P<lk>\[)|(?P<rk>\])", re.S)


def _detect_angular(rel, text, out):
    if rel.endswith(".spec.ts") or not re.search(r"\bRoutes\b|RouterModule\s*\.\s*for|provideRouter\s*\(|"
                                                 r":\s*Route\s*\[\]", text):
        return
    root_config = bool(re.search(r"\bforRoot\s*\(|provideRouter\s*\(", text)) or \
        rel.rsplit("/", 1)[-1] in ("app.routes.ts", "app-routing.module.ts")
    stack, pending, seen = [], None, set()
    for m in _NG_TOKEN.finditer(text):
        kind = m.lastgroup
        if kind == "comment":
            continue
        if kind == "key":
            pending = m.group("key").split(":")[0].strip()
            if pending != "path" and stack and stack[-1]["t"] == "obj":
                stack[-1]["redirect" if pending == "redirectTo" else "guard"] = True
                pending = None
            continue
        if kind == "string":
            if pending == "path" and stack and stack[-1]["t"] == "obj":
                stack[-1]["path"] = m.group("string")[1:-1]
                stack[-1]["pos"] = m.start()
            pending = None
            continue
        pending = None
        if kind == "lb":
            stack.append({"t": "obj", "path": None, "guard": False, "redirect": False, "pos": 0})
        elif kind in ("lk", "children"):
            stack.append({"t": "arr", "children": kind == "children"})
        elif kind == "rk":
            while stack and stack.pop()["t"] != "arr":
                pass
        elif kind == "rb":
            while stack and stack[-1]["t"] != "obj":
                stack.pop()
            if not stack:
                continue
            obj = stack.pop()
            if obj["path"] is None or obj["redirect"] or "**" in obj["path"]:
                continue
            parts, guarded = [], obj["guard"]
            for i, frame in enumerate(stack):
                if frame["t"] == "obj" and i + 1 < len(stack) and stack[i + 1]["t"] == "arr" \
                        and stack[i + 1]["children"] and frame["path"] is not None:
                    parts.append(frame["path"])
                    guarded = guarded or frame["guard"]
            path = _join(*parts, obj["path"])
            if path in seen:
                continue
            seen.add(path)
            out.append(Finding("endpoint", path, f"{rel}:{_line_of(text, obj['pos'])}",
                               MEDIUM if root_config else LOW, "angular-router", protected=guarded,
                               note="client-side route served by the SPA" if root_config else
                               "child route config; the lazy-loading parent's prefix lives elsewhere"))


# --------------------------------------------------------------------------
# 4. staging base URL
# --------------------------------------------------------------------------

_STAGING_WORD = re.compile(r"(?i)(?<![a-z])(staging|stage|stg)(?![a-z])")
_APPSETTINGS = re.compile(r"^appsettings(?:\.([\w-]+))?\.json$", re.I)
_NG_ENV = re.compile(r"^environment(?:\.([\w-]+))?\.ts$", re.I)
_ENV_TEMPLATE = re.compile(r"^\.env(?:\.[\w-]+)*\.(?:example|sample|template)$|^\.env\.(?:example|sample|template)$",
                           re.I)
_TF_OUTPUT = re.compile(r"^\s*output\s+\"([^\"]+)\"\s*\{", re.M)


def _url_finding(url, rel, text, idx, conf, detector, note=""):
    url = url.rstrip("/.")
    if _is_placeholder(url):
        conf, note = LOW, (note + "; " if note else "") + "placeholder value"
    return Finding("staging_url", url, f"{rel}:{_line_of(text, idx)}", conf, detector, note=note)


def _detect_staging_files(rel, text, out):
    name = rel.rsplit("/", 1)[-1]
    staging_file = bool(_STAGING_WORD.search(name)) or bool(_STAGING_WORD.search(rel))
    m = _APPSETTINGS.match(name) or _NG_ENV.match(name)
    if m:
        detector = "appsettings" if name.lower().startswith("appsettings") else "angular-environment"
        env_is_staging = bool(m.group(1) and _STAGING_WORD.search(m.group(1)))
        for um in _URL_RE.finditer(text):
            url = um.group(0)
            if _is_local(url):
                continue
            if env_is_staging:
                out.append(_url_finding(url, rel, text, um.start(), MEDIUM, detector,
                                        f"URL in the {m.group(1)} environment file"))
            elif "stag" in (urllib.parse.urlsplit(url).hostname or ""):
                out.append(_url_finding(url, rel, text, um.start(), LOW, detector,
                                        "staging-looking host in a non-staging file"))
        return
    if _ENV_TEMPLATE.match(name):
        for lm in re.finditer(r"^\s*(?:export\s+)?([A-Za-z_]\w*)\s*=\s*['\"]?([^'\"\s#]*)", text, re.M):
            key, value = lm.group(1), lm.group(2)
            if not _URL_RE.fullmatch(value) or _is_local(value):
                continue
            if _STAGING_WORD.search(key) or staging_file or "stag" in (urllib.parse.urlsplit(value).hostname or ""):
                out.append(_url_finding(value, rel, text, lm.start(2), MEDIUM, "env-template", f"{key}="))
        return
    if name.endswith(".tf"):
        for om in _TF_OUTPUT.finditer(text):
            body = text[om.end():om.end() + 800]
            vm = re.search(r"^\s*value\s*=\s*(.+)$", body, re.M)
            oname = om.group(1)
            if not vm or not (_STAGING_WORD.search(oname) or staging_file):
                continue
            if not re.search(r"(?i)url|endpoint|host|domain|fqdn|dns|address|origin", oname):
                continue
            value = vm.group(1).strip()
            idx = om.end() + vm.start(1)
            lit = re.fullmatch(r"\"(https?://[^\"$]+)\"", value)
            if lit:
                out.append(_url_finding(lit.group(1), rel, text, idx, MEDIUM, "terraform-output",
                                        f"output \"{oname}\""))
            else:
                out.append(Finding("staging_url", "", f"{rel}:{_line_of(text, idx)}", LOW, "terraform-output",
                                   note=f"output \"{oname}\" = {value[:120]} - resolved only at apply time "
                                        f"(`terraform output {oname}` against the staging state)"))


def _detect_github_envs(rel, text, out, checked):
    yaml = _yaml()
    if yaml is None:
        checked.append(f"{rel}: PyYAML is not installed - GitHub environments not read")
        return
    try:
        doc = yaml.safe_load(text)
    except Exception:  # pylint: disable=broad-exception-caught
        checked.append(f"{rel}: not parseable YAML - skipped")
        return
    jobs = doc.get("jobs") if isinstance(doc, dict) else None
    for job in (jobs or {}).values():
        env = job.get("environment") if isinstance(job, dict) else None
        name, url = (env.get("name"), env.get("url")) if isinstance(env, dict) else (env, None)
        if not isinstance(name, str) or not _STAGING_WORD.search(name):
            continue
        anchor = text.find(str(url)) if url else text.find(name)
        if isinstance(url, str) and "${{" not in url and _URL_RE.fullmatch(url.strip()):
            out.append(_url_finding(url.strip(), rel, text, anchor, MEDIUM, "github-environment",
                                    f"environment '{name}'"))
        else:
            out.append(Finding("staging_url", "", f"{rel}:{_line_of(text, anchor)}", LOW, "github-environment",
                               note=f"environment '{name}' has " + (f"url {url}, an expression resolved at run time"
                                                                   if url else "no url") +
                               " - the value may be in Settings -> Environments"))


def _walk_bb_steps(node):
    if isinstance(node, dict):
        if isinstance(node.get("step"), dict):
            yield node["step"]
        for v in node.values():
            yield from _walk_bb_steps(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_bb_steps(v)


def _detect_bitbucket_deployments(rel, text, out, checked):
    yaml = _yaml()
    if yaml is None:
        checked.append(f"{rel}: PyYAML is not installed - Bitbucket deployments not read")
        return
    try:
        doc = yaml.safe_load(text)
    except Exception:  # pylint: disable=broad-exception-caught
        checked.append(f"{rel}: not parseable YAML - skipped")
        return
    seen = set()
    for step in _walk_bb_steps(doc):
        dep = step.get("deployment")
        if not isinstance(dep, str) or not _STAGING_WORD.search(dep) or dep in seen:
            continue
        seen.add(dep)
        urls = [u for line in step.get("script") or [] if isinstance(line, str)
                for u in _URL_RE.findall(line) if "api.bitbucket.org" not in u]
        for url in urls:
            out.append(_url_finding(url, rel, text, text.find(url), MEDIUM, "bitbucket-deployment",
                                    f"URL in the '{dep}' deployment step"))
        if not urls:
            m = re.search(r"deployment\s*:\s*['\"]?" + re.escape(dep), text)
            out.append(Finding("staging_url", "", f"{rel}:{_line_of(text, m.start() if m else 0)}", LOW,
                               "bitbucket-deployment",
                               note=f"deployment '{dep}' exists; its variables live in Repository settings -> "
                                    f"Deployments and cannot be read from the repository"))


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------

def crew_present(root):
    return os.path.isdir(os.path.join(root, ".crew")) and (
        os.path.isfile(os.path.join(root, ".crew", "endpoints.json"))
        or os.path.isfile(os.path.join(root, ".crew", "config.json")))


def detect(root, subdir="."):
    """Everything this module can find under root/subdir. Pure read."""
    root = os.path.abspath(root)
    det = Detection(root=root, subdir=subdir, crew_present=crew_present(root))
    out, checked = [], []
    ledger = os.path.join(root, subdir, ".crew", "endpoints.json")
    text = _read(ledger) if os.path.isfile(ledger) else None
    if text is not None:
        _detect_crew(os.path.relpath(ledger, root).replace("\\", "/"), text, out, checked)
    else:
        checked.append(f"{LEDGER_REL}: absent")
    n_files = 0
    for rel, full in _walk(root, subdir):
        name = rel.rsplit("/", 1)[-1]
        ext = os.path.splitext(name)[1].lower()
        if rel.endswith(LEDGER_REL) or ext not in (".json", ".yaml", ".yml", ".cs", ".py", ".js", ".mjs",
                                                  ".cjs", ".ts", ".tf") and not _ENV_TEMPLATE.match(name):
            continue
        text = _read(full)
        if text is None:
            continue
        n_files += 1
        if ext in (".json", ".yaml", ".yml"):
            _detect_openapi(rel, text, out, checked)
        if ext == ".cs":
            _cs_controllers(rel, text, out)
            _cs_minimal(rel, text, out)
            _cs_openapi_urls(rel, text, out)
        elif ext == ".py":
            _detect_python(rel, text, out)
        elif ext in (".js", ".mjs", ".cjs", ".ts"):
            _detect_express(rel, text, out)
            if ext == ".ts":
                _detect_angular(rel, text, out)
        if "/.github/workflows/" in "/" + rel and ext in (".yml", ".yaml"):
            _detect_github_envs(rel, text, out, checked)
        if name == "bitbucket-pipelines.yml":
            _detect_bitbucket_deployments(rel, text, out, checked)
        _detect_staging_files(rel, text, out)
    checked.append(f"{n_files} candidate file(s) read under {subdir}")
    det.findings = _dedupe(out)
    det.checked = checked
    return det


def _dedupe(findings):
    seen, out = set(), []
    for f in findings:
        key = (f.kind, f.value, f.method, f.source)
        if key not in seen:
            seen.add(key)
            out.append(f)
    return sorted(out, key=lambda f: (f.kind, -_RANK[f.confidence], f.value, f.method, f.source))


# --------------------------------------------------------------------------
# presentation: findings and Decision-needed blocks
# --------------------------------------------------------------------------

def render_findings(det):
    lines = [f"# gizmoduck endpoint detection ({det.subdir})", ""]
    labels = {"endpoint": "Endpoints", "openapi_url": "Live OpenAPI documents (fetchable per run)",
              "staging_url": "Staging base URL candidates", "auth": "Authentication signals"}
    for kind in ("endpoint", "openapi_url", "staging_url", "auth"):
        items = det.of(kind)
        lines.append(f"## {labels[kind]}: {len(items)}")
        for f in items:
            what = f"{f.method + ' ' if f.method else ''}{f.value or '(no literal value)'}"
            extra = (" [protected]" if f.protected else "") + (f" - {f.note}" if f.note else "")
            lines.append(f"- [{f.confidence}] {what}  ({f.source}, {f.detector}){extra}")
        lines.append("")
    if not det.of("endpoint"):
        lines += ["**UNVERIFIED:** no endpoint was detected or declared. Until one is, every endpoint-scan run "
                  f"fails rather than passing an empty scan. Declare them (setup, or {LEDGER_REL} when crew is "
                  "present) or configure a live OpenAPI document.", ""]
    lines.append("## Checked")
    lines += [f"- {c}" for c in det.checked]
    return "\n".join(lines) + "\n"


@dataclass
class Decision:
    key: str
    question: str
    options: list          # [(label, cost)], recommendation first
    checked: str
    unsettled: str

    def render(self):
        lines = [f"**Decision needed:** {self.question}", ""]
        for i, (label, cost) in enumerate(self.options, 1):
            lines.append(f"{i}. {label}{' (Recommended)' if i == 1 else ''} - {cost}")
        lines += ["", f"**What I already checked:** {self.checked}",
                  f"**What I could not settle:** {self.unsettled}"]
        return "\n".join(lines) + "\n"


def _staging_candidates(det):
    best = {}
    for f in det.of("staging_url"):
        if f.value and (f.value not in best or _RANK[f.confidence] > _RANK[best[f.value].confidence]):
            best[f.value] = f
    return sorted(best.values(), key=lambda f: (-_RANK[f.confidence], f.value))


def decisions(det, config=None):
    """The questions setup must ask. A settled field in an existing
    gizmoduck-ci.json is not asked again; nothing here ever fills one in."""
    config = config or {}
    out = []
    staging = config.get("staging") or {}
    cands = _staging_candidates(det)
    leads = [f for f in det.of("staging_url") if not f.value]
    sources = sorted({f.detector for f in det.of("staging_url")})
    if "base_url" not in staging:
        opts = []
        for f in cands[:3]:
            opts.append((f"Use {f.value} as the staging base URL",
                         f"[{f.confidence}] from {f.source}; confirm it is staging and that scanning it is "
                         f"authorised - the render-time guard refuses it only if you also list it as production"))
        opts.append(("Install code scans only for now (`--staging-url none`)",
                     "the endpoint stage stays UNVERIFIED and fails every run with "
                     f"\"{DETECT_HINT}\" until a staging URL is set"))
        if not cands:
            opts.insert(0, ("Name the staging base URL yourself (`--staging-url <url>`)",
                            "nothing in the repository names one, so it has to come from you; endpoint scans "
                            "start on the next staging deploy"))
        out.append(Decision(
            "staging_url", "Which base URL is staging - the only origin endpoint scans may touch?", opts[:4],
            f"appsettings/environment files, .env templates, Terraform outputs, GitHub environments, Bitbucket "
            f"deployments, OpenAPI servers - {len(cands)} literal candidate(s)"
            + (f", {len(leads)} lead(s) with no literal value ({'; '.join(f.note for f in leads[:2])})"
               if leads else "") + (f" (sources: {', '.join(sources)})" if sources else ""),
            "whether a URL is staging, and whether scanning it is authorised, is not something a file can state"
            if cands else "no file in the repository names a staging URL; I will not guess one"))
    endpoints = det.of("endpoint")
    protected = [f for f in endpoints if f.protected]
    if "mode" not in (config.get("auth") or {}):
        auth_sig = det.of("auth")
        out.append(Decision(
            "auth", f"How should endpoint scans treat protected endpoints ({len(protected)} detected)?",
            [("Scan unauthenticated (`--auth none`)",
              "protected endpoints are probed only as an anonymous caller sees them (401/403 surface); the "
              "authenticated attack surface stays unscanned"),
             (f"Send a staging test account's header to Nuclei (`--auth header`, secret {AUTH_SECRET})",
              "a staging credential lives in CI secrets and scans act as that user (they can change its data); "
              "ZAP baseline and testssl still run unauthenticated"),
             ("Leave protected endpoints out (`--auth exclude-protected`)",
              "they are not scanned at all; only endpoints detection could mark protected are excluded")],
            f"{len(protected)} endpoint(s) carry an auth marker ([Authorize], RequireAuthorization, Depends/"
            f"login_required, auth middleware, canActivate, OpenAPI security); {len(auth_sig)} auth signal(s)",
            "whether a staging test account exists and may be used by a scanner"))
    if "scope" not in config:
        ops = sorted({f.value for f in endpoints if re.search(r"(?i)health|metrics|ready|live|swagger|openapi",
                                                              f.value)})
        out.append(Decision(
            "scope", "Which detected endpoints are in scope for scanning?",
            [("Every detected endpoint (`--scope all`)",
              "operational endpoints get scanner traffic too" + (f" ({', '.join(ops[:4])})" if ops else "")),
             ("Everything except operational endpoints (`--exclude '*health*' --exclude '*metrics*'`)",
              "a vulnerability on an excluded path is never scanned"),
             ("Only a prefix you name (`--include '/api/*'`)",
              "endpoints outside it, including new ones, are reported but not scanned")],
            f"{len(endpoints)} endpoint(s) detected", "which endpoints the owner wants scanner traffic on"))
    if "accept" not in config:
        by = {c: len([f for f in endpoints if f.confidence == c]) for c in (HIGH, MEDIUM, LOW)}
        out.append(Decision(
            "accept", "Which detected endpoints go into the committed list?",
            [("High and medium confidence (`--accept medium`)",
              f"{by[LOW]} low-confidence one(s) are not committed; each run still scans them and reports them "
              "\"new, confirm at next setup\""),
             ("High confidence only (`--accept high`)",
              f"{by[MEDIUM] + by[LOW]} inferred one(s) stay uncommitted and are reported as new every run"),
             ("All, including low (`--accept low`)",
              "guessed routes (lazy Angular children, unmounted routers) are committed and may 404")],
            f"high {by[HIGH]}, medium {by[MEDIUM]}, low {by[LOW]}",
            "whether the inferred routes are real at the URLs detection assembled"))
    live = det.of("openapi_url")
    if live and "openapi_path" not in staging:
        out.append(Decision(
            "openapi", "Fetch the live OpenAPI document from staging on every run?",
            [(f"Yes, {live[0].value} (`--openapi-path {live[0].value}`)",
              "one extra guarded GET per run; endpoints added since setup are found and reported as new"),
             ("No (`--openapi-path none`)", "endpoints added after setup are found only by static detection")],
            f"{len(live)} framework-default document route(s): " + ", ".join(f"{f.value} ({f.source})"
                                                                                for f in live[:3]),
            "whether staging exposes the document (many apps serve it only in Development)"))
    return out


# --------------------------------------------------------------------------
# setup: config and ledger writes (owner-confirmed only)
# --------------------------------------------------------------------------

class SetupError(ValueError):
    pass


def load_config(root):
    path = os.path.join(root, CONFIG_NAME)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        try:
            doc = json.load(fh)
        except ValueError as exc:
            raise SetupError(f"{CONFIG_NAME} is not valid JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise SetupError(f"{CONFIG_NAME} is not a JSON object")
    return doc


def grouped_endpoints(findings, accept):
    """One committed entry per normalised path, from findings at or above the
    accepted confidence. Ledger-sourced findings are left out: the ledger is
    already the committed record for those."""
    floor = _RANK[accept]
    groups = {}
    for f in findings:
        if f.kind != "endpoint" or f.detector == "crew-ledger" or not f.value.startswith("/") \
                or _RANK[f.confidence] < floor:
            continue
        key = normalise_path(f.value)
        g = groups.setdefault(key, {"path": key, "methods": set(), "confidence": f.confidence,
                                    "source": f.source, "protected": False})
        if f.method:
            g["methods"].add(f.method)
        g["protected"] = g["protected"] or f.protected
        if _RANK[f.confidence] > _RANK[g["confidence"]]:
            g["confidence"], g["source"] = f.confidence, f.source
    return [dict(g, methods=sorted(g["methods"])) for _, g in sorted(groups.items())]


def build_config(det, staging_url, auth_mode, accept, include=(), exclude=(), scope_all=False,
                 openapi_path=None, auth_header="Authorization"):
    if staging_url is None:
        raise SetupError("--staging-url is required: a URL the owner named, or 'none' for code scans only")
    if auth_mode not in AUTH_MODES:
        raise SetupError(f"--auth must be one of {', '.join(AUTH_MODES)}")
    if accept not in _RANK:
        raise SetupError("--accept must be high, medium or low")
    if not scope_all and not include and not exclude:
        raise SetupError("scope is not decided: pass --scope all, or --include/--exclude patterns")
    if scope_all and (include or exclude):
        raise SetupError("--scope all cannot be combined with --include/--exclude")
    base = None
    if staging_url.lower() != "none":
        if "${{" in staging_url or not re.fullmatch(r"https?://[^\s]+", staging_url):
            raise SetupError(f"staging URL {staging_url!r} is not an http(s) URL")
        base = staging_url.rstrip("/")
    if openapi_path and openapi_path.lower() != "none":
        if not openapi_path.startswith("/") or any(c.isspace() for c in openapi_path) or "://" in openapi_path:
            raise SetupError("--openapi-path must be a path on the staging origin, like /swagger/v1/swagger.json")
        live = openapi_path
    else:
        live = None
    if auth_mode == "header" and not re.fullmatch(r"[A-Za-z0-9-]+", auth_header or ""):
        raise SetupError("--auth-header must be a header name")
    store = LEDGER_REL if det.crew_present else CONFIG_NAME
    endpoints = grouped_endpoints(det.findings, accept)
    config = {
        "schema": CONFIG_SCHEMA,
        "staging": {"base_url": base, "openapi_path": live},
        "auth": {"mode": auth_mode, **({"header": auth_header, "secret": AUTH_SECRET}
                                       if auth_mode == "header" else {})},
        "scope": {"include": sorted(set(include)), "exclude": sorted(set(exclude))},
        "accept": accept,
        "endpoints_store": store,
        "endpoints": [] if det.crew_present else endpoints,
    }
    return config, (endpoints if det.crew_present else [])


def config_text(config):
    return json.dumps(config, indent=2, sort_keys=True) + "\n"


def ledger_additions(root, endpoints):
    """The declared records `apply_ledger` would append: accepted endpoints not
    already present (by endpoint string), in path order."""
    path = os.path.join(root, LEDGER_REL)
    doc = {"records": [], "nextSeq": 0}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            try:
                doc = json.load(fh)
            except ValueError as exc:
                raise SetupError(f"{LEDGER_REL} is not valid JSON; fix it before setup writes to it: {exc}") \
                    from exc
    have = {str(r.get("endpoint")) for r in doc.get("records") or [] if isinstance(r, dict)}
    return [e for e in endpoints if e["path"] not in have]


def apply_ledger(root, endpoints, now):
    """Append owner-confirmed endpoints to crew's ledger with crew's own writer
    semantics (crew_endpoints.declare_endpoint): `source: "declared"`, status
    open, ids minted from the persisted `nextSeq`, an O_EXCL lock across the
    read-modify-write, and an atomic temp-file replace. This is the only
    path in gizmoduck that writes `source: "declared"`, and setup reaches it
    only with --apply after the owner confirmed the list."""
    path = os.path.join(root, LEDGER_REL)
    lock = path + ".lock"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
    except FileExistsError as exc:
        raise SetupError(f"{LEDGER_REL}.lock exists - another writer holds the ledger; retry") from exc
    try:
        doc = {"records": [], "nextSeq": 0}
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        records = [r for r in doc.get("records") or [] if isinstance(r, dict)]
        seq = doc.get("nextSeq")
        seq = seq if isinstance(seq, int) and not isinstance(seq, bool) and seq >= 0 else 0
        have = {str(r.get("endpoint")) for r in records}
        added = []
        for e in endpoints:
            if e["path"] in have:
                continue
            seq += 1
            rec = {"id": f"ep-{seq:04d}", "endpoint": e["path"], "source": "declared", "status": "open",
                   "location": e["source"], "ticket": None, "createdAt": now}
            records.append(rec)
            added.append(rec)
            have.add(e["path"])
        text = json.dumps({"records": records, "nextSeq": seq}, indent=2, sort_keys=True) + "\n"
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
        return added
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass


# --------------------------------------------------------------------------
# per-run merge
# --------------------------------------------------------------------------

def _in_scope(path, scope):
    include, exclude = scope.get("include") or [], scope.get("exclude") or []
    if include and not any(fnmatch.fnmatchcase(path, p) for p in include):
        return False
    return not any(fnmatch.fnmatchcase(path, p) for p in exclude)


def merge_for_run(config, ledger_doc, det, live_ops=()):
    """The endpoint list one pipeline run scans: the committed list (the
    config's endpoints plus the crew ledger's open records) merged with what
    detection and the live OpenAPI document see now. Anything not committed
    is scanned AND listed under `new`. Zero endpoints after scope filtering is
    status UNVERIFIED, which every caller treats as a failure."""
    config = config or {}
    scope = config.get("scope") or {}
    auth = config.get("auth") or {"mode": "none"}
    entries = {}

    def add(key, endpoint, origin, committed, conf, source, protected=False, method=""):
        e = entries.setdefault(key, {"path": key, "endpoint": endpoint, "origins": set(), "committed": False,
                                     "confidence": conf, "source": source, "protected": False,
                                     "methods": set()})
        e["origins"].add(origin)
        e["committed"] = e["committed"] or committed
        e["protected"] = e["protected"] or protected
        if method:
            e["methods"].add(method)
        if _RANK.get(conf, 0) > _RANK.get(e["confidence"], 0):
            e["confidence"], e["source"] = conf, source

    for c in config.get("endpoints") or []:
        if isinstance(c, dict) and isinstance(c.get("path"), str):
            key = normalise_path(c["path"])
            add(key, scan_path(key), "committed", True, c.get("confidence", HIGH), c.get("source", CONFIG_NAME),
                bool(c.get("protected")))
    for n, rec in enumerate((ledger_doc or {}).get("records") or [], 1):
        if not isinstance(rec, dict) or str(rec.get("status", "")).lower() == "closed":
            continue
        value = rec.get("endpoint")
        if not isinstance(value, str) or not value.strip() or any(ch.isspace() for ch in value.strip()):
            continue
        value = value.strip()
        key = normalise_path(value) if value.startswith("/") else value
        add(key, scan_path(value) if value.startswith("/") else value, "crew-ledger", True, HIGH,
            f"{LEDGER_REL}:{rec.get('id') or n}")
    for f in det.of("endpoint") if det is not None else []:
        if f.detector == "crew-ledger":
            continue
        key = normalise_path(f.value) if f.value.startswith("/") else f.value
        add(key, scan_path(f.value) if f.value.startswith("/") else f.value, "detected", False, f.confidence,
            f.source, f.protected, f.method)
    for method, path, protected in live_ops:
        key = normalise_path(path)
        add(key, scan_path(key), "live-openapi", False, HIGH, "live OpenAPI", protected, method)

    kept, excluded = [], []
    for key in sorted(entries):
        e = entries[key]
        e = dict(e, origins=sorted(e["origins"]), methods=sorted(e["methods"]), new=not e["committed"])
        del e["committed"]
        path_for_scope = key if key.startswith("/") else (urllib.parse.urlsplit(key).path or "/")
        if not _in_scope(path_for_scope, scope):
            excluded.append(dict(e, reason="outside include/exclude scope"))
        elif auth.get("mode") == "exclude-protected" and e["protected"]:
            excluded.append(dict(e, reason="protected, and auth mode is exclude-protected"))
        else:
            kept.append(e)
    status, reason = "OK", ""
    if not kept:
        status = "UNVERIFIED"
        reason = (f"every endpoint is excluded by scope or auth mode ({len(excluded)} excluded) - {DETECT_HINT}"
                  if excluded else f"no endpoints are committed, declared or detected - {DETECT_HINT}")
    return {"status": status, "reason": reason, "auth": auth, "endpoints": kept,
            "new": [e for e in kept if e["new"]], "excluded": excluded}


def render_run_report(run, live_note=""):
    lines = [f"## gizmoduck endpoints: {run['status']}", ""]
    if run["status"] != "OK":
        lines += [f"**UNVERIFIED** - {run['reason']}. The endpoint stage fails rather than passing an empty "
                  f"scan.", ""]
    lines.append(f"- {len(run['endpoints'])} endpoint(s) to scan, {len(run['new'])} new, "
                 f"{len(run['excluded'])} excluded")
    if live_note:
        lines.append(f"- live OpenAPI: {live_note}")
    if run["new"]:
        lines += ["", "### New - scanned, not in the committed list (new, confirm at next setup)"]
        for e in run["new"]:
            lines.append(f"- `{' '.join(e['methods']) + ' ' if e['methods'] else ''}{e['path']}` "
                         f"[{e['confidence']}] {e['source']} - new, confirm at next setup")
    return "\n".join(lines) + "\n"
