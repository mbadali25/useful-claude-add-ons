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
(--grace, default 30 s) that lasts until the whole GROUP is gone, not just its
leader, then SIGKILL. A heavy-run call that dies leaves every heavy/solo step
it had not recorded COULD-NOT-TELL, and a heavy-part.json result is taken only
for a table step, under its own name, with a state its rc could give (PASS
needs rc 0, SKIP rc 77 or null) -- anything else is COULD-NOT-TELL. The inner
runner refuses (exit 2, no step run) unless the table it loads has the digest
the outer runner validated (--table-digest), so a table or runner file edited
by a cheap step never runs.

Overall and exit: any FAIL = FAIL, exit 1; else any COULD-NOT-TELL, or no step
PASSED at all = COULD-NOT-TELL, exit 3; else PASS, exit 0. Usage error or
refusal = exit 2. The last stdout line counts every SKIP and says when the
table or the step set is not the repo gate (--table, --only).

Status: one JSON file, <out>/status.json, default out
$TMPDIR/gate-runner/<shortsha>-<utc>/ (claimed with mkdir, so two runs in one
second get two directories), rewritten (temp file + os.replace) after every
step -- a heavy step's result is copied in from heavy-part.json as soon as the
inner runner records it, not when the heavy-run call ends; per-step logs
under <out>/logs/. --skip records SKIP before anything about the step is built
or probed.

A --table step is refused (exit 2) unless its name matches _NAME and is not
reserved (it becomes a log path), its keys are known, every field has its
type, a heavy step's group is A or B and any other step has none, and its cwd
resolves inside --root. The cwd is resolved again when the step launches (an
earlier step may have swapped it for a symlink); outside --root then is
COULD-NOT-TELL. On Linux the checked directory is opened, the opened directory
is checked again, and the child starts in it through /proc/self/fd, so a later
swap of the pathname cannot redirect it; elsewhere (no /proc/self/fd) the
child gets the resolved path and a swap in between is not prevented. A tool
named in `needs` is run by its absolute path.

The table is derived from .github/workflows/; `--check-ci` (and
scripts/_test/gate-runner.py) fails when a workflow `run:` command is in
neither the table nor EXCLUDED_CI, or a workflow file is unclassified. Each
`run:` line is split into simple commands (on ; && || |, quote-aware), so a
check chained onto an install or inside a one-line if/while/for still counts.
No job is excluded whole; a step is excluded only by a WINDOWS_ONLY_IFS
condition. The check is one-way: table steps CI does not run (sabotage.py,
ruff-no-new, check-tooling-pr) are allowed.

