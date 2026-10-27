import json
from pathlib import Path


def refuse_duplicates(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(key)
        seen[key] = value
    return seen


def load_state(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=refuse_duplicates)


def literal() -> dict:
    return json.loads('{"a": 1}')
