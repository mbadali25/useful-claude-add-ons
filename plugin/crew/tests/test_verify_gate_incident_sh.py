"""The verify gate's emergency lane, and the debt row it leaves behind.

These three cases used to live in test_gates_powershell.py, driving
verify-gate.ps1. L-0869 deleted that file, so they now drive verify-gate.sh -
which is what the dispatcher has actually run on Windows since L-0727 slice 2,
and what every POSIX host has always run. They were the only coverage of the
VERIFY gate's `.crew/incident-skips.log` row, so porting them rather than
dropping them is the point: `crew_incident_log` (_common.sh:486) is shared, and
its de-dup rule was otherwise only exercised through promote-gate
(test_promote_gate_dispatch.py, test_promote_gate_review.py).

The rule being pinned, from _common.sh's own comment: one row per gate+detail
per incident, NOT per turn. Stop fires every turn, so a ten-turn incident must
still report one owed check - a count that measures what is owed, not how long
the incident lasted. The call site is verify-gate.sh:510.
"""
import json
import os
import subprocess
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

_ROOT = context._ROOT  # pylint: disable=protected-access
_VERIFY_SH = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")
_BASH = crew_fixtures.resolve_bash()

pytestmark = pytest.mark.skipif(_BASH is None, reason="needs bash")

# No rule matches the changed file and `unmapped` is "warn", so the gate exits 0
# whether or not an incident stands it down. That is deliberate: it isolates the
# thing under test to what gets RECORDED, not to the exit code.
_VERIFY_JSON = {"version": 1, "rules": [], "always": [], "default": [],
                "unmapped": "warn"}


def _git(root, *args):
    subprocess.run(("git",) + args, cwd=root, check=True, capture_output=True,
                   text=True, stdin=subprocess.DEVNULL,
                   timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


def _repo(tmp_path, config=None):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    (root / ".work").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    # .crew/ and .work/ are gitignored in a real crew repo, and must be: the
    # gate's own marker file would otherwise dirty the tree it is judging.
    (root / ".gitignore").write_text(".crew/\n.work/\n", encoding="utf-8")
    (root / ".crew" / "verify.json").write_text(json.dumps(_VERIFY_JSON), encoding="utf-8")
    (root / ".crew" / "config.json").write_text(json.dumps(config or {}), encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    return root


def _incident(root, seconds_from_now):
    """An incident expiring `seconds_from_now`. Negative = already expired."""
    (root / ".crew" / "incident.json").write_text(json.dumps({
        "id": "INC-TEST", "summary": "suite",
        "expiresAtEpoch": int(time.time()) + seconds_from_now,
    }), encoding="utf-8")


def _verify(root):
    return crew_fixtures.run_gate(
        [_BASH, _VERIFY_SH], input="{}", cwd=str(root),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)),
        capture_output=True, text=True, check=False,
        timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


def _skips(root):
    path = root / ".crew" / "incident-skips.log"
    if not path.exists():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_the_verify_gate_stands_down_during_an_incident_and_records_the_debt(tmp_path):
    root = _repo(tmp_path)
    (root / "unverified.py").write_text("x = 1\n", encoding="utf-8")
    _incident(root, 3600)

    result = _verify(root)

    assert result.returncode == 0, result.stderr
    joined = "\n".join(_skips(root))
    assert "verify" in joined
    # The precondition, not just the gate name: a debt list that says only
    # "the verify gate stood down" tells the next session nothing.
    assert "1 changed file(s) unverified" in joined


def test_a_repeated_identical_skip_is_one_debt_not_one_per_turn(tmp_path):
    """_common.sh:486's de-dup rule, through the verify gate. Stop fires every
    turn; the same unrun check is one debt however often the gate declines."""
    root = _repo(tmp_path)
    (root / "unverified.py").write_text("x = 1\n", encoding="utf-8")
    _incident(root, 3600)

    _verify(root)
    first = len(_skips(root))
    _verify(root)

    assert first == 1, _skips(root)
    assert len(_skips(root)) == first, "a repeated identical skip must not stack"


def test_an_expired_incident_is_not_recorded_as_a_stand_down(tmp_path):
    """The gate exits 0 either way here (no rule matches, `unmapped` is warn),
    so this pins the recording: an expired incident stands nothing down, and a
    debt list that claimed otherwise would owe a check nobody skipped."""
    root = _repo(tmp_path)
    (root / "unverified.py").write_text("x = 1\n", encoding="utf-8")
    _incident(root, -60)

    result = _verify(root)

    assert result.returncode == 0, result.stderr
    assert _skips(root) == [], "an expired incident must not log a stand-down"
