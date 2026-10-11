"""crew_kimi_agent.py (L-0777): a crew subagent role run on the Kimi Code CLI,
read-only, with the KIMI UNAVAILABLE fallback the dispatcher agents rely on.

Every case runs a fake `kimi` (kimi_fixtures.fake_kimi_bin) against a
throwaway repo and a fixture KIMI_CODE_HOME under tmp_path, with a PATH that
cannot reach a real install. Nothing here calls the real Kimi CLI.

Three tables, matching the spec's acceptance checks:
  must-block  Kimi changed the tree (or it cannot be told): exit 8, the first
              line names it, and Kimi's answer is never relayed.
  must-allow  a read-only run: exit 0, `KIMI OK`, the answer relayed.
  fallback    Kimi must not or cannot run: exit 3, `KIMI UNAVAILABLE: <state>`,
              the tree untouched, no answer.
"""
import json
import os
import shutil
import subprocess
import sys
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
import crew_kimi_agent as cka
import crew_state
import kimi_probe
import review_run
from kimi_fixtures import LATE_WRITE_S, fake_kimi_bin, kimi_home
from review_fixtures import git, init_repo

_SCRIPT = os.path.join(context._ROOT, "hooks", "scripts", "crew_kimi_agent.py")  # pylint: disable=protected-access
_REAL_AGENTS = os.path.join(context._ROOT, "agents")  # pylint: disable=protected-access
ROLES = ("explorer", "researcher", "security", "reviewer")
KIMI_PIN = {"provider": "kimi", "model": "k3"}
ALL_PINNED = {"dev": {"roles": {"explorer": KIMI_PIN, "researcher": KIMI_PIN,
                                "security": KIMI_PIN}},
              "qa": {"roles": {"review": KIMI_PIN}}}
TASK = "Where is the seed file read?"


def _agents(tmp_path):
    """An agents dir holding every role with a marker, so the reviewer (whose
    real file is L-0778's) runs here too."""
    directory = tmp_path / "agents"
    directory.mkdir(exist_ok=True)
    for role in ROLES:
        (directory / f"{role}.md").write_text(
            f"---\nname: {role}\n---\nDispatch.\n\n{cka.MARKER}\n\nYou are the {role}.\n",
            encoding="utf-8", newline="\n")
    return directory


