---
name: localgpu
description: >-
  Run a local Ollama model on this machine's own GPU as a code search and Q&A
  sidecar for a repository - a semantic index built with nomic-embed-text, three
  MCP tools (search_code, index_status, index_refresh) that answer with file:line
  plus a three-line excerpt, and a qwen2.5-coder chat model for cheap questions.
  Use whenever the user mentions localgpu, Ollama, a local model, running a model
  on their own GPU or card, nomic-embed-text, qwen2.5-coder, semantic or vector
  code search over the repo, "index this repo", "search the code locally", "ask
  the local model", or wants to keep tokens or code off a hosted API. Also use it
  for the other half of the plugin - the `localgpu` command, `localgpu shell`,
  `localgpu proxy`, ANTHROPIC_BASE_URL pointed at a local endpoint, "run a whole
  Claude Code session on my own GPU" - and when they ask whether a local model can
  take over crew work, when a search returns nothing and the index may be stale,
  and when Ollama itself misbehaves - connection refused on 127.0.0.1:11434, a
  model that will not load, or a GPU that runs out of VRAM when two models are
  resident at once.
---

# localgpu

A local Ollama instance, an on-disk vector index of the repository, and three MCP
tools that read from it. Everything runs on `127.0.0.1`; nothing here calls a
hosted API.

There are two halves, and they are used for different things. The **MCP tools**
put local retrieval inside the session you are already in — that is the half that
earns its keep on almost every task. The **`localgpu` command** puts a separate
Claude Code session on the local chat model, through a proxy that translates the
Anthropic Messages API into Ollama's `/api/chat`. Reach for the second only when
the whole session should be local; it is not a mode for the current one.

This skill is the reference behind the six `/localgpu:*` commands and both
`localgpu` subcommands. The commands are the entry points; read this when a
command hits something it did not expect, or when the user asks how the pieces fit.

## What is where

| Thing | Path |
|---|---|
| Install root, Windows (incl. Git Bash/MSYS) | `%LOCALAPPDATA%\localgpu` |
| Install root, real POSIX (Linux/macOS) | `~/.local/share/localgpu` |
| Python environment | `$LOCALGPU_HOME/venv` |
| `localgpu` console script | `$LOCALGPU_HOME/venv/bin/localgpu`, `$LOCALGPU_HOME\venv\Scripts\localgpu.exe` on Windows |
| Vectors | `$LOCALGPU_HOME/index/vectors.f16` |
| Metadata | `$LOCALGPU_HOME/index/meta.sqlite` |
| Index manifest | `$LOCALGPU_HOME/index/manifest.json` |
| Repo config | `<repo>/.localgpu/config.json` |
| Machine config | `$LOCALGPU_HOME/config.json` |

`$LOCALGPU_HOME` is the install root above. Refer to it by name in prose; resolve
it to the real path before running anything. Git Bash/MSYS on Windows can reach BOTH
paths, so `bootstrap.sh` resolves to the Windows one there too (T-0002) - it is never
safe to assume the POSIX default just because a POSIX-shaped shell is running.

The index is **per machine, not per repo**. One `vectors.f16` holds every root the
config lists, and `meta.sqlite` is what tells a hit which root and which file it
came from. Two repositories indexed on one machine share the file and are
separated by their `root` column, which is why `search_code` takes a `root`
argument at all.

## Configuration

Read `<repo>/.localgpu/config.json` first; fall back to `$LOCALGPU_HOME/config.json`
for any key it does not set. The fallback is per key, not per file - a repo config
that sets only `roots` still gets the machine's model choices.

| Key | Type | Default | What it does |
|---|---|---|---|
| `roots` | list of paths | the current directory | Directories that get indexed, resolved absolute |
| `ignore` | list of globs | see below | Paths excluded before embedding |
| `unignore` | list of globs | `[]` | Drops a pattern from the effective `ignore` list — see below |
| `embed_model` | string | `nomic-embed-text` | Ollama model that produces vectors |
| `chat_model` | string | `qwen2.5-coder:7b-instruct-q4_K_M` | Ollama model that answers questions |
| `ollama_url` | string | `http://127.0.0.1:11434` | Where Ollama listens |

