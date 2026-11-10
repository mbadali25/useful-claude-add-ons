"""crew 1.3.36: promote-gate.sh decides in ONE python process (_promote_gate.py).

What this holds, each a must-block or a must-allow:

1. The decision corpus (promote_gate_corpus.py). Its expected exit statuses and
   phrases were RECORDED from the shell-only gate of crew 1.3.32 and are
   replayed here on the current gate, so a rule the rewrite dropped turns a case
   red. All 41 recorded cases agreed with the new gate when it was written.
2. The protocol between the shell and the python gate: statuses 10+N and 20+N
   keep their wording, any other non-zero status blocks, and a missing gate
   blocks. An error is not permission.
3. The spawn count: bash starts no helper program for a deploy-shaped command,
   allowed or blocked, and python once.
4. The deadline: derived from the hook timeout, configurable, clamped, and
   enforced end to end.
5. The allow fast path, now the first step of the gate.
"""
import json
import os
import pathlib
import shlex
import re
import shutil
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
import promote_gate_corpus as corpus
import _promote_gate

_SCRIPTS = pathlib.Path(context._ROOT) / "hooks" / "scripts"  # pylint: disable=protected-access
_BASH = crew_fixtures.resolve_bash()
needs_bash = pytest.mark.skipif(_BASH is None, reason="bash not installed - the sh flavour was NOT run")


def _env(tmp_path, root):
    env = crew_fixtures.isolated_home_env(tmp_path / "home")
    env["CLAUDE_PROJECT_DIR"] = str(root)
    env["CREW_PYTHON"] = sys.executable
    return env


def _run(tmp_path, spec, scripts=_SCRIPTS, trace=False, extra_env=None):
    root, short, full, base = corpus.build(tmp_path, spec)
    env = _env(tmp_path, root)
    env.update(extra_env or {})
    argv = [_BASH] + (["-x"] if trace else []) + [(scripts / "promote-gate.sh").as_posix()]
    if trace:
        env["PS4"] = "+ "
    proc = subprocess.run(argv, input=corpus.payload(root, spec, short, full, base),
                          capture_output=True, env=env, cwd=str(root), check=False, timeout=170)
    return proc, root, short


def _text(data):
    return data.decode("utf-8", errors="replace")


# --- 1. the decision corpus --------------------------------------------------

@needs_bash
@pytest.mark.parametrize("spec", corpus.CASES, ids=corpus.NAMES)
def test_the_corpus_decides_as_the_old_gate_did(spec, tmp_path):
    proc, root, short = _run(tmp_path, spec)
    err = _text(proc.stderr)
    assert proc.returncode == spec["code"], err
    if spec["why"]:
        assert spec["why"] in err, err
    marker = root / ".crew" / ".deploy-in-flight"
    if spec["code"] == 2:
        assert not marker.exists(), "a blocked deploy must leave no in-flight marker"
    if spec["state"].get("incident") == "open":
        skips = root / ".crew" / "incident-skips.log"
        assert skips.exists() and "promote" in skips.read_text(encoding="utf-8"), \
            "an open incident records the unmet preconditions as skips"
        assert not marker.exists() or marker.read_text(encoding="utf-8").strip()
    if spec["name"] in ("staging-with-nothing-upstream", "prod-with-every-precondition-met",
                        "prod-dispatch-with-every-precondition-met"):
        env = "staging" if spec["name"].startswith("staging") else "prod"
        assert marker.read_text(encoding="utf-8").strip() == f"{env} {short}"


def test_every_case_the_old_gate_decided_is_in_the_corpus():
    """The corpus is the record: dropping a case would drop what it guards."""
    assert len(corpus.CASES) >= 40
    assert len(set(corpus.NAMES)) == len(corpus.NAMES)
    assert {c["code"] for c in corpus.CASES} == {0, 2}
    assert not any(c["fixed"] for c in corpus.CASES), "no recorded decision differs from the old gate"


# --- 2. the protocol between the shell and the python gate ----------------------