@pytest.fixture(name="repo")
def _repo(tmp_path):
    repo = init_repo(tmp_path / "r")
    (repo / ".gitignore").write_text(".idea/\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "ignore")
    return repo


def _configure(repo, cfg):
    (repo / ".crew").mkdir(exist_ok=True)
    (repo / ".crew" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    # The config is ignored in a real repo; here it is committed so the
    # fixture's tree is clean before each run and only Kimi's writes count.
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "config")


def _git_only_path():
    """The directory `git` resolves from, alone: the fixture repo needs git, and
    a hardcoded `/usr/bin` holds no git on Windows (WinError 2 in CI). A real
    `kimi` installed next to git would leak in, so that case is skipped rather
    than run against the real CLI."""
    found = shutil.which("git")
    assert found, "git is not on PATH"
    directory = os.path.dirname(found)
    if shutil.which("kimi", path=directory):
        pytest.skip(f"a real kimi sits next to git in {directory}")
    return directory


@pytest.fixture(name="kimi")
def _kimi(tmp_path, monkeypatch):
    """Fake kimi on a PATH that cannot reach a real install; returns a setter
    for the FAKE_KIMI_* knobs."""
    fakes = fake_kimi_bin(tmp_path / "bin")
    home = kimi_home(tmp_path / "kimi-home")
    monkeypatch.setenv("PATH", os.pathsep.join([str(fakes), _git_only_path()]))
    monkeypatch.setenv("KIMI_CODE_HOME", str(home))
    # The settle is real in the detached-descendant case, short everywhere else.
    monkeypatch.setattr(cka, "SETTLE_S", 0.05)
    for name in [k for k in os.environ if k.startswith("FAKE_KIMI_")]:
        monkeypatch.delenv(name)

    def knobs(**values):
        for key, value in values.items():
            monkeypatch.setenv(key, value)
    return knobs


def _call(repo, tmp_path, role="explorer", task=TASK, cfg=None, args=(), capsys=None):
    if not (repo / ".crew" / "config.json").exists():
        _configure(repo, ALL_PINNED if cfg is None else cfg)
    argv = ["--role", role, "--root", str(repo), "--agents-dir", str(_agents(tmp_path)),
            *args]
    parsed = _parser_args(argv)
    code = cka.run(parsed, task)
    out = capsys.readouterr().out if capsys else ""
    return code, out


def _parser_args(argv):
    import argparse  # pylint: disable=import-outside-toplevel
    parser = argparse.ArgumentParser()
    parser.add_argument("--role")
    parser.add_argument("--root")
    parser.add_argument("--authors", action="append", default=[])
    parser.add_argument("--diff-base", default=None)
    parser.add_argument("--timeout", type=int, default=cka.DEFAULT_TIMEOUT)
    parser.add_argument("--agents-dir")
    return parser.parse_args(argv)


def _status(repo):
    return git(repo, "status", "--porcelain", "--ignored")


# --- must-block: Kimi changed the tree --------------------------------------


@pytest.mark.parametrize("knob, value, named", [
    ("FAKE_KIMI_WRITES", "seed.txt", "seed.txt"),
    ("FAKE_KIMI_WRITES", "new-file.txt", "new-file.txt"),
    ("FAKE_KIMI_PUT", json.dumps({"seed.txt": "replaced\n"}), "seed.txt"),
])
def test_a_write_by_kimi_is_exit_8_and_no_answer(repo, tmp_path, kimi, capsys, knob, value,
                                                  named):
    kimi(**{knob: value})

    code, out = _call(repo, tmp_path, capsys=capsys)

    assert code == cka.EXIT_TREE
    first = out.splitlines()[0]
    assert first.startswith("KIMI CHANGED THE TREE:") and named in first
    assert "KIMI OK" not in out and "CLEAN" not in out


@pytest.mark.skipif(os.name == "nt", reason="chmod +x has no meaning here")
def test_a_chmod_by_kimi_is_exit_8(repo, tmp_path, kimi, capsys):
    kimi(FAKE_KIMI_CHMOD="seed.txt")

    code, out = _call(repo, tmp_path, capsys=capsys)

    assert code == cka.EXIT_TREE and "seed.txt" in out.splitlines()[0]


@pytest.mark.parametrize("git_argv", [
    [["add", "seed.txt"]],
    [["commit", "-qam", "kimi fixed it"]],
], ids=["staged", "committed"])
def test_a_staged_or_committed_change_by_kimi_is_exit_8(repo, tmp_path, kimi, capsys,
                                                        git_argv):
    kimi(FAKE_KIMI_WRITES="seed.txt", FAKE_KIMI_GIT=json.dumps(git_argv))

    code, out = _call(repo, tmp_path, capsys=capsys)

    assert code == cka.EXIT_TREE
    assert out.startswith("KIMI CHANGED THE TREE:")
    assert "KIMI OK" not in out


def test_a_probe_that_writes_is_exit_8_before_any_run(repo, tmp_path, kimi, capsys):
    dump = tmp_path / "dump.jsonl"
    kimi(FAKE_KIMI_PROBE_WRITE=str(repo / "probe-wrote.txt"), FAKE_KIMI_DUMP=str(dump))

    code, out = _call(repo, tmp_path, capsys=capsys)

    assert code == cka.EXIT_TREE
    assert out.startswith("KIMI CHANGED THE TREE: probe-wrote.txt")
    assert "during the kimi probe" in out
    calls = [json.loads(line) for line in dump.read_text(encoding="utf-8").splitlines()]
    assert len(calls) == 1, "the role must never run after a probe changed the tree"


def test_a_tree_that_cannot_be_fingerprinted_after_the_run_is_exit_8(
        repo, tmp_path, kimi, capsys, monkeypatch):
    kimi()
    real = review_run.tree_fingerprint
    calls = []

    def flaky(root, problems=None, _depth=0):
        calls.append(root)
        return None if len(calls) >= 3 else real(root, problems, _depth)
    monkeypatch.setattr(review_run, "tree_fingerprint", flaky)

    code, out = _call(repo, tmp_path, capsys=capsys)

    assert code == cka.EXIT_TREE and out.startswith("KIMI TREE UNKNOWN:")
    assert "KIMI OK" not in out


def test_a_process_kimi_leaves_behind_is_stopped_before_it_writes(repo, tmp_path, kimi,
                                                                  capsys):
    late = repo / "late.txt"
    kimi(FAKE_KIMI_LATE=str(late))

    code, out = _call(repo, tmp_path, capsys=capsys)
    time.sleep(LATE_WRITE_S + 1)

    assert not late.exists(), "a survivor wrote after the tree was checked"
    assert code == cka.EXIT_OK, out


# --- must-allow: a read-only run ---------------------------------------------


@pytest.mark.parametrize("role", ROLES)
def test_a_read_only_run_relays_the_answer(repo, tmp_path, kimi, capsys, role):
    kimi()
    before = _status(repo)

    code, out = _call(repo, tmp_path, role=role, args=("--authors", "claude"),
                      capsys=capsys)

    lines = out.splitlines()
    assert code == cka.EXIT_OK, out
    assert lines[0] == f"KIMI OK: {role} ran on kimi kimi-code/k3"
    assert "CLEAN" in lines[1:]
    assert _status(repo) == before


@pytest.mark.parametrize("path", ["graphify-out/graph.json", ".idea/workspace.xml"])
def test_graph_out_and_ignored_ide_writes_are_set_aside(repo, tmp_path, kimi, capsys,
                                                       path):
    kimi(FAKE_KIMI_WRITES=path)

    code, out = _call(repo, tmp_path, capsys=capsys)

    assert code == cka.EXIT_OK, out


def test_a_long_task_goes_by_file_with_the_scratch_dir_added(repo, tmp_path, kimi, capsys):
    dump = tmp_path / "dump.jsonl"
    kimi(FAKE_KIMI_DUMP=str(dump))

    code, out = _call(repo, tmp_path, task="x" * (review_run.INLINE_PROMPT_LIMIT + 10),
                      capsys=capsys)

    run_call = json.loads(dump.read_text(encoding="utf-8").splitlines()[-1])
    assert code == cka.EXIT_OK, out
    prompt = run_call["argv"][run_call["argv"].index("-p") + 1]
    assert prompt.startswith("Your complete instructions are in the file ")
    assert "--add-dir" in run_call["argv"]


# --- fallback: KIMI UNAVAILABLE ----------------------------------------------


@pytest.mark.parametrize("probe, state", [
    ("401", "not-authenticated"),
    ("quota:exceeded_current_quota_error", "rate-limited"),
    ("garbage", "unknown"),
])
def test_a_probe_that_is_not_ok_is_unavailable(repo, tmp_path, kimi, capsys, probe, state):
    kimi(FAKE_KIMI_PROBE=probe)
    before = _status(repo)

    code, out = _call(repo, tmp_path, capsys=capsys)

    assert code == cka.EXIT_UNAVAILABLE
    assert out.startswith(f"KIMI UNAVAILABLE: {state} - ")
    assert "CLEAN" not in out and _status(repo) == before


def test_no_kimi_on_path_is_not_installed(repo, tmp_path, kimi, capsys, monkeypatch):
    kimi()
    monkeypatch.setenv("PATH", _git_only_path())

    code, out = _call(repo, tmp_path, capsys=capsys)

    assert code == cka.EXIT_UNAVAILABLE and out.startswith("KIMI UNAVAILABLE: not-installed")


@pytest.mark.parametrize("mode", ["fail", "turnfail", "empty"])
def test_a_run_that_fails_is_unavailable(repo, tmp_path, kimi, capsys, mode):
    kimi(FAKE_KIMI_MODE=mode)

    code, out = _call(repo, tmp_path, capsys=capsys)

    assert code == cka.EXIT_UNAVAILABLE and out.startswith("KIMI UNAVAILABLE: failed - ")
    assert len(out.splitlines()) == 1, "an unavailable run relays no answer"


def test_a_run_that_times_out_is_unavailable(repo, tmp_path, kimi, capsys):
    kimi(FAKE_KIMI_MODE="hang")

    code, out = _call(repo, tmp_path, args=("--timeout", "3"), capsys=capsys)

    assert code == cka.EXIT_UNAVAILABLE and out.startswith("KIMI UNAVAILABLE: timed-out")


def test_a_secret_in_the_failure_is_redacted(repo, tmp_path, kimi, capsys):
    kimi(FAKE_KIMI_MODE="turnfail-secret")

    code, out = _call(repo, tmp_path, capsys=capsys)

    assert code == cka.EXIT_UNAVAILABLE
    assert "eyJhbGciOi" not in out and "[redacted]" in out


@pytest.mark.parametrize("cfg", [
    {},
    {"dev": {"roles": {"explorer": {"provider": "codex", "model": "gpt-6-astra"}}}},
], ids=["no-pin", "codex-pin"])
def test_a_role_not_pinned_to_kimi_is_not_routed(repo, tmp_path, kimi, capsys, cfg):
    dump = tmp_path / "dump.jsonl"
    kimi(FAKE_KIMI_DUMP=str(dump))

    code, out = _call(repo, tmp_path, cfg=cfg, capsys=capsys)

    assert code == cka.EXIT_UNAVAILABLE and out.startswith("KIMI UNAVAILABLE: not-routed")
    assert not dump.exists(), "nothing may be launched for a role that is not routed"


@pytest.mark.parametrize("role", ["security", "reviewer"])
def test_a_reviewing_role_on_kimi_authored_work_is_barred(repo, tmp_path, kimi, capsys,
                                                          role):
    dump = tmp_path / "dump.jsonl"
    kimi(FAKE_KIMI_DUMP=str(dump))

    code, out = _call(repo, tmp_path, role=role, args=("--authors", "kimi"), capsys=capsys)

    assert code == cka.EXIT_UNAVAILABLE and out.startswith("KIMI UNAVAILABLE: barred")
    assert "`kimi`" in out and not dump.exists()


def test_a_writer_role_is_never_barred_by_author(repo, tmp_path, kimi, capsys):
    kimi()

    code, out = _call(repo, tmp_path, role="explorer", args=("--authors", "kimi"),
                      capsys=capsys)

    assert code == cka.EXIT_OK, out


@pytest.mark.parametrize("role", ["security", "reviewer"])
def test_a_reviewing_role_with_no_author_family_is_author_unknown(
        repo, tmp_path, kimi, capsys, monkeypatch, role):
    kimi()
    monkeypatch.setattr(crew_state, "author_families",
                        lambda root, cfg, stale=False: (frozenset(), "config"))

    code, out = _call(repo, tmp_path, role=role, capsys=capsys)

    assert code == cka.EXIT_UNAVAILABLE
    assert out.startswith("KIMI UNAVAILABLE: author-unknown")


def test_the_author_set_unites_the_flag_and_the_record(repo, tmp_path, kimi, capsys,
                                                       monkeypatch):
    kimi()
    monkeypatch.setattr(crew_state, "author_families",
                        lambda root, cfg, stale=False: (frozenset({"kimi"}), "dispatch"))

    code, out = _call(repo, tmp_path, role="security", args=("--authors", "claude"),
                      capsys=capsys)

    assert code == cka.EXIT_UNAVAILABLE and out.startswith("KIMI UNAVAILABLE: barred")


def test_a_task_over_the_cap_is_too_large(repo, tmp_path, kimi, capsys):
    kimi()

    code, out = _call(repo, tmp_path, task="x" * (cka.TASK_CAP + 1), capsys=capsys)

    assert code == cka.EXIT_UNAVAILABLE and out.startswith("KIMI UNAVAILABLE: too-large")


# --- the launch -------------------------------------------------------------


@pytest.mark.parametrize("role", ROLES)
def test_the_launch_is_read_only_and_scrubbed(repo, tmp_path, kimi, capsys, monkeypatch,
                                              role):
    dump = tmp_path / "dump.jsonl"
    kimi(FAKE_KIMI_DUMP=str(dump))
    monkeypatch.setenv("KIMI_MODEL_OVERRIDE", "x")

    code, out = _call(repo, tmp_path, role=role, args=("--authors", "claude"),
                      capsys=capsys)

    assert code == cka.EXIT_OK, out
    run_call = json.loads(dump.read_text(encoding="utf-8").splitlines()[-1])
    argv = run_call["argv"]
    assert argv[argv.index("-m") + 1] == "kimi-code/k3"
    assert argv[argv.index("--output-format") + 1] == "stream-json"
    tools = ", ".join(cka.ROLE_TOOLS[role])
    assert f"tools: [{tools}]\n" in run_call["agent_file"]
    assert "disallowedTools: [Write, Edit, Bash]\n" in run_call["agent_file"]
    assert run_call["skills"] == []
    assert run_call["stdin"] == ""
    assert "KIMI_MODEL_OVERRIDE" not in run_call["env"]
    assert run_call["env"].get("KIMI_CODE_NO_AUTO_UPDATE") == "1"
    assert os.path.realpath(run_call["cwd"]) == os.path.realpath(repo)
    assert not os.path.exists(argv[argv.index("--agent-file") + 1]), "scratch left behind"


def test_no_role_may_use_a_shell_or_write_on_kimi():
    for role, tools in cka.ROLE_TOOLS.items():
        assert not set(tools) & {"Bash", "Write", "Edit", "MultiEdit", "NotebookEdit"}, role
    assert set(cka.DISALLOWED) == {"Write", "Edit", "Bash"}


def test_the_review_round_agent_file_is_unchanged(tmp_path):
    with open(kimi_probe.write_agent_file(str(tmp_path)), encoding="utf-8") as fh:
        text = fh.read()

    assert text == ("---\nname: crew-reviewer\n"
                    "description: Read-only code reviewer for crew's review round.\n"
                    "tools: [Read, Grep, Glob]\ndisallowedTools: [Write, Edit, Bash]\n---\n"
                    "You are a read-only code reviewer. Follow the user's message exactly; "
                    "never modify files.\n")


# --- the agent files ----------------------------------------------------------


@pytest.mark.parametrize("role", ["explorer", "researcher", "security"])
def test_each_dispatcher_carries_its_instructions_after_the_marker(role):
    instructions = cka.role_instructions(role, _REAL_AGENTS)

    assert instructions and len(instructions) > 200
    with open(os.path.join(_REAL_AGENTS, f"{role}.md"), encoding="utf-8") as fh:
        head = fh.read().split(cka.MARKER, 1)[0]
    assert "crew_kimi_agent.py" in head and f"--role {role}" in head
    assert "KIMI UNAVAILABLE" in head and "KIMI CHANGED THE TREE" in head


def test_a_file_with_no_marker_or_two_is_refused(tmp_path):
    (tmp_path / "none.md").write_text("no marker\n", encoding="utf-8")
    (tmp_path / "two.md").write_text(f"{cka.MARKER}\na\n{cka.MARKER}\nb\n", encoding="utf-8")
    (tmp_path / "empty.md").write_text(f"x\n{cka.MARKER}\n\n", encoding="utf-8")

    assert [cka.role_instructions(n, str(tmp_path)) for n in ("none", "two", "empty")] == [
        None, None, None]


# --- the script end to end ----------------------------------------------------


def test_the_cli_reads_the_task_from_stdin(repo, tmp_path, kimi):
    kimi()
    _configure(repo, ALL_PINNED)
    env = dict(os.environ, HOME=str(tmp_path / "home"))

    done = subprocess.run(
        [sys.executable, _SCRIPT, "--role", "explorer", "--root", str(repo),
         "--agents-dir", str(_agents(tmp_path))],
        input=TASK, capture_output=True, text=True, env=env, check=False, timeout=120)

    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.startswith("KIMI OK: explorer ran on kimi")


def test_the_cli_refuses_an_empty_task(repo, tmp_path):
    done = subprocess.run(
        [sys.executable, _SCRIPT, "--role", "explorer", "--root", str(repo)],
        input="  \n", capture_output=True, text=True, check=False, timeout=60,
        env=dict(os.environ, HOME=str(tmp_path / "home")))

    assert done.returncode == cka.EXIT_USAGE and "no task" in done.stdout


def test_the_cli_refuses_a_task_that_is_not_utf8(repo, tmp_path):
    done = subprocess.run(
        [sys.executable, _SCRIPT, "--role", "explorer", "--root", str(repo),
         "--agents-dir", str(_agents(tmp_path))],
        input=b"caf\xe9 where?", capture_output=True, env=dict(os.environ), check=False,
        timeout=120)

    assert done.returncode == cka.EXIT_USAGE
    assert done.stdout.decode("utf-8").startswith("crew-kimi-agent: the task on stdin is not UTF-8")


def test_a_non_ascii_answer_reaches_a_cp1252_stdout_intact(repo, tmp_path, kimi):
    kimi(FAKE_KIMI_ANSWER="résumé → seed.txt")
    _configure(repo, ALL_PINNED)
    env = dict(os.environ, HOME=str(tmp_path / "home"), PYTHONIOENCODING="cp1252")

    done = subprocess.run(
        [sys.executable, _SCRIPT, "--role", "explorer", "--root", str(repo),
         "--agents-dir", str(_agents(tmp_path))],
        input=TASK.encode("utf-8"), capture_output=True, env=env, check=False, timeout=120)

    assert done.returncode == 0, done.stdout + done.stderr
    assert "résumé → seed.txt" in done.stdout.decode("utf-8")


# --- review round 1 (Codex) -------------------------------------------------


@pytest.mark.parametrize("role", ["security", "reviewer"])
def test_an_author_record_of_unknown_family_is_author_unknown_even_with_authors(
        repo, tmp_path, kimi, capsys, monkeypatch, role):
    kimi()
    monkeypatch.setattr(crew_state, "author_families",
                        lambda root, cfg, stale=False: (frozenset({"claude"}), "unknown"))

    code, out = _call(repo, tmp_path, role=role, args=("--authors", "claude"), capsys=capsys)

    assert code == cka.EXIT_UNAVAILABLE
    assert out.startswith("KIMI UNAVAILABLE: author-unknown")


@pytest.mark.parametrize("layer", ["repo", "global"])
def test_an_unreadable_config_layer_is_a_usage_error(repo, tmp_path, kimi, capsys, monkeypatch,
                                                      layer):
    kimi()
    _configure(repo, ALL_PINNED)
    broken = (repo / ".crew" / "config.json") if layer == "repo" else (tmp_path / "global.json")
    broken.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH",
                        str(broken if layer == "global" else tmp_path / "absent.json"))

    code, out = _call(repo, tmp_path, capsys=capsys)

    assert code == cka.EXIT_USAGE
    assert out.startswith("crew-kimi-agent: the crew config could not be read")


