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

# Vendored/installed trees that contribute no dependency coverage (trivy reads
# lockfiles, not installed packages) and plenty of secret-scanner noise from
# third-party test fixtures. See the comment at the --skip-dirs loop in run().
#
# THE `**/` PREFIX IS LOAD-BEARING. A bare `.venv` matches only a directory at
# the scan root, so `backend/.venv/` sails straight through - verified against
# trivy directly: `--skip-dirs .venv` still returned 3 secrets from
# `backend/.venv/Lib/site-packages/moto/`, while `--skip-dirs '**/.venv/**'`
# returned 0. Do not "simplify" these back to bare directory names.
DEFAULT_SKIP_DIRS = ("**/.venv/**", "**/venv/**", "**/node_modules/**",
                     "**/.terraform/**", "**/site-packages/**",
                     "**/frontend_dist/**", "**/.git/**")


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

    # DEFECT 1 (critical): establish freshness BEFORE invoking trivy. Without
    # this, a stale file left over from a previous run in the same outdir
    # would still be sitting at raw_path after a failed invocation that wrote
    # nothing new, and the `raw_path.exists()` check below would return it as
    # if it were this run's evidence - a failed scan inheriting the previous
    # run's clean bill of health.
    if raw_path.exists():
        raw_path.unlink()

    trivy_timeout = opts.get("trivy_timeout", DEFAULT_TRIVY_TIMEOUT)
    argv = ["trivy", "fs", "--format", "json", "--scanners", scanner,
            "--timeout", trivy_timeout, "--output", str(raw_path), str(path)]

    # Skip vendored and installed trees. Trivy reads LOCKFILES for dependency
    # CVEs - requirements.txt, package-lock.json, go.sum - so an installed
    # .venv or node_modules adds no dependency coverage at all. What it does
    # add is secret-scanner noise from third-party test fixtures, and that is
    # not hypothetical: a real sweep of 18 modules reported moto's mock AWS
    # access key as a CRITICAL committed secret and its test CA keys as HIGH,
    # all out of a gitignored virtualenv. Those three outranked the one genuine
    # critical in the same run (unrestricted security-group egress) and buried
    # it.
    #
    # Overridable per target, because a repo that genuinely vendors its
    # dependencies into the tree has the opposite need.
    for d in opts.get("trivy_skip_dirs", DEFAULT_SKIP_DIRS):
        argv += ["--skip-dirs", d]

    timeout = opts.get("timeout", DEFAULT_TIMEOUT)
    result = base.run_tool(argv, timeout=timeout, cwd=opts.get("cwd"))
    if result.timed_out or not raw_path.exists():
        return None, result
    return str(raw_path), result


def _first_cvss(cvss_block):
    if not cvss_block:
        return ""
    if not isinstance(cvss_block, dict):
        raise base.ParseError(
            "trivy: 'CVSS' must be an object, got %r" % type(cvss_block).__name__)
    for source in ("nvd", "redhat", "ghsa"):
        entry = cvss_block.get(source)
        if entry and entry.get("V3Score") is not None:
            return entry["V3Score"]
    for entry in cvss_block.values():
        if entry and entry.get("V3Score") is not None:
            return entry["V3Score"]
    return ""


