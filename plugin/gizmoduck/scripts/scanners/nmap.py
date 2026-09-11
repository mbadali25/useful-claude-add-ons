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

vulns.lua field coverage: the library's documented fields are title, state,
IDS, risk_factor, scores, description, dates, check_results, exploit_results,
extra_info, references. This parser reads title, state, description, IDS,
scores and references - the ones that have a home in the finding shape (cve,
cvss, reference respectively). `cve` comes only from the IDS table's "CVE:"
entries, never inferred from the outer <table key=...> attribute - that
attribute happens to look like a CVE in real vulns.lua output but is not
guaranteed to be one, and a wrong CVE is worse than none. risk_factor is
read nowhere: state is already a reliable enum for severity and mixing in a
second severity source without a real scan to confirm how the two agree
would trade a working signal for an unverified one. dates, check_results,
exploit_results and extra_info have no field in the finding shape and are
deliberately left unread rather than inventing one. Any of the fields this
parser does read are omitted (not guessed) when the source table is absent
or malformed - see _cve_ids_from_table / _cvss_from_table /
_references_from_table / _description_from_table below.

Two lookup shapes exist and must not be confused: title and state are
direct <elem key="..."> children of the vuln table (read via _elem_text),
while ids, scores, references and description are each their own nested
<table key="..."> (read via _direct_child_table plus a per-field helper).
description was originally read as if it were the first shape, which left
it silently "" on every finding - the same mistake QA later caught for
ids/scores/references, just not caught for description until a second
pass. Confirmed correct for title/state - see test_finding_name_comes_
from_the_title_elem.
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


def _direct_child_table(parent, key):
    """Direct-child <table key="..."> lookup - the table-shaped counterpart
    to _elem_text's direct-child-only <elem> lookup, and deliberately not
    recursive for the same reason: nothing here should reach past one level
    and pick up some other table's same-named child by accident.
    """
    for t in parent.findall("table"):
        if t.get("key") == key:
            return t
    return None


def _cve_ids_from_table(vt):
    """vulns.lua's IDS table holds anonymous <elem> entries shaped
    "TYPE:VALUE" (spec 13.11 names IDS among the library's fields; the
    "CVE:CVE-xxxx-xxxx" element text is the documented form). Only entries
    prefixed "CVE:" are kept, and only the value after that prefix.

    This is the one thing this function must never do: infer a CVE from the
    outer <table key=...> attribute (e.g. "CVE-2014-3566" on the enclosing
    vulnerability table). That attribute merely happens to look like a CVE
    in real vulns.lua output - it is not guaranteed to be one, and a wrong
    CVE on a real finding is worse than none, since it sends a reader to the
    wrong advisory. An absent or malformed ids table yields [], never a
    guess.
    """
    ids_table = _direct_child_table(vt, "ids")
    if ids_table is None:
        return []
    cves = []
    for el in ids_table.findall("elem"):
        text = (el.text or "").strip()
        if text[:4].upper() == "CVE:":
            cve_id = text[4:].strip()
            if cve_id:
                cves.append(cve_id)
    return cves


def _cvss_from_table(vt):
    """vulns.lua's scores table carries a CVSS numeric score as
    <elem key="CVSS">. Returned as a float, matching every other adapter's
    `cvss` convention (see trivy.py's _first_cvss) - "" when the table is
    absent or its value does not parse as a number, never a guess.
    """
    scores_table = _direct_child_table(vt, "scores")
    if scores_table is None:
        return ""
    raw = _elem_text(scores_table, "CVSS")
    if not raw:
        return ""
    try:
        return float(raw)
    except ValueError:
        return ""


def _references_from_table(vt):
    """vulns.lua's references table holds anonymous <elem> entries, each one
    whole reference string (typically a URL). Absent table -> [], never
    fabricated from anything else on the finding.
    """
    refs_table = _direct_child_table(vt, "references")
    if refs_table is None:
        return []
    return [text for text in
            ((el.text or "").strip() for el in refs_table.findall("elem"))
            if text]


def _description_from_table(vt):
    """vulns.lua's description table holds one or more anonymous <elem>
    entries - the same nesting shape as ids/scores/references, not a direct
    <elem key="description"> child of the vuln table. (A lookup written for
    that wrong shape previously left `description` silently "" on every
    finding.) Multiple elem children join with a blank line; absent table
    -> "", never fabricated.
    """
    desc_table = _direct_child_table(vt, "description")
    if desc_table is None:
        return ""
    parts = [text for text in
             ((el.text or "").strip() for el in desc_table.findall("elem"))
             if text]
    return "\n\n".join(parts)


