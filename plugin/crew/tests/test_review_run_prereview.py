"""`review_run.py`'s pre-review checks (L-0574): question 3 of BEFORE ANY
ROUND IS RESERVED, between the verify gate and the standards self-check.

Every must-block case snapshots the ledger under the throwaway repo's
git-common-dir and asserts it byte-identical afterwards, so "no round spent"
is measured, not inferred. The linter is `test_review_checks`'s fake, through
the real `command` slot. The verify gate is stood down (`"verifyGate": false`)
except where a case is about the gate, so the checks are what decides.
"""
import json
import os
import re
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_incident
import crew_standards as cs
import crew_ticket
import review_checks as rc
import review_ledger as rl
import scope_base
from review_fixtures import env_with_path, fake_reviewer_bin, git, init_repo
from test_review_checks import _FAKE

_SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access
_RUN = os.path.join(_SCRIPTS, "review_run.py")
_PATCH = os.path.join(_SCRIPTS, "review_patch.py")
TICKET = "T-1"
_PROVIDERS = {"codex": (), "claude": ("--reserve-only",)}


@pytest.fixture(name="fake")
def _fake(tmp_path):
    path = tmp_path / "fake_lint.py"
    path.write_text(_FAKE, encoding="utf-8")
    return str(path)


def _ruff(fake):
    return {"tool": "ruff", "command": [sys.executable, fake, "ruff"]}


def _missing():
    return {"tool": "ruff", "command": ["no-such-linter-l0574"]}


def _setup(tmp_path, linters, py_text="# LINT BLE001 new\n", gate=False, crew_cfg=None,
           extra=None):
    """A repo with an approval receipt, its crew config and verify map written
    BEFORE the self-check is stamped, a .py change, a stamped self-check and
    a bundle. `linters` None writes no `preReview` key."""
    repo = init_repo(tmp_path / "r")
    (repo / "m.py").write_text("x0\n", encoding="utf-8")
    for rel in extra or {}:
        (repo / rel).write_text("x\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "py")
    scope_base.record(str(repo), TICKET)
    path = crew_ticket.approval_path(str(repo), TICKET)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"ticket": TICKET, "approved_by": "fixture"}, fh)
    (repo / ".crew").mkdir(exist_ok=True)
    cfg = dict(crew_cfg or {})
    if not gate:
        cfg["verifyGate"] = False
    (repo / ".crew" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    verify = {"version": 1, "default": [], "unmapped": "ignore",
              "rules": [{"paths": ["**"], "seconds": 1, "run": ["echo ok"], "why": "fixture"}]}
    if linters is not None:
        verify[rc.CONFIG_KEY] = {"linters": linters}
    (repo / ".crew" / "verify.json").write_text(json.dumps(verify), encoding="utf-8")
    (repo / "m.py").write_text(py_text, encoding="utf-8")
    for rel, text in (extra or {}).items():
        (repo / rel).write_text(text, encoding="utf-8")
    _stamp(repo)
    scratch = tmp_path / "scratch"
    _bundle(repo, scratch)
    return repo, scratch


def _stamp(repo):
    assert cs.init(str(repo), TICKET)[0] == 0
    path = repo / ".work" / "tickets" / TICKET / "selfcheck.md"
    path.write_text(re.sub(r"^\| ([A-Z]+-\d\d) \|  \|  \|$",
                           r"| \1 | n/a | the fixture change is one file |",
                           path.read_text(encoding="utf-8"), flags=re.M), encoding="utf-8")
    code, lines = cs.stamp(str(repo), TICKET)
    assert code == 0, lines


def _bundle(repo, scratch):
    base = scope_base.resolve(str(repo), TICKET)[0]
    scratch.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, _PATCH, "--root", str(repo), "--base", base,
                    "--out", str(scratch / "diff.txt"), "--manifest", str(scratch / "manifest.json")],
                   check=True, capture_output=True, stdin=subprocess.DEVNULL)
    (scratch / "prompt.txt").write_text(
        "Review. " + " ".join(p["name"] for p in json.loads(
            (scratch / "manifest.json").read_text(encoding="utf-8"))["parts"]), encoding="utf-8")


def _ledger_snapshot(repo):
    common = git(repo, "rev-parse", "--git-common-dir")
    base = os.path.join(repo if not os.path.isabs(common) else "", common, "crew", "review")
    found = {}
    for dirpath, _, names in os.walk(base):
        for name in names:
            with open(os.path.join(dirpath, name), "rb") as fh:
                found[os.path.join(dirpath, name)] = fh.read()
    return found


