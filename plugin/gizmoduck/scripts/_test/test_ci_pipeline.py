"""The pipeline-side commands of gizmoduck_ci.py: `.crew/endpoints.json`
ingestion, the runtime guard (`targets`), the two stages (with a fake routine
runner - no scanner ever runs here), SARIF and Bitbucket Code Insights output,
the GitHub baseline lookup (fake opener) and the opt-in SDP ticket flow (the
real gizmoduck.py confirm-then-open, a fake SDP client).

Nothing here contacts a network or a real scanner.
"""
import io
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import ci_gate
import gizmoduck_ci as ci
import pytest

_CLI = Path(__file__).resolve().parent.parent / "gizmoduck_ci.py"
ENV = {"GIZMODUCK_STAGING_URLS": "https://staging.example.com",
       "GIZMODUCK_AUTHORIZED_BY": "Jane Doe"}


def ledger(*records):
    return {"records": list(records), "nextSeq": len(records)}


def rec(rid, endpoint, status="open"):
    return {"id": rid, "endpoint": endpoint, "source": "declared", "status": status,
            "location": "app.py:1", "ticket": None, "createdAt": "2026-09-01T00:00:00Z"}


# --- ingestion ----------------------------------------------------------------

def test_ingest_url_path_and_host_forms():
    cands, skipped = ci.ingest_endpoints(ledger(
        rec("ep-0001", "https://staging.example.com/api/users"),
        rec("ep-0002", "/api/orders"),
        rec("ep-0003", "staging.example.com/health"),
    ), ["https://staging.example.com"])
    assert cands == [("ep-0001", "https://staging.example.com/api/users"),
                     ("ep-0002", "https://staging.example.com/api/orders"),
                     ("ep-0003", "https://staging.example.com/health")]
    assert skipped == []


def test_ingest_joins_a_path_onto_every_base_with_its_prefix():
    cands, _ = ci.ingest_endpoints(ledger(rec("ep-0001", "/v1")),
                                   ["https://staging.example.com/app", "https://s2.example.com"])
    assert [u for _, u in cands] == ["https://staging.example.com/app/v1", "https://s2.example.com/v1"]


@pytest.mark.parametrize("value,reason", [
    ("the new orders API", "free text"),
    ("", "free text"),
    (None, "free text"),
    ("grpc://staging.example.com:50051", "scheme"),
])
def test_ingest_skips_what_is_not_a_target(value, reason):
    cands, skipped = ci.ingest_endpoints(ledger(rec("ep-0001", value)), ["https://staging.example.com"])
    assert cands == [] and reason in skipped[0]["reason"]


def test_ingest_skips_closed_records():
    cands, skipped = ci.ingest_endpoints(ledger(rec("ep-0001", "/x", status="closed")),
                                         ["https://staging.example.com"])
    assert cands == [] and skipped[0]["reason"] == "status is closed"


@pytest.mark.parametrize("doc", [[], {"records": "nope"}, {"nextSeq": 1}])
def test_malformed_ledger_is_an_error(doc):
    with pytest.raises(ci.LedgerError):
        ci.ingest_endpoints(doc, ["https://staging.example.com"])


# --- runtime guard: targets ---------------------------------------------------

def no_redirects(url):
    return 200, None


def test_targets_keeps_staging_and_drops_refused_ledger_endpoints():
    report, rc = ci.build_targets(ENV, ledger(
        rec("ep-0001", "/api"),
        rec("ep-0002", "https://www.example.com/admin"),
        rec("ep-0003", "https://staging.example.com.evil.com/"),
        rec("ep-0004", "http://127.0.0.1:8080/"),
    ), fetch=no_redirects)
    assert rc == 0
    assert [t["url"] for t in report["allowed"]] == ["https://staging.example.com",
                                                     "https://staging.example.com/api"]
    assert [r["rule"] for r in report["refused"]] == ["R7", "R7", "R6"]


