"""The pipeline-side halves of the trigger tiers and of endpoint detection:
what each tier's code stage runs, the gate's per-tier threshold, the guard's
handling of the endpoints step's output (UNVERIFIED, all-refused, a manual
run's URL), the auth header for protected endpoints, the Nuclei template
cache, and the gitleaks adapter. No scanner, no git binary, no network: the
routine runner, `git diff` and every fetch are fakes.
"""
import json
import os
from types import SimpleNamespace

import ci_detect
import ci_gate
import gizmoduck_ci as ci
import pytest
from scanners import base, gitleaks

ENV = {"GIZMODUCK_STAGING_URLS": "https://staging.example.com", "GIZMODUCK_AUTHORIZED_BY": "Jane Doe"}


def no_redirects(_url):
    return 200, None


class FakeRunner:
    """routine.run_routine's stand-in: records the call and writes the combined
    findings file the real one always writes (empty unless `records`)."""

    def __init__(self, records=()):
        self.calls = []
        self.records = list(records)

    def __call__(self, manifest, out, confirm=None):
        self.calls.append((manifest, out, confirm))
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "findings.jsonl"), "w", encoding="utf-8") as fh:
            fh.write("".join(json.dumps(r) + "\n" for r in self.records))


def fake_git(files, rc=0, stderr=""):
    calls = []

    def run(argv, **_kw):
        calls.append(argv)
        return SimpleNamespace(returncode=rc, stdout="\n".join(files) + "\n", stderr=stderr)
    run.calls = calls
    return run


def code_stage(tmp_path, tier, base_ref="abc123def456", files=(), rc=0, env=None, touch=True):
    for f in files:
        if touch:
            p = tmp_path / "repo" / f
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x\n", encoding="utf-8")
    (tmp_path / "repo").mkdir(exist_ok=True)
    runner, git = FakeRunner(), fake_git(files, rc=rc, stderr="fatal: bad revision")
    args = SimpleNamespace(path=str(tmp_path / "repo"), out=str(tmp_path / "out"), tier=tier, base_ref=base_ref)
    status = ci.cmd_code_stage(args, env=dict(ENV, **(env or {})), runner=runner, run=git)
    manifest = runner.calls[0][0] if runner.calls else None
    return status, manifest, git


def by_name(manifest):
    return {t.name: t for t in manifest.targets}


# --- code stage per tier --------------------------------------------------------

def test_light_scans_only_changed_files_and_always_secrets(tmp_path):
    rc, manifest, git = code_stage(tmp_path, "light", files=["src/app.py", "src/util.py"])
    assert rc == 0
    t = by_name(manifest)
    assert set(t) == {"code", "secrets"}
    assert t["code"].options["semgrep_paths"] == ["src/app.py", "src/util.py"]
    assert t["code"].options["semgrep_baseline_commit"] == "abc123def456"
    assert t["secrets"].options == {"gitleaks_mode": "git", "gitleaks_log_opts": "abc123def456..HEAD",
                                    "cwd": t["secrets"].path}
    assert git.calls[0][-1] == "abc123def456...HEAD"
    plan = json.loads((tmp_path / "out" / "tier-plan.json").read_text())
    assert "trivy: no lockfile/manifest changed" in plan["skipped"]


@pytest.mark.parametrize("changed,expect", [
    (["package-lock.json"], {"deps"}),
    (["svc/requirements-dev.txt"], {"deps"}),
    (["src/Api/Api.csproj"], {"deps"}),
    (["infra/main.tf"], {"iac"}),
    (["infra/main.tf", "go.sum"], {"deps", "iac"}),
    (["README.md"], set()),
])
def test_light_runs_trivy_and_checkov_only_on_their_triggers(tmp_path, changed, expect):
    _, manifest, _ = code_stage(tmp_path, "light", files=changed)
    t = by_name(manifest)
    assert set(t) - {"code", "secrets"} == expect
    if "deps" in t:
        assert t["deps"].tools == ["trivy"]
    if "iac" in t:
        assert t["iac"].tools == ["checkov"]


def test_light_with_only_deleted_files_skips_semgrep_but_not_secrets(tmp_path):
    _, manifest, _ = code_stage(tmp_path, "light", files=["gone.py"], touch=False)
    assert set(by_name(manifest)) == {"secrets"}


