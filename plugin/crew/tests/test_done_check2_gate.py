"""`/crew:done` check 2's local path asks the gate, not the marker (L-0710).

WHY. Check 2 passes without a CI receipt only when HEAD itself passed every
rule here. An empty verify record plus `.crew/.verify-verified-at` naming HEAD
is NOT that evidence: both survive an uncommitted edit, because a failing Stop
run does not persist into the record and never moves the marker (Codex, L-0710
review round 2). `review_gate.gate_state` also compares the working tree's
fingerprint with the one the clean pass wrote, so check 2 runs it and needs
`GATE VERIFIED`.

These cases run the exact command `done.md` prints on a throwaway repository,
so reverting check 2 to a marker-only test (dropping the command, or the prose
that requires its VERIFIED line) turns them red.
"""

import os
import re
import subprocess
import sys

import pytest

import crew_fixtures

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
DONE = os.path.join(PLUGIN, "commands", "done.md")
# A bash proved to run here: a bare "bash" on a Windows runner is WSL's
# launcher, which prints "no installed distributions" and never runs the line.
_BASH = crew_fixtures.resolve_bash()
needs_bash = pytest.mark.skipif(_BASH is None, reason="runs done.md's bash line")


def _env(home):
    """No GIT_* from the caller (a hook's GIT_DIR would point the fixture's git
    at the real repository), and a throwaway HOME so no user config is read."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(HOME=str(home), GIT_CONFIG_NOSYSTEM="1")
    return env


def _shim_env(home):
    """`_env`, plus a `python3` on PATH that is this interpreter: Git Bash on
    Windows ships without one, and done.md's line names `python3`."""
    shim = home / "shim-bin"
    shim.mkdir(exist_ok=True)
    exe = sys.executable.replace("\\", "/")
    with open(shim / "python3", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f'#!/bin/sh\nexec "{exe}" "$@"\n')
    os.chmod(shim / "python3", 0o755)
    env = _env(home)
    env["PATH"] = str(shim) + os.pathsep + env.get("PATH", "")
    return env


def _check2():
    with open(DONE, encoding="utf-8", errors="strict") as fh:
        text = fh.read()
    start = text.index("## Check 2")
    return text[start:text.index("## Check 3", start)]


def _gate_command():
    lines = [line for line in _check2().splitlines() if "review_gate.gate_state" in line]
    assert len(lines) == 1, "done.md check 2 must run review_gate.gate_state exactly once"
    return lines[0].replace("${CLAUDE_PLUGIN_ROOT}", PLUGIN.replace("\\", "/"))


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True,
                          encoding="utf-8", errors="strict", stdin=subprocess.DEVNULL,
                          timeout=60, env=_env(root.parent)).stdout


@pytest.fixture(name="verified_repo")
def _verified_repo(tmp_path):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    (root / ".crew" / "verify.json").write_text('{"rules": []}\n', encoding="utf-8")
    (root / "app.py").write_text("print('ok')\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@example.com", "add", "-A")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "base")
    head = _git(root, "rev-parse", "HEAD").strip()
    (root / ".crew" / ".verify-verified-at").write_text(head + "\n", encoding="utf-8")
    (root / ".crew" / ".verify-gate.record.json").write_text('{"rules": {}}\n', encoding="utf-8")
    return root, head


def _gate_line(root):
    out = subprocess.run([_BASH, "-c", _gate_command()], cwd=root, encoding="utf-8",
                         errors="strict", capture_output=True, stdin=subprocess.DEVNULL,
                         timeout=60, check=False, env=_shim_env(root.parent))
    lines = [line for line in out.stdout.splitlines() if line.startswith("GATE ")]
    assert lines, f"no GATE line: rc={out.returncode} stdout={out.stdout!r} stderr={out.stderr!r}"
    return lines[-1]


def test_check2_requires_the_gate_line_to_read_verified():
    text = " ".join(_check2().split())

    assert "the `GATE` line reads `VERIFIED`" in text


@needs_bash
def test_gate_line_reads_verified_on_the_clean_tree_the_pass_left(verified_repo):
    root, _ = verified_repo

    assert _gate_line(root).startswith("GATE VERIFIED ")


@needs_bash
def test_an_uncommitted_edit_after_the_pass_is_not_verified(verified_repo):
    root, head = verified_repo
    (root / "app.py").write_text("raise SystemExit(1)\n", encoding="utf-8")
    marker_only = ((root / ".crew" / ".verify-verified-at").read_text(encoding="utf-8").strip() == head
                   and re.fullmatch(r'\{"rules": \{\}\}\s*',
                                    (root / ".crew" / ".verify-gate.record.json").read_text(encoding="utf-8")))

    line = _gate_line(root)

    assert (bool(marker_only), line.split()[1]) == (True, "UNVERIFIED")
