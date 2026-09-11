"""scanners.py - the adapter layer that lets four other tools land in Nuclei's
record shape so they merge into one report.

Unlike test_tickets_gate.py, which drives gizmoduck.py as a subprocess because
its contract is the CLI surface, these are in-process imports: scanners.py is a
module that gizmoduck.py imports, its functions are the contract, and the
expensive part (actually running trivy/semgrep/sslyze) is exactly what must NOT
happen in a test. Every case below feeds a recorded tool payload to the parsing
half of an adapter.

The first case is a REGRESSION with a real history. The ROBOT check was first
written as `if "VULNERABLE" in result.upper()`, which matches sslyze's SAFE
enum values too - they are spelled NOT_VULNERABLE_RSA_NOT_SUPPORTED and
friends. A correctly configured host was reported as "Vulnerable to ROBOT" at
High severity. That is the worst class of scanner bug: it does not miss a
finding, it manufactures one, and a reader who checks two of them by hand
learns to discount the whole report.

Run: pytest scripts/_test/test_scanners.py
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import scanners  # noqa: E402


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _sslyze_payload(tmp_path, scan_result):
    """A minimal sslyze --json_out document wrapping one scan_result block."""
    doc = {"server_scan_results": [
        {"scan_status": "COMPLETED", "scan_result": scan_result}]}
    p = tmp_path / "sslyze.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def _run_sslyze_against(monkeypatch, tmp_path, scan_result):
    """Drive run_sslyze's parsing without launching sslyze.

    The adapter shells out and then reads a JSON file it named itself, so the
    seam is subprocess.run plus the tempfile path. Both are stubbed.
    """
    payload = _sslyze_payload(tmp_path, scan_result)

    class _Proc:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(scanners, "_run", lambda cmd, timeout: _Proc())
    monkeypatch.setattr(scanners, "_which", lambda *names: "sslyze")
    # run_sslyze builds its temp path from gettempdir()+pid; point both at ours.
    monkeypatch.setattr(scanners.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(scanners.os, "getpid", lambda: 0)
    (tmp_path / "gizmo-sslyze-0.json").write_text(
        payload.read_text(encoding="utf-8"), encoding="utf-8")
    return scanners.run_sslyze("example.test")


def _names(run):
    return [f["info"]["name"] for f in run.findings]


def _sevs(run):
    return [f["info"]["severity"] for f in run.findings]


# --------------------------------------------------------------------------
# ROBOT: the false-positive regression
# --------------------------------------------------------------------------

@pytest.mark.parametrize("safe_value", [
    "NOT_VULNERABLE_RSA_NOT_SUPPORTED",
    "NOT_VULNERABLE_NO_ORACLE",
])
def test_robot_safe_values_raise_nothing(monkeypatch, tmp_path, safe_value):
    """sslyze spells its SAFE outcomes NOT_VULNERABLE_*. A substring test for
    "VULNERABLE" matches them, which is how a healthy host got reported High."""
    run = _run_sslyze_against(monkeypatch, tmp_path,
                              {"robot": {"result": {"robot_result": safe_value}}})
    assert run.status == "ok"
    assert not [n for n in _names(run) if "ROBOT" in n], (
        f"{safe_value} must not produce a ROBOT finding; got {_names(run)}")


@pytest.mark.parametrize("bad_value", [
    "VULNERABLE_WEAK_ORACLE",
    "VULNERABLE_STRONG_ORACLE",
])
def test_robot_real_vulnerability_is_still_reported(monkeypatch, tmp_path, bad_value):
    """The fix must not be "never report ROBOT"."""
    run = _run_sslyze_against(monkeypatch, tmp_path,
                              {"robot": {"result": {"robot_result": bad_value}}})
    robot = [f for f in run.findings if "ROBOT" in f["info"]["name"]]
    assert len(robot) == 1
    assert robot[0]["info"]["severity"] == "high"


# --------------------------------------------------------------------------
# sslyze: protocol and certificate rules
# --------------------------------------------------------------------------

def test_obsolete_protocols_are_graded_not_lumped(monkeypatch, tmp_path):
    """SSL 2/3 is critical; TLS 1.0/1.1 is medium. Flattening them to one
    severity is what makes a report unreadable."""
    accepted = {"result": {"accepted_cipher_suites": [{"x": 1}]}}
    run = _run_sslyze_against(monkeypatch, tmp_path, {
        "ssl_2_0_cipher_suites": accepted,
        "tls_1_0_cipher_suites": accepted,
        "tls_1_2_cipher_suites": {"result": {"accepted_cipher_suites": [{"x": 1}]}},
    })
    by_sev = dict(zip(_names(run), _sevs(run)))
    assert any(v == "critical" for k, v in by_sev.items() if "SSL 2.0" in k)
    assert any(v == "medium" for k, v in by_sev.items() if "TLS 1.0" in k)


def test_healthy_host_produces_no_findings(monkeypatch, tmp_path):
    """A modern host must yield an empty list, not info-severity inventory.
    Nuclei already emits the fingerprinting; duplicating it here would double
    the noise the Medium floor exists to suppress."""
    ok = {"result": {"accepted_cipher_suites": [{"x": 1}]}}
    run = _run_sslyze_against(monkeypatch, tmp_path, {
        "tls_1_2_cipher_suites": ok,
        "tls_1_3_cipher_suites": ok,
        "robot": {"result": {"robot_result": "NOT_VULNERABLE_NO_ORACLE"}},
    })
    assert run.findings == []


def test_untrusted_chain_is_high(monkeypatch, tmp_path):
    ok = {"result": {"accepted_cipher_suites": [{"x": 1}]}}
    run = _run_sslyze_against(monkeypatch, tmp_path, {
        "tls_1_2_cipher_suites": ok,
        "certificate_info": {"result": {"certificate_deployments": [
            {"path_validation_results": [
                {"was_validation_successful": False,
                 "trust_store": {"name": "Mozilla"},
                 "openssl_error_string": "unable to get local issuer certificate"}],
             "leaf_certificate_subject_matches_hostname": True}]}},
    })
    bad = [f for f in run.findings if "does not validate" in f["info"]["name"]]
    assert len(bad) == 1 and bad[0]["info"]["severity"] == "high"


# --------------------------------------------------------------------------
# a missing tool is not a clean result
# --------------------------------------------------------------------------

@pytest.mark.parametrize("fn,args", [
    (scanners.run_trivy_fs, ("src",)),
    (scanners.run_trivy_config, ("src",)),
    (scanners.run_semgrep, ("src",)),
    (scanners.run_checkov, ("src",)),
])
def test_missing_tool_reports_missing_not_empty(monkeypatch, fn, args):
    """Four silent zero-finding runs next to one clean Nuclei run would read as
    a clean bill of health. Status has to carry the difference."""
    monkeypatch.setattr(scanners, "_which", lambda *names: None)
    run = fn(*args)
    assert run.status == "missing"
    assert run.findings == []


# --------------------------------------------------------------------------
# checkov: severity is never invented
# --------------------------------------------------------------------------

def test_checkov_null_severity_is_floored_at_low(monkeypatch):
    """Checkov OSS returns severity: null on every finding - the field is
    populated by the commercial platform. Promoting those to Medium would put
    hundreds of unranked results above the report's detail floor and bury the
    findings that WERE ranked."""
    payload = {"results": {"failed_checks": [
        {"check_id": "CKV_AWS_158", "check_name": "Encrypt log group",
         "severity": None, "file_path": "/a.tf", "file_line_range": [5, 8]},
        {"check_id": "CKV_AWS_999", "check_name": "Ranked one",
         "severity": "high", "file_path": "/b.tf", "file_line_range": [1, 2]},
    ]}}

    class _Proc:
        returncode = 0
        stdout = json.dumps(payload)
        stderr = ""

    monkeypatch.setattr(scanners, "_which", lambda *names: "checkov")
    monkeypatch.setattr(scanners, "_run", lambda cmd, timeout: _Proc())
    run = scanners.run_checkov("src")
    sev = {f["info"]["name"]: f["info"]["severity"] for f in run.findings}
    assert sev["Encrypt log group"] == "low"
    assert sev["Ranked one"] == "high"
    assert "floored at Low" in run.detail


# --------------------------------------------------------------------------
# trivy / semgrep severity mapping
# --------------------------------------------------------------------------

def test_trivy_severity_maps_straight_across(monkeypatch):
    payload = {"Results": [{"Target": "package-lock.json", "Vulnerabilities": [
        {"VulnerabilityID": "CVE-1", "PkgName": "p", "InstalledVersion": "1",
         "FixedVersion": "2", "Severity": "CRITICAL", "Title": "t"},
        {"VulnerabilityID": "CVE-2", "PkgName": "q", "InstalledVersion": "1",
         "Severity": "UNKNOWN", "Title": "u"},
    ]}]}

    class _Proc:
        returncode = 0
        stdout = json.dumps(payload)
        stderr = ""

    monkeypatch.setattr(scanners, "_which", lambda *names: "trivy")
    monkeypatch.setattr(scanners, "_run", lambda cmd, timeout: _Proc())
    run = scanners.run_trivy_fs("src")
    sevs = sorted(_sevs(run))
    assert sevs == ["critical", "info"], sevs
    fixed = [f for f in run.findings if "CVE-1" in f["template-id"]][0]
    assert "Upgrade p to 2." in fixed["info"]["remediation"]
    unfixed = [f for f in run.findings if "CVE-2" in f["template-id"]][0]
    assert "No fixed version" in unfixed["info"]["remediation"]


def test_trivy_secret_finding_never_quotes_the_value(monkeypatch):
    """A report that prints the matched credential republishes it."""
    payload = {"Results": [{"Target": "app.py", "Secrets": [
        {"RuleID": "aws-access-key", "Title": "AWS key", "Severity": "HIGH",
         "StartLine": 4, "Match": "AKIAIOSFODNN7EXAMPLE",
         "Code": {"Lines": [{"Content": "key = AKIAIOSFODNN7EXAMPLE"}]}}]}]}

    class _Proc:
        returncode = 0
        stdout = json.dumps(payload)
        stderr = ""

    monkeypatch.setattr(scanners, "_which", lambda *names: "trivy")
    monkeypatch.setattr(scanners, "_run", lambda cmd, timeout: _Proc())
    run = scanners.run_trivy_fs("src")
    blob = json.dumps(run.findings)
    assert "AKIAIOSFODNN7EXAMPLE" not in blob
    assert run.findings[0]["info"]["severity"] == "high"


def test_semgrep_severity_mapping(monkeypatch):
    payload = {"results": [
        {"check_id": "r1", "path": "a.py", "start": {"line": 3},
         "extra": {"severity": "ERROR", "message": "bad", "metadata": {}}},
        {"check_id": "r2", "path": "b.py", "start": {"line": 9},
         "extra": {"severity": "WARNING", "message": "meh", "metadata": {}}},
        {"check_id": "r3", "path": "c.py", "start": {"line": 1},
         "extra": {"severity": "INFO", "message": "fyi", "metadata": {}}},
    ]}

    class _Proc:
        returncode = 0
        stdout = json.dumps(payload)
        stderr = ""

    monkeypatch.setattr(scanners, "_which", lambda *names: "semgrep")
    monkeypatch.setattr(scanners, "_run", lambda cmd, timeout: _Proc())
    run = scanners.run_semgrep("src")
    assert _sevs(run) == ["high", "medium", "info"]


# --------------------------------------------------------------------------
# suite wiring
# --------------------------------------------------------------------------

def test_source_tools_are_skipped_not_clean_without_a_source(monkeypatch):
    """Running without --source must not make trivy/semgrep look like they ran
    and found nothing."""
    monkeypatch.setattr(scanners, "run_sslyze",
                        lambda t, **kw: scanners.ToolRun("sslyze", "ok", []))
    findings, runs = scanners.run_suite("https://example.test", source=None)
    status = {r.tool: r.status for r in runs}
    assert status["trivy-fs"] == "skipped"
    assert status["semgrep"] == "skipped"
    assert findings == []


def test_optional_tools_are_off_by_default(monkeypatch):
    monkeypatch.setattr(scanners, "run_sslyze",
                        lambda t, **kw: scanners.ToolRun("sslyze", "ok", []))
    _, runs = scanners.run_suite("https://example.test", source=None)
    assert "zap" not in {r.tool for r in runs}
    assert "checkov" not in {r.tool for r in runs}


# --------------------------------------------------------------------------
# ZAP: launched from the wrong directory, and exiting 0 while failing
# --------------------------------------------------------------------------

def test_zap_runs_from_its_own_install_directory(monkeypatch, tmp_path):
    """REGRESSION. zap.bat and zap.sh invoke their jar by a RELATIVE path
    (`java -jar zap-2.17.0.jar`), so they only work when the process's working
    directory is the ZAP install directory. Launched from anywhere else they
    print "Error: Unable to access jarfile" and exit 0 - so the failure is
    invisible to a returncode check and the adapter silently contributed zero
    findings to every scan."""
    exe = tmp_path / "ZAP" / "zap.bat"
    exe.parent.mkdir(parents=True)
    exe.write_text("", encoding="utf-8")
    seen = {}

    class _Proc:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(cmd, timeout, cwd=None):
        seen["cwd"] = cwd
        # Write the report ZAP would have written, so the adapter proceeds.
        out = cmd[cmd.index("-quickout") + 1]
        with open(out, "w", encoding="utf-8") as fh:
            json.dump({"site": [{"alerts": []}]}, fh)
        return _Proc()

    monkeypatch.setattr(scanners, "_which", lambda *names: str(exe))
    monkeypatch.setattr(scanners, "_run", _fake_run)
    run = scanners.run_zap("https://example.test")
    assert run.status == "ok"
    assert seen["cwd"] == str(exe.parent), (
        "run_zap must set cwd to the ZAP install dir; got " + repr(seen["cwd"]))


def test_zap_missing_jar_is_failed_not_clean(monkeypatch, tmp_path):
    """ZAP exits 0 on this failure. Only the absent report file distinguishes
    it from a clean run, and the detail has to name the real cause."""
    exe = tmp_path / "ZAP" / "zap.bat"
    exe.parent.mkdir(parents=True)
    exe.write_text("", encoding="utf-8")

    class _Proc:
        returncode = 0                      # ZAP really does exit 0 here
        stdout = "Error: Unable to access jarfile zap-2.17.0.jar"
        stderr = ""

    monkeypatch.setattr(scanners, "_which", lambda *names: str(exe))
    monkeypatch.setattr(scanners, "_run", lambda cmd, timeout, cwd=None: _Proc())
    run = scanners.run_zap("https://example.test")
    assert run.status == "failed"
    assert "jar" in run.detail


def test_zap_severity_mapping(monkeypatch, tmp_path):
    exe = tmp_path / "ZAP" / "zap.bat"
    exe.parent.mkdir(parents=True)
    exe.write_text("", encoding="utf-8")
    report = {"site": [{"alerts": [
        {"pluginid": "10038", "alert": "CSP Header Not Set",
         "riskdesc": "Medium (High)", "desc": "d", "solution": "s",
         "instances": [{"uri": "https://example.test/"}]},
        {"pluginid": "10035", "alert": "HSTS Not Set",
         "riskdesc": "Low (High)", "desc": "d", "solution": "s",
         "instances": [{"uri": "https://example.test/"}]},
    ]}]}

    class _Proc:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(cmd, timeout, cwd=None):
        with open(cmd[cmd.index("-quickout") + 1], "w", encoding="utf-8") as fh:
            json.dump(report, fh)
        return _Proc()

    monkeypatch.setattr(scanners, "_which", lambda *names: str(exe))
    monkeypatch.setattr(scanners, "_run", _fake_run)
    run = scanners.run_zap("https://example.test")
    assert _sevs(run) == ["medium", "low"]


def test_every_record_matches_the_nuclei_shape_load_expects():
    """gizmoduck.load() reads template-id / type / host / matched-at / info.*.
    An adapter that drifts from this shape produces findings that silently
    vanish from the report."""
    rec = scanners._rec("trivy-fs", "CVE-1", "name", "high", "where",
                        host="h", description="d", remediation="r",
                        reference=["u"], tags=["t"], cve=["CVE-1"], cvss="9.8")
    assert rec["template-id"] == "trivy-fs:CVE-1"
    assert rec["type"] == "trivy-fs"
    info = rec["info"]
    for key in ("name", "severity", "description", "remediation", "reference",
                "tags", "classification"):
        assert key in info, key
    assert info["classification"]["cve-id"] == ["CVE-1"]
    assert info["severity"] in scanners.TRIVY_SEV.values()
