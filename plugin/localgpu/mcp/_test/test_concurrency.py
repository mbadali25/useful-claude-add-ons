"""The store is opened fresh per MCP tool call (see server._open_store), so
two calls racing each other get two independent VectorStore objects with no
shared state even though they touch the same files on disk - within one
process via threads, and across processes via two separate `server.py`.

See the comment on `_process_locks` in store.py and RefreshLock's docstring
for the two different mechanisms these tests cover.
"""

# These tests acquire and release RefreshLock by hand rather than with `with`,
# because the acquire/release SEQUENCE across interleaved holders is the thing
# under test - a `with` block would hide exactly the interleaving being
# checked. Module-level rather than per-call: an inline disable only applies
# from its own line onward, so the three call sites would each need their own.
# pylint: disable=unnecessary-dunder-call

from __future__ import annotations

import threading

import numpy as np
import pytest
from conftest import TEST_DIM

import config
import store as store_mod
from store import ChunkRecord, RefreshBusy, RefreshLock, StoreError


def test_live_rows_limit_excludes_rows_not_yet_trusted(store, embedder):
    """The primitive the search() fix relies on: `limit` bounds which rows
    are read back, independent of whatever `self.row_count` says right now."""
    for i in range(3):
        store.add(
            [ChunkRecord(f"/repo/f{i}.py", 1, 5, f"sha{i}", 1.0, 10)],
            [embedder.vector(f"t{i}")],
        )
    assert store.row_count == 3

    # Simulate a 4th row committed by someone else after a caller already
    # captured a 3-row matrix - append the bytes and the chunk row directly,
    # bypassing store.add() (which would take the lock this test is probing
    # around).
    with open(store.vectors_path, "ab") as handle:
        handle.write(np.asarray([embedder.vector("t3")], dtype=np.float16).tobytes())
    store.db.execute(
        'INSERT INTO chunks (path, start_line, end_line, sha256, mtime, size, "row") '
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("/repo/f3.py", 1, 5, "sha3", 1.0, 10, 3),
    )
    store.db.commit()
    assert store.row_count == 4

    # A caller that already has a 3-row matrix must not be handed row 3.
    candidates = store._live_rows(limit=3)
    assert 3 not in candidates

    # Asking fresh (the default) sees it, as any new search() call would.
    assert 3 in store._live_rows()


def test_search_does_not_raise_when_a_row_lands_between_matrix_and_metadata(
    store, embedder
):
    """Reproduces the exact bug: before the fix, search() built `matrix` from
    an N-row snapshot, then `_live_rows()` re-read a fresher `row_count` -
    so a row committed in that gap made `matrix[block]` raise IndexError.
    """
    for i in range(3):
        store.add(
            [ChunkRecord(f"/repo/f{i}.py", 1, 5, f"sha{i}", 1.0, 10)],
            [embedder.vector(f"t{i}")],
        )

    real_matrix = store._matrix

    def matrix_then_a_concurrent_append_lands(*args, **kwargs):
        matrix = real_matrix(*args, **kwargs)
        # This is what the old code's window let happen: another add()
        # completes after the matrix was captured but before the metadata
        # filter ran.
        with open(store.vectors_path, "ab") as handle:
            handle.write(
                np.asarray([embedder.vector("t3")], dtype=np.float16).tobytes()
            )
        store.db.execute(
            'INSERT INTO chunks (path, start_line, end_line, sha256, mtime, size, "row") '
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("/repo/f3.py", 1, 5, "sha3", 1.0, 10, 3),
        )
        store.db.commit()
        return matrix

    store._matrix = matrix_then_a_concurrent_append_lands
    try:
        hits = store.search(embedder.vector("t0"), k=10)  # must not raise IndexError
    finally:
        del store._matrix

    assert len(hits) == 3, "the row committed mid-search is correctly not included"


def test_search_blocks_a_concurrent_add_until_it_finishes(embedder, home, monkeypatch):
    """The lock introduced in store.py must actually be held across the
    whole of search(), not merely exist - proven with two real threads, not
    one thread re-entering an RLock (which would always succeed trivially).

    Each thread opens its own VectorStore, matching production: sqlite
    connections are thread-affine (see server._open_store's docstring), so
    two concurrent MCP tool calls always mean two connections to the same
    files. They must still share one lock, keyed by the physical vectors
    file rather than by Python object identity - that sharing is exactly
    what _process_lock() in store.py exists to provide.
    """
    seed = store_mod.VectorStore(config.index_dir(home), dim=TEST_DIM)
    seed.add([ChunkRecord("/repo/a.py", 1, 5, "sha", 1.0, 10)], [embedder.vector("a")])
    seed.close()

    entered = threading.Event()
    release = threading.Event()
    real_live_rows = store_mod.VectorStore._live_rows

    def blocked_live_rows(self, *args, **kwargs):
        entered.set()
        release.wait(timeout=2)
        return real_live_rows(self, *args, **kwargs)

    monkeypatch.setattr(store_mod.VectorStore, "_live_rows", blocked_live_rows)

    def do_search():
        searcher_store = store_mod.VectorStore(config.index_dir(home), dim=TEST_DIM)
        try:
            searcher_store.search(embedder.vector("a"), k=1)
        finally:
            searcher_store.close()

    searcher = threading.Thread(target=do_search)
    searcher.start()
    assert entered.wait(timeout=2), "search() never reached _live_rows()"

    added = threading.Event()

    def do_add():
        adder_store = store_mod.VectorStore(config.index_dir(home), dim=TEST_DIM)
        try:
            adder_store.add(
                [ChunkRecord("/repo/b.py", 1, 5, "sha2", 1.0, 10)],
                [embedder.vector("b")],
            )
        finally:
            adder_store.close()
        added.set()

    adder = threading.Thread(target=do_add)
    adder.start()
    finished_early = added.wait(timeout=0.2)
    assert not finished_early, "add() must block while search() holds the lock"

    release.set()
    searcher.join(timeout=2)
    adder.join(timeout=2)
    assert added.is_set()


