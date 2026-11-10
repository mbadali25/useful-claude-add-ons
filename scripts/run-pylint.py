#!/usr/bin/env python3
"""Run pylint over every tracked Python file, in-process, with no argv limit.

CI (.github/workflows/pylint.yml) runs
`pylint -j N $(git ls-files '*.py')`. On Windows that expansion exceeds the
command-line limit ("Argument list too long"), so the local verify rule could
never run. Here the same file list (same `git ls-files '*.py'`, same single
pylint invocation, so cross-file checks see the same set) is handed to
`pylint.lint.Run` as a Python list, which has no limit. Config is .pylintrc at
the repo root, exactly as in CI.

Usage: python3 scripts/run-pylint.py [--list] [extra pylint args...]
  --list  print the file list and exit 0 (used by the suite and for comparing
          against CI's set).
Exit: pylint's own code; 77 = pylint is not importable (TOOL MISSING, not a
pass and not a failure); 2 = git could not list files.
"""

from __future__ import annotations

import os
import subprocess
import sys

EXIT_MISSING = 77


def tracked_python_files() -> list[str]:
    """`git ls-files '*.py'` in the current directory, as CI runs it."""
    proc = subprocess.run(["git", "ls-files", "*.py"], capture_output=True,
                          text=True, check=False)
    if proc.returncode != 0:
        sys.stderr.write(f"run-pylint: git ls-files failed: {proc.stderr}\n")
        sys.exit(2)
    return proc.stdout.splitlines()


def main(argv: list[str]) -> int:
    """Entry point."""
    files = tracked_python_files()
    if argv[:1] == ["--list"]:
        sys.stdout.write("".join(f"{name}\n" for name in files))
        return 0
    try:
        from pylint.lint import Run  # pylint: disable=import-outside-toplevel
    except ImportError:
        sys.stderr.write(
            "TOOL MISSING: pylint is not importable by this python3, so the "
            "pylint pass DID NOT RUN. This is a missing tool, not a passing "
            "check and not a failing one. CI (pylint.yml, 3.11/3.12/3.13) "
            "still runs it. Install pylint to check locally.\n")
        return EXIT_MISSING
    if not files:
        return 0
    jobs = ["-j", str(os.cpu_count() or 1)]
    # Keep the script's own directory off sys.path, as `pylint` itself would.
    if sys.path and os.path.abspath(sys.path[0]) == os.path.dirname(os.path.abspath(__file__)):
        sys.path.pop(0)
    result = Run([*jobs, *argv, *files], exit=False)
    return int(result.linter.msg_status)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
