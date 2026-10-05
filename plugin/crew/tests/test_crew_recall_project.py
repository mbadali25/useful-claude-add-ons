"""L-0675: crew passes the repo's project to vault recall (`--project`) and
falls back cleanly on an obsidian-vault CLI that does not know the option.

Every test builds throwaway repos and vaults under tmp_path and points the
recall layer at a stub CLI (or at the checkout's real vault_ops.py for the
end-to-end case) through CREW_VAULT_OPS / CREW_OBSIDIAN_CONFIG, so the real
`~/.claude/obsidian/config.json` and installed plugins are never read.
"""
import json
import os
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_context
import crew_recall
from context_fixtures import (git, log_records, make_obsidian_config, make_repo,
                              make_stub_cli, payload)

_HERE = os.path.dirname(os.path.abspath(__file__))
_VAULT_SCRIPTS = os.path.abspath(os.path.join(_HERE, os.pardir, os.pardir, "obsidian-vault",
                                              "hooks", "scripts"))
_REAL_CLI = os.path.join(_VAULT_SCRIPTS, "vault_ops.py")


@pytest.fixture(autouse=True)
def _isolated_recall(tmp_path, monkeypatch):
    """No test may find the machine's real obsidian-vault plugin or config."""
    monkeypatch.setenv("CREW_VAULT_OPS", str(tmp_path / "absent-vault-ops.py"))
    monkeypatch.setenv("CREW_OBSIDIAN_CONFIG", str(tmp_path / "absent-obsidian.json"))
    monkeypatch.delenv("OBSIDIAN_VAULT_PLUGIN_ROOT", raising=False)


@pytest.fixture
def stub(tmp_path, monkeypatch):
    cli = make_stub_cli(tmp_path)
    monkeypatch.setenv("CREW_VAULT_OPS", str(cli))
    cfg = make_obsidian_config(tmp_path, {"primary-v": {"path": str(tmp_path), "role": "primary"}})
    monkeypatch.setenv("CREW_OBSIDIAN_CONFIG", str(cfg))
    argsfile = tmp_path / "stub-args.jsonl"
    monkeypatch.setenv("STUB_ARGS_OUT", str(argsfile))
    monkeypatch.setenv("STUB_JSON", json.dumps([{"vault": "primary-v", "note": "a.md", "text": "A-NOTE"}]))
    return argsfile


def _calls(argsfile):
    if not argsfile.exists():
        return []
    return [json.loads(line) for line in argsfile.read_text(encoding="utf-8").splitlines() if line]


def _project_args(argv):
    return [a for a in argv if a.startswith("--project")]


def _git_repo(path):
    path.mkdir(parents=True)
    git(path, "init", "-q")
    (path / "f.txt").write_text("x\n", encoding="utf-8")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "init")
    return path