def test_search_detects_a_racing_compaction_instead_of_misassigning_rows(
    store, embedder
):
    """SIMULATION, not the real cross-process race - this machine is
    Windows, where the race cannot actually occur (see below), so this
    fabricates the after-effect directly rather than pretending to
    reproduce it.

    The real bug: on Linux, POSIX allows replacing a file another process
    still has memory-mapped, so a *different* process's compact() can
    tombstone an earlier row and renumber the survivors while this
    process's `matrix` keeps serving pre-compaction bytes at pre-compaction
    offsets - `_live_rows()` re-reads sqlite fresh and sees the new
    (correct) row numbers, but pairing them with the stale `matrix` would
    silently score one file's metadata against a different file's vector.
    Windows instead refuses that same replace outright, raising
    PermissionError before the mismatch could ever happen - see
    `_replace_vectors_file`'s KNOWN PARTIAL docstring, which this is the
    mirror image of. A live memmap on this file would make Windows' own
    os.replace fail before this test could even set up the scenario, so
    here the "racing compact()" is fabricated directly: the exact sqlite
    state a real compact() would have committed (tombstoned row gone,
    survivor renumbered, generation bumped), applied without touching the
    real vectors.f16 file or closing the memmap - standing in for a
    separate process's compaction landing in the gap between `matrix` being
    captured and the row/path associations being resolved against it.
    """
    store.add([ChunkRecord("/repo/a.py", 1, 5, "sha_a", 1.0, 10)], [embedder.vector("a")])
    store.add([ChunkRecord("/repo/b.py", 1, 5, "sha_b", 1.0, 10)], [embedder.vector("b")])

    real_matrix = store._matrix

    def matrix_then_a_racing_compaction(*args, **kwargs):
        matrix = real_matrix(*args, **kwargs)
        # What a different process's compact() would already have committed
        # by the time this search resumes.
        store.db.execute("DELETE FROM chunks WHERE path = ?", ("/repo/a.py",))
        store.db.execute('UPDATE chunks SET "row" = 0 WHERE path = ?', ("/repo/b.py",))
        store.db.execute(
            "INSERT INTO meta (key, value) VALUES ('compaction_generation', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(store._compaction_generation() + 1),),
        )
        store.db.commit()
        return matrix

    store._matrix = matrix_then_a_racing_compaction
    try:
        with pytest.raises(StoreError, match="compacted by another process"):
            store.search(embedder.vector("a"), k=10)
    finally:
        del store._matrix


def test_refresh_lock_is_exclusive_across_separate_instances(tmp_path):
    """Simulates two separate `server.py` processes: two RefreshLock objects
    that share no Python state, only the lock file on disk."""
    index_dir = tmp_path / "index"
    first = RefreshLock(index_dir)
    first.__enter__()
    try:
        second = RefreshLock(index_dir)
        with pytest.raises(RefreshBusy):
            second.__enter__()
    finally:
        first.__exit__(None, None, None)

    # Released - a fresh attempt now succeeds.
    third = RefreshLock(index_dir)
    third.__enter__()
    third.__exit__(None, None, None)


def test_compact_reports_a_clear_error_instead_of_a_bare_permission_error(
    store, embedder, monkeypatch
):
    """The residual cross-process gap this lane does not fully close: a
    search() in a *different* process can still hold vectors.f16 memory-mapped
    when this process's compact() tries to replace it, and Windows refuses to
    replace a file another process has mapped. That must surface as a clear,
    actionable error - not a raw PermissionError, and not silently "succeed"
    while dropping rows.
    """
    store.add([ChunkRecord("/repo/a.py", 1, 5, "sha", 1.0, 10)], [embedder.vector("a")])
    store.add([ChunkRecord("/repo/b.py", 1, 5, "sha2", 1.0, 10)], [embedder.vector("b")])
    store.tombstone_paths(["/repo/a.py"])
    assert store.tombstone_ratio() == 0.5

    monkeypatch.setattr(store_mod.time, "sleep", lambda _seconds: None)

    def always_denied(*_args, **_kwargs):
        raise PermissionError("[WinError 32] the process cannot access the file")

    monkeypatch.setattr(store_mod.os, "replace", always_denied)

    with pytest.raises(StoreError, match="Retry index_refresh"):
        store.compact()

    # No data lost: the live row is untouched and still searchable.
    assert store.counts() == (1, 1)
    hits = store.search(embedder.vector("b"), k=5)
    assert any(hit.path == "/repo/b.py" for hit in hits)
