---
name: claude-memories-vault
description: >
  Conventions for the `claude-memories` Obsidian vault at `C:\repos\claude-memories`
  (Windows) / `/repos/claude-memories` (Linux) —
  folder layout, the six required frontmatter fields, the `type`/`status` value sets, the
  templates in `wiki/templates`, how wikilinks resolve on each host, the write lock, and the
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

Root: **`C:\repos\claude-memories`** (Windows) / **`/repos/claude-memories`** (Linux) — a git repo, synced by Obsidian Sync and
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
| Where | `~/.claude/projects/<slug>/memory/` | `C:\repos\claude-memories` (Windows) / `/repos/claude-memories` (Linux) |
| Size | small | 291 concepts, 500+ session pages |
| Loaded | every session, automatically | on demand, via `/recall` |
| Holds | operational state: what is in flight, this box's quirks | distilled concepts, provenance, visual maps |

`~/.claude` means `%USERPROFILE%\.claude` on Windows. Write it that way rather than
spelling a username: the vault root maps `C:\repos\X` <-> `/repos/X` between the two
hosts, but **the user profile does not** — the accounts are unrelated and need not
share a name, so a hardcoded `C:\Users\<someone>\...` is wrong on one host and
silently wrong on the other if the account was ever renamed.

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
  - "[[Session - ACME slowness incident and deploy pipeline repair 2026-08-18]]"
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
`title:` field. Three consequences — and the third is the one that differs
between the two hosts, so it is invisible to anyone testing on only one:

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
3. **Match the filename's CASE exactly. This is the one that breaks Linux.** NTFS
   is case-insensitive and ext4 is not, so `[[Project - Scripts]]` finds
   `Project - scripts.md` on Windows and finds **nothing** on Linux. The link is
   not reported as broken on the host where it works, which is why this survives:
   it is correct on the machine the author was sitting at.

   Measured on the live vault, 2026-09-22, by a read-only walk (3043 files,
   14138 wikilinks): **10 link occurrences resolve case-insensitively only**, all
   of them the single pair `[[Project - Scripts]]` -> `Project - scripts.md`. Not
   a hypothetical, and not yet fixed — fixing it means editing the vault, which
   this skill's reader may not be authorised to do.

   **This makes consequence 2's counts host-dependent, which is the expensive
   part.** Those 10 references count toward `Project - scripts` on Windows and
   toward nothing on Linux, so the same exact-boundary recount that disqualified
   2 of 12 promotion candidates returns a *different answer on each host*. Before
   promoting anything on a reference count, say which host you counted on — a
   count without its host is the same unverifiable claim as a measurement without
   its ref.

   **Unverified:** whether Obsidian's own resolver falls back to a
   case-insensitive match on Linux, which would hide these 10 inside the app
   while `grep`, `/recall` and every script still miss them. Nobody has tested
   it; do not assume either answer.

Canvas links include the extension: `[[exec-insights.canvas]]`.

## Writing into the vault

1. **Search before writing.** Extending an existing concept beats creating a
   near-duplicate every time; duplicates dilute search for everyone afterwards.
