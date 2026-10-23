"""A rule's `eval`'d command must not inherit the gate's own variables.

verify-gate.sh's variables (`c`, the rule's command text; `RULE_OUT_FILE`,
its capture path; `CMDS`; every other name the script assigns) are plain,
un-exported shell variables, so a rule that does `env | grep ...`, or a
script it shells out to that dumps its own environment for diagnostics, never
sees its own source text or output path as if they were legitimate input.
The test below pins that for every variable verify-gate.sh assigns, derived
from the script (and the helpers it sources) so a new gate variable is
covered the day it is added.

History: verify-gate.ps1 (deleted in L-0869) handed each rule's command text
to bash through two env vars, `CREW_VERIFY_RULE_CMD` and
`CREW_VERIFY_RULE_OUT`, because `eval` inherits positional parameters and
interpolating a rule command into a script string is an injection shape. That
leaked both into the rule's own environment until the wrapper copied them to
local shell variables and `unset` them before `eval`. A test drove that
carrier directly and went with the script. The sh gate never set those two
names, so it could never leak them.
"""
import json
import os
import re
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

_ROOT = context._ROOT  # pylint: disable=protected-access
_VERIFY_SH = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")
_BASH = crew_fixtures.resolve_bash()

_PY = "'" + sys.executable.replace("\\", "/").replace("'", "'\\''") + "'"


def _git(root, *args):
    subprocess.run(("git",) + args, cwd=root, check=True,
                   capture_output=True, text=True, stdin=subprocess.DEVNULL,
                   timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


def _repo(tmp_path, run_entry):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / "README.md").write_text("committed\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    (root / "changed.py").write_text("x = 1\n", encoding="utf-8")
    verify = {"version": 1, "rules": [
        {"paths": ["changed.py"], "reach": "local", "run": [run_entry]}
    ], "always": [], "default": [], "unmapped": "warn"}
    (root / ".crew" / "verify.json").write_text(json.dumps(verify), encoding="utf-8")
    return root


# Every name verify-gate.sh (and each helper it sources with `. "$(dirname
# ...)/<file>.sh"`) assigns: `NAME=`, `local NAME=`, `for NAME in`,
# `read [-flags] NAME...`. Derived from the scripts rather than listed here,
# so a new gate variable is covered the day it is added. Over-inclusive on
# purpose -- embedded Python keyword arguments and words after "read" in
# prose land in the set too, and each only costs a name that must not
# appear in a rule's environment, which none of them do.
_ASSIGN_RE = re.compile(
    r"(?:^|[\s;&|(])(?:local\s+|readonly\s+)?([A-Za-z_][A-Za-z0-9_]*)=")
_FOR_RE = re.compile(r"\bfor\s+([A-Za-z_][A-Za-z0-9_]*)\s+in\b")
_READ_RE = re.compile(r"\bread\s+(?:-[A-Za-z]+\s+)*((?:[A-Za-z_][A-Za-z0-9_]*\s*)+)")
_SOURCED_RE = re.compile(r'^\s*\.\s+"\$\(dirname "\$\{BASH_SOURCE\[0\]\}"\)/([\w.-]+\.sh)"',
                         re.MULTILINE)

# Exported by the gate ON PURPOSE, so a rule inherits it: `export PATH`
# after prepending the python3 shim dir (verify-gate.sh, "PATH=\"$SHIM_DIR:$PATH\"").
# The per-rule pinned vars (`export "$VAR=$VAL"`: ENV, AWS_PROFILE, ...) are
# never assigned as `NAME=` in the script, so they are not in the derived set.
# CLAUDE_PLUGIN_ROOT is exported when the caller left it unset or empty, so a
# rule can call a crew script under `/crew:verify --all` as under Stop
# (crew 1.0.164, test_verify_gate_plugin_root.py). GATE_PLUGIN_ROOT, the value
# it is copied from, stays a plain shell variable and is still watched here.
_DELIBERATELY_EXPORTED = frozenset({"PATH", "CLAUDE_PLUGIN_ROOT"})


def _sh_gate_variable_names():
    with open(_VERIFY_SH, encoding="utf-8") as handle:
        gate = handle.read()
    sources = [gate]
    for rel in _SOURCED_RE.findall(gate):
        with open(os.path.join(os.path.dirname(_VERIFY_SH), rel),
                  encoding="utf-8") as handle:
            sources.append(handle.read())
    names = set()
    for text in sources:
        for line in text.splitlines():
            if line.lstrip().startswith("#"):
                continue
            names.update(_ASSIGN_RE.findall(line))
            names.update(_FOR_RE.findall(line))
            for group in _READ_RE.findall(line):
                names.update(group.split())
    return names, len(sources)


def test_the_sh_gate_variable_list_is_derived_not_vacuous():
    """Guard for the test below: if the derivation silently matched nothing
    (a regex drifting from the script's style), the leak check would pass
    by checking no names at all. The two variables the loop hands every
    rule's eval -- the command text `c` and its capture path
    `RULE_OUT_FILE` -- must be in the set, and `_common.sh` must have been
    read."""
    names, files_read = _sh_gate_variable_names()

    assert {"c", "RULE_OUT_FILE", "CMDS"} <= names and files_read >= 2, (
        f"derived {len(names)} names from {files_read} files: {sorted(names)}")


@pytest.mark.skipif(_BASH is None, reason="needs bash")
def test_sh_rule_never_sees_a_gate_variable_in_its_environment(tmp_path):
    """The parity half: verify-gate.sh's own variables (`c`, the command
    text; `RULE_OUT_FILE`, the capture path; `CMDS`; every other name the
    script assigns, derived above) are plain shell variables the eval'd
    rule does not inherit. The rule reads that list and exits 7 naming any
    it finds in its own environment. The gate is launched with every
    derived name stripped from its environment (bash auto-exports a
    variable it inherited, so an inherited `c` would read as a leak the
    gate did not cause); PATH stays, being deliberately exported.

    Sabotage: `export RULE_OUT_FILE c` just before `( eval "$c" )` makes
    the rule see both and the gate report VERIFY FAILED."""
    names, _ = _sh_gate_variable_names()
    watched = sorted(names - _DELIBERATELY_EXPORTED)
    names_file = tmp_path / "gate-names.json"
    names_file.write_text(json.dumps(watched), encoding="utf-8")
    quoted = "'" + str(names_file).replace("\\", "/").replace("'", "'\\''") + "'"
    check = (
        f'{_PY} -c "import json, os, sys; '
        "names = json.load(open(sys.argv[1], encoding='utf-8')); "
        "leaked = [n for n in names if n in os.environ]; "
        "print('LEAKED', leaked); "
        f'sys.exit(7 if leaked else 0)" {quoted}'
    )
    root = _repo(tmp_path, check)
    env = {k: v for k, v in os.environ.items() if k not in names or k == "PATH"}
    env["CLAUDE_PROJECT_DIR"] = str(root)

    result = crew_fixtures.run_gate(
        [_BASH, _VERIFY_SH], input=json.dumps({}), cwd=str(root), env=env,
        capture_output=True, text=True, check=False,
        timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S,
    )

    assert result.returncode == 0 and "VERIFY FAILED" not in result.stderr, (
        f"stdout: {result.stdout} stderr: {result.stderr}")
