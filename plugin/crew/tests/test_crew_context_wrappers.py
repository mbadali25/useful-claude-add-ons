"""crew-context.sh: the wrapper is non-blocking.

For every payload shape -- valid events, garbage, empty stdin, a non-crew
directory -- the wrapper exits 0, and its stdout is either empty or a single
`hookSpecificOutput` object with no `decision`.
"""
import json
import os
import pathlib
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
from context_fixtures import make_repo, payload

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "hooks" / "scripts"
# A bare "bash" can resolve to WSL's system32 copy, which cannot open a
# Windows path at all (see crew_fixtures.resolve_bash's docstring) --
# resolved and proved once here, same as every other flavour-paired suite.
BASH = crew_fixtures.resolve_bash()
needs_bash = pytest.mark.skipif(BASH is None, reason="bash not installed - the sh flavour was NOT run")


def _payloads(root):
    return [
        b"",
        b"{not json",
        json.dumps(payload("SessionStart", root, source="startup")).encode(),
        json.dumps(payload("UserPromptSubmit", root, prompt="alpha please", prompt_id="w1")).encode(),
        json.dumps(payload("PostToolUse", root, tool_name="Edit",
                           tool_input={"file_path": str(root / "src" / "alpha" / "core.py")})).encode(),
        json.dumps(payload("SubagentStart", root, agent_id="a", agent_type="explorer")).encode(),
        json.dumps(payload("Stop", root)).encode(),
    ]


def _env(tmp_path, **extra):
    env = dict(os.environ, CREW_VAULT_OPS=str(tmp_path / "absent.py"),
               CREW_OBSIDIAN_CONFIG=str(tmp_path / "absent.json"))
    env.pop("CLAUDE_PROJECT_DIR", None)
    env.update(extra)
    return env


def _assert_non_blocking(done):
    assert done.returncode == 0, done.stderr
    out = done.stdout.strip()
    if out:
        parsed = json.loads(out)
        assert set(parsed) == {"hookSpecificOutput"}
        assert "decision" not in out and '"continue"' not in out


@needs_bash
def test_bash_flavour_always_exits_zero_and_never_decides(tmp_path):
    root = make_repo(tmp_path)
    emitted = 0
    for raw in _payloads(root):
        done = subprocess.run([BASH, str(SCRIPTS / "crew-context.sh")], input=raw, cwd=root,
                              capture_output=True, env=_env(tmp_path), check=False, timeout=60)
        done.stdout, done.stderr = done.stdout.decode(), done.stderr.decode()
        _assert_non_blocking(done)
        emitted += bool(done.stdout.strip())

    assert emitted >= 3


@needs_bash
@pytest.mark.parametrize("config,inject", [
    ({"memory": {"mode": "repo"}}, False),
    (None, False),
])
def test_bash_flavour_emits_and_logs_nothing_when_inject_is_false(tmp_path, config, inject):
    root = make_repo(tmp_path, config=config, inject=inject)
    outputs = []

    for raw in _payloads(root):
        done = subprocess.run([BASH, str(SCRIPTS / "crew-context.sh")], input=raw, cwd=root,
                              capture_output=True, env=_env(tmp_path), check=False, timeout=60)
        outputs.append((done.returncode, done.stdout, done.stderr))

    assert (outputs, (root / ".git" / "crew" / "context-log.jsonl").exists()) == \
        ([(0, b"", b"")] * len(outputs), False)


@needs_bash
@pytest.mark.parametrize("config,inject", [
    (None, True),
    (None, None),
    ({"memory": {"mode": "repo"}}, None),
])
def test_bash_flavour_emits_when_inject_is_on_or_unset(tmp_path, config, inject):
    root = make_repo(tmp_path, config=config, inject=inject)
    start = json.dumps(payload("SessionStart", root, source="startup")).encode()

    done = subprocess.run([BASH, str(SCRIPTS / "crew-context.sh")], input=start, cwd=root,
                          capture_output=True, env=_env(tmp_path), check=False, timeout=60)

    assert "additionalContext" in json.loads(done.stdout)["hookSpecificOutput"]


@needs_bash
def test_bash_flavour_passes_the_codex_harness_through(tmp_path):
    root = make_repo(tmp_path)

    done = subprocess.run([BASH, str(SCRIPTS / "crew-context.sh"), "--harness", "codex"],
                          input=_payloads(root)[3], cwd=root, capture_output=True,
                          env=_env(tmp_path), check=False, timeout=60)
    log = (root / ".git" / "crew" / "context-log.jsonl").read_text(encoding="utf-8")

    assert done.returncode == 0
    assert json.loads(log.splitlines()[-1])["harness"] == "codex"


@needs_bash
def test_bash_flavour_exits_zero_when_python_crashes(tmp_path):
    root = make_repo(tmp_path)
    (root / ".crew" / "config.json").write_text("{", encoding="utf-8")
    done = subprocess.run([BASH, str(SCRIPTS / "crew-context.sh"), "--harness", "not-a-harness"],
                          input=b"{}", cwd=root, capture_output=True, env=_env(tmp_path), check=False,
                          timeout=60)

    assert done.returncode == 0


@pytest.mark.parametrize("name", ["crew-context.sh", "crew_context.py",
                                  "crew_recall.py", "crew_instructions.py"])
def test_wrappers_and_modules_are_lf_only(name):
    assert b"\r\n" not in (SCRIPTS / name).read_bytes()