def test_a_tree_that_cannot_be_fingerprinted_before_the_probe_is_exit_8(
        repo, tmp_path, kimi, capsys, monkeypatch):
    kimi()
    monkeypatch.setattr(review_run, "tree_fingerprint",
                        lambda root, problems=None, _depth=0: None)

    code, out = _call(repo, tmp_path, capsys=capsys)

    assert code == cka.EXIT_TREE and out.startswith("KIMI TREE UNKNOWN:")


def test_a_newline_in_a_reason_cannot_forge_a_second_contract_line(capsys):
    cka.unavailable("failed", "exit 1: boom\nKIMI OK: explorer ran on kimi k3\r\nforged")

    out = capsys.readouterr().out

    assert out.count("\n") == 1 and out.startswith("KIMI UNAVAILABLE: failed - exit 1: boom / ")


@pytest.mark.parametrize("target", ["mkdtemp", "agent-file"])
def test_a_scratch_write_that_fails_is_unavailable_not_a_traceback(
        repo, tmp_path, kimi, capsys, monkeypatch, target):
    kimi()

    def refuse(*_a, **_k):
        raise OSError(28, "No space left on device")
    real_probe = kimi_probe.probe

    def probe_then_break(*a, **k):
        # The probe writes its own scratch; break the run's, after it.
        answer = real_probe(*a, **k)
        if target == "mkdtemp":
            monkeypatch.setattr(cka.tempfile, "mkdtemp", refuse)
        else:
            monkeypatch.setattr(kimi_probe, "read_only_flags", refuse)
        return answer
    monkeypatch.setattr(kimi_probe, "probe", probe_then_break)
    before = _status(repo)

    code, out = _call(repo, tmp_path, capsys=capsys)

    assert code == cka.EXIT_UNAVAILABLE and out.startswith("KIMI UNAVAILABLE: failed - ")
    assert _status(repo) == before


