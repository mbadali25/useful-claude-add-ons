---
name: crew-memory
description: Conventions for durable project memory across repos, including Obsidian vault integration. Use when the user says set up memory, wire up Obsidian, connect my vault, or when writing or reading code maps, decision notes, or cross-repo contracts.
---

# Crew memory

Obsidian is a good choice here for an unglamorous reason: it is a folder of
markdown files. Claude Code can read and write it with no integration layer, and
you get backlinks and graph view for free. There is nothing to build.

## Vault layout

```
vault/
  repos/<repo>/codemap/<subsystem>.md    # mirrors .crew/codemap/
  repos/<repo>/decisions/<adr>.md
  contracts/<service-a>--<service-b>.md  # cross-repo API contracts
  INDEX.md                               # one line per note
```

## The rule that makes this work

**Only INDEX.md is read by default.** Everything else is read by path, on demand,
one note at a time.

A vault is unbounded. An agent that "checks the vault" will happily pull 40k
tokens of notes to answer a question the code would have answered in 400. Index
first, then one targeted read. If a task needs more than three notes, the notes
are badly organized — say so.

## Anchors and rot

Every claim carries the file path it came from, and every note carries
`anchor: <repo>@<sha>`. Before relying on a note, check whether its anchor files
moved:

```
git diff --name-only <anchor-sha>..HEAD -- <paths>
```

Changed? Re-verify that section before using it.

**Code always wins over notes.** When a note and the code disagree, the note is
wrong, full stop. Fix the note, do not reason from it.

This matters more than it sounds. A stale note is confidently wrong in exactly
the way a fresh search never is, and it arrives with the authority of something
you wrote down deliberately.

## What belongs in the vault

Yes: subsystem maps, cross-repo contracts, decisions and their rejected
alternatives, landmines, "we tried X and it failed because Y."

No: anything derivable by reading the code in under a minute. API docs. Copies of
tickets. Anything you would not re-verify before trusting.

## Cross-repo value

This is the real payoff with 5+ repos. `contracts/` notes are where you record
that repo A's endpoint is consumed by repo B in a way B's code does not make
obvious. No single repo's code contains that fact, so it is the one kind of note
that cannot rot into irrelevance — only into inaccuracy, which anchors catch.

## Sync

Repo-local `.crew/codemap/` is the source of truth; the vault mirrors it. If the
vault is on the same machine, symlink `.crew/codemap` into the vault rather than
copying, so there is never a divergence question.
