"""A hard wall-clock limit a hook child sets on itself, so it cannot outlive
its parent forever.

Why it exists: a guard reads its payload from stdin. When the shell that
started it dies, a pipe the guard was waiting on can stay open or never close,
and the read blocks with no CPU and no owner. Measured on one Windows host:
guard processes blocked 4.5 to 36.7 hours after their parent was gone. The
dispatcher (`crew_hook.py`) kills a guard at its row timeout, but only while
the dispatcher itself is alive; a guard started by a dead shell had no one left
to kill it.

`arm(seconds)` starts a daemon timer. When it fires the process writes one line
to stderr and ends with `EXIT_CODE` (124, the `timeout(1)` convention) through
`os._exit`, which works even while the main thread is blocked in a read. 124 is
neither 0 (allow) nor 2 (deny): the dispatcher reads it as "exited without a
decision", the same fail-closed UNKNOWN result it already gives a guard it
killed at its timeout. The limit never changes a deny decision: a guard that
decides in time never reaches it.

`CREW_SELF_LIMIT_S` overrides the number of seconds (a positive number); zero,
a negative or text leaves the caller's value. Standard library only.
"""
from __future__ import annotations

import os
import sys
import threading

EXIT_CODE = 124
ENV = "CREW_SELF_LIMIT_S"

_timer = None


def limit_seconds(default, env=None):
    """The seconds to arm: `CREW_SELF_LIMIT_S` when it is a positive number,
    else `default`."""
    raw = (os.environ if env is None else env).get(ENV)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return float(default)
    return value if value > 0 else float(default)


def _expire(name, seconds, exit_fn):
    try:
        sys.stderr.write(f"{name}: self-limit of {seconds:g}s reached; exiting without a decision "
                         "(the hook's parent may be gone)\n")
        sys.stderr.flush()
    except (OSError, ValueError):
        pass
    exit_fn(EXIT_CODE)


def arm(default_seconds, name="crew hook", exit_fn=os._exit):  # pylint: disable=protected-access
    """Start the watchdog once per process; returns the timer (or None when it
    was already armed). `exit_fn` is a seam for the test."""
    global _timer  # pylint: disable=global-statement
    if _timer is not None:
        return None
    seconds = limit_seconds(default_seconds)
    _timer = threading.Timer(seconds, _expire, (name, seconds, exit_fn))
    _timer.daemon = True
    _timer.start()
    return _timer


def disarm():
    """Cancel the watchdog (tests; a caller that finished its blocking work)."""
    global _timer  # pylint: disable=global-statement
    if _timer is not None:
        _timer.cancel()
        _timer = None