def _append_vuln_findings(findings, script_el, target, host_ip, matched_at):
    """Shared by port-level and host-level script handling: walk a <script>
    element's vulns.lua tables and append one finding per state that is not
    "not vulnerable". Factored out so host/hostscript/script gets the exact
    same severity mapping, tagging and field enrichment as port/script - the
    QA-caught defect was this code path silently never existing for
    host-level scripts, not a mismatch between two divergent copies of it.
    """
    for vt in _vuln_tables(script_el):
        state_text = _elem_text(vt, "state").strip().lower()
        if state_text == "not vulnerable":
            continue
        sev_word = _VULN_STATE_SEVERITY.get(state_text)
        severity, known = normalize.sev_from_text(sev_word, default="medium")
        title = _elem_text(vt, "title") or script_el.get("id", "")
        description = _description_from_table(vt)
        tags = [script_el.get("id")] if script_el.get("id") else []

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
            cve=_cve_ids_from_table(vt),
            cvss=_cvss_from_table(vt),
            reference=_references_from_table(vt),
        ))


def parse_errors(raw_path, target):
    """Return a scan-error record for every host nmap reported DOWN.

    A host that did not respond is not a clean scan - nmap ran, but the
    target was unreachable, so `parse()` legitimately finds no ports and
    returns []. Left unsurfaced, that reads in the coverage table exactly
    like "scanned, nothing found" for a host that was up. This channel
    (which routine folds into the run manifest, the same way it does
    testssl's WARN/FATAL) makes "target unreachable" distinct from "clean",
    shaped nothing like a finding so it can never be mistaken for one.

    Lenient by design: parse() owns raising on malformed XML, so a shape
    this secondary reader cannot handle simply yields no error records
    rather than masking parse()'s own ParseError.
    """
    errors = []
    try:
        root = ET.parse(raw_path).getroot()
    except (ET.ParseError, OSError):
        return errors
    if root.tag != "nmaprun":
        return errors
    for host_el in root.findall("host"):
        status = host_el.find("status")
        if status is not None and status.get("state") == "down":
            addr_el = host_el.find("address")
            errors.append({
                "tool": NAME,
                "target": target,
                "severity": "error",
                "message": "host reported down (%s) - target unreachable, not scanned"
                           % (status.get("reason") or "no-response"),
                "host": addr_el.get("addr") if addr_el is not None else "",
            })
    return errors


def parse(raw_path, target):
    """Pure parse: no subprocess, no network. Reads nmap's -oX output and
    returns findings for every open port (info), one additional, separate
    finding per vulns.lua table found in that port's <script> children, and
    the same for any <script> found under the host's own <hostscript>
    element (host/hostscript/script, a sibling of <ports> rather than a
    child of any one <port>).

    Many `--script vuln` NSE scripts report at host level rather than port
    level (e.g. whole-host SMB or clock-skew checks) - a parser that only
    ever visits port-level <script> elements silently drops those findings,
    which is exactly as unsafe as returning [] on a parse failure: the
    target reads as clean when it is not. A host-level finding has no port,
    so `matched_at` falls back to the bare host address rather than
    "host:port".

    Malformed, empty or truncated XML must never surface as an empty finding
    list either - that is indistinguishable from "nmap ran and found
    nothing". Any parse failure is raised as base.ParseError so routine can
    record error:parse:<detail> for just this one cell instead of the whole
    run failing.
    """
    try:
        tree = ET.parse(raw_path)
    except ET.ParseError as e:
        raise base.ParseError("nmap: could not parse %s: %s" % (raw_path, e)) from e
    root = tree.getroot()

    # DEFECT 1 (CRITICAL): `<wrong/>` and similar are syntactically valid
    # XML but not the report -oX actually writes (root element <nmaprun>).
    # Walking <host> children of the wrong root silently returned [] -
    # indistinguishable from "nmap ran and found nothing" - for a file that
    # was never a real nmap report at all.
    if root.tag != "nmaprun":
        raise base.ParseError(
            "nmap: expected <nmaprun> root element in %s, got <%s>" % (raw_path, root.tag))

    findings = []

    for host_el in root.findall("host"):
        addr_el = host_el.find("address")
        host_ip = addr_el.get("addr") if addr_el is not None else ""

        # host/hostscript/script - a sibling of <ports>, not nested under
        # any one <port>. matched_at has no port to append, so it is just
        # the bare host: still a sensible locator, and distinguishable from
        # a port-level finding's "host:port" shape.
        hostscript_el = host_el.find("hostscript")
        if hostscript_el is not None:
            for script_el in hostscript_el.findall("script"):
                _append_vuln_findings(findings, script_el, target, host_ip, host_ip)

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

            # A <script> carrying a structured <table> yields its own
            # separate finding at the mapped severity, in addition to the
            # port's info finding above.
            for script_el in port_el.findall("script"):
                _append_vuln_findings(findings, script_el, target, host_ip, matched_at)

    return findings
