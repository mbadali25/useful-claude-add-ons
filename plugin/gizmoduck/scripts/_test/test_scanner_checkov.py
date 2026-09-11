"""Tests for the checkov adapter.

Checkov's own severity field is normally null in a free/open-source run
(spec 13.5), so the primary fixture (checkov.json) is the JSON *array* shape
(multi-framework) with every failed check carrying severity: null. A second
fixture (checkov-single.json) covers the single-object shape and exercises
populated severities, including the legacy MODERATE->medium alias.

Following the convention every sibling adapter in this package uses (nikto,
zap, testssl, depcheck): `target` is a plain string in both run() and
parse() - the location string (a path, here) for run(), the target name for
parse() - not an object with attributes.
"""
import json

import pytest

from scanners import base, checkov


def _parse(fixture, name="thd-processors-terraform"):
    return checkov.parse(str(fixture("checkov.json")), name)


# --- module constants -------------------------------------------------

def test_module_constants():
    assert checkov.NAME == "checkov"
    assert checkov.KINDS == ["iac"]
    assert checkov.ACTIVE is False
    assert checkov.ACTIVE_OPTS == []


# --- parse(): array shape, severity null is the normal path -----------

def test_array_shape_yields_only_failed_checks_across_frameworks(fixture):
    findings = _parse(fixture)
    # 2 failed checks in the terraform report + 1 in the secrets report;
    # the one passed_checks entry must not appear.
    assert len(findings) == 3


def test_null_severity_is_the_normal_path_not_an_edge_case(fixture):
    findings = _parse(fixture)
    for f in findings:
        assert f["severity"] == 2
        assert f["severity_name"] == "medium"
        assert "severity-assigned" in f["tags"]


def test_template_id_is_namespaced_by_tool(fixture):
    ids = {f["template_id"] for f in _parse(fixture)}
    assert ids == {"checkov:CKV_AWS_20", "checkov:CKV_AWS_21", "checkov:CKV_SECRET_6"}


def test_target_is_set_from_the_argument(fixture):
    findings = checkov.parse(str(fixture("checkov.json")), "site-a")
    assert all(f["target"] == "site-a" for f in findings)


def test_matched_at_combines_file_path_and_line_range(fixture):
    by_id = {f["template_id"]: f for f in _parse(fixture)}
    assert by_id["checkov:CKV_AWS_20"]["matched_at"] == "/main.tf:10-25"
    # guideline is null on the secrets entry - reference must not carry it
    assert by_id["checkov:CKV_SECRET_6"]["reference"] == []


def test_merge_key_fields_are_populated_alongside_matched_at_and_host(fixture):
    """Task 18's iac cross-tool merge keys on (path, line, resource) as
    distinct fields - these must be additive, not a replacement for
    matched_at/host, and `line` must be the START of the range as an int.
    """
    by_id = {f["template_id"]: f for f in _parse(fixture)}

    f = by_id["checkov:CKV_AWS_20"]
    assert f["path"] == "/main.tf"
    assert f["line"] == 10
    assert f["resource"] == "aws_s3_bucket.data"
    # additive, not instead of:
    assert f["matched_at"] == "/main.tf:10-25"
    assert f["host"] == "aws_s3_bucket.data"

    f2 = by_id["checkov:CKV_AWS_21"]
    assert f2["path"] == "/main.tf"
    assert f2["line"] == 30
    assert f2["resource"] == "aws_s3_bucket.data2"

    f3 = by_id["checkov:CKV_SECRET_6"]
    assert f3["path"] == "/vars.tf"
    assert f3["line"] == 5
    assert f3["resource"] == "vars.tf.5"


def test_passed_checks_never_become_findings(fixture):
    ids = {f["template_id"] for f in _parse(fixture)}
    assert "checkov:CKV_AWS_18" not in ids  # a passed_checks entry


# --- parse(): single-object shape, populated severities ----------------

def test_single_object_shape_is_accepted(fixture):
    findings = checkov.parse(str(fixture("checkov-single.json")), "thd-iam")
    assert len(findings) == 2


def test_populated_severity_and_legacy_alias_are_recognized(fixture):
    findings = checkov.parse(str(fixture("checkov-single.json")), "thd-iam")
    by_id = {f["template_id"]: f for f in findings}

    critical = by_id["checkov:CKV_AWS_100"]
    assert critical["severity"] == 4
    assert critical["severity_name"] == "critical"
    assert "severity-assigned" not in critical["tags"]

    moderate = by_id["checkov:CKV_AWS_101"]
    assert moderate["severity"] == 2
    assert moderate["severity_name"] == "medium"
    assert "severity-assigned" not in moderate["tags"]


def test_single_shape_passed_checks_are_ignored(fixture):
    findings = checkov.parse(str(fixture("checkov-single.json")), "thd-iam")
    ids = {f["template_id"] for f in findings}
    assert "checkov:CKV_AWS_1" not in ids


# --- parse(): resilience -------------------------------------------------
#
# CRITICAL false-clean defect: unreadable/malformed/wrong-shaped input used
# to come back as an empty finding list - byte-identical to "this target is
# clean". A file Checkov never actually scanned must never look the same as
# a clean scan, so every case below now raises base.ParseError instead. The
# three tests below previously asserted the buggy `== []` behaviour; they
# are rewritten here to assert the fix.

def test_missing_file_raises_parse_error(tmp_path):
    with pytest.raises(base.ParseError):
        checkov.parse(str(tmp_path / "nope.json"), "site-a")


