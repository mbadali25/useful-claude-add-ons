#!/usr/bin/env python3
"""Regression suite for scripts/gate-runner.py -- the one local gate runner.

Every case builds throwaway fixtures in a temp directory: a fake root, a step
table written as JSON for `--table`, and a fake heavy-run that logs each call
and marks what it runs with FAKE_HEAVY_RUN=1. No case runs a real repository
step, reads real config, or calls the machine's real heavy-run. The two drift
cases read this repository's `.github/workflows/` (read only).

What the runner exists to get right, and so what most cases pin:
- a step that times out, is killed, cannot start, or leaves no result is
  COULD-NOT-TELL, never PASS (T-0082);
- cheap steps run outside heavy-run; the heavy groups and the solo tail are
  ONE heavy-run call; groups A and B really run at the same time (proved by a
  rendezvous, not a stopwatch);
- every pytest step but `wallclock` carries a literal `-n 4`, and no xdist
  means COULD-NOT-TELL, never a quiet serial run;
- the step table covers every `run:` line of the PR-path CI workflows.

Exit: 0 all passed, 1 any failed, 77 none failed but a case was SKIPPED
(pyyaml missing for the drift cases) -- a skip is never reported as a pass.

Run: python3 scripts/_test/gate-runner.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
TARGET = os.path.join(os.path.dirname(HERE), "gate-runner.py")
CALL_TIMEOUT = 180


class Skip(Exception):
    """A case that could not run here; counted, never passed."""


def load_runner():
    spec = importlib.util.spec_from_file_location("gate_runner", TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolves annotations through sys.modules
    spec.loader.exec_module(module)
    return module


def write(path: str, text: str, mode: int | None = None) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    if mode is not None:
        os.chmod(path, mode)
    return path


def fake_heavy_run(tmp: str, body: str | None = None) -> str:
    """A heavy-run stand-in: one line per call (args and whether either cap
    variable is set), then run the command with FAKE_HEAVY_RUN=1."""
    calls = os.path.join(tmp, "heavy-calls.txt")
    if body is None:
        body = 'FAKE_HEAVY_RUN=1 exec "$@"\n'
    script = (
        "#!/bin/sh\n"
        f'echo "call nocap=${{HEAVY_RUN_NOCAP:-unset}} mem=${{HEAVY_RUN_MEM:-unset}} $*" >> "{calls}"\n'
        + body
    )
    return write(os.path.join(tmp, "fake-heavy-run"), script, 0o755)


def trace_step(tmp: str, name: str, phase: str, group: str | None = None,
               extra: str = "", timeout: int = 60) -> dict:
    """A step that records its name, FAKE_HEAVY_RUN and the cap variables."""
    trace = os.path.join(tmp, "trace.txt")
    cmd = (f'echo "{name} fake=${{FAKE_HEAVY_RUN:-unset}} nocap=${{HEAVY_RUN_NOCAP:-unset}} '
           f'mem=${{HEAVY_RUN_MEM:-unset}}" >> "{trace}"' + (f"; {extra}" if extra else ""))
    return {"name": name, "phase": phase, "group": group, "argv": ["sh", "-c", cmd],
            "timeout": timeout}


def sh_step(name: str, phase: str, cmd: str, group: str | None = None, timeout: int = 60,
            **kw) -> dict:
    step = {"name": name, "phase": phase, "group": group, "argv": ["sh", "-c", cmd],
            "timeout": timeout}
    step.update(kw)
    return step


def part_row(name: str, state: str, rc, reason: str = "", phase: str = "heavy",
             group: str | None = "A", cwd: str = ".", timeout: int = 60,
             argv: list | None = None) -> dict:
    """A heavy-part.json result as run_step writes it: every field status.json
    must carry for a step, matching sh_step's table defaults."""
    return {"name": name, "phase": phase, "group": group,
            "argv": ["sh", "-c", "exit 0"] if argv is None else argv, "cwd": cwd,
            "timeout": timeout, "rc": rc, "state": state, "reason": reason, "seconds": 0.0,
            "log": "/nonexistent.log"}


def read_trace(tmp: str) -> dict:
    path = os.path.join(tmp, "trace.txt")
    out = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                out[parts[0]] = dict(p.split("=", 1) for p in parts[1:])
    return out


