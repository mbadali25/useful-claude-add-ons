"""Where localgpu keeps its things, and what the user asked for.

Two layers of configuration, nearest wins:

    <cwd>/.localgpu/config.json     per-repo
    $LOCALGPU_HOME/config.json      per-machine

Recognised keys: ``roots``, ``ignore``, ``embed_model``, ``chat_model``,
``ollama_url``. Every layer may set any subset; unset keys fall through to the
layer below and then to :data:`DEFAULTS`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# nomic-embed-text emits 768 floats. Changing the embed model means rebuilding
# the index from scratch, because the vector file has no room for two widths.
EMBED_DIM = 768

DEFAULT_EMBED_MODEL = "nomic-embed-text"
DEFAULT_CHAT_MODEL = "qwen2.5-coder:7b-instruct-q4_K_M"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"

# Always applied, on top of whatever the config layers add. Indexing .git or a
# node_modules tree is not a preference anyone holds; it is a mistake.
DEFAULT_IGNORE = [
    ".git",
    ".hg",
    ".svn",
    ".localgpu",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    "dist",
    "build",
    "target",
    "*.min.js",
    "*.map",
    "*.lock",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.ico",
    "*.pdf",
    "*.zip",
    "*.gz",
    "*.tar",
    "*.7z",
    "*.exe",
    "*.dll",
    "*.so",
    "*.dylib",
    "*.pyc",
    "*.class",
    "*.jar",
    "*.wasm",
    "*.mp4",
    "*.mp3",
    "*.woff",
    "*.woff2",
    "*.ttf",
    # Credentials. The indexer embeds file *contents* into an on-disk vector
    # store, so a secret excluded from git by name but missing here gets a
    # second, less-guarded copy written to disk on every machine this plugin
    # is installed on. ".env.*" is not the bare name "env.production" some
    # tools use instead - that variant is deliberately left out of this list
    # rather than caught here, since it cannot be told apart from an ordinary
    # dotted filename by name alone.
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa*",
    "credentials.json",
]

DEFAULTS: dict[str, Any] = {
    "roots": [],
    "ignore": [],
    "embed_model": DEFAULT_EMBED_MODEL,
    "chat_model": DEFAULT_CHAT_MODEL,
    "ollama_url": DEFAULT_OLLAMA_URL,
}

CONFIG_KEYS = tuple(DEFAULTS)

# "ignore": "node_modules" is the mistake a user actually makes - a string is
# iterable, so it would silently become the single-character patterns
# 'n','o','d',... instead of failing. Every key gets its expected shape
# checked eagerly, before it ever reaches the merge, so a typo reports itself
# by name instead of turning into inexplicable behaviour three layers away.
_LIST_KEYS = frozenset({"roots", "ignore"})
_STR_KEYS = frozenset({"embed_model", "chat_model", "ollama_url"})


class ConfigError(RuntimeError):
    """A config file exists but cannot be used."""


def localgpu_home() -> Path:
    r"""The install root: ``%LOCALAPPDATA%\localgpu`` or ``~/.local/share/localgpu``.

    An explicit ``LOCALGPU_HOME`` beats both, which is what the tests use.
    """
    override = os.environ.get("LOCALGPU_HOME")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Local"
        return root / "localgpu"
    return Path.home() / ".local" / "share" / "localgpu"


def venv_dir(home: Path | None = None) -> Path:
    """The interpreter the bootstrap builds. Never the system Python."""
    return (home or localgpu_home()) / "venv"


def venv_python(home: Path | None = None) -> Path:
    venv = venv_dir(home)
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def index_dir(home: Path | None = None) -> Path:
    return (home or localgpu_home()) / "index"


def vectors_path(home: Path | None = None) -> Path:
    return index_dir(home) / "vectors.f16"


def meta_path(home: Path | None = None) -> Path:
    return index_dir(home) / "meta.sqlite"


def manifest_path(home: Path | None = None) -> Path:
    return index_dir(home) / "manifest.json"


def global_config_path(home: Path | None = None) -> Path:
    return (home or localgpu_home()) / "config.json"


def repo_config_path(cwd: Path | str | None = None) -> Path:
    return Path(cwd or Path.cwd()) / ".localgpu" / "config.json"


def _read_layer(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must hold a JSON object, found {type(raw).__name__}")
    filtered = {k: v for k, v in raw.items() if k in CONFIG_KEYS}
    for key, value in filtered.items():
        if key in _LIST_KEYS and not isinstance(value, list):
            raise ConfigError(
                f"{path}: {key!r} must be a list of strings, found "
                f"{type(value).__name__} ({value!r}). Did you mean [{value!r}]?"
            )
        if key in _STR_KEYS and not isinstance(value, str):
            raise ConfigError(
                f"{path}: {key!r} must be a string, found "
                f"{type(value).__name__} ({value!r})"
            )
    return filtered


def load_config(
    cwd: Path | str | None = None,
    home: Path | None = None,
) -> dict[str, Any]:
    """Merge the two layers and fill in the defaults.

    ``roots`` defaults to ``[cwd]`` and is always returned absolute.
    ``ignore`` is the union of :data:`DEFAULT_IGNORE` and every layer's list —
    a layer can add exclusions, not drop the built-in ones.
    """
    cwd = Path(cwd or Path.cwd()).resolve()
    home = home or localgpu_home()

    merged = dict(DEFAULTS)
    ignore: list[str] = list(DEFAULT_IGNORE)

    for layer in (_read_layer(global_config_path(home)), _read_layer(repo_config_path(cwd))):
        for key, value in layer.items():
            if key == "ignore":
                ignore.extend(str(v) for v in value or [])
            else:
                merged[key] = value

    seen: set[str] = set()
    merged["ignore"] = [p for p in ignore if not (p in seen or seen.add(p))]

    roots = [str(Path(r).expanduser().resolve()) for r in merged.get("roots") or []]
    merged["roots"] = roots or [str(cwd)]

    for key in ("embed_model", "chat_model", "ollama_url"):
        merged[key] = str(merged[key])
    merged["ollama_url"] = merged["ollama_url"].rstrip("/")

    merged["home"] = str(home)
    merged["embed_dim"] = EMBED_DIM
    return merged
