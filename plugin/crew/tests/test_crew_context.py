"""crew_context.py: budgets per event, dedup per subsystem and compaction
epoch, vault-labelled recall in the repo's priority order, degradation when
the vault CLI is missing or broken, and the emission log.

Every test runs in a throwaway git repo and points the recall layer at a stub
CLI (or at nothing) through CREW_VAULT_OPS / CREW_OBSIDIAN_CONFIG, so the real
`~/.claude/obsidian/config.json` and installed plugins are never read.
"""
import json
import os
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_context
import crew_recall
from context_fixtures import (log_records, make_obsidian_config, make_repo,
                              make_stub_cli, payload)


@pytest.fixture(autouse=True)
def _isolated_recall(tmp_path, monkeypatch):
    """No test may find the machine's real obsidian-vault plugin or config."""
    monkeypatch.setenv("CREW_VAULT_OPS", str(tmp_path / "absent-vault-ops.py"))
    monkeypatch.setenv("CREW_OBSIDIAN_CONFIG", str(tmp_path / "absent-obsidian.json"))
    monkeypatch.delenv("OBSIDIAN_VAULT_PLUGIN_ROOT", raising=False)


def _run(data):
    return crew_context.run(data, json.dumps(data).encode())


def _snippets(n, vault="primary-v", width=300):
    return [{"vault": vault, "path": f"notes/n{i}.md", "text": f"RECALL-{i} " + "w" * width}
            for i in range(n)]


@pytest.fixture
def stub(tmp_path, monkeypatch):
    cli = make_stub_cli(tmp_path)
    monkeypatch.setenv("CREW_VAULT_OPS", str(cli))
    cfg = make_obsidian_config(tmp_path, {
        "primary-v": {"path": str(tmp_path), "role": "primary"},
        "recall-v": {"path": str(tmp_path), "role": "recall"},
        "ignored-v": {"path": str(tmp_path), "role": "ignore"},
    })
    monkeypatch.setenv("CREW_OBSIDIAN_CONFIG", str(cfg))
    argsfile = tmp_path / "stub-args.jsonl"
    monkeypatch.setenv("STUB_ARGS_OUT", str(argsfile))
    return argsfile


# --- budgets ----------------------------------------------------------------

def test_startup_emission_stays_within_twelve_lines_and_1500_chars(tmp_path, stub, monkeypatch):
    many = {f"sub{i:02d}": ([f"s{i}/a.py", f"s{i}/b.py", f"s{i}/c.py"], [f"mark {i}"]) for i in range(30)}
    root = make_repo(tmp_path, subsystems=many)
    monkeypatch.setenv("STUB_JSON", json.dumps(_snippets(20)))

    text = _run(payload("SessionStart", root, source="startup"))

    assert text
    assert len(text) <= crew_context.STARTUP_CHARS == 1500
    assert len(text.splitlines()) <= crew_context.STARTUP_LINES == 12


def test_resume_with_a_handoff_carries_it_within_3000_chars(tmp_path):
    root = make_repo(tmp_path, handoff="# Handoff\n\n## Next action\nFinish HANDOFF-TOKEN work.\n" + "z" * 5000)

    text = _run(payload("SessionStart", root, source="resume"))

    assert "HANDOFF-TOKEN" in text
    assert len(text) <= crew_context.RESUME_CHARS == 3000


def test_a_stale_handoff_is_archived_rather_than_injected(tmp_path, monkeypatch):
    import crew_state  # pylint: disable=import-outside-toplevel
    root = make_repo(tmp_path, handoff="# Handoff\nSTALE-HANDOFF-TOKEN\n")

    def archive(root_arg, _cfg):
        os.replace(os.path.join(root_arg, ".work", "HANDOFF.md"), os.path.join(root_arg, ".work", "old.md"))
        return {"archived": True}

    monkeypatch.setattr(crew_state, "archive_stale_handoff", archive)

    text = _run(payload("SessionStart", root, source="clear"))

    assert "STALE-HANDOFF-TOKEN" not in text
    assert log_records(root)[-1]["handoff"] == "archived-stale"


