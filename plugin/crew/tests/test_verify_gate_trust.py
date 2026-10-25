"""`verify-gate.sh` and the trust store (L-0888): the gate runs a repo's verify
map, or its smoke script, only for a repo this machine trusts.

MUST-BLOCK (nothing runs, exit 0, no pass record, the line names the cause):
a repo with no store entry, for a Stop and for `--all`; one byte changed after
approval; a smoke script nobody approved; a corrupt store; a verify.json
rewritten between the first trust check and the second (the matcher reads it
in between); `--price` on an untrusted repo.

MUST-ALLOW: the same repo after `approve` (both the rules and the smoke script
run, exit codes unchanged); an allowlisted remote owner; `--ci` with no store
at all, which says its trust check is exempt.
"""
import json
import os
import shutil
import stat
import subprocess

import pytest

import crew_fixtures

import context  # noqa: F401  pylint: disable=unused-import
import verify_trust

_ROOT = context._ROOT  # pylint: disable=protected-access
_SH = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")
_BASH = crew_fixtures.resolve_bash()
pytestmark = pytest.mark.skipif(_BASH is None, reason="needs bash")

_MARKER = os.path.join(".crew", ".verify-verified-at")
_FINGERPRINT = os.path.join(".crew", ".verify-gate.fingerprint")


def _git(root, *args):
    subprocess.run(("git",) + args, cwd=root, check=True, capture_output=True,
                   timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


def _map(sentinel, run=None):
    return json.dumps({"version": 1, "always": [], "default": [], "unmapped": "ignore",
                       "rules": [{"paths": ["a.py"], "seconds": 1, "why": "fixture",
                                  "reach": "local", "run": [run or f"echo ran > '{sentinel}'"]}]})


def _repo(tmp_path, sentinel, verify=True, smoke=None, remote=None):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / "a.py").write_text("x = 1", encoding="utf-8")
    if verify:
        (root / ".crew" / "verify.json").write_text(_map(sentinel), encoding="utf-8")
    if smoke is not None:
        (root / "_verify").mkdir()
        (root / "_verify" / "smoke.sh").write_text(smoke, encoding="utf-8")
    if remote:
        _git(root, "remote", "add", "origin", remote)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    (root / "a.py").write_text("x = 2", encoding="utf-8")
    return root


@pytest.fixture(name="store")
def _store(tmp_path, monkeypatch):
    """A real decision: no `testTrustAll`, so the conftest seam is replaced."""
    path = tmp_path / "trust" / "verify-trust.json"
    monkeypatch.setenv(verify_trust.ENV_STORE, str(path))
    return path


