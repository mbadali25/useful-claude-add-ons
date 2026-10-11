"""Stand-in for the `keyring` package: the credential store is the JSON file in $FAKE_KEYRING_FILE.

On PYTHONPATH for every deploy run of the suites, ahead of any real keyring, so no
test reads or writes this machine's own credential store. FAKE_KEYRING_MODE=absent
makes the import fail the way an uninstalled package does; =broken makes every
call raise, the way a machine with no backend does.
"""
import json
import os
from pathlib import Path

if os.environ.get("FAKE_KEYRING_MODE") == "absent":
    raise ImportError("No module named 'keyring' (fake_keyring, absent mode)")


def _load() -> dict:
    if os.environ.get("FAKE_KEYRING_MODE") == "broken":
        raise RuntimeError("no keyring backend (fake_keyring, broken mode)")
    path = Path(os.environ["FAKE_KEYRING_FILE"])
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def get_password(service: str, username: str):
    return _load().get(f"{service}/{username}")


def set_password(service: str, username: str, password: str) -> None:
    store = _load()
    store[f"{service}/{username}"] = password
    text = json.dumps(store)  # build the payload before the write truncates the file
    Path(os.environ["FAKE_KEYRING_FILE"]).write_text(text, encoding="utf-8")