def test_per_turn_slices_share_one_2000_char_budget(tmp_path):
    many = {f"sub{i:02d}": ([f"s{i}/a.py", f"s{i}/b.py", f"s{i}/c.py"],
                            [f"landmine {i} " + "q" * 150 for _ in range(4)]) for i in range(12)}
    root = make_repo(tmp_path, subsystems=many)
    total = len(_run(payload("UserPromptSubmit", root, prompt="look at sub00 and sub01 and sub02",
                             prompt_id="p1")))
    for i in range(3, 12):
        total += len(_run(payload("PostToolUse", root, tool_name="Read",
                                  tool_input={"file_path": str(root / f"s{i}" / "a.py")})))

    assert total > 0
    assert total <= crew_context.TURN_CHARS == 2000


def test_fit_never_exceeds_the_6000_char_hard_cap_whatever_the_budget():
    items = [{"id": f"i{n}", "text": "x" * 900, "source": {"kind": "codemap"}} for n in range(20)]

    text, _, cut = crew_context.fit(items, 100_000)

    assert len(text) <= 6000
    assert cut


# --- dedup ------------------------------------------------------------------

def test_a_subsystem_slice_is_injected_once_per_epoch(tmp_path):
    root = make_repo(tmp_path)
    touch = payload("PostToolUse", root, tool_name="Edit",
                    tool_input={"file_path": str(root / "src" / "alpha" / "core.py")})

    first = _run(touch)
    second = _run(dict(touch, tool_use_id="t2"))

    assert "ALPHA-LANDMINE" in first
    assert second == ""
    assert log_records(root)[-1]["dedupHits"] == 1


def test_a_compaction_starts_a_new_epoch_and_the_slice_returns(tmp_path):
    root = make_repo(tmp_path)
    touch = payload("PostToolUse", root, tool_name="Read",
                    tool_input={"file_path": str(root / "src" / "beta" / "api.py")})
    _run(touch)
    _run(payload("SessionStart", root, source="compact"))
    _run(payload("UserPromptSubmit", root, prompt="continue", prompt_id="p9"))

    again = _run(dict(touch, tool_use_id="t3"))

    assert "BETA-LANDMINE" in again


def test_subagent_context_is_deduplicated_separately_from_the_main_agent(tmp_path):
    root = make_repo(tmp_path)
    _run(payload("UserPromptSubmit", root, prompt="fix alpha", prompt_id="p1"))

    sub = _run(payload("SubagentStart", root, agent_id="a1", agent_type="explorer"))

    assert "ALPHA-LANDMINE" in sub


# --- recall -----------------------------------------------------------------

def test_every_recall_snippet_names_its_vault_and_unlabelled_items_are_dropped(tmp_path, stub, monkeypatch):
    root = make_repo(tmp_path)
    items = _snippets(2, width=20) + [{"path": "notes/orphan.md", "text": "UNLABELLED-SNIPPET"}]
    monkeypatch.setenv("STUB_JSON", json.dumps(items))

    text = _run(payload("UserPromptSubmit", root, prompt="what do we know about retries", prompt_id="p1"))

    recall_lines = [l for l in text.splitlines() if "RECALL-" in l]
    assert len(recall_lines) == 2
    assert all(l.startswith("- [vault:primary-v] notes/") for l in recall_lines)
    assert "UNLABELLED-SNIPPET" not in text
    assert log_records(root)[-1]["recall"]["dropped"] == 1


def test_label_puts_the_vault_first():
    assert crew_recall.label({"vault": "v1", "note": "a.md", "text": "t"}) == "- [vault:v1] a.md: t"


def test_snippets_follow_the_repo_vault_priority_not_the_cli_order(tmp_path, stub, monkeypatch):
    root = make_repo(tmp_path, config={"memory": {"recall": {"vaults": ["recall-v", "primary-v"],
                                                             "maxChars": 600}}})
    monkeypatch.setenv("STUB_JSON", json.dumps(
        [{"vault": "primary-v", "note": "p.md", "text": "FROM-PRIMARY"},
         {"vault": "recall-v", "note": "r.md", "text": "FROM-RECALL"}]))

    text = _run(payload("UserPromptSubmit", root, prompt="deploy checklist please", prompt_id="p1"))

    assert text.index("FROM-RECALL") < text.index("FROM-PRIMARY")
    argv = json.loads(stub.read_text(encoding="utf-8").splitlines()[-1])
    assert argv[argv.index("--vaults") + 1] == "recall-v,primary-v"
    assert argv[argv.index("--max-chars") + 1] == "600"
    assert "--json" in argv


