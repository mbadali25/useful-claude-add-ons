"""Makes the repo root importable regardless of how pytest is invoked.

tests/ has no __init__.py, so pytest's default "prepend" import mode only
puts tests/ on sys.path, not the repo root where installer.py and
config_loader.py live.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
