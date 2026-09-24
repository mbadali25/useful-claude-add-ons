"""ci_gate.py and `gizmoduck_ci.py gate` - fail only on NEW Critical/High, and fail
closed on anything the gate cannot read.

SABOTAGE-TEST before trusting a change here: in a scratch copy of ci_gate.py,
make an unknown severity count as Info, drop the baseline-key check, lower the
blocking floor to Medium, treat a missing baseline as empty-and-passing, treat
an empty/absent manifest or an unknown cell status as complete, skip unknown
severities in the baseline, or keep the first of several duplicate records,
and confirm the matching case below goes red. Restore the copy afterwards.
"""
import json
import subprocess
import sys
from pathlib import Path

import ci_gate
import gizmoduck_ci
import pytest

_CLI = Path(__file__).resolve().parent.parent / "gizmoduck_ci.py"
_GZ = Path(__file__).resolve().parent.parent / "gizmoduck.py"


def norm(tid, sev, where="app.py:1", tags=None, name=None):
    names = {4: "critical", 3: "high", 2: "medium", 1: "low", 0: "info"}
    return {"template_id": tid, "name": name or tid, "severity": sev,
            "severity_name": names[sev], "type": "", "timestamp": "", "host": "",
            "matched_at": where, "cve": [], "cvss": "", "description": "", "remediation": "",
            "reference": [], "tags": tags or [], "tool": "semgrep", "target": "code"}


def raw(tid, sev, where="https://staging.example.com/"):
    return {"template-id": tid, "info": {"name": tid, "severity": sev},
            "host": "staging.example.com", "matched-at": where, "type": "http"}


def jsonl(path, records):
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return path


def parse(records, trust=False):
    return [ci_gate.parse_line(json.dumps(r), trust) for r in records]


OK = {"cells": [{"target": "code", "tool": "semgrep", "status": "ran"}]}


def evaluate(baseline, current, manifest="complete", **kw):
    """ci_gate.evaluate with a complete run manifest unless a test says otherwise."""
    return ci_gate.evaluate(baseline, current, OK if manifest == "complete" else manifest, **kw)


def test_new_high_fails():
    r = evaluate(parse([]), parse([norm("semgrep:x", 3)]))
    assert r.fail and len(r.new_blocking) == 1


def test_new_critical_fails():
    assert evaluate(parse([]), parse([norm("semgrep:x", 4)])).fail


def test_existing_high_passes():
    rec = norm("semgrep:x", 3)
    r = evaluate(parse([rec]), parse([rec]))
    assert not r.fail and r.new_total == 0


def test_same_rule_at_a_new_location_is_new():
    r = evaluate(parse([norm("semgrep:x", 3, "a.py:1")]),
                         parse([norm("semgrep:x", 3, "b.py:9")]))
    assert r.fail


@pytest.mark.parametrize("sev", [2, 1, 0])
def test_new_medium_low_info_pass(sev):
    r = evaluate(parse([]), parse([norm("semgrep:x", sev)]))
    assert not r.fail and r.new_total == 1


def test_raw_nuclei_high_fails_and_medium_passes():
    assert evaluate(parse([]), parse([raw("t1", "high")])).fail
    assert not evaluate(parse([]), parse([raw("t1", "medium")])).fail


@pytest.mark.parametrize("record", [
    raw("t1", "unknown"),
    raw("t1", None),
    raw("t1", "severe"),
    {**norm("x:y", 2), "severity": 7},
    {**norm("x:y", 2), "severity": "high"},
    {**norm("x:y", 2), "severity": True},
    {**norm("x:y", 2), "severity_name": "bogus"},
    {**norm("x:y", 2), "severity_name": "high"},     # int and name disagree
    norm("checkov:CKV_1", 2, tags=["severity-assigned"]),
])
def test_unknown_severity_fails_closed(record):
    r = evaluate(parse([]), parse([record]))
    assert r.fail and len(r.new_unknown) == 1, r.reasons


