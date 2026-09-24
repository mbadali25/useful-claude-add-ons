"""`/crew:onboard` and `/crew:migrate` are what generate `.claude/rules/`.

`crew_instructions.py rules` had no caller: nothing in commands, skills or
hooks ran it, so the generated rules the redesign promises were never written
in a consuming repo. The two commands are prose, so the call they make IS the
code path. These tests pull the exact `crew_instructions.py ... rules` line out
of each command file's bash fences and run it, verbatim, in a throwaway repo:
delete or break that line and the tests below go red, not just a grep.

    python3 -m pytest plugin/crew/tests/test_rules_generation_path.py -q
"""
import os
import re
import subprocess
import sys

import context  # noqa: F401  pylint: disable=unused-import
from context_fixtures import make_repo

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ONBOARD = os.path.join(CREW, "commands", "onboard.md")
MIGRATE = os.path.join(CREW, "commands", "migrate.md")
RULES_CALL = re.compile(r'crew_instructions\.py"?\s+rules\b')


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _fenced_commands(text):
    """Every line inside a ```bash fence, in document order."""
    out, inside = [], False
    for line in text.splitlines():
        if line.startswith("```"):
            inside = line.strip() == "```bash" if not inside else False
            continue
        if inside and line.strip():
            out.append(line.strip())
    return out


def _rules_calls(path, check):
    return [c for c in _fenced_commands(_read(path))
            if RULES_CALL.search(c) and ("--check" in c.split()) == check]


def _run(command, root):
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=CREW)
    env.pop("CLAUDE_PROJECT_DIR", None)
    command = command.replace("python3 ", f'"{sys.executable}" ', 1)
    return subprocess.run(["bash", "-c", command], cwd=str(root), env=env,
                          capture_output=True, text=True, check=False)


def _repo(tmp_path):
    return make_repo(tmp_path, subsystems={
        "alpha": (["src/alpha/core.py", "src/alpha/util.py", "src/alpha/io.py"],
                  ["ALPHA-LANDMINE the cache is never invalidated"]),
    })


def _check(root):
    return _run(f'python3 "{CREW}/hooks/scripts/crew_instructions.py" rules --root . --check', root)


def test_onboard_runs_exactly_one_rules_generation_call():
    assert len(_rules_calls(ONBOARD, check=False)) == 1


def test_onboard_refresh_path_reaches_the_rules_step():
    refresh = _read(ONBOARD).split("## `--refresh <subsystem>`", 1)[1]

    assert "Then run step 6." in refresh


def test_onboard_call_writes_a_scoped_hashed_rule_within_budget(tmp_path):
    root = _repo(tmp_path)

    done = _run(_rules_calls(ONBOARD, check=False)[0], root)

    rule = root / ".claude" / "rules" / "alpha.md"
    lines = rule.read_text(encoding="utf-8").splitlines()
    assert done.returncode == 0, done.stdout + done.stderr
    assert "wrote " + os.path.join(".claude", "rules", "alpha.md") in done.stdout
    assert len(lines) <= 30
    assert lines[:3] == ["---", "paths:", '  - "src/alpha/**"']
    assert "sha256=" in rule.read_text(encoding="utf-8")


def test_a_note_edited_after_onboard_drifts_until_onboard_runs_again(tmp_path):
    root = _repo(tmp_path)
    call = _rules_calls(ONBOARD, check=False)[0]
    _run(call, root)
    note = root / ".crew" / "codemap" / "alpha.md"
    note.write_text(note.read_text(encoding="utf-8") + "- a second landmine.\n", encoding="utf-8")

    stale = _check(root)
    _run(call, root)
    fresh = _check(root)

    assert (stale.returncode, fresh.returncode) == (1, 0)
    assert "stale: " + os.path.join(".claude", "rules", "alpha.md") in stale.stdout


def test_onboard_call_leaves_a_hand_written_rule_alone_and_says_so(tmp_path):
    root = _repo(tmp_path)
    hand = root / ".claude" / "rules" / "alpha.md"
    hand.parent.mkdir(parents=True)
    hand.write_text("mine\n", encoding="utf-8")

    done = _run(_rules_calls(ONBOARD, check=False)[0], root)

    assert hand.read_text(encoding="utf-8") == "mine\n"
    assert "hand-written, left alone: " + os.path.join(".claude", "rules", "alpha.md") in done.stdout


def test_migrate_preview_lists_the_rules_and_writes_nothing(tmp_path):
    root = _repo(tmp_path)
    previews = _rules_calls(MIGRATE, check=True)

    done = _run(previews[0], root)

    assert len(previews) == 1
    assert "missing: " + os.path.join(".claude", "rules", "alpha.md") in done.stdout
    assert not (root / ".claude").exists()


def test_migrate_apply_generates_the_rules_after_crew_migrate_applies(tmp_path):
    root = _repo(tmp_path)
    commands = _fenced_commands(_read(MIGRATE))
    apply_at = next(i for i, c in enumerate(commands) if "crew_migrate.py" in c and "--apply" in c)
    generate = [i for i in range(len(commands))
                if commands[i] in _rules_calls(MIGRATE, check=False)]

    done = _run(commands[generate[0]], root)

    assert len(generate) == 1 and generate[0] > apply_at
    assert done.returncode == 0, done.stdout + done.stderr
    assert (root / ".claude" / "rules" / "alpha.md").is_file()
    assert _check(root).returncode == 0
