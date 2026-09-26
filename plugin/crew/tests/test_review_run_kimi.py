"""review_run.py --provider kimi (T-0028): probe before reserve, a read-only
agent file, the stream-json parse, and the working-tree fingerprint.

Every case runs a fake `kimi` (review_fixtures.fake_kimi_bin) against a
throwaway repo and a fixture KIMI_CODE_HOME under tmp_path; the ledger lands in
THAT repo's git-common-dir. Nothing here calls the real Kimi CLI.
"""
import json
import os
import subprocess
import sys

import pytest
import yaml

import context  # noqa: F401  pylint: disable=unused-import
import kimi_probe
import review_ledger as rl
import review_run
from review_fixtures import env_with_path, fake_kimi_bin, git, init_repo, kimi_home

_SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access
_RUN = os.path.join(_SCRIPTS, "review_run.py")
_PATCH = os.path.join(_SCRIPTS, "review_patch.py")


@pytest.fixture(name="repo")
def _repo(tmp_path):
    repo = init_repo(tmp_path / "r")
    (repo / "change.txt").write_text("change\n", encoding="utf-8")
    return repo


def _bundle(repo, scratch, prompt=None):
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True,
                          text=True, check=True).stdout.strip()
    scratch.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, _PATCH, "--root", str(repo), "--base", base,
                    "--out", str(scratch / "diff.txt"),
                    "--manifest", str(scratch / "manifest.json")],
                   check=True, capture_output=True, stdin=subprocess.DEVNULL)
    names = " ".join(p["name"] for p in json.loads(
        (scratch / "manifest.json").read_text(encoding="utf-8"))["parts"])
    (scratch / "prompt.txt").write_text(prompt or f"Review. {names}", encoding="utf-8",
                                        newline="\n")


def _run(repo, tmp_path, probe="ok", mode="clean", model="k3", **env_extra):
    scratch, work = tmp_path / "scratch", tmp_path / "work"
    if not (scratch / "prompt.txt").exists():
        _bundle(repo, scratch)
    fakes = fake_kimi_bin(tmp_path / "bin")
    home = kimi_home(tmp_path / "kimi-home")
    env = env_with_path(fakes, FAKE_KIMI_PROBE=probe, FAKE_KIMI_MODE=mode,
                        KIMI_CODE_HOME=str(home), **env_extra)
    result = subprocess.run(
        [sys.executable, _RUN, "--root", str(repo), "--ticket", "T1", "--scratch",
         str(scratch), "--provider", "kimi", "--model", model, "--work-dir", str(work)],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False, env=env,
        timeout=120)
    review_path = work / "review.json"
    review = json.loads(review_path.read_text(encoding="utf-8")) \
        if review_path.exists() else None
    return result, review


def test_run_kimi_quota_spends_no_round(repo, tmp_path):
    result, review = _run(repo, tmp_path, probe="quota:exceeded_current_quota_error")

    assert result.returncode == 2 and "rate-limited" in result.stderr
    assert (rl.status(str(repo), "T1")["rounds"], review) == ([], None)


def test_run_kimi_not_authenticated_spends_no_round(repo, tmp_path):
    result, _ = _run(repo, tmp_path, probe="401")

    assert result.returncode == 2 and "not-authenticated" in result.stderr
    assert rl.status(str(repo), "T1")["rounds"] == []


def test_run_kimi_unknown_spends_no_round(repo, tmp_path):
    result, _ = _run(repo, tmp_path, probe="garbage")

    assert result.returncode == 2 and "unknown" in result.stderr
    assert rl.status(str(repo), "T1")["rounds"] == []


def test_run_kimi_not_installed_spends_no_round(repo, tmp_path):
    scratch = tmp_path / "scratch"
    _bundle(repo, scratch)
    env = dict(os.environ, PATH=os.path.dirname(sys.executable),
               KIMI_CODE_HOME=str(kimi_home(tmp_path / "kimi-home")))

    result = subprocess.run(
        [sys.executable, _RUN, "--root", str(repo), "--ticket", "T1", "--scratch",
         str(scratch), "--provider", "kimi", "--model", "k3"],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False, env=env,
        timeout=120)

    assert result.returncode == 2 and "not-installed" in result.stderr
    assert rl.status(str(repo), "T1")["rounds"] == []


