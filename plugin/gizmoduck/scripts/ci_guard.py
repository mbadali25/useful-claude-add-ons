"""ci_guard.py - the prod-refusal guard for `/gizmoduck:ci` endpoint scans.

Every endpoint-scan target passes through `check_target` twice: once when the
pipeline is rendered (gizmoduck_ci.py render), and again as a runtime step in
the pipeline itself, before any scanner starts. The rules, in the order they
are applied:

  R1 scheme     - only http and https. No other scheme is a web endpoint.
  R2 shape      - no whitespace (ASCII or Unicode: NBSP, ideographic space,
                  line/paragraph separators), control or format characters
                  (zero-width space, bidi marks) or backslashes anywhere in the
                  URL - including at either end: an input is refused, never
                  stripped into something else. A parser and a scanner that
                  disagree about where the host ends is how a lookalike gets
                  through.
  R3 userinfo   - any `user@` / `user:pass@` part is refused outright.
                  `https://staging.example.com@evil.test` has host evil.test.
                  So is a query parameter whose name says it carries a
                  credential (token, key, secret, password, signature, ...):
                  a scan target is logged and uploaded as an artifact, and a
                  credential in it would be too.
  R4 host       - lower-cased, trailing dots stripped, IDNA-encoded to its
                  ASCII (punycode) form. A host that will not encode is refused.
  R5 port       - explicit or scheme default; must be 1-65535. It is part of
                  the origin, so :8443 is a different origin from :443.
  R6 literal    - an IP literal (any form `inet_aton` accepts, so `127.1` and
                  `0x7f000001` too, plus IPv6) or `localhost` / `*.localhost`
                  is refused unless its exact origin is in the IP allow-list,
                  even when it is also configured as a staging origin.
  R7 staging    - the normalised origin (scheme, host, port) must equal one of
                  the configured staging origins exactly. Not a suffix match,
                  not a prefix match: `staging.example.com.evil.test` fails.
  R8 production - an origin on the production allow-list is scanned only when
                  the second opt-in is also set. Either one alone refuses. An
                  origin on BOTH the staging and the production list is
                  production: listing it as staging does not waive the opt-in.
  R9 redirects  - `check_redirects` follows the chain hop by hop without
                  letting the HTTP client follow it, and re-applies R1-R8 to
                  every Location. A hop to a non-allowed origin refuses the
                  whole target, as does a chain longer than `max_hops`.
                  That probe is a pre-check, NOT the redirect control: a
                  server can answer a probe and a scanner differently (by
                  User-Agent or method). The control is that every endpoint
                  scanner runs with redirects disabled or scope-restricted to
                  the target origin (gizmoduck_ci.endpoint_manifest), and
                  `audit_findings` re-checks the origin of every URL the
                  scanners recorded, after the scan, and fails the stage if
                  any left the policy.

`redact_url` / `redact_text` are how a URL reaches a log or an artifact:
userinfo becomes `***@` and credential-named query values become `***`, the
name judged after percent-decoding; a query that decodes ambiguously (an
encoded `=` or `&`, or a double encoding) is replaced whole by `***`.

Stdlib only, like the rest of scripts/. The fetcher used for R9 is injectable
so tests never make a network call.
"""
import ipaddress
import re
import socket
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

_DEFAULT_PORTS = {"http": 80, "https": 443}
_FORBIDDEN_CHARS = set(" \t\r\n\\") | {chr(c) for c in range(0x20)} | {"\x7f"}
_SECRET_PARAM = re.compile(r"(?i)(token|secret|passw(or)?d|pwd|api[_-]?key|access[_-]?key|auth|"
                           r"credential|signature|session|jwt|private|^sig$|^key$|^code$)")
_URL_IN_TEXT = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s\"'<>]+")


def bad_char(ch):
    """Whitespace of any script, control, format (zero-width, bidi) and
    separator characters, and the backslash."""
    return ch in _FORBIDDEN_CHARS or ch.isspace() or unicodedata.category(ch)[0] in ("C", "Z")


def secret_param(name):
    """True for a query parameter whose name says it carries a credential."""
    return bool(_SECRET_PARAM.search(urllib.parse.unquote_plus(name or "")))


def redact_url(url):
    """`url` safe to print or store: userinfo -> `***@`, credential-named query
    values -> `***`. Never raises."""
    if not isinstance(url, str):
        return url
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        # Unparseable: userinfo masked, and the whole query with it.
        return re.sub(r"\?.*", "?***", re.sub(r"//[^/?#]*@", "//***@", url), flags=re.S)
    netloc = parts.netloc
    if "@" in netloc:
        netloc = "***@" + netloc.rsplit("@", 1)[1]
    return urllib.parse.urlunsplit((parts.scheme, netloc, parts.path, _redact_query(parts.query),
                                    parts.fragment))


