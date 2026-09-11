"""Trivy adapter. One binary serves both `deps` (--scanners vuln) and `iac`
(--scanners misconfig) kinds; parse only the array matching the requested
kind. Exits 0 regardless of findings unless --exit-code is passed - never
infer findings from the exit code (spec 13.7). No tfsec: its engine folded
into Trivy in 2023 (spec 13.4).

A single native output file can carry Vulnerabilities[], Misconfigurations[]
and Secrets[] together, all keyed under the same Results[] entries. run()
already scopes the invocation to one `--scanners` value, but parse() is kept
defensive on top of that and reads only the array for the kind it was asked
about - so a Trivy version that reports more than requested still can't leak
IaC findings into a deps section or vice versa.

`target` (both run() and parse()) is accepted as a plain string (used
directly as the path to scan / the finding's `target` tag), OR as a
dict/object carrying `path`/`name`/`kind` attributes for a richer manifest
Target - the same testable-without-routine.py shape nmap.py's `_target_host`
and depcheck.py's `_scan_path` use. Because one adapter now answers to two
KINDS, `kind` is threaded explicitly: via `opts["kind"]` for run(), and via
an explicit `kind` argument (falling back to `target.kind`) for parse() -
rather than inferred from the file - since the same native/fixture file must
be parsable as either kind on request.

run() follows the cross-adapter contract pinned in spec 13.14 / plan Tasks
5-13: `run(target, outdir, opts) -> (raw_path | None, base.ToolResult)`,
always returning the ToolResult even when raw_path is None, so routine can
record error:timeout / error:<message> per cell. Per that same note, trivy is
one of the three adapters whose raw_path needs an extra word of explanation:
the filename itself (`trivy-deps.json` vs `trivy-iac.json`) is what tells
routine which kind a given call served, since one adapter now writes one of
two different native files depending on the call.
"""
import json
from pathlib import Path

import normalize
from . import base

NAME = "trivy"
KINDS = ["deps", "iac"]
ACTIVE = False
ACTIVE_OPTS = []
DEFAULT_ENABLED = True

_SCANNERS = {"deps": "vuln", "iac": "misconfig"}

# base.run_tool's own timeout is the real guard (spec 13.13); trivy's
# --timeout only bounds trivy's internal work and must always be passed
# (its own default, 5m0s, is too short for a large repo - spec 13.7).
DEFAULT_TIMEOUT = 600
DEFAULT_TRIVY_TIMEOUT = "10m0s"


def _attr(obj, key, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _target_path(target):
    if isinstance(target, str):
        return target
    return _attr(target, "path") or _attr(target, "name")


def _target_name(target):
    if isinstance(target, str):
        return target
    return _attr(target, "name") or _attr(target, "path") or str(target)


def _resolve_kind(target, kind, opts=None):
    if kind is None and opts:
        kind = opts.get("kind")
    if kind is None:
        kind = _attr(target, "kind")
    if kind not in KINDS:
        raise ValueError(
            "trivy: kind must be one of %s, got %r" % (KINDS, kind))
    return kind


def is_available():
    return base.which("trivy") is not None


def run(target, outdir, opts=None):
    """Returns (raw_path, result) per the pinned adapter contract (spec
    13.14): raw_path is None whenever trivy did not run or wrote no output -
    including a timeout - and the ToolResult is always returned so routine
    can record error:timeout / error:<message> either way.

    Trivy's own exit code is never read to decide any of this: it exits 0
    regardless of findings unless --exit-code is passed (spec 13.7), so a
    plain 0/nonzero check would tell us nothing. Whether --output exists is
    the only success signal used here.

    kind is a required, adapter-specific piece of config - not a tool
    outcome - so an unresolvable kind raises ValueError immediately, the
    same way nmap.py's _target_host raises for a target with neither .host
    nor .url, rather than being folded into the (None, result) tool-failure
    path.
    """
    opts = opts or {}
    kind = _resolve_kind(target, None, opts)
    scanner = _SCANNERS[kind]
    path = _target_path(target)

    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    raw_path = outdir / ("trivy-%s.json" % kind)

    trivy_timeout = opts.get("trivy_timeout", DEFAULT_TRIVY_TIMEOUT)
    argv = ["trivy", "fs", "--format", "json", "--scanners", scanner,
            "--timeout", trivy_timeout, "--output", str(raw_path), str(path)]

    timeout = opts.get("timeout", DEFAULT_TIMEOUT)
    result = base.run_tool(argv, timeout=timeout, cwd=opts.get("cwd"))
    if result.timed_out or not raw_path.exists():
        return None, result
    return str(raw_path), result


def _first_cvss(cvss_block):
    if not cvss_block:
        return ""
    for source in ("nvd", "redhat", "ghsa"):
        entry = cvss_block.get(source)
        if entry and entry.get("V3Score") is not None:
            return entry["V3Score"]
    for entry in cvss_block.values():
        if entry and entry.get("V3Score") is not None:
            return entry["V3Score"]
    return ""


def _parse_vulnerabilities(results, target_name):
    findings = []
    for result in results:
        file_target = result.get("Target", "")
        for vuln in result.get("Vulnerabilities") or []:
            sev, known = normalize.sev_from_text(vuln.get("Severity"))
            pkg = vuln.get("PkgName", "")
            fixed = vuln.get("FixedVersion", "")
            rule_id = vuln.get("VulnerabilityID", "")
            primary_url = vuln.get("PrimaryURL")
            references = ([primary_url] if primary_url else []) + \
                list(vuln.get("References") or [])
            remediation = ("upgrade %s to %s" % (pkg, fixed)) if fixed else ""
            findings.append(normalize.make_finding(
                NAME, target_name, rule_id, vuln.get("Title") or rule_id, sev,
                severity_known=known,
                type="vulnerability",
                cve=[rule_id] if rule_id else [],
                cvss=_first_cvss(vuln.get("CVSS")),
                description=vuln.get("Description", ""),
                remediation=remediation,
                reference=references,
                tags=list(vuln.get("CweIDs") or []),
                matched_at=file_target,
            ))
    return findings


def _parse_misconfigurations(results, target_name):
    findings = []
    for result in results:
        file_target = result.get("Target", "")
        for mis in result.get("Misconfigurations") or []:
            sev, known = normalize.sev_from_text(mis.get("Severity"))
            rule_id = mis.get("ID", "")
            cause = mis.get("CauseMetadata") or {}
            start_line = cause.get("StartLine")
            matched_at = ("%s:%s" % (file_target, start_line)
                          if start_line else file_target)
            primary_url = mis.get("PrimaryURL")
            findings.append(normalize.make_finding(
                NAME, target_name, rule_id, mis.get("Title") or rule_id, sev,
                severity_known=known,
                type="misconfiguration",
                description=mis.get("Description", ""),
                remediation=mis.get("Resolution", ""),
                reference=[primary_url] if primary_url else [],
                matched_at=matched_at,
            ))
    return findings


def parse(raw_path, target, kind=None):
    kind = _resolve_kind(target, kind)
    target_name = _target_name(target)

    with open(raw_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    results = data.get("Results") or []

    if kind == "deps":
        return _parse_vulnerabilities(results, target_name)
    return _parse_misconfigurations(results, target_name)
