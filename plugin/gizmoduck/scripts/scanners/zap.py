"""OWASP ZAP adapter.

The only runnable local path on a Docker-less operator machine is ZAP's
**Automation Framework**: `zap.bat -cmd -autorun <plan>.yaml` with a `report`
job of `template: traditional-json`. `zap-baseline.py` / `zap-full-scan.py`
shell out to `docker run ghcr.io/zaproxy/zaproxy:...` internally even when
invoked as plain Python (spec 13.3) - this adapter never touches Docker, in
either `is_available()` or `run()`.

Baseline (spider + passive scan) is the default, no-attack-traffic mode and
runs like any other DEFAULT_ENABLED tool. The active scan is attack traffic,
so it is gated the same way Nmap's `vuln` NSE is: ACTIVE stays False (a bare
True would wrongly gate baseline off by default too), and `zap_active` in
ACTIVE_OPTS is the per-target opt-in that turns it on. `routine` records which
mode actually ran - `ran(baseline)` vs `ran(baseline+active)` - never a bare
`ran` (Global Constraints, plan).

The AF's exit-code contract (0/1/2 on job errors/warnings) is unrelated to
alert risk, unlike zap-baseline.py's docker-wrapper codes that look the same
numerically (spec 13.11/13.12) - `run()` never inspects `ToolResult.returncode`
to decide anything about findings; only `parse()` of the report JSON does.

`riskcode` 0-3 -> info/low/medium/high is a high-confidence inference from
example output, not a documented mapping (spec 13.3). `normalize.sev_from_riskcode`
already encodes exactly that inference and refuses anything outside 0-3, so
this module defers to it rather than re-deriving the mapping.
"""
import json
from pathlib import Path

import yaml

import normalize as n
from . import base

NAME = "zap"
KINDS = ["web"]
ACTIVE = False              # baseline (spider + passive scan) sends no attack traffic
ACTIVE_OPTS = ["zap_active"]  # ...but this option turns on ZAP's active scan job
DEFAULT_ENABLED = True

REPORT_TEMPLATE = "traditional-json"
DEFAULT_TIMEOUT = 1800  # seconds; base.run_tool is the real guard (spec 13.13)


def is_available():
    """True only for a local ZAP install. Never probes Docker - see module
    docstring; a Docker-only delivery is doctor's (Task 21) concern to report
    as a distinct state, not this adapter's to fall back onto.
    """
    return _zap_binary() is not None


def _zap_binary():
    return base.which("zap.bat") or base.which("zap.sh")


def _context_name(target):
    name = getattr(target, "name", None) or str(target)
    # AF context names are free text but keep this readable in the plan file.
    return "".join(c if c.isalnum() else "-" for c in name) or "target"


def _build_plan(url, context_name, active, report_dir, report_file):
    jobs = [
        {"type": "passiveScan-config", "parameters": {"maxAlertsPerRule": 0}},
        {"type": "spider", "parameters": {"context": context_name, "url": url}},
        {"type": "passiveScan-wait", "parameters": {"maxDuration": 10}},
    ]
    if active:
        jobs.append({"type": "activeScan", "parameters": {"context": context_name}})
    jobs.append({
        "type": "report",
        "parameters": {
            "template": REPORT_TEMPLATE,
            "reportDir": str(report_dir),
            "reportFile": report_file,
            "reportTitle": "Gizmoduck ZAP scan - %s" % context_name,
        },
    })
    return {
        "env": {
            "contexts": [{
                "name": context_name,
                "urls": [url],
                "includePaths": [url.rstrip("/") + ".*"],
            }],
            "parameters": {"progressToStdout": True},
        },
        "jobs": jobs,
    }


