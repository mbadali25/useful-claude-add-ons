"""The localgpu MCP server: three tools over stdio.

    search_code(query, k=10, root=None, path_glob=None)
    index_status()
    index_refresh(root=None)

``search_code`` answers with ``file:line`` and at most three lines of context
per hit - never a file. The caller already has Read; what it lacks is the
locator, and a tool that returns 400 lines of source has spent the context it
was supposed to save.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Any

# This directory is named `mcp`, which is also the SDK's package name, so it
# must not become an importable package - `import mcp` would find it instead of
# the SDK. Siblings are therefore imported flat, off an explicit sys.path entry.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from config import EMBED_DIM, index_dir, load_config, localgpu_home  # noqa: E402
from indexer import (  # noqa: E402
    EmbedModelMismatch,
    Indexer,
    check_embed_model,
    excerpt,
    query_text,
)
from ollama import OllamaClient, OllamaError  # noqa: E402
from store import RefreshBusy, RefreshLock, VectorStore  # noqa: E402

from mcp.server.mcpserver import MCPServer  # noqa: E402

VERSION = "0.1.0"

INSTRUCTIONS = """\
Local semantic code search, backed by an on-disk index and a local Ollama.
Use search_code when you know what the code does but not where it lives;
it returns file:line locators with a <=3-line excerpt, so read the file
yourself for anything more. Run index_refresh after large changes, and
index_status when a search returns nothing.
"""

mcp = MCPServer(name="localgpu", version=VERSION, instructions=INSTRUCTIONS)

# One refresh at a time. Two concurrent passes would embed the same files twice
# and race each other's tombstones.
_refresh_lock = threading.Lock()


def _settings() -> dict[str, Any]:
    return load_config(cwd=Path.cwd(), home=localgpu_home())


def _open_store(settings: dict[str, Any]) -> VectorStore:
    # Built per call, in the calling thread: sqlite connections belong to the
    # thread that opened them, and MCP tool calls do not run on one thread.
    return VectorStore(index_dir(Path(settings["home"])), dim=EMBED_DIM)


def _client(settings: dict[str, Any]) -> OllamaClient:
    return OllamaClient(settings["ollama_url"])


@mcp.tool()
def search_code(
    query: str,
    k: int = 10,
    root: str | None = None,
    path_glob: str | None = None,
) -> str:
    """Semantic code search over the local index.

    Args:
        query: What the code does, in your own words.
        k: How many hits to return (default 10).
        root: Only search under this absolute path.
        path_glob: Only search paths matching this glob, e.g. ``*.py``.

    Returns:
        One ``file:line`` locator per hit with at most a three-line excerpt.
    """
    query = (query or "").strip()
    if not query:
        return "localgpu: empty query."

    settings = _settings()
    store = _open_store(settings)
    try:
        live, _dead = store.counts()
        if live == 0:
            return (
                "localgpu: the index is empty. Run index_refresh() first "
                f"(roots: {', '.join(settings['roots'])})."
            )
        try:
            # A dimension check alone would stay silent here: two different
            # models can share a width, and cosine similarity between their
            # vectors is meaningless while still producing a score. Without
            # this, an index built with model A can be queried with model
            # B's vectors and return confidently wrong-but-plausible hits.
            check_embed_model(
                store.read_manifest(),
                settings["embed_model"],
                store_has_content=live > 0,
            )
        except EmbedModelMismatch as exc:
            return f"localgpu: {exc}"
        try:
            vector = _client(settings).embed(
                query_text(query), settings["embed_model"]
            )[0]
        except OllamaError as exc:
            return f"localgpu: {exc}"

        hits = store.search(vector, k=max(1, int(k)), root=root, path_glob=path_glob)
    finally:
        store.close()

    if not hits:
        scope = []
        if root:
            scope.append(f"root={root}")
        if path_glob:
            scope.append(f"path_glob={path_glob}")
        suffix = f" within {', '.join(scope)}" if scope else ""
        return f"localgpu: no hits for {query!r}{suffix}."

    lines = [f"{len(hits)} hit(s) for {query!r}, best first (cosine):", ""]
    for hit in hits:
        piece = excerpt(hit.path, hit.start_line, hit.end_line, query)
        if piece is None:
            lines.append(
                f"{hit.path}:{hit.start_line}  {hit.score:.3f}  "
                "[file changed or gone since indexing - run index_refresh()]"
            )
            lines.append("")
            continue
        line_no, body = piece
        lines.append(f"{hit.path}:{line_no}  {hit.score:.3f}")
        lines.extend(f"    {text}" for text in body)
        lines.append("")
    lines.append(
        "Excerpts are capped at 3 lines. Read the file at the locator for the rest."
    )
    return "\n".join(lines)


@mcp.tool()
def index_status() -> dict[str, Any]:
    """What is indexed, how stale it is, and whether Ollama is reachable."""
    settings = _settings()
    store = _open_store(settings)
    try:
        status: dict[str, Any] = store.stats()
        status["roots"] = settings["roots"]
        status["embed_model"] = settings["embed_model"]
        status["chat_model"] = settings["chat_model"]
        status["ollama_url"] = settings["ollama_url"]
        manifest = store.read_manifest()
        status["last_refresh"] = manifest.get("last_refresh")
        status["manifest_updated_at"] = manifest.get("updated_at")
    finally:
        store.close()

    try:
        models = _client(settings).list_models()
        status["ollama"] = "reachable"
        status["embed_model_present"] = any(
            m == settings["embed_model"] or m.split(":", 1)[0] == settings["embed_model"]
            for m in models
        )
    except OllamaError as exc:
        status["ollama"] = str(exc)
        status["embed_model_present"] = None
    return status


@mcp.tool()
def index_refresh(root: str | None = None) -> dict[str, Any]:
    """Re-index changed files. Incremental: unchanged files are not re-embedded.

    Args:
        root: Refresh only this path. Defaults to every configured root.
    """
    if not _refresh_lock.acquire(blocking=False):
        return {"status": "busy", "detail": "a refresh is already running"}
    try:
        settings = _settings()
        try:
            # _refresh_lock above only ever protected against another
            # thread in *this* process. A second Claude session running
            # its own server.py against the same index directory is a
            # different process entirely - this is the lock that actually
            # stops two refreshes from compacting the same vectors.f16 at
            # once. See RefreshLock's docstring in store.py.
            cross_process_lock = RefreshLock(index_dir(Path(settings["home"])))
            cross_process_lock.__enter__()
        except RefreshBusy as exc:
            return {"status": "busy", "detail": str(exc)}
        try:
            client = _client(settings)
            try:
                client.require_models([settings["embed_model"]])
            except OllamaError as exc:
                return {"status": "error", "detail": str(exc)}

            roots = [root] if root else settings["roots"]
            store = _open_store(settings)
            try:
                indexer = Indexer(
                    store,
                    embed=lambda texts: client.embed(texts, settings["embed_model"]),
                    ignore=settings["ignore"],
                    embed_model=settings["embed_model"],
                )
                try:
                    result = indexer.refresh(roots)
                except OllamaError as exc:
                    return {"status": "error", "detail": str(exc)}
                except EmbedModelMismatch as exc:
                    # Not silent, not auto-fixed: an incremental refresh cannot
                    # safely reconcile this on its own. The files most likely to
                    # carry stale vectors are exactly the mtime/size-unchanged
                    # ones an incremental pass skips, so "auto" here would really
                    # mean silently forcing a full rebuild - the opposite of loud.
                    return {"status": "error", "detail": str(exc)}
                result["status"] = "ok"
                return result
            finally:
                store.close()
        finally:
            cross_process_lock.__exit__(None, None, None)
    finally:
        _refresh_lock.release()


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
