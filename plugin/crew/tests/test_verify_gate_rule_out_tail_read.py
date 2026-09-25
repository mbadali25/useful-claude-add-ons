"""verify-gate.ps1's rule-output capture reads a bounded TAIL of a rule's
captured output (see `CREW_VERIFY_GATE_TEST_RULE_OUT_CAP`, the test-only
cap-size seam used below) through a `[System.IO.FileStream]`, not a text
read of the whole file -- fast on a regular file, and the twin of
`verify-gate.sh`'s `stat`+`tail -c` pair. Two separate defects lived in
that same few lines.

FIX (this file's first test): `$fs.Seek(-$readLen, [System.IO.SeekOrigin]::End)`
seeks from the file's LIVE end at the moment `Seek` runs, not the `$size`
snapshot taken earlier in the same block specifically so the read would be
anchored to one fixed instant. On an ordinary (non-growing) rule output
file the live end and the snapshot happen to be the same number, so this
could not be told apart from the correct behaviour by running an ordinary
rule -- the divergence only shows up when a rule keeps writing between the
snapshot and the Seek, which is exactly the same timing-dependent shape
this repo's own rules elsewhere warn against pinning a test to (see the
`sh -c 'yes &'` comment a few lines above this code in verify-gate.ps1).
So the regression coverage here is split, deliberately:

- a BEHAVIOURAL test on a static (non-growing) file, which cannot
  distinguish old from new code by itself (see above) but DOES catch an
  off-by-one or a flipped sign in the new `$size - $readLen` offset -- the
  real risk of hand-editing that arithmetic;
- a STRUCTURAL test asserting the read path no longer seeks from
  `SeekOrigin::End` at all, which is what actually goes red on a revert to
  the original code (sabotage below), since the behavioural case can't.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

_ROOT = context._ROOT  # pylint: disable=protected-access
_VERIFY_PS1 = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.ps1")
_PWSH = shutil.which("pwsh")

_PY = "'" + sys.executable.replace("\\", "/").replace("'", "'\\''") + "'"

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("win") or _PWSH is None,
    reason="the .ps1 gate is the native-Windows flavour; needs Windows + pwsh",
)

# 20 distinct, non-repeating characters and no embedded newline -- an exact
# match on the tail window is only possible if the read is BOTH the right
# length AND anchored to the right end of the file; a read anchored to the
# wrong end, or off by even one byte, produces a substring that does not
# equal this constant.
_CONTENT = "0123456789ABCDEFGHIJ"
_CAP = 10
_EXPECTED_TAIL = _CONTENT[-_CAP:]  # "ABCDEFGHIJ"


def _git(root, *args):
    subprocess.run(("git",) + args, cwd=root, check=True,
                   capture_output=True, text=True, stdin=subprocess.DEVNULL,
                   timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


def _repo(tmp_path):
    """A rule that writes exactly `_CONTENT` (no trailing newline) to
    stdout and then fails, so the gate's report shows the captured tail."""
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / "README.md").write_text("committed\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    (root / "changed.py").write_text("x = 1\n", encoding="utf-8")
    run_entry = (
        f'{_PY} -c "import sys; sys.stdout.write(\'{_CONTENT}\'); sys.exit(9)"'
    )
    verify = {"version": 1, "rules": [
        {"paths": ["changed.py"], "reach": "local", "run": [run_entry]}
    ], "always": [], "default": [], "unmapped": "warn"}
    (root / ".crew" / "verify.json").write_text(json.dumps(verify), encoding="utf-8")
    return root


def _run_capped(root):
    return crew_fixtures.run_gate(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", _VERIFY_PS1],
        input=json.dumps({}), cwd=str(root),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root),
                  CREW_VERIFY_GATE_TEST_RULE_OUT_CAP=str(_CAP)),
        capture_output=True, text=True, check=False,
        timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S,
    )


def test_the_capped_tail_read_is_anchored_to_the_size_snapshot_not_the_live_end(tmp_path):
    """Behavioural: on a static file, proves the new `$size - $readLen`
    offset produces the CORRECT trailing window -- catches an off-by-one or
    a flipped Begin/End in that arithmetic, though (see module docstring)
    not the original End-vs-live-end race itself."""
    root = _repo(tmp_path)

    result = _run_capped(root)

    assert result.returncode == 2, f"stdout: {result.stdout} stderr: {result.stderr}"
    assert "VERIFY FAILED" in result.stderr, result.stderr
    # Checked as a whole LINE, not a substring: the report also echoes the
    # rule's own command text ($c), which literally contains `_CONTENT` as
    # part of the python source it ran -- a plain substring check on
    # `result.stderr` would pass on that echo alone, whether or not the
    # capture itself is right. `$out | Select-Object -Last 25 | ForEach-
    # Object { ... }` prints each captured element on its own line, and
    # `_CONTENT` has no embedded newline, so the captured tail is exactly
    # one line if the capture is correct.
    lines = result.stderr.splitlines()
    assert _EXPECTED_TAIL in lines, (
        f"no line equal to the expected tail {_EXPECTED_TAIL!r} in: {lines!r}")
    # Not merely "the tail line is present" -- the WHOLE uncapped content,
    # or a shorter/longer/misaligned window, must not ALSO appear as its
    # own captured-output line, or a read that grabbed the wrong window (or
    # ignored the cap entirely) would still satisfy the assertion above.
    assert _CONTENT not in lines, (
        f"the full uncapped content appeared as a captured-output line: {lines!r}")


def test_the_tail_read_no_longer_seeks_from_the_live_end(tmp_path):
    """Structural: the actual revert-catcher (see module docstring for why
    the behavioural case above cannot tell old from new code apart on a
    static file). Sabotage: restoring
    `$fs.Seek(-$readLen, [System.IO.SeekOrigin]::End)` makes this fail
    without needing to reproduce the live-growth race at all."""
    with open(_VERIFY_PS1, encoding="utf-8") as handle:
        source = handle.read()

    seek_idx = source.index("$fs.Seek(")
    seek_line_end = source.index("\n", seek_idx)
    seek_line = source[seek_idx:seek_line_end]

    assert "SeekOrigin]::End" not in seek_line, (
        "the rule-output tail read still seeks from the file's LIVE end, "
        f"not the $size snapshot: {seek_line!r}")
    assert "SeekOrigin]::Begin" in seek_line, seek_line
    assert "$size" in seek_line, (
        "the seek offset must be computed from the $size snapshot, not a "
        f"live re-read of the file's length: {seek_line!r}")
