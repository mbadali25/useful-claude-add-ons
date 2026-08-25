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
claiming the plugin is current. The suites for all of this live in `scripts/_test/`:

| Script | Covers | Needs |
|---|---|---|
| `scripts/check-marketplace.py` | every registration rule here, version drift, and the two install scripts being a matched pair | python3, git |
| `scripts/check-powershell.ps1` | the `.ps1` parses **and** every `Verb-Noun` call resolves | pwsh |
| `scripts/_test/drift-detection.sh` | the plugin update path, against a throwaway marketplace | the `claude` CLI |
| `scripts/_test/menu-groups.sh` | the sub-picker catalogs, `--<group>` flags, parent implication, and once-per-marketplace registration | bash |

All but the drift suite run in CI (`.github/workflows/marketplace.yml`). That one drives
the real Claude Code CLI, which a runner does not have, so run it by hand before pushing
a change to the plugin update path. Every suite builds throwaway fixtures, uses
`--dry-run` or a stub `claude`, and never touches the real config or installs anything.

`check-powershell.ps1` exists because the `.ps1` is Windows-only end to end: a call to a
function that does not exist parses cleanly, is never reached on Linux, and dies on the
one platform that matters. That is not hypothetical - a mis-named picker call shipped
exactly that way and killed every sub-picker on Windows.

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

Three rules that apply to plugins and not to skills:

- **A plugin that registers hooks defaults to OFF in the menu.** A hook is not
  advisory — it runs whether or not Claude agrees with it — so a bootstrap run must not
  add one to someone's machine without the box being ticked.
- **Think about the shell before registering a hook.** A `hooks.json` entry's
  `shell` field (`"bash"` or `"powershell"`) is documented and Claude Code does read
  it: setting `"powershell"` runs that entry via PowerShell on Windows, without
  needing `CLAUDE_CODE_USE_POWERSHELL_TOOL`, since hooks spawn the interpreter
  directly. `crew` shipped a release where the guard stood down on Windows instead of
  being registered this way, so the command guard blocked nothing there — see
  `plugin/crew/hooks/hooks.json` and `plugin/crew/hooks/scripts/_common.sh` for the
  fixed pattern: each event registered once per flavour, `shell: powershell` on the
  PowerShell side.
  - **What is not configurable is the shell form's default.** A bare `command`
    string (no `args`) is passed to a shell: `sh -c` on macOS/Linux, **Git Bash** on
    Windows, or PowerShell only when Git Bash isn't installed. A `bash` resolved from
    some non-MSYS parent process is not necessarily what actually runs it — verify on
    the machine you're targeting rather than assuming.
  - **Branch on the tool, not the OS.** A hook that judges a *command* (a `PreToolUse`
    guard) must dispatch on `tool_name`, either via separate matchers per tool (each
    with its matching `shell` field) or from inside one script to its twin: a `Bash`
    tool call is bash syntax even on Windows, and judging it with PowerShell rules
    gets it wrong in both directions.
  - **A hook that judges no command still needs a real answer for both shells** —
    either register both flavours (one is expected to fail on a given machine, which
    is fine) or dispatch from inside a single registered script. A `.ps1` sitting on
    disk that `hooks.json` never references is dead code either way.
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
