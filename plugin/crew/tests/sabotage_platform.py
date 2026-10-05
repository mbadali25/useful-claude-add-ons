"""Platform declarations, the per-entry runner and the verdicts for
`sabotage.py` (L-0608).

pytest exits 0 for a run whose every test SKIPPED, the same code it gives a
run that PASSED, so a verdict read from the exit code alone called a test that
never ran "STILL GREEN" - thirteen entries on Linux, ten of them Windows-only
by design. And it exits 1 for a fixture error, or for a failure beside cases
that never ran, which is no proof the named test caught the mutation. Each
entry therefore runs with a `--junitxml` report and this module's collection
plugin, and is judged from what the report says ran:

- `RED (good)`: exit 1, every collected case reported, at least one FAILED,
  none skipped or errored.
- `RED BUT UNPROVEN`: any other non-zero exit, or exit 1 with an error, a
  skipped case or an unreported collected case beside the failure.
- `STILL GREEN`: exit 0 and at least one case PASSED.
- `COULD-NOT-TELL`: exit 0 with every case skipped (or none), no readable
  report, or the per-entry timeout overran (the whole process tree is killed).

An entry only some platforms can exercise is declared in `PLATFORM_ONLY`; on
any other host it is never applied, and the summary counts it - so it reads as
"not exercised here", never as green and never as silence. On its own
platform a skip is COULD-NOT-TELL like any other.
"""

import ctypes
import os
import signal
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

import sabotage_bound

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HERE = os.path.dirname(os.path.abspath(__file__))
_COLLECTED_ENV = "SABOTAGE_COLLECTED_FILE"
# Windows needs a job object to reach a grandchild once pytest has exited
# (taskkill /T walks only a live tree); without one an entry is COULD-NOT-TELL.
_NEEDS_JOB = os.name == "nt"
# The entry running right now, as (proc, job). It is in its own session or job,
# so a signal sent to sabotage.py's process group no longer reaches it:
# sabotage.py's signal handler calls kill_current() before it restores.
_CURRENT = []

_WIN = frozenset({"win"})
_LINUX = frozenset({"linux"})
_WIN_WHY = ("its target test is the native-Windows .ps1 flavour (skipif off "
            "Windows; the hook exits 0 off Windows_NT)")
_ZERO_WHY = ("the mutation reads /dev/zero unbounded; only Linux bounds the "
             "hook child (RLIMIT_AS in _run_bounded)")

# label -> (platforms that can exercise it, why). Every label must name exactly
# one entry of sabotage.MUTATIONS (test_sabotage_harness.py asserts it).
PLATFORM_ONLY = {
    "promote-gate.ps1 reads an unreadable map as one that gates nothing":
        (_WIN, _WIN_WHY),
    "the PowerShell gate stops rejecting a `run` entry it cannot represent":
        (_WIN, _WIN_WHY),
    "the PowerShell Stop budget charges each command the rule's cost":
        (_WIN, _WIN_WHY),
    "the PowerShell deadline read overflows Int32 again": (_WIN, _WIN_WHY),
    "the bash gate stops publishing a deadline at all":
        (_WIN, "its target is the cross-flavour case, which needs both gates "
               "on one Windows host; the bash-only twin below runs on Linux"),
    "the PowerShell gate stops publishing a deadline at all": (_WIN, _WIN_WHY),
    "the PowerShell budget lets a priced rule defer an `always` command":
        (_WIN, _WIN_WHY),
    "the PowerShell gate stops making an unpriced rule unconditional":
        (_WIN, _WIN_WHY),
    "the PowerShell gate charges a mandatory command twice": (_WIN, _WIN_WHY),
    "the PowerShell gate hoists a mandatory command out of its rule":
        (_WIN, _WIN_WHY),
    "the PowerShell gate lets a dearer measurement replace a declared price":
        (_WIN, _WIN_WHY),
    "the PowerShell gate charges a rule that passed on this exact tree":
        (_WIN, _WIN_WHY),
    "the PowerShell gate saves the tree-pass cache after the tree moved":
        (_WIN, _WIN_WHY),
    "the PowerShell gate credits from the tree-pass cache under -All":
        (_WIN, _WIN_WHY),
    "the PowerShell gate keeps a credit after the tree moved": (_WIN, _WIN_WHY),
    "the PowerShell gate keeps a withdrawn credit in the record sync":
        (_WIN, _WIN_WHY),
    "Get-CrewChildTabRecheck skips the post-delay tab check again":
        (_WIN, "System.Windows.Forms/UIAutomation exist only on Windows; the "
               "(Linux structural) twin covers the same mutation elsewhere"),
    "cloud guard r1: a FIFO or device is opened as a plan": (_LINUX, _ZERO_WHY),
    "cloud guard r1: azureProfile.json opened whatever it is":
        (_LINUX, _ZERO_WHY),
    "the bash gate stops publishing a deadline at all (bash only)":
        (_LINUX, "its target's rule runs GNU `stat -c %Y`, which macOS's stat "
                 "does not take"),
}

