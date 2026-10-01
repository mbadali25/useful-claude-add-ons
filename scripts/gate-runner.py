#!/usr/bin/env python3
"""One local gate runner for this repository: the whole PR-path CI suite, run
the way a lane needs it, with one status file.

Run: python3 scripts/gate-runner.py            (the whole table)
     python3 scripts/gate-runner.py --list     (what it would run)
     python3 scripts/gate-runner.py --check-ci (is the table still CI's?)

Three phases, in order:
  cheap  every quick check, serially, directly -- never under heavy-run, so a
         one-second check never queues for a heavy slot;
  heavy  two groups, A and B, run AT THE SAME TIME inside ONE heavy-run call
         (one slot, one 6G cgroup); each group is serial within itself;
  solo   after both groups finish, inside that same call: the `wallclock`
         pytest set (asserts elapsed time, so it cannot share the CPU with
         xdist workers -- plugin/crew/tests/conftest.py) and sabotage.py (it
         edits real source in place, so nothing else may read the tree).

heavy-run is found from HEAVY_RUN: unset = /root/crew-tmp/heavy-run when that
is executable, else absent; `none` = absent; any other value must be an
executable or the run refuses (exit 2). Absent means the heavy phase runs
directly and the run SAYS so: `heavy_run: absent (uncapped)`. This runner
never sets HEAVY_RUN_NOCAP or HEAVY_RUN_MEM.

Every pytest step except `wallclock` carries a literal `-n 4`. If pytest-xdist
is not importable those steps are COULD-NOT-TELL; they never fall back to a
serial run.

States: PASS (rc 0), FAIL (rc non-zero, the step completed), SKIP (rc 77, or a
tool the step needs is missing -- NOT VERIFIED), COULD-NOT-TELL (timed out,
killed by a signal incl. rc 137/143, could not start, or no result recorded).
A timeout kills the step's whole process group: SIGTERM, a grace period
(--grace, default 30 s), then SIGKILL. A heavy-run call that dies leaves every
heavy/solo step it had not recorded COULD-NOT-TELL.

Overall and exit: any FAIL = FAIL, exit 1; else any COULD-NOT-TELL, or no step
PASSED at all = COULD-NOT-TELL, exit 3; else PASS, exit 0. Usage error or
refusal = exit 2. The last stdout line counts every SKIP and says when the
table or the step set is not the repo gate (--table, --only).

Status: one JSON file, <out>/status.json, default out
$TMPDIR/gate-runner/<shortsha>-<utc>/, rewritten (temp file + os.replace)
after every step; per-step logs under <out>/logs/.

The table is derived from .github/workflows/; `--check-ci` (and
scripts/_test/gate-runner.py) fails when a workflow `run:` command is in
neither the table nor EXCLUDED_CI, or a workflow file is unclassified. The
check is one-way: table steps CI does not run (sabotage.py, ruff-no-new,
check-tooling-pr) are allowed.

Windows: the kill path uses CREATE_NEW_PROCESS_GROUP and `taskkill /T`. Not
verified on a Windows host.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.dirname(HERE)
DEFAULT_HEAVY_RUN = "/root/crew-tmp/heavy-run"
DEFAULT_RUFF_NO_NEW = "/root/crew-tmp/ruff-no-new.py"
WINDOWS_PWSH = "C:/Program Files/PowerShell/7/pwsh.exe"

PASS, FAIL, SKIP, CNT = "PASS", "FAIL", "SKIP", "COULD-NOT-TELL"
EXIT_PASS, EXIT_FAIL, EXIT_USAGE, EXIT_CNT, EXIT_SKIP = 0, 1, 2, 3, 77
SIGNAL_RCS = {129: "SIGHUP", 130: "SIGINT", 131: "SIGQUIT", 134: "SIGABRT",
              137: "SIGKILL (a memory cap or OOM kill looks like this)", 139: "SIGSEGV",
              143: "SIGTERM"}
PHASES = ("cheap", "heavy", "solo")
SLOT_WAIT_ALLOWANCE = 3600


@dataclass(frozen=True)
class Step:
    name: str
    phase: str
    argv: tuple
    group: str | None = None
    cwd: str = "."
    timeout: int = 300
    needs: tuple = ()
    pytest: bool = False
    ci: tuple = ()


PY = "{python}"
COMBINED_DIRS = ("plugin/crew/tests/", "plugin/gizmoduck/scripts/_test/",
                 "skills/mermaid-svg-bitbucket/tests/", "skills/notify/tests/",
                 "skills/doc-builder/scripts/_test/", "skills/intune-graph/scripts/_test/")
NO_CACHE = ("-p", "no:cacheprovider")


def _py_suite(name: str, path: str, workflow: str = "marketplace.yml") -> Step:
    return Step(name, "cheap", (PY, path), ci=((workflow, f"python3 {path}"),))


def _bash_suite(name: str, path: str, workflow: str, phase: str = "cheap",
                group: str | None = None, timeout: int = 300, ci_cmd: str | None = None) -> Step:
    return Step(name, phase, ("bash", path), group=group, timeout=timeout, needs=("bash",),
                ci=((workflow, ci_cmd or f"bash {path}"),))


TABLE = (
    Step("check-marketplace", "cheap", (PY, "scripts/check-marketplace.py"),
         ci=(("marketplace.yml", "python3 scripts/check-marketplace.py"),)),
    _py_suite("argument-hint-frontmatter", "scripts/_test/argument-hint-frontmatter.py"),
    _py_suite("self-claims", "scripts/_test/self-claims.py"),
    _py_suite("crew-ignore-policy", "scripts/_test/crew-ignore-policy.py"),
    _py_suite("version-drift", "scripts/_test/version-drift.py"),
    _py_suite("instruction-budgets-suite", "scripts/_test/instruction-budgets.py",
              "instruction-budgets.yml"),
    Step("sync-updates", "cheap", (PY, "scripts/sync-updates.py", "--check"),
         ci=(("marketplace.yml", "python3 scripts/sync-updates.py --check"),)),
    Step("install-prerequisites-syntax", "cheap", ("bash", "-n", "scripts/install-prerequisites.sh"),
         needs=("bash",), ci=(("marketplace.yml", "bash -n scripts/install-prerequisites.sh"),)),
    _bash_suite("menu-groups", "scripts/_test/menu-groups.sh", "marketplace.yml",
                ci_cmd="./scripts/_test/menu-groups.sh"),
    _bash_suite("check-powershell-suite", "scripts/_test/check-powershell.sh", "marketplace.yml"),
    _bash_suite("ps-install-keys", "scripts/_test/ps-install-keys.sh", "marketplace.yml"),
    _bash_suite("uv-install", "scripts/_test/uv-install.sh", "marketplace.yml"),
    _bash_suite("mcp-preflight-catalog", "scripts/_test/mcp-preflight-catalog.sh", "marketplace.yml"),
    Step("validate-prompts", "cheap", (PY, "hooks/scripts/_test/validate-prompts.py"),
         cwd="plugin/crew",
         ci=(("marketplace.yml", "python3 hooks/scripts/_test/validate-prompts.py"),)),
    Step("check-powershell", "cheap", ("pwsh", "-NoProfile", "-File", "scripts/check-powershell.ps1"),
         needs=("pwsh",), ci=(("marketplace.yml", "./scripts/check-powershell.ps1"),)),
    Step("check-instructions", "cheap", (PY, "scripts/check_instructions.py"),
         ci=(("instruction-budgets.yml", "python3 scripts/check_instructions.py"),
             ("instruction-budgets.yml", 'python3 scripts/check_instructions.py --base "$BASE"'))),
    _bash_suite("bitbucket-merge-gate", "skills/bitbucket/scripts/_test/merge_gate.sh",
                "shell-suites.yml"),
    _bash_suite("doc-builder-checklist", "skills/doc-builder/scripts/_test/checklist.sh",
                "shell-suites.yml"),
    _bash_suite("jira-manager-jq-absence", "skills/jira-manager/scripts/_test/jq_absence.sh",
                "shell-suites.yml"),
    Step("ruff", "cheap", ("ruff", "check", "."), needs=("ruff",),
         ci=(("pylint.yml", "ruff check ."),)),
    Step("ruff-no-new", "cheap", (PY, "{ruff_no_new}", "{root}"), needs=("path:{ruff_no_new}",)),
    Step("check-tooling-pr", "cheap", (PY, "scripts/check-tooling-pr.py")),

    Step("pytest-combined", "heavy",
         (PY, "-m", "pytest", *COMBINED_DIRS, "-n", "4", "-m", "not wallclock", *NO_CACHE),
         group="A", timeout=1800, pytest=True,
         ci=(("pytest-crew.yml", "pytest " + " ".join(COMBINED_DIRS)
              + ' -n auto -m "not wallclock" -v'),)),

    _bash_suite("crew-run-tests", "plugin/crew/hooks/scripts/_test/run-tests.sh", "marketplace.yml",
                phase="heavy", group="B", timeout=900),
    _bash_suite("obsidian-vault-run-tests", "plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh",
                "shell-suites.yml", phase="heavy", group="B", timeout=900),
    Step("pylint", "heavy", ("pylint", "-j", "4", "{git_py_files}"), group="B", timeout=900,
         needs=("pylint",),
         ci=(("pylint.yml", "pylint -j \"$(python -c 'import os; print(os.cpu_count() or 1)')\" "
              "$(git ls-files '*.py')"),)),
    Step("pytest-cisco-meraki", "heavy",
         (PY, "-m", "pytest", "skills/cisco-meraki/tests/", "-n", "4", *NO_CACHE),
         group="B", timeout=900, pytest=True,
         ci=(("pytest-crew.yml", "pytest skills/cisco-meraki/tests/ -v"),)),
    Step("pytest-wazuh-onprem", "heavy",
         (PY, "-m", "pytest", "skills/wazuh-onprem/scripts/_test/", "-n", "4", *NO_CACHE),
         group="B", timeout=900, pytest=True,
         ci=(("pytest-crew.yml", "pytest skills/wazuh-onprem/scripts/_test/ -v"),)),
    Step("mcp-servers-npm-test", "heavy", ("npm", "test"), group="B", cwd="mcp-servers", timeout=900,
         needs=("npm", "path:mcp-servers/node_modules"), ci=(("mcp-servers.yml", "npm test"),)),

    Step("wallclock", "solo", (PY, "-m", "pytest", "plugin/crew/tests/", "-m", "wallclock", *NO_CACHE),
         timeout=900, pytest=True,
         ci=(("pytest-crew.yml", "pytest plugin/crew/tests/ -m wallclock -v"),)),
    Step("sabotage", "solo", (PY, "plugin/crew/tests/sabotage.py"), timeout=5400),
)

INCLUDED_WORKFLOWS = ("instruction-budgets.yml", "marketplace.yml", "mcp-servers.yml",
                      "pylint.yml", "pytest-crew.yml", "shell-suites.yml")
EXCLUDED_WORKFLOWS = (
    ("plugin-evals.yml", "real, billed model calls behind a repository secret"),
    ("publish-mcp-servers.yml", "tag-only npm publish; its npm test is mcp-servers.yml's"),
)
EXCLUDED_JOBS = (
    ("pytest-crew.yml", "crew-shell-matrix", "windows-latest only; this runner has no Windows leg"),
)
INSTALL = "an install step, not a check"
EXCLUDED_CI = (
    ("marketplace.yml", "python -m pip install *", INSTALL),
    ("marketplace.yml", "npm install -g @anthropic-ai/claude-code@*", INSTALL),
    ("marketplace.yml", "claude plugin validate --strict *",
     "CI pins the Claude Code CLI version; a lane's CLI differs, so its verdict is not CI's"),
    ("pylint.yml", "python -m pip install *", INSTALL),
    ("pylint.yml", "pip install *", INSTALL),
    ("pylint.yml", "pylint --version", "prints a version"),
    ("pylint.yml", "ruff --version", "prints a version"),
    ("pytest-crew.yml", "python -m pip install *", INSTALL),
    ("pytest-crew.yml", "pip install *", INSTALL),
    ("mcp-servers.yml", "npm ci", INSTALL + "; the npm test step SKIPs without node_modules"),
)


class Refusal(Exception):
    """A usage error or refusal: exit 2."""


class CannotStart(Exception):
    """A step's command could not be built or launched."""


