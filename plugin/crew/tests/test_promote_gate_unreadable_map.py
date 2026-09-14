"""A deployment map crew cannot read must not read as "not a deployment".

`promote-gate.sh` caught every failure of its own env-resolution step with
`except Exception: sys.exit(0)`, and read the empty output that followed as "this
command deploys nothing". So a single stray comma in `.crew/verify.json` removed
every pre-deploy gate -- requires, rollback, requireHuman, clean tree -- with no
output, exit 0, and behaviour byte-identical to an unrelated command. The same
collapse sat one level in: `environments` holding a list instead of an object
found no environment in it and permitted for the same reason.

An ABSENT `verify.json` is a repo that opted out of deploy gating and still
exits 0. That distinction is the whole point: absent is a decision somebody
made, unreadable is a file nobody can read, and the two were one answer.

Both flavours, with one asymmetry stated rather than smoothed over: PowerShell
7's `ConvertFrom-Json` ACCEPTS a trailing comma where python's `json` rejects
it, so the stray comma that motivated this work is caught by the bash flavour
and parses cleanly in the PowerShell one. It is asserted below for bash only.
Closing that gap would mean shipping a second JSON parser; what matters is that
neither flavour treats a map it could not read as a map that gates nothing, and
both are checked for that on the inputs they can both see.

SABOTAGE-TEST THIS FILE before trusting it: see `sabotage.py`.
"""
import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

_HOOKS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      os.pardir, "hooks", "scripts")
_GATE_SH = os.path.join(_HOOKS, "promote-gate.sh").replace("\\", "/")
_GATE_PS1 = os.path.join(_HOOKS, "promote-gate.ps1")

_BASH = crew_fixtures.resolve_bash()
_PWSH = crew_fixtures.resolve_pwsh()
needs_bash = pytest.mark.skipif(_BASH is None, reason="no MSYS/POSIX bash")
needs_pwsh = pytest.mark.skipif(
    not sys.platform.startswith("win") or _PWSH is None,
    reason="promote-gate.ps1 is the native-Windows flavour; needs Windows + pwsh")

_DEPLOY = "deploy-prod"

# One environment that passes every gate it declares, so any exit 2 below is
# about the map being unreadable and nothing else.
_GOOD = {"environments": {"prod": {
    "deploy": [_DEPLOY], "rollback": "none",
    "rollbackReason": "the fixture deploys nothing"}}}

# Every shape that must BLOCK in both flavours. Keyed by what is wrong with it,
# because the label is what a failure report will show.
_UNREADABLE = {
    "not json at all": "{ not json, half-edited",
    "truncated": '{ "environments": { "prod": ',
    "top level list": "[1, 2, 3]",
    "environments is a list": json.dumps({"environments": [{"prod": {}}]}),
    "environments is a string": json.dumps({"environments": "prod"}),
    "an environment is a number": json.dumps({"environments": {"prod": 7}}),
    "deploy is a number": json.dumps({"environments": {"prod": {
        "deploy": 7, "rollback": "none", "rollbackReason": "x"}}}),
}


def _fixture(tmp_path, body, name="repo"):
    """A clean, committed repo whose `.crew/verify.json` holds `body`.

    Committing matters and so does the .gitignore: leave the tree dirty and the
    gate's clean-tree check fires first and blocks for a different reason
    entirely, which reads as "the gate works" while proving nothing about this.
    `body=None` writes no map at all.
    """
    root = tmp_path / name
    (root / ".crew").mkdir(parents=True)
    (root / ".work").mkdir()
    for args in (["init", "-q"],
                 ["config", "user.email", "t@example.invalid"],
                 ["config", "user.name", "T"]):
        subprocess.run(["git"] + args, cwd=root, check=False,
                       capture_output=True, text=True,
                       stdin=subprocess.DEVNULL)
    (root / ".gitignore").write_text(".crew/\n.work/\n", encoding="utf-8")
    (root / "README.md").write_text("x\n", encoding="utf-8")
    if body is not None:
        (root / ".crew" / "verify.json").write_text(body, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=False,
                   capture_output=True, text=True, stdin=subprocess.DEVNULL)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=root,
                   check=False, capture_output=True, text=True,
                   stdin=subprocess.DEVNULL)
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=root,
                           capture_output=True, text=True, check=False,
                           stdin=subprocess.DEVNULL).stdout
    assert dirty.strip() == "", f"fixture tree must be clean, got: {dirty!r}"
    return root


