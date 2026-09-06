"""Secrets must never reach the vector store.

Two independent guards are exercised here: `DEFAULT_IGNORE`'s credential
patterns (a `.env`, a `*.pem`) and the project's own `.gitignore` for a file
neither `DEFAULT_IGNORE` nor any configured pattern would otherwise catch.
Both are checked against the *content* fed to the embedder, not just the file
list - a file merely missing from the index proves nothing about whether its
bytes were the ones that never got read, and the whole risk this guards
against is content reaching the on-disk store.
"""

from __future__ import annotations

import config
from conftest import TEST_DIM
from indexer import Indexer
from store import VectorStore


def make_indexer(home, embedder):
    store = VectorStore(config.index_dir(home), dim=TEST_DIM)
    return store, Indexer(store, embed=embedder, ignore=list(config.DEFAULT_IGNORE))


def test_env_pem_and_gitignored_secrets_never_reach_the_embedder(home, repo, write, embedder):
    write(repo / ".env", "API_TOKEN=sk-fake-0123456789abcdef\n")
    write(
        repo / "server.pem",
        "-----BEGIN PRIVATE KEY-----\nMIIFAKEKEYMATERIALNOTREAL\n-----END PRIVATE KEY-----\n",
    )
    # Not a name DEFAULT_IGNORE knows about at all - only the project's own
    # .gitignore says this one is off limits.
    write(repo / "notes.local", "SLACK_WEBHOOK=https://hooks.slack.com/services/FAKE\n")
    write(repo / ".gitignore", "notes.local\n")
    write(repo / "app.py", "def handler():\n    return 'ordinary source line'\n")

    store, indexer = make_indexer(home, embedder)
    try:
        indexer.refresh([repo])

        live = store.files_under([str(repo)])
        assert str(repo / "app.py") in live, "the ordinary file must be indexed"
        assert str(repo / ".env") not in live
        assert str(repo / "server.pem") not in live
        assert str(repo / "notes.local") not in live

        blob = "\n".join(embedder.texts)
        assert "ordinary source line" in blob, "the ordinary file's content must reach the embedder"
        assert "sk-fake-0123456789abcdef" not in blob
        assert "MIIFAKEKEYMATERIALNOTREAL" not in blob
        assert "hooks.slack.com/services/FAKE" not in blob
    finally:
        store.close()
