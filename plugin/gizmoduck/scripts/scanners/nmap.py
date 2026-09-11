"""Nmap adapter - `-oX <file> -sV <host>` runs by default; `--script vuln`
only when the target opts in via `opts["nmap_vuln"]`.

ACTIVE is False at the module level: base version/port scanning is not
intrusive. The `vuln` NSE opt-in is a per-run option, not the registry-level
ACTIVE/DEFAULT_ENABLED gate - it is expressed instead through ACTIVE_OPTS (see
the plan's Global Constraints note on two-mode adapters). `routine` must treat
this adapter as active whenever "nmap_vuln" is set for a target, and must
record which mode actually ran (`ran(safe)` vs `ran(safe+vuln)`) rather than a
bare `ran` - a bare `ran` would imply vulnerability coverage a safe-only scan
never attempted.

Nmap is also the one tool in this whole set whose exit code is a trustworthy
success signal (0 on a completed scan regardless of findings, non-zero only
on an nmap-level error - spec 13.12). That is unusual enough among the nine
adapters that it is called out here explicitly: run() below gates on
`result.returncode` for exactly this reason, but no other adapter should.

Parser note: the exact <table>/<elem key=...> nesting vulns.lua emits is
"secondhand" per spec 13.11 - nmap is not installed in this environment, so
`_vuln_tables` below was written against the documented shape only and has
NOT been verified against a real `nmap --script vuln -oX` run. Lock it
against real output before relying on it in production; see
scripts/_test/fixtures/nmap.xml for the caveat repeated at the fixture.
"""
import os
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

from . import base
import normalize

NAME = "nmap"
KINDS = ["web", "host"]
ACTIVE = False
ACTIVE_OPTS = ["nmap_vuln"]
DEFAULT_ENABLED = True

# vulns.lua's confirmed machine-readable state values (spec 13.11), mapped to
# a severity keyword and then routed through normalize.sev_from_text so the
# int<->name mapping stays in the one shared table rather than a second copy
# here. "not vulnerable" is deliberately absent: it is never emitted as a
# finding (it only appears at all when a script sets vulns.showall, which
# this adapter never does) - a stray "not vulnerable" table is skipped, not
# mapped to info.
_VULN_STATE_SEVERITY = {
    "vulnerable (exploitable)": "critical",
    "vulnerable (dos)": "high",
    "vulnerable": "high",
    "likely vulnerable": "medium",
}


def is_available():
    return base.which("nmap") is not None


def _target_host(target):
    """Extract a bare host/IP for nmap's positional target argument.

    Accepts a plain string (so this adapter is testable without importing
    routine.py's Target dataclass), or an object exposing .host (host-kind
    targets) or .url (web-kind targets, per the manifest shape in the plan).
    """
    if isinstance(target, str):
        return target
    host = getattr(target, "host", None)
    if host:
        return host
    url = getattr(target, "url", None)
    if url:
        parsed = urlparse(url)
        return parsed.hostname or parsed.netloc or url
    raise ValueError("nmap target has neither .host nor .url: %r" % (target,))


def _opt(opts, key, default=None):
    if opts is None:
        return default
    getter = getattr(opts, "get", None)
    if callable(getter):
        return getter(key, default)
    return getattr(opts, key, default)


def run(target, outdir, opts=None):
    """Run the safe -sV scan, adding --script vuln only when opted in.

    Returns (raw_path, result) per the pinned adapter contract (spec 13.14):
    (path, ToolResult) on success, (None, ToolResult) when nmap did not
    complete - and the ToolResult is always returned either way, since it is
    routine's only source for error:timeout / error:<message> in the run
    manifest. Nmap is the one adapter in this set allowed to gate on
    returncode (spec 13.12: 0 is a trustworthy "scan completed" signal here,
    unlike every other tool) - a non-zero or timed-out run means -oX's file
    is absent or incomplete, so raw_path is withheld rather than handed to
    parse() against a file that may not parse.

    base.run_tool's own timeout is the real guard on total wall-clock -
    nmap's --host-timeout/--script-timeout cap per-host and per-script, not
    the whole run (spec 13.13), so no reliance is placed on those flags here.

    Mode reporting: this function does not echo back whether --script vuln
    ran, because routine.py already has that answer - it is the one that
    built `opts` and decided whether to set opts["nmap_vuln"] before calling
    run(). ToolResult tells routine whether the invocation it asked for
    succeeded; routine combines that with its own opts["nmap_vuln"] value to
    write ran(safe) vs ran(safe+vuln) into the coverage table. Widening
    ToolResult itself to carry mode is deliberately avoided since it is
    shared, already-committed foundation code every adapter returns.
    """
    host = _target_host(target)
    raw_path = os.path.join(outdir, "nmap.xml")
    argv = ["nmap", "-oX", raw_path, "-sV"]
    if _opt(opts, "nmap_vuln", False):
        argv += ["--script", "vuln"]
    argv.append(host)
    result = base.run_tool(argv, timeout=_opt(opts, "timeout", 600))
    if result.timed_out or result.returncode != 0:
        return None, result
    return raw_path, result