def _stub_scripts(tmp_path, body):
    """promote-gate.sh and _common.sh beside a stub _promote_gate.py."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for name in ("promote-gate.sh", "_common.sh"):
        shutil.copyfile(_SCRIPTS / name, scripts / name)
    if body is not None:
        (scripts / "_promote_gate.py").write_text(body, encoding="utf-8")
    return scripts


def _stub_run(tmp_path, body):
    scripts = _stub_scripts(tmp_path, body)
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    (root / ".crew" / "verify.json").write_text("{}\n", encoding="utf-8")
    env = _env(tmp_path, root)
    payload = json.dumps({"tool_name": "Bash", "cwd": str(root), "tool_input": {"command": "x"}})
    proc = subprocess.run([_BASH, (scripts / "promote-gate.sh").as_posix()], input=payload.encode(),
                          capture_output=True, env=env, cwd=str(root), check=False, timeout=60)
    return proc.returncode, _text(proc.stderr)


@needs_bash
@pytest.mark.parametrize("status,code,phrases", [
    (0, 0, ()),
    (2, 2, ()),
    (13, 2, ("could not be read as a deployment map (exit 3)", "This is NOT a pass.")),
    (14, 2, ("(exit 4)",)),
    (25, 2, ("This is not a pass. Something in .crew/verify.json",)),
    (7, 2, ("failed to run (exit 7)", "This is not a pass.")),
    (1, 2, ("failed to run (exit 1)",)),
    (127, 2, ("failed to run (exit 127)",)),
    (99, 2, ("failed to run (exit 99)",)),
])
def test_the_shell_maps_the_gates_exit_status(tmp_path, status, code, phrases):
    got, err = _stub_run(tmp_path, f"import sys\nsys.stderr.write('stub reason\\n')\nsys.exit({status})\n")
    assert got == code, err
    for phrase in phrases:
        assert phrase in err, err


@needs_bash
def test_a_missing_gate_blocks(tmp_path):
    got, err = _stub_run(tmp_path, None)
    assert got == 2, err
    assert "_promote_gate.py is missing" in err and "This is not a pass." in err


@needs_bash
def test_a_gate_that_cannot_start_blocks(tmp_path):
    got, err = _stub_run(tmp_path, "raise SystemExit('syntax is fine, the interpreter is not')\n")
    assert got == 2, err


# --- 3. the spawn count --------------------------------------------------------

_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\[[^]]*\])?\+?=")
_HELPERS = {"tr", "dirname", "uname", "cut", "cygpath", "date", "jq", "sed", "awk", "git",
            "basename", "head", "wc", "grep", "cat", "timeout"}


def _programs(trace):
    found = []
    for line in trace.splitlines():
        match = re.match(r"^\++ (.*)$", line)
        if not match:
            continue
        try:
            words = shlex.split(match.group(1))
        except ValueError:
            words = match.group(1).split()
        while words and _ASSIGN.match(words[0]):
            words.pop(0)
        if words:
            found.append(words[0].replace("\\", "/").rsplit("/", 1)[-1])
    return found


def _python_runs(programs):
    return [p for p in programs if re.match(r"^(python[0-9.]*|py)(\.exe)?$", p, re.I)]


@needs_bash
@pytest.mark.parametrize("name", ["prod-with-every-precondition-met",
                                  "prod-without-a-staging-row",
                                  "prod-dispatch-with-every-precondition-met",
                                  "a-leading-cd-into-the-repo"])
def test_a_deploy_starts_one_python_and_no_helper_in_bash(tmp_path, name):
    """The bug: about forty-five process starts for one deploy-shaped command. Here
    bash starts python once and nothing else (git is asked by python itself)."""
    spec = next(c for c in corpus.CASES if c["name"] == name)
    proc, _, _ = _run(tmp_path, spec, trace=True)
    programs = _programs(_text(proc.stderr))
    assert proc.returncode == spec["code"], _text(proc.stderr)[-3000:]
    assert sorted(set(programs) & _HELPERS) == [], programs
    assert len(_python_runs(programs)) == 1, programs


# --- 4. the deadline -----------------------------------------------------------

def test_the_default_deadline_is_the_hook_timeout_less_the_margin():
    import crew_hook  # pylint: disable=import-outside-toplevel
    row = next(r for r in crew_hook.TABLE if r.script == "promote-gate.sh")
    assert _promote_gate.hook_timeout() == row.timeout
    assert _promote_gate.deadline_seconds() == row.timeout - _promote_gate.DEFAULT_MARGIN
    assert _promote_gate.deadline_seconds(timeout=20) == 16
    assert _promote_gate.deadline_seconds(timeout=90) == 86, "a raised hook timeout raises the default"


@pytest.mark.parametrize("configured,expected", [
    (None, 16), (5, 5), (7.5, 7.5), (17, 17), (18, 18),
    (19, 18), (300, 18),          # clamped to the timeout less the reap: never outlive the hook
])
def test_a_configured_deadline_is_used_and_clamped(configured, expected):
    assert _promote_gate.deadline_seconds(timeout=20, configured=configured) == expected


@pytest.mark.parametrize("value", [None, True, False, "9", [], {}, 0, -3, 0.0, float("nan"), float("inf")])
def test_an_unusable_configured_deadline_reads_as_null(value, monkeypatch):
    import crew_config  # pylint: disable=import-outside-toplevel
    monkeypatch.setattr(crew_config, "resolve_config", lambda root: {"promote": {"deadlineSeconds": value}})
    assert _promote_gate.configured_seconds() is None


@pytest.mark.parametrize("value", [3, 7.5, 18])
def test_a_usable_configured_deadline_is_read(value, monkeypatch):
    import crew_config  # pylint: disable=import-outside-toplevel
    monkeypatch.setattr(crew_config, "resolve_config", lambda root: {"promote": {"deadlineSeconds": value}})
    assert _promote_gate.configured_seconds() == float(value)


def test_a_config_that_cannot_be_read_is_null(monkeypatch):
    import crew_config  # pylint: disable=import-outside-toplevel

    def boom(root):
        raise OSError("unreadable")
    monkeypatch.setattr(crew_config, "resolve_config", boom)
    assert _promote_gate.configured_seconds() is None


def test_the_clock_counts_from_the_shells_start(monkeypatch):
    monkeypatch.setenv("CREW_GATE_START", "1000")
    monkeypatch.setattr(_promote_gate, "configured_seconds", lambda: None)
    assert _promote_gate.Clock().deadline == 1016
    monkeypatch.setattr(_promote_gate, "configured_seconds", lambda: 9.0)
    assert _promote_gate.Clock().deadline == 1009


@needs_bash
def test_the_configured_deadline_is_enforced_end_to_end(tmp_path):
    """A deadline shorter than one second leaves the policy-map listing no time:
    the gate blocks, naming the deadline, and does not deploy."""
    spec = next(c for c in corpus.CASES if c["name"] == "prod-with-every-precondition-met")
    root, short, full, base = corpus.build(tmp_path, spec)
    (root / ".crew" / "config.json").write_text(
        json.dumps({"promote": {"deadlineSeconds": 0.4}}), encoding="utf-8")
    proc = subprocess.run([_BASH, (_SCRIPTS / "promote-gate.sh").as_posix()],
                          input=corpus.payload(root, spec, short, full, base),
                          capture_output=True, env=_env(tmp_path, root), cwd=str(root),
                          check=False, timeout=170)
    err = _text(proc.stderr)
    assert proc.returncode == 2, err
    assert "inside the gate's deadline" in err, err
    assert not (root / ".crew" / ".deploy-in-flight").exists()


# --- 5. the allow fast path ----------------------------------------------------

_MAP = {"environments": {"prod": {"deploy": "deploy-prod", "rollback": "none",
                                  "rollbackReason": "fixture"}}}
_DISPATCH_MAP = {"environments": {"prod": {
    "deploy": "gh workflow run deploy.yml -f environment=prod",
    "rollback": "none", "rollbackReason": "fixture"}}}


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _repo(tmp_path, monkeypatch, doc):
    root = tmp_path / "fast"
    (root / ".crew").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "T")
    _git(root, "config", "core.autocrlf", "false")
    (root / ".crew" / "verify.json").write_bytes(json.dumps(doc, indent=2).encode())
    _git(root, "add", "-A", "-f")
    _git(root, "commit", "-q", "-m", "map")
    monkeypatch.chdir(root)
    monkeypatch.delenv("CREW_MAP_DIRTY", raising=False)
    monkeypatch.delenv("CREW_HEAD_MAP", raising=False)
    monkeypatch.setattr(_promote_gate, "configured_seconds", lambda: None)
    return root


def _gate(command):
    gate = _promote_gate.Gate()
    gate.cmd = command
    return gate


def test_the_fast_path_allows_an_unrelated_command_with_a_clean_map(tmp_path, monkeypatch):
    _repo(tmp_path, monkeypatch, _MAP)
    assert _gate("echo hi").provably_no_deploy() is True


def test_the_fast_path_allows_a_map_checked_out_with_crlf(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch, _MAP)
    path = root / ".crew" / "verify.json"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert _gate("echo hi").provably_no_deploy() is True


def test_the_fast_path_refuses_a_map_that_is_not_committed_as_is(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch, _MAP)
    edited = dict(_MAP, environments={"prod": dict(_MAP["environments"]["prod"], deploy="renamed")})
    (root / ".crew" / "verify.json").write_text(json.dumps(edited), encoding="utf-8")
    assert _gate("deploy-prod").provably_no_deploy() is False


def test_the_fast_path_refuses_a_map_with_an_added_line(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch, _MAP)
    with open(root / ".crew" / "verify.json", "a", encoding="utf-8") as handle:
        handle.write("\n")
    assert _gate("echo hi").provably_no_deploy() is False


def test_the_fast_path_refuses_a_command_the_map_declares(tmp_path, monkeypatch):
    _repo(tmp_path, monkeypatch, _MAP)
    assert _gate("deploy-prod --now").provably_no_deploy() is False


def test_the_fast_path_refuses_a_dispatch_of_a_declared_workflow(tmp_path, monkeypatch):
    _repo(tmp_path, monkeypatch, _DISPATCH_MAP)
    assert _gate("gh workflow run deploy.yml -f environment=prod").provably_no_deploy() is False
    # not a substring of the declared command, so only the dispatch reader can see it
    assert _gate("gh workflow run deploy.yml -f x=1 -f environment=prod").provably_no_deploy() is False
    # a declared workflow with an input that fits no environment is could-not-tell, not "nothing"
    assert _gate("gh workflow run deploy.yml -f environment=dev").provably_no_deploy() is False
    assert _gate("gh workflow run other.yml -f environment=prod").provably_no_deploy() is True


def test_the_fast_path_refuses_when_there_is_no_map(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch, _MAP)
    os.remove(root / ".crew" / "verify.json")
    assert _gate("echo hi").provably_no_deploy() is False


def test_the_fast_path_refuses_a_map_it_cannot_read(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch, _MAP)
    (root / ".crew" / "verify.json").write_text("{ nope", encoding="utf-8")
    assert _gate("echo hi").provably_no_deploy() is False


def test_committed_as_is_compares_git_blob_ids(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch, _MAP)
    blob = subprocess.run(["git", "rev-parse", "HEAD:./.crew/verify.json"], cwd=root, check=True,
                          capture_output=True, text=True).stdout.strip()
    assert _promote_gate.committed_as_is(blob) is True
    assert _promote_gate.committed_as_is("0" * len(blob)) is False


# --- the pieces ----------------------------------------------------------------

@pytest.mark.parametrize("doc,field,expected", [
    ({"tool_input": {"command": "a\r\nb\n\n"}}, ("tool_input", "command"), "a\nb"),
    ({"tool_input": {"command": None}}, ("tool_input", "command"), ""),
    ({"tool_input": {"command": False}}, ("tool_input", "command"), ""),
    ({"tool_input": {"command": 7}}, ("tool_input", "command"), "7"),
    ({"tool_input": "x"}, ("tool_input", "command"), ""),
    ({}, ("cwd",), ""),
    ({"cwd": "C:\\work\r"}, ("cwd",), "C:\\work"),
])
def test_the_payload_is_read_as_jq_read_it(doc, field, expected):
    assert _promote_gate.clean(_promote_gate.payload_field(doc, *field)) == expected


def test_resolve_dir_follows_cd_and_refuses_what_is_not_a_directory(tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "file.txt").write_text("x", encoding="utf-8")
    base = str(tmp_path)
    real = os.path.realpath
    assert _promote_gate.resolve_dir(base, "a") == real(tmp_path / "a")
    assert _promote_gate.resolve_dir(base, "a/b") == real(tmp_path / "a" / "b")
    assert _promote_gate.resolve_dir(base, "a/../a/b") == real(tmp_path / "a" / "b")
    assert _promote_gate.resolve_dir(base, str(tmp_path / "a")) == real(tmp_path / "a")
    assert _promote_gate.resolve_dir(base, "") == real(base)
    assert _promote_gate.resolve_dir(base, "nope") == ""
    assert _promote_gate.resolve_dir(base, "file.txt") == ""


def test_resolve_dir_expands_a_leading_tilde(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "w").mkdir()
    assert _promote_gate.resolve_dir("/", "~") == os.path.realpath(tmp_path)
    assert _promote_gate.resolve_dir("/", "~/w") == os.path.realpath(tmp_path / "w")


@pytest.mark.skipif(os.name != "nt", reason="MSYS drive paths only exist under Git Bash on Windows")
def test_native_turns_an_msys_drive_path_into_a_windows_one():
    assert _promote_gate.native("/c/work/x") == "C:/work/x"
    assert _promote_gate.native("/d") == "D:/"
    assert _promote_gate.native("C:/already") == "C:/already"
    assert _promote_gate.native("relative/x") == "relative/x"


def test_tree_asks_git_once_and_names_the_failing_field_when_it_cannot(tmp_path):
    repo = tmp_path / "unborn"
    repo.mkdir()
    _git(repo, "init", "-q")
    info = _promote_gate.Tree(str(repo))
    assert info.top and info.common, "a repository with no commit still has a top and a common dir"
    assert info.full == "" and info.short == "", "no commit at HEAD is its own answer"
    assert _promote_gate.Tree(str(tmp_path)).top == "", "not a repository"
    committed = tmp_path / "committed"
    committed.mkdir()
    _git(committed, "init", "-q")
    _git(committed, "-c", "user.email=t@example.invalid", "-c", "user.name=T", "commit", "-q",
         "--allow-empty", "-m", "x")
    got = _promote_gate.Tree(str(committed))
    assert len(got.full) == 40 and got.full.startswith(got.short) and len(got.short) >= 7


# --- a reader that raises --------------------------------------------------------

def test_a_dispatch_reader_that_raises_blocks(tmp_path, monkeypatch, capsys):
    """A reader that FAILS is never "nothing": the gate blocks (exit 2) and names it."""
    _repo(tmp_path, monkeypatch, _DISPATCH_MAP)
    import _promote_dispatch  # pylint: disable=import-outside-toplevel

    def boom(command, shell):
        raise RuntimeError("reader broke")
    monkeypatch.setattr(_promote_dispatch, "decide", boom)
    gate = _gate("gh workflow run deploy.yml -f environment=prod")
    with pytest.raises(_promote_gate.Stop) as stop:
        gate.add_dispatched([])
    assert stop.value.code == 2
    assert "_promote_dispatch.py failed" in capsys.readouterr().err


@needs_bash
@pytest.mark.parametrize("helper", ["_promote_dispatch.py", "_promote_tree.py", "_promote_github.py"])
def test_a_helper_that_ends_the_interpreter_is_never_an_allow(tmp_path, helper):
    """The helpers are imported now, so a broken or replaced one that calls
    sys.exit(0) must not end the whole gate with an allow nobody decided."""
    plugin = tmp_path / "plugin"
    scripts = plugin / "hooks" / "scripts"
    skip = shutil.ignore_patterns("_test", "__pycache__")
    shutil.copytree(_SCRIPTS, scripts, ignore=skip)
    graph = pathlib.Path("skills") / "crew-graph" / "scripts"
    shutil.copytree(_SCRIPTS.parents[1] / graph, plugin / graph, ignore=skip)
    (scripts / helper).write_text("raise SystemExit(0)\n", encoding="utf-8")
    spec = next(c for c in corpus.CASES if c["name"] == "prod-with-every-precondition-met")
    proc, root, _ = _run(tmp_path / "run", spec, scripts=scripts)
    assert proc.returncode == 2, _text(proc.stderr)
    assert not (root / ".crew" / ".deploy-in-flight").exists()
