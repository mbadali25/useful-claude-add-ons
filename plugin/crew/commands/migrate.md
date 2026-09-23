---
description: One-time move of a 0.20 crew setup to the 1.0 layout - preview, backup, atomic apply, rollback
argument-hint: "[--preview | --apply | --rollback <backup-dir>]"
allowed-tools: Bash, Read
---

Move this repo's crew data onto the 1.0 layout. Run once per repository.

## Step 1 - preview (always first)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_migrate.py" --root . --preview
```

On Git Bash without `python3`, use `python` or `py -3`. If none resolves, say
so and stop.

Preview writes nothing. Show me its output verbatim and point out:

- every `CONFLICT` line - apply refuses while any exist;
- every `unmapped` key - carried into `crew.json` under `unmapped`, never dropped;
- every `skip` line - a file that was not imported, and why;
- every `retireable` line - an original left in place that 1.0 no longer reads.

Then ask whether to apply. Do not apply in the same turn as the preview.

## Step 2 - apply (only after I say yes)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_migrate.py" --root . --apply
```

What apply does, in order:

1. Copies the sources (`config.json`, `metrics.md`, the PM journal) into a new
   `.crew/backups/migrate-<UTC timestamp>/` and writes a manifest naming every
   file it is about to create, with the sha256 of what it will write.
2. Stages every new file as a temp beside its target, then moves each into
   place with `os.replace`. If anything raises, whatever landed is removed and
   the tree is the old one. A hard kill leaves the manifest unfinished; every
   later run reports it until you roll back.
3. Never overwrites and never deletes. An existing target with different bytes
   is a conflict, found in preview.

| From | To |
|---|---|
| `.crew/config.json` (schema up to 7) | `.crew/crew.json` (schema 1) |
| `.work/tickets/<ID>.md` | `.work/tickets/<ID>/ticket.md` + `provenance.json` |
| `.work/cache/<ID>.md` (Jira, SDP, Obsidian) | the same, with `source` naming the tracker |
| `.crew/metrics.md` | `.crew/metrics.jsonl`, one object per row, missing values `UNKNOWN` |
| `.crew/pm-journal.md`, `pm-standing.md` | copied to `.crew/archive/` |
| `.crew/codemap/` and its anchors | untouched |

The full key-by-key table for `crew.json` is the docstring of
`hooks/scripts/crew_migrate.py`; a test holds the table and the code to each
other.

Print the `backup:` line apply ends with. That path is the only way to undo it.

## Rollback

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_migrate.py" --root . --rollback <backup-dir>
```

Removes exactly the files apply created, after checking each still holds the
bytes apply wrote. If you edited one since, rollback refuses and changes
nothing - resolve that file by hand. The backup directory itself is kept as
the record.

## After

The originals marked `retireable` still exist. Removing them is a separate,
explicit decision for the owner - never do it as part of this command.

Run `/crew:status` to confirm the repo now reads as `.crew/crew.json schema 1`.
