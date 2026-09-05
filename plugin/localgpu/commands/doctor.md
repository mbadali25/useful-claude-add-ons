---
description: Check the local model sidecar - Ollama, models, venv, config, index freshness, MCP registration
allowed-tools: Read, Bash, Glob, mcp__localgpu__search_code, mcp__localgpu__index_status
---

Diagnose every layer between this repo and the GPU, and report all of them —
including the healthy ones. A doctor that speaks only when something is wrong
gets ignored during the run where something actually is.

Report only. Offer the fix; never apply it without being asked.

## The checks

Run all seven. Each is `OK`, `WARN` or `FAIL`, one line each, plus the fix when it
is not `OK`.

### 1. Ollama is installed and serving

`ollama --version`, then `GET /api/tags` on the configured `ollama_url`. Version
without `/api/tags` is `FAIL` and means the server is down, not missing — say
which of the two it is, because the fixes are unrelated.

### 2. Both models are pulled, at the exact tags in config

Compare `/api/tags` against `embed_model` and `chat_model` as resolved from the
config. Tag equality is exact: `qwen2.5-coder:7b` is not
`qwen2.5-coder:7b-instruct-q4_K_M`, and the wrong one silently uses a different
quantization and a different amount of VRAM.

### 3. The environment exists, and the `localgpu` CLI is in it

`$LOCALGPU_HOME/venv` is present and its Python runs. A venv built for a Python
that has since been upgraded or uninstalled still has a directory, which is why
this check runs the interpreter rather than testing for the path.

Then the console script, because `/localgpu:crew` reports whether `localgpu shell`
is available on this machine and needs an answer that is not a guess:

```bash
"$LOCALGPU_HOME/venv/bin/python" -c "import localgpu_cli"     # POSIX
"$LOCALGPU_HOME/venv/bin/localgpu" --version
```

On Windows the same two, at `venv\Scripts\python.exe` and
`venv\Scripts\localgpu.exe`. Report three distinct states, because their fixes are
different:

| State | Verdict | Fix |
|---|---|---|
| Import works and `--version` answers | `OK` | Say the version, and that a bare `localgpu` only resolves if the venv is on `PATH` — nothing in this plugin puts it there |
| Neither works | `WARN` | The CLI was never installed. Re-run the bootstrap; `/localgpu:index` and `search_code` are unaffected |
| The script runs but exits saying it cannot find the plugin's `mcp/` directory | `FAIL` | A non-editable install. `"$LOCALGPU_HOME/venv/bin/python" -m pip install -e <plugin>/localgpu`, which is what the bootstrap does |

`WARN` and not `FAIL` for a missing CLI: the retrieval half of the plugin — the
part that saves context on every task — does not use it. Only `localgpu shell` and
`localgpu proxy` do.

### 4. Config resolves, and to what

Print the effective config **and where each key came from** — repo
`.localgpu/config.json`, machine `$LOCALGPU_HOME/config.json`, or the built-in
default. A merged value with no provenance is the single most confusing thing this
command can print, because the user then edits the file that was not winning.

`FAIL` on malformed JSON in either file, with the parse error verbatim. Do not
repair it silently.

### 5. The index exists, and how stale it is

Read `$LOCALGPU_HOME/index/manifest.json` and report:

| Field | Why it matters |
|---|---|
| Roots | From `last_refresh.roots`. A repo missing from this list is invisible to search, not merely stale |
| `dim` | The vector width the store was built at, 768 for `nomic-embed-text`. It is the only fingerprint of the embedding model the manifest carries |
| Chunk and file counts | A count of zero after a build that reported success means the `ignore` list ate everything |
| `updated_at`, and `last_refresh.elapsed_s` | Last build time, against the newest mtime in the working tree |

**The manifest does not record the embed model's name** — `indexer.refresh` writes
`dim`, `updated_at` and the `last_refresh` block, and nothing else identifies what
produced the vectors. So report this honestly rather than claiming a comparison the
files cannot support:

- A new `embed_model` of a **different** width is caught hard and needs no check
  here: `VectorStore` refuses to open a store whose stored `dim` disagrees, and the
  error names the fix. Surface that error verbatim if you hit it.
- A new `embed_model` of the **same** width is caught by nothing at all. Search
  quietly gets worse. If the user has changed `embed_model` since the last build,
  say that no artifact can confirm it and that `/localgpu:index --full` is the only
  safe answer.

`index_status()["embed_model"]` is the *configured* model, not the one that built
the index. Do not report it as evidence of the second.

Staleness is a `WARN` with a number: "last built 3 days ago; 41 tracked files have
changed since". "Stale" on its own tells nobody whether to care.

### 6. MCP registration

Does the repo's `.mcp.json` hold a `localgpu` entry, do its `command` and `args`
point at paths that exist, and are the three placeholders expanded? An unexpanded
`{{LOCALGPU_PYTHON}}` or a literal `${CLAUDE_PLUGIN_ROOT}` is `FAIL` — the server
will not spawn, and Claude Code's error for it does not name the cause.

Registration is not connection. If the entry is present, say that the user must
have approved the server via `/mcp` for the tools to exist, and check whether
`search_code` is actually callable in this session rather than assuming.

### 7. VRAM discipline

Report `OLLAMA_MAX_LOADED_MODELS` and `OLLAMA_KEEP_ALIVE` as the Ollama server
actually sees them, then `GET /api/ps` for what is resident right now.

`WARN` when `OLLAMA_MAX_LOADED_MODELS` is unset or above 1: on an 8 GB card with a
display attached, the embed and chat models co-residing is what causes the slow
index runs and the driver resets, and nothing else in this report will point at
it. `/api/ps` showing both models loaded at once is the same warning with
evidence attached.

Do **not** warn about a chat model whose `/api/ps` expiry is minutes away. Both
clients here send `keep_alive` per request and they send different values on
purpose — `30s` from `mcp/ollama.py` for the small embed model, `5m` from
`cli/anthropic_proxy.py` for the 4.7 GB chat model an interactive session would
otherwise reload every turn. That is the design, not drift, and reporting it as a
fault sends someone to change a default that is correct.

## Report format

One block, one line per check, in the order above. End with exactly one next step:

| If | Say |
|---|---|
| Ollama down or models missing | `/localgpu:setup` |
| Index missing, stale, or the user changed `embed_model` since it was built | `/localgpu:index` |
| MCP entry missing or unexpanded | `/localgpu:setup` re-runs step 6 only |
| The venv is fine but the `localgpu` CLI is missing or non-editable | Re-run the bootstrap; say that retrieval still works and only `localgpu shell` is affected |
| Everything is `OK` | Say that plainly and stop |

Do not print the whole menu. A report that ends in a list of options is a report
that made no judgement.
