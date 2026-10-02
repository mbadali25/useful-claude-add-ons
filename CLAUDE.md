# CLAUDE.md

A Claude Code **marketplace**. Each directory under `skills/` is an installable plugin holding one
`SKILL.md`; each under `plugin/` is a full plugin that may also bundle subagents, commands and
hooks. Both register in `.claude-plugin/marketplace.json` — the root's is the **only** one here.

## Commands - build, test, verify, regression, promote

No build. `python3 scripts/check-marketplace.py` is the gate: every registration rule, both install
scripts being a matched pair, hook quoting and exit codes, and version drift. Commit, then run it,
then push: its version-drift check compares commits, so uncommitted plugin edits pass it locally.
Per-path commands and promotion steps live in `.crew/verify.json` — that file is the mechanism, this
one is the judgment. Do not restate its commands here. A lane runs the whole local suite with
`python3 scripts/gate-runner.py` (one status file, heavy-run aware) instead of its own `suites*.sh`;
its step table is checked against `.github/workflows/` by its own suite.

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

**A number this repo states about itself gets a marker, or it is not checked.** Write
`<!-- claim: skills-count -->` or `<!-- claim: plugin-version:<name> -->` beside it and
`check_self_claims` in `scripts/check-marketplace.py` verifies it against `marketplace.json` or that
plugin's `plugin.json`. The marker binds to the first matching line within 12, so a claim inside a
fenced code block is marked from the line above the fence. Unmarked numbers are deliberately not
checked: `17 skills` is true of crew's bundle and false of the marketplace, and a checker that
guesses which is which fails correct lines. That silence is asserted by
`scripts/_test/self-claims.py`, so do not "improve" the check into inferring claims.

**A change to the review/gate harness lands alone, with no feature work in the same PR.** Owner rule,
2026-09-28 (T-0087). The harness is the set of paths in `HARNESS` in `scripts/check-tooling-pr.py`.
Whenever one of them changes, `.crew/verify.json`'s harness rule runs that checker, its suite
`scripts/_test/tooling-pr.py`, the golden replay of real reviewer output, the seam contracts and
the canary review. Tests, docs, version files, the code map and the graph may ride along. A feature
may not, and neither may production code or a prompt outside the harness. The few files that read a
harness format (`SEAM` in the same script) ride along only when a lane commit declares each with a
`Tooling-seam: <path>` trailer, a claim the reviewer holds the diff to.

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

Two maps, both **in this repo**, both tracked; no Obsidian vault. The history and measurements
behind every rule here are in `docs/claude-md-evidence.md`, "From Memory".

- **`.crew/codemap/`** — the prose map: one file per subsystem, each claim marked DERIVED (with a
  `path:line`) or JUDGEMENT, each file carrying an `anchor:` commit; `INDEX.md` is the contents.
  Refresh with `/crew:onboard --refresh <subsystem>`. Anchor length does not matter (7-40
  characters all compare on their first 7); grep `[:7] == head[:7]` rather than trusting a line
  number for where that happens.
- **`graphify-out/graph.json` and `graphify-out/GRAPH_REPORT.md`** — the mechanical graph, both
  tracked. **`graphify update .` owns the pair** (decided 2026-09-12). A hand-run
  `graphify . --no-viz --code-only` writes `graph.json` alone and does not reproduce what is in git;
  if you run it anyway, follow with `graphify cluster-only .` and compare the report's `## Summary`
  with the graph's `nodes` / `links` (**`links`, not `edges`**) before committing.
- **A background rebuild starts on every commit, checkout and pull** (log:
  `~/.cache/graphify-rebuild.log`) and will overwrite a build you are measuring. Wait for the log to
  stop growing first.
- **The user's global `~/.claude/CLAUDE.md` names the other graphify command on purpose** — its
  "Project `CLAUDE.md` overrides" clause is the mechanism. **Do not reconcile the two files.**

An `anchor:` behind HEAD means *re-check the claims*, not that they are wrong. Do the per-path check
first — `git diff --name-only <anchor>..HEAD -- <paths the map documents>` — because a repo-wide
version bump moves every anchor without invalidating a word. Empty output means current despite the
lag. The same comparison for `graphify-out/` and `docs/diagrams/` can never come out current: they
are tracked, so committing one advances HEAD past the sha it records.

