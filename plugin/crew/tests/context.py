"""Puts crew's script directories on sys.path so tests can import them."""
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))

for _rel in ("hooks/scripts", "skills/crew-graph/scripts"):
    _path = os.path.join(_ROOT, *_rel.split("/"))
    if _path not in sys.path:
        sys.path.insert(0, _path)
