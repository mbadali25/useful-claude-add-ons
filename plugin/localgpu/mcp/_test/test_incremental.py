"""Re-indexing must be cheap: unchanged files never reach the embedder."""

from __future__ import annotations

import os

import pytest

import config
from conftest import TEST_DIM
from indexer import Indexer
from store import VectorStore


def make_indexer(home, embedder, ignore=(), batch=None):
    store = VectorStore(config.index_dir(home), dim=TEST_DIM)
    kwargs = {} if batch is None else {"batch": batch}
    return store, Indexer(store, embed=embedder, ignore=list(ignore) or ["*.bin"], **kwargs)


class FlakyEmbedder:
    """Wraps a real embedder but raises once a call budget is exhausted.

    Stands in for an Ollama request timing out partway through a large file:
    the first N batches succeed and reach the store, the next one blows up.
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


def test_first_pass_indexes_everything(home, repo, write, embedder):
    write(repo / "alpha.py", "def alpha():\n    return 1\n")
    write(repo / "pkg" / "beta.py", "def beta():\n    return 2\n")
    store, indexer = make_indexer(home, embedder)
    try:
        result = indexer.refresh([repo])
        assert result["files_added"] == 2
        assert result["files_unchanged"] == 0
        assert result["chunks_added"] == 2
        assert store.counts() == (2, 0)
        assert embedder.calls == 2
    finally:
        store.close()


def test_unchanged_files_are_skipped_without_hashing(home, repo, write, embedder):
    write(repo / "alpha.py", "def alpha():\n    return 1\n")
    store, indexer = make_indexer(home, embedder)
    try:
        indexer.refresh([repo])
        embedder.reset()

        result = indexer.refresh([repo])
        assert result["files_unchanged"] == 1
        assert result["files_added"] == 0
        assert result["files_reindexed"] == 0
        assert result["chunks_added"] == 0
        assert embedder.calls == 0
        assert store.counts() == (1, 0)
    finally:
        store.close()


def test_touched_but_identical_file_is_not_re_embedded(home, repo, write, embedder, clock):
    path = write(repo / "alpha.py", "def alpha():\n    return 1\n")
    store, indexer = make_indexer(home, embedder)
    try:
        indexer.refresh([repo])
        embedder.reset()

        stamp = clock.tick()
        os.utime(path, (stamp, stamp))  # same bytes, new mtime

        result = indexer.refresh([repo])
        assert result["files_unchanged"] == 1
        assert result["files_reindexed"] == 0
        assert embedder.calls == 0, "sha256 should have vetoed the re-embed"
        assert store.counts() == (1, 0)

        # The fast path must now recognise it, without a second hash.
        result = indexer.refresh([repo])
        assert result["files_unchanged"] == 1
    finally:
        store.close()


def test_changed_file_is_re_embedded_and_its_old_chunks_retired(
    home, repo, write, embedder
):
    write(repo / "alpha.py", "def alpha():\n    return 1\n")
    write(repo / "beta.py", "def beta():\n    return 2\n")
    store, indexer = make_indexer(home, embedder)
    try:
        indexer.refresh([repo])
        embedder.reset()

        write(repo / "alpha.py", "def alpha():\n    return 99\n# changed\n")
        result = indexer.refresh([repo])

        assert result["files_reindexed"] == 1
        assert result["files_unchanged"] == 1
        assert result["chunks_added"] == 1
        assert result["chunks_tombstoned"] == 1
        assert embedder.calls == 1
        assert "return 99" in "\n".join(embedder.texts)

        # 1 dead of 3 rows is past the 20% threshold, so the pass compacted.
        assert result["compacted"] is True
        assert store.counts() == (2, 0), "one live chunk per file, the old one gone"

        rows = store._live_rows()
        assert sorted(meta["path"] for meta in rows.values()) == sorted(
            [str(repo / "alpha.py"), str(repo / "beta.py")]
        )
    finally:
        store.close()


def test_a_file_growing_past_one_window_gains_chunks(home, repo, write, embedder):
    write(repo / "big.py", "".join(f"a = {i}\n" for i in range(30)))
    store, indexer = make_indexer(home, embedder)
    try:
        indexer.refresh([repo])
        assert store.counts() == (1, 0)

        write(repo / "big.py", "".join(f"a = {i}\n" for i in range(150)))
        result = indexer.refresh([repo])
        assert result["chunks_added"] == 3
        assert store.counts()[0] == 3
    finally:
        store.close()


def test_new_file_is_picked_up_on_the_next_pass(home, repo, write, embedder):
    write(repo / "alpha.py", "def alpha():\n    return 1\n")
    store, indexer = make_indexer(home, embedder)
    try:
        indexer.refresh([repo])
        embedder.reset()

        write(repo / "gamma.py", "def gamma():\n    return 3\n")
        result = indexer.refresh([repo])
        assert result["files_added"] == 1
        assert result["files_unchanged"] == 1
        assert embedder.calls == 1
    finally:
        store.close()


def test_ignored_paths_are_never_walked(home, repo, write, embedder):
    write(repo / "keep.py", "keep me\n")
    write(repo / "node_modules" / "dep" / "index.js", "drop me\n")
    write(repo / "bundle.min.js", "drop me too\n")
    write(repo / ".git" / "config", "[core]\n")
    store, indexer = make_indexer(
        home, embedder, ignore=["node_modules", "*.min.js", ".git"]
    )
    try:
        result = indexer.refresh([repo])
        assert result["scanned"] == 1
        assert result["files_added"] == 1
        assert [meta["path"] for meta in store._live_rows().values()] == [
            str(repo / "keep.py")
        ]
    finally:
        store.close()


def test_empty_file_is_recorded_but_produces_no_chunks(home, repo, write, embedder):
    write(repo / "empty.py", "")
    store, indexer = make_indexer(home, embedder)
    try:
        result = indexer.refresh([repo])
        assert result["chunks_added"] == 0
        assert embedder.calls == 0
        assert store.counts() == (0, 0)
        assert str(repo / "empty.py") in store.files_under([str(repo)])

        result = indexer.refresh([repo])
        assert result["files_unchanged"] == 1
        assert result["files_added"] == 0
    finally:
        store.close()


def test_failed_first_time_index_leaves_no_live_orphans_to_duplicate(
    home, repo, write, embedder
):
    """A new file split across multiple embed batches must be all-or-nothing.

    Before the fix, ``index_file`` called ``store.add()`` once per batch, so
    a failure on batch 2 left batch 1's chunks live with no matching file
    record. The next refresh then saw the file as brand-new again and
    re-added the same first batch permanently.
    """
    write(repo / "big.py", "".join(f"a = {i}\n" for i in range(150)))  # 3 chunks
    store = VectorStore(config.index_dir(home), dim=TEST_DIM)
    flaky = FlakyEmbedder(embedder, fail_after=1)
    indexer = Indexer(store, embed=flaky, ignore=["*.bin"], batch=1)
    try:
        with pytest.raises(RuntimeError):
            indexer.refresh([repo])
        # The failed attempt left nothing live and no file record - the next
        # pass will retry it cleanly rather than seeing it as unchanged.
        assert store.counts() == (0, 0)
        assert store.files_under([str(repo)]) == {}

        good = Indexer(store, embed=embedder, ignore=["*.bin"], batch=1)
        result = good.refresh([repo])
        assert result["files_added"] == 1
        assert result["chunks_added"] == 3
        assert store.counts() == (3, 0), "no duplicate rows from the failed attempt"
    finally:
        store.close()


def test_overlapping_roots_do_not_index_a_file_twice(home, repo, write, embedder):
    """A root and one of its own subdirectories, both configured, must not
    double-count or double-embed the files under the overlap."""
    write(repo / "pkg" / "alpha.py", "def alpha():\n    return 1\n")
    store, indexer = make_indexer(home, embedder)
    try:
        result = indexer.refresh([repo, repo / "pkg"])
        assert result["files_added"] == 1
        assert result["chunks_added"] == 1
        assert embedder.calls == 1
        assert store.counts() == (1, 0)
        assert len(store.files_under([str(repo)])) == 1
    finally:
        store.close()


def test_refresh_writes_a_manifest(home, repo, write, embedder):
    write(repo / "alpha.py", "def alpha():\n    return 1\n")
    store, indexer = make_indexer(home, embedder)
    try:
        indexer.refresh([repo])
        manifest = store.read_manifest()
        assert config.manifest_path(home).is_file()
        assert manifest["last_refresh"]["files_added"] == 1
        assert manifest["dim"] == TEST_DIM
        assert manifest["chunks"] == 1
    finally:
        store.close()
