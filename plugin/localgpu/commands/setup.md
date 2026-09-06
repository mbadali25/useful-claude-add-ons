---
description: Install the local model sidecar for this repo - venv, models, config, and the MCP registration
argument-hint: [--no-pull]
allowed-tools: Read, Write, Edit, Bash, Glob
---

Set this repository up to use the local GPU. Seven steps, in order, each of which
detects before it acts. `$ARGUMENTS` may contain `--no-pull` — skip step 3 and
report which models are missing instead of downloading ~5 GB.

Read `${CLAUDE_PLUGIN_ROOT}/skills/localgpu/SKILL.md` first. It holds the paths,
the config keys, and the VRAM rules this command applies.

**Ask before writing anything.** This creates files in the repo and downloads
several gigabytes. Show the plan and wait.

## Step 1 — resolve `$LOCALGPU_HOME`, and say which one

| Platform | Install root |
|---|---|
| Windows | `%LOCALAPPDATA%\localgpu` |
| Linux, macOS, WSL | `~/.local/share/localgpu` |

Print the resolved absolute path. Every later step and every error message in
this session refers to it, and a user reading "check `$LOCALGPU_HOME/index`"
cannot act on a variable that was never expanded.

Under WSL, decide deliberately which side you are on. A WSL install root with a
repo on `/mnt/c` indexes at Windows filesystem speed, which is roughly an order
of magnitude slower than a native path. Say so rather than letting it be
discovered during the first index run.

## Step 2 — is Ollama there, and is it serving

```bash
ollama --version
curl -s http://127.0.0.1:11434/api/tags
```

Both have to answer. A version with no `/api/tags` means the binary is installed
and the server is not running — on Windows that is the tray app, on Linux that is
`ollama serve` or its systemd unit. Say which one applies to the platform you
resolved in step 1.

If Ollama is absent, stop and point at its installer. Do not install it silently;
it registers a background service and a GPU runtime, and that is the user's call.

## Step 3 — pull the two models

Skip on `--no-pull`. Otherwise check `/api/tags` before pulling — a model already
present is reported as present, not re-pulled.

```bash
ollama pull nomic-embed-text
ollama pull qwen2.5-coder:7b-instruct-q4_K_M
```

Roughly 5 GB combined. Say that before starting, not after.

## Step 4 — build the environment

Run the bootstrap for the platform from step 1:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/bootstrap.sh"          # Linux, macOS, WSL
pwsh -File "${CLAUDE_PLUGIN_ROOT}/bootstrap.ps1"   # Windows
```

It creates `$LOCALGPU_HOME/venv`, installs the indexer's dependencies into it,
installs the `localgpu` console script **editable** into that venv, creates
`$LOCALGPU_HOME/index/`, sets `OLLAMA_MAX_LOADED_MODELS=1`, and finishes by
verifying that each model loads on the GPU with no CPU offload. It covers step 3
as well, so a model you skipped there is pulled here unless `--no-pull` said
otherwise. Every one of those detects first — an existing venv is reported and
reused.

The editable install is not a preference: `cli/localgpu_cli.py` finds its sibling
`mcp/` directory relative to its own `__file__`, and a copied install puts that
`__file__` in `site-packages` where `mcp/` does not exist. If it fails, report its
output verbatim; do not improvise a `pip install` around it, and never drop the
`-e`.

## Step 5 — write the config

Write `<repo>/.localgpu/config.json`. Only keys this repo actually needs to
override belong here; everything else falls back to `$LOCALGPU_HOME/config.json`
per key.

```json
{
  "roots": ["."],
  "ignore": [],
  "embed_model": "nomic-embed-text",
  "chat_model": "qwen2.5-coder:7b-instruct-q4_K_M",
  "ollama_url": "http://127.0.0.1:11434"
}
```

Leave `ignore` empty unless this repo has something extra to exclude. It is the
one key that accumulates rather than overriding — the effective list is the union
of the built-in defaults (`.git`, `node_modules`, `venv`, `dist`, `build`,
`__pycache__`, binaries, lockfiles) and whatever you put here. Restating the
defaults in the file makes it look like they can be removed, and they cannot.

Then ask the one question that is a decision rather than a default: **is
`.localgpu/` committed or ignored?** Committed shares the model choices with
everyone on the repo. Ignored keeps them personal. Either is defensible; drifting
between them is not, so record the answer by adding the entry to `.gitignore` or
by leaving it tracked, and say which you did.

Never put a secret in this file. Every key it holds is a path, a model name, or a
loopback URL.

## Step 6 — register the MCP server

One command. It resolves every path itself:

```bash
"$LOCALGPU_HOME/venv/bin/localgpu" mcp-init <repo>            # Linux, macOS, WSL
"$LOCALGPU_HOME\venv\Scripts\localgpu.exe" mcp-init <repo>   # Windows
```

**Do not hand-substitute a template.** The three values it needs are already
known to the process doing the work — `sys.executable` is the venv interpreter,
`PLUGIN_ROOT` is `__file__`'s parent, and `localgpu_home()` resolves the install
root — so a model copying placeholders by hand is a step that can go wrong and
buys nothing. That is why `mcp-init` exists.

What it does, all of it detecting before acting:

- **Verifies before writing.** If the interpreter or `mcp/server.py` is not
  actually on disk it refuses and names the missing path, rather than writing a
  registration that produces a server failing to spawn with no readable error.
- **Merges, never clobbers.** An existing `.mcp.json` keeps its other servers.
  Invalid JSON is refused, not overwritten.
- **Idempotent.** An entry that already matches reports "already registered" and
  writes nothing, exit 0.
- **Refuses a silent overwrite.** An entry that *differs* is shown as a diff and
  left alone unless `--force`. That difference is usually a plugin path pinned
  to an older localgpu, and quietly rewriting it hides that an upgrade happened.
- **Ignores the file by default.** `--no-gitignore` opts out. The paths inside
  are machine-specific, so a committed copy points at one box; everyone else
  runs `mcp-init` and gets their own.

Exit codes are honest: `0` written or already correct, `1` refused. A script may
branch on it.

**Re-run it after every localgpu upgrade.** `args` contains the plugin
directory, which is version-pinned — bump the plugin and the old path stops
existing. `mcp-init --force` re-pins it.

Then tell the user to run `/mcp` and approve the server. A project-scope
`.mcp.json` requires explicit approval and will not connect silently — a setup
that ends without that sentence looks broken to the next person who opens the
repo.

**Per repo, never plugin-level.** A plugin-shipped `.mcp.json` would spawn this
server in every repository the plugin is enabled in, each one holding a Python
process and pointing at an index that has never heard of that repo. No plugin in
this marketplace does that, and this one does not either.

## Step 7 — hand off, do not index

Setup does not build the index. Say what was created, what needs approving, and
then point at `/localgpu:index` as the next command. A first build is minutes of
GPU time and belongs to a command the user chose to run.

Mention the other half once, and only as an aside: the venv now holds a `localgpu`
console script, so `localgpu shell` can open a separate Claude Code session on the
local chat model. Nothing here puts that venv on `PATH`, so say the full path
(`$LOCALGPU_HOME/venv/bin/localgpu`, or `Scripts\localgpu.exe` on Windows) rather
than a bare command the user's shell may not resolve. `/localgpu:crew` is where
what that session may and may not be used for is written down.

Finish by running `/localgpu:doctor` and showing its report. A setup nobody
verified is a claim, not a setup.
