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
import contextlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import time

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


def _check(root, env="staging", path_env=None, encoding=None):
    environ = dict(os.environ)
    if encoding is not None:
        environ["PYTHONIOENCODING"] = encoding
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

    if isinstance(github, dict):
        assert crew_ghdeploy.entry_problem(github, "staging")[0] == reason, label
    # Two `inputs` keys equal ignoring case are a JSON object both promote
    # gates refuse, so in a file the map is refused before the entry is read.
    if label == "input names equal by case":
        reason = "gate-refuses-map"

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
    cannot forge a second line, least of all a `result=` one. U+2028 is a
    line break to `splitlines` and not a control character, so the gates
    read the map (a `\\n` in a name refuses it: gate-refuses-map)."""
    env = "a\u2028result=ok github=none"
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
    for deploy in ([p1], [p1, p2, "./deploy.sh"], "./deploy.sh", [p2]):
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


# --- several environments: the gates' union rule (L-1503) --------------------
#
# Both promote-gate flavours apply EVERY environment one of whose `deploy`
# strings matches the command (literally, ignoring case, either way round):
# the union of their requires, rollback and requireHuman. `check` therefore
# refuses no overlap; it prints, under each dispatch, `gated-as:` with the
# exact set both gates apply. A map the gates refuse to read is refused.

_PROD = {"workflow": "deploy.yml", "ref": "main", "inputs": {"target": "prod"},
         "shaInput": "sha"}
_PROD_PREFIX = "gh workflow run deploy.yml --ref main -f target=prod"


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


def _raw(envs_text):
    return '{"environments": {' + envs_text + '}}\n'


_RB = '"rollback": "none", "rollbackReason": "f"'
_GH_PROD = json.dumps(_PROD)

# label -> (map: a doc or raw JSON text, {github env: what check decides}).
# The decision is the `gated-as` set, or "refused" for `gate-refuses-map`.
_CONFIGS = {
    # The review's repro: an input-less staging entry is a prefix of
    # production's dispatch. First-match gated production as staging; the
    # union gates it as both, so production's requireHuman holds.
    "inputless staging before production": (_envs(
        ("staging", {"workflow": "deploy.yml", "ref": "main"}, None),
        ("production", _PROD, None), human=("production",)),
        {"staging": "staging", "production": "staging,production"}),
    "shaInput-only staging before production": (_envs(
        ("staging", {"workflow": "deploy.yml", "ref": "main", "shaInput": "sha"}, None),
        ("production", _PROD, None), human=("production",)),
        {"staging": "staging", "production": "staging,production"}),
    # Case variants: `target=Prod` and `target=prod` match each other.
    "qa/Prod before production/prod": (_envs(
        ("qa", _with(inputs={"target": "Prod"}, shaInput="sha",
                     correlationInput=_DROP), None),
        ("production", _PROD, None), human=("production",)),
        {"qa": "qa,production", "production": "qa,production"}),
    "plain deploy contained in a dispatch": (_envs(
        ("legacy", None, ["gh workflow run deploy.yml"]),
        ("production", _PROD, None), human=("production",)),
        {"production": "legacy,production"}),
    "B2 plain production string contains staging's prefix": (_envs(
        ("staging", _with(inputs={"target": "staging"}, correlationInput=_DROP), None),
        ("production", None, ["gh workflow run deploy.yml --ref main -f target=staging"
                              " -f promote=prod"]), human=("production",)),
        {"staging": "staging"}),
    "three-environment chain": (_envs(
        ("dev", _with(inputs={"target": "dev"}, shaInput=_DROP,
                      correlationInput=_DROP), None),
        ("qa", None, ["gh workflow run deploy.yml --ref main -f target=dev -f stage=qa"]),
        ("production", None, ["gh workflow run deploy.yml --ref main -f target=dev"
                              " -f stage=qa -f go=prod"]), human=("production",)),
        {"dev": "dev"}),
    # `*`, `?` and `[...]` are text to both gates: no wildcard claims a dispatch.
    "a star in an earlier plain string": (_envs(
        ("legacy", None, ["gh workflow run deploy.yml --ref main -f target=*"]),
        ("production", _PROD, None), human=("production",)),
        {"production": "production"}),
    "a bracket set in an earlier plain string": (_envs(
        ("legacy", None, ["gh workflow run [d]eploy.yml --ref main"]),
        ("production", _PROD, None), human=("production",)),
        {"production": "production"}),
    # Round 4 low FIX: `[!-[]` is a range pwsh's -like threw on; the gates no
    # longer read wildcards, so it is four characters and check accepts it.
    "a [!-[] deploy beside a github one": (_envs(
        ("legacy", None, ["ship [!-[]", "jq .items[0]"]),
        ("production", _PROD, None), human=("legacy",)),
        {"production": "production"}),
    # The `deploy` key, `environments` and per-environment keys in any case.
    "a Deploy key on another environment": ({"environments": {
        "preview": {"Deploy": "gh workflow run deploy.yml --ref main", "rollback": "none",
                    "rollbackReason": "fixture"},
        **_envs(("production", _PROD, None), human=("production",))["environments"]}},
        {"production": "preview,production"}),
    "an upper-case DEPLOY key and Environments on the github one": (
        '{"Environments": {"production": {"DEPLOY": ["' + _PROD_PREFIX + '"], '
        '"github": ' + _GH_PROD + ', "RequireHuman": true, ' + _RB + '}}}\n',
        {"production": "production"}),
    # A CRLF map, and a CR inside another environment's deploy string.
    "a CRLF map": (_raw(
        '\r\n"production": {"deploy": ["' + _PROD_PREFIX + '"],\r\n"github": '
        + _GH_PROD + ', ' + _RB + '},\r\n"cr": {"deploy": "gh workflow run deploy.yml\\r", '
        + _RB + '}\r\n'), {"production": "production"}),
    "empty deploy lists declare nothing": (_envs(
        ("empty", None, []), ("blank", None, [""]), ("production", _PROD, None)),
        {"production": "production"}),
    "distinct targets": (_envs(
        ("staging", _with(inputs={"target": "staging"}, correlationInput=_DROP), None),
        ("production", _PROD, None), human=("production",)),
        {"staging": "staging", "production": "production"}),
    # Maps both gates refuse: every command blocks, so check refuses too.
    "a comma in an environment name": (_envs(
        ("a,b", None, ["./deploy.sh x"]), ("production", _PROD, None)),
        {"production": "refused"}),
    "a newline in an environment name": (_envs(
        ("a\nb", None, ["./deploy.sh x"]), ("production", _PROD, None)),
        {"production": "refused"}),
    "an empty environment name": (_envs(
        ("", None, ["./deploy.sh x"]), ("production", _PROD, None)),
        {"production": "refused"}),
    "a null deploy elsewhere": (_envs(
        ("broken", None, None), ("production", _PROD, None)),
        {"production": "refused"}),
    "a numeric deploy elsewhere": (_envs(
        ("broken", None, 7), ("production", _PROD, None)),
        {"production": "refused"}),
    "a list requireHuman elsewhere": ({"environments": {
        "odd": {"deploy": "./deploy.sh odd", "requireHuman": [0], "rollback": "none",
                "rollbackReason": "fixture"},
        **_envs(("production", _PROD, None))["environments"]}},
        {"production": "refused"}),
    "an object requireHuman on the github one": ({"environments": {"production": dict(
        _envs(("production", _PROD, None))["environments"]["production"],
        requireHuman={})}}, {"production": "refused"}),
    "an environment that is not an object elsewhere": ({"environments": {
        "odd": "./deploy.sh odd",
        **_envs(("production", _PROD, None))["environments"]}},
        {"production": "refused"}),
    "an exact duplicate key": (_raw(
        '"production": {"deploy": ["' + _PROD_PREFIX + '"], "github": ' + _GH_PROD
        + ', "requireHuman": true, "requireHuman": false, ' + _RB + '}'),
        {"production": "refused"}),
    "keys differing only by case": (_raw(
        '"preview": {"deploy": "./deploy.sh preview", "Deploy": "./deploy.sh x", '
        + _RB + '}, "production": {"deploy": ["' + _PROD_PREFIX + '"], "github": '
        + _GH_PROD + ', ' + _RB + '}'), {"production": "refused"}),
    "duplicate environments": (_raw(
        '"production": {"deploy": "x", ' + _RB + '}, "production": {"deploy": ["'
        + _PROD_PREFIX + '"], "github": ' + _GH_PROD + ', ' + _RB + '}'),
        {"production": "refused"}),
    # Re-review FIX-1: maps only ONE gate refuses. `check` takes the stricter.
    "an empty key inside an environment (ps1 refuses)": (_raw(
        '"production": {"deploy": ["' + _PROD_PREFIX + '"], "github": ' + _GH_PROD
        + ', "note": {"": 1}, ' + _RB + '}'), {"production": "refused"}),
    "iota-subscript twin names (ps1 refuses)": (_envs(
        ("\u1f80", None, ["./deploy.sh a"]), ("\u1f88", None, ["./deploy.sh b"]),
        ("production", _PROD, None)), {"production": "refused"}),
    "a date-time deploy elsewhere (ps1 refuses)": (_envs(
        ("dated", None, ["2026-10-04T00:00:00Z"]), ("production", _PROD, None)),
        {"production": "refused"}),
    "a /Date()/ deploy elsewhere (ps1 refuses)": (_envs(
        ("dated", None, "/Date(0)/"), ("production", _PROD, None)),
        {"production": "refused"}),
    "dotless-i twin names (sh refuses)": (_envs(
        ("Iq", None, ["./deploy.sh a"]), ("\u0131q", None, ["./deploy.sh b"]),
        ("production", _PROD, None)), {"production": "refused"}),
    # A date-shaped string that ConvertFrom-Json keeps as a string is fine.
    "a near-date deploy elsewhere": (_envs(
        ("dated", None, ["2026-10-04T00:00"]), ("production", _PROD, None)),
        {"production": "production"}),
}
# The one gate that refuses each of these maps; the other reads it.
_ONE_GATE_REFUSES = {
    "an empty key inside an environment (ps1 refuses)": "ps1",
    "iota-subscript twin names (ps1 refuses)": "ps1",
    "a date-time deploy elsewhere (ps1 refuses)": "ps1",
    "a /Date()/ deploy elsewhere (ps1 refuses)": "ps1",
    "dotless-i twin names (sh refuses)": "sh",
}


def _config_repo(tmp_path, label):
    doc, expect = _CONFIGS[label]
    if isinstance(doc, str):
        return _repo(tmp_path, None, raw=doc), expect
    return _repo(tmp_path, doc), expect


def _decision(proc):
    """What `check` decided: its `gated-as` names, or "refused"."""
    if _last(proc) == "result=refused reason=gate-refuses-map":
        assert proc.returncode == 2, proc.stdout
        return "refused"
    assert proc.returncode == 0, proc.stdout + proc.stderr
    gated = {ln for ln in proc.stdout.splitlines() if ln.startswith("gated-as: ")}
    assert len(gated) == 1, proc.stdout
    return gated.pop()[len("gated-as: "):].strip("'")


@pytest.mark.parametrize("label", sorted(_CONFIGS))
def test_check_applies_the_gates_union_rule(tmp_path, label):
    root, expect = _config_repo(tmp_path, label)
    for env, decided in expect.items():
        assert _decision(_check(root, env=env)) == decided, f"{label}/{env!r}"


def test_check_names_the_union_and_says_it_is_one(tmp_path):
    root, _expect = _config_repo(tmp_path, "inputless staging before production")
    proc = _check(root, env="production")
    assert proc.returncode == 0, proc.stdout
    lines = proc.stdout.splitlines()
    assert lines[0].startswith("dispatch: " + _PROD_PREFIX + " -f sha=")
    assert lines[1] == "gated-as: 'staging,production'"


_PWSH = crew_fixtures.resolve_pwsh()
_GATE_PS1 = os.path.join(_HOOKS, "promote-gate.ps1")


def _gate(flavour, root, command):
    """What the real promote-gate.<flavour> decides for `command`: the names
    it gates it as (blocked or allowed), "map" for a refused map, or None."""
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
                          check=False, cwd=str(root), timeout=120,
                          env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root), **extra))
    if proc.returncode == 0:
        return marker.read_text(encoding="utf-8").split()[0] if marker.exists() else None
    assert proc.returncode == 2, f"{flavour} exited {proc.returncode}: {proc.stderr}"
    named = re.search(r"PROMOTION BLOCKED \((.+?)(?:, sha |\):)", proc.stderr)
    return named.group(1) if named else "map"


# One pwsh start per command is too slow for a 60s Stop: the .ps1 halves are
# `slow` (pytest-crew.yml runs that set with pwsh) except one smoke map each.
def _by_flavour(labels, smoke):
    return [pytest.param(label, flavour, id=f"{label}-{flavour}",
                         marks=() if flavour == "sh" or label == smoke
                         else crew_fixtures.SLOW)
            for label in labels for flavour in ("sh", "ps1")]


@pytest.mark.parametrize("label, flavour", _by_flavour(
    sorted(_CONFIGS), "a [!-[] deploy beside a github one"))
def test_check_agrees_with_the_real_gate(tmp_path, label, flavour):
    """For each github environment, `check`'s decision equals the real
    gate's on the dispatch it printed: the same `gated-as` set, or a map the
    gate refuses (it then blocks the dispatch without naming anyone)."""
    root, expect = _config_repo(tmp_path, label)
    for env in expect:
        proc = _check(root, env=env)
        decided = _decision(proc)
        if decided == "refused":
            command = "gh workflow run deploy.yml --ref main -f target=prod"
            real = _gate(flavour, root, command)
            if _ONE_GATE_REFUSES.get(label, flavour) == flavour:
                assert real == "map", f"{label}/{env!r}: {flavour} did not refuse"
            else:
                # The laxer gate reads the map; check took the stricter one.
                assert real != "map", f"{label}/{env!r}: {flavour} refused too"
            continue
        for line in proc.stdout.splitlines():
            if line.startswith("dispatch: "):
                real = _gate(flavour, root, line[len("dispatch: "):])
                assert real == decided, f"{label}/{env!r}: gate {real}, check {decided}"


# --- the agreement table: simulate_gate against both real gates --------------
#
# L-1503's own agreement maps (test_promote_gate_literal_match.py, the source
# of truth for gate behaviour) plus this module's: every command of every map
# goes to the real promote-gate.sh, the real promote-gate.ps1 and
# `simulate_gate`, and all three must decide the same.

import test_promote_gate_literal_match as gate_tests  # noqa: E402  pylint: disable=wrong-import-position,wrong-import-order

_EXTRA = [
    # the round-4 FIX: `[!-[]` and other sets are literal text
    ({"legacy": gate_tests._env(["ship [!-[]"], human=True),  # pylint: disable=protected-access
      "prod": _PROD_PREFIX},
     ["ship [!-[]", "ship [!-[] now", "SHIP [!-[]", "ship !", "ship ["]),
    # union with a dispatch, case variants in values
    ({"staging": "gh workflow run deploy.yml --ref main",
      "Prod": _PROD_PREFIX, "qa": "GH WORKFLOW RUN deploy.yml --ref main -f target=PROD"},
     [_PROD_PREFIX + " -f sha=" + "0" * 40, "gh workflow run deploy.yml --ref main -f target=PROD",
      "gh workflow run deploy.yml --ref main -f target=staging"]),
    # CRLF map text, and CRs inside a deploy string and the command
    (_raw('\r\n"a": {"deploy": "./deploy.sh a\\r", ' + _RB + '},\r\n'
          '"b": {"deploy": ["./deploy.sh b", "./deploy.sh"], ' + _RB + '}\r\n'),
     ["./deploy.sh a", "./deploy.sh a\r\n", "./deploy.sh\r", "./deploy.sh b\r\r\n"]),
    # bad names, duplicates, null / [] / [""] deploys, non-scalar requireHuman
    ({"x": "deploy-x", "a\u0085b": "deploy-y"}, ["deploy-x"]),
    (_raw('"a": {"deploy": "deploy-a", ' + _RB + '}, "A": {"deploy": "deploy-b", '
          + _RB + '}'), ["deploy-a", "echo hi"]),
    ({"none": {"deploy": None, "rollback": "none", "rollbackReason": "f"},
      "x": "deploy-x"}, ["deploy-x"]),
    ({"e": gate_tests._env([]), "b": gate_tests._env(["", "deploy-b"]),  # pylint: disable=protected-access
      "x": "deploy-x"}, ["deploy-x", "deploy-b", "deploy-"]),
    ({"h": dict(gate_tests._env("deploy-h"), requireHuman=["yes"])},  # pylint: disable=protected-access
     ["deploy-h"]),
    ({"h": dict(gate_tests._env("deploy-h"), requireHuman=1)},  # pylint: disable=protected-access
     ["deploy-h", "git status"]),
]
_TABLE = list(gate_tests._AGREEMENT) + _EXTRA  # pylint: disable=protected-access


@pytest.mark.parametrize("index, flavour", [
    pytest.param(i, flavour, id=f"map{i}-{flavour}",
                 marks=() if flavour == "sh" or i == len(gate_tests._AGREEMENT)  # pylint: disable=protected-access
                 else crew_fixtures.SLOW)
    for i in range(len(_TABLE)) for flavour in ("sh", "ps1")])
def test_simulate_gate_agrees_with_the_real_gate(tmp_path, index, flavour):
    deploys, commands = _TABLE[index]
    repo = gate_tests.Repo(tmp_path / "r", deploys if isinstance(deploys, str) else
                           {n: gate_tests._cfg(d) for n, d in deploys.items()})  # pylint: disable=protected-access
    text = (repo.root / ".crew" / "verify.json").read_text(encoding="utf-8")
    for command in commands:
        real = _gate(flavour, repo.root, command)
        assert crew_ghdeploy.simulate_gate(text, command) == real, (
            f"map {index}, {command!r}: promote-gate.{flavour} decided {real!r}")


# --- re-review FIX-1: refuse when EITHER gate refuses, match with the union --
#
# Maps and commands where the two real gates decide differently. The rule:
# `simulate_gate` says "map" when either gate refuses the map, and otherwise
# names the union of what the two gates apply.

_EITHER = [
    # ps1 alone refuses (ConvertFrom-Json / OrdinalIgnoreCase / DateTime)
    (_raw('"p": {"deploy": "deploy-p", "x": {"": 1}, ' + _RB + '}'), ["deploy-p"]),
    ({"\u1f80": "deploy-a", "\u1f88": "deploy-b"}, ["deploy-a", "echo hi"]),
    ({"p": {"deploy": "deploy-p", "\u1fb3": 1, "\u1fbc": 2, "rollback": "none",
            "rollbackReason": "f"}}, ["deploy-p"]),
    ({"d": gate_tests._env(["2026-10-04T00:00:00Z"]), "p": "deploy-p"},  # pylint: disable=protected-access
     ["deploy-p"]),
    ({"d": gate_tests._env("2026-10-04T00:00:00.123+02:00"), "p": "deploy-p"},  # pylint: disable=protected-access
     ["deploy-p"]),
    ({"d": gate_tests._env("/Date(0)/"), "p": "deploy-p"}, ["deploy-p"]),  # pylint: disable=protected-access
    # sh alone refuses (Python's fold)
    ({"Iq": "deploy-a", "\u0131q": "deploy-b"}, ["deploy-a"]),
    ({"Sx": "deploy-a", "\u017fx": "deploy-b"}, ["deploy-a"]),
    # both read it; a date-shaped string ConvertFrom-Json keeps is a command
    ({"d": gate_tests._env(["2026-10-04T00:00", "2026-10-04 00:00:00"]),  # pylint: disable=protected-access
      "p": "deploy-p"}, ["2026-10-04T00:00", "deploy-p", "2026-10-04 00:00:00 now"]),
    # the gates match differently; the simulation names the union
    ({"net": "ship \u1f88", "py": "ship \u0131x"},
     ["ship \u1f80", "SHIP \u1f88", "ship Ix", "ship \u0131x"]),
]


def _union(sh, ps1, names):
    """The rule's expectation from two real decisions."""
    if "map" in (sh, ps1):
        return "map"
    hit = set((sh or "").split(",")) | set((ps1 or "").split(","))
    return ",".join(n for n in names if n in hit) or None


