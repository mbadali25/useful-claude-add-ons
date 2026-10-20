"""Shared helpers for the crew-hook launcher suites (L-0727): run the REAL
launcher for this OS in a constructed environment and compare it to the golden
per-script outputs `record_golden_hooks.py` recorded.

Everything runs under pytest's tmp_path with a temporary HOME; nothing here
touches the real config or the real checkout. The PowerShell launcher runs
under pwsh with `OS=Windows_NT` on a POSIX host so its flavour guard proceeds
(the dispatcher itself still picks POSIX rows there); on Windows that variable
is already set and the `.sh` launcher is not run at all.
"""
import json
import os
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
import record_golden_hooks as rgh

SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access
SH = os.path.join(SCRIPTS, "crew-hook.sh")
PS1 = os.path.join(SCRIPTS, "crew-hook.ps1")
BASH = crew_fixtures.resolve_bash()
PWSH = crew_fixtures.resolve_pwsh()
WINDOWS = os.name == "nt"

needs_bash = pytest.mark.skipif(BASH is None or WINDOWS, reason="no POSIX bash - crew-hook.sh was NOT run")
needs_pwsh = pytest.mark.skipif(PWSH is None, reason="pwsh not installed - crew-hook.ps1 was NOT run")
# The launcher for this OS: sh on POSIX, ps1 on Windows. ps1 on POSIX is the
# fake-OS model and runs as a slow case.
FLAVOURS = ("sh",) if not WINDOWS else ("ps1",)
POSIX_FLAVOURS = ("sh", pytest.param("ps1", marks=crew_fixtures.SLOW))


def launcher_argv(flavour, event, harness="claude"):
    if flavour == "sh":
        argv = [BASH or "bash", SH, event]
        return argv + (["--harness", "codex"] if harness == "codex" else [])
    argv = [PWSH or "pwsh", "-NoProfile", "-File", PS1, event]
    return argv + (["-Harness", "codex"] if harness == "codex" else [])


def run_launcher(flavour, event, data, root, home, harness="claude", env_extra=None, path=None,
                 timeout=180):
    """(exit, stdout, stderr) of the real launcher with `data` on stdin."""
    env = rgh.env_for(root, home, path=path)
    if flavour == "ps1" and not WINDOWS:
        env["OS"] = "Windows_NT"
    if env_extra:
        env.update(env_extra)
    done = subprocess.run(launcher_argv(flavour, event, harness), input=data, capture_output=True,
                          env=env, cwd=root, timeout=timeout, check=False)
    return done.returncode, done.stdout.decode("utf-8", "replace"), done.stderr.decode("utf-8", "replace")


def golden_ids(key):
    _, event, case, variant, armed = key
    return f"{event}/{case}{('+' + variant) if variant else ''}.{'armed' if armed else 'unarmed'}"


def golden_keys(no_python):
    return sorted((k for k in rgh.load_golden() if k[0] is no_python), key=golden_ids)


def payload_bytes(record, root):
    return record["payload"].replace("{ROOT}", root.replace("\\", "/")).encode("utf-8")


def _json(text):
    stripped = (text or "").strip()
    if not stripped.startswith("{"):
        return None
    try:
        value = json.loads(stripped)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


RANK = {"deny": 3, "ask": 2, "allow": 1}


def expected(record):
    """What the launcher must print for the recorded children, worked out here
    from the spec's U2 rule and NOT by calling crew_hook.merge (a test that asks
    the code under test for its own answer cannot go red when that code breaks).
    Returns the facts `assert_same` checks."""
    rows = record["rows"]
    blockers = [row for row in rows if row["exit"] == 2]
    live = [row for row in rows if row["stdout"].strip()]
    decisions = []
    pieces = []
    block = False
    for row in live:
        obj = _json(row["stdout"])
        if obj is None:
            pieces.append(row["stdout"].strip())
            continue
        hso = obj.get("hookSpecificOutput") or {}
        if hso.get("permissionDecision"):
            decisions.append(hso["permissionDecision"])
        if hso.get("additionalContext"):
            pieces.append(hso["additionalContext"])
        block = block or obj.get("decision") == "block"
    return {
        "exit": 2 if blockers else 0,
        "blocking_stderr": "".join(row["stderr"] for row in blockers),
        "stderr": "".join(row["stderr"] for row in rows),
        "single": live[0]["stdout"] if len(live) == 1 else None,
        "silent": not live,
        "decision": max(decisions, key=lambda d: RANK.get(d, 0)) if decisions else None,
        "block": block,
        "pieces": pieces,
        "mixed": len(live) > 1 and any(_json(row["stdout"]) is not None for row in live),
    }


def expected_no_python(record):
    """Without python the launcher concatenates stdout and ORs exit 2."""
    rows = record["rows"]
    blockers = [row for row in rows if row["exit"] == 2]
    if blockers:
        return {"exit": 2, "stdout": "", "stderr": "".join(row["stderr"] for row in blockers)}
    return {"exit": 0, "stdout": "".join(row["stdout"] for row in rows),
            "stderr": "".join(row["stderr"] for row in rows)}


def assert_same(want, got, root, home, strict=True):
    """The launcher's exit code, stdout and stderr against `expected`'s facts.
    `strict=False` (Windows, whose paths and platform fields differ from the
    Linux recording) compares exit, block/allow and permissionDecision only,
    and that a block carries a reason on stderr."""
    code, out, err = got
    err = rgh.normalise(err, root, home)
    out = rgh.normalise(out, root, home)
    assert code == want["exit"], f"exit {code} != {want['exit']}; stderr: {err!r}"
    obj = _json(out)
    hso = (obj or {}).get("hookSpecificOutput") or {}
    if not strict:
        assert hso.get("permissionDecision") == want["decision"]
        assert (code != 2) or err.strip()
        return
    if code == 2:
        for line in want["blocking_stderr"].splitlines():
            assert line.strip() in err, f"blocking text missing: {line!r}"
        return
    assert err == want["stderr"]
    if want["silent"]:
        assert out.strip() == ""
    elif want["single"] is not None:
        if obj is not None and _json(want["single"]) is not None:
            assert obj == _json(want["single"])
        else:
            assert out == want["single"]
    else:
        assert hso.get("permissionDecision") == want["decision"]
        assert (obj or {}).get("decision") == ("block" if want["block"] else None)
        merged_context = hso.get("additionalContext", "") if obj is not None else out
        for piece in want["pieces"]:
            assert piece in merged_context, f"missing from the merged output: {piece!r}"


def read_text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()
