import subprocess
import sys


def run_py(script: str) -> None:
    subprocess.run([sys.executable, script], check=False)


def run_ps(pwsh_path: str, script: str) -> None:
    subprocess.run([pwsh_path, "-File", script], check=False)


def run_other() -> None:
    subprocess.run(["/usr/bin/env", "true"], check=False)
