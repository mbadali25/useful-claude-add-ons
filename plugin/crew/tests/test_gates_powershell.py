"""The PowerShell gates' emergency-lane behaviour, compared with the bash pair.

hooks/scripts/_test/run-tests.sh covers the bash flavour and cannot run the
.ps1 one. That asymmetry is this plugin's recurring failure: context-watch.ps1
kept a file-size heuristic for a release after the bash flavour dropped it, so
Windows sessions were cut short while Linux ones were not, and nothing caught
it because the suite only fed the shared path. An emergency lane that stands
gates down on one flavour and not the other is the same bug with worse
consequences - the gates would keep blocking during an outage on Windows, or
keep standing down after the incident expired.

Windows + pwsh only, by the same reasoning as
test_verify_gate_bash_resolver.py: these are the native-Windows halves of the
pair, and there is nothing to compare on a POSIX runner.
"""
import json
import os
import shutil
import subprocess
import sys
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_VERIFY_PS1 = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.ps1")
_PROMOTE_PS1 = os.path.join(_ROOT, "hooks", "scripts", "promote-gate.ps1")
_PWSH = shutil.which("pwsh")

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("win") or _PWSH is None,
    reason="the .ps1 gates are the native-Windows flavour; needs Windows + pwsh",
)

_VERIFY_JSON = {
    "version": 1, "rules": [], "always": [], "default": [], "unmapped": "warn",
    "environments": {
        # No rollback key at all, so this environment blocks unless an incident
        # is standing the gate down - the fail-closed case from ANEWINF-720.
        "production": {"deploy": ["./deploy.sh prod"], "requires": ["qa"]},
    },
}


def _git(root, *args):
    subprocess.run(("git",) + args, cwd=root, check=True,
                   capture_output=True, text=True)


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
    (root / "deploy.sh").write_text("#!/bin/sh\necho deployed\n", encoding="utf-8")
    (root / ".crew" / "verify.json").write_text(json.dumps(_VERIFY_JSON),
                                                encoding="utf-8")
    (root / ".crew" / "config.json").write_text(json.dumps(config or {}),
                                                encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    return root


def _incident(root, seconds_from_now):
    """An incident expiring `seconds_from_now`. Negative = already expired."""
    (root / ".crew" / "incident.json").write_text(json.dumps({
        "id": "INC-TEST",
        "summary": "suite",
        "expiresAtEpoch": int(time.time()) + seconds_from_now,
    }), encoding="utf-8")


def _run(script, root, payload):
    return subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", script],
        input=json.dumps(payload), cwd=str(root),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)),
        capture_output=True, text=True, check=False,
    )


def _verify(root):
    return _run(_VERIFY_PS1, root, {})


def _promote(root):
    return _run(_PROMOTE_PS1, root,
                {"tool_name": "PowerShell",
                 "tool_input": {"command": "./deploy.sh prod"}})


def _skips(root):
    path = root / ".crew" / "incident-skips.log"
    if not path.exists():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line]


# --- promote-gate.ps1 -----------------------------------------------------


def test_promote_gate_blocks_with_no_incident(tmp_path):
    # The baseline the stand-down is measured against. If this ever passes,
    # every "allowed during an incident" assertion below proves nothing.
    root = _repo(tmp_path)
    result = _promote(root)
    assert result.returncode == 2, result.stderr
    assert "PROMOTION BLOCKED" in result.stderr


def test_promote_gate_stands_down_and_records_during_an_incident(tmp_path):
    root = _repo(tmp_path)
    _incident(root, 3600)
    result = _promote(root)
    assert result.returncode == 0, result.stderr
    rows = _skips(root)
    assert rows, "an ungated deploy must be recorded"
    joined = "\n".join(rows)
    assert "promote" in joined
    # The precondition, not just the gate name: a debt list that says only
    # "the promote gate stood down" tells the next session nothing.
    assert "rollback" in joined or "all-pass row" in joined


def test_promote_gate_blocks_again_once_the_incident_expires(tmp_path):
    root = _repo(tmp_path)
    _incident(root, -60)
    result = _promote(root)
    assert result.returncode == 2, result.stderr


def test_promote_gate_blocks_when_stand_down_is_false(tmp_path):
    root = _repo(tmp_path, config={"emergency": {"standDown": False}})
    _incident(root, 3600)
    result = _promote(root)
    assert result.returncode == 2, result.stderr


def test_promote_gate_fails_closed_on_an_unparseable_incident(tmp_path):
    root = _repo(tmp_path)
    (root / ".crew" / "incident.json").write_text("{ not json", encoding="utf-8")
    result = _promote(root)
    assert result.returncode == 2, result.stderr


# --- verify-gate.ps1 -----------------------------------------------------


def test_verify_gate_stands_down_during_an_incident(tmp_path):
    root = _repo(tmp_path)
    (root / "unverified.py").write_text("x = 1\n", encoding="utf-8")
    _incident(root, 3600)
    result = _verify(root)
    assert result.returncode == 0, result.stderr
    joined = "\n".join(_skips(root))
    assert "verify" in joined
    assert "1 changed file(s) unverified" in joined


def test_verify_gate_logs_one_row_per_debt_not_one_per_turn(tmp_path):
    root = _repo(tmp_path)
    (root / "unverified.py").write_text("x = 1\n", encoding="utf-8")
    _incident(root, 3600)
    _verify(root)
    first = len(_skips(root))
    _verify(root)
    assert len(_skips(root)) == first, "a repeated identical skip must not stack"


def test_verify_gate_is_unaffected_by_an_expired_incident(tmp_path):
    # verify.json here has no rule for the changed file and unmapped is "warn",
    # so the gate exits 0 either way -- what this pins is that the expired
    # incident is not *recorded* as a stand-down.
    root = _repo(tmp_path)
    (root / "unverified.py").write_text("x = 1\n", encoding="utf-8")
    _incident(root, -60)
    result = _verify(root)
    assert result.returncode == 0, result.stderr
    assert _skips(root) == [], "an expired incident must not log a stand-down"
