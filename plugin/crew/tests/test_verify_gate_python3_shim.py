"""verify-gate.sh's python3 shim for RULE COMMANDS.

CLAUDE.md's own landmine: Git Bash ships with no python3 at all. Most of
this repo's own `.crew/verify.json` rules hardcode `python3` (e.g. "python3
scripts/check-marketplace.py"), so a rule that is otherwise perfectly
satisfiable - the machine DOES have a working python, just as `python` or
`py` - used to fail with a bare "python3: command not found", a false
failure that has nothing to do with what the rule actually checks.

**Review round 1 correction, and why this file's shape changed.** The first
version shimmed python3 AND python AND py, unconditionally, and was
reviewed BLOCK: it broke `py -3 -c ...` rules on a machine where `py`
already worked, because Windows' `py` launcher's `-3`/`-2` version-select
flags forwarded straight into a plain `exec "$REAL" "$@"` wrapper produce
"Unknown option: -3" against a real interpreter that does not understand
that flag. The fix now shims ONLY `python3`, and ONLY when `python3` itself
does not already resolve - `python` and `py`, wherever they are real, are
never shadowed. `test_py_dash_3_still_works_when_python_is_also_present`
below is the regression test for the reviewed-out bug.

`.crew/verify.json` itself is untouched by any of this - every rule still
reads exactly `python3 ...`, so anything else that reads the file's `run`
arrays (the crew-verification skill, /crew:verify tooling - see
`.crew/codemap/verification-harness.md`) keeps seeing portable, ordinary
bash syntax rather than a variable only this gate would know how to expand.

Every case below runs under a PATH containing ONLY the external tools
verify-gate.sh/_common.sh actually invoke (symlinked in, one at a time) -
never the real system PATH - so "no python3 present" and "nothing at all
resolves" are both genuine, not merely shadowed by an entry earlier in a
PATH that still has the real one further along.

Sabotage, done by hand in this ticket's own worktree and confirmed red
before this file was written green: reverting the `command -v python3`
guard (shimming unconditionally again, `python`/`py` included) turns
`test_py_dash_3_still_works_when_python_is_also_present` red with "Unknown
option: -3" - the exact review reproduction. Restoring the fix turns it
green again; `git diff` against the ticket's start commit confirmed the
revert touched nothing else before restoring it.
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

_BASH = crew_fixtures.resolve_bash()
pytestmark = pytest.mark.skipif(_BASH is None, reason="needs bash")

# Every EXTERNAL (non-builtin) command verify-gate.sh and _common.sh invoke,
# found by grepping both files - printf/read/local/export/eval/case etc. are
# bash builtins and need nothing on PATH.
_NEEDED_TOOLS = ("cat", "chmod", "cut", "date", "dirname", "find", "git",
                 "grep", "head", "kill", "mkdir", "mktemp", "ps", "pwd",
                 "rm", "sed", "sleep", "sort", "stat", "tail", "tr")


def _scoped_tools_dir(tmp_path, python_names, real_py=None):
    """A directory that is the ENTIRE PATH for the subprocess under test:
    real tool binaries symlinked in one at a time (so no real system
    directory - and no python3 it might also hold - ever appears on PATH),
    plus one stub per name in `python_names`, each `exec`ing `real_py`
    (default: the REAL system python, resolved from THIS process's own
    unrestricted PATH, before the scoped one is built)."""
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    for name in _NEEDED_TOOLS:
        real = shutil.which(name)
        if real:
            os.symlink(real, tools_dir / name)
    if real_py is None:
        real_py = shutil.which("python3") or shutil.which("python") or sys.executable
    for name in python_names:
        stub = tools_dir / name
        stub.write_text("#!/bin/sh\nexec \"" + real_py + "\" \"$@\"\n",
                        encoding="utf-8", newline="\n")
        os.chmod(stub, 0o755)
    return str(tools_dir)


def _git(root, *args):
    subprocess.run(("git",) + args, cwd=root, check=True,
                   capture_output=True, text=True)


def _repo(tmp_path, verify_map):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / "README.md").write_text("committed", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    (root / ".crew" / "verify.json").write_text(json.dumps(verify_map),
                                                encoding="utf-8")
    return root


def _run(root, tools_dir):
    env = dict(os.environ, PATH=tools_dir, CLAUDE_PROJECT_DIR=str(root))
    return subprocess.run(
        [_BASH, _SH], input="{}", cwd=str(root), env=env,
        capture_output=True, text=True, check=False,
    )


def test_a_rule_hardcoding_python3_still_runs_with_only_python_on_path(tmp_path):
    """MUST-ALLOW. `python3 -c ...` in a rule's `run` must succeed on a PATH
    that has `python` but genuinely no `python3` anywhere - the exact Git
    Bash shape - proven with a side-effect file the rule can only have
    created by actually executing under a real interpreter."""
    marker = tmp_path / "repo" / "ran.marker"
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "seconds": 5,
                   "run": ["python3 -c \"open('ran.marker', 'w').close()\""],
                   "reach": "local"}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    tools_dir = _scoped_tools_dir(tmp_path, ["python"])

    result = _run(root, tools_dir)
    assert result.returncode == 0, (
        "a rule invoking python3 must still pass when only python is on "
        "PATH. stderr: " + result.stderr
    )
    assert marker.exists(), (
        "the rule's python3 command never actually ran (or ran against the "
        "wrong interpreter) - the shim did not substitute a working "
        "interpreter. stderr: " + result.stderr
    )


def test_a_rule_hardcoding_python3_still_runs_with_only_py_on_path(tmp_path):
    """The same case for the `py` launcher name, so both names crew_py_strict
    can fall back to (python, py) are proven to feed the shim."""
    marker = tmp_path / "repo" / "ran.marker"
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "seconds": 5,
                   "run": ["python3 -c \"open('ran.marker', 'w').close()\""],
                   "reach": "local"}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    tools_dir = _scoped_tools_dir(tmp_path, ["py"])

    result = _run(root, tools_dir)
    assert result.returncode == 0, (
        "a rule invoking python3 must still pass when only py is on PATH. "
        "stderr: " + result.stderr
    )
    assert marker.exists(), result.stderr


def test_py_dash_3_still_works_when_python_is_also_present(tmp_path):
    """Regression test for the reviewed-out BLOCK - the exact shape review
    named: a plain `python` on PATH (found first by crew_py's python3 >
    python > py order, so it is what runs the MATCHER script) alongside a
    REAL `py` launcher (understands `-3`, rejects anything else it is not
    taught to accept). A rule invoking `py -3 ...` must reach the REAL `py`
    unshadowed - the reviewed-out version shimmed `python3`/`python`/`py`
    ALL THREE as `exec "$PY" "$@"` (where $PY was the plain `python`), so a
    rule's `py -3 ...` hit that shim instead of the real launcher and
    forwarded `-3` into a plain interpreter that rejects it."""
    marker = tmp_path / "repo" / "ran.marker"
    real_py = shutil.which("python3") or shutil.which("python") or sys.executable
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "seconds": 5,
                   "run": ["py -3 -c \"open('ran.marker', 'w').close()\""],
                   "reach": "local"}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    # "python" (plain, unrestricted) is what crew_py resolves as $PY and
    # runs the matcher script through - it must be a genuinely working
    # interpreter or the WHOLE gate fails before reaching the rule at all.
    tools_dir = _scoped_tools_dir(tmp_path, ["python"], real_py=real_py)
    # A REAL `py` launcher stand-in: accepts -3 (strips it and execs the
    # real interpreter), rejects anything else it is not taught - never
    # reached by the matcher (crew_py finds "python" first), only by a rule
    # naming `py` directly.
    launcher = os.path.join(tools_dir, "py")
    with open(launcher, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(
            "#!/bin/sh\n"
            "if [ \"$1\" != \"-3\" ]; then echo \"Unknown option: $1\" >&2; exit 1; fi\n"
            "shift\n"
            "exec \"" + real_py + "\" \"$@\"\n"
        )
    os.chmod(launcher, 0o755)

    result = _run(root, tools_dir)
    assert result.returncode == 0, (
        "py -3 must still work when a plain python is ALSO present and py "
        "is a real launcher - the gate must not have shadowed py with a "
        "plain-interpreter shim. stderr: " + result.stderr
    )
    assert "Unknown option" not in result.stderr, (
        "the -3 flag was forwarded into something that does not understand "
        "it - py was shimmed/shadowed. stderr: " + result.stderr
    )
    assert marker.exists(), result.stderr


def test_python3_already_present_is_never_shadowed(tmp_path):
    """MUST-ALLOW / must-not-shim. When python3 already resolves, the gate
    must not build or prepend anything - proven by making the real python3
    on PATH the ONLY one capable of writing the marker (a second, broken
    'python3'-named entry would never be reached if the shim mechanism, or
    anything else, put a directory ahead of it)."""
    marker = tmp_path / "repo" / "ran.marker"
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "seconds": 5,
                   "run": ["python3 -c \"open('ran.marker', 'w').close()\""],
                   "reach": "local"}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    tools_dir = _scoped_tools_dir(tmp_path, ["python3"])

    result = _run(root, tools_dir)
    assert result.returncode == 0, result.stderr
    assert marker.exists(), result.stderr


def test_a_command_v_hit_that_fails_the_proved_check_fails_loudly(tmp_path):
    """The failure mode the shim CODE ITSELF is responsible for: `command -v
    py` finds a real, executable file, and it is real enough to run the
    MATCHER script (invoked as `py - args << script`, so the plain
    top-level $PY / crew_py check that only gates reading .crew/verify.json
    at all is satisfied, and the gate reaches this rule) - but it rejects
    `-c` specifically (a narrow but real shape: a policy-wrapped launcher
    that permits running a script but not inline code), which is exactly
    what crew_py_strict's proof (`py -c "import sys; print(sys.executable)"`)
    needs. So no python3 shim can be built. Distinct from
    `test_nothing_resolves_via_command_v_at_all` below, which never reaches
    this code at all - there, the top-level check ITSELF fails first."""
    marker = tmp_path / "repo" / "ran.marker"
    real_py = shutil.which("python3") or shutil.which("python") or sys.executable
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "seconds": 5,
                   "run": ["python3 -c \"open('ran.marker', 'w').close()\""],
                   "reach": "local"}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    # A "py" that WORKS for the matcher's own `py - <<script` invocation
    # (crew_py accepts it as $PY) but refuses `-c` specifically, which is
    # the only thing crew_py_strict's proof ever asks of it.
    tools_dir = _scoped_tools_dir(tmp_path, [])
    launcher = os.path.join(tools_dir, "py")
    with open(launcher, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(
            "#!/bin/sh\n"
            "if [ \"$1\" = \"-c\" ]; then exit 1; fi\n"
            "exec \"" + real_py + "\" \"$@\"\n"
        )
    os.chmod(launcher, 0o755)

    result = _run(root, tools_dir)
    assert "no python3, python or py resolves to a PROVED working interpreter" in result.stderr, (
        "the shim's own no-proved-interpreter message did not fire. "
        "stderr: " + result.stderr
    )
    assert not marker.exists(), (
        "a rule ran despite no PROVED interpreter being resolvable. "
        + result.stderr
    )


def test_nothing_resolves_via_command_v_at_all(tmp_path):
    """The PRE-EXISTING top-level failure, kept here for the shim story's
    boundary but NOT attributable to the shim change itself: with nothing
    at all named python3/python/py anywhere on PATH, `crew_py` (the plain
    top-level resolver used just to read .crew/verify.json) fails before
    the matcher or the shim code ever runs, and the gate prints its own,
    separate, pre-existing message.

    **PM ruling, 2026-09-22, superseding this test's own earlier
    exit-0 assertion.** An exit-0 Stop hook does not block the turn, so
    this case used to reach the calling agent as an unblocked, silently
    UNVERIFIED turn - indistinguishable from one that actually passed, and
    exactly the "unknown collapsing into the safe-looking value" shape
    CLAUDE.md names as this repo's own recurring defect. verify-gate.sh:630
    now fails CLOSED instead - a single named `VERIFY GATE: ... exit 2`
    line, the SAME pattern this file already uses when .crew/verify.json
    itself fails to parse (re-evaluated fresh every turn; no separate
    one-shot suppression - the failure clears itself the moment python is
    installed, the same way a parse error clears itself the moment the JSON
    is fixed)."""
    marker = tmp_path / "repo" / "ran.marker"
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "seconds": 5,
                   "run": ["python3 -c \"open('ran.marker', 'w').close()\""],
                   "reach": "local"}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    tools_dir = _scoped_tools_dir(tmp_path, [])  # no python/python3/py at all

    result = _run(root, tools_dir)
    assert "no python" in result.stderr, (
        "no python resolvable at all must be named on stderr, not silently "
        "swallowed. stderr: " + result.stderr
    )
    # NIT from review round 4: the message must say how to get out of it -
    # install python, or the documented, deliberate stand-down.
    assert "install python" in result.stderr.lower(), (
        "the exit-2 message does not say how to get out of it (install "
        "python). stderr: " + result.stderr
    )
    assert '"verifyGate": false' in result.stderr, (
        "the exit-2 message does not name the deliberate stand-down escape "
        "hatch (\"verifyGate\": false in .crew/config.json). stderr: "
        + result.stderr
    )
    assert not marker.exists(), (
        "a rule ran despite no interpreter being resolvable at all. "
        + result.stderr
    )
    assert "Traceback" not in result.stderr, (
        "a raw python traceback leaked instead of the named failure. "
        + result.stderr
    )
    assert result.returncode == 2, (
        "no python resolving at all must fail CLOSED (exit 2), not exit 0 "
        "and let the turn read as unblocked/verified - see "
        "verify-gate.sh:630's comment for the PM ruling. rc="
        + str(result.returncode) + " " + result.stderr
    )

    # A second, unchanged run must fail the SAME way - fresh every turn,
    # not a one-shot that goes quiet (or silently passes) the second time.
    second = _run(root, tools_dir)
    assert second.returncode == 2, (
        "a repeat turn with the same missing-python environment must keep "
        "failing closed, not go quiet or pass on a later Stop. rc="
        + str(second.returncode) + " " + second.stderr
    )
    assert "no python" in second.stderr, second.stderr


def test_shim_cleanup_does_not_clobber_the_lock_release_trap(tmp_path):
    """FIX 3 from review: the shim's own EXIT/INT/TERM cleanup must be
    CHAINED onto whatever trap the lock already installed, not replace it.
    Proven by checking the LOCK directory (`.crew/.verify-gate.lock`), not
    the shim directory itself (which lives under the OS temp root, outside
    this repo, and proves nothing about chaining on its own) - a bare
    `trap ... EXIT` in the shim setup would silently drop the lock's own
    release trap, leaving the lock on disk and every LATER Stop backing off
    behind a lock nothing will ever remove."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "seconds": 5,
                   "run": ["python3 -c \"pass\""], "reach": "local"}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    tools_dir = _scoped_tools_dir(tmp_path, ["python"])

    result = _run(root, tools_dir)
    assert result.returncode == 0, result.stderr
    assert not (root / ".crew" / ".verify-gate.lock").exists(), (
        "the lock directory survived the run - the shim's own cleanup trap "
        "clobbered the lock's release trap instead of chaining onto it. "
        + result.stderr
    )


