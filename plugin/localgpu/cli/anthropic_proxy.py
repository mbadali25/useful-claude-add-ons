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
* **A request too big for the local model's context window.** This is
  refused up front (see `check_fits_context`), not sent to Ollama to be
  silently truncated. Ollama has no equivalent of Anthropic's 400 for an
  oversized prompt - it drops the front of the conversation and answers
  about whatever survived, which looks exactly like success.
"""

from __future__ import annotations

import json
import sys
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

# num_predict (above) only bounds the OUTPUT. A request with no `num_ctx`
# silently runs Ollama's own built-in default INPUT window of 4096, no matter
# how large the model actually supports - the model then truncates the front
# of the prompt to fit and answers confidently about whatever survived. That
# is the whole bug this module exists to not reproduce.
#
# 32768 - qwen2.5-coder's own advertised max - and not a smaller "safer"
# number, because a smaller number was measured to break the actual job:
# a single opening turn of `localgpu shell -p` in this project's own Claude
# Code install, even with --strict-mcp-config stripping every optional MCP
# server, still comes in around 22k real tokens (measured via Ollama's
# `prompt_eval_count`) before the model has answered anything - tool
# schemas and skill listings dominate it, not the conversation. A
# conservative half-window default left no room for that and would have
# turned right back into a version of the bug this fixes: the model just
# never gets to see the actual question.
#
# The VRAM trade this makes, measured with `ollama ps` on the 8 GB card this
# was built against: qwen2.5-coder:7b-instruct-q4_K_M stays 100% GPU-resident
# (5.9 GB) through 24576, and spills to 12%/88% CPU/GPU at the full 32768
# (6.8 GB requested against 8 GB of card, with Windows/driver overhead eating
# the rest). That 12% is a real, bounded cost - slower token generation - not
# a correctness one; the alternative (fitting only the low context) makes the
# tool unable to answer at all in a normal Claude Code install. resolve_num_ctx
# still caps this at whatever a *smaller*-context model actually supports.
DEFAULT_NUM_CTX = 32768

# There is no local tokenizer for qwen2.5-coder available without adding a
# dependency, and the check this feeds only has to catch "this cannot
# possibly fit," not count exactly. 4 characters/token is the same rule of
# thumb Anthropic's own docs use for English text, and it held up against
# this model's own tokenizer on a real, tool-schema-heavy Claude Code
# request: Ollama's `prompt_eval_count` for a captured 104k-character request
# came back at 22,056 tokens - about 4.7 chars/token, i.e. this estimate runs
# slightly conservative on exactly the content this module actually sees.
_CHARS_PER_TOKEN_ESTIMATE = 4


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


def resolve_num_ctx(
    ollama_url: str,
    model: str,
    timeout: float = 10.0,
    default: int = DEFAULT_NUM_CTX,
) -> int:
    """The context window to request, capped by what the model actually supports.

    Asks Ollama's `/api/show` for the model's own advertised context length
    and returns the smaller of that and `default` - `default` exists so one
    model's huge native window does not get requested against an 8 GB card
    that cannot hold the KV cache for it (see DEFAULT_NUM_CTX), and the cap
    the other direction exists so a *smaller*-context model is never asked
    for more than it supports, which is its own failure.

    `/api/show`'s `model_info` names context length with an
    architecture-prefixed key ("qwen2.context_length", "llama.context_length",
    ...) rather than one fixed name, because that GGUF metadata field is
    namespaced under the architecture that defines it.

    Any failure here - Ollama unreachable, model not pulled yet, a build that
    does not report context_length, an unrecognised key - falls back to
    `default` rather than raising. This runs on the hot path of a session's
    first turn; a local model that already works at a documented default
    context beats a session that cannot start because a metadata probe
    failed.
    """
    try:
        request = urllib.request.Request(
            f"{ollama_url.rstrip('/')}/api/show",
            data=json.dumps({"model": model}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            info = json.loads(response.read().decode("utf-8"))
        model_info = info.get("model_info") or {}
        arch = model_info.get("general.architecture")
        context_length = model_info.get(f"{arch}.context_length")
        if not isinstance(context_length, int) or context_length <= 0:
            return default
        return min(default, context_length)
    except Exception:
        return default


def estimate_prompt_tokens(body: dict[str, Any]) -> int:
    """A cheap, deliberately conservative upper bound on the request's prompt
    size, in tokens. See `_CHARS_PER_TOKEN_ESTIMATE` for why this is a
    character count and not a real tokenizer."""
    size = len(json.dumps(body.get("system") or ""))
    size += sum(len(json.dumps(m)) for m in body.get("messages") or [])
    size += len(json.dumps(body.get("tools") or []))
    return size // _CHARS_PER_TOKEN_ESTIMATE


def check_fits_context(body: dict[str, Any], num_ctx: int) -> None:
    """Refuse a request before it ever reaches Ollama, rather than let Ollama
    truncate the front of the prompt and have the model answer confidently
    about whatever survived.

    Ollama has no equivalent of "400: prompt too long" - a prompt that does
    not fit in `num_ctx` is silently context-shifted (oldest tokens dropped)
    and generation proceeds as if nothing were missing. That silent shape is
    exactly the bug this module exists to not reproduce, so this fails loudly
    here instead.

    The reply only gets a small reservation out of `num_ctx`, not whatever
    `max_tokens` the request asked for - Claude Code routinely asks for a
    very large max_tokens (64000, in practice) regardless of how long the
    answer will actually be, and that is not the failure mode being guarded
    against here. Running out of room *during* generation already has an
    honest outcome: Ollama's "length" `done_reason` maps to Anthropic's
    "max_tokens" `stop_reason` (see `_STOP_REASONS`), a real, visible signal
    that the reply was cut short - not the silent front-truncation of the
    prompt this function exists to prevent.
    """
    requested_max = int(body.get("max_tokens") or DEFAULT_MAX_TOKENS)
    reserved_for_reply = min(requested_max, DEFAULT_MAX_TOKENS)
    estimated = estimate_prompt_tokens(body)
    budget = num_ctx - reserved_for_reply
    if estimated > budget:
        raise ProxyError(
            f"This request is an estimated ~{estimated} tokens of prompt - "
            f"more than fits in the local model's {num_ctx}-token context "
            f"window (with {reserved_for_reply} reserved so a reply can "
            "start at all). Sending it anyway would make Ollama silently "
            "drop the front of the prompt and answer about whatever "
            "survived. Shorten the conversation, or start a fresh "
            "`localgpu shell`.",
            status=400,
            kind="invalid_request_error",
        )


def to_ollama_request(
    body: dict[str, Any], model: str, keep_alive: str, num_ctx: int
) -> dict[str, Any]:
    """The whole request translation, in one place."""
    options: dict[str, Any] = {
        "num_predict": int(body.get("max_tokens") or DEFAULT_MAX_TOKENS),
        # Ollama's own default (4096) if this is left out - see DEFAULT_NUM_CTX.
        "num_ctx": int(num_ctx),
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
    """Models love to wrap JSON in ```json fences.

    Only unwraps when the fence is *all there is*. Text after the closing
    fence - a disclaimer, more explanation, anything - means this was not a
    bare tool call, so the original (still fenced) text is returned
    unchanged. The caller's `candidate.startswith(("{", "["))` check then
    disqualifies it, because it still starts with the fence marker rather
    than JSON. Without this, `rsplit("```", 1)` silently discarded trailing
    prose and let a documentation example with "do not execute this" written
    right after it be promoted to a real tool call anyway.
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    body = stripped[3:]
    if body.lower().startswith("json"):
        body = body[4:]
    if "```" not in body:
        return body.strip()
    inner, _, trailing = body.partition("```")
    if trailing.strip():
        return stripped
    return inner.strip()


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
        if isinstance(arguments, str):
            # A malformed argument string (e.g. "not json") is not a
            # degraded call - it is a different call, with input the model
            # never wrote. _parse_arguments's silent {} fallback exists for
            # Ollama's own real tool_calls (see
            # test_unparseable_arguments_degrade_to_empty_not_crash); a
            # *recovered* call earns no such benefit of the doubt, so reject
            # the whole recovery instead of promoting an empty-input call.
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                return []
        if not isinstance(arguments, dict):
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

    Ollama streams token by token, so the opening ` ``` ` of a fence can arrive
    split across chunks - a lone "`" or "``" is not yet three characters, but
    it is still a *prefix* of one and must not be judged prose early. Without
    the prefix check, `"``"` fails `startswith("```")` and (not being `{`/`[`
    either) was flushed as ordinary text, ending buffering before the rest of
    the fence and the JSON inside it ever arrived - so a fenced call that
    happened to be tokenized that way was never recovered.
    """
    head = buffered.lstrip()
    if not head:
        return True
    if head.startswith("```") or "```".startswith(head):
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
    carrying the stop reason, then `message_stop` - unless the upstream
    stream fails, in which case an `error` event replaces the last two: a
    truncated answer must never look identical to a completed one.

    Ollama streams text incrementally and resolves `tool_calls` once it has
    the full call assembled, which is usually - but not always - the same
    chunk marked `done`. Tool calls are accumulated across *every* chunk that
    carries them, not assumed to live on the final one, and not collapsed to
    whichever chunk arrives last - a multi-call reply can resolve one call
    per chunk.
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
    saw_done = False
    error_message: str | None = None
    # Every chunk that actually carried tool_calls, concatenated in arrival
    # order - not just the last one, and not necessarily the chunk marked
    # `done`. Ollama can resolve separate calls a chunk apart; overwriting
    # instead of appending here silently executed only the final batch.
    accumulated_tool_calls: list[dict[str, Any]] = []

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
        if chunk.get("error"):
            # Ollama reports a mid-stream failure (an OOM on the GPU is the
            # common one on an 8GB card) as a bare {"error": ...} object
            # instead of a "done" chunk. Stop reading - there is nothing
            # further to translate - and report it below.
            error_message = str(chunk["error"])
            break
        if chunk.get("done"):
            final = chunk
            saw_done = True
        message = chunk.get("message") or {}
        if message.get("tool_calls"):
            accumulated_tool_calls.extend(message["tool_calls"])
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

    if error_message is None and not saw_done:
        # The generator ran dry without ever seeing a "done" chunk - the
        # upstream connection dropped or the model process died mid-answer.
        # Without this check that reads exactly like a completed turn: same
        # message_delta/message_stop, an end_turn stop_reason, and whatever
        # partial text had streamed so far looking like the whole answer.
        error_message = (
            "Ollama's stream ended before a done chunk arrived - the "
            "connection dropped or the model crashed (check for an "
            "out-of-memory error on the GPU) before the reply finished."
        )

    if error_message is not None:
        if text_open:
            yield _sse("content_block_stop", {"type": "content_block_stop", "index": index})
        yield _sse(
            "error",
            {"type": "error", "error": {"type": "api_error", "message": error_message}},
        )
        return

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

    tool_source = {"tool_calls": accumulated_tool_calls} if accumulated_tool_calls else (final.get("message") or {})
    tool_uses = _tool_use_blocks(tool_source, offered) or recovered
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
            # message_start already went out with input_tokens: 0 - Ollama
            # does not report prompt_eval_count until the done chunk, which
            # is long after message_start had to be sent. Carrying the real
            # count here, alongside output_tokens, is the only point in the
            # protocol left to report it; without it every streaming turn
            # looked like it cost 0 input tokens.
            "usage": {
                "input_tokens": usage["input_tokens"],
                "output_tokens": usage["output_tokens"],
            },
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


class _QuietThreadingHTTPServer(ThreadingHTTPServer):
    """A client that hangs up mid-session is normal, not an error.

    socketserver's default `handle_error` dumps a full traceback to stderr
    for *any* uncaught exception in a request thread - including
    `ConnectionResetError: [WinError 10054]` from Claude Code simply exiting
    while the keep-alive socket was open. Nothing in `ProxyHandler` can catch
    that: it happens in `handle_one_request`'s own socket read, outside every
    try/except this module writes. A real session end should be silent, the
    same way `_stream`'s own `except (BrokenPipeError, ConnectionResetError)`
    already treats a mid-response disconnect - this is that same rule at the
    one layer above the handler.
    """

    def handle_error(self, request: Any, client_address: Any) -> None:
        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
            return
        super().handle_error(request, client_address)


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
    # None means "auto-detect via resolve_num_ctx"; make_server can pin an
    # explicit value instead. `_num_ctx_cache` is a one-slot cache so
    # auto-detection costs one extra `/api/show` round trip per *server*, not
    # per request - make_server gives each bound handler class its own dict,
    # so this base value is never actually shared or mutated.
    num_ctx: int | None = None
    _num_ctx_cache: dict[str, int] = {}

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        if self.verbose:
            super().log_message(fmt, *args)

    def _resolved_num_ctx(self) -> int:
        if self.num_ctx is not None:
            return self.num_ctx
        cached = self._num_ctx_cache.get("value")
        if cached is None:
            # Capped, not self.timeout_seconds outright - that one is sized
            # for a local model to finish *generating* (DEFAULT_TIMEOUT is
            # 600s) and a metadata lookup that should return in well under a
            # second has no business inheriting it. The min() still respects
            # a deliberately short timeout_seconds (e.g. a test proving
            # behaviour under a fast timeout) instead of overriding it.
            probe_timeout = min(self.timeout_seconds, 10.0)
            cached = resolve_num_ctx(self.ollama_url, self.chat_model, timeout=probe_timeout)
            self._num_ctx_cache["value"] = cached
        return cached

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
        num_ctx = self._resolved_num_ctx()
        check_fits_context(body, num_ctx)
        payload = to_ollama_request(body, self.chat_model, self.keep_alive, num_ctx)
        with _post_ollama(self.ollama_url, payload, self.timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
        self._send_json(
            200, to_anthropic_response(data, self.chat_model, offered_tool_names(body))
        )

    def _stream(self, body: dict[str, Any]) -> None:
        num_ctx = self._resolved_num_ctx()
        check_fits_context(body, num_ctx)
        payload = to_ollama_request(body, self.chat_model, self.keep_alive, num_ctx)
        upstream = _post_ollama(self.ollama_url, payload, self.timeout_seconds)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        # Chunked, because the length is unknowable until Ollama is done.
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        def _write_chunk(frame: bytes) -> None:
            self.wfile.write(f"{len(frame):X}\r\n".encode("ascii"))
            self.wfile.write(frame)
            self.wfile.write(b"\r\n")
            self.wfile.flush()

        try:
            offered = offered_tool_names(body)
            for frame in stream_anthropic_events(_iter_ndjson(upstream), self.chat_model, offered):
                _write_chunk(frame)
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            # `send_response`/`end_headers` above already put status line and
            # headers on the wire, and the body is already chunked - so a
            # failure here (an upstream timeout is the common one: Ollama
            # stops mid-answer and the next socket read past
            # self.timeout_seconds raises) must not propagate to do_POST's
            # handler, which would call send_response again and write a
            # second HTTP response *inside* this chunked body. That corrupts
            # the connection for the next request on this keep-alive socket.
            # Report it the same way a stream-ending error already does:
            # an SSE error event, then a valid zero-length terminator chunk.
            try:
                _write_chunk(
                    _sse("error", {"type": "error", "error": {"type": "api_error", "message": str(exc)}})
                )
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
    num_ctx: int | None = None,
) -> ThreadingHTTPServer:
    """Bind a proxy. Port 0 asks the OS for a free one - read it back off the
    returned server's `server_address`.

    `num_ctx=None` (the default) auto-detects the context window from Ollama
    on first use - see `resolve_num_ctx`. Passing an explicit value skips
    that probe entirely, for a caller that already knows what it wants.
    """
    handler = type(
        "BoundProxyHandler",
        (ProxyHandler,),
        {
            "ollama_url": ollama_url,
            "chat_model": chat_model,
            "keep_alive": keep_alive,
            "timeout_seconds": timeout,
            "verbose": verbose,
            "num_ctx": num_ctx,
            # A fresh dict per server - ProxyHandler's own `_num_ctx_cache` is
            # never mutated, so unrelated servers (each test's `endpoint`
            # fixture, for one) never share a cached value.
            "_num_ctx_cache": {},
        },
    )
    server = _QuietThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server