@pytest.mark.parametrize("kwargs,needle", [
    ({"base_ref": None}, "needs --base-ref"),
    ({"rc": 128}, "git diff abc123def456...HEAD failed"),
])
def test_light_fails_closed_when_it_cannot_tell_what_changed(tmp_path, capsys, kwargs, needle):
    rc, manifest, _ = code_stage(tmp_path, "light", files=["a.py"], **kwargs)
    assert rc == 2 and manifest is None
    assert needle in capsys.readouterr().err


def test_full_skips_dependency_check_and_sweep_runs_it_with_cached_data(tmp_path):
    import routine
    _, full, _ = code_stage(tmp_path, "full")
    _, sweep, _ = code_stage(tmp_path, "sweep", env={"GIZMODUCK_DEPCHECK_DATA": "/tmp/nvd"})

    def tools(m):
        return {x for t in m.targets for x in routine.resolve_adapters(t)}
    assert tools(full) == {"semgrep", "trivy", "checkov", "gitleaks"}
    assert tools(sweep) == {"semgrep", "trivy", "checkov", "depcheck", "gitleaks"}
    assert by_name(sweep)["deps"].options == {"depcheck_data_dir": "/tmp/nvd"}
    secrets = by_name(full)["secrets"].options
    assert secrets["gitleaks_mode"] == "git" and "gitleaks_log_opts" not in secrets, \
        "tier 2 scans the whole git history, not just the tree"
    assert by_name(sweep)["secrets"].options["gitleaks_mode"] == "git"


# --- gate thresholds ---------------------------------------------------------------

def finding(tid, sev):
    names = {4: "critical", 3: "high", 2: "medium", 1: "low", 0: "info"}
    return ci_gate.parse_line(json.dumps({"template_id": tid, "name": tid, "severity": sev,
                                          "severity_name": names[sev], "matched_at": "x", "tags": []}))


@pytest.mark.parametrize("block_at,current,fails", [
    ("critical", [3], False),
    ("critical", [4], True),
    ("high", [3], True),
    ("high", [2], False),
    ("never", [4, 3], False),
])
def test_block_at(block_at, current, fails):
    cur = [finding(f"t{i}", s) for i, s in enumerate(current)]
    result = ci_gate.evaluate([], cur, COMPLETE, block_at=ci_gate.BLOCK_AT[block_at])
    assert result.fail is fails


COMPLETE = {"cells": [{"target": "code", "tool": "semgrep", "status": "ran"}]}


def test_never_still_lists_new_critical_high_for_tickets_and_reports_why():
    result = ci_gate.evaluate([], [finding("a", 4), finding("b", 3), finding("c", 2)], COMPLETE, block_at=None)
    assert not result.fail and len(result.new_blocking) == 2
    assert any("never blocks" in r for r in result.reasons)


def test_never_does_not_hide_incomplete_coverage_it_only_stops_blocking():
    manifest = {"cells": [{"target": "code", "tool": "semgrep", "status": "skipped-missing"}]}
    result = ci_gate.evaluate([], [], manifest, block_at=None)
    assert not result.fail and any("incomplete coverage" in r for r in result.reasons)


def test_gate_cli_block_at(tmp_path):
    cur = tmp_path / "cur.jsonl"
    cur.write_text(json.dumps({"template_id": "a", "name": "a", "severity": 3, "severity_name": "high",
                               "matched_at": "x", "tags": []}) + "\n", encoding="utf-8")
    base_file = tmp_path / "base.jsonl"
    base_file.write_text("", encoding="utf-8")
    manifest = tmp_path / "run-manifest.json"
    manifest.write_text(json.dumps(COMPLETE), encoding="utf-8")

    def args(block_at):
        return SimpleNamespace(current=str(cur), baseline=str(base_file), manifest=str(manifest), json_out=None,
                               new_out=None, summary=None, block_at=block_at)
    assert ci.cmd_gate(args("critical"), env={}) == 0
    assert ci.cmd_gate(args("high"), env={}) == 1
    assert ci.cmd_gate(args("never"), env={}) == 0


# --- guard with the endpoints step's output -------------------------------------------

def run_doc(*endpoints, status="OK", auth=None):
    return {"status": status, "reason": "" if status == "OK" else "no endpoints - run /gizmoduck:ci --detect",
            "auth": auth or {"mode": "none"},
            "endpoints": [{"path": e, "endpoint": e} for e in endpoints]}


def test_unverified_run_doc_refuses_the_whole_stage():
    report, rc = ci.build_targets(ENV, None, fetch=no_redirects, run_doc=run_doc(status="UNVERIFIED"))
    assert rc == 2 and report["refused"][0]["rule"] == "UNVERIFIED"
    assert "run /gizmoduck:ci --detect" in report["refused"][0]["reason"]


