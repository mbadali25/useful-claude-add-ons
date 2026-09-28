# External tool output formats crew relies on

crew parses the output of three tools it does not own: the Codex CLI (the
review stream), `wsl.exe` (tool resolution on Windows) and `gh` (posting a
review to a pull request). This page records what crew relies on from each,
where the fact comes from, and what was probed on which host. Every fact
carries its source and the date it was read. When a tool's output changes,
this page is the first thing to check, and
`plugin/crew/tests/test_external_tool_formats.py` holds crew's call sites and
the golden corpus to it (T-0087).

A probe that could not run is recorded as "not probed", with the reason.
It is never a pass.

## Codex CLI

**What crew calls.** `review_run.command_for` (`plugin/crew/hooks/scripts/review_run.py:135-143`)
runs `codex exec` with these flags and nothing else:

| Flag | Meaning |
|------|---------|
| `--json` | print the run as JSON Lines on stdout, one event per line |
| `--sandbox` | sandbox policy; crew passes `read-only`, so the reviewer cannot edit the code |
| `--skip-git-repo-check` | run even where Codex does not recognise a trusted git repository |
| `-C` | working directory (long form `--cd`) |
| `--model` | model, only when `qa.model` is set (short form `-m`) |
| `-c` | config override (long form `--config`); crew passes `model_reasoning_effort=<effort>` only when an effort is set |

stdin is always closed. A real run hung waiting on it.

**The stream.** Each line is one JSON object whose `type` names the event:
`thread.started`, `turn.started`, `turn.completed`, `turn.failed`,
`item.started`, `item.updated`, `item.completed`, `error`. An item event
carries `item.type`: `agent_message`, `reasoning`, `command_execution`,
`file_change`, `mcp_tool_call`, `web_search`, `todo_list`.
Sources: https://learn.chatgpt.com/docs/non-interactive-mode (redirected from
https://developers.openai.com/codex/noninteractive), read 2026-09-28.

The source of truth is `codex-rs/exec/src/exec_events.rs`
(https://github.com/openai/codex/blob/main/codex-rs/exec/src/exec_events.rs,
read 2026-09-28). `ThreadEvent` is `#[serde(tag = "type")]` with the eight
event names above. `TurnFailedEvent` holds `error: ThreadErrorEvent { message }`.
Item details are `#[serde(tag = "type", rename_all = "snake_case")]`.

**Where the docs and the source diverge.** The source also defines item types
`collab_tool_call` and `error`, and the docs page does not list them.
`review_verdict.CODEX_ITEM_TYPES` (`plugin/crew/hooks/scripts/review_verdict.py:82`)
follows the source. `CODEX_EVENT_TYPES` (`:80`) is the eight event names.

**Line separators arrive raw.** serde_json escapes only bytes 0x00-0x1F, `"`
and `\` (its `ESCAPE` table, https://github.com/serde-rs/json/blob/master/src/ser.rs,
read 2026-09-28). So U+2028 and U+2029 inside a message reach the stream
unescaped. Python's `str.splitlines()` splits on them and cuts one event in
two. `review_verdict.codex_final_message` (`:192`) splits on `"\n"` only. That
bug cost T-0072 its round 4. The golden corpus commits one stream that carries
raw U+2028 (`plugin/crew/tests/golden/review/uca-t0072--T-0072-build--2BJpY8/events.jsonl`).

**How crew reads it.** `codex_final_message` returns the last
`agent_message` item's text. It counts a turn as complete only on
`turn.completed`. A `turn.failed`, an `error` event or an unparseable line is
an error, and a stream with no completed turn is also an error. The verdict
parser (`review_run.py:421`) turns any of those into INCOMPLETE of class
`tool`, which is refunded. Every event and item type in the committed corpus is
one of the documented types (`test_golden_codex_events_use_documented_types`).
On 2026-09-28, the 26 local streams used only `thread.started`, `turn.started`,
`item.started`, `item.completed` and `turn.completed`, with items of type
`agent_message` and `command_execution`. Several streams carry more than one
`agent_message`, and only the last one is the answer.

Probed: codex-cli 0.155.1 on Linux (Ubuntu), 2026-09-28. `codex exec --help` lists `--json`, `-s, --sandbox`, `--skip-git-repo-check`, `-C, --cd`, `-m, --model`, `-c, --config`, `-o, --output-last-message`. The live stream probe (`CREW_PROBE_LIVE=1`, run once by hand, 2026-09-28) hit the account's usage limit. It did not get its CLEAN, but it did capture the real failure shape: four lines, `thread.started`, `turn.started`, then a top-level `error` event carrying `message`, then `turn.failed` carrying `error.message`, all of them documented types. `codex_final_message` returned no message and the limit text as the error, which the verdict parser records as an INCOMPLETE of class `tool` (refunded). A CLEAN live run is still unprobed.

## wsl.exe

**What crew calls.** On Windows, `plugin/crew/skills/crew-setup/scripts/platform.ps1:8`
runs `wsl --list --quiet` and strips NUL characters from the result.
`plugin/crew/skills/crew-setup/scripts/resolve-tools.sh:136-153` runs
`wsl.exe -e ...` and pipes the output through `tr -d '\r'`.

**The format.** `wsl.exe` writes its own output, such as `--list`, as UTF-16LE
without a BOM (https://github.com/microsoft/WSL/issues/4607, read 2026-09-28).
Read as bytes or as UTF-8, every other byte is NUL. Output from a command run
inside the distribution (`wsl.exe -e ...`) is that command's own bytes. It
carries CRLF line ends when it crosses into Windows, which is why the script
strips `\r`.

**The switch.** Setting `WSL_UTF8=1` makes `wsl.exe` write UTF-8. Microsoft's
WSL product manager recommends setting it, because a UTF-8 default is under
consideration (Craig Loewen in https://github.com/containers/podman/issues/26527,
citing https://github.com/microsoft/WSL/issues/13093, both read 2026-09-28).
crew does not set it. It strips NULs instead, which works under either encoding.

Probed: not probed. The T-0087 host is Linux (Ubuntu) with no `wsl.exe`, so `test_wsl_list_is_utf16_unless_wsl_utf8` skips visibly there. It runs on a Windows or WSL-interop host.

## gh

**What crew calls.** `plugin/crew/commands/review.md:514-519` posts the review
outcome with `gh pr review <PR> --request-changes --body-file <out.txt>` when
there is any BLOCK, and with `gh pr review <PR> --approve --body "<reviewer>: CLEAN"`
when there is none. `plugin/crew/skills/crew-providers/SKILL.md:179` reads
`gh api orgs/<org>/copilot/billing --jq '.cli'`.

**The format.** `gh` exits 0 on success, 1 on failure, 2 when cancelled and 4
when authentication is required, and individual commands may add more codes
(https://cli.github.com/manual/gh_help_exit-codes, read 2026-09-28).
`gh pr review` takes `--approve`, `--comment`, `--request-changes`, `--body`
and `--body-file`, and `--request-changes` needs a body
(https://cli.github.com/manual/gh_pr_review, read 2026-09-28). `gh api` prints
the response as JSON, and `--jq` selects from it
(https://cli.github.com/manual/gh_api, read 2026-09-28).

Probed: gh version 2.46.0 on Linux (Ubuntu), 2026-09-28. `gh pr review --help` lists `-a, --approve`, `-b, --body`, `-F, --body-file`, `-c, --comment`, `-r, --request-changes`.
