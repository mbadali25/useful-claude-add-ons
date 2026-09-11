"""Finding shape and severity normalization shared by every scanner adapter.

Deliberately imports nothing from gizmoduck.py: adapters and their tests must
be loadable without the CLI. The severity ints are re-declared here and are
required to match SEV_NUM at gizmoduck.py:38-41 - test_normalize asserts the
values directly so a drift shows up as a test failure rather than as findings
quietly landing in the wrong band.
"""
import re

# "unknown": 0 is here only because gizmoduck.py:38 carries it - kept for the
# exact-equality parity check below, not because "unknown" is a real severity
# level. sev_from_text excludes it from the recognized-key lookup on purpose:
# a tool that reports the literal text "unknown" must still come back
# unrecognized (known=False), the same as any other unmapped value.
SEV_NUM = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0, "unknown": 0}
SEV_NAME = {4: "critical", 3: "high", 2: "medium", 1: "low", 0: "info"}

_TEXT_ALIASES = {
    "informational": "info",
    "moderate": "medium",   # Bridgecrew legacy
    "important": "high",    # Bridgecrew legacy
}

# ZAP riskcode. Treated as high-confidence inference, not documented fact
# (spec 13.3) - anything outside 0-3 is reported unknown rather than guessed.
_RISKCODE = {0: 0, 1: 1, 2: 2, 3: 3}


def sev_from_text(value, default="info"):
    """Map a tool's text severity to (int, was_recognized).

    was_recognized=False means the caller should mark the finding so a report
    reader can tell an assigned default from a real assessment.
    """
    if value is None:
        return SEV_NUM[default], False
    key = str(value).strip().lower()
    if not key:
        return SEV_NUM[default], False
    key = _TEXT_ALIASES.get(key, key)
    if key in SEV_NUM and key != "unknown":
        return SEV_NUM[key], True
    return SEV_NUM[default], False


def sev_from_cvss(score):
    if score is None or score == "":
        return 0
    try:
        s = float(score)
    except (TypeError, ValueError):
        return 0
    if s >= 9.0:
        return 4
    if s >= 7.0:
        return 3
    if s >= 4.0:
        return 2
    if s > 0:
        return 1
    return 0


def sev_from_riskcode(code):
    try:
        c = int(code)
    except (TypeError, ValueError):
        return 0, False
    if c in _RISKCODE:
        return _RISKCODE[c], True
    return 0, False


def synthetic_id(tool, rule_id):
    return "%s:%s" % (tool, rule_id or "unknown")


def make_finding(tool, target, rule_id, name, severity,
                 severity_known=True, **extra):
    f = {
        "template_id": synthetic_id(tool, rule_id),
        "name": name or rule_id or "",
        "severity": severity,
        "severity_name": SEV_NAME[severity],
        "type": extra.get("type", ""),
        "timestamp": extra.get("timestamp", ""),
        "host": extra.get("host", ""),
        "matched_at": extra.get("matched_at", ""),
        "cve": extra.get("cve") or [],
        "cvss": extra.get("cvss", ""),
        "description": extra.get("description", "") or "",
        "remediation": extra.get("remediation", "") or "",
        "reference": extra.get("reference") or [],
        "tags": extra.get("tags") or [],
        "tool": tool,
        "target": target,
    }
    if not severity_known:
        f["tags"] = list(f["tags"]) + ["severity-assigned"]
    return f


# --- Cross-tool merge for `deps` and `iac` (spec sec 7, plan Task 18) ------
#
# Two tools cover each of these categories - Trivy + Dependency-Check for
# deps, Checkov + Trivy-misconfig for iac - so without a merge the same
# underlying issue is read and ticketed twice. The merge keys below are
# deliberately narrow and must not be widened for a better hit rate: a
# missed merge costs a reader a duplicate row, but an over-eager one hides a
# real, distinct finding behind a single collapsed entry.
#
# merge_category() takes a list of findings that the CALLER has already
# scoped to one category (routine's own target/kind bookkeeping decides
# that, not this function) - nothing here ever merges across categories,
# because each category reads its own, disjoint set of key fields.