def test_targets_prod_endpoint_only_with_both_opt_ins():
    doc = ledger(rec("ep-0001", "https://www.example.com/"))
    env = dict(ENV, GIZMODUCK_ALLOWED_PROD_ORIGINS="https://www.example.com")
    r1, _ = ci.build_targets(env, doc, fetch=no_redirects)
    r2, _ = ci.build_targets(dict(env, GIZMODUCK_ALLOW_PROD_SCAN="true"), doc, fetch=no_redirects)
    assert len(r1["allowed"]) == 1 and r1["refused"][0]["rule"] == "R8"
    assert len(r2["allowed"]) == 2


def test_targets_refuses_everything_when_the_configured_base_is_refused():
    report, rc = ci.build_targets(dict(ENV, GIZMODUCK_STAGING_URLS="https://127.0.0.1"),
                                  None, fetch=no_redirects)
    assert rc == 2 and report["allowed"] == []


def test_targets_refuses_a_base_that_redirects_off_staging():
    def fetch(url):
        return (302, "https://www.example.com/") if url == "https://staging.example.com" else (200, None)
    report, rc = ci.build_targets(ENV, None, fetch=fetch)
    assert rc == 2 and report["refused"][0]["rule"] == "R9"


def test_targets_with_no_staging_configured_refuses():
    report, rc = ci.build_targets({}, None, fetch=no_redirects)
    assert rc == 2 and report["allowed"] == []


def run_cli(*argv, env=None):
    return subprocess.run([sys.executable, str(_CLI), *argv], capture_output=True, text=True,
                          env={"PATH": "", **(env or {})}, check=False)


def test_targets_cli_malformed_ledger_exits_2(tmp_path):
    bad = tmp_path / "endpoints.json"
    bad.write_text("{nope", encoding="utf-8")
    p = run_cli("targets", "--endpoints", str(bad), "--out", str(tmp_path / "t.json"),
                "--no-redirect-check", env=ENV)
    assert p.returncode == 2 and "GIZMODUCK_GUARD_REFUSED" in p.stderr


def test_targets_cli_absent_ledger_scans_base_only(tmp_path):
    p = run_cli("targets", "--endpoints", str(tmp_path / "absent.json"), "--out",
                str(tmp_path / "t.json"), "--no-redirect-check", env=ENV)
    assert p.returncode == 0, p.stderr
    report = json.loads((tmp_path / "t.json").read_text())
    assert [t["name"] for t in report["allowed"]] == ["staging"]


def test_targets_cli_refusal_writes_report_and_exits_2(tmp_path):
    p = run_cli("targets", "--endpoints", str(tmp_path / "absent.json"), "--out",
                str(tmp_path / "t.json"), "--no-redirect-check",
                env=dict(ENV, GIZMODUCK_STAGING_URLS="https://localhost"))
    assert p.returncode == 2 and "REFUSED  https://localhost" in p.stdout


# --- stages (fake runner) -----------------------------------------------------

class FakeRunner:
    def __init__(self):
        self.calls = []

    def __call__(self, manifest, out, confirm=None):
        self.calls.append((manifest, out, confirm))


def write_targets(tmp_path, targets):
    path = tmp_path / "targets.json"
    path.write_text(json.dumps({"allowed": targets, "refused": [], "skipped": []}), encoding="utf-8")
    return path


def test_endpoint_stage_default_tools_and_no_sqlmap(tmp_path):
    t = write_targets(tmp_path, [
        {"name": "staging", "url": "https://staging.example.com", "kind": "base"},
        {"name": "endpoint-ep-0001-1", "url": "https://staging.example.com/api", "kind": "endpoint"}])
    runner = FakeRunner()
    args = SimpleNamespace(targets=str(t), out=str(tmp_path / "o"), no_redirect_check=True)
    assert ci.cmd_endpoint_stage(args, env=ENV, runner=runner) == 0
    manifest, _, confirm = runner.calls[0]
    assert [x.tools for x in manifest.targets] == [["nuclei", "zap", "testssl"], ["nuclei", "zap"]]
    assert confirm is False and manifest.authorized_by == "Jane Doe"
    assert all(x.kind == "web" and "sqlmap" not in x.options for x in manifest.targets)


