"""Walk the roots, cut files into overlapping windows, embed what changed.

Windows are 60 lines with 15 lines of overlap, so a function that starts near a
window boundary is still whole in the next one. Re-indexing is incremental:
mtime and size decide whether a file is even worth hashing, and the sha256
decides whether it is worth embedding. Files that have vanished have their
chunks tombstoned, and the store compacts itself once enough of them pile up.
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Sequence

# This directory is named `mcp`, which is also the SDK's package name, so it
# must not become an importable package - `import mcp` would find it instead of
# the SDK. Siblings are therefore imported flat, off an explicit sys.path entry.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from config import EMBED_DIM  # noqa: E402
from store import ChunkRecord, FileRecord, VectorStore  # noqa: E402

WINDOW_LINES = 60
OVERLAP_LINES = 15

# Files above this are generated, vendored, or data. Embedding them costs GPU
# time and buries the code you were looking for.
MAX_FILE_BYTES = 1_000_000

# Chunks per embed request. Small enough that one request does not pin the
# embed model for long on an 8 GB card.
EMBED_BATCH = 16

# nomic-embed-text is trained with task prefixes; documents and queries get
# different ones. Mixing them up costs real retrieval quality.
DOC_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "

Embedder = Callable[[Sequence[str]], Sequence[Sequence[float]]]


@dataclass(frozen=True)
class Chunk:
    start_line: int  # 1-based, inclusive
    end_line: int  # 1-based, inclusive
    text: str


def chunk_lines(
    lines: Sequence[str],
    window: int = WINDOW_LINES,
    overlap: int = OVERLAP_LINES,
) -> list[Chunk]:
    """Cut lines into overlapping windows.

    An empty file yields no chunks. A file shorter than one window yields
    exactly one. The last window always ends on the last line rather than
    being padded, and no window is emitted that the previous one already
    covered entirely.
    """
    if window <= 0:
        raise ValueError("window must be positive")
    if not 0 <= overlap < window:
        raise ValueError("overlap must be at least 0 and smaller than window")

    total = len(lines)
    if total == 0:
        return []

    step = window - overlap
    chunks: list[Chunk] = []
    start = 0
    while start < total:
        end = min(start + window, total)
        chunks.append(
            Chunk(
                start_line=start + 1,
                end_line=end,
                text="".join(lines[start:end]),
            )
        )
        if end >= total:
            break
        start += step
    return chunks


def is_ignored(path: Path, root: Path, patterns: Sequence[str]) -> bool:
    """Match a pattern against the name, the path relative to the root, or any parent."""
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        relative = path.as_posix()
    parts = relative.split("/")
    for pattern in patterns:
        clean = pattern.rstrip("/")
        if not clean:
            continue
        if fnmatch(path.name, clean) or fnmatch(relative, clean):
            return True
        if clean in parts:
            return True
        if clean.startswith("**/") and fnmatch(relative, clean[3:]):
            return True
    return False


def iter_files(root: Path, patterns: Sequence[str]) -> Iterator[Path]:
    """Every candidate file under ``root``, ignored directories pruned as we go."""
    root = Path(root)
    if root.is_file():
        if not is_ignored(root, root.parent, patterns):
            yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        dirnames[:] = sorted(
            d for d in dirnames if not is_ignored(here / d, root, patterns)
        )
        for name in sorted(filenames):
            candidate = here / name
            if not is_ignored(candidate, root, patterns):
                yield candidate


def read_text_file(path: Path) -> list[str] | None:
    """Lines with their endings kept, or ``None`` if this is not text we index."""
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw[:4096]:
        return None  # binary
    text = raw.decode("utf-8", "replace")
    return text.splitlines(keepends=True)


def sha256_bytes(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def document_text(path: Path, chunk: Chunk, root: Path | None = None) -> str:
    """What actually gets embedded: a locator line, then the code."""
    try:
        label = path.relative_to(root).as_posix() if root else path.as_posix()
    except ValueError:
        label = path.as_posix()
    return f"{DOC_PREFIX}{label}:{chunk.start_line}-{chunk.end_line}\n{chunk.text}"


def query_text(query: str) -> str:
    return f"{QUERY_PREFIX}{query}"


class EmbedModelMismatch(RuntimeError):
    """The index on disk was built with a different embedding model.

    Vectors from two embedding models are not comparable even when both
    happen to produce the same width - the store's own dimension check would
    stay silent, cosine similarity between them is meaningless, and nothing
    in a search result would show the mismatch. That makes it the wrong kind
    of failure to paper over: this is raised rather than absorbed, so a stale
    index never looks fine.

    This is refused rather than auto-repaired on purpose. "Auto" on an
    incremental refresh would really mean "silently force a full rebuild" -
    and the files most likely to be carrying stale vectors are exactly the
    mtime/size-unchanged ones an incremental pass skips, so a quiet fix-up
    would leave the worst-affected files untouched while claiming success.
    A full rebuild is a deliberate, confirmed, GPU-minutes decision
    elsewhere in this plugin (see commands/index.md); it does not become
    an implicit side effect of a routine refresh just because this check
    exists.
    """


def check_embed_model(
    manifest: dict[str, Any],
    embed_model: str | None,
    *,
    store_has_content: bool = False,
) -> None:
    """Raise :class:`EmbedModelMismatch` if ``manifest`` was not built with ``embed_model``.

    Shared by every path that touches the vectors on disk - a refresh
    (:meth:`Indexer._check_embed_model`) and a search
    (``server.search_code``) alike. A dimension check cannot catch this: two
    different models can emit the same width, and cosine similarity between
    their vectors is meaningless even though it happily produces a score.

    Absent is not a match: a manifest with no ``embed_model`` key predates
    this check and must be treated as unknown, not as agreement.

    ``store_has_content`` distinguishes a genuinely empty index (nothing
    built yet, nothing to conflict with) from one whose ``manifest.json`` is
    merely missing while live vectors already exist on disk - which happens
    when an *initial* refresh embeds some files under one model and then
    fails before ``write_manifest`` ever runs. A caller that only checked
    "is there a manifest" would see none and wave a later refresh under a
    different same-width model through, which then certifies the resulting
    mix of both models' vectors as if it were built entirely with the new
    one. So a missing manifest is safe to treat as "nothing built yet" only
    when the store backs that up - otherwise it is treated exactly like a
    manifest that exists but predates this check.
    """
    if embed_model is None:
        return
    if not manifest and not store_has_content:
        return  # no manifest at all, no vectors either - nothing built yet
    stored = None if not manifest else manifest.get("embed_model")
    if stored is None:
        raise EmbedModelMismatch(
            "the existing index has no recorded embed_model (it predates "
            "this check), so it cannot be confirmed to match the "
            f"configured model {embed_model!r}. If the embed model "
            "has not changed, this is safe to ignore only by rebuilding "
            "to record it; otherwise delete the index and rebuild with "
            "index_refresh (or /localgpu:index --full)."
        )
    if stored != embed_model:
        raise EmbedModelMismatch(
            f"the index was built with embed_model {stored!r}, but "
            f"{embed_model!r} is configured now. Vectors from "
            "different models are not comparable even at the same width. "
            "Delete the index and rebuild with index_refresh (or "
            "/localgpu:index --full)."
        )


class Indexer:
    """Drives one refresh pass over the configured roots."""

    def __init__(
        self,
        store: VectorStore,
        embed: Embedder,
        ignore: Sequence[str] = (),
        batch: int = EMBED_BATCH,
        embed_model: str | None = None,
    ) -> None:
        self.store = store
        self.embed = embed
        self.ignore = list(ignore)
        self.batch = max(1, int(batch))
        # ``None`` means the caller did not tell us what model it configured -
        # e.g. an older call site that predates this check. We then neither
        # verify nor record it, rather than guessing.
        self.embed_model = embed_model

    # -- embed model bookkeeping ---------------------------------------------

    def _check_embed_model(self) -> None:
        """Refuse to touch an index built with a different embedding model.

        Absent is not a match: a manifest with no ``embed_model`` key predates
        this check and must be treated as unknown, not as agreement - it may
        or may not have been built with the model configured now, and there is
        no way to tell which. That includes a manifest that is missing
        entirely while the store already holds live chunks - a failed
        *initial* refresh never reaches ``write_manifest``, but any files it
        embedded before failing are already live vectors of unknown
        provenance (see ``check_embed_model``'s ``store_has_content``).
        """
        live, _dead = self.store.counts()
        check_embed_model(
            self.store.read_manifest(), self.embed_model, store_has_content=live > 0
        )

    # -- one file ----------------------------------------------------------

    def index_file(self, path: Path, root: Path) -> int:
        """Embed every window of one file and append it. Returns chunks added."""
        lines = read_text_file(path)
        if lines is None:
            return 0
        chunks = chunk_lines(lines)
        if not chunks:
            # A real but empty file. Record it so it is not rescanned as new.
            stat = path.stat()
            self.store.upsert_file(
                FileRecord(
                    path=str(path),
                    root=str(root),
                    sha256=sha256_bytes(path),
                    mtime=stat.st_mtime,
                    size=stat.st_size,
                    chunks=0,
                )
            )
            return 0

        stat = path.stat()
        digest = sha256_bytes(path)

        # Every batch is embedded before anything is written to the store.
        # store.add() appends live rows immediately - if it ran per batch and
        # a later batch's embed() call failed, the earlier batches' chunks
        # would already be live with no matching file record (upsert_file
        # below never runs), so the next refresh sees this as a brand-new
        # file and re-adds them, duplicating those rows permanently. Failing
        # before the first add() call means a failed file leaves nothing
        # behind to duplicate.
        all_records: list[ChunkRecord] = []
        all_vectors: list[Sequence[float]] = []
        for start in range(0, len(chunks), self.batch):
            window = chunks[start : start + self.batch]
            vectors = self.embed([document_text(path, c, root) for c in window])
            all_records.extend(
                ChunkRecord(
                    path=str(path),
                    start_line=c.start_line,
                    end_line=c.end_line,
                    sha256=digest,
                    mtime=stat.st_mtime,
                    size=stat.st_size,
                )
                for c in window
            )
            all_vectors.extend(vectors)

        self.store.add(all_records, all_vectors)
        added = len(all_records)

        self.store.upsert_file(
            FileRecord(
                path=str(path),
                root=str(root),
                sha256=digest,
                mtime=stat.st_mtime,
                size=stat.st_size,
                chunks=added,
            )
        )
        return added

    # -- the pass ----------------------------------------------------------

    def refresh(self, roots: Iterable[Path | str]) -> dict[str, Any]:
        """Bring the index level with what is on disk under these roots."""
        self._check_embed_model()
        started = time.time()
        roots = [Path(r).expanduser().resolve() for r in roots]
        known = self.store.files_under([str(r) for r in roots])

        seen: set[str] = set()
        scanned = unchanged = reindexed = added_files = 0
        chunks_added = tombstoned = 0

        for root in roots:
            if not root.exists():
                continue
            for path in iter_files(root, self.ignore):
                key = str(path)
                if key in seen:
                    # Overlapping roots (e.g. a root and one of its own
                    # subdirectories, both configured) enumerate the same
                    # file once per enclosing root. Process it only the
                    # first time or its chunks get embedded and added twice.
                    continue
                seen.add(key)
                scanned += 1
                record = known.get(key)
                try:
                    stat = path.stat()
                except OSError:
                    continue

                if (
                    record is not None
                    and int(record.size) == stat.st_size
                    and abs(record.mtime - stat.st_mtime) < 1e-6
                ):
                    unchanged += 1
                    continue  # fast path: nothing to hash, nothing to embed

                if read_text_file(path) is None:
                    if record is not None:
                        # Previously indexed, now binary or past
                        # MAX_FILE_BYTES. Leaving its old chunks alone would
                        # keep stale content searchable forever - treat this
                        # like the file was deleted.
                        tombstoned += self.store.tombstone_paths([key])
                        self.store.forget_files([key])
                    continue

                digest = sha256_bytes(path)
                if (
                    record is not None
                    and record.sha256 == digest
                    and self.store.count_live_chunks(key) == record.chunks
                ):
                    # Touched but identical - refresh the stat, keep the vectors.
                    #
                    # The live-chunk check matters: a matching hash alone is
                    # not proof the vectors are still there. A prior refresh
                    # could have tombstoned this file's old chunks for a
                    # change, then failed the re-embed before upsert_file()
                    # recorded the new hash - leaving this old FileRecord in
                    # place with its old hash and every one of its chunks
                    # dead. If the file is then restored to that old content,
                    # the hash matches again while nothing live backs it. A
                    # mismatch here falls through to the reindex path below,
                    # which re-embeds from the current (matching) content.
                    self.store.upsert_file(
                        FileRecord(
                            path=key,
                            root=str(root),
                            sha256=digest,
                            mtime=stat.st_mtime,
                            size=stat.st_size,
                            chunks=record.chunks,
                        )
                    )
                    unchanged += 1
                    continue

                if record is not None:
                    # Retire the old windows *before* the new ones land, or the
                    # tombstone-by-path below would bury what we just wrote.
                    tombstoned += self.store.tombstone_paths([key])
                    reindexed += 1
                else:
                    added_files += 1
                chunks_added += self.index_file(path, root)

        deleted = [p for p in known if p not in seen]
        tombstoned += self.store.tombstone_paths(deleted)
        self.store.forget_files(deleted)

        compacted = self.store.maybe_compact()
        stats = self.store.stats()
        result = {
            "roots": [str(r) for r in roots],
            "scanned": scanned,
            "files_added": added_files,
            "files_reindexed": reindexed,
            "files_unchanged": unchanged,
            "files_deleted": len(deleted),
            "chunks_added": chunks_added,
            "chunks_tombstoned": tombstoned,
            "compacted": compacted,
            "elapsed_s": round(time.time() - started, 3),
        }
        # write_manifest rebuilds the manifest from scratch rather than
        # merging, so a refresh that was not told the embed_model must carry
        # forward whatever a previous refresh already recorded - otherwise a
        # call site that has not been updated yet would erase it on every run.
        prior_embed_model = self.store.read_manifest().get("embed_model")
        embed_model = self.embed_model if self.embed_model is not None else prior_embed_model
        extra: dict[str, Any] = {"last_refresh": result, "dim": stats["dim"]}
        if embed_model is not None:
            extra["embed_model"] = embed_model
        self.store.write_manifest(extra)
        return result


def excerpt(
    path: str | Path,
    start_line: int,
    end_line: int,
    query: str,
    max_lines: int = 3,
) -> tuple[int, list[str]] | None:
    """The best <=3 lines of a hit, and the line number the first one sits on.

    Whole files are never returned - the point of this index is to hand back a
    locator and just enough context to decide whether to open it.
    """
    path = Path(path)
    lines = read_text_file(path)
    if lines is None:
        return None

    lo = max(1, int(start_line))
    hi = min(len(lines), int(end_line))
    if lo > hi:
        return None

    span = [line.rstrip("\n").rstrip("\r") for line in lines[lo - 1 : hi]]
    tokens = {t for t in _tokenise(query) if len(t) > 1}

    best = 0
    best_score = -1.0
    for offset, text in enumerate(span):
        if not text.strip():
            continue
        line_tokens = set(_tokenise(text))
        score = float(len(tokens & line_tokens))
        if score > best_score:
            best_score = score
            best = offset

    if best_score <= 0:
        # Nothing lexically matched; show the first non-blank line instead.
        best = next((i for i, t in enumerate(span) if t.strip()), 0)

    start = max(0, min(best - (max_lines - 1) // 2, len(span) - max_lines))
    start = max(0, start)
    window = span[start : start + max_lines]
    while window and not window[-1].strip():
        window.pop()
    if not window:
        return None
    return lo + start, [w[:240] for w in window]


def _tokenise(text: str) -> list[str]:
    out: list[str] = []
    current: list[str] = []
    for ch in text.lower():
        if ch.isalnum() or ch == "_":
            current.append(ch)
        elif current:
            out.append("".join(current))
            current = []
    if current:
        out.append("".join(current))
    return out


__all__ = [
    "Chunk",
    "EMBED_BATCH",
    "EMBED_DIM",
    "EmbedModelMismatch",
    "Indexer",
    "OVERLAP_LINES",
    "WINDOW_LINES",
    "chunk_lines",
    "document_text",
    "excerpt",
    "is_ignored",
    "iter_files",
    "query_text",
    "read_text_file",
    "sha256_bytes",
]
