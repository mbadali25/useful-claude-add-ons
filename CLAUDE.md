# CLAUDE.md

A Claude Code **marketplace**. Each directory under `skills/` is an installable plugin holding one
`SKILL.md`; each under `plugin/` is a full plugin that may also bundle subagents, commands and
hooks. Both register in `.claude-plugin/marketplace.json` — the root's is the **only** one here.

## Commands - build, test, verify, regression, promote

No build. `python3 scripts/check-marketplace.py` is the gate: every registration rule, both install
scripts being a matched pair, hook quoting and exit codes, and version drift. Run it before pushing.
Per-path commands and promotion steps live in `.crew/verify.json` — that file is the mechanism, this
one is the judgment. Do not restate its commands here.

## Where things are - entrypoints, logic, DO NOT TOUCH

- `scripts/install-prerequisites.{sh,ps1}` — a matched pair. Change one, change the other.
- `scripts/_test/`, `plugin/crew/hooks/scripts/_test/` — the suites. Each builds throwaway fixtures
  and must never touch real config or install anything.
- `graphify-out/`, `node_modules/` — generated. Do not hand-edit.

## Scope discipline - fix the ticket, not what you notice nearby

Registering an entry means updating **every** place in the same commit — marketplace entry, catalog
row, `plugin/PLUGINS.md` for plugins, and both install scripts in the same order with the same text.
A partial registration is worse than none: the checker fails and nobody can tell which half was
intended. Renaming or removing means the same places, in reverse.

## Stop and ask - the conditions that should halt work

- **Content change with no `version` bump.** `claude plugin update` compares the *declared version*,
  not contents. Ship without the bump and every machine that already installed it keeps the old copy
  forever, reporting "already at the latest version". Nothing in the repo looks wrong; the bug
  exists only on other people's machines. A plugin with its own `plugin.json` bumps in both.
- **Adding a hook.** It runs whether or not Claude agrees with it, so a plugin registering one
  **defaults to OFF in the menu**. One that can *block* needs a committed regression suite with
  must-block and must-allow cases, sabotage-tested: reintroduce a bug it should catch and confirm
  the suite goes red. Two of `crew`'s guard bugs shipped past review and were caught only by that.
- **A `marketplace.json` inside a plugin directory** (makes it look like a second marketplace), or
  **deleting or renaming a registered entry.** Ask first.

## Promotion: development -> qa -> production

Nothing is deployed; "production" means merged to `main` and installable. Two steps no script
enforces: `scripts/_test/drift-detection.sh` drives the real `claude` CLI so CI cannot run it — run
it by hand before pushing a change to the plugin update path; and the README's install URLs are
**pinned to a commit SHA** — after merging a change to either install script, `git rev-parse HEAD`
and re-pin both.

## Reporting - errors verbatim, say what you did NOT verify

Quote failures exactly; never summarise a stack trace. Name which suites ran and which did not.
`drift-detection.sh` is skipped by default — say so rather than implying the gate is green.

## Memory - where the code map and runbooks live

`graphify-out/graph.json`, exported to the `claude-memories-codegraphs` vault under
`personal/useful-claude-add-ons`; refresh with `graphify . --no-viz --code-only`. Decisions in
`docs/adr/`; crew state in `.crew/`.

## Landmines - every one of these has already shipped broken

- **`pwsh` is not on Git Bash's PATH here.** Name it absolutely. A bare `pwsh` fails as "command
  not found" and the gate reports that as a *failed check*, not a missing tool.
- **Git Bash ships without `python3`.** Resolve `python3`/`python`/`py` and fail loudly on stderr
  rather than suppressing the error and exiting 0.
- **A bare hook `command` goes to Git Bash on Windows**, not PowerShell — set `shell: "powershell"`
  and register each event once per flavour. `crew` shipped a release where the guard stood down on
  Windows instead, so it blocked nothing there.
- **Branch on the tool, not the OS.** A `Bash` call is bash syntax even on Windows; PowerShell rules
  get it wrong both ways. A `.ps1` that `hooks.json` never references is dead code.
- **Nothing may bypass `pick_fit` / `Format-PickerLine`.** Clipping is degradation; a line that
  *wraps* throws off the cursor-up redraw count and smears the menu over what was above it.
- **Both install scripts are idempotent** — a new step needs a detection branch reporting "already
  installed".
- **`pathlib.write_text` converts a `.sh` to CRLF on Windows** — it is text mode, so every `\n`
  becomes `\r\n` and the script dies on its shebang as `bad interpreter: ...^M`. Pass
  `newline="\n"`. `.gitattributes`' `*.sh text eol=lf` does *not* save you: it governs what git
  stores and what a checkout produces, and the damage lands after checkout, in the working tree
  bash actually executes. Worse, the obvious check lies — with `core.autocrlf=true`,
  `git show <rev>:<path>` renders CRLF whatever the blob holds, so grepping its output reports the
  same count for a clean file and a broken one. Measure the worktree with `od -c` or `file`(1).
  Repair with `git checkout -- <path>`, then confirm the same way.

Skills follow `Skill-Authoring-Standard.md`; changes follow `Skill-Pipeline.md`.