def test_run_kimi_clean(repo, tmp_path):
    result, review = _run(repo, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert (review["verdict"], review["provider"], review["model"],
            review["model_family"]) == ("CLEAN", "kimi", "k3", "kimi")


def test_run_kimi_findings(repo, tmp_path):
    result, review = _run(repo, tmp_path, mode="findings")

    assert (result.returncode, review["verdict"]) == (1, "FINDINGS")


def test_run_kimi_failed_turn_is_incomplete_at_exit_0(repo, tmp_path):
    result, review = _run(repo, tmp_path, mode="turnfail")

    assert (result.returncode, review["verdict"], review["exit_code"]) == (3, "INCOMPLETE", 0)
    assert any(r.startswith("kimi: ") for r in review["reasons"])


def test_run_kimi_tree_change_is_incomplete(repo, tmp_path):
    result, review = _run(repo, tmp_path, mode="write")

    assert (result.returncode, review["verdict"]) == (3, "INCOMPLETE")
    assert any("working tree changed" in r for r in review["reasons"])


def test_run_kimi_argv_and_env(repo, tmp_path):
    dump = tmp_path / "dump.jsonl"
    scratch = tmp_path / "scratch"

    _run(repo, tmp_path, FAKE_KIMI_DUMP=str(dump), KIMI_CODE_INFINITE_RETRY="1",
         KIMI_MODEL_THINKING_EFFORT="max")
    calls = [json.loads(line) for line in dump.read_text(encoding="utf-8").splitlines()]

    probe, review = calls
    argv = review["argv"]
    assert probe["argv"][:2] == ["-p", "Reply with exactly: PROBE_OK"]
    assert argv[argv.index("-m") + 1] == "kimi-code/k3"
    assert argv[argv.index("--output-format") + 1] == "stream-json"
    assert argv[argv.index("--agent-file") + 1] == str(scratch / "kimi-reviewer.md")
    assert argv[argv.index("--skills-dir") + 1] == str(scratch / "kimi-no-skills")
    assert os.listdir(scratch / "kimi-no-skills") == []
    for call in calls:
        assert call["stdin"] == ""
        assert not [k for k in call["env"]
                    if k == "KIMI_CODE_INFINITE_RETRY" or k.startswith("KIMI_MODEL_")]


@pytest.mark.parametrize("size", ["inline", "over-limit"])
def test_kimi_prompt_argument_is_byte_identical_to_codex(repo, tmp_path, size):
    scratch = tmp_path / "scratch"
    _bundle(repo, scratch)
    if size == "over-limit":
        text = (scratch / "prompt.txt").read_text(encoding="utf-8")
        (scratch / "prompt.txt").write_text(
            text + "\n" + "x" * (review_run.INLINE_PROMPT_LIMIT + 1), encoding="utf-8",
            newline="\n")
    dump = tmp_path / "dump.jsonl"

    _run(repo, tmp_path, FAKE_KIMI_DUMP=str(dump))
    argv = json.loads(dump.read_text(encoding="utf-8").splitlines()[-1])["argv"]
    codex = review_run.command_for("codex", "codex", str(repo),
                                   review_run.prompt_argument(str(scratch / "prompt.txt")),
                                   "", "")

    assert argv[argv.index("-p") + 1] == codex[-1]


def test_kimi_agent_file_is_read_only(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "prompt.txt").write_text("Review this.\nREAD every part.\n", encoding="utf-8")

    path = kimi_probe.write_agent_file(str(scratch))
    text = open(path, encoding="utf-8").read()  # pylint: disable=consider-using-with
    front = yaml.safe_load(text.split("---\n")[1])
    body = text.split("---\n", 2)[2]

    assert (front["tools"], front["disallowedTools"]) == (
        ["Read", "Grep", "Glob"], ["Write", "Edit", "Bash"])
    assert not [line for line in ("Review this.", "READ every part.") if line in body]


def test_tree_fingerprint_ignores_work_and_sees_an_edit(repo):
    before = review_run.tree_fingerprint(str(repo))
    (repo / ".work").mkdir(exist_ok=True)
    (repo / ".work" / "note.txt").write_text("scratch\n", encoding="utf-8")
    unchanged = review_run.tree_fingerprint(str(repo))
    (repo / "seed.txt").write_text("edited\n", encoding="utf-8")

    assert before == unchanged != review_run.tree_fingerprint(str(repo))


def test_tree_fingerprint_sees_a_committed_edit(repo):
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True, capture_output=True)
    before = review_run.tree_fingerprint(str(repo))
    (repo / "seed.txt").write_text("edited\n", encoding="utf-8")
    subprocess.run(["git", "commit", "-qam", "reviewer fixed it"], cwd=repo, check=True,
                   capture_output=True)

    assert review_run.tree_fingerprint(str(repo)) != before


