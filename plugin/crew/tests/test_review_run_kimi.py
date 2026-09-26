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
import time

import pytest
import yaml

import context  # noqa: F401  pylint: disable=unused-import
import kimi_probe
import review_ledger as rl
import review_run
from review_fixtures import (LATE_WRITE_S, env_with_path, fake_kimi_bin, git, init_repo,
                             kimi_home)

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


def test_tree_fingerprint_sees_a_move_of_head_alone(repo):
    """Every tracked file is hashed now (round 3), so a committed edit is seen
    through its file too; `:HEAD` is what sees a commit that changes no file,
    and a `reset --soft` that un-commits one."""
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    before = review_run.tree_fingerprint(str(repo))

    git(repo, "commit", "-q", "--allow-empty", "-m", "reviewer was here")

    assert review_run.reviewer_changes(before, review_run.tree_fingerprint(str(repo)),
                                       None)[0] == [":HEAD"]


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


# --- round 2 FIX review_run.py:221, round 3 FIX :127 and NIT :360: what is set aside


def test_set_aside_names_are_the_fixed_tuples():
    assert (review_run.IDE_DIRS, review_run.CREW_LOGS, review_run.CREW_MARKERS) == (
        (".idea", ".vscode"), (".crew/guard.log", ".crew/.autoclear.log"),
        (".crew/.handoff-requested", ".crew/.autoclear-sent"))


def _ignore_repo(repo, lines=(".crew/*", ".idea/", ".vscode/", "__pycache__/", ".pytest_cache/",
                              ".ruff_cache/", ".mypy_cache/", "node_modules/", ".env",
                              ".coverage", "*.swp")):
    (repo / ".gitignore").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (repo / ".env").write_text("TOKEN=placeholder\n", encoding="utf-8")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-qm", "ignore")
    return repo


_NOT_THE_REVIEWERS = (".crew/guard.log", ".crew/.autoclear.log",
                      ".crew/.handoff-requested", ".crew/.handoff-requested-a1b2",
                      ".crew/.autoclear-sent-a1b2", ".idea/workspace.xml",
                      ".vscode/settings.json", "sub/.idea/misc.xml")


def test_run_kimi_crew_hook_logs_and_ide_files_are_not_the_reviewers(repo, tmp_path):
    """Round 3: crew's own hooks (guard.log, the auto-clear log and markers) and
    an IDE write ignored files mid-review, and each one spent the round."""
    _ignore_repo(repo)

    result, review = _run(repo, tmp_path, FAKE_KIMI_WRITES=",".join(_NOT_THE_REVIEWERS))

    assert (result.returncode, review["verdict"]) == (0, "CLEAN"), review["reasons"]
    assert [p for p in _NOT_THE_REVIEWERS if p not in result.stderr] == []


@pytest.mark.parametrize("path", [
    "pkg/__pycache__/m.cpython-314.pyc", ".pytest_cache/v/cache/lastfailed", ".ruff_cache/0.6/abc",
    "sub/.mypy_cache/3.12/m.json", "node_modules/.cache/babel/x.json",
    ".crew/.verify-verified-at", ".crew/.verify-gate.fingerprint",
    ".crew/.verify-gate.record.json", ".crew/.verify-gate.timings.json", ".crew/.scope-base",
    ".crew/guard.log.1", ".crew/.handoff-requestedX", ".crew/.handoff-requested-a/b",
    ".crew/config.json", ".env", ".coverage", ".seed.txt.swp", "x.idea/y", ".idea"])
def test_run_kimi_a_cache_or_gate_input_write_still_counts(repo, tmp_path, path):
    """Round 3 NIT :360: CPython runs a `__pycache__` .pyc whose header matches
    its source, so a write there changes what the tests execute. Every tool
    cache has that shape (a cached verdict or cached output a later run trusts),
    and so does every crew file a gate reads -- the verify marker above all."""
    _ignore_repo(repo)

    result, review = _run(repo, tmp_path, FAKE_KIMI_WRITES=path)

    assert (result.returncode, review["verdict"]) == (3, "INCOMPLETE")
    assert any(path in r for r in review["reasons"] if "working tree changed" in r)