def _run(repo, scratch, tmp_path, provider, *extra):
    argv = [sys.executable, _RUN, "--root", str(repo), "--ticket", TICKET,
            "--scratch", str(scratch), "--provider", provider,
            "--work-dir", str(tmp_path / "work")] + list(_PROVIDERS.get(provider, ())) + list(extra)
    return subprocess.run(argv, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                          check=False, timeout=180,
                          env=env_with_path(fake_reviewer_bin(tmp_path / "bin"),
                                            FAKE_REVIEWER_MODE="clean"))


def _record(scratch):
    """The round's record when a round was reserved, else the one record a
    refusing run staged."""
    bound = sorted(scratch.glob(f"prereview-{TICKET}-r*.json"))
    found = bound or sorted(scratch.glob("prereview.run-*.json"))
    assert len(found) == 1, found
    return json.loads(found[-1].read_text(encoding="utf-8"))


@pytest.mark.parametrize("provider", sorted(_PROVIDERS))
def test_new_finding_refuses_before_reserve(tmp_path, fake, provider):
    repo, scratch = _setup(tmp_path, [_ruff(fake)])
    before = _ledger_snapshot(repo)

    result = _run(repo, scratch, tmp_path, provider)

    assert (result.returncode, "NEW x1 m.py: BLE001 new" in result.stderr,
            _ledger_snapshot(repo) == before, _record(scratch)["result"]) == (
        5, True, True, rc.FAIL), result.stderr


@pytest.mark.parametrize("linters", ["new-alone", "new-and-could-not"])
def test_new_finding_is_not_overridable(tmp_path, fake, linters):
    chosen = [_ruff(fake)] + ([_missing()] if linters == "new-and-could-not" else [])
    repo, scratch = _setup(tmp_path, chosen)
    before = _ledger_snapshot(repo)

    result = _run(repo, scratch, tmp_path, "claude", "--allow-unverified")

    assert (result.returncode, _ledger_snapshot(repo) == before,
            "does not override a new finding" in result.stderr) == (5, True, True), result.stderr


def test_could_not_check_refuses_unless_allow_unverified(tmp_path):
    repo, scratch = _setup(tmp_path, [_missing()])
    before = _ledger_snapshot(repo)

    refused = _run(repo, scratch, tmp_path, "claude")
    refused_ledger_same = _ledger_snapshot(repo) == before
    allowed = _run(repo, scratch, tmp_path, "claude", "--allow-unverified")

    assert (refused.returncode, refused_ledger_same, "COULD NOT CHECK" in refused.stderr,
            allowed.returncode, "ROUND=1" in allowed.stdout, _record(scratch)["overridden"]) == (
        5, True, True, 0, True, True), refused.stderr + allowed.stderr


def test_incident_stands_checks_down(tmp_path, fake):
    repo, scratch = _setup(tmp_path, [_ruff(fake)])
    crew_incident.declare(str(repo), "fixture incident")

    result = _run(repo, scratch, tmp_path, "claude")

    skips = crew_incident.read_skips(str(repo))
    assert (result.returncode, "ROUND=1" in result.stdout, _record(scratch)["stood_down"],
            any("prereview-checks" in json.dumps(s) for s in skips)) == (
        0, True, True, True), result.stderr


@pytest.mark.parametrize("case", ["expired", "standdown-off"])
def test_only_an_active_incident_stands_down(tmp_path, fake, case):
    cfg = {"emergency": {"standDown": False}} if case == "standdown-off" else None
    repo, scratch = _setup(tmp_path, [_ruff(fake)], crew_cfg=cfg)
    now = None if case == "standdown-off" else 1_000_000
    crew_incident.declare(str(repo), "fixture incident", cfg=cfg, now=now)

    result = _run(repo, scratch, tmp_path, "claude")

    assert result.returncode == 5, result.stderr


def test_order_gate_before_checks(tmp_path, fake):
    repo, scratch = _setup(tmp_path, [_ruff(fake)], gate=True)

    result = _run(repo, scratch, tmp_path, "codex")

    assert (result.returncode, "gate UNVERIFIED" in result.stderr,
            "pre-review checks" in result.stderr) == (5, True, False), result.stderr


