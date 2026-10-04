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
    "ref tag": (_with(ref="refs/tags/v1"), "ref-not-branch"),
    "ref tag upper case": (_with(ref="REFS/TAGS/v1"), "ref-not-branch"),
    "ref remote": (_with(ref="refs/remotes/origin/main"), "ref-not-branch"),
    "ref HEAD": (_with(ref="HEAD"), "ref-not-branch"),
    "ref head lower case": (_with(ref="head"), "ref-not-branch"),
    "ref leading @": (_with(ref="@main"), "ref-at"),
    "ref lone @": (_with(ref="@"), "ref-at"),
    "ref .lock": (_with(ref="main.lock"), "ref-format"),
    "ref component .lock": (_with(ref="a.lock/b"), "ref-format"),
    "ref colon": (_with(ref="a:b"), "ref-format"),
    "ref trailing slash": (_with(ref="main/"), "ref-format"),
    "ref leading slash": (_with(ref="/main"), "ref-format"),
    "ref double slash": (_with(ref="a//b"), "ref-format"),
    "ref leading dot": (_with(ref=".main"), "ref-format"),
    "ref component leading dot": (_with(ref="a/.b"), "ref-format"),
    "ref trailing dot": (_with(ref="main."), "ref-format"),
    "ref null": (_with(ref=None), "ref-chars"),
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
    "shaInput in inputs by case": (_with(inputs={"Target": "staging"}, shaInput="target"),
                                   "sha-input-in-inputs"),
    "shaInput null": (_with(shaInput=None), "input-name-chars"),
    "correlationInput null": (_with(correlationInput=None), "input-name-chars"),
    "correlationInput in inputs by case": (_with(correlationInput="MODE"),
                                           "correlation-in-inputs"),
    "shaInput equals correlationInput by case": (_with(correlationInput="SHA"),
                                                 "sha-equals-correlation"),
    "input names equal by case": (_with(inputs={"a": "1", "A": "2"}),
                                  "input-name-duplicate"),
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
    "deployJob DEL": (_with(deployJob="deploy\x7f"), "deploy-job-bad"),
    "deployJob line separator": (_with(deployJob="deploy\u2028x"), "deploy-job-bad"),
    "deployJob paragraph separator": (_with(deployJob="deploy\u2029x"), "deploy-job-bad"),
    "deployJob NEL": (_with(deployJob="deploy\x85x"), "deploy-job-bad"),
    "deployJob null": (_with(deployJob=None), "deploy-job-bad"),
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


def test_an_env_name_is_never_printed_raw(tmp_path):
    """A detail line names the environment by repr, so a newline in its name
    cannot forge a second line, least of all a `result=` one."""
    env = "a\nresult=ok github=none"
    root = _repo(tmp_path, _doc(_with(inputs={"n": "a b"}), deploy=[_PREFIX], env=env))

    proc = _check(root, env=env)

    assert proc.returncode == 2, proc.stdout
    lines = proc.stdout.strip().splitlines()
    assert len(lines) == 2, lines
    assert repr(env) in lines[0], lines[0]
    assert lines[1] == "result=refused reason=value-chars"


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


@pytest.mark.parametrize("ref", ["main", "refs/heads/main", "release/1.2", "user@x",
                                 "a+b", "feature/a.b-c", "v1.2.3"])
def test_branch_refs_are_accepted(ref):
    """`v1.2.3` is accepted on purpose: a tag given by its bare name cannot be
    told from a branch without asking the remote, and `check` asks nothing."""
    assert crew_ghdeploy.entry_problem(_with(ref=ref), "staging") is None


# --- two environments: the gates' first substring match ----------------------
#
# Both promote-gate flavours take the FIRST environment, in file order, one of
# whose `deploy` strings is a substring of the command (the .ps1 with -like,
# which ignores case). So an environment whose dispatch contains another
# environment's `deploy` string is gated as that other environment. `check`
# refuses either side of such a pair as `ambiguous-environment`.

_PROD = {"workflow": "deploy.yml", "ref": "main", "inputs": {"target": "prod"},
         "shaInput": "sha"}


def _envs(*pairs, human=()):
    """{"environments": ...} from (name, github entry or None, deploy) triples."""
    out = {}
    for name, github, deploy in pairs:
        cfg = {"deploy": deploy, "rollback": "none",
               "rollbackReason": "the fixture deploys nothing"}
        if github is not None:
            cfg["github"] = github
            if deploy is None:
                cfg["deploy"] = [crew_ghdeploy.prefix(github)]
        if name in human:
            cfg["requireHuman"] = True
        out[name] = cfg
    return {"environments": out}


