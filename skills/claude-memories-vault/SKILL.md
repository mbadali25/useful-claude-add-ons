---
name: claude-memories-vault
description: >
  Conventions for the `claude-memories` Obsidian vault at `C:\repos\claude-memories` —
  folder layout, the six required frontmatter fields, the `type`/`status` value sets, the
  templates in `wiki/templates`, how wikilinks resolve on Windows, the write lock, and the
  rule for choosing between this vault and Claude Code auto-memory. Use this skill whenever
  writing, extending, linking or auditing a note in that vault; when a task mentions the
  memory vault, `claude-memories`, `wiki/concepts`, `wiki/daily`, `wiki/sessions`,
  `pending-reflect`, the gardener, `/recall`, `/reflect`, `/hydrate`, `/garden`,
  `/vault-status`, distilling a session, or "write this down so I do not lose it"; and
  before creating any new page there. Do NOT use it for ordinary repo markdown, READMEs, or
  docs that belong in a project. For hosting a vault on a server see `obsidian-vault-server`;
  for canvases in this vault see `claude-memories-canvas`.
---

# The claude-memories vault

Root: **`C:\repos\claude-memories`** — a git repo, synced by Obsidian Sync and
committed by Obsidian Git every 15 minutes. **Another process owns commits here.**
Write notes; do not commit unless you were explicitly asked to.

## Scope — read this first

This skill documents **one specific vault**, not Obsidian in general. Everything below
is a convention of the `claude-memories` vault: its folder names, its frontmatter
contract, its lock script, its slash commands. On a machine without that vault the
conventions are still a workable template, but the paths will not resolve.

| If you want | Use |
|---|---|
| Notes and frontmatter in the `claude-memories` vault | this skill |
| A `.canvas` visual map in the `claude-memories` vault | `claude-memories-canvas` |
| JSON Canvas authoring in *any* Obsidian vault | `obsidian-canvas` |
| Running a vault on a headless server, Sync, the REST/MCP endpoint | `obsidian-vault-server` |

## Two memory stores, different jobs

| | Auto-memory | This vault |
|---|---|---|
| Where | `C:\Users\mbadali\.claude\projects\<slug>\memory\` | `C:\repos\claude-memories` |
| Size | small | 291 concepts, 500+ session pages |
| Loaded | every session, automatically | on demand, via `/recall` |
| Holds | operational state: what is in flight, this box's quirks | distilled concepts, provenance, visual maps |

Write to **auto-memory** when the fact is current operational state for one project —
a port number, a credential location, which branch is live. Write to **the vault**
when the fact is a durable lesson that would save time months from now, in any
project. If you are unsure, ask which one; guessing wrong buries the fact either way.

## Folder layout

```
HOME.md                     Dataview dashboard. Do NOT hand-edit; the queries maintain it.
inbox/pending-reflect.md    capture queue, authoritative check-off
inbox/ready-to-distil.md    triaged subset, IDENTICAL line format on purpose
wiki/index.md               the human entry point - read this to orient
wiki/concepts/              one distilled idea per file (291 files)
wiki/sessions/              provenance: "Session - <topic> <YYYY-MM-DD>.md"
wiki/daily/                 "YYYY-MM-DD.md"
wiki/sources/               source records with provenance fields
wiki/decisions/             "D-00N - <decision>.md", numbered and accepted
wiki/maps/                  .canvas files - use the claude-memories-canvas skill
wiki/templates/             Template - Concept / Daily / Entity / Source / Decision
wiki/bases/                 .base files (Obsidian Bases views)
wiki/meta/                  ledgers and vault bookkeeping
Excalidraw/                 drawings, not canvases
```

## Frontmatter: six fields, always

Every page carries `title`, `type`, `status`, `created`, `updated`, `tags`. A page
missing any of them is a `missing_frontmatter` lint finding. `title` is quoted;
dates are bare `YYYY-MM-DD`; `tags` is a block list.

```yaml
---
type: concept
title: "A dead if-guard silenced nineteen deploy workflows for over a year"
created: 2026-08-18
updated: 2026-08-19
status: established
tags:
  - github-actions
  - gotcha
project: "anew"
sources:
  - "[[Session - THD slowness incident and deploy pipeline repair 2026-08-18]]"