def test_order_checks_before_selfcheck(tmp_path, fake):
    repo, scratch = _setup(tmp_path, [_ruff(fake)])
    os.remove(repo / ".work" / "tickets" / TICKET / "selfcheck.md")

    result = _run(repo, scratch, tmp_path, "codex")

    assert (result.returncode, "pre-review checks: ruff FAIL" in result.stderr,
            "self-check" in result.stderr) == (5, True, False), result.stderr


def test_spent_budget_skips_checks(tmp_path, fake):
    repo, scratch = _setup(tmp_path, [_ruff(fake)])
    for _ in range(2):
        assert rl.reserve(str(repo), TICKET, "claude")[0]

    result = _run(repo, scratch, tmp_path, "codex")

    assert (result.returncode, "pre-review checks" in result.stderr) == (4, False), result.stderr


def test_unconfigured_proceeds_and_says_so(tmp_path):
    repo, scratch = _setup(tmp_path, None)

    result = _run(repo, scratch, tmp_path, "claude")

    assert (result.returncode, "ROUND=1" in result.stdout,
            "pre-review checks: none configured" in result.stderr,
            _record(scratch)["result"]) == (0, True, True, rc.NOT_CONFIGURED), result.stderr


def test_review_json_records_prereview(tmp_path, fake):
    repo, scratch = _setup(tmp_path, [_ruff(fake)], py_text="clean\n")

    result = _run(repo, scratch, tmp_path, "codex")

    review = json.loads((tmp_path / "work" / "review.json").read_text(encoding="utf-8"))
    assert (result.returncode, review["prereview"]["result"],
            [c["status"] for c in review["prereview"]["checks"]]) == (
        0, rc.PASS, [rc.PASS]), result.stdout + result.stderr


@pytest.mark.parametrize("record", ["kept", "removed"])
def test_claude_completion_carries_prereview(tmp_path, fake, record):
    repo, scratch = _setup(tmp_path, [_ruff(fake)], py_text="clean\n")
    reserved = _run(repo, scratch, tmp_path, "claude")
    assert "ROUND=1" in reserved.stdout, reserved.stderr
    if record == "removed":
        os.remove(rc.round_record_path(str(scratch), TICKET, 1))
    manifest = json.loads((scratch / "manifest.json").read_text(encoding="utf-8"))
    out = tmp_path / "out.txt"
    out.write_text("\n".join("READ|" + p["path"] for p in manifest["parts"]) + "\nCLEAN\n",
                   encoding="utf-8")

    done = subprocess.run([sys.executable, _RUN, "--root", str(repo), "--ticket", TICKET,
                           "--scratch", str(scratch), "--provider", "claude", "--round", "1",
                           "--output", str(out), "--exit-code", "0",
                           "--work-dir", str(tmp_path / "work")],
                          capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False,
                          timeout=120)

    review = json.loads((tmp_path / "work" / "review.json").read_text(encoding="utf-8"))
    expected = rc.PASS if record == "kept" else rc.NOT_RECORDED
    assert (done.returncode, review["prereview"]["result"]) == (0, expected), done.stderr


def test_a_record_that_cannot_be_written_is_said_not_fatal(tmp_path, fake):
    repo, scratch = _setup(tmp_path, [_ruff(fake)], py_text="clean\n")
    missing = tmp_path / "no-such-scratch"

    result = subprocess.run(
        [sys.executable, _RUN, "--root", str(repo), "--ticket", TICKET, "--scratch", str(missing),
         "--manifest", str(scratch / "manifest.json"), "--provider", "claude", "--reserve-only"],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False, timeout=120)

    assert (result.returncode, "ROUND=1" in result.stdout,
            "could not record the pre-review checks" in result.stderr) == (0, True, True), (
        result.stdout + result.stderr)


def test_allow_unverified_never_passes_a_new_finding_beside_a_parse_failure(tmp_path, fake):
    sh = {"tool": "shellcheck", "command": [sys.executable, fake, "shellcheck"]}
    repo, scratch = _setup(tmp_path, [sh], py_text="x\n", extra={
        "a.sh": "x\n# LINT 2086 a new problem\n", "b.sh": "# ABORT\n"})
    before = _ledger_snapshot(repo)

    result = _run(repo, scratch, tmp_path, "claude", "--allow-unverified")

    assert (result.returncode, _ledger_snapshot(repo) == before,
            _record(scratch)["result"]) == (5, True, rc.FAIL), result.stderr