def test_trust_assigned_severity_covers_only_the_tagged_case():
    tagged = norm("checkov:CKV_1", 2, tags=["severity-assigned"])
    assert not evaluate(parse([]), parse([tagged], trust=True)).fail
    assert evaluate(parse([]), parse([raw("t1", "unknown")], trust=True)).fail


def test_unknown_severity_in_the_baseline_fails_closed():
    rec = raw("t1", "unknown")
    r = evaluate(parse([rec]), parse([rec]))
    assert r.fail and "baseline" in " ".join(r.reasons)


def test_unknown_baseline_record_cannot_suppress_a_new_critical():
    base = {**norm("semgrep:x", 3), "severity": 9, "severity_name": "critical"}
    assert evaluate(parse([base]), parse([norm("semgrep:x", 3)])).fail


@pytest.mark.parametrize("order", [(1, 3), (3, 1), (0, 4, 2)])
def test_duplicate_identities_are_judged_at_their_max_severity(order):
    r = evaluate(parse([]), parse([norm("semgrep:x", s) for s in order]))
    assert r.fail and [f.severity for f in r.new_blocking] == [max(order)] and r.new_total == 1


def test_duplicate_identity_with_an_unknown_severity_still_fails():
    r = evaluate(parse([]), parse([norm("semgrep:x", 1), raw("semgrep:x", "bogus", "app.py:1")]))
    assert r.fail and len(r.new_unknown) == 1


def test_missing_baseline_fails_closed_on_high():
    r = evaluate(None, parse([norm("semgrep:x", 3)]))
    assert r.fail and not r.baseline_present


@pytest.mark.parametrize("records", [[], [norm("semgrep:x", 2)], [norm("semgrep:x", 0)]])
def test_missing_baseline_fails_even_with_nothing_blocking(records):
    r = evaluate(None, parse(records))
    assert r.fail and any("no baseline" in x for x in r.reasons)


def test_missing_baseline_allowed_passes_as_first_run():
    r = evaluate(None, parse([norm("semgrep:x", 4)]), allow_missing_baseline=True)
    assert not r.fail


def test_first_run_opt_in_still_fails_an_unknown_severity():
    assert evaluate(None, parse([raw("t1", "bogus")]), allow_missing_baseline=True).fail


@pytest.mark.parametrize("status", ["error:timeout", "error:returncode=2", "skipped-missing", "not-run",
                                    "", None, 3, "ran-ish", "RAN", "skipped"])
def test_incomplete_coverage_fails_unless_allowed(status):
    manifest = {"cells": [{"target": "code", "tool": "semgrep", "status": status}]}
    assert evaluate(parse([]), parse([]), manifest).fail
    assert not evaluate(parse([]), parse([]), manifest, allow_incomplete=True).fail


@pytest.mark.parametrize("manifest", [None, {}, {"cells": []}, {"cells": None}, {"cells": "ran"}, [],
                                      {"cells": ["ran"]}, {"cells": [{"target": "a", "tool": "b"}]}])
def test_missing_or_empty_coverage_fails_closed(manifest):
    r = ci_gate.evaluate(parse([]), parse([]), manifest)
    assert r.fail and any("incomplete coverage" in x for x in r.reasons)
    assert not ci_gate.evaluate(parse([]), parse([]), manifest, allow_incomplete=True).fail


def test_ran_and_skipped_active_cells_are_complete():
    manifest = {"cells": [{"target": "a", "tool": "semgrep", "status": "ran"},
                          {"target": "a", "tool": "zap", "status": "ran(baseline)"},
                          {"target": "a", "tool": "sqlmap", "status": "skipped-active"}]}
    assert not evaluate(parse([]), parse([]), manifest).fail


@pytest.mark.parametrize("line", ["not json", "[1,2]", '{"hello": "world"}'])
def test_unreadable_line_is_an_error(line):
    with pytest.raises(ci_gate.GateInputError):
        ci_gate.parse_line(line)


# --- the CLI, as the pipeline runs it -------------------------------------

