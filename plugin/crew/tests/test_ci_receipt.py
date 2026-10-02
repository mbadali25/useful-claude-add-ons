"""ci_receipt.py: the CI verify-gate receipt is accepted only when it provably
matches HEAD, and every other state -- missing, mismatched, failed, pending,
unreadable -- is refused. "Could not tell" (UNKNOWN) is its own state.

`build` runs the REAL verify-gate.sh --all on fixture repos. `check` gets a
fake `fetch` (API path -> bytes) so nothing here touches the network; the CLI
cases put a fake `gh` first on PATH for the same reason.
"""
import io
import json
import os
import subprocess
import sys
import time
import zipfile

import pytest
import yaml

import context  # noqa: F401  pylint: disable=unused-import
import ci_receipt as cr
import crew_fixtures
from review_fixtures import git, init_repo

_SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access
_SH = os.path.join(_SCRIPTS, "verify-gate.sh")
_CLI = os.path.join(_SCRIPTS, "ci_receipt.py")
_REPO_ROOT = os.path.dirname(os.path.dirname(context._ROOT))  # pylint: disable=protected-access
_WORKFLOW = os.path.join(_REPO_ROOT, ".github", "workflows", "verify-gate.yml")
_BASH = crew_fixtures.resolve_bash()
needs_bash = pytest.mark.skipif(_BASH is None, reason="runs the real verify-gate.sh")
SLUG = "owner/repo"
RUN_ID = 4242


def _map(run="echo RAN-ok"):
    return {"version": 1,
            "rules": [{"paths": ["**"], "seconds": 1, "run": [run], "why": "fixture"}],
            "default": [], "unmapped": "ignore"}


def _repo(tmp_path, run="echo RAN-ok", config=None):
    root = init_repo(tmp_path / "r")
    (root / ".crew").mkdir()
    (root / ".crew" / "verify.json").write_text(json.dumps(_map(run)), encoding="utf-8")
    (root / ".gitignore").write_text(".crew/.verify*\n.crew/config.json\n", encoding="utf-8")
    if config is not None:
        (root / ".crew" / "config.json").write_text(config, encoding="utf-8")
    for path in cr.GATE_IMPL:
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(f"fixture copy of {path}\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "map")
    git(root, "remote", "add", "origin", f"https://github.com/{SLUG}.git")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    return root


def _gate_all(root):
    return crew_fixtures.run_gate(
        [_BASH, _SH, "--all"], input="", cwd=str(root),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)),
        capture_output=True, text=True, check=False,
        timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


def _env(head):
    return {"GITHUB_RUN_ID": str(RUN_ID), "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_REPOSITORY": SLUG, "GITHUB_SHA": head, "GITHUB_EVENT_NAME": "push"}


# --- parse_log ----------------------------------------------------------------------

def test_parse_log_reads_pass_fail_and_skip_and_ignores_the_total_line():
    log = "\n".join([
        "verify-gate: 3s  echo a",
        "VERIFY FAILED: false",
        "some output",
        "verify-gate: 1s  false",
        "verify-gate: SKIP (rc 77, environment absent): sh -c 'exit 77'",
        "verify-gate: 0s  sh -c 'exit 77'",
        "verify-gate: 4s total across 3 command(s)",
    ])
    assert cr.parse_log(log) == [
        {"cmd": "echo a", "seconds": 3, "state": "PASS"},
        {"cmd": "false", "seconds": 1, "state": "FAIL"},
        {"cmd": "sh -c 'exit 77'", "seconds": 0, "state": "SKIP"},
    ]


# --- build, against the real gate ----------------------------------------------------

@needs_bash
def test_build_after_a_real_clean_gate_passes_and_binds_head_tree_and_map(tmp_path):
    root = _repo(tmp_path)
    since = int(time.time())
    result = _gate_all(root)
    assert result.returncode == 0, result.stderr
    head = git(root, "rev-parse", "HEAD")

    receipt = cr.build(str(root), str(result.returncode), result.stderr, env=_env(head),
                       since=since)

    assert receipt["pass"] is True, receipt["reasons"]
    assert (receipt["head"], receipt["tree"], receipt["verify_json"]) == (
        head, git(root, "rev-parse", "HEAD^{tree}"),
        git(root, "rev-parse", "HEAD:.crew/verify.json"))


