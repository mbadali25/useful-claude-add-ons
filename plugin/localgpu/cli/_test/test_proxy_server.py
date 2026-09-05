"""The proxy as Claude Code meets it: a real socket, real HTTP, a fake Ollama.

The translation tests cover the shapes. These cover the things only a bound
server gets wrong - routing, status codes, chunked SSE framing, and the error
text a user sees when Ollama is not running.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

# Inline, not a conftest.py - see the note in test_proxy_translation.py.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthropic_proxy as proxy  # noqa: E402


class FakeOllama(BaseHTTPRequestHandler):
    """Answers /api/chat with whatever the test parked on the server."""

    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # keep pytest output clean
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        self.server.last_request = json.loads(self.rfile.read(length) or b"{}")

        if self.server.status != 200:
            body = json.dumps({"error": self.server.error_text}).encode()
            self.send_response(self.server.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.server.stream_chunks is not None:
            body = b"".join(
                json.dumps(c).encode() + b"\n" for c in self.server.stream_chunks
            )
        else:
            body = json.dumps(self.server.reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def ollama():
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
    server.daemon_threads = True
    server.reply = {"message": {"content": "hi"}, "done_reason": "stop"}
    server.stream_chunks = None
    server.status = 200
    server.error_text = ""
    server.last_request = None
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture
def endpoint(ollama):
    host, port = ollama.server_address[0], ollama.server_address[1]
    server = proxy.make_server("127.0.0.1", 0, f"http://{host}:{port}", "qwen-test")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def post(url, payload):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, response.read()


def test_messages_round_trip(endpoint):
    status, raw = post(f"{endpoint}/v1/messages", {"max_tokens": 16, "messages": [{"role": "user", "content": "hi"}]})
    assert status == 200
    body = json.loads(raw)
    assert body["type"] == "message"
    assert body["content"] == [{"type": "text", "text": "hi"}]
    assert body["model"] == "qwen-test"


def test_the_configured_model_is_what_reaches_ollama(endpoint, ollama):
    post(f"{endpoint}/v1/messages", {"max_tokens": 8, "messages": [{"role": "user", "content": "x"}]})
    assert ollama.last_request["model"] == "qwen-test"
    assert ollama.last_request["keep_alive"] == proxy.DEFAULT_KEEP_ALIVE


def test_streaming_returns_sse_frames(endpoint, ollama):
    ollama.stream_chunks = [
        {"message": {"content": "he"}},
        {"message": {"content": "llo"}},
        {"done": True, "done_reason": "stop", "eval_count": 2},
    ]
    request = urllib.request.Request(
        f"{endpoint}/v1/messages",
        data=json.dumps({"max_tokens": 8, "stream": True, "messages": []}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        assert response.headers["Content-Type"] == "text/event-stream"
        text = response.read().decode()

    assert text.startswith("event: message_start")
    assert text.rstrip().endswith('data: {"type": "message_stop"}')
    assembled = "".join(
        json.loads(line.removeprefix("data: "))["delta"]["text"]
        for line in text.split("\n")
        if line.startswith("data: ") and '"text_delta"' in line
    )
    assert assembled == "hello"


def test_unknown_route_is_404_in_anthropic_error_shape(endpoint):
    with pytest.raises(urllib.error.HTTPError) as caught:
        post(f"{endpoint}/v1/complete", {})
    assert caught.value.code == 404
    body = json.loads(caught.value.read())
    assert body["type"] == "error"
    assert body["error"]["type"] == "not_found_error"


def test_bad_json_is_400_not_500(endpoint):
    request = urllib.request.Request(
        f"{endpoint}/v1/messages",
        data=b"{not json",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(request, timeout=10)
    assert caught.value.code == 400


def test_missing_model_names_the_pull_command(endpoint, ollama):
    ollama.status = 404
    ollama.error_text = 'model "qwen-test" not found'
    with pytest.raises(urllib.error.HTTPError) as caught:
        post(f"{endpoint}/v1/messages", {"max_tokens": 8, "messages": []})
    message = json.loads(caught.value.read())["error"]["message"]
    assert "ollama pull qwen-test" in message


def test_ollama_down_says_how_to_start_it():
    """No fake upstream at all - the port is closed."""
    server = proxy.make_server("127.0.0.1", 0, "http://127.0.0.1:1", "qwen-test")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/v1/messages"
    try:
        with pytest.raises(urllib.error.HTTPError) as caught:
            post(url, {"max_tokens": 8, "messages": []})
        assert caught.value.code == 503
        assert "ollama serve" in json.loads(caught.value.read())["error"]["message"]
    finally:
        server.shutdown()
        server.server_close()


def test_health_reports_the_model(endpoint):
    with urllib.request.urlopen(f"{endpoint}/health", timeout=10) as response:
        assert json.loads(response.read())["model"] == "qwen-test"


def test_a_404_with_a_body_does_not_poison_the_connection(endpoint):
    """The regression this file's one intermittent failure turned out to be.

    protocol_version is HTTP/1.1, so connections persist. A route that answered
    without reading the request body left it in the socket buffer, where the
    handler parsed it as the next request line. The symptom appeared on the
    request AFTER the 404, which is why it looked like flakiness.

    Driven over one raw socket because urllib opens a fresh connection per
    request and cannot reproduce it.
    """
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(endpoint)
    body = json.dumps({"max_tokens": 8, "messages": [{"role": "user", "content": "hi"}]})

    def frame(path):
        return (
            f"POST {path} HTTP/1.1\r\nHost: {parsed.netloc}\r\n"
            f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n{body}"
        ).encode()

    with socket.create_connection((parsed.hostname, parsed.port), timeout=10) as sock:
        sock.sendall(frame("/v1/complete"))   # unknown route, with a body
        sock.sendall(frame("/v1/messages"))   # must still be understood
        sock.settimeout(10)
        received = b""
        while b'"type": "message"' not in received and b"400" not in received:
            chunk = sock.recv(4096)
            if not chunk:
                break
            received += chunk

    text = received.decode("utf-8", "replace")
    assert "404" in text, "the first response should still be the 404"
    assert "400 Bad Request" not in text, "the leftover body was parsed as a request line"
    assert '"type": "message"' in text, "the second request on the connection was lost"


# -- FIX: a timeout after streaming has started must not write a second ----
# -- HTTP response into the already-chunked body --------------------------


class OneChunkThenHangOllama(BaseHTTPRequestHandler):
    """Emits one NDJSON line, then goes silent without closing the socket.

    Promises more bytes than it ever sends (Content-Length overstated), so a
    client reading it blocks past its socket timeout instead of hitting a
    clean EOF - reproducing an Ollama hang mid-stream.
    """

    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        chunk = json.dumps({"message": {"content": "partial"}}).encode() + b"\n"
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Content-Length", str(len(chunk) * 100))
        self.end_headers()
        try:
            self.wfile.write(chunk)
            self.wfile.flush()
            time.sleep(2)  # far longer than the proxy's configured timeout
        except (BrokenPipeError, ConnectionResetError):
            pass


def test_a_timeout_after_streaming_started_ends_the_stream_cleanly():
    """Without the fix, the TimeoutError raised by reading past
    timeout_seconds escapes `_stream` into do_POST's generic handler, which
    calls send_response(500) again - writing a second HTTP status line and
    headers into the middle of the already-chunked SSE body. A client
    reading that gets a corrupted chunked encoding instead of a clean error.
    """
    ollama = ThreadingHTTPServer(("127.0.0.1", 0), OneChunkThenHangOllama)
    ollama.daemon_threads = True
    threading.Thread(target=ollama.serve_forever, daemon=True).start()

    host, port = ollama.server_address
    server = proxy.make_server(
        "127.0.0.1", 0, f"http://{host}:{port}", "qwen-test", timeout=0.3
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/v1/messages"

    try:
        request = urllib.request.Request(
            url,
            data=json.dumps({"max_tokens": 8, "stream": True, "messages": []}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            assert response.status == 200
            text = response.read().decode()
    finally:
        server.shutdown()
        server.server_close()
        ollama.shutdown()
        ollama.server_close()

    assert "event: error" in text
    assert text.rstrip().endswith('data: {"type": "message_stop"}') is False
    assert '"type": "error"' in text