**`ignore` is the one key that does not override — it accumulates.** The effective
list is the union of the built-in defaults and every layer's entries, deduplicated.
So a repo config can add to it and cannot subtract from it directly, and a user
asking why `dist/` is still excluded after they emptied the list is asking about
intended behaviour. The built-in list covers `.git`, `node_modules`, `venv`,
`.venv`, `dist`, `build`, `__pycache__`, binary and lockfile extensions, and a
deliberately broad set of credential patterns — `.env`, `.env.*`, `*.pem`,
`*.key`, `*.p12`, `*.pfx`, `id_rsa*`, `credentials.json`. That breadth is a
tradeoff made on purpose: a secret the indexer embeds into the on-disk vector
store is a permanent second copy, while a file wrongly excluded from indexing
is not — it is just missing from search until someone notices.

**`unignore` is how a wrongly-excluded file comes back.** `"unignore": ["*.key"]`
removes the whole `*.key` pattern from the effective `ignore` list — pattern
removal, not a per-file exemption, so every `.key` file is indexed again, not
just the one that prompted the change. It layers the same way `ignore` does:
either config layer can list it, and the two accumulate rather than one
overriding the other. Three entries cannot be lifted this way no matter what a
config asks for — `.git`, `.localgpu`, and `node_modules` — because indexing
those is not a preference anyone holds, it is a mistake. Listing one is a
**hard error**, not a silently discarded line: `load_config` raises and names
the entry. Dropping it quietly would leave the floor intact and the user
re-reading their own config for a typo that was never there. If a search is missing
a file, check the `ignore` list `/localgpu:index` reports before assuming the
indexer is broken.