def run(target, outdir, opts):
    """Write the AF plan and invoke `zap.bat -cmd -autorun <plan>.yaml`.

    Returns `(raw_path | None, ToolResult)` (routine.py contract, standardized
    across all nine adapters): the report job writes the native JSON itself
    (reportDir/reportFile below), so success is decided by whether that file
    landed on disk, never by ToolResult.returncode - the AF's 0/1/2 there
    track job errors/warnings, not alert risk (module docstring). The
    ToolResult is returned unconditionally so routine can still record
    `error:timeout` / `error:<message>` per cell even when raw_path is None.
    """
    opts = opts or {}
    active = bool(opts.get("zap_active"))
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    url = getattr(target, "url", None) or str(target)
    context_name = _context_name(target)
    report_path = outdir / ("%s.json" % NAME)

    # DEFECT 1 (critical): establish freshness BEFORE invoking ZAP. A stale
    # report left in outdir from a previous run would otherwise still be
    # sitting at report_path after a failed invocation that wrote nothing
    # new, and `report_path.is_file()` below would hand it back as if it
    # were this run's evidence - a failed scan inheriting the previous run's
    # clean bill of health.
    if report_path.exists():
        report_path.unlink()

    plan = _build_plan(url, context_name, active, outdir, NAME)

    plan_path = outdir / "zap-plan.yaml"
    with open(plan_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(plan, fh, sort_keys=False)

    binary = _zap_binary()
    if binary is None:
        return None, base.ToolResult(-1, "", "no local ZAP install found (zap.bat/zap.sh)", False)

    argv = [binary, "-cmd", "-autorun", str(plan_path)]
    result = base.run_tool(argv, timeout=opts.get("timeout", DEFAULT_TIMEOUT))
    raw_path = str(report_path) if report_path.is_file() else None
    return raw_path, result


def _as_list(value, label):
    if value is None:
        return []
    if not isinstance(value, list):
        raise base.ParseError("zap: %r must be a list, got %r" % (label, type(value).__name__))
    return value


def _as_obj(value, label):
    if not isinstance(value, dict):
        raise base.ParseError("zap: %r entry is not an object: %r" % (label, value))
    return value


def parse(raw_path, target):
    """Parse the AF `report` job's traditional-json output, or raise
    base.ParseError.

    Schema: site[] -> alerts[] -> instances[]. One alert with N instances
    yields N findings sharing a template_id, so gizmoduck.dedupe()'s
    (target, template_id) key later collapses them back into one row with
    `instances == N` - the fan-out happens here, the aggregation happens
    there, matching how a multi-match Nuclei template already works.

    DEFECT 2: a missing, empty, truncated or malformed report - and a
    well-formed-but-wrongly-shaped one, such as `{"site": [null]}` - must
    never come back as `[]` (indistinguishable from "ZAP ran and found
    nothing") and must never let AttributeError escape from a `None` where a
    site/alert/instance object was expected. Pure otherwise: no subprocess,
    no network.
    """
    try:
        with open(raw_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        raise base.ParseError("zap: could not read %s: %s" % (raw_path, e)) from e

    if not isinstance(data, dict):
        raise base.ParseError(
            "zap: expected a JSON object at the top level, got %r" % type(data).__name__)

    findings = []
    for site in _as_list(data.get("site"), "site"):
        site = _as_obj(site, "site")
        host = site.get("@name") or site.get("@host") or ""
        for alert in _as_list(site.get("alerts"), "alerts"):
            alert = _as_obj(alert, "alerts")
            rule_id = alert.get("pluginid") or alert.get("alertRef") or "unknown"
            name = alert.get("alert") or alert.get("name") or rule_id
            severity, known = n.sev_from_riskcode(alert.get("riskcode"))

            reference = [line for line in (alert.get("reference") or "").splitlines()
                        if line.strip()]
            tags = []
            cweid = alert.get("cweid")
            if cweid not in (None, "", "-1"):
                tags.append("cwe:%s" % cweid)

            instances = _as_list(alert.get("instances"), "instances") or [{}]
            for inst in instances:
                inst = _as_obj(inst, "instances")
                findings.append(n.make_finding(
                    tool=NAME,
                    target=target,
                    rule_id=rule_id,
                    name=name,
                    severity=severity,
                    severity_known=known,
                    host=host,
                    matched_at=inst.get("uri", ""),
                    description=alert.get("desc", ""),
                    remediation=alert.get("solution", ""),
                    reference=reference,
                    tags=tags,
                    type="http",
                ))
    return findings
