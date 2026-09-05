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


# --------------------------------------------------------------------------
# num_ctx: resolved from Ollama, not left for Ollama's own 4096 default
# --------------------------------------------------------------------------


class ShowingOllama(BaseHTTPRequestHandler):
    """A fake that actually answers /api/show, unlike FakeOllama above -
    resolve_num_ctx needs a realistic model_info shape to parse."""

    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        self.server.last_request = json.loads(self.rfile.read(length) or b"{}")
        body = json.dumps(self.server.show_reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def showing_ollama():
    server = ThreadingHTTPServer(("127.0.0.1", 0), ShowingOllama)
    server.daemon_threads = True
    server.show_reply = {
        "model_info": {"general.architecture": "qwen2", "qwen2.context_length": 32768}
    }
    server.last_request = None
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()
    server.server_close()


def test_resolve_num_ctx_reads_the_models_own_context_length(showing_ollama):
    host, port = showing_ollama.server_address
    got = proxy.resolve_num_ctx(f"http://{host}:{port}", "qwen-test", default=99999)
    # The model's real 32768 is smaller than the (deliberately absurd)
    # default, so the real value wins.
    assert got == 32768


def test_resolve_num_ctx_caps_at_default_for_a_bigger_window_model(showing_ollama):
    """default exists to protect VRAM - a model that claims a bigger window
    than the card can hold must not get more than `default` asks for."""
    showing_ollama.show_reply = {
        "model_info": {"general.architecture": "llama", "llama.context_length": 131072}
    }
    host, port = showing_ollama.server_address
    got = proxy.resolve_num_ctx(f"http://{host}:{port}", "big-model", default=16384)
    assert got == 16384


def test_resolve_num_ctx_falls_back_when_context_length_is_missing(showing_ollama):
    """A build of Ollama that does not report context_length must not crash
    the request that needed it - it should just get the documented default."""
    showing_ollama.show_reply = {"model_info": {}}
    host, port = showing_ollama.server_address
    got = proxy.resolve_num_ctx(f"http://{host}:{port}", "qwen-test", default=16384)
    assert got == 16384


def test_resolve_num_ctx_falls_back_when_ollama_is_unreachable():
    got = proxy.resolve_num_ctx("http://127.0.0.1:1", "qwen-test", timeout=1, default=16384)
    assert got == 16384


def test_num_ctx_is_auto_detected_end_to_end(showing_ollama):
    """No explicit num_ctx override, driven through the real server - proves
    _resolved_num_ctx actually gets called on the request path and its
    result reaches the /api/chat body, not just that resolve_num_ctx works
    in isolation."""
    host, port = showing_ollama.server_address
    server = proxy.make_server("127.0.0.1", 0, f"http://{host}:{port}", "qwen-test")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        # ShowingOllama answers /api/chat with the /api/show shape too (it
        # does not branch on path), which to_anthropic_response tolerates -
        # the point here is only what ends up in the request it received.
        post(
            f"http://127.0.0.1:{server.server_address[1]}/v1/messages",
            {"max_tokens": 8, "messages": [{"role": "user", "content": "hi"}]},
        )
    finally:
        server.shutdown()
        server.server_close()
    assert showing_ollama.last_request["options"]["num_ctx"] == 32768


# --------------------------------------------------------------------------
# Refusing a request that cannot fit, instead of letting Ollama truncate it
# --------------------------------------------------------------------------


def test_check_fits_context_allows_a_request_with_room_to_spare():
    body = {"max_tokens": 100, "messages": [{"role": "user", "content": "hi"}]}
    proxy.check_fits_context(body, num_ctx=4096)  # must not raise


def test_check_fits_context_refuses_an_oversized_prompt():
    huge = {"role": "user", "content": "x" * 100_000}
    body = {"max_tokens": 100, "messages": [huge]}
    with pytest.raises(proxy.ProxyError) as caught:
        proxy.check_fits_context(body, num_ctx=4096)
    assert caught.value.status == 400
    assert caught.value.kind == "invalid_request_error"


def test_check_fits_context_does_not_let_a_huge_max_tokens_reject_everything():
    """Claude Code routinely asks for a very large max_tokens no matter how
    long the reply will actually be - only a small amount is reserved for
    it, not the full requested ceiling, or every real request gets refused."""
    body = {"max_tokens": 64000, "messages": [{"role": "user", "content": "hi"}]}
    proxy.check_fits_context(body, num_ctx=8192)  # must not raise


def test_oversized_request_is_refused_before_reaching_ollama(endpoint, ollama):
    huge = {"role": "user", "content": "x" * 300_000}
    with pytest.raises(urllib.error.HTTPError) as caught:
        post(f"{endpoint}/v1/messages", {"max_tokens": 8, "messages": [huge]})
    assert caught.value.code == 400
    body = json.loads(caught.value.read())
    assert body["error"]["type"] == "invalid_request_error"
    # Never sent - the fake never saw a /api/chat body anywhere near this size.
    assert ollama.last_request is None or len(json.dumps(ollama.last_request)) < 300_000


# --------------------------------------------------------------------------
# A client hanging up is not a server error
# --------------------------------------------------------------------------


def test_handle_error_swallows_a_connection_reset(capsys):
    server = proxy.make_server("127.0.0.1", 0, "http://127.0.0.1:1", "qwen-test")
    try:
        try:
            raise ConnectionResetError("simulated WinError 10054")
        except ConnectionResetError:
            server.handle_error(None, ("127.0.0.1", 0))
    finally:
        server.server_close()
    assert capsys.readouterr().err == ""


def test_handle_error_still_reports_a_real_bug(capsys):
    server = proxy.make_server("127.0.0.1", 0, "http://127.0.0.1:1", "qwen-test")
    try:
        try:
            raise ValueError("an actual bug, not a client hanging up")
        except ValueError:
            server.handle_error(None, ("127.0.0.1", 0))
    finally:
        server.server_close()
    assert "an actual bug" in capsys.readouterr().err


# --------------------------------------------------------------------------
# The bug, against a REAL Ollama
# --------------------------------------------------------------------------
#
# Every test above talks to a fake. A fake has no context window, so no test
# above it can observe num_ctx being left unset any more than it could
# observe it being set correctly - that is exactly how the original bug
# shipped: 207 passing tests, two independent review rounds, and a deep
# suite, all green over a proxy that silently ran every real request at
# Ollama's built-in 4096-token default. This is the one test in the suite
# that talks to the real thing, and it is written to fail the way the real
# bug failed - input_tokens pinned at a small constant regardless of prompt
# size - not merely "num_ctx key missing."
#
# Sabotage-tested by hand: delete the "num_ctx" line from to_ollama_request's
# options dict and rerun just this test - it goes red, reporting input_tokens
# pinned near ~2000 for both the small and the large prompt, the original
# symptom. Restoring the line turns it green again. That check is not itself
# part of the suite, since breaking the fix on every run defeats the point
# of a regression test.

REAL_OLLAMA_URL = "http://127.0.0.1:11434"
REAL_CHAT_MODEL = "qwen2.5-coder:7b-instruct-q4_K_M"


def _real_ollama_ready() -> bool:
    """Both the server and the exact model this project ships must be
    present - a bare "is Ollama up" ping would skip cleanly on a machine
    missing the model, and this would fail confusingly instead."""
    try:
        with urllib.request.urlopen(f"{REAL_OLLAMA_URL}/api/tags", timeout=3) as response:
            tags = json.loads(response.read())
        return REAL_CHAT_MODEL in {m.get("name") for m in tags.get("models", [])}
    except Exception:
        return False


requires_real_ollama = pytest.mark.skipif(
    not _real_ollama_ready(),
    reason=f"real Ollama with {REAL_CHAT_MODEL} not reachable at {REAL_OLLAMA_URL}",
)


@pytest.fixture
def real_endpoint():
    """A proxy pointed at the real Ollama and the real chat model - no fake
    anywhere in the loop, which is the entire point of this test."""
    server = proxy.make_server("127.0.0.1", 0, REAL_OLLAMA_URL, REAL_CHAT_MODEL)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@requires_real_ollama
def test_input_tokens_scale_with_prompt_size_on_a_real_model(real_endpoint):
    filler = (
        "The quick brown fox jumps over the lazy dog near the riverbank "
        "while the sun sets slowly behind the distant mountains. "
    ) * 600  # ~15k real tokens - measured via prompt_eval_count, see the
    # module docstring's chars-per-token note.

    def input_tokens_for(user_text: str) -> int:
        # Not the shared post() helper - real inference (and a cold model
        # load on the first call) comfortably exceeds its fixed 10s timeout.
        request = urllib.request.Request(
            f"{real_endpoint}/v1/messages",
            data=json.dumps(
                {"max_tokens": 8, "messages": [{"role": "user", "content": user_text}]}
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            assert response.status == 200
            return json.loads(response.read())["usage"]["input_tokens"]

    small_tokens = input_tokens_for("Say hi in one word.")
    large_tokens = input_tokens_for(filler + "\n\nSay hi in one word.")

    assert small_tokens < 100
    # Ollama's own default context is 4096 tokens; the original bug's
    # symptom was every request pinning at roughly 2050 regardless of size.
    # A real fix clears both of those by a wide margin instead of landing
    # near either.
    assert large_tokens > 6000, (
        f"input_tokens did not scale with prompt size (small={small_tokens}, "
        f"large={large_tokens}) - num_ctx is likely unset again, capping "
        "every request at Ollama's built-in default window."
    )
    assert large_tokens > small_tokens * 20