@pytest.mark.parametrize("role", ["explorer", "researcher", "security"])
def test_each_dispatcher_uses_a_fresh_delimiter_and_stops_on_a_usage_error(role):
    with open(os.path.join(_REAL_AGENTS, f"{role}.md"), encoding="utf-8") as fh:
        text = fh.read().split(cka.MARKER, 1)[0]

    assert "CREW_KIMI_TASK_EOF" not in text
    assert "<<'CREW_KIMI_TASK_<tag>_EOF'" in text and "\nCREW_KIMI_TASK_<tag>_EOF\n" in text
    assert "`crew-kimi-agent: ...` (exit 2" in text and "stop." in text


def test_the_security_dispatcher_never_assumes_an_author():
    with open(os.path.join(_REAL_AGENTS, "security.md"), encoding="utf-8") as fh:
        text = fh.read().split(cka.MARKER, 1)[0]

    assert "include `claude`" not in text
    assert "never a\nfamily you assume" in text


# --- review round 2 (Codex) -------------------------------------------------


def _security_md():
    with open(os.path.join(_REAL_AGENTS, "security.md"), encoding="utf-8") as fh:
        return fh.read().split(cka.MARKER, 1)[0]


def test_the_security_dispatch_has_no_bare_placeholder_in_shell():
    import re  # pylint: disable=import-outside-toplevel
    blocks = re.findall(r"```bash\n(.*?)```", _security_md(), re.S)

    assert blocks
    for block in blocks:
        shell = re.sub(r"<<'(CREW_KIMI_TASK_<tag>_EOF)'.*?\n\1\n", "", block, flags=re.S)
        assert not re.search(r"(?<!')<[a-z]+>", shell), shell
    assert "--diff-base '<base>'" in _security_md()


