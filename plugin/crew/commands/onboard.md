---
description: Learn this codebase once and write a durable, verifiable code map
allowed-tools: Read, Grep, Glob, Bash, Write, Edit, Agent
---

Build the code map for this repo. This is the expensive one-time cost. Do it
properly or do not do it — a half-accurate map is worse than none, because it
gets trusted.

**Budget it.** Spawn `crew:explorer` once per subsystem, in parallel, not one
agent over the whole repo. Each returns a summary; only summaries reach this
conversation. Cap at 6 subsystems per run. If the repo is bigger, do it in
several runs and say which areas are still unmapped.

**Write `.crew/codemap/<subsystem>.md`**, each under 60 lines:
```
# <subsystem>
anchor: <repo>@<short-sha>
verified: <date>

## Does
<2 sentences>

## Entry points
- `path:line` — <what calls this and when>

## Owns data
- <table/collection> via `path`

## Calls out to
- <service/repo> at `path:line`

## Landmines
- <the thing that breaks when touched>

## Unverified
- <what you inferred but could not confirm>
```

**Anchors are the whole point.** Every claim names a file path. A map without
anchors cannot be re-verified, so it silently rots and you keep trusting it.

**Write `.crew/codemap/INDEX.md`** — one line per subsystem: name, one-sentence
purpose, anchor sha. This is the only codemap file loaded by default.

**Freshness rule** (put this in the repo CLAUDE.md too): before relying on a
codemap note, check whether its anchor files changed since the recorded sha:
`git diff --name-only <anchor-sha>..HEAD -- <paths>`. If they did, re-verify that
section before using it. Code always wins over notes.

## Then make the knowledge executable

A code map describes; it does not verify. Onboarding is not finished until the
repo also has:

1. `.crew/verify.json` — run `/crew:verify`. Which checks a change requires is
   the part that prevents mistakes; the description only helps you find things.
2. `docs/reference/` — run `/crew:reference`. The codemap answers "where does
   this live"; the reference answers "what can this system do, and how do I call
   it". Those are different questions and the second does not fall out of the
   first. Endpoints, scheduled jobs, queue consumers, CLI commands, feature
   flags, integrations — each anchored to a file and line.
3. `.crew/secrets.md` — record where test credentials come from and which env
   var each lands in. Names and retrieval commands only, never values. See the
   `crew-verification` skill.
4. `e2e/` specs if this repo has a UI — delegate to `crew:browser-tester`.

Report which of the four are missing when you finish. A codemap on its own is
the least useful of the five artifacts.

Run `/crew:onboard --refresh <subsystem>` to re-map one area after big changes.
Do not re-run the whole thing on a schedule; that is the cost you were avoiding.
