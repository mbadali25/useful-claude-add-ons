"""Puts the skill's scripts/ directory on sys.path so tests can import it."""
import os
import sys

SCRIPTS = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, "scripts")
)
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