def _dirty(repo):
    (repo / "seed.txt").write_text("unstaged edit\n", encoding="utf-8")
    (repo / "staged.txt").write_text("staged file\n", encoding="utf-8")
    git(repo, "add", "staged.txt")
    (repo / "untracked.txt").write_text("untracked file\n", encoding="utf-8")


def test_the_bundle_carries_staged_unstaged_and_untracked_changes(repo):
    base = git(repo, "rev-parse", "HEAD")
    _dirty(repo)

    text = cka.diff_bundle(str(repo), base)

    assert "unstaged edit" in text and "staged file" in text and "untracked file" in text


def test_the_security_dispatch_sends_the_bundle_to_kimi(repo, tmp_path, kimi, capsys):
    dump = tmp_path / "dump.jsonl"
    kimi(FAKE_KIMI_DUMP=str(dump))
    _configure(repo, ALL_PINNED)
    base = git(repo, "rev-parse", "HEAD")
    _dirty(repo)

    code, out = _call(repo, tmp_path, role="security",
                      args=("--authors", "claude", "--diff-base", base), capsys=capsys)

    argv = json.loads(dump.read_text(encoding="utf-8").splitlines()[-1])["argv"]
    prompt = argv[argv.index("-p") + 1]
    assert code == cka.EXIT_OK, out
    assert "unstaged edit" in prompt and "staged file" in prompt and "untracked file" in prompt


