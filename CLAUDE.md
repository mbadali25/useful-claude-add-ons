# CLAUDE.md

Instructions for Claude Code working in this repository.

## What this repo is

A Claude Code **skill marketplace**. Every directory under `skills/` is an installable
plugin, registered in `.claude-plugin/marketplace.json`. Two bootstrap scripts under
`scripts/` install those skills, plus the team's other marketplaces and tooling, onto a
fresh machine.

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

## Conventions

- Skills follow `Skill-Authoring-Standard.md`; changes follow `Skill-Pipeline.md`.
- The picker menus in both scripts clip long lines to the terminal width — keep menu
  labels under roughly 80 characters or they get truncated on a standard console.
- Both scripts are idempotent by design: detect first, then act. A new install step
  needs a detection branch that reports "already installed" rather than reinstalling.
