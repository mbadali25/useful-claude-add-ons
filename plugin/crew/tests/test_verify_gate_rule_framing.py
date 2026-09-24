"""A `run` entry is ONE command, and the three readers of the map agree on it.

`.crew/verify.json` carries commands as JSON strings, and JSON strings can
hold a newline. Three scripts read that file and every one of them assumed
they could not.

`verify-gate.sh` returned two records -- the commands to run, and the paths no
rule matched -- down a single text channel separated by a NEWLINE, then read
them back with `sed -n 1p` / `sed -n 2p`. Measured on a fixture whose rule was
`["echo first\\necho second", "exit 1"]`: with `"unmapped": "warn"` the gate
exited **0** while the rule contained `exit 1`, and with `"fail"` it exited 2
but named `echo second` and `exit 1` as unmapped *paths*. Either way the
failing check never ran and the reader was pointed at files that do not exist.
`resolve-tools.sh` tokenised the same entry into junk tool names and reported
them as MISSING TOOLS; `map-audit.sh` read half of one as a filename and
reported it under "rules pointing at files that do not exist".

Two things are fixed and they are not the same size:

* **The rejection is the load-bearing half.** A rule crew cannot represent is
  not a rule that passed, so all three scripts now refuse the map, name the
  entry, and exit non-zero. `verify-gate.ps1` refuses it too -- not because it
  has the framing bug (it never serialises the lists; `ConvertFrom-Json` hands
  it objects) but because without the refusal the PAIR disagrees: `bash -c`
  over there would happily run both halves, so the same map would block the
  turn on one flavour and pass it on the other.
* **The separator is the belt.** The record separator is now `\\x1d` and the
  field separator inside each record `\\x1e`, neither of which can appear in a
  command *because the rejection ran first*. That makes it unreachable by any
  input, which is exactly why `test_the_two_halves_of_the_framing_contract_
  agree` reads the source instead of driving the script: sabotage.py's own
  header warns that a mutation of a line no input reaches proves nothing, and
  a behavioural test here would be green with the separator reverted.
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
_VERIFY_SH = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")
_VERIFY_PS1 = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.ps1")
_RESOLVE_TOOLS = os.path.join(_ROOT, "skills", "crew-setup", "scripts",
                              "resolve-tools.sh")
_MAP_AUDIT = os.path.join(_ROOT, "skills", "crew-setup", "scripts",
                          "map-audit.sh")

_BASH = crew_fixtures.resolve_bash()
_PWSH = shutil.which("pwsh")

pytestmark = pytest.mark.skipif(_BASH is None, reason="needs bash")

# The entry that used to split. Kept in one place so every script is refused
# for the same input rather than for three inputs that merely look alike.
_MULTILINE = "echo first\necho second"


def _git(root, *args):
    subprocess.run(("git",) + args, cwd=root, check=True,
                   capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


def _repo(tmp_path, verify_map):
    """A repo with one untracked .py file, so `git ls-files --others` reports
    a changed file and the gate reaches the matcher rather than exiting early
    on an empty changed set."""
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / "README.md").write_text("committed\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    (root / "unverified.py").write_text("x = 1\n", encoding="utf-8")
    (root / ".crew" / "verify.json").write_text(
        verify_map if isinstance(verify_map, str) else json.dumps(verify_map),
        encoding="utf-8")
    return root


def _run(script, root, interpreter=None):
    cmd = list(interpreter or [_BASH]) + [script]
    return crew_fixtures.run_gate(
        cmd, input=json.dumps({}), cwd=str(root),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)),
        capture_output=True, text=True, check=False, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S,
    )


# --- must block ----------------------------------------------------------

def test_a_multiline_run_entry_is_refused_by_name(tmp_path):
    """The must-block case, and the assertion is the MESSAGE, not the exit
    code. With the rejection removed the gate still exits 2 on this fixture --
    the separator keeps the entry whole and the read loop then evals
    `exit 1` -- so a test that asserted only the status would be green with
    the defect restored."""
    root = _repo(tmp_path, {
        "rules": [{"paths": ["**/*.py"], "run": [_MULTILINE, "exit 1"]}],
        "unmapped": "warn",
    })

    result = _run(_VERIFY_SH, root)

    assert result.returncode == 2, f"stderr: {result.stderr}"
    assert "PARSE_ERROR" in result.stderr
    assert "rules[0].run[0]" in result.stderr, result.stderr
    assert "a newline" in result.stderr, result.stderr
    assert "'echo first'" in result.stderr, result.stderr
    assert "Verification did NOT run" in result.stderr


def test_a_run_entry_carrying_the_record_separator_is_refused(tmp_path):
    """The separators are only safe while no command can contain one. A
    command carrying \\x1e would split into two commands exactly the way a
    newline used to, so it is refused on the same terms."""
    root = _repo(tmp_path, {
        "rules": [{"paths": ["**/*.py"],
                   "run": ["echo one\x1eexit 1"]}],
    })

    result = _run(_VERIFY_SH, root)

    assert result.returncode == 2, f"stderr: {result.stderr}"
    assert "rules[0].run[0]" in result.stderr, result.stderr
    assert "record separator" in result.stderr, result.stderr


def test_always_and_default_entries_are_checked_too(tmp_path):
    """`always` and `default` feed the same command list as `run`, so a
    rejection that covered only `rules[].run` would leave two doors open."""
    root = _repo(tmp_path, {
        "rules": [{"paths": ["**/*.py"], "run": ["true"]}],
        "always": [_MULTILINE],
    })

    result = _run(_VERIFY_SH, root)

    assert result.returncode == 2, f"stderr: {result.stderr}"
    assert "always[0]" in result.stderr, result.stderr


# --- must allow ----------------------------------------------------------

def test_an_ordinary_map_still_runs_every_command_and_reports_unmapped(
        tmp_path):
    """The boundary between the two records has to land in the right place
    for a map with several commands AND an unmapped path: every command runs,
    and the unmapped report names the file and nothing else."""
    root = _repo(tmp_path, {
        "rules": [{"paths": ["**/*.py"], "reach": "local",
                   "run": ["true", "echo ran >> ran.txt", "exit 1"]}],
        "unmapped": "fail",
    })
    (root / "stray.txt").write_text("unmapped\n", encoding="utf-8")

    result = _run(_VERIFY_SH, root)

    assert result.returncode == 2
    assert "VERIFY FAILED: exit 1" in result.stderr, result.stderr
    assert (root / "ran.txt").exists(), "a command after the first never ran"
    assert "stray.txt" in result.stderr, result.stderr
    for line in result.stderr.splitlines():
        if line.strip() == "echo ran >> ran.txt":
            pytest.fail("a command was reported as an unmapped path")


def test_a_single_line_command_full_of_shell_syntax_still_runs(tmp_path):
    """Only the framing characters are refused. Operators, quotes and
    redirections are ordinary content in a one-line command and a rejection
    that caught them would break every real map."""
    root = _repo(tmp_path, {
        # reach: local - this rule's `cd .` is a deliberate no-op used to
        # exercise shell-operator framing, not an undeclared reach; the
        # round-4 scanner defers ANY `cd` on its own terms.
        "rules": [{"paths": ["**/*.py"], "reach": "local",
                   "run": ["cd . && echo 'a; b && c' > shell.txt || true"]}],
    })

    result = _run(_VERIFY_SH, root)

    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (root / "shell.txt").read_text(encoding="utf-8").strip() \
        == "a; b && c"


# --- the belt --------------------------------------------------------------

def test_the_two_halves_of_the_framing_contract_agree():
    """The record separator is \\x1d on both sides and is not a newline.

    Read from the source on purpose. The rejection above makes a newline
    unreachable in a command, so no input can distinguish the fixed writer
    from the old two-`print()` one -- a behavioural test would stay green with
    the separator reverted, and sabotage.py's header calls a mutation of a
    line no input reaches a mutation that proves nothing. This asserts the
    contract itself: the writer emits \\x1d, the reader splits on \\035, and
    neither half is a newline any more.
    """
    text = open(_VERIFY_SH, encoding="utf-8").read()  # pylint: disable=consider-using-with

    # The WHOLE statement, not its first line. It has wrapped since 0.19.90
    # added the deferred-count record, and reading one line silently undercounted
    # the separators -- which made the derived record count disagree with the
    # readers and failed a correct change.
    lines = text.splitlines()
    starts = [i for i, l in enumerate(lines) if "sys.stdout.write(" in l]
    assert len(starts) == 1, starts
    statement = lines[starts[0]]
    for follow in lines[starts[0] + 1:]:
        if statement.count("(") <= statement.count(")"):
            break
        statement += " " + follow.strip()
    emit = [statement]
    assert r'"\x1d"' in emit[0], emit[0]
    assert r'"\x1e".join(cmds)' in emit[0], emit[0]

    readers = [l for l in text.splitlines() if "tr '\\035'" in l]
    # DERIVED from the writer, not hardcoded. This said `== 2` until the Stop
    # budget added a third record (the deferral notices) in 0.19.69, and a
    # hardcoded count fails on a correct change while proving nothing about
    # the contract -- which is that every record the writer emits has a reader
    # splitting on the same separator. One separator joins two records.
    records = emit[0].count(r'"\x1d"') + 1
    assert len(readers) == records, (
        "the writer emits " + str(records) + " records but " + str(len(readers))
        + " readers split on \\035: " + repr(readers)
    )
    # Record 6 (EXTRAS) is the one exception: it is a single JSON blob, not
    # a \x1e-joined list of subfields, so it has nothing to split further --
    # unlike records 1-5, which predate it and are still \x1e-joined lists.
    for line in readers:
        assert "sed -n" in line, line
        if "EXTRAS=" in line:
            continue
        assert "tr '\\036'" in line, line

    assert 'print("\\x1e".join(cmds))' not in text, \
        "the record separator is a newline again"


# --- the three readers agree ----------------------------------------------

def test_resolve_tools_refuses_the_same_map_by_name(tmp_path):
    """Setup writes the map the gate later enforces. A resolver that keeps
    going produces a MISSING TOOLS table full of tokens nobody wrote, and a
    user pastes those back into verify.json."""
    root = _repo(tmp_path, {
        "rules": [{"paths": ["**/*.py"], "run": [_MULTILINE]}],
    })

    result = _run(_RESOLVE_TOOLS, root)

    assert result.returncode == 2, f"stdout: {result.stdout}"
    assert "rules[0].run[0]" in result.stderr, result.stderr
    assert "refusing to resolve tools" in result.stderr, result.stderr
    assert "TOOL" not in result.stdout, result.stdout


def test_map_audit_refuses_the_same_map_by_name(tmp_path):
    """A drift report drawn from a map crew cannot represent is not a
    report: half a multi-line entry reads as a filename and lands under
    "rules pointing at files that do not exist"."""
    root = _repo(tmp_path, {
        "rules": [{"paths": ["**/*.py"], "run": [_MULTILINE]}],
    })

    result = _run(_MAP_AUDIT, root)

    assert result.returncode == 2, f"stdout: {result.stdout}"
    assert "rules[0].run[0]" in result.stderr, result.stderr
    assert "refusing to audit" in result.stderr, result.stderr
    assert "no rule" not in result.stdout, result.stdout


@pytest.mark.skipif(not sys.platform.startswith("win") or _PWSH is None,
                    reason="the .ps1 gate is the native-Windows flavour")
def test_the_powershell_gate_refuses_the_same_map_by_name(tmp_path):
    """The matched pair. `verify-gate.ps1` never had the framing bug -- it
    reads objects, not text -- but without the refusal the same map blocks
    the turn on bash and passes it here, and a pair that disagrees about
    whether the work is done is worse than either answer alone."""
    root = _repo(tmp_path, {
        "rules": [{"paths": ["**/*.py"], "run": [_MULTILINE, "exit 1"]}],
        "unmapped": "warn",
    })

    result = _run(_VERIFY_PS1, root,
                  interpreter=[_PWSH, "-NoProfile", "-NonInteractive",
                               "-File"])

    assert result.returncode == 2, f"stderr: {result.stderr}"
    assert "PARSE_ERROR" in result.stderr
    assert "rules[0].run[0]" in result.stderr, result.stderr
    assert "a newline" in result.stderr, result.stderr
    assert "Verification did NOT run" in result.stderr
