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
config, the same way `index_status()["embed_model_present"]` and
`OllamaClient.require_models()` do it (`mcp/ollama.py`): a name matches if it is
byte-identical to an installed tag, **or** if it matches once the installed
tag's `:suffix` is stripped. That second branch is not a loophole to flag — it
is what makes a config value with no tag at all (`nomic-embed-text`) correctly
match an install Ollama tagged `nomic-embed-text:latest` on its own, which is
the normal, healthy result of a plain `ollama pull nomic-embed-text`. Comparing
those two byte-for-byte and calling it a mismatch is a false `FAIL` on a
correctly configured machine.

What *is* exact, with no leniency: two tags that both name something after the
colon. `qwen2.5-coder:7b` is not `qwen2.5-coder:7b-instruct-q4_K_M` — both sides
name a tag, they disagree, and the wrong one silently uses a different
quantization and a different amount of VRAM. Strip-and-compare only when the
config side is bare; once both sides carry a tag, they must match in full.

### 3. The environment exists, and the `localgpu` CLI is in it

`$LOCALGPU_HOME/venv` is present and its Python runs. A venv built for a Python
that has since been upgraded or uninstalled still has a directory, which is why
this check runs the interpreter rather than testing for the path.

Test that first, on its own, before anything else in this check:

```bash
"$LOCALGPU_HOME/venv/bin/python" --version
```

This is not only a CLI concern. `.mcp.json` spawns the MCP server as
`{{LOCALGPU_PYTHON}}` — this exact interpreter — so if it does not run at all,
`search_code` and `index_refresh` are down too, not just `localgpu shell`. Report
that plainly as `FAIL` and stop; the fix is the bootstrap, which rebuilds the
venv against a working interpreter.

Once the interpreter itself answers, check the console script, because
`/localgpu:crew` reports whether `localgpu shell` is available on this machine
and needs an answer that is not a guess:

```bash
"$LOCALGPU_HOME/venv/bin/python" -c "import localgpu_cli"     # POSIX
"$LOCALGPU_HOME/venv/bin/localgpu" --version
```

On Windows the same two, at `venv\Scripts\python.exe` and
`venv\Scripts\localgpu.exe`. Report three distinct states here, because their
fixes are different:

| State | Verdict | Fix |
|---|---|---|
| Import works and `--version` answers | `OK` | Say the version, and that a bare `localgpu` only resolves if the venv is on `PATH` — nothing in this plugin puts it there |
| Interpreter answered above, but neither the import nor `--version` works | `WARN` | The CLI package's editable install never ran. Re-run the bootstrap. `mcp/requirements.txt` installs into this same venv as an earlier, separate bootstrap step, so `/localgpu:index` and `search_code` are unaffected *if that earlier step completed* — say that qualifier rather than asserting it, and point at check 6's live `search_code` call as the actual proof, not this one |
| The script runs but exits saying it cannot find the plugin's `mcp/` directory | `FAIL` | A non-editable install. `"$LOCALGPU_HOME/venv/bin/python" -m pip install -e <plugin>/localgpu`, which is what the bootstrap does |

`WARN` and not `FAIL` for a missing CLI *package*: `mcp/server.py` does not import
`localgpu_cli` at all, so its absence alone does not touch retrieval. Only
`localgpu shell` and `localgpu proxy` do. That is a narrower claim than "the venv
is fine" — which is what the interpreter check above already settled.

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
| `embed_model` | The name of the model that actually built these vectors. `indexer.refresh` writes it every time, alongside `dim` |
| `dim` | The vector width the store was built at, 768 for `nomic-embed-text`. A second, lower-level safety net inside `VectorStore` — not what catches an `embed_model` swap; see below |
| Chunk and file counts | A count of zero after a build that reported success means the `ignore` list ate everything |
| `updated_at`, and `last_refresh.elapsed_s` | Last build time, against the newest mtime in the working tree |

**The manifest does record the embed model's name, and the plugin refuses an
`embed_model` swap out loud.** `check_embed_model()` (`mcp/indexer.py`) compares
the manifest's `embed_model` against the *currently configured* one — by name,
not by vector width — and it runs on **both** paths: at the start of every
`index_refresh()` and at the start of every `search_code()` call, before either
one touches Ollama. A mismatch raises `EmbedModelMismatch` immediately, and the
error names the fix. This is tested directly
(`mcp/_test/test_embed_model.py::test_same_dim_different_model_is_detected`), so
do not repeat the older claim that a same-width swap passes unnoticed — it does
not, and there is no width condition on the check at all:

- A new `embed_model` of a **different** width would also trip `VectorStore`'s
  own `dim` check if it ever got that far, but in practice `check_embed_model`
  fires first and stops it before that check is even reached.
- A new `embed_model` of the **same** width is caught exactly as hard, by the
  same name comparison, on the very next `search_code()` or `index_refresh()`
  call — not silently, and not eventually.
- A manifest with **no** `embed_model` key at all (an index built by a version
  of this plugin that predates this field) is treated as unconfirmed, not as a
  match, and raises the same way.

So if the user says they changed `embed_model`, do not preempt it with "no
artifact can confirm this, run `/localgpu:index --full` to be safe" — the very
next tool call already confirms it, on its own, with the fix named in the error.
Report the manifest's `embed_model` and the configured one side by side and say
whether they agree; if they do not, say that the next search or refresh will
refuse rather than degrade, and that `/localgpu:index --full` (or deleting the
index and letting the next refresh rebuild it) is what clears it once it does.

`index_status()["embed_model"]` is still the *configured* model, which is not
necessarily the manifest's — report both when you have reason to think they
might differ, but do not call the difference undetectable.

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