def test_malformed_json_raises_parse_error(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(base.ParseError):
        checkov.parse(str(p), "site-a")


def test_empty_file_raises_parse_error(tmp_path):
    p = tmp_path / "empty.json"
    p.write_text("", encoding="utf-8")
    with pytest.raises(base.ParseError):
        checkov.parse(str(p), "site-a")


def test_json_null_raises_parse_error(tmp_path):
    """A file containing only `null` is valid JSON but not a report - this
    reproduces defect 1's third example ("`null` does too")."""
    p = tmp_path / "null.json"
    p.write_text("null", encoding="utf-8")
    with pytest.raises(base.ParseError):
        checkov.parse(str(p), "site-a")


def test_null_entry_in_failed_checks_raises_parse_error_not_attribute_error(fixture):
    """Shape failures count as parse failures too (plan: 'Shape validation
    counts as parse failure'). Before the fix this raised AttributeError
    from `check.get(...)` on a None entry, which fails the whole run
    instead of being caught as a per-cell parse error.
    """
    with pytest.raises(base.ParseError):
        checkov.parse(str(fixture("checkov-bad-shape.json")), "site-a")


def test_parsing_errors_are_not_silently_dropped(fixture):
    """A file Checkov could not read at all (results.parsing_errors) must
    not be presented as a clean scan. parse() still returns the [] its
    failed_checks legitimately contained (parsing_errors is reported
    through the separate parse_errors() channel, not by raising here) -
    but the caller (routine) must be able to see the parsing_errors via
    parse_errors() so the cell is never recorded as a clean `ran`.
    """
    findings = checkov.parse(str(fixture("checkov-parsing-errors.json")), "site-a")
    assert findings == []
    errors = checkov.parse_errors(str(fixture("checkov-parsing-errors.json")), "site-a")
    assert len(errors) == 1
    assert "broken.tf" in errors[0]["message"]
    # Shaped unlike a finding so nothing downstream mistakes one for the
    # other (same convention as testssl.parse_errors).
    assert "severity" not in errors[0]
    assert "template_id" not in errors[0]


def test_parse_errors_returns_empty_when_no_parsing_errors_present(fixture):
    assert checkov.parse_errors(str(fixture("checkov.json")), "site-a") == []


# --- is_available() -----------------------------------------------------

def test_is_available_true_when_binary_on_path(monkeypatch):
    monkeypatch.setattr(base, "which", lambda name: "/usr/bin/checkov" if name == "checkov" else None)
    assert checkov.is_available() is True


def test_is_available_false_when_binary_missing(monkeypatch):
    monkeypatch.setattr(base, "which", lambda name: None)
    assert checkov.is_available() is False


# --- run() ---------------------------------------------------------------

def test_run_returns_none_path_and_a_toolresult_when_binary_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(checkov.base, "which", lambda name: None)
    raw_path, result = checkov.run("/repo/terraform/thd-processors", str(tmp_path), {})
    assert raw_path is None
    assert isinstance(result, base.ToolResult)


def test_run_builds_argv_and_writes_stdout_verbatim(monkeypatch, tmp_path):
    monkeypatch.setattr(checkov.base, "which", lambda name: "/usr/bin/checkov" if name == "checkov" else None)

    captured = {}

    def fake_run_tool(argv, timeout, cwd=None):
        captured["argv"] = argv
        captured["timeout"] = timeout
        payload = {"check_type": "terraform",
                   "results": {"passed_checks": [], "failed_checks": []}}
        return base.ToolResult(returncode=1, stdout=json.dumps(payload), stderr="", timed_out=False)

    monkeypatch.setattr(checkov.base, "run_tool", fake_run_tool)

    outdir = tmp_path / "out"
    raw_path, result = checkov.run("/repo/terraform/thd-processors", str(outdir), {})

    assert raw_path == str(outdir / "checkov.json")
    assert result.returncode == 1
    with open(raw_path, encoding="utf-8") as fh:
        written = fh.read()
    assert json.loads(written)["check_type"] == "terraform"

    argv = captured["argv"]
    assert argv[0] == "/usr/bin/checkov"
    assert "-d" in argv and argv[argv.index("-d") + 1] == "/repo/terraform/thd-processors"
    assert "-o" in argv and argv[argv.index("-o") + 1] == "json"


def test_run_never_gates_on_checkovs_own_exit_code(monkeypatch, tmp_path):
    """Checkov exits 1 by default when any check fails - run() must still
    write the file and return its path rather than treating that as failure.
    """
    monkeypatch.setattr(checkov.base, "which", lambda name: "/usr/bin/checkov" if name == "checkov" else None)
    monkeypatch.setattr(checkov.base, "run_tool",
                        lambda argv, timeout, cwd=None: base.ToolResult(1, "[]", "", False))

    raw_path, result = checkov.run("/repo/terraform/thd-processors", str(tmp_path), {})
    assert raw_path is not None
    assert result.returncode == 1
    assert checkov.parse(raw_path, "site-a") == []


def test_run_returns_none_path_on_timeout(monkeypatch, tmp_path):
    """A timed-out invocation's stdout may be truncated mid-JSON - run() must
    not write it out or hand back a path parse() could be tempted to trust.
    """
    monkeypatch.setattr(checkov.base, "which", lambda name: "/usr/bin/checkov" if name == "checkov" else None)
    monkeypatch.setattr(checkov.base, "run_tool",
                        lambda argv, timeout, cwd=None: base.ToolResult(-1, '{"resu', "", True))

    raw_path, result = checkov.run("/repo/terraform/thd-processors", str(tmp_path), {})
    assert raw_path is None
    assert result.timed_out is True
    assert not (tmp_path / "checkov.json").exists()
