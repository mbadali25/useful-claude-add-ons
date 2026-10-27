import json
from pathlib import Path


def load_state(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_handle(path: Path) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)
