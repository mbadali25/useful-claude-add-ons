# Plugin updates

New capability added under `plugin/`, newest first. Each entry names the version
it landed in, so a reader can tell what their installed copy actually has. For
fixes and internal changes, see [`CHANGELOG.md`](../CHANGELOG.md); this file is
only what is newly *possible*.

Mirrored into [`plugin/README.md`](README.md) and the root
[`README.md`](../README.md) by `scripts/sync-updates.py`. Edit here, then run it.

## localgpu 0.1.0

A new plugin: the GPU in this machine, as a sidecar for one repository. Two
halves - a semantic index the session you are already in can search, and a
separate session that runs entirely on the local model.

| Added | What it does |
|---|---|
| `/localgpu:setup` | Six detect-then-act steps - resolve the install root, verify Ollama is installed *and* serving, pull the two models, run the bootstrap (venv, dependencies, the `localgpu` CLI), write the config, register the MCP server. Asks before writing anything, and will not install Ollama silently |
| `/localgpu:doctor` | Seven checks - Ollama, model tags, venv, config provenance, index freshness, MCP registration, VRAM - each reported whether or not it passes, ending in exactly one next step |
| `/localgpu:index` | Build or refresh the vector index. Incremental by default; a changed embedding model forces a full rebuild, because vectors from two models are not comparable |
| `/localgpu:search` | Semantic search of the repo - `file:line` plus a three-line excerpt, via the `search_code` MCP tool |
| `/localgpu:ask` | Retrieve first, then put the question and the excerpts to the local chat model. Always labelled `qwen2.5-coder:7b (local)`, always with its sources |
| `/localgpu:crew` | Report-only: which crew roles a local 7B could take over and which it must not, ending in the one supported route - `localgpu shell`. Writes nothing |
| `localgpu shell` | A **separate** Claude Code session on the local model. Starts the bundled proxy on a loopback port, launches a second `claude` against it, and leaves your current session and crew's config exactly as they were |
| `localgpu proxy` | The same proxy in the foreground, for debugging it or for pointing something other than Claude Code at the local model |
| `localgpu` skill | The paths, the two config layers and their precedence, the model tags, the VRAM rules, and the `mcp.json` template the commands render |

`localgpu shell` and `localgpu proxy` are a console script, not slash commands:
the bootstrap installs it into `$LOCALGPU_HOME/venv`, and you type it in a
terminal. What makes them possible is `cli/anthropic_proxy.py`, which speaks the
**Anthropic Messages API** on the front and Ollama's `/api/chat` on the back.
That translation is the feature, not plumbing: `ANTHROPIC_BASE_URL` makes a
client POST `/v1/messages`, while Ollama's OpenAI-compatible surface is
`/v1/chat/completions` with a different body, so pointing one straight at the
other 404s on every request.

- **What crosses intact**: system prompts, multi-turn text, tool definitions,
  tool calls, tool results, stop sequences, sampling options, and both reply
  modes - non-streaming and Anthropic's SSE event order.
- **What does not, and is reported rather than faked**: images (replaced with a
  visible placeholder, because a 7B coder model has no vision), thinking blocks,
  prompt caching (`cache_control` accepted and ignored, cache usage reported as
  zero), and token counts, which are Ollama's own and will not match Anthropic's
  tokenizer.
- **Tool calls the model writes as prose are recovered.** The shipped
  `qwen2.5-coder:7b-instruct-q4_K_M` answers a tools request by putting the call
  into `content` as JSON and leaving `tool_calls` empty. Claude Code reads that as
  prose: the tool never runs and nothing errors. The proxy promotes it to a real
  `tool_use` block under four narrow conditions, each with a must-not-fire test,
  so it cannot invent a call the user never asked for. Without it the shell could
  not drive a single tool.