# ---- process handling -----------------------------------------------------

STOP = threading.Event()
# The first signal that set STOP; the inner runner exits 128+signum with it, so
# the outer status never records a signal-stopped heavy-run call as rc=0.
STOP_SIGNAL: list = []
_LIVE: set = set()
_LIVE_LOCK = threading.Lock()


def _group_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _signal_group(proc: subprocess.Popen, hard: bool) -> None:
    if os.name == "nt":
        cmd = ["taskkill", "/T", "/PID", str(proc.pid)] + (["/F"] if hard else [])
        subprocess.run(cmd, capture_output=True, check=False, stdin=subprocess.DEVNULL)
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL if hard else signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        if hard and proc.poll() is None:
            # No group to signal (it was never made, or is gone): kill the
            # child itself, so the caller's wait() cannot block forever.
            try:
                proc.kill()
            except OSError:
                pass


def _kill_group(proc: subprocess.Popen, grace: float) -> None:
    """SIGTERM the whole group, wait `grace`, SIGKILL; then sweep the group
    once more so a grandchild that outlived its leader is not left running."""
    _signal_group(proc, hard=False)
    try:
        proc.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        _signal_group(proc, hard=True)
        proc.wait()
    _signal_group(proc, hard=True)


def spawn_and_wait(argv: list, cwd: str, log: str, timeout: float, grace: float,
                   env: dict | None = None, on_tick=None):
    """Run argv in its own process group, output to `log`, no pipes (an orphan
    holding a pipe would hang the caller). Returns (rc, timed_out, started, note)."""
    os.makedirs(os.path.dirname(log), exist_ok=True)
    with open(log, "wb") as fh:
        try:  # not `with`: the loop below waits on it and owns killing its group
            # pylint: disable-next=consider-using-with
            proc = subprocess.Popen(argv, cwd=cwd, stdout=fh, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, env=env, **_group_kwargs())
        except (OSError, ValueError) as exc:
            return None, False, False, f"could not start: {exc}"
        with _LIVE_LOCK:
            _LIVE.add(proc)
        try:
            deadline = time.monotonic() + timeout
            stopped_at = None
            while True:
                try:
                    return proc.wait(timeout=0.5), False, True, ""
                except subprocess.TimeoutExpired:
                    pass
                if on_tick is not None:
                    on_tick()
                now = time.monotonic()
                if STOP.is_set():
                    if stopped_at is None:
                        stopped_at = now
                        _signal_group(proc, hard=False)
                    elif now - stopped_at > grace:
                        _signal_group(proc, hard=True)
                if now >= deadline:
                    _kill_group(proc, grace)
                    return (proc.returncode, True, True,
                            f"timed out after {timeout:g}s; process group killed "
                            f"(SIGTERM, {grace:g}s grace, SIGKILL)")
        finally:
            with _LIVE_LOCK:
                _LIVE.discard(proc)