<!-- crew-ignore-policy:list -->
Decisions in `docs/adr/`. The gitignore policy for the rest, stated once: `.crew/*` is ignored
and a **named** list is un-ignored — `!.crew/codemap/`, `!.crew/endpoints.json`,
`!.crew/verify.json`, `!.crew/standards.md`. Nothing else under `.crew/` is tracked, `.work/` is
ignored entirely, and `.crew/.approved-*` is listed too, as documentation of the promotion approval
marker **the operator creates** — `.crew/*` already ignores it and no negation re-admits it, so that
line and its position are not what keeps it untracked.
`scripts/check-marketplace.py::check_crew_ignore_policy` asserts that list is the same set here, in
crew-setup's shipped template, and in every doc that states it — so change the list in one place and
the gate tells you the other places exist.

## Landmines - every one of these has already shipped broken

The incident and evidence behind each are in `docs/claude-md-evidence.md`, "From Landmines".

- **`pwsh` is not on Git Bash's PATH here.** Name it absolutely. A bare `pwsh` fails as "command
  not found" and the gate reports that as a *failed check*, not a missing tool.
- **Git Bash ships without `python3`.** Resolve `python3`/`python`/`py` and fail loudly on stderr
  rather than suppressing the error and exiting 0.
- **A bare hook `command` goes to Git Bash on Windows**, not PowerShell — set `shell: "powershell"`
  and register each event once per flavour.
- **Branch on the tool, not the OS.** A `Bash` call is bash syntax even on Windows. A `.ps1` that
  `hooks.json` never references is dead code.
- **Nothing may bypass `pick_fit` / `Format-PickerLine`.** A line that *wraps* throws off the
  cursor-up redraw count and smears the menu over what was above it.
- **Both install scripts are idempotent** — a new step needs a detection branch reporting "already
  installed".
- **`open(p, "w")` truncates at open time, before the payload exists.** Compute the full text into
  a variable, then open — or write a temp file and `os.replace` it. `pathlib.write_text(expr)` is
  not this trap; the `with open(...) as fh:` form is. Repair with `git checkout --`. The per-site
  audit, and the one live site to re-check first, are in the evidence file.
- **`pathlib.write_text` converts a `.sh` to CRLF on Windows** — pass `newline="\n"`.
  `.gitattributes` does not save you, and with `core.autocrlf=true` `git show` renders CRLF
  whatever the blob holds; measure the worktree with `od -c` or `file`(1). Repair with
  `git checkout -- <path>`.

Skills follow `Skill-Authoring-Standard.md`; changes follow `Skill-Pipeline.md`.

## Lessons - each one cost real time here, more than once

Stated as rules. The incident that earned each one, and the review history of this section, are
in `docs/claude-md-evidence.md`, "From Lessons". That history's own lesson applies to every line
below: claims outrun their evidence, so get a reader who did not write yours.

- **An unknown must not collapse into the safe-looking value.** Where a probe can fail, "could not
  tell" is its own value and survives into every line derived from it.
- **Re-review the fix to a guard as hard as the guard**, and check the neighbouring case before
  closing it.
- **Put the check where the evidence is dropped** — in the code that reads it, not in prose the
  parser never reads.
- **A failing gate names the failure, not the cause.** Read the status and check the artifact, not
  the summary, and name the environment a failure needs (e.g. `MSYS_NO_PATHCONV=1`).
- **Run the states; do not reason about them.** Check what you changed about the measurement before
  reporting a regression.
- **Attach the ref and the layer to every measurement** — which branch, and which of
  `.crew/config.json` / `~/.claude/crew/config.json`.
- **Check `ListAgents` before assuming a diff, a branch, or a dirty tree is yours.**
- **Write anchors repo-relative** — a full path from the repo root, so it pastes straight into
  `git diff --name-only <anchor>..HEAD -- <paths>`.
- **A self-referential count changes itself.** State the invariant and how to re-measure instead.