@needs_bash
@pytest.mark.parametrize("run,needle", [
    ("false", "exited"),
    ("sh -c 'exit 77'", "gate state on the runner is UNVERIFIED"),
], ids=["failing-rule", "skipped-rule"])
def test_build_after_a_real_failing_or_skipping_gate_does_not_pass(tmp_path, run, needle):
    root = _repo(tmp_path, run=run)
    since = int(time.time())
    result = _gate_all(root)
    head = git(root, "rev-parse", "HEAD")

    receipt = cr.build(str(root), str(result.returncode), result.stderr, env=_env(head),
                       since=since)

    assert receipt["pass"] is False
    assert any(needle in r for r in receipt["reasons"]), receipt["reasons"]


@needs_bash
def test_build_with_a_material_change_after_the_gate_does_not_pass(tmp_path):
    root = _repo(tmp_path)
    result = _gate_all(root)
    (root / "late.txt").write_text("written after the gate\n", encoding="utf-8")

    receipt = cr.build(str(root), "0", result.stderr, env=_env(git(root, "rev-parse", "HEAD")),
                       since=0)

    assert receipt["clean"] is False
    assert receipt["pass"] is False


@needs_bash
@pytest.mark.parametrize("since", [None, "future"], ids=["no-start-time", "marker-older"])
def test_build_on_evidence_not_written_by_this_run_does_not_pass(tmp_path, since):
    root = _repo(tmp_path)
    result = _gate_all(root)
    assert result.returncode == 0, result.stderr
    start = int(time.time()) + 100 if since == "future" else None

    receipt = cr.build(str(root), "0", result.stderr, env=_env(git(root, "rev-parse", "HEAD")),
                       since=start)

    assert receipt["pass"] is False
    assert any("marker" in r for r in receipt["reasons"]), receipt["reasons"]


def test_build_with_rc_zero_but_no_marker_does_not_pass(tmp_path):
    root = _repo(tmp_path)

    receipt = cr.build(str(root), "0", "verify-gate: 0s  echo RAN-ok",
                       env=_env(git(root, "rev-parse", "HEAD")), since=0)

    assert receipt["pass"] is False
    assert receipt["gate"]["state"] == cr.UNVERIFIED


@pytest.mark.parametrize("rc", ["none", "", "1", "137"])
def test_build_with_a_non_zero_or_missing_rc_does_not_pass(tmp_path, rc):
    root = _repo(tmp_path)

    receipt = cr.build(str(root), rc, "", env=_env(git(root, "rev-parse", "HEAD")), since=0)

    assert receipt["pass"] is False


# --- check: the fake API -------------------------------------------------------------

def _receipt(root, **over):
    head = git(root, "rev-parse", "HEAD")
    receipt = {
        "schema": cr.SCHEMA, "pass": True, "reasons": [], "head": head,
        "tree": git(root, "rev-parse", "HEAD^{tree}"),
        "verify_json": git(root, "rev-parse", "HEAD:.crew/verify.json"),
        "gate_impl": cr.gate_impl(str(root)),
        "gate": {"rc": 0, "state": cr.VERIFIED, "reason": "clean"},
        "outstanding": [], "clean": True, "commands": [],
        "run": {"id": str(RUN_ID), "attempt": "1", "repository": SLUG},
    }
    for key, value in over.items():
        node = receipt
        parts = key.split("__")
        for part in parts[:-1]:
            node = node[part]
        node[parts[-1]] = value
    return receipt


def _zip(payload, name=cr.RECEIPT_NAME):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, payload)
    return buf.getvalue()


def _run(head, **over):
    run = {"id": RUN_ID, "run_attempt": 1, "head_sha": head, "path": cr.WORKFLOW,
           "event": "push", "status": "completed", "conclusion": "success",
           "created_at": "2026-10-01T10:00:00Z",
           "repository": {"full_name": SLUG}, "head_repository": {"full_name": SLUG}}
    run.update(over)
    return run


def _artifact(head, **over):
    art = {"id": 7, "name": cr.artifact_name(1), "expired": False,
           "workflow_run": {"id": RUN_ID, "head_sha": head}}
    art.update(over)
    return art


