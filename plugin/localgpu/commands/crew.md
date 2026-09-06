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

**`localgpu` is not a provider crew dispatches a role to. Not on the dev side,
not on the QA side.**

The provider set in `plugin/crew/hooks/scripts/crew_config.py` is the same
three names on both sides:

```python
DEV_PROVIDERS = ("claude", "codex", "copilot")
QA_PROVIDERS  = ("claude", "codex", "copilot")
```

`localgpu` was briefly admitted to `DEV_PROVIDERS` alone, on the reasoning
that a local 7B is legitimate for work whose failure is *visible* — an
explorer that returns the wrong file, a scribe note that reads badly, a docs
draft a human edits. That reasoning is still correct, and the admission was
still wrong: `dev.provider` backs the `developer` role, and step 2's own table
below has always said `developer` is `No — code lands. A 7B's failures are
fluent and pass a skim.` A provider slot that contradicts the role table two
rows below it is not a narrower gate, it is the same defect approached from
the other side. It was reverted.

**Where a local model actually earns its keep is one level down: role
tooling, not provider selection.** `explorer`, `scribe` and `docs-writer`
already list `mcp__localgpu__search_code` among their tools, and
`/crew:onboard` and `/crew:diagram` inherit the same capability for free —
both locate code by spawning `crew:explorer`, and explorer's tool list is
what carries it. No separate wiring, no config flag, no provider name. See
step 2.

**Why an invalid name is refused rather than ignored, on both the write path
and the read path.** crew's gates fail *open* against a provider name nothing
resolves: an unrecognised entry in `qa.order` is not an error at review time,
it is a rung the selector walks past in silence, leaving `/crew:review` on the
fallback while the config file goes on claiming a reviewer is configured. So
the name is rejected at the write boundary (`crew_config.validate_providers`,
reached from `/crew:model` and `/crew:config`'s global write) — but
hand-editing `.crew/config.json` was always the way past that boundary, so the
read path refuses it too, in two places: `crew_state.resolve_role` bars a `qa`
provider outside `QA_PROVIDERS` outright, before family is even asked about —
an unrecognised name is not merely unproven-independent, it is not a reviewer
at all — and `crew_config.order_candidates` refuses the same name in
`qa.order` before PATH or family are even consulted. `resolve_config` still
promises never to raise on a malformed file, and `provider_problems` reports
what a hand-edited config got wrong in the same words `validate_providers`
would have raised, so a reader of `/crew:model`'s report sees it even when
nothing wrote it through the guarded path.

**Why QA specifically refuses everything outside the three names.** Not
because a 7B reads code badly. Because review's whole value is a second,
*differently*-wrong reader, and a weaker model does not review — it agrees,
fluently, and produces output indistinguishable from a real pass. crew already
refuses a reviewer from the author's own family for exactly this reason; a
weaker-family reviewer is the same failure wearing a better disguise.

**PATH note.** `localgpu` is deliberately *not* on PATH — the bootstrap
installs the console script into `$LOCALGPU_HOME/venv` so the venv's Python is
never shadowed. `crew_config.localgpu_which()` therefore checks PATH first and
then the install root; a bare `which("localgpu")` answers None on a correctly
installed machine and would mark it missing exactly where it works. This is
still used to report whether the CLI itself is present (for the MCP tools and
the shell route below) — it has nothing to do with provider validity, which
is closed regardless of what is installed.

## Step 2 — which roles are plausible, and which are not

Judge on one axis: what does being wrong cost, and would anyone notice?

| Role | Offload to a local 7B? | Why |
|---|---|---|
| `explorer` | **Partly — via the MCP tools, not the chat model** | Its job is locating code and returning excerpts. `search_code` does that on the GPU for free. What it must not offload is the judgement about what the excerpts mean |
| `/crew:onboard` (codemap) | **Partly, same terms as `explorer`** | Locates code the same way, through the same role. `localgpu ask` may produce a first draft of a codemap note; a human or frontier model edits it against the code before it lands, and the edited version is what lands — never the last pass |
| `/crew:diagram` | **Partly, same terms as `explorer`** | Same locate-then-judge split. A first-draft diagram shape from `localgpu ask` is fine; the shape is checked against the code before it is written, never taken as-is |
| graph building (`graphify`) | **No tie-in at all** | `graphify` is a CLI with no model in it. There is nothing at that layer for a local model to plug into — say so rather than inventing one |
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

**`qa-reviewer` is the categorical never, with no exception for a first draft.**
Review's whole value is that a second, differently-wrong reader looks at code
the first one wrote. A weaker model does not review — it agrees, fluently, on
almost everything, and produces output that is indistinguishable from a real
pass. crew already refuses a same-family reviewer for this reason; a
weaker-family reviewer is the same failure with a better disguise. Unlike a
codemap note or a diagram, there is no "edit it before it lands" step that
rescues a review: the whole point of a review is to be the check nobody
re-derives, and a first draft nobody re-derives is exactly the failure this
gate exists to prevent.

The boundary across every row above is the same one: **mechanical capture and
locating code, yes; any judgement that gets committed unreviewed, no.**

Say the honest summary out loud: **the useful offload here is retrieval and
first drafts, not judgement.** The MCP tools save real context on every crew
task without touching a single gate, and a draft note or diagram shape saves
a blank page without touching what actually lands. Neither is a role a
config file dispatches to, and neither is review.

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

- **It will not write `"provider": "localgpu"` into `.crew/config.json` —
  neither side.** It would raise on the `qa` side (`validate_providers`) and,
  since the revert, on the `dev` side too — there is no provider slot this is
  legal in any more. Even where it were legal, this command would not be the
  one to write it: changing which model backs a role is `/crew:model`'s job,
  and a report command that edits config is how a "report only" promise stops
  meaning anything.
- **It will not shadow `codex` or `copilot` on `PATH`.** A wrapper named `codex`
  that routes to Ollama makes every crew probe pass, every review return, and every
  `/crew:roster` line read "on PATH". The gate then reports green forever while a
  7B writes the reviews. Do not do this, and do not describe it as an option.
- **It will not add `localgpu` to `qa.order` or `dev.provider`.**
  `validate_providers` refuses both at the write boundary, and `resolve_role` /
  `order_candidates` refuse the QA side again on read, in case a config ever
  gets there without going through the write path. Do not go looking for a way
  around either guard — the guard is the feature.

The common thread: crew's gates fail *open* against a provider name nothing
resolves. `localgpu` is not a name the provider table resolves at all, on
either side, and that is deliberate — the work it is genuinely good at lives
one layer down, in role tooling (step 2), where a wrong answer is a location a
human re-checks or a draft a human edits, never a diff or a review that lands
unreviewed.

## Step 4 — end with one recommendation

Pick the one that fits what you found, and stop:

| If | Say |
|---|---|
| MCP tools are registered and crew is set up | Use `search_code` during crew tasks, onboard and diagram passes included; leave the config alone |
| MCP tools are not registered | `/localgpu:setup`, then re-run this |
| The user wants a local reviewer | There is not one, in any provider slot, and `crew_config` refuses the config that would claim otherwise on both write and read. Codex or Copilot, per `crew:crew-providers` |
| The user wants a local first draft of a codemap note or a diagram | Fine, on the same terms as `docs-writer`: `localgpu ask` drafts, a human or frontier model edits it against the code, and the edited version is what lands |
| The user wants to experiment | `localgpu shell`, and not for gate commands |

Do not list all five. A report that ends in a menu made no judgement.
