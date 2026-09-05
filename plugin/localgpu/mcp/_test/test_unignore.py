"""`unignore` re-includes a file `DEFAULT_IGNORE` would otherwise swallow.

Same shape as `test_secrets.py`: assert on the *content* fed to the embedder,
not just the file list, because a file missing from the index proves nothing
about whether its bytes were the ones that never got read.
"""

from __future__ import annotations

import json

import config
from conftest import TEST_DIM
from indexer import Indexer
from store import VectorStore


def make_indexer(home, embedder, ignore):
    store = VectorStore(config.index_dir(home), dim=TEST_DIM)
    return store, Indexer(store, embed=embedder, ignore=ignore)


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_unignoring_a_liftable_default_lets_the_file_through(home, repo, write, embedder):
    # ".strings.key" is caught only by the broad "*.key" default, not by any
    # of the other credential patterns - a legitimate localization resource,
    # not a secret.
    write(repo / "strings.key", "GREETING=hello\n")
    write(repo / ".env", "API_TOKEN=sk-fake-0123456789abcdef\n")
    write_json(config.repo_config_path(repo), {"unignore": ["*.key"]})

    settings = config.load_config(cwd=repo, home=home)
    store, indexer = make_indexer(home, embedder, settings["ignore"])
    try:
        indexer.refresh([repo])

        live = store.files_under([str(repo)])
        assert str(repo / "strings.key") in live, "unignored file must be indexed"
        assert str(repo / ".env") not in live, "a pattern the user did not lift stays excluded"

        blob = "\n".join(embedder.texts)
        assert "hello" in blob, "the unignored file's content must reach the embedder"
        assert "sk-fake-0123456789abcdef" not in blob
    finally:
        store.close()


def test_hard_floor_survives_an_unignore_attempt(home, repo, write, embedder):
    write(repo / "node_modules" / "pkg" / "index.js", "console.log('should never be indexed')\n")
    write(repo / "app.py", "def handler():\n    return 'ordinary source line'\n")
    write_json(config.repo_config_path(repo), {"unignore": ["node_modules"]})

    settings = config.load_config(cwd=repo, home=home)
    assert "node_modules" in settings["ignore"], "the hard floor must survive the merge"

    store, indexer = make_indexer(home, embedder, settings["ignore"])
    try:
        indexer.refresh([repo])

        live = store.files_under([str(repo)])
        assert str(repo / "app.py") in live
        assert str(repo / "node_modules" / "pkg" / "index.js") not in live

        blob = "\n".join(embedder.texts)
        assert "should never be indexed" not in blob
        assert "ordinary source line" in blob
    finally:
        store.close()
