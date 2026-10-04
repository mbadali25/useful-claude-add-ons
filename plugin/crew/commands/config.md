---
description: Show where every crew setting comes from, and set machine or repo config from a menu
argument-hint: [--show|--models|--rebuild|--restore <stamp>|--backups|--save-profile]
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Skill, AskUserQuestion
---

Crew config, both layers: the machine-global `~/.claude/crew/config.json` and
this repo's `.crew/config.json`.

Arguments: $ARGUMENTS
- no argument — the menu. Follow
  `${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/config-menu.md` exactly: pick the
  layer (this machine, this repo, view both, or delete this repo's config),
  an area, a setting, and a value from the list. `/crew:config-setup` is the
  same menu under another name.
- `--show` — `crew_config.py --root <repo> --explain --all`, then
  `--check-global`, and stop: every key with its value and layer (`default`,
  `global`, `repo`, `repo+global`; `repo-only` marked, `held down by <layer>`
  for a personal or ratcheted key), then the `shadow:` and `profile drift:`
  findings. Ask nothing, write nothing.
- `--rebuild --repo|--global [--no-profile]` — regenerate a lost or corrupt
  config from the template plus the owner's saved profile
  (`~/.claude/crew/profile.json`; the vault copy when `memory.vaultPath` is
  set, the newer one when they differ). Exit 3 when a profile copy is there
  and unreadable (could not tell), 2 when none exists without `--no-profile`.
- `--restore <stamp> --repo|--global` — put a backup back; `--backups
  --repo|--global` lists the stamps, newest first.
- `--save-profile [--repo|--global]` — capture the non-default values of
  either layer (both when neither is named) into the profile.
- `--models` — the per-role table only: which provider, model and family back
  each `qa` and `dev` role, which fallbacks are armed, and whether the
  self-review guard is barring anything. Reports, writes nothing.

`global-config.md` stays the reference for what the machine-layer keys mean;
the menu's recommendations cite it.

Two behaviours of the global file to state whenever they come up, because both
changed in 0.16.0 and both are silent if unmentioned:

- **A repo-only key in this file takes effect nowhere.** The global layer is
  filtered to machine-and-person keys before it is merged, so a `tracker` or a
  `graph.obsidian.dir` set here reaches no repository at all. `--show` names
  each one it finds.
- **What survives is a default, not a lock.** Every key here is overridable in
  a repo's own `.crew/config.json`, which is why step 1's `source` column
  exists. The personal `autopilot` keys are the exception: the STRICTER of the
  two layers wins, and a silent layer imposes nothing. A repo file that spells
  one at its default holds the global value down; `--show` names it as a
  `shadow:` and `--unset <path> --repo --apply` removes it on a yes.

On native Windows the walkthrough also probes WSL (`crew_shell.py probe --write`)
and offers `shellRoute.mode`: `auto`, `wsl`, `powershell` or `gitbash`.

This command works with no repo in mind: `--root` is optional, and with no
`.crew/config.json` the `repo` layer is simply empty and the menu offers the
machine layer only. In a linked git worktree with no crew config of its own,
the `repo` layer is the main checkout's file; `--explain` and `--models` print it first, as
`repo layer: <path> (<own | main checkout | unknown>)`. An `own` line in a linked
worktree whose main checkout also has a config adds `the main checkout's (<path>)
is not read`: own wins whole, and a crew <= 1.0.68 heal wrote a default into
every lane that had none, so say which it is before trusting the lane's settings.

How it writes, whatever the arguments say:

- **Nothing before the plan is shown and approved.** Every write is a dry run
  first, and `--apply` follows a yes. Each one backs the file up first to
  `~/.claude/crew/backups/` (newest 20 kept); a failed backup writes nothing
  (exit 4). Name the backup after the write. `--set`/`--unset` and Save also
  refresh the profile; rebuild and restore never do.
- **This command writes `.crew/config.json` by four routes, all `--apply`
  only:** `--set`/`--unset PATH --repo`, `--rebuild --repo`, `--restore
  <stamp> --repo`, and the menu's Save, never a hand edit:
  `crew_config.py --set PATH=JSON --repo [--apply]`, or the menu's
  `crew_config_menu.py save`. It merges, judges every leaf (a whole-block
  value included) and the whole file it would produce, refuses unknown keys
  and out-of-range values, and marks a widening with `!`. Both writers are
  compare-and-swap under a lock beside the file: the dry run prints a
  `digest:` (`absent` for no file), and `--apply --expect <digest>` refuses a
  file that changed, or appeared, since; a repo write also prints the
  `machine digest:` its widening marks read and takes `--expect-global`. It refuses `platform.*` (platform-sync
  owns it), `schema`, `scope.mode` and `scope.allowCliApproval` (the scope
  guard's trust root, a hand edit by the owner or `/crew:init`), and
  `context.autoClear.onlyRepos` / `.onlySessions` (read from the machine file
  only); `context.autoClear.enabled` and `resume.auto` take only a veto
  (`false`) or `null` at the repo layer.
- **Deleting the repo config** is the menu's delete step only: preview, typed
  repo name, then one rename of the file to `.crew/config.json.bak-<UTC>`
  under the lock, compared with what the preview read (a changed file is put
  back and nothing is deleted), and three printed restore lines (sh, cmd,
  PowerShell).
