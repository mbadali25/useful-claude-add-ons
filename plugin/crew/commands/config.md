---
description: Show where every crew setting comes from, and guide the machine-global config
argument-hint: [--show]
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Skill
---

Walk the machine-global crew config at `~/.claude/crew/config.json`.

Follow `${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/global-config.md` exactly. It
defines the four steps, the two reporting commands, the dry-run-then-`--apply`
discipline, and the rules about writing outside the repository.

Arguments: $ARGUMENTS
- `--show` — run step 1 only (the resolved table and the findings) and stop.
  Ask nothing, write nothing.
- `--models` — the per-role table only: which provider, model and family back
  each `qa` and `dev` role, which fallbacks are armed, and whether the
  self-review guard is barring anything. Reports, writes nothing.
- no argument — the full walkthrough.

Two behaviours of the global file to state whenever they come up, because both
changed in 0.16.0 and both are silent if unmentioned:

- **A repo-only key in this file takes effect nowhere.** The global layer is
  filtered to machine-and-person keys before it is merged, so a `tracker` or a
  `graph.obsidian.dir` set here reaches no repository at all. `--show` names
  each one it finds.
- **What survives is a default, not a lock.** Every key here is overridable in
  a repo's own `.crew/config.json`, which is why step 1's `source` column
  exists.

This command works with no repo in mind: `--root` is optional, and with no
`.crew/config.json` the `repo` layer is simply empty. Run it from anywhere.

Two things it never does, whatever the arguments say: it does not write
`.crew/config.json` — that is `/crew:init` — and it does not write anything at
all until it has shown the plan and been told to go ahead.
