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
        {"staging": "staging,production", "production": "staging,production"}),
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
        {"dev": "dev,qa,production"}),
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
    "JSON nested 1000 deep (sh refuses)": (_raw(
        '"production": {"deploy": ["' + _PROD_PREFIX + '"], "github": ' + _GH_PROD
        + ', ' + _RB + '}, "deep": {"x": ' + "[" * 1000 + "]" * 1000 + '}'),
        {"production": "refused"}),
    "JSON nested 1100 deep (both refuse)": (_raw(
        '"production": {"deploy": ["' + _PROD_PREFIX + '"], "github": ' + _GH_PROD
        + ', ' + _RB + '}, "deep": {"x": ' + "[" * 1100 + "]" * 1100 + '}'),
        {"production": "refused"}),
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
    "JSON nested 1000 deep (sh refuses)": "sh",
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
     [_PROD_PREFIX + " -f sha=" + "0" * 40, "gh workflow run deploy.yml",
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
    # sh alone refuses (Python's fold, Python's recursion limit)
    ({"Iq": "deploy-a", "\u0131q": "deploy-b"}, ["deploy-a"]),
    ({"Sx": "deploy-a", "\u017fx": "deploy-b"}, ["deploy-a"]),
    (_raw('"p": {"deploy": "deploy-p", ' + _RB + '}, "deep": {"x": '
          + "[" * 1000 + "]" * 1000 + '}'), ["deploy-p"]),
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
    # The raw rows name only `p` (and `deep`); json cannot read the deep one.
    names = list(deploys) if isinstance(deploys, dict) else ["p", "deep"]
    differed = False
    for command in commands:
        sh, ps1 = _gate("sh", repo.root, command), _gate("ps1", repo.root, command)
        differed |= sh != ps1
        assert crew_ghdeploy.simulate_gate(text, command) == _union(sh, ps1, names), (
            f"either{index}, {command!r}: sh {sh!r}, ps1 {ps1!r}")
    # Each row but the both-read one is a case where the gates really differ.
    assert differed or index == 9, f"either{index}: the gates agree; the row proves nothing"


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


def test_deep_json_is_refused_not_a_traceback(tmp_path):
    """NIT1: past Python's recursion limit json raises RecursionError, which
    is no ValueError; check must still end on a result line."""
    root = _repo(tmp_path, None, raw=_raw(
        '"staging": {"deploy": ["' + _PREFIX + '"], "github": ' + json.dumps(_ENTRY)
        + ', ' + _RB + '}, "deep": {"x": ' + "[" * 5000 + "]" * 5000 + '}'))
    proc = _check(root)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert _last(proc) == "result=refused reason=gate-refuses-map"
    assert crew_ghdeploy.simulate_gate(
        _raw('"d": {"x": ' + "[" * 5000 + "]" * 5000 + '}'), "x") == "map"
