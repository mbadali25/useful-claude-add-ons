# pylint: disable=consider-using-with,consider-using-f-string
"""Supervisor-side measurements for ADR 0010 (NOT a gate; never run by CI).

usage: spike_supervisor.py OUTDIR
Windows: run it in its OWN console (see run_windows.py) because CTRL_C_EVENT to
pid 0 reaches every process on the console. It only signals Popen objects it made.
Writes OUTDIR/results.json. Windows-only and POSIX-only calls sit behind sys.platform checks.
"""
import json
import os
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CHILD = os.path.join(HERE, "spike_child.py")
WIN = sys.platform == "win32"


def alive(pid):
    if sys.platform == "win32":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, 0, pid)
        if not h:
            return False
        c = ctypes.c_ulong()
        k.GetExitCodeProcess(h, ctypes.byref(c))
        k.CloseHandle(h)
        return c.value == 259
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def slurp(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def launch(mode, d):
    os.makedirs(d, exist_ok=True)
    kw = {}
    if sys.platform == "win32":
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    p = subprocess.Popen([sys.executable, CHILD, mode, d], **kw)
    for _ in range(100):
        if slurp(os.path.join(d, "grandchild.pid")):
            break
        time.sleep(0.05)
    time.sleep(0.7)
    return p


def report(name, p, d, t_sent, grace=6.0):
    try:
        rc = p.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        rc = "STILL RUNNING after %.0fs" % grace
    el = time.time() - t_sent
    gp = slurp(os.path.join(d, "grandchild.pid"))
    work = slurp(os.path.join(d, "work.txt")) or ""
    return {
        "scenario": name,
        "returncode": rc if isinstance(rc, str) else [rc, hex(rc & 0xFFFFFFFF)],
        "seconds_to_exit": round(el, 2),
        "child_log": [ln.split(" ", 1)[1] for ln in (slurp(os.path.join(d, "child.log")) or "").splitlines()],
        "work_tail": work[-40:], "work_ends_complete": work.endswith("\n"),
        "lock_remains": os.path.exists(os.path.join(d, "lock")),
        "grandchild_alive": bool(gp) and alive(int(gp)),
    }


def finish(p):
    if p.poll() is None:  # our own Popen only
        p.kill()
        p.wait()


def posix(out):
    res = []
    for mode in ("handled", "default", "slow", "ignore"):
        d = os.path.join(out, "posix-" + mode)
        p = launch(mode, d)
        t = time.time()
        os.killpg(p.pid, signal.SIGTERM)  # pylint: disable=no-member
        grace = 1.0 if mode in ("slow", "ignore") else 3.0
        try:
            p.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            if mode == "slow":  # re-measure with a grace long enough to flush
                p.wait(timeout=4)
            else:
                os.killpg(p.pid, signal.SIGKILL)  # pylint: disable=no-member
        r = report("SIGTERM, escalate to SIGKILL after %.0fs: %s" % (grace, mode), p, d, t)
        res.append(r)
        finish(p)
    return res


def win(out):
    import ctypes
    from ctypes import wintypes as W
    k = ctypes.windll.kernel32
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # supervisor ignores CTRL_C
    res = []
    for mode in ("handled", "default"):
        d = os.path.join(out, "win-break-" + mode)
        p = launch(mode, d)
        t = time.time()
        os.kill(p.pid, signal.CTRL_BREAK_EVENT)  # pylint: disable=no-member  # Windows-only
        res.append(report("CTRL_BREAK_EVENT to new process group: " + mode, p, d, t))
        finish(p)
    for mode in ("handled", "default"):
        d = os.path.join(out, "win-ctrlc-" + mode)
        p = launch(mode, d)
        t = time.time()
        k.GenerateConsoleCtrlEvent(0, 0)  # CTRL_C to every process on THIS console
        r = report("CTRL_C_EVENT (pid 0) to new-group child: " + mode, p, d, t, grace=3)
        r["supervisor_survived"] = True
        res.append(r)
        finish(p)
    d = os.path.join(out, "win-ctrlc-samegroup")  # control: child NOT in a new group
    os.makedirs(d, exist_ok=True)
    p = subprocess.Popen([sys.executable, CHILD, "handled", d])
    time.sleep(1.2)
    t = time.time()
    k.GenerateConsoleCtrlEvent(0, 0)
    res.append(report("CTRL_C_EVENT (pid 0) to same-group child: handled", p, d, t, grace=3))
    finish(p)

    class Basic(ctypes.Structure):
        _fields_ = [("a", ctypes.c_int64), ("b", ctypes.c_int64), ("LimitFlags", W.DWORD),
                    ("c", ctypes.c_size_t), ("d", ctypes.c_size_t), ("e", W.DWORD),
                    ("f", ctypes.c_size_t), ("g", W.DWORD), ("h", W.DWORD)]

    class IoCounters(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in "abcdef"]

    class Ext(ctypes.Structure):
        _fields_ = [("Basic", Basic), ("Io", IoCounters), ("p", ctypes.c_size_t), ("j", ctypes.c_size_t),
                    ("pm", ctypes.c_size_t), ("pk", ctypes.c_size_t)]

    k.OpenProcess.restype = ctypes.c_void_p
    k.CreateJobObjectW.restype = ctypes.c_void_p
    for how in ("TerminateJobObject", "CloseHandle(KILL_ON_JOB_CLOSE)"):
        d = os.path.join(out, "win-job-" + how.split("(", maxsplit=1)[0])
        p = launch("handled", d)
        h = ctypes.c_void_p(k.CreateJobObjectW(None, None))
        e = Ext()
        e.Basic.LimitFlags = 0x2000
        k.SetInformationJobObject(h, 9, ctypes.byref(e), ctypes.sizeof(e))
        ph = ctypes.c_void_p(k.OpenProcess(0x1F0FFF, 0, p.pid))
        ok = k.AssignProcessToJobObject(h, ph)
        t = time.time()
        if how == "TerminateJobObject":
            k.TerminateJobObject(h, 1)
        k.CloseHandle(h)
        r = report("Job object, " + how, p, d, t)
        r["assigned_after_spawn"] = bool(ok)
        res.append(r)
        k.CloseHandle(ph)
        finish(p)
    return res


if __name__ == "__main__":
    OUT = sys.argv[1]
    os.makedirs(OUT, exist_ok=True)
    RESULTS = json.dumps(win(OUT) if WIN else posix(OUT), indent=1)
    with open(os.path.join(OUT, "results.json"), "w", encoding="utf-8") as fh:
        fh.write(RESULTS)
    print("done")
