"""`review_run.py`'s pre-review checks (L-0574): question 3 of BEFORE ANY
ROUND IS RESERVED, between the verify gate and the standards self-check.

Every must-block case snapshots the ledger under the throwaway repo's
git-common-dir and asserts it byte-identical afterwards, so "no round spent"
is measured, not inferred. The linter is `test_review_checks`'s fake, through
the real `command` slot. The verify gate is stood down (`"verifyGate": false`)
except where a case is about the gate, so the checks are what decides.
"""
import json
import os
import re
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_incident
import crew_standards as cs
import crew_ticket
import review_checks as rc
import review_ledger as rl
import scope_base
from review_fixtures import env_with_path, fake_reviewer_bin, git, init_repo
from test_review_checks import _FAKE

_SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access
_RUN = os.path.join(_SCRIPTS, "review_run.py")
_PATCH = os.path.join(_SCRIPTS, "review_patch.py")
TICKET = "T-1"
_PROVIDERS = {"codex": (), "claude": ("--reserve-only",)}


@pytest.fixture(name="fake")
def _fake(tmp_path):
    path = tmp_path / "fake_lint.py"
    path.write_text(_FAKE, encoding="utf-8")
    return str(path)


def _ruff(fake):
    return {"tool": "ruff", "command": [sys.executable, fake, "ruff"]}


def _missing():
    return {"tool": "ruff", "command": ["no-such-linter-l0574"]}


def _setup(tmp_path, linters, py_text="# LINT BLE001 new\n", gate=False, crew_cfg=None,
           extra=None):
    """A repo with an approval receipt, its crew config and verify map written
    BEFORE the self-check is stamped, a .py change, a stamped self-check and
    a bundle. `linters` None writes no `preReview` key."""
    repo = init_repo(tmp_path / "r")
    (repo / "m.py").write_text("x0\n", encoding="utf-8")
    for rel in extra or {}:
        (repo / rel).write_text("x\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "py")
    scope_base.record(str(repo), TICKET)
    path = crew_ticket.approval_path(str(repo), TICKET)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"ticket": TICKET, "approved_by": "fixture"}, fh)
    (repo / ".crew").mkdir(exist_ok=True)
    cfg = dict(crew_cfg or {})
    if not gate:
        cfg["verifyGate"] = False
    (repo / ".crew" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    verify = {"version": 1, "default": [], "unmapped": "ignore",
              "rules": [{"paths": ["**"], "seconds": 1, "run": ["echo ok"], "why": "fixture"}]}
    if linters is not None:
        verify[rc.CONFIG_KEY] = {"linters": linters}
    (repo / ".crew" / "verify.json").write_text(json.dumps(verify), encoding="utf-8")
    (repo / "m.py").write_text(py_text, encoding="utf-8")
    for rel, text in (extra or {}).items():
        (repo / rel).write_text(text, encoding="utf-8")
    _stamp(repo)
    scratch = tmp_path / "scratch"
    _bundle(repo, scratch)
    return repo, scratch


def _stamp(repo):
    assert cs.init(str(repo), TICKET)[0] == 0
    path = repo / ".work" / "tickets" / TICKET / "selfcheck.md"
    path.write_text(re.sub(r"^\| ([A-Z]+-\d\d) \|  \|  \|$",
                           r"| \1 | n/a | the fixture change is one file |",
                           path.read_text(encoding="utf-8"), flags=re.M), encoding="utf-8")
    code, lines = cs.stamp(str(repo), TICKET)
    assert code == 0, lines


def _bundle(repo, scratch):
    base = scope_base.resolve(str(repo), TICKET)[0]
    scratch.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, _PATCH, "--root", str(repo), "--base", base,
                    "--out", str(scratch / "diff.txt"), "--manifest", str(scratch / "manifest.json")],
                   check=True, capture_output=True, stdin=subprocess.DEVNULL)
    (scratch / "prompt.txt").write_text(
        "Review. " + " ".join(p["name"] for p in json.loads(
            (scratch / "manifest.json").read_text(encoding="utf-8"))["parts"]), encoding="utf-8")


def _ledger_snapshot(repo):
    common = git(repo, "rev-parse", "--git-common-dir")
    base = os.path.join(repo if not os.path.isabs(common) else "", common, "crew", "review")
    found = {}
    for dirpath, _, names in os.walk(base):
        for name in names:
            with open(os.path.join(dirpath, name), "rb") as fh:
                found[os.path.join(dirpath, name)] = fh.read()
    return found