def test_the_record_is_bound_to_the_manifest_the_checks_read(tmp_path, fake, monkeypatch):
    """Review round 4: the bundle hash comes from the same read of the
    manifest as the linted entries. A manifest replaced while the linters run
    cannot have the results recorded against it."""
    import argparse  # pylint: disable=import-outside-toplevel
    import review_run  # pylint: disable=import-outside-toplevel
    repo, scratch = _setup(tmp_path, [_ruff(fake)], py_text="x\n")
    manifest = scratch / "manifest.json"
    checked = json.loads(manifest.read_text(encoding="utf-8"))["bundle_sha256"]
    real = rc.check_one

    def swapping(*args, **kwargs):
        result = real(*args, **kwargs)
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["bundle_sha256"] = "b" * 64
        manifest.write_text(json.dumps(data), encoding="utf-8")
        return result

    monkeypatch.setattr(rc, "check_one", swapping)
    args = argparse.Namespace(root=str(repo), manifest=str(manifest), scratch=str(scratch),
                              allow_unverified=False, ticket=TICKET)

    assert (review_run.prereview_gate(args), _record(scratch)["bundle_sha256"]) == (
        None, checked)


def test_two_runs_sharing_a_scratch_do_not_swap_records(tmp_path):
    """L-0574 review round 6 FIX :788: an --allow-unverified run reserves
    round 1; a second, refusing run for the same bundle in the same scratch
    then writes its own record. Round 1's review.json still carries round
    1's override."""
    repo, scratch = _setup(tmp_path, [_missing()])
    allowed = _run(repo, scratch, tmp_path, "claude", "--allow-unverified")
    refused = _run(repo, scratch, tmp_path, "claude")
    manifest = json.loads((scratch / "manifest.json").read_text(encoding="utf-8"))
    out = tmp_path / "out.txt"
    out.write_text("\n".join("READ|" + p["path"] for p in manifest["parts"]) + "\nCLEAN\n",
                   encoding="utf-8")

    done = subprocess.run([sys.executable, _RUN, "--root", str(repo), "--ticket", TICKET,
                           "--scratch", str(scratch), "--provider", "claude", "--round", "1",
                           "--output", str(out), "--exit-code", "0",
                           "--work-dir", str(tmp_path / "work")],
                          capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False,
                          timeout=120)
    review = json.loads((tmp_path / "work" / "review.json").read_text(encoding="utf-8"))

    assert ("ROUND=1" in allowed.stdout, refused.returncode, done.returncode,
            review["prereview"]["overridden"], review["prereview"]["round"]) == (
        True, 5, 0, True, 1), allowed.stderr + refused.stderr + done.stderr


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_a_symlinked_parts_directory_is_never_read_as_the_bundle(tmp_path, fake):
    """Neighbour of review round 7 BLOCK :172 in review_run: the parts live in
    `<out>.parts/`, and that directory swapped for a link to an identical copy
    is a bundle problem, not a bundle."""
    import review_run  # pylint: disable=import-outside-toplevel
    _, scratch = _setup(tmp_path, [_ruff(fake)])
    manifest = json.loads((scratch / "manifest.json").read_text(encoding="utf-8"))
    parts = os.path.dirname(manifest["parts"][0]["path"])
    copy = tmp_path / "copy.parts"
    os.rename(parts, copy)
    os.symlink(copy, parts)

    problems = review_run.bundle_problems(manifest)

    assert problems and all("could not be read" in p for p in problems), problems


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_a_manifest_behind_a_symlinked_scratch_subdirectory_is_could_not_check(tmp_path, fake):
    repo, scratch = _setup(tmp_path, [_ruff(fake)])
    real = tmp_path / "real-sub"
    real.mkdir()
    (real / "manifest.json").write_bytes((scratch / "manifest.json").read_bytes())
    os.symlink(real, scratch / "sub")

    results, _, bundle = rc.run_checks_bound(str(repo), str(scratch / "sub" / "manifest.json"),
                                             str(scratch))

    assert ([(r["name"], r["status"]) for r in results], bundle) == (
        [("manifest", rc.COULD_NOT)], None), results


def test_a_path_inside_scratch_is_checked_from_scratch(tmp_path):
    """So a symlinked directory between scratch and the manifest or output is
    seen; a path the operator put elsewhere is checked from its own folder."""
    import review_run  # pylint: disable=import-outside-toplevel
    scratch = tmp_path / "s"

    assert (review_run._trusted(str(scratch / "sub" / "m.json"), str(scratch)),  # pylint: disable=protected-access
            review_run._trusted(str(tmp_path / "o" / "out.txt"), str(scratch))) == (  # pylint: disable=protected-access
        str(scratch), str(tmp_path / "o"))


