"""Deleted files must vanish from results, and dead rows must not accumulate."""

from __future__ import annotations

import config
from conftest import TEST_DIM
from indexer import Indexer
from store import TOMBSTONE_COMPACT_RATIO, ChunkRecord, VectorStore


def make_indexer(home, embedder):
    store = VectorStore(config.index_dir(home), dim=TEST_DIM)
    return store, Indexer(store, embed=embedder, ignore=["*.bin"])


def paths_in(store):
    return sorted(meta["path"] for meta in store._live_rows().values())


def test_deleted_file_disappears_from_results(home, repo, write, embedder):
    for name in ("a.py", "b.py", "c.py", "d.py", "e.py"):
        write(repo / name, f"def {name[0]}():\n    return {name!r}\n")
    store, indexer = make_indexer(home, embedder)
    try:
        indexer.refresh([repo])
        assert len(paths_in(store)) == 5

        (repo / "c.py").unlink()
        result = indexer.refresh([repo])

        assert result["files_deleted"] == 1
        assert result["chunks_tombstoned"] == 1
        assert str(repo / "c.py") not in paths_in(store)
        assert str(repo / "c.py") not in store.files_under([str(repo)])

        # And it is gone from search, not merely from the bookkeeping.
        hits = store.search(embedder.vector("def c(): return c.py"), k=10)
        assert all(hit.path != str(repo / "c.py") for hit in hits)
        assert len(hits) == 4
    finally:
        store.close()


def test_deleting_one_of_five_stays_under_the_threshold(home, repo, write, embedder):
    for name in ("a.py", "b.py", "c.py", "d.py", "e.py"):
        write(repo / name, f"def {name[0]}():\n    return 1\n")
    store, indexer = make_indexer(home, embedder)
    try:
        indexer.refresh([repo])
        (repo / "c.py").unlink()
        result = indexer.refresh([repo])

        assert result["compacted"] is False, "1 of 5 is 20%, not more than 20%"
        assert store.tombstone_ratio() == 0.2
        assert store.row_count == 5, "the dead row is still on disk"
        assert store.counts() == (4, 1)
    finally:
        store.close()


def test_compaction_fires_past_the_threshold(home, repo, write, embedder):
    for name in ("a.py", "b.py", "c.py", "d.py", "e.py"):
        write(repo / name, f"def {name[0]}():\n    return 1\n")
    store, indexer = make_indexer(home, embedder)
    try:
        indexer.refresh([repo])
        (repo / "c.py").unlink()
        (repo / "d.py").unlink()
        result = indexer.refresh([repo])

        assert result["files_deleted"] == 2
        assert result["compacted"] is True, "2 of 5 is 40%, past the 20% threshold"
        assert store.counts() == (3, 0)
        assert store.row_count == 3, "the vector file was rewritten"
        assert paths_in(store) == sorted(
            str(repo / n) for n in ("a.py", "b.py", "e.py")
        )
    finally:
        store.close()


def test_compaction_renumbers_rows_contiguously(store, embedder):
    for index in range(10):
        store.add(
            [ChunkRecord(f"/repo/f{index}.py", 1, 5, f"sha{index}", 1.0, 10)],
            [embedder.vector(f"token{index}")],
        )
    assert store.row_count == 10

    store.tombstone_paths([f"/repo/f{i}.py" for i in (2, 5, 7)])
    assert store.tombstone_ratio() == 0.3
    assert store.maybe_compact() is True

    rows = store._live_rows()
    assert sorted(rows) == list(range(7)), "rows renumbered 0..6 with no holes"
    assert store.row_count == 7
    assert sorted(meta["path"] for meta in rows.values()) == sorted(
        f"/repo/f{i}.py" for i in (0, 1, 3, 4, 6, 8, 9)
    )


def test_compaction_preserves_which_vector_belongs_to_which_chunk(store, embedder):
    words = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot"]
    for word in words:
        store.add(
            [ChunkRecord(f"/repo/{word}.py", 1, 5, word, 1.0, 10)],
            [embedder.vector(word)],
        )

    before = store.search(embedder.vector("echo"), k=1)[0]
    assert before.path == "/repo/echo.py"

    store.tombstone_paths(["/repo/alpha.py", "/repo/bravo.py"])
    assert store.maybe_compact() is True

    after = store.search(embedder.vector("echo"), k=1)[0]
    assert after.path == "/repo/echo.py"
    assert after.score == before.score
    assert store.search(embedder.vector("alpha"), k=6)[0].path != "/repo/alpha.py"


def test_threshold_is_strictly_greater_than(store, embedder):
    for index in range(5):
        store.add(
            [ChunkRecord(f"/repo/f{index}.py", 1, 5, "sha", 1.0, 10)],
            [embedder.vector(f"t{index}")],
        )
    store.tombstone_paths(["/repo/f0.py"])
    assert store.tombstone_ratio() == TOMBSTONE_COMPACT_RATIO
    assert store.maybe_compact() is False
    assert store.row_count == 5

    store.tombstone_paths(["/repo/f1.py"])
    assert store.maybe_compact() is True
    assert store.row_count == 3


def test_tombstoning_is_idempotent(store, embedder):
    store.add(
        [ChunkRecord("/repo/one.py", 1, 5, "sha", 1.0, 10)],
        [embedder.vector("one")],
    )
    assert store.tombstone_paths(["/repo/one.py"]) == 1
    assert store.tombstone_paths(["/repo/one.py"]) == 0
    assert store.tombstone_paths([]) == 0
    assert store.search(embedder.vector("one"), k=5) == []


def test_compacting_an_index_with_no_live_rows_leaves_an_empty_file(store, embedder):
    store.add(
        [ChunkRecord("/repo/one.py", 1, 5, "sha", 1.0, 10)],
        [embedder.vector("one")],
    )
    store.tombstone_paths(["/repo/one.py"])
    assert store.maybe_compact() is True
    assert store.row_count == 0
    assert store.counts() == (0, 0)
    assert store.search(embedder.vector("one"), k=5) == []
