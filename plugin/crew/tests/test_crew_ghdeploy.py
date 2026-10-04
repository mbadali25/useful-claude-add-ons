"""`crew_ghdeploy.py check`: the `github` entry of a `.crew/verify.json`
environment, validated, and the one literal `gh workflow run` for HEAD.

T-0045 slice 1. `check` writes nothing and runs no `gh`; the only subprocess
it starts is `git rev-parse HEAD`. A map it cannot read, an environment it
cannot find and a HEAD it cannot resolve are could-not-tell (exit 3), never
"no github entry". Every entry problem is refused by name (exit 2) and never
quoted or escaped into a command.

The cases are the spec's acceptance checks. The mutations that prove each
refusing branch is tested are in `ghdeploy_mutations.py` (unwired; L-0650
wires them into the sabotage harness).
"""
import json
import os
import re
import stat
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

import crew_ghdeploy  # noqa: E402  pylint: disable=wrong-import-position

_HOOKS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      os.pardir, "hooks", "scripts")
_SCRIPT = os.path.join(_HOOKS, "crew_ghdeploy.py")
_GATE_SH = os.path.join(_HOOKS, "promote-gate.sh").replace("\\", "/")
_BASH = crew_fixtures.resolve_bash()

_ENTRY = {"workflow": "deploy.yml", "ref": "main",
          "inputs": {"target": "staging", "mode": "full"},
          "shaInput": "sha", "correlationInput": "crew_id"}
_PREFIX = "gh workflow run deploy.yml --ref main -f target=staging -f mode=full"


def _git(root, *args):
    return subprocess.run(
        ["git"] + list(args), cwd=str(root), capture_output=True, text=True,
        check=False, stdin=subprocess.DEVNULL,
        env=dict(os.environ, **crew_fixtures.fixture_git_env(os.environ)))


def _repo(tmp_path, doc, commit=True, raw=None):
    """A repo whose `.crew/verify.json` holds `doc` (or the text `raw`).

    `.crew/` and `.work/` are ignored and the rest committed, so the tree is
    clean for the promote-gate case. `commit=False` leaves HEAD unborn."""
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "T")
    (root / ".gitignore").write_text(".crew/\n.work/\n", encoding="utf-8")
    (root / "README.md").write_text("x\n", encoding="utf-8")
    if raw is not None:
        (root / ".crew" / "verify.json").write_text(raw, encoding="utf-8")
    elif doc is not None:
        (root / ".crew" / "verify.json").write_text(json.dumps(doc),
                                                     encoding="utf-8")
    if commit:
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "fixture")
    return root


def _doc(github, deploy=None, env="staging"):
    entries = github if isinstance(github, list) else [github]
    if deploy is None:
        deploy = [crew_ghdeploy.prefix(e) for e in entries
                  if isinstance(e, dict)
                  and crew_ghdeploy.entry_problem(e, env) is None]
    return {"environments": {env: {
        "deploy": deploy, "github": github, "rollback": "none",
        "rollbackReason": "the fixture deploys nothing"}}}


def _check(root, env="staging", path_env=None):
    environ = dict(os.environ)
    if path_env is not None:
        environ["PATH"] = path_env
    return subprocess.run(
        [sys.executable, _SCRIPT, "check", "--root", str(root), "--env", env],
        capture_output=True, text=True, check=False, env=environ,
        stdin=subprocess.DEVNULL)


def _last(proc):
    lines = proc.stdout.strip().splitlines()
    return lines[-1] if lines else ""


def _head(root):
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def _tree(root):
    """Every path under `.crew/` and `.work/`, to prove `check` wrote nothing."""
    out = set()
    for sub in (".crew", ".work"):
        base = root / sub
        if base.exists():
            out.update(str(p.relative_to(root)) for p in base.rglob("*"))
        else:
            out.add(f"{sub} absent")
    return out


# --- must block: entry problems ----------------------------------------------

def _with(**changes):
    entry = dict(_ENTRY)
    for key, value in changes.items():
        if value is _DROP:
            entry.pop(key, None)
        else:
            entry[key] = value
    return entry


_DROP = object()