def _sh(root, command=_DEPLOY):
    payload = json.dumps({"tool_name": "Bash",
                          "tool_input": {"command": command}})
    return subprocess.run(
        [_BASH, _GATE_SH], input=payload, capture_output=True, text=True,
        check=False, cwd=str(root),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)))


def _ps1(root, command=_DEPLOY):
    payload = json.dumps({"tool_name": "PowerShell",
                          "tool_input": {"command": command}})
    return subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", _GATE_PS1],
        input=payload, capture_output=True, text=True, check=False,
        cwd=str(root), env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)))


def _marker(root):
    return (root / ".crew" / ".deploy-in-flight").exists()


# --- must block ------------------------------------------------------------


@needs_bash
@pytest.mark.parametrize("label", sorted(_UNREADABLE))
def test_sh_blocks_on_a_map_it_cannot_read(tmp_path, label):
    root = _fixture(tmp_path, _UNREADABLE[label])

    proc = _sh(root)

    assert proc.returncode == 2, f"{label}: exit {proc.returncode}"
    assert "PROMOTION BLOCKED" in proc.stderr
    assert "NOT a pass" in proc.stderr
    assert not _marker(root), "a blocked deploy must leave no in-flight marker"


@needs_bash
def test_sh_blocks_on_the_stray_comma_that_started_this(tmp_path):
    """The exact trigger from the ticket: one comma, in a file that otherwise
    declares a complete and valid environment. Asserted for bash only -- see
    the module docstring on ConvertFrom-Json."""
    body = json.dumps(_GOOD)[:-1] + ",}"
    root = _fixture(tmp_path, body)

    proc = _sh(root)

    assert proc.returncode == 2, proc.stderr
    assert "does not parse as JSON" in proc.stderr
    assert not _marker(root)


@needs_bash
def test_sh_blocks_when_the_map_is_not_a_file_at_all(tmp_path):
    """A directory named `.crew/verify.json`. The test for the map's presence
    was `-f`, which answers false for a directory, so this exited 0 as though
    the repo had opted out of gating. `-e` sends it to the read, which fails
    and says so."""
    root = _fixture(tmp_path, None)
    (root / ".crew" / "verify.json").mkdir()

    proc = _sh(root)

    assert proc.returncode == 2, proc.stderr
    assert "could not be read" in proc.stderr


@needs_pwsh
@pytest.mark.parametrize("label", sorted(_UNREADABLE))
def test_ps1_blocks_on_a_map_it_cannot_read(tmp_path, label):
    root = _fixture(tmp_path, _UNREADABLE[label])

    proc = _ps1(root)

    assert proc.returncode == 2, f"{label}: exit {proc.returncode}"
    assert "PROMOTION BLOCKED" in proc.stderr
    assert "NOT a pass" in proc.stderr
    assert not _marker(root)


