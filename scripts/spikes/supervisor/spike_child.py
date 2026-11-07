# pylint: disable=consider-using-with,consider-using-f-string
"""Stand-in for a long-running console child (NOT a gate; spike for ADR 0010).

usage: spike_child.py MODE DIR     MODE = handled | default | ignore | slow
Writes DIR/lock, DIR/work.txt (two-part records, so a kill mid-record is visible),
DIR/child.log (what signals it saw) and DIR/grandchild.pid (a grandchild that
sleeps 20 s and exits by itself). Self-terminates after 30 s so nothing outlives a run.
This is a Python stand-in, not a real `claude`; see docs/adr/0010-supervised-restart.md.
"""
import os
import signal
import subprocess
import sys
import time

mode, d = sys.argv[1], sys.argv[2]
log = open(os.path.join(d, "child.log"), "a", buffering=1, encoding="utf-8")
stop = []


def say(msg):
    log.write(f"{time.time():.3f} {msg}\n")
    log.flush()
    os.fsync(log.fileno())


def on_sig(n, _f):
    say(f"saw signal {n}")
    stop.append(n)


names = [s for s in ("SIGINT", "SIGTERM", "SIGBREAK") if hasattr(signal, s)]
if mode in ("handled", "slow"):
    for s in names:
        signal.signal(getattr(signal, s), on_sig)
elif mode == "ignore":
    for s in names:
        signal.signal(getattr(signal, s), signal.SIG_IGN)
with open(os.path.join(d, "lock"), "w", encoding="utf-8") as lockfh:
    lockfh.write(str(os.getpid()))
gc = subprocess.Popen([sys.executable, "-c",
                       "import os,sys,time;open(sys.argv[1],'w').write(str(os.getpid()));time.sleep(20)",
                       os.path.join(d, "grandchild.pid")])
say(f"start pid={os.getpid()} mode={mode} grandchild={gc.pid}")
work = open(os.path.join(d, "work.txt"), "w", buffering=1, encoding="utf-8")
i, t0 = 0, time.time()
try:
    while not stop and time.time() - t0 < 30:
        work.write(f"BEGIN {i} ")
        work.flush()
        time.sleep(0.3)  # a kill landing here leaves a half record
        work.write(f"END {i}\n")
        work.flush()
        i += 1
except KeyboardInterrupt:
    say("KeyboardInterrupt (default SIGINT handler)")
    raise
if stop:
    if mode == "slow":
        say("flushing 1.5 s")
        time.sleep(1.5)
    work.write("FLUSHED\n")
    work.close()
    os.remove(os.path.join(d, "lock"))
    say("clean exit 0")
    sys.exit(0)
say("self-timeout")