@pytest.mark.parametrize("base, why", [
    ("-p", "is not a plain commit or ref"),
    ("main;touch x", "is not a plain commit or ref"),
    ("a b", "is not a plain commit or ref"),
    ("no-such-ref", "the bundle could not be built"),
])
def test_a_diff_base_that_is_not_a_plain_ref_is_a_usage_error(repo, tmp_path, kimi, capsys,
                                                               base, why):
    kimi()

    code, out = _call(repo, tmp_path, role="security",
                      args=("--authors", "claude", f"--diff-base={base}"), capsys=capsys)

    assert code == cka.EXIT_USAGE and out.startswith("crew-kimi-agent: --diff-base")
    assert why in out


@pytest.mark.parametrize("name", ["Kimi", "KIMI", "kimi-k3", "k3", "moonshot/Kimi-for-coding"])
def test_an_author_name_is_normalised_before_the_guard(repo, tmp_path, kimi, capsys, name):
    kimi()

    code, out = _call(repo, tmp_path, role="security", args=("--authors", name),
                      capsys=capsys)

    assert code == cka.EXIT_UNAVAILABLE and out.startswith("KIMI UNAVAILABLE: barred")


@pytest.mark.parametrize("name", ["123", "--", "?"])
def test_an_author_name_that_names_no_family_is_a_usage_error(repo, tmp_path, kimi, capsys,
                                                                name):
    kimi()

    code, out = _call(repo, tmp_path, role="security", args=(f"--authors={name}",),
                      capsys=capsys)

    assert code == cka.EXIT_USAGE and "names no model family" in out


