"""crew-context.sh / crew-context.ps1: both flavours are non-blocking.

For every payload shape -- valid events, garbage, empty stdin, a non-crew
directory -- each wrapper exits 0, and its stdout is either empty or a single
`hookSpecificOutput` object with no `decision`. The .ps1 half needs pwsh; off
a host that has it those cases skip and say so.
"""
import json
import os
import pathlib
import shutil
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
from context_fixtures import make_repo, payload

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "hooks" / "scripts"
PWSH = shutil.which("pwsh")


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


def test_bash_flavour_always_exits_zero_and_never_decides(tmp_path):
    root = make_repo(tmp_path)
    emitted = 0
    for raw in _payloads(root):
        done = subprocess.run(["bash", str(SCRIPTS / "crew-context.sh")], input=raw, cwd=root,
                              capture_output=True, env=_env(tmp_path), check=False)
        done.stdout, done.stderr = done.stdout.decode(), done.stderr.decode()
        _assert_non_blocking(done)
        emitted += bool(done.stdout.strip())

    assert emitted >= 3


@pytest.mark.parametrize("config,inject", [
    (None, None),
    ({"memory": {"mode": "repo"}}, None),
    (None, False),
])
def test_bash_flavour_emits_and_logs_nothing_unless_inject_is_true(tmp_path, config, inject):
    root = make_repo(tmp_path, config=config, inject=inject)
    outputs = []

    for raw in _payloads(root):
        done = subprocess.run(["bash", str(SCRIPTS / "crew-context.sh")], input=raw, cwd=root,
                              capture_output=True, env=_env(tmp_path), check=False)
        outputs.append((done.returncode, done.stdout, done.stderr))

    assert (outputs, (root / ".git" / "crew" / "context-log.jsonl").exists()) == \
        ([(0, b"", b"")] * len(outputs), False)


def test_bash_flavour_emits_when_inject_is_true(tmp_path):
    root = make_repo(tmp_path, inject=True)
    start = json.dumps(payload("SessionStart", root, source="startup")).encode()

    done = subprocess.run(["bash", str(SCRIPTS / "crew-context.sh")], input=start, cwd=root,
                          capture_output=True, env=_env(tmp_path), check=False)

    assert "additionalContext" in json.loads(done.stdout)["hookSpecificOutput"]


def test_bash_flavour_exits_zero_when_python_crashes(tmp_path):
    root = make_repo(tmp_path)
    (root / ".crew" / "config.json").write_text("{", encoding="utf-8")
    done = subprocess.run(["bash", str(SCRIPTS / "crew-context.sh"), "--harness", "not-a-harness"],
                          input=b"{}", cwd=root, capture_output=True, env=_env(tmp_path), check=False)

    assert done.returncode == 0


@pytest.mark.skipif(PWSH is None, reason="pwsh not installed - the .ps1 flavour was NOT run")
def test_powershell_flavour_always_exits_zero_and_never_decides(tmp_path):
    root = make_repo(tmp_path)
    emitted = 0
    for raw in _payloads(root):
        done = subprocess.run([PWSH, "-NoProfile", "-File", str(SCRIPTS / "crew-context.ps1")],
                              input=raw, cwd=root, capture_output=True,
                              env=_env(tmp_path, OS="Windows_NT"), check=False, timeout=60)
        done.stdout, done.stderr = done.stdout.decode(), done.stderr.decode()
        _assert_non_blocking(done)
        emitted += bool(done.stdout.strip())

    assert emitted >= 3


@pytest.mark.skipif(PWSH is None, reason="pwsh not installed - the .ps1 flavour was NOT run")
def test_powershell_flavour_stands_down_off_windows(tmp_path):
    root = make_repo(tmp_path)
    env = _env(tmp_path)
    env.pop("OS", None)
    done = subprocess.run([PWSH, "-NoProfile", "-File", str(SCRIPTS / "crew-context.ps1")],
                          input=_payloads(root)[2], cwd=root, capture_output=True, env=env,
                          check=False, timeout=60)

    assert (done.returncode, done.stdout, done.stderr) == (0, b"", b"")


@pytest.mark.skipif(PWSH is None, reason="pwsh not installed - the .ps1 flavour was NOT run")
def test_powershell_flavour_passes_the_codex_harness_through(tmp_path):
    root = make_repo(tmp_path)
    done = subprocess.run([PWSH, "-NoProfile", "-File", str(SCRIPTS / "crew-context.ps1"), "-Harness", "codex"],
                          input=_payloads(root)[3], cwd=root, capture_output=True,
                          env=_env(tmp_path, OS="Windows_NT"), check=False, timeout=60)
    log = (root / ".git" / "crew" / "context-log.jsonl").read_text(encoding="utf-8")

    assert done.returncode == 0
    assert json.loads(log.splitlines()[-1])["harness"] == "codex"


def _resolver(path):
    src = path.read_text(encoding="utf-8")
    start = src.index("function Resolve-CrewPython {")
    return src[start:src.index("\n}\n", start) + 3]


def test_the_powershell_resolver_is_byte_for_byte_role_write_guards():
    assert _resolver(SCRIPTS / "crew-context.ps1") == _resolver(SCRIPTS / "role-write-guard.ps1")


def test_the_flavour_guard_is_the_first_executable_statement():
    code = [l for l in (SCRIPTS / "crew-context.ps1").read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.lstrip().startswith("#")]
    after_param = code[code.index(")") + 1]

    assert after_param == "if ($env:OS -ne 'Windows_NT') { exit 0 }"


@pytest.mark.parametrize("name", ["crew-context.sh", "crew-context.ps1", "crew_context.py",
                                  "crew_recall.py", "crew_instructions.py"])
def test_wrappers_and_modules_are_lf_only(name):
    assert b"\r\n" not in (SCRIPTS / name).read_bytes()