@needs_pwsh
def test_ps1_blocks_when_the_map_is_not_a_file_at_all(tmp_path):
    """`Get-Content` fails NON-TERMINATINGLY without `-ErrorAction Stop`, so
    the catch never fired, `$vm` stayed null, and `-not $vm.environments` read
    the corruption as "no environments declared" -- exit 0, with a red
    PowerShell error on stderr and the deploy allowed."""
    root = _fixture(tmp_path, None)
    (root / ".crew" / "verify.json").mkdir()

    proc = _ps1(root)

    assert proc.returncode == 2, proc.stderr
    assert "PROMOTION BLOCKED" in proc.stderr
    # WHICH line refused matters, not only that one did. The null $vm also
    # trips the "does not hold a JSON object" check two lines further down, so
    # asserting the exit code alone would pass with `-ErrorAction Stop`
    # removed -- the belt tested while the braces held. Pinning the message
    # keeps "crew could not OPEN the file" distinct from "the file's contents
    # are the wrong shape", which are different things for the reader to fix.
    assert "could not be read or parsed" in proc.stderr


# --- must allow ------------------------------------------------------------


@needs_bash
def test_sh_an_absent_map_is_still_an_opt_out(tmp_path):
    """The distinction the fix rests on. A repo that never wrote a verify.json
    is not gated, and turning that into a refusal would make every deploy in
    every ungated repo fail."""
    root = _fixture(tmp_path, None)

    assert _sh(root).returncode == 0


@needs_bash
def test_sh_a_readable_map_still_gates_and_still_allows(tmp_path):
    """The control that stops "block everything" passing as a fix: the gate
    must still run the real checks and still allow when they are met, and it
    must still record the deploy for the Stop gate."""
    root = _fixture(tmp_path, json.dumps(_GOOD))

    proc = _sh(root)

    assert proc.returncode == 0, proc.stderr
    assert _marker(root), "an allowed deploy must record itself"


@needs_bash
def test_sh_an_unrelated_command_passes_straight_through(tmp_path):
    root = _fixture(tmp_path, json.dumps(_GOOD))

    assert _sh(root, "npm test").returncode == 0
    assert not _marker(root)


@needs_bash
def test_sh_a_string_deploy_matches_the_whole_string_not_its_letters(tmp_path):
    """`deploy: "deploy-prod"` -- a string where the schema shows a list -- was
    iterated CHARACTER BY CHARACTER, so `"d" in cmd` matched any command with a
    `d` in it. `echo done` was therefore treated as a deploy to production: it
    ran the whole gate and wrote `.crew/.deploy-in-flight`, which the Stop gate
    then demands a PROMOTIONS row for. Both halves are asserted -- the string
    still matches its own command, and an unrelated one no longer does --
    because dropping the string form entirely would break every map that uses
    it, the PowerShell flavour included.
    """
    body = json.dumps({"environments": {"prod": {
        "deploy": _DEPLOY, "rollback": "none", "rollbackReason": "x"}}})
    root = _fixture(tmp_path, body)

    assert _sh(root, "echo done").returncode == 0
    assert not _marker(root), "`echo done` deploys nothing"

    assert _sh(root, _DEPLOY).returncode == 0
    assert _marker(root), "the declared command must still be recognised"


@needs_pwsh
def test_ps1_an_absent_map_is_still_an_opt_out(tmp_path):
    root = _fixture(tmp_path, None)

    assert _ps1(root).returncode == 0


@needs_pwsh
def test_ps1_a_readable_map_still_gates_and_still_allows(tmp_path):
    root = _fixture(tmp_path, json.dumps(_GOOD))

    proc = _ps1(root)

    assert proc.returncode == 0, proc.stderr
    assert _marker(root)


@needs_pwsh
def test_ps1_an_unrelated_command_passes_straight_through(tmp_path):
    root = _fixture(tmp_path, json.dumps(_GOOD))

    assert _ps1(root, "npm test").returncode == 0
    assert not _marker(root)


@needs_pwsh
def test_ps1_a_string_deploy_is_one_command(tmp_path):
    body = json.dumps({"environments": {"prod": {
        "deploy": _DEPLOY, "rollback": "none", "rollbackReason": "x"}}})
    root = _fixture(tmp_path, body)

    assert _ps1(root, "echo done").returncode == 0
    assert not _marker(root)
    assert _ps1(root, _DEPLOY).returncode == 0
    assert _marker(root)
