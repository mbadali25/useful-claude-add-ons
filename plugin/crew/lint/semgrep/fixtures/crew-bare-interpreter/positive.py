import subprocess


def run_ps(script: str) -> None:
    subprocess.run(["pwsh", "-NoProfile", "-File", script], check=False)


def run_py(script: str) -> None:
    subprocess.Popen(("python3", script))