def _run(root, *args, env=None):
    full = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    full.update(env or {})
    return crew_fixtures.run_gate([_BASH, _SH, *args], input="{}", cwd=str(root), env=full,
                                  capture_output=True, text=True, check=False,
                                  timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


def _approve(root):
    assert verify_trust.main(["approve", "--root", str(root), "--yes"]) == 0


def _nothing_ran(done, root, sentinel, word):
    assert done.returncode == 0, done.stderr
    assert not sentinel.exists(), "the repo-authored command RAN"
    assert word in done.stdout + done.stderr
    assert "nothing was verified" in done.stdout + done.stderr
    assert not (root / _MARKER).exists()
    assert not (root / _FINGERPRINT).exists()


@pytest.mark.parametrize("args", [(), ("--all",)])
def test_gate_an_untrusted_repo_runs_nothing_and_records_no_pass(tmp_path, store, args):
    sentinel = tmp_path / "ran.txt"
    root = _repo(tmp_path, sentinel)

    done = _run(root, *args)

    _nothing_ran(done, root, sentinel, "UNTRUSTED, not run")


def test_gate_an_untrusted_repo_with_a_failing_rule_exits_0_having_run_nothing(tmp_path, store):
    sentinel = tmp_path / "ran.txt"
    root = _repo(tmp_path, sentinel)
    (root / ".crew" / "verify.json").write_text(_map(sentinel, "exit 1"), encoding="utf-8")

    done = _run(root, "--all")

    _nothing_ran(done, root, sentinel, "UNTRUSTED, not run")


@pytest.mark.parametrize("args", [(), ("--all",)])
def test_gate_an_approved_repo_runs_its_rules(tmp_path, store, args):
    sentinel = tmp_path / "ran.txt"
    root = _repo(tmp_path, sentinel)
    _approve(root)

    done = _run(root, *args)

    assert done.returncode == 0, done.stderr
    assert sentinel.is_file(), done.stderr
    assert "UNTRUSTED" not in done.stdout + done.stderr


def test_gate_an_approved_repo_still_fails_a_failing_rule(tmp_path, store):
    sentinel = tmp_path / "ran.txt"
    root = _repo(tmp_path, sentinel)
    (root / ".crew" / "verify.json").write_text(_map(sentinel, "exit 1"), encoding="utf-8")
    _approve(root)

    done = _run(root, "--all")

    assert done.returncode == 2, done.stderr


def test_gate_one_byte_changed_after_approval_runs_nothing(tmp_path, store):
    sentinel = tmp_path / "ran.txt"
    root = _repo(tmp_path, sentinel)
    _approve(root)
    path = root / ".crew" / "verify.json"
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")

    done = _run(root, "--all")

    _nothing_ran(done, root, sentinel, "CHANGED, not run")


def test_gate_a_smoke_script_nobody_approved_runs_nothing(tmp_path, store):
    sentinel = tmp_path / "ran.txt"
    root = _repo(tmp_path, sentinel, verify=False, smoke=f"echo ran > '{sentinel}'\n")

    done = _run(root)

    _nothing_ran(done, root, sentinel, "UNTRUSTED, not run")


def test_gate_an_approved_smoke_script_runs(tmp_path, store):
    sentinel = tmp_path / "ran.txt"
    root = _repo(tmp_path, sentinel, verify=False, smoke=f"echo ran > '{sentinel}'\n")
    _approve(root)

    done = _run(root)

    assert done.returncode == 0, done.stderr
    assert sentinel.is_file(), done.stderr


def test_gate_a_smoke_script_changed_after_approval_runs_nothing(tmp_path, store):
    sentinel = tmp_path / "ran.txt"
    root = _repo(tmp_path, sentinel, verify=False, smoke="true\n")
    _approve(root)
    (root / "_verify" / "smoke.sh").write_text(f"echo ran > '{sentinel}'\n", encoding="utf-8")

    done = _run(root)

    _nothing_ran(done, root, sentinel, "CHANGED, not run")


def test_gate_a_corrupt_store_runs_nothing(tmp_path, store):
    sentinel = tmp_path / "ran.txt"
    root = _repo(tmp_path, sentinel)
    store.parent.mkdir(parents=True)
    store.write_text("{broken", encoding="utf-8")

    done = _run(root, "--all")

    _nothing_ran(done, root, sentinel, "UNKNOWN, not run")


def test_gate_an_allowlisted_remote_owner_runs_its_rules(tmp_path, store):
    sentinel = tmp_path / "ran.txt"
    root = _repo(tmp_path, sentinel, remote="https://github.com/mbadali25/useful.git")
    assert verify_trust.main(["allow-owner", "github.com/mbadali25", "--yes"]) == 0

    done = _run(root, "--all")

    assert done.returncode == 0, done.stderr
    assert sentinel.is_file(), done.stderr


def test_gate_a_foreign_remote_owner_runs_nothing(tmp_path, store):
    sentinel = tmp_path / "ran.txt"
    root = _repo(tmp_path, sentinel, remote="https://github.com/evil/useful.git")
    assert verify_trust.main(["allow-owner", "github.com/mbadali25", "--yes"]) == 0

    done = _run(root, "--all")

    _nothing_ran(done, root, sentinel, "UNTRUSTED, not run")


def test_gate_ci_mode_needs_no_store_and_says_its_trust_check_is_exempt(tmp_path, store):
    sentinel = tmp_path / "ran.txt"
    root = _repo(tmp_path, sentinel)

    done = _run(root, "--ci")

    assert done.returncode == 0, done.stderr
    assert sentinel.is_file(), done.stderr
    assert "trust check exempt" in done.stderr


def test_gate_price_on_an_untrusted_repo_runs_nothing(tmp_path, store):
    sentinel = tmp_path / "ran.txt"
    root = _repo(tmp_path, sentinel)
    before = (root / ".crew" / "verify.json").read_bytes()

    done = _run(root, "--price")

    assert done.returncode == 1, done.stderr
    assert not sentinel.exists(), "the repo-authored command RAN"
    assert "UNTRUSTED, not run" in done.stderr
    assert (root / ".crew" / "verify.json").read_bytes() == before


@pytest.mark.skipif(os.name != "posix", reason="the git shim is a POSIX script")
def test_gate_a_verify_json_rewritten_between_the_two_checks_runs_nothing(tmp_path, store):
    """The first check reads verify.json, THEN asks git for the repo identity
    (`rev-parse --git-common-dir`, the only call of that exact shape). The git
    shim swaps verify.json for one that runs the sentinel on that call, once:
    the first check has already passed on the approved bytes, the matcher then
    reads the swapped file, and only the second check can see it."""
    sentinel = tmp_path / "ran.txt"
    root = _repo(tmp_path, sentinel)
    swapped = tmp_path / "swapped.json"
    swapped.write_text(_map(sentinel), encoding="utf-8")
    original = root / ".crew" / "verify.json"
    original.write_text(_map(sentinel, "true"), encoding="utf-8")
    _approve(root)
    shim = tmp_path / "shim"
    shim.mkdir()
    script = shim / "git"
    script.write_text(
        '#!/usr/bin/env bash\n'
        'if [ "$1" = rev-parse ] && [ "$2" = --git-common-dir ] && [ -z "$3" ] '
        '&& [ ! -e "$SWAP_FLAG" ]; then : > "$SWAP_FLAG"; cp "$SWAP_FROM" "$SWAP_TO"; fi\n'
        f'exec "{shutil.which("git")}" "$@"\n', encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    flag = tmp_path / "swapped.flag"
    env = {"PATH": f"{shim}{os.pathsep}{os.environ['PATH']}", "SWAP_FROM": str(swapped),
           "SWAP_TO": str(original), "SWAP_FLAG": str(flag)}

    done = _run(root, "--all", env=env)

    assert flag.exists(), "fixture: the shim never saw the identity lookup"
    assert done.returncode == 0, done.stderr
    assert not sentinel.exists(), "the swapped verify.json ran"
    assert "CHANGED, not run" in done.stdout + done.stderr
    assert not (root / _MARKER).exists()
