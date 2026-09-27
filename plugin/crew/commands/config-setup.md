---
description: Set up crew config from a menu - machine or repo layer, dry run then apply, or delete the repo config
allowed-tools: Read, Bash, Grep, Glob, Skill, AskUserQuestion
---

The `/crew:config` menu, under the name people look for first. Same
procedure, same rules: `/crew:config` with no argument does exactly this.

Follow `${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/config-menu.md` exactly. Pick
the layer (this machine's `~/.claude/crew/config.json` or this repo's
`.crew/config.json`), an area, a setting and a value from the list; nothing
is written until Save shows the dry run and the owner says yes. Deleting the
repo config previews what changes, needs the typed repo name, backs up first
and prints the restore command.

It takes no arguments. `/crew:config --show` and `/crew:config --models`
report without the menu.