_VERIFY_SH = os.path.join(CREW, "hooks", "scripts", "verify-gate.sh")

# The bash half of the deadline-publication mutation, aimed at a bash-only
# test so it can go red on a host without the PowerShell gate. Same find and
# replace as its cross-flavour entry in sabotage.py.
PLATFORM_MUTATIONS = (
    ("the bash gate stops publishing a deadline at all (bash only)",
     _VERIFY_SH,
     "lock_extend() {\n"
     "  [ \"$UNLOCKED\" -eq 0 ] || return 0\n"
     "  [ \"$(cat \"$LOCK/token\" 2>/dev/null)\" = "
     "\"${LOCK_TOKEN:-}\" ] || return 0\n"
     "  printf '%s\\n' \"$(( $(date +%s) + $(lock_window) ))\" > "
     "\"$LOCK/deadline\" 2>/dev/null || true\n"
     "}\n",
     "lock_extend() {\n  return 0\n}\n",
     "tests/test_verify_gate_lock_window.py::"
     "test_the_deadline_is_republished_during_a_run_not_only_once[sh]"),
    # Review of ee01a3ca: the entry leaves the registry before its tree is
    # killed, so a signal in between finds nothing to kill.
    ("an entry is unregistered before its tree is killed",
     os.path.join(_HERE, "sabotage_platform.py"),
     "        try:\n            _kill_tree(proc, job)\n        finally:\n"
     "            if _CURRENT:\n                _CURRENT.pop()\n",
     "        if _CURRENT:\n            _CURRENT.pop()\n        _kill_tree(proc, job)\n",
     "tests/test_sabotage_harness.py::"
     "test_an_entry_stays_registered_until_its_tree_is_killed"),
    # Review of d0b7fd8e (L-0608 port), FIX: an entry no job object held on
    # Windows gets a verdict although a grandchild may have outlived it.
    ("an entry no job object held still gets a verdict",
     os.path.join(_HERE, "sabotage_platform.py"),
     '    if report.get("uncontained"):\n',
     "    if False:\n",
     "tests/test_sabotage_harness.py::"
     "test_an_entry_no_job_object_could_hold_is_could_not_tell"),
)


def host_platform():
    """`win`, `darwin` or `linux` (any other value is `sys.platform`)."""
    if sys.platform.startswith("win"):
        return "win"
    if sys.platform.startswith("linux"):
        return "linux"
    return sys.platform


def not_exercised_here(label, host=None):
    """The platforms `label` is declared for, when `host` is not one of them;
    None when the entry runs here."""
    declared = PLATFORM_ONLY.get(label)
    if declared is None or (host or host_platform()) in declared[0]:
        return None
    return declared[0]


def pytest_collection_finish(session):
    """Collection plugin (`-p sabotage_platform`): writes every collected
    case's name, so a report missing one cannot read as a complete run."""
    path = os.environ.get(_COLLECTED_ENV)
    if path:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("".join(item.name + "\n" for item in session.items))


def read_collected(path):
    """The case names the plugin wrote, or None when it wrote nothing."""
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return None
    return [line for line in text.splitlines() if line] if text else None


