"""The verify gate runs every rule command with CLAUDE_PLUGIN_ROOT set.

A verify.json rule may call a crew script through it -- the AGENTS.md drift
check does -- and it must resolve the same way under the Stop hook (Claude
Code exports it to hook processes) and under `/crew:verify --all`, which the
Bash tool runs with the variable substituted into the command text but not
exported. MUST-ALLOW: unset or empty, the gate sets it to its own plugin root,
also when the gate was started by a relative path from another directory.
MUST NOT: a value the caller already set is never replaced.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

import crew_fixtures

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_SH = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")
_PS1 = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.ps1")
_BASH = crew_fixtures.resolve_bash()
_PWSH = shutil.which("pwsh")

_FLAVOURS = [
    pytest.param("sh", marks=pytest.mark.skipif(_BASH is None, reason="needs bash")),
    pytest.param("ps1", marks=pytest.mark.skipif(
        not sys.platform.startswith("win") or _PWSH is None,
        reason="the .ps1 gate is the native-Windows flavour")),
]


def _repo(tmp_path, out):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    for args in (("init", "-q"), ("config", "user.email", "t@example.invalid"),
                 ("config", "user.name", "t")):
        subprocess.run(("git",) + args, cwd=root, check=True, capture_output=True,
                       timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    (root / "README.md").write_text("committed", encoding="utf-8")
    subprocess.run(("git", "add", "-A"), cwd=root, check=True, capture_output=True,
                   timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    subprocess.run(("git", "commit", "-q", "-m", "fixture"), cwd=root, check=True,
                   capture_output=True, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    (root / "a.py").write_text("x = 1", encoding="utf-8")
    rule = {"paths": ["a.py"], "seconds": 1, "reach": "local", "why": "echo the root",
            # Read from a CHILD process's environment, the way a real rule's
            # `python3` sees it: an unexported shell variable is visible to
            # the gate's own shell but not to a child.
            "run": [f"{{ env | grep '^CLAUDE_PLUGIN_ROOT=' | cut -d= -f2- | tr -d '\\n'; }} "
                    f"> '{out}'"]}
    (root / ".crew" / "verify.json").write_text(json.dumps(
        {"version": 1, "rules": [rule], "default": [], "unmapped": "ignore"}), encoding="utf-8")
    return root


def _run(flavour, root, plugin_root=None, script=None, cwd=None):
    if flavour == "sh":
        cmd = [_BASH, script or _SH]
    else:
        cmd = [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1]
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    if plugin_root is not None:
        env["CLAUDE_PLUGIN_ROOT"] = plugin_root
    return crew_fixtures.run_gate(cmd, input="{}", cwd=str(cwd or root), env=env,
                                  capture_output=True, text=True, check=False,
                                  timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


def _own_root(out, done):
    got = out.read_text(encoding="utf-8")
    assert got, "the rule's child process saw no CLAUDE_PLUGIN_ROOT. " + done.stderr
    assert os.path.samefile(got, _ROOT), (got, _ROOT)


@pytest.mark.parametrize("given", [None, ""], ids=["unset", "empty"])
@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_an_unset_plugin_root_is_the_gates_own(flavour, given, tmp_path):
    """MUST-ALLOW: the `/crew:verify --all` case, nothing (or nothing usable)
    exported. On Git Bash the value must be one a native python can open."""
    out = tmp_path / "root.txt"
    root = _repo(tmp_path, out)

    done = _run(flavour, root, plugin_root=given)

    assert done.returncode == 0, done.stderr
    _own_root(out, done)


@pytest.mark.skipif(_BASH is None, reason="needs bash")
def test_a_gate_started_by_a_relative_path_still_finds_its_root(tmp_path):
    """MUST-ALLOW: `bash hooks/scripts/verify-gate.sh` from the plugin dir. The
    gate cd's into the project before the rules run, where that relative path
    no longer resolves; resolved there, the root came out as `/`."""
    out = tmp_path / "root.txt"
    root = _repo(tmp_path, out)

    done = _run("sh", root, script=os.path.join("hooks", "scripts", "verify-gate.sh"),
                cwd=_ROOT)

    assert done.returncode == 0, done.stderr
    _own_root(out, done)


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_plugin_root_the_caller_set_is_kept(flavour, tmp_path):
    """MUST NOT replace: the hook case, where Claude Code set it."""
    out = tmp_path / "root.txt"
    root = _repo(tmp_path, out)
    mine = str(tmp_path / "somewhere-else")

    done = _run(flavour, root, plugin_root=mine)

    assert done.returncode == 0, done.stderr
    assert out.read_text(encoding="utf-8") == mine, done.stderr
