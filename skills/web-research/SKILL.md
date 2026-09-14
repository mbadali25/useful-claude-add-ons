---
name: web-research
description: >
  Answer questions from the live web through the Perplexity MCP server
  (`mcp__perplexity__perplexity_search`, `perplexity_ask`, `perplexity_research`,
  `perplexity_reason`) - routing each question to the right one of the four, with
  recency filters and domain restriction. Use this skill whenever the user wants
  something looked up rather than recalled: "look this up", "what's the latest on
  X", "research X", "is this still true", "has this changed", "find current
  pricing for X", "any CVE or advisory for X", "compare these vendors", "who
  actually offers X", "find me sources on X", "search the web for X", or a plain
  "use perplexity". Also use it whenever answering would otherwise rest on
  training data for something that changes - prices, versions, release dates,
  incidents, security advisories, company or product status, news, regulations,
  or anything the user says might be out of date. Do NOT use this for library,
  framework, SDK or API reference and code examples - those go to Context7
  (`resolve-library-id` then `query-docs`), which returns versioned docs rather
  than web pages.
---

# Web research via Perplexity

Four read-only MCP tools on the `perplexity` server, backed by the Perplexity
Agent API. All four hit the live web and return citations. Nothing here mutates
anything, and this skill registers nothing itself: the server is registered once
per machine — by hand, or by this repo's installers — and its API key lives in
that registration. **Never copy that key into a file, an example, a `.mcp.json`,
or a report — reference the existing registration instead.**

## Trigger honesty — read this once

This skill fires because its `description` matched what the user said. That match
is **probabilistic, not enforced**: there is no hook behind it, and a request that
plainly needs live data can still land without this skill loading. That is a
property of description-based invocation, not a defect to work around here — this
repo defaults hooks to OFF and requires a sabotage-tested regression suite before
one ships, which a routing skill does not warrant.

A user who wants it deterministic owns the lever: a line in their own
`~/.claude/CLAUDE.md` or the project's, such as *"Before answering anything about
current prices, versions, advisories or news, invoke the `web-research` skill."*
Offer that if they say the skill "doesn't fire".

## Pick the tool

| Tool | Use it for | Cost |
|---|---|---|
| `perplexity_search` | Finding URLs, facts, recent news. The default when the user wants *sources* or you need to know what exists. | Fast |
| `perplexity_ask` | One question, one cited answer. The default when the user wants *the answer*, not a reading list. | Fast |
| `perplexity_research` | Deep multi-source investigation — vendor comparisons, market or landscape questions, "everything known about X". | **Slow — minutes.** Say so before starting. **Accepts no recency or domain filter** — see below. |
| `perplexity_reason` | Analysis that needs step-by-step logic over what was found — trade-offs, "which of these fits our constraints", chains of inference. | Medium |

Route on the shape of the request, not its wording:

- "What's the latest on X" / "find me sources" → `perplexity_search`
- "Is this still true" / "what does X cost now" / "which version is current" → `perplexity_ask`
- "Compare the vendors" / "research X properly" / "write me a landscape" → `perplexity_research`
- "Given all that, should we…" / "work out whether X breaks Y" → `perplexity_reason`

Start narrow. A `perplexity_ask` that comes back thin is cheap; a
`perplexity_research` that was not needed costs the user minutes of waiting.
Escalate to `research` only after a cheap call underdelivers, or when the user
asked for depth outright.

## Filters — and the one tool that ignores them

**`perplexity_research` takes no filters at all.** Its schema is `messages` and
nothing else, and its handler passes no options through, so a recency or domain
argument sent to it is dropped on the floor — the call still succeeds and still
returns an answer, unfiltered, with no warning. Verified by reading
`dist/server.js` in `@perplexity-ai/mcp-server` **1.2.1**. Do not send filters to
it and do not reach for it when filtering is the point; filter with `ask` or
`search` instead, or accept an unfiltered sweep.

What each tool actually honours, at 1.2.1:

| Parameter | `search` | `ask` | `reason` | `research` |
|---|---|---|---|---|
| `search_recency_filter` (`hour`/`day`/`week`/`month`/`year`) | yes | yes | yes | **no** |
| `search_domain_filter` (array; `-` prefix excludes) | yes | yes | yes | **no** |
| `search_context_size` (`low`/`medium`/`high`) | **no** | yes | yes | **no** |
| `max_results` (1-20, default 10), `max_tokens_per_page` (256-2048), `country` (ISO 3166-1 alpha-2) | yes | no | no | no |

`search` takes a `query` string; `ask`, `reason` and `research` take `messages`.

How to use them:

- **Recency** — pass it whenever the question is about *now*: pricing, versions,
  advisories, outages, news, "still". Without it the top results are often years
  old and read as current. Prefer the tightest window that still returns results,
  and widen only if the first call comes back empty.
- **Domain restriction** — restrict when the authoritative source is known: the
  vendor's own domain for pricing and release notes, `nvd.nist.gov` or `cve.org`
  for CVEs, a regulator's domain for rules. `['-reddit.com']` excludes instead.
  Restricting to the vendor is what separates "what a blog said in 2023" from
  "what the vendor says today".