def junit_outcome(path):
    """`{"names", "passed", "failed", "errored", "skipped", "skip_reason"}`
    from a `--junitxml` report, or None when there is no readable report."""
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return None
    out = {"names": [], "passed": 0, "failed": 0, "errored": 0, "skipped": 0,
           "skip_reason": ""}
    for case in root.iter("testcase"):
        out["names"].append(case.get("name", ""))
        if case.find("error") is not None:
            out["errored"] += 1
        elif case.find("failure") is not None:
            out["failed"] += 1
        elif case.find("skipped") is not None:
            out["skipped"] += 1
            if not out["skip_reason"]:
                skipped = case.find("skipped")
                out["skip_reason"] = (skipped.get("message") or skipped.text
                                      or "").strip()
        else:
            out["passed"] += 1
    return out


def _new_job(proc):
    """A Windows Job Object holding `proc`, closed with KILL_ON_JOB_CLOSE, so a
    grandchild is reachable after its parent exits. None off Windows or when
    the job cannot be made (the tree kill then falls back to taskkill)."""
    if os.name != "nt":
        return None

    class _Basic(ctypes.Structure):  # pylint: disable=too-few-public-methods
        _fields_ = [("a", ctypes.c_int64), ("b", ctypes.c_int64),
                    ("LimitFlags", ctypes.c_uint32),
                    ("c", ctypes.c_size_t), ("d", ctypes.c_size_t),
                    ("e", ctypes.c_uint32), ("f", ctypes.c_size_t),
                    ("g", ctypes.c_uint32), ("h", ctypes.c_uint32)]

    class _Extended(ctypes.Structure):  # pylint: disable=too-few-public-methods
        _fields_ = [("Basic", _Basic), ("Io", ctypes.c_uint64 * 6),
                    ("m", ctypes.c_size_t * 4)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = ctypes.c_void_p
    kernel32.SetInformationJobObject.argtypes = (
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32)
    kernel32.AssignProcessToJobObject.argtypes = (ctypes.c_void_p,
                                                  ctypes.c_void_p)
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None
    info = _Extended()
    info.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(info),
                                            ctypes.sizeof(info)) or \
            not kernel32.AssignProcessToJobObject(
                job, int(proc._handle)):  # pylint: disable=protected-access
        return None
    return (kernel32, job)


def _kill_tree(proc, job):
    """Kill everything the entry started. POSIX: the entry's own session, which
    still reaches a grandchild after pytest has exited. Windows: the job, or
    taskkill /T when there is none (that entry is COULD-NOT-TELL: taskkill
    cannot reach a child whose parent has exited). Known gaps: a POSIX grandchild that calls
    setsid itself, and a Windows grandchild started between Popen and the job
    assignment (pytest's startup is far longer than that window)."""
    if job is not None:
        kernel32, handle = job
        kernel32.TerminateJobObject.argtypes = (ctypes.c_void_p,
                                                ctypes.c_uint32)
        kernel32.TerminateJobObject(handle, 1)
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        kernel32.CloseHandle(handle)
    elif os.name == "nt":
        try:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           capture_output=True, check=False, timeout=60)
        except subprocess.TimeoutExpired:
            pass  # proc.kill() below still ends the entry's own process
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    if proc.poll() is None:
        proc.kill()
    proc.wait()


def kill_current():
    """Kill the running entry's whole tree, if there is one. Signal-safe: it
    never raises."""
    while _CURRENT:
        proc, job = _CURRENT.pop()
        try:
            _kill_tree(proc, job)
        except OSError:
            pass