def test_run_kimi_an_ide_path_that_is_not_ignored_still_counts(repo, tmp_path):
    """The exemption is for IGNORED paths: an untracked, non-ignored file under
    `.idea/` is a reviewer write like any other."""
    _ignore_repo(repo, lines=(".env",))

    result, review = _run(repo, tmp_path, FAKE_KIMI_WRITES=".idea/workspace.xml")

    assert (result.returncode, review["verdict"]) == (3, "INCOMPLETE")


def test_a_rewrite_with_the_same_content_is_no_change(repo):
    """The verify gate rewrites `.crew/.verify-verified-at` on every clean Stop
    (verify-gate.sh:122); at an unchanged HEAD it writes the same sha, and the
    fingerprint hashes CONTENT, so that rewrite is not a change."""
    _ignore_repo(repo)
    marker = repo / ".crew" / ".verify-verified-at"
    marker.parent.mkdir()
    marker.write_text(git(repo, "rev-parse", "HEAD") + "\n", encoding="utf-8")
    before = review_run.tree_fingerprint(str(repo))

    marker.write_text(git(repo, "rev-parse", "HEAD") + "\n", encoding="utf-8")

    assert review_run.tree_fingerprint(str(repo)) == before


# --- round 3 BLOCK review_run.py:317: "ignored THROUGHOUT" has a failing control --


@pytest.mark.parametrize("rel", [".idea/workspace.xml", ".crew/guard.log"])
@pytest.mark.parametrize("now_ignored", [True, False])
def test_a_set_aside_path_whose_ignore_state_flipped_still_counts(repo, rel, now_ignored):
    """A reviewer that adds a path to `.git/info/exclude` (which the fingerprint
    does not hash) and then rewrites it moves it from `??` to `!!`; the reverse
    edit moves it from `!!` to `??`. Neither state held throughout."""
    target, exclude = repo / rel, repo / ".git" / "info" / "exclude"
    target.parent.mkdir(parents=True, exist_ok=True)
    exclude.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("before\n", encoding="utf-8")
    exclude.write_text("" if now_ignored else rel + "\n", encoding="utf-8")
    before = review_run.tree_fingerprint(str(repo))

    exclude.write_text(rel + "\n" if now_ignored else "", encoding="utf-8")
    target.write_text("after\n", encoding="utf-8")

    assert review_run.reviewer_changes(before, review_run.tree_fingerprint(str(repo)),
                                       None) == ([rel], [])


@pytest.mark.parametrize("rel,kept", [
    ("pkg/.idea/x", True), (".vscode/a/b.json", True), (".idea", False), ("my.idea/x", False),
    (".idea-old/x", False), (".crew/guard.log", True), ("sub/.crew/guard.log", False),
    (".crew/.autoclear-sent", True), (".crew/.autoclear-sent-k", True),
    (".crew/.autoclear-sent-k/x", False), (".crew/.autoclear-sentk", False),
    ("pkg/__pycache__/m.pyc", False),
])
def test_set_aside_matches_by_whole_segment_and_whole_name(rel, kept):
    assert review_run._not_a_check_input(rel) is kept  # pylint: disable=protected-access


# --- round 3 FIX review_run.py:246: every tracked file is hashed ------------------


_OLD_NS = 1_600_000_000_000_000_000


def _old_mtime(repo):
    """seed.txt given a 2020 mtime and re-added, so the index records it."""
    os.utime(repo / "seed.txt", ns=(_OLD_NS, _OLD_NS))
    git(repo, "add", "seed.txt")


def _index_flag(flag):
    def hide(repo):
        git(repo, "update-index", flag, "seed.txt")
        (repo / "seed.txt").write_text("FIXED\n", encoding="utf-8")
    return hide


def _stat_config(key, value):
    def hide(repo):
        git(repo, "config", key, value)
        size = (repo / "seed.txt").stat().st_size
        (repo / "seed.txt").write_text("X" * (size - 1) + "\n", encoding="utf-8")
        os.utime(repo / "seed.txt", ns=(_OLD_NS, _OLD_NS))
    return hide


@pytest.mark.parametrize("hide", [_index_flag("--skip-worktree"),
                                  _index_flag("--assume-unchanged"),
                                  _stat_config("core.trustctime", "false"),
                                  _stat_config("core.checkStat", "minimal")],
                         ids=["skip-worktree", "assume-unchanged", "trustctime", "checkStat"])
