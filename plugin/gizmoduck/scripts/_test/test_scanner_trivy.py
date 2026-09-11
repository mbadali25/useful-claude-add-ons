import json

import pytest

from scanners import base, trivy


# ---------------------------------------------------------------------------
# parse() - deps kind
# ---------------------------------------------------------------------------

def test_deps_kind_parses_only_vulnerabilities(fixture):
    findings = trivy.parse(fixture("trivy.json"), "myrepo", kind="deps")
    assert len(findings) == 2
    assert all(f["type"] == "vulnerability" for f in findings)
    # The iac-only Misconfigurations entries must never leak into deps.
    assert all("Terraform" not in f["description"] for f in findings)


def test_deps_findings_have_expected_severities_and_ids(fixture):
    findings = trivy.parse(fixture("trivy.json"), "myrepo", kind="deps")
    by_id = {f["template_id"]: f for f in findings}
    assert by_id["trivy:CVE-2023-1234"]["severity"] == 3          # high
    assert by_id["trivy:CVE-2023-1234"]["severity_name"] == "high"
    assert "severity-assigned" not in by_id["trivy:CVE-2023-1234"]["tags"]


def test_unknown_severity_maps_to_info_and_is_flagged(fixture):
    findings = trivy.parse(fixture("trivy.json"), "myrepo", kind="deps")
    by_id = {f["template_id"]: f for f in findings}
    unknown = by_id["trivy:CVE-2024-9999"]
    assert unknown["severity"] == 0
    assert unknown["severity_name"] == "info"
    assert "severity-assigned" in unknown["tags"]


def test_deps_target_is_set_from_the_argument(fixture):
    findings = trivy.parse(fixture("trivy.json"), "myrepo", kind="deps")
    assert all(f["target"] == "myrepo" for f in findings)


# ---------------------------------------------------------------------------
# parse() - iac kind, same fixture file
# ---------------------------------------------------------------------------

def test_iac_kind_parses_only_misconfigurations(fixture):
    findings = trivy.parse(fixture("trivy.json"), "myrepo", kind="iac")
    assert len(findings) == 2
    assert all(f["type"] == "misconfiguration" for f in findings)
    # The deps-only Vulnerabilities entries must never leak into iac.
    assert all("requests" not in f["description"] for f in findings)
    assert all(not f["cve"] for f in findings)


def test_iac_findings_have_expected_severities_and_ids(fixture):
    findings = trivy.parse(fixture("trivy.json"), "myrepo", kind="iac")
    by_id = {f["template_id"]: f for f in findings}
    assert by_id["trivy:AVD-AWS-0001"]["severity"] == 4   # critical
    assert by_id["trivy:AVD-AWS-0002"]["severity"] == 2   # medium
    assert by_id["trivy:AVD-AWS-0001"]["matched_at"] == "main.tf:12"


def test_iac_target_is_set_from_the_argument(fixture):
    findings = trivy.parse(fixture("trivy.json"), "myrepo", kind="iac")
    assert all(f["target"] == "myrepo" for f in findings)


def test_kind_is_required_and_must_be_valid(fixture):
    with pytest.raises(ValueError):
        trivy.parse(fixture("trivy.json"), "myrepo", kind="web")
    with pytest.raises(ValueError):
        trivy.parse(fixture("trivy.json"), "myrepo")  # no kind, no target.kind


def test_kind_can_come_from_a_target_object_instead_of_the_kwarg(fixture):
    target = {"name": "myrepo", "kind": "deps"}
    findings = trivy.parse(fixture("trivy.json"), target)
    assert len(findings) == 2
    assert all(f["target"] == "myrepo" for f in findings)


# ---------------------------------------------------------------------------
# run() - never infer findings (or success) from the exit code
# ---------------------------------------------------------------------------

def test_run_builds_the_expected_argv_per_kind(tmp_path, monkeypatch, fixture):
    captured = {}

    def fake_run_tool(argv, timeout, cwd=None):
        captured["argv"] = argv
        captured["timeout"] = timeout
        # Simulate trivy: exit 0, findings written to --output regardless.
        out = argv[argv.index("--output") + 1]
        with open(fixture("trivy.json"), "r", encoding="utf-8") as fh:
            content = fh.read()
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(content)
        return base.ToolResult(returncode=0, stdout="", stderr="", timed_out=False)

    monkeypatch.setattr(trivy.base, "run_tool", fake_run_tool)

    raw_path = trivy.run("/repos/myrepo", str(tmp_path), {"kind": "deps"})

    assert "--scanners" in captured["argv"]
    assert captured["argv"][captured["argv"].index("--scanners") + 1] == "vuln"
    assert "--timeout" in captured["argv"]
    assert raw_path.endswith("trivy-deps.json")


def test_run_yields_findings_from_a_zero_exit_scan(tmp_path, monkeypatch, fixture):
    """Trivy exits 0 whether or not it found anything (spec 13.7) - this
    proves the adapter reads findings from the parsed output of a run whose
    process exit code was a plain, unremarkable 0, not from the code itself.
    """
    def fake_run_tool(argv, timeout, cwd=None):
        out = argv[argv.index("--output") + 1]
        with open(fixture("trivy.json"), "r", encoding="utf-8") as fh:
            content = fh.read()
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(content)
        return base.ToolResult(returncode=0, stdout="", stderr="", timed_out=False)

    monkeypatch.setattr(trivy.base, "run_tool", fake_run_tool)

    raw_path = trivy.run("/repos/myrepo", str(tmp_path), {"kind": "iac"})
    findings = trivy.parse(raw_path, "myrepo", kind="iac")

    assert len(findings) == 2
    assert all(f["severity"] > 0 for f in findings)


def test_run_raises_timeout_error_when_the_process_times_out(tmp_path, monkeypatch):
    def fake_run_tool(argv, timeout, cwd=None):
        return base.ToolResult(returncode=-1, stdout="", stderr="", timed_out=True)

    monkeypatch.setattr(trivy.base, "run_tool", fake_run_tool)

    with pytest.raises(TimeoutError):
        trivy.run("/repos/myrepo", str(tmp_path), {"kind": "deps"})


def test_run_requires_a_resolvable_kind(tmp_path):
    with pytest.raises(ValueError):
        trivy.run("/repos/myrepo", str(tmp_path), {})


# ---------------------------------------------------------------------------
# Protocol basics
# ---------------------------------------------------------------------------

def test_module_constants():
    assert trivy.NAME == "trivy"
    assert trivy.KINDS == ["deps", "iac"]
    assert trivy.ACTIVE is False
    assert trivy.ACTIVE_OPTS == []


def test_is_available_reflects_which(monkeypatch):
    monkeypatch.setattr(trivy.base, "which", lambda b: None)
    assert trivy.is_available() is False
    monkeypatch.setattr(trivy.base, "which", lambda b: "/usr/bin/trivy")
    assert trivy.is_available() is True