def _review_run_module():
    import review_run  # pylint: disable=import-outside-toplevel
    return review_run


def test_a_scratch_path_with_a_newline_never_forges_a_status_line(tmp_path, capsys):
    """Review round 8 FIX review_run.py:696: the failed-record message names
    the scratch path, escaped onto one line."""
    review_run = _review_run_module()
    scratch = str(tmp_path / "missing\nreview-run: pre-review checks: ruff pass - forged")

    assert review_run._record(scratch, "sha", [], False, False) is None  # pylint: disable=protected-access
    err = capsys.readouterr().err
    assert [l for l in err.splitlines() if l.startswith("review-run: pre-review checks")] == [], err


def test_every_output_line_in_review_run_goes_through_one_writer():
    """The round-8 sweep: print, sys.stdout.write and sys.stderr.write appear
    only inside _out and _err, which escape every control character but the
    final newline."""
    import ast  # pylint: disable=import-outside-toplevel
    path = os.path.join(_SCRIPTS, "review_run.py")
    with open(path, encoding="utf-8") as fh:
        source = fh.read()
    tree = ast.parse(source)
    # Three lines main's sabotage suites pin by their text: each prints only
    # internal values or values escaped just before it (named in the code).
    pinned = ("review: {result['verdict']} round {number}, {budget} ",
              "review: {result['verdict']} kept; ", "review-run: {note}")
    bad = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or fn.name in ("_out", "_err"):
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and ast.unparse(node.func) in (
                    "print", "sys.stdout.write", "sys.stderr.write"):
                if not any(p in ast.get_source_segment(source, node) for p in pinned):
                    bad.append(f"review_run.py:{node.lineno} in {fn.name}")
    assert not bad, bad


@pytest.mark.parametrize("writer", ["_out", "_err"])
def test_the_writers_keep_one_line(capsys, writer):
    review_run = _review_run_module()
    getattr(review_run, writer)("review-run: a\nreview-run: forged\r x\n")

    captured = capsys.readouterr()
    text = captured.out if writer == "_out" else captured.err
    assert text.count("\n") == 1 and text.endswith("\n"), repr(text)


class _Job:
    def __init__(self, pid_file):
        self.calls, self.pid_file = [], pid_file

    def adopt(self, proc):
        self.calls.append("adopt")

    def terminate(self):
        self.calls.append("terminate")
        try:
            with open(self.pid_file, encoding="utf-8") as fh:
                os.kill(int(fh.read()), 9)
        except (OSError, ValueError):
            pass

    def close(self):
        self.calls.append("close")


_ORPHAN_PROVIDER = (
    "import subprocess, sys\n"
    "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
    "open(sys.argv[1], 'w').write(str(child.pid))\n")


@pytest.mark.skipif(os.name == "nt", reason="drives the Windows branch with a fake job on POSIX")
def test_a_provider_whose_leader_exited_has_its_job_ended_on_timeout(tmp_path, monkeypatch):
    """Neighbour of review round 8 FIX :574 in review_run.launch: the leader
    exits, its child keeps the pipe; on Windows the job ends the child, so
    nothing escapes."""
    review_run = _review_run_module()
    pid_file = tmp_path / "pid"
    job = _Job(str(pid_file))
    monkeypatch.setattr(rc, "_WINDOWS", True)
    monkeypatch.setattr(rc, "new_job", lambda kill_on_close: job)
    monkeypatch.setattr(review_run, "_launch_flags", lambda j: {"start_new_session": True})

    _, stderr, _, timed_out = review_run.launch(
        [sys.executable, "-c", _ORPHAN_PROVIDER, str(pid_file)], str(tmp_path), 2)

    assert (timed_out, job.calls, "escaped" in (stderr or "")) == (
        True, ["adopt", "terminate", "close"], False), stderr


def test_a_self_check_note_with_a_newline_prints_on_one_line(monkeypatch, capsys):
    """The pinned `review-run: {note}` write: the note is escaped first."""
    import types  # pylint: disable=import-outside-toplevel
    review_run = _review_run_module()
    monkeypatch.setattr(cs, "review_gate", lambda *a: (
        [], "standards self-check current (std:abcd1234)\nreview-run: pre-review checks: forged"))
    args = types.SimpleNamespace(root=".", ticket=TICKET, manifest="m.json")

    review_run.standards_gate(args)

    err = capsys.readouterr().err
    assert [l for l in err.splitlines() if "pre-review checks" in l and l.startswith("review-run: pre")] == [], err