def test_tree_fingerprint_outside_a_repository_is_none(tmp_path):
    assert review_run.tree_fingerprint(str(tmp_path)) is None


def test_run_kimi_unfingerprintable_tree_is_incomplete(repo, tmp_path, monkeypatch, capsys):
    """"Could not tell" whether the reviewer wrote must never read as "it
    did not": an AFTER fingerprint that failed makes the round INCOMPLETE. (A
    failed BEFORE fingerprint stops earlier, spending nothing - round 2.)"""
    scratch, work = tmp_path / "scratch", tmp_path / "work"
    _bundle(repo, scratch)
    fakes = fake_kimi_bin(tmp_path / "bin")
    monkeypatch.setenv("PATH", str(fakes) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("KIMI_CODE_HOME", str(kimi_home(tmp_path / "kimi-home")))
    real, taken = review_run.tree_fingerprint, []

    def fingerprint(root, problems=None):
        taken.append(root)
        return real(root, problems) if len(taken) <= 2 else None

    monkeypatch.setattr(review_run, "tree_fingerprint", fingerprint)

    code = review_run.main(["--root", str(repo), "--ticket", "T1", "--scratch", str(scratch),
                            "--provider", "kimi", "--model", "k3", "--work-dir", str(work)])
    review = json.loads((work / "review.json").read_text(encoding="utf-8"))
    capsys.readouterr()

    assert (code, review["verdict"]) == (3, "INCOMPLETE")
    assert any("could not be fingerprinted" in r for r in review["reasons"])


# --- round 1 FIX review_run.py:179: untracked and ignored contents --------------


def _ignored_repo(repo):
    (repo / ".gitignore").write_text(".crew/config.json\ncache/\n", encoding="utf-8")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-qm", "ignore")
    (repo / ".crew").mkdir()
    (repo / ".crew" / "config.json").write_text('{"a": 1}\n', encoding="utf-8")
    (repo / "cache").mkdir()
    (repo / "cache" / "old.bin").write_text("old\n", encoding="utf-8")
    (repo / "u.py").write_text("x = 1\n", encoding="utf-8")
    return repo


def _edit_untracked(repo):
    (repo / "u.py").write_text("x = 2\n", encoding="utf-8")


def _edit_ignored(repo):
    (repo / ".crew" / "config.json").write_text('{"a": 2}\n', encoding="utf-8")


def _new_file_in_ignored_dir(repo):
    (repo / "cache" / "new.bin").write_text("new\n", encoding="utf-8")


def _delete_untracked(repo):
    (repo / "u.py").unlink()


def _stage_untracked(repo):
    git(repo, "add", "u.py")


def _restage_under_the_same_status(repo):
    """Status stays `MM` and the worktree bytes stay the same; only what is
    staged changes -- the case the per-path entries cannot see."""
    (repo / "seed.txt").write_text("staged by the reviewer\n", encoding="utf-8")
    git(repo, "add", "seed.txt")
    (repo / "seed.txt").write_text("worktree\n", encoding="utf-8")


@pytest.mark.parametrize("edit", [_edit_untracked, _edit_ignored, _new_file_in_ignored_dir,
                                  _delete_untracked, _stage_untracked,
                                  _restage_under_the_same_status])
def test_tree_fingerprint_sees_untracked_and_ignored_contents(repo, edit):
    """Round 1: hashing only the porcelain LINE of an already-untracked file,
    and skipping ignored files, let an edit to either leave before == after."""
    _ignored_repo(repo)
    (repo / "seed.txt").write_text("staged\n", encoding="utf-8")
    git(repo, "add", "seed.txt")
    (repo / "seed.txt").write_text("worktree\n", encoding="utf-8")
    before = review_run.tree_fingerprint(str(repo))

    edit(repo)

    assert review_run.tree_fingerprint(str(repo)) != before


@pytest.mark.parametrize("failure", [OSError("git vanished"),
                                     review_run.subprocess.TimeoutExpired("git", 1)])
def test_tree_fingerprint_git_that_fails_to_run_is_none(repo, monkeypatch, failure):
    """Round 1 NIT: an OSError or a hung git must be "could not tell", never
    a crash or a hang after the round is reserved."""
    def boom(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(review_run.crew_common, "git_out", lambda *_a: "0" * 40)
    monkeypatch.setattr(review_run.subprocess, "run", boom)

    assert review_run.tree_fingerprint(str(repo)) is None


# --- round 1 FIX review_run.py:464: a background graph rebuild ------------------


def _graph_repo(repo):
    (repo / ".gitignore").write_text("graphify-out/cache/\n", encoding="utf-8")
    (repo / "graphify-out").mkdir()
    (repo / "graphify-out" / "graph.json").write_text("{}\n", encoding="utf-8")
    git(repo, "add", ".gitignore", "graphify-out")
    git(repo, "commit", "-qm", "graph")
    return repo


def test_run_kimi_graph_rebuild_during_the_review_is_not_the_reviewers(repo, tmp_path):
    """graphify's post-commit rebuild rewrites graph.json and its cache in the
    background; that must not spoil and spend the round."""
    _graph_repo(repo)

    result, review = _run(repo, tmp_path, FAKE_KIMI_WRITES="graphify-out/graph.json,"
                                                           "graphify-out/cache/ast.json")

    assert (result.returncode, review["verdict"]) == (0, "CLEAN"), review["reasons"]
    assert "graphify-out/graph.json" in result.stderr


@pytest.mark.parametrize("writes,named", [
    ("graphify-out/graph.json,seed.txt", "seed.txt"),
    ("graphify-outX/graph.json", "graphify-outX/graph.json"),
])
def test_run_kimi_a_write_beside_the_graph_is_still_incomplete(repo, tmp_path, writes, named):
    _graph_repo(repo)

    result, review = _run(repo, tmp_path, FAKE_KIMI_WRITES=writes)

    assert (result.returncode, review["verdict"]) == (3, "INCOMPLETE")
    reason = next(r for r in review["reasons"] if "working tree changed" in r)
    assert named in reason and "graphify-out/graph.json" not in reason.replace(named, "")


def test_run_kimi_honours_a_configured_graph_out(repo, tmp_path):
    (repo / ".crew").mkdir()
    (repo / ".crew" / "config.json").write_text('{"graph": {"out": "docs/graph"}}\n',
                                                encoding="utf-8")
    git(repo, "add", ".crew")
    git(repo, "commit", "-qm", "cfg")

    result, review = _run(repo, tmp_path, FAKE_KIMI_WRITES="docs/graph/graph.json")

    assert (result.returncode, review["verdict"]) == (0, "CLEAN"), review["reasons"]


# --- round 1 FIX kimi_probe.py:219: the probe is watched and read-only ---------


def test_run_kimi_probe_is_read_only_and_runs_outside_the_repo(repo, tmp_path):
    dump = tmp_path / "dump.jsonl"

    _run(repo, tmp_path, FAKE_KIMI_DUMP=str(dump))
    probe = json.loads(dump.read_text(encoding="utf-8").splitlines()[0])
    front = yaml.safe_load(probe["agent_file"].split("---\n")[1])

    assert (front["tools"], front["disallowedTools"], probe["skills"]) == (
        ["Read", "Grep", "Glob"], ["Write", "Edit", "Bash"], [])
    assert os.path.realpath(probe["cwd"]) != os.path.realpath(repo)


def test_run_kimi_probe_that_writes_the_tree_spends_no_round(repo, tmp_path):
    """The `before` fingerprint is taken BEFORE the probe, so a probe call
    that wrote into the repository is seen -- and refused before any round is
    reserved."""
    result, review = _run(repo, tmp_path, FAKE_KIMI_PROBE_WRITE=str(repo / "seed.txt"))

    assert (result.returncode, review) == (2, None)
    assert "seed.txt" in result.stderr
    assert rl.status(str(repo), "T1")["rounds"] == []


# --- round 1 NITs ------------------------------------------------------------------


def test_run_kimi_stream_error_is_redacted_in_the_reasons(repo, tmp_path):
    result, review = _run(repo, tmp_path, mode="turnfail-secret")

    assert review["verdict"] == "INCOMPLETE"
    assert "eyJzdWIiOi" not in json.dumps(review["reasons"]) + result.stdout


@pytest.mark.parametrize("model,alias", [("", "kimi-code/kimi-for-coding"),
                                         ("k3", "kimi-code/k3")])
def test_run_kimi_records_the_alias_it_launched(repo, tmp_path, model, alias):
    _result, review = _run(repo, tmp_path, model=model)

    assert (review["model"], review["model_launched"]) == (model or None, alias)


def test_run_kimi_with_the_budget_spent_spends_no_probe_request(repo, tmp_path):
    for _ in range(rl.BUDGET):
        rl.reserve(str(repo), "T1", "kimi", "k3")
    dump = tmp_path / "dump.jsonl"

    result, _review = _run(repo, tmp_path, FAKE_KIMI_DUMP=str(dump))

    assert (result.returncode, dump.exists()) == (4, False)


def test_run_kimi_probes_after_the_reservation_when_the_status_was_stale(
        repo, tmp_path, monkeypatch, capsys):
    """The neighbour of skipping the probe on a spent budget: the status read
    is unlocked, so a round can still be granted. The probe then runs after the
    reservation, and a failing one makes the round INCOMPLETE rather than
    launching an unprobed reviewer."""
    scratch, work = tmp_path / "scratch", tmp_path / "work"
    _bundle(repo, scratch)
    fakes = fake_kimi_bin(tmp_path / "bin")
    monkeypatch.setenv("PATH", str(fakes) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("KIMI_CODE_HOME", str(kimi_home(tmp_path / "kimi-home")))
    monkeypatch.setenv("FAKE_KIMI_PROBE", "quota:exceeded_current_quota_error")
    monkeypatch.setattr(review_run.review_ledger, "status",
                        lambda *_a: {"state": rl.NEEDS_REPLAN, "rounds_left": 0})

    code = review_run.main(["--root", str(repo), "--ticket", "T1", "--scratch", str(scratch),
                            "--provider", "kimi", "--model", "k3", "--work-dir", str(work)])
    review = json.loads((work / "review.json").read_text(encoding="utf-8"))
    capsys.readouterr()

    assert (code, review["verdict"]) == (3, "INCOMPLETE")
    assert any("rate-limited" in r for r in review["reasons"])


# --- round 2 FIX review_run.py:301: graph.out is resolved before the review -----


def _crew_repo(repo, crew_json=None):
    """`.crew/config.json` gitignored and present, `.crew/verify.json` tracked
    -- the shape of this repository -- and optionally a committed crew.json."""
    (repo / ".gitignore").write_text(".crew/config.json\n", encoding="utf-8")
    (repo / ".crew").mkdir()
    (repo / ".crew" / "config.json").write_text('{"a": 1}\n', encoding="utf-8")
    (repo / ".crew" / "verify.json").write_text('{"rules": []}\n', encoding="utf-8")
    if crew_json is not None:
        (repo / ".crew" / "crew.json").write_text(crew_json, encoding="utf-8")
    git(repo, "add", ".gitignore", ".crew")
    git(repo, "commit", "-qm", "crew")
    return repo


def test_run_kimi_a_reviewer_that_moves_graph_out_is_incomplete(repo, tmp_path):
    """Round 2: graph.out was read AFTER the review, from the tree the reviewer
    could write, so writing `.crew/crew.json` = {"graph":{"out":".crew"}}
    excused every other write under `.crew/`."""
    _crew_repo(repo)

    result, review = _run(repo, tmp_path, FAKE_KIMI_PUT=json.dumps({
        ".crew/crew.json": '{"graph": {"out": ".crew"}}\n',
        ".crew/config.json": '{"a": 2}\n',
        ".crew/verify.json": '{"rules": ["weakened"]}\n'}))

    assert (result.returncode, review["verdict"]) == (3, "INCOMPLETE")
    reason = next(r for r in review["reasons"] if "working tree changed" in r)
    assert [p for p in (".crew/crew.json", ".crew/config.json", ".crew/verify.json")
            if p not in reason] == []


@pytest.mark.parametrize("name", ["config.json", "crew.json"])
def test_run_kimi_a_crew_config_write_counts_even_under_graph_out(repo, tmp_path, name):
    """A reviewer that writes crew config is itself a change, even when the
    configured graph.out already contains `.crew/`."""
    _crew_repo(repo, crew_json='{"graph": {"out": ".crew"}}\n')

    result, review = _run(repo, tmp_path,
                          FAKE_KIMI_PUT=json.dumps({f".crew/{name}": '{"b": 1}\n'}))

    assert (result.returncode, review["verdict"]) == (3, "INCOMPLETE")
    assert any(f".crew/{name}" in r for r in review["reasons"])


def test_run_kimi_graph_out_is_resolved_once_before_the_probe(repo, tmp_path, monkeypatch,
                                                              capsys):
    scratch, work = tmp_path / "scratch", tmp_path / "work"
    _bundle(repo, scratch)
    fakes = fake_kimi_bin(tmp_path / "bin")
    monkeypatch.setenv("PATH", str(fakes) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("KIMI_CODE_HOME", str(kimi_home(tmp_path / "kimi-home")))
    real, resolved = review_run.graph_out, []
    monkeypatch.setattr(review_run, "graph_out",
                        lambda root: resolved.append(root) or real(root))

    review_run.main(["--root", str(repo), "--ticket", "T1", "--scratch", str(scratch),
                     "--provider", "kimi", "--model", "k3", "--work-dir", str(work)])
    capsys.readouterr()

    assert resolved == [str(repo)]


# --- round 2 FIX review_run.py:623: no "before" fingerprint, nothing spent -------


def _env_repo(repo):
    (repo / ".gitignore").write_text(".env\n", encoding="utf-8")
    (repo / ".env").write_text("TOKEN=placeholder\n", encoding="utf-8")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-qm", "env")
    return repo


def test_run_kimi_unreadable_file_spends_no_probe_and_no_round(repo, tmp_path, monkeypatch,
                                                               capsys):
    """A "before" fingerprint that could not be taken already decides the
    round (INCOMPLETE), so the probe request and the reservation are both
    waste - round 2 measured one root-owned `.env` spending every round."""
    _env_repo(repo)
    scratch, work, dump = tmp_path / "scratch", tmp_path / "work", tmp_path / "dump.jsonl"
    _bundle(repo, scratch)
    fakes = fake_kimi_bin(tmp_path / "bin")
    monkeypatch.setenv("PATH", str(fakes) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("KIMI_CODE_HOME", str(kimi_home(tmp_path / "kimi-home")))
    monkeypatch.setenv("FAKE_KIMI_DUMP", str(dump))
    real = review_run._path_digest  # pylint: disable=protected-access
    monkeypatch.setattr(review_run, "_path_digest",
                        lambda p: None if os.path.basename(p) == ".env" else real(p))

    code = review_run.main(["--root", str(repo), "--ticket", "T1", "--scratch", str(scratch),
                            "--provider", "kimi", "--model", "k3", "--work-dir", str(work)])
    err = capsys.readouterr().err

    assert (code, dump.exists(), rl.status(str(repo), "T1")["rounds"]) == (2, False, [])
    assert "unknown - cannot fingerprint the tree" in err and ".env" in err


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0,
                    reason="root reads a mode-000 file, and NTFS has no mode bits: the "
                           "file is not unreadable there")
def test_run_kimi_mode_000_ignored_file_spends_no_round(repo, tmp_path):
    _env_repo(repo)
    os.chmod(repo / ".env", 0)
    dump = tmp_path / "dump.jsonl"
    try:
        result, review = _run(repo, tmp_path, FAKE_KIMI_DUMP=str(dump))
    finally:
        os.chmod(repo / ".env", 0o600)

    assert (result.returncode, review, dump.exists()) == (2, None, False)
    assert rl.status(str(repo), "T1")["rounds"] == []


# --- round 2 FIX review_run.py:221: tool caches are not the reviewer's ----------


def test_tool_caches_are_the_fixed_tuple():
    assert review_run.TOOL_CACHES == (".pytest_cache", "__pycache__", ".ruff_cache",
                                      ".mypy_cache", "node_modules/.cache")


_CACHE_WRITES = ",".join((".pytest_cache/v/cache/lastfailed", "pkg/__pycache__/m.cpython-314.pyc",
                          ".ruff_cache/0.6/abc", "sub/.mypy_cache/3.12/m.json",
                          "node_modules/.cache/babel/x.json"))


def _cache_repo(repo, ignore=True):
    lines = ["__pycache__/", ".pytest_cache/", ".ruff_cache/", ".mypy_cache/", "node_modules/",
             ".env"] if ignore else [".env"]
    (repo / ".gitignore").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (repo / ".env").write_text("TOKEN=placeholder\n", encoding="utf-8")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-qm", "ignore caches")
    return repo


def test_run_kimi_a_concurrent_tool_cache_write_is_not_the_reviewers(repo, tmp_path):
    """Round 2: a background pytest or ruff writing its ignored cache spent the
    round as INCOMPLETE with no reviewer write at all."""
    _cache_repo(repo)

    result, review = _run(repo, tmp_path, FAKE_KIMI_WRITES=_CACHE_WRITES)

    assert (result.returncode, review["verdict"]) == (0, "CLEAN"), review["reasons"]
    assert "pkg/__pycache__/m.cpython-314.pyc" in result.stderr


@pytest.mark.parametrize("path", [".env", ".crew/config.json"])
def test_run_kimi_an_ignored_secret_or_config_edit_still_counts(repo, tmp_path, path):
    _cache_repo(repo)
    with open(repo / ".gitignore", "a", encoding="utf-8") as fh:
        fh.write(".crew/config.json\n")
    (repo / ".crew").mkdir()
    (repo / ".crew" / "config.json").write_text('{"a": 1}\n', encoding="utf-8")

    result, review = _run(repo, tmp_path, FAKE_KIMI_WRITES=path)

    assert (result.returncode, review["verdict"]) == (3, "INCOMPLETE")
    assert any(path in r for r in review["reasons"] if "working tree changed" in r)


def test_run_kimi_a_cache_path_that_is_not_ignored_still_counts(repo, tmp_path):
    """The exemption is for IGNORED caches: an untracked, non-ignored file in a
    `__pycache__` directory is a reviewer write like any other."""
    _cache_repo(repo, ignore=False)

    result, review = _run(repo, tmp_path, FAKE_KIMI_WRITES="pkg/__pycache__/m.cpython-314.pyc")

    assert (result.returncode, review["verdict"]) == (3, "INCOMPLETE")


@pytest.mark.parametrize("rel,cache", [
    ("pkg/__pycache__/m.pyc", True), ("node_modules/.cache/x", True),
    (".pytest_cache/v/x", True), ("__pycache__", False), ("node_modules/x/.cache", False),
    ("my__pycache__/x", False), ("node_modules/.cachex/y", False), (".env", False),
])
def test_tool_cache_matches_by_whole_segment(rel, cache):
    assert review_run._tool_cache(rel) is cache  # pylint: disable=protected-access
