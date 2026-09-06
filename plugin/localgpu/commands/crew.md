---
description: Report honestly which crew work a local 7B could take over, and which it must not
allowed-tools: Read, Bash, Grep
---

Answer one question, for this repo, without flattering the local model: **what
crew work can move onto the GPU in this box, and what cannot.**

Report only. This command writes nothing — not `.crew/config.json`, not an
environment variable, not a shim on `PATH`. Read the "what this command will not
do" section before doing anything else; it is the reason the command exists.

## Step 0 — is crew even set up here

Read `.crew/config.json`. If there is no `.crew/` directory, say so plainly and
keep going — everything below is a statement about crew's design, not about this
repo's configuration, and it is worth reading before someone runs `/crew:init`.
Do not create `.crew/`, and do not suggest running `/crew:init` just so this
command has something to read.

When it does exist, report the current `dev.provider`, `qa.provider` and
`qa.order` as facts before offering any opinion about them.

## Step 1 — the constraint, stated first

**crew's provider set is closed. `localgpu` cannot be a crew provider.**

`default_config()` in `plugin/crew/hooks/scripts/crew_config.py` hardcodes the
whole set:

```python
"qa":  {"provider": "auto", "order": ["codex", "copilot", "claude"], ...}
"dev": {"provider": "claude", ...}
```

and `/crew:model` validates `dev.provider` against exactly `claude`, `codex`,
`copilot`. Every downstream consumer — `/crew:review`'s reviewer selection, the
same-family interlock that strikes the author's family from QA, `/crew:roster`'s
staffing report — reads those names and nothing else.

Making `localgpu` a first-class provider means editing crew. That is out of scope
for this plugin, and it is out of scope on purpose: the review gate is the one
thing crew exists to hold, and a plugin that reached into another plugin's config
schema to add itself to that gate is doing the exact thing the gate is there to
catch.

## Step 2 — which roles are plausible, and which are not

Judge on one axis: what does being wrong cost, and would anyone notice?

| Role | Offload to a local 7B? | Why |
|---|---|---|
| `explorer` | **Partly — via the MCP tools, not the chat model** | Its job is locating code and returning excerpts. `search_code` does that on the GPU for free. What it must not offload is the judgement about what the excerpts mean |
| `scribe` | Plausible | Mechanical capture. A clumsy note is visibly clumsy and costs a re-read |
| `docs-writer` | Plausible as a first draft only | A human or a frontier model edits it before it lands. Never as the last pass |
| `researcher` | Marginal | A 7B with no browsing is a worse search engine than search. Use it to triage what to read, not to conclude |
| `analyst` | No | Its output feeds decisions nobody re-derives |
| `planner` | No | A plan that is subtly wrong is more expensive than no plan |
| `developer` | No | Code lands. A 7B's failures are fluent and pass a skim |
| `qa-reviewer` | **Never** | See below |
| `security`, `dba`, `infrastructure-architect` | **Never** | Domain gates where the failure mode is silent and the blast radius is production |
| `smoke-author`, `browser-tester` | No | A test that passes for the wrong reason is worse than no test |
| `pm` | No | It owns the gates. A gatekeeper that cannot reason about the gate is decorative |

**`qa-reviewer` is the categorical one.** Review's whole value is that a second,
differently-wrong reader looks at code the first one wrote. A weaker model does not
review — it agrees, fluently, on almost everything, and produces output that is
indistinguishable from a real pass. crew already refuses a same-family reviewer for
this reason; a weaker-family reviewer is the same failure with a better disguise.

Say the honest summary out loud: **the useful offload here is retrieval, not
judgement.** The MCP tools save real context on every crew task without touching a
single gate. That is the win. `chat_model` doing a role's thinking is not.

## Step 3 — the one supported route: a separate proxy session

There is a legitimate way to put crew work on the local model, and it is not a
config edit. `localgpu shell` launches a **separate `claude` session** with
`ANTHROPIC_BASE_URL` pointed at a translating proxy this plugin ships
(`cli/anthropic_proxy.py`), which speaks the **Anthropic Messages API** on the
front and Ollama's `/api/chat` on the back:

