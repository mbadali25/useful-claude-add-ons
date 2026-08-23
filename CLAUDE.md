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

### 2. Changing a skill or plugin → bump its `version`

`claude plugin update` decides whether to re-copy a plugin by comparing the **declared
version**, not its contents. Editing anything under `skills/<name>/` or `plugin/<name>/`
without bumping that entry's `version` in `.claude-plugin/marketplace.json` means every
machine that already installed it keeps the old copy forever — the CLI reports "already
at the latest version" and copies nothing. Nothing about the repo looks wrong; the bug
only exists on other people's machines.

So: **content change → version bump, in the same commit.** A plugin that carries its own
`.claude-plugin/plugin.json` (`crew`) has to be bumped in both, to the same value.

`scripts/check-marketplace.py` enforces this and runs in CI. It walks the history of
`marketplace.json` to find where each version was last set and fails if that plugin's
files have changed since. It also checks every registration rule below, so run it before
pushing:

```bash
python3 scripts/check-marketplace.py
```

The install scripts detect the same condition at runtime and report it rather than
claiming the plugin is current; `scripts/_test/drift-detection.sh` is its regression
suite (needs the `claude` CLI; it builds a throwaway marketplace and never touches the
real config).

### 3. New skill under `skills/` → update `README.md`

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

### 4. New plugin under `plugin/` → five places, plus two extra rules

A directory under `plugin/` is a full Claude Code plugin, not a skill. It carries the
skills' registration rule with one more place bolted on — `plugin/` has both a catalog
(`README.md`) and a detail doc (`PLUGINS.md`), where `skills/` has only the catalog.
Register it in all five, with `source` pointing at `./plugin/<name>`:

1. `.claude-plugin/marketplace.json`.
2. `plugin/README.md` — a row in the overview table (all five columns).
3. `plugin/PLUGINS.md` — a section with the full component breakdown: every command,
   agent, bundled skill, and hook, and what starts running the moment it is enabled.
4. `README.md` — the same row, inside the `<!-- BEGIN plugin/README.md -->` block, plus
   the plugin count wherever it appears as a number.
5. Both install scripts — `PLUGIN_KEYS` / `PLUGIN_NAME` in the `.sh`,
   `$script:PluginCatalog` in the `.ps1`.

Four rules that apply to plugins and not to skills:

- **A plugin that registers hooks defaults to OFF in the menu.** A hook is not
  advisory — it runs whether or not Claude agrees with it — so a bootstrap run must not
  add one to someone's machine without the box being ticked.
- **Register each hook once, as bash, and branch inside the script.** There is no
  `shell` field in a `hooks.json` entry - Claude Code does not read one, so a hook
  registered with `shell: powershell` is silently inert, which reads as "the gate
  passed" rather than "the gate never ran". `crew` shipped exactly that bug for a
  release; see `plugin/crew/hooks/scripts/_common.sh` for the working pattern.
  - **Branch on the tool, not the OS.** A hook that judges a *command* (a `PreToolUse`
    guard) must dispatch on `tool_name`: a `Bash` tool call is bash syntax even on
    Windows, and judging it with PowerShell rules gets it wrong in both directions.
  - **A hook that judges no command needs no twin.** It is reached through `bash`, so
    if it runs at all bash is present and can do the work; a `.ps1` beside it is
    unreachable code. Ship one only for someone wiring the hooks in by hand, and say
    in the docs that `hooks.json` does not reference it.
  - **Assume nothing about the interpreter.** Git Bash ships without `python3`. Resolve
    `python3`/`python`/`py` and fail loudly on stderr rather than suppressing the error
    and exiting 0.
- **A hook that can block needs a committed regression suite**, with must-block and
  must-allow cases, and it must be sabotage-tested: reintroduce a bug it should catch
  and confirm the suite goes red. `plugin/crew/hooks/scripts/_test/run-tests.sh` is the
  worked example. Two of `crew`'s guard bugs shipped past code review and were only
  found by running the thing.

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
