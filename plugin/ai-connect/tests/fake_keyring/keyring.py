"""Stand-in for the `keyring` package: the credential store is the JSON file in $FAKE_KEYRING_FILE.

On PYTHONPATH for every deploy run of the suites, ahead of any real keyring, so no
test reads or writes this machine's own credential store. FAKE_KEYRING_MODE=absent
makes the import fail the way an uninstalled package does; =broken makes every
call raise NoKeyringError, the way a machine with no backend does; =locked makes
every call raise KeyringLocked, the way a store that will not open does; =half
lets the client ID be written and refuses the secret.
"""
import json
import os
from pathlib import Path

if os.environ.get("FAKE_KEYRING_MODE") == "absent":
    raise ImportError("No module named 'keyring' (fake_keyring, absent mode)")


class NoKeyringError(RuntimeError):
    """keyring.errors.NoKeyringError, by name."""


class KeyringLocked(RuntimeError):
    """keyring.errors.KeyringLocked, by name."""


def _load() -> dict:
    if os.environ.get("FAKE_KEYRING_MODE") == "broken":
        raise NoKeyringError("no keyring backend (fake_keyring, broken mode)")
    if os.environ.get("FAKE_KEYRING_MODE") == "locked":
        raise KeyringLocked("the store is locked (fake_keyring, locked mode)")
    path = Path(os.environ["FAKE_KEYRING_FILE"])
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def get_password(service: str, username: str):
    return _load().get(f"{service}/{username}")


def delete_password(service: str, username: str) -> None:
    store = _load()
    del store[f"{service}/{username}"]
    text = json.dumps(store)
    Path(os.environ["FAKE_KEYRING_FILE"]).write_text(text, encoding="utf-8")


def set_password(service: str, username: str, password: str) -> None:
    if os.environ.get("FAKE_KEYRING_MODE") == "half" and username.endswith("secret"):
        raise KeyringLocked("this item cannot be written (fake_keyring, half mode)")
    store = _load()
    store[f"{service}/{username}"] = password
    text = json.dumps(store)  # build the payload before the write truncates the file
    Path(os.environ["FAKE_KEYRING_FILE"]).write_text(text, encoding="utf-8")
