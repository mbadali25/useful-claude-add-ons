"""Tests for the semgrep adapter.

Semgrep is the only tool in this package that reads source code, so it is the
only one that can see a check that is MISSING - an authorization gate nobody
wrote has no signature, no CVE and no misconfigured resource, and the endpoint
answers 200 exactly as it should. The tests that matter most here are the
severity mapping (because Semgrep's vocabulary does not overlap everyone
else's) and the ParseError discipline shared across the package.

Following the convention every sibling adapter uses (checkov, nikto, zap,
testssl, depcheck): `target` is a plain string in both run() and parse() - the
path for run(), the target name for parse() - not an object with attributes.

semgrep.json is shaped from a real `semgrep --config p/security-audit --json`
run (1.177.0) against a Python backend, trimmed to one finding per severity
tier plus one unrecognised tier and one parse error.
"""
import json

import pytest

from scanners import base, semgrep


def _parse(fixture, name="drata-insights"):
    return semgrep.parse(str(fixture("semgrep.json")), name)


def _by_rule(findings, needle):
    return next(f for f in findings if needle in f["template_id"])


# --- module constants -------------------------------------------------

def test_module_constants():
    assert semgrep.NAME == "semgrep"
    assert semgrep.KINDS == ["code"]
    assert semgrep.ACTIVE is False
    assert semgrep.ACTIVE_OPTS == []


def test_registered_under_the_code_kind():
    """A new kind is only real once the registry and routine's location map
    both know it; either half alone leaves `kind: code` unroutable."""
    import routine
    from scanners import ADAPTERS, KIND_DEFAULTS, get

    assert get("semgrep") is semgrep
    assert "semgrep" in ADAPTERS
    assert KIND_DEFAULTS["code"] == ["semgrep"]
    assert routine._location_field_name("code") == "path"


# --- severity mapping -------------------------------------------------
#
# Semgrep's ERROR/WARNING/INFO does not overlap the
# critical/high/medium/low/info vocabulary the rest of the package uses.
# Handing it to sev_from_text would score every WARNING as `info` through the
# default and drop the bulk of a real run below the report's Medium floor.

def test_error_maps_to_high(fixture):
    f = _by_rule(_parse(fixture), "debug-enabled")
    assert f["severity_name"] == "high"
    assert "severity-assigned" not in f["tags"]


def test_warning_maps_to_medium(fixture):
    """The tier most security rules use. If this lands below Medium the whole
    adapter contributes nothing to a Medium-and-above report."""
    f = _by_rule(_parse(fixture), "dynamic-urllib-use-detected")
    assert f["severity_name"] == "medium"
    assert "severity-assigned" not in f["tags"]


def test_info_maps_to_info(fixture):
    f = _by_rule(_parse(fixture), "arbitrary-sleep")
    assert f["severity_name"] == "info"


def test_nothing_maps_to_critical(fixture):
    """Semgrep does not assign a critical tier. Inventing one would rank SAST
    findings above CVEs carrying real CVSS scores in the same report."""
    assert all(f["severity_name"] != "critical" for f in _parse(fixture))


def test_unrecognised_tier_is_marked_not_guessed(fixture):
    """NOTICE is not one of Semgrep's three documented tiers. It falls back to
    info AND carries the marker, so a reader can tell an assigned default from
    Semgrep's own assessment."""
    f = _by_rule(_parse(fixture), "detected-generic-secret")
    assert f["severity_name"] == "info"
    assert "severity-assigned" in f["tags"]


# --- finding shape ----------------------------------------------------

def test_location_carries_path_and_line(fixture):
    f = _by_rule(_parse(fixture), "dynamic-urllib-use-detected")
    assert f["matched_at"] == "backend/src/common/drata.py:106"
    assert f["path"] == "backend/src/common/drata.py"
    assert f["line"] == 106


def test_name_is_the_first_line_of_the_message(fixture):
    f = _by_rule(_parse(fixture), "debug-enabled")
    assert f["name"].startswith("Detected Flask app with debug=True")
    assert "\n" not in f["name"]


def test_fix_becomes_remediation_and_is_optional(fixture):
    findings = _parse(fixture)
    assert _by_rule(findings, "debug-enabled")["remediation"] == "app.run(debug=False)"
    assert _by_rule(findings, "arbitrary-sleep")["remediation"] == ""


def test_cwe_and_shortlink_are_carried(fixture):
    f = _by_rule(_parse(fixture), "dynamic-urllib-use-detected")
    assert "sast" in f["tags"]
    assert any("CWE-939" in t for t in f["tags"])
    assert "https://sg.run/dKZZ" in f["reference"]


def test_target_and_tool_are_recorded(fixture):
    f = _parse(fixture)[0]
    assert f["tool"] == "semgrep"
    assert f["target"] == "drata-insights"