def run_gate(tmp: str, steps: list[dict] | None, *args: str, heavy: str = "none",
             env_extra: dict | None = None, grace: str = "1", cwd: str | None = None):
    """Run the CLI on a fixture table. Returns (rc, stdout, status-or-None)."""
    root = os.path.join(tmp, "root")
    os.makedirs(root, exist_ok=True)
    out = os.path.join(tmp, "out")
    argv = [sys.executable, TARGET, "--root", root, "--out", out, "--grace", grace]
    if steps is not None:
        table = write(os.path.join(tmp, "table.json"), json.dumps({"steps": steps}))
        argv += ["--table", table]
    argv += list(args)
    env = {k: v for k, v in os.environ.items()
           if k not in ("HEAVY_RUN_NOCAP", "HEAVY_RUN_MEM", "HEAVY_RUN")}
    env["HEAVY_RUN"] = heavy
    env.update(env_extra or {})
    proc = subprocess.run(argv, capture_output=True, text=True, env=env, cwd=cwd,
                          stdin=subprocess.DEVNULL, timeout=CALL_TIMEOUT, check=False)
    status = None
    path = os.path.join(out, "status.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            status = json.load(fh)
    return proc.returncode, proc.stdout + proc.stderr, status


def by_name(status: dict) -> dict:
    assert status is not None, "no status.json written"
    return {s["name"]: s for s in status["steps"]}


def expect(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


# ---- Acceptance 1 ---------------------------------------------------------

def case_list_prints_phases(tmp: str) -> None:
    proc = subprocess.run([sys.executable, TARGET, "--list"], capture_output=True, text=True,
                          timeout=CALL_TIMEOUT, check=False, stdin=subprocess.DEVNULL)
    expect(proc.returncode == 0, f"--list rc={proc.returncode}: {proc.stdout}{proc.stderr}")
    runner = load_runner()
    for step in runner.TABLE:
        expect(step.name in proc.stdout, f"--list does not name {step.name}")
    for label in ("cheap", "heavy A", "heavy B", "solo"):
        expect(label in proc.stdout, f"--list has no {label!r} step")
    expect({s.phase for s in runner.TABLE} == {"cheap", "heavy", "solo"},
           f"phases are {sorted({s.phase for s in runner.TABLE})}")
    expect({s.group for s in runner.TABLE if s.phase == "heavy"} == {"A", "B"},
           "heavy groups are not exactly A and B")


# ---- Acceptance 2 ---------------------------------------------------------

def case_one_heavy_run_call_for_both_groups(tmp: str) -> None:
    hr = fake_heavy_run(tmp)
    steps = [trace_step(tmp, "c1", "cheap"), trace_step(tmp, "c2", "cheap"),
             trace_step(tmp, "a1", "heavy", "A"), trace_step(tmp, "a2", "heavy", "A"),
             trace_step(tmp, "b1", "heavy", "B"), trace_step(tmp, "s1", "solo")]
    rc, out, status = run_gate(tmp, steps, heavy=hr)
    expect(rc == 0, f"rc={rc}\n{out}")
    with open(os.path.join(tmp, "heavy-calls.txt"), encoding="utf-8") as fh:
        calls = fh.read().splitlines()
    expect(len(calls) == 1, f"{len(calls)} heavy-run calls: {calls}")
    trace = read_trace(tmp)
    for name in ("c1", "c2"):
        expect(trace[name]["fake"] == "unset", f"cheap step {name} ran under heavy-run")
    for name in ("a1", "a2", "b1", "s1"):
        expect(trace[name]["fake"] == "1", f"heavy/solo step {name} ran outside heavy-run")
    expect(f"heavy_run: {hr}" in out, f"stdout does not name the heavy-run path\n{out}")
    expect(status["heavy_run"]["mode"] == "present" and status["heavy_run"]["path"] == hr,
           f"status heavy_run = {status['heavy_run']}")


# ---- Acceptance 3 ---------------------------------------------------------

def case_groups_parallel_then_solo(tmp: str) -> None:
    hr = fake_heavy_run(tmp)
    d = tmp

    def wait_for(mine: str, other: str) -> str:
        return (f'touch "{d}/{mine}.flag"; i=0; while [ ! -e "{d}/{other}.flag" ]; do '
                f'i=$((i+1)); [ $i -gt 200 ] && exit 1; sleep 0.1; done; touch "{d}/{mine}.done"')

    steps = [sh_step("a1", "heavy", wait_for("a", "b"), "A"),
             sh_step("b1", "heavy", wait_for("b", "a"), "B"),
             sh_step("s1", "solo", f'[ -e "{d}/a.done" ] && [ -e "{d}/b.done" ]')]
    rc, out, status = run_gate(tmp, steps, heavy=hr)
    states = {n: s["state"] for n, s in by_name(status).items()}
    expect(states == {"a1": "PASS", "b1": "PASS", "s1": "PASS"}, f"states {states}\n{out}")
    expect(rc == 0, f"rc={rc}")


# ---- Acceptance 4 ---------------------------------------------------------

def case_heavy_run_absent_is_stated(tmp: str) -> None:
    steps = [trace_step(tmp, "c1", "cheap"), trace_step(tmp, "a1", "heavy", "A"),
             trace_step(tmp, "s1", "solo")]
    rc, out, status = run_gate(tmp, steps, heavy="none")
    expect(rc == 0, f"rc={rc}\n{out}")
    expect("heavy_run: absent (uncapped)" in out, f"stdout does not say absent\n{out}")
    expect(status["heavy_run"]["mode"] == "absent", f"status heavy_run = {status['heavy_run']}")
    trace = read_trace(tmp)
    expect(trace["a1"]["fake"] == "unset" and trace["s1"]["fake"] == "unset",
           "heavy steps did not run directly")


def case_heavy_run_bad_path_refuses(tmp: str) -> None:
    steps = [trace_step(tmp, "c1", "cheap"), trace_step(tmp, "a1", "heavy", "A")]
    rc, out, _ = run_gate(tmp, steps, heavy=os.path.join(tmp, "no-such-heavy-run"))
    expect(rc == 2, f"rc={rc}, expected 2\n{out}")
    expect("not executable" in out, f"refusal does not say why\n{out}")
    expect(read_trace(tmp) == {}, "steps ran despite the refusal")


# ---- Acceptance 5 ---------------------------------------------------------

def case_states_from_rc(tmp: str) -> None:
    runner = load_runner()
    expect(runner.classify(0, timed_out=False, started=True)[0] == "PASS", "rc 0 is not PASS")
    expect(runner.classify(1, timed_out=False, started=True)[0] == "FAIL", "rc 1 is not FAIL")
    expect(runner.classify(77, timed_out=False, started=True)[0] == "SKIP", "rc 77 is not SKIP")
    steps = [sh_step("ok", "cheap", "exit 0"), sh_step("bad", "cheap", "exit 1"),
             sh_step("skip", "cheap", "exit 77")]
    rc, out, status = run_gate(tmp, steps)
    states = {n: s["state"] for n, s in by_name(status).items()}
    expect(states == {"ok": "PASS", "bad": "FAIL", "skip": "SKIP"}, f"states {states}")
    expect(rc == 1, f"rc={rc}\n{out}")


def case_timeout_is_could_not_tell(tmp: str) -> None:
    runner = load_runner()
    expect(runner.classify(0, timed_out=True, started=True)[0] == "COULD-NOT-TELL",
           "a timed-out step that exited 0 is not COULD-NOT-TELL")
    rc, out, status = run_gate(tmp, [sh_step("hang", "cheap", "sleep 30", timeout=1)])
    step = by_name(status)["hang"]
    expect(step["state"] == "COULD-NOT-TELL", f"timeout state {step['state']}\n{out}")
    expect("timed out" in step["reason"], f"reason {step['reason']!r}")
    expect(rc == 3, f"rc={rc}")


def case_signal_death_is_could_not_tell(tmp: str) -> None:
    runner = load_runner()
    for rc_in in (-9, -15, 137, 143):
        expect(runner.classify(rc_in, timed_out=False, started=True)[0] == "COULD-NOT-TELL",
               f"rc {rc_in} is not COULD-NOT-TELL")
    steps = [sh_step("sigterm", "cheap", "kill -TERM $$"), sh_step("oom", "cheap", "exit 137")]
    rc, out, status = run_gate(tmp, steps)
    states = {n: s["state"] for n, s in by_name(status).items()}
    expect(states == {"sigterm": "COULD-NOT-TELL", "oom": "COULD-NOT-TELL"}, f"states {states}\n{out}")
    expect(rc == 3, f"rc={rc}")


def case_cannot_start_is_could_not_tell(tmp: str) -> None:
    runner = load_runner()
    expect(runner.classify(None, timed_out=False, started=False)[0] == "COULD-NOT-TELL",
           "a step that never started is not COULD-NOT-TELL")
    expect(runner.classify(None, timed_out=False, started=True)[0] == "COULD-NOT-TELL",
           "a step with no rc is not COULD-NOT-TELL")
    steps = [{"name": "nobin", "phase": "cheap", "argv": [os.path.join(tmp, "no-such-binary")],
              "timeout": 10},
             {"name": "nocwd", "phase": "cheap", "argv": ["sh", "-c", "exit 0"],
              "cwd": "no/such/dir", "timeout": 10}]
    rc, out, status = run_gate(tmp, steps)
    states = {n: s["state"] for n, s in by_name(status).items()}
    expect(states == {"nobin": "COULD-NOT-TELL", "nocwd": "COULD-NOT-TELL"}, f"states {states}\n{out}")
    expect(rc == 3, f"rc={rc}")


# ---- Acceptance 6 ---------------------------------------------------------

def case_timeout_kills_grandchildren(tmp: str) -> None:
    pidfile = os.path.join(tmp, "grandchild.pid")
    step = sh_step("spawner", "cheap", f'sleep 300 & echo $! > "{pidfile}"; wait', timeout=1)
    rc, out, status = run_gate(tmp, [step])
    expect(by_name(status)["spawner"]["state"] == "COULD-NOT-TELL", f"state\n{out}")
    expect(rc == 3, f"rc={rc}")
    with open(pidfile, encoding="utf-8") as fh:
        pid = int(fh.read().strip())
    deadline = time.monotonic() + 5
    alive = True
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            alive = False
            break
        time.sleep(0.1)
    if alive:
        try:
            os.kill(pid, 9)
        except OSError:
            pass
    expect(not alive, f"grandchild {pid} survived the step's timeout")


# ---- Acceptance 7 ---------------------------------------------------------

def case_heavy_call_killed_marks_unfinished(tmp: str) -> None:
    # (a) heavy-run dies before running anything: every heavy/solo step is
    # COULD-NOT-TELL, the cheap step keeps its PASS.
    t1 = os.path.join(tmp, "before")
    os.makedirs(t1)
    hr = fake_heavy_run(t1, "exit 137\n")
    steps = [trace_step(t1, "c1", "cheap"), trace_step(t1, "a1", "heavy", "A"),
             trace_step(t1, "b1", "heavy", "B"), trace_step(t1, "s1", "solo")]
    rc, out, status = run_gate(t1, steps, heavy=hr)
    st = by_name(status)
    expect(st["c1"]["state"] == "PASS", f"cheap step lost its PASS\n{out}")
    for name in ("a1", "b1", "s1"):
        expect(st[name]["state"] == "COULD-NOT-TELL", f"{name} is {st[name]['state']}\n{out}")
        expect("rc=137" in st[name]["reason"], f"{name} reason {st[name]['reason']!r}")
    expect(status["heavy_run"]["rc"] == 137, f"heavy_run {status['heavy_run']}")
    expect(rc == 3, f"rc={rc}")

    # (b) heavy-run dies mid-run: a1 finished and keeps PASS; b1 was running
    # and s1 never started, both COULD-NOT-TELL.
    t2 = os.path.join(tmp, "during")
    os.makedirs(t2)
    marker = os.path.join(t2, "b1.started")
    pidf = os.path.join(t2, "b1.pid")
    body = (
        'part=""; prev=""\n'
        'for a in "$@"; do [ "$prev" = "--inner" ] && part="$a"; prev="$a"; done\n'
        'FAKE_HEAVY_RUN=1 "$@" & p=$!\n'
        'i=0\n'
        f'until [ -e "{marker}" ] && grep -q \'"a1"\' "$part" 2>/dev/null; do\n'
        '  i=$((i+1)); [ $i -gt 300 ] && break; sleep 0.1\n'
        'done\n'
        'kill -9 $p; exit 137\n'
    )
    hr = fake_heavy_run(t2, body)
    steps = [sh_step("a1", "heavy", "exit 0", "A"),
             sh_step("b1", "heavy", f'echo $$ > "{pidf}"; touch "{marker}"; exec sleep 30', "B"),
             sh_step("s1", "solo", "exit 0")]
    try:
        rc, out, status = run_gate(t2, steps, heavy=hr)
    finally:
        if os.path.exists(pidf):
            try:
                with open(pidf, encoding="utf-8") as fh:
                    os.kill(int(fh.read().strip()), 9)
            except (OSError, ValueError):
                pass
    st = by_name(status)
    expect(st["a1"]["state"] == "PASS", f"finished a1 is {st['a1']['state']}\n{out}")
    for name in ("b1", "s1"):
        expect(st[name]["state"] == "COULD-NOT-TELL", f"{name} is {st[name]['state']}\n{out}")
    expect(rc == 3, f"rc={rc}")


# ---- Acceptance 8 ---------------------------------------------------------

def case_inner_signal_is_not_heavy_rc_zero(tmp: str) -> None:
    # Measured 2026-09-30 (step 6): the heavy-run scope hit its 6G cap, systemd
    # stopped the scope with SIGTERM, and status.json still said heavy_run rc=0
    # because the inner runner returned 0 after its signal handler. The step
    # states were right; the heavy-run rc must not read as a clean call.
    steps = [sh_step("a1", "heavy", "kill -TERM $PPID; sleep 5", "A"),
             sh_step("s1", "solo", "exit 0")]
    rc, out, status = run_gate(tmp, steps)
    st = by_name(status)
    expect(st["a1"]["state"] == "COULD-NOT-TELL", f"a1 is {st['a1']['state']}\n{out}")
    expect(st["s1"]["state"] == "COULD-NOT-TELL", f"s1 is {st['s1']['state']}\n{out}")
    expect(status["heavy_run"]["rc"] == 128 + signal.SIGTERM,
           f"heavy_run {status['heavy_run']} after the inner runner took SIGTERM")
    expect(rc == 3, f"rc={rc}")


def case_table_pins_n4(tmp: str) -> None:
    runner = load_runner()
    pytest_steps = [s for s in runner.TABLE if s.pytest]
    expect(len(pytest_steps) >= 4, f"only {len(pytest_steps)} pytest steps")
    for step in runner.TABLE:
        if "pytest" in step.argv:
            expect(step.pytest, f"{step.name} runs pytest but is not flagged pytest")
    for step in pytest_steps:
        pairs = list(zip(step.argv, step.argv[1:]))
        if step.name == "wallclock":
            expect("-n" not in step.argv, "wallclock carries -n; it must run serially")
        else:
            expect(("-n", "4") in pairs, f"{step.name} has no literal -n 4: {step.argv}")
            expect("auto" not in step.argv, f"{step.name} uses -n auto")
    expect(any(s.name == "wallclock" for s in pytest_steps), "no wallclock step")


def case_missing_xdist_is_could_not_tell(tmp: str) -> None:
    shadow = os.path.join(tmp, "shadow")
    write(os.path.join(shadow, "xdist.py"), "raise ImportError('fixture: no xdist')\n")
    ran = os.path.join(tmp, "ran.txt")
    step = {"name": "px", "phase": "heavy", "group": "A", "pytest": True, "timeout": 30,
            "argv": ["{python}", "-c", f"open({ran!r}, 'a').write('ran')", "-n", "4"]}
    rc, out, status = run_gate(tmp, [step], env_extra={"PYTHONPATH": shadow})
    st = by_name(status)["px"]
    expect(st["state"] == "COULD-NOT-TELL", f"state {st['state']}\n{out}")
    expect("pytest-xdist not importable" in st["reason"], f"reason {st['reason']!r}")
    expect(not os.path.exists(ran), "the pytest step ran without xdist (serial fallback)")
    expect(rc == 3, f"rc={rc}")


# ---- Acceptance 9 ---------------------------------------------------------

def _need_yaml() -> None:
    try:
        import yaml  # noqa: F401  pylint: disable=unused-import
    except ImportError as exc:
        raise Skip("pyyaml not importable") from exc


def case_ci_drift_table_covers_workflows(tmp: str) -> None:
    _need_yaml()
    runner = load_runner()
    problems = runner.ci_drift(REPO)
    expect(problems == [], "drift on the real repo:\n  " + "\n  ".join(problems))


def case_ci_drift_goes_red_on_unknown_step(tmp: str) -> None:
    _need_yaml()
    import yaml
    runner = load_runner()
    root = os.path.join(tmp, "repo")
    shutil.copytree(os.path.join(REPO, ".github", "workflows"),
                    os.path.join(root, ".github", "workflows"))
    expect(runner.ci_drift(root) == [], "the copied workflows already drift")
    wf = os.path.join(root, ".github", "workflows", "shell-suites.yml")
    with open(wf, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    job = next(iter(doc["jobs"].values()))
    job["steps"].append({"name": "new", "run": "python3 scripts/new-check.py"})
    write(wf, yaml.safe_dump(doc))
    problems = runner.ci_drift(root)
    expect(any("python3 scripts/new-check.py" in p for p in problems),
           f"an unknown CI step was not reported: {problems}")
    write(os.path.join(root, ".github", "workflows", "brand-new.yml"), "jobs: {}\n")
    problems = runner.ci_drift(root)
    expect(any("brand-new.yml" in p for p in problems),
           f"an unclassified workflow was not reported: {problems}")


# ---- Acceptance 10 --------------------------------------------------------

def case_overall_and_exit_codes(tmp: str) -> None:
    runner = load_runner()

    def ov(*states):
        return runner.overall([{"state": s} for s in states])

    expect(ov("PASS", "PASS") == ("PASS", 0), "all PASS")
    expect(ov("PASS", "SKIP") == ("PASS", 0), "PASS with a SKIP")
    expect(ov("PASS", "FAIL", "COULD-NOT-TELL") == ("FAIL", 1), "FAIL wins")
    expect(ov("PASS", "COULD-NOT-TELL") == ("COULD-NOT-TELL", 3), "COULD-NOT-TELL is not PASS")
    expect(ov() == ("COULD-NOT-TELL", 3), "an empty run is not PASS")
    steps = [sh_step("ok", "cheap", "exit 0"), sh_step("bad", "cheap", "exit 1"),
             sh_step("hang", "cheap", "sleep 30", timeout=1)]
    rc, out, status = run_gate(tmp, steps)
    expect(rc == 1 and status["overall"] == "FAIL", f"rc={rc} overall={status['overall']}\n{out}")


def case_all_skip_is_not_pass(tmp: str) -> None:
    rc, out, status = run_gate(tmp, [sh_step("s1", "cheap", "exit 77"),
                                     sh_step("s2", "cheap", "exit 77")])
    expect(rc == 3, f"rc={rc}\n{out}")
    expect(status["overall"] == "COULD-NOT-TELL", f"overall {status['overall']}")
    last = out.strip().splitlines()[-1]
    expect("2 SKIPPED" in last, f"last line does not count the skips: {last!r}")


# ---- Acceptance 11 --------------------------------------------------------

def case_status_file_shape_and_atomic_write(tmp: str) -> None:
    rc, out, status = run_gate(tmp, [sh_step("ok", "cheap", "echo hi"),
                                     sh_step("a1", "heavy", "exit 0", "A")])
    expect(rc == 0, f"rc={rc}\n{out}")
    for key in ("head", "dirty", "table_source", "heavy_run", "started", "ended", "overall",
                "steps"):
        expect(key in status, f"status has no {key!r}")
    for key in ("mode", "path", "rc", "waited_seconds"):
        expect(key in status["heavy_run"], f"heavy_run has no {key!r}")
    for step in status["steps"]:
        for key in ("name", "phase", "group", "argv", "cwd", "rc", "state", "reason", "seconds",
                    "log"):
            expect(key in step, f"step {step.get('name')} has no {key!r}")
        expect(os.path.exists(step["log"]), f"log {step['log']} missing")
    with open(by_name(status)["ok"]["log"], encoding="utf-8") as fh:
        expect("hi" in fh.read(), "step output not in its log")
    lines = [ln for ln in out.splitlines() if ln.startswith(("PASS ", "FAIL ", "SKIP ",
                                                               "COULD-NOT-TELL "))]
    expect(len(lines) == 2, f"expected one summary line per step, got {lines}")
    leftovers = [f for f in os.listdir(os.path.join(tmp, "out")) if f.endswith(".tmp")]
    expect(leftovers == [], f"temp files left: {leftovers}")

    runner = load_runner()
    path = os.path.join(tmp, "atomic", "status.json")
    runner.write_status(path, {"ok": 1})
    try:
        runner.write_status(path, {"bad": object()})
    except TypeError:
        pass
    with open(path, encoding="utf-8") as fh:
        expect(json.load(fh) == {"ok": 1}, "a failed write damaged the previous status file")


# ---- Acceptance 12 --------------------------------------------------------

def case_never_sets_heavy_run_caps(tmp: str) -> None:
    hr = fake_heavy_run(tmp)
    steps = [trace_step(tmp, "c1", "cheap"), trace_step(tmp, "a1", "heavy", "A"),
             trace_step(tmp, "s1", "solo")]
    rc, out, _ = run_gate(tmp, steps, heavy=hr)
    expect(rc == 0, f"rc={rc}\n{out}")
    with open(os.path.join(tmp, "heavy-calls.txt"), encoding="utf-8") as fh:
        call = fh.read()
    expect("nocap=unset" in call and "mem=unset" in call, f"heavy-run saw a cap variable: {call}")
    for name, rec in read_trace(tmp).items():
        expect(rec["nocap"] == "unset" and rec["mem"] == "unset", f"{name} saw a cap variable")


# ---- Acceptance 13 --------------------------------------------------------

def case_skip_and_table_are_recorded(tmp: str) -> None:
    steps = [trace_step(tmp, "c1", "cheap"), trace_step(tmp, "c2", "cheap")]
    rc, out, status = run_gate(tmp, steps, "--skip", "c2")
    st = by_name(status)
    expect(st["c2"]["state"] == "SKIP" and st["c2"]["reason"] == "skipped by --skip",
           f"c2 = {st['c2']}")
    expect("c2" not in read_trace(tmp), "a --skip step ran")
    expect(status["table_source"] == os.path.join(tmp, "table.json"),
           f"table_source {status['table_source']}")
    last = out.strip().splitlines()[-1]
    expect("not the repo gate" in last, f"last line does not flag the table: {last!r}")
    expect("1 SKIPPED" in last, f"last line does not count the skip: {last!r}")
    expect(rc == 0, f"rc={rc}")


# ---- review round 1 (L-0513 Fix phase) -------------------------------------

def _drift_fixture(tmp: str):
    """A copy of this repo's workflows; returns (runner, root, yaml)."""
    _need_yaml()
    import yaml
    runner = load_runner()
    root = os.path.join(tmp, "repo")
    shutil.copytree(os.path.join(REPO, ".github", "workflows"),
                    os.path.join(root, ".github", "workflows"))
    expect(runner.ci_drift(root) == [], "the copied workflows already drift")
    return runner, root, yaml


def _edit_workflow(root: str, yaml, name: str, edit) -> None:
    path = os.path.join(root, ".github", "workflows", name)
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    edit(doc)
    write(path, yaml.safe_dump(doc))


def case_ci_drift_scans_crew_shell_matrix(tmp: str) -> None:
    # BLOCK r1: the whole crew-shell-matrix job was excluded as Windows-only,
    # but its ubuntu leg runs the slow hook matrix on every PR.
    runner, root, yaml = _drift_fixture(tmp)
    slow = [s for s in runner.TABLE if any(wf == "pytest-crew.yml" and " -m slow" in cmd
                                           for wf, cmd in s.ci)]
    expect(len(slow) == 1, f"no table step covers the slow hook matrix: {[s.name for s in slow]}")
    expect(slow[0].phase == "heavy" and ("-n", "4") in list(zip(slow[0].argv, slow[0].argv[1:])),
           f"slow step is not a heavy -n 4 pytest step: {slow[0]}")
    _edit_workflow(root, yaml, "pytest-crew.yml", lambda d: d["jobs"]["crew-shell-matrix"]["steps"]
                   .append({"name": "new", "run": "python3 scripts/new-check.py"}))
    problems = runner.ci_drift(root)
    expect(any("crew-shell-matrix" in p and "new-check.py" in p for p in problems),
           f"a command added to crew-shell-matrix was not reported: {problems}")


def case_ci_drift_windows_only_step_needs_its_if(tmp: str) -> None:
    # Neighbour of the crew-shell-matrix BLOCK: a Windows-only step is excluded
    # by its `if:`, so dropping the `if:` makes its command count again. The
    # Windows default set lives in crew-windows-default since L-0577.
    runner, root, yaml = _drift_fixture(tmp)
    windows_ifs = {cond for cond, _ in runner.WINDOWS_ONLY_IFS}

    def drop_if(doc):
        for step in doc["jobs"]["crew-windows-default"]["steps"]:
            if step.get("if") in windows_ifs and "not wallclock" in step.get("run", ""):
                del step["if"]
                return
        raise AssertionError("fixture: no Windows-only step to edit")

    _edit_workflow(root, yaml, "pytest-crew.yml", drop_if)
    problems = runner.ci_drift(root)
    expect(any("crew-windows-default" in p and "not wallclock" in p for p in problems),
           f"a Windows-only command that lost its if: was not reported: {problems}")


def case_ci_drift_compound_commands(tmp: str) -> None:
    # FIX r1 (wildcard prefix) and FIX r1 (dropped `if` lines), plus their
    # neighbours: a check chained onto an excluded install, an echo, or hidden
    # in a one-line conditional or loop is still a command CI runs.
    runner = load_runner()
    hidden = [
        "pip install pytest && python3 scripts/new-check.py",
        "pip install pytest; python3 scripts/new-check.py",
        "pip install pytest || python3 scripts/new-check.py",
        "pip install $(python3 scripts/new-check.py)",
        "if true; then python3 scripts/new-check.py; fi",
        "if python3 scripts/new-check.py; then :; fi",
        "if ! python3 scripts/new-check.py; then exit 1; fi",
        "while python3 scripts/new-check.py; do :; done",
        "for f in a b; do python3 scripts/new-check.py; done",
        "echo hi && python3 scripts/new-check.py",
        "if [ -n \"$X\" ]; then\n  python3 scripts/new-check.py\nfi",
    ]
    for run in hidden:
        cmds = runner.split_commands(run)
        unknown = [c for c in cmds if not runner._excluded("pytest-crew.yml", c)]
        expect(any("new-check.py" in c for c in unknown),
               f"{run!r} hides new-check.py: commands {cmds}, unknown {unknown}")
    runner_, root, yaml = _drift_fixture(tmp)

    def chain(doc):
        for step in doc["jobs"]["test"]["steps"]:
            if isinstance(step.get("run"), str) and "pip install" in step["run"]:
                step["run"] = "pip install pytest && python3 scripts/new-check.py\n"
                return
        raise AssertionError("fixture: no install step to edit")

    _edit_workflow(root, yaml, "pytest-crew.yml", chain)
    problems = runner_.ci_drift(root)
    expect(any("new-check.py" in p for p in problems),
           f"a check chained onto an install was not reported: {problems}")


def case_table_rejects_unsafe_step_names(tmp: str) -> None:
    # BLOCK r1: a custom-table name became a log path, so `/abs` or `../x`
    # escaped --out and truncated a file outside it. Neighbour: a step named
    # heavy-run would share the outer heavy-run call's log.
    victim = os.path.join(tmp, "victim")
    write(victim + ".log", "keep me\n")
    for bad in (victim, "../escape", "a/b", "..", ".hidden", "heavy-run", "a\\b", ""):
        sub = os.path.join(tmp, f"t{abs(hash(bad))}")
        os.makedirs(sub)
        rc, out, _ = run_gate(sub, [{"name": bad, "phase": "cheap", "argv": ["true"]}])
        expect(rc == 2, f"name {bad!r}: rc={rc}, expected a refusal (2)\n{out}")
        expect("Traceback" not in out, f"name {bad!r} crashed\n{out}")
    with open(victim + ".log", encoding="utf-8") as fh:
        expect(fh.read() == "keep me\n", "a file outside --out was truncated")


def case_table_rejects_wrong_field_types(tmp: str) -> None:
    # FIX r1: valid JSON of the wrong shape crashed with a traceback. Neighbours:
    # needs as a bare string (tuple("bash") is its characters), a bool timeout
    # (bool is an int), and an unknown key (a typo silently defaulted).
    base = {"name": "x", "phase": "cheap", "argv": ["true"]}
    bad = [{"cwd": []}, {"cwd": 5}, {"cwd": ""}, {"needs": "bash"}, {"needs": [1]},
           {"pytest": "yes"}, {"timeout": True}, {"timeot": 5}]
    for i, extra in enumerate(bad):
        sub = os.path.join(tmp, f"t{i}")
        os.makedirs(sub)
        rc, out, _ = run_gate(sub, [{**base, **extra}])
        expect(rc == 2, f"{extra}: rc={rc}, expected a refusal (2)\n{out}")
        expect("Traceback" not in out, f"{extra} crashed\n{out}")


def case_skip_wins_before_argv_is_built(tmp: str) -> None:
    # FIX r1: --skip was applied after argv construction, so a skipped step
    # whose {git_py_files} expansion fails (non-git root) read COULD-NOT-TELL.
    # Neighbour: the same for a heavy step, which runs in the inner runner.
    steps = [{"name": "gp", "phase": "cheap", "argv": ["echo", "{git_py_files}"]},
             {"name": "hp", "phase": "heavy", "group": "A", "argv": ["echo", "{git_py_files}"]},
             sh_step("ok", "cheap", "exit 0")]
    rc, out, status = run_gate(tmp, steps, "--skip", "gp", "--skip", "hp")
    st = by_name(status)
    for name in ("gp", "hp"):
        expect(st[name]["state"] == "SKIP" and st[name]["reason"] == "skipped by --skip",
               f"{name} = {st[name]['state']} {st[name]['reason']!r}\n{out}")
    expect(rc == 0, f"rc={rc}\n{out}")


def case_heavy_results_reach_status_json(tmp: str) -> None:
    # FIX r1: heavy results lived only in heavy-part.json until the whole
    # heavy call ended; an outer runner killed then left status.json with
    # none of them. A finished heavy step must reach status.json while the
    # call is still running.
    root = os.path.join(tmp, "root")
    os.makedirs(root)
    out = os.path.join(tmp, "out")
    pidf = os.path.join(tmp, "b1.pid")
    steps = [sh_step("a1", "heavy", "exit 0", "A"),
             sh_step("b1", "heavy", f'echo $$ > "{pidf}"; exec sleep 30', "B")]
    table = write(os.path.join(tmp, "table.json"), json.dumps({"steps": steps}))
    env = {k: v for k, v in os.environ.items() if not k.startswith("HEAVY_RUN")}
    env["HEAVY_RUN"] = "none"
    # not `with`: the case SIGKILLs it mid-run and reaps it in `finally`
    # pylint: disable-next=consider-using-with
    proc = subprocess.Popen([sys.executable, TARGET, "--root", root, "--out", out, "--grace", "1",
                             "--table", table], stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, env=env)
    status_path = os.path.join(out, "status.json")
    seen = None
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and seen is None:
            try:
                with open(status_path, encoding="utf-8") as fh:
                    got = json.load(fh)
                seen = next((s for s in got["steps"] if s["name"] == "a1"), None)
            except (OSError, ValueError):
                pass
            time.sleep(0.2)
        expect(proc.poll() is None, "fixture: the runner ended before the check")
        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=10)
        with open(status_path, encoding="utf-8") as fh:
            final = json.load(fh)
    finally:
        if proc.poll() is None:
            proc.kill()
        part = os.path.join(out, "heavy-part.json")
        for pid_src in (pidf, part):
            try:
                with open(pid_src, encoding="utf-8") as fh:
                    text = fh.read()
                pid = json.loads(text)["pid"] if pid_src == part else int(text.strip())
                os.kill(pid, signal.SIGKILL)
            except (OSError, ValueError, KeyError):
                pass
    expect(seen is not None and seen["state"] == "PASS",
           f"a1 never reached status.json while the heavy call ran: {seen}")
    a1 = next((s for s in final["steps"] if s["name"] == "a1"), None)
    expect(a1 is not None and a1["state"] == "PASS",
           f"after SIGKILL of the outer runner status.json has a1 = {a1}")
    expect(final["overall"] == "RUNNING", f"overall {final['overall']} for an unfinished run")


def case_default_out_is_claimed_atomically(tmp: str) -> None:
    # FIX r1: default_out checked for a free name without creating it, so two
    # runs at one commit in one UTC second could share a directory.
    import threading
    from datetime import datetime, timezone
    runner = load_runner()

    class FixedClock:
        @staticmethod
        def now(tz=None):
            return datetime(2026, 9, 30, 12, 0, 0, tzinfo=tz or timezone.utc)

    saved_dt, saved_tmp = runner.datetime, tempfile.tempdir
    runner.datetime, tempfile.tempdir = FixedClock, tmp
    got, lock = [], threading.Lock()

    def claim():
        path = runner.default_out(REPO)
        with lock:
            got.append(path)

    try:
        threads = [threading.Thread(target=claim) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        runner.datetime, tempfile.tempdir = saved_dt, saved_tmp
    expect(len(set(got)) == 8, f"concurrent runs shared an output directory: {sorted(got)}")
    expect(all(os.path.isdir(p) for p in got), "default_out returned a directory it did not create")


# ---- review round 2 (L-0513 successor plan) --------------------------------

def run_raw_table(tmp: str, text: str, *args: str, grace: str = "1"):
    """Run the CLI on a table given as raw JSON text (NaN, Infinity, 1e999)."""
    root = os.path.join(tmp, "root")
    os.makedirs(root, exist_ok=True)
    table = write(os.path.join(tmp, "table.json"), text)
    argv = [sys.executable, TARGET, "--root", root, "--out", os.path.join(tmp, "out"),
            "--grace", grace, "--table", table, *args]
    env = {k: v for k, v in os.environ.items() if not k.startswith("HEAVY_RUN")}
    env["HEAVY_RUN"] = "none"
    proc = subprocess.run(argv, capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL,
                          timeout=CALL_TIMEOUT, check=False)
    return proc.returncode, proc.stdout + proc.stderr


def case_table_rejects_non_finite_timeout(tmp: str) -> None:
    # BLOCK r2: json.load accepts NaN/Infinity, so `"timeout": NaN` passed the
    # positive-number check and `now >= deadline` was never true. Neighbours:
    # --grace and --heavy-timeout (argparse type=float) took nan, inf and 0.
    for i, raw in enumerate(("NaN", "Infinity", "-Infinity", "1e999")):
        sub = os.path.join(tmp, f"t{i}")
        text = ('{"steps": [{"name": "x", "phase": "cheap", "argv": ["true"], "timeout": '
                + raw + "}]}")
        rc, out = run_raw_table(sub, text)
        expect(rc == 2, f"timeout {raw}: rc={rc}, expected a refusal (2)\n{out}")
        expect("timeout" in out and "Traceback" not in out, f"timeout {raw}: refusal\n{out}")
    ok = '{"steps": [{"name": "x", "phase": "cheap", "argv": ["true"]}]}'
    for i, (flag, value) in enumerate((("--grace", "nan"), ("--grace", "inf"),
                                       ("--heavy-timeout", "nan"), ("--heavy-timeout", "0"),
                                       ("--heavy-timeout", "inf"))):
        sub = os.path.join(tmp, f"f{i}")
        if flag == "--grace":
            rc, out = run_raw_table(sub, ok, grace=value)
        else:
            rc, out = run_raw_table(sub, ok, flag, value)
        expect(rc == 2, f"{flag} {value}: rc={rc}, expected a refusal (2)\n{out}")
        expect("Traceback" not in out, f"{flag} {value} crashed\n{out}")


def case_ci_drift_substitution_in_dropped_line(tmp: str) -> None:
    # FIX r2: echo, conditions, exit, assignments and `for` headers were
    # dropped whole, so a check inside $(...) or backticks there was invisible.
    runner, root, yaml = _drift_fixture(tmp)
    hidden = {
        "new-check1.py": 'echo "$(python3 scripts/new-check1.py)"',
        "new-check2.py": 'echo "`python3 scripts/new-check2.py`"',
        "new-check3.py": '[ -n "$(python3 scripts/new-check3.py)" ]',
        "new-check4.py": 'test -z "$(python3 scripts/new-check4.py)"',
        "new-check5.py": "X=$(python3 scripts/new-check5.py)",
        "new-check6.py": "exit $(python3 scripts/new-check6.py)",
        "new-check7.py": "for f in $(python3 scripts/new-check7.py); do :; done",
        "new-check8.py": "if [ \"$(python3 scripts/new-check8.py)\" = ok ]; then :; fi",
        "new-check9.py": "echo $(echo $(python3 scripts/new-check9.py))",
    }

    def add(doc):
        job = doc["jobs"][next(iter(doc["jobs"]))]
        for i, run in enumerate(hidden.values()):
            job["steps"].append({"name": f"new{i}", "run": run})
        job["steps"].append({"name": "plain", "run": "echo done\nX=1\ni=$((i+1))\n"})

    _edit_workflow(root, yaml, "shell-suites.yml", add)
    problems = runner.ci_drift(root)
    for script, run in hidden.items():
        expect(any(script in p for p in problems),
               f"{run!r} hides {script}: problems {problems}")
    expect(len(problems) == len(hidden),
           f"plain echo/assignment/arithmetic lines added drift: {problems}")


class _StuckProc:
    """A Popen stand-in that never exits: wait(timeout) sleeps then raises
    TimeoutExpired, wait() with no timeout blocks for good."""

    def __init__(self, pid: int):
        self.pid, self.returncode = pid, None
        self._never = __import__("threading").Event()

    def wait(self, timeout=None):
        if timeout is None:
            self._never.wait()
            return None
        time.sleep(min(timeout, 0.5))
        raise subprocess.TimeoutExpired("stuck", timeout)

    def poll(self):
        return None

    def kill(self):
        return None


class _FakeSubprocess:
    """The runner's `subprocess` with Popen replaced; everything else real."""

    def __init__(self, proc):
        self._proc = proc

    def Popen(self, *_a, **_k):  # noqa: N802  pylint: disable=invalid-name
        return self._proc

    def __getattr__(self, name):
        return getattr(subprocess, name)


def _in_thread(fn, limit: float):
    """Run fn in a daemon thread; (finished, result-or-exception)."""
    import threading
    box = {}

    def target():
        try:
            box["value"] = fn()
        except BaseException as exc:  # pylint: disable=broad-exception-caught
            box["value"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(limit)
    return not thread.is_alive(), box.get("value")


def case_kill_wait_is_bounded(tmp: str) -> None:
    # FIX r2: after SIGKILL, _kill_group waited with no bound, so a child that
    # never got reaped (uninterruptible I/O) hung the runner instead of giving
    # COULD-NOT-TELL. Neighbour: the signal-STOP path's SIGKILL is bounded too.
    reaped = subprocess.Popen(["sleep", "0"])  # pylint: disable=consider-using-with
    reaped.wait()
    runner = load_runner()
    sent = []
    runner._signal_group = lambda proc, hard: sent.append(hard)
    runner.KILL_REAP_SECONDS = 1
    finished, got = _in_thread(lambda: runner._kill_group(_StuckProc(reaped.pid), 0.2), 10)
    expect(finished, "_kill_group still waiting 10 s after SIGKILL (unbounded wait)")
    expect(got is False, f"_kill_group on an unreaped process returned {got!r}, not False")
    expect(True in sent, f"no SIGKILL sent: {sent}")

    runner.subprocess = _FakeSubprocess(_StuckProc(reaped.pid))
    log = os.path.join(tmp, "logs", "stuck.log")
    finished, got = _in_thread(lambda: runner.spawn_and_wait(["stuck"], tmp, log, 0.3, 0.2), 10)
    expect(finished, "spawn_and_wait hung on a process that never exits after SIGKILL")
    expect(not isinstance(got, BaseException), f"spawn_and_wait raised {got!r}")
    rc, timed_out, started, note = got
    expect(rc is None and timed_out and started, f"returned {got!r}")
    expect("SIGKILL" in note, f"note does not name SIGKILL: {note!r}")
    state, _reason = runner.classify(rc, timed_out, started)
    expect(state == "COULD-NOT-TELL", f"classify gave {state}")

    runner.STOP.set()
    try:
        started_at = time.monotonic()
        finished, got = _in_thread(
            lambda: runner.spawn_and_wait(["stuck"], tmp, log, 60, 0.2), 10)
        took = time.monotonic() - started_at
    finally:
        runner.STOP.clear()
    expect(finished, "the STOP path spun past its SIGKILL bound (still running after 10 s)")
    expect(not isinstance(got, BaseException), f"STOP path raised {got!r}")
    expect(got[0] is None and runner.classify(*got[:3])[0] == "COULD-NOT-TELL",
           f"STOP path returned {got!r}")
    expect(took < 0.2 + 1 + 3, f"STOP path took {took:.1f}s")


def case_heavy_part_wrong_shape_is_could_not_tell(tmp: str) -> None:
    # FIX r2: a valid heavy-part.json of the wrong shape crashed the outer
    # runner's tick (AttributeError on .get) and orphaned the heavy process.
    shapes = ["[]", "[1]", '"x"', '{"steps": []}', '{"steps": {"a1": 1}}', '{"steps": null}',
              '{"steps": "abc"}', '{"steps": {"a1": {}}}', '{"steps": {"a1": {"state": "PASS"}}}']
    for i, shape in enumerate(shapes):
        sub = os.path.join(tmp, f"s{i}")
        os.makedirs(sub)
        pidf = os.path.join(sub, "hr.pid")
        payload = write(os.path.join(sub, "payload.json"), shape)
        body = ('part=""; prev=""\n'
                'for a in "$@"; do [ "$prev" = "--inner" ] && part="$a"; prev="$a"; done\n'
                f'cp "{payload}" "$part"\n'
                f'echo $$ > "{pidf}"\n'
                'exec sleep 300\n')
        hr = fake_heavy_run(sub, body)
        steps = [sh_step("a1", "heavy", "exit 0", "A"), sh_step("s1", "solo", "exit 0")]
        try:
            rc, out, status = run_gate(sub, steps, "--heavy-timeout", "3", heavy=hr, grace="0.5")
            exited = time.monotonic()
            expect("Traceback" not in out, f"part {shape}: the outer runner crashed\n{out}")
            expect(rc == 3, f"part {shape}: rc={rc}, expected 3\n{out}")
            st = by_name(status)
            for name in ("a1", "s1"):
                expect(st[name]["state"] == "COULD-NOT-TELL",
                       f"part {shape}: {name} is {st[name]['state']}\n{out}")
            with open(pidf, encoding="utf-8") as fh:
                pid = int(fh.read().strip())
            alive = True
            while time.monotonic() < exited + 5:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    alive = False
                    break
                time.sleep(0.1)
            expect(not alive, f"part {shape}: heavy-run process {pid} outlived the runner")
        finally:
            try:
                with open(pidf, encoding="utf-8") as fh:
                    os.kill(int(fh.read().strip()), signal.SIGKILL)
            except (OSError, ValueError):
                pass
    # Neighbour: `started` must be a finite non-bool number, or waited_seconds
    # stays absent rather than 1-launch or NaN.
    for i, shape in enumerate(('{"started": true, "steps": {}}', '{"started": NaN, "steps": {}}')):
        sub = os.path.join(tmp, f"w{i}")
        os.makedirs(sub)
        payload = write(os.path.join(sub, "payload.json"), shape)
        body = ('part=""; prev=""\n'
                'for a in "$@"; do [ "$prev" = "--inner" ] && part="$a"; prev="$a"; done\n'
                f'cp "{payload}" "$part"\n'
                'exit 0\n')
        hr = fake_heavy_run(sub, body)
        rc, out, status = run_gate(sub, [sh_step("a1", "heavy", "exit 0", "A")], heavy=hr)
        expect(rc == 3, f"started {shape}: rc={rc}\n{out}")
        waited = status["heavy_run"].get("waited_seconds")
        expect(waited is None, f"started {shape}: waited_seconds={waited!r}, expected absent")


def case_table_cwd_stays_in_root(tmp: str) -> None:
    # FIX r2: a custom step's cwd was only type-checked, so `..` or an absolute
    # path ran it outside --root.
    for i, cwd in enumerate(("..", "/", "sub/../../x", tmp)):
        sub = os.path.join(tmp, f"t{i}")
        os.makedirs(sub)
        rc, out, _ = run_gate(sub, [{"name": "x", "phase": "cheap", "argv": ["true"], "cwd": cwd}])
        expect(rc == 2, f"cwd {cwd!r}: rc={rc}, expected a refusal (2)\n{out}")
        expect("cwd" in out and "Traceback" not in out, f"cwd {cwd!r}: refusal\n{out}")
    if os.name != "nt":
        sub = os.path.join(tmp, "link")
        os.makedirs(os.path.join(sub, "root"))
        os.makedirs(os.path.join(sub, "outside"))
        os.symlink(os.path.join(sub, "outside"), os.path.join(sub, "root", "link"))
        rc, out, _ = run_gate(sub, [{"name": "x", "phase": "cheap", "argv": ["true"],
                                     "cwd": "link"}])
        expect(rc == 2, f"cwd through an escaping symlink: rc={rc}, expected 2\n{out}")
    else:
        print("  (symlink neighbour not run on Windows)")
    for i, cwd in enumerate(("sub/..", "sub", "sub/deeper")):
        sub = os.path.join(tmp, f"ok{i}")
        os.makedirs(os.path.join(sub, "root", "sub", "deeper"))
        rc, out, _ = run_gate(sub, [{"name": "x", "phase": "cheap", "argv": ["true"], "cwd": cwd}])
        expect(rc == 0, f"in-root cwd {cwd!r}: rc={rc}, expected 0\n{out}")
    runner = load_runner()
    for step in runner.TABLE:
        expect(runner.cwd_in_root(REPO, step.cwd), f"built-in {step.name} cwd {step.cwd!r}")


def case_non_utf8_tracked_name_does_not_crash(tmp: str) -> None:
    # FIX r2: a tracked .py name holding byte 0xff crashed argv construction
    # (proc.stdout.decode()). Neighbour: a workflow file that is not UTF-8 is a
    # drift problem naming it, never an exception.
    if os.name == "nt":
        raise Skip("bytes file names are POSIX only")
    root = os.path.join(tmp, "root")
    os.makedirs(root)
    name = b"bad\xff.py"
    with open(os.path.join(os.fsencode(root), name), "wb") as fh:
        fh.write(b"x = 1\n")
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
    for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "fixture"]):
        subprocess.run(git + cmd, cwd=root, check=True, capture_output=True,
                       stdin=subprocess.DEVNULL, timeout=60)
    check = ("import os, sys; a = sys.argv[1:]; "
             "sys.exit(0 if len(a) == 1 and os.fsencode(a[0]) == b'bad\\xff.py' "
             "and os.path.exists(os.fsencode(a[0])) else 1)")
    rc, out, status = run_gate(tmp, [{"name": "gp", "phase": "cheap",
                                      "argv": [sys.executable, "-c", check, "{git_py_files}"]}])
    expect("Traceback" not in out, f"a non-UTF-8 tracked name crashed the runner\n{out}")
    expect(status is not None and by_name(status)["gp"]["state"] == "PASS",
           f"the child did not get the original bytes name\n{out}")
    expect(rc == 0, f"rc={rc}\n{out}")

    runner, droot, _yaml = _drift_fixture(os.path.join(tmp, "drift"))
    with open(os.path.join(droot, ".github", "workflows", "pytest-crew.yml"), "ab") as fh:
        fh.write(b"# \xff\n")
    try:
        problems = runner.ci_drift(droot)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        raise AssertionError(f"ci_drift raised on a non-UTF-8 workflow: {exc!r}") from exc
    expect(any("pytest-crew.yml" in p for p in problems),
           f"a non-UTF-8 workflow was not reported: {problems}")


# ---- review round 3 (L-0513 Fix phase) ------------------------------------

def case_heavy_part_forged_pass_is_could_not_tell(tmp: str) -> None:
    # BLOCK r3: a heavy-part result with the required keys and state PASS was
    # taken as PASS though rc was null, so a heavy-run that wrote such a file
    # and exited 0 gave an overall PASS for a step that never ran. Neighbours:
    # rc of the wrong type or contradicting the state, a result filed under
    # another step's name, and a result for a step that is not in the table.
    def result(**kw):
        return {**part_row("a1", "PASS", 0), **kw}

    forged = {
        "rc null": {"a1": result(rc=None)},
        "rc string": {"a1": result(rc="0")},
        "rc bool": {"a1": result(rc=False)},
        "rc 1 with PASS": {"a1": result(rc=1)},
        "rc 0 with FAIL": {"a1": result(state="FAIL")},
        "name mismatch": {"a1": result(name="b1")},
        "unknown step": {"zz": result(name="zz")},
    }
    cases = list(forged.items()) + [("control", {"a1": result()})]
    # The fake holds the call open past the outer runner's 0.5 s tick, so the
    # live copy into status.json (tick) reads the part as well as the final merge.
    for i, (label, steps_doc) in enumerate(cases):
        sub = os.path.join(tmp, f"p{i}")
        os.makedirs(sub)
        payload = write(os.path.join(sub, "payload.json"),
                        json.dumps({"started": time.time(), "pid": 1, "steps": steps_doc}))
        body = ('part=""; prev=""\n'
                'for a in "$@"; do [ "$prev" = "--inner" ] && part="$a"; prev="$a"; done\n'
                f'cp "{payload}" "$part"\n'
                'sleep 1.2; exit 0\n')
        hr = fake_heavy_run(sub, body)
        rc, out, status = run_gate(sub, [sh_step("a1", "heavy", "exit 0", "A")], heavy=hr)
        st = by_name(status)
        expect("a1" in st, f"{label}: status.json has no a1 (a result under another name "
                           f"replaced it): {sorted(st)}\n{out}")
        if label == "control":
            expect(rc == 0 and st["a1"]["state"] == "PASS",
                   f"control: a well-formed PASS was not taken: rc={rc} {st['a1']}\n{out}")
            continue
        expect(st["a1"]["state"] == "COULD-NOT-TELL",
               f"{label}: a1 is {st['a1']['state']} from a forged result\n{out}")
        expect(rc == 3, f"{label}: rc={rc}, expected 3\n{out}")
        expect("zz" not in st, f"{label}: a step outside the table reached status.json: {st}")


def case_ci_drift_process_substitution_in_excluded_install(tmp: str) -> None:
    # FIX r3: a wildcard EXCLUDED_CI entry refused only `$(` and backticks in
    # its tail, so `pip install <(python3 x.py)` hid x.py. Neighbour: `>(...)`.
    runner = load_runner()
    for run in ("pip install <(python3 scripts/new-check.py)",
                "pip install >(python3 scripts/new-check.py)",
                'python -m pip install -r <(python3 scripts/new-check.py)'):
        cmds = runner.split_commands(run)
        unknown = [c for c in cmds if not runner._excluded("pytest-crew.yml", c)]
        expect(any("new-check.py" in c for c in unknown),
               f"{run!r} hides new-check.py: commands {cmds}, unknown {unknown}")
    expect(runner._excluded("pytest-crew.yml", "pip install pytest pytest-xdist"),
           "a plain install is no longer excluded")
    runner_, root, yaml = _drift_fixture(tmp)

    def add(doc):
        doc["jobs"]["test"]["steps"].append(
            {"name": "new", "run": "pip install <(python3 scripts/new-check.py)\n"})

    _edit_workflow(root, yaml, "pytest-crew.yml", add)
    problems = runner_.ci_drift(root)
    expect(any("new-check.py" in p for p in problems),
           f"a process substitution in an install line was not reported: {problems}")


def case_table_rejects_group_on_non_heavy_step(tmp: str) -> None:
    # FIX r3: only heavy steps had their group checked, so a cheap or solo step
    # took any group value. Neighbour: solo, and a falsy non-null group.
    bad = []
    for phase in ("cheap", "solo"):
        for group in ([], "", 0, False, {}, "A", "C"):
            bad.append({"name": "x", "phase": phase, "group": group, "argv": ["true"]})
    for i, step in enumerate(bad):
        sub = os.path.join(tmp, f"t{i}")
        os.makedirs(sub)
        rc, out, _ = run_gate(sub, [step])
        expect(rc == 2, f"{step['phase']} group {step['group']!r}: rc={rc}, expected 2\n{out}")
        expect("Traceback" not in out, f"{step} crashed\n{out}")
    for i, step in enumerate(({"name": "x", "phase": "cheap", "argv": ["true"]},
                              {"name": "x", "phase": "cheap", "group": None, "argv": ["true"]})):
        sub = os.path.join(tmp, f"ok{i}")
        os.makedirs(sub)
        rc, out, _ = run_gate(sub, [step])
        expect(rc == 0, f"cheap step with no group: rc={rc}\n{out}")


def case_ci_drift_wrong_yaml_shape_is_a_problem(tmp: str) -> None:
    # FIX r3: valid YAML of the wrong shape (a list at the top, a scalar jobs)
    # crashed ci_drift. Neighbours: every level below -- a job, its steps, a
    # step and its run -- and a document with no jobs at all, which read as
    # "nothing to check".
    shapes = ["[1]\n", "x\n", "", "on: push\n", "jobs: 5\n", "jobs: [1]\n", "jobs:\n  a: 5\n",
              "jobs:\n  a:\n    steps: 5\n", "jobs:\n  a:\n    steps: {x: 1}\n",
              "jobs:\n  a:\n    steps: [5]\n", "jobs:\n  a:\n    steps:\n      - run: 5\n"]
    for i, text in enumerate(shapes):
        runner, root, _yaml = _drift_fixture(os.path.join(tmp, f"s{i}"))
        write(os.path.join(root, ".github", "workflows", "pytest-crew.yml"), text)
        try:
            problems = runner.ci_drift(root)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            raise AssertionError(f"ci_drift raised on {text!r}: {exc!r}") from exc
        expect(any("pytest-crew.yml" in p for p in problems),
               f"workflow {text!r} was not reported: {problems}")


def case_timeout_grace_covers_grandchildren(tmp: str) -> None:
    # FIX r3: the grace period ended when the group LEADER exited, so a
    # grandchild still cleaning up after SIGTERM was SIGKILLed at once.
    # Neighbour: once the whole group is gone the runner does not sit out
    # the rest of the grace period.
    cleaned = os.path.join(tmp, "cleaned")
    pidfile = os.path.join(tmp, "grandchild.pid")
    inner = f'trap "sleep 1; touch \\"{cleaned}\\"; exit 0" TERM; while :; do sleep 0.1; done'
    step = sh_step("spawner", "cheap", f"sh -c '{inner}' & echo $! > \"{pidfile}\"; wait",
                   timeout=1)
    try:
        rc, out, status = run_gate(tmp, [step], grace="8")
    finally:
        try:
            with open(pidfile, encoding="utf-8") as fh:
                os.kill(int(fh.read().strip()), signal.SIGKILL)
        except (OSError, ValueError):
            pass
    res = by_name(status)["spawner"]
    expect(res["state"] == "COULD-NOT-TELL" and rc == 3, f"rc={rc} {res}\n{out}")
    expect(os.path.exists(cleaned),
           f"the grandchild was killed inside its grace period (no cleanup)\n{out}")
    expect(res["seconds"] < 6, f"the runner sat out the grace after the group was gone: {res}")


def case_cwd_rechecked_at_launch(tmp: str) -> None:
    # FIX r3: cwd containment was checked only when the table loaded, so a step
    # that swapped an in-root directory for a symlink sent the next step
    # outside --root. Neighbour: the same inside a heavy group (inner runner).
    for label, phase, group in (("cheap", "cheap", None), ("heavy", "heavy", "A")):
        sub = os.path.join(tmp, label)
        root = os.path.join(sub, "root")
        outside = os.path.join(sub, "outside")
        os.makedirs(os.path.join(root, "sub"))
        os.makedirs(outside)
        steps = [sh_step("swap", phase, f'rm -rf sub && ln -s "{outside}" sub', group),
                 sh_step("use", phase, "touch ran-here", group, cwd="sub")]
        rc, out, status = run_gate(sub, steps)
        st = by_name(status)
        expect(st["swap"]["state"] == "PASS", f"{label}: fixture swap failed: {st['swap']}\n{out}")
        expect(not os.path.exists(os.path.join(outside, "ran-here")),
               f"{label}: the step ran outside --root through the swapped symlink\n{out}")
        expect(st["use"]["state"] == "COULD-NOT-TELL", f"{label}: use is {st['use']}\n{out}")
        expect(rc == 3, f"{label}: rc={rc}\n{out}")


# ---- review round 4 (L-0513 successor plan) --------------------------------

def _inner_part_heavy_run(sub: str, steps_doc: dict) -> str:
    """A fake heavy-run that writes `steps_doc` as the inner part and exits 0."""
    payload = write(os.path.join(sub, "payload.json"),
                    json.dumps({"started": time.time(), "pid": 1, "steps": steps_doc}))
    body = ('part=""; prev=""\n'
            'for a in "$@"; do [ "$prev" = "--inner" ] && part="$a"; prev="$a"; done\n'
            f'cp "{payload}" "$part"\n'
            'exit 0\n')
    return fake_heavy_run(sub, body)


def case_heavy_part_state_contradicts_rc(tmp: str) -> None:
    # BLOCK r4: a heavy-part SKIP was taken with any rc, so a step that exited 1
    # and was filed as SKIP read SKIP and the run could exit 0. Neighbours: the
    # SKIP and COULD-NOT-TELL results classify() and run_step() really give are
    # still taken as they are (their payload reason survives).
    def result(name, state, rc, reason):
        return part_row(name, state, rc, reason, group="A" if name == "a1" else "B")

    refuse = [("SKIP", 1), ("SKIP", 0), ("SKIP", 137), ("SKIP", -9), ("SKIP", 2)]
    allow = [("SKIP", 77), ("SKIP", None), ("COULD-NOT-TELL", None), ("COULD-NOT-TELL", 1),
             ("COULD-NOT-TELL", 143), ("COULD-NOT-TELL", -9)]
    rows = [(st, rc, False) for st, rc in refuse] + [(st, rc, True) for st, rc in allow]
    for i, (state, rcv, taken) in enumerate(rows):
        label = f"b1 {state} rc {rcv}"
        sub = os.path.join(tmp, f"r{i}")
        os.makedirs(sub)
        doc = {"a1": result("a1", "PASS", 0, ""), "b1": result("b1", state, rcv, f"payload-{i}")}
        hr = _inner_part_heavy_run(sub, doc)
        rc, out, status = run_gate(sub, [sh_step("a1", "heavy", "exit 0", "A"),
                                         sh_step("b1", "heavy", "exit 0", "B")], heavy=hr)
        st = by_name(status)
        expect(st["a1"]["state"] == "PASS", f"{label}: control a1 is {st['a1']}\n{out}")
        if not taken:
            expect(st["b1"]["state"] == "COULD-NOT-TELL",
                   f"{label}: a contradicting result was taken as {st['b1']['state']}\n{out}")
            expect(rc == 3, f"{label}: rc={rc}, expected 3\n{out}")
            continue
        expect(st["b1"]["state"] == state and st["b1"]["reason"] == f"payload-{i}",
               f"{label}: a result run_step can give was not taken: {st['b1']}\n{out}")
        expect(rc == (0 if state == "SKIP" else 3), f"{label}: rc={rc}\n{out}")


def _cwd_fixture(tmp: str, label: str):
    sub = os.path.join(tmp, label)
    root, outside = os.path.join(sub, "r"), os.path.join(sub, "o")
    os.makedirs(os.path.join(root, "sub"))
    os.makedirs(outside)
    return sub, root, outside


def _swap_to(root: str, outside: str) -> None:
    os.rename(os.path.join(root, "sub"), os.path.join(root, "sub.real"))
    os.symlink(outside, os.path.join(root, "sub"))


def _run_where(runner, sub: str, root: str, cwd: str) -> tuple:
    where = os.path.join(sub, "where.txt")
    step = runner.Step("w", "cheap", ("sh", "-c", f'pwd -P > "{where}"'), cwd=cwd)
    ctx = runner.Context(root, os.path.join(sub, "out"), 1.0, set())
    res = runner.run_step(step, ctx)
    landed = None
    if os.path.exists(where):
        with open(where, encoding="utf-8") as fh:
            landed = fh.read().strip()
    return res, landed


def case_cwd_swap_after_check_cannot_escape(tmp: str) -> None:
    # FIX r4: containment was checked on a pathname that Popen then resolved
    # again, so a symlink swapped in between sent the child outside --root.
    # Neighbours: a swap after the directory is opened cannot redirect the
    # child; no swap and an in-root symlink cwd still run.
    if os.name == "nt" or not os.path.isdir("/proc/self/fd"):
        raise Skip("the cwd binding needs /proc/self/fd (Linux)")

    runner = load_runner()
    sub, root, outside = _cwd_fixture(tmp, "pre-open")
    checked = runner.contained_cwd

    def swapping_check(r, c):
        got = checked(r, c)
        _swap_to(root, outside)
        return got

    runner.contained_cwd = swapping_check
    res, landed = _run_where(runner, sub, root, "sub")
    expect(landed is None or not landed.startswith(os.path.realpath(outside)),
           f"pre-open swap: the child ran outside --root, in {landed}: {res}")
    expect(res["state"] == "COULD-NOT-TELL" and "cwd" in res["reason"],
           f"pre-open swap: {res}")

    runner = load_runner()
    sub, root, outside = _cwd_fixture(tmp, "post-open")
    opener = runner._open_cwd  # pylint: disable=protected-access

    def swapping_open(r, c):
        got = opener(r, c)
        _swap_to(root, outside)
        return got

    runner._open_cwd = swapping_open  # pylint: disable=protected-access
    res, landed = _run_where(runner, sub, root, "sub")
    expect(res["state"] == "PASS" and landed == os.path.realpath(os.path.join(root, "sub.real")),
           f"post-open swap: the child did not run in the checked directory: {landed} {res}")

    runner = load_runner()
    sub, root, _outside = _cwd_fixture(tmp, "no-swap")
    res, landed = _run_where(runner, sub, root, "sub")
    expect(res["state"] == "PASS" and landed == os.path.realpath(os.path.join(root, "sub")),
           f"no swap: {landed} {res}")
    os.symlink(os.path.join(root, "sub"), os.path.join(root, "lnk"))
    res, landed = _run_where(runner, sub, root, "lnk")
    expect(res["state"] == "PASS" and landed == os.path.realpath(os.path.join(root, "sub")),
           f"in-root symlink cwd: {landed} {res}")


def _git_repo(root: str) -> list:
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
    os.makedirs(root, exist_ok=True)
    write(os.path.join(root, "a.txt"), "a\n")
    for cmd in (["init", "-q"], ["config", "core.quotePath", "false"], ["add", "-A"],
                ["commit", "-q", "-m", "fixture"]):
        subprocess.run(git + cmd, cwd=root, check=True, capture_output=True,
                       stdin=subprocess.DEVNULL, timeout=60)
    return git


def _dirty_runs(sub: str) -> list:
    """(label, rc, out, status) with --out and with the default --out."""
    step = [{"name": "c", "phase": "cheap", "argv": ["sh", "-c", "exit 0"]}]
    runs = []
    rc, out, status = run_gate(sub, step)
    runs.append(("--out", rc, out, status))
    tmpd = os.path.join(sub, "tmpd")
    os.makedirs(tmpd)
    table = write(os.path.join(sub, "table2.json"), json.dumps({"steps": step}))
    env = {k: v for k, v in os.environ.items() if k != "HEAVY_RUN"}
    env.update({"HEAVY_RUN": "none", "TMPDIR": tmpd})
    proc = subprocess.run([sys.executable, TARGET, "--root", os.path.join(sub, "root"),
                           "--table", table, "--grace", "1"], capture_output=True, text=True,
                          env=env, stdin=subprocess.DEVNULL, timeout=CALL_TIMEOUT, check=False)
    found = None
    base = os.path.join(tmpd, "gate-runner")
    for name in (os.listdir(base) if os.path.isdir(base) else []):
        path = os.path.join(base, name, "status.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                found = json.load(fh)
    runs.append(("default --out", proc.returncode, proc.stdout + proc.stderr, found))
    return runs


def case_non_utf8_dirty_name_does_not_crash(tmp: str) -> None:
    # FIX r4: `git status --porcelain` was decoded as UTF-8 text, so an untracked
    # name holding byte 0xff raised before status.json existed. Neighbours: a
    # tracked file modified is dirty too, and a clean repository is not.
    if os.name == "nt":
        raise Skip("bytes file names are POSIX only")
    rows = []
    sub = os.path.join(tmp, "untracked")
    _git_repo(os.path.join(sub, "root"))
    with open(os.path.join(os.fsencode(sub), b"root", b"bad\xff.py"), "wb") as fh:
        fh.write(b"x = 1\n")
    rows.append(("untracked bad name", sub, True))

    sub = os.path.join(tmp, "tracked")
    git = _git_repo(os.path.join(sub, "root"))
    bad = os.path.join(os.fsencode(sub), b"root", b"bad\xff.py")
    with open(bad, "wb") as fh:
        fh.write(b"x = 1\n")
    for cmd in (["add", "-A"], ["commit", "-q", "-m", "bad"]):
        subprocess.run(git + cmd, cwd=os.path.join(sub, "root"), check=True,
                       capture_output=True, stdin=subprocess.DEVNULL, timeout=60)
    with open(bad, "ab") as fh:
        fh.write(b"y = 2\n")
    rows.append(("tracked bad name modified", sub, True))

    sub = os.path.join(tmp, "clean")
    _git_repo(os.path.join(sub, "root"))
    rows.append(("clean", sub, False))

    for label, sub, dirty in rows:
        for how, rc, out, status in _dirty_runs(sub):
            expect("Traceback" not in out, f"{label} ({how}): the runner crashed\n{out}")
            expect(status is not None, f"{label} ({how}): no status.json\n{out}")
            expect(status["dirty"] is dirty,
                   f"{label} ({how}): dirty is {status['dirty']!r}, expected {dirty}\n{out}")
            expect(rc == 0, f"{label} ({how}): rc={rc}\n{out}")


def case_table_changed_mid_run_is_refused(tmp: str) -> None:
    # FIX r4: the inner runner re-read --table after the cheap steps ran, so a
    # cheap step that rewrote the file ran a different heavy command than the
    # one the outer runner validated. Neighbours: a byte-identical rewrite still
    # runs; a changed built-in step changes the digest; --inner refuses a
    # digest that does not match, and refuses to run without one.
    for label, changed in (("changed", True), ("identical", False)):
        sub = os.path.join(tmp, label)
        os.makedirs(sub)
        flag = os.path.join(sub, "replaced.flag")
        table = os.path.join(sub, "table.json")
        h1 = sh_step("h1", "heavy", "exit 0", "A")
        replacement = dict(h1, argv=["touch", flag]) if changed else h1
        rewrite = {"name": "rw", "phase": "cheap", "argv": ["cp", os.path.join(sub, "next.json"),
                                                            table]}
        write(os.path.join(sub, "next.json"), json.dumps({"steps": [rewrite, replacement]}))
        rc, out, status = run_gate(sub, [rewrite, h1])
        st = by_name(status)
        expect(st["rw"]["state"] == "PASS", f"{label}: fixture rewrite failed {st['rw']}\n{out}")
        if changed:
            expect(not os.path.exists(flag), f"changed: the replaced heavy command ran\n{out}")
            expect(st["h1"]["state"] == "COULD-NOT-TELL" and "table changed" in st["h1"]["reason"],
                   f"changed: h1 is {st['h1']}\n{out}")
            expect(rc == 3, f"changed: rc={rc}\n{out}")
        else:
            expect(st["h1"]["state"] == "PASS" and rc == 0,
                   f"identical: a byte-identical rewrite was refused: rc={rc} {st['h1']}\n{out}")

    import dataclasses
    runner = load_runner()
    digest = runner.table_digest
    base = digest(list(runner.TABLE))
    target = runner.TABLE[0]
    for field, value in (("argv", target.argv + ("--x",)), ("cwd", "scripts"), ("timeout", 7),
                         ("phase", "solo"), ("group", "A")):
        edited = [dataclasses.replace(target, **{field: value})] + list(runner.TABLE[1:])
        expect(digest(edited) != base, f"table_digest does not change with {field}")

    sub = os.path.join(tmp, "by-hand")
    os.makedirs(os.path.join(sub, "root"))
    table = write(os.path.join(sub, "t.json"), json.dumps({"steps": [h1]}))
    part = os.path.join(sub, "part.json")
    for extra in (["--table-digest", "0" * 64], []):
        if os.path.exists(part):
            os.remove(part)
        proc = subprocess.run([sys.executable, TARGET, "--inner", part, "--root",
                               os.path.join(sub, "root"), "--out", os.path.join(sub, "out"),
                               "--table", table, *extra], capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=CALL_TIMEOUT, check=False)
        what = "a wrong digest" if extra else "no digest"
        expect(proc.returncode == 2, f"--inner with {what}: rc={proc.returncode}\n"
                                     f"{proc.stdout}{proc.stderr}")
        recorded = {}
        if os.path.exists(part):
            with open(part, encoding="utf-8") as fh:
                recorded = json.load(fh).get("steps", {})
        expect(not recorded, f"--inner with {what} recorded steps: {recorded}")


def case_relative_path_tool_is_made_absolute(tmp: str) -> None:
    # FIX r4: _which returned a relative path for a relative PATH entry, and the
    # child resolved it again against the step's cwd. Neighbours: `bin` without
    # `./`, an empty PATH entry, and an absolute entry.
    if os.name == "nt":
        raise Skip("POSIX shebang fixture")
    sh_dir = os.path.dirname(shutil.which("sh") or "/bin/sh")
    for i, (label, entry, at) in enumerate((("./bin", "./bin", "bin"), ("bin", "bin", "bin"),
                                            ("empty entry", "", "."),
                                            ("absolute", None, "bin"))):
        sub = os.path.join(tmp, f"p{i}")
        root = os.path.join(sub, "root")
        os.makedirs(os.path.join(root, "sub"))
        tool = write(os.path.join(root, at, "tool"), "#!/bin/sh\nexit 0\n", 0o755)
        path = (os.path.join(root, "bin") if entry is None else entry) + os.pathsep + sh_dir
        step = {"name": "t", "phase": "cheap", "argv": ["tool"], "needs": ["tool"], "cwd": "sub"}
        rc, out, status = run_gate(sub, [step], env_extra={"PATH": path}, cwd=root)
        st = by_name(status)["t"]
        got = st["argv"][0]
        expect(st["state"] == "PASS", f"{label}: {st}\n{out}")
        expect(os.path.isabs(got) and os.path.realpath(got) == os.path.realpath(tool),
               f"{label}: recorded argv[0] {got!r}, expected {tool}\n{out}")
        expect(rc == 0, f"{label}: rc={rc}\n{out}")


# ---- review round 5 (L-0513 Fix phase) ------------------------------------

def _many_heavy(sub: str, rows: dict):
    """One gate run: heavy step `name` per row (groups alternating A, B, each
    `exit 0`), under a fake heavy-run that files each row as that step's
    result. One run per batch keeps the case inside the suite's budget."""
    names = sorted(rows)
    hr = _inner_part_heavy_run(sub, rows)
    return run_gate(sub, [sh_step(n, "heavy", "exit 0", _row_group(i))
                          for i, n in enumerate(names)], heavy=hr)


def _row_group(i: int) -> str:
    """The group of the i-th step in sorted name order: A, B, A, ..."""
    return "AB"[i % 2]


def case_heavy_part_fail_needs_a_failing_rc(tmp: str) -> None:
    # FIX r5: a heavy-part FAIL was taken with any non-zero rc, so rc 77 (a
    # skip), a negative rc and 129-143 (signal deaths) read FAIL and exit 1
    # where run_step's classify() gives SKIP or COULD-NOT-TELL. Neighbours: a
    # FAIL with an ordinary failing rc (1, 2, 128, 255) is still taken.
    refuse = [77, -9, -15, 129, 130, 131, 134, 137, 139, 143]
    allow = [1, 2, 128, 255]
    for label, rcs, want_state, want_rc in (("refused", refuse, "COULD-NOT-TELL", 3),
                                            ("allowed", allow, "FAIL", 1)):
        rows = {f"s{i:02d}": part_row(f"s{i:02d}", "FAIL", rcv, f"payload-{rcv}",
                                      group=_row_group(i))
                for i, rcv in enumerate(rcs)}
        sub = os.path.join(tmp, label)
        os.makedirs(sub)
        rc, out, status = _many_heavy(sub, rows)
        st = by_name(status)
        for name, row in rows.items():
            got = st[name]
            expect(got["state"] == want_state,
                   f"FAIL rc {row['rc']}: read {got['state']}, expected {want_state}\n{out}")
            if want_state == "FAIL":
                expect(got["reason"] == row["reason"],
                       f"FAIL rc {row['rc']}: the payload's reason was not kept: {got}")
        expect(rc == want_rc, f"{label}: rc={rc}, expected {want_rc}\n{out}")


def case_heavy_part_needs_step_metadata(tmp: str) -> None:
    # FIX r5: a heavy-part row with only name/rc/state/reason/seconds/log was
    # taken, so overall PASS came with a status.json step lacking phase,
    # group, argv, cwd and timeout (acceptance check 11). Neighbours: each
    # field present but contradicting the table, or of the wrong type, is not
    # taken either; the full row run_step writes still is.
    def full(name, i):
        return part_row(name, "PASS", 0, group=_row_group(i))

    def other_group(i):
        return _row_group(i + 1)

    edits = [("missing phase", lambda r, i: r.pop("phase")),
             ("missing group", lambda r, i: r.pop("group")),
             ("missing argv", lambda r, i: r.pop("argv")),
             ("missing cwd", lambda r, i: r.pop("cwd")),
             ("missing timeout", lambda r, i: r.pop("timeout")),
             ("phase solo", lambda r, i: r.update(phase="solo")),
             ("other group", lambda r, i: r.update(group=other_group(i))),
             ("group null", lambda r, i: r.update(group=None)),
             ("cwd sub", lambda r, i: r.update(cwd="sub")),
             ("timeout 61", lambda r, i: r.update(timeout=61)),
             ("timeout string", lambda r, i: r.update(timeout="60")),
             ("timeout float", lambda r, i: r.update(timeout=60.0)),
             ("argv string", lambda r, i: r.update(argv="sh -c exit 0")),
             ("argv non-str item", lambda r, i: r.update(argv=["sh", 1]))]
    rows, labels = {}, {}
    for i, (label, edit) in enumerate(edits):
        name = f"m{i:02d}"
        row = full(name, i)
        edit(row, i)
        rows[name], labels[name] = row, label
    sub = os.path.join(tmp, "bad")
    os.makedirs(sub)
    rc, out, status = _many_heavy(sub, rows)
    st = by_name(status)
    for name, label in labels.items():
        got = st[name]
        expect(got["state"] == "COULD-NOT-TELL",
               f"{label}: {name} is {got['state']} from a row without the step's metadata"
               f"\n{out}")
        for key in ("phase", "group", "argv", "cwd", "timeout"):
            expect(key in got, f"{label}: status.json's {name} lacks {key}: {got}")
    expect(rc == 3, f"bad rows: rc={rc}, expected 3\n{out}")
    sub = os.path.join(tmp, "control")
    os.makedirs(sub)
    rc, out, status = _many_heavy(sub, {"c0": full("c0", 0), "c1": full("c1", 1)})
    st = by_name(status)
    expect(rc == 0 and all(st[n]["state"] == "PASS" for n in ("c0", "c1")),
           f"control: the full rows were not taken: rc={rc} {st}\n{out}")


def _record_killpg(calls: list, procs: list):
    """Wrap os.killpg so each call records (pgid, sig, whether the step's leader
    was already reaped at that moment); the real signal is still sent."""
    real = os.killpg

    def recorder(pgid, sig):
        reaped = any(p.pid == pgid and p.returncode is not None for p in procs)
        calls.append((pgid, int(sig), reaped))
        return real(pgid, sig)
    return real, recorder


def _pid_gone(pid: int, limit: float) -> bool:
    """True once pid no longer exists or is a zombie (dead, awaiting its reaper)."""
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        try:
            with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
                if fh.read().rsplit(")", 1)[1].split()[0] == "Z":
                    return True
        except FileNotFoundError:
            return True
        except OSError:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return True
        time.sleep(0.1)
    return False


def case_no_group_signal_after_leader_reaped(tmp: str) -> None:
    # BLOCK r6 (owner amendment): after proc.wait() reaped the leader,
    # _kill_group sent one more SIGKILL to its process group. Once the leader
    # is reaped and its group is empty the numeric PGID is free for reuse, so
    # that sweep could SIGKILL an unrelated process group. Neither
    # _signal_group on a reaped leader nor _kill_group on a timed-out one may
    # call killpg once the leader has been reaped.
    runner = load_runner()
    calls: list = []
    ready = os.path.join(tmp, "ready")
    proc = subprocess.Popen(  # pylint: disable=consider-using-with
        ["sh", "-c", f'trap "" TERM; touch "{ready}"; while :; do sleep 0.1; done'],
        stdin=subprocess.DEVNULL, **runner._group_kwargs())
    try:
        deadline = time.monotonic() + 10
        while not os.path.exists(ready) and time.monotonic() < deadline:
            time.sleep(0.05)
        real, recorder = _record_killpg(calls, [proc])
        os.killpg = recorder
        try:
            got = runner._kill_group(proc, 0.3)
        finally:
            os.killpg = real
    finally:
        if proc.returncode is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            proc.wait()
    expect(got is True, f"_kill_group returned {got!r} for a leader SIGKILL reaps")
    expect(proc.returncode is not None, "_kill_group returned without reaping the leader")
    expect(any(sig == signal.SIGKILL for _pg, sig, _r in calls), f"no SIGKILL sent: {calls}")
    late = [c for c in calls if c[2]]
    expect(not late, f"killpg sent after the leader was reaped (PGID may be reused): {late}")

    calls.clear()
    done = subprocess.Popen(["sleep", "0"],  # pylint: disable=consider-using-with
                            **runner._group_kwargs())
    done.wait()
    real, recorder = _record_killpg(calls, [done])
    os.killpg = recorder
    try:
        runner._signal_group(done, hard=True)
        runner._signal_group(done, hard=False)
    finally:
        os.killpg = real
    expect(not calls, f"_signal_group signalled a reaped leader's group: {calls}")


def case_timeout_kills_group_outliving_leader(tmp: str) -> None:
    # BLOCK r6 neighbour: the fix must not stop at the leader. A timed-out
    # group whose leader exits on SIGTERM while a child ignoring SIGTERM lives
    # on is still SIGKILLed after the grace period.
    runner = load_runner()
    pidfile = os.path.join(tmp, "child.pid")
    script = (f'(trap "" TERM; while :; do sleep 0.1; done) & echo $! > "{pidfile}"; '
              'trap "exit 0" TERM; while :; do sleep 0.1; done')
    proc = subprocess.Popen(["sh", "-c", script],  # pylint: disable=consider-using-with
                            stdin=subprocess.DEVNULL, **runner._group_kwargs())
    child = None
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                with open(pidfile, encoding="utf-8") as fh:
                    child = int(fh.read().strip())
                break
            except (OSError, ValueError):
                time.sleep(0.05)
        expect(child is not None, "the fixture's child never wrote its pid")
        time.sleep(0.3)
        got = runner._kill_group(proc, 0.5)
        gone = _pid_gone(child, 5)
    finally:
        for pid in (child, proc.pid):
            if pid is not None:
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
        if proc.returncode is None:
            proc.wait()
    expect(got is True, f"_kill_group returned {got!r}")
    expect(gone, f"child {child} outlived its leader and survived the group SIGKILL")


CASES = [
    case_list_prints_phases,
    case_one_heavy_run_call_for_both_groups,
    case_groups_parallel_then_solo,
    case_heavy_run_absent_is_stated,
    case_heavy_run_bad_path_refuses,
    case_states_from_rc,
    case_timeout_is_could_not_tell,
    case_signal_death_is_could_not_tell,
    case_cannot_start_is_could_not_tell,
    case_timeout_kills_grandchildren,
    case_heavy_call_killed_marks_unfinished,
    case_inner_signal_is_not_heavy_rc_zero,
    case_table_pins_n4,
    case_missing_xdist_is_could_not_tell,
    case_ci_drift_table_covers_workflows,
    case_ci_drift_goes_red_on_unknown_step,
    case_overall_and_exit_codes,
    case_all_skip_is_not_pass,
    case_status_file_shape_and_atomic_write,
    case_never_sets_heavy_run_caps,
    case_skip_and_table_are_recorded,
    case_ci_drift_scans_crew_shell_matrix,
    case_ci_drift_windows_only_step_needs_its_if,
    case_ci_drift_compound_commands,
    case_table_rejects_unsafe_step_names,
    case_table_rejects_wrong_field_types,
    case_skip_wins_before_argv_is_built,
    case_heavy_results_reach_status_json,
    case_default_out_is_claimed_atomically,
    case_table_rejects_non_finite_timeout,
    case_ci_drift_substitution_in_dropped_line,
    case_kill_wait_is_bounded,
    case_heavy_part_wrong_shape_is_could_not_tell,
    case_table_cwd_stays_in_root,
    case_non_utf8_tracked_name_does_not_crash,
    case_heavy_part_forged_pass_is_could_not_tell,
    case_ci_drift_process_substitution_in_excluded_install,
    case_table_rejects_group_on_non_heavy_step,
    case_ci_drift_wrong_yaml_shape_is_a_problem,
    case_timeout_grace_covers_grandchildren,
    case_cwd_rechecked_at_launch,
    case_heavy_part_state_contradicts_rc,
    case_cwd_swap_after_check_cannot_escape,
    case_non_utf8_dirty_name_does_not_crash,
    case_table_changed_mid_run_is_refused,
    case_relative_path_tool_is_made_absolute,
    case_heavy_part_fail_needs_a_failing_rc,
    case_heavy_part_needs_step_metadata,
    case_no_group_signal_after_leader_reaped,
    case_timeout_kills_group_outliving_leader,
]


def main() -> int:
    if os.name == "nt":
        print("gate-runner suite: POSIX fixtures (sh); NOT RUN on Windows")
        return 77
    passed = failed = skipped = 0
    for case in CASES:
        tmp = tempfile.mkdtemp(prefix="gate-runner-test-")
        try:
            case(tmp)
            passed += 1
            print(f"PASS {case.__name__}")
        except Skip as exc:
            skipped += 1
            print(f"SKIP {case.__name__}: {exc} (NOT VERIFIED)")
        except Exception as exc:  # a crash in a case is a failure of that case
            failed += 1
            detail = str(exc) if isinstance(exc, AssertionError) else traceback.format_exc()
            print(f"FAIL {case.__name__}: {detail}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"{passed} passed, {failed} failed, {skipped} skipped")
    if failed:
        return 1
    return 77 if skipped else 0


if __name__ == "__main__":
    sys.exit(main())
