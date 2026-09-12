"""Semgrep adapter - static analysis of source code.

The gap this closes. Every other adapter in this package reads something the
code PRODUCED - a running endpoint, a lockfile, a rendered Terraform plan - so
all of them are blind to the same class of defect: a check that is *missing*.
An authorization gate that was never written has no signature to match, no CVE,
no misconfigured resource and no anomalous response; the endpoint answers 200
exactly as it should. Semgrep reads the source itself, which is the only way
that class becomes visible.

`kind: code` is new with this adapter and takes `path`, like `iac` and `deps`.

Severity is Semgrep's own ERROR/WARNING/INFO, which does not overlap the
critical/high/medium/low/info vocabulary every other tool here uses, so it is
mapped explicitly rather than passed to sev_from_text - that function would
score every WARNING as `info` via its default and quietly drop the bulk of a
run below the report's Medium floor. The mapping is deliberately conservative:

    ERROR   -> high     Semgrep's own "this is a bug" tier
    WARNING -> medium   the default tier for the security rulesets
    INFO    -> info     style and nitpick rules

Nothing here maps to `critical`. Semgrep does not assign one, and inventing a
tier a tool does not have would put SAST findings above CVEs with real CVSS
scores in the same report.

Semgrep's exit code is 0 when clean, 1 when findings exist, and other values on
error - the same 0/1 ambiguity Trivy and sqlmap have. Per the package rule, it
is never inspected; the parsed output decides. The one exception is that the
`errors` array is read and surfaced through `scan_errors()`, because a run where
half the files failed to parse is not the same claim as a clean run.

Memory is capped with --max-memory and -j. This is a stability requirement, not
tuning: Semgrep defaults to one worker per core with no ceiling, and across a
repo-wide run that is what exhausts the machine. The symptom is not a scanner
error - the OS kills the process, which reads as a hang.
"""
import json
import os

import normalize as n
from . import base

NAME = "semgrep"
KINDS = ["code"]
ACTIVE = False
ACTIVE_OPTS = []  # reads source; never touches the target system
DEFAULT_ENABLED = True

# base.run_tool's timeout is the whole-scan guard. --timeout below is
# Semgrep's own PER-RULE-PER-FILE cap, which is a different control: it stops
# one pathological file from consuming the whole budget.
DEFAULT_TIMEOUT = 1800
DEFAULT_CONFIG = "p/security-audit"
DEFAULT_MAX_MEMORY_MB = 2048
DEFAULT_JOBS = 2
DEFAULT_RULE_TIMEOUT = 120

_SEVERITY = {"ERROR": "high", "WARNING": "medium", "INFO": "info"}


def is_available():
    return base.which("semgrep") is not None


def run(target, outdir, opts=None):
    """Invoke semgrep and write its JSON report.

    `target` is a plain path string, matching checkov and depcheck.

    Returns `(raw_path, result)`. `raw_path` is None when no trustworthy output
    was produced - the binary is missing, or the run timed out, since a
    timed-out invocation's stdout may be truncated mid-JSON and handing that to
    parse() would produce a partial finding list that looks complete.
    """
    opts = opts or {}
    binary = base.which("semgrep")
    if not binary:
        return None, base.ToolResult(returncode=-1, stdout="",
                                     stderr="semgrep not found on PATH",
                                     timed_out=False)

    os.makedirs(outdir, exist_ok=True)
    raw_path = os.path.join(outdir, "semgrep.json")
    argv = [
        binary, "--config", opts.get("semgrep_config", DEFAULT_CONFIG),
        "--json", "--quiet",
        "--timeout", str(opts.get("semgrep_rule_timeout", DEFAULT_RULE_TIMEOUT)),
        "--max-memory", str(opts.get("semgrep_max_memory_mb", DEFAULT_MAX_MEMORY_MB)),
        "-j", str(opts.get("semgrep_jobs", DEFAULT_JOBS)),
        target,
    ]
    result = base.run_tool(argv, timeout=opts.get("timeout", DEFAULT_TIMEOUT),
                           cwd=opts.get("cwd"))

    if result.timed_out:
        return None, result

    with open(raw_path, "w", encoding="utf-8") as fh:
        fh.write(result.stdout)
    return raw_path, result


def _load(raw_path):
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
    if not isinstance(data, dict) or "results" not in data:
        raise base.ParseError(
            "%s: not a semgrep report (no 'results' key)" % raw_path)
    return data


def parse(raw_path, target):
    """Read Semgrep's JSON report. Pure - no subprocess, no network.

    A clean run emits `{"results": [], "errors": [...]}`, so an empty list is a
    real "scanned and found nothing" and is returned as such. Output that is
    unreadable, empty, malformed, or missing `results` raises `base.ParseError`
    instead - a file Semgrep never scanned must never look identical to a clean
    scan.
    """
    data = _load(raw_path)
    findings = []

    for r in data.get("results") or []:
        if not isinstance(r, dict):
            raise base.ParseError(
                "%s: results[] contains a %s, expected an object"
                % (raw_path, type(r).__name__))
        extra = r.get("extra") or {}
        meta = extra.get("metadata") or {}
        rule_id = r.get("check_id") or "rule"

        raw_sev = str(extra.get("severity") or "").upper()
        sev_name = _SEVERITY.get(raw_sev)
        # An unrecognised tier is marked rather than guessed, so a report
        # reader can tell an assigned default from Semgrep's own assessment.
        severity, known = (n.SEV_NUM[sev_name], True) if sev_name \
            else (n.SEV_NUM["info"], False)

        line = (r.get("start") or {}).get("line")
        path = r.get("path") or ""
        where = "%s:%s" % (path, line) if line else path

        cwe = meta.get("cwe")
        cwe = cwe if isinstance(cwe, list) else ([cwe] if cwe else [])
        refs = []
        if meta.get("shortlink"):
            refs.append(meta["shortlink"])
        refs.extend([u for u in (meta.get("references") or []) if u][:3])

        message = (extra.get("message") or "").strip()
        finding = n.make_finding(
            tool=NAME,
            target=target,
            rule_id=rule_id,
            name=message.split("\n")[0][:160] or rule_id,
            severity=severity,
            severity_known=known,
            type="code",
            matched_at=where,
            description=message[:600],
            # `fix` is Semgrep's own suggested replacement when a rule carries
            # one. It is the remediation; most rules have none.
            remediation=extra.get("fix") or "",
            reference=refs,
            tags=["sast"] + [str(c) for c in cwe][:2],
        )
        # Additive fields, alongside matched_at rather than instead of it -
        # the same shape checkov and trivy-misconfig use for the iac merge, so
        # a future code-category merge has it available. `path` is the file
        # path alone, never "path:line". make_finding does not pass unknown
        # keyword arguments through, so these are set after it.
        finding["path"] = path
        finding["line"] = int(line) if isinstance(line, int) else None
        findings.append(finding)
    return findings


def scan_errors(raw_path):
    """Files Semgrep could not parse, as human-readable strings.

    A distinct signal from a failed report: those files simply contributed no
    findings, which is not the same claim as "the whole report is unreadable".
    Surfaced rather than raised so a partially-parsed run is not thrown away,
    but never silently dropped either - a run where most files failed to parse
    is close to no coverage at all.
    """
    data = _load(raw_path)
    out = []
    for e in data.get("errors") or []:
        if isinstance(e, dict):
            where = (e.get("path") or (e.get("location") or {}).get("path") or "")
            msg = e.get("message") or e.get("long_msg") or e.get("type") or "error"
            out.append("%s: %s" % (where, msg) if where else str(msg))
        else:
            out.append(str(e))
    return out
