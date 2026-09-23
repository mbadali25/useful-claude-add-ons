"""crew_instructions.py: generated `.claude/rules/`, AGENTS.md and Codex files.

Budgets are asserted on generator output for oversized inputs, drift is
asserted by editing a source after generation, and the Codex hooks file is
asserted to come from the same table as the Claude registration.
"""
import json
import os
import stat

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_instructions as ci
from context_fixtures import make_repo


def _big_repo(tmp_path, count=3, marks=40):
    subs = {f"sub{i:03d}": ([f"s{i}/a.py", f"s{i}/b.py", f"s{i}/c.py"],
                            [f"landmine {i}.{m} " + "w" * 80 for m in range(marks)])
            for i in range(count)}
    return make_repo(tmp_path, subsystems=subs)


def test_every_rules_file_is_path_scoped_hashed_and_at_most_30_lines(tmp_path):
    root = _big_repo(tmp_path)

    problems, written = ci.rules(str(root))

    assert not problems
    assert len(written) == 3
    for rel in written:
        text = (root / rel).read_text(encoding="utf-8")
        lines = text.splitlines()
        assert len(lines) <= 30
        assert lines[:2] == ["---", "paths:"]
        assert '  - "s' in lines[2] and lines[2].endswith('/**"')
        assert "sha256=" in text and "crew:generated" in text


def test_rules_check_reports_no_drift_right_after_generation(tmp_path):
    root = _big_repo(tmp_path)
    ci.rules(str(root))

    assert ci.rules(str(root), check=True) == ([], [])


def test_rules_check_flags_a_stale_rule_when_its_note_changes(tmp_path):
    root = _big_repo(tmp_path)
    ci.rules(str(root))
    note = root / ".crew" / "codemap" / "sub001.md"
    note.write_text(note.read_text(encoding="utf-8") + "- a new landmine.\n", encoding="utf-8")

    problems, _ = ci.rules(str(root), check=True)

    assert problems == ["stale: " + os.path.join(".claude", "rules", "sub001.md")]
    assert ci.main(["rules", "--root", str(root), "--check"]) == 1


def test_rules_check_flags_an_orphan_and_leaves_hand_written_rules_alone(tmp_path):
    root = _big_repo(tmp_path)
    ci.rules(str(root))
    (root / ".crew" / "codemap" / "sub002.md").unlink()
    hand = root / ".claude" / "rules" / "mine.md"
    hand.write_text("---\npaths:\n  - x/**\n---\nmine\n", encoding="utf-8")

    problems, _ = ci.rules(str(root), check=True)

    assert problems == ["orphan: " + os.path.join(".claude", "rules", "sub002.md")]
    assert hand.read_text(encoding="utf-8").endswith("mine\n")


def test_agents_md_stays_within_80_lines_for_a_large_code_map(tmp_path):
    root = _big_repo(tmp_path, count=120, marks=1)

    problems, written = ci.agents(str(root))

    assert (problems, written) == ([], ["AGENTS.md"])
    assert len((root / "AGENTS.md").read_text(encoding="utf-8").splitlines()) <= 80


def test_agents_md_regeneration_preserves_the_keep_block(tmp_path):
    root = _big_repo(tmp_path)
    ci.agents(str(root))
    path = root / "AGENTS.md"
    text = path.read_text(encoding="utf-8")
    start = text.index(ci.KEEP_START) + len(ci.KEEP_START)
    end = text.index(ci.KEEP_END)
    path.write_text(text[:start] + "\n- NEVER-PUSH-TO-MAIN\n" + text[end:], encoding="utf-8")
    (root / ".crew" / "codemap" / "sub000.md").unlink()

    ci.agents(str(root))

    after = path.read_text(encoding="utf-8")
    assert "- NEVER-PUSH-TO-MAIN" in after
    assert "`sub000`" not in after


def test_a_hand_written_agents_md_is_never_overwritten(tmp_path):
    root = _big_repo(tmp_path)
    (root / "AGENTS.md").write_text("# mine\n", encoding="utf-8")

    problems, written = ci.agents(str(root))

    assert written == [] and problems == ["hand-written, left alone: AGENTS.md"]
    assert (root / "AGENTS.md").read_text(encoding="utf-8") == "# mine\n"


def _registrations(hooks):
    return sorted((event, entry.get("matcher")) for event, entries in hooks["hooks"].items()
                  for entry in entries)


