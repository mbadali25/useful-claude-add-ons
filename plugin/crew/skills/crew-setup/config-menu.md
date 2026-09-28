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
  (exit 2) is the guard working: read it out, never route around it.
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
another area, the other layer, show pending, Save, or Discard.

## 4. Save

Build the pending set as `{"machine": {...}, "repo": {...}}` and run the dry
run first:

```
S save --changes '<json>'
```

It validates both layers before writing either and prints both diffs. Read
back every `!` line (a widening) and every `held down by the machine-global
layer` line (a repo value the machine layer overrules). Then, and only after
the dry run has been shown and the owner said yes, the same command with
`--apply`. Each changed layer is written once. If it reports one layer
written and the other not, say exactly that; the written layer stays written.

**Discard** writes nothing and ends the menu.

## 5. Afterwards

Run `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_config.py --root . --explain`
again, and `--models` too if any `qa.*` or `dev.*` key changed, and read the
result back. A config change nobody verified is a claim, not a change.

## 6. Delete this repo's config

1. Preview: `S delete-repo`. It prints what changes (a `!` marks a
   widening: `scope.mode` returning to `off` disarms the scope guard), a
   `stays` line for a ratcheted key the repo narrowed under a wider machine
   value (deleting does not widen it: an absent repo value is the floor), and
   what deleting means on disk: hooks stand down until the next SessionStart,
   then platform-sync recreates the built-in defaults and re-detects
   `platform.*`, which is why `platform.*` is not listed. It exits 2 without
   a confirmation; that is expected.
2. Ask the owner to type the repo name the preview asks for: the checkout's
   name (`git rev-parse --show-toplevel`'s basename, else the directory's).
   Never fill it in for them, and never infer it from a yes.
3. `S delete-repo --confirm <name> --apply`. It writes a verified backup
   (`.crew/config.json.bak-<UTC timestamp>`) before it deletes, and refuses if
   the backup fails.
4. Read the printed `restore:` command back to the owner verbatim. It copies
   the backup back (backing up whatever is there first, such as healed
   defaults).

## Headless

With no AskUserQuestion (a headless or scripted session), print the plan
instead of asking: `crew_config_menu.py --root . spec --layer <layer>`, and
require the explicit flags, `save --changes '<json>' --apply` or
`delete-repo --confirm <name> --apply`. Nothing is applied from a default.