```bash
localgpu shell            # new session, ANTHROPIC_BASE_URL -> the local endpoint
localgpu shell --model qwen2.5-coder:14b-instruct-q4_K_M   # this run only; writes nothing
```

The console script lives in `$LOCALGPU_HOME/venv`, the proxy binds a free loopback
port, and `ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_PROFILE` are stripped from the
child so an OAuth profile cannot quietly send that session back to the hosted API.
Anything after the flags is handed to `claude`.

| Property | Consequence |
|---|---|
| A different process, a different session | Nothing in your current session changes model |
| crew's config is untouched | `dev.provider` and `qa.order` still say what they said |
| Everything in that session is the 7B | Including any `/crew:*` command run inside it |

An OpenAI-compatible endpoint will **not** work here, and it is worth knowing
why before someone tries to simplify this away: `ANTHROPIC_BASE_URL` makes the
client POST `/v1/messages` in the Anthropic Messages format, while Ollama's
OpenAI surface is `/v1/chat/completions` with a different body. Pointing one
straight at the other 404s on every request. The proxy is the translation, not
a convenience wrapper. Text, tool calls, tool results, stop sequences and
streaming cross it intact; images, thinking blocks and prompt caching do not,
and it reports that rather than faking it. Token counts are Ollama's own and
are passed through unchanged — they are not Anthropic's tokenizer, so a usage
number read inside that session is not comparable to one from a real session.

That last row is the catch, and it is the reason this is a separate session rather
than a mode. Running `/crew:review` inside the proxy session produces a review by
a 7B that is labelled like any other review. If you use the shell, use it for
exploration and drafting, and do not run gate commands in it. Nothing enforces
that — it is a discipline, and this document is where it is written down.

Report whether the shell is even available on this machine rather than describing
a route the user cannot take. Check it where it is actually installed — the venv —
because nothing puts that directory on `PATH`, so a bare `localgpu` missing from
`PATH` proves nothing either way:

```bash
"$LOCALGPU_HOME/venv/bin/localgpu" --version      # Scripts\localgpu.exe on Windows
```

Three outcomes, three different sentences: it answers (say the version, and give
the full path if a bare `localgpu` does not resolve); it is absent (the bootstrap
never installed the CLI — re-run it, and note that the MCP retrieval half is
unaffected); or it exits saying it cannot find the plugin's `mcp/` directory (a
non-editable install — `pip install -e` with the venv's own Python). `localgpu
shell` also needs `claude` itself on `PATH`, and says so before launching rather
than failing halfway in. `/localgpu:doctor` check 3 runs the same three-way test.

## What this command will not do

Three specific things, each of which would look like a feature and behave like a
regression:

- **It will not write `"provider": "localgpu"` into `.crew/config.json`.** crew
  resolves providers by name against a known set. An unrecognised name does not
  error — it falls through provider selection, and `/crew:review` ends up on the
  `qa-reviewer` fallback while the config file says a reviewer is configured. That
  is a silently degraded review gate, which is precisely the failure crew was built
  to prevent. If a user asks for this, refuse and show them this paragraph.
- **It will not shadow `codex` or `copilot` on `PATH`.** A wrapper named `codex`
  that routes to Ollama makes every crew probe pass, every review return, and every
  `/crew:roster` line read "on PATH". The gate then reports green forever while a
  7B writes the reviews. Do not do this, and do not describe it as an option.
- **It will not add itself to `qa.order`.** Same failure as the first, one level
  down: a name in `order` that resolves to nothing is a rung the selector walks past
  in silence.

The common thread: crew's gates fail *open* against an unknown provider. Anything
that puts an unknown name where crew expects a known one converts a hard failure
into a green light, and green lights are load-bearing here.

## Step 4 — end with one recommendation

Pick the one that fits what you found, and stop:

| If | Say |
|---|---|
| MCP tools are registered and crew is set up | Use `search_code` during crew tasks; leave the config alone |
| MCP tools are not registered | `/localgpu:setup`, then re-run this |
| The user wants a local reviewer | There is not one. Codex or Copilot, per `crew:crew-providers` |
| The user wants to experiment | `localgpu shell`, and not for gate commands |

Do not list all four. A report that ends in a menu made no judgement.