def _deps_key(finding):
    """(cve, package, version), or None when there is no CVE id to key on.

    None is a sentinel the caller (merge_category) reads as "never merges" -
    a finding with no CVE always renders on its own (spec sec 7), even if it
    happens to share a package and version with another finding.
    """
    cves = finding.get("cve") or []
    if not cves:
        return None
    return (cves[0], finding.get("package"), finding.get("version"))


def _iac_key(finding):
    """(path, line, resource).

    Checkov and Trivy's misconfig scanner both encode "path:line" into the
    existing `matched_at` field (checkov.py, trivy.py) rather than carrying
    separate path/line keys, and checkov puts the Terraform resource address
    in `host`. Explicit `path`/`line`/`resource` keys are read first so a
    future adapter can supply them directly; matched_at/host are the
    fallback that today's two iac adapters actually populate.
    """
    path = finding.get("path")
    line = finding.get("line")
    if path is None or line is None:
        matched_at = finding.get("matched_at") or ""
        found_path, sep, found_line = matched_at.rpartition(":")
        if path is None:
            path = found_path if sep else matched_at
        if line is None:
            line = found_line if sep else ""
    resource = finding.get("resource") or finding.get("host") or ""
    return (path, str(line), resource)


_KEY_FUNCS = {"deps": _deps_key, "iac": _iac_key}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _title_tokens(name):
    return set(_TOKEN_RE.findall(str(name or "").lower()))


def _native_rule_id(finding):
    """The contributing tool's own rule id, recovered from `template_id`
    ("<tool>:<rule_id>", per synthetic_id) so merged_from can name it
    without the caller having kept the raw rule_id around separately.
    """
    template_id = finding.get("template_id", "")
    _, sep, rest = template_id.partition(":")
    return rest if sep else template_id


def _merge_group(members):
    """Collapse one same-key group into a single finding: the highest
    severity any contributor assigned, every reporting tool in `tools`, and
    each contributor's own rule id preserved in `merged_from` so provenance
    survives the collapse (spec sec 7) - an over-merge is then visible in
    the report rather than silent.
    """
    best = max(members, key=lambda f: f.get("severity", 0))
    merged = dict(best)
    merged["severity_name"] = SEV_NAME[best["severity"]]
    merged["tools"] = sorted({m.get("tool", "") for m in members if m.get("tool")})
    merged["merged_from"] = [
        {"tool": m.get("tool", ""), "rule_id": _native_rule_id(m)}
        for m in members
    ]
    return merged


def merge_category(findings, category):
    """Merge duplicate findings within one category (`"deps"` or `"iac"`).

    Returns `(merged, near_misses)`. `merged` is every input finding, in
    order, with same-key groups collapsed into one entry each (see
    _merge_group) - a finding with no key (e.g. a CVE-less deps finding)
    always passes through unchanged and alone.

    The guard is asymmetric on purpose: if a would-be merge group's titles
    share no token in common, the merge is refused and every member of that
    group passes through separately instead, with the near-miss recorded so
    it is visible (e.g. in the run manifest) rather than silently dropped. A
    duplicate finding costs a reader half a minute to notice; a wrong merge
    hides a real vulnerability behind another one's entry.
    """
    if category not in _KEY_FUNCS:
        raise ValueError(
            "merge_category: category must be one of %s, got %r"
            % (sorted(_KEY_FUNCS), category))
    key_fn = _KEY_FUNCS[category]

    groups = {}
    order = []
    for finding in findings:
        key = key_fn(finding)
        if key is None:
            order.append((None, finding))
            continue
        if key not in groups:
            groups[key] = []
            order.append((key, None))
        groups[key].append(finding)

    merged = []
    near_misses = []
    emitted_keys = set()
    for key, solo_finding in order:
        if key is None:
            merged.append(solo_finding)
            continue
        if key in emitted_keys:
            continue
        emitted_keys.add(key)

        members = groups[key]
        if len(members) == 1:
            merged.append(members[0])
            continue

        token_sets = [_title_tokens(m.get("name")) for m in members]
        shared = set.intersection(*token_sets) if token_sets else set()
        if not shared:
            near_misses.append({
                "category": category,
                "key": key,
                "titles": [m.get("name", "") for m in members],
                "tools": sorted({m.get("tool", "") for m in members if m.get("tool")}),
            })
            merged.extend(members)
            continue

        merged.append(_merge_group(members))

    return merged, near_misses
