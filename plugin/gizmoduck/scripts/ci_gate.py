"""ci_gate.py - the pass/fail decision a `/gizmoduck:ci` pipeline ends on.

The pipeline fails only on a finding that is NEW since the baseline and is
Critical or High. The identity of a finding is the one `gizmoduck.py diff`
uses - (template_id, matched_at or host) - so the gate and the diff.md artifact
the pipeline publishes can never disagree about what is "new".

It reads the two JSONL files itself rather than parsing diff.md, because the
diff renders severity through SEV_NAME, where an unrecognised severity has
already become Info. Everything this gate cannot read fails closed:

- a new finding whose severity is not one of critical/high/medium/low/info, or
  that carries normalize.py's `severity-assigned` tag (the tool gave none and
  the adapter assigned a default), is UNKNOWN and fails the gate unless
  `trust_assigned` is set - and `trust_assigned` only covers the tagged case,
  never an unreadable value;
- a line that is neither raw Nuclei JSONL nor a normalised finding, in either
  file, fails the gate;
- a missing baseline fails the gate unless `allow_missing_baseline` is set
  (that flag is how a repository creates its first baseline);
- a run manifest with an `error:*` or `skipped-missing` cell fails the gate
  unless `allow_incomplete` is set, because a scanner that did not run is not
  a scanner that found nothing.
"""
import json
from dataclasses import dataclass, field

_SEVERITIES = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
_BLOCKING = 3  # High and above


class GateInputError(ValueError):
    pass


@dataclass
class Finding:
    key: tuple
    severity: int        # -1 means unknown
    severity_label: str
    name: str
    record: dict


@dataclass
class GateResult:
    fail: bool
    reasons: list = field(default_factory=list)
    new_blocking: list = field(default_factory=list)
    new_unknown: list = field(default_factory=list)
    new_total: int = 0
    baseline_present: bool = True

    def to_dict(self):
        return {
            "fail": self.fail,
            "reasons": list(self.reasons),
            "new_total": self.new_total,
            "new_blocking": [f.record for f in self.new_blocking],
            "new_unknown": [f.record for f in self.new_unknown],
            "baseline_present": self.baseline_present,
        }


def _severity_of(record, trust_assigned):
    """(int, label). -1 for anything this gate cannot read as a severity."""
    if "template-id" in record and isinstance(record.get("info"), dict):
        raw = record["info"].get("severity")
        key = str(raw).strip().lower() if raw is not None else ""
        if key in _SEVERITIES:
            return _SEVERITIES[key], key
        return -1, f"unknown ({raw!r})"
    sev = record.get("severity")
    name = str(record.get("severity_name") or "").strip().lower()
    if isinstance(sev, bool) or not isinstance(sev, int) or name not in _SEVERITIES \
            or _SEVERITIES[name] != sev:
        return -1, f"unknown (severity={sev!r}, severity_name={record.get('severity_name')!r})"
    if "severity-assigned" in (record.get("tags") or []) and not trust_assigned:
        return -1, f"unknown (tool gave none; adapter assigned {name})"
    return sev, name


def parse_line(line, trust_assigned=False, where=""):
    try:
        record = json.loads(line)
    except ValueError as exc:
        raise GateInputError(f"{where}: not JSON: {line[:200]!r}") from exc
    if not isinstance(record, dict):
        raise GateInputError(f"{where}: not a JSON object")
    if "template-id" in record and isinstance(record.get("info"), dict):
        key = (record.get("template-id", ""),
               record.get("matched-at", record.get("matched", "")) or record.get("host", ""))
        name = record["info"].get("name") or record.get("template-id", "")
    elif "template_id" in record and "severity_name" in record:
        key = (record["template_id"], record.get("matched_at") or record.get("host", ""))
        name = record.get("name") or record["template_id"]
    else:
        raise GateInputError(f"{where}: line is neither raw Nuclei JSONL nor a normalised "
                             f"gizmoduck finding")
    sev, label = _severity_of(record, trust_assigned)
    return Finding(key=key, severity=sev, severity_label=label, name=name, record=record)


def load_findings(path, trust_assigned=False):
    out = []
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if line.strip():
                out.append(parse_line(line.strip(), trust_assigned, f"{path}:{n}"))
    return out


def incomplete_cells(manifest):
    cells = (manifest or {}).get("cells") or []
    return [c for c in cells
            if str(c.get("status", "")).startswith("error")
            or c.get("status") == "skipped-missing"]


def evaluate(baseline, current, manifest=None, allow_missing_baseline=False,
             allow_incomplete=False):
    """`baseline` is a list of Finding or None (no baseline); `current` a list."""
    result = GateResult(fail=False, baseline_present=baseline is not None)
    if baseline is None:
        if allow_missing_baseline:
            result.reasons.append("no baseline; allowed by GIZMODUCK_ALLOW_NO_BASELINE - "
                                  "this run is accepted and becomes the baseline")
            return _with_coverage(result, manifest, allow_incomplete)
        baseline = []
        result.reasons.append("no baseline found; every finding counts as new "
                              "(set GIZMODUCK_ALLOW_NO_BASELINE=true for a first run)")
    base_keys = {f.key for f in baseline}
    seen = set()
    for f in current:
        if f.key in base_keys or f.key in seen:
            continue
        seen.add(f.key)
        result.new_total += 1
        if f.severity < 0:
            result.new_unknown.append(f)
        elif f.severity >= _BLOCKING:
            result.new_blocking.append(f)
    if result.new_blocking:
        result.fail = True
        result.reasons.append(f"{len(result.new_blocking)} new Critical/High finding(s)")
    if result.new_unknown:
        result.fail = True
        result.reasons.append(f"{len(result.new_unknown)} new finding(s) with an unknown "
                              f"severity (fail closed)")
    return _with_coverage(result, manifest, allow_incomplete)


def _with_coverage(result, manifest, allow_incomplete):
    bad = incomplete_cells(manifest)
    if bad:
        names = ", ".join(f"{c.get('target')}/{c.get('tool')}={c.get('status')}" for c in bad)
        if allow_incomplete:
            result.reasons.append(f"incomplete coverage allowed by GIZMODUCK_ALLOW_INCOMPLETE: {names}")
        else:
            result.fail = True
            result.reasons.append(f"incomplete coverage - a tool that did not run found "
                                  f"nothing only by not running: {names}")
    return result