_ENCODED = re.compile(r"%[0-9A-Fa-f]{2}")
_NESTED_SECRET = re.compile(r"(?i)(?:^|[?&;#])([^=&;?#]*)=")


def _redact_query(query):
    """Credential-named values -> `***`, judged on the percent-DECODED key, so
    `access%5Ftoken=` and `access_token%3DSECRET` are caught too. A value whose
    decoded form is itself a query or URL carrying a credential (`next=%2F%3F
    token%3D...`, `cb=https://u:p@...`) is masked whole. When a piece does not
    split the same way before and after decoding - an encoded `=` or `&`, or
    something still encoded after one decode - the whole query is `***`: a
    parse that can be read two ways is not one to leave half-redacted."""
    if not query:
        return query
    pieces = []
    for piece in query.split("&"):
        name, sep, value = piece.partition("=")
        dname = urllib.parse.unquote_plus(name)
        dvalue = urllib.parse.unquote_plus(value)
        if any(c in dname for c in "=&") or _ENCODED.search(dname) \
                or "&" in dvalue or _ENCODED.search(dvalue):
            return "***"
        if secret_param(dname):
            pieces.append(f"{name}=***" if sep else "***")
        elif "@" in dvalue or any(secret_param(k) for k in _NESTED_SECRET.findall(dvalue)):
            pieces.append(f"{name}=***")
        else:
            pieces.append(piece)
    return "&".join(pieces)


def redact_text(text):
    """Every URL inside free text (a refusal reason, a log line) redacted."""
    if not isinstance(text, str):
        return text
    return _URL_IN_TEXT.sub(lambda m: redact_url(m.group(0)), text)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    rule: str
    reason: str
    origin: str = ""


class GuardError(ValueError):
    """A URL that cannot be normalised at all - carries the rule it broke."""

    def __init__(self, rule, reason):
        super().__init__(reason)
        self.rule = rule
        self.reason = reason


def _normalise_host(raw_host):
    host = (raw_host or "").strip().lower().rstrip(".")
    if not host:
        raise GuardError("R4", "no host")
    if host.startswith("[") and host.endswith("]"):
        inner = host[1:-1]
        try:
            return str(ipaddress.IPv6Address(inner)), True
        except ValueError as exc:
            raise GuardError("R4", f"unparseable IPv6 literal {raw_host!r}") from exc
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise GuardError("R4", f"host {raw_host!r} does not IDNA-encode") from exc
    ascii_host = ascii_host.lower().rstrip(".")
    return ascii_host, _is_ip_literal(ascii_host)


def _is_ip_literal(host):
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    try:
        socket.inet_aton(host)
        return True
    except OSError:
        return False


def _is_localhost(host):
    return host == "localhost" or host.endswith(".localhost")


def normalise_origin(url):
    """(origin_string, is_ip_or_localhost) for `url`, or GuardError.

    The origin string is `scheme://host:port` with the port always explicit,
    so two spellings of one origin compare equal and two different ports never
    do.
    """
    if not isinstance(url, str) or not url:
        raise GuardError("R2", "empty URL")
    if any(bad_char(ch) for ch in url):
        raise GuardError("R2", f"URL contains whitespace (ASCII or Unicode), a control or format character "
                               f"or a backslash - refused, not stripped: {redact_url(url)!r}")
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError as exc:
        # `https://[broken` - urlsplit raises on an unbalanced bracketed host.
        raise GuardError("R4", f"unparseable host in {redact_url(url)!r}") from exc
    scheme = parts.scheme.lower()
    if scheme not in _DEFAULT_PORTS:
        raise GuardError("R1", f"scheme {parts.scheme or '(none)'!r} is not http or https")
    netloc = parts.netloc
    if "@" in netloc:
        raise GuardError("R3", f"URL carries a userinfo part ({redact_url(url)!r}); refused outright")
    # parse_qsl decodes, so `access_token%3DSECRET` arrives as the NAME
    # `access_token=SECRET`: only the part before a decoded `=` is echoed.
    leaked = sorted({name.partition("=")[0].partition("&")[0]
                     for name, _v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
                     if secret_param(name)})
    if leaked:
        raise GuardError("R3", f"URL carries a credential-named query parameter ({', '.join(leaked)}); a "
                               f"scan target is logged and uploaded, so it is refused outright")
    try:
        port = parts.port
    except ValueError as exc:
        raise GuardError("R5", f"invalid port in {netloc!r}") from exc
    if port is None:
        port = _DEFAULT_PORTS[scheme]
    if not 1 <= port <= 65535:
        raise GuardError("R5", f"port {port} out of range")
    raw_host = parts.hostname
    if netloc.startswith("["):
        raw_host = "[" + (parts.hostname or "") + "]"
    host, is_ip = _normalise_host(raw_host)
    shown = f"[{host}]" if ":" in host else host
    return f"{scheme}://{shown}:{port}", (is_ip or _is_localhost(host))


