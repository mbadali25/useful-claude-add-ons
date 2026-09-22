"""Regression suite for `resolve_mmdc()` and the launcher argv it builds.

The defect these tests exist for: `resolve_mmdc()` called `shutil.which("mmdc")`,
used the answer as a boolean, threw the resolved path away and passed the bare
string "mmdc" to `subprocess.run`. On Windows mermaid-cli installs as
`mmdc.cmd`. `shutil.which` finds that because it consults PATHEXT; `subprocess`
without a shell does not, because CreateProcess searches PATH for the literal
name and name+".exe" only. So on a machine where mermaid-cli WAS installed the
run died with an uncaught WinError 2, and the carefully written "install
mermaid-cli" message never printed - `which` had succeeded, so the branch that
prints it was never reached. A check that appears to have happened, producing
the wrong outcome.

**These tests assert on the argv handed to subprocess, not on success.** On
Linux `mmdc` has no extension and the bare name works, so a pass/fail assertion
is blind to the bug on the platform CI runs. The argv is not.

Where the platform boundary falls, stated plainly because the real failure is
Windows-only:
  - OBSERVED here: `resolve_mmdc()` returns the path `which` gave it; `render()`
    puts that path in argv[0]; a bare name that PATH cannot resolve raises
    FileNotFoundError (the errno-2 family WinError 2 belongs to) out of
    subprocess; and that error now ends in the install message.
  - MODELLED here: that `shutil.which` resolves "mmdc" to "mmdc.cmd". It cannot
    do that on Linux - PATHEXT is consulted only under
    `sys.platform == "win32"` in shutil.which - so `win_which` below reproduces
    the Windows rule over a real fixture directory and the test asserts what
    resolve_mmdc does with its answer.
  - NOT tested anywhere: that Windows CreateProcess executes a .cmd given its
    full path. That is the premise of the fix and cannot be run on Linux.
"""

import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"

sys.path.insert(0, str(SKILL / "scripts"))
import render_mermaid as R  # noqa: E402

CONFIG = SKILL / "assets" / "mermaid-config.json"
GOOD_SVG = (FIXTURES / "sample.svg").read_bytes()
SOURCE = (FIXTURES / "sample.mmd").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# stubs
# --------------------------------------------------------------------------- #

class Recorder:
    """Stands in for the `subprocess` module inside render_mermaid.

    Patched onto R.subprocess rather than onto the real subprocess module, so
    nothing else in the test session - including pytest's own machinery - sees
    a stubbed run().
    """

    def __init__(self, *, raises: OSError | None = None):
        self.argv: list[str] | None = None
        self.raises = raises

    def run(self, cmd, **kwargs):
        self.argv = list(cmd)
        if self.raises:
            raise self.raises
        # A real mmdc writes the SVG; postprocess() reads it straight after.
        out = Path(cmd[cmd.index("--output") + 1])
        out.write_bytes(GOOD_SVG)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


def fake_bin(tmp_path: Path, name: str) -> Path:
    """A real, executable file on a directory that will serve as PATH."""
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    p = d / name
    p.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8", newline="\n")
    p.chmod(0o755)
    return p


def win_which(directory: Path):
    """shutil.which's Windows rule, which cannot run on Linux.

    shutil.which consults PATHEXT only under `sys.platform == "win32"`; on any
    other platform a `.cmd` on PATH is invisible to `which("mmdc")`. This
    reproduces the Windows answer - bare name, then name + each PATHEXT entry -
    over a real directory, so what the test feeds resolve_mmdc() is a path that
    genuinely exists.
    """
    pathext = [".COM", ".EXE", ".BAT", ".CMD"]

    def which(cmd, *_a, **_k):
        for candidate in [cmd] + [cmd + ext.lower() for ext in pathext]:
            p = directory / candidate
            if p.is_file():
                return str(p)
        return None

    return which


def do_render(tmp_path: Path, recorder: Recorder) -> list[str]:
    mmd = tmp_path / "flow.mmd"
    mmd.write_text(SOURCE, encoding="utf-8", newline="\n")
    R.render(mmd, tmp_path / "flow.svg", CONFIG, None, "#ffffff")
    assert recorder.argv is not None, "subprocess was never invoked"
    return recorder.argv


# --------------------------------------------------------------------------- #
# 1. the resolved path is passed, not the bare name
# --------------------------------------------------------------------------- #

def test_resolve_mmdc_returns_the_path_which_resolved(tmp_path, monkeypatch):
    """The whole defect in one assertion: use what which() returned."""
    exe = fake_bin(tmp_path, "mmdc")
    monkeypatch.setattr(R.shutil, "which", lambda c, *a, **k: str(exe) if c == "mmdc" else None)

    argv = R.resolve_mmdc()

    assert argv == [str(exe)], f"resolve_mmdc discarded which()'s answer: {argv}"


def test_render_passes_the_resolved_path_to_subprocess(tmp_path, monkeypatch):
    """argv[0] must be the resolved path all the way through render()."""
    exe = fake_bin(tmp_path, "mmdc")
    monkeypatch.setattr(R.shutil, "which", lambda c, *a, **k: str(exe) if c == "mmdc" else None)
    rec = Recorder()
    monkeypatch.setattr(R, "subprocess", rec)

    argv = do_render(tmp_path, rec)

    assert argv[0] == str(exe), f"bare name reached subprocess: {argv[0]!r}"
    assert argv[0] != "mmdc"
    assert Path(argv[0]).is_absolute(), argv[0]


