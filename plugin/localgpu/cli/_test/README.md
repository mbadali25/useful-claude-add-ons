# `cli/_test`

Covers `cli/anthropic_proxy.py` and `cli/localgpu_cli.py` — the `localgpu shell`
half of the plugin. Nothing here needs Ollama, a GPU, or a network.

The runner in the plugin root finds the bootstrap's interpreter for you and runs
**both** suites in one pytest invocation, which is the run that counts — see
"Why there is no `conftest.py`" below:

```bash
./run-tests.sh                                    # POSIX, and Git Bash on Windows
pwsh -NoProfile -File run-tests.ps1               # Windows
./run-tests.sh --cli                              # this suite only, for narrowing a red run
```

By hand, if you would rather name the interpreter yourself:

```bash
"$LOCALAPPDATA/localgpu/venv/Scripts/python.exe" -m pytest cli/_test -q   # Windows
"$LOCALGPU_HOME/venv/bin/python" -m pytest cli/_test -q                   # POSIX
```

| File | What it holds down |
|---|---|
| `test_proxy_translation.py` | The wire format as pure functions — system prompts, content blocks, the tool-call round trip, options, non-streaming replies, and the SSE event sequence |
| `test_proxy_server.py` | The same proxy on a real socket against a fake Ollama — routing, status codes, chunked SSE framing, and the text a user sees when Ollama is down or the model is not pulled |
| `test_cli.py` | The `localgpu` command: the child environment that decides which API the launched session really reaches, `cmd_shell`'s wiring and proxy shutdown, `_find_claude` and `_preflight` error text, and every parser default. Starts no process and binds no socket |

`test_cli.py`'s centre of gravity is `_child_env`. `ANTHROPIC_AUTH_TOKEN` and
`ANTHROPIC_PROFILE` outrank `ANTHROPIC_API_KEY` in Anthropic's credential
resolution, so if either survives into the child, `localgpu shell` prints a
banner claiming a local 7B and then talks to the real API — no error, no
symptom, and a bill. Those tests set both in the parent environment first,
because a test that only proves an absent variable stays absent proves nothing.

## Why there is no `conftest.py` here

There was, and it broke `mcp/_test`. Both directories are outside any package,
so pytest imports each `conftest.py` as the **same top-level module name**,
`conftest`. `mcp/_test/conftest.py` exports helpers its tests import by name
(`from conftest import TEST_DIM`), so a second file of that name wins the
import and every one of those modules fails to collect — but only when both
suites run in the same invocation, which is exactly what a full run does.

The path setup is therefore inlined at the top of each test module here. If you
add a file, copy those three lines rather than reintroducing a `conftest.py`.

## Sabotage log

A test that cannot fail is decoration. Each of these was reintroduced as a real
edit to the source named, and the suite confirmed red.

| Sabotage | Went red |
|---|---|
| Tool calls no longer flip `stop_reason` to `tool_use` | `test_tool_calls_become_tool_use_and_flip_stop_reason` |
| `tool_result` blocks stay in the user turn instead of becoming `role: "tool"` | `test_tool_results_move_out_of_the_user_turn`, `test_tool_result_only_turn_emits_no_empty_user_message` |
| Text recovery stops checking the tool was actually offered | `test_an_unoffered_tool_name_is_not_invented` |
| Streaming buffers all prose instead of only possible-JSON | `test_streaming_prose_is_not_buffered_to_the_end` |
| `_child_env` stops popping `ANTHROPIC_AUTH_TOKEN` (`localgpu_cli.py`) — the silent fall-back to the real API | `test_child_env_credentials_that_outrank_the_api_key_are_dropped`, `test_child_env_drops_them_even_when_they_are_empty`, `test_shell_launches_claude_with_the_sanitised_environment` |

## The recovery, and why it is not optional

`qwen2.5-coder:7b-instruct-q4_K_M` — the chat model this plugin ships with —
answers a tools request by writing the call into `content` as JSON and leaving
`tool_calls` empty. Verified against the real model on this machine:

```
Ollama /api/chat returned:
  {"role": "assistant",
   "content": "{\"name\": \"get_weather\", \"arguments\": {\"city\": \"Oslo\"}}"}
  done_reason: stop        <- and no tool_calls field at all
```

Claude Code reads that as prose. The tool never runs, `stop_reason` stays
`end_turn`, and nothing errors — the same silent failure the Anthropic docs
describe for thinking-disabled models. `recover_text_tool_calls` promotes it to
a real `tool_use` block, under four conditions that all have a must-not-fire
test above. Without it `localgpu shell` cannot drive a single tool, which is
most of what Claude Code does.