def _on_signal(signum, _frame) -> None:
    if not STOP_SIGNAL:
        STOP_SIGNAL.append(int(signum))
    STOP.set()
    with _LIVE_LOCK:
        live = list(_LIVE)
    for proc in live:
        _signal_group(proc, hard=False)
    print(f"gate-runner: received signal {signum}; stopping steps", file=sys.stderr, flush=True)


def install_signal_handlers() -> None:
    for name in ("SIGTERM", "SIGINT", "SIGHUP"):
        sig = getattr(signal, name, None)
        if sig is not None:
            try:
                signal.signal(sig, _on_signal)
            except (ValueError, OSError):
                pass


# ---- classification -------------------------------------------------------

def classify(rc, timed_out: bool, started: bool):
    """(state, reason) from a step's outcome. Anything that is not a completed
    run with an exit status is COULD-NOT-TELL, never PASS (T-0082)."""
    if not started:
        return CNT, "could not start"
    if timed_out:
        return CNT, "timed out"
    if rc is None:
        return CNT, "no exit status recorded"
    if rc < 0:
        try:
            sig = signal.Signals(-rc).name
        except ValueError:
            sig = str(-rc)
        return CNT, f"killed by signal {sig}"
    if rc in SIGNAL_RCS:
        return CNT, f"exit {rc}: killed by {SIGNAL_RCS[rc]}"
    if rc == EXIT_SKIP:
        return SKIP, "exit 77: NOT VERIFIED"
    if rc == 0:
        return PASS, ""
    return FAIL, f"exit {rc}"