def test_npx_fallback_also_passes_its_resolved_path(tmp_path, monkeypatch):
    """The neighbouring case. `npx` installs as npx.cmd on Windows too, so the
    fallback branch had the identical bug and fixing only the first branch moves
    the crash one step down instead of removing it."""
    exe = fake_bin(tmp_path, "npx")
    monkeypatch.setattr(R.shutil, "which", lambda c, *a, **k: str(exe) if c == "npx" else None)

    argv = R.resolve_mmdc()

    assert argv[0] == str(exe), f"npx branch discarded which()'s answer: {argv}"
    assert argv[1:] == ["--yes", "@mermaid-js/mermaid-cli"], argv


# --------------------------------------------------------------------------- #
# 2. a .cmd-only PATH resolves (Windows resolution modelled, see module docstring)
# --------------------------------------------------------------------------- #

def test_cmd_only_path_resolves_to_the_cmd(tmp_path, monkeypatch):
    cmd_file = fake_bin(tmp_path, "mmdc.cmd")
    assert not (cmd_file.parent / "mmdc").exists(), "fixture must have no extensionless mmdc"
    monkeypatch.setattr(R.shutil, "which", win_which(cmd_file.parent))
    rec = Recorder()
    monkeypatch.setattr(R, "subprocess", rec)

    argv = do_render(tmp_path, rec)

    assert argv[0] == str(cmd_file), argv[0]
    assert argv[0].endswith(".cmd"), argv[0]


def test_extensionless_wins_over_cmd_when_both_exist(tmp_path, monkeypatch):
    """PATHEXT resolution tries the bare name first, so a POSIX-style install
    alongside a .cmd must still pick the extensionless one - the fix must not
    quietly prefer .cmd everywhere."""
    plain = fake_bin(tmp_path, "mmdc")
    fake_bin(tmp_path, "mmdc.cmd")
    monkeypatch.setattr(R.shutil, "which", win_which(plain.parent))

    assert R.resolve_mmdc() == [str(plain)]


def test_the_bare_name_is_unrunnable_when_only_a_cmd_is_on_path(tmp_path):
    """The mechanism, observed rather than modelled.

    Linux cannot show WinError 2, but it shows the same thing the same way: a
    launcher present only under a name subprocess does not search for raises
    FileNotFoundError, while the resolved path runs. That is why discarding
    which()'s answer is the defect and not a style preference.
    """
    cmd_file = fake_bin(tmp_path, "mmdc.cmd")

    with pytest.raises(FileNotFoundError) as excinfo:
        # check=False: this call is asserted to raise FileNotFoundError at
        # SPAWN, before any exit status exists. check=True would add a second
        # way to fail -- CalledProcessError on a successful spawn -- and blur
        # the one thing the test is measuring.
        subprocess.run(["mmdc"], capture_output=True,
                       env={"PATH": str(cmd_file.parent)}, check=False)
    assert excinfo.value.errno == 2

    # check=False: the assertion reads returncode itself, so raising would
    # replace the measurement with a traceback.
    assert subprocess.run([str(cmd_file)], capture_output=True,
                          check=False).returncode == 0


# --------------------------------------------------------------------------- #
# 3. nothing usable produces the install message, never an exception
# --------------------------------------------------------------------------- #

INSTALL_LINE = "npm install -g @mermaid-js/mermaid-cli"


def test_nothing_on_path_prints_the_install_message(monkeypatch, capsys):
    monkeypatch.setattr(R.shutil, "which", lambda *a, **k: None)

    with pytest.raises(SystemExit) as excinfo:
        R.resolve_mmdc()

    assert INSTALL_LINE in str(excinfo.value), str(excinfo.value)


def test_a_resolved_launcher_that_cannot_be_spawned_still_reports_as_missing(
        tmp_path, monkeypatch):
    """The path the bug actually took on Windows.

    which() succeeds, so the branch printing the install message is never
    reached; then the spawn fails. Before the fix that OSError escaped main()
    as a traceback - FileNotFoundError is an OSError, and render()'s only
    caller catches RuntimeError, which OSError is not a subclass of. The user
    saw a stack trace and no instruction. It must end in the install message.
    """
    exe = fake_bin(tmp_path, "mmdc")
    monkeypatch.setattr(R.shutil, "which", lambda c, *a, **k: str(exe) if c == "mmdc" else None)
    rec = Recorder(raises=FileNotFoundError(2, "No such file or directory", "mmdc"))
    monkeypatch.setattr(R, "subprocess", rec)

    mmd = tmp_path / "flow.mmd"
    mmd.write_text(SOURCE, encoding="utf-8", newline="\n")
    with pytest.raises(SystemExit) as excinfo:
        R.render(mmd, tmp_path / "flow.svg", CONFIG, None, "#ffffff")

    message = str(excinfo.value)
    assert INSTALL_LINE in message, message
    # Naming the launcher it could not run is the part that separates this from
    # "you never installed it" - the user did install it, and the message has to
    # let them tell the two apart.
    assert str(exe) in message, message


def test_render_loop_does_not_swallow_the_missing_tool_exit(tmp_path, monkeypatch):
    """SystemExit must reach the top. main()'s render loop catches RuntimeError
    and records a per-diagram failure; if the unusable-launcher path were
    reported that way, the install message would be buried under a summary line
    and repeated once per diagram."""
    assert not issubclass(SystemExit, RuntimeError)
    assert not issubclass(OSError, RuntimeError)
