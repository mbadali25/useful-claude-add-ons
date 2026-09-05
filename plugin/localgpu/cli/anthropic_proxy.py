"""An Anthropic Messages API front end for a local Ollama.

`ANTHROPIC_BASE_URL` does not mean "any OpenAI-compatible server". Claude Code
POSTs `/v1/messages` in the Anthropic Messages wire format; Ollama's
OpenAI-compatible surface is `/v1/chat/completions` with a different body. Point
one at the other and every request 404s. This module is the translation that
makes the two actually meet:

    Claude Code --POST /v1/messages--> this proxy --POST /api/chat--> Ollama

The translation is deliberately split from the server. Everything above
:class:`ProxyHandler` is a pure function over dicts, so the wire format is
tested without binding a socket.

What crosses the boundary intact: system prompts, multi-turn text, tool
definitions, tool calls, tool results, stop sequences, temperature, and both
streaming and non-streaming replies.

What does not, and is reported rather than faked:

* **Images.** A 7B coder model has no vision. Image blocks are replaced with a
  visible placeholder so the turn still makes sense, instead of being dropped.
* **Thinking blocks.** No local model emits them. Nothing is synthesised.
* **Prompt caching.** `cache_control` is accepted and ignored; the usage
  numbers report zero cache hits rather than inventing them.
* **Token counts.** Ollama reports its own prompt/eval counts and those are
  passed through. They are not Anthropic's tokenizer and will not match it.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Iterator

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"

# The chat model is the big one on an 8 GB card. Hold it just long enough to
# survive the gap between turns in an interactive session, and no longer -
# OLLAMA_MAX_LOADED_MODELS=1 means whatever is resident blocks the embed model.
DEFAULT_KEEP_ALIVE = "5m"

# A local generate can legitimately take minutes on first load.
DEFAULT_TIMEOUT = 600.0

# Anthropic requires max_tokens; Ollama calls the same thing num_predict.
DEFAULT_MAX_TOKENS = 4096


class ProxyError(RuntimeError):
    """Something upstream failed in a way the client should be told about."""

    def __init__(self, message: str, status: int = 502, kind: str = "api_error") -> None:
        super().__init__(message)
        self.status = status
        self.kind = kind


# --------------------------------------------------------------------------
# Request translation: Anthropic Messages -> Ollama /api/chat
# --------------------------------------------------------------------------


def _system_to_text(system: Any) -> str:
    """`system` is either a string or a list of content blocks."""
    if not system:
        return ""
    if isinstance(system, str):
        return system
    parts = [
        str(block.get("text", ""))
        for block in system
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "\n\n".join(p for p in parts if p)


def _blocks_to_text(content: Any) -> str:
    """Flatten one message's content blocks into text Ollama can read."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text":
            parts.append(str(block.get("text", "")))
        elif kind == "image":
            # Say so out loud. A silently dropped image makes the following
            # text ("what is wrong with this screenshot?") unanswerable in a
            # way that looks like the model being stupid.
            parts.append("[image omitted: the local model has no vision]")
        elif kind == "thinking":
            continue
    return "\n\n".join(p for p in parts if p)


def _tool_results(content: Any) -> list[dict[str, Any]]:
    """Pull `tool_result` blocks out of a user turn."""
    if not isinstance(content, list):
        return []
    out: list[dict[str, Any]] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_result":
            out.append(block)
    return out