Windows: the kill path uses CREATE_NEW_PROCESS_GROUP and `taskkill /T`. Not
verified on a Windows host.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
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
# The wait after the final SIGKILL is a wait too: a child stuck in uninterruptible
# I/O may never be reaped, and the step is then COULD-NOT-TELL, not a hang.
KILL_REAP_SECONDS = 10


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
    # crew-shell-matrix's ubuntu leg: the full bash/pwsh hook matrix, which
    # plugin/crew/tests/conftest.py deselects from every run not naming `slow`.
    # 201.8s under heavy-run, 1690 passed / 22 skipped (2026-10-01).
    Step("pytest-crew-slow", "heavy",
         (PY, "-m", "pytest", "plugin/crew/tests/", "-m", "slow", "-n", "4", *NO_CACHE),
         group="A", timeout=900, pytest=True,
         ci=(("pytest-crew.yml", "python -m pytest plugin/crew/tests -m slow -n auto -v"),)),

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
    ("runner-autostart.yml", "dispatches a start of the self-hosted runner host; checks nothing"),
)
# A step is excluded by its `if:` only when that condition confines it to a
# leg this runner does not have. Whole jobs are never excluded: a job's legs
# change (crew-shell-matrix is ubuntu-only today) and its other steps still run.
WINDOWS_ONLY_IFS = (
    ("matrix.os == 'windows-latest'", "runs only on the Windows leg; this runner has none"),
    ("env.RUN_LEG == 'true' && matrix.os == 'windows-latest'",
     "runs only on the Windows leg (behind T-0110's RUN_LEG decision); this runner has none"),
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
    ("pytest-crew.yml",
     "changed=$(git diff --name-only HEAD^1 HEAD -- plugin/crew .github/workflows/pytest-crew.yml)",
     "decides whether crew-shell-matrix's Windows leg runs on a PR (T-0110); checks nothing"),
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
        try:
            subprocess.run(cmd, capture_output=True, check=False, stdin=subprocess.DEVNULL,
                           timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            pass
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


def _group_alive(proc: subprocess.Popen) -> bool:
    """Whether any process of the step's group is still there. POSIX asks the
    group itself (signal 0), so a grandchild that outlived its leader counts;
    Windows has no group probe and falls back to the leader."""
    if os.name == "nt":
        return proc.poll() is None
    try:
        os.killpg(proc.pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _kill_group(proc: subprocess.Popen, grace: float) -> bool:
    """SIGTERM the whole group and give the WHOLE group `grace` to exit -- not
    just the leader, so a grandchild still cleaning up is not SIGKILLed the
    moment its leader is gone; SIGKILL whatever is left, then sweep once more.
    True when the leader was reaped; False when it was still there
    KILL_REAP_SECONDS after SIGKILL (the caller records COULD-NOT-TELL)."""
    _signal_group(proc, hard=False)
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if proc.poll() is not None and not _group_alive(proc):
            return True
        time.sleep(0.1)
    _signal_group(proc, hard=True)
    reaped = True
    try:
        proc.wait(timeout=KILL_REAP_SECONDS)
    except subprocess.TimeoutExpired:
        reaped = False
    _signal_group(proc, hard=True)
    return reaped


def _not_reaped(what: str) -> str:
    return (f"{what}; process group sent SIGKILL and did not exit within "
            f"{KILL_REAP_SECONDS:g}s")


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
            stopped_at = killed_at = None
            while True:
                try:
                    return proc.wait(timeout=0.5), False, True, ""
                except subprocess.TimeoutExpired:
                    pass
                if on_tick is not None:
                    try:
                        on_tick()
                    # Any fault in the caller's merge must not orphan the group: the
                    # recovery is to kill it and say so (the caller marks COULD-NOT-TELL).
                    except Exception as exc:  # pylint: disable=broad-exception-caught
                        what = f"status merge failed ({exc!r})"
                        if not _kill_group(proc, grace):
                            return None, False, True, _not_reaped(what)
                        return None, False, True, f"{what}; process group killed"
                now = time.monotonic()
                if STOP.is_set():
                    if stopped_at is None:
                        stopped_at = now
                        _signal_group(proc, hard=False)
                    elif killed_at is None and now - stopped_at > grace:
                        killed_at = now
                        _signal_group(proc, hard=True)
                    elif killed_at is not None and now - killed_at > KILL_REAP_SECONDS:
                        return None, False, True, _not_reaped("runner stopped by a signal")
                if now >= deadline:
                    what = f"timed out after {timeout:g}s"
                    if not _kill_group(proc, grace):
                        return None, True, True, _not_reaped(what)
                    return (proc.returncode, True, True,
                            f"{what}; process group killed (SIGTERM, {grace:g}s grace, SIGKILL)")
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

# A step name becomes <out>/logs/<name>.log, so it may not carry a path
# separator, start with a dot, or be the outer heavy-run call's own log name.
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
RESERVED_NAMES = ("heavy-run",)
TABLE_KEYS = frozenset(("name", "phase", "group", "argv", "cwd", "timeout", "needs", "pytest"))


def positive_finite(value) -> bool:
    """A JSON or CLI number usable as a duration: not bool, finite, > 0
    (json.load accepts NaN and Infinity, and 1e999 parses as inf)."""
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and value > 0)


def contained_cwd(root: str, cwd: str) -> str | None:
    """The real path (symlinks resolved) of a repository-relative step cwd, or
    None when cwd is absolute or that real path is outside the root's."""
    if os.path.isabs(cwd) or os.path.splitdrive(cwd)[0]:
        return None
    real_root = os.path.realpath(root)
    real = os.path.realpath(os.path.join(real_root, cwd))
    return real if _inside(real_root, real) else None


def _inside(real_root: str, real: str) -> bool:
    try:
        return os.path.commonpath([real_root, real]) == real_root
    except ValueError:  # different drives on Windows
        return False


def cwd_in_root(root: str, cwd: str) -> bool:
    return contained_cwd(root, cwd) is not None


def load_table(path: str | None, root: str = DEFAULT_ROOT):
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
        if not _NAME.match(name) or name in RESERVED_NAMES:
            raise Refusal(f"--table step {i}: name {name!r} must match {_NAME.pattern} and not be "
                          f"one of {RESERVED_NAMES} (it becomes <out>/logs/<name>.log)")
        unknown = sorted(set(item) - TABLE_KEYS)
        if unknown:
            raise Refusal(f"--table step {name}: unknown key(s) {', '.join(unknown)}")
        if phase not in PHASES:
            raise Refusal(f"--table step {name}: phase must be one of {PHASES}")
        if (group not in ("A", "B")) if phase == "heavy" else (group is not None):
            raise Refusal(f"--table step {name}: heavy steps need group A or B; cheap and solo "
                          "steps take no group (absent or null)")
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
            raise Refusal(f"--table step {name}: argv must be a non-empty list of strings")
        timeout = item.get("timeout", 300)
        if not positive_finite(timeout):
            raise Refusal(f"--table step {name}: timeout must be a finite positive number")
        cwd, needs, pytest = item.get("cwd", "."), item.get("needs", []), item.get("pytest", False)
        if not isinstance(cwd, str) or not cwd:
            raise Refusal(f"--table step {name}: cwd must be a non-empty string")
        if not cwd_in_root(root, cwd):
            raise Refusal(f"--table step {name}: cwd {cwd!r} must be a directory inside --root "
                          "(relative, symlinks resolved)")
        if not isinstance(needs, list) or not all(isinstance(n, str) and n for n in needs):
            raise Refusal(f"--table step {name}: needs must be a list of non-empty strings")
        if not isinstance(pytest, bool):
            raise Refusal(f"--table step {name}: pytest must be true or false")
        seen.add(name)
        steps.append(Step(name, phase, tuple(argv), group=group, cwd=cwd, timeout=timeout,
                          needs=tuple(needs), pytest=pytest))
    return steps, src


def table_digest(steps: list) -> str:
    """sha256 over every field of every step of a loaded table (built-in or
    --table alike), so the inner runner can prove it loaded the table the
    outer runner validated."""
    text = json.dumps([dataclasses.asdict(s) for s in steps], sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
    """The tool's absolute path: shutil.which resolves a relative PATH entry
    against this process's cwd, and the step runs in another one."""
    found = shutil.which(tool)
    if found is None and tool == "pwsh" and os.path.exists(WINDOWS_PWSH):
        found = WINDOWS_PWSH
    return os.path.abspath(found) if found else None


def _git_py_files(root: str) -> list:
    try:
        proc = subprocess.run(["git", "ls-files", "-z", "*.py"], cwd=root, capture_output=True,
                              timeout=60, check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CannotStart(f"git ls-files failed: {exc}") from exc
    if proc.returncode != 0:
        raise CannotStart(f"git ls-files exit {proc.returncode}: "
                          f"{proc.stderr.decode(errors='replace').strip()}")
    # fsdecode: surrogateescape on POSIX, so a name that is not UTF-8 reaches the
    # child as its original bytes instead of raising here.
    return [os.fsdecode(p) for p in proc.stdout.split(b"\0") if p]


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


def _open_cwd(root: str, cwd: str):
    """(fd, path to start the child in) for a step cwd inside the root, or None.
    With /proc/self/fd (Linux) the checked directory is opened and the OPENED
    directory is checked again; the child starts in /proc/self/fd/<fd>, which it
    resolves through its own inherited copy of fd before exec (fd stays
    close-on-exec, so the step never holds it), so a swap of the pathname after
    this check cannot redirect it. Elsewhere fd is None and the path is the
    resolved one (a swap in between is not prevented there)."""
    real = contained_cwd(root, cwd)
    if real is None:
        return None
    if os.name == "nt" or not os.path.isdir("/proc/self/fd"):
        return None, real
    try:
        fd = os.open(real, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return None
    if not _inside(os.path.realpath(root), os.path.realpath(f"/proc/self/fd/{fd}")):
        os.close(fd)
        return None
    return fd, f"/proc/self/fd/{fd}"


def new_result(step: Step, ctx: Context) -> dict:
    return {"name": step.name, "phase": step.phase, "group": step.group, "argv": list(step.argv),
            "cwd": step.cwd, "timeout": step.timeout, "rc": None, "state": None, "reason": "",
            "seconds": 0.0, "log": os.path.join(ctx.out, "logs", f"{step.name}.log")}


def run_step(step: Step, ctx: Context) -> dict:
    res = new_result(step, ctx)
    if step.name in ctx.skip:  # before argv is built: a skipped step probes nothing
        res["state"], res["reason"] = SKIP, "skipped by --skip"
        return res
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
    # Resolved again at launch, not only when the table loaded: an earlier step
    # may have swapped a directory on this path for a symlink out of the root.
    # On Linux the child starts in the directory that was checked (_open_cwd).
    opened = _open_cwd(ctx.root, step.cwd)
    if opened is None:
        res["state"] = CNT
        res["reason"] = (f"could not start: cwd {step.cwd!r} resolves outside --root at launch "
                         "(symlinks resolved) or could not be opened")
        return res
    fd, cwd = opened
    started_at = time.monotonic()
    try:
        rc, timed_out, started, note = spawn_and_wait(argv, cwd, res["log"], step.timeout,
                                                      ctx.grace)
    finally:
        if fd is not None:
            os.close(fd)
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

RESULT_KEYS = ("name", "rc", "state", "reason", "seconds", "log")


def _valid_result(name: str, res) -> bool:
    """A heavy-part result is taken only when it is filed under its own name,
    its rc is an int or null (never a bool or a string), and its state is one
    the inner runner's classify() could give that rc: PASS needs rc 0, FAIL a
    non-zero rc, SKIP rc 77 or null (--skip, a missing tool) -- a PASS without
    the exit status that proves it, or a SKIP over a failed exit, is never
    taken (T-0082). COULD-NOT-TELL takes any rc: it never passes. Anything
    else is dropped, and the step reads COULD-NOT-TELL."""
    if not isinstance(res, dict) or not all(k in res for k in RESULT_KEYS):
        return False
    rc, state = res["rc"], res["state"]
    if res["name"] != name or state not in (PASS, FAIL, SKIP, CNT):
        return False
    if rc is not None and (isinstance(rc, bool) or not isinstance(rc, int)):
        return False
    if state == PASS:
        return rc == 0
    if state == FAIL:
        return rc is not None and rc != 0
    if state == SKIP:
        return rc is None or rc == EXIT_SKIP
    return True


def _part(got):
    """(steps, started) from heavy-part.json as read: only well-formed step
    results, and `started` only when a finite non-bool number. A document of
    any other shape gives ({}, None), never an exception."""
    if not isinstance(got, dict):
        return {}, None
    steps = got.get("steps")
    steps = {n: r for n, r in steps.items() if isinstance(n, str) and _valid_result(n, r)} \
        if isinstance(steps, dict) else {}
    started = got.get("started")
    if isinstance(started, bool) or not isinstance(started, (int, float)) \
            or not math.isfinite(started):
        started = None
    return steps, started


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
        proc = subprocess.run(["git", *args], cwd=root, capture_output=True, timeout=60,
                              check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    # surrogateescape cannot raise: a file name that is not UTF-8 in
    # `status --porcelain` must not crash the runner before status.json exists.
    return proc.stdout.decode("utf-8", "surrogateescape") if proc.returncode == 0 else None


def heavy_run_label(hr: dict) -> str:
    return hr["path"] if hr["mode"] == "present" else "absent (uncapped)"


def heavy_budget(steps: list, grace: float) -> float:
    a = sum(s.timeout for s in steps if s.group == "A")
    b = sum(s.timeout for s in steps if s.group == "B")
    solo = sum(s.timeout for s in steps if s.phase == "solo")
    return max(a, b) + solo + grace * (len(steps) + 2) + SLOT_WAIT_ALLOWANCE


def _log_tail(path: str) -> str:
    """The last non-empty line of a log, for a reason string ('' if none)."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - 4096))
            lines = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return ""
    lines = [ln.strip() for ln in lines if ln.strip()]
    return lines[-1][:300] if lines else ""


def run_outer(args, steps: list, source: str, ctx: Context, hr: dict, digest: str) -> int:
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
               "--out", ctx.out, "--grace", f"{ctx.grace:g}", "--table-digest", digest]
        if source != "builtin":
            cmd += ["--table", source]
        for name in args.skip or ():
            cmd += ["--skip", name]
        for name in args.only or ():
            cmd += ["--only", name]
        if hr["mode"] == "present":
            cmd = [hr["path"], *cmd]
        printed: set = set()
        wanted = {s.name for s in inner_steps}  # a result for any other name is never taken
        slot: dict = {}  # step name -> its index in results, once recorded

        def take(name: str, res: dict) -> None:
            if name in slot:
                results[slot[name]] = res
            else:
                slot[name] = len(results)
                results.append(res)

        def tick() -> None:
            # Copy each heavy result into status.json as soon as heavy-part.json
            # has it, so an outer runner killed mid-call loses none of them.
            fresh = [(n, r) for n, r in _part(read_json(part))[0].items()
                     if n in wanted and n not in printed]
            for name, res in fresh:
                printed.add(name)
                take(name, res)
                print(summary_line(res), flush=True)
            if fresh:
                save()

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
        recorded, inner_started = _part(read_json(part))
        if inner_started is not None:
            hr["waited_seconds"] = round(inner_started - launched, 1)
        why = (f"heavy-run call timed out after {budget:g}s (slot wait included)" if timed_out
               else note or f"heavy-run call ended rc={rc}")
        if rc == EXIT_USAGE and not timed_out and not note:
            # The inner runner refused (e.g. the table changed): say why.
            tail = _log_tail(os.path.join(ctx.out, "logs", "heavy-run.log"))
            if tail:
                why = f"{why} ({tail})"
        for step in inner_steps:
            res = recorded.get(step.name)
            if res is None:
                res = new_result(step, ctx)
                res["state"] = CNT
                res["reason"] = f"{why} before this step recorded a result"
            take(step.name, res)
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
    os.makedirs(os.path.dirname(base), exist_ok=True)
    out, n = base, 1
    while True:  # mkdir is the claim: two runs in one second never share a directory
        try:
            os.mkdir(out)
            return out
        except FileExistsError:
            n += 1
            out = f"{base}-{n}"


# ---- CI drift ---------------------------------------------------------------

_ASSIGN = re.compile(r"""^[A-Za-z_][A-Za-z0-9_]*=("[^"]*"|'[^']*'|\S*)$""")
_LEAD_KEYWORDS = ("if", "elif", "then", "else", "while", "until", "do", "!")
_END_KEYWORDS = ("fi", "done")
_NO_OPS = (":", "true", "false")


def normalise(cmd: str) -> str:
    return " ".join(cmd.split())


def _split_simple(line: str) -> list:
    """Split one shell line on `;`, `&&`, `||` and `|` outside quotes and
    outside `$(...)`, keeping each part's original text."""
    parts, buf, quote, depth, i = [], [], None, 0, 0
    while i < len(line):
        ch, two = line[i], line[i:i + 2]
        if quote:
            if ch == "\\" and quote == '"':
                buf.append(line[i:i + 2])
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif two == "$(":
            depth += 1
            buf.append(two)
            i += 2
            continue
        elif ch == ")" and depth:
            depth -= 1
        elif depth == 0 and two in ("&&", "||"):
            parts.append("".join(buf))
            buf = []
            i += 2
            continue
        elif depth == 0 and ch in (";", "|"):
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts


def _simple_command(part: str):
    """The command a split part runs, or None for shell syntax that runs no
    check: keywords alone, `[ ... ]`/`test` conditions, no-ops, `for` headers,
    `echo`, bare assignments."""
    words = part.split()
    while words and words[0] in _LEAD_KEYWORDS:
        words = words[1:]
    if not words or words[0] in _END_KEYWORDS or words[0] in _NO_OPS or words[0] == "for":
        return None
    if words[0] in ("[", "[[", "test", "echo", "exit"):
        return None
    cmd = " ".join(words)
    return None if _ASSIGN.match(cmd) else cmd


def _close(text: str, i: int) -> int:
    """Index just past the `)` that closes the `(` before i: quote-aware and
    nesting-aware; len(text) when unclosed."""
    depth, quote = 1, None
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\" and quote == '"':
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "\\":
            i += 2
            continue
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(text)


def substitutions(text: str) -> list:
    """The bodies of every command substitution in `text` that the shell would
    run: `$(...)`, backticks, `<(...)` and `>(...)`, outside single quotes
    (inside double quotes they still run). `$((...))` is arithmetic, not a
    command; substitutions inside it are still returned. Nested bodies are
    returned whole; split_commands recurses into them."""
    out, quote, i = [], None, 0
    while i < len(text):
        ch, two = text[i], text[i:i + 2]
        if quote == "'":
            if ch == "'":
                quote = None
            i += 1
            continue
        if ch == "\\":
            i += 2
            continue
        if ch == '"':
            quote = None if quote == '"' else '"'
            i += 1
            continue
        if quote is None and ch == "'":
            quote = "'"
            i += 1
            continue
        if text[i:i + 3] == "$((":
            end = _close(text, i + 2)
            out += substitutions(text[i + 3:end - 1])
            i = end
            continue
        if two in ("$(", "<(", ">("):
            end = _close(text, i + 2)
            out.append(text[i + 2:end - 1])
            i = end
            continue
        if ch == "`":
            end = text.find("`", i + 1)
            end = len(text) if end < 0 else end
            out.append(text[i + 1:end])
            i = end + 1
            continue
        i += 1
    return out


def split_commands(run: str) -> list:
    """Every simple command in a `run:` block. A line is split on `;`, `&&`,
    `||` and `|` (quote- and `$(...)`-aware), so a check chained onto an
    install, an echo or a condition, or written as a one-line `if`/`while`/
    `for` body, is still a command. Dropped: blank and comment lines, shell
    keywords, `[ ]`/`test` conditions, no-ops, `echo`, `exit` and bare
    variable assignments -- but a dropped part is first searched for command
    substitutions (`$(...)`, backticks, `<(...)`), and each body is split the
    same way, so `echo "$(python3 x.py)"` still counts `python3 x.py`."""
    out = []
    for raw in run.replace("\\\n", " ").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        for part in _split_simple(line):
            cmd = _simple_command(part)
            if cmd is not None:
                out.append(normalise(cmd))
                continue
            for body in substitutions(part):
                out += split_commands(body)
    return out


def _excluded(workflow: str, cmd: str) -> bool:
    """A wildcard covers one simple command only: its tail may not run another
    command through any substitution -- `$(...)`, backticks, `<(...)` or
    `>(...)` (substitutions() is the one definition of what runs)."""
    for wf, pattern, _reason in EXCLUDED_CI:
        if wf != workflow:
            continue
        pattern = normalise(pattern)
        if pattern.endswith("*") and cmd.startswith(pattern[:-1]):
            tail = cmd[len(pattern) - 1:]
            if not substitutions(tail):
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
    windows_only = {cond for cond, _ in WINDOWS_ONLY_IFS}
    for wf in INCLUDED_WORKFLOWS:
        if wf not in present:
            continue
        try:
            with open(os.path.join(wfdir, wf), encoding="utf-8") as fh:
                doc = yaml.safe_load(fh)
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            problems.append(f"{wf}: cannot parse: {exc}")
            continue
        problems += _workflow_commands(wf, doc, covered, windows_only)
    return problems


def _workflow_commands(wf: str, doc, covered: set, windows_only: set) -> list:
    """Drift problems for one parsed workflow. Valid YAML of the wrong shape at
    any level (no `jobs` mapping, a job, `steps`, a step or a `run` of the
    wrong type) is itself a problem naming where: the check never reads a
    workflow it cannot walk as "nothing to check", and never raises."""
    if not isinstance(doc, dict) or not isinstance(doc.get("jobs"), dict):
        return [f"{wf}: cannot check: the document has no `jobs` mapping"]
    problems = []
    for job_id, job in doc["jobs"].items():
        if not isinstance(job, dict):
            problems.append(f"{wf} jobs.{job_id}: cannot check: the job is not a mapping")
            continue
        steps = job.get("steps")
        if steps is None:  # a reusable-workflow call (`uses:`) has no steps
            continue
        if not isinstance(steps, list):
            problems.append(f"{wf} jobs.{job_id}: cannot check: `steps` is not a list")
            continue
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                problems.append(f"{wf} jobs.{job_id}.steps[{i}]: cannot check: not a mapping")
                continue
            run = step.get("run")
            if run is None or normalise(str(step.get("if", ""))) in windows_only:
                continue
            if not isinstance(run, str):
                problems.append(f"{wf} jobs.{job_id}.steps[{i}]: cannot check: `run` is not text")
                continue
            for cmd in split_commands(run):
                if (wf, cmd) not in covered and not _excluded(wf, cmd):
                    problems.append(f"{wf} jobs.{job_id}: `{cmd}` is in neither the step "
                                    "table nor EXCLUDED_CI")
    return problems


# ---- main -----------------------------------------------------------------

def _duration(text: str) -> float:
    try:
        value = float(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{text!r} is not a number") from exc
    if not positive_finite(value):
        raise argparse.ArgumentTypeError(f"{text!r} must be a finite number > 0")
    return value


def parse_args(argv):
    ap = argparse.ArgumentParser(description="Run this repository's whole local gate.")
    ap.add_argument("--root", default=DEFAULT_ROOT, help="repository root (default: this repo)")
    ap.add_argument("--out", help="status/log directory (default $TMPDIR/gate-runner/<sha>-<utc>)")
    ap.add_argument("--list", action="store_true", help="print the step table and exit")
    ap.add_argument("--check-ci", action="store_true", help="check the table against CI and exit")
    ap.add_argument("--skip", action="append", metavar="NAME", help="record NAME as SKIP, do not run it")
    ap.add_argument("--only", action="append", metavar="NAME", help="run only NAME (repeatable)")
    ap.add_argument("--table", help="a JSON step table instead of the built-in one (tests, ad-hoc)")
    ap.add_argument("--grace", type=_duration, default=30.0, help="seconds between SIGTERM and SIGKILL")
    ap.add_argument("--heavy-timeout", type=_duration, default=None,
                    help="seconds for the whole heavy-run call (default: from the step timeouts)")
    ap.add_argument("--inner", metavar="PART_JSON", help=argparse.SUPPRESS)
    ap.add_argument("--table-digest", help=argparse.SUPPRESS)
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        steps, source = load_table(args.table, os.path.abspath(args.root))
        digest = table_digest(steps)  # the full table, before --only
        if args.inner and args.table_digest != digest:
            raise Refusal("--inner: table changed since the outer runner validated it "
                          f"(outer {args.table_digest or 'none given'}, inner {digest})"
                          if args.table_digest else
                          "--inner needs --table-digest (no unchecked table is run)")
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
    return run_outer(args, steps, source, ctx, hr, digest)


if __name__ == "__main__":
    sys.exit(main())
