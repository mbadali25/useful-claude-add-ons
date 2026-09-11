"""OWASP Dependency-Check adapter.

Invocation: `dependency-check --format JSON --out <dir> --scan <path>`; the
tool writes `dependency-check-report.json` into that directory regardless of
what target path was scanned, so `run()` always knows the file to hand back.

Schema: `dependencies[] -> vulnerabilities[]`. Each vulnerability carries a
`name` (CVE/GHSA id), a plain-text `severity`, and two independent scoring
blocks, `cvssv2 {score, ...}` and `cvssv3 {baseScore, baseSeverity, ...}`.

Severity fallback order (spec 13.8, corrects section 4's CVSS-first
reading): plain-text `severity` first, then `cvssv2.score`, then
`cvssv3.baseScore`. `cvssv3.baseScore` can be null or absent for a
dependency whose only NVD entry is CVSSv2-scored or which is unscored
outright, while the plain-text `severity` is still populated - trusting a
missing cvssv3 block first would silently drop those findings to info.
"""
import json
import os

import normalize
from . import base

NAME = "depcheck"
KINDS = ["deps"]
ACTIVE = False
ACTIVE_OPTS = []
DEFAULT_ENABLED = True

REPORT_FILENAME = "dependency-check-report.json"
DEFAULT_TIMEOUT = 900


def is_available():
    return base.which("dependency-check") is not None


def _scan_path(target):
    if isinstance(target, str):
        return target
    return getattr(target, "path", None) or getattr(target, "url", None) or str(target)


def run(target, outdir, opts):
    os.makedirs(outdir, exist_ok=True)
    opts = opts or {}
    argv = [
        "dependency-check", "--format", "JSON",
        "--out", outdir, "--scan", _scan_path(target),
    ]
    result = base.run_tool(argv, timeout=opts.get("timeout", DEFAULT_TIMEOUT))
    return result, os.path.join(outdir, REPORT_FILENAME)


def _score(vuln, block, field):
    v = (vuln.get(block) or {}).get(field)
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _severity(vuln):
    """(severity_int, was_a_real_assessment) via the documented fallback."""
    sev, known = normalize.sev_from_text(vuln.get("severity"))
    if known:
        return sev, True
    score2 = _score(vuln, "cvssv2", "score")
    if score2 is not None:
        return normalize.sev_from_cvss(score2), True
    score3 = _score(vuln, "cvssv3", "baseScore")
    if score3 is not None:
        return normalize.sev_from_cvss(score3), True
    return 0, False


def _best_score(vuln):
    """Numeric score for the finding's `cvss` field - CVSSv3 preferred as the
    more current standard, falling back to CVSSv2 - independent of which
    block actually decided the severity band in `_severity` above.
    """
    score3 = _score(vuln, "cvssv3", "baseScore")
    if score3 is not None:
        return score3
    score2 = _score(vuln, "cvssv2", "score")
    if score2 is not None:
        return score2
    return ""


def parse(raw_path, target):
    with open(raw_path, encoding="utf-8") as fh:
        data = json.load(fh)

    findings = []
    for dep in data.get("dependencies") or []:
        file_name = dep.get("fileName", "")
        for vuln in dep.get("vulnerabilities") or []:
            rule_id = vuln.get("name", "")
            sev, known = _severity(vuln)
            refs = [r.get("url") for r in (vuln.get("references") or []) if r.get("url")]
            findings.append(normalize.make_finding(
                tool=NAME,
                target=target,
                rule_id=rule_id,
                name=rule_id,
                severity=sev,
                severity_known=known,
                matched_at=file_name,
                cve=[rule_id] if rule_id else [],
                cvss=_best_score(vuln),
                description=vuln.get("description", ""),
                reference=refs,
                tags=list(vuln.get("cwes") or []),
            ))
    return findings
