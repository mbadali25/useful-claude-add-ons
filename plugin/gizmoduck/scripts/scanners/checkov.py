"""Checkov adapter - IaC misconfiguration scanning.

`BaseCheck.__init__` sets `self.severity = None`; Checkov only populates
`severity` when checks sync from Bridgecrew/Prisma Cloud via `--bc-api-key`.
In a free/open-source run the large majority of built-in checks emit
`"severity": null`, so `sev_from_text(..., default="medium")` is the **normal
path** here, not an edge case (spec 13.5) - every such finding carries the
`severity-assigned` marker (make_finding's severity_known=False path) so a
report reader can tell an assigned default from a real assessment.

When more than one framework is scanned in one run, Checkov emits a JSON
**array** of report objects instead of a single object; `parse()` accepts
both shapes by wrapping a bare dict in a one-element list.

Only `results.failed_checks[]` becomes findings - `passed_checks[]` is read
by nothing here. When severity IS populated the values are INFO, LOW,
MEDIUM, HIGH, CRITICAL, plus legacy Bridgecrew aliases MODERATE->MEDIUM and
IMPORTANT->HIGH, both already handled by normalize.sev_from_text.

Checkov's own exit code (1 by default when any check fails, unless
--soft-fail is passed) is the opposite convention from Trivy/sqlmap and is
never inspected here either way - per the global rule, every adapter decides
from parsed output, not from status.
"""
import json
import os

import normalize as n
from . import base

NAME = "checkov"
KINDS = ["iac"]
ACTIVE = False
ACTIVE_OPTS = []  # single mode - nothing here makes a run active
DEFAULT_ENABLED = True

# base.run_tool's own timeout is the real guard (spec 13.13); Checkov has no
# documented whole-scan cap of its own.
DEFAULT_TIMEOUT = 900


def is_available():
    return base.which("checkov") is not None


def run(target, outdir, opts=None):
    """Invoke `checkov -d <path> -o json` and write its stdout verbatim.

    `target` is the plain path string to scan, matching the convention every
    sibling adapter in this package follows (nikto/testssl take a URL/host
    string; depcheck takes a scan-path string) - not a manifest Target object.

    Never gates on availability's caller-side check alone: if the binary
    disappeared between is_available() and run(), this still returns None
    rather than letting base.run_tool fail loudly.
    """
    opts = opts or {}
    binary = base.which("checkov")
    if not binary:
        return None

    os.makedirs(outdir, exist_ok=True)
    raw_path = os.path.join(outdir, "checkov.json")
    argv = [binary, "-d", target, "-o", "json"]
    timeout = opts.get("timeout", DEFAULT_TIMEOUT)
    result = base.run_tool(argv, timeout=timeout, cwd=opts.get("cwd"))

    with open(raw_path, "w", encoding="utf-8") as fh:
        fh.write(result.stdout)
    return raw_path


def _line_range(rng):
    if not rng:
        return ""
    if isinstance(rng, (list, tuple)):
        if len(rng) >= 2:
            return "%s-%s" % (rng[0], rng[1])
        if len(rng) == 1:
            return str(rng[0])
        return ""
    return str(rng)


def parse(raw_path, target):
    """Read Checkov's JSON report(s). Pure - no subprocess, no network.

    Accepts both the single-framework object shape and the multi-framework
    array shape. Missing/unreadable/malformed input yields an empty list
    rather than raising - a broken scan should show up as a run-manifest
    error from the caller, not as this function crashing (matching the
    convention every other adapter in this package follows).
    """
    try:
        with open(raw_path, encoding="utf-8") as fh:
            content = fh.read()
        data = json.loads(content) if content.strip() else []
    except (OSError, ValueError):
        return []

    reports = data if isinstance(data, list) else [data]

    findings = []
    for report in reports:
        if not isinstance(report, dict):
            continue
        check_type = report.get("check_type") or ""
        results = report.get("results") or {}
        for check in results.get("failed_checks") or []:
            rule_id = check.get("check_id") or check.get("bc_check_id") or "unknown"
            sev, known = n.sev_from_text(check.get("severity"), default="medium")
            guideline = check.get("guideline") or ""
            resource = check.get("resource") or ""
            location = "%s:%s" % (check.get("file_path") or "",
                                   _line_range(check.get("file_line_range")))

            findings.append(n.make_finding(
                tool=NAME,
                target=target,
                rule_id=rule_id,
                name=check.get("check_name") or rule_id,
                severity=sev,
                severity_known=known,
                host=resource,
                matched_at=location,
                description=check.get("check_name") or "",
                remediation=guideline,
                reference=[guideline] if guideline else [],
                tags=[check_type] if check_type else [],
            ))
    return findings