@pytest.mark.parametrize("index", [
    pytest.param(i, id=f"either{i}", marks=() if i == 1 else crew_fixtures.SLOW)
    for i in range(len(_EITHER))])
def test_simulate_gate_refuses_when_either_gate_refuses(tmp_path, index):
    deploys, commands = _EITHER[index]
    repo = gate_tests.Repo(tmp_path / "r", deploys if isinstance(deploys, str) else
                           {n: gate_tests._cfg(d) for n, d in deploys.items()})  # pylint: disable=protected-access
    text = (repo.root / ".crew" / "verify.json").read_text(encoding="utf-8")
    names = list(json.loads(text)["environments"])
    differed = False
    for command in commands:
        sh, ps1 = _gate("sh", repo.root, command), _gate("ps1", repo.root, command)
        differed |= sh != ps1
        assert crew_ghdeploy.simulate_gate(text, command) == _union(sh, ps1, names), (
            f"either{index}, {command!r}: sh {sh!r}, ps1 {ps1!r}")
    # Each row but the both-read one is a case where the gates really differ.
    assert differed or index == 8, f"either{index}: the gates agree; the row proves nothing"


def test_the_dotnet_only_fold_table_is_pinned():
    """27 pairs, measured on pwsh 7.4.6 over every BMP code point: equal
    under OrdinalIgnoreCase, different under Python's per-character fold."""
    table = crew_ghdeploy._DOTNET_ONLY_FOLDS  # pylint: disable=protected-access
    assert len(table) == 27
    for low, up in table.items():
        assert crew_ghdeploy._fold(low) != crew_ghdeploy._fold(up)  # pylint: disable=protected-access
        assert crew_ghdeploy._dotnet_fold(low) == crew_ghdeploy._dotnet_fold(up)  # pylint: disable=protected-access
    assert crew_ghdeploy._dotnet_fold("\u0131\u017f") == "\u0131\u017f"  # pylint: disable=protected-access
    if _PWSH is None:
        pytest.skip("pwsh not installed - the .NET side of the table was NOT measured")
    pairs = ";".join(f"[string]::Equals([string][char]{ord(a)},[string][char]{ord(b)},"
                     "[StringComparison]::OrdinalIgnoreCase)" for a, b in table.items())
    out = subprocess.run([_PWSH, "-NoProfile", "-NonInteractive", "-Command", pairs],
                         capture_output=True, text=True, check=True, timeout=120).stdout
    assert out.split() == ["True"] * 27, out


