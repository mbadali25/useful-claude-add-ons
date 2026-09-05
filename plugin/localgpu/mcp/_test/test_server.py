"""The three tools: exact signatures, and the excerpt-not-file promise.

Skipped when the MCP SDK is absent - the SDK lives in $LOCALGPU_HOME/venv, not
in the system interpreter.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from conftest import FakeEmbedder

pytest.importorskip("mcp.server.mcpserver", reason="the MCP SDK is not installed here")

import config  # noqa: E402
import server  # noqa: E402


class FakeClient:
    """Stands in for OllamaClient. Same three methods, no network."""

    def __init__(self, *_args, **_kwargs) -> None:
        self.embedder = FakeEmbedder(dim=config.EMBED_DIM)

    def embed(self, texts, _model, **_kwargs):
        if isinstance(texts, str):
            texts = [texts]
        return self.embedder(texts)

    def list_models(self, **_kwargs):
        return ["nomic-embed-text:latest"]

    def require_models(self, _models):
        return None


@pytest.fixture
def wired(home, repo, write, monkeypatch):
    """A server whose cwd is a small repo and whose Ollama is a stub."""
    write(
        repo / "auth.py",
        "import hashlib\n\n\n"
        "def verify_password(user, password):\n"
        "    digest = hashlib.sha256(password.encode()).hexdigest()\n"
        "    return digest == user.password_hash\n",
    )
    write(
        repo / "views" / "cart.py",
        "def add_to_cart(session, sku, quantity):\n"
        "    session.setdefault('cart', {})\n"
        "    session['cart'][sku] = quantity\n"
        "    return session['cart']\n",
    )
    write(repo / "notes.md", "# Notes\n\nNothing to see here.\n")
    monkeypatch.chdir(repo)
    monkeypatch.setattr(server, "OllamaClient", FakeClient)
    return repo


def tools() -> dict:
    listed = asyncio.run(server.mcp.list_tools())
    return {tool.name: tool for tool in listed}


def schema_of(name: str) -> dict:
    """The tool's input schema, under whichever name this SDK gives it."""
    tool = tools()[name]
    return getattr(tool, "input_schema", None) or tool.inputSchema


def test_exactly_three_tools_are_exposed():
    assert set(tools()) == {"search_code", "index_status", "index_refresh"}


def test_search_code_signature_is_the_agreed_one():
    schema = schema_of("search_code")
    assert set(schema["properties"]) == {"query", "k", "root", "path_glob"}
    assert schema["required"] == ["query"]
    assert schema["properties"]["k"].get("default") == 10


def test_index_refresh_takes_only_an_optional_root():
    schema = schema_of("index_refresh")
    assert set(schema["properties"]) == {"root"}
    assert not schema.get("required")


def test_index_status_takes_nothing():
    assert not schema_of("index_status").get("properties")


def test_refresh_then_search_returns_locators_with_short_excerpts(wired):
    result = server.index_refresh()
    assert result["status"] == "ok"
    assert result["files_added"] == 3
    assert result["chunks_added"] == 3

    answer = server.search_code("verify a password hash", k=2)
    assert str(wired / "auth.py") in answer

    # The answer is a header, one block per hit, then a footer. Each block
    # gets a locator and at most three indented lines - never the file.
    blocks = answer.split("\n\n")
    assert blocks[0].startswith("2 hit(s)")
    for block in blocks[1:-1]:
        body = [line for line in block.splitlines() if line.startswith("    ")]
        assert 1 <= len(body) <= 3, block

    source = (wired / "auth.py").read_text(encoding="utf-8")
    assert source not in answer, "search_code must never return a whole file"
    assert answer.count(str(wired / "auth.py")) == 1


def test_hits_are_reported_as_path_colon_line(wired):
    server.index_refresh()
    answer = server.search_code("add an item to the shopping cart", k=1)
    header = [line for line in answer.splitlines() if line and not line.startswith(" ")]
    locator = header[1]
    path, _, rest = locator.rpartition(":")
    assert path.endswith(".py")
    assert rest.split()[0].isdigit()


def test_k_caps_the_number_of_hits(wired):
    server.index_refresh()
    answer = server.search_code("session", k=1)
    assert answer.startswith("1 hit(s)")