def test_endpoint_stage_opt_ins(tmp_path):
    t = write_targets(tmp_path, [
        {"name": "staging", "url": "https://staging.example.com", "kind": "base"},
        {"name": "ep", "url": "https://staging.example.com/api?id=1", "kind": "endpoint"}])
    runner = FakeRunner()
    env = dict(ENV, GIZMODUCK_ENABLE="nikto,nmap,sqlmap")
    args = SimpleNamespace(targets=str(t), out=str(tmp_path / "o"), no_redirect_check=True)
    assert ci.cmd_endpoint_stage(args, env=env, runner=runner) == 0
    manifest, _, confirm = runner.calls[0]
    assert manifest.targets[0].tools == ["nuclei", "zap", "testssl", "nmap", "nikto"]
    assert manifest.targets[1].tools == ["nuclei", "zap", "nikto", "sqlmap"]
    assert manifest.targets[1].options["sqlmap"] is True and confirm is True


def test_endpoint_stage_re_guards_a_tampered_targets_file(tmp_path):
    t = write_targets(tmp_path, [{"name": "prod", "url": "https://www.example.com", "kind": "base"}])
    runner = FakeRunner()
    args = SimpleNamespace(targets=str(t), out=str(tmp_path / "o"), no_redirect_check=True)
    assert ci.cmd_endpoint_stage(args, env=ENV, runner=runner) == 2
    assert runner.calls == []


def test_endpoint_stage_re_checks_redirects(tmp_path):
    t = write_targets(tmp_path, [{"name": "staging", "url": "https://staging.example.com", "kind": "base"}])
    runner = FakeRunner()
    args = SimpleNamespace(targets=str(t), out=str(tmp_path / "o"), no_redirect_check=False)
    rc = ci.cmd_endpoint_stage(args, env=ENV, runner=runner,
                               fetch=lambda u: (301, "https://evil.test/"))
    assert rc == 2 and runner.calls == []


def test_endpoint_stage_passes_the_image_template_dir(tmp_path):
    t = write_targets(tmp_path, [{"name": "staging", "url": "https://staging.example.com", "kind": "base"}])
    runner = FakeRunner()
    args = SimpleNamespace(targets=str(t), out=str(tmp_path / "o"), no_redirect_check=True)
    ci.cmd_endpoint_stage(args, env=dict(ENV, GIZMODUCK_NUCLEI_TEMPLATES="/opt/nuclei-templates"),
                          runner=runner)
    assert runner.calls[0][0].targets[0].options["extra"] == "-t /opt/nuclei-templates -duc"


def test_code_stage_manifest(tmp_path):
    runner = FakeRunner()
    args = SimpleNamespace(path=str(tmp_path), out=str(tmp_path / "o"))
    assert ci.cmd_code_stage(args, env=ENV, runner=runner) == 0
    manifest = runner.calls[0][0]
    assert [(x.name, x.kind, x.path) for x in manifest.targets] == [
        ("code", "code", str(tmp_path)), ("deps", "deps", str(tmp_path)), ("iac", "iac", str(tmp_path))]


def test_code_stage_resolves_to_the_four_code_scanners(tmp_path):
    import routine
    runner = FakeRunner()
    ci.cmd_code_stage(SimpleNamespace(path=".", out=str(tmp_path)), env=ENV, runner=runner)
    tools = {t for x in runner.calls[0][0].targets for t in routine.resolve_adapters(x)}
    assert tools == {"semgrep", "trivy", "checkov", "depcheck"}


# --- publish / SARIF / Code Insights -----------------------------------------

def norm(tid, sev, where, tags=None):
    names = {4: "critical", 3: "high", 2: "medium", 1: "low", 0: "info"}
    return {"template_id": tid, "name": f"name of {tid}", "severity": sev,
            "severity_name": names[sev], "type": "", "timestamp": "", "host": "",
            "matched_at": where, "cve": [], "cvss": "", "description": "why it matters",
            "remediation": "", "reference": ["https://example.org/rule"], "tags": tags or [],
            "tool": "semgrep", "target": "code"}


