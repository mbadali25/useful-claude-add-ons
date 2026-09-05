"""Shared fixtures. Nothing here talks to Ollama, a GPU, or the network."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Sequence

import pytest

# The module under test lives one directory up and is imported flat - see the
# comment in server.py about why that directory must not be a package.
_MCP_DIR = str(Path(__file__).resolve().parent.parent)
if _MCP_DIR not in sys.path:
    sys.path.insert(0, _MCP_DIR)

import config  # noqa: E402
import indexer as indexer_mod  # noqa: E402
import store as store_mod  # noqa: E402

TEST_DIM = 16


class FakeEmbedder:
    """Deterministic bag-of-words vectors. Same text in, same vector out.

    Stands in for nomic-embed-text: the numbers are meaningless but the
    behaviour that matters here - identical text embeds identically, related
    text embeds nearby, and every call is counted - is real.
    """

    def __init__(self, dim: int = TEST_DIM) -> None:
        self.dim = dim
        self.calls = 0
        self.texts: list[str] = []

    def __call__(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        self.texts.extend(texts)
        return [self.vector(text) for text in texts]

    def vector(self, text: str) -> list[float]:
        out = [0.0] * self.dim
        for token in indexer_mod._tokenise(text):
            out[hash_token(token) % self.dim] += 1.0
        if not any(out):
            out[0] = 1.0
        return out

    def reset(self) -> None:
        self.calls = 0
        self.texts = []


def hash_token(token: str) -> int:
    """A stable hash - Python's is salted per process."""
    value = 2166136261
    for ch in token.encode("utf-8"):
        value = ((value ^ ch) * 16777619) & 0xFFFFFFFF
    return value


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway $LOCALGPU_HOME. Never the real one."""
    root = tmp_path / "localgpu-home"
    root.mkdir()
    monkeypatch.setenv("LOCALGPU_HOME", str(root))
    return root


@pytest.fixture
def store(home: Path) -> store_mod.VectorStore:
    with store_mod.VectorStore(config.index_dir(home), dim=TEST_DIM) as opened:
        yield opened


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    return root


class Clock:
    """Hands out strictly increasing mtimes so 'changed' is never a coin flip."""

    def __init__(self) -> None:
        self.now = time.time() - 3600.0

    def tick(self) -> float:
        self.now += 10.0
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def write(clock: Clock):
    """Write a file and stamp it with a fresh mtime."""

    def _write(path: Path, text: str, mtime: float | None = None) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        stamp = clock.tick() if mtime is None else mtime
        os.utime(path, (stamp, stamp))
        return path

    return _write


def lines(count: int, prefix: str = "line") -> list[str]:
    return [f"{prefix} {i}\n" for i in range(1, count + 1)]
