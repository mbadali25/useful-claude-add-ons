"""Run one `.crew/verify.json` rule's crew test files, in parallel where safe.

    python3 plugin/crew/tests/pytest_rule.py <test file or dir>... [pytest option]...

WHY. The verify gate runs each matched rule as one serial pytest process, and
a Stop has a 60s budget. Measured on rule 4 (the gate/lock/promote/role-guard
files): 49s serial, 15s split this way, same 195 tests (4 CPUs, 2026-10-03).

HOW. Two pytest processes over the same arguments, the way CI runs the crew
suite (`.github/workflows/pytest-crew.yml`):

  1. `-n auto -m "not wallclock"` -- everything that is safe beside other
     workers. CI already runs every unmarked crew test under xdist, so this is
     no new exposure.
  2. `-m wallclock`, serially -- the tests that assert elapsed time against a
     real bound (conftest.py), which read past it beside busy workers.

Exit 5 ("no tests collected") from either half is not a failure: most rules'
files carry no wallclock test, and a file whose every test is wallclock
leaves nothing for the first half. Both halves exiting 5 IS a failure -- the
rule selected nothing at all, which is never what a rule means.

Without pytest-xdist this is exactly one serial `pytest <args>`, the command
the rule ran before, so a machine without it loses nothing but the speed.
"""
import subprocess
import sys

NO_TESTS = 5


def _has_xdist():
    try:
        import xdist  # noqa: F401  pylint: disable=import-outside-toplevel,unused-import
    except ImportError:
        return False
    return True


def _pytest(args):
    return subprocess.run([sys.executable, "-m", "pytest", *args], check=False).returncode


def main(argv):
    if not argv:
        sys.stderr.write(__doc__.split("\n\n", 1)[0] + "\n")
        return 2
    if any(a in ("-m", "-n") or a.startswith(("-m=", "-n=", "--numprocesses")) for a in argv):
        # This script owns the marker split and the worker count; a rule's own
        # -m or -n would be silently overridden by the later one.
        sys.stderr.write("pytest_rule.py: pass neither -m nor -n; this script sets both\n")
        return 2
    if not _has_xdist():
        return _pytest(argv)
    parallel = _pytest([*argv, "-n", "auto", "-m", "not wallclock"])
    serial = _pytest([*argv, "-m", "wallclock"])
    if parallel == NO_TESTS and serial == NO_TESTS:
        return NO_TESTS
    # The first real failure, never max(): a half killed by a signal returns a
    # NEGATIVE code, and max() would pick the other half's 0 over it.
    failed = [rc for rc in (parallel, serial) if rc not in (0, NO_TESTS)]
    return (failed[0] if failed[0] > 0 else 1) if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