def findings_file(tmp_path, records):
    path = tmp_path / "findings.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return path


def test_publish_writes_reports_and_diff(tmp_path, fixture):
    out = tmp_path / "out"
    out.mkdir()
    (out / "findings.jsonl").write_bytes(fixture("combined-findings.jsonl").read_bytes())
    base = findings_file(tmp_path, [])
    rc = ci.cmd_publish(SimpleNamespace(out=str(out), baseline=str(base), title="t"))
    assert rc == 0
    assert (out / "report.md").read_text().count("**Total finding instances:**") == 1
    assert (out / "report.html").is_file()
    assert "**New findings:**" in (out / "diff.md").read_text()


def test_publish_without_baseline_says_so(tmp_path, fixture):
    out = tmp_path / "out"
    out.mkdir()
    (out / "findings.jsonl").write_bytes(fixture("combined-findings.jsonl").read_bytes())
    ci.cmd_publish(SimpleNamespace(out=str(out), baseline=str(tmp_path / "none"), title="t"))
    assert "No baseline was available" in (out / "diff.md").read_text()


def test_sarif_shape(tmp_path):
    recs = [norm("semgrep:a", 3, "/w/src/app.py:12"), norm("trivy:b", 2, "package-lock.json"),
            norm("checkov:c", 2, "main.tf:4", tags=["severity-assigned"])]
    parsed = [ci_gate.parse_line(json.dumps(r)) for r in recs]
    sarif = ci.to_sarif(parsed, srcroot="/w", version="9.9.9")
    run = sarif["runs"][0]
    assert sarif["version"] == "2.1.0" and run["tool"]["driver"]["version"] == "9.9.9"
    locs = [r["locations"][0]["physicalLocation"] for r in run["results"]]
    assert locs[0] == {"artifactLocation": {"uri": "src/app.py"}, "region": {"startLine": 12}}
    assert locs[1] == {"artifactLocation": {"uri": "package-lock.json"}}
    assert [r["level"] for r in run["results"]] == ["error", "warning", "warning"]
    rules = {r["id"]: r for r in run["tool"]["driver"]["rules"]}
    assert rules["semgrep:a"]["properties"]["security-severity"] == "8.0"
    assert "security-severity" not in rules["checkov:c"]["properties"]


def test_bb_insights_report_and_chunked_annotations():
    recs = [norm(f"semgrep:r{i}", 3 if i == 0 else 1, f"src/f{i}.py:{i + 1}") for i in range(250)]
    parsed = [ci_gate.parse_line(json.dumps(r)) for r in recs]
    gate = {"fail": True, "reasons": ["1 new Critical/High finding(s)"],
            "new_blocking": [recs[0]], "new_total": 1}
    report, chunks = ci.bb_insights(parsed, gate)
    assert report["result"] == "FAILED" and report["report_type"] == "SECURITY"
    assert report["data"][0] == {"title": "New Critical/High", "type": "NUMBER", "value": 1}
    assert [len(c) for c in chunks] == [100, 100, 50]
    first = chunks[0][0]
    assert first["severity"] == "HIGH" and first["path"] == "src/f0.py" and first["line"] == 1
    assert len({a["external_id"] for c in chunks for a in c}) == 250


def test_bb_insights_unreadable_gate_reports_failed():
    report, _ = ci.bb_insights([], {})
    assert report["result"] == "FAILED"


# --- GitHub baseline lookup -----------------------------------------------------

class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_previous_run_skips_the_current_run_and_filters_success():
    seen = {}

    def opener(req, timeout):
        seen["url"] = req.full_url
        seen["auth"] = req.get_header("Authorization")
        return FakeResp(json.dumps({"workflow_runs": [{"id": 42}, {"id": 41}]}).encode())
    env = {"GITHUB_REPOSITORY": "o/r", "GITHUB_RUN_ID": "42", "GH_TOKEN": "t0k"}
    assert ci.previous_run_id("gizmoduck-code.yml", "main", env, opener) == "41"
    assert "status=success" in seen["url"] and "branch=main" in seen["url"]
    assert "/actions/workflows/gizmoduck-code.yml/runs" in seen["url"]
    assert seen["auth"] == "Bearer t0k"


