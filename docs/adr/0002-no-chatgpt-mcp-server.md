# 2. No MCP server for ChatGPT; `codex:codex-rescue` as-is

**Status:** accepted, 2026-09-14
**Decided by:** the user, after scoping

## Context

The ask was an MCP server for ChatGPT — or for an AI browser — that Claude Code
would invoke automatically. What would have been built here is a new plugin
directory plus a marketplace entry, a catalog row, a `plugin/PLUGINS.md` row and
both install scripts. None of that was written. Nothing is registered and no
version was bumped; this file is the whole of the work.

Scoping killed the premise rather than the implementation, so the reasoning is
worth more than the absent code.

**The mental model was inverted. ChatGPT is an MCP *client*, not a server.** Its
Developer Mode connectors *consume* remote MCP servers over SSE or streamable
HTTP; a connector needs a publicly reachable HTTPS endpoint, is selected per
conversation, and is approved per invocation. Sources:
<https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt>
and <https://developers.openai.com/api/docs/guides/tools-connectors-mcp>. So "an
MCP server for ChatGPT" is a thing Claude Code would *expose to* ChatGPT, and it
could not auto-invoke anything on the Claude Code side — which was the entire
point of the request.

**Driving `chatgpt.com`'s web UI is excluded on terms, not only on
brittleness.** OpenAI's terms of use bar automatically or programmatically
extracting data or output. Source:
<https://openai.com/policies/row-terms-of-use/>. **That clause was read via
search extraction, because `openai.com` returned 403 to the fetcher** — it is
quoted second-hand here. Re-check it against the page itself before relying on
it; do not treat this note as the primary source.

**The capability already exists with no server.** `codex:codex-rescue` signs in
with a ChatGPT paid plan rather than a metered API key, so the subscription the
request was trying to reach is already reachable. Browser driving exists too:
`claude mcp list` on this machine reports `playwright` and `chrome-devtools`
both `✔ Connected`. `claude-in-chrome` does **not** appear in that list — its
tools arrive as `mcp__claude-in-chrome__*` through the Chrome extension, so this
probe says nothing about whether it is available; two connected servers are
enough to carry the claim, and the third is simply not established here.

## Decision

Build nothing. Use `codex:codex-rescue` as it ships.

## Why not build it

**A read-only consult wrapper** would be small, and it was the closest call. It
loses because it does not buy the thing that was actually wanted: wrapping
Codex in an MCP server does not make invocation deterministic, so the cost is
real and the gap it closes is not the gap.

**A `UserPromptSubmit` hook** *would* make invocation deterministic, and that is
exactly why it was considered. It loses on this repo's own standing rules: a
plugin registering a hook defaults to OFF in the menu, and one that can block
needs a committed, sabotage-tested regression suite. Paying that for
probabilistic-versus-deterministic subagent pickup is out of proportion to the
gap.

**An MCP server wrapping the OpenAI Responses API** would work technically and
needs no browser. It loses twice: billing is metered per token and is separate
from the ChatGPT plan that `codex-rescue` already uses, and it duplicates
`codex-rescue` rather than adding anything.

## Consequences

- **Invocation is probabilistic, knowingly.** Claude picks `codex-rescue` up
  from its description; nothing guarantees it fires. That was accepted as the
  price of not shipping a hook.
- **`codex-rescue` defaults to `--write`, knowingly.** It is an implementer, not
  a read-only consultant — "Default to a write-capable Codex run by adding
  `--write` unless the user explicitly asks for read-only behavior or only wants
  review, diagnosis, or research without edits" at
  `~/.claude/plugins/cache/openai-codex/codex/1.0.6/agents/codex-rescue.md:34`.
  That citation is **machine-local and version-pinned**: it is outside this
  repo, so `git diff <anchor>..HEAD` cannot re-check it and it moves when the
  plugin updates. Contrast `plugin/crew/agents/kimi-consult.md:29` and `:32`,
  which do the opposite — `--mode plan` by default, write only on an explicit
  ask — and are repo-relative, so they can be re-checked. Asking `codex-rescue`
  to consult without editing is a thing the caller must say.
- **Unverified:** whether this machine's Codex CLI is authenticated was never
  checked. It is an operational precondition, not part of this decision; probe
  it with `/codex:setup`.
- **What would reopen this.** Any one of: the goal inverts to *exposing* Claude
  Code's tools to ChatGPT and a publicly reachable HTTPS endpoint exists to
  serve them; this repo's hook policy changes, or a measured rate of missed
  `codex-rescue` pickups makes the sabotage-tested suite worth its cost; OpenAI
  bills Responses API usage under the ChatGPT plan rather than separately; or
  `codex-rescue`'s `--write` default causes an unwanted edit here, which would
  revive the read-only wrapper as a fix for an observed incident rather than a
  worry.
