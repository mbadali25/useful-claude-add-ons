"""Regression test for a defect a review pass (gpt-5.6-sol, on the range
485a1b08..3f347d52) found in the auto-clear/context-watch pair:

`context-watch.sh` (~line 103): a `mktemp` failure used to redirect
`auto-clear.sh`'s stdout -- the ONE real path that carries the `notify`
systemMessage -- to `/dev/null`, and by the time that redirection ran,
`auto-clear.sh` had already claimed the one-per-session SENT_MARKER, so
the message was lost and a retry would refuse before printing anything
again. Fixed by removing the mktemp dependency (and its failure mode)
entirely.
"""
import json
import os
import subprocess
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

_ROOT = context._ROOT  # pylint: disable=protected-access
_WATCH_SH = _ROOT + "/hooks/scripts/context-watch.sh"
_BASH = crew_fixtures.resolve_bash()


def _watch_repo(tmp_path, session):
    cfg = {"context": {"warnAt": 0.8}}
    root = crew_fixtures.make_repo(tmp_path, config=cfg, git=False)
    crew = root.parent / "home" / ".claude" / "crew"
    crew.mkdir(parents=True, exist_ok=True)
    (crew / "config.json").write_text(json.dumps({"context": {"autoClear": {
        "enabled": True}}}), encoding="utf-8")
    (root / ".crew" / (".handoff-requested-" + session)).write_text(json.dumps({
        "session_id": session, "requested_at": time.time() - 30,
        "trusted": True, "why": "measured"}), encoding="utf-8")
    handoff = root / ".work" / "HANDOFF.md"
    handoff.write_text(
        "# Handoff\nwritten: now\nticket: T-1\nbranch: x\nhead: y\n\n"
        "## Done\n- a thing\n\n## Next action\nDo the next thing.\n", encoding="utf-8")
    os.utime(handoff, (time.time() + 5, time.time() + 5))
    return root


def _no_mktemp_path(tmp_path):
    """A directory prepended to PATH holding a `mktemp` that always fails,
    the same shape a genuinely absent/broken `mktemp` produces (no stdout,
    non-zero exit) -- without needing to reconstruct an entire minimal
    PATH just to remove one binary from it."""
    bindir = tmp_path / "no-mktemp-bin"
    crew_fixtures.write_shim(str(bindir), "mktemp", "#!/bin/sh\nexit 1\n")
    return str(bindir)


@pytest.mark.skipif(_BASH is None, reason="needs bash")
def test_context_watch_forwards_the_notify_json_even_when_mktemp_fails(tmp_path):
    """End to end through context-watch.sh (not auto-clear.sh directly):
    a `stop_hook_active` continuation with this session's wrap-up marker
    already present hands straight to `cw_run_auto_clear`, which shells out
    to auto-clear.sh. With no TMUX/DISPLAY and OS=Windows_NT, `auto`
    resolves to `notify`, whose systemMessage is the ONE real path that
    writes to auto-clear.sh's stdout -- and `mktemp` is shadowed here to
    always fail, reproducing the exact condition the swallow bug needed."""
    session = "sess-fix3"
    root = _watch_repo(tmp_path, session)
    home = str(root.parent / "home")
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root), OS="Windows_NT",
               TMUX="", DISPLAY="", TMUX_PANE="",
               CREW_AUTOCLEAR_INHIBIT="1", HOME=home, USERPROFILE=home)
    env["PATH"] = _no_mktemp_path(tmp_path) + os.pathsep + env["PATH"]
    payload = json.dumps({"session_id": session, "cwd": str(root),
                          "hook_event_name": "Stop", "stop_hook_active": True})

    result = subprocess.run([_BASH, _WATCH_SH], cwd=str(root), env=env,
                            input=payload, capture_output=True, text=True,
                            check=False, timeout=60)

    assert result.returncode == 0
    assert result.stdout.strip(), (
        "the notify systemMessage never reached this hook's own stdout "
        "with mktemp shadowed to fail" + repr(result))
    out = json.loads(result.stdout.strip())
    assert "safe to run" in out["systemMessage"], result.stdout
    log_path = root / ".crew" / ".autoclear.log"
    assert log_path.exists()
    assert "sent - method notify" in log_path.read_text(encoding="utf-8")
