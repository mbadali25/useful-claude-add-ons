import subprocess
from pathlib import Path


def read_ledger(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return text.splitlines()


def git_lines() -> list[str]:
    done = subprocess.run(["git", "status"], capture_output=True, text=True, check=False)
    return done.stdout.splitlines()