- **The catch, printed on every launch because nothing enforces it**: everything
  in that session is the 7B, including any `/crew:*` command run inside it. Use it
  for exploring and drafting, not for gates - a 7B review is labelled exactly like
  a real one. The child process also has `ANTHROPIC_AUTH_TOKEN` and
  `ANTHROPIC_PROFILE` stripped, since either would outrank the API key and send the
  session back to the real API without saying so.

Also worth knowing before enabling it:

- **No hooks, so nothing starts running when it is enabled.** There is no
  background indexer and no watcher - the index goes stale until someone runs
  `/localgpu:index`. That is deliberate: GPU work firing on somebody else's
  schedule evicts whatever model was resident, which on an 8 GB card is the
  difference between a fast index run and a slow one.
- **Installing the plugin downloads nothing.** Ollama, the virtualenv and roughly
  5 GB of model weights come from `/localgpu:setup`, per repository, after it has
  shown the plan and asked.
- **Nothing leaves the machine.** No prompt, no file and no embedding reaches a
  vendor, which is the point - code that is not permitted to reach an API still
  gets search by meaning and a fast first-pass answer.
- **The local model is a triage tier, not a second opinion.** A 7B model at 4-bit
  quantization sits several tiers below the model reading these commands, so
  every command that reaches for it attributes the answer and prints the excerpts
  it was given.

## crew 0.15.1

Three new agents and a skill, taking crew to 14 agents and 17 bundled skills.

| Added | What it does |
|---|---|
| `infrastructure-architect` | Designs and reviews AWS network and account architecture — VPCs, routing, connectivity, DNS, ingress, landing zones. Returns the design with its tradeoffs. Never applies anything to a live account. |
| `scribe` | Keeps the durable record: ADRs, CHANGELOG entries, handoff notes, and what was tried and rejected. ADRs are append-only — a correction is a new ADR, never an edit to the old one. |
| `researcher` | External research only — library and SDK docs at the version actually pinned, API behaviour, vendor limits, standards. Every claim carries its source; it refuses to answer a version, a limit, or an API surface from memory. |
| `crew-house-style` skill | House style for documents a human will read: format choice, headings, capitalization, palette. Routes to the office and diagram skills rather than reimplementing generation. |

Also in 0.15.0:

- **`docs-writer` exports for humans.** Documentation a person will consume ships
  as HTML, DOCX or PDF, not raw markdown. The markdown under `docs/` stays the
  source of truth — the export is an additional artifact, so anything reading
  those paths keeps working. Repo-native files (`CHANGELOG.md`, `README.md`,
  `CLAUDE.md`, ADRs) stay markdown, because exporting one breaks the tool that
  reads it. `docs-writer` also gained the return contract it never had.
- **`dba` covers DynamoDB as its own model**, not as a row in a relational
  checklist — access-pattern-first, single-table design, partition-key
  cardinality, GSI backfill cost, the creation-time-only nature of LSIs, and the
  400KB item limit. Relational review is now split by engine, because lock
  behaviour under `ALTER TABLE` differs across Postgres, MySQL/InnoDB and SQL
  Server, and the old text applied Postgres vocabulary to all three.
- **`planner` asks what a decision forecloses** — whether it is one-way, what
  undoing it costs later, and the cheapest experiment that would settle it before
  committing.
- **Agents can now load the skills they cite.** Eight agents referenced a crew
  skill without declaring `skills:` frontmatter, so the reference was decoration:
  naming a skill does not load it. `browser-tester`, `docs-writer`,
  `infrastructure-architect`, `planner`, `pm`, `qa-reviewer`, `scribe` and
  `smoke-author` now declare what they cite.
- **`explorer` no longer orders a write it cannot perform.** It held
  `Read, Grep, Glob` and was told to append findings to memory; it now returns a
  `**Durable:**` block for its caller to persist.
- **The PM's guards apply on every path.** Removal needing an explicit yes was
  previously gated to `authority: act`, which switched it off exactly when a user
  told a `report-only` PM to go ahead.