_PROBLEMS = {
    "workflow missing": (_with(workflow=_DROP), "workflow-missing"),
    "workflow display name": (_with(workflow="Deploy app"), "workflow-not-filename"),
    "workflow numeric id": (_with(workflow="123456"), "workflow-not-filename"),
    "workflow not yml": (_with(workflow="deploy.sh"), "workflow-not-filename"),
    "workflow bad char": (_with(workflow="de$ploy.yml"), "workflow-not-filename"),
    "workflow leading dash": (_with(workflow="-R.yml"), "workflow-not-filename"),
    "workflow not a string": (_with(workflow=7), "workflow-not-filename"),
    "ref missing": (_with(ref=_DROP), "ref-missing"),
    "ref leading dash": (_with(ref="-R"), "ref-dash"),
    "ref dotdot": (_with(ref="main..x"), "ref-dotdot"),
    "ref tag": (_with(ref="refs/tags/v1"), "ref-tag"),
    "ref space": (_with(ref="ma in"), "ref-chars"),
    "ref not a string": (_with(ref=["main"]), "ref-chars"),
    "inputs not object": (_with(inputs=["a=b"]), "inputs-not-object"),
    "input value not string": (_with(inputs={"n": 3}), "input-not-string"),
    "input value with space": (_with(inputs={"n": "a b"}), "value-chars"),
    "input value with $(": (_with(inputs={"n": "$(id)"}), "value-chars"),
    "input value with ;": (_with(inputs={"n": "a;b"}), "value-chars"),
    "input value empty": (_with(inputs={"n": ""}), "value-chars"),
    "input name bad": (_with(inputs={"a b": "x"}), "input-name-chars"),
    "shaInput name bad": (_with(shaInput="s ha"), "input-name-chars"),
    "shaInput also in inputs": (_with(shaInput="target"), "sha-input-in-inputs"),
    "correlationInput also in inputs": (_with(correlationInput="mode"),
                                        "correlation-in-inputs"),
    "shaInput equals correlationInput": (_with(correlationInput="sha"),
                                         "sha-equals-correlation"),
    "watchMinutes 0": (_with(watchMinutes=0), "watch-minutes-range"),
    "watchMinutes 361": (_with(watchMinutes=361), "watch-minutes-range"),
    "watchMinutes bool": (_with(watchMinutes=True), "watch-minutes-range"),
    "watchMinutes string": (_with(watchMinutes="60"), "watch-minutes-range"),
    "identifySeconds 5": (_with(identifySeconds=5), "identify-seconds-range"),
    "identifySeconds 901": (_with(identifySeconds=901), "identify-seconds-range"),
    "deployJob empty": (_with(deployJob=""), "deploy-job-bad"),
    "deployJob control char": (_with(deployJob="deploy\n"), "deploy-job-bad"),
    "unknown key": (_with(repo="other/repo"), "unknown-key"),
    "github a string": ("deploy.yml", "github-shape"),
    "github a number": (7, "github-shape"),
    "github list holding a string": ([_ENTRY, "x"], "github-shape"),
    "github empty list": ([], "github-shape"),
}


@pytest.mark.parametrize("label", sorted(_PROBLEMS))
def test_entry_problem(tmp_path, label):
    github, reason = _PROBLEMS[label]
    root = _repo(tmp_path, _doc(github, deploy=[_PREFIX]))

    proc = _check(root)

    assert proc.returncode == 2, f"{label}: exit {proc.returncode}\n{proc.stdout}{proc.stderr}"
    assert _last(proc) == f"result=refused reason={reason}", proc.stdout
    assert "gh workflow run" not in proc.stdout, "a refused entry prints no dispatch"


def test_correlation_needs_an_env_name_in_the_value_grammar(tmp_path):
    root = _repo(tmp_path, _doc(_ENTRY, env="st age"))

    proc = _check(root, env="st age")

    assert proc.returncode == 2, proc.stdout
    assert _last(proc) == "result=refused reason=env-name-chars"


def test_check_refuses_deploy_prefix_mismatch(tmp_path):
    second = _with(inputs={"target": "staging", "mode": "migrate"})
    both = [_ENTRY, second]
    p1, p2 = crew_ghdeploy.prefix(_ENTRY), crew_ghdeploy.prefix(second)
    for deploy in ([p1], [p1, p2, "./deploy.sh"], "./deploy.sh", [p2, 7]):
        sub = tmp_path / str(abs(hash(json.dumps(deploy))))
        sub.mkdir()
        root = _repo(sub, _doc(both, deploy=deploy))

        proc = _check(root)

        assert proc.returncode == 2, f"{deploy!r}: {proc.stdout}"
        assert _last(proc) == "result=refused reason=deploy-prefix-mismatch", deploy


def test_check_unreadable_map_is_could_not_tell(tmp_path):
    cases = {
        "absent": (None, None, "staging", True, "verify-json-absent"),
        "unparseable": (None, "{ not json", "staging", True, "verify-json-unreadable"),
        "top level list": (None, "[1]", "staging", True, "verify-json-unreadable"),
        "environments a list": ({"environments": []}, None, "staging", True,
                                "verify-json-unreadable"),
        "environment a string": ({"environments": {"staging": "x"}}, None,
                                 "staging", True, "verify-json-unreadable"),
        "no such environment": (_doc(_ENTRY), None, "prod", True,
                                "environment-absent"),
        "head unreadable": (_doc(_ENTRY), None, "staging", False, "head-unreadable"),
    }
    for label, (doc, raw, env, commit, reason) in cases.items():
        sub = tmp_path / label.replace(" ", "_")
        sub.mkdir()
        root = _repo(sub, doc, commit=commit, raw=raw)

        proc = _check(root, env=env)

        assert proc.returncode == 3, f"{label}: exit {proc.returncode}\n{proc.stdout}{proc.stderr}"
        assert _last(proc) == f"result=could-not-tell reason={reason}", label
        assert "github=none" not in proc.stdout, label


