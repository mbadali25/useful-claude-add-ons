"""The index on disk: float16 vectors in a flat file, metadata in sqlite.

``vectors.f16`` is ``rows x dim`` little-endian float16 and nothing else - no
header, no padding - so row *n* lives at byte ``n * dim * 2`` and the whole
thing can be memmapped and scored in blocks. Every vector is stored already
L2-normalised, which makes cosine similarity a plain dot product.

``meta.sqlite`` holds one row per chunk (path, line span, the file's sha256,
mtime, size, the row offset above, and a tombstone flag) plus one row per file
for the incremental scan.

Deletes are tombstones, because rewriting a 200 MB vector file to remove one
chunk is absurd. Once more than 20% of the rows are dead the file is compacted
and every surviving row is renumbered.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import threading
import time
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence

import numpy as np

# This directory is named `mcp`, which is also the SDK's package name, so it
# must not become an importable package - `import mcp` would find it instead of
# the SDK. Siblings are therefore imported flat, off an explicit sys.path entry.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from config import EMBED_DIM  # noqa: E402

# Strictly greater than this fraction of dead rows triggers a compaction.
TOMBSTONE_COMPACT_RATIO = 0.20

# Rows scored per block. Keeps the float32 working copy of the matrix bounded
# no matter how large the index grows.
_SCORE_BLOCK = 4096

# server.py opens a fresh VectorStore per MCP tool call, in the calling
# thread (see its _open_store docstring) - so two calls racing each other
# (a search and a refresh, or two refreshes) get two independent Python
# objects with no shared state, even though they touch the same files on
# disk. A per-instance lock would do nothing; this registers one RLock per
# *physical* vectors file, shared by every VectorStore that opens it, so
# search()/add()/compact() are mutually exclusive within one process. This
# closes the same-process half of the race: a search's memmap is held (and
# a refresh's compact() cannot os.replace() the file out from under it)
# only while another thread genuinely holds the same lock, not merely while
# the same code happens to be running.
#
# It does NOT reach across processes - two separate `python server.py`
# processes (e.g. two Claude sessions on the same repo) get separate
# _process_locks dicts. That half is handled by RefreshLock below, and the
# residual gap between the two (a search in process B racing a compact in
# process A) is handled by compact()'s loud retry-then-report rather than
# claimed as fixed - see the comment on compact().
_process_locks: dict[str, threading.RLock] = {}
_process_locks_guard = threading.Lock()


def _process_lock(vectors_path: Path) -> threading.RLock:
    key = os.path.normcase(str(vectors_path))
    with _process_locks_guard:
        lock = _process_locks.get(key)
        if lock is None:
            lock = threading.RLock()
            _process_locks[key] = lock
        return lock


def _try_lock_file_exclusive(handle) -> bool:
    """Best-effort, non-blocking, whole-file exclusive advisory lock.

    True if acquired. Advisory: only cooperating code (RefreshLock below) is
    stopped by it - it is not a filesystem permission.
    """
    if os.name == "nt":
        import msvcrt

        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock_file(handle) -> None:
    if os.name == "nt":
        import msvcrt

        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        return
    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


class RefreshBusy(RuntimeError):
    """Another process already holds the cross-process refresh lock."""


class RefreshLock:
    """An OS-level lock so two *processes* cannot both refresh one index.

    ``server.py``'s ``_refresh_lock`` is a ``threading.Lock`` - real
    protection against two threads in one process, nothing at all against a
    second Claude session running its own ``server.py`` against the same
    index directory. Without this, two concurrent refreshes could both
    append and both compact the same ``vectors.f16``; the second one's
    ``compact()`` reads the chunk table as of *its* read, so any row the
    first refresh committed after that read is live in sqlite (tombstone=0)
    but silently absent from the rewritten vector file the moment
    ``os.replace`` lands - a "successful" refresh that just deleted another
    session's vectors while keeping their metadata.

    Acquired for the whole refresh pass, not just the compact step, because
    add() is just as capable of interleaving badly with a concurrent
    compact()'s read of the chunk table. Non-blocking: a second process (or
    a stray second thread that skipped the in-process lock) is told
    immediately that a refresh is already running, rather than blocking or
    racing.
    """

    def __init__(self, index_dir: Path | str) -> None:
        self.path = Path(index_dir) / "refresh.lock"
        self._handle = None

    def __enter__(self) -> "RefreshLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+b")
        if not _try_lock_file_exclusive(handle):
            handle.close()
            raise RefreshBusy(
                f"another process already holds the refresh lock at {self.path}"
            )
        self._handle = handle
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._handle is not None:
            _unlock_file(self._handle)
            self._handle.close()
            self._handle = None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    path       TEXT    NOT NULL,
    start_line INTEGER NOT NULL,
    end_line   INTEGER NOT NULL,
    sha256     TEXT    NOT NULL,
    mtime      REAL    NOT NULL,
    size       INTEGER NOT NULL,
    "row"      INTEGER NOT NULL UNIQUE,
    tombstone  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS chunks_path_idx ON chunks (path);
CREATE INDEX IF NOT EXISTS chunks_live_idx ON chunks (tombstone);

CREATE TABLE IF NOT EXISTS files (
    path       TEXT PRIMARY KEY,
    root       TEXT NOT NULL,
    sha256     TEXT NOT NULL,
    mtime      REAL NOT NULL,
    size       INTEGER NOT NULL,
    chunks     INTEGER NOT NULL,
    indexed_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class StoreError(RuntimeError):
    """The index on disk cannot be used as-is."""


@dataclass(frozen=True)
class ChunkRecord:
    """One window of one file, before it has a row number."""

    path: str
    start_line: int
    end_line: int
    sha256: str
    mtime: float
    size: int


@dataclass(frozen=True)
class FileRecord:
    path: str
    root: str
    sha256: str
    mtime: float
    size: int
    chunks: int


@dataclass(frozen=True)
class Hit:
    chunk_id: int
    path: str
    start_line: int
    end_line: int
    score: float


def normalise(vectors: Sequence[Sequence[float]] | np.ndarray) -> np.ndarray:
    """L2-normalise to float32. A zero vector stays zero rather than becoming NaN."""
    matrix = np.asarray(vectors, dtype=np.float32)
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return matrix / norms


class VectorStore:
    """Owns ``vectors.f16`` and ``meta.sqlite`` in one directory."""

    def __init__(self, index_dir: Path | str, dim: int = EMBED_DIM) -> None:
        self.dir = Path(index_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.dim = int(dim)
        self.vectors_path = self.dir / "vectors.f16"
        self.meta_path = self.dir / "meta.sqlite"
        self.manifest_path = self.dir / "manifest.json"
        self._mm: np.memmap | None = None
        # Shared across every VectorStore instance opened on this same
        # vectors file within this process - see the comment above
        # _process_locks for why a per-instance lock would not help.
        self._lock = _process_lock(self.vectors_path)

        self.db = sqlite3.connect(self.meta_path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)
        self._check_dim()

    # -- lifecycle ---------------------------------------------------------

    def _check_dim(self) -> None:
        stored = self.get_meta("dim")
        if stored is None:
            self.set_meta("dim", str(self.dim))
            return
        if int(stored) != self.dim:
            raise StoreError(
                f"{self.meta_path} was built with {stored}-dimensional vectors, "
                f"but this run expects {self.dim}. Changing the embed model means "
                "rebuilding: delete the index directory and run index_refresh."
            )

    def close(self) -> None:
        self._close_memmap()
        self.db.close()

    def __enter__(self) -> "VectorStore":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _close_memmap(self) -> None:
        # Windows will not let the file be replaced while a mapping is open.
        if self._mm is not None:
            mapping = getattr(self._mm, "_mmap", None)
            if mapping is not None:
                mapping.close()
            self._mm = None

    def _matrix(self) -> np.memmap | None:
        rows = self.row_count
        if rows == 0:
            return None
        if self._mm is None or self._mm.shape[0] != rows:
            self._close_memmap()
            self._mm = np.memmap(
                self.vectors_path, dtype=np.float16, mode="r", shape=(rows, self.dim)
            )
        return self._mm

    # -- metadata ----------------------------------------------------------

    def get_meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row["value"])

    def set_meta(self, key: str, value: str) -> None:
        self.db.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )
        self.db.commit()

    @property
    def row_count(self) -> int:
        """Rows physically present in the vector file, dead ones included."""
        try:
            return self.vectors_path.stat().st_size // (self.dim * 2)
        except FileNotFoundError:
            return 0

    def counts(self) -> tuple[int, int]:
        """``(live chunks, tombstoned chunks)``."""
        row = self.db.execute(
            "SELECT SUM(tombstone = 0) AS live, SUM(tombstone = 1) AS dead FROM chunks"
        ).fetchone()
        return int(row["live"] or 0), int(row["dead"] or 0)

    def count_live_chunks(self, path: str) -> int:
        """Live (non-tombstoned) chunk rows recorded for one file path.

        A matching ``files.sha256`` is not by itself proof that this path
        still has live vectors - a refresh that tombstoned the old chunks
        for a change and then failed the re-embed (before ``upsert_file``
        recorded the new hash) leaves the *old* ``FileRecord`` in place with
        its *old* hash. If the file is later restored to that old content,
        the hash matches again while every chunk it once had is dead. The
        caller (``Indexer.refresh``) uses this to confirm live chunks
        actually back a hash match before trusting it as "nothing to do".
        """
        row = self.db.execute(
            "SELECT COUNT(*) AS n FROM chunks WHERE path = ? AND tombstone = 0",
            (path,),
        ).fetchone()
        return int(row["n"] or 0)

    def _compaction_generation(self) -> int:
        """Bumped by every :meth:`compact` - see the check in :meth:`search`."""
        return int(self.get_meta("compaction_generation") or 0)

    # -- writing -----------------------------------------------------------

    def add(
        self,
        records: Sequence[ChunkRecord],
        vectors: Sequence[Sequence[float]] | np.ndarray,
    ) -> list[int]:
        """Append chunks and their vectors. Returns the new chunk ids."""
        if not records:
            return []
        matrix = normalise(vectors)
        if matrix.shape[0] != len(records):
            raise ValueError(
                f"{len(records)} chunk(s) but {matrix.shape[0]} vector(s)"
            )
        if matrix.shape[1] != self.dim:
            raise ValueError(
                f"vectors are {matrix.shape[1]}-dimensional, index expects {self.dim}"
            )

        # Mutually exclusive with search()/compact() in this process - see
        # the comment on _process_locks.
        with self._lock:
            first_row = self.row_count
            self._close_memmap()
            with open(self.vectors_path, "ab") as handle:
                handle.write(matrix.astype(np.float16, copy=False).tobytes(order="C"))

            ids: list[int] = []
            cursor = self.db.cursor()
            for offset, record in enumerate(records):
                cursor.execute(
                    'INSERT INTO chunks (path, start_line, end_line, sha256, mtime, size, "row")'
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        record.path,
                        record.start_line,
                        record.end_line,
                        record.sha256,
                        record.mtime,
                        record.size,
                        first_row + offset,
                    ),
                )
                ids.append(int(cursor.lastrowid or 0))
            self.db.commit()
            return ids

    def tombstone_paths(self, paths: Iterable[str]) -> int:
        """Mark every live chunk of these files dead. Returns how many."""
        paths = list(paths)
        if not paths:
            return 0
        before = self.db.total_changes
        self.db.executemany(
            "UPDATE chunks SET tombstone = 1 WHERE path = ? AND tombstone = 0",
            [(p,) for p in paths],
        )
        self.db.commit()
        return int(self.db.total_changes - before)

    def upsert_file(self, record: FileRecord) -> None:
        self.db.execute(
            "INSERT INTO files (path, root, sha256, mtime, size, chunks, indexed_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(path) DO UPDATE SET root = excluded.root,"
            " sha256 = excluded.sha256, mtime = excluded.mtime, size = excluded.size,"
            " chunks = excluded.chunks, indexed_at = excluded.indexed_at",
            (
                record.path,
                record.root,
                record.sha256,
                record.mtime,
                record.size,
                record.chunks,
                time.time(),
            ),
        )
        self.db.commit()

    def forget_files(self, paths: Iterable[str]) -> None:
        paths = list(paths)
        if not paths:
            return
        self.db.executemany("DELETE FROM files WHERE path = ?", [(p,) for p in paths])
        self.db.commit()

    def files_under(self, roots: Sequence[str] | None = None) -> dict[str, FileRecord]:
        """Every known file, or only those recorded under the given roots."""
        rows = self.db.execute(
            "SELECT path, root, sha256, mtime, size, chunks FROM files"
        ).fetchall()
        out: dict[str, FileRecord] = {}
        keys = [_prefix_key(r) for r in (roots or [])]
        for row in rows:
            if keys and not any(_under(str(row["path"]), k) for k in keys):
                continue
            out[str(row["path"])] = FileRecord(
                path=str(row["path"]),
                root=str(row["root"]),
                sha256=str(row["sha256"]),
                mtime=float(row["mtime"]),
                size=int(row["size"]),
                chunks=int(row["chunks"]),
            )
        return out

    # -- searching ---------------------------------------------------------

    def search(
        self,
        query: Sequence[float] | np.ndarray,
        k: int = 10,
        root: str | None = None,
        path_glob: str | None = None,
    ) -> list[Hit]:
        """Brute-force cosine over every live row, best first."""
        if k <= 0:
            return []
        # Held for the whole read, including the scoring loop below, not
        # just the matrix() call: without this, a concurrent add()/compact()
        # in another thread of this process could still land mid-search -
        # the exact interleaving this lock exists to rule out. Scoring is
        # cheap numpy work, so holding it this long is not a bottleneck. See
        # _process_locks.
        with self._lock:
            generation = self._compaction_generation()
            matrix = self._matrix()
            if matrix is None:
                return []
            # The chunk table is read fresh every search (rows tombstoned or
            # added since the last call must be reflected), but it must be
            # filtered against the row count *this* matrix was built from,
            # not a fresh self.row_count read - those two could previously
            # disagree if something appended between the two reads, and a
            # candidate row >= matrix.shape[0] made the block index below
            # raise IndexError instead of just being newer than this search.
            #
            # This closes the IndexError structurally, not by catching it:
            # `limit` here can never exceed matrix.shape[0], so `matrix[block]`
            # below can never be handed an out-of-range row, regardless of
            # what appended concurrently, in this process or another. Unlike
            # compact()'s os.replace() below, there is no residual gap here to
            # paper over with a caught exception.
            candidates = self._live_rows(
                root=root, path_glob=path_glob, limit=matrix.shape[0]
            )
            if not candidates:
                return []

            # `_process_locks` only rules out another THREAD OF THIS PROCESS
            # compacting mid-search. A different process's compact() renumbers
            # `chunks."row"` in sqlite (visible to `candidates` above the
            # instant it commits) but cannot invalidate `matrix` here - on
            # POSIX, replacing a file another process has memory-mapped is
            # allowed, so `matrix` keeps quietly serving pre-compaction bytes
            # at pre-compaction offsets (Windows instead refuses that replace
            # outright and raises PermissionError - see the KNOWN PARTIAL note
            # on `_replace_vectors_file`; same cross-process gap, its other
            # platform face). Scoring `candidates`' new row numbers against
            # `matrix`'s old bytes would silently pair a row's stale vector
            # with a different file's metadata. `compaction_generation` is
            # bumped inside the same sqlite transaction `compact()` uses to
            # renumber rows, so a change here proves that race happened in
            # this exact window - closing it for real needs search() to also
            # take the cross-process lock (a materially bigger change than
            # this lane covers), so this raises loudly instead.
            if self._compaction_generation() != generation:
                raise StoreError(
                    f"{self.vectors_path} was compacted by another process "
                    "while this search was reading it - results would be "
                    "unreliable. Retry the search."
                )

            vector = normalise(query)[0]
            rows = np.fromiter(
                (r for r in candidates), dtype=np.int64, count=len(candidates)
            )
            scores = np.empty(rows.shape[0], dtype=np.float32)
            for start in range(0, rows.shape[0], _SCORE_BLOCK):
                block = rows[start : start + _SCORE_BLOCK]
                scores[start : start + block.shape[0]] = (
                    np.asarray(matrix[block], dtype=np.float32) @ vector
                )

            k = min(k, scores.shape[0])
            top = np.argpartition(-scores, k - 1)[:k]
            top = top[np.argsort(-scores[top], kind="stable")]

            hits: list[Hit] = []
            for position in top:
                meta = candidates[int(rows[position])]
                hits.append(
                    Hit(
                        chunk_id=meta["id"],
                        path=meta["path"],
                        start_line=meta["start_line"],
                        end_line=meta["end_line"],
                        score=float(scores[position]),
                    )
                )
            return hits

    def _live_rows(
        self,
        root: str | None = None,
        path_glob: str | None = None,
        limit: int | None = None,
    ) -> dict[int, dict[str, Any]]:
        """Live chunks that pass the filters, keyed by vector row.

        ``limit`` bounds which rows are trusted as real - by default (and
        for every caller outside ``search()``) that is ``self.row_count``,
        a fresh read. ``search()`` passes the row count of the specific
        memmap it already captured, so a concurrent append between the two
        reads cannot let through a row index that memmap does not have.
        """
        rows = self.db.execute(
            'SELECT id, path, start_line, end_line, "row" FROM chunks '
            "WHERE tombstone = 0"
        ).fetchall()

        # Filtering happens here rather than in SQL: LIKE has its own escaping
        # rules and its own opinion about case, and neither matches a path.
        prefix = _prefix_key(root) if root else None
        limit = self.row_count if limit is None else limit
        out: dict[int, dict[str, Any]] = {}
        for row in rows:
            index = int(row["row"])
            if index >= limit:
                continue  # a half-written append; ignore rather than read garbage
            path = str(row["path"])
            if prefix and not _under(path, prefix):
                continue
            if path_glob and not match_glob(path, path_glob):
                continue
            out[index] = {
                "id": int(row["id"]),
                "path": path,
                "start_line": int(row["start_line"]),
                "end_line": int(row["end_line"]),
            }
        return out

    # -- compaction --------------------------------------------------------

    def tombstone_ratio(self) -> float:
        live, dead = self.counts()
        total = live + dead
        return 0.0 if total == 0 else dead / total

    def maybe_compact(self, ratio: float = TOMBSTONE_COMPACT_RATIO) -> bool:
        """Compact only once the dead rows are worth the rewrite."""
        if self.tombstone_ratio() > ratio:
            self.compact()
            return True
        return False

    def compact(self) -> int:
        """Rewrite the vector file with the live rows only. Returns rows dropped."""
        # Mutually exclusive with add()/search() in this process (see
        # _process_locks): the read of `keep` below and the read of
        # `source` must not have a concurrent add() land between them, or
        # the rewritten file would silently drop rows that are live in
        # sqlite - a "successful" compaction that just deleted someone
        # else's just-committed vectors.
        with self._lock:
            live, dead = self.counts()
            if dead == 0:
                return 0

            keep = self.db.execute(
                'SELECT id, "row" FROM chunks WHERE tombstone = 0 ORDER BY "row"'
            ).fetchall()
            source = self._matrix()
            temp = self.vectors_path.with_suffix(".f16.compacting")

            with open(temp, "wb") as handle:
                if source is not None and keep:
                    rows = np.fromiter(
                        (int(r["row"]) for r in keep), dtype=np.int64, count=len(keep)
                    )
                    for start in range(0, rows.shape[0], _SCORE_BLOCK):
                        block = rows[start : start + _SCORE_BLOCK]
                        handle.write(
                            np.asarray(source[block], dtype=np.float16).tobytes()
                        )

            self._close_memmap()
            self._replace_vectors_file(temp)

            self.db.execute("DELETE FROM chunks WHERE tombstone = 1")
            self.db.executemany(
                'UPDATE chunks SET "row" = ? WHERE id = ?',
                [(new_row, int(r["id"])) for new_row, r in enumerate(keep)],
            )
            # Committed in the same transaction as the renumbering above, so
            # any reader (this process or another) that observes the bump
            # also observes the new row numbers, never the old numbers with
            # a bumped generation or vice versa. See the check in search().
            self.db.execute(
                "INSERT INTO meta (key, value) VALUES ('compaction_generation', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(self._compaction_generation() + 1),),
            )
            self.db.commit()
            self.db.execute("VACUUM")
            if self.row_count != live:
                raise StoreError(
                    f"compaction left {self.row_count} row(s) on disk for {live} live "
                    f"chunk(s) in {self.vectors_path}"
                )
            return dead

    def _replace_vectors_file(self, temp: Path) -> None:
        """``os.replace`` the compacted file in, tolerating a lingering reader.

        The in-process lock above rules out another thread of *this*
        process holding the memmap - it cannot reach a second `server.py`
        process on the same repo (a separate Claude session), whose
        search() may still have ``vectors.f16`` memory-mapped when this
        compaction tries to replace it. Windows refuses to replace a file
        that any process still has mapped, raising ``PermissionError``.
        This is not silently retried into looking fine: a few short retries
        give a fast-finishing reader a chance to close its handle (a
        search's memmap is closed as soon as its ``store.close()`` runs -
        see ``server._open_store`` and every tool's ``finally`` block), and
        if it still fails, the error surfaces with an actionable message
        instead of a bare ``PermissionError`` traceback, so a cross-process
        race lands as a clear "retry" rather than either corruption or a
        confusing crash.

        KNOWN PARTIAL - not a placeholder pending a follow-up patch, a
        deliberate boundary. Closing this gap for real would mean search()
        also taking the cross-process lock (shared-mode, so concurrent
        searches from different sessions do not needlessly serialise) - a
        materially bigger change than this lane covers. Do not "simplify"
        the retry loop or the ``except PermissionError`` down to a bare
        ``os.replace()`` call: the error it is catching is a real, recurring
        cross-process race on Windows, not a hypothetical. Only
        ``PermissionError`` is caught here on purpose - anything else
        propagates unchanged, so a genuine bug is never relabelled as "busy,
        retry".

        This is one problem with two platform faces, not two unrelated ones.
        Here, on Windows, the OS itself refuses the replace outright, so the
        race surfaces as a loud, retryable error and no data is ever
        misread. On Linux, POSIX allows the exact same replace to succeed
        while another process still has the old file memory-mapped - there
        is no refusal to catch, so that process's `search()` can keep
        scoring pre-compaction bytes against post-compaction row numbers
        with no exception raised at all. See the `compaction_generation`
        check in `search()` for how that silent half is turned back into a
        loud one.
        """
        last: OSError | None = None
        for attempt in range(5):
            try:
                os.replace(temp, self.vectors_path)
                return
            except PermissionError as exc:
                last = exc
                if attempt < 4:
                    time.sleep(0.05 * (attempt + 1))
        temp.unlink(missing_ok=True)
        raise StoreError(
            f"could not replace {self.vectors_path} during compaction - "
            "another process likely still has it open (e.g. a concurrent "
            "search_code in a different Claude session). No data was lost: "
            f"the compacted rows were never written. Retry index_refresh()."
        ) from last

    # -- reporting ---------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        live, dead = self.counts()
        files = int(
            self.db.execute("SELECT COUNT(*) AS n FROM files").fetchone()["n"] or 0
        )
        return {
            "index_dir": str(self.dir),
            "files": files,
            "chunks": live,
            "tombstoned": dead,
            "tombstone_ratio": round(self.tombstone_ratio(), 4),
            "rows_on_disk": self.row_count,
            "dim": self.dim,
            "vectors_bytes": (
                self.vectors_path.stat().st_size if self.vectors_path.exists() else 0
            ),
            "meta_bytes": (
                self.meta_path.stat().st_size if self.meta_path.exists() else 0
            ),
        }

    def write_manifest(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        manifest = self.stats()
        manifest["updated_at"] = time.time()
        manifest.update(extra or {})
        self.manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        return manifest

    def read_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.is_file():
            return {}
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}


def _prefix_key(root: str | Path) -> str:
    """A normalised ``root`` that only matches whole path components."""
    return os.path.normcase(str(Path(root))).rstrip("\\/") + os.sep


def _under(path: str, prefix_key: str) -> bool:
    normalised = os.path.normcase(path)
    return normalised.startswith(prefix_key) or normalised == prefix_key.rstrip(os.sep)


def match_glob(path: str, pattern: str) -> bool:
    """Forgiving glob match against a full path or its basename.

    ``*`` crosses directory separators here, so ``*.py``, ``**/*.py`` and
    ``src/*.py`` all do the obvious thing on ``C:/x/src/a.py``.
    """
    posix = PurePosixPath(Path(path).as_posix())
    text = str(posix)
    candidates = (text, posix.name)
    patterns = (pattern, pattern.replace("**/", "*"))
    return any(fnmatch(c, p) for c in candidates for p in patterns)