def test_default_order_is_primary_then_recall_and_ignore_is_never_asked(tmp_path, stub):
    order = crew_recall.vault_order({})

    assert order == ["primary-v", "recall-v"]


def test_a_repo_list_cannot_resurrect_an_ignored_vault(stub):
    order = crew_recall.vault_order({"memory": {"recall": {"vaults": ["ignored-v", "recall-v"]}}})

    assert order == ["recall-v"]


@pytest.mark.parametrize("mode, reason", [("exit", "cli-exit-2"), ("badjson", "cli-bad-json")])
def test_a_broken_cli_is_a_logged_miss_not_a_failure(tmp_path, stub, monkeypatch, mode, reason):
    root = make_repo(tmp_path)
    monkeypatch.setenv("STUB_MODE", mode)

    text = _run(payload("UserPromptSubmit", root, prompt="anything at all about alpha", prompt_id="p1"))

    assert "ALPHA-LANDMINE" in text
    assert log_records(root)[-1]["recall"] == {"status": "miss", "reason": reason, "snippets": 0,
                                               "dropped": 0, "vaults": ["primary-v", "recall-v"]}


def test_a_missing_cli_degrades_silently_and_logs_the_miss(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    cfg = make_obsidian_config(tmp_path, {"only": {"path": str(tmp_path), "default": True}})
    monkeypatch.setenv("CREW_OBSIDIAN_CONFIG", str(cfg))

    text = _run(payload("UserPromptSubmit", root, prompt="tell me about beta", prompt_id="p1"))

    assert "BETA-LANDMINE" in text
    assert log_records(root)[-1]["recall"]["reason"] == "cli-missing"


def test_a_cli_timeout_is_a_miss(monkeypatch, stub):
    def slow(*_a, **_k):
        raise subprocess.TimeoutExpired("vault_ops", 4)

    result = crew_recall.recall("some query", {}, runner=slow)

    assert (result["status"], result["reason"]) == ("miss", "cli-timeout")


# --- subagents --------------------------------------------------------------

def test_subagent_start_reads_the_task_from_the_parent_transcript(tmp_path, stub, monkeypatch):
    root = make_repo(tmp_path)
    monkeypatch.setenv("STUB_JSON", json.dumps([{"vault": "recall-v", "note": "k.md", "text": "KEEPER-FACT"}]))
    transcript = tmp_path / "t.jsonl"
    call = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Agent", "input": {
        "subagent_type": "explorer", "description": "map beta", "prompt": "Explain the beta retry path"}}]}}
    transcript.write_text(json.dumps(call) + "\n", encoding="utf-8")

    text = _run(payload("SubagentStart", root, agent_id="ag1", agent_type="explorer",
                        transcript_path=str(transcript)))

    assert "BETA-LANDMINE" in text
    assert "- [vault:recall-v] k.md: KEEPER-FACT" in text
    assert len(text) <= crew_context.SUBAGENT_CHARS
    rec = log_records(root)[-1]
    assert (rec["event"], rec["agent_type"], rec["query_from"]) == ("SubagentStart", "explorer", "transcript")
    argv = json.loads(stub.read_text(encoding="utf-8").splitlines()[-1])
    assert "beta retry path" in argv[argv.index("--query") + 1]


# Parallel same-type dispatches: see test_crew_context_fixes.py. The test
# that stood here asserted list-order attribution, which the T6 review showed
# hands task one's recall to whichever sibling's hook runs first.


def test_slice_for_subagent_prints_labelled_context_for_a_dispatch_prompt(tmp_path, stub, monkeypatch):
    root = make_repo(tmp_path)
    monkeypatch.setenv("STUB_JSON", json.dumps([{"vault": "primary-v", "note": "a.md", "text": "ALPHA-NOTE"}]))

    text = crew_context.slice_for_subagent(str(root), "review alpha caching", [])

    assert "[codemap:alpha" in text
    assert "- [vault:primary-v] a.md: ALPHA-NOTE" in text