def _run(repo, scratch, tmp_path, provider, *extra):
    argv = [sys.executable, _RUN, "--root", str(repo), "--ticket", TICKET,
            "--scratch", str(scratch), "--provider", provider,
            "--work-dir", str(tmp_path / "work")] + list(_PROVIDERS.get(provider, ())) + list(extra)
    return subprocess.run(argv, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                          check=False, timeout=180,
                          env=env_with_path(fake_reviewer_bin(tmp_path / "bin"),
                                            FAKE_REVIEWER_MODE="clean"))


def _record(scratch):
    return json.loads((scratch / rc.RESULT_FILE).read_text(encoding="utf-8"))


@pytest.mark.parametrize("provider", sorted(_PROVIDERS))
def test_new_finding_refuses_before_reserve(tmp_path, fake, provider):
    repo, scratch = _setup(tmp_path, [_ruff(fake)])
    before = _ledger_snapshot(repo)

    result = _run(repo, scratch, tmp_path, provider)

    assert (result.returncode, "NEW x1 m.py: BLE001 new" in result.stderr,
            _ledger_snapshot(repo) == before, _record(scratch)["result"]) == (
        5, True, True, rc.FAIL), result.stderr


@pytest.mark.parametrize("linters", ["new-alone", "new-and-could-not"])
def test_new_finding_is_not_overridable(tmp_path, fake, linters):
    chosen = [_ruff(fake)] + ([_missing()] if linters == "new-and-could-not" else [])
    repo, scratch = _setup(tmp_path, chosen)
    before = _ledger_snapshot(repo)

    result = _run(repo, scratch, tmp_path, "claude", "--allow-unverified")

    assert (result.returncode, _ledger_snapshot(repo) == before,
            "does not override a new finding" in result.stderr) == (5, True, True), result.stderr


def test_could_not_check_refuses_unless_allow_unverified(tmp_path):
    repo, scratch = _setup(tmp_path, [_missing()])
    before = _ledger_snapshot(repo)

    refused = _run(repo, scratch, tmp_path, "claude")
    refused_ledger_same = _ledger_snapshot(repo) == before
    allowed = _run(repo, scratch, tmp_path, "claude", "--allow-unverified")

    assert (refused.returncode, refused_ledger_same, "COULD NOT CHECK" in refused.stderr,
            allowed.returncode, "ROUND=1" in allowed.stdout, _record(scratch)["overridden"]) == (
        5, True, True, 0, True, True), refused.stderr + allowed.stderr


def test_incident_stands_checks_down(tmp_path, fake):
    repo, scratch = _setup(tmp_path, [_ruff(fake)])
    crew_incident.declare(str(repo), "fixture incident")

    result = _run(repo, scratch, tmp_path, "claude")

    skips = crew_incident.read_skips(str(repo))
    assert (result.returncode, "ROUND=1" in result.stdout, _record(scratch)["stood_down"],
            any("prereview-checks" in json.dumps(s) for s in skips)) == (
        0, True, True, True), result.stderr


@pytest.mark.parametrize("case", ["expired", "standdown-off"])
def test_only_an_active_incident_stands_down(tmp_path, fake, case):
    cfg = {"emergency": {"standDown": False}} if case == "standdown-off" else None
    repo, scratch = _setup(tmp_path, [_ruff(fake)], crew_cfg=cfg)
    now = None if case == "standdown-off" else 1_000_000
    crew_incident.declare(str(repo), "fixture incident", cfg=cfg, now=now)

    result = _run(repo, scratch, tmp_path, "claude")

    assert result.returncode == 5, result.stderr


def test_order_gate_before_checks(tmp_path, fake):
    repo, scratch = _setup(tmp_path, [_ruff(fake)], gate=True)

    result = _run(repo, scratch, tmp_path, "codex")

    assert (result.returncode, "gate UNVERIFIED" in result.stderr,
            "pre-review checks" in result.stderr) == (5, True, False), result.stderr


def test_order_checks_before_selfcheck(tmp_path, fake):
    repo, scratch = _setup(tmp_path, [_ruff(fake)])
    os.remove(repo / ".work" / "tickets" / TICKET / "selfcheck.md")

    result = _run(repo, scratch, tmp_path, "codex")

    assert (result.returncode, "pre-review checks: ruff FAIL" in result.stderr,
            "self-check" in result.stderr) == (5, True, False), result.stderr


def test_spent_budget_skips_checks(tmp_path, fake):
    repo, scratch = _setup(tmp_path, [_ruff(fake)])
    for _ in range(2):
        assert rl.reserve(str(repo), TICKET, "claude")[0]

    result = _run(repo, scratch, tmp_path, "codex")

    assert (result.returncode, "pre-review checks" in result.stderr) == (4, False), result.stderr


