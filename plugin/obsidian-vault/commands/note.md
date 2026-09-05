---
description: Create a contract-conforming note from this plugin's templates, with title and dates stamped so the vault guard passes on the first write
argument-hint: <memory|concept|decision|session|source|design> <note title>
allowed-tools: Read, Write, Grep, Glob
---

Create a new note of type $1 titled $2 (everything after the first word is the
title).

This command exists so a note passes `hooks/scripts/vault_guard.py` on the
first write rather than after a rejection. The guard blocks a bad note in the
same turn you write it; that is a fine safety net and a terrible authoring
loop. Read `${CLAUDE_PLUGIN_ROOT}/templates/README.md` before your first run -
it states the substitution rules once, and this command does not repeat them.

## Steps

1. **Validate the kind against the template set.** $1 must be one of `memory`,
   `concept`, `decision`, `session`, `source`, `design`. Anything else: stop
   and say which six exist. Do not improvise a seventh template.

   **The guard will not catch this for you.** It checks that `type:` is
   present, never what it says, so a made-up type is written, accepted, and
   invisible until a Dataview query keyed on the contract's types silently
   omits the note.

2. **Read the vault's own `CLAUDE.md` first**, at the vault root. It wins
   wherever it differs from these templates - its own type vocabulary, its
   folder layout, its tag families, and whether it requires pure ASCII. If it
   names a folder for this kind of note, write there; otherwise follow the
   layout already visible in the vault (`Glob` for `**/*.md` and look at where
   siblings of this type live).

3. **Decide the filename, then derive the title from it.** Not the other way
   round. Take $2, apply whatever casing and separator the vault's existing
   filenames already use, and settle on the exact path you are going to write.
   The filename stem - the name without `.md` - is now the value of `title:`,
   byte for byte.

4. **Read the template** from
   `${CLAUDE_PLUGIN_ROOT}/templates/<kind>.md` and substitute:

   - `__TITLE__` -> the filename stem from step 3.
   - `__TODAY__` -> today's date as `YYYY-MM-DD`. Use the current date from
     this session's context; this command runs no shell and needs none.
   - `__DECISION_ID__` -> `D-NNN` (decision only). `Grep` the vault for
     `decision_id:` and take the next unused number. Never reuse one.

   Replace every occurrence. A leftover token is a visible defect rather than
   a silent one, which is the whole reason the tokens look like that.

5. **Write the note, then fill in what you actually know.** The body headings
   are a skeleton; replace the guidance line under each with real content or
   delete the section. Leave a type-specific frontmatter key empty rather than
   guessing at it - `authority: unknown` is a correct value, an invented URL
   or hash is not.

6. **Never overwrite.** If the path already exists, stop and report it. This
   command creates; editing an existing note is `/obsidian-vault:garden` or a
   plain `Edit`, both of which keep `created:` as it was and bump `updated:`.

## When the guard rejects it anyway

The failure text names the file and the rule. Four causes cover almost all of
them, so read the message rather than re-running:

- `MISSING required frontmatter` - one of the six keys is absent or empty. A
  bare `tags:` with no `  - item` under it counts as empty, and the list items
  need the two leading spaces.
- `title: ... does not match filename` - step 3 ran backwards. Fix `title:`
  to the filename stem, or rename the file. They must be identical.
- `updated: ... but you just edited it` - the `__TODAY__` substitution used a
  stale date, or ran on a session that started yesterday.
- `NON-ASCII introduced` - the vault has `guard.asciiOnly` on and something
  you wrote carries a smart quote or an em dash. The message names the
  character and its replacement.

Report what you wrote, where, and any frontmatter key you deliberately left
empty.
