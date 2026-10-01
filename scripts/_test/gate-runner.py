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
             env_extra: dict | None = None, grace: str = "1"):
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
    proc = subprocess.run(argv, capture_output=True, text=True, env=env,
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