# --- log, stats, never-blocking ---------------------------------------------

def test_every_emission_appends_a_log_line_with_its_sources(tmp_path, stub, monkeypatch):
    root = make_repo(tmp_path)
    monkeypatch.setenv("STUB_JSON", json.dumps([{"vault": "primary-v", "note": "n.md", "text": "NOTE"}]))

    text = _run(payload("UserPromptSubmit", root, prompt="alpha question", prompt_id="p1"))

    rec = log_records(root)[-1]
    assert rec["chars"] == len(text)
    assert {"ts", "event", "harness", "dedupHits", "truncated", "sources"} <= set(rec)
    kinds = {(s["kind"], s.get("vault"), s.get("note"), s.get("subsystem")) for s in rec["sources"]}
    assert ("vault", "primary-v", "n.md", None) in kinds
    assert ("codemap", None, None, "alpha") in kinds


def test_stats_counts_hits_misses_chars_and_vault_tool_calls(tmp_path, stub, monkeypatch):
    root = make_repo(tmp_path)
    monkeypatch.setenv("STUB_JSON", json.dumps([{"vault": "primary-v", "note": "n.md", "text": "NOTE"}]))
    _run(payload("UserPromptSubmit", root, prompt="alpha question", prompt_id="p1"))
    monkeypatch.setenv("STUB_MODE", "exit")
    _run(payload("UserPromptSubmit", root, prompt="beta question", prompt_id="p2"))
    _run(payload("PostToolUse", root, tool_name="mcp__obsidian-claude-memories__search", tool_input={}))

    stats = json.loads(crew_context.stats(str(root), as_json=True))

    assert stats["recall"]["hit"] == 1
    assert stats["recall"]["miss"] == 1
    assert stats["missReasons"] == {"cli-exit-2": 1}
    assert stats["vaultTools"] == {"mcp__obsidian-claude-memories__search": 1}
    assert stats["chars"] > 0


def test_a_repo_without_crew_gets_nothing(tmp_path):
    bare = tmp_path / "plain"
    bare.mkdir()

    assert _run(payload("SessionStart", bare, source="startup")) == ""


def test_the_low_context_note_shows_once_per_epoch(tmp_path):
    root = make_repo(tmp_path)
    transcript = tmp_path / "t.jsonl"
    usage = {"message": {"model": "claude-haiku-4", "usage": {
        "input_tokens": 10, "cache_read_input_tokens": 150_000, "cache_creation_input_tokens": 0}}}
    transcript.write_text(json.dumps(usage) + "\n", encoding="utf-8")
    ask = payload("UserPromptSubmit", root, prompt="go", prompt_id="p1", transcript_path=str(transcript))

    first = _run(ask)
    second = _run(dict(ask, prompt_id="p2"))

    assert "context is at 75%" in first
    assert "context is at" not in second


def test_main_never_emits_a_decision_and_always_returns_zero(tmp_path, monkeypatch, capsys):
    root = make_repo(tmp_path)
    for raw in (b"", b"not json", b"[1,2]", json.dumps(payload("Stop", root)).encode(),
                json.dumps(payload("UserPromptSubmit", root, prompt="alpha", prompt_id="z")).encode()):
        monkeypatch.setattr("sys.stdin", type("S", (), {"buffer": type("B", (), {"read": lambda self, r=raw: r})()})())
        assert crew_context.main([]) == 0
        out = capsys.readouterr().out
        if out.strip():
            parsed = json.loads(out)
            assert set(parsed) == {"hookSpecificOutput"}
            assert "decision" not in json.dumps(parsed)


def test_the_state_and_log_live_under_the_git_common_dir(tmp_path):
    root = make_repo(tmp_path)

    _run(payload("UserPromptSubmit", root, prompt="alpha", prompt_id="p1"))

    assert os.path.isfile(os.path.join(root, ".git", "crew", "context-log.jsonl"))
    assert not os.path.exists(os.path.join(root, ".work", "crew"))