def test_tree_fingerprint_sees_an_edit_git_status_does_not_report(repo, hide):
    """Round 3: an index flag hides a tracked file's edit from `git status`,
    and so (measured) does a same-size rewrite that restores the mtime once
    `.git/config` -- which the fingerprint does not hash -- stops git trusting
    ctime. Hashing every tracked file's contents does not ask git."""
    _old_mtime(repo)
    before = review_run.tree_fingerprint(str(repo))

    hide(repo)

    assert review_run.reviewer_changes(before, review_run.tree_fingerprint(str(repo)),
                                       None)[0] == ["seed.txt"]


@pytest.mark.parametrize("flag", ["--skip-worktree", "--assume-unchanged"])
def test_tree_fingerprint_sees_an_edit_under_a_flag_set_before_the_review(repo, flag):
    git(repo, "update-index", flag, "seed.txt")
    before = review_run.tree_fingerprint(str(repo))

    (repo / "seed.txt").write_text("FIXED\n", encoding="utf-8")

    assert review_run.reviewer_changes(before, review_run.tree_fingerprint(str(repo)),
                                       None)[0] == ["seed.txt"]


# --- round 3 FIX review_run.py:194: a nested repository is hashed, not "dir" -------


def _nested(repo, where):
    inner = init_repo(repo / "vendor" / "lib")
    if where == "ignored":
        (repo / ".gitignore").write_text("vendor/\n", encoding="utf-8")
        git(repo, "add", ".gitignore")
        git(repo, "commit", "-qm", "ignore vendor")
    return inner


def _submodule(repo, tmp_path, ignore_all=False):
    src = init_repo(tmp_path / "src")
    git(repo, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(src), "lib")
    git(repo, "commit", "-qm", "submodule")
    if ignore_all:
        git(repo, "config", "submodule.lib.ignore", "all")
    return repo / "lib"


@pytest.mark.parametrize("where", ["untracked", "ignored"])
@pytest.mark.parametrize("dirty_before", [False, True])
def test_tree_fingerprint_sees_an_edit_inside_a_nested_repository(repo, where, dirty_before):
    inner = _nested(repo, where)
    if dirty_before:
        (inner / "seed.txt").write_text("dirty\n", encoding="utf-8")
    before = review_run.tree_fingerprint(str(repo))

    (inner / "seed.txt").write_text("FIXED\n", encoding="utf-8")

    assert review_run.reviewer_changes(before, review_run.tree_fingerprint(str(repo)),
                                       None)[0] == ["vendor/lib"]


@pytest.mark.parametrize("ignore_all", [False, True])
@pytest.mark.parametrize("dirty_before", [False, True])
def test_tree_fingerprint_sees_an_edit_inside_a_submodule(repo, tmp_path, ignore_all,
                                                          dirty_before):
    """A dirty submodule stayed ` M lib` / `dir` whatever changed inside it;
    `submodule.<name>.ignore=all` in `.git/config` hides it from status."""
    inner = _submodule(repo, tmp_path, ignore_all)
    if dirty_before:
        (inner / "seed.txt").write_text("dirty\n", encoding="utf-8")
    before = review_run.tree_fingerprint(str(repo))

    (inner / "seed.txt").write_text("FIXED\n", encoding="utf-8")

    assert review_run.reviewer_changes(before, review_run.tree_fingerprint(str(repo)),
                                       None)[0] == ["lib"]


def test_tree_fingerprint_of_a_nested_repository_with_no_commit(repo):
    inner = repo / "scratch-clone"
    inner.mkdir()
    git(inner, "init", "-q")
    (inner / "a.txt").write_text("a\n", encoding="utf-8")
    before = review_run.tree_fingerprint(str(repo))

    (inner / "a.txt").write_text("FIXED\n", encoding="utf-8")

    assert before is not None
    assert review_run.reviewer_changes(before, review_run.tree_fingerprint(str(repo)),
                                       None)[0] == ["scratch-clone"]


def test_tree_fingerprint_sees_a_write_into_an_uninitialised_submodule(repo, tmp_path):
    """Neighbour of the nested-repository FIX, measured: after `git submodule
    deinit`, a file written into the empty `lib/` is listed by no `git status`
    mode. A directory is walked, never hashed as a constant."""
    _submodule(repo, tmp_path)
    git(repo, "submodule", "deinit", "-q", "-f", "lib")
    before = review_run.tree_fingerprint(str(repo))

    (repo / "lib" / "conftest.py").write_text("FIXED = True\n", encoding="utf-8")

    assert review_run.reviewer_changes(before, review_run.tree_fingerprint(str(repo)),
                                       None)[0] == ["lib"]


