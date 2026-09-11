"""Nikto adapter.

Nikto has no JSON output worth trusting (spec 13.6): `-Format json` emits
invalid JSON on 2.1.6 when the target has no webserver (duplicate closing
brace, issue #721's sibling #837), and the fix is unconfirmed on current
releases. CSV is the parse path here, not a fallback.

Nikto also has no severity field at all. Every finding is assigned `medium`
unless its message matches a banner/version-disclosure pattern, in which case
it is `info` - and every finding therefore carries the `severity-assigned`
marker (make_finding's severity_known=False path), so a report reader can
never mistake this heuristic for a real assessment.

Nikto exits non-zero regardless of outcome (issue #837). This adapter never
reads that exit code: run() ignores ToolResult.returncode, and success is
decided by the caller from whether parse() finds any rows in the output file.

CRITICAL defect fix: run() previously left a pre-existing CSV at raw_path
untouched and always returned that path regardless of whether THIS
invocation actually produced anything. A failed invocation (binary crash,
target unreachable, whatever) that wrote no fresh CSV would then have its
`run()` call reuse an earlier CSV sitting in the same outdir - a failed scan
inheriting a previous run's clean bill of health, or worse, its findings.
Fixed the same way trivy.py/testssl.py/zap.py/depcheck.py already do:
establish freshness by deleting any pre-existing output BEFORE invoking
nikto, and return `(None, result)` - the standard cross-adapter contract -
whenever no fresh CSV lands afterward. parse() is symmetric with this: a
missing file at parse time is no longer treated as "zero findings" (that
claim belongs only to a real, empty-of-rows CSV); it raises base.ParseError,
since routine only ever calls parse() with the path run() just returned, and
a file missing at that point means something is wrong that a silent []
would let nobody notice (base.ParseError's own docstring).
"""
import csv
import hashlib
import os
import re
from pathlib import Path

import normalize as n
from . import base

NAME = "nikto"
KINDS = ["web"]
ACTIVE = False
ACTIVE_OPTS = []
DEFAULT_ENABLED = True

# base.run_tool's own subprocess timeout is the real guard here (spec 13.13):
# Nikto's -timeout flag caps a single request, not the whole scan.
DEFAULT_TIMEOUT = 900

# Nikto's CSV has no header row. These are the columns it ACTUALLY emits, in
# order, verified against real `nikto -Format csv` output from v2.6.1 - seven
# fields, not the thirteen the SQL/DB schema documents. The earlier list was
# taken from Nikto's SQL export (spec 13.6) and was wrong: the CSV has no
# numeric id/scanid/testid columns at all (those `[0xxxxx]` ids appear only in
# the human-readable text report), and no request/response columns. Keying
# `message` at index 10 against this 7-field reality read the port or a doc
# URL as the finding text and discarded every real row as "malformed".
CSV_FIELDS = ["host", "ip", "port", "refs", "httpmethod", "uri", "message"]

# Banner/version-disclosure findings are informational, not vulnerabilities;
# everything else defaults to medium (spec 13.6, design spec section 4).
_BANNER_RE = re.compile(
    r"(x-powered-by|retrieved .*(banner|header)|server (banner|version|leaks)|"
    r"version banner|\bbanner\b)",
    re.IGNORECASE,
)


# Nikto is a Perl script with no native Windows package (bootstrap.ps1's
# Install-Nikto comment): on Windows there is no `nikto` binary on PATH at
# all, only a cloned nikto.pl that needs a Perl runtime to run it.
#
# Whether "some perl on PATH" can actually run nikto (it needs XML::Writer)
# is a BOOTSTRAP-time concern, not a runtime one: bootstrap.ps1's
# Test-PerlHasXmlWriter verifies this and installs the module (or falls
# back to Strawberry Perl) before this adapter ever runs, so by the time
# is_available()/run() execute, whichever perl is on PATH is expected to
# already work. An earlier version of this adapter re-probed XML::Writer
# itself and preferred a hard-coded Strawberry Perl path over PATH - that
# was based on one install agent's environment where PATH perl happened to
# be broken; a second, independent verification found PATH perl to be the
# *better* choice once XML::Writer is actually present (Strawberry's perl
# emitted an unrelated warning nikto.pl doesn't hit under Git's perl). So
# this adapter trusts `base.which("perl")` like any other adapter trusts
# `base.which()` for its tool - the capability check belongs in bootstrap.
_NIKTO_PL_CANDIDATES = tuple(
    p for p in (
        os.environ.get("GIZMODUCK_NIKTO_PL"),
        (str(Path(os.environ["LOCALAPPDATA"]) / "Programs" / "nikto" / "program" / "nikto.pl")
         if os.environ.get("LOCALAPPDATA") else None),
    ) if p
)


def _find_nikto_pl():
    for candidate in _NIKTO_PL_CANDIDATES:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def _resolve_argv(target, raw_path):
    """The nikto command line to run: a native `nikto` binary on PATH (the
    Linux/apt-installed case), or - lacking one - whatever `perl` is on
    PATH launching nikto.pl directly (the Windows case). Returns None if
    neither route is usable, so run() can decline cleanly instead of
    handing an unusable argv to base.run_tool.
    """
    native = base.which("nikto")
    if native:
        return [native, "-h", target, "-Format", "csv", "-output", raw_path]
    nikto_pl = _find_nikto_pl()
    perl = base.which("perl")
    if nikto_pl and perl:
        return [perl, nikto_pl, "-h", target, "-Format", "csv", "-output", raw_path]
    return None


