"""T-0080: the bound every `sabotage.py` entry runs under, and how its exit
code is judged. Kept apart only because `sabotage.py` sits at `.pylintrc`'s
max-module-lines; run that file, not this one.

WHY. A mutation can turn a bounded read into an unbounded one (the cloud guard
entry that swaps `_read_small` for `json.load` on a symlink to /dev/zero). An
uncapped full run then grew one python3 past 19 GB and the host's OOM killer
took the orchestrating session with it. The host's heavy-run cgroup is not on
CI or on other machines, so the harness bounds itself, per entry:

- MEMORY. `RLIMIT_AS` set in the child before exec, so every process the test
  spawns inherits it. Over the cap the reading process gets MemoryError, the
  guard turns that into an "internal error" deny, the test's own assertion
  fails and pytest exits 1: RED by a real assertion, never a new outcome that
  counts as a pass. Enforced on Linux only; elsewhere the line says `absent`.
- TIME. The child runs in its own session/process group. Past the limit the
  whole group is stopped (TERM, a short grace, KILL; the process tree on
  Windows) and `run` returns TIMED_OUT, which `verdict` reports as unproven:
  could-not-tell stays could-not-tell.

`CREW_SABOTAGE_MEM_MB` (default 4096, 0 = no cap, and the line says so) and
`CREW_SABOTAGE_TIMEOUT_S` (default 600). Anything else that is not an integer
in range raises ValueError: an unreadable limit refuses the run, it never
means the default or no cap. 4096 MiB because pwsh needs more than 2 GiB of
address space to start (measured: exit 134 under 2 GiB, clean under 4 GiB).

A harness killed by SIGKILL cannot stop its child; any other exit the harness
sees (its signal handler's SystemExit, Ctrl-C) stops the group before it
unwinds, because the group is outside the caller's own process group.
"""
import os
import re
import signal
import subprocess
import sys

try:
    import resource
except ImportError:  # Windows
    resource = None

DEFAULT_MEM_MIB = 4096
DEFAULT_TIMEOUT_S = 600
MEM_VAR = "CREW_SABOTAGE_MEM_MB"
TIMEOUT_VAR = "CREW_SABOTAGE_TIMEOUT_S"
TIMED_OUT = 124
_GRACE_S = 5

# pytest's own exit codes (documented, not this file's invention): 0 all
# passed; 1 at least one test FAILED (a real assertion, or an error raised
# during a test); 2 execution interrupted; 3 an internal pytest error; 4 a
# usage error, which is what a collection failure -- an import blowing up
# on a SyntaxError, say -- actually produces; 5 no tests were collected at
# all. Only 1 is evidence that the TARGET TEST caught the mutation. Finding
# 13: the previous version of this treated every non-zero code the same,
# so a mutation that broke the whole file's syntax (crashing collection
# for every test in the suite, this one included) reported "RED (good)"
# indistinguishably from a mutation the target test actually caught -- and
# only 4 of the round's 18 new mutations had been hand-verified as the real
# thing rather than this.
REAL_TEST_FAILURE = 1


def _limit(environ, name, default, minimum):
    raw = environ.get(name)
    if raw is None:
        return default
    if not re.fullmatch(r"[0-9]+", raw) or int(raw) < minimum:
        raise ValueError(f"{name}={raw!r} is not an integer of at least {minimum}; "
                         f"an unreadable limit refuses the run rather than meaning "
                         f"the default or no cap")
    return int(raw)


def limits(environ):
    """(mem_mib, timeout_s) from the environment; ValueError when unreadable."""
    return (_limit(environ, MEM_VAR, DEFAULT_MEM_MIB, 0),
            _limit(environ, TIMEOUT_VAR, DEFAULT_TIMEOUT_S, 1))


def _absent(mem_mib):
    """Why no memory cap is enforced, or None when it is."""
    if mem_mib == 0:
        return f"{MEM_VAR}=0"
    if not sys.platform.startswith("linux"):
        return f"not enforced on {sys.platform}"
    if resource is None:
        return "no resource module"
    return None


def describe(mem_mib, timeout_s):
    """The one line `sabotage.py` prints before the first mutation."""
    why = _absent(mem_mib)
    memory = (f"memory {mem_mib} MiB per process (RLIMIT_AS)" if why is None
              else f"memory cap absent ({why})")
    return f"bound: {memory}, {timeout_s} s per entry"


def verdict(code, timeout_s):
    """(outcome text, counts as good) for one entry's exit code."""
    if code == REAL_TEST_FAILURE:
        return "RED (good)", True
    if code == 0:
        return "STILL GREEN -- TEST IS VACUOUS", False
    if code == TIMED_OUT:
        return f"RED BUT UNPROVEN -- timed out after {timeout_s}s", False
    # Went red, but not because the target test caught anything -- a
    # collection/import error crashed the run before the test executed, or
    # nothing matching the target was collected. Proves nothing.
    return f"RED BUT UNPROVEN -- exit {code}, not a test failure", False


def _signal_group(pid, sig):
    try:
        os.killpg(pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _stop(proc):
    """Stop the child's whole group, not just its leader."""
    if os.name == "posix":
        _signal_group(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=_GRACE_S)
        except subprocess.TimeoutExpired:
            pass
        _signal_group(proc.pid, signal.SIGKILL)
    else:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       capture_output=True, check=False)
    try:
        proc.wait(timeout=_GRACE_S)
    except subprocess.TimeoutExpired:
        proc.kill()


def run(argv, cwd, env, mem_mib, timeout_s):
    """Run `argv` bounded; return (exit_code, stdout + stderr)."""
    cap = mem_mib << 20 if _absent(mem_mib) is None else 0
    kwargs = {}
    if os.name == "posix":
        kwargs["start_new_session"] = True
    else:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    if cap:
        kwargs["preexec_fn"] = lambda: resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
    proc = subprocess.Popen(  # pylint: disable=consider-using-with
        argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL, text=True, **kwargs)
    try:
        out, err = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _stop(proc)
        try:
            out, err = proc.communicate(timeout=_GRACE_S)
        except subprocess.TimeoutExpired:
            out, err = "", "(output not read: a process outside the group holds it)"
        return TIMED_OUT, (out or "") + (err or "")
    except BaseException:
        _stop(proc)
        raise
    return proc.returncode, out + err
