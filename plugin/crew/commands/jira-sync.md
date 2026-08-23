---
description: Sync a ticket between Jira (via MCP) and the local cache
argument-hint: <ISSUE-KEY> [--push]
allowed-tools: Read, Write, Edit, Bash, ToolSearch
---

Sync $ARGUMENTS.

## Preconditions

1. `.crew/config.json` -> `tracker` must be `"jira"`.
2. The Atlassian MCP server must be connected. Check your available tools for
   `mcp__atlassian__*`. If tool search is active you may need to search for them
   rather than seeing them listed.

If either is missing, say exactly which one and stop. Do not fall back to file
tickets — a silent fallback splits the source of truth and you will not notice
until two people have divergent ticket state.

## Discover tools, do not assume names

Atlassian's Rovo MCP server has changed tool names between versions. Find the
read, edit, comment, and transition tools for Jira issues before calling them.
Cloud instances also require a cloudId — fetch the accessible resources once and
cache it in `.crew/config.json` under `jira.cloudId` so you never look it up twice.

## Pull (default)

Fetch issue $1. Write `.work/cache/<KEY>.md` in the same shape a files-mode
ticket uses.

**Store only these fields:**
key, title, status, description, acceptance criteria, labels, and the last 3
comments.

**Discard everything else** — reporter, watchers, sprint and board metadata,
custom fields, attachments, changelog, full comment history, rendered ADF.

This is the whole game with Jira. A single Jira issue payload can run several
thousand tokens and roughly forty of them affect what you build. `/crew:work`
reads the cache, never the API, so that payload gets paid once instead of on
every pickup, retry, and context reset.

When you query for multiple issues, use JQL with an explicit field list and a
`maxResults` cap. Never fetch a board or a whole sprint to find one ticket.

## Push (`--push`)

Transition the status, and append exactly ONE comment:

> files touched, smoke result, reviewer used (Codex or Claude), BLOCK count.
> Two sentences.

Never paste diffs, review output, or agent reasoning into Jira. That is what the
repo and the PR are for, and it makes the issue more expensive to read back later.

## Sync at boundaries only

Pickup and completion. Never mid-task. If a single ticket causes three Jira calls,
the cache is wrong — fix the cache rather than adding calls.

## Auth note

Anthropic and Atlassian both moved off the old SSE endpoint; `/v1/sse` was retired
mid-2026. Use the `/v1/mcp` HTTP endpoint. If you hit repeated mid-session
re-authentication with OAuth, switch to API token auth, which does not drop the
way the OAuth flow does.
