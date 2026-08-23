# CLAUDE.md

Instructions for Claude Code working in this repository.

## What this repo is

A Claude Code **marketplace**. Every directory under `skills/` is an installable plugin
holding a single `SKILL.md`; every directory under `plugin/` is a full plugin that may
also bundle subagents, slash commands, and hooks. Both are registered in
`.claude-plugin/marketplace.json`. Two bootstrap scripts under `scripts/` install them,
plus the team's other marketplaces and tooling, onto a fresh machine.

## Documentation rules — not optional

### 1. Install scripts change → update `README.md`

Any edit to `scripts/install-prerequisites.sh` or `scripts/install-prerequisites.ps1`
must be reflected in `README.md` in the same change. That means, at minimum:

- The numbered **menu table** (item number, label, whether it's on by default).
- The **"What each item actually installs"** table.
- The **switch table** if you added, renamed, or removed a command-line flag.
- Any per-item prose that names an item by number — the numbers shift whenever an item
  is added or removed.

Also update `INSTALLATION.md` (it documents the same menu in more detail) and add a
`CHANGELOG.md` entry.

The two scripts are a **matched pair**: the menu keys, their order, and their default
flags must be identical between them, or `--select 3,7` means different things on
Windows and Linux. Change one, change the other.

The README's one-liner install URLs are pinned to a commit SHA. After merging a change
to either script to `main`, run `git rev-parse HEAD` and re-pin both URLs.

### 2. New skill under `skills/` → update `README.md`

Adding a directory to `skills/` is not finished until it is registered in all four
places:

1. `.claude-plugin/marketplace.json` — `name`, `source` (`./skills/<name>`),
   `description`, `version`.
2. `skills/README.md` — a row in the overview table (all five columns).
3. `README.md` — the same row, inside the `<!-- BEGIN skills/README.md -->` block, plus
   the skill count wherever it appears as a number.
4. Both install scripts — `SKILL_KEYS` / `SKILL_NAME` in the `.sh`, `$script:SkillCatalog`
   in the `.ps1`. Keep the two in the same order, with the same text.

Renaming or removing a skill means the same four places, in reverse.

### 3. New plugin under `plugin/` → the same rule, plus two

A directory under `plugin/` is a full Claude Code plugin, not a skill. Register it in
the same four places, with `source` pointing at `./plugin/<name>`:

1. `.claude-plugin/marketplace.json`.
2. `plugin/README.md` — a row in the overview table (all five columns).
3. `README.md` — the same row, inside the `<!-- BEGIN plugin/README.md -->` block, plus
   the plugin count wherever it appears as a number.
4. Both install scripts — `PLUGIN_KEYS` / `PLUGIN_NAME` in the `.sh`,
   `$script:PluginCatalog` in the `.ps1`.

Two rules that apply to plugins and not to skills:

- **A plugin that registers hooks defaults to OFF in the menu.** A hook is not
  advisory — it runs whether or not Claude agrees with it — so a bootstrap run must not
  add one to someone's machine without the box being ticked.
- **Ship every hook script in both flavours**, a `.sh` and a `.ps1` registered with
  `shell: powershell`. A bash-only hook is silently inert on Windows, which reads as
  "the gate passed" rather than "the gate never ran".

Never commit a `marketplace.json` inside a plugin directory. The repo root's is the only
marketplace here; a nested one makes the plugin directory look like a second marketplace
to `claude plugin marketplace add`.

## Conventions

- Skills follow `Skill-Authoring-Standard.md`; changes follow `Skill-Pipeline.md`.
- The picker menus clip every line at `terminal width - 9` (`pick_fit` in bash,
  `Format-PickerLine` in PowerShell) and append an ellipsis. The current labels are
  written for a ~95-column window; narrower consoles clip them, which is degradation
  rather than breakage. What is *not* survivable is a line that wraps — that throws off
  the cursor-up redraw count and smears the menu over whatever was above it, which is
  why nothing may bypass the clip helpers.
- Both scripts are idempotent by design: detect first, then act. A new install step
  needs a detection branch that reports "already installed" rather than reinstalling.