def test_tree_fingerprint_a_broken_nested_git_file_is_walked_as_plain_files(repo):
    """git lists a directory whose `.git` names no repository file by file;
    those files are hashed like any untracked file (control)."""
    inner = repo / "vendor" / "broken"
    inner.mkdir(parents=True)
    (inner / ".git").write_text("gitdir: /nonexistent/crew-test\n", encoding="utf-8")
    (inner / "a.txt").write_text("a\n", encoding="utf-8")
    before = review_run.tree_fingerprint(str(repo))

    (inner / "a.txt").write_text("FIXED\n", encoding="utf-8")

    assert review_run.reviewer_changes(before, review_run.tree_fingerprint(str(repo)),
                                       None)[0] == ["vendor/broken/a.txt"]


# --- round 3 NIT review_run.py:250: a worktree rename --------------------------------


def test_tree_fingerprint_reads_a_worktree_rename_as_two_paths(repo):
    """`git add -N` on a moved file gave ` R`, and its source path was parsed
    as an entry of its own: a key `.txt` stat'ing a truncated path."""
    (repo / "seed.txt").rename(repo / "moved.txt")
    git(repo, "add", "-N", "moved.txt")

    snapshot = review_run.tree_fingerprint(str(repo))

    assert sorted(k for k in snapshot if not k.startswith(":")) == [
        "change.txt", "moved.txt", "seed.txt"]
    assert snapshot["seed.txt"].endswith(" missing")


# --- round 3 NIT review_run.py:628: a probe fingerprint that failed ----------------