2. **Take the lock — after establishing that this host has one.** The nightly gardener
   and other agents write this same tree, and they have collided before — one agent
   committed another's staged-but-uncommitted edits inside its own 68-file commit.

   **The lock is a host-local artifact and it does not travel.** It lives at
   `<vault>\.claude\vault-lock.ps1`, and `.claude/` is outside the Obsidian Sync payload
   *and* absent from the vault's git history, so it reaches a machine only when that
   machine installs it. The vault's own `CLAUDE.md` states both halves: `.claude/` is
   "host-local only: gardener logs, lock, config guard, one-shot miners", and "the lock
   file cannot serialize across machines. It serializes agents on this box only." Two
   hosts writing `wiki/` at once is therefore **not** a case this lock covers and never
   was — it serializes the agents on one box, which is the case that produced the 68-file
   commit.

   So run `-Status` first and read its result as the first step of the write, not a
   formality. **Resolve the interpreter and the vault root; never name either bare.**
   A bare `pwsh` is not on Git Bash's PATH on Windows, and its "command not found"
   is indistinguishable, to the agent reading the exit code, from a lock that
   refused you — which is the failure this whole step exists to prevent:
   ```bash
   # Interpreter. Order is load-bearing and is ported from .crew/verify.json:178:
   # under WSL the reachable binary is the Windows one and is named pwsh.exe, so
   # the .exe suffix must be tried as well as omitted, at both known locations.
   PWSH=""
   for c in pwsh pwsh.exe \
            "/c/Program Files/PowerShell/7/pwsh" "/c/Program Files/PowerShell/7/pwsh.exe" \
            "/mnt/c/Program Files/PowerShell/7/pwsh.exe" "/mnt/c/Program Files/PowerShell/7/pwsh"; do
     if command -v "$c" >/dev/null 2>&1 || [ -x "$c" ]; then PWSH="$c"; break; fi
   done

   # Vault root. Same tree, two machines.
   VAULT="/repos/claude-memories"                        # Linux / macOS
   [ -d "$VAULT" ] || VAULT="C:/repos/claude-memories"   # Windows
   LOCK="$VAULT/.claude/vault-lock.ps1"

   if [ -z "$PWSH" ] || [ ! -f "$LOCK" ]; then
     # THIRD OUTCOME, not a failure: there is no lock on this host to hold or be
     # refused by. Take the "No lock on this host" branch below.
     # Never read this as contention. An absent lock is not a held lock.
     echo "NO VAULT LOCK: pwsh=${PWSH:-unresolved} lock=$LOCK" >&2
   else
     "$PWSH" -NoProfile -File "$LOCK" -Status
     "$PWSH" -NoProfile -File "$LOCK" -Acquire -Owner <who>
     "$PWSH" -NoProfile -File "$LOCK" -Release
   fi
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

   **No lock on this host — a named outcome, not a dead end.** The lock is PowerShell and
   it is the only lock there is: no POSIX equivalent exists in the vault or anywhere in
   this marketplace. On a Linux or macOS host — where the vault root is
   `/repos/claude-memories`, not `C:\repos\claude-memories`, and `.claude/` is simply
   absent — there is nothing to acquire, and **both reflexes are wrong**. *Stopping*
   leaves the vault unwritable on that host, over a hazard the lock would not have covered
   between hosts anyway. *Writing as though you had taken it* reinstates exactly the
   collision the lock exists to prevent. Do this instead:

   1. **Say so in your first reply** — "this host has no vault lock; writes here are
      unserialized". A silent degradation is how the operator stops finding out that the
      lock is uninstalled.
   2. **Stage by path, never by sweep.** Commits here are not normally yours at all (see
      the top of this file), but when you were explicitly asked to commit:
      `git add -- <the exact files you wrote>`. Never `git add -A`, never `git add .`,
      never `git commit -a`. A sweep is precisely what turned one agent's write into the
      68-file commit above; a path-scoped add cannot reach another writer's staged work.
   3. **Bracket the write with `git status --porcelain`.** If a path you did not write
      changed while you worked, another writer is live: stop, commit nothing, and report
      what moved.

   **None of that is a lock and it must not be recorded as one.** It serializes nothing —
   two agents can still write the same note and the last write wins. It only bounds the
   blast radius to the files you touched. A cross-platform lock is unwritten work, not an
   undocumented feature.
3. **One idea per page.** Set `updated` when you touch a page. Populate `sources:`.
4. **Facts in notes, shape on canvases.** Anything load-bearing must exist as text in
   a note even if it also appears on a canvas — a canvas-only fact is invisible to
   search. See the `claude-memories-canvas` skill.
5. **Never hand-edit the queue.** `inbox/pending-reflect.md` has exactly one writer,
   and it is `vault-queue.py` — **resolve both the interpreter and the script; pin
   neither.** `C:\Python314\python.exe` names one build directory and stops being
   true at the next Python upgrade on that same Windows box, never mind on Linux:
   ```bash
   PY=""
   for c in python3 python py; do
     command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }
   done
   QUEUE="$HOME/.claude/hooks/vault-queue.py"   # %USERPROFILE%\.claude\... on Windows

   if [ -z "$PY" ] || [ ! -f "$QUEUE" ]; then
     # Same third outcome as the lock: the writer is a host-local hook, so on a
     # host that never installed it there is nothing to run. Say so and stop.
     # Do NOT fall back to editing the file by hand - see below.
     echo "NO QUEUE WRITER: python=${PY:-unresolved} script=$QUEUE" >&2
   else
     "$PY" "$QUEUE" checkoff --session <id> --result "<what came out>"
   fi
   ```
   It holds a lock the capture hooks respect. Hand-editing races them — so when the
   writer is absent the answer is to report the check-off as not done, never to edit
   `pending-reflect.md` yourself.

   **Measured 2026-09-22:** `vault-queue.py` is installed on no host this was checked
   on, and it is shipped by nothing in this marketplace — `vault-automation/` ships
   `vault-capture.py` (the queue's *appender*) and `gardener-template.ps1`, and no
   `vault-queue.py` at all. So on a fresh machine step 5 has no writer to call. That
   is the same host-local-artifact gap as the lock, one file further down the loop,
   and it is unfixed: shipping the writer is work this skill cannot do from here.
6. **Never create a file named `nul`.** Windows reserves the name and git aborts every
   `git add -A` with "short read while indexing nul" — it broke every commit in this
   repo for days. Redirect to `$null` in PowerShell, never to `nul`.

## Do not touch

`HOME.md` (Dataview maintains it) and `.obsidian/` (per-machine plugin state).

Auto-memory under `~/.claude/projects/<slug>/memory/` is written
**through the harness's memory tooling for the current project only** — that is the
route the table above means by "write to auto-memory". Do not hand-edit those files,
and do not touch another project's `<slug>` directory or anything else under
`~/.claude/projects/`; the harness owns that tree.

## The loop this vault sits inside

`work → capture → distil → recall`. Capture is the `SessionEnd` / `PreCompact` hook
`vault-capture.py`, which queues one line per session. Distil is the nightly
**Claude Vault Gardener** task running `.claude\gardener.ps1`, or `/garden` attended.
Recall is `/hydrate`, `/recall`, `/reflect`, `/pickup`, `/vault-status`. Full design:
`wiki/concepts/Vault automation - the capture and gardener loop.md`, and the shipped
implementation of that loop is this repo's [`vault-automation/`](../../vault-automation).