def _api(root, runs=None, artifacts=None, blob=None, receipt=None):
    head = git(root, "rev-parse", "HEAD")
    runs = [_run(head)] if runs is None else runs
    artifacts = [_artifact(head)] if artifacts is None else artifacts
    if blob is None:
        blob = _zip(json.dumps(receipt if receipt is not None else _receipt(root)))
    return {
        f"repos/{SLUG}/actions/workflows/{cr.WORKFLOW_FILE}/runs?head_sha={head}&per_page=100":
            json.dumps({"workflow_runs": runs}).encode(),
        f"repos/{SLUG}/actions/runs/{RUN_ID}/artifacts?per_page=100":
            json.dumps({"artifacts": artifacts}).encode(),
        f"repos/{SLUG}/actions/artifacts/7/zip": blob,
    }


def _fetcher(api):
    def fetch(path):
        if path not in api:
            raise cr.Unreadable(f"fake gh: no response for {path}")
        return api[path]
    return fetch


def _check(root, api=None):
    return cr.check(str(root), fetch=_fetcher(api if api is not None else _api(root)))


def test_check_accepts_a_matching_receipt_from_a_successful_run_at_head(tmp_path):
    root = _repo(tmp_path)

    state, reason, head = _check(root)

    assert (state, head) == (cr.VERIFIED, git(root, "rev-parse", "HEAD")), reason


def _older_pass_newer_fail(root):
    head = git(root, "rev-parse", "HEAD")
    return _api(root, runs=[_run(head), _run(head, id=RUN_ID + 1, conclusion="failure",
                                              created_at="2026-10-01T11:00:00Z")])


def _older_pass_newer_queued(root):
    head = git(root, "rev-parse", "HEAD")
    return _api(root, runs=[_run(head), _run(head, id=RUN_ID + 1, status="queued",
                                              conclusion=None,
                                              created_at="2026-10-01T11:00:00Z")])


def _foreign_head_repo(root):
    return _api(root, runs=[_run(git(root, "rev-parse", "HEAD"),
                                 head_repository={"full_name": "fork/repo"})])


def _other_workflow(root):
    return _api(root, runs=[_run(git(root, "rev-parse", "HEAD"),
                                 path=".github/workflows/other.yml")])


def _pull_request_event(root):
    return _api(root, runs=[_run(git(root, "rev-parse", "HEAD"), event="pull_request")])


BLOCKED = {
    "no-run": lambda root: _api(root, runs=[]),
    "in-progress": lambda root: _api(root, runs=[_run(git(root, "rev-parse", "HEAD"),
                                                     status="in_progress", conclusion=None)]),
    "failed": lambda root: _api(root, runs=[_run(git(root, "rev-parse", "HEAD"),
                                                conclusion="failure")]),
    "cancelled": lambda root: _api(root, runs=[_run(git(root, "rev-parse", "HEAD"),
                                                   conclusion="cancelled")]),
    "newest-failed-older-passed": _older_pass_newer_fail,
    "newest-queued-older-passed": _older_pass_newer_queued,
    "run-for-other-sha": lambda root: _api(root, runs=[_run("0" * 40)]),
    "fork-head-repository": _foreign_head_repo,
    "other-workflow-path": _other_workflow,
    "pull-request-event": _pull_request_event,
    "head-mismatch": lambda root: _api(root, receipt=_receipt(root, head="1" * 40)),
    "tree-mismatch": lambda root: _api(root, receipt=_receipt(root, tree="2" * 40)),
    "verify-json-mismatch": lambda root: _api(root, receipt=_receipt(root, verify_json="3" * 40)),
    "gate-impl-forged": lambda root: _api(root, receipt=_receipt(root, gate_impl="5" * 64)),
    "gate-impl-missing": lambda root: _api(root, receipt={
        k: v for k, v in _receipt(root).items() if k != "gate_impl"}),
    "run-id-mismatch": lambda root: _api(root, receipt=_receipt(root, run__id="999")),
    "attempt-mismatch": lambda root: _api(root, receipt=_receipt(root, run__attempt="2")),
    "repository-mismatch": lambda root: _api(root, receipt=_receipt(root, run__repository="x/y")),
    "gate-not-verified": lambda root: _api(root, receipt=_receipt(root, gate__state="UNVERIFIED")),
    "gate-rc-nonzero": lambda root: _api(root, receipt=_receipt(root, gate__rc=2)),
    "outstanding-rules": lambda root: _api(root, receipt=_receipt(
        root, outstanding=[{"label": "r", "status": "skipped", "reason": "rc 77"}])),
    "not-clean": lambda root: _api(root, receipt=_receipt(root, clean=False)),
    "pass-false": lambda root: _api(root, receipt=_receipt(root, **{"pass": False})),
    # `==` alone holds 1 == True and False == 0: each of these matched before.
    "pass-is-int-one": lambda root: _api(root, receipt=_receipt(root, **{"pass": 1})),
    "clean-is-int-one": lambda root: _api(root, receipt=_receipt(root, clean=1)),
    "gate-rc-is-false": lambda root: _api(root, receipt=_receipt(root, gate__rc=False)),
}