def test_a_map_that_is_a_directory_is_could_not_tell(tmp_path):
    root = _repo(tmp_path, None)
    (root / ".crew" / "verify.json").mkdir()

    proc = _check(root)

    assert proc.returncode == 3
    assert _last(proc) == "result=could-not-tell reason=verify-json-unreadable"


# --- must allow ---------------------------------------------------------------

def test_prefix_is_listed_order():
    entry = {"workflow": "d.yaml", "ref": "release/1.2",
             "inputs": {"z": "1", "a": "x@y:z+w", "m": "p/q"}}
    assert crew_ghdeploy.entry_problem(entry, "e") is None
    assert crew_ghdeploy.prefix(entry) == (
        "gh workflow run d.yaml --ref release/1.2 -f z=1 -f a=x@y:z+w -f m=p/q")
    assert crew_ghdeploy.prefix({"workflow": "d.yml", "ref": "main"}) == (
        "gh workflow run d.yml --ref main")


def test_dispatch_appends_sha_then_correlation():
    sha = "0123456789abcdef0123456789abcdef01234567"
    line = crew_ghdeploy.dispatch(_ENTRY, "staging", sha)

    assert line.startswith(_PREFIX + f" -f sha={sha} -f crew_id=crew-staging-0123456-")
    assert re.fullmatch(re.escape(_PREFIX) + f" -f sha={sha}"
                        r" -f crew_id=crew-staging-0123456-[0-9a-f]{8}", line), line
    bare = {"workflow": "deploy.yml", "ref": "main"}
    assert crew_ghdeploy.dispatch(bare, "staging", sha) == "gh workflow run deploy.yml --ref main"


def test_check_prints_dispatch_for_head(tmp_path):
    second = {"workflow": "migrate.yml", "ref": "main", "shaInput": "rev"}
    root = _repo(tmp_path, _doc([_ENTRY, second]))
    before = _tree(root)
    sha = _head(root)

    proc = _check(root)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    dispatches = [ln for ln in proc.stdout.splitlines() if ln.startswith("dispatch: ")]
    assert len(dispatches) == 2, proc.stdout
    assert dispatches[0].startswith(f"dispatch: {_PREFIX} -f sha={sha} -f crew_id=crew-staging-{sha[:7]}-")
    assert dispatches[1] == f"dispatch: gh workflow run migrate.yml --ref main -f rev={sha}"
    assert _last(proc) == f"result=ok entries=2 sha={sha}"
    assert _tree(root) == before, "check must create nothing under .crew/ or .work/"


def test_a_single_object_and_a_string_deploy_are_accepted(tmp_path):
    entry = {"workflow": "deploy.yml", "ref": "main"}
    root = _repo(tmp_path, _doc(entry, deploy="gh workflow run deploy.yml --ref main"))

    proc = _check(root)

    assert proc.returncode == 0, proc.stdout
    assert _last(proc).startswith("result=ok entries=1 ")


def test_environment_without_github_is_not_a_problem(tmp_path):
    root = _repo(tmp_path, {"environments": {"staging": {"deploy": ["./deploy.sh"]}}},
                 commit=False)

    proc = _check(root)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _last(proc) == "result=ok github=none"


def test_check_calls_no_gh(tmp_path):
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    ran = tmp_path / "gh-ran"
    stub = stub_dir / "gh"
    stub.write_text(f"#!/bin/sh\necho ran >> '{ran}'\nexit 1\n", encoding="utf-8",
                    newline="\n")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    (stub_dir / "gh.cmd").write_text(f"@echo ran >> \"{ran}\"\r\n@exit /b 1\r\n",
                                     encoding="utf-8")
    root = _repo(tmp_path, _doc(_ENTRY))

    proc = _check(root, path_env=str(stub_dir) + os.pathsep + os.environ.get("PATH", ""))

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not ran.exists(), "check ran gh"


@pytest.mark.skipif(_BASH is None, reason="no MSYS/POSIX bash")
def test_dispatch_matches_promote_gate(tmp_path):
    root = _repo(tmp_path, _doc(_ENTRY))
    proc = _check(root)
    assert proc.returncode == 0, proc.stdout
    command = proc.stdout.splitlines()[0][len("dispatch: "):]
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})

    gate = subprocess.run(
        [_BASH, _GATE_SH], input=payload, capture_output=True, text=True,
        check=False, cwd=str(root),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)))

    marker = root / ".crew" / ".deploy-in-flight"
    if gate.returncode == 0:
        assert marker.exists(), "allowed but the gate matched nothing: " + gate.stderr
        assert marker.read_text(encoding="utf-8").split()[0] == "staging"
    else:
        assert gate.returncode == 2, gate.stderr
        assert "PROMOTION BLOCKED (staging" in gate.stderr, gate.stderr
