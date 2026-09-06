"""The HTTP client, against a stub server on localhost. No Ollama, no GPU."""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from ollama import (
    DEFAULT_KEEP_ALIVE,
    ModelNotPulled,
    OllamaClient,
    OllamaError,
    OllamaUnavailable,
)


class StubOllama:
    """Answers whatever the test tells it to, and records what it was sent."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, dict]] = []
        self.responses: dict[str, tuple[int, dict]] = {}
        self.server: ThreadingHTTPServer | None = None

    def reply(self, path: str, status: int, payload: dict) -> None:
        self.responses[path] = (status, payload)

    @property
    def url(self) -> str:
        assert self.server is not None
        port = self.server.server_address[1]
        return f"http://127.0.0.1:{port}"

    def start(self) -> None:
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):  # keep pytest output clean
                pass

            def _send(self, status: int, payload: dict) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler's naming
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length) or b"{}")
                stub.requests.append((self.path, payload))
                status, response = stub.responses.get(self.path, (404, {}))
                self._send(status, response)

            def do_GET(self):  # noqa: N802
                stub.requests.append((self.path, {}))
                status, response = stub.responses.get(self.path, (404, {}))
                self._send(status, response)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()


@pytest.fixture
def stub():
    server = StubOllama()
    server.start()
    try:
        yield server
    finally:
        server.stop()


def closed_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_embed_returns_one_vector_per_input(stub):
    stub.reply("/api/embed", 200, {"embeddings": [[0.1, 0.2], [0.3, 0.4]]})
    client = OllamaClient(stub.url)
    assert client.embed(["a", "b"], "nomic-embed-text") == [[0.1, 0.2], [0.3, 0.4]]


def test_embed_accepts_a_bare_string(stub):
    stub.reply("/api/embed", 200, {"embeddings": [[1.0, 0.0]]})
    assert OllamaClient(stub.url).embed("query", "nomic-embed-text") == [[1.0, 0.0]]
    _path, payload = stub.requests[-1]
    assert payload["input"] == ["query"]


def test_every_request_carries_a_short_keep_alive(stub):
    """8 GB of VRAM with a display attached: the models must not co-reside."""
    stub.reply("/api/embed", 200, {"embeddings": [[1.0]]})
    stub.reply("/api/generate", 200, {"response": "hi"})
    client = OllamaClient(stub.url)
    client.embed("q", "nomic-embed-text")
    client.generate("prompt", "qwen2.5-coder:7b-instruct-q4_K_M")

    assert [p for _, p in stub.requests], "the stub saw no requests"
    for path, payload in stub.requests:
        assert payload["keep_alive"] == DEFAULT_KEEP_ALIVE, path
    assert DEFAULT_KEEP_ALIVE.endswith("s")


def test_embed_of_nothing_makes_no_request(stub):
    assert OllamaClient(stub.url).embed([], "nomic-embed-text") == []
    assert stub.requests == []


def test_generate_is_not_streamed(stub):
    stub.reply("/api/generate", 200, {"response": "an answer"})
    assert OllamaClient(stub.url).generate("q", "chat-model") == "an answer"
    _path, payload = stub.requests[-1]
    assert payload["stream"] is False
    assert payload["model"] == "chat-model"


def test_missing_model_names_the_pull_command(stub):
    stub.reply(
        "/api/embed", 404, {"error": "model 'nomic-embed-text' not found, try pulling it"}
    )
    with pytest.raises(ModelNotPulled) as caught:
        OllamaClient(stub.url).embed("q", "nomic-embed-text")
    assert "ollama pull nomic-embed-text" in str(caught.value)


def test_missing_endpoint_is_not_reported_as_a_missing_model(stub):
    stub.reply("/api/embed", 404, {"detail": "404 page not found"})
    with pytest.raises(OllamaError) as caught:
        OllamaClient(stub.url).embed("q", "nomic-embed-text")
    assert not isinstance(caught.value, ModelNotPulled)
    assert "/api/embed" in str(caught.value)


def test_server_not_running_names_ollama_serve():
    port = closed_port()
    client = OllamaClient(f"http://127.0.0.1:{port}")
    with pytest.raises(OllamaUnavailable) as caught:
        client.embed("q", "nomic-embed-text")
    message = str(caught.value)
    assert "ollama serve" in message
    assert f"127.0.0.1:{port}" in message


def test_list_models_also_reports_an_absent_server():
    client = OllamaClient(f"http://127.0.0.1:{closed_port()}")
    with pytest.raises(OllamaUnavailable):
        client.list_models()


def test_a_short_answer_is_not_silently_padded(stub):
    stub.reply("/api/embed", 200, {"embeddings": [[1.0]]})
    with pytest.raises(OllamaError) as caught:
        OllamaClient(stub.url).embed(["a", "b"], "nomic-embed-text")
    assert "nomic-embed-text" in str(caught.value)


def test_a_200_with_no_response_field_is_an_error_not_an_empty_answer(stub):
    """The generate-side twin of the test above, and the same defect class.

    `data.get("response", "")` turned a malformed 200 into an empty string, which
    the CLI then printed as a successful blank answer - a failure wearing the
    shape of a success. The caller cannot tell "the model said nothing" from
    "the server sent something we could not read", so the two must not collapse.
    """
    stub.reply("/api/generate", 200, {"done": True, "model": "chat-model"})
    with pytest.raises(OllamaError) as caught:
        OllamaClient(stub.url).generate("q", "chat-model")

    message = str(caught.value)
    assert "chat-model" in message
    assert "no 'response' field" in message
    assert "done, model" in message, "the message must name what DID come back"


def test_a_genuinely_empty_response_is_still_returned(stub):
    """The other side of it: an empty answer the server actually sent is data,
    not an error. Guarding the missing key must not reject a present one."""
    stub.reply("/api/generate", 200, {"response": ""})

    assert OllamaClient(stub.url).generate("q", "chat-model") == ""


def test_require_models_accepts_a_latest_tag(stub):
    stub.reply(
        "/api/tags",
        200,
        {"models": [{"name": "nomic-embed-text:latest"}, {"name": "qwen2.5-coder:7b"}]},
    )
    client = OllamaClient(stub.url)
    client.require_models(["nomic-embed-text", "qwen2.5-coder:7b"])

    with pytest.raises(ModelNotPulled) as caught:
        client.require_models(["llama3"])
    assert "ollama pull llama3" in str(caught.value)


def test_http_500_is_reported_with_its_body(stub):
    stub.reply("/api/embed", 500, {"error": "out of memory"})
    with pytest.raises(OllamaError) as caught:
        OllamaClient(stub.url).embed("q", "nomic-embed-text")
    assert "out of memory" in str(caught.value)