def _elem_text(table_el, key):
    """Direct-child <elem key="..."> lookup only - deliberately not
    recursive, so a nested table's own elem (e.g. a "year" inside a "dates"
    sub-table) can never be mistaken for this table's own state/title.
    """
    for el in table_el.findall("elem"):
        if el.get("key") == key:
            return (el.text or "").strip()
    return ""


def _vuln_tables(script_el):
    """Yield every <table> under a <script> that represents one vulns.lua
    finding - i.e. carries a direct elem key="state" child. Walks every
    descendant table rather than assuming a fixed nesting depth, since the
    exact shape is unconfirmed (spec 13.11): nested tables like "ids" or
    "dates" never have their own state elem, so they are never yielded.
    """
    for table in script_el.iter("table"):
        if _elem_text(table, "state"):
            yield table


def parse(raw_path, target):
    """Pure parse: no subprocess, no network. Reads nmap's -oX output and
    returns findings for every open port (info) plus one additional, separate
    finding per vulns.lua table found in that port's <script> children.
    """
    tree = ET.parse(raw_path)
    root = tree.getroot()
    findings = []

    for host_el in root.findall("host"):
        addr_el = host_el.find("address")
        host_ip = addr_el.get("addr") if addr_el is not None else ""
        ports_el = host_el.find("ports")
        if ports_el is None:
            continue

        for port_el in ports_el.findall("port"):
            state_el = port_el.find("state")
            if state_el is None or state_el.get("state") != "open":
                continue

            proto = port_el.get("protocol", "")
            portid = port_el.get("portid", "")
            service_el = port_el.find("service")
            service_name = service_el.get("name", "") if service_el is not None else ""
            product = service_el.get("product", "") if service_el is not None else ""
            version = service_el.get("version", "") if service_el is not None else ""
            svc_desc = " ".join(p for p in (product, version) if p)
            matched_at = "%s:%s" % (host_ip, portid)

            # An open port with no <script> child yields exactly this one
            # info finding - the port/service discovery itself, not a
            # vulnerability assessment, so severity_known stays True.
            findings.append(normalize.make_finding(
                tool=NAME,
                target=target,
                rule_id="open-port/%s/%s" % (proto, portid),
                name="Open port %s/%s (%s)" % (portid, proto, service_name or "unknown"),
                severity=0,
                type="port",
                host=host_ip,
                matched_at=matched_at,
                description=("%s %s" % (service_name, svc_desc)).strip(),
            ))

            for script_el in port_el.findall("script"):
                for vt in _vuln_tables(script_el):
                    state_text = _elem_text(vt, "state").strip().lower()
                    if state_text == "not vulnerable":
                        continue
                    sev_word = _VULN_STATE_SEVERITY.get(state_text)
                    severity, known = normalize.sev_from_text(sev_word, default="medium")
                    title = _elem_text(vt, "title") or script_el.get("id", "")
                    description = _elem_text(vt, "description")
                    tags = [script_el.get("id")] if script_el.get("id") else []

                    # A <script> carrying a structured <table> yields its
                    # own separate finding at the mapped severity, in
                    # addition to the port's info finding above.
                    findings.append(normalize.make_finding(
                        tool=NAME,
                        target=target,
                        rule_id=vt.get("key") or script_el.get("id", ""),
                        name=title,
                        severity=severity,
                        severity_known=known,
                        type="vuln",
                        host=host_ip,
                        matched_at=matched_at,
                        description=description,
                        tags=tags,
                    ))

    return findings
