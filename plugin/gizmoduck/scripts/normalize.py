"""Finding shape and severity normalization shared by every scanner adapter.

Deliberately imports nothing from gizmoduck.py: adapters and their tests must
be loadable without the CLI. The severity ints are re-declared here and are
required to match SEV_NUM at gizmoduck.py:38-41 - test_normalize asserts the
values directly so a drift shows up as a test failure rather than as findings
quietly landing in the wrong band.
"""

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