class _Done:
    def __init__(self, returncode, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


# --- which project ----------------------------------------------------------

def test_the_main_checkout_name_is_sent_as_the_project(tmp_path, stub):
    root = _git_repo(tmp_path / "acme-app")

    result = crew_recall.recall("deploy checklist please", {}, root=str(root))

    assert _project_args(_calls(stub)[-1]) == ["--project=acme-app"]
    assert result["project"] == ["acme-app"]
    assert (result["status"], result["projectUsed"]) == ("hit", True)


def test_a_linked_worktree_sends_the_main_checkout_name(tmp_path, stub):
    root = _git_repo(tmp_path / "acme-app")
    lane = tmp_path / "lane-7"
    git(root, "worktree", "add", "-q", str(lane))

    crew_recall.recall("deploy checklist please", {}, root=str(lane))

    assert _project_args(_calls(stub)[-1]) == ["--project=acme-app"]


def test_the_config_list_wins_over_the_directory_name(tmp_path, stub):
    root = _git_repo(tmp_path / "acme-app")
    cfg = {"memory": {"recall": {"projects": ["crew", "Crew Plugin"]}}}

    crew_recall.recall("deploy checklist please", cfg, root=str(root))

    assert _project_args(_calls(stub)[-1]) == ["--project=crew,Crew Plugin"]


@pytest.mark.parametrize("bad", ["a,b", "two\nlines", "acme\n", "\tacme",
                                 "bell\x07", "sep x", 7, None, "", "   "])
def test_unusable_project_names_are_dropped(tmp_path, stub, bad):
    root = _git_repo(tmp_path / "acme-app")

    kept = crew_recall.projects({"memory": {"recall": {"projects": [bad, " ok ", "ok"]}}}, str(root))
    assert kept == ["ok"]

    crew_recall.recall("deploy checklist please", {"memory": {"recall": {"projects": [bad]}}},
                       root=str(root))
    assert _project_args(_calls(stub)[-1]) == []


def test_no_git_answer_sends_no_project(tmp_path, stub):
    plain = tmp_path / "not-a-repo"
    plain.mkdir()

    result = crew_recall.recall("deploy checklist please", {}, root=str(plain))

    assert _project_args(_calls(stub)[-1]) == []
    assert result["project"] == []
    assert result["projectUsed"] is None


def test_no_root_sends_todays_argv(stub):
    result = crew_recall.recall("deploy checklist please", {})

    assert _project_args(_calls(stub)[-1]) == []
    assert (result["project"], result["projectUsed"]) == ([], None)


# --- the fallback -----------------------------------------------------------

def test_an_older_cli_is_asked_again_without_the_project(tmp_path, stub, monkeypatch):
    root = _git_repo(tmp_path / "acme-app")
    monkeypatch.setenv("STUB_MODE", "noproject")

    result = crew_recall.recall("deploy checklist please", {}, root=str(root))

    calls = _calls(stub)
    assert len(calls) == 2
    assert _project_args(calls[0]) == ["--project=acme-app"]
    assert _project_args(calls[1]) == []
    assert calls[1] == [a for a in calls[0] if not a.startswith("--project")]
    assert result["status"] == "hit"
    assert result["projectUsed"] is False
    assert result["project"] == ["acme-app"]


def _timeout_runner(seen):
    def run(argv, **_kw):
        seen.append(argv)
        raise subprocess.TimeoutExpired("vault_ops", 4)
    return run


def _exit_runner(code, stdout=""):
    def make(seen):
        def run(argv, **_kw):
            seen.append(argv)
            return _Done(code, stdout)
        return run
    return make


@pytest.mark.parametrize("make, reason", [
    (_exit_runner(1), "cli-exit-1"),
    (_exit_runner(3), "cli-exit-3"),
    (_timeout_runner, "cli-timeout"),
    (_exit_runner(0, "not json"), "cli-bad-json"),
])
def test_only_exit_2_is_retried(tmp_path, stub, make, reason):
    root = _git_repo(tmp_path / "acme-app")
    seen = []

    result = crew_recall.recall("deploy checklist please", {}, root=str(root), runner=make(seen))

    assert len(seen) == 1
    assert (result["status"], result["reason"]) == ("miss", reason)
    assert result["projectUsed"] is None


def test_the_retry_shares_one_time_budget(tmp_path, stub, monkeypatch):
    root = _git_repo(tmp_path / "acme-app")
    clock = [100.0]
    monkeypatch.setattr(crew_recall, "_clock", lambda: clock[0])
    seen = []

    def slow_then_exit_2(argv, **kw):
        seen.append((argv, kw.get("timeout")))
        clock[0] += kw["timeout"]  # the first call spends the whole budget
        return _Done(2)

    result = crew_recall.recall("deploy checklist please", {}, root=str(root), runner=slow_then_exit_2)

    assert len(seen) == 1
    assert seen[0][1] == crew_recall.CLI_TIMEOUT_SECONDS
    assert (result["status"], result["reason"], result["projectUsed"]) == ("miss", "cli-exit-2", None)


def test_the_retry_gets_only_the_time_left(tmp_path, stub, monkeypatch):
    root = _git_repo(tmp_path / "acme-app")
    clock = [100.0]
    monkeypatch.setattr(crew_recall, "_clock", lambda: clock[0])
    seen = []

    def runner(argv, **kw):
        seen.append(kw["timeout"])
        if any(a.startswith("--project") for a in argv):
            clock[0] += 3
            return _Done(2)
        return _Done(0, json.dumps([{"vault": "primary-v", "note": "a.md", "text": "A"}]))

    result = crew_recall.recall("deploy checklist please", {}, root=str(root), runner=runner)

    assert seen == [crew_recall.CLI_TIMEOUT_SECONDS, crew_recall.CLI_TIMEOUT_SECONDS - 3]
    assert (result["status"], result["projectUsed"]) == ("hit", False)


def test_a_cli_that_exits_2_both_times_is_the_same_miss_as_today(tmp_path, stub, monkeypatch):
    root = _git_repo(tmp_path / "acme-app")
    monkeypatch.setenv("STUB_MODE", "exit")

    result = crew_recall.recall("deploy checklist please", {}, root=str(root))

    assert len(_calls(stub)) == 2
    assert (result["status"], result["reason"]) == ("miss", "cli-exit-2")
    assert result["projectUsed"] is None


# --- the context log --------------------------------------------------------

def test_the_context_log_records_the_project(tmp_path, stub):
    root = make_repo(tmp_path)

    crew_context.run(*_event(payload("UserPromptSubmit", root, prompt="deploy checklist please",
                                     prompt_id="p1")))
    rec = log_records(root)[-1]
    assert rec["recall"]["project"] == ["repo"]
    assert rec["recall"]["projectUsed"] is True

    transcript = tmp_path / "t.jsonl"
    call = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Agent", "input": {
        "subagent_type": "explorer", "description": "map beta", "prompt": "Explain the beta retry path"}}]}}
    transcript.write_text(json.dumps(call) + "\n", encoding="utf-8")
    crew_context.run(*_event(payload("SubagentStart", root, agent_id="ag1", agent_type="explorer",
                                     transcript_path=str(transcript))))
    rec = log_records(root)[-1]
    assert rec["event"] == "SubagentStart"
    assert rec["recall"]["project"] == ["repo"]
    assert rec["recall"]["projectUsed"] is True

    crew_context.slice_for_subagent(str(root), "review alpha caching", [])
    rec = log_records(root)[-1]
    assert rec["event"] == "slice-for-subagent"
    assert (rec["recall"]["project"], rec["recall"]["projectUsed"]) == (["repo"], True)


