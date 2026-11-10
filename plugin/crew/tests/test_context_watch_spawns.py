"""crew 1.3.23: context-watch's no-op Stop turn starts as few processes as it can.

context-watch.sh runs on EVERY Stop, almost always to do nothing (the window is
well under the threshold). On Git Bash each process start is an MSYS fork, and the
hook's 20s limit is shared with the other Stop hooks. Measured on the Windows host
before this change, a no-op turn (a crew repo, a 27 MB transcript well under the
threshold) took ~9s and started FIVE python processes (three one-field `read_json`
calls, a config read, the transcript scan) plus `dirname`, `cat`, `grep`, `sed`,
`tr`, `cygpath` and `timeout`; the production report was `context-watch.sh timed
out ... limit is 20s` under load. After: one python, no helper in bash.

Decisions are not under test here (test_context_watch.py holds every case); this
holds the COST of reaching a no-op, plus the controls that the one python still
does all the work the five did: it still reads the transcript (over the threshold
the hook still blocks) and still reads the config (a malformed block, a disabled
hook).
"""
import json
import pathlib
import re
import shlex
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

_SCRIPTS = pathlib.Path(context._ROOT) / "hooks" / "scripts"  # pylint: disable=protected-access
_BASH = crew_fixtures.resolve_bash()
needs_bash = pytest.mark.skipif(_BASH is None, reason="bash not installed - the sh flavour was NOT run")

# Never on the no-op path any more.
_HELPERS = {"tr", "dirname", "uname", "cut", "cygpath", "date", "jq", "sed", "awk", "git",
            "basename", "head", "wc", "grep", "cat", "timeout", "mktemp"}
_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\[[^]]*\])?\+?=")


def _programs(trace):
    found = []
    for line in trace.splitlines():
        match = re.match(r"^\++ (.*)$", line)
        if not match:
            continue
        try:
            words = shlex.split(match.group(1))
        except ValueError:
            words = match.group(1).split()
        while words and _ASSIGN.match(words[0]):
            words.pop(0)
        if words:
            found.append(words[0].replace("\\", "/").rsplit("/", 1)[-1])
    return found


def _python_runs(programs):
    return [p for p in programs if re.match(r"^(python[0-9.]*|py)(\.exe)?$", p, re.I)]


def _repo(tmp_path, used, config=None):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    (root / ".crew" / "config.json").write_text(
        json.dumps(config if config is not None else {"context": {"warnAt": 0.8}}), encoding="utf-8")
    record = {"type": "assistant", "message": {"model": "claude-opus-4", "usage": {
        "input_tokens": used, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}}
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("\n".join([json.dumps({"type": "user"}), json.dumps(record)]) + "\n",
                          encoding="utf-8")
    return root, transcript


def _run(tmp_path, root, transcript, trace=False, **extra):
    payload = {"hook_event_name": "Stop", "session_id": "s-1", "cwd": str(root),
               "transcript_path": str(transcript), "stop_hook_active": False}
    payload.update(extra)
    env = crew_fixtures.isolated_home_env(tmp_path / "home")
    env["CLAUDE_PROJECT_DIR"] = str(root)
    env["CREW_PYTHON"] = sys.executable
    argv = [_BASH] + (["-x"] if trace else []) + [str(_SCRIPTS / "context-watch.sh").replace("\\", "/")]
    if trace:
        env["PS4"] = "+ "
    return subprocess.run(argv, input=json.dumps(payload), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, cwd=str(root),
                          check=False, timeout=170)


@needs_bash
def test_a_no_op_turn_starts_one_python_and_no_helper(tmp_path):
    root, transcript = _repo(tmp_path, used=1000)
    proc = _run(tmp_path, root, transcript, trace=True)
    programs = _programs(proc.stderr)

    assert proc.returncode == 0, proc.stderr[-4000:]
    helpers = sorted(set(programs) & _HELPERS)
    assert helpers == [], f"context-watch.sh started {helpers} on the no-op path:\n{proc.stderr[-4000:]}"
    assert len(_python_runs(programs)) == 1, programs
    assert not list((root / ".crew").glob(".handoff-requested-*")), "a no-op must claim no marker"


@needs_bash
def test_the_one_python_still_measures_the_transcript(tmp_path):
    """The control for folding five reads into one: over the threshold the hook
    still blocks, so the single python really scanned the transcript."""
    root, transcript = _repo(tmp_path, used=190_000)
    proc = _run(tmp_path, root, transcript)

    assert proc.returncode == 2, proc.stderr
    assert "context budget" in proc.stderr
    assert (root / ".crew" / ".handoff-requested-s-1").exists()


@needs_bash
def test_the_one_python_still_reads_the_config(tmp_path):
    off_root, off_transcript = _repo(tmp_path / "off", used=190_000,
                                     config={"context": {"enabled": False}})
    off = _run(tmp_path / "off", off_root, off_transcript)
    bad_root, bad_transcript = _repo(tmp_path / "bad", used=190_000, config={"context": None})
    bad = _run(tmp_path / "bad", bad_root, bad_transcript)

    assert off.returncode == 0 and off.stderr == "", off.stderr
    assert bad.returncode == 0 and "malformed" in bad.stderr, bad.stderr


@needs_bash
def test_a_stop_hook_active_turn_is_left_alone(tmp_path):
    root, transcript = _repo(tmp_path, used=190_000)
    proc = _run(tmp_path, root, transcript, stop_hook_active=True)

    assert proc.returncode == 0, proc.stderr
    assert not list((root / ".crew").glob(".handoff-requested-*"))
