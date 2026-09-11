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
directly as the path to scan / the finding's `target` tag - what routine.py
will pass once it exists), OR as a dict/object carrying `path`/`name`/`kind`
attributes for a richer manifest Target. Because one adapter now answers to
two KINDS, `kind` is threaded explicitly - via `opts["kind"]` for run() and
an explicit `kind` argument (or `target.kind`) for parse() - rather than
inferred, since the same fixture/native file must be parsable as either kind.
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
    result = base.run_tool(argv, timeout=timeout)
    if result.timed_out:
        raise TimeoutError(
            "trivy timed out after %ss scanning %s" % (timeout, path))
    if not raw_path.exists():
        # Trivy exits 0 whether or not it found anything, so a missing
        # output file - not a non-zero return code - is what actually means
        # the scan failed to produce results.
        raise RuntimeError(
            "trivy produced no output for %s: %s" % (path, result.stderr.strip()))
    return str(raw_path)


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
