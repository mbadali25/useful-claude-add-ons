---
description: Build or refresh the local semantic index of this repo
argument-hint: [--full] [--root <path>]
allowed-tools: Read, Bash, Glob, mcp__localgpu__index_refresh, mcp__localgpu__search_code
---

Embed this repository into `$LOCALGPU_HOME/index/` so `search_code` has something
to search. `$ARGUMENTS`:

| Argument | Effect |
|---|---|
| none | Incremental refresh of every configured root |
| `--root <path>` | Incremental refresh of that root only |
| `--full` | Discard the index artifacts and rebuild from nothing. See step 1 — this is not a switch the code has, and it is machine-wide |

Read `${CLAUDE_PLUGIN_ROOT}/skills/localgpu/SKILL.md` for the config resolution and
the VRAM rules before running anything.

## Step 1 — say what is about to happen, then wait for `--full`

Report the resolved roots, the `ignore` list in effect, how many files match, and
the embed model. If a file the user expects is missing, this is the list to check
first — the credential patterns (`*.env`, `*.pem`, `*.key`, and friends) are
deliberately broad, because a wrongly-included secret written into the vector
store is permanent while a wrongly-excluded file is not. `"unignore": ["*.key"]`
in either config layer drops that whole pattern from the effective `ignore` list
(pattern removal, not a per-file exemption — see `load_config`'s docstring in
`mcp/config.py`). `.git`, `.localgpu`, and `node_modules` cannot be lifted this
way, and asking to is a hard error rather than a line that quietly does
nothing — the config fails to load and names the entry. Then:

- **Incremental** — go. It touches only files whose content hash changed, and
  doing nothing is its normal outcome on a clean tree.
- **`--full`** — confirm first. A full rebuild of a large repo is minutes of GPU
  time and evicts whatever model was resident. Say the estimate before asking.

A full rebuild is genuinely required in exactly one case, and it is not a
judgement call: `embed_model` has changed since the vectors were built. Vectors
from two embedding models are not comparable, and mixing them would degrade
every future search — which is exactly why this plugin refuses to let it happen
silently.

`manifest.json` records the embed model's *name* (`indexer.refresh` writes it),
and `check_embed_model()` (`mcp/indexer.py`) compares that name against the
currently configured `embed_model` on every single `index_refresh()` and
`search_code()` call — by name, not by vector width, so a same-width swap is
caught exactly as hard as a different-width one. A mismatch raises immediately,
before anything is touched, with the fix named in the error. A manifest with no
`embed_model` key at all (an index built before this field existed) is treated
as unconfirmed, not as a match, and raises the same way. So if the user says
they changed `embed_model`, the very next `index_refresh()` or `search_code()`
call will say so on its own — `--full` is the fix once that error actually
names the mismatch (or once you already know a rebuild is wanted, e.g.
switching the default model on purpose), not a hedge run pre-emptively against
an undetectable failure.

**There is no `--full` switch in the code.** `index_refresh(root=None)` is the only
entry point the plugin ships, and it is incremental by construction. `--full` here
means: remove the artifacts in `$LOCALGPU_HOME/index/` and let the next refresh
rebuild them. Say that out loud before doing it, because the index is **per
machine** — deleting `vectors.f16` and `meta.sqlite` discards every root indexed on
this box, not just this repo's, and every other project pays for the rebuild too.
When another root is present and the reason is only this repo's staleness, prefer
`--root <path>` and an ordinary refresh.

## Step 2 — hold one model, and only one

Before the run, confirm `OLLAMA_MAX_LOADED_MODELS=1`. An index run is thousands of
sequential `/api/embed` calls; if the chat model is still resident on an 8 GB card,
the embed model competes with it for the whole run. The symptom is not an error —
it is the run getting an order of magnitude slower partway through, which reads as
"big repo" rather than "misconfigured".

The embedding client sends `"keep_alive": "30s"` on every call itself
(`mcp/ollama.py`), so there is nothing to set for this run. What can be in the way
is the *chat* model: the proxy behind `/localgpu:ask` and `localgpu shell` holds it
for `5m` on purpose, because an interactive session would otherwise reload 4.7 GB
every turn.

`GET /api/ps` before starting. If the chat model is loaded, say so, and say how
long its lease has left rather than guessing — then either wait it out or evict it
deliberately. A shell session opened in the last five minutes is the usual reason.

## Step 3 — run it, and report numbers

Report, from `index_refresh`'s own return value, which carries exactly these keys:

- `scanned`, `files_added`, `files_reindexed`, `files_unchanged`, `files_deleted`.
- `chunks_added` and `chunks_tombstoned` — a re-indexed file tombstones its old
  windows and appends new ones, so "updated" is those two numbers together, not a
  field of its own.
- `elapsed_s`, and `compacted` when the tombstone ratio triggered a compaction.
- The manifest's new `updated_at`.

Files excluded by `ignore` are never scanned, so there is no count of them to
report. Say that rather than inventing one — a "0 skipped" line implies the
`ignore` list was checked and matched nothing, which is the opposite of what
happened.

**Zero chunks on a first build or a `--full` rebuild is a failure report, not a
success one.** It almost always means the `ignore` list matched everything, or
`roots` points at a directory that does not exist — `refresh` skips a root that
does not exist without complaining, so `scanned: 0` is the tell. Say which, rather
than reporting "0 files indexed" as though it were a clean pass.

On an incremental run the same numbers mean the opposite: `chunks_added: 0` with a
non-zero `scanned` and `files_unchanged` is exactly what a clean tree looks like.
Read `scanned` before judging `chunks_added`.

## Step 4 — prove it answers

Run one real query against something you know is in the repo and show the hits.
An index nobody queried is a file, not a working index — the same reason
`/localgpu:setup` ends by running `/localgpu:doctor`.

## When to run this

| Situation | Command |
|---|---|
| After `/localgpu:setup` | `--full`, once |
| After pulling a branch with substantial changes | no arguments |
| A search misses a file you know exists | no arguments, then re-search |
| `embed_model` changed | `--full`, non-negotiable |
| A second repo added to `roots` | `--root <that path>` |

The MCP `index_refresh(root=None)` tool does the incremental case without a slash
command, which is what an agent mid-task should call. Use this command when the
user wants to see the numbers, or when a full rebuild is on the table — a rebuild
is a decision, and a tool call is not the place to make one.