# --- ParseError discipline -------------------------------------------
#
# The package rule: parse() must never turn a parse failure into an empty
# finding list. A file semgrep never scanned must not look identical to
# "scanned and found nothing".

def test_clean_run_is_an_empty_list_not_an_error(tmp_path):
    p = tmp_path / "semgrep.json"
    p.write_text(json.dumps({"results": [], "errors": []}), encoding="utf-8")
    assert semgrep.parse(str(p), "t") == []


def test_empty_output_raises(tmp_path):
    p = tmp_path / "semgrep.json"
    p.write_text("", encoding="utf-8")
    with pytest.raises(base.ParseError):
        semgrep.parse(str(p), "t")


def test_invalid_json_raises(tmp_path):
    p = tmp_path / "semgrep.json"
    p.write_text('{"results": [', encoding="utf-8")
    with pytest.raises(base.ParseError):
        semgrep.parse(str(p), "t")


def test_missing_results_key_raises(tmp_path):
    """Semgrep always emits `results`, even on a clean run. Its absence means
    this is not a semgrep report at all."""
    p = tmp_path / "semgrep.json"
    p.write_text(json.dumps({"errors": [], "version": "1.177.0"}), encoding="utf-8")
    with pytest.raises(base.ParseError):
        semgrep.parse(str(p), "t")


def test_wrongly_shaped_results_entry_raises(tmp_path):
    p = tmp_path / "semgrep.json"
    p.write_text(json.dumps({"results": ["a string, not an object"]}),
                 encoding="utf-8")
    with pytest.raises(base.ParseError):
        semgrep.parse(str(p), "t")


def test_unreadable_path_raises(tmp_path):
    with pytest.raises(base.ParseError):
        semgrep.parse(str(tmp_path / "does-not-exist.json"), "t")


# --- scan_errors ------------------------------------------------------

def test_scan_errors_are_surfaced_not_raised(fixture):
    """Files semgrep could not parse contributed no findings - a different
    claim from "the report is unreadable". Surfaced so a mostly-failed run is
    visible, never silently dropped."""
    errs = semgrep.scan_errors(str(fixture("semgrep.json")))
    assert len(errs) == 1
    assert "legacy.ts" in errs[0]
    # and the parseable half still yields findings
    assert len(_parse(fixture)) == 4


# --- run() ------------------------------------------------------------

def test_missing_binary_returns_no_raw_path(monkeypatch, tmp_path):
    monkeypatch.setattr(base, "which", lambda b: None)
    raw, result = semgrep.run(str(tmp_path), str(tmp_path / "out"))
    assert raw is None
    assert result.returncode == -1
    assert "not found" in result.stderr


def test_timeout_writes_nothing(monkeypatch, tmp_path):
    """A timed-out run's stdout may be truncated mid-JSON. Writing it would
    hand parse() something that looks parseable and is not."""
    monkeypatch.setattr(base, "which", lambda b: "semgrep")
    monkeypatch.setattr(base, "run_tool", lambda *a, **k: base.ToolResult(
        -1, '{"results": [{"che', "", True))
    raw, result = semgrep.run(str(tmp_path), str(tmp_path / "out"))
    assert raw is None
    assert result.timed_out is True


def test_memory_and_job_caps_are_passed(monkeypatch, tmp_path):
    """Not tuning - a stability requirement. Semgrep defaults to one worker
    per core with no memory ceiling, and across a repo-wide run that is what
    exhausts the machine. The OS kills the process, which reads as a hang
    rather than a scanner problem."""
    seen = {}
    monkeypatch.setattr(base, "which", lambda b: "semgrep")

    def _fake(argv, timeout, cwd=None):
        seen["argv"] = argv
        return base.ToolResult(0, '{"results": [], "errors": []}', "", False)

    monkeypatch.setattr(base, "run_tool", _fake)
    semgrep.run(str(tmp_path), str(tmp_path / "out"))
    assert "--max-memory" in seen["argv"]
    assert "-j" in seen["argv"]
    assert str(semgrep.DEFAULT_MAX_MEMORY_MB) in seen["argv"]


def test_exit_code_one_is_not_treated_as_failure(monkeypatch, tmp_path):
    """Semgrep exits 1 when findings exist - the same 0/1 ambiguity trivy and
    sqlmap have. Per the package rule the status is never inspected; the
    parsed output decides."""
    monkeypatch.setattr(base, "which", lambda b: "semgrep")
    payload = json.dumps({"results": [
        {"check_id": "r", "path": "a.py", "start": {"line": 1},
         "extra": {"severity": "ERROR", "message": "m", "metadata": {}}}],
        "errors": []})
    monkeypatch.setattr(base, "run_tool",
                        lambda *a, **k: base.ToolResult(1, payload, "", False))
    raw, _ = semgrep.run(str(tmp_path), str(tmp_path / "out"))
    assert raw is not None
    assert len(semgrep.parse(raw, "t")) == 1
