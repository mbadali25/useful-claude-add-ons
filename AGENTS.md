# AGENTS.md

Instructions for Codex CLI, Cursor, Gemini CLI, Copilot CLI, and any other
non-Claude tool working in this repository. Facts, not policy.

## What this repo is

A Claude Code plugin marketplace. `.claude-plugin/marketplace.json` is the
only marketplace file — nothing under a plugin directory should look like a
second one. Two installable unit types: `plugin/<name>/` (a full plugin —
may bundle subagents, commands, skills, and hooks as bash + PowerShell
pairs) and `skills/<name>/` (a single-skill plugin, one `SKILL.md`).
`plugin/crew` is the large one: many agents, commands, skills, and hooks
under one plugin.

## How to verify a change

Run in order: `python3 scripts/check-marketplace.py` (the gate — checks
registration completeness, version drift, self-stated numeric claims, and
that each plugin's declared licence matches the repo's `LICENSE`), then
`bash _verify/smoke.sh`, `python3 scripts/_test/self-claims.py`,
`python3 -m pytest plugin/crew/tests/ -q`, and
`python3 -m pylint $(git ls-files '*.py')`. Read the exit code, not the
printed score — pylint can print `10.00/10` and still exit 4 on a warning.

## The rule that bites every change

A content change under `plugin/*` or `skills/*` needs a version bump in that
plugin's `plugin.json` **and** its `marketplace.json` entry **and** its
`PLUGINS.md`/catalog row, all in the same commit — `claude plugin update`
compares the declared version, not file contents, so a missed bump means
installed copies silently never update. Any number the repo states about
itself (a skill count, a plugin's version) is expected to carry a
`<!-- claim: ... -->` marker next to it, which `check-marketplace.py`
verifies against the manifests; don't add a count with no marker.

## Windows landmines

- `.sh` files must stay LF — a CRLF shebang fails as `bad interpreter: ^M`.
  `git show <rev>:<path>` lies about this under `core.autocrlf=true` (always
  renders CRLF), so check the working-tree bytes directly (`od -c`/`file`).
- Git Bash's `/tmp` is invisible to a native Windows Python process.
- `MSYS_NO_PATHCONV=1` is needed for `git show rev:path`-style commands in
  Git Bash, but set it per-command only — exporting it breaks other tools'
  `/c/...`-style path resolution.

## What to hunt for in review

The recurring defect shape here is an unknown collapsing into the
safe-looking value: a failed probe reported as pass, an empty result
reported as clean. Example: a config-derived "author family" check declared
its own uncertainty once in prose, then printed a bare `BARRED`/`ELIGIBLE`
on every row with no caveat — the uncertainty never reached the derived
value. Prefer "couldn't determine X" over a guess reported as clean.

## More detail

Claude Code sessions read `CLAUDE.md` at the repo root, which holds the full
house rules and incident history. This file is the short form for tools
that don't read that one.