@pytest.mark.parametrize("text, date", [
    ("2026-10-04T00:00:00Z", True), ("2026-10-04T00:00:00", True),
    ("2026-10-04T00:00:00.123+02:00", True), ("0001-01-01T00:00:00", True),
    ("9999-12-31T23:59:59.9999999", True), ("2026-10-04T24:00:00", True),
    ("2026-10-04T00:00:00-0500", True), ("2026-10-04T00:00:00+05", True),
    ("2026-10-04T00:00:00.123456789", True), ("/Date(0)/", True),
    ("/Date(-1)/", True), ("/Date(0+0100)/", True),
    ("2026-10-04", False), ("2026-10-04 00:00:00", False), ("2026-10-04T00:00", False),
    ("2026-10-04T00:00:00 x", False), ("x 2026-10-04T00:00:00Z", False),
    ("2026-13-04T00:00:00", False), ("2026-10-04t00:00:00", False),
    ("2023-02-29T00:00:00", False), ("2026-10-04T24:00:01", False),
    ("2026-10-04T00:00:00.1234567890123Z", False), ("2026-10-04T00:00:00Zx", False),
    ("\uff12026-10-04T00:00:00", False), ("/Date(x)/", False), ("/Date()/", False),
    ("/Date(99999999999999999999)/", False), ("/Date(1)/x", False),
])
def test_is_dotnet_date_is_what_convertfrom_json_converts(text, date):
    """Each measured with ConvertFrom-Json on pwsh 7.4.6; 9,000 fuzzed
    strings agreed with the port on 2026-10-04."""
    assert crew_ghdeploy._is_dotnet_date(text) is date  # pylint: disable=protected-access


def _nested(depth):
    """A map whose `deep` environment nests `depth` levels in all."""
    inner = depth - 3  # the document, `environments` and `deep` are three
    return _raw('"staging": {"deploy": ["' + _PREFIX + '"], "github": '
                + json.dumps(_ENTRY) + ', ' + _RB + '}, "deep": {"x": '
                + "[" * inner + "]" * inner + '}')


@pytest.mark.parametrize("depth, refused", [
    (crew_ghdeploy._MAX_DEPTH, False),  # pylint: disable=protected-access
    (crew_ghdeploy._MAX_DEPTH + 1, True),  # pylint: disable=protected-access
    (5000, True)])
def test_nesting_past_a_fixed_bound_is_refused_on_every_interpreter(tmp_path, depth, refused):
    """NIT1, re-done. Where json.loads hits RecursionError depends on the
    interpreter (3.11 refuses 1,000 levels, 3.12 reads them), so `check`
    refuses past a fixed `_MAX_DEPTH` (200), below every interpreter's limit
    and ConvertFrom-Json's 1,024, and never reaches a RecursionError. What
    the real promote-gate.sh does at 1,000 levels is deliberately not asserted."""
    text = _nested(depth)
    assert crew_ghdeploy._depth(text) == depth  # pylint: disable=protected-access
    root = _repo(tmp_path, None, raw=text)
    proc = _check(root)
    if refused:
        assert proc.returncode == 2, proc.stdout + proc.stderr
        assert _last(proc) == "result=refused reason=gate-refuses-map"
        assert crew_ghdeploy.simulate_gate(text, "x") == "map"
    else:
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert crew_ghdeploy.simulate_gate(text, _PREFIX) == "staging"


@pytest.mark.parametrize("text, depth", [
    ('{"a": "[[[{{{"}', 1), ('{"a": "\\"[[["}', 1), ('{"a": "\\\\", "b": [[]]}', 3),
    ("[]", 1), ('"x"', 0), ('{"a": {"b": [1, {"c": []}]}}', 5)])
def test_depth_skips_brackets_inside_strings(text, depth):
    assert crew_ghdeploy._depth(text) == depth  # pylint: disable=protected-access


@pytest.mark.parametrize("label", ["iota-subscript twin names (ps1 refuses)",
                                   "dotless-i twin names (sh refuses)"])
def test_a_non_ascii_name_in_a_message_survives_a_cp1252_stdout(tmp_path, label):
    """Windows CI: printing the refusal (which names the key) on a cp1252
    stdout raised UnicodeEncodeError, exit 1 with no result line."""
    root, _expect = _config_repo(tmp_path, label)
    proc = _check(root, env="production", encoding="cp1252")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert _last(proc) == "result=refused reason=gate-refuses-map"


# --- the github sequence (L-0644 to L-0647): shared fixtures ------------------
#
# Every `gh` call goes through `crew_ghdeploy._run_gh`, which these tests
# replace with `FakeGh`: it answers from a table keyed by the call's leading
# words and records every argv, so `test_helper_never_dispatches` can prove no
# scenario dispatched, cancelled, re-ran, merged or sent a mutating `api`.

_SEQ_SHA_ENTRY = {"workflow": "deploy.yml", "ref": "main",
                  "inputs": {"target": "staging"}, "shaInput": "sha"}
_ACTOR = "octo-bot"
_SCENARIOS = []         # every sequence scenario, for the never-dispatches test


