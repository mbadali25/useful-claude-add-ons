# The `/crew:config` menu

Followed by `/crew:config` with no argument and by its alias
`/crew:config-setup`. One procedure, two entry points.

The menu is a view over `hooks/scripts/crew_config_menu.py`, which reads
`crew_config.py`'s own key lists. Do not add, rename or hide a key in prose:
what the script lists is what the menu offers, and what it refuses stays
refused. `global-config.md` is still the reference for what each key means
(`pm.authority` tiers, the role-pin table and its three warnings); read it
before explaining a choice.

`S` below is:

```
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_config_menu.py --root .
```

## Rules

- **Select, never type.** Every writable setting offers at least one value,
  recommendation first. Other is an escape and is never required: offer it,
  never lead with it, and never ask the owner to type a value a choice
  already covers.
- **Nothing is written before Save.** Choices go into a pending set held in
  this conversation. Show it whenever asked, and let the owner change or drop
  any entry, across areas and across both layers.
- **Save is one dry run, then one apply.** The dry run is
  `S save --changes '<json>'`; `--apply` is added only after the dry run has
  been shown and the owner said yes to it.
- **Never hand-edit either config file.** Every write goes through
  `S save`, which calls `crew_config.py`'s validated writers. A refusal
  (exit 2) is the guard working: read it out, never route around it. Both
  writers judge every leaf (a whole-block value included) and the whole file
  they would produce, and both are compare-and-swap under a lock beside the
  file (`config.json.lock`): a file another session changed since the dry run
  is refused, never merged over.
- **A row Save would refuse is read-only, with the writer's reason.** The
  menu probes every value through the layer's own planner on the file Save
  would produce, the pending set included. A row whose every value is
  refused (a bad value already in the file, such as an unknown `qa.provider`)
  shows `refusedReason`: read it out, fix the key it names first, then come
  back to the row.
- **Read-only rows stay read-only.** At the repo layer `platform.*`,
  `schema`, `scope.mode`, `scope.allowCliApproval` and
  `context.autoClear.onlyRepos` / `.onlySessions` are shown with the reason
  they are refused. `scope.*` is the approval and scope guard's trust root: it
  is a hand edit by the owner or `/crew:init`, never this menu. At the machine
  layer `platform.*` and `schema` are shown read-only too. When
  `.crew/config.json` is absent or does not parse, the repo spec's own
  `refusedReason` says so and every repo row is read-only: say that once and
  point at `/crew:init` or a new session (platform-sync heals it), rather
  than collecting picks Save would refuse.

## 1. Pick the layer

Ask with AskUserQuestion:

- **This machine** — `~/.claude/crew/config.json`, the default for every repo
  here.
- **This repo** — `.crew/config.json`.
- **View both** — run `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_config.py --root . --explain`
  and `S spec --layer repo`, show them, then ask again.
- **Delete this repo's config** — go to step 6.

## 2. Pick an area

```
S spec --layer <machine|repo> --json
```

Offer the areas that have rows (models, autopilot, guards, notify, memory,
autoclear, other), 3 choices per page plus More. When the repo layer's
`crewJson` is true, say once that `.crew/crew.json` exists and is read first
by `crew_context`, `crew_resume` and `crew_refresh_check`.

## 3. Pick a setting, then a value

Show the area's rows, 3 choices per page plus More. Each row's label carries
its current value and the layer that decided it (`value`, `source`). Pick a
row, then show its `choices` in order, 3 choices per page plus More: the
first is the recommendation, and each label already names which choice is
`current` and which is the `default`. Before offering a value that widens
something (a ratcheted key, `pm.authority`, `autopilot.mode: plan`,
`verifyGate: false`, `context.autoClear.unsafeFocus: true`), say what it
grants, from `global-config.md` or the `!` line Save will print.

A read-only row shows its `refusedReason` and offers nothing.

Add the pick to the pending set, then ask: another setting in this area,
another area, the other layer, show pending, Save, or Discard. Every `spec`
after the first pick passes the pending set, so rows are judged on the file
Save would produce: `S spec --layer <layer> --json --pending '<json>'`. A row
that becomes writable or read-only because of a pick is expected.

## 4. Save

Build the pending set as `{"machine": {...}, "repo": {...}}` and run the dry
run first:

```
S save --changes '<json>'
```

It validates both layers before writing either and prints both diffs, with a
`machine digest:` line whenever anything changes (a repo value's widening
marks are judged against the machine file, as this Save leaves it) and a
`repo digest:` line when the repo changes; `absent` means the file does not
exist yet. Read back every `!` line (a widening) and every `held down by the
machine-global layer` line (a repo value the machine layer overrules), and
record the digests. Then, and only after the dry run has been shown and the
owner said yes, the same command with `--apply --expect-machine <digest>
--expect-repo <digest>` (every digest the dry run printed, `absent`
included). A refusal naming a layer that "changed since the dry run" means
another session or an editor wrote or created the file in between: nothing
was written; run the dry run again and show it.
Each changed layer is written once. If it reports one layer written and the
other not, say exactly that; the written layer stays written.

**Discard** writes nothing and ends the menu.

## 5. Afterwards

Run `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_config.py --root . --explain`
again, and `--models` too if any `qa.*` or `dev.*` key changed, and read the
result back. A config change nobody verified is a claim, not a change.

## 6. Delete this repo's config

1. Preview: `S delete-repo`. It walks the file's own leaves and prints
   what changes (a `!` marks a widening: `scope.mode` returning to `off`
   disarms the scope guard), `-> (removed)` for a key crew does not know
   (kept by every write, removed with the file), a `stays` line for a
   ratcheted key the repo narrowed under a wider machine value (deleting does
   not widen it: an absent repo value is the floor), a `re-detected by
   platform-sync` group for the `platform.*` keys platform-sync writes (it
   promises no value: a key this machine gives no value for is left unset;
   any other `platform.*` key is `-> (removed)`), and what deleting means on disk:
   hooks stand down until the next SessionStart, then platform-sync recreates
   the built-in defaults. It ends with a `repo digest:` and a `machine
   digest:` line: the two files the preview was built from. It exits 2
   without a confirmation; that is expected. A file that does not parse, is
   empty, is `{}` or is not an object is refused outright (a restore could
   not take it back): say that platform-sync backs it up to
   `config.json.broken` and heals it at the next SessionStart, or the owner
   removes it by hand, and stop. A symlink or other non-regular file is
   refused the same way (its backup would be one restore refuses): the owner
   replaces or removes it by hand.
2. Ask the owner to type the repo name the preview asks for: the checkout's
   name (`git rev-parse --show-toplevel`'s basename, else the directory's).
   Never fill it in for them, and never infer it from a yes.
3. `S delete-repo --confirm <name> --apply --expect-repo <digest>
   --expect-machine <digest>`, with the two digests the preview printed:
   the apply refuses (exit 2) without them or when either file changed since,
   so the typed name confirms the preview that was shown. Under the machine
   lock and then the config lock it reads the machine file again (changed
   since the preview: exit 2, preview again), then moves the file to
   `.crew/config.json.bak-<UTC timestamp>` in one
   rename that never replaces an existing file (the backup is the file
   itself, never a copy), compares the moved bytes with what the preview
   read, and if the file changed since, moves it straight back, never over a
   file saved in between, and deletes nothing (exit 2: preview again).
   Exit 1 means another writer interleaved with the move: nothing is lost.
   Read out every path it names (the backup, `.crew/config.json`, and a
   `*.moving` name holding the other writer's file) and stop; never delete
   one for the owner.
4. It prints three restore lines, `restore (sh):`, `restore (cmd):` and
   `restore (PowerShell):`. Read back the one that matches the owner's shell
   verbatim, and say the other two exist. Each puts the backup back byte for
   byte (moving whatever is there aside first, such as healed defaults).
   Restore exits 1 the same way when another writer interleaves with that
   move-aside: read out the paths it names.

## Headless

With no AskUserQuestion (a headless or scripted session), print the plan
instead of asking: `crew_config_menu.py --root . spec --layer <layer>`, and
require the explicit flags, `save --changes '<json>' --apply
--expect-machine <digest> --expect-repo <digest>` (the digests from the dry
run) or `delete-repo --confirm <name> --apply --expect-repo <digest>
--expect-machine <digest>` (the digests from the preview). Nothing is
applied from a default.