def test_path_glob_narrows_the_search(wired):
    server.index_refresh()
    answer = server.search_code("anything at all", k=5, path_glob="*.md")
    assert "notes.md" in answer
    assert "auth.py" not in answer


def test_root_narrows_the_search(wired):
    server.index_refresh()
    answer = server.search_code("anything at all", k=5, root=str(wired / "views"))
    assert "cart.py" in answer
    assert "auth.py" not in answer


def test_searching_an_empty_index_says_so(home, repo, monkeypatch):
    monkeypatch.chdir(repo)
    monkeypatch.setattr(server, "OllamaClient", FakeClient)
    answer = server.search_code("anything")
    assert "index_refresh" in answer


def test_an_empty_query_is_refused(home, repo, monkeypatch):
    monkeypatch.chdir(repo)
    assert "empty query" in server.search_code("   ")


def test_index_status_reports_the_index_and_the_models(wired):
    server.index_refresh()
    status = server.index_status()
    assert status["files"] == 3
    assert status["chunks"] == 3
    assert status["dim"] == config.EMBED_DIM
    assert status["roots"] == [str(wired)]
    assert status["embed_model"] == "nomic-embed-text"
    assert status["ollama"] == "reachable"
    assert status["embed_model_present"] is True
    assert status["last_refresh"]["files_added"] == 3


def test_ollama_failures_come_back_as_the_fix_not_a_traceback(wired, monkeypatch):
    from ollama import ModelNotPulled

    class Broken(FakeClient):
        def embed(self, *_args, **_kwargs):
            raise ModelNotPulled(
                "Ollama does not have the model 'nomic-embed-text'.\n"
                "Pull it with:  ollama pull nomic-embed-text"
            )

        def require_models(self, _models):
            raise ModelNotPulled(
                "Ollama does not have the model 'nomic-embed-text'.\n"
                "Pull it with:  ollama pull nomic-embed-text"
            )

    server.index_refresh()  # index first, with the working client
    monkeypatch.setattr(server, "OllamaClient", Broken)

    answer = server.search_code("verify a password hash")
    assert "ollama pull nomic-embed-text" in answer

    result = server.index_refresh()
    assert result["status"] == "error"
    assert "ollama pull nomic-embed-text" in result["detail"]


def test_a_second_refresh_is_incremental(wired):
    first = server.index_refresh()
    second = server.index_refresh()
    assert first["files_added"] == 3
    assert second["files_added"] == 0
    assert second["files_unchanged"] == 3
    assert second["chunks_added"] == 0


def test_index_refresh_wires_embed_model_through_to_the_indexer(wired):
    """Regression test for the call site, not just the Indexer logic.

    ``Indexer`` has verified this check since it was added; what stayed
    invisible was that ``index_refresh`` never told the ``Indexer`` it built
    which model was configured, so the check never ran in the only path that
    matters. This goes through ``server.index_refresh`` itself - construct an
    ``Indexer`` directly here and the wiring gap would pass silently again.
    """
    first = server.index_refresh()
    assert first["status"] == "ok"

    # Same width, different name - the case a dim check cannot catch.
    (wired / ".localgpu").mkdir(exist_ok=True)
    (wired / ".localgpu" / "config.json").write_text(
        json.dumps({"embed_model": "a-different-model"}), encoding="utf-8"
    )

    result = server.index_refresh()
    assert result["status"] == "error"
    assert "a-different-model" in result["detail"]
    assert config.DEFAULT_EMBED_MODEL in result["detail"]


def test_search_code_refuses_a_mismatched_embed_model(wired):
    """The refresh-time guard (above) does not cover this path at all.

    Build the index with one model, reconfigure a different one (same
    width - a dim check would stay silent), and search without ever calling
    index_refresh again. Without a check in search_code itself, this would
    embed the query with the new model and score it against vectors from
    the old one - same width, incompatible space, a confident but
    meaningless ranking with no error anywhere.
    """
    first = server.index_refresh()
    assert first["status"] == "ok"

    (wired / ".localgpu").mkdir(exist_ok=True)
    (wired / ".localgpu" / "config.json").write_text(
        json.dumps({"embed_model": "a-different-model"}), encoding="utf-8"
    )

    answer = server.search_code("verify a password hash")
    assert "a-different-model" in answer
    assert config.DEFAULT_EMBED_MODEL in answer
    assert "hit(s)" not in answer