def test_a_native_windows_sys_executable_path_is_accepted_and_works(tmp_path):
    """FIX from review round 3. `sys.executable` for a NATIVE Windows python
    (as opposed to an MSYS-built one) prints a drive-letter path like
    `C:\\fakepy\\python.exe`, not a POSIX `/...` one - a bare `case ... /*)`
    test rejected that shape outright, so a Git Bash host with only
    `python`/`py` (never `python3`) reported "no python3, python or py
    resolves" and every rule hardcoding python3 failed "command not found",
    reviewer-reproduced with rc=2. `.ps1`'s own resolver already accepted
    both shapes (`^[A-Za-z]:[\\\\/]`) - the two flavours disagreed on the
    exact case the shim exists for. The shim must now accept EITHER
    absolute shape and convert the Windows one before writing it into its
    own exec line."""
    marker = tmp_path / "repo" / "ran.marker"
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "seconds": 5,
                   "run": ["python3 -c \"open('ran.marker', 'w').close()\""],
                   "reach": "local"}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    real_py = shutil.which("python3") or shutil.which("python") or sys.executable

    tools_dir = os.path.join(str(tmp_path), "tools")
    os.makedirs(tools_dir, exist_ok=True)
    for name in _NEEDED_TOOLS:
        real = shutil.which(name)
        if real:
            os.symlink(real, os.path.join(tools_dir, name))
    # A "python" whose sys.executable reports a NATIVE WINDOWS path -
    # otherwise a real, working interpreter, so the MATCHER's own
    # `python - args << script` invocation (which crew_py, not
    # crew_py_strict, resolves to this SAME file) still works. Only the
    # EXACT crew_py_strict probe (`-c 'import sys; print(sys.executable)'`)
    # gets the fake answer.
    stub = os.path.join(tools_dir, "python")
    with open(stub, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(
            "#!/bin/sh\n"
            "if [ \"$1\" = \"-c\" ] && [ \"$2\" = \"import sys; print(sys.executable)\" ]; then\n"
            # printf, not echo - some /bin/sh implementations (dash's
            # builtin echo among them) interpret XSI backslash escapes by
            # default, so `echo 'C:\fakepy\...'` silently eats the `\f` as
            # a form-feed escape instead of emitting it literally. Caught
            # by running this exact stub by hand before trusting the test.
            "  printf '%s\\n' 'C:\\fakepy\\python.exe'\n"
            "  exit 0\n"
            "fi\n"
            "exec \"" + real_py + "\" \"$@\"\n"
        )
    os.chmod(stub, 0o755)

    # The REAL target the shim's exec line names after conversion: no
    # cygpath on this host (confirmed absent - the fallback branch is what
    # this test exercises), so "C:\fakepy\python.exe" becomes
    # "C:/fakepy/python.exe" via a bare backslash->forward-slash swap - a
    # RELATIVE-looking path (no leading "/"), resolved against the gate's
    # own cwd (the repo root), exactly as a native Windows path handed to a
    # POSIX exec on real Git Bash resolves against its process's cwd.
    windows_target_dir = root / "C:" / "fakepy"
    windows_target_dir.mkdir(parents=True)
    windows_target = windows_target_dir / "python.exe"
    windows_target.write_text(
        "#!/bin/sh\nexec \"" + real_py + "\" \"$@\"\n",
        encoding="utf-8", newline="\n")
    os.chmod(windows_target, 0o755)

    result = _run(root, tools_dir)
    assert result.returncode == 0, (
        "a rule invoking python3 must still pass when the only resolvable "
        "python reports a native Windows sys.executable path. stderr: "
        + result.stderr
    )
    assert marker.exists(), (
        "the shim was not built (or did not work) for a Windows-style "
        "absolute sys.executable path. stderr: " + result.stderr
    )


def test_the_cygpath_branch_is_taken_when_cygpath_is_present(tmp_path):
    """NIT from review round 4. This host has no real `cygpath`, so
    `test_a_native_windows_sys_executable_path_is_accepted_and_works` above
    only ever exercises the `tr '\\\\' '/'` fallback - the cygpath branch
    itself was never actually run by anything in this suite. Puts a FAKE
    `cygpath` on PATH that answers ONLY for the exact `C:\\fakepy\\
    python.exe` argument the gate is expected to hand it (anything else
    exits 1), and points its answer at an interpreter that lives somewhere
    the tr fallback's own conversion ("C:\\fakepy\\python.exe" ->
    "C:/fakepy/python.exe", repo-cwd-relative) would NEVER find - so this
    only passes if the gate actually called `cygpath -u` and used ITS
    output, not the fallback."""
    marker = tmp_path / "repo" / "ran.marker"
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "seconds": 5,
                   "run": ["python3 -c \"open('ran.marker', 'w').close()\""],
                   "reach": "local"}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    real_py = shutil.which("python3") or shutil.which("python") or sys.executable

    tools_dir = os.path.join(str(tmp_path), "tools")
    os.makedirs(tools_dir, exist_ok=True)
    for name in _NEEDED_TOOLS:
        real = shutil.which(name)
        if real:
            os.symlink(real, os.path.join(tools_dir, name))

    # Same fake-Windows-sys.executable "python" as the test above.
    stub = os.path.join(tools_dir, "python")
    with open(stub, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(
            "#!/bin/sh\n"
            "if [ \"$1\" = \"-c\" ] && [ \"$2\" = \"import sys; print(sys.executable)\" ]; then\n"
            "  printf '%s\\n' 'C:\\fakepy\\python.exe'\n"
            "  exit 0\n"
            "fi\n"
            "exec \"" + real_py + "\" \"$@\"\n"
        )
    os.chmod(stub, 0o755)

    # An ABSOLUTE target, deliberately OUTSIDE the repo entirely - the tr
    # fallback's own output ("C:/fakepy/python.exe", a relative path
    # resolved against the repo root) can never land here by coincidence,
    # so finding it proves cygpath's output was actually used.
    cygpath_target_dir = tmp_path / "cygpath_target"
    cygpath_target_dir.mkdir()
    cygpath_target = cygpath_target_dir / "python.exe"
    cygpath_target.write_text(
        "#!/bin/sh\nexec \"" + real_py + "\" \"$@\"\n",
        encoding="utf-8", newline="\n")
    os.chmod(cygpath_target, 0o755)

    fake_cygpath = os.path.join(tools_dir, "cygpath")
    with open(fake_cygpath, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(
            "#!/bin/sh\n"
            "if [ \"$1\" = \"-u\" ] && [ \"$2\" = \"C:\\\\fakepy\\\\python.exe\" ]; then\n"
            "  printf '%s\\n' '" + str(cygpath_target) + "'\n"
            "  exit 0\n"
            "fi\n"
            "exit 1\n"
        )
    os.chmod(fake_cygpath, 0o755)

    result = _run(root, tools_dir)
    assert result.returncode == 0, (
        "a rule invoking python3 must pass when a fake cygpath maps the "
        "Windows-style sys.executable to a working interpreter. stderr: "
        + result.stderr
    )
    assert marker.exists(), (
        "the cygpath branch was not taken (or did not work) - the shim did "
        "not exec the interpreter cygpath -u pointed at. stderr: "
        + result.stderr
    )