def test_codex_hooks_and_claude_hooks_come_from_the_same_table():
    claude = ci.claude_hooks()
    codex = ci.codex_hooks("/opt/crew")

    expected = sorted((row["event"], row["matcher"]) for row in ci.HOOK_TABLE)
    assert sorted(set(_registrations(claude))) == sorted(set(expected))
    assert sorted((e, m and next(r["matcher"] for r in ci.HOOK_TABLE if r["codex"] == m and r["event"] == e))
                  for e, m in _registrations(codex)) == expected
    assert len(_registrations(claude)) == 2 * len(ci.HOOK_TABLE)


def test_every_codex_hook_has_a_windows_command_and_passes_the_codex_harness():
    for entries in ci.codex_hooks("/opt/crew")["hooks"].values():
        for entry in entries:
            hook = entry["hooks"][0]
            assert hook["command"].endswith("--harness codex")
            assert hook["commandWindows"].endswith("-Harness codex")
            assert "crew-context.ps1" in hook["commandWindows"]


def test_claude_entries_satisfy_the_marketplace_hook_command_rules():
    for entries in ci.claude_hooks()["hooks"].values():
        for entry in entries:
            hook = entry["hooks"][0]
            assert '"${CLAUDE_PLUGIN_ROOT}' in hook["command"]
            if hook.get("shell") == "powershell":
                assert hook["command"].rstrip().endswith("exit $LASTEXITCODE")


def test_the_registered_crew_context_rows_are_exactly_the_generated_ones():
    """hooks.json is hand-formatted, so this compares parsed rows: every
    crew-context registration is what `claude-hooks` prints, event by event,
    and nothing else registers crew-context."""
    path = os.path.join(os.path.dirname(os.path.abspath(ci.__file__)), os.pardir, "hooks.json")
    with open(path, encoding="utf-8") as handle:
        registered = json.load(handle)["hooks"]
    ours = {event: [row for row in rows if "crew-context" in json.dumps(row)]
            for event, rows in registered.items()}

    assert {e: rows for e, rows in ours.items() if rows} == ci.claude_hooks()["hooks"]


def test_codex_generation_writes_both_files_and_detects_drift(tmp_path):
    root = _big_repo(tmp_path)

    assert ci.codex(str(root), "/opt/crew")[1] == [os.path.join(".codex", "hooks.json"),
                                                   os.path.join(".codex", "config.toml")]
    assert ci.codex(str(root), "/opt/crew", check=True) == ([], [])
    config = (root / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert 'project_doc_fallback_filenames = ["CLAUDE.md"]' in config
    assert '[profiles.review]\nsandbox_mode = "read-only"' in config
    assert "[profiles.work]" in config
    assert json.loads((root / ".codex" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    assert ci.codex(str(root), "/elsewhere", check=True)[0] == ["stale: " + os.path.join(".codex", "hooks.json")]


@pytest.fixture
def fake_codex(tmp_path, monkeypatch):
    path = tmp_path / "codex"
    path.write_text("#!/bin/sh\n[ \"$1\" = --version ] && echo 'codex-cli 9.9.9' && exit 0\n"
                    "echo 'hooks                                    stable             true'\n",
                    encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("CREW_CODEX_BIN", str(path))
    return path


def test_codex_probe_says_configured_not_proven_without_an_observed_invocation(tmp_path, fake_codex):
    root = _big_repo(tmp_path)
    ci.codex(str(root), "/opt/crew")

    lines = ci.codex_probe(str(root), "/opt/crew")

    assert "hooks feature: enabled" in lines
    assert "project files: current" in lines
    assert "SubagentStart: configured, not proven" in lines


def test_codex_probe_reports_an_invocation_only_as_invoked(tmp_path, fake_codex):
    root = _big_repo(tmp_path)
    log = root / ".git" / "crew" / "context-log.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text(json.dumps({"harness": "codex", "event": "SessionStart"}) + "\n", encoding="utf-8")

    lines = ci.codex_probe(str(root), "/opt/crew")

    assert "SessionStart: hook invoked 1x under Codex (delivery to the model not measured)" in lines


def test_codex_probe_without_codex_installed(monkeypatch, tmp_path):
    monkeypatch.setenv("CREW_CODEX_BIN", str(tmp_path / "nope"))

    assert ci.codex_probe(str(tmp_path), "/opt/crew") == ["codex: not installed - Codex parity not configured"]