def _scenario(fn):
    _SCENARIOS.append(fn)
    return fn


class FakeGh:  # pylint: disable=too-few-public-methods
    """`_run_gh`'s stand-in. `answers` maps a tuple of leading words to
    `(status, stdout)` or to a list of them, consumed one call at a time
    (the last one repeats)."""

    def __init__(self, answers):
        self.answers = {k: list(v) if isinstance(v, list) else [v]
                        for k, v in answers.items()}
        self.calls = []

    def __call__(self, args, _root, **_kw):
        args = list(args)
        self.calls.append(args)
        for key in sorted(self.answers, key=len, reverse=True):
            if tuple(args[:len(key)]) == key:
                queue = self.answers[key]
                return queue.pop(0) if len(queue) > 1 else queue[0]
        return 1, ""


def _ok(obj):
    return 0, json.dumps(obj)


def _seq_repo(tmp_path, monkeypatch, entry=None, env="staging", workflows=None,
              non_prod=("staging",)):
    """A committed repo whose `env` carries `entry`, with the repo layer's
    `environments` block, the machine layer pointed at an empty file, and
    the clock at 1,000,000."""
    entry = dict(_SEQ_SHA_ENTRY if entry is None else entry)
    root = _repo(tmp_path, _doc(entry, env=env))
    config = {"environments": {"nonProd": list(non_prod), "workflows": (
        {"deploy.yml": "input:target"} if workflows is None else workflows)}}
    (root / ".crew" / "config.json").write_text(json.dumps(config), encoding="utf-8")
    glob = tmp_path / "global.json"
    glob.write_text("{}", encoding="utf-8")
    import crew_config  # pylint: disable=import-outside-toplevel
    import crew_state  # pylint: disable=import-outside-toplevel
    monkeypatch.setattr(crew_state, "GLOBAL_CONFIG_PATH", str(glob))
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(glob))
    monkeypatch.setattr(crew_ghdeploy, "_clock", lambda: 1_000_000)
    monkeypatch.setattr(crew_ghdeploy, "_sleep", lambda _s: None)
    return root


def _prepare_answers(sha, **over):
    answers = {("api", "user"): _ok({"login": _ACTOR}),
               ("api", f"repos/{{owner}}/{{repo}}/commits/{sha}"): _ok({"sha": sha}),
               ("api", "repos/{owner}/{repo}/branches/main"): _ok({"commit": {"sha": sha}}),
               ("run", "list"): _ok([{"databaseId": 11}, {"databaseId": 12}])}
    answers.update({tuple(k.split(" ")): v for k, v in over.items()})
    return answers


def _run(monkeypatch, gh, *argv):
    """`crew_ghdeploy.main(argv)` in-process with `gh`: `(exit, stdout lines)`."""
    monkeypatch.setattr(crew_ghdeploy, "_run_gh", gh)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = crew_ghdeploy.main(list(argv))
    return code, out.getvalue().splitlines()


def _forbidden(argv):
    """A `gh` call the helper must never make: a dispatch, a cancel, a re-run,
    a merge, or an `api` call with a method other than GET."""
    if argv[:2] in (["workflow", "run"], ["run", "cancel"], ["run", "rerun"],
                    ["pr", "merge"]):
        return True
    if argv[:1] == ["api"]:
        for i, word in enumerate(argv):
            method = (argv[i + 1] if word in ("-X", "--method") and i + 1 < len(argv)
                      else word[2:] if word.startswith("-X") and len(word) > 2
                      else word.split("=", 1)[1] if word.startswith("--method=")
                      else None)
            if method is not None and method.upper() != "GET":
                return True
    return False


def _state(root, env="staging", index=0):
    path = root / ".crew" / ".ghdeploy" / f"{env}-{index}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


# --- prepare (L-0644) ---------------------------------------------------------

def _prepare(monkeypatch, root, gh, env="staging"):
    return _run(monkeypatch, gh, "prepare", "--root", str(root), "--env", env)


@_scenario
def test_nonprod_prepare(tmp_path, monkeypatch):
    """must-allow: exit 0, the dispatch is the last line before `result=`,
    the state holds the snapshot and t0, and gh saw exactly three calls."""
    root = _seq_repo(tmp_path, monkeypatch)
    sha = _head(root)
    gh = FakeGh(_prepare_answers(sha))
    code, lines = _prepare(monkeypatch, root, gh)
    assert code == 0, lines
    assert lines[-1].startswith("result=ok class=nonProd")
    assert lines[-2] == f"gh workflow run deploy.yml --ref main -f target=staging -f sha={sha}"
    state = _state(root)
    assert state["snapshot"] == [11, 12] and state["t0"] == 1_000_000
    assert state["actor"] == _ACTOR and state["sha"] == sha
    assert state["deadline"] == 1_000_000 + 60 * 60
    assert state["command"] == lines[-2]
    assert [c[:2] for c in gh.calls] == [
        ["api", "user"], ["api", f"repos/{{owner}}/{{repo}}/commits/{sha}"],
        ["run", "list"]]


@_scenario
def test_prepare_with_a_correlation_input_records_the_id(tmp_path, monkeypatch):
    entry = dict(_SEQ_SHA_ENTRY, correlationInput="crew_id")
    root = _seq_repo(tmp_path, monkeypatch, entry=entry)
    code, lines = _prepare(monkeypatch, root, FakeGh(_prepare_answers(_head(root))))
    assert code == 0, lines
    corr = _state(root)["correlationId"]
    assert re.fullmatch(r"crew-staging-[0-9a-f]{7}-[0-9a-f]{8}", corr)
    assert lines[-2].endswith(f"-f crew_id={corr}")


def _no_branch_entry():
    return {k: v for k, v in _SEQ_SHA_ENTRY.items() if k != "shaInput"}


_PREPARE_BLOCKS = {
    # name: (entry, deploy override, config workflows, nonProd, gh overrides, reason)
    "config-problem": (dict(_SEQ_SHA_ENTRY, workflow="Deploy"), None, None,
                       ("staging",), {}, "workflow-not-filename"),
    "deploy-prefix-mismatch": (None, ["gh workflow run deploy.yml"], None,
                               ("staging",), {}, "deploy-prefix-mismatch"),
    "unmapped-workflow": (None, None, {"other.yml": "staging"}, ("staging",), {},
                          "unmapped-workflow"),
    "unknown-environment": (None, None, {"deploy.yml": "input:region"},
                            ("staging",), {}, "unknown-environment"),
    "class-mismatch": (None, None, {"deploy.yml": "production"}, ("staging",), {},
                       "class-mismatch"),
    "actor-unreadable": (None, None, None, ("staging",),
                         {"api user": (1, "")}, "actor-unreadable"),
    "sha-not-on-remote": (None, None, None, ("staging",),
                          {"api commits": None}, "sha-not-on-remote"),
    "branch-tip-not-head": ("no-sha", None, None, ("staging",),
                            {"api repos/{owner}/{repo}/branches/main":
                             _ok({"commit": {"sha": "0" * 40}})},
                            "branch-tip-not-head"),
    "snapshot-unreadable": (None, None, None, ("staging",),
                            {"run list": (1, "")}, "snapshot-unreadable"),
}


@pytest.mark.parametrize("name", sorted(_PREPARE_BLOCKS))
def test_prepare_refuses(tmp_path, monkeypatch, name):
    """must-block: exit 2 and nothing under `.crew/.ghdeploy/`."""
    entry, deploy, workflows, non_prod, over, reason = _PREPARE_BLOCKS[name]
    entry = _no_branch_entry() if entry == "no-sha" else entry
    root = _seq_repo(tmp_path, monkeypatch, entry=entry, workflows=workflows,
                     non_prod=non_prod)
    if deploy is not None:
        doc = json.loads((root / ".crew" / "verify.json").read_text(encoding="utf-8"))
        doc["environments"]["staging"]["deploy"] = deploy
        (root / ".crew" / "verify.json").write_text(json.dumps(doc), encoding="utf-8")
    sha = _head(root)
    answers = _prepare_answers(sha)
    for key, value in over.items():
        if key == "api commits":
            answers[("api", f"repos/{{owner}}/{{repo}}/commits/{sha}")] = _ok({"sha": "1" * 40})
        else:
            answers[tuple(key.split(" "))] = value
    code, lines = _prepare(monkeypatch, root, FakeGh(answers))
    assert code == 2, lines
    assert lines[-1] == f"result=refused reason={reason}"
    assert not (root / ".crew" / ".ghdeploy").exists()


for _name in sorted(_PREPARE_BLOCKS):
    _scenario(lambda t, m, _n=_name: test_prepare_refuses(t, m, _n))


def test_prepare_refuses_an_environment_without_a_github_entry(tmp_path, monkeypatch):
    root = _seq_repo(tmp_path, monkeypatch)
    doc = json.loads((root / ".crew" / "verify.json").read_text(encoding="utf-8"))
    del doc["environments"]["staging"]["github"]
    (root / ".crew" / "verify.json").write_text(json.dumps(doc), encoding="utf-8")
    code, lines = _prepare(monkeypatch, root, FakeGh(_prepare_answers(_head(root))))
    assert code == 2, lines
    assert lines[-1] == "result=refused reason=github-none"
    assert not (root / ".crew" / ".ghdeploy").exists()