def run_target(target, timeout=None, cwd=CREW, extra=("--run-slow",),
               mem_mib=None):
    """Run one pytest target from the crew directory. Returns
    `(code, output, report, collected, seconds, timed_out)`; `code` is None
    when the run timed out. Ambient PYTEST_ADDOPTS / PYTEST_PLUGINS are
    dropped, so an inherited `-x` or `--maxfail` cannot cut the target short,
    and there is no `-x`: every case of a parametrized target runs.
    T-0080's bound applies: `timeout` and `mem_mib` default to
    `sabotage_bound.limits` (CREW_SABOTAGE_TIMEOUT_S, CREW_SABOTAGE_MEM_MB),
    and on Linux the entry and everything it spawns run under that
    RLIMIT_DATA cap."""
    if timeout is None or mem_mib is None:
        default_mem, default_timeout = sabotage_bound.limits(os.environ)
        timeout = default_timeout if timeout is None else timeout
        mem_mib = default_mem if mem_mib is None else mem_mib
    scratch = tempfile.mkdtemp(prefix="sabotage-entry-")
    junit = os.path.join(scratch, "junit.xml")
    collected_path = os.path.join(scratch, "collected.txt")
    log = os.path.join(scratch, "output.txt")
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS")}
    env.update(PYTHONDONTWRITEBYTECODE="1", **{_COLLECTED_ENV: collected_path})
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (_HERE, env.get("PYTHONPATH", "")) if p)
    argv = [sys.executable, "-m", "pytest", target, "-q", "--no-header",
            "-p", "no:cacheprovider", "-p", "sabotage_platform", *extra,
            f"--junitxml={junit}"]
    kwargs = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
              if os.name == "nt" else {"start_new_session": True})
    cap = sabotage_bound.data_cap_bytes(mem_mib)
    if cap:
        kwargs["preexec_fn"] = lambda: sabotage_bound.resource.setrlimit(
            sabotage_bound.resource.RLIMIT_DATA, (cap, cap))
    start = time.monotonic()
    timed_out = False
    with open(log, "w", encoding="utf-8", errors="replace") as out:
        proc = subprocess.Popen(  # pylint: disable=consider-using-with
            argv, cwd=cwd, stdout=out, stderr=subprocess.STDOUT, env=env,
            **kwargs)
        job = _new_job(proc)
        _CURRENT.append((proc, job))
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
        # Always: a survivor of this entry would contend with the next one.
        # Registered until the tree is gone (review of ee01a3ca): a signal in
        # between still finds it through kill_current.
        try:
            _kill_tree(proc, job)
        finally:
            if _CURRENT:
                _CURRENT.pop()
    seconds = time.monotonic() - start
    with open(log, encoding="utf-8", errors="replace") as handle:
        output = handle.read()
    report = None if timed_out else junit_outcome(junit)
    if report is not None and job is None and _NEEDS_JOB:
        report["uncontained"] = True
    collected = read_collected(collected_path)
    for name in (junit, collected_path, log):
        try:
            os.remove(name)
        except OSError:
            pass
    try:
        os.rmdir(scratch)
    except OSError:
        pass
    return (None if timed_out else proc.returncode, output, report, collected,
            seconds, timed_out)


def verdict(code, report, collected, timed_out, seconds):
    """`(text, ok)` for one applied entry; `ok` is False for every verdict
    except RED (good)."""
    if timed_out:
        return f"COULD-NOT-TELL -- timed out after {seconds:.0f}s", False
    if report is None:
        return f"COULD-NOT-TELL -- no test report (exit {code})", False
    if report.get("uncontained"):
        return "COULD-NOT-TELL -- no job object held the entry's tree", False
    if code == 1:
        unrun = (len(set(collected) - set(report["names"]))
                 if collected is not None else None)
        if report["errored"]:
            why = f"{report['errored']} errored"
        elif report["skipped"]:
            why = f"partial: {report['skipped']} skipped"
        elif unrun is None:
            why = "collection not recorded"
        elif unrun:
            why = f"partial: {unrun} unrun"
        elif not report["failed"]:
            why = "no failing case"
        else:
            return "RED (good)", True
        return f"RED BUT UNPROVEN -- exit 1, {why}", False
    if code == 0:
        if report["passed"]:
            return "STILL GREEN -- TEST IS VACUOUS", False
        reason = report["skip_reason"] or "no case ran"
        return f"COULD-NOT-TELL -- target skipped ({reason})", False
    return f"RED BUT UNPROVEN -- exit {code}, not a test failure", False


def line(text, label, seconds):
    """One verdict line; `seconds` None for an entry that was not applied."""
    took = "-" if seconds is None else f"{seconds:.1f}s"
    return f"{text:40} {label} [{took}]"


def not_exercised_text(platforms):
    return f"PLATFORM-ONLY, NOT EXERCISED ({','.join(sorted(platforms))})"


def summary(ok, not_exercised, host=None):
    """The last line. The platform-only count is in it whatever the verdict."""
    return (f"\nSABOTAGE SUITE: {'PASS' if ok else 'FAIL'} ({not_exercised} "
            f"platform-only, not exercised on {host or host_platform()})")