def overall(steps: list):
    """(state, exit code) for a run."""
    states = [s["state"] for s in steps]
    if FAIL in states:
        return FAIL, EXIT_FAIL
    if states and PASS in states and all(s in (PASS, SKIP) for s in states):
        return PASS, EXIT_PASS
    return CNT, EXIT_CNT


def write_status(path: str, data: dict) -> None:
    """Serialise first, then temp file + os.replace: a payload that cannot be
    written never truncates the previous status (CLAUDE.md, open() landmine)."""
    text = json.dumps(data, indent=2, sort_keys=False) + "\n"
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def read_json(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


# ---- table ----------------------------------------------------------------

def load_table(path: str | None):
    if path is None:
        return list(TABLE), "builtin"
    src = os.path.abspath(path)
    data = read_json(src)
    if data is None:
        raise Refusal(f"--table {path}: not readable JSON")
    raw = data.get("steps") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        raise Refusal(f"--table {path}: expected a list of steps or {{\"steps\": [...]}}")
    steps, seen = [], set()
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise Refusal(f"--table step {i}: not an object")
        name, phase, group = item.get("name"), item.get("phase"), item.get("group")
        argv = item.get("argv")
        if not isinstance(name, str) or not name or name in seen:
            raise Refusal(f"--table step {i}: missing or duplicate name")
        if phase not in PHASES:
            raise Refusal(f"--table step {name}: phase must be one of {PHASES}")
        if (phase == "heavy") != (group in ("A", "B")):
            raise Refusal(f"--table step {name}: heavy steps need group A or B, others none")
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
            raise Refusal(f"--table step {name}: argv must be a non-empty list of strings")
        timeout = item.get("timeout", 300)
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise Refusal(f"--table step {name}: timeout must be a positive number")
        seen.add(name)
        steps.append(Step(name, phase, tuple(argv), group=group, cwd=item.get("cwd", "."),
                          timeout=timeout, needs=tuple(item.get("needs", ())),
                          pytest=bool(item.get("pytest", False))))
    return steps, src


def phase_label(step: Step) -> str:
    return f"heavy {step.group}" if step.phase == "heavy" else step.phase


def print_list(steps: list) -> None:
    for step in steps:
        cwd = f" (cwd {step.cwd})" if step.cwd != "." else ""
        print(f"{phase_label(step):<8} {step.name:<28} timeout={step.timeout:>5}s  "
              f"{' '.join(step.argv)}{cwd}")


# ---- step execution -------------------------------------------------------

class Context:
    def __init__(self, root: str, out: str, grace: float, skip: set):
        self.root, self.out, self.grace, self.skip = root, out, grace, skip
        self.ruff_no_new = os.environ.get("RUFF_NO_NEW") or DEFAULT_RUFF_NO_NEW
        self._probe: dict = {}
        self._probe_lock = threading.Lock()

    def subst(self, text: str) -> str:
        return (text.replace("{python}", sys.executable).replace("{root}", self.root)
                .replace("{ruff_no_new}", self.ruff_no_new))

    def importable(self, module: str) -> bool:
        with self._probe_lock:
            if module not in self._probe:
                try:
                    proc = subprocess.run([sys.executable, "-c", f"import {module}"], cwd=self.root,
                                          capture_output=True, timeout=120, check=False,
                                          stdin=subprocess.DEVNULL)
                    self._probe[module] = proc.returncode == 0
                except (OSError, subprocess.TimeoutExpired):
                    self._probe[module] = False
            return self._probe[module]


def _which(tool: str) -> str | None:
    found = shutil.which(tool)
    if found is None and tool == "pwsh" and os.path.exists(WINDOWS_PWSH):
        found = WINDOWS_PWSH
    return found


def _git_py_files(root: str) -> list:
    try:
        proc = subprocess.run(["git", "ls-files", "-z", "*.py"], cwd=root, capture_output=True,
                              timeout=60, check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CannotStart(f"git ls-files failed: {exc}") from exc
    if proc.returncode != 0:
        raise CannotStart(f"git ls-files exit {proc.returncode}: "
                          f"{proc.stderr.decode(errors='replace').strip()}")
    return [p for p in proc.stdout.decode().split("\0") if p]


def build_argv(step: Step, ctx: Context) -> list:
    argv = []
    for arg in step.argv:
        if arg == "{git_py_files}":
            argv.extend(_git_py_files(ctx.root))
        else:
            argv.append(ctx.subst(arg))
    return argv


def preflight(step: Step, ctx: Context, argv: list):
    """(state, reason) when the step must not run, else None. Mutates argv[0]
    to the resolved tool path."""
    if step.name in ctx.skip:
        return SKIP, "skipped by --skip"
    for need in step.needs:
        if need.startswith("path:"):
            path = ctx.subst(need[len("path:"):])
            full = path if os.path.isabs(path) else os.path.join(ctx.root, path)
            if not os.path.exists(full):
                return SKIP, f"NOT VERIFIED: {path} does not exist"
            continue
        found = _which(need)
        if found is None:
            return SKIP, f"NOT VERIFIED: {need} not found on PATH"
        if argv and argv[0] == need:
            argv[0] = found
    if step.pytest:
        if not ctx.importable("pytest"):
            return CNT, "pytest not importable"
        if "-n" in step.argv and not ctx.importable("xdist"):
            return CNT, "pytest-xdist not importable (never run serially in its place)"
    return None


def new_result(step: Step, ctx: Context) -> dict:
    return {"name": step.name, "phase": step.phase, "group": step.group, "argv": list(step.argv),
            "cwd": step.cwd, "timeout": step.timeout, "rc": None, "state": None, "reason": "",
            "seconds": 0.0, "log": os.path.join(ctx.out, "logs", f"{step.name}.log")}


def run_step(step: Step, ctx: Context) -> dict:
    res = new_result(step, ctx)
    if STOP.is_set():
        res["state"], res["reason"] = CNT, "runner stopped by a signal before this step started"
        return res
    try:
        argv = build_argv(step, ctx)
    except CannotStart as exc:
        res["state"], res["reason"] = CNT, f"could not start: {exc}"
        return res
    blocked = preflight(step, ctx, argv)
    res["argv"] = argv
    if blocked is not None:
        res["state"], res["reason"] = blocked
        return res
    started_at = time.monotonic()
    rc, timed_out, started, note = spawn_and_wait(
        argv, os.path.join(ctx.root, step.cwd), res["log"], step.timeout, ctx.grace)
    res["seconds"] = round(time.monotonic() - started_at, 1)
    res["rc"] = rc
    state, reason = classify(rc, timed_out, started)
    if note:
        reason = note
    if STOP.is_set() and state != PASS:
        state, reason = CNT, f"runner stopped by a signal while this step ran ({reason})"
    res["state"], res["reason"] = state, reason
    return res


def summary_line(res: dict) -> str:
    line = (f"{res['state']} {res['name']} rc={res['rc']} secs={res['seconds']} "
            f"log={res['log']}")
    return f"{line} -- {res['reason']}" if res["reason"] else line


# ---- inner: the heavy and solo phases, inside the one heavy-run call ------

def run_inner(part: str, steps: list, ctx: Context) -> int:
    data = {"started": time.time(), "pid": os.getpid(), "steps": {}}
    lock = threading.Lock()
    write_status(part, data)

    def record(res: dict) -> None:
        with lock:
            data["steps"][res["name"]] = res
            write_status(part, data)
        print(summary_line(res), flush=True)

    def run_group(group: list) -> None:
        for step in group:
            record(run_step(step, ctx))

    threads = [threading.Thread(target=run_group, args=([s for s in steps if s.group == g],),
                                name=f"group-{g}") for g in ("A", "B")]
    for thread in threads:
        thread.start()
    while any(t.is_alive() for t in threads):
        for thread in threads:
            thread.join(timeout=0.5)
    run_group([s for s in steps if s.phase == "solo"])
    if STOP.is_set():
        return 128 + (STOP_SIGNAL[0] if STOP_SIGNAL else int(signal.SIGTERM))
    return 0


# ---- outer ----------------------------------------------------------------

def resolve_heavy_run(env) -> tuple:
    value = env.get("HEAVY_RUN")
    if value in (None, ""):
        if os.path.isfile(DEFAULT_HEAVY_RUN) and os.access(DEFAULT_HEAVY_RUN, os.X_OK):
            return "present", DEFAULT_HEAVY_RUN
        return "absent", None
    if value == "none":
        return "absent", None
    if os.path.isfile(value) and os.access(value, os.X_OK):
        return "present", os.path.abspath(value)
    raise Refusal(f"HEAVY_RUN={value} is not executable (unset it, or set HEAVY_RUN=none to run "
                  "the heavy phase directly)")


def _git(root: str, *args: str):
    try:
        proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=60,
                              check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 else None


def heavy_run_label(hr: dict) -> str:
    return hr["path"] if hr["mode"] == "present" else "absent (uncapped)"


def heavy_budget(steps: list, grace: float) -> float:
    a = sum(s.timeout for s in steps if s.group == "A")
    b = sum(s.timeout for s in steps if s.group == "B")
    solo = sum(s.timeout for s in steps if s.phase == "solo")
    return max(a, b) + solo + grace * (len(steps) + 2) + SLOT_WAIT_ALLOWANCE


def run_outer(args, steps: list, source: str, ctx: Context, hr: dict) -> int:
    status_path = os.path.join(ctx.out, "status.json")
    head = _git(ctx.root, "rev-parse", "HEAD")
    porcelain = _git(ctx.root, "status", "--porcelain")
    status = {
        "runner": "scripts/gate-runner.py",
        "root": ctx.root,
        "head": head.strip() if head else None,
        "dirty": (porcelain.strip() != "") if porcelain is not None else None,
        "table_source": source,
        "only": args.only or None,
        "heavy_run": hr,
        "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ended": None,
        "overall": "RUNNING",
        "steps": [],
    }
    results = status["steps"]

    def save() -> None:
        write_status(status_path, status)

    print(f"gate-runner: root {ctx.root}  heavy_run: {heavy_run_label(hr)}  status: {status_path}",
          flush=True)
    save()
    for step in [s for s in steps if s.phase == "cheap"]:
        res = run_step(step, ctx)
        results.append(res)
        save()
        print(summary_line(res), flush=True)

    inner_steps = [s for s in steps if s.phase in ("heavy", "solo")]
    if inner_steps:
        part = os.path.join(ctx.out, "heavy-part.json")
        cmd = [sys.executable, os.path.abspath(__file__), "--inner", part, "--root", ctx.root,
               "--out", ctx.out, "--grace", f"{ctx.grace:g}"]
        if source != "builtin":
            cmd += ["--table", source]
        for name in args.skip or ():
            cmd += ["--skip", name]
        for name in args.only or ():
            cmd += ["--only", name]
        if hr["mode"] == "present":
            cmd = [hr["path"], *cmd]
        printed: set = set()

        def tick() -> None:
            got = read_json(part)
            for name, res in ((got or {}).get("steps") or {}).items():
                if name not in printed:
                    printed.add(name)
                    print(summary_line(res), flush=True)

        budget = args.heavy_timeout or heavy_budget(inner_steps, ctx.grace)
        launched = time.time()
        hr["launched"] = True
        save()
        if STOP.is_set():
            rc, timed_out, note = None, False, "runner stopped by a signal before the heavy-run call"
        else:
            rc, timed_out, _started, note = spawn_and_wait(
                cmd, ctx.root, os.path.join(ctx.out, "logs", "heavy-run.log"), budget,
                ctx.grace * 2 + 5, on_tick=tick)
        hr["rc"] = rc
        got = read_json(part)
        recorded = (got or {}).get("steps") or {}
        if got and isinstance(got.get("started"), (int, float)):
            hr["waited_seconds"] = round(got["started"] - launched, 1)
        why = (f"heavy-run call timed out after {budget:g}s (slot wait included)" if timed_out
               else note or f"heavy-run call ended rc={rc}")
        for step in inner_steps:
            res = recorded.get(step.name)
            if not isinstance(res, dict) or res.get("state") not in (PASS, FAIL, SKIP, CNT):
                res = new_result(step, ctx)
                res["state"] = CNT
                res["reason"] = f"{why} before this step recorded a result"
            results.append(res)
            if step.name not in printed:
                printed.add(step.name)
                print(summary_line(res), flush=True)

    state, code = overall(results)
    status["overall"] = state
    status["ended"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save()
    print(f"overall: {state}  heavy_run: {heavy_run_label(hr)}  status: {status_path}")
    print(last_line(results, source, args.only))
    return code


def last_line(results: list, source: str, only) -> str:
    notes = []
    skipped = [r["name"] for r in results if r["state"] == SKIP]
    if skipped:
        notes.append(f"{len(skipped)} SKIPPED (NOT VERIFIED): {', '.join(skipped)}")
    if source != "builtin":
        notes.append(f"table {source}: not the repo gate")
    if only:
        notes.append("subset (--only): not the repo gate")
    if not notes:
        notes.append(f"all {len(results)} steps of the repo gate ran; none SKIPPED")
    return "; ".join(notes)


def default_out(root: str) -> str:
    head = _git(root, "rev-parse", "--short=12", "HEAD")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = os.path.join(tempfile.gettempdir(), "gate-runner", f"{(head or 'nogit').strip()}-{stamp}")
    out, n = base, 1
    while os.path.exists(out):
        n += 1
        out = f"{base}-{n}"
    return out


# ---- CI drift ---------------------------------------------------------------

_ASSIGN = re.compile(r"""^[A-Za-z_][A-Za-z0-9_]*=("[^"]*"|'[^']*'|\S*)$""")
_SHELL_KEYWORD = re.compile(r"^(if|elif|for|while|until)\s")


def normalise(cmd: str) -> str:
    return " ".join(cmd.split())


def split_commands(run: str) -> list:
    """The commands in a `run:` block. Dropped: blank and comment lines, shell
    control keywords, `echo` lines and bare variable assignments. A check
    hidden inside an `if` condition would be missed; none is today."""
    out = []
    for raw in run.replace("\\\n", " ").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("echo "):
            continue
        if line in ("then", "else", "fi", "do", "done") or _SHELL_KEYWORD.match(line):
            continue
        if _ASSIGN.match(line):
            continue
        out.append(normalise(line))
    return out


def _excluded(workflow: str, cmd: str) -> bool:
    for wf, pattern, _reason in EXCLUDED_CI:
        if wf != workflow:
            continue
        pattern = normalise(pattern)
        if pattern.endswith("*") and cmd.startswith(pattern[:-1]):
            return True
        if cmd == pattern:
            return True
    return False


def ci_drift(root: str, table=TABLE) -> list:
    """Problems, one string each; [] when the table covers PR-path CI."""
    import yaml
    wfdir = os.path.join(root, ".github", "workflows")
    try:
        present = sorted(f for f in os.listdir(wfdir) if f.endswith((".yml", ".yaml")))
    except OSError as exc:
        return [f"cannot read {wfdir}: {exc}"]
    excluded = {f for f, _ in EXCLUDED_WORKFLOWS}
    problems = [f"{f}: workflow is neither in INCLUDED_WORKFLOWS nor EXCLUDED_WORKFLOWS"
                for f in present if f not in INCLUDED_WORKFLOWS and f not in excluded]
    problems += [f"{f}: in INCLUDED_WORKFLOWS but not in .github/workflows/"
                 for f in INCLUDED_WORKFLOWS if f not in present]
    covered = {(wf, normalise(cmd)) for step in table for wf, cmd in step.ci}
    skip_jobs = {(wf, job) for wf, job, _ in EXCLUDED_JOBS}
    for wf in INCLUDED_WORKFLOWS:
        if wf not in present:
            continue
        try:
            with open(os.path.join(wfdir, wf), encoding="utf-8") as fh:
                doc = yaml.safe_load(fh)
        except (OSError, yaml.YAMLError) as exc:
            problems.append(f"{wf}: cannot parse: {exc}")
            continue
        jobs = (doc or {}).get("jobs") or {}
        for job_id, job in jobs.items():
            if (wf, job_id) in skip_jobs or not isinstance(job, dict):
                continue
            for step in job.get("steps") or []:
                run = step.get("run") if isinstance(step, dict) else None
                if not isinstance(run, str):
                    continue
                for cmd in split_commands(run):
                    if (wf, cmd) not in covered and not _excluded(wf, cmd):
                        problems.append(f"{wf} jobs.{job_id}: `{cmd}` is in neither the step "
                                        "table nor EXCLUDED_CI")
    return problems


# ---- main -----------------------------------------------------------------

def parse_args(argv):
    ap = argparse.ArgumentParser(description="Run this repository's whole local gate.")
    ap.add_argument("--root", default=DEFAULT_ROOT, help="repository root (default: this repo)")
    ap.add_argument("--out", help="status/log directory (default $TMPDIR/gate-runner/<sha>-<utc>)")
    ap.add_argument("--list", action="store_true", help="print the step table and exit")
    ap.add_argument("--check-ci", action="store_true", help="check the table against CI and exit")
    ap.add_argument("--skip", action="append", metavar="NAME", help="record NAME as SKIP, do not run it")
    ap.add_argument("--only", action="append", metavar="NAME", help="run only NAME (repeatable)")
    ap.add_argument("--table", help="a JSON step table instead of the built-in one (tests, ad-hoc)")
    ap.add_argument("--grace", type=float, default=30.0, help="seconds between SIGTERM and SIGKILL")
    ap.add_argument("--heavy-timeout", type=float, default=None,
                    help="seconds for the whole heavy-run call (default: from the step timeouts)")
    ap.add_argument("--inner", metavar="PART_JSON", help=argparse.SUPPRESS)
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        steps, source = load_table(args.table)
        names = {s.name for s in steps}
        unknown = sorted(set(args.skip or ()) - names) + sorted(set(args.only or ()) - names)
        if unknown:
            raise Refusal(f"unknown step name(s): {', '.join(unknown)} (see --list)")
        if args.only:
            steps = [s for s in steps if s.name in set(args.only)]
        if args.list:
            print_list(steps)
            return EXIT_PASS
        if args.check_ci:
            try:
                import yaml  # noqa: F401  pylint: disable=unused-import
            except ImportError:
                print("gate-runner --check-ci: pyyaml not importable; NOT VERIFIED")
                return EXIT_SKIP
            problems = ci_drift(os.path.abspath(args.root), steps)
            for problem in problems:
                print(f"DRIFT {problem}")
            print(f"gate-runner --check-ci: {len(problems)} problem(s)")
            return EXIT_FAIL if problems else EXIT_PASS
        root = os.path.abspath(args.root)
        install_signal_handlers()
        if args.inner:
            ctx = Context(root, os.path.abspath(args.out), args.grace, set(args.skip or ()))
            return run_inner(args.inner, [s for s in steps if s.phase != "cheap"], ctx)
        mode, path = resolve_heavy_run(os.environ)
    except Refusal as exc:
        print(f"gate-runner: {exc}", file=sys.stderr)
        return EXIT_USAGE
    out = os.path.abspath(args.out) if args.out else default_out(root)
    ctx = Context(root, out, args.grace, set(args.skip or ()))
    hr = {"mode": mode, "path": path, "launched": False, "rc": None, "waited_seconds": None,
          "note": "uncapped" if mode == "absent" else None}
    return run_outer(args, steps, source, ctx, hr)


if __name__ == "__main__":
    sys.exit(main())
