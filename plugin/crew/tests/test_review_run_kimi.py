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
import review_ledger as rl
import review_run
from review_fixtures import env_with_path, fake_kimi_bin, init_repo, kimi_home

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

    path = review_run.kimi_agent_file(str(scratch))
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
    did not": a fingerprint that failed makes the round INCOMPLETE."""
    scratch, work = tmp_path / "scratch", tmp_path / "work"
    _bundle(repo, scratch)
    fakes = fake_kimi_bin(tmp_path / "bin")
    monkeypatch.setenv("PATH", str(fakes) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("KIMI_CODE_HOME", str(kimi_home(tmp_path / "kimi-home")))
    monkeypatch.setattr(review_run, "tree_fingerprint", lambda _root: None)

    code = review_run.main(["--root", str(repo), "--ticket", "T1", "--scratch", str(scratch),
                            "--provider", "kimi", "--model", "k3", "--work-dir", str(work)])
    review = json.loads((work / "review.json").read_text(encoding="utf-8"))
    capsys.readouterr()

    assert (code, review["verdict"]) == (3, "INCOMPLETE")
    assert any("could not be fingerprinted" in r for r in review["reasons"])