@pytest.mark.parametrize("case", sorted(BLOCKED))
def test_check_refuses_every_receipt_that_is_not_a_proven_match(tmp_path, case):
    root = _repo(tmp_path)

    state, reason, _ = _check(root, BLOCKED[case](root))

    assert state in (cr.UNVERIFIED, cr.UNKNOWN), reason
    assert state != cr.VERIFIED


UNREADABLE = {
    "artifact-missing": lambda root: _api(root, artifacts=[]),
    "artifact-expired": lambda root: _api(root, artifacts=[
        _artifact(git(root, "rev-parse", "HEAD"), expired=True)]),
    "artifact-expiry-unknown": lambda root: _api(root, artifacts=[
        _artifact(git(root, "rev-parse", "HEAD"), expired=None)]),
    "artifact-of-an-earlier-attempt": lambda root: _api(root, artifacts=[
        _artifact(git(root, "rev-parse", "HEAD"), name=cr.artifact_name(0))]),
    "artifact-duplicated": lambda root: _api(root, artifacts=[
        _artifact(git(root, "rev-parse", "HEAD")), _artifact(git(root, "rev-parse", "HEAD"))]),
    "artifact-from-another-run": lambda root: _api(root, artifacts=[
        _artifact(git(root, "rev-parse", "HEAD"), workflow_run={"id": 1, "head_sha": "x"})]),
    "artifact-for-another-sha": lambda root: _api(root, artifacts=[
        _artifact(git(root, "rev-parse", "HEAD"),
                  workflow_run={"id": RUN_ID, "head_sha": "4" * 40})]),
    "artifact-not-a-zip": lambda root: _api(root, blob=b"not a zip"),
    "receipt-not-in-zip": lambda root: _api(root, blob=_zip("{}", name="other.json")),
    "receipt-not-json": lambda root: _api(root, blob=_zip("{nope")),
    "receipt-a-list": lambda root: _api(root, blob=_zip("[]")),
    "receipt-unknown-schema": lambda root: _api(root, receipt=_receipt(root, schema="v0")),
    "runs-response-a-list": lambda root: {
        **_api(root),
        f"repos/{SLUG}/actions/workflows/{cr.WORKFLOW_FILE}/runs?head_sha="
        f"{git(root, 'rev-parse', 'HEAD')}&per_page=100": b"[]"},
    "runs-response-no-list": lambda root: {
        **_api(root),
        f"repos/{SLUG}/actions/workflows/{cr.WORKFLOW_FILE}/runs?head_sha="
        f"{git(root, 'rev-parse', 'HEAD')}&per_page=100": b'{"workflow_runs": 3}'},
    "gh-fails": lambda root: {},
}


@pytest.mark.parametrize("case", sorted(UNREADABLE))
def test_check_says_could_not_tell_when_the_evidence_cannot_be_read(tmp_path, case):
    root = _repo(tmp_path)

    state, reason, _ = _check(root, UNREADABLE[case](root))

    assert state == cr.UNKNOWN, reason


def test_check_refuses_local_edits_on_top_of_head(tmp_path):
    root = _repo(tmp_path)
    api = _api(root)
    (root / "seed.txt").write_text("edited locally\n", encoding="utf-8")

    state, reason, _ = _check(root, api)

    assert state == cr.UNVERIFIED
    assert "differ from HEAD locally" in reason