def to_ollama_messages(system: Any, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build Ollama's flat message list from Anthropic's block structure.

    Anthropic puts tool results in a *user* message; Ollama wants them in their
    own `role: "tool"` message. Anthropic puts tool calls in an *assistant*
    message's content; Ollama wants them in `tool_calls` alongside content.
    """
    out: list[dict[str, Any]] = []

    system_text = _system_to_text(system)
    if system_text:
        out.append({"role": "system", "content": system_text})

    for message in messages:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = message.get("content")

        if role == "user":
            results = _tool_results(content)
            for result in results:
                out.append(
                    {
                        "role": "tool",
                        "content": _blocks_to_text(result.get("content")) or "",
                    }
                )
            text = _blocks_to_text(
                [b for b in content if not (isinstance(b, dict) and b.get("type") == "tool_result")]
                if isinstance(content, list)
                else content
            )
            if text or not results:
                out.append({"role": "user", "content": text})

        elif role == "assistant":
            calls = []
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        calls.append(
                            {
                                "function": {
                                    "name": block.get("name", ""),
                                    "arguments": block.get("input") or {},
                                }
                            }
                        )
            entry: dict[str, Any] = {"role": "assistant", "content": _blocks_to_text(content)}
            if calls:
                entry["tool_calls"] = calls
            out.append(entry)

        elif role == "system":
            # Mid-conversation system messages. Ollama has no equivalent slot,
            # so it lands as another system turn rather than being dropped.
            out.append({"role": "system", "content": _blocks_to_text(content)})

    return out


def to_ollama_tools(tools: Any) -> list[dict[str, Any]]:
    """Anthropic `input_schema` is Ollama/OpenAI `parameters`; the rest matches."""
    if not isinstance(tools, list):
        return []
    out: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = tool.get("name")
        # Server-side tool types (web_search, code_execution, ...) have no local
        # equivalent and no input_schema. Skipping is the only honest option.
        if not name or "input_schema" not in tool:
            continue
        out.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema") or {"type": "object"},
                },
            }
        )
    return out


def offered_tool_names(body: dict[str, Any]) -> set[str]:
    """Which tool names this request actually put on the table."""
    return {t["function"]["name"] for t in to_ollama_tools(body.get("tools"))}


def to_ollama_request(body: dict[str, Any], model: str, keep_alive: str) -> dict[str, Any]:
    """The whole request translation, in one place."""
    options: dict[str, Any] = {
        "num_predict": int(body.get("max_tokens") or DEFAULT_MAX_TOKENS),
    }
    if body.get("temperature") is not None:
        options["temperature"] = float(body["temperature"])
    if body.get("top_p") is not None:
        options["top_p"] = float(body["top_p"])
    if body.get("top_k") is not None:
        options["top_k"] = int(body["top_k"])
    stops = body.get("stop_sequences")
    if isinstance(stops, list) and stops:
        options["stop"] = [str(s) for s in stops]

    request: dict[str, Any] = {
        "model": model,
        "messages": to_ollama_messages(body.get("system"), body.get("messages") or []),
        "stream": bool(body.get("stream")),
        "keep_alive": keep_alive,
        "options": options,
    }
    tools = to_ollama_tools(body.get("tools"))
    if tools:
        request["tools"] = tools
    return request


# --------------------------------------------------------------------------
# Response translation: Ollama -> Anthropic Messages
# --------------------------------------------------------------------------

_STOP_REASONS = {
    "stop": "end_turn",
    "length": "max_tokens",
    "load": "end_turn",
}


def _new_message_id() -> str:
    return f"msg_local_{uuid.uuid4().hex[:24]}"


def _parse_arguments(raw: Any) -> dict[str, Any]:
    """Ollama usually sends a dict; some builds send a JSON string."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _tool_use_block(name: str, arguments: Any) -> dict[str, Any]:
    return {
        "type": "tool_use",
        "id": f"toolu_local_{uuid.uuid4().hex[:20]}",
        "name": str(name),
        "input": _parse_arguments(arguments),
    }


def _strip_fence(text: str) -> str:
    """Models love to wrap JSON in ```json fences."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    body = stripped[3:]
    if body.lower().startswith("json"):
        body = body[4:]
    return body.rsplit("```", 1)[0].strip() if "```" in body else body.strip()


def recover_text_tool_calls(text: str, offered: set[str]) -> list[dict[str, Any]]:
    """Promote a tool call the model wrote as *prose* into real `tool_use` blocks.

    Not a nicety. `qwen2.5-coder:7b-instruct-q4_K_M` - the model this plugin
    ships with - answers a tools request by putting
    `{"name": "get_weather", "arguments": {"city": "Oslo"}}` in `content` and
    leaving `tool_calls` empty. Claude Code reads that as prose, the tool never
    runs, and nothing errors. A tool-driven client is useless against that.

    Deliberately narrow, because the cost of a false positive is inventing a
    tool call the user never asked for. All of these must hold:

    * tools were actually offered on this request;
    * the *entire* message body (bar a code fence) is one JSON value;
    * it is an object, or a list of objects, and nothing else;
    * every `name` is one of the offered tools.

    Prose that merely contains or discusses JSON fails the second condition and
    is left alone.
    """
    if not offered or not text:
        return []
    candidate = _strip_fence(text)
    if not candidate.startswith(("{", "[")):
        return []
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return []

    entries = parsed if isinstance(parsed, list) else [parsed]
    blocks: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            return []
        name = entry.get("name")
        if not isinstance(name, str) or name not in offered:
            return []
        arguments = entry.get("arguments", entry.get("parameters", {}))
        if not isinstance(arguments, (dict, str)):
            return []
        blocks.append(_tool_use_block(name, arguments))
    return blocks


def _tool_use_blocks(message: dict[str, Any], offered: set[str] | None = None) -> list[dict[str, Any]]:
    calls = message.get("tool_calls")
    blocks: list[dict[str, Any]] = []
    if isinstance(calls, list):
        for call in calls:
            if not isinstance(call, dict):
                continue
            function = call.get("function") or {}
            name = function.get("name")
            if not name:
                continue
            blocks.append(_tool_use_block(str(name), function.get("arguments")))
    if blocks:
        return blocks
    return recover_text_tool_calls(str(message.get("content") or ""), offered or set())


def _usage(payload: dict[str, Any]) -> dict[str, int]:
    return {
        "input_tokens": int(payload.get("prompt_eval_count") or 0),
        "output_tokens": int(payload.get("eval_count") or 0),
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }


def to_anthropic_response(
    payload: dict[str, Any],
    model: str,
    offered: set[str] | None = None,
) -> dict[str, Any]:
    """Ollama's single non-streaming reply, as an Anthropic Message."""
    message = payload.get("message") or {}
    content: list[dict[str, Any]] = []

    tool_uses = _tool_use_blocks(message, offered)
    # When the call was recovered out of the text, that same text IS the call.
    # Emitting both would show the user the raw JSON next to the tool block.
    recovered = bool(tool_uses) and not message.get("tool_calls")

    text = "" if recovered else str(message.get("content") or "")
    if text:
        content.append({"type": "text", "text": text})

    content.extend(tool_uses)

    if not content:
        content.append({"type": "text", "text": ""})

    if tool_uses:
        stop_reason = "tool_use"
    else:
        stop_reason = _STOP_REASONS.get(str(payload.get("done_reason") or "stop"), "end_turn")

    return {
        "id": _new_message_id(),
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": _usage(payload),
    }


def _sse(event: str, data: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode("utf-8")


def _could_still_be_a_tool_call(buffered: str) -> bool:
    """Is this partial text still possibly a bare JSON tool call?

    Lets ordinary prose stream token by token while holding back only the shape
    that might turn out to be a call the model wrote as text. An answer that
    genuinely opens with `{` is buffered to the end - rare, and harmless.
    """
    head = buffered.lstrip()
    if not head:
        return True
    if head.startswith("```"):
        return True
    return head.startswith(("{", "["))


def stream_anthropic_events(
    chunks: Iterator[dict[str, Any]],
    model: str,
    offered: set[str] | None = None,
) -> Iterator[bytes]:
    """Turn Ollama's NDJSON stream into Anthropic's SSE event sequence.

    Anthropic's order is fixed and clients depend on it:
    `message_start`, then per block `content_block_start` /
    `content_block_delta`* / `content_block_stop`, then `message_delta`
    carrying the stop reason, then `message_stop`.

    Ollama streams text incrementally but only resolves `tool_calls` on the
    final chunk, so tool blocks are emitted after the text block closes.
    """
    message_id = _new_message_id()

    yield _sse(
        "message_start",
        {
            "type": "message_start",
            "message": {
                "id": message_id,
                "type": "message",
                "role": "assistant",
                "model": model,
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
        },
    )

    offered = offered or set()
    text_open = False
    index = 0
    final: dict[str, Any] = {}

    # Held back only while the text so far might still resolve to a bare JSON
    # tool call (see recover_text_tool_calls). Prose flushes on its first token.
    pending = ""
    buffering = bool(offered)

    def open_text() -> Iterator[bytes]:
        yield _sse(
            "content_block_start",
            {
                "type": "content_block_start",
                "index": index,
                "content_block": {"type": "text", "text": ""},
            },
        )

    def delta(piece: str) -> bytes:
        return _sse(
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": index,
                "delta": {"type": "text_delta", "text": piece},
            },
        )

    for chunk in chunks:
        if chunk.get("done"):
            final = chunk
        message = chunk.get("message") or {}
        piece = str(message.get("content") or "")
        if not piece:
            continue

        if buffering:
            pending += piece
            if _could_still_be_a_tool_call(pending):
                continue
            # Settled: it is prose after all. Flush everything held back.
            buffering = False
            piece, pending = pending, ""

        if not text_open:
            yield from open_text()
            text_open = True
        yield delta(piece)

    recovered: list[dict[str, Any]] = []
    if pending:
        recovered = recover_text_tool_calls(pending, offered)
        if not recovered:
            if not text_open:
                yield from open_text()
                text_open = True
            yield delta(pending)

    if text_open:
        yield _sse("content_block_stop", {"type": "content_block_stop", "index": index})
        index += 1

    tool_uses = _tool_use_blocks((final.get("message") or {}), offered) or recovered
    for block in tool_uses:
        yield _sse(
            "content_block_start",
            {
                "type": "content_block_start",
                "index": index,
                "content_block": {
                    "type": "tool_use",
                    "id": block["id"],
                    "name": block["name"],
                    "input": {},
                },
            },
        )
        yield _sse(
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": index,
                "delta": {
                    "type": "input_json_delta",
                    "partial_json": json.dumps(block["input"]),
                },
            },
        )
        yield _sse("content_block_stop", {"type": "content_block_stop", "index": index})
        index += 1

    if tool_uses:
        stop_reason = "tool_use"
    else:
        stop_reason = _STOP_REASONS.get(str(final.get("done_reason") or "stop"), "end_turn")

    usage = _usage(final)
    yield _sse(
        "message_delta",
        {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": usage["output_tokens"]},
        },
    )
    yield _sse("message_stop", {"type": "message_stop"})


# --------------------------------------------------------------------------
# The server
# --------------------------------------------------------------------------


def _post_ollama(url: str, payload: dict[str, Any], timeout: float):
    request = urllib.request.Request(
        f"{url.rstrip('/')}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        if exc.code == 404 and "model" in detail.lower():
            raise ProxyError(
                f"Ollama does not have the model '{payload.get('model')}'.\n"
                f"Pull it with:  ollama pull {payload.get('model')}",
                status=404,
                kind="not_found_error",
            ) from exc
        raise ProxyError(f"Ollama returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ProxyError(
            f"Cannot reach Ollama at {url} ({exc.reason}).\nStart it with:  ollama serve",
            status=503,
        ) from exc


def _iter_ndjson(response) -> Iterator[dict[str, Any]]:
    for line in response:
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line.decode("utf-8"))
        except json.JSONDecodeError:
            continue


class ProxyHandler(BaseHTTPRequestHandler):
    """Serves the slice of the Anthropic API that Claude Code actually calls."""

    server_version = "localgpu-proxy"
    protocol_version = "HTTP/1.1"

    # Injected by make_server.
    ollama_url = DEFAULT_OLLAMA_URL
    chat_model = ""
    keep_alive = DEFAULT_KEEP_ALIVE
    timeout_seconds = DEFAULT_TIMEOUT
    verbose = False

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        if self.verbose:
            super().log_message(fmt, *args)

    # -- helpers -----------------------------------------------------------

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status: int, kind: str, message: str) -> None:
        self._send_json(status, {"type": "error", "error": {"type": kind, "message": message}})

    def _drain(self) -> bytes:
        """Always consume the request body, even on a path that ignores it.

        `protocol_version` is HTTP/1.1, so the connection persists. An unread
        body stays in the socket buffer and the handler parses it as the next
        request line - which shows up as an intermittent failure on the request
        AFTER a 404, not on the 404 itself.
        """
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length > 0 else b""

    def _read_body(self) -> dict[str, Any]:
        raw = self._drain() or b"{}"
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ProxyError(f"Request body is not JSON: {exc}", 400, "invalid_request_error")
        if not isinstance(parsed, dict):
            raise ProxyError("Request body must be a JSON object", 400, "invalid_request_error")
        return parsed

    # -- routes ------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/")
        if path in ("/health", "/v1/health"):
            self._send_json(200, {"status": "ok", "model": self.chat_model})
            return
        if path == "/v1/models":
            self._send_json(
                200,
                {
                    "data": [
                        {
                            "type": "model",
                            "id": self.chat_model,
                            "display_name": f"{self.chat_model} (local)",
                            "created_at": "2020-01-01T00:00:00Z",
                        }
                    ],
                    "has_more": False,
                },
            )
            return
        self._send_error_json(404, "not_found_error", f"No route {self.path}")

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/")
        if path != "/v1/messages":
            self._drain()
            self._send_error_json(404, "not_found_error", f"No route {self.path}")
            return
        try:
            body = self._read_body()
            if body.get("stream"):
                self._stream(body)
            else:
                self._complete(body)
        except ProxyError as exc:
            self._send_error_json(exc.status, exc.kind, str(exc))
        except Exception as exc:  # pragma: no cover - last resort
            self._send_error_json(500, "api_error", f"{type(exc).__name__}: {exc}")

    def _complete(self, body: dict[str, Any]) -> None:
        payload = to_ollama_request(body, self.chat_model, self.keep_alive)
        with _post_ollama(self.ollama_url, payload, self.timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
        self._send_json(
            200, to_anthropic_response(data, self.chat_model, offered_tool_names(body))
        )

    def _stream(self, body: dict[str, Any]) -> None:
        payload = to_ollama_request(body, self.chat_model, self.keep_alive)
        upstream = _post_ollama(self.ollama_url, payload, self.timeout_seconds)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        # Chunked, because the length is unknowable until Ollama is done.
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        try:
            offered = offered_tool_names(body)
            for frame in stream_anthropic_events(_iter_ndjson(upstream), self.chat_model, offered):
                self.wfile.write(f"{len(frame):X}\r\n".encode("ascii"))
                self.wfile.write(frame)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            upstream.close()


def make_server(
    host: str,
    port: int,
    ollama_url: str,
    chat_model: str,
    keep_alive: str = DEFAULT_KEEP_ALIVE,
    timeout: float = DEFAULT_TIMEOUT,
    verbose: bool = False,
) -> ThreadingHTTPServer:
    """Bind a proxy. Port 0 asks the OS for a free one - read it back off the
    returned server's `server_address`."""
    handler = type(
        "BoundProxyHandler",
        (ProxyHandler,),
        {
            "ollama_url": ollama_url,
            "chat_model": chat_model,
            "keep_alive": keep_alive,
            "timeout_seconds": timeout,
            "verbose": verbose,
        },
    )
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server
