"""Golden parity: the launcher gives what the registrations it replaced gave (L-0727, A5).

`record_golden_hooks.py` recorded, at the base SHA, what each `.sh` hook does
for a matrix of payloads (every event, the tool names of every matcher including
`PowerShell` and an MCP vault tool, a must-block and a must-allow payload per
guard, an armed and an unarmed repo, and stdin with a BOM, non-ASCII, CRLF and a
malformed JSON body). This suite replays each case through the REAL launcher for
this OS, in a fresh fixture, and holds the combined result to the spec's U2 merge
of the recorded children: exit code, block/allow, permissionDecision and every
blocking child's stderr.

The recorded argv of every child is also held against `crew_hook.select`, the
pure selector the dispatcher uses (the A5 `select` check), and the Codex-shaped
payloads are replayed with `--harness codex`.

Without python the POSIX launcher runs the scripts itself; its recorded
no-python outcomes (a restricted role blocked, an unrestricted one allowed,
a guard armed or not) are replayed under a PATH with no python in it.

Windows: golden stdout carries Linux paths and platform fields, so there the
comparison is exit code, block/allow and permissionDecision (`assert_same` with
`strict=False`); the win-repo-2 run of this file is spec A10's evidence.
"""
import json
import os
import re
import tempfile

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_hook
import crew_hook_harness as h
import record_golden_hooks as rgh

PYTHON_KEYS = h.golden_keys(False)
NO_PYTHON_KEYS = h.golden_keys(True)


def _payload_obj(record):
    try:
        value = json.loads(record["payload"].encode("utf-8").decode("utf-8-sig"))
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def test_the_golden_corpus_is_there_and_covers_every_event():
    events = {key[1] for key in PYTHON_KEYS}

    assert events == set(crew_hook.EVENTS)
    assert len(PYTHON_KEYS) >= 100 and len(NO_PYTHON_KEYS) >= 100
    assert {key[4] for key in PYTHON_KEYS} == {True, False}


@pytest.mark.parametrize("key", PYTHON_KEYS, ids=h.golden_ids)
def test_select_returns_the_recorded_argv_for_every_golden_case(key):
    record = rgh.load_golden()[key]

    chosen = crew_hook.select(record["event"], record["harness"], _payload_obj(record))

    assert [argv for _, argv in chosen] == [row["argv"] for row in record["rows"]]


@h.needs_bash
@pytest.mark.parametrize("flavour", h.POSIX_FLAVOURS)
@pytest.mark.parametrize("key", PYTHON_KEYS, ids=h.golden_ids)
def test_launcher_matches_the_golden_result(key, flavour, tmp_path):
    if h.WINDOWS and flavour == "sh":
        pytest.skip("crew-hook.sh exits 0 on Windows by design; the ps1 flavour is the one run here")
    record = rgh.load_golden()[key]
    if flavour == "ps1" and not h.WINDOWS and record["case"].startswith("powershell-cloud"):
        pytest.skip("the fake OS=Windows_NT stands the bash cloud-guard down for a PowerShell call (its twin "
                    "judges it on real Windows): test_crew_hook_windows.py runs that case natively")
    root, home = rgh.build_repo(str(tmp_path), record["armed"], record.get("dirty") or None)

    got = h.run_launcher(flavour, record["event"], h.payload_bytes(record, root), root, home,
                         harness=record["harness"])

    h.assert_same(h.expected(record), got, root, home, strict=not h.WINDOWS)


@h.needs_bash
@pytest.mark.skipif(h.WINDOWS, reason="the no-python POSIX path is not a Windows path (B10)")
@pytest.mark.parametrize("key", NO_PYTHON_KEYS, ids=h.golden_ids)
def test_launcher_without_python_matches_the_recorded_no_python_outcome(key, tmp_path):
    record = rgh.load_golden()[key]
    root, home = rgh.build_repo(str(tmp_path), record["armed"], record.get("dirty") or None)
    path = rgh.no_python_path(str(tmp_path))

    got = h.run_launcher("sh", record["event"], h.payload_bytes(record, root), root, home,
                         harness=record["harness"], path=path)

    want = h.expected_no_python(record)
    code, out, err = got
    assert code == want["exit"], err
    assert rgh.normalise(out, root, home) == want["stdout"]
    if code == 2:
        for line in want["stderr"].splitlines():
            assert line.strip() in rgh.normalise(err, root, home)


def test_the_golden_matrix_has_a_must_block_and_a_must_allow_per_guard():
    golden = rgh.load_golden()
    seen = {}
    for key, record in golden.items():
        if key[0] or record["variant"]:
            continue
        for row in record["rows"]:
            blocked = row["exit"] == 2 or '"permissionDecision": "deny"' in row["stdout"]
            seen.setdefault(row["script"], set()).add(blocked)
    guards = {"promote-gate.sh", "role-write-guard.sh", "cloud-guard.sh", "env-guard.sh", "scope-guard.sh",
              "approval-hook.sh"}

    assert {g for g in guards if seen.get(g) != {True, False}} == set()


def test_the_recorder_reports_drift_when_a_recorded_output_changes(tmp_path, monkeypatch):
    golden = rgh.load_golden()
    key = next(k for k in golden if not k[0] and k[1] == "Notification" and k[4])
    tampered = json.loads(json.dumps(golden[key]))
    tampered["rows"][0]["stdout"] = "changed"
    monkeypatch.setattr(rgh, "load_golden", lambda: {key: tampered})
    monkeypatch.setattr(rgh, "matrix", lambda no_python: iter([] if no_python else [golden[key]]))

    assert rgh.check() == 1


def test_a_temp_directory_name_in_a_recording_is_normalised_away():
    with tempfile.TemporaryDirectory() as base:
        root = os.path.join(base, "r")
        home = os.path.join(base, "home")

        text = rgh.normalise(f"in {root}/src and {home}/.claude", root, home)

    assert text == "in <ROOT>/src and <HOME>/.claude" and re.search(r"<ROOT>", text)
