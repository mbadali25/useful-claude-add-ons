"""Deadline polls for tests that used to sleep a fixed time and then check.

A test that sleeps a fixed time and then checks a condition is a timing flake
waiting for a slow host: the condition usually holds by then, and under load it
sometimes does not. The fix is to poll the condition until it holds or a
deadline passes, with the deadline well under the natural lifetime of the thing
being waited for, so a real failure still fails. That is not a wall-clock test:
the `wallclock` (serial) marker is only for tests that measure elapsed time
themselves (L-0516; `skills/crew-qa-standards/references/harness.md` H3).

This lives in its own module rather than `crew_fixtures.py` because another
lane (L-0557) edits that file's pwsh helpers; keeping the poll here means the
two changes cannot conflict.
"""
import pathlib
import time


def poll_until(probe, done, timeout, interval=0.05):
    """Call `probe()` until `done(value)` is true or `timeout` seconds pass.

    Always probes at least once, even with a zero timeout. Returns the LAST
    probed value, never a synthesized success: at the deadline the caller gets
    what the probe actually saw and makes its own assertion on it, so a real
    survivor still fails the test. The deadline uses `time.monotonic()`, which
    a wall-clock step cannot stretch or cut (PEP 418).
    """
    deadline = time.monotonic() + timeout
    while True:
        value = probe()
        if done(value) or time.monotonic() >= deadline:
            return value
        time.sleep(interval)


def wait_for_pidfile(path, timeout=10):
    """Wait until `path` holds a decimal pid, and return it, or None at the deadline.

    Waiting for the file to EXIST is not enough. A shell redirect such as
    `echo $! > pidfile` creates or truncates the file before the command
    writes to it (POSIX.1-2024 XCU 2.7.2, "Redirecting Output"), so there is a
    window in which the file exists and is empty. A tight reader over that
    exact shape saw it in 389 of 500 reads (L-0516 spec E6). A missing, empty
    or non-decimal file reads as "not yet".
    """
    def _read():
        try:
            text = pathlib.Path(path).read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return int(text) if text.isdigit() else None

    return poll_until(_read, done=lambda v: v is not None, timeout=timeout, interval=0.05)
