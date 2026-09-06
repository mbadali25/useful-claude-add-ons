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

Two maps, both **in this repo**, both tracked. No Obsidian vault — the graph used to be exported to
one, which meant the map lived on one machine and reached nobody who cloned.

- **`.crew/codemap/`** — the prose map: one file per subsystem, every claim marked DERIVED (with a
  `path:line` to re-check) or JUDGEMENT, each carrying an `anchor:` commit. `INDEX.md` is the table
  of contents. Refresh with `/crew:onboard --refresh <subsystem>`. Anchor length does not matter:
  `_ANCHOR_RE` accepts 7-40 and `crew_state.py:421` compares `found.group(1)[:7] != head[:7]`,
  truncating **both** sides, so 8 and 40-char anchors match exactly as well as 7. (This line
  previously warned that an 8-char anchor "parses fine and then never matches". It was wrong,
  and wrong in the expensive direction — it sends you rewriting correct anchors and distrusting
  working ones. Corrected 2026-09-05 by reading the comparison.)
- **`graphify-out/graph.json`** — the mechanical graph. Refresh with `graphify . --no-viz
  --code-only`; a post-commit hook does it automatically.

An `anchor:` behind HEAD means *re-check the claims*, not that they are wrong. Do the per-path check
first — `git diff --name-only <anchor>..HEAD -- <paths the map documents>` — because a repo-wide
version bump moves every anchor without invalidating a word. Empty output means current despite the
lag. The same comparison for `graphify-out/` and `docs/diagrams/` can never come out current: they
are tracked, so committing one advances HEAD past the sha it records.

Decisions in `docs/adr/`; the rest of `.crew/` is machine-local and stays ignored.

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

## Lessons - each one cost real time here, more than once

Recovered 2026-09-05. These existed only as an uncommitted local edit that a CLAUDE.md rewrite
overwrote, so they survived in nothing tracked and were then cited twice, at two other sessions, as
this file's policy — while living in no commit at all. Every one below carries the evidence that
earned it, precisely so nobody has to take it on faith the way those citations asked people to.

- **The recurring bug is an unknown collapsing into the safe-looking value.** Not a wrong answer —
  a *missing* answer wearing the label of a check that happened. `crew_config.py --models` derives
  "author family" from config describing the NEXT run, and on a Claude-authored diff barred Codex,
  the only independent reviewer, while clearing Claude. It declares that uncertainty once in prose
  and then prints `BARRED` / `ELIGIBLE` with no caveat on any row drawn from it. Where a probe can
  fail, "could not tell" has to be its own value that survives into every line derived from it, or
  the guard fails open while looking like it checked.

- **A guard is usually wrong again in the fix for the last time it was wrong.** Seven consecutive
  review rounds on `vault_guard.py`, each fix right about the case it aimed at and one rung short
  of its neighbour: frontmatter, then ASCII, then the three config defaults, then the comment
  justifying the interpreter stand-down, then a count corrected in one of the two places that
  stated it. Fixes to a guard need *more* adversarial reading than the original, not less.

- **Put the check where the evidence is dropped.** `read_metrics` averages BLOCK+FIX per *row* and
  returns that count under the key `tickets`, so one ticket reviewed twice reads as two and the
  health signal recommends "cut ticket scope" on a 90-line docs diff. `cells[1]` — the ticket
  column, filled in by every row — is never referenced. A correction written in prose beneath the
  table fixed nothing, because the parser never reads prose.

- **Judge every gate by exit code, and read what it actually printed.** `render.sh` prints a
  summary line and creates its output directory while exiting 1 and rendering nothing; its six
  `FAIL` lines were a `/tmp` path a Windows `mmdc` cannot open, not broken Mermaid. An
  exit-code-only check would have passed it; a log-only read would have sent someone editing
  correct diagrams.

- **Run the states; do not reason about them.** A guard suite reported 24 passed / 33 failed, and
  the cause was `MSYS_NO_PATHCONV=1` in the *runner's* environment mangling `/c/repos/...` into
  `C:\c\repos\...`. Settled tree, same commit: 65/0. Check what you changed about the measurement
  before reporting a regression.

- **Attach the ref and the layer to every measurement.** "The suite passes 65/0 on main" was false
  — the shared worktree was on another session's branch and `main` ran 57. Two agents disagreed
  about `dev.provider` for an hour because one read `.crew/config.json` and the other
  `~/.claude/crew/config.json`, and neither named which. A number without its ref can only be
  believed, not checked.

- **Check `ListAgents` before assuming a diff, a branch, or a dirty tree is yours.** Three sessions
  worked this repo in one night; the checkout was switched under a running measurement, and commits
  appeared on `main` from elsewhere mid-task.

- **Write anchors repo-relative.** Write `plugin/localgpu/mcp/config.py:99`, never a bare
  `config.py` with a line number after it. The bare form resolves by eye and cannot be pasted into
  `git diff --name-only <anchor>..HEAD -- <paths>`, which is the entire re-verification mechanism.
  60 were in that shape — 30 in the codemap, 30 more inside the diagrams. The bad form is described
  rather than shown here on purpose: a checker walking these citations cannot tell a counter-example
  from a broken one, and would report this section as containing an unresolvable anchor forever.

- **A self-referential count changes itself.** Recording "87 anchors" in a note took the total to
  88, and the commit correcting the figure took it to 89. State the invariant and how to
  re-measure instead; a number wrong by one is worse than no number, because it looks measured.