def test_run_kimi_unfingerprintable_tree_after_the_probe_spends_no_round(repo, tmp_path,
                                                                        monkeypatch, capsys):
    scratch, work = tmp_path / "scratch", tmp_path / "work"
    _bundle(repo, scratch)
    fakes = fake_kimi_bin(tmp_path / "bin")
    monkeypatch.setenv("PATH", str(fakes) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("KIMI_CODE_HOME", str(kimi_home(tmp_path / "kimi-home")))
    real, taken = review_run.tree_fingerprint, []

    def fingerprint(root, problems=None):
        taken.append(root)
        return real(root, problems) if len(taken) == 1 else None

    monkeypatch.setattr(review_run, "tree_fingerprint", fingerprint)

    code = review_run.main(["--root", str(repo), "--ticket", "T1", "--scratch", str(scratch),
                            "--provider", "kimi", "--model", "k3", "--work-dir", str(work)])
    err = capsys.readouterr().err

    assert (code, (work / "review.json").exists()) == (2, False)
    assert rl.status(str(repo), "T1")["rounds"] == []
    assert "could not be fingerprinted after the probe" in err


# --- round 3 NIT review_run.py:643: a process the reviewer left running ------------


@pytest.mark.skipif(os.name == "nt", reason="POSIX process groups; see review_run's NOT SEEN")
@pytest.mark.parametrize("knob", ["FAKE_KIMI_LATE", "FAKE_KIMI_PROBE_LATE"])
def test_run_kimi_a_process_left_running_cannot_write_after_the_check(repo, tmp_path, knob):
    """A background process the review (or probe) call started wrote the tree
    a moment after the leader exited -- after the fingerprint was taken, so
    the round read CLEAN and the write landed unreviewed."""
    seed = (repo / "seed.txt").read_text(encoding="utf-8")

    result, review = _run(repo, tmp_path, **{knob: str(repo / "seed.txt")})
    time.sleep(LATE_WRITE_S + 1.5)

    assert (repo / "seed.txt").read_text(encoding="utf-8") == seed
    assert (result.returncode, review["verdict"]) == (0, "CLEAN"), review["reasons"]


def test_a_git_dir_that_is_not_its_own_repository_is_could_not_tell(repo):
    """A `.git` git does not accept (here an empty directory) makes git inside
    it walk UP to the parent: that subtree must never be fingerprinted as if it
    were a repository of its own. Driven through `_entry_digest` directly,
    because a top-level `git status` over such a submodule already fails."""
    (repo / "d" / ".git").mkdir(parents=True)
    (repo / "d" / "a.txt").write_text("a\n", encoding="utf-8")
    problems = []

    assert review_run._entry_digest(str(repo), "d", problems, 0) is None  # pylint: disable=protected-access
    assert any(p.startswith("d holds a .git") for p in problems), problems


def test_tree_fingerprint_nested_deeper_than_the_cap_is_none(repo):
    where = repo
    for _ in range(review_run.NESTED_DEPTH + 1):
        where = where / "n"
        where.mkdir()
        git(where, "init", "-q")
        (where / "a.txt").write_text("a\n", encoding="utf-8")
    problems = []

    assert review_run.tree_fingerprint(str(repo), problems) is None
    assert any("nested more than" in p for p in problems), problems


@pytest.mark.skipif(not os.path.isdir("/proc/self"), reason="reads /proc")
def test_group_alive_ignores_a_zombie_and_sees_a_live_member():
    """A killed member stays a zombie until something reaps it, and a zombie
    still answers signal 0: it must not read as a survivor."""
    live = subprocess.Popen(["sleep", "30"], start_new_session=True)  # pylint: disable=consider-using-with
    dead = subprocess.Popen(["true"], start_new_session=True)  # pylint: disable=consider-using-with
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            with open(f"/proc/{dead.pid}/stat", encoding="ascii") as fh:
                if fh.read().rsplit(")", 1)[1].split()[0] == "Z":
                    break
            time.sleep(0.05)

        assert (review_run._group_alive(live.pid),  # pylint: disable=protected-access
                review_run._group_alive(dead.pid)) == (True, False)  # pylint: disable=protected-access
    finally:
        live.kill()
        live.wait()
        dead.wait()


def test_stop_survivors_that_will_not_die_is_could_not_tell(monkeypatch):
    monkeypatch.setattr(review_run, "_group_alive", lambda _pgid: True)
    monkeypatch.setattr(review_run.os, "killpg", lambda *_a: None)
    monkeypatch.setattr(review_run, "POST_KILL_TIMEOUT", 0.2)
    if os.name == "nt":
        pytest.skip("no process group is probed on Windows")

    assert review_run.stop_survivors([12345]) == (True, review_run.KIMI_SURVIVOR_UNKNOWN)


def _main_with_survivor_unknown(repo, tmp_path, monkeypatch, capsys):
    scratch, work = tmp_path / "scratch", tmp_path / "work"
    _bundle(repo, scratch)
    fakes = fake_kimi_bin(tmp_path / "bin")
    monkeypatch.setenv("PATH", str(fakes) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("KIMI_CODE_HOME", str(kimi_home(tmp_path / "kimi-home")))
    calls = []

    def stop(started):
        calls.append(started)
        return (True, review_run.KIMI_SURVIVOR_UNKNOWN) if len(calls) == 2 else (False, None)

    monkeypatch.setattr(review_run, "stop_survivors", stop)
    code = review_run.main(["--root", str(repo), "--ticket", "T1", "--scratch", str(scratch),
                            "--provider", "kimi", "--model", "k3", "--work-dir", str(work)])
    capsys.readouterr()
    review_path = work / "review.json"
    return code, json.loads(review_path.read_text(encoding="utf-8")) \
        if review_path.exists() else None


def test_run_kimi_a_review_survivor_that_will_not_die_is_incomplete(repo, tmp_path, monkeypatch,
                                                                   capsys):
    code, review = _main_with_survivor_unknown(repo, tmp_path, monkeypatch, capsys)

    assert (code, review["verdict"]) == (3, "INCOMPLETE")
    assert review_run.KIMI_SURVIVOR_UNKNOWN in review["reasons"]


def test_run_kimi_a_probe_survivor_that_will_not_die_spends_no_round(repo, tmp_path,
                                                                    monkeypatch, capsys):
    monkeypatch.setattr(review_run, "stop_survivors",
                        lambda _started: (True, review_run.KIMI_SURVIVOR_UNKNOWN))
    scratch, work = tmp_path / "scratch", tmp_path / "work"
    _bundle(repo, scratch)
    fakes = fake_kimi_bin(tmp_path / "bin")
    monkeypatch.setenv("PATH", str(fakes) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("KIMI_CODE_HOME", str(kimi_home(tmp_path / "kimi-home")))

    code = review_run.main(["--root", str(repo), "--ticket", "T1", "--scratch", str(scratch),
                            "--provider", "kimi", "--model", "k3", "--work-dir", str(work)])
    err = capsys.readouterr().err

    assert (code, rl.status(str(repo), "T1")["rounds"]) == (2, [])
    assert "kimi probe: unknown" in err
