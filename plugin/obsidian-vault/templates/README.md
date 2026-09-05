# Note templates

Six starting notes that satisfy the frontmatter contract in the
`obsidian-memory-contract` skill. Copy one, substitute the tokens below, write
it into the vault. `/obsidian-vault:note` does exactly that for you.

These exist because `hooks/scripts/vault_guard.py` blocks a write that breaks
the contract, and until now nothing in this plugin helped you produce a note
that passes. A guard with no template is a wall with no door.

## Substitution is a literal string replace, and it is not optional

There is no Templater syntax here and no `{{date}}`. Those resolve inside the
Obsidian app, and Claude writes these notes through the filesystem or the REST
bridge, where nothing would ever replace them. Every token below is an inert
ASCII string that no Obsidian feature rewrites, so if you forget one it stays
visible in the note instead of quietly becoming something else.

| Token | Replace with | Rule |
|---|---|---|
| `__TITLE__` | the filename you are about to write, without `.md` | Must be byte-identical to the filename stem. The guard compares them and blocks on any difference, including case. |
| `__TODAY__` | today's date, `YYYY-MM-DD` | The guard blocks when `updated:` is not today. On a new note `created:` is the same date and never changes again. |
| `__DECISION_ID__` | `D-NNN` | `decision.md` only. Use the next unused number in the vault; grep `decision_id:` to find the highest one. |

Replace every occurrence in the file, frontmatter and body alike.

## What the guard checks, and what it does not

Blocking: the six keys present and non-empty, `title` equal to the filename,
`updated` equal to today, and (where a vault turns `guard.asciiOnly` on) pure
ASCII in what you wrote. Advisory: the type-specific keys. Every template here
already carries every type key the guard names for its type, so a note built
from one produces no advisory either.

The guard does **not** validate the value of `type:`. An unsubstituted token or
a type the contract never defined passes it silently, which is why
`/obsidian-vault:note` checks the type itself.

## Empty values are deliberate

Most type-specific keys ship with no value. That is the contract's own evidence
rule: an absent value is honest, an invented one is a fact the vault will later
be asked to trust. Fill them in as you learn them. The exception is
`authority: unknown` on a source, which the contract names as a correct value
rather than a gap.

## Two things to watch

- **A YAML comment must sit on its own line.** The frontmatter parser reads
  everything after `key:` as the value, so `title: "x"  # a note` makes the
  title `"x"  # a note` and the guard blocks it against the filename.
- **A vault's own templates folder is exempt.** The guard skips any path with
  a `templates/` segment, so a copy of these files parked in
  `<vault>/wiki/templates/` will not be flagged for its unsubstituted tokens -
  and will not be checked when you edit it either.

## Tags

Each template carries one tag naming its type. Check the vault's existing
vocabulary before keeping a second one - `design.md` adds `design`, which is
new in a fresh vault and may already have a home in yours.
