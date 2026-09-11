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

Each finding also carries `path`, `line` (the check's START line as an int -
never the range end), and `resource` as distinct fields, additive alongside
`matched_at`/`host` - these are the iac category's cross-tool merge key
(Task 18), so Trivy's misconfig parser must agree on these exact names.
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

    Returns `(raw_path, result)` — the cross-adapter contract routine.py
    relies on to record `error:timeout`/`error:<message>` per cell in the run
    manifest, which a bare path can't carry. `raw_path` is None whenever no
    output file was produced: the binary is missing, or the run timed out
    (a timed-out invocation's stdout may be truncated mid-JSON, so nothing is
    written rather than handing parse() something that looks parseable but
    isn't trustworthy). `result` is always a ToolResult, even in those cases.
    """
    opts = opts or {}
    binary = base.which("checkov")
    if not binary:
        return None, base.ToolResult(returncode=-1, stdout="",
                                     stderr="checkov not found on PATH", timed_out=False)

    os.makedirs(outdir, exist_ok=True)
    raw_path = os.path.join(outdir, "checkov.json")
    argv = [binary, "-d", target, "-o", "json"]
    timeout = opts.get("timeout", DEFAULT_TIMEOUT)
    result = base.run_tool(argv, timeout=timeout, cwd=opts.get("cwd"))

    if result.timed_out:
        return None, result

    with open(raw_path, "w", encoding="utf-8") as fh:
        fh.write(result.stdout)
    return raw_path, result


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


def _start_line(rng):
    """The START line of file_line_range as an int, or None when absent.

    Merge keys on the start line only (Global Constraints) - Checkov and
    Trivy's misconfig scanner will not agree on where a block ends, and the
    merge must not be asked to.
    """
    if isinstance(rng, (list, tuple)) and rng:
        try:
            return int(rng[0])
        except (TypeError, ValueError):
            return None
    if isinstance(rng, int):
        return rng
    return None


def parse(raw_path, target):
    """Read Checkov's JSON report(s). Pure - no subprocess, no network.

    Accepts both the single-framework object shape and the multi-framework
    array shape. Unreadable, empty, malformed, or wrongly-shaped input
    raises `base.ParseError` rather than returning an empty list - a file
    Checkov never actually scanned must never look identical to "scanned
    and found nothing" (Global Constraints: "parse() must never convert a
    parse failure into an empty finding list"). `routine` catches
    ParseError and records `error:parse:<detail>` for that cell.

    Checkov's own `results.parsing_errors` (files it could not read, even
    when other files in the same run parsed fine) is a distinct signal and
    is surfaced through `parse_errors()` below instead of raising here -
    those files simply contributed no failed_checks, which is not the same
    claim as "the whole report is unreadable".
    """
    try:
        with open(raw_path, encoding="utf-8") as fh:
            content = fh.read()
    except OSError as e:
        raise base.ParseError("%s: could not read file: %s" % (raw_path, e)) from e

    if not content.strip():
        raise base.ParseError("%s: empty output" % raw_path)

    try:
        data = json.loads(content)
    except ValueError as e:
        raise base.ParseError("%s: invalid JSON: %s" % (raw_path, e)) from e

    reports = data if isinstance(data, list) else [data]

    # DEFECT 1: a bare `[]` at the top level is zero framework reports, not
    # a clean multi-framework run - a real checkov invocation always emits
    # at least one report object. Treating it as "nothing to report" was the
    # false-clean this whole check exists to close.
    if not reports:
        raise base.ParseError("%s: empty report list" % raw_path)

    findings = []
    for report in reports:
        if not isinstance(report, dict):
            raise base.ParseError(
                "%s: report entry is not an object: %r" % (raw_path, report))
        check_type = report.get("check_type") or ""

        # DEFECT 1/2: the report's mandatory top-level container must be
        # PRESENT, not merely absent-or-empty. `{}` and `{"results": 1}`
        # both used to reach `results.get(...)` below - the first silently
        # via `or {}`/`or []` (a false-clean), the second as a raw
        # AttributeError once `results` turned out not to be a dict (a
        # contract leak). A genuine empty scan still has
        # `results.failed_checks: []`, which is the one shape this
        # validation must let through unchanged.
        if "results" not in report:
            raise base.ParseError("%s: report is missing 'results'" % raw_path)
        results = report.get("results")
        if not isinstance(results, dict):
            raise base.ParseError(
                "%s: 'results' must be an object, got %r" % (raw_path, type(results).__name__))
        if "failed_checks" not in results:
            raise base.ParseError("%s: 'results' is missing 'failed_checks'" % raw_path)
        failed_checks = results.get("failed_checks")
        if not isinstance(failed_checks, list):
            raise base.ParseError(
                "%s: 'failed_checks' must be a list, got %r" %
                (raw_path, type(failed_checks).__name__))

        for check in failed_checks:
            if not isinstance(check, dict):
                raise base.ParseError(
                    "%s: failed_checks entry is not an object: %r" % (raw_path, check))
            rule_id = check.get("check_id") or check.get("bc_check_id") or "unknown"
            sev, known = n.sev_from_text(check.get("severity"), default="medium")
            guideline = check.get("guideline") or ""
            resource = check.get("resource") or ""
            location = "%s:%s" % (check.get("file_path") or "",
                                   _line_range(check.get("file_line_range")))

            finding = n.make_finding(
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
            )
            # Additive merge-key fields for Task 18's iac cross-tool merge
            # (Global Constraints) - alongside matched_at/host, not instead
            # of them. `path` is the file path alone, never "path:line".
            finding["path"] = check.get("file_path") or ""
            finding["line"] = _start_line(check.get("file_line_range"))
            finding["resource"] = resource
            findings.append(finding)
    return findings


def parse_errors(raw_path, target):
    """Return Checkov's own `results.parsing_errors` as tool-error records.

    These name files Checkov could not parse at all - distinct from an
    empty `failed_checks` list, which means "parsed cleanly, nothing
    failed". Conflating the two is the exact false-clean defect `parse()`
    now guards against for the whole-report case; this is the analogous
    per-file case, surfaced through the optional second channel `routine`
    calls alongside `parse()` (the same convention testssl.parse_errors
    uses), so a broken file is folded into that cell's run-manifest entry
    instead of silently vanishing.

    Shaped deliberately unlike a finding (no template_id, no severity) so
    nothing downstream can mistake one for the other. Never raises: this
    is a best-effort supplementary read of a file `parse()` has, by the
    time this is called, already read successfully.
    """
    try:
        with open(raw_path, encoding="utf-8") as fh:
            content = fh.read()
        data = json.loads(content) if content.strip() else []
    except (OSError, ValueError):
        return []

    reports = data if isinstance(data, list) else [data]

    errors = []
    for report in reports:
        if not isinstance(report, dict):
            continue
        results = report.get("results") or {}
        for entry in results.get("parsing_errors") or []:
            errors.append({
                "tool": NAME,
                "target": target,
                "message": str(entry),
            })
    return errors