def test_previous_run_lookup_failure_prints_empty(capsys):
    args = SimpleNamespace(workflow="w.yml", branch=None)
    assert ci.cmd_gh_previous_run(args, env={}) == 0
    assert capsys.readouterr().out.strip() == "run_id="


# --- SDP tickets: gizmoduck.py's confirm-then-open, CI-driven -------------------

class FakeSdp:
    def __init__(self):
        self.records = []

    def open_or_note(self, record):
        self.records.append(record)
        return "created", str(len(self.records))


SDP_ENV = {"GIZMODUCK_SDP_TICKETS": "true", "SDP_BASE_URL": "https://sdp.invalid", "SDP_API_KEY": "k"}


def new_blocking(tmp_path):
    return findings_file(tmp_path, [norm("semgrep:a", 3, "a.py:1"), norm("semgrep:b", 4, "b.py:2")])


@pytest.mark.parametrize("env", [{}, {"GIZMODUCK_SDP_TICKETS": "false", "SDP_BASE_URL": "x", "SDP_API_KEY": "k"},
                                 {"GIZMODUCK_SDP_TICKETS": "true"},
                                 {"GIZMODUCK_SDP_TICKETS": "true", "SDP_BASE_URL": "x"}])
def test_tickets_default_off_without_variable_and_secrets(tmp_path, env):
    sdp = FakeSdp()
    args = SimpleNamespace(findings=str(new_blocking(tmp_path)), out=str(tmp_path / "t.json"), yes=True)
    assert ci.cmd_tickets(args, env=env, client=sdp) == 0
    assert sdp.records == [] and not (tmp_path / "t.json").exists()


def test_tickets_without_yes_previews_and_opens_nothing(tmp_path):
    sdp = FakeSdp()
    args = SimpleNamespace(findings=str(new_blocking(tmp_path)), out=str(tmp_path / "t.json"), yes=False)
    assert ci.cmd_tickets(args, env=SDP_ENV, client=sdp) == 3
    assert sdp.records == []


def test_tickets_with_yes_uses_the_previewed_digest(tmp_path):
    sdp = FakeSdp()
    args = SimpleNamespace(findings=str(new_blocking(tmp_path)), out=str(tmp_path / "t.json"), yes=True)
    assert ci.cmd_tickets(args, env=SDP_ENV, client=sdp) == 0
    assert [r["template_id"] for r in sdp.records] == ["semgrep:b", "semgrep:a"]
    assert all(r["subject"].startswith("[Nuclei semgrep:") for r in sdp.records)


def test_tickets_empty_file_is_nothing_to_do(tmp_path):
    empty = findings_file(tmp_path, [])
    args = SimpleNamespace(findings=str(empty), out=str(tmp_path / "t.json"), yes=True)
    assert ci.cmd_tickets(args, env=SDP_ENV, client=FakeSdp()) == 0


def test_tickets_refuses_a_preview_without_a_digest(tmp_path):
    def fake_run(argv, **kw):
        return SimpleNamespace(returncode=3, stdout="GIZMODUCK_CONFIRMATION_REQUIRED\n", stderr="")
    with pytest.raises(RuntimeError):
        ci.ticket_records(str(new_blocking(tmp_path)), True, run=fake_run)


def test_sdp_client_notes_an_open_request_instead_of_duplicating():
    calls = []

    def opener(req, timeout):
        calls.append((req.get_method(), req.full_url))
        if req.get_method() == "GET":
            return FakeResp(json.dumps({"requests": [{"id": "77"}]}).encode())
        return FakeResp(b"{}")
    client = ci.SdpClient("https://sdp.invalid", "k", opener=opener)
    action, rid = client.open_or_note({"subject": "[Nuclei x:y] thing", "description": "d"})
    assert (action, rid) == ("noted", "77")
    assert calls[1] == ("POST", "https://sdp.invalid/api/v3/requests/77/notes")