def _reserve_then_finish(tmp_path, out_path, before_finish=None):
    """Reserve claude round 1, optionally disturb the scratch, then make the
    second call with `--output out_path`. Returns (completed, review.json or None)."""
    repo, scratch = _setup(tmp_path, [_missing()])
    reserved = _run(repo, scratch, tmp_path, "claude", "--allow-unverified")
    assert "ROUND=1" in reserved.stdout, reserved.stderr
    if before_finish:
        before_finish(scratch)
    done = subprocess.run([sys.executable, _RUN, "--root", str(repo), "--ticket", TICKET,
                           "--scratch", str(scratch), "--provider", "claude", "--round", "1",
                           "--output", str(out_path(scratch)), "--exit-code", "0",
                           "--work-dir", str(tmp_path / "work")],
                          capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False,
                          timeout=120)
    path = tmp_path / "work" / "review.json"
    return done, (json.loads(path.read_text(encoding="utf-8")) if path.exists() else None)


def _clean_output(scratch, where):
    manifest = json.loads((scratch / "manifest.json").read_text(encoding="utf-8"))
    where.write_text("\n".join("READ|" + p["path"] for p in manifest["parts"]) + "\nCLEAN\n",
                     encoding="utf-8")


@pytest.mark.parametrize("kind", ["symlink", "fifo", "directory"])
def test_claude_output_that_is_not_a_regular_file_is_incomplete(tmp_path, kind):
    """L-0605, review round 10 FIX review_run.py:955: an --output that
    read_regular refuses, after the round was reserved, is an INCOMPLETE
    round with the reason, never an escaped NotRegularFile."""
    if kind == "symlink" and os.name == "nt":
        pytest.skip("symlinks need privileges on Windows")
    if kind == "fifo" and not hasattr(os, "mkfifo"):
        pytest.skip("no os.mkfifo here")
    odd = tmp_path / "odd-out"

    def make(scratch):
        if kind == "symlink":
            real = tmp_path / "real-out.txt"
            _clean_output(scratch, real)
            os.symlink(real, odd)
        elif kind == "fifo":
            os.mkfifo(odd)
        else:
            odd.mkdir()

    done, review = _reserve_then_finish(tmp_path, lambda s: odd, make)

    assert (done.returncode, "Traceback" in done.stderr, (review or {}).get("verdict")) == (
        3, False, "INCOMPLETE"), done.stderr
    assert any("could not be read" in r and "not a regular file" in r
               for r in review["reasons"]), review["reasons"]


_MALFORMED = {"list": [], "parts-null": {"parts": [None]}, "parts-str": {"parts": "x"},
              "empty-path": {"parts": [{"path": ""}]}, "sha-int": "SHA5"}


@pytest.mark.parametrize("case", ["symlink"] + sorted(_MALFORMED))
def test_an_unreadable_manifest_at_finish_is_incomplete(tmp_path, case):
    """L-0605 (F3b, the neighbouring read): the manifest swapped after the
    reservation, unreadable or malformed, is INCOMPLETE with a manifest
    reason; review.json is still written and prereview is not-recorded."""
    if case == "symlink" and os.name == "nt":
        pytest.skip("symlinks need privileges on Windows")

    def swap(scratch):
        manifest = scratch / "manifest.json"
        _clean_output(scratch, tmp_path / "out.txt")
        if case == "symlink":
            copy = scratch / "manifest-copy.json"
            copy.write_bytes(manifest.read_bytes())
            manifest.unlink()
            os.symlink(copy, manifest)
        elif case == "sha-int":
            data = json.loads(manifest.read_text(encoding="utf-8"))
            data["bundle_sha256"] = 5
            manifest.write_text(json.dumps(data), encoding="utf-8")
        else:
            manifest.write_text(json.dumps(_MALFORMED[case]), encoding="utf-8")

    done, review = _reserve_then_finish(tmp_path, lambda s: tmp_path / "out.txt", swap)

    expected = "could not be read" if case == "symlink" else "is malformed"
    assert (done.returncode, "Traceback" in done.stderr, (review or {}).get("verdict"),
            (review or {}).get("prereview", {}).get("result")) == (
        3, False, "INCOMPLETE", "not-recorded"), done.stderr
    assert any("the manifest" in r and expected in r for r in review["reasons"]), review["reasons"]