def _event(data):
    return data, json.dumps(data).encode()


# --- end to end against the real CLI ----------------------------------------

def _real_cli_knows_project():
    try:
        with open(os.path.join(_VAULT_SCRIPTS, "vault_recall.py"), encoding="utf-8") as handle:
            return "--project" in handle.read()
    except OSError:
        return False


def _concept(vault, name, project, body):
    path = vault / "wiki" / "concepts" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\ntitle: {name}\nproject: {project}\n---\n# {name}\n\n{body}\n",
                    encoding="utf-8")


@pytest.mark.skipif(not _real_cli_knows_project(),
                    reason="this checkout's obsidian-vault CLI has no --project option")
def test_this_repos_concept_outranks_another_projects_note(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    # The other project's note scores higher on the query; only the project
    # rank can put this repo's note first.
    _concept(vault, "sluice-other", "other-app",
             "brackenmoor sluice gate\nbrackenmoor sluice gate\nbrackenmoor sluice gate")
    _concept(vault, "sluice-ours", "acme-app", "brackenmoor sluice")
    cfg = tmp_path / "obsidian.json"
    cfg.write_text(json.dumps({"vaults": {"mem": {"path": str(vault), "role": "primary"}}}),
                   encoding="utf-8")
    monkeypatch.setenv("CREW_OBSIDIAN_CONFIG", str(cfg))
    monkeypatch.setenv("OBSIDIAN_VAULT_CONFIG", str(cfg))
    monkeypatch.setenv("CREW_VAULT_OPS", _REAL_CLI)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = _git_repo(tmp_path / "acme-app")

    result = crew_recall.recall("brackenmoor sluice", {}, root=str(root))

    assert (result["status"], result["projectUsed"]) == ("hit", True), result
    first = crew_recall.label(result["snippets"][0])
    assert first.startswith("- [vault:mem] wiki/concepts/sluice-ours.md:"), first
