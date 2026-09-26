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
- every `retireable` line - an original left in place that 1.0 no longer reads;
- every `note` line - notably `pm.authority: autonomous`, which 1.0 keeps under
  `retired.pm` and records in `crew.json` `notes`: it arms nothing, and
  `/crew:autopilot` is its successor, off until `autopilot.mode: plan`.

Then list the path-scoped rules apply will generate from the code map:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_instructions.py" rules --root . --check
```

It writes nothing. Each `missing:` or `stale:` line is a `.claude/rules/` file apply will write,
each `orphan:` one it will remove, each `hand-written` line a file it will leave alone. Exit 1 here
means only that there is something to generate.

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
| `.crew/pm-journal.md`, `pm-standing.md` | copied to `.crew/archive/` | <!-- deliberate -->
| `.crew/codemap/` and its anchors | untouched |

The full key-by-key table for `crew.json` is the docstring of
`hooks/scripts/crew_migrate.py`; a test holds the table and the code to each
other.

Print the `backup:` line apply ends with. That path is the only way to undo it.

Then convert `context.autoClear` — the one helper `/crew:init` and
`/crew:onboard` also call, so relay its output rather than restating this.
Run it **once**: a second run cannot see this repo's pre-migration opt-in.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autoclear_setup.py" --root . apply-migrate
```

It rewrites `context.autoClear` in **both** `.crew/config.json` (what every sender reads) and `.crew/crew.json` (step 2's un-converted copy), whichever exist — converting only one leaves the other's stale value live. Prints a `notes` line per conversion, never silently: pre-1.0 `"windows"` becomes `"notify"` (sendkeys is an explicit opt-in); a duplicated repo `enabled: true` (0.20.17's read-only-the-repo-file workaround) is dropped since 1.0 gives it no effect (`enabled: false` opt-outs are kept); repo-copied `onlyRepos`/`onlySessions` are dropped too, being global-only under 1.0. `alreadyConfigured: true` means nothing to convert; a non-zero exit (e.g. a malformed machine-global file) means nothing was written — show the stderr message and stop.

A `widening: true` means the global file arms every crew repo on this machine (`enabled: true`, `onlyRepos: null`) — show `proposedOnlyRepos` and ask; only on yes, apply it with the generic writer (this write always precedes either repo write), never by re-running the command above: `crew_config.py --set 'context.autoClear.onlyRepos=<the list>' --apply`. Without a yes, say the widening is still in effect and leave it.

Then generate the rules the preview listed, and show the output verbatim:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_instructions.py" rules --root .
```

A `hand-written, left alone` line is a collision to report, never to overwrite. These files are
derived from `.crew/codemap/`, which migrate does not change, so they are outside the backup
manifest and rollback leaves them; `/crew:onboard` regenerates them.

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
