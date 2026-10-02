# External tool output formats crew relies on

crew parses the output of three tools it does not own: the Codex CLI (the
review stream), `wsl.exe` (tool resolution on Windows) and `gh` (posting a
review to a pull request). Since L-0574 it also parses four linters' output
before a review round is reserved; they have their own section at the end. This page records what crew relies on from each,
where the fact comes from, and what was probed on which host. Every fact
carries its source and the date it was read. When a tool's output changes,
this page is the first thing to check, and
`plugin/crew/tests/test_external_tool_formats.py` holds crew's call sites and
the golden corpus to it (T-0087). Two Windows facts crew's launch and its
golden corpus depend on, batch-file shims and the corpus checkout, follow the
three tools.

A probe that could not run is recorded as "not probed", with the reason.
It is never a pass.

## Codex CLI

**What crew calls.** `review_run.command_for` (`plugin/crew/hooks/scripts/review_run.py:237-247`)
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
parser (`review_run.py:432`) turns any of those into INCOMPLETE of class
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

**A host with no distribution.** The hosted `windows-latest` runner has
`wsl.exe` on PATH and no WSL distribution installed, so `wsl.exe --list --quiet`
prints nothing under either encoding (PR #260, run 36538308986, where the
probe's first assertion read `assert b'\x00' in b''`). That is "could not
tell", not a wrong encoding: `_probe_wsl_encoding` in
`plugin/crew/tests/test_external_tool_formats.py` skips with `listed no
distribution` and the exit code whenever either listing exits non-zero or holds
nothing but NULs and line ends, and still fails when a distribution answers and
`WSL_UTF8=1` does not change the encoding.

Probed: not probed. The T-0087 host is Linux (Ubuntu) with no `wsl.exe`, so `test_wsl_list_is_utf16_unless_wsl_utf8` skips visibly there. The hosted Windows runner has `wsl.exe` but no distribution, so it skips there too, saying so. It runs for real on a Windows host with a distribution installed.

## Windows batch shims

**What crew calls.** On Windows, `shutil.which("codex")` or `shutil.which("copilot")`
resolves an npm-installed CLI to its `.cmd` shim. `review_run.through_batch_shim`
(`plugin/crew/hooks/scripts/review_run.py:212`) names a provider whose resolved
path ends `.cmd` or `.bat` (`BATCH_SHIM_SUFFIXES`, `:173`), and
`review_run.prompt_argument` (`:219`) never hands such a provider the prompt
inline: it passes the one-line pointer to `prompt.txt` that an over-limit prompt
already gets, and says why on stderr.

**The format.** A batch file is not an executable: to run one, CreateProcess
must start the command interpreter, `cmd.exe /c` plus the batch file's name
(https://learn.microsoft.com/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw,
read 2026-09-29). npm on Windows, and every tool installed with
`npm install -g`, is such a batch file
(https://learn.microsoft.com/azure/devops/pipelines/tasks/reference/cmd-line-v2?view=azure-pipelines,
read 2026-09-29). Python's `subprocess` says a `.bat` or `.cmd` may be launched
in a system shell whatever arguments are passed, so the arguments are parsed by
shell rules without Python's escaping
(https://docs.python.org/3/library/subprocess.html, "Security Considerations",
read 2026-09-29). cmd.exe also caps the command line of a batch file at 8191
characters, below crew's 24000-character `INLINE_PROMPT_LIMIT`
(https://learn.microsoft.com/troubleshoot/windows-client/shell-experience/command-line-string-limitation,
read 2026-09-29). None of those pages states in so many words that cmd.exe ends
a batch file's arguments at the first line break; that part is what the probe
below showed.

Probed: the hosted `windows-latest` runner, PR #260 (run 36538308986, 2026-09-29). With the prompt passed inline through the test stub's `codex.cmd`, both inline canaries in `plugin/crew/tests/test_review_canary.py` reported `no READ line for 16 of 16 bundle part(s)`: the stub received only the prompt's first line. The over-limit canary, which passes the one-line pointer, passed on the same runner.

## Golden corpus checkout

`plugin/crew/tests/golden/review/` is a byte-exact replay of real reviewer
output, and the committed blobs hold LF and no CR. An autocrlf checkout rewrote
it to CRLF on PR #260's Windows job, so
`test_golden_codex_stream_yields_its_out_txt` compared a stream's `\n` lines
with an `out.txt` ending `\r\n`. `plugin/crew/tests/golden/.gitattributes`
holds `* -text`, which turns off end-of-line conversion for the corpus only
(https://git-scm.com/docs/gitattributes, "Unsetting the text attribute",
read 2026-09-29).
`test_golden_corpus_is_checked_out_without_line_ending_conversion` pins the
attribute and `test_golden_corpus_files_carry_no_carriage_return` pins the bytes.

Probed: a `core.autocrlf=true` clone on the T-0087 host (Linux), 2026-09-29. Without the attribute, `out.txt` came out with `\r\n` and the CI assertion failed there. With it, the corpus came out LF only and both golden and canary suites passed.

## gh

**What crew calls.** `plugin/crew/commands/review.md:513-517` posts the review
outcome with `gh pr review <PR> --request-changes --body-file <out.txt>` when
there is any BLOCK, and with `gh pr review <PR> --approve --body "<reviewer>: CLEAN"`
when there is none. `plugin/crew/skills/crew-providers/SKILL.md:195` reads
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

## Pre-review linters (L-0574)

**What crew calls.** `review_checks.py` runs each linter `.crew/verify.json`
lists under `preReview` once, over both throwaway trees (base and bundle),
with stdin closed and argv lists only. The `command` slot may replace the
binary (this repo runs ShellCheck and actionlint through pinned `uvx`
packages). Facts below were probed on this Linux host on 2026-10-01 with
ruff 0.16.9, ShellCheck 0.11.0 (`shellcheck-py==0.11.0.1`), actionlint
1.7.12 (`actionlint-py==1.7.12.25`) and PSScriptAnalyzer 1.25.0 under pwsh
7.6.5. They were not probed on Windows.

| Tool | Invocation | Exit statuses read as "ran" | Output crew reads | Parse-abort marker |
|------|------------|-----------------------------|-------------------|--------------------|
| ruff | `check --output-format json --exit-zero --no-cache --extend-select E902 <args> <files>` | 0 | a JSON list; `filename` (absolute), `code`, `message` | `code` `invalid-syntax` (null codes are read as it), or `E902` (the file could not be read, e.g. not UTF-8; selected always, because an unselected E902 reports nothing): ruff then reports nothing else for that file |
| ShellCheck | `-f json1 --rcfile <bundle .shellcheckrc>` (or `--norc` when the bundle has none) `<args> <files>` | 0 none, 1 findings (2 unreadable file, 3 bad syntax, 4 bad options are errors) | `{"comments": [...]}`; `file` (as passed), `code` (int, read as `SC<code>`), `message` | `SC1072` ("Fix any mentioned problems and try again"): parsing of that file stopped; `SC1071`: a shell ShellCheck does not check (zsh, fish) |
| actionlint | `-format '{{json .}}' -no-color -shellcheck= -pyflakes= [-config-file <bundle .github/actionlint.y(a)ml>] <args> <files>` (1.7.12 discovers only `actionlint.yaml` by itself) | 0 none, 1 findings (2 bad flag, 3 fatal are errors) | a JSON list; `filepath` (as passed), `kind`, `message` | `kind` `syntax-check` |
| PSScriptAnalyzer | `pwsh -NoProfile -NonInteractive -File <script> <file-list> <rule-list>` | 0 (the script exits 3 on any error, an unknown `-IncludeRule` name included) | one JSON line from `ConvertTo-Json`; `file`, `rule`, `severity`, `message` | `severity` `ParseError` |

Each linter runs with stdin closed, a copy of the environment with every
variable whose name carries TOKEN, SECRET, PASSWORD, API_KEY or CREDENTIAL
dropped, and `XDG_CONFIG_HOME` pointed at an empty directory, so a
user-level ruff config cannot judge the bundle. `HOME` is kept, because
`uvx`'s cache and PowerShell's user module path live under it. A `command`
that resolves to a `.cmd`/`.bat` shim is refused as could-not-check, because
cmd.exe would re-parse the file names.

actionlint's embedded shellcheck and pyflakes passes are switched off by
name: actionlint silently skips them when those binaries are not on PATH, so
leaving them on would make one bundle's answer depend on the host. `run:`
scripts inside workflows are therefore not checked by this pass. PowerShell
file names go to `-Path` escaped with `WildcardPattern.Escape`, because
`-Path` takes wildcards and `a[1].ps1` would otherwise match nothing and read
as clean. A file git calls binary (a UTF-16 `.ps1`) is still handed to the
linter, and the tool decides whether it can read it. Before counting, line
and column positions inside a message are read as `N` (`line 3`, `column 9`,
a `2:28:` pair), because ruff (`from line 3`) and actionlint
(`SC2086:info:2:28`) quote them. Every other digit is kept, so a changed
value (`requires 2` to `requires 3`) is a new finding. A row with no
`message` string is "could not check".

**How crew reads it.** Anything outside the table is "could not check",
never a pass: another exit status, a timeout, output that is not the JSON
shown (empty output included), a field missing from a row, or, for
ShellCheck and actionlint, a status that contradicts the output (exit 1 with
no findings, or exit 0 with some). A bad row, or a contradicting status, does
not throw away the rows that could be read: a new finding among them still
refuses. A bad row naming a base-side file leaves only that file unchecked,
because its base count is short. A timeout kills the linter's whole process
group (`taskkill /T` on Windows), and covers a child left holding the output
open after the linter exits. A parse-abort marker on either side
makes that file "could not check" too, because the tool did not analyse it.
That covers only that file: a new finding in any other file still refuses
the round, and `--allow-unverified` does not override it.
`-IncludeRule` silently ignores a rule name PSScriptAnalyzer does not know,
so the script compares the allowlist with `Get-ScriptAnalyzerRule` first. The
tests that pin these shapes are `tests/test_review_checks.py` (one fake
speaking all four formats, plus real ruff and real PSScriptAnalyzer cases,
which are skipped with a reason when the tool is absent).