def test_unconfigured_proceeds_and_says_so(tmp_path):
    repo, scratch = _setup(tmp_path, None)

    result = _run(repo, scratch, tmp_path, "claude")

    assert (result.returncode, "ROUND=1" in result.stdout,
            "pre-review checks: none configured" in result.stderr,
            _record(scratch)["result"]) == (0, True, True, rc.NOT_CONFIGURED), result.stderr


def test_review_json_records_prereview(tmp_path, fake):
    repo, scratch = _setup(tmp_path, [_ruff(fake)], py_text="clean\n")

    result = _run(repo, scratch, tmp_path, "codex")

    review = json.loads((tmp_path / "work" / "review.json").read_text(encoding="utf-8"))
    assert (result.returncode, review["prereview"]["result"],
            [c["status"] for c in review["prereview"]["checks"]]) == (
        0, rc.PASS, [rc.PASS]), result.stdout + result.stderr


@pytest.mark.parametrize("record", ["kept", "removed"])
def test_claude_completion_carries_prereview(tmp_path, fake, record):
    repo, scratch = _setup(tmp_path, [_ruff(fake)], py_text="clean\n")
    reserved = _run(repo, scratch, tmp_path, "claude")
    assert "ROUND=1" in reserved.stdout, reserved.stderr
    if record == "removed":
        os.remove(scratch / rc.RESULT_FILE)
    manifest = json.loads((scratch / "manifest.json").read_text(encoding="utf-8"))
    out = tmp_path / "out.txt"
    out.write_text("\n".join("READ|" + p["path"] for p in manifest["parts"]) + "\nCLEAN\n",
                   encoding="utf-8")

    done = subprocess.run([sys.executable, _RUN, "--root", str(repo), "--ticket", TICKET,
                           "--scratch", str(scratch), "--provider", "claude", "--round", "1",
                           "--output", str(out), "--exit-code", "0",
                           "--work-dir", str(tmp_path / "work")],
                          capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False,
                          timeout=120)

    review = json.loads((tmp_path / "work" / "review.json").read_text(encoding="utf-8"))
    expected = rc.PASS if record == "kept" else rc.NOT_RECORDED
    assert (done.returncode, review["prereview"]["result"]) == (0, expected), done.stderr


def test_a_record_that_cannot_be_written_is_said_not_fatal(tmp_path, fake):
    repo, scratch = _setup(tmp_path, [_ruff(fake)], py_text="clean\n")
    missing = tmp_path / "no-such-scratch"

    result = subprocess.run(
        [sys.executable, _RUN, "--root", str(repo), "--ticket", TICKET, "--scratch", str(missing),
         "--manifest", str(scratch / "manifest.json"), "--provider", "claude", "--reserve-only"],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False, timeout=120)

    assert (result.returncode, "ROUND=1" in result.stdout,
            "could not record the pre-review checks" in result.stderr) == (0, True, True), (
        result.stdout + result.stderr)


def test_allow_unverified_never_passes_a_new_finding_beside_a_parse_failure(tmp_path, fake):
    sh = {"tool": "shellcheck", "command": [sys.executable, fake, "shellcheck"]}
    repo, scratch = _setup(tmp_path, [sh], py_text="x\n", extra={
        "a.sh": "x\n# LINT 2086 a new problem\n", "b.sh": "# ABORT\n"})
    before = _ledger_snapshot(repo)

    result = _run(repo, scratch, tmp_path, "claude", "--allow-unverified")

    assert (result.returncode, _ledger_snapshot(repo) == before,
            _record(scratch)["result"]) == (5, True, rc.FAIL), result.stderr


def test_the_record_is_bound_to_the_manifest_the_checks_read(tmp_path, fake, monkeypatch):
    """Review round 4: the bundle hash comes from the same read of the
    manifest as the linted entries. A manifest replaced while the linters run
    cannot have the results recorded against it."""
    import argparse  # pylint: disable=import-outside-toplevel
    import review_run  # pylint: disable=import-outside-toplevel
    repo, scratch = _setup(tmp_path, [_ruff(fake)], py_text="x\n")
    manifest = scratch / "manifest.json"
    checked = json.loads(manifest.read_text(encoding="utf-8"))["bundle_sha256"]
    real = rc.check_one

    def swapping(*args, **kwargs):
        result = real(*args, **kwargs)
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["bundle_sha256"] = "b" * 64
        manifest.write_text(json.dumps(data), encoding="utf-8")
        return result

    monkeypatch.setattr(rc, "check_one", swapping)
    args = argparse.Namespace(root=str(repo), manifest=str(manifest), scratch=str(scratch),
                              allow_unverified=False, ticket=TICKET)

    assert (review_run.prereview_gate(args), _record(scratch)["bundle_sha256"]) == (
        None, checked)