def run_gate(tmp_path, base, cur, *extra, env=None, manifest="complete"):
    argv = [sys.executable, str(_CLI), "gate", "--current", str(cur),
            "--json-out", str(tmp_path / "gate.json"), "--new-out", str(tmp_path / "new.jsonl")]
    if manifest is not None and "--manifest" not in extra:
        path = tmp_path / "run-manifest.json"
        path.write_text(json.dumps(OK if manifest == "complete" else manifest), encoding="utf-8")
        argv += ["--manifest", str(path)]
    if base is not None:
        argv += ["--baseline", str(base)]
    return subprocess.run(argv + list(extra), capture_output=True, text=True,
                          env={"PATH": "", **(env or {})}, check=False)


def test_cli_exit_codes_and_new_out(tmp_path):
    base = jsonl(tmp_path / "b.jsonl", [norm("semgrep:old", 3)])
    cur = jsonl(tmp_path / "c.jsonl", [norm("semgrep:old", 3), norm("semgrep:new", 3),
                                       norm("semgrep:med", 2)])
    p = run_gate(tmp_path, base, cur)
    assert p.returncode == 1, p.stdout + p.stderr
    new = [json.loads(x) for x in (tmp_path / "new.jsonl").read_text().splitlines()]
    assert [r["template_id"] for r in new] == ["semgrep:new"]
    assert json.loads((tmp_path / "gate.json").read_text())["fail"] is True


def test_cli_passes_on_existing_only(tmp_path):
    base = jsonl(tmp_path / "b.jsonl", [norm("semgrep:old", 3)])
    cur = jsonl(tmp_path / "c.jsonl", [norm("semgrep:old", 3), norm("semgrep:med", 2)])
    assert run_gate(tmp_path, base, cur).returncode == 0


def test_cli_missing_baseline_and_env_override(tmp_path):
    cur = jsonl(tmp_path / "c.jsonl", [norm("semgrep:x", 3)])
    missing = tmp_path / "nope.jsonl"
    assert run_gate(tmp_path, missing, cur).returncode == 1
    assert run_gate(tmp_path, missing, cur,
                    env={"GIZMODUCK_ALLOW_NO_BASELINE": "true"}).returncode == 0


def test_cli_without_a_manifest_fails_closed(tmp_path):
    cur = jsonl(tmp_path / "c.jsonl", [])
    p = run_gate(tmp_path, cur, cur, manifest=None)
    assert p.returncode == 1 and "incomplete coverage" in p.stdout


def test_cli_corrupt_current_fails_closed(tmp_path):
    cur = tmp_path / "c.jsonl"
    cur.write_text("{not json\n", encoding="utf-8")
    p = run_gate(tmp_path, None, cur)
    assert p.returncode == 2 and "GIZMODUCK_GATE_FAILED" in p.stderr


def test_cli_missing_manifest_fails_closed(tmp_path):
    cur = jsonl(tmp_path / "c.jsonl", [])
    p = run_gate(tmp_path, cur, cur, "--manifest", str(tmp_path / "absent.json"))
    assert p.returncode == 2


def test_gate_and_gizmoduck_diff_agree_on_what_is_new(tmp_path, fixture):
    """The gate re-derives "new" itself; it must match `gizmoduck.py diff`."""
    records = [json.loads(x) for x in fixture("nuclei.jsonl").read_text().splitlines() if x.strip()]
    base = jsonl(tmp_path / "b.jsonl", records[: len(records) // 2])
    cur = jsonl(tmp_path / "c.jsonl", records)
    diff = subprocess.run([sys.executable, str(_GZ), "diff", str(base), str(cur),
                           "--min-severity", "info"], capture_output=True, text=True, check=True)
    diff_new = int(diff.stdout.split("**New findings:** ")[1].split()[0])
    result = ci_gate.evaluate(ci_gate.load_findings(base), ci_gate.load_findings(cur))
    assert diff_new > 0
    assert result.new_total == diff_new


def test_env_truthiness_is_exact():
    assert gizmoduck_ci._truthy("true") and gizmoduck_ci._truthy(" TRUE ")
    assert not any(gizmoduck_ci._truthy(v) for v in ("", "1", "yes", "false", None))