def _origin_set(urls):
    """Normalise a list of configured origins. A configured value that does
    not normalise is a configuration error, not something to skip past."""
    out = set()
    for u in urls or ():
        if not u:
            continue
        origin, _ = normalise_origin(u)
        out.add(origin)
    return out


@dataclass(frozen=True)
class Policy:
    staging: frozenset
    production: frozenset = frozenset()
    allow_production: bool = False
    ip_allowed: frozenset = frozenset()

    @classmethod
    def build(cls, staging_urls, production_urls=(), allow_production=False,
              ip_allowed_urls=()):
        staging = _origin_set(staging_urls)
        if not staging:
            raise GuardError("R7", "no staging origin configured; refusing every target")
        return cls(staging=frozenset(staging),
                   production=frozenset(_origin_set(production_urls)),
                   allow_production=bool(allow_production),
                   ip_allowed=frozenset(_origin_set(ip_allowed_urls)))


def check_target(url, policy):
    """Apply R1-R8 to one URL. Never raises; a refusal is a Decision."""
    try:
        origin, literal = normalise_origin(url)
    except GuardError as exc:
        return Decision(False, exc.rule, exc.reason)
    if literal and origin not in policy.ip_allowed:
        return Decision(False, "R6", f"{origin} is an IP literal or localhost and is not "
                                     f"on the IP allow-list", origin)
    # Production first: an origin listed as both staging and production is
    # production, and listing it as staging must not waive the second opt-in.
    if origin in policy.production:
        if policy.allow_production:
            return Decision(True, "R8", f"{origin} is an allow-listed production origin and "
                                        f"the production opt-in is set", origin)
        return Decision(False, "R8", f"{origin} is on the production allow-list but the "
                                     f"second opt-in (GIZMODUCK_ALLOW_PROD_SCAN=true) is "
                                     f"not set", origin)
    if origin in policy.staging:
        return Decision(True, "R7", f"{origin} is a configured staging origin", origin)
    if literal:
        # IP-allow-listed but neither staging nor production: the IP list
        # lifts R6 only, it never makes an origin a target on its own.
        return Decision(False, "R7", f"{origin} is IP-allow-listed but is not a configured "
                                     f"staging origin", origin)
    return Decision(False, "R7", f"{origin} is not under any configured staging origin", origin)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_fetch(url, timeout=10.0):
    """(status, Location header or None) for one request, redirects NOT followed."""
    opener = urllib.request.build_opener(_NoRedirect())
    req = urllib.request.Request(url, method="GET",
                                 headers={"User-Agent": "gizmoduck-ci-guard"})
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.status, resp.headers.get("Location")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Location") if exc.headers else None


def check_redirects(url, policy, fetch=http_fetch, max_hops=5):
    """R9. Walk the redirect chain from `url` and refuse if any hop leaves the
    allowed set. `url` itself must already have passed check_target."""
    first = check_target(url, policy)
    if not first.allowed:
        return first
    current = url
    for _ in range(max_hops + 1):
        try:
            status, location = fetch(current)
        except (OSError, ValueError) as exc:
            return Decision(False, "R9", f"could not probe {redact_url(current)} for redirects: "
                                         f"{redact_text(str(exc))}", first.origin)
        if not (300 <= int(status) < 400) or not location:
            return Decision(True, "R9", f"redirect chain from {redact_url(url)} stays on allowed "
                                        f"origins", first.origin)
        nxt = urllib.parse.urljoin(current, location)
        hop = check_target(nxt, policy)
        if not hop.allowed:
            return Decision(False, "R9", f"{redact_url(current)} redirects to {redact_url(nxt)}, "
                                         f"which is refused: {hop.reason}", first.origin)
        current = nxt
    return Decision(False, "R9", f"more than {max_hops} redirects from {redact_url(url)}; refused",
                    first.origin)


_RECORDED_URL_FIELDS = ("matched_at", "matched-at", "url", "host")


def audit_findings(records, policy):
    """The after-the-scan half of R9: the ORIGIN of every http(s) URL a scanner
    recorded in a finding must still pass check_target. Returns
    [(field, redacted url, Decision)] for each one that does not - a scanner
    that reached an origin outside the policy, by a redirect or otherwise,
    fails the stage even though the pre-scan probe passed. Only the origin is
    judged (a fuzzing payload in a path or query is not a different target);
    a value that is not an http(s) URL (nmap and testssl record host:port) is
    not a request to a URL and is skipped."""
    bad = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        for fld in _RECORDED_URL_FIELDS:
            value = rec.get(fld)
            if not isinstance(value, str) or not re.match(r"(?i)https?://", value):
                continue
            try:
                parts = urllib.parse.urlsplit(value)
                origin_url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, "/", "", ""))
            except ValueError:
                origin_url = value
            d = check_target(origin_url, policy)
            if not d.allowed:
                bad.append((fld, redact_url(value), d))
    return bad