def test_check_refuses_a_working_verify_map_that_differs_from_heads(tmp_path):
    root = _repo(tmp_path)
    api = _api(root)
    (root / ".crew" / "verify.json").write_text(json.dumps(_map("echo other")), encoding="utf-8")

    state, _, _ = _check(root, api)

    assert state == cr.UNVERIFIED


@pytest.mark.parametrize("producer", cr.PRODUCER_PATHS)
def test_check_refuses_a_branch_that_changes_the_receipt_producer(tmp_path, producer):
    root = _repo(tmp_path)
    target = root / producer
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("changed on this branch\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "edit the producer")

    state, reason, _ = _check(root)

    assert state == cr.UNVERIFIED
    assert "receipt producer" in reason


def test_check_allows_a_producer_change_that_came_from_main(tmp_path):
    root = _repo(tmp_path)
    target = root / cr.WORKFLOW
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("landed on main\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "main moved the producer")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")

    state, reason, _ = _check(root)

    assert state == cr.VERIFIED, reason


def test_check_refuses_a_head_without_the_gate_implementation(tmp_path):
    root = _repo(tmp_path)
    git(root, "rm", "-q", cr.GATE_IMPL[-1])
    git(root, "commit", "-qm", "drop one gate file")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")

    state, reason, _ = _check(root)

    assert state == cr.UNVERIFIED
    assert "gate implementation" in reason


def test_check_without_origin_main_could_not_tell(tmp_path):
    root = _repo(tmp_path)
    api = _api(root)
    git(root, "update-ref", "-d", "refs/remotes/origin/main")

    state, _, _ = _check(root, api)

    assert state == cr.UNKNOWN


@pytest.mark.parametrize("url", [
    "https://gitlab.example/owner/repo.git",
    f"https://gitlab.example/github.com/{SLUG}.git",
    f"git@gitlab.example:github.com/{SLUG}.git",
    f"https://github.com.evil.example/{SLUG}.git",
    f"https://notgithub.com/{SLUG}.git",
    f"ssh://git@gitlab.example/github.com/{SLUG}.git",
], ids=["other-host", "github-in-path", "scp-github-in-path", "github-prefix-host",
        "github-suffix-host", "ssh-github-in-path"])
def test_check_with_a_non_github_remote_could_not_tell(tmp_path, url):
    root = _repo(tmp_path)
    api = _api(root)
    git(root, "remote", "set-url", "origin", url)

    state, _, _ = _check(root, api)

    assert state == cr.UNKNOWN


@pytest.mark.parametrize("url", [
    f"https://github.com/{SLUG}.git",
    f"https://github.com/{SLUG}",
    f"https://x-access-token@github.com/{SLUG}.git",
    f"git@github.com:{SLUG}.git",
    f"ssh://git@github.com/{SLUG}.git",
], ids=["https", "https-no-suffix", "https-userinfo", "scp", "ssh"])
def test_check_accepts_every_github_remote_form(tmp_path, url):
    root = _repo(tmp_path)
    api = _api(root)
    git(root, "remote", "set-url", "origin", url)

    state, reason, _ = _check(root, api)

    assert state == cr.VERIFIED, reason


def test_check_when_the_stand_down_cannot_be_read_could_not_tell(tmp_path):
    root = _repo(tmp_path)
    api = _api(root)
    (root / ".crew" / "config.json").mkdir()

    state, _, _ = _check(root, api)

    assert state == cr.UNKNOWN


@pytest.mark.parametrize("config", [None, '{"verifyGate": false}'], ids=["no-map", "stood-down"])
def test_check_without_a_live_gate_is_no_gate(tmp_path, config):
    root = _repo(tmp_path, config=config)
    if config is None:
        git(root, "rm", "-q", ".crew/verify.json")
        git(root, "commit", "-qm", "no map")

    state, _, _ = _check(root, {})

    assert state == cr.NO_GATE


def test_check_when_head_moves_mid_check_could_not_tell(tmp_path):
    root = _repo(tmp_path)
    api = _api(root)
    zip_path = f"repos/{SLUG}/actions/artifacts/7/zip"

    def fetch(path):
        if path == zip_path:
            git(root, "commit", "-q", "--allow-empty", "-m", "moved")
        return _fetcher(api)(path)

    state, _, _ = cr.check(str(root), fetch=fetch)

    assert state == cr.UNKNOWN


def _rerun_mid_check(root, api):
    head = git(root, "rev-parse", "HEAD")
    runs_path = (f"repos/{SLUG}/actions/workflows/{cr.WORKFLOW_FILE}/runs?head_sha={head}"
                 "&per_page=100")
    api[runs_path] = json.dumps({"workflow_runs": [_run(head, run_attempt=2,
                                                        status="in_progress",
                                                        conclusion=None)]}).encode()


def _edit_mid_check(root, _api_map):
    (root / "seed.txt").write_text("edited during the check\n", encoding="utf-8")


def _map_mid_check(root, _api_map):
    (root / ".crew" / "verify.json").write_text(json.dumps(_map("echo x")), encoding="utf-8")


def _stand_down_mid_check(root, _api_map):
    (root / ".crew" / "config.json").write_text('{"verifyGate": false}', encoding="utf-8")


@pytest.mark.parametrize("change", [_rerun_mid_check, _edit_mid_check, _map_mid_check,
                                    _stand_down_mid_check],
                         ids=["rerun-started", "local-edit", "map-edited", "stood-down"])
def test_check_when_anything_changes_mid_check_could_not_tell(tmp_path, change):
    root = _repo(tmp_path)
    api = _api(root)
    zip_path = f"repos/{SLUG}/actions/artifacts/7/zip"

    def fetch(path):
        body = _fetcher(api)(path)
        if path == zip_path:
            change(root, api)
        return body

    state, _, _ = cr.check(str(root), fetch=fetch)

    assert state == cr.UNKNOWN


def test_check_with_a_fake_fetcher_never_runs_gh(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    api = _api(root)
    real = subprocess.run

    def guarded(argv, *a, **kw):
        assert argv[0] != "gh", "check() reached for the network with a fake fetcher"
        return real(argv, *a, **kw)  # pylint: disable=subprocess-run-check

    monkeypatch.setattr(cr.subprocess, "run", guarded)

    assert _check(root, api)[0] == cr.VERIFIED


def test_gh_fetch_without_gh_on_path_is_unreadable(monkeypatch):
    monkeypatch.setattr(cr.shutil, "which", lambda _name: None)

    with pytest.raises(cr.Unreadable):
        cr.gh_fetch("repos/x/y")


def test_gh_fetch_that_cannot_start_is_unreadable(monkeypatch):
    def boom(*_a, **_kw):
        raise FileNotFoundError("gh")

    monkeypatch.setattr(cr.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(cr.subprocess, "run", boom)

    with pytest.raises(cr.Unreadable):
        cr.gh_fetch("repos/x/y")


# --- the CLI, with a fake gh on PATH --------------------------------------------------

_FAKE_GH = """#!{python}
import base64, json, os, sys
api = json.load(open(os.environ["FAKE_GH_MAP"]))
path = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "api" else None
if path not in api:
    sys.stderr.write("fake gh: HTTP 404 for %r\\n(second line of gh's stderr)\\n" % path)
    sys.exit(1)
sys.stdout.buffer.write(base64.b64decode(api[path]))
"""


def _cli(root, tmp_path, api):
    import base64  # pylint: disable=import-outside-toplevel
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text(_FAKE_GH.format(python=sys.executable), encoding="utf-8", newline="\n")
    gh.chmod(0o755)
    mapping = tmp_path / "gh-map.json"
    mapping.write_text(json.dumps({k: base64.b64encode(v).decode() for k, v in api.items()}),
                       encoding="utf-8")
    env = dict(os.environ, FAKE_GH_MAP=str(mapping),
               PATH=str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))
    return subprocess.run([sys.executable, _CLI, "check", "--root", str(root)], env=env,
                          capture_output=True, text=True, check=False,
                          stdin=subprocess.DEVNULL, timeout=120)


@pytest.mark.skipif(os.name == "nt", reason="the fake gh is a shebang script")
@pytest.mark.parametrize("case,code,state", [
    ("verified", 0, cr.VERIFIED),
    ("failed", 1, cr.UNVERIFIED),
    ("gh-404", 3, cr.UNKNOWN),
])
def test_cli_exit_codes_and_last_line(tmp_path, case, code, state):
    root = _repo(tmp_path)
    head = git(root, "rev-parse", "HEAD")
    api = {"verified": _api(root),
           "failed": _api(root, runs=[_run(head, conclusion="failure")]),
           "gh-404": {}}[case]

    result = _cli(root, tmp_path, api)

    assert result.returncode == code, result.stdout + result.stderr
    assert result.stdout.strip().splitlines()[-1].startswith(f"CI_RECEIPT {state} head={head} ")
    assert not [line for line in result.stdout.splitlines() if line.startswith("(second line")]


def test_cli_usage_error_exits_2():
    result = subprocess.run([sys.executable, _CLI, "nonsense"], capture_output=True, text=True,
                            check=False, stdin=subprocess.DEVNULL, timeout=60)

    assert result.returncode == cr.EXIT_USAGE


def test_cli_build_writes_the_receipt_and_exits_1_when_not_passed(tmp_path):
    root = _repo(tmp_path)
    log = tmp_path / "gate.log"
    log.write_text("verify-gate: 0s  echo RAN-ok\n", encoding="utf-8")
    out = tmp_path / "out" / "receipt.json"

    result = subprocess.run([sys.executable, _CLI, "build", "--root", str(root), "--gate-rc", "0",
                             "--gate-log", str(log), "--out", str(out)],
                            capture_output=True, text=True, check=False,
                            stdin=subprocess.DEVNULL, timeout=120)

    assert (result.returncode, json.loads(out.read_text(encoding="utf-8"))["pass"]) == (1, False)


# --- the workflow -------------------------------------------------------------------

@pytest.fixture(name="workflow")
def _workflow():
    with open(_WORKFLOW, encoding="utf-8") as fh:
        text = fh.read()
    data = yaml.safe_load(text)
    return text, data


def test_workflow_triggers_only_on_lane_pushes_and_dispatch(workflow):
    _, data = workflow
    on = data.get("on", data.get(True))

    assert set(on) == {"push", "workflow_dispatch"}
    assert on["push"] == {"branches": ["L-*", "T-*", "W-*"]}


def test_workflow_holds_a_read_only_token_and_no_secrets(workflow):
    text, data = workflow

    assert data["permissions"] == {"contents": "read"}
    code = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    assert not [line for line in code if "secrets" in line]


def test_workflow_job_runs_only_on_the_self_hosted_pool_when_opted_in(workflow):
    _, data = workflow
    job = data["jobs"]["verify-gate"]

    assert "vars.CREW_RUNNER == 'self-hosted'" in job["if"]
    assert "github.repository ==" in job["if"]
    assert job["runs-on"] == ["self-hosted", "linux", "x64", "crew"]


def test_workflow_checkout_keeps_no_credentials_and_fetches_main(workflow):
    _, data = workflow
    steps = data["jobs"]["verify-gate"]["steps"]
    checkout = next(s for s in steps if str(s.get("uses", "")).startswith("actions/checkout@"))

    assert checkout["with"] == {"fetch-depth": 0, "persist-credentials": False}


def test_workflow_runs_the_gate_with_all_then_always_builds_and_uploads(workflow):
    _, data = workflow
    steps = data["jobs"]["verify-gate"]["steps"]
    gate = next(s for s in steps if s.get("id") == "gate")
    build = next(s for s in steps if "ci_receipt.py build" in str(s.get("run", "")))
    upload = next(s for s in steps if str(s.get("uses", "")).startswith("actions/upload-artifact@"))

    assert "verify-gate.sh --all" in gate["run"]
    assert "--since" in build["run"]
    assert any("rm -rf .crew/.verify-verified-at" in str(s.get("run", ""))
               for s in steps[:steps.index(gate)])
    assert (build["if"], upload["if"]) == ("always()", "always()")
    assert upload["with"]["name"] == cr.ARTIFACT + "-${{ github.run_attempt }}"


def test_workflow_installs_a_pinned_mmdc_so_the_diagram_rule_does_not_skip(workflow):
    _, data = workflow
    runs = [str(s.get("run", "")) for s in data["jobs"]["verify-gate"]["steps"]]

    assert any("@mermaid-js/mermaid-cli@12.0.0" in r for r in runs)