def is_available():
    if base.which("nikto") is not None:
        return True
    return _find_nikto_pl() is not None and base.which("perl") is not None


def run(target, outdir, opts=None):
    """Returns (raw_path | None, base.ToolResult) per the cross-adapter
    contract: raw_path is None whenever this invocation did not itself
    produce a fresh CSV, so a failed run can never be handed back as if it
    were evidence.
    """
    os.makedirs(outdir, exist_ok=True)
    raw_path = os.path.join(outdir, "nikto.csv")

    # DEFECT 1 (critical): establish freshness BEFORE invoking nikto, same
    # pattern as trivy.py/testssl.py/zap.py/depcheck.py. Without this, a
    # stale CSV left over from a previous run in the same outdir would still
    # be sitting at raw_path after a failed invocation that wrote nothing
    # new, and the existence check below would hand it back as if it were
    # this run's evidence.
    if os.path.isfile(raw_path):
        os.remove(raw_path)

    argv = _resolve_argv(target, raw_path)
    if argv is None:
        return None, base.ToolResult(
            -1, "",
            "nikto not found: no nikto binary on PATH, and no nikto.pl + "
            "perl available", False)

    timeout = (opts or {}).get("timeout", DEFAULT_TIMEOUT)
    result = base.run_tool(argv, timeout=timeout)
    if result.timed_out or not os.path.isfile(raw_path):
        return None, result
    return raw_path, result


def _is_banner(message):
    return bool(_BANNER_RE.search(message or ""))


# A bare vulnerability-id token in the refs column, e.g. "CWE-548" or
# "OSVDB-3092" - as opposed to a documentation URL, which most refs are.
_ID_TOKEN_RE = re.compile(r"^(CWE|OSVDB|CVE|BID)-[\w.-]+$", re.IGNORECASE)


def _rule_id(rec):
    """Synthesise a stable rule id: Nikto's CSV carries no id column.

    Prefer a bare id token from refs (CWE-548, OSVDB-3092) when present, since
    the same check reports the same token across scans. Otherwise derive a
    short deterministic hash of the message so the same finding keeps the same
    id run to run - which is what `dedupe()` needs to aggregate it by
    (target, template_id) rather than treating every scan as new.
    """
    for ref in (rec.get("refs") or "").split(","):
        ref = ref.strip()
        if _ID_TOKEN_RE.match(ref):
            return ref
    message = rec.get("message") or ""
    return "msg-" + hashlib.sha1(message.encode("utf-8")).hexdigest()[:10]


def parse(raw_path, target):
    """Read Nikto's CSV output. Pure - no subprocess, no network.

    A missing file raises `base.ParseError` rather than returning zero
    findings (CRITICAL defect fix): routine only ever calls parse() with the
    path run() just returned as a fresh output, so a file missing at that
    point means the scan never actually produced evidence - not "nikto ran
    and found nothing". Conflating the two is exactly the false-clean
    outcome base.ParseError exists to prevent (its own docstring). A real,
    present-but-empty CSV (zero rows) still yields `[]`, same as always.

    Nikto emits two structural rows on every run that are NOT findings and
    are skipped rather than raised on: a one-field version banner
    (`"Nikto - v2.6.1/"`) as the first line, and a seven-field scan-start
    marker whose refs/method/uri/message are all empty. Both are normal
    output, not truncation.

    A row that is neither of those and does not have exactly the seven
    columns Nikto emits raises `base.ParseError`. Rows used to be padded to a
    (wrong) thirteen-column set and turned into a `medium` finding regardless
    of content, so a truncated row from an interrupted scan or a stray line
    manufactured a vulnerability that was never observed. Inventing a finding
    is as damaging as missing one: it sends a reader chasing something with
    no underlying fact (Global Constraints: "never fabricate a finding from
    unvalidatable input").
    """
    if not os.path.isfile(raw_path):
        raise base.ParseError("nikto output file not found: %s" % raw_path)

    findings = []
    with open(raw_path, newline="", encoding="utf-8", errors="replace") as fh:
        for row in csv.reader(fh):
            if not row:
                continue
            # The version banner is a single field like "Nikto - v2.6.1/".
            if len(row) == 1 and row[0].lstrip().lower().startswith("nikto"):
                continue
            if len(row) != len(CSV_FIELDS):
                # Not the seven columns Nikto emits and not the known banner:
                # truncated output or a stray line, never a finding.
                raise base.ParseError(
                    "%s: expected %d Nikto CSV columns, got %d: %r"
                    % (raw_path, len(CSV_FIELDS), len(row), row))
            rec = dict(zip(CSV_FIELDS, row))

            message = rec.get("message", "")
            if not message:
                # The scan-start marker: a well-formed seven-field row with an
                # empty message. Structural, not a finding - skip it. (A
                # finding always carries message text.)
                continue

            severity = n.SEV_NUM["info"] if _is_banner(message) else n.SEV_NUM["medium"]
            refs = [r for r in (rec.get("refs") or "").split(",") if r]

            findings.append(n.make_finding(
                tool=NAME,
                target=target,
                rule_id=_rule_id(rec),
                name=message,
                severity=severity,
                severity_known=False,
                host=rec.get("host") or rec.get("ip") or "",
                matched_at=rec.get("uri") or "",
                description=message,
                reference=refs,
                tags=["nikto"],
            ))
    return findings
