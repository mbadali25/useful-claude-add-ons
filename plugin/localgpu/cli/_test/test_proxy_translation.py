"""The wire format, tested without binding a socket.

Every assertion here is about a shape Claude Code will actually send or parse.
The reason this file exists at all is that `ANTHROPIC_BASE_URL` speaks the
Anthropic Messages format and Ollama does not, so a mistranslation is invisible
until a real session misbehaves.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Set up inline rather than in a conftest.py. Both _test directories would
# import as the top-level module `conftest`, and mcp/_test/conftest.py exports
# fixtures its tests import by name - a second file of that name silently wins
# and breaks them. See cli/_test/README.md.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthropic_proxy as proxy  # noqa: E402


# -- request: system + messages -------------------------------------------


def test_string_system_becomes_a_system_turn():
    out = proxy.to_ollama_messages("be terse", [{"role": "user", "content": "hi"}])
    assert out[0] == {"role": "system", "content": "be terse"}
    assert out[1] == {"role": "user", "content": "hi"}


def test_block_list_system_is_joined():
    system = [{"type": "text", "text": "one"}, {"type": "text", "text": "two"}]
    out = proxy.to_ollama_messages(system, [])
    assert out == [{"role": "system", "content": "one\n\ntwo"}]


def test_absent_system_adds_no_turn():
    out = proxy.to_ollama_messages(None, [{"role": "user", "content": "hi"}])
    assert [m["role"] for m in out] == ["user"]


def test_text_blocks_are_flattened():
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}
    ]
    assert proxy.to_ollama_messages(None, messages) == [{"role": "user", "content": "a\n\nb"}]


def test_image_blocks_are_announced_not_dropped():
    """A silently dropped image makes the surrounding text unanswerable."""
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "data": "..."}},
                {"type": "text", "text": "what is wrong here?"},
            ],
        }
    ]
    content = proxy.to_ollama_messages(None, messages)[0]["content"]
    assert "image omitted" in content
    assert "what is wrong here?" in content


def test_thinking_blocks_are_stripped():
    messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "secret"},
                {"type": "text", "text": "answer"},
            ],
        }
    ]
    assert proxy.to_ollama_messages(None, messages)[0]["content"] == "answer"


# -- request: the tool round trip -----------------------------------------


def test_assistant_tool_use_becomes_tool_calls():
    messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "looking"},
                {"type": "tool_use", "id": "toolu_1", "name": "grep", "input": {"q": "x"}},
            ],
        }
    ]
    out = proxy.to_ollama_messages(None, messages)[0]
    assert out["content"] == "looking"
    assert out["tool_calls"] == [{"function": {"name": "grep", "arguments": {"q": "x"}}}]


def test_tool_results_move_out_of_the_user_turn():
    """Anthropic puts tool results in a user message; Ollama wants role=tool."""
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "toolu_1", "content": "42"},
                {"type": "text", "text": "and now?"},
            ],
        }
    ]
    out = proxy.to_ollama_messages(None, messages)
    assert out[0] == {"role": "tool", "content": "42"}
    assert out[1] == {"role": "user", "content": "and now?"}


def test_tool_result_only_turn_emits_no_empty_user_message():
    messages = [
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": "ok"}]}
    ]
    assert proxy.to_ollama_messages(None, messages) == [{"role": "tool", "content": "ok"}]


def test_input_schema_becomes_parameters():
    tools = [{"name": "grep", "description": "search", "input_schema": {"type": "object"}}]
    assert proxy.to_ollama_tools(tools) == [
        {
            "type": "function",
            "function": {"name": "grep", "description": "search", "parameters": {"type": "object"}},
        }
    ]


def test_server_side_tools_are_skipped():
    """web_search has no input_schema and no local equivalent."""
    tools = [
        {"type": "web_search_20260209", "name": "web_search"},
        {"name": "grep", "input_schema": {"type": "object"}},
    ]
    assert [t["function"]["name"] for t in proxy.to_ollama_tools(tools)] == ["grep"]


# -- request: options ------------------------------------------------------


def test_max_tokens_maps_to_num_predict():
    req = proxy.to_ollama_request({"max_tokens": 64, "messages": []}, "m", "5m")
    assert req["options"]["num_predict"] == 64


def test_missing_max_tokens_falls_back_rather_than_crashing():
    req = proxy.to_ollama_request({"messages": []}, "m", "5m")
    assert req["options"]["num_predict"] == proxy.DEFAULT_MAX_TOKENS


def test_stop_sequences_map_to_stop():
    req = proxy.to_ollama_request({"messages": [], "stop_sequences": ["END"]}, "m", "5m")
    assert req["options"]["stop"] == ["END"]


def test_keep_alive_is_always_sent():
    """The VRAM bargain: nothing may linger on an 8GB card by default."""
    req = proxy.to_ollama_request({"messages": []}, "m", "30s")
    assert req["keep_alive"] == "30s"


def test_no_tools_key_when_there_are_none():
    assert "tools" not in proxy.to_ollama_request({"messages": []}, "m", "5m")


# -- response: non-streaming ----------------------------------------------


def test_text_reply_becomes_a_text_block():
    out = proxy.to_anthropic_response(
        {"message": {"content": "hello"}, "done_reason": "stop"}, "qwen"
    )
    assert out["type"] == "message"
    assert out["role"] == "assistant"
    assert out["model"] == "qwen"
    assert out["content"] == [{"type": "text", "text": "hello"}]
    assert out["stop_reason"] == "end_turn"


def test_length_maps_to_max_tokens():
    out = proxy.to_anthropic_response({"message": {"content": "x"}, "done_reason": "length"}, "m")
    assert out["stop_reason"] == "max_tokens"


def test_tool_calls_become_tool_use_and_flip_stop_reason():
    payload = {
        "message": {
            "content": "",
            "tool_calls": [{"function": {"name": "grep", "arguments": {"q": "x"}}}],
        },
        "done_reason": "stop",
    }
    out = proxy.to_anthropic_response(payload, "m")
    assert out["stop_reason"] == "tool_use"
    block = [b for b in out["content"] if b["type"] == "tool_use"][0]
    assert block["name"] == "grep"
    assert block["input"] == {"q": "x"}
    assert block["id"].startswith("toolu_")


def test_string_arguments_are_parsed():
    """Some Ollama builds send arguments as a JSON string."""
    payload = {
        "message": {"tool_calls": [{"function": {"name": "g", "arguments": '{"q": 1}'}}]},
    }
    block = [b for b in proxy.to_anthropic_response(payload, "m")["content"] if b["type"] == "tool_use"][0]
    assert block["input"] == {"q": 1}


def test_unparseable_arguments_degrade_to_empty_not_crash():
    payload = {"message": {"tool_calls": [{"function": {"name": "g", "arguments": "not json"}}]}}
    block = [b for b in proxy.to_anthropic_response(payload, "m")["content"] if b["type"] == "tool_use"][0]
    assert block["input"] == {}


def test_empty_reply_still_has_a_content_block():
    """An empty content list is not a valid Anthropic Message."""
    out = proxy.to_anthropic_response({"message": {"content": ""}}, "m")
    assert out["content"] == [{"type": "text", "text": ""}]


def test_usage_passes_ollama_counts_through_and_zeroes_cache():
    out = proxy.to_anthropic_response(
        {"message": {"content": "x"}, "prompt_eval_count": 11, "eval_count": 7}, "m"
    )
    assert out["usage"]["input_tokens"] == 11
    assert out["usage"]["output_tokens"] == 7
    assert out["usage"]["cache_read_input_tokens"] == 0


# -- response: streaming ---------------------------------------------------


def _events_with_tools(chunks):
    return _events(chunks, offered={"get_weather", "grep"})


def _events(chunks, offered=None):
    """Parse the SSE byte stream back into (event, data) pairs."""
    raw = b"".join(proxy.stream_anthropic_events(iter(chunks), "m", offered)).decode("utf-8")
    out = []
    for frame in raw.strip().split("\n\n"):
        lines = frame.split("\n")
        event = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        out.append((event, data))
    return out


def test_stream_emits_the_required_event_order():
    events = _events(
        [
            {"message": {"content": "he"}},
            {"message": {"content": "llo"}},
            {"done": True, "done_reason": "stop", "eval_count": 2},
        ]
    )
    assert [e for e, _ in events] == [
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]


def test_stream_deltas_reassemble_to_the_full_text():
    events = _events(
        [{"message": {"content": "he"}}, {"message": {"content": "llo"}}, {"done": True}]
    )
    text = "".join(
        d["delta"]["text"] for e, d in events if e == "content_block_delta"
    )
    assert text == "hello"


def test_stream_carries_stop_reason_on_message_delta():
    events = _events([{"message": {"content": "x"}}, {"done": True, "done_reason": "length"}])
    delta = [d for e, d in events if e == "message_delta"][0]
    assert delta["delta"]["stop_reason"] == "max_tokens"


def test_stream_with_no_text_opens_no_text_block():
    """Ollama can answer with tool calls and no prose at all."""
    events = _events(
        [
            {
                "done": True,
                "done_reason": "stop",
                "message": {"content": "", "tool_calls": [{"function": {"name": "g", "arguments": {}}}]},
            }
        ]
    )
    kinds = [d.get("content_block", {}).get("type") for e, d in events if e == "content_block_start"]
    assert kinds == ["tool_use"]


def test_stream_tool_use_sets_stop_reason_and_indexes_after_text():
    events = _events(
        [
            {"message": {"content": "ok"}},
            {
                "done": True,
                "message": {"tool_calls": [{"function": {"name": "g", "arguments": {"a": 1}}}]},
            },
        ]
    )
    starts = [(d["index"], d["content_block"]["type"]) for e, d in events if e == "content_block_start"]
    assert starts == [(0, "text"), (1, "tool_use")]
    delta = [d for e, d in events if e == "message_delta"][0]
    assert delta["delta"]["stop_reason"] == "tool_use"


def test_stream_tool_input_is_sent_as_input_json_delta():
    events = _events(
        [{"done": True, "message": {"tool_calls": [{"function": {"name": "g", "arguments": {"a": 1}}}]}}]
    )
    delta = [d for e, d in events if e == "content_block_delta"][0]
    assert delta["delta"]["type"] == "input_json_delta"
    assert json.loads(delta["delta"]["partial_json"]) == {"a": 1}


# -- recovering a tool call the model wrote as prose -----------------------
#
# qwen2.5-coder:7b-instruct-q4_K_M answers a tools request by putting the call
# in `content` as JSON and leaving `tool_calls` empty. Verified against the real
# model. Without recovery the tool never runs and nothing errors.

OFFERED = {"get_weather", "grep"}


def test_bare_json_call_is_promoted_to_tool_use():
    payload = {
        "message": {"content": '{"name": "get_weather", "arguments": {"city": "Oslo"}}'},
        "done_reason": "stop",
    }
    out = proxy.to_anthropic_response(payload, "m", OFFERED)
    assert out["stop_reason"] == "tool_use"
    assert out["content"] == [
        {
            "type": "tool_use",
            "id": out["content"][0]["id"],
            "name": "get_weather",
            "input": {"city": "Oslo"},
        }
    ]


def test_fenced_json_call_is_promoted():
    payload = {"message": {"content": '```json\n{"name": "grep", "arguments": {"q": "x"}}\n```'}}
    out = proxy.to_anthropic_response(payload, "m", OFFERED)
    assert [b["type"] for b in out["content"]] == ["tool_use"]


def test_the_raw_json_is_not_also_shown_as_text():
    """Emitting both would put the raw call next to the tool block."""
    payload = {"message": {"content": '{"name": "grep", "arguments": {}}'}}
    out = proxy.to_anthropic_response(payload, "m", OFFERED)
    assert not [b for b in out["content"] if b["type"] == "text"]


def test_recovery_is_off_when_no_tools_were_offered():
    payload = {"message": {"content": '{"name": "grep", "arguments": {}}'}}
    out = proxy.to_anthropic_response(payload, "m", set())
    assert out["content"] == [{"type": "text", "text": '{"name": "grep", "arguments": {}}'}]
    assert out["stop_reason"] == "end_turn"


def test_an_unoffered_tool_name_is_not_invented():
    payload = {"message": {"content": '{"name": "rm_rf", "arguments": {"path": "/"}}'}}
    out = proxy.to_anthropic_response(payload, "m", OFFERED)
    assert [b["type"] for b in out["content"]] == ["text"]


def test_prose_mentioning_json_is_left_alone():
    text = 'You could call {"name": "grep", "arguments": {}} to search.'
    assert proxy.recover_text_tool_calls(text, OFFERED) == []


def test_a_json_object_that_is_not_a_call_is_left_alone():
    assert proxy.recover_text_tool_calls('{"city": "Oslo"}', OFFERED) == []


def test_streaming_recovers_a_buffered_json_call():
    events = _events_with_tools(
        [
            {"message": {"content": '{"name": "get_'}},
            {"message": {"content": 'weather", "arguments": {"city": "Oslo"}}'}},
            {"done": True, "done_reason": "stop"},
        ]
    )
    kinds = [d["content_block"]["type"] for e, d in events if e == "content_block_start"]
    assert kinds == ["tool_use"]
    delta = [d for e, d in events if e == "message_delta"][0]
    assert delta["delta"]["stop_reason"] == "tool_use"


def test_streaming_prose_is_not_buffered_to_the_end():
    """Ordinary prose must still arrive token by token, not in one lump."""
    events = _events_with_tools(
        [
            {"message": {"content": "Hello "}},
            {"message": {"content": "there"}},
            {"done": True, "done_reason": "stop"},
        ]
    )
    deltas = [d["delta"]["text"] for e, d in events if e == "content_block_delta"]
    assert deltas == ["Hello ", "there"]