**Changing `embed_model` invalidates the whole index, and this plugin refuses to
let that happen silently.** Vectors from one embedding model are not comparable
to vectors from another. `manifest.json` records the embed model's *name*
(`indexer.refresh` writes it, alongside `dim` and the last refresh's counts),
and `check_embed_model()` (`mcp/indexer.py`) compares that stored name against
the currently configured `embed_model` — by name, not by vector width — on
every single `index_refresh()` and every `search_code()` call. A mismatch
raises immediately, before anything is touched, and names the fix. A same-width
swap is caught exactly as hard as a different-width one; there is no quiet
middle case where search "just gets worse" unnoticed. A manifest missing the
`embed_model` key entirely (an index built before this field existed) is
treated the same way - unconfirmed, not a match.

`index_status()["embed_model"]` is still the currently *configured* model, not
necessarily the one that built the index - report both when they might differ,
but do not call the difference invisible: the next tool call proves it either
way, on its own. If a user says they changed `embed_model`, the coming error
confirms it without help; `/localgpu:index --full` (or deleting the index and
letting the next refresh rebuild it) is the fix once that happens, not a hedge
against uncertainty.

## The models, and why these two

| Role | Model | Size on disk | Dimensions |
|---|---|---|---|
| Embedding | `nomic-embed-text` | ~270 MB | 768 |
| Chat | `qwen2.5-coder:7b-instruct-q4_K_M` | ~4.7 GB | n/a |

768 dimensions at float16 is 1,536 bytes per chunk, so a hundred thousand chunks is
roughly 150 MB of vectors. That is the whole reason the file is `f16` rather than
`f32`: the accuracy loss on a cosine ranking is not measurable, and the file halves.

## VRAM discipline

The target machine is an 8 GB card **with a display attached**, so the desktop, the
browser, and anything else with a GPU surface are already holding a slice. A 4.7 GB
chat model and a 270 MB embed model both fit, but not alongside the working set of
a long index run.

Two settings keep them from co-residing:

```bash
OLLAMA_MAX_LOADED_MODELS=1     # server-side; Ollama evicts one model to load the other
```

plus an explicit `keep_alive` on every request the client makes (`"keep_alive":
"30s"` in the JSON body, or `OLLAMA_KEEP_ALIVE=30s` on the server as the blunt
version). Without a short keep-alive on the indexing side,
`OLLAMA_MAX_LOADED_MODELS=1` still leaves the last model resident for five minutes
by default, which is long enough for the next command to fight it for memory.

Symptoms when this is wrong: an index run that slows by an order of magnitude
partway through, `cuda malloc` or `out of memory` in the `ollama serve` log, or the
display driver resetting. All three mean two models were resident, not that the
card is too small.

### The two keep-alive defaults are deliberate

They differ, and a reader who finds both will assume one is a mistake. Neither is:

| Client | Default | Holds | Why |
|---|---|---|---|
| `mcp/ollama.py` — indexing and search | `30s` | `nomic-embed-text`, ~270 MB | Thousands of back-to-back `/api/embed` calls. It only has to survive the gap between two of them, and reloading it costs a fraction of a second. Anything longer just blocks the chat model |
| `cli/anthropic_proxy.py` — the chat proxy | `5m` | `qwen2.5-coder:7b-instruct-q4_K_M`, ~4.7 GB | A person thinks between turns. At 30s it unloads while they read the last answer, and every turn then reopens with a ~10 s cold load |

The rule underneath both: the model that is cheap to reload gets the short lease,
the model that is expensive to reload gets the long one. The cost of the long one
is that a chat turn keeps the embed model out for up to five minutes — which is
why interleaving `/localgpu:ask` or `localgpu shell` with an index run is the one
combination to avoid. `localgpu shell --keep-alive 30s` trades the latency back if
both really are needed at once.

Neither default is changed from here. If a user wants different behaviour, it is
`--keep-alive` on the command, not an edit to the module.

## The MCP tools

Exactly three, registered in the repository's `.mcp.json` by `/localgpu:setup`.

| Tool | Signature | Returns |
|---|---|---|
| `search_code` | `search_code(query, k=10, root=None, path_glob=None)` | Ranked hits: `file:line` plus an excerpt of **at most 3 lines** |
| `index_status` | `index_status()` | Root list, chunk and file counts, embed model, last build time, staleness |
| `index_refresh` | `index_refresh(root=None)` | Chunks added, updated, removed, and how long it took |

**`search_code` never returns a whole file, and must not be asked to.** It hands
back a location and just enough text to judge whether the location is the right
one; you then `Read` the specific range you decided you needed. This is the same
discipline `crew:explorer` follows, and for the same reason - a tool that returns
files turns a cheap lookup into a context-budget event, and the thing that made the
lookup worth doing disappears.

`path_glob` filters before ranking, so `path_glob="**/*.ps1"` with `k=10` gives ten
PowerShell hits rather than ten hits of which two happen to be PowerShell. Use it
whenever the question is already scoped to a language or a subtree.

`root` selects one indexed root when the machine has several. Omitted, it searches
all of them, which is usually wrong once a second repo is indexed - hits from
another project look identical in the output.

## When search returns nothing

In this order, because each step rules out the next one's cause:

1. `index_status()` - is there an index at all, and does its root list contain the
   file you expect? A repo added to `roots` after the last build is simply absent.
2. Is it stale? Compare the manifest's build time against the working tree. A file
   written since the last refresh has no vector and cannot be found by meaning.
3. Does `ignore` exclude it? A `dist/` or `build/` glob catching generated code the
   user considers source is the common one.
4. Is the query semantic or lexical? Embedding search finds *ideas*. An exact
   symbol name, a magic string, or an error code is a `Grep` job - say so and use
   `Grep` rather than re-running the search with different words.

That last one is a routing rule, not a fallback. Reach for `Grep` first for anything
you could have found with an exact string, and for `search_code` when you do not
know what the code calls the thing you are looking for.

## The `localgpu` command

A console script installed into `$LOCALGPU_HOME/venv` by the bootstrap, editable
(`pip install -e`) because `localgpu_cli.py` locates its sibling `mcp/` directory
relative to its own `__file__`. Two subcommands:

| Command | What it does |
|---|---|
| `localgpu shell [args for claude]` | Starts the proxy on a loopback port, then launches a **separate** `claude` process with `ANTHROPIC_BASE_URL` and `ANTHROPIC_API_KEY` set for that child only. Trailing arguments pass through to `claude` |
| `localgpu proxy` | The same proxy in the foreground, printing its URL. For debugging it, or for a client that is not Claude Code |

Flags: `--model` (override `chat_model` for this run, writes nothing), `--port`
(`shell` defaults to a free port, `proxy` to `8817`), `--host` (`proxy` only),
`--keep-alive`, and `--verbose` on `shell` — `proxy` is always verbose.

Both preflight before they start anything: Ollama must answer and `chat_model`
must be pulled. `shell` additionally needs `claude` on `PATH`, and says so rather
than failing three prompts in. Nothing adds the venv to `PATH`, so a bare
`localgpu` only resolves if the user put it there — check for the script inside
`$LOCALGPU_HOME/venv` and quote that full path, rather than recommending a command
their shell may not find.

Two environment variables are deliberately **removed** from the child:
`ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_PROFILE`. Either would outrank the API key
and send the session back to the hosted API — silently, which is the worst way to
find out you were never on the local model.

### What the proxy carries

`ANTHROPIC_BASE_URL` does not mean "any OpenAI-compatible server". Claude Code
POSTs `/v1/messages` in the Anthropic Messages format; Ollama's OpenAI surface is
`/v1/chat/completions` with a different body, so the two 404 at each other.
`cli/anthropic_proxy.py` is the translation, not a convenience wrapper.

Intact across it: system prompts, multi-turn text, tool definitions, tool calls,
tool results, stop sequences, temperature, and both streaming and non-streaming
replies.

Not carried, and reported rather than faked — say which one applies when a user
reports something missing:

| Not carried | What the proxy does instead |
|---|---|
| Images | Replaces the block with a visible placeholder. A 7B coder model has no vision, and a dropped block would make the turn incoherent for no stated reason |
| Thinking blocks | Nothing is synthesised; no local model emits them |
| Prompt caching | `cache_control` accepted and ignored, with zero cache hits reported rather than invented |
| Token counts | Ollama's own prompt and eval counts, passed through. Not Anthropic's tokenizer, and they will not match it |

The shipped chat model answers a tools request by writing the call into `content`
as JSON text with `tool_calls` empty. The proxy promotes that to a real `tool_use`
block, only for a tool the request actually offered. Without it the shell cannot
drive a single tool. `cli/_test/` holds the tests and the sabotage log.

### When to reach for it

| Situation | Answer |
|---|---|
| Save context on a task in this session | The MCP tools. Not the shell |
| Explore or draft with tokens that cost nothing | `localgpu shell` |
| A client that is not Claude Code, or debugging the translation | `localgpu proxy` |
| Any crew gate — review, security, planning | Neither. See `/localgpu:crew` |

*Everything* in a shell session is the 7B, including any `/crew:*` command run
inside it, and a review produced there is labelled exactly like a real one.
Nothing enforces that boundary, which is why it is written down in the README, in
`/localgpu:crew`, and in the banner the shell prints on every launch — and why
this skill will not describe the shell as a way to "use crew on the local model".

## Talking to Ollama directly

Useful when a command's own error is not specific enough:

```bash
curl -s http://127.0.0.1:11434/api/tags     # is it up, and what is pulled
curl -s http://127.0.0.1:11434/api/ps       # what is resident right now
curl -s http://127.0.0.1:11434/api/embed -d '{"model":"nomic-embed-text","input":"hello","keep_alive":"30s"}'
```

`/api/ps` is the one that settles a VRAM argument: it names every loaded model and
its size, so "two models are resident" stops being a theory.

| Symptom | Cause | Fix |
|---|---|---|
| `connection refused` on 11434 | `ollama serve` is not running | Start it; on Windows the tray app owns it |
| `model 'x' not found` | Never pulled, or pulled under a different tag | `ollama pull <exact tag from config>` |
| Embeddings all zero, or the wrong length | `embed_model` names a chat model | Only an embedding model answers `/api/embed` usefully |
| First call after idle takes ~10 s | Model loading from disk | Expected; that is what `keep_alive` shortens or lengthens |
| `localgpu: command not found` | The venv is not on `PATH`, and nothing here puts it there | Run the console script by its full path under `$LOCALGPU_HOME/venv` |
| `localgpu: cannot find <plugin>/mcp` | Installed non-editable — `localgpu_cli.py` is in `site-packages`, with no sibling `mcp/` | `pip install -e <plugin>/localgpu` with the venv's own Python, or re-run the bootstrap |
| A client pointed at Ollama 404s every request | `/v1/messages` against `/v1/chat/completions` | Point it at `localgpu proxy` instead |

## Safety rails

- **Never index a path the user did not name.** `roots` is explicit. Do not add a
  home directory, a parent of the repo, or a sibling checkout because it looked
  related - the index is readable by anything that can read `$LOCALGPU_HOME`.
- **Ask before rebuilding.** A full rebuild of a large repo is minutes of GPU time
  and evicts whatever else was loaded. `/localgpu:index` confirms first;
  `index_refresh` is incremental and does not need to.
- **Never write secrets into `.localgpu/config.json`.** Every key it holds is a
  path, a model name, or a localhost URL. There is nothing to authenticate to.
- **`.localgpu/` is committed or ignored - decide, do not drift.** Committing it
  shares model choices with the team, which is usually what you want. What must
  never be committed is the index, and the index is not in the repo, which is the
  other reason it lives under `$LOCALGPU_HOME`.
- **A local 7B answer is a lead, not a verdict.** Say which model produced any
  answer relayed from `chat_model`, every time. See `/localgpu:crew` for where that
  boundary matters most.
- **Never change the current session's model.** `localgpu shell` exists because
  the alternatives — editing `.crew/config.json`, exporting `ANTHROPIC_BASE_URL`
  into the running session, shimming a provider binary — all move a gate onto a
  weaker model while everything still reports normally. A second process is the
  only version of this that stays honest, and it is still not for gate commands.