- **Search context size** — raise it for broad or ambiguous questions; leave it
  alone for a single factual lookup.

That table is a fact about **1.2.1**, which is a version the user can upgrade
without telling you. Read each tool's own parameter schema before the first call
in a session; where the live schema and this table disagree, the schema wins and
this file is stale.

## Boundaries — what does NOT come here

| The question is about | Go to | Why |
|---|---|---|
| A library, framework, SDK, API, CLI tool **or cloud service** — syntax, config, setup, version migration, code examples | **Context7**, where it is available: `resolve-library-id`, then `query-docs` | Versioned docs beat web pages, and Context7 indexes cloud-service docs as well as libraries. Applies even to well-known names. |
| Code in this repo, business logic, a failing test | Neither — read the code | Web search on your own codebase returns nothing useful. |
| A specific URL the user handed you | `WebFetch`, or `ctx_fetch_and_index` where context-mode is available | You already know the page; you do not need a search engine to find it. |

**The line, stated once so it does not need looking up:** Context7 owns
*documentation* — how a thing is used. This skill owns *currency* — what is true
about a thing right now. So a cloud service's API reference, SDK syntax, config
schema and setup steps go to Context7, **including** its documented pricing tiers
and documented limits. Its **live** status, an outage, a breach or advisory, a
price change someone is reporting but the docs do not yet show, or "has this been
deprecated" go here. If Context7 is not installed on the machine, this skill is
the fallback for the documentation questions too — say in the answer that the
source was the open web rather than versioned docs.

When a request genuinely spans both — "what changed in the last release of this
SDK and is anyone reporting problems with it" — take the API surface from
Context7 and the field reports from Perplexity, and say which came from which.

## Reporting what you found

- **Carry the citations through.** The tools return them; an answer that drops
  them is indistinguishable from one you made up.
- **Date the claim.** "As of the sources returned today" — a price or version
  with no date attached becomes wrong silently.
- **Say when the search disagreed with itself.** Two sources giving different
  numbers is a finding, not a problem to smooth over by picking one.
- **Say when you found nothing.** An empty result is an answer. Do not fall back
  to training data and present it in the same voice as a cited result.

## Operator: is the server actually connected?

The `perplexity` server reaches a machine one of two ways, and this skill works
the same either way:

- **By hand, globally** — `~/.claude.json`, server name `perplexity`, run via
  `npx @perplexity-ai/mcp-server`. This is how it got onto the machine this skill
  was written on.
- **By this repo's installers** — `scripts/install-prerequisites.sh` /
  `.ps1`, menu row 25 (`--select perplexity-mcp`). The key comes from
  `--perplexity-api-key` / `-PerplexityApiKey`, or from `PERPLEXITY_API_KEY` in
  the environment; with neither, the row prints where to create one and skips
  rather than registering a server that can never authenticate.

Either way the key ends up on disk in the MCP registration, which is the one
copy of it to reference — never a second one in a file, an example, a
`.mcp.json`, or a report.

**To check, run `claude mcp list` in a terminal.** It prints
`Checking MCP server health…` and then one line per server; the one you want
reads:

```
perplexity: npx -y @perplexity-ai/mcp-server - ✔ Connected
```

That is a real health check, not a config dump, and it prints the command and
args only — no key. Anything other than `✔ Connected` on that line, or no
`perplexity` line at all, means not connected. The in-session equivalent is
`/mcp`, which lists the servers and their status. Either way the definitive test
is the same: if a `mcp__perplexity__*` tool call returns a result, it is
connected.

**If it is not connected:**

1. **Restart the session.** MCP servers are started at session start; a server
   added or edited mid-session is not live until the next one.
2. **Do not try to probe the package by running it.** `npx -y
   @perplexity-ai/mcp-server --help` is **not** a connectivity test and will
   mislead you: the entrypoint parses no arguments, so with the key set it opens
   an MCP stdio server and sits waiting on stdin, and without the key it exits 1
   with `Error: PERPLEXITY_API_KEY environment variable is required` — which
   reads like "the package is broken" when the package is fine. `claude mcp list`
   is the probe; use it.
3. **Check the API key is present in the existing global registration** — it is
   the `PERPLEXITY_API_KEY` environment variable on the `perplexity` server
   entry. Check that the **name** is there; never print, echo, copy or read the
   value. Do not read `~/.claude.json` into the session to look. If it is
   missing or rejected, the user re-adds it themselves with `claude mcp` or in
   their own config — that is a user action, not one to do for them.
4. **A 401/403 from the tool** means the key is bad or out of credit; a timeout
   on `perplexity_research` alone usually means the call is simply still
   running — it can take minutes.

**Fallback when it stays down:** use `WebSearch` and `WebFetch`, and **say in the
answer that Perplexity was unavailable and the result is unsourced by it**. The
fallback is weaker — no recency filter, no domain restriction, no citation
structure — so a silent downgrade hands the user a worse answer that looks the
same.
