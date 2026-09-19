# AGENTS.md

Instructions for Codex CLI, Cursor, Gemini CLI, Copilot CLI, and any other
non-Claude tool working in this repository. Facts, not policy.

## What this repo is

A Claude Code plugin marketplace. `.claude-plugin/marketplace.json` is the
only marketplace file — nothing under a plugin directory should look like a
second one. Two installable unit types: `plugin/<name>/` (full plugin — may
bundle subagents, commands, skills, hooks as bash+PowerShell pairs) and
`skills/<name>/` (single-skill plugin, one `SKILL.md`). `plugin/crew` is
the large one: many agents, commands, skills, and hooks in one plugin.

## How to verify a change

Run in order: `python3 scripts/check-marketplace.py` (the gate — checks
registration completeness, version drift, self-stated numeric claims, and
that each plugin's declared licence matches the repo's `LICENSE`), then
`bash _verify/smoke.sh`, `python3 scripts/_test/self-claims.py`,
`python3 -m pytest plugin/crew/tests/ -q`, and
`python3 -m pylint $(git ls-files '*.py')`. Read the exit code, not the
printed score — pylint can print `10.00/10` and still exit 4 on a warning.

## The rule that bites every change

A content change needs a version bump everywhere that entry's version is
declared, same commit — `claude plugin update` compares the declared
version, not file contents. Full plugins under `plugin/<name>/` bump
`plugin.json` **and** `marketplace.json` **and** `PLUGINS.md`. A
`skills/<name>/` plugin has no `plugin.json` (`check_plugin_manifests()`
skips entries that lack one), so bump only its `marketplace.json` entry and
catalog row. A self-stated number can carry a `<!-- claim: ... -->` marker
`check-marketplace.py` verifies, but only three kinds exist: `skills-count`,
`plugin-skills:<name>`, `plugin-version:<name>` — any other kind (e.g. an
agent count) fails the gate as unimplemented, so leave others unmarked.

## Windows landmines

- `.sh` files must stay LF — a CRLF shebang fails as `bad interpreter: ^M`.
  `git show <rev>:<path>` emits the blob unchanged even under
  `core.autocrlf=true`; CRLF shows up only in the checked-out working tree.
  Measure the blob (`git show <rev>:<path> | tr -cd '\r' | wc -c`, 0 =
  clean) and the worktree (`od -c`/`file`) separately — root `CLAUDE.md`
  currently states this backwards, fixed there separately.
- Git Bash's `/tmp` is invisible to a native Windows Python process.
- `MSYS_NO_PATHCONV=1` is needed for `git show rev:path` in Git Bash — set
  it per-command only; exporting it breaks other tools' `/c/...` resolution.

## What to hunt for in review

The recurring defect shape here is an unknown collapsing into the
safe-looking value: a failed probe reported as pass, an empty result
reported as clean. Example: a config-derived "author family" check declared
its uncertainty once in prose, then printed a bare `BARRED`/`ELIGIBLE` on
every row with no caveat — the uncertainty never reached the derived value.
Prefer "couldn't determine X" over a guess reported as clean.

Claude Code sessions read `CLAUDE.md` at the repo root — the full house
rules and incident history. This file is the short form for other tools.
