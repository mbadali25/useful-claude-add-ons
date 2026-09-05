---
description: Build or update a graphify code graph for a repo, exported into the configured codegraphs vault
argument-hint: [repo-path, default cwd] [codegraphs-vault-name, default "codegraphs"]
allowed-tools: Read, Write, Bash, PowerShell
---

Build or update the graphify code graph for: $1 (default: the current repo),
exporting into the vault named $2 (default: `codegraphs`).

**The full graph never lives inside the default (memory) vault.** A repo of
any size produces a graph with more notes than a hand-curated memory vault's
own content - one real example runs to hundreds of thousands of notes across
several repos. That volume needs a **separate, full Obsidian vault of its
own** with its own Local REST API port, not a folder bolted onto the memory
vault - `/obsidian-vault:init` sets this up as a second named vault
(`obsidian.vaults.codegraphs` in config, with `"layout": "org/repo"`). This
command writes there and nowhere else for the graph itself.

## The two graphify commands - do not conflate them

Building the graph and exporting it to Obsidian are **separate subcommands**
with separate, exact flags. Getting either wrong fails in a way that looks
like success:

```bash
# 1. Build (or update) the graph - run FROM the source repo directory
graphify . --no-viz --code-only          # first build
graphify update .                        # subsequent builds, same repo

# 2. Export to the codegraphs vault - a DIFFERENT subcommand
graphify export obsidian --graph graphify-out/graph.json \
  --dir <codegraphs-vault-path>/<org>/<repo>
```

**`--no-viz --code-only` are both required** on a first build - dropping
either changes what gets built (`--no-viz` skips `graph.html` generation,
worth keeping for a large graph; `--code-only` skips whatever this graphify
install's default extra passes are). **`graphify . --obsidian` is not a
thing** - that flag is silently ignored with no error, producing a graph but
no Obsidian export, which reads as success right up until someone looks for
notes that were never written. Always use `graphify export obsidian`
explicitly as its own step.

## Steps

1. Check `graphify --version`; if missing, install it (`graphify install
   --platform claude` per its own CLI, or point at its install docs) before
   proceeding - do not silently skip the build.
2. Resolve the source repo path (`$1` or cwd) and its current commit sha
   (`git rev-parse --short HEAD` in that repo).
3. Resolve the codegraphs vault from `~/.claude/obsidian/config.json` ->
   `vaults.$2` (or `vaults.codegraphs` by default). If it is not configured,
   say so and point at `/obsidian-vault:init` rather than inventing a path -
   this is exactly the kind of guess that produces graphs nobody can find
   later.
4. Resolve `<org>/<repo>` from the source repo path: the two path segments
   immediately above the repo directory name commonly encode this
   (`.../solomon/aws-managed-services` -> `org=solomon`,
   `repo=aws-managed-services`). If the source repo does not sit under an
   `<org>/<repo>` parent structure, ask rather than guess - a wrong org
   silently scatters graphs across the vault in the wrong place.
5. Run the build from inside the source repo (`graphify . --no-viz
   --code-only` first time, `graphify update .` thereafter).
6. Run the export: `graphify export obsidian --graph graphify-out/graph.json
   --dir <codegraphs-vault-path>/<org>/<repo>` - this writes real notes
   directly into the codegraphs vault, laid out `<org>/<repo>/` to match its
   convention. Do not run `--obsidian` on the build command instead; see
   above.
7. Write or refresh a short **stub note** inside the *default* (memory)
   vault's `codegraphs/` folder, mirroring the vault's own established
   convention if it has one: node/edge/note counts, the commit sha the graph
   was built at, and the path to the codegraphs vault entry - never the graph
   content itself. This is what makes the graph discoverable from the memory
   vault without duplicating hundreds of thousands of notes into it.
8. Report node/edge/note counts and where both the export and the stub
   landed.

## Working inside the codegraphs vault afterward

**Prefer plain filesystem `Read`/`Grep` over the codegraphs vault's MCP
server**, once notes are there. At the scale this vault reaches, Omnisearch
and backlink resolution get slow; MCP calls against it are for what only the
running app can do (a plugin command, live backlinks in the Obsidian UI
itself), not for routine reading or searching. This is the opposite default
from the memory vault, where MCP's `search_query`/`vault_get_document_map`
are often the right tool - say so if a session starts reaching for MCP calls
against a codegraphs-scale vault out of habit.

## Checking the export afterward

After a build, and any time the graph looks stale or wrong, run:

```
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" graph-health --vault <name>
```

It reports the vault's `<org>/<repo>` layout, which repos have exports, and
how old each one is. Add `--fix` only when its dry-run output says what it
would remove - it removes empty export folders and nothing else.

Run it *after* a build, never instead of one. It keys off note counts and
modification times, so a vault that has just been initialised and never
exported reports empty because it is empty - that is a correct reading of a
vault with no graph in it, not a fault to chase.