def test_unverified_status_wins_even_if_the_doc_lists_endpoints():
    """The status is the verdict: a doc that says UNVERIFIED is refused whatever
    else it carries, rather than trusting its list over its own conclusion."""
    report, rc = ci.build_targets(ENV, None, fetch=no_redirects, run_doc=run_doc("/api", status="UNVERIFIED"))
    assert rc == 2 and report["allowed"] == []
    assert report["refused"][0]["rule"] == "UNVERIFIED"


def test_ok_run_doc_scans_its_endpoints_and_carries_auth():
    report, rc = ci.build_targets(ENV, None, fetch=no_redirects,
                                  run_doc=run_doc("/api/users", "/", auth={"mode": "header"}))
    assert rc == 0
    assert [t["url"] for t in report["allowed"]] == ["https://staging.example.com",
                                                     "https://staging.example.com/api/users"]
    assert report["auth"] == {"mode": "header"}


def test_run_doc_whose_every_endpoint_is_refused_is_unverified_not_a_base_only_pass():
    report, rc = ci.build_targets(ENV, None, fetch=no_redirects, run_doc=run_doc("https://prod.example.com/x"))
    assert rc == 2
    assert [r["rule"] for r in report["refused"]] == ["R7", "UNVERIFIED"]
    assert [t["kind"] for t in report["allowed"]] == ["base"]


def test_manual_target_url_still_has_to_pass_the_guard():
    ok, rc_ok = ci.build_targets(dict(ENV, GIZMODUCK_TARGET_URL="https://staging.example.com/app"), None,
                                 fetch=no_redirects, run_doc=run_doc("/x"))
    bad, rc_bad = ci.build_targets(dict(ENV, GIZMODUCK_TARGET_URL="https://prod.example.com"), None,
                                   fetch=no_redirects, run_doc=run_doc("/x"))
    assert rc_ok == 0 and ok["allowed"][1]["url"] == "https://staging.example.com/app/x"
    assert rc_bad == 2 and bad["allowed"] == []


def test_targets_cli_missing_run_file_is_unverified(tmp_path, capsys):
    args = SimpleNamespace(run_endpoints=str(tmp_path / "nope.json"), endpoints=None, out=str(tmp_path / "t.json"),
                           no_redirect_check=True)
    assert ci.cmd_targets(args, env=ENV) == 2
    assert "UNVERIFIED" in capsys.readouterr().err


# --- auth header for protected endpoints ---------------------------------------------------

def stage(tmp_path, auth, env):
    path = tmp_path / "targets.json"
    path.write_text(json.dumps({"allowed": [{"name": "staging", "url": "https://staging.example.com",
                                             "kind": "base"}], "auth": auth}), encoding="utf-8")
    runner = FakeRunner()
    rc = ci.cmd_endpoint_stage(SimpleNamespace(targets=str(path), out=str(tmp_path / "o"), no_redirect_check=True),
                               env=dict(ENV, **env), runner=runner)
    return rc, runner


def test_header_auth_without_its_secret_refuses_rather_than_scanning_anonymously(tmp_path, capsys):
    rc, runner = stage(tmp_path, {"mode": "header", "header": "Authorization", "secret": ci_detect.AUTH_SECRET}, {})
    assert rc == 2 and runner.calls == []
    assert ci_detect.AUTH_SECRET in capsys.readouterr().err


def test_header_auth_reaches_nuclei_as_one_argument(tmp_path):
    rc, runner = stage(tmp_path, {"mode": "header", "header": "Authorization", "secret": ci_detect.AUTH_SECRET},
                       {ci_detect.AUTH_SECRET: "Bearer abc def"})
    assert rc == 0
    assert runner.calls[0][0].targets[0].options["headers"] == ["Authorization: Bearer abc def"]


def test_no_auth_sends_no_header(tmp_path):
    _, runner = stage(tmp_path, {"mode": "none"}, {ci_detect.AUTH_SECRET: "Bearer abc"})
    assert "headers" not in runner.calls[0][0].targets[0].options


def test_nuclei_adapter_passes_headers_as_separate_argv_items(monkeypatch, tmp_path):
    from scanners import nuclei
    seen = {}
    monkeypatch.setattr(nuclei, "_gizmoduck", lambda: SimpleNamespace(find_nuclei=lambda: "/bin/nuclei"))
    monkeypatch.setattr(base, "run_tool", lambda argv, timeout, cwd=None: seen.setdefault(
        "argv", argv) and base.ToolResult(0, "", "", False))
    nuclei.run("https://staging.example.com", str(tmp_path), {"headers": ["Authorization: Bearer a b"]})
    i = seen["argv"].index("-H")
    assert seen["argv"][i + 1] == "Authorization: Bearer a b"