_CONFIGS = {
    # The review's repro: an input-less staging entry is a prefix of
    # production's dispatch, so production went out as staging, with no human.
    "inputless staging before production": (_envs(
        ("staging", {"workflow": "deploy.yml", "ref": "main"}, None),
        ("production", _PROD, None), human=("production",)), set()),
    # The other direction: staging's own dispatch overlaps no deploy string,
    # but its `deploy` is inside production's dispatch.
    "shaInput-only staging before production": (_envs(
        ("staging", {"workflow": "deploy.yml", "ref": "main", "shaInput": "sha"}, None),
        ("production", _PROD, None), human=("production",)), set()),
    # -like ignores case: `target=Prod` matches `target=prod` in the .ps1 only.
    "qa/Prod before production/prod": (_envs(
        ("qa", _with(inputs={"target": "Prod"}, shaInput="sha",
                     correlationInput=_DROP), None),
        ("production", _PROD, None), human=("production",)), set()),
    # A plain deploy string inside a github environment's dispatch.
    "plain deploy contained in a dispatch": (_envs(
        ("legacy", None, ["gh workflow run deploy.yml"]),
        ("production", _PROD, None), human=("production",)), {"legacy"}),
    "distinct targets": (_envs(
        ("staging", _with(inputs={"target": "staging"}, correlationInput=_DROP), None),
        ("production", _PROD, None), human=("production",)),
        {"staging", "production"}),
}


@pytest.mark.parametrize("label", sorted(_CONFIGS))
def test_check_refuses_an_environment_another_one_matches(tmp_path, label):
    doc, accepted = _CONFIGS[label]
    root = _repo(tmp_path, doc)
    for env, cfg in doc["environments"].items():
        proc = _check(root, env=env)
        if env in accepted:
            assert proc.returncode == 0, f"{label}/{env}: {proc.stdout}"
        elif "github" in cfg:
            assert proc.returncode == 2, f"{label}/{env}: {proc.stdout}"
            assert _last(proc) == "result=refused reason=ambiguous-environment", proc.stdout


def test_another_unreadable_environment_is_could_not_tell(tmp_path):
    """The gates exit 4 on any malformed environment, so `check` cannot say
    which environment a dispatch would be gated as either."""
    doc = _envs(("staging", _PROD, None))
    doc["environments"]["broken"] = {"deploy": 7}
    root = _repo(tmp_path, doc)

    proc = _check(root)

    assert proc.returncode == 3, proc.stdout
    assert _last(proc) == "result=could-not-tell reason=verify-json-unreadable"


_PWSH = crew_fixtures.resolve_pwsh()
_GATE_PS1 = os.path.join(_HOOKS, "promote-gate.ps1")


def _gate(flavour, root, command):
    if flavour == "sh":
        if _BASH is None:
            pytest.skip("no MSYS/POSIX bash - the .sh flavour was NOT run")
        argv, tool, extra = [_BASH, _GATE_SH], "Bash", {}
    else:
        if _PWSH is None:
            pytest.skip("pwsh not installed - the .ps1 flavour was NOT run")
        argv = [_PWSH, "-NoProfile", "-NonInteractive", "-File", _GATE_PS1]
        tool, extra = "PowerShell", {"OS": "Windows_NT"}
    marker = root / ".crew" / ".deploy-in-flight"
    if marker.exists():
        marker.unlink()
    payload = json.dumps({"tool_name": tool, "tool_input": {"command": command}})
    proc = subprocess.run(argv, input=payload, capture_output=True, text=True,
                          check=False, cwd=str(root),
                          env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root), **extra))
    if proc.returncode == 0:
        return marker.read_text(encoding="utf-8").split()[0] if marker.exists() else None
    found = re.search(r"PROMOTION BLOCKED \(([^,)]+)", proc.stderr)
    return found.group(1) if found else "unparsed: " + proc.stderr


@pytest.mark.parametrize("flavour", ["sh", "ps1"])
@pytest.mark.parametrize("label", sorted(_CONFIGS))
def test_every_accepted_dispatch_is_gated_as_its_own_environment(tmp_path, label, flavour):
    """For each environment `check` accepts, both real gates attribute its
    printed dispatch to that environment - blocked or allowed, never another
    environment's gates and never none."""
    doc, accepted = _CONFIGS[label]
    root = _repo(tmp_path, doc)
    gated = set()
    for env, cfg in doc["environments"].items():
        if "github" not in cfg:
            continue
        proc = _check(root, env=env)
        if proc.returncode != 0:
            continue
        for line in proc.stdout.splitlines():
            if line.startswith("dispatch: "):
                assert _gate(flavour, root, line[len("dispatch: "):]) == env, (
                    f"{label}: {env}'s dispatch is gated as another environment")
        gated.add(env)
    assert gated == {e for e in accepted if "github" in doc["environments"][e]}
