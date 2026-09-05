"""Swapping the embed model for a different one of the same width must not be
silently invisible. See ``Indexer._check_embed_model`` in ``indexer.py``.
"""

from __future__ import annotations

import pytest

import config
from conftest import TEST_DIM
from indexer import EmbedModelMismatch, Indexer
from store import VectorStore


def make_indexer(home, embedder, embed_model=None):
    store = VectorStore(config.index_dir(home), dim=TEST_DIM)
    return store, Indexer(
        store, embed=embedder, ignore=["*.bin"], embed_model=embed_model
    )


class FlakyEmbedder:
    """Wraps a real embedder but raises once a call budget is exhausted.

    Stands in for an Ollama request timing out partway through the first
    ever refresh - see test_incremental.py, which defines the same helper
    for the same reason: each test file stays self-contained.
    """

    def __init__(self, base, fail_after: int) -> None:
        self.base = base
        self.fail_after = fail_after
        self.calls = 0

    def __call__(self, texts):
        self.calls += 1
        if self.calls > self.fail_after:
            raise RuntimeError("embed request failed")
        return self.base(texts)


def test_fresh_build_records_embed_model(home, repo, write, embedder):
    write(repo / "alpha.py", "def alpha():\n    return 1\n")
    store, indexer = make_indexer(home, embedder, embed_model="model-a")
    try:
        indexer.refresh([repo])
        manifest = store.read_manifest()
        assert manifest["embed_model"] == "model-a"
    finally:
        store.close()


def test_same_model_reload_passes(home, repo, write, embedder):
    write(repo / "alpha.py", "def alpha():\n    return 1\n")
    store, indexer = make_indexer(home, embedder, embed_model="model-a")
    try:
        indexer.refresh([repo])
    finally:
        store.close()

    # A fresh Indexer over the same on-disk store, same model configured.
    store2, indexer2 = make_indexer(home, embedder, embed_model="model-a")
    try:
        result = indexer2.refresh([repo])  # must not raise
        assert result["files_unchanged"] == 1
        assert store2.read_manifest()["embed_model"] == "model-a"
    finally:
        store2.close()


def test_same_dim_different_model_is_detected(home, repo, write, embedder):
    """The whole point of this check: two models of equal width, silently swapped."""
    write(repo / "alpha.py", "def alpha():\n    return 1\n")
    store, indexer = make_indexer(home, embedder, embed_model="model-a")
    try:
        indexer.refresh([repo])
    finally:
        store.close()

    store2, indexer2 = make_indexer(home, embedder, embed_model="model-b")
    try:
        with pytest.raises(EmbedModelMismatch, match="model-a.*model-b"):
            indexer2.refresh([repo])
        # Refusing must mean refusing - no partial write, no silent update.
        assert store2.read_manifest()["embed_model"] == "model-a"
    finally:
        store2.close()


def test_legacy_manifest_with_no_embed_model_key_is_not_treated_as_a_match(
    home, repo, write, embedder
):
    write(repo / "alpha.py", "def alpha():\n    return 1\n")
    # No embed_model passed here - the pre-fix call shape. The manifest this
    # produces has dim/last_refresh but never gets an embed_model key.
    store, indexer = make_indexer(home, embedder, embed_model=None)
    try:
        indexer.refresh([repo])
        manifest = store.read_manifest()
        assert manifest  # a real manifest was written
        assert "embed_model" not in manifest
    finally:
        store.close()

    store2, indexer2 = make_indexer(home, embedder, embed_model="model-a")
    try:
        with pytest.raises(EmbedModelMismatch, match="predates this check"):
            indexer2.refresh([repo])
    finally:
        store2.close()


def test_failed_initial_refresh_does_not_let_a_later_model_switch_through(
    home, repo, write, embedder
):
    """model-a indexes alpha.py, then fails embedding beta.py before the
    manifest is ever written - so the manifest this leaves behind is
    missing entirely, not merely lacking an ``embed_model`` key. A later
    refresh under a different, same-width model must not read "no manifest"
    as "nothing built yet": alpha.py's vectors are already live, embedded by
    model-a, with nothing on disk recording that fact.
    """
    write(repo / "alpha.py", "def alpha():\n    return 1\n")
    write(repo / "beta.py", "def beta():\n    return 2\n")
    store = VectorStore(config.index_dir(home), dim=TEST_DIM)
    flaky = FlakyEmbedder(embedder, fail_after=1)
    failing_indexer = Indexer(
        store, embed=flaky, ignore=["*.bin"], embed_model="model-a"
    )
    try:
        with pytest.raises(RuntimeError):
            failing_indexer.refresh([repo])
        # alpha.py (sorted first) made it in under model-a; beta.py's embed
        # call is what failed, before write_manifest ever ran.
        assert store.counts()[0] == 1
        assert not store.read_manifest()

        switched = Indexer(
            store, embed=embedder, ignore=["*.bin"], embed_model="model-b"
        )
        with pytest.raises(EmbedModelMismatch, match="predates this check"):
            switched.refresh([repo])
        # Refusing must mean refusing: alpha.py's model-a vectors are
        # untouched, and no manifest exists certifying a mixed index as
        # model-b.
        assert store.counts()[0] == 1
        assert not store.read_manifest()
    finally:
        store.close()


def test_indexer_without_embed_model_skips_the_check_entirely(
    home, repo, write, embedder
):
    """Backward compatibility: a call site that never passes embed_model keeps
    working exactly as before - no check, no manifest key written, no crash."""
    write(repo / "alpha.py", "def alpha():\n    return 1\n")
    store, indexer = make_indexer(home, embedder, embed_model="model-a")
    try:
        indexer.refresh([repo])
    finally:
        store.close()

    store2, indexer2 = make_indexer(home, embedder, embed_model=None)
    try:
        result = indexer2.refresh([repo])  # must not raise even though model-a was used
        assert result["files_unchanged"] == 1
        # Nothing told it to overwrite the recorded model - it must survive.
        assert store2.read_manifest()["embed_model"] == "model-a"
    finally:
        store2.close()