@_scenario
def test_prepare_refuses_an_env_name_that_leaves_the_state_dir(tmp_path, monkeypatch):
    """An environment named `../x` exists in the map, but its state file
    would land outside `.crew/.ghdeploy/`: refused before any gh call."""
    root = _seq_repo(tmp_path, monkeypatch, env="../escape", non_prod=("../escape",))
    gh = FakeGh(_prepare_answers(_head(root)))
    code, lines = _prepare(monkeypatch, root, gh, env="../escape")
    assert code == 2, lines
    assert lines[-1] == "result=refused reason=env-name-path"
    assert gh.calls == []
    assert not (root / ".crew" / "escape-0.json").exists()
    assert not (root / ".crew" / ".ghdeploy").exists()


@_scenario
def test_prepare_refuses_a_corrupt_machine_environments_block(tmp_path, monkeypatch):
    """The dispatch guard reads the machine layer's block too: a corrupt one
    is unknown-environment, never the repo layer's nonProd answer."""
    root = _seq_repo(tmp_path, monkeypatch)
    (tmp_path / "global.json").write_text('{"environments": {"nonProd": "staging"}}',
                                          encoding="utf-8")
    code, lines = _prepare(monkeypatch, root, FakeGh(_prepare_answers(_head(root))))
    assert code == 2, lines
    assert lines[-1] == "result=refused reason=unknown-environment"
    assert not (root / ".crew" / ".ghdeploy").exists()


_BRANCH_ANSWERS = [{"commit": None}, {"commit": "abc"}, [], "x"]


@pytest.mark.parametrize("answer", _BRANCH_ANSWERS)
def test_prepare_a_malformed_branch_answer_is_not_head(tmp_path, monkeypatch, answer):
    root = _seq_repo(tmp_path, monkeypatch, entry=_no_branch_entry())
    answers = _prepare_answers(_head(root))
    answers[("api", "repos/{owner}/{repo}/branches/main")] = _ok(answer)
    code, lines = _prepare(monkeypatch, root, FakeGh(answers))
    assert code == 2, lines
    assert lines[-1] == "result=refused reason=branch-tip-not-head"
    assert not (root / ".crew" / ".ghdeploy").exists()


for _answer in _BRANCH_ANSWERS:
    _scenario(lambda t, m, _a=_answer: test_prepare_a_malformed_branch_answer_is_not_head(t, m, _a))


@_scenario
def test_prepare_and_identify_take_a_full_branch_ref(tmp_path, monkeypatch):
    """`check` accepts `refs/heads/main`: the dispatch keeps it, but the
    branches GET, `run list -b` and the run's `headBranch` use the name."""
    entry = dict(_no_branch_entry(), ref="refs/heads/main")
    root = _seq_repo(tmp_path, monkeypatch, entry=entry)
    doc = json.loads((root / ".crew" / "verify.json").read_text(encoding="utf-8"))
    doc["environments"]["staging"]["deploy"] = [crew_ghdeploy.prefix(entry)]
    (root / ".crew" / "verify.json").write_text(json.dumps(doc), encoding="utf-8")
    gh = FakeGh(_prepare_answers(_head(root)))
    code, lines = _prepare(monkeypatch, root, gh)
    assert code == 0, lines
    assert "--ref refs/heads/main" in lines[-2]
    assert ["api", "repos/{owner}/{repo}/branches/main"] in gh.calls
    assert [c[5] for c in gh.calls if c[:2] == ["run", "list"]] == ["main"]
    gh = FakeGh({("run", "list"): _ok([_new_run(13, created=1_000_002)])})
    code, lines = _run(monkeypatch, gh, "identify", "--root", str(root), "--env", "staging")
    assert code == 0, lines
    assert gh.calls[0][5] == "main" and _state(root)["runId"] == 13


def test_prepare_classifier_crash_refuses(tmp_path, monkeypatch):
    import crew_dispatch  # pylint: disable=import-outside-toplevel
    root = _seq_repo(tmp_path, monkeypatch)

    def boom(*_a):
        raise RuntimeError("classifier exploded")
    monkeypatch.setattr(crew_dispatch, "dispatch_environment", boom)
    code, lines = _prepare(monkeypatch, root, FakeGh(_prepare_answers(_head(root))))
    assert code == 2, lines
    assert lines[-1] == "result=refused reason=classifier-failed"
    assert not (root / ".crew" / ".ghdeploy").exists()


def test_prepare_state_is_atomic(tmp_path, monkeypatch):
    """A failure while writing leaves no partial state file."""
    root = _seq_repo(tmp_path, monkeypatch)
    real = os.replace

    def fail(src, dst):
        raise OSError("disk full")
    monkeypatch.setattr(crew_ghdeploy.os, "replace", fail)
    with pytest.raises(OSError):
        _prepare(monkeypatch, root, FakeGh(_prepare_answers(_head(root))))
    monkeypatch.setattr(crew_ghdeploy.os, "replace", real)
    left = list((root / ".crew" / ".ghdeploy").iterdir())
    assert left == []


def test_helper_never_dispatches(tmp_path, monkeypatch):
    """Across every registered scenario of every subcommand, no recorded gh
    argv dispatches, cancels, re-runs, merges or sends a mutating `api`."""
    seen = []
    real = FakeGh.__call__

    def spy(self, args, root, **kw):
        seen.append(list(args))
        return real(self, args, root, **kw)
    monkeypatch.setattr(FakeGh, "__call__", spy)
    for index, scenario in enumerate(_SCENARIOS):
        where = tmp_path / f"scenario-{index}"
        where.mkdir()
        with monkeypatch.context() as patch:
            scenario(where, patch)
    assert seen, "no scenario reached gh"
    assert [a for a in seen if _forbidden(a)] == []
    for bad in (["workflow", "run", "x.yml"], ["run", "cancel", "1"],
                ["run", "rerun", "1"], ["pr", "merge", "1"],
                ["api", "-X", "POST", "x"], ["api", "--method=DELETE", "x"],
                ["api", "-XPATCH", "x"]):
        assert _forbidden(bad), bad
    assert not _forbidden(["api", "user"])


# --- identify (L-0645) --------------------------------------------------------

_T0 = 1_000_000