# --- Nuclei template cache --------------------------------------------------------------

def test_templates_seeded_from_the_image_and_not_updated_outside_the_sweep(tmp_path):
    seed = tmp_path / "seed"
    (seed / "http").mkdir(parents=True)
    (seed / "http" / "t.yaml").write_text("id: t\n", encoding="utf-8")
    calls = []
    rc = ci.cmd_prepare_templates(SimpleNamespace(dir=str(tmp_path / "cache"), tier="full"),
                                  run=lambda *a, **k: calls.append(a), seeds=[str(seed)])
    assert rc == 0 and (tmp_path / "cache" / "http" / "t.yaml").is_file() and calls == []


def test_sweep_updates_templates_and_a_failed_update_keeps_the_cached_set(tmp_path, capsys):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "t.yaml").write_text("id: t\n", encoding="utf-8")
    calls = []

    def run(argv, **_kw):
        calls.append(argv)
        return SimpleNamespace(returncode=1, stdout="", stderr="network down")
    assert ci.cmd_prepare_templates(SimpleNamespace(dir=str(cache), tier="sweep"), run=run, seeds=[]) == 0
    assert calls[0][:4] == ["nuclei", "-update-templates", "-ud", str(cache)]
    assert "network down" in capsys.readouterr().err


def test_no_templates_anywhere_and_no_update_fails(tmp_path):
    def run(argv, **_kw):
        return SimpleNamespace(returncode=1, stdout="", stderr="down")
    assert ci.cmd_prepare_templates(SimpleNamespace(dir=str(tmp_path / "c"), tier="full"), run=run, seeds=[]) == 2


# --- gitleaks adapter ------------------------------------------------------------------------

LEAKS = [
    {"RuleID": "aws-access-token", "Description": "AWS Access Key", "File": "src/config.py", "StartLine": 12,
     "Commit": "0123456789abcdef", "Secret": "REDACTED", "Match": "REDACTED", "Fingerprint": "x"},
    {"RuleID": "generic-api-key", "Description": "Generic API Key", "File": "app.js", "StartLine": 3,
     "Secret": "sk_live_should_never_appear", "Match": "key = sk_live_should_never_appear"},
]


def test_gitleaks_parse_assigns_severity_and_never_copies_the_secret(tmp_path):
    raw = tmp_path / "gitleaks.json"
    raw.write_text(json.dumps(LEAKS), encoding="utf-8")
    out = gitleaks.parse(str(raw), "secrets")
    assert [(f["severity_name"], f["matched_at"]) for f in out] == [("critical", "src/config.py:12"),
                                                                     ("high", "app.js:3")]
    assert all("severity-assigned" not in f["tags"] for f in out), "an assigned default would fail the gate"
    assert "sk_live" not in json.dumps(out)
    assert ci_gate.parse_line(json.dumps(out[0])).severity == 4


def test_gitleaks_clean_report_is_an_empty_list(tmp_path):
    raw = tmp_path / "gitleaks.json"
    raw.write_text("[]", encoding="utf-8")
    assert gitleaks.parse(str(raw), "secrets") == []


@pytest.mark.parametrize("content", ["", "{", '{"findings": []}', "[1]"])
def test_gitleaks_unreadable_report_raises(tmp_path, content):
    raw = tmp_path / "gitleaks.json"
    raw.write_text(content, encoding="utf-8")
    with pytest.raises(base.ParseError):
        gitleaks.parse(str(raw), "secrets")


def test_gitleaks_run_modes_and_redaction(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(base, "which", lambda b: "/bin/gitleaks")

    def run_tool(argv, timeout, cwd=None):
        seen.append(argv)
        path = argv[argv.index("--report-path") + 1]
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("[]")
        return base.ToolResult(0, "", "", False)
    monkeypatch.setattr(base, "run_tool", run_tool)
    raw, _ = gitleaks.run("/repo", str(tmp_path), {"gitleaks_mode": "git", "gitleaks_log_opts": "a..HEAD"})
    assert raw and seen[0][1:5] == ["git", "/repo", "--log-opts", "a..HEAD"] and "--redact" in seen[0]
    gitleaks.run("/repo", str(tmp_path), {"gitleaks_mode": "dir"})
    assert seen[1][1:3] == ["dir", "/repo"] and "--redact" in seen[1]