---
```

**`type`** — exactly one of eight values, chosen by where the page lives:
`concept`, `source`, `entity`, `daily`, `project-index`, `meta`, plus `session` (every
page in `wiki/sessions/`) and `decision` (every page in `wiki/decisions/`). All eight
are legal to write. Do not invent a ninth; the Dataview queries in `HOME.md` filter on
these exactly, and an unknown value drops the page out of every dashboard silently.

**`status`** — `seed` (a stub), `developing` (being worked out), `established`
(trustworthy). New pages start at `seed` or `developing`. Promote deliberately, not
by default: `/vault-status` reports `developing` pages untouched for 30 days as stale,
and that report is only useful if the values mean something.

**`sources:`** — a list of real wikilinks to the session or source pages that support
the claim. An empty `sources:` list makes the concept **unsupported**, and `/recall`
says so out loud. Populating it is not optional bookkeeping; it is what separates a
recorded fact from a remembered impression.

Type-specific extras are in the templates: `decision_id` / `decision_status` /
`date_decided` on decisions, `session_id` / `store` on sessions, and the provenance
block (`authority`, `review_status`, `sha256`, `url`) on sources. Source templates
default `authority: unknown` and `review_status: unreviewed` **on purpose** — promote
them only when the evidence actually supports it, and never invent a locator, quote,
date or confidence.

## Templates

`wiki/templates/` holds `Template - Concept.md`, `- Daily.md`, `- Entity.md`,
`- Source.md` and `- Decision.md`. Read the one you need and follow it; a page built
from a template passes lint immediately. Obsidian's template folder setting points at
`wiki/templates`, so `{{title}}` and `{{date:YYYY-MM-DD}}` placeholders are expanded
by Obsidian — when you write a file directly, substitute them yourself.

## Filenames are the search index

A concept's filename is the claim, phrased as a readable sentence:

```
A dead if-guard silenced nineteen deploy workflows for over a year.md
AWS OpenSearch balances shards by count not size.md
Transcript emptiness is measured in message text, not record count or file size.md
```

This is why `/recall` finds things: a filename glob is usually a direct hit. A vague
filename ("Notes on deploys.md") is effectively unfindable. Name the page after what
it asserts, not the topic it is about.

Project index pages are `Project - <name>.md`, in `wiki/concepts/`, with
`type: project-index`.

## Wikilinks resolve by FILENAME

`[[Some page]]` resolves against the file called `Some page.md`, not against a
`title:` field. Two consequences on Windows:

1. **A `:` cannot appear in a filename**, so a title containing one cannot be linked
   verbatim. This vault substitutes a hyphen: the concept about the `+00:00` timezone
   trap is the file
   `exec-insights timezone traps - +00-00 rejection and UTC-anchored day windows.md`,
   and the link must be `[[exec-insights timezone traps - +00-00 rejection and UTC-anchored day windows]]`
   even though the prose says `+00:00`. **Match the link to the file, not the prose.**
2. **Count references with exact boundaries.** A prefix match once put
   `Project - aws` at 206 references because it also counted every
   `Project - aws-managed-services-*` link; an exact-boundary recount disqualified 2
   of 12 promotion candidates. `[[X]]` and `[[X|` and `[[X#` are references to `X`;
   `[[X-something]]` is not.

Canvas links include the extension: `[[exec-insights.canvas]]`.

## Writing into the vault

1. **Search before writing.** Extending an existing concept beats creating a
   near-duplicate every time; duplicates dilute search for everyone afterwards.
2. **Take the lock.** The nightly gardener and other agents write this same tree, and
   they have collided before — one agent committed another's staged-but-uncommitted
   edits inside its own 68-file commit:
   ```
   pwsh -NoProfile -File C:\repos\claude-memories\.claude\vault-lock.ps1 -Acquire -Owner <who>
   pwsh -NoProfile -File C:\repos\claude-memories\.claude\vault-lock.ps1 -Release
   ```
   Non-zero from `-Acquire` means someone else holds it. Stop; do not write anyway.
   `-Owner` is a short string naming who took it, so the next agent can see who to
   chase. **Always `-Release` when you finish**, including on the path where the write
   failed — an unreleased lock wedges the gardener and every other agent. `-Status`
   reports the current holder if you need to check before deciding.

   **Exception — the lock may already be held *for* you.** If `VAULT_LOCK_HELD=1` is set
   in your environment, a wrapper took the lock before spawning you and holds it for the
   whole run; `VAULT_LOCK_PID` names the holder. Write normally, and **do not acquire or
   release** — the wrapper's `finally` owns the release.

   This is not hypothetical. `gardener.ps1` acquires with `-KeepOpen` and then invokes
   `claude -p`; without this exception the agent inside follows the rule above, is refused
   **by its own parent**, reads that as contention, and stops. The run logs a lock
   acquired and a model invoked, and distils nothing — silent success while doing nothing,
   nightly.

   If the variable is somehow absent, the distinguisher is the **process tree, never the
   lock file** — `pid`, `owner`, `mode` and `ttl` look identical whether the holder is
   your own parent or a stranger. Walk `ParentProcessId` from `$PID`; if the lock's pid is
   an ancestor, the serialising has already been done on your behalf. **Never `-Force`
   past a lock to resolve this** — on a genuinely foreign lock that is exactly the
   collision the lock exists to prevent, and the two cases are indistinguishable without
   the check.
3. **One idea per page.** Set `updated` when you touch a page. Populate `sources:`.
4. **Facts in notes, shape on canvases.** Anything load-bearing must exist as text in
   a note even if it also appears on a canvas — a canvas-only fact is invisible to
   search. See the `claude-memories-canvas` skill.
5. **Never hand-edit the queue.** `inbox/pending-reflect.md` has exactly one writer:
   ```
   C:\Python314\python.exe C:\Users\mbadali\.claude\hooks\vault-queue.py checkoff --session <id> --result "<what came out>"
   ```
   It holds a lock the capture hooks respect. Hand-editing races them.
6. **Never create a file named `nul`.** Windows reserves the name and git aborts every
   `git add -A` with "short read while indexing nul" — it broke every commit in this
   repo for days. Redirect to `$null` in PowerShell, never to `nul`.

## Do not touch

`HOME.md` (Dataview maintains it) and `.obsidian/` (per-machine plugin state).

Auto-memory under `C:\Users\mbadali\.claude\projects\<slug>\memory\` is written
**through the harness's memory tooling for the current project only** — that is the
route the table above means by "write to auto-memory". Do not hand-edit those files,
and do not touch another project's `<slug>` directory or anything else under
`C:\Users\mbadali\.claude\projects\`; the harness owns that tree.

## The loop this vault sits inside

`work → capture → distil → recall`. Capture is the `SessionEnd` / `PreCompact` hook
`vault-capture.py`, which queues one line per session. Distil is the nightly
**Claude Vault Gardener** task running `.claude\gardener.ps1`, or `/garden` attended.
Recall is `/hydrate`, `/recall`, `/reflect`, `/pickup`, `/vault-status`. Full design:
`wiki/concepts/Vault automation - the capture and gardener loop.md`, and the shipped
implementation of that loop is this repo's [`vault-automation/`](../../vault-automation).
