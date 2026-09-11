"""Tests for the OWASP Dependency-Check adapter (Task 11).

The edge case this file must cover (plan Task 11 / spec 13.8): a
vulnerability whose `severity` is the plain text "HIGH" but which carries
no `cvssv3` block at all must still resolve to severity 3 - the fallback
order is text `severity` -> `cvssv2.score` -> `cvssv3.baseScore`, not
CVSS-first as section 4 originally implied.
"""
import json
import os

import pytest

from scanners import depcheck, base


def _parse(fixture):
    return depcheck.parse(str(fixture("depcheck.json")), "repo-a")


def test_finding_count(fixture):
    findings = _parse(fixture)
    assert len(findings) == 4


def test_template_id_is_namespaced_by_tool(fixture):
    findings = _parse(fixture)
    ids = {f["template_id"] for f in findings}
    assert ids == {
        "depcheck:CVE-2020-8203",
        "depcheck:CVE-2021-23337",
        "depcheck:GHSA-xxxx-yyyy-zzzz",
        "depcheck:CVE-2019-99999",
    }


def test_target_is_set_from_the_argument(fixture):
    findings = _parse(fixture)
    assert all(f["target"] == "repo-a" for f in findings)


def _by_cve(findings, cve):
    return next(f for f in findings if cve in f["cve"])


def test_text_severity_with_full_cvssv3_block(fixture):
    f = _by_cve(_parse(fixture), "CVE-2020-8203")
    assert f["severity"] == 4
    assert f["severity_name"] == "critical"
    assert f["cvss"] == 9.8
    assert "severity-assigned" not in f["tags"]


def test_high_text_severity_with_no_cvssv3_block_still_resolves_to_3(fixture):
    """THE required edge case: severity text "HIGH", no cvssv3 block at all."""
    findings = _parse(fixture)
    f = _by_cve(findings, "CVE-2021-23337")
    assert f["severity"] == 3
    assert f["severity_name"] == "high"
    # The numeric score carried into `cvss` still comes from whatever score
    # block exists (cvssv2 here), independent of what drove the severity.
    assert f["cvss"] == 6.4
    assert "severity-assigned" not in f["tags"]


def test_cvssv2_only_fallback_when_text_severity_is_absent(fixture):
    f = _by_cve(_parse(fixture), "CVE-2019-99999")
    # sev_from_cvss(7.5) bands to "high" (>= 7.0)
    assert f["severity"] == 3
    assert f["cvss"] == 7.5
    assert "severity-assigned" not in f["tags"]


def test_fully_unscored_vulnerability_falls_back_to_info_and_is_flagged(fixture):
    f = _by_cve(_parse(fixture), "GHSA-xxxx-yyyy-zzzz")
    assert f["severity"] == 0
    assert f["severity_name"] == "info"
    assert f["cvss"] == ""
    assert "severity-assigned" in f["tags"]


def test_package_and_version_resolve_from_the_highest_confidence_purl(fixture):
    """Both vulnerabilities on the lodash dependency share its one
    `packages[]` entry, so both must carry the same (package, version)
    resolved from the PURL "pkg:npm/lodash@4.17.15".
    """
    findings = _parse(fixture)
    for cve in ("CVE-2020-8203", "CVE-2021-23337"):
        f = _by_cve(findings, cve)
        assert f["package"] == "lodash"
        assert f["version"] == "4.17.15"


def test_package_and_version_are_omitted_when_unresolvable(fixture):
    """The second fixture dependency carries no `packages[]` block at all -
    the merge key must treat that as "does not merge on it" rather than
    guessing, so the fields must be absent entirely, not empty strings.
    """
    findings = _parse(fixture)
    for cve in ("GHSA-xxxx-yyyy-zzzz", "CVE-2019-99999"):
        f = _by_cve(findings, cve)
        assert "package" not in f
        assert "version" not in f


def test_is_available_delegates_to_which(monkeypatch):
    monkeypatch.setattr(base, "which", lambda name: "/usr/bin/dependency-check")
    assert depcheck.is_available() is True
    monkeypatch.setattr(base, "which", lambda name: None)
    assert depcheck.is_available() is False


def test_run_builds_the_documented_argv_and_resolves_the_output_path(monkeypatch, tmp_path):
    captured = {}

    def fake_run_tool(argv, timeout, cwd=None):
        captured["argv"] = argv
        captured["timeout"] = timeout
        # Simulate dependency-check writing its fixed-name report into the
        # --out directory, the way the real tool does.
        report = os.path.join(argv[argv.index("--out") + 1], depcheck.REPORT_FILENAME)
        with open(report, "w", encoding="utf-8") as fh:
            fh.write("{}")
        return base.ToolResult(0, "", "", False)

    monkeypatch.setattr(depcheck.base, "run_tool", fake_run_tool)
    outdir = tmp_path / "out"
    raw_path, result = depcheck.run("/scan/repo", str(outdir), {})

    assert captured["argv"] == [
        "dependency-check", "--format", "JSON",
        "--out", str(outdir), "--scan", "/scan/repo",
    ]
    assert raw_path == str(outdir / "dependency-check-report.json")
    assert result.returncode == 0
    assert outdir.is_dir()


def test_run_returns_none_path_when_no_output_file_was_produced(monkeypatch, tmp_path):
    def fake_run_tool(argv, timeout, cwd=None):
        return base.ToolResult(1, "", "boom", False)

    monkeypatch.setattr(depcheck.base, "run_tool", fake_run_tool)
    outdir = tmp_path / "out"
    raw_path, result = depcheck.run("/scan/repo", str(outdir), {})

    assert raw_path is None
    assert result.returncode == 1


def test_active_flags_are_off():
    assert depcheck.ACTIVE is False
    assert depcheck.ACTIVE_OPTS == []