def _as_list(value, label):
    """Validate an optional array field: None/absent -> [], present-but-not-a-
    list -> raise. Shape validation counts as a parse failure just as much as
    malformed JSON does (plan Global Constraints) - a Results/Vulnerabilities
    field that isn't the array shape trivy documents must never be silently
    coerced into an empty list.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        raise base.ParseError("trivy: %r must be a list, got %r" % (label, type(value).__name__))
    return value


def _as_obj(value, label):
    if not isinstance(value, dict):
        raise base.ParseError("trivy: %r entry is not an object: %r" % (label, value))
    return value


def _parse_vulnerabilities(results, target_name):
    findings = []
    for result in results:
        result = _as_obj(result, "Results")
        file_target = result.get("Target", "")
        for vuln in _as_list(result.get("Vulnerabilities"), "Vulnerabilities"):
            vuln = _as_obj(vuln, "Vulnerabilities")
            sev, known = normalize.sev_from_text(vuln.get("Severity"))
            pkg = vuln.get("PkgName", "")
            installed = vuln.get("InstalledVersion", "")
            fixed = vuln.get("FixedVersion", "")
            rule_id = vuln.get("VulnerabilityID", "")
            primary_url = vuln.get("PrimaryURL")
            references = ([primary_url] if primary_url else []) + \
                list(vuln.get("References") or [])
            remediation = ("upgrade %s to %s" % (pkg, fixed)) if fixed else ""
            finding = normalize.make_finding(
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
            )
            # Merge-key fields for Task 18's deps merge (CVE, package,
            # version) - additive, alongside matched_at rather than instead
            # of it, and omitted entirely when trivy didn't carry them (plan
            # Global Constraints: absent means "does not merge on this
            # slot", never a guessed value).
            if pkg:
                finding["package"] = pkg
            if installed:
                finding["version"] = installed
            findings.append(finding)
    return findings


def _parse_misconfigurations(results, target_name):
    findings = []
    for result in results:
        result = _as_obj(result, "Results")
        file_target = result.get("Target", "")
        for mis in _as_list(result.get("Misconfigurations"), "Misconfigurations"):
            mis = _as_obj(mis, "Misconfigurations")
            sev, known = normalize.sev_from_text(mis.get("Severity"))
            rule_id = mis.get("ID", "")
            cause = mis.get("CauseMetadata") or {}
            start_line = cause.get("StartLine")
            matched_at = ("%s:%s" % (file_target, start_line)
                          if start_line else file_target)
            primary_url = mis.get("PrimaryURL")
            finding = normalize.make_finding(
                NAME, target_name, rule_id, mis.get("Title") or rule_id, sev,
                severity_known=known,
                type="misconfiguration",
                description=mis.get("Description", ""),
                remediation=mis.get("Resolution", ""),
                reference=[primary_url] if primary_url else [],
                matched_at=matched_at,
            )
            # Merge-key fields for Task 18's iac merge (path, line,
            # resource) - additive alongside matched_at, not a replacement
            # for it. `path` is the file alone (matched_at keeps the
            # "file:line" form the report reads); `line` is the *start*
            # line only, per plan Global Constraints - Checkov and Trivy
            # will not agree on where a block ends. Each is omitted when
            # trivy's own output doesn't carry it.
            if file_target:
                finding["path"] = file_target
            if start_line is not None:
                finding["line"] = int(start_line)
            resource = cause.get("Resource")
            if resource:
                finding["resource"] = resource
            findings.append(finding)
    return findings


def parse(raw_path, target, kind=None):
    """Returns findings for the requested kind, or raises base.ParseError.

    DEFECT 2: an empty, truncated or malformed trivy report - and a
    well-formed-but-wrongly-shaped one, such as `{"Results": [null]}` - must
    never come back as `[]`. That is indistinguishable from "trivy ran and
    found nothing," which is the exact false-assurance the coverage table
    exists to prevent. JSONDecodeError is caught and re-raised as
    base.ParseError rather than allowed to escape uncaught (which would fail
    the whole routine run instead of just this cell).
    """
    kind = _resolve_kind(target, kind)
    target_name = _target_name(target)

    try:
        with open(raw_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        raise base.ParseError("trivy: could not read %s: %s" % (raw_path, e)) from e

    if not isinstance(data, dict):
        raise base.ParseError(
            "trivy: expected a JSON object at the top level, got %r" % type(data).__name__)

    # DEFECT 1, corrected against real trivy 0.74.0 output: `Results` is
    # `omitempty` on trivy's own Report struct, so a genuine clean scan - one
    # where trivy ran fine but found no artifacts to report on at all, e.g.
    # `trivy fs` over a directory with no recognized lockfiles/IaC files -
    # omits the key ENTIRELY rather than emitting `"Results": []`. Both an
    # `fs` scan of a real repo with no Python/npm lockfile and a scan of a
    # truly empty directory were captured live and neither carries a
    # `Results` key at all (spec 13.7 addendum). Treating that as a parse
    # failure would reject every genuinely clean trivy run, which is the
    # opposite of the false-clean this check exists to prevent.
    #
    # The distinguishing signal is the rest of the trivy envelope: a real
    # report - Results-bearing or not - always carries `ArtifactType`
    # (verified against live captures). A file missing `Results` AND that
    # sentinel is not trivy's own output and must still raise.
    if "Results" not in data:
        if "ArtifactType" not in data:
            raise base.ParseError("trivy: report is missing 'Results'")
        results = []
    else:
        results = _as_list(data.get("Results"), "Results")

    if kind == "deps":
        return _parse_vulnerabilities(results, target_name)
    return _parse_misconfigurations(results, target_name)
