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
"""
import csv
import os
import re

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

# Nikto's CSV has no header row - these are the documented column names
# (spec 13.6) in their fixed emission order.
CSV_FIELDS = ["id", "scanid", "testid", "ip", "hostname", "port", "tls",
              "refs", "httpmethod", "uri", "message", "request", "response"]

# Banner/version-disclosure findings are informational, not vulnerabilities;
# everything else defaults to medium (spec 13.6, design spec section 4).
_BANNER_RE = re.compile(
    r"(x-powered-by|retrieved .*(banner|header)|server (banner|version|leaks)|"
    r"version banner|\bbanner\b)",
    re.IGNORECASE,
)


def is_available():
    return base.which("nikto") is not None


def run(target, outdir, opts=None):
    os.makedirs(outdir, exist_ok=True)
    raw_path = os.path.join(outdir, "nikto.csv")
    argv = ["nikto", "-h", target, "-Format", "csv", "-output", raw_path]
    timeout = (opts or {}).get("timeout", DEFAULT_TIMEOUT)
    result = base.run_tool(argv, timeout=timeout)
    return raw_path, result


def _is_banner(message):
    return bool(_BANNER_RE.search(message or ""))


def parse(raw_path, target):
    """Read Nikto's CSV output. Pure - no subprocess, no network.

    Missing/unreadable output is treated as zero findings rather than an
    error here; run()'s caller is responsible for distinguishing "no findings"
    from "scan never produced a file" using the manifest, not this function.
    """
    if not os.path.isfile(raw_path):
        return []

    findings = []
    with open(raw_path, newline="", encoding="utf-8", errors="replace") as fh:
        for row in csv.reader(fh):
            if not row:
                continue
            # Pad short rows defensively rather than raising on a truncated
            # or interrupted scan.
            row = list(row) + [""] * (len(CSV_FIELDS) - len(row))
            rec = dict(zip(CSV_FIELDS, row))

            message = rec.get("message", "")
            rule_id = rec.get("id") or "unknown"
            severity = n.SEV_NUM["info"] if _is_banner(message) else n.SEV_NUM["medium"]
            refs = [r for r in (rec.get("refs") or "").split(",") if r]

            findings.append(n.make_finding(
                tool=NAME,
                target=target,
                rule_id=rule_id,
                name=message or rule_id,
                severity=severity,
                severity_known=False,
                host=rec.get("hostname") or rec.get("ip") or "",
                matched_at=rec.get("uri") or "",
                description=message,
                reference=refs,
                tags=["nikto"],
            ))
    return findings