def test_a_detached_descendant_that_writes_within_the_settle_is_exit_8(
        repo, tmp_path, kimi, capsys, monkeypatch):
    kimi(FAKE_KIMI_DETACHED=str(repo / "seed.txt"), FAKE_KIMI_DETACHED_S="0.3")
    monkeypatch.setattr(cka, "SETTLE_S", 3.0)

    code, out = _call(repo, tmp_path, capsys=capsys)

    assert code == cka.EXIT_TREE and out.startswith("KIMI CHANGED THE TREE:")
    assert "KIMI OK" not in out


@pytest.mark.parametrize("role", ["security", "reviewer"])
def test_an_unpinned_reviewing_role_is_not_routed_before_any_author_check(
        repo, tmp_path, kimi, capsys, monkeypatch, role):
    kimi()
    monkeypatch.setattr(crew_state, "author_families",
                        lambda root, cfg, stale=False: (frozenset(), "config"))

    code, out = _call(repo, tmp_path, role=role, cfg={}, capsys=capsys)

    assert code == cka.EXIT_UNAVAILABLE and out.startswith("KIMI UNAVAILABLE: not-routed")


def test_a_pin_of_the_wrong_type_is_a_usage_error(repo, tmp_path, kimi, capsys):
    kimi()

    code, out = _call(repo, tmp_path, cfg={"dev": {"roles": {"explorer": {"provider": []}}}},
                      capsys=capsys)

    assert code == cka.EXIT_USAGE and out.startswith("crew-kimi-agent: the crew config could not")


def test_an_oversized_stdin_is_too_large_without_reading_it_all(repo, tmp_path):
    big = b"x" * (cka.STDIN_LIMIT + 10)

    done = subprocess.run(
        [sys.executable, _SCRIPT, "--role", "explorer", "--root", str(repo),
         "--agents-dir", str(_agents(tmp_path))],
        input=big, capture_output=True, env=dict(os.environ, HOME=str(tmp_path / "home")),
        check=False, timeout=120)

    assert done.returncode == cka.EXIT_UNAVAILABLE
    assert done.stdout.decode("utf-8").startswith(
        f"KIMI UNAVAILABLE: too-large - the task on stdin is over {cka.STDIN_LIMIT} bytes")
