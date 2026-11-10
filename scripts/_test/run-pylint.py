#!/usr/bin/env python3
"""Suite for scripts/run-pylint.py, the verify rule's pylint runner.

Each case builds a throwaway git repo; nothing touches this repository.
Must-pass: clean file exits 0; a huge tracked set (past the Windows
command-line limit) runs; the file list equals `git ls-files '*.py'`.
Must-fail: a file with a real error exits non-zero; pylint not importable
exits 77 (not 0).

Run: python3 scripts/_test/run-pylint.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "run-pylint.py")
FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    """Record one case."""
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        FAILURES.append(f"{name}: {detail}")


def git(cwd: str, *args: str) -> None:
    """Run git quietly in cwd."""
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   cwd=cwd, check=True, capture_output=True)


def make_repo(files: dict[str, str]) -> str:
    """Create a git repo holding files, all tracked."""
    root = tempfile.mkdtemp(prefix="run-pylint-")
    git(root, "init", "-q")
    for name, body in files.items():
        with open(os.path.join(root, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
    git(root, "add", "-A")
    return root


def run(root: str, *args: str, pre: str = "") -> subprocess.CompletedProcess:
    """Run the script in root; pre is python source run first."""
    code = (pre + "import runpy,sys; "
            f"sys.argv=[{SCRIPT!r}]+{list(args)!r}; "
            f"runpy.run_path({SCRIPT!r}, run_name='__main__')")
    return subprocess.run([sys.executable, "-c", code], cwd=root,
                          capture_output=True, text=True, check=False)


def main() -> int:
    """Run every case."""
    clean = '"""Doc."""\n\n\ndef f():\n    """Doc."""\n    return 1\n'
    bad = '"""Doc."""\n\n\ndef f():\n    """Doc."""\n    return undefined_name\n'

    root = make_repo({"ok.py": clean})
    proc = run(root)
    check("clean file exits 0", proc.returncode == 0, proc.stdout + proc.stderr)

    root = make_repo({"ok.py": clean, "bad.py": bad})
    proc = run(root)
    check("real error exits non-zero", proc.returncode != 0, proc.stdout + proc.stderr)

    root = make_repo({"ok.py": clean})
    proc = run(root, pre="import sys; sys.modules['pylint']=None\n")
    check("pylint missing exits 77", proc.returncode == 77 and "TOOL MISSING" in proc.stderr,
          f"{proc.returncode} {proc.stderr}")

    many = {f"module_with_a_deliberately_long_name_{i:05d}.py": '"""Doc."""\n'
            for i in range(1500)}
    many["notpy.txt"] = "x"
    root = make_repo(many)
    listed = run(root, "--list").stdout.splitlines()
    expected = subprocess.run(["git", "ls-files", "*.py"], cwd=root, capture_output=True,
                              text=True, check=True).stdout.splitlines()
    check("list equals git ls-files '*.py'", listed == expected and len(listed) == 1500,
          f"{len(listed)} listed")
    total = sum(len(name) + 1 for name in listed)
    check("fixture exceeds the Windows 32767-char limit", total > 32767, str(total))
    proc = run(root, "--disable=all", "--enable=E")
    check("1500 files (past the argv limit) lint and exit 0", proc.returncode == 0,
          (proc.stdout + proc.stderr)[-500:])

    for line in FAILURES:
        print("  " + line)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
