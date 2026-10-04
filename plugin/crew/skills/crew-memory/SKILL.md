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

## Native memories as vault pointers

A native memory file (Claude Code's `~/.claude/projects/<project>/memory/<fact>.md`)
may hold one line in place of its body, with the frontmatter left as it is:

```
vault: <name> | note: <vault-relative path, forward slashes, ending .md>
```

The vault is named, never given as an absolute path, so the same file works on
every machine the vault is synced to. When you meet one, resolve it on this host
and read the path it prints:

```
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_memory.py" resolve --file <memory file>
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_memory.py" check --memory-dir <memory dir>
```

The name maps to a path through `vaults.<name>.path` in `~/.claude/obsidian/config.json`
(a `role: ignore` vault is not resolved). Only the name `memory` falls back: to the
crew config's `memory.vaultPath`, then, only when that file has no `vaults` block, to
its legacy top-level `vaultPath`. `OBSIDIAN_VAULT_PATH` is not honoured. The pointer
line is exact and must be the whole body: a first line that starts `vault` and `:` in
any case, indent or spacing, is a pointer attempt when `note:` or `|` appears anywhere
in the body (a pointer wrapped before its `|` included) or the line is a bare vault name
alone (`vault: work`); anything less than the full grammar is then `malformed`. With
neither it is prose (`Vault: keep client notes in the work vault` is a memory, not a
pointer). A config file counts as missing
only when it is not there at all; one that is there and does not read, parse or match
its expected shape (or has a duplicate key, nests too deep or is over 1 MiB) is
`no-vault-config`, naming the field. A bad Obsidian config stops every name; a bad crew config stops `memory`, the one name it can answer for, and any name when there is no Obsidian config to say which failure applies.

| state | meaning | exit |
|---|---|---|
| `resolved` | the note exists; `path:` is printed | 0 |
| `full-text` | not a pointer; the body is the memory | 0 |
| `malformed` | a `vault:` first line holding `note:` or `|` (any case, indent or spacing) that fails the grammar or is not alone | 1 |
| `no-vault-config` | no Obsidian config and no `memory.vaultPath`, or a config that cannot be read, does not parse or has a field of the wrong shape | 1 |
| `vault-unknown` | this host names no such vault, or it is `ignore` | 1 |
| `vault-unavailable` | the configured path is not an absolute, listable directory here | 1 |
| `note-missing` | the vault is there, the note is not | 1 |
| `outside-vault` | a symlink below the vault, or the path leaves it | 1 |
| `unreadable` | the memory file is not a readable UTF-8 regular file, or a folder or note below the vault cannot be read or opened | 1 |

Any state other than `resolved` or `full-text`: tell the user the state and its
reason. Do not guess the note, search another vault for it, or treat the pointer
as the memory. This crew version only reads pointers; writing them arrives in a
later version.
