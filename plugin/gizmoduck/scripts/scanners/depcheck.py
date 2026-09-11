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

NVD API key (optional): dependency-check's first run (and periodic
refreshes after) must sync the NVD CVE feed, and NIST rate-limits that sync
to about 5 requests/30s without an API key versus about 50 with one - the
whole difference between a sync taking the better part of an hour and one
taking a few minutes (dependency-check 12.1.0, confirmed via `--help`: the
flag is `--nvdApiKey <apiKey>`). This adapter reads it from the
`NVD_API_KEY` environment variable rather than an `opts` field so it is
never threaded through the manifest/CLI and is optional throughout: its
absence must never be an error, only a slower first sync. It is a
credential - `run()` only ever places it inline in the subprocess argv, and
must never log it, print it, write it to a file, or fold it into anything
this adapter returns.
"""
import json
import os
import re

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
    """Returns (raw_path, result) - raw_path is None when the tool was not
    run or produced no output file, per the cross-adapter run() contract:
    routine.py needs the ToolResult even on failure to record error/timeout
    per-cell in the run manifest, and dependency-check writes into an --out
    DIRECTORY under a fixed filename rather than a path we name directly, so
    routine has no way to find the file except by us resolving and returning
    it.
    """
    os.makedirs(outdir, exist_ok=True)
    opts = opts or {}
    raw_path = os.path.join(outdir, REPORT_FILENAME)

    # DEFECT 1 (critical): establish freshness BEFORE invoking the tool.
    # dependency-check always writes REPORT_FILENAME under a fixed name, so a
    # stale report left in `outdir` from a previous run would still be sitting
    # there after a failed invocation that wrote nothing new - and the
    # os.path.isfile check below would hand it back as if it were this run's
    # evidence. Removing it first means "no fresh artifact" is the only way
    # isfile() can come back True afterward.
    if os.path.isfile(raw_path):
        os.remove(raw_path)

    argv = [
        "dependency-check", "--format", "JSON",
        "--out", outdir, "--scan", _scan_path(target),
    ]
    # Optional NVD API key (see module docstring): appended only when set,
    # never required. Read straight from the environment and placed nowhere
    # but this argv - never logged, printed, or written to a file - since
    # it's a credential.
    nvd_api_key = os.environ.get("NVD_API_KEY")
    if nvd_api_key:
        argv += ["--nvdApiKey", nvd_api_key]
    result = base.run_tool(argv, timeout=opts.get("timeout", DEFAULT_TIMEOUT))
    if not os.path.isfile(raw_path):
        return None, result
    return raw_path, result


def _score(vuln, block, field):
    v = (vuln.get(block) or {}).get(field)
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _severity(vuln):
    """(severity_int, was_a_real_assessment) via the documented fallback:
    text `severity` -> `cvssv2.score` -> `cvssv3.baseScore`.

    DEFECT 3: a garbage numeric score (NaN, Infinity, negative, or above the
    valid CVSS 0.0-10.0 range - e.g. dependency-check emitting "NaN" or -1 as
    cvssv2.score) must never be accepted as a real assessment, even when it
    parses as a float. normalize.sev_from_cvss now reports that back as
    `known=False` instead of silently banding a nonsense score, so this
    fallback chain must actually respect that and try the next source rather
    than stopping at the first non-None float it sees.
    """
    sev, known = normalize.sev_from_text(vuln.get("severity"))
    if known:
        return sev, True
    score2 = _score(vuln, "cvssv2", "score")
    if score2 is not None:
        sev2, known2 = normalize.sev_from_cvss(score2)
        if known2:
            return sev2, True
    score3 = _score(vuln, "cvssv3", "baseScore")
    if score3 is not None:
        sev3, known3 = normalize.sev_from_cvss(score3)
        if known3:
            return sev3, True
    return 0, False


def _best_score(vuln):
    """Numeric score for the finding's `cvss` field - CVSSv3 preferred as the
    more current standard, falling back to CVSSv2 - independent of which
    block actually decided the severity band in `_severity` above.

    Only a score normalize.sev_from_cvss recognizes as valid is surfaced here
    too: a NaN/Infinity/out-of-range value has no business being displayed as
    if it were a real CVSS score in the report, so an invalid score falls
    through to the next source exactly like it does in `_severity`.
    """
    score3 = _score(vuln, "cvssv3", "baseScore")
    if score3 is not None and normalize.sev_from_cvss(score3)[1]:
        return score3
    score2 = _score(vuln, "cvssv2", "score")
    if score2 is not None and normalize.sev_from_cvss(score2)[1]:
        return score2
    return ""


# A Package URL (https://github.com/package-url/purl-spec), e.g.
# "pkg:npm/lodash@4.17.15" or "pkg:maven/org.apache.commons/commons-lang3@3.9".
# Namespace is optional and folded into the captured name group along with
# the leaf name, since the deps merge key wants a single package identifier
# to compare against Trivy's `PkgName`, not a namespace/name pair.
_PURL_RE = re.compile(r"^pkg:[^/]+/(?P<name>.+)@(?P<version>[^@]+)$")

_CONFIDENCE_ORDER = {"HIGHEST": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def _package_and_version(dep):
    """Best-effort (package, version) for the deps merge key `(CVE, package,
    version)` - each returned as None when unresolved, never guessed, per the
    "absent slot means does not merge" rule: a wrong package name would merge
    two unrelated CVEs.

    Dependency-Check does not expose a clean name/version pair the way Trivy's
    `PkgName`/`InstalledVersion` do. The most reliable structured source in
    the real schema is `packages[].id`, a Package URL (PURL) such as
    "pkg:npm/lodash@4.17.15", which dependency-check itself tags with a
    `confidence` level (HIGHEST/HIGH/MEDIUM/LOW) - we prefer the
    highest-confidence entry. `evidenceCollected`'s vendor/product/version
    arrays are free-text guesses scraped from file contents and are
    deliberately NOT used here; they're a weaker signal than a PURL the tool
    already committed to.

    Confidence in this extraction: reasonably high for the common ecosystems
    (npm, Maven, PyPI, NuGet) where dependency-check reliably emits a
    well-formed PURL, but not verified against a real 9.x/10.x report end to
    end - flagged for reviewer follow-up per spec §13.11's pattern for
    secondhand schema details.
    """
    packages = _as_list(dep.get("packages"), "packages")
    if not packages:
        return None, None
    for pkg in packages:
        _as_obj(pkg, "packages")
    ordered = sorted(
        packages,
        key=lambda p: _CONFIDENCE_ORDER.get((p.get("confidence") or "").upper(), 99),
    )
    for pkg in ordered:
        m = _PURL_RE.match(pkg.get("id") or "")
        if m:
            return m.group("name"), m.group("version")
    return None, None


def _as_list(value, label):
    if value is None:
        return []
    if not isinstance(value, list):
        raise base.ParseError("depcheck: %r must be a list, got %r" % (label, type(value).__name__))
    return value


def _as_obj(value, label):
    if not isinstance(value, dict):
        raise base.ParseError("depcheck: %r entry is not an object: %r" % (label, value))
    return value


def parse(raw_path, target):
    """Returns findings, or raises base.ParseError.

    DEFECT 2: an empty, truncated or malformed dependency-check report - and
    a well-formed-but-wrongly-shaped one, such as `{"dependencies": [null]}`
    - must never come back as `[]`. That is indistinguishable from "the tool
    ran and found nothing." JSONDecodeError is caught and re-raised as
    base.ParseError instead of escaping uncaught, which would fail the whole
    routine run rather than just this one cell.
    """
    try:
        with open(raw_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        raise base.ParseError("depcheck: could not read %s: %s" % (raw_path, e)) from e

    if not isinstance(data, dict):
        raise base.ParseError(
            "depcheck: expected a JSON object at the top level, got %r" % type(data).__name__)

    # DEFECT 1: `dependencies` must be PRESENT, not merely absent-or-empty.
    # A real dependency-check report always carries this key (an empty list
    # on a clean scan) - reading a missing key the same as a
    # present-but-empty one used to silently return a clean-looking [].
    if "dependencies" not in data:
        raise base.ParseError("depcheck: report is missing 'dependencies'")

    findings = []
    for dep in _as_list(data.get("dependencies"), "dependencies"):
        dep = _as_obj(dep, "dependencies")
        file_name = dep.get("fileName", "")
        package, version = _package_and_version(dep)
        for vuln in _as_list(dep.get("vulnerabilities"), "vulnerabilities"):
            vuln = _as_obj(vuln, "vulnerabilities")
            rule_id = vuln.get("name", "")
            sev, known = _severity(vuln)
            refs = [r.get("url") for r in (vuln.get("references") or []) if r.get("url")]
            finding = normalize.make_finding(
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
            )
            # Optional deps-merge-key fields (plan Global Constraints,
            # spec Task 18): additive, alongside matched_at, and omitted
            # entirely rather than guessed when unresolved.
            if package is not None:
                finding["package"] = package
            if version is not None:
                finding["version"] = version
            findings.append(finding)
    return findings
