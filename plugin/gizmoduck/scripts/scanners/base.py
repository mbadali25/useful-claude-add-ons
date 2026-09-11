"""Shared plumbing for scanner adapters.

run_tool never raises on a non-zero exit and never infers success from one:
Trivy exits 0 with findings present unless --exit-code is passed, sqlmap
exits 0 whether or not it found an injection, and ZAP's documented 0/1/2/3
contract belongs to its Docker wrapper rather than the Automation Framework
we actually invoke. Every adapter decides from parsed output, not status.
"""
import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class ToolResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool


def which(binary):
    return shutil.which(binary)


def run_tool(argv, timeout, cwd=None):
    try:
        p = subprocess.run(argv, capture_output=True, text=True,
                           timeout=timeout, cwd=cwd, check=False)
        return ToolResult(p.returncode, p.stdout or "", p.stderr or "", False)
    except subprocess.TimeoutExpired as e:
        return ToolResult(-1, e.stdout or "", e.stderr or "", True)
    except FileNotFoundError as e:
        return ToolResult(-1, "", str(e), False)