def _iso(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _new_run(run_id, created=_T0 + 2, branch="main", event="workflow_dispatch", title="Deploy"):
    return {"databaseId": run_id, "createdAt": created if isinstance(created, str)
            else _iso(created), "headBranch": branch, "event": event,
            "displayTitle": title, "url": f"https://github.com/o/r/actions/runs/{run_id}"}


_OLD = [_new_run(11, created=_T0 - 3600), _new_run(12, created=_T0 - 1800)]


def _identify_repo(tmp_path, monkeypatch, corr=False, t0=_T0, now=_T0 + 3):
    """A repo after a successful `prepare` (snapshot 11 and 12, t0 = `t0`),
    with a clock at `now` that each 5-second sleep advances."""
    entry = dict(_SEQ_SHA_ENTRY, correlationInput="crew_id") if corr else None
    root = _seq_repo(tmp_path, monkeypatch, entry=entry)
    monkeypatch.setattr(crew_ghdeploy, "_clock", lambda: t0)
    code, lines = _prepare(monkeypatch, root, FakeGh(_prepare_answers(_head(root))))
    assert code == 0, lines
    clock = {"now": now}
    monkeypatch.setattr(crew_ghdeploy, "_clock", lambda: clock["now"])
    monkeypatch.setattr(crew_ghdeploy, "_sleep",
                        lambda s: clock.__setitem__("now", clock["now"] + s))
    return root


def _identify(monkeypatch, root, answers):
    """`identify` with `run list` answering `answers` (one per poll, the last
    repeating): `(exit, lines, gh)`."""
    gh = FakeGh({("run", "list"): answers})
    code, lines = _run(monkeypatch, gh, "identify", "--root", str(root), "--env", "staging")
    return code, lines, gh


def _title(root):
    return f"Deploy {_state(root)['correlationId']}"


_IDENTIFY_BLOCKS = {
    # name: (correlation?, run-list answers or a callable of root, reason)
    "two-candidates": (False, [_ok(_OLD + [_new_run(13), _new_run(14)])], "two-candidates"),
    "none-in-timeout": (False, [_ok(_OLD)], "none-in-timeout"),
    "old-run-only": (False, [_ok([_new_run(11, created=_T0 + 1)])], "none-in-timeout"),
    "wrong-branch": (False, [_ok(_OLD + [_new_run(13, branch="other")])], "none-in-timeout"),
    "wrong-event": (False, [_ok(_OLD + [_new_run(13, event="push")])], "none-in-timeout"),
    "outside-the-window": (False, [_ok(_OLD + [_new_run(13, created=_T0 - 31)])],
                           "none-in-timeout"),
    "correlation-not-found": (True, [_ok(_OLD + [_new_run(13, title="Deploy crew-other")])],
                              "correlation-not-found"),
    "created-unparseable": (False, [_ok(_OLD + [_new_run(13, created="yesterday")])],
                            "created-unparseable"),
    "created-without-zone": (False, [_ok(_OLD + [_new_run(13, created="2026-10-04T12:00:00")])],
                             "created-unparseable"),
    "run-list-fails": (False, [(1, "")], "run-list-fails"),
    "run-list-not-runs": (False, [_ok({"runs": []})], "run-list-unreadable"),
    "run-without-url": (False, [_ok(_OLD + [dict(_new_run(13), url=None)])],
                        "run-url-unreadable"),
}


@pytest.mark.parametrize("name", sorted(_IDENTIFY_BLOCKS))
def test_identify_could_not_tell(tmp_path, monkeypatch, name):
    """must-block: exit 3, the last line names the reason, no run id written
    and the state file byte-identical."""
    corr, answers, reason = _IDENTIFY_BLOCKS[name]
    root = _identify_repo(tmp_path, monkeypatch, corr=corr)
    path = root / ".crew" / ".ghdeploy" / "staging-0.json"
    before = path.read_bytes()
    code, lines, _gh = _identify(monkeypatch, root, answers)
    assert code == 3, lines
    assert lines[-1] == f"result=could-not-tell reason={reason}"
    assert path.read_bytes() == before
    assert not any("runs/1" in line for line in lines)


for _name in sorted(_IDENTIFY_BLOCKS):
    _scenario(lambda t, m, _n=_name: test_identify_could_not_tell(t, m, _n))


@_scenario
def test_identify_polls_until_identify_seconds(tmp_path, monkeypatch):
    """none-in-timeout polls every 5 seconds for identifySeconds (120): 24
    polls, at 0 to 115 seconds; none starts at the deadline itself."""
    root = _identify_repo(tmp_path, monkeypatch)
    code, lines, gh = _identify(monkeypatch, root, [_ok(_OLD)])
    assert code == 3, lines
    assert len(gh.calls) == 120 // 5


@_scenario
def test_identify_stale_prepare(tmp_path, monkeypatch):
    root = _identify_repo(tmp_path, monkeypatch, now=_T0 + 601)
    code, lines, gh = _identify(monkeypatch, root, [_ok(_OLD + [_new_run(13)])])
    assert code == 3, lines
    assert lines[-1] == "result=could-not-tell reason=stale-prepare"
    assert gh.calls == [] and "runId" not in _state(root)


def test_identify_at_600_seconds_is_not_stale(tmp_path, monkeypatch):
    root = _identify_repo(tmp_path, monkeypatch, now=_T0 + 600)
    code, lines, _gh = _identify(monkeypatch, root, [_ok(_OLD + [_new_run(13)])])
    assert code == 0, lines


@_scenario
def test_identify_state_file_missing(tmp_path, monkeypatch):
    root = _seq_repo(tmp_path, monkeypatch)
    code, lines, gh = _identify(monkeypatch, root, [_ok([_new_run(13)])])
    assert code == 3, lines
    assert lines[-1] == "result=could-not-tell reason=state-file-missing"
    assert gh.calls == []


@pytest.mark.parametrize("text", ["{not json", "[]", '{"workflow": "deploy.yml"}'])
def test_identify_state_file_unreadable(tmp_path, monkeypatch, text):
    root = _identify_repo(tmp_path, monkeypatch)
    path = root / ".crew" / ".ghdeploy" / "staging-0.json"
    path.write_text(text, encoding="utf-8")
    code, lines, gh = _identify(monkeypatch, root, [_ok([_new_run(13)])])
    assert code == 3, lines
    assert lines[-1] == "result=could-not-tell reason=state-file-unreadable"
    assert gh.calls == [] and path.read_text(encoding="utf-8") == text


_scenario(lambda t, m: test_identify_state_file_unreadable(t, m, "{not json"))


@_scenario
def test_identify_one_new_run(tmp_path, monkeypatch):
    """must-allow: the one new run's id and URL go into the state file, and
    the call carries the snapshot's filters."""
    root = _identify_repo(tmp_path, monkeypatch)
    code, lines, gh = _identify(monkeypatch, root, [_ok(_OLD + [_new_run(13)])])
    assert code == 0, lines
    assert lines[-1] == "result=ok run=13"
    state = _state(root)
    assert state["runId"] == 13
    assert state["runUrl"] == "https://github.com/o/r/actions/runs/13"
    assert gh.calls == [["run", "list", "-w", "deploy.yml", "-b", "main", "-e",
                         "workflow_dispatch", "-u", _ACTOR, "-L", "50", "--json",
                         crew_ghdeploy.RUN_FIELDS]]


@_scenario
def test_identify_new_run_after_two_polls(tmp_path, monkeypatch):
    root = _identify_repo(tmp_path, monkeypatch)
    code, lines, gh = _identify(monkeypatch, root,
                                [_ok(_OLD), (1, ""), _ok(_OLD + [_new_run(13)])])
    assert code == 0, lines
    assert _state(root)["runId"] == 13 and len(gh.calls) == 3


@_scenario
def test_identify_correlation_found(tmp_path, monkeypatch):
    """Two new runs in the window: the one titled with the id is the run."""
    root = _identify_repo(tmp_path, monkeypatch, corr=True)
    runs = _OLD + [_new_run(13, title="Deploy crew-staging-other"),
                   _new_run(14, title=_title(root))]
    code, lines, _gh = _identify(monkeypatch, root, [_ok(runs)])
    assert code == 0, lines
    assert _state(root)["runId"] == 14


@_scenario
def test_identify_clock_skew_within_30s(tmp_path, monkeypatch):
    root = _identify_repo(tmp_path, monkeypatch)
    code, lines, _gh = _identify(monkeypatch, root,
                                 [_ok(_OLD + [_new_run(13, created=_T0 - 20)])])
    assert code == 0, lines
    assert _state(root)["runId"] == 13


def test_identify_writes_run_atomically(tmp_path, monkeypatch):
    """A failed write leaves the state file byte-identical."""
    root = _identify_repo(tmp_path, monkeypatch)
    path = root / ".crew" / ".ghdeploy" / "staging-0.json"
    before = path.read_bytes()

    def fail(_src, _dst):
        raise OSError("disk full")
    monkeypatch.setattr(crew_ghdeploy.os, "replace", fail)
    with pytest.raises(OSError):
        _identify(monkeypatch, root, [_ok(_OLD + [_new_run(13)])])
    assert path.read_bytes() == before
    assert sorted(p.name for p in path.parent.iterdir()) == ["staging-0.json"]


# --- watch (L-0646) -----------------------------------------------------------

_WATCH_ENTRY = dict(_SEQ_SHA_ENTRY, deployJob="deploy*")


class ClockGh(FakeGh):  # pylint: disable=too-few-public-methods
    """FakeGh whose `run watch` takes time: a 124 (killed at its timeout)
    advances the clock by that timeout, anything else by 80 seconds or the
    timeout, whichever is less."""

    def __init__(self, answers, clock):
        super().__init__(answers)
        self.clock = clock
        self.timeouts = []

    def __call__(self, args, root, **kw):
        code, out = super().__call__(args, root, **kw)
        if list(args[:2]) == ["run", "watch"]:
            self.timeouts.append(kw.get("timeout"))
            timeout = kw.get("timeout", 0)
            self.clock["now"] += timeout if code == 124 else min(80, timeout)
        return code, out


def _watch_repo(tmp_path, monkeypatch, entry=None, run_id=13, now=_T0 + 10):
    """A repo after prepare and identify (run `run_id`, deadline t0 + 3600),
    with an advancing clock: `(root, clock)`."""
    root = _seq_repo(tmp_path, monkeypatch, entry=_WATCH_ENTRY if entry is None else entry)
    code, lines = _prepare(monkeypatch, root, FakeGh(_prepare_answers(_head(root))))
    assert code == 0, lines
    state = _state(root)
    if run_id is not None:
        state["runId"] = run_id
    crew_ghdeploy.write_state(str(root / ".crew" / ".ghdeploy" / "staging-0.json"), state)
    clock = {"now": now}
    monkeypatch.setattr(crew_ghdeploy, "_clock", lambda: clock["now"])
    monkeypatch.setattr(crew_ghdeploy, "_sleep",
                        lambda s: clock.__setitem__("now", clock["now"] + s))
    return root, clock


def _view(root, status="completed", conclusion="success", jobs=(("deploy-prod", "success"),),
          head=None):
    return _ok({"status": status, "conclusion": conclusion,
                "headSha": head or _head(root), "url": "https://github.com/o/r/actions/runs/13",
                "jobs": [{"name": n, "conclusion": c} for n, c in jobs]})


def _watch(monkeypatch, root, clock, watch, view, *extra):
    gh = ClockGh({("run", "watch"): watch, ("run", "view"): view}, clock)
    code, lines = _run(monkeypatch, gh, "watch", "--root", str(root), "--env", "staging",
                       *extra)
    return code, lines, gh


_NO_SHA_WATCH = {k: v for k, v in _WATCH_ENTRY.items() if k != "shaInput"}

_WATCH_CASES = {
    # name: (entry, watch answers, view answers (root -> list), exit, verdict line)
    "watch-exit0-conclusion-failure": (None, [(0, "")],
                                       lambda r: [_view(r, conclusion="failure")],
                                       1, "fail", "conclusion-failure"),
    "deploy-job-skipped": (None, [(0, "")],
                           lambda r: [_view(r, jobs=[("build", "success"),
                                                     ("deploy-prod", "skipped")])],
                           1, "fail", "deploy-job-skipped"),
    "deploy-job-absent": (None, [(0, "")], lambda r: [_view(r, jobs=[("build", "success")])],
                          1, "fail", "deploy-job-absent"),
    "cancelled": (None, [(1, "")], lambda r: [_view(r, conclusion="cancelled")],
                  1, "fail", "conclusion-cancelled"),
    "headsha-mismatch": (_NO_SHA_WATCH, [(0, "")], lambda r: [_view(r, head="0" * 40)],
                         1, "fail", "headsha-mismatch"),
    "watch-nonzero-view-unreadable": (None, [(1, "")], lambda r: [(1, "")],
                                      3, "unknown", "view-unreadable"),
    "view-not-json": (None, [(0, "")], lambda r: [(0, "not json")],
                      3, "unknown", "view-unreadable"),
    "jobs-unreadable": (None, [(0, "")], lambda r: [_ok({"status": "completed",
                                                         "conclusion": "success",
                                                         "headSha": _head(r), "jobs": None})],
                        3, "unknown", "jobs-unreadable"),
    "nonprod-happy": (None, [(0, "")], lambda r: [_view(r)], 0, "pass",
                      "success-deploy-job-succeeded"),
    "no-deploy-job-configured": (dict(_SEQ_SHA_ENTRY), [(0, "")], lambda r: [_view(r)],
                                 0, "pass", "success-deploy-job-not-checked"),
    "watch-nonzero-view-success": (None, [(1, "token type not supported")],
                                   lambda r: [_view(r)], 0, "pass",
                                   "success-deploy-job-succeeded"),
    "status-unreadable": (None, [(0, "")], lambda r: [_view(r, status=None, conclusion="")],
                          3, "unknown", "status-unreadable"),
    "status-unknown-word": (None, [(0, "")], lambda r: [_view(r, status="paused", conclusion="")],
                            3, "unknown", "status-unreadable"),
    "no-shainput-head-matches": (_NO_SHA_WATCH, [(0, "")], lambda r: [_view(r)],
                                 0, "pass", "success-deploy-job-succeeded"),
}


@pytest.mark.parametrize("name", sorted(_WATCH_CASES))
def test_watch_verdict(tmp_path, monkeypatch, name):
    """The verdict comes from the run view, never the watch exit code, and
    goes into the state file and the last line."""
    entry, watch, view, code_wanted, verdict, reason = _WATCH_CASES[name]
    root, clock = _watch_repo(tmp_path, monkeypatch, entry=entry)
    code, lines, gh = _watch(monkeypatch, root, clock, watch, view(root))
    assert code == code_wanted, lines
    assert lines[-1] == f"result={verdict} run=13 reason={reason}"
    state = _state(root)
    assert (state["verdict"], state["verdictReason"]) == (verdict, reason)
    assert state["watchExit"] == watch[0][0]
    assert ["run", "watch", "13", "--exit-status", "--interval", "15"] in gh.calls


for _name in sorted(_WATCH_CASES):
    _scenario(lambda t, m, _n=_name: test_watch_verdict(t, m, _n))


@_scenario
def test_watch_timeout_is_unknown_and_never_cancels(tmp_path, monkeypatch):
    """In progress at the deadline: unknown, the run named and left running."""
    root, clock = _watch_repo(tmp_path, monkeypatch, now=_T0 + 3600 - 100)
    code, lines, gh = _watch(monkeypatch, root, clock, [(124, "")],
                             [_view(root, status="in_progress", conclusion="")])
    assert code == 3, lines
    assert lines[-1] == "result=unknown run=13 reason=still-running"
    assert any("left running" in line for line in lines)
    assert gh.timeouts == [100]
    assert not any(c[:2] == ["run", "cancel"] for c in gh.calls)


@_scenario
def test_watch_queued_then_success(tmp_path, monkeypatch):
    """The first slice ends before the deadline (exit 75, no verdict); the
    second passes."""
    root, clock = _watch_repo(tmp_path, monkeypatch)
    code, lines, gh = _watch(monkeypatch, root, clock, [(124, "")],
                             [_view(root, status="queued", conclusion="")])
    assert code == 75, lines
    assert lines[-1].startswith("result=again run=13")
    assert gh.timeouts == [540] and "verdict" not in _state(root)
    code, lines, _gh = _watch(monkeypatch, root, clock, [(0, "")], [_view(root)])
    assert code == 0, lines
    assert _state(root)["verdict"] == "pass"


@_scenario
def test_watch_a_watch_that_cannot_run_polls_the_view(tmp_path, monkeypatch):
    """The watch fails at once: the view is polled every 15 seconds and the
    run finishing inside the slice is judged then."""
    root, clock = _watch_repo(tmp_path, monkeypatch)
    views = [_view(root, status="in_progress", conclusion="")] * 3 + [_view(root)]
    code, lines, gh = _watch(monkeypatch, root, clock, [(1, "")], views)
    assert code == 0, lines
    assert len([c for c in gh.calls if c[:2] == ["run", "view"]]) == 4


@_scenario
def test_watch_no_run_id_in_state(tmp_path, monkeypatch):
    root, clock = _watch_repo(tmp_path, monkeypatch, run_id=None)
    code, lines, gh = _watch(monkeypatch, root, clock, [(0, "")], [_view(root)])
    assert code == 3, lines
    assert lines[-1] == "result=could-not-tell reason=no-run-id-in-state"
    assert gh.calls == [] and "verdict" not in _state(root)


def test_watch_slice_seconds_range(tmp_path, monkeypatch):
    root, clock = _watch_repo(tmp_path, monkeypatch)
    for bad in ("0", "571"):
        code, lines, gh = _watch(monkeypatch, root, clock, [(0, "")], [_view(root)],
                                 "--slice-seconds", bad)
        assert code == 2 and lines[-1] == "result=refused reason=slice-seconds-range"
        assert gh.calls == []
    code, lines, gh = _watch(monkeypatch, root, clock, [(0, "")], [_view(root)],
                             "--slice-seconds", "30")
    assert code == 0 and gh.timeouts == [30]


@_scenario
def test_identify_bounds_each_poll_by_the_exact_time_left(tmp_path, monkeypatch):
    """The call gets the fractional time left (not rounded down), and no
    poll starts once identifySeconds is spent."""
    root = _identify_repo(tmp_path, monkeypatch)
    clock = {"now": _T0 + 3.0}
    monkeypatch.setattr(crew_ghdeploy, "_clock", lambda: clock["now"])
    monkeypatch.setattr(crew_ghdeploy, "_sleep",
                        lambda s: clock.__setitem__("now", clock["now"] + s))
    timeouts = []

    def slow(_args, _root, timeout=None):
        timeouts.append(round(timeout, 3))
        clock["now"] += 110.1 if len(timeouts) == 1 else 3.0
        return _ok(_OLD)
    code, lines = _run(monkeypatch, slow, "identify", "--root", str(root), "--env", "staging")
    assert code == 3, lines
    # 113.1 -> sleep -> 118.1 (4.9 left) -> 121.1 -> sleep -> 126.1: past the
    # deadline, so no third poll starts.
    assert timeouts == [120.0, 4.9]


@_scenario
def test_identify_an_answer_after_identify_seconds_is_not_used(tmp_path, monkeypatch):
    """A `run list` that answers after the deadline is not a run, and the
    call itself is bounded by the time left."""
    root = _identify_repo(tmp_path, monkeypatch)
    clock = {"now": _T0 + 3}
    monkeypatch.setattr(crew_ghdeploy, "_clock", lambda: clock["now"])
    timeouts = []

    def slow(_args, _root, timeout=None):
        timeouts.append(timeout)
        clock["now"] += 130
        return _ok(_OLD + [_new_run(13)])
    code, lines = _run(monkeypatch, slow, "identify", "--root", str(root), "--env", "staging")
    assert code == 3, lines
    assert lines[-1] == "result=could-not-tell reason=none-in-timeout"
    assert timeouts == [120] and "runId" not in _state(root)


# --- record (L-0647) ----------------------------------------------------------

_FAIL_LOG = "\n".join([f"step {i} \x1b[31merror\x1b[0m | {'x' * 400}" for i in range(50)]
                      + ["| development | abc | pass | pass | pass |"])
_PREV = ("| when (UTC) | env | sha | smoke | regression | verify | by |\n"
         "|---|---|---|---|---|---|---|\n"
         "| 2026-10-01T10:00Z | staging | " + "a" * 40 + " | pass | pass | pass | octo |\n"
         "| 2026-10-02T10:00Z | staging | " + "b" * 40 + " | pass | FAIL | pass | octo |\n")


def _record_repo(tmp_path, monkeypatch, verdict="fail", reason="conclusion-failure",
                 run_id=13, promotions=None):
    """A repo after prepare, identify and watch (`verdict`), the clock at
    2026-10-05T12:00Z, PROMOTIONS.md holding `promotions` (None: absent)."""
    root, _clock = _watch_repo(tmp_path, monkeypatch, run_id=run_id)
    state = _state(root)
    if verdict is not None:
        state.update(verdict=verdict, verdictReason=reason,
                     runUrl="https://github.com/o/r/actions/runs/13")
    crew_ghdeploy.write_state(str(root / ".crew" / ".ghdeploy" / "staging-0.json"), state)
    monkeypatch.setattr(crew_ghdeploy, "_clock", lambda: 1_791_201_600)
    if promotions is not None:
        (root / ".work").mkdir(exist_ok=True)
        (root / ".work" / "PROMOTIONS.md").write_text(promotions, encoding="utf-8")
    return root


def _record(monkeypatch, root, log=(0, _FAIL_LOG)):
    gh = FakeGh({("run", "view"): log})
    code, lines = _run(monkeypatch, gh, "record", "--root", str(root), "--env", "staging")
    text = root / ".work" / "PROMOTIONS.md"
    return code, lines, gh, text.read_text(encoding="utf-8") if text.exists() else None


def _verify_gate_finds(text, env, sha):
    """verify-gate.sh's Stop-check pattern, run with grep as the hook runs it."""
    proc = subprocess.run(["grep", "-qE", rf"\|[[:space:]]*{env}[[:space:]]*\|[[:space:]]*{sha}"],
                          input=text, text=True, check=False)
    return proc.returncode == 0


@_scenario
def test_record_pass_writes_one_detail_line(tmp_path, monkeypatch):
    root = _record_repo(tmp_path, monkeypatch, verdict="pass",
                        reason="success-deploy-job-succeeded", promotions=_PREV)
    code, lines, gh, text = _record(monkeypatch, root)
    assert code == 0, lines
    sha = _head(root)
    added = text[len(_PREV):].splitlines()
    assert added == [f"- deploy staging {sha} github deploy.yml@main run 13 pass "
                     "https://github.com/o/r/actions/runs/13 at 2026-10-05T12:00Z - "
                     "success-deploy-job-succeeded"]
    assert gh.calls == [] and lines[-1] == "result=recorded outcome=pass"


@_scenario
def test_record_fail(tmp_path, monkeypatch):
    """The detail line, the previous good sha, the cleaned excerpt and the
    not-run row with the full sha, which verify-gate's pattern finds."""
    root = _record_repo(tmp_path, monkeypatch, promotions=_PREV)
    code, lines, gh, text = _record(monkeypatch, root)
    assert code == 0, lines
    sha = _head(root)
    added = text[len(_PREV):].splitlines()
    assert added[0].startswith(f"- deploy staging {sha} github deploy.yml@main run 13 FAIL ")
    assert added[1] == "  previous all-pass sha for staging: " + "a" * 40
    log = added[3:-1]
    assert len(log) == 40
    assert all(line.startswith("    ") and "|" not in line and "\x1b" not in line
               and len(line) <= 304 for line in log)
    assert log[-1] == "    / development / abc / pass / pass / pass /"
    assert log[0].startswith("    step 11 error / xxx")  # the colour codes are gone, not blanked
    assert added[-1] == f"| 2026-10-05T12:00Z | staging | {sha} | not-run | not-run | not-run | {_ACTOR} |"
    assert ["run", "view", "13", "--log-failed"] in gh.calls
    assert _verify_gate_finds(text, "staging", sha[:7])
    assert lines[-1] == "result=recorded outcome=FAIL"
    assert all("|" not in line for line in added[:-1])


@_scenario
def test_record_could_not_tell(tmp_path, monkeypatch):
    """No run id: run `none`, a not-run row, no excerpt."""
    root = _record_repo(tmp_path, monkeypatch, verdict=None, run_id=None, promotions=_PREV)
    code, lines, gh, text = _record(monkeypatch, root)
    assert code == 0, lines
    added = text[len(_PREV):].splitlines()
    assert " run none could-not-tell - at " in added[0]
    assert added[1] == "  previous all-pass sha for staging: " + "a" * 40
    assert len(added) == 3 and added[2].startswith("| 2026-10-05T12:00Z | staging |")
    assert gh.calls == []


@_scenario
def test_record_unknown_with_no_previous_good(tmp_path, monkeypatch):
    root = _record_repo(tmp_path, monkeypatch, verdict="unknown", reason="still-running")
    code, lines, _gh, text = _record(monkeypatch, root, log=(1, ""))
    assert code == 0, lines
    assert "  previous all-pass sha for staging: none" in text
    assert "    (the failed-step log could not be read)" in text


@_scenario
def test_record_absent_file_gets_the_header(tmp_path, monkeypatch):
    root = _record_repo(tmp_path, monkeypatch, verdict="pass", reason="x")
    code, lines, _gh, text = _record(monkeypatch, root)
    assert code == 0, lines
    assert text.startswith(crew_ghdeploy.HEADER)
    assert len(text.splitlines()) == 3


@_scenario
def test_record_without_verdict(tmp_path, monkeypatch):
    root = _record_repo(tmp_path, monkeypatch, verdict=None, promotions=_PREV)
    code, lines, gh, text = _record(monkeypatch, root)
    assert code == 3, lines
    assert lines[-1] == "result=could-not-tell reason=record-without-verdict"
    assert text == _PREV and gh.calls == []


@_scenario
def test_record_is_atomic(tmp_path, monkeypatch):
    """A record that raises while building the excerpt leaves the file
    byte-identical, and so does a failed replace."""
    root = _record_repo(tmp_path, monkeypatch, promotions=_PREV)
    path = root / ".work" / "PROMOTIONS.md"
    before = path.read_bytes()

    def boom(_root, _run_id):
        raise RuntimeError("log exploded")
    monkeypatch.setattr(crew_ghdeploy, "excerpt", boom)
    with pytest.raises(RuntimeError):
        _record(monkeypatch, root)
    assert path.read_bytes() == before
    monkeypatch.undo()
    root = _record_repo(tmp_path / "again", monkeypatch, promotions=_PREV)
    path = root / ".work" / "PROMOTIONS.md"

    def fail(_src, _dst):
        raise OSError("disk full")
    monkeypatch.setattr(crew_ghdeploy.os, "replace", fail)
    with pytest.raises(OSError):
        _record(monkeypatch, root)
    assert path.read_bytes() == before
    assert sorted(p.name for p in path.parent.iterdir()) == ["PROMOTIONS.md"]


def test_previous_good_is_the_last_all_pass_row():
    text = _PREV + "| 2026-10-03T10:00Z | staging | " + "c" * 40 + " | PASS | pass | pass | o |\n"
    assert crew_ghdeploy.previous_good(text, "staging") == "c" * 40
    assert crew_ghdeploy.previous_good(_PREV, "qa") is None


_BAD_ENTRY_KEYS = {"deployJob absent": ("deployJob", _DROP), "deployJob empty": ("deployJob", ""),
                   "deployJob a number": ("deployJob", 3), "shaInput absent": ("shaInput", _DROP),
                   "shaInput true": ("shaInput", True), "shaInput empty": ("shaInput", "")}


@pytest.mark.parametrize("label", sorted(_BAD_ENTRY_KEYS))
def test_watch_a_state_file_without_the_entry_keys_is_unreadable(tmp_path, monkeypatch, label):
    """A state file that does not say, as prepare writes it, whether
    `deployJob` or `shaInput` was set is never read as "not configured"."""
    root, clock = _watch_repo(tmp_path, monkeypatch)
    state = _state(root)
    key, value = _BAD_ENTRY_KEYS[label]
    if value is _DROP:
        del state[key]
    else:
        state[key] = value
    crew_ghdeploy.write_state(str(root / ".crew" / ".ghdeploy" / "staging-0.json"), state)
    code, lines, gh = _watch(monkeypatch, root, clock, [(0, "")],
                             [_view(root, jobs=[("deploy-prod", "skipped")])])
    assert code == 3, lines
    assert lines[-1] == "result=could-not-tell reason=state-file-unreadable"
    assert gh.calls == [] and "verdict" not in _state(root)


for _label in sorted(_BAD_ENTRY_KEYS):
    _scenario(lambda t, m, _l=_label: test_watch_a_state_file_without_the_entry_keys_is_unreadable(
        t, m, _l))


@_scenario
def test_watch_one_call_ends_inside_the_bash_limit(tmp_path, monkeypatch):
    """A watch that uses its whole 570-second slice leaves the run view at
    most 25 seconds, so one call ends inside 600."""
    root, clock = _watch_repo(tmp_path, monkeypatch)
    start = clock["now"]
    seen = []

    def gh(args, _root, timeout=None):
        seen.append((list(args[:2]), timeout))
        clock["now"] += timeout  # every call runs until it is killed
        return 124, ""
    code, lines = _run(monkeypatch, gh, "watch", "--root", str(root), "--env", "staging",
                       "--slice-seconds", "570")
    assert code == 3, lines
    assert lines[-1] == "result=unknown run=13 reason=view-unreadable"
    assert seen == [(["run", "watch"], 570), (["run", "view"], 25)]
    assert clock["now"] - start < 600


@_scenario
def test_record_an_unreadable_promotions_file_is_could_not_tell(tmp_path, monkeypatch):
    """A PROMOTIONS.md that cannot be read is exit 3 and left as it was; it
    is never replaced by a fresh header."""
    root = _record_repo(tmp_path, monkeypatch)
    (root / ".work").mkdir(exist_ok=True)
    (root / ".work" / "PROMOTIONS.md").mkdir()
    gh = FakeGh({("run", "view"): (0, _FAIL_LOG)})
    code, lines = _run(monkeypatch, gh, "record", "--root", str(root), "--env", "staging")
    assert code == 3, lines
    assert lines[-1] == "result=could-not-tell reason=promotions-unreadable"
    assert (root / ".work" / "PROMOTIONS.md").is_dir()
    assert sorted(p.name for p in (root / ".work").iterdir()) == ["PROMOTIONS.md"]
