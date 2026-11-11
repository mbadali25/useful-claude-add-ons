# pylint: disable=consider-using-with
"""Launch spike_supervisor.py in its own new console and wait (NOT a gate; Windows only)."""
import os
import subprocess
import sys

if sys.platform != "win32":
    sys.exit("run_windows.py is Windows-only; run spike_supervisor.py directly on POSIX")

here = os.path.dirname(os.path.abspath(__file__))
p = subprocess.Popen([sys.executable, os.path.join(here, "spike_supervisor.py"), sys.argv[1]],
                     creationflags=subprocess.CREATE_NEW_CONSOLE)
print("supervisor exit", p.wait(timeout=240))
