"""ci_gate.py - the pass/fail decision a `/gizmoduck:ci` pipeline ends on.

The pipeline fails only on a finding that is NEW since the baseline and is
Critical or High. The identity of a finding is the one `gizmoduck.py diff`
uses - (template_id, matched_at or host) - so the gate and the diff.md artifact
the pipeline publishes can never disagree about what is "new".

It reads the two JSONL files itself rather than parsing diff.md, because the
diff renders severity through SEV_NAME, where an unrecognised severity has
already become Info. Everything this gate cannot read fails closed:

- a finding whose severity is not one of critical/high/medium/low/info, or
  that carries normalize.py's `severity-assigned` tag (the tool gave none and
  the adapter assigned a default), is UNKNOWN - in the current scan when it is
  new, and in the BASELINE whenever it is there at all, because an unknown
  baseline record would otherwise suppress a current Critical with the same
  identity. `trust_assigned` covers only the tagged case, never an unreadable
  value;
- several current records sharing one identity are judged at their MAXIMUM
  severity, so the order a scanner wrote them in cannot hide a High behind a
  Low;
- a line that is neither raw Nuclei JSONL nor a normalised finding, in either
  file, fails the gate;
- a missing baseline fails the gate on its own - even when the scan found
  nothing - unless `allow_missing_baseline` is set (that flag is how a
  repository creates its first baseline);
- the run manifest must list at least one cell, and every cell must be one of
  the exact statuses in COMPLETE_STATUSES: `ran`, `skipped-active` (an active
  tool that declined by design) or a `ran(<mode>)` an adapter actually writes.
  No manifest, no cells, `error:*`, `skipped-missing` or any status this gate
  does not know fails unless `allow_incomplete` is set, because a scanner that
  did not run is not a scanner that found nothing.

`block_at` is the trigger tier's threshold (ci_render.py): 4 blocks on a new
Critical only (tier 1, the light PR check), 3 on a new Critical or High
(tier 2 and manual runs), and None never blocks (tier 3, the weekly sweep).
None changes only the verdict: every reason above is still computed and
reported, and `new_blocking` still lists the new Critical/High findings so
the sweep can ticket them.
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


# Every status that proves a tool ran, as exact strings. The `ran(<mode>)`
# forms are the ones routine._ran_status writes from routine._MODE_LABELS
# (nmap and zap, the two adapters with ACTIVE_OPTS); a test holds the two in
# step. Anything else - `ran()`, `ran(anything)`, a mode no adapter defines -
# is not proof of coverage and fails.
COMPLETE_STATUSES = frozenset({
    "ran", "skipped-active",
    "ran(safe)", "ran(safe+vuln)",
    "ran(baseline)", "ran(baseline+active)",
})


def _cell_complete(cell):
    status = cell.get("status") if isinstance(cell, dict) else None
    return isinstance(status, str) and status in COMPLETE_STATUSES


def incomplete_cells(manifest):
    """Every cell that does not prove its tool ran. A manifest with no cells at
    all is one synthetic incomplete cell: coverage nobody recorded is not
    coverage."""
    if not isinstance(manifest, dict):
        return [{"target": "(run)", "tool": "(all)", "status": "no run manifest"}]
    cells = manifest.get("cells")
    if not isinstance(cells, list) or not cells:
        return [{"target": "(run)", "tool": "(all)", "status": "no coverage cells"}]
    return [c if isinstance(c, dict) else {"target": "?", "tool": "?", "status": repr(c)}
            for c in cells if not _cell_complete(c)]


BLOCK_AT = {"critical": 4, "high": 3, "never": None}


def evaluate(baseline, current, manifest=None, allow_missing_baseline=False,
             allow_incomplete=False, block_at=_BLOCKING):
    """`baseline` is a list of Finding or None (no baseline); `current` a list;
    `manifest` the run manifest (None is incomplete coverage)."""
    result = _evaluate(baseline, current, manifest, allow_missing_baseline, allow_incomplete,
                       _BLOCKING if block_at is None else block_at)
    if block_at is None and result.fail:
        result.fail = False
        result.reasons.append("report only: this tier never blocks (the findings above are recorded, "
                              "diffed and optionally ticketed)")
    return result


def _worst_by_key(findings):
    """{key: (worst Finding, any_unknown)} - order-independent. The worst is the
    highest known severity; an unknown one is tracked separately so it still
    fails even beside a known record of the same identity."""
    out = {}
    for f in findings:
        worst, unknown = out.get(f.key, (None, False))
        if f.severity < 0:
            unknown = True
            if worst is None:
                worst = f
        elif worst is None or worst.severity < 0 or f.severity > worst.severity:
            worst = f
        out[f.key] = (worst, unknown)
    return out


def _evaluate(baseline, current, manifest, allow_missing_baseline, allow_incomplete, threshold):
    result = GateResult(fail=False, baseline_present=baseline is not None)
    first_run = baseline is None and allow_missing_baseline
    if baseline is None:
        if allow_missing_baseline:
            result.reasons.append("no baseline; allowed by GIZMODUCK_ALLOW_NO_BASELINE - "
                                  "this run is accepted and becomes the baseline")
        else:
            result.fail = True
            result.reasons.append("no baseline found - failing closed; nothing can be called new or "
                                  "old without one (set GIZMODUCK_ALLOW_NO_BASELINE=true for a first run)")
        baseline = []
    base_unknown = [f for f in baseline if f.severity < 0]
    if base_unknown:
        result.fail = True
        result.reasons.append(f"{len(base_unknown)} baseline finding(s) with an unknown severity "
                              f"(fail closed - an unreadable baseline record could hide a new "
                              f"Critical/High with the same identity)")
    base_keys = {f.key for f in baseline}
    for key, (worst, unknown) in _worst_by_key(current).items():
        if key in base_keys:
            continue
        result.new_total += 1
        if unknown:
            result.new_unknown.append(next(f for f in current if f.key == key and f.severity < 0))
        if worst.severity >= threshold and not first_run:
            result.new_blocking.append(worst)
    if result.new_blocking:
        result.fail = True
        label = "Critical" if threshold >= 4 else "Critical/High"
        result.reasons.append(f"{len(result.new_blocking)} new {label} finding(s)")
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
