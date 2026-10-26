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

`VERIFYING.md` is the map: every layer, its command, when to run it and what
no automated layer runs. The detail on the pytest sets and CI jobs is below.

Run in order: `python3 scripts/check-marketplace.py` (the gate — checks
registration completeness, version drift, self-stated numeric claims, and
that each plugin's declared licence matches the repo's `LICENSE`), then
`bash _verify/smoke.sh`, `python3 scripts/_test/self-claims.py`,
`python3 -m pytest plugin/crew/tests/ -q`, and
`python3 -m pylint $(git ls-files '*.py')`. Read the exit code, not the
printed score — pylint can print `10.00/10` and still exit 4 on a warning.

`python3 -m pytest plugin/crew/tests/ -q` is the DEFAULT set, not the whole
suite: `plugin/crew/tests/conftest.py` deselects everything marked `slow`
(the full per-shell `bash`/`pwsh` driver matrix for a hook) unless asked
for, and it deselects a lot — `--collect-only -q` on that same command
prints how many. What is left is a per-shell PARITY SAMPLE (one case per
decision, per flavour) plus the full python-driven decision table, which is
what most local runs and most changes need. To run the full matrix too, use
`python3 -m pytest plugin/crew/tests -m slow` (only the slow set) or
`--run-slow` (everything, slow and default together) — see
`plugin/crew/tests/conftest.py`'s own header comment for the three forms.

The two CI jobs in `.github/workflows/pytest-crew.yml` split the same way:
the `test` job runs the DEFAULT command above (no `-m`, no `--run-slow`),
on `ubuntu-latest` across three Python versions on main pushes, manual dispatch and
the nightly schedule (on a pull request only the 3.12 leg does work; 3.11 and 3.13
report a skipped pass so the required check names stay satisfied; the nightly runs
at 07:17 UTC; a newer push to a pull request cancels its older run, and a main run
is never cancelled), alongside
gizmoduck's and several skills' suites. Since L-0590 the default set there runs
`-n 16 --dist worksteal` (then `-m wallclock` serially, as before), and on every event but a
pull request the three Python legs run one at a time (`max-parallel` 1), so a main push no
longer puts three Python legs on the one self-hosted host at once. The `crew-shell-matrix` job
runs `-m slow` (`-n 8`)
on `ubuntu-latest` — the full hook matrix the `test` job deselects. On Windows the
same suite runs as parallel `crew-windows-*` jobs (L-0577): the plain default
command split in six by pytest-split (L-1506; `test` already covers that set, but only
on ubuntu, so the PowerShell parity-sample cases run natively nowhere else), `-m slow`
split in three the same way (L-1507), and `-m wallclock` serially in one job. Their
fan-in, `crew-windows-gate`, carries the required check name
`crew-shell-matrix (windows-latest)` and passes only when every Windows job succeeded
and `scripts/check-windows-shards.py` finds every collected default test, and every
collected slow test, in exactly one of its set's shards' JUnit. On a pull request the Windows jobs do work only when the PR
changes `plugin/crew/**` or `pytest-crew.yml` (T-0110), and otherwise the gate reports
a skipped pass. Neither job substitutes for the other: a change to `conftest.py`'s
slow-marker logic, or to a hook only the matrix exercises, can pass one and still be wrong.

Both jobs' `ubuntu-latest` placement is the default, not a fixed fact: when the
repo variable `CREW_RUNNER` is `self-hosted`, the `test` job and the
`crew-shell-matrix` ubuntu leg run on the owner's self-hosted pool
(`[self-hosted, linux, x64, crew]`) instead; the `windows-latest` jobs and every
other job and workflow stay GitHub-hosted. Fork pull requests never reach the
pool: this repo is public, so only non-PR events (push, schedule, manual
dispatch) and pull requests from branches of this repo use it. The owner's runner playbook
(mbadali25/github-runner-infra) sets the variable on `make up` and unsets it on
`make down`, so required checks never wait on a torn-down pool. Unset, nothing
changes.

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

<!-- crew-standards-export start digest=df6052ac0825389b086b6ca038d9f2c0e191ea1a5407dee8f55424f8dff3a8e6 crew=1.2.86 -->
## Code Review Rules

Every standard crew applies in review is written out in `docs/review-rules/`, one file per set, each stating the files it applies to.
Check a change against the standards whose scope matches the files it touches. The always-on standards are also written out in full in `REVIEW.md`.

- GEN-01 Unknown stays unknown: [docs/review-rules/GEN.md](docs/review-rules/GEN.md)
- GEN-02 Shared files change atomically: [docs/review-rules/GEN.md](docs/review-rules/GEN.md)
- GEN-03 The irreversible action carries what was checked: [docs/review-rules/GEN.md](docs/review-rules/GEN.md)
- GEN-04 Every behaviour has a control that fails, in both directions: [docs/review-rules/GEN.md](docs/review-rules/GEN.md)
- GEN-05 Recognise a narrow allowlist; everything else is could-not-tell: [docs/review-rules/GEN.md](docs/review-rules/GEN.md)
- GEN-06 Hostile text and paths are neutralised at the sink: [docs/review-rules/GEN.md](docs/review-rules/GEN.md)
- GEN-07 One validated contract between producer and consumer: [docs/review-rules/GEN.md](docs/review-rules/GEN.md)
- GEN-08 Portable across Windows and POSIX: [docs/review-rules/GEN.md](docs/review-rules/GEN.md)
- GEN-09 What the change says is true at this commit: [docs/review-rules/GEN.md](docs/review-rules/GEN.md)
- GEN-10 External behaviour is measured, not assumed: [docs/review-rules/GEN.md](docs/review-rules/GEN.md)
- GEN-11 Named requirements hold on every path: [docs/review-rules/GEN.md](docs/review-rules/GEN.md)
- GEN-12 Verification evidence matches the final HEAD: [docs/review-rules/GEN.md](docs/review-rules/GEN.md)
- PWSH-16 An external program is resolved to an Application that is proven to run, never to whatever name lookup returns first: [docs/review-rules/PWSH.md](docs/review-rules/PWSH.md)
- PYTHON-01 Every text open and decode states its encoding, error handler and newline: [docs/review-rules/PYTHON.md](docs/review-rules/PYTHON.md)
- PYTHON-03 Records split on the separator the protocol defines, and one-line output is one line: [docs/review-rules/PYTHON.md](docs/review-rules/PYTHON.md)
- PYTHON-04 A file someone else reads is replaced, never rewritten in place: [docs/review-rules/PYTHON.md](docs/review-rules/PYTHON.md)
- PYTHON-06 Launch a child as an argv list, by a resolved path, through an interpreter Windows can run: [docs/review-rules/PYTHON.md](docs/review-rules/PYTHON.md)
- PYTHON-07 Every wait has a bound, and the bound uses a clock that cannot go backwards: [docs/review-rules/PYTHON.md](docs/review-rules/PYTHON.md)
- PYTHON-08 A child process gets a constructed environment and an explicit home: [docs/review-rules/PYTHON.md](docs/review-rules/PYTHON.md)
- PYTHON-10 Parsed JSON and TOML are checked for shape before they are indexed, hashed, joined or sorted: [docs/review-rules/PYTHON.md](docs/review-rules/PYTHON.md)
- PYTHON-11 The `try` body is the one call whose failure is being classified: [docs/review-rules/PYTHON.md](docs/review-rules/PYTHON.md)
- PYTHON-13 Paths are compared and contained only after canonicalisation, and junctions count: [docs/review-rules/PYTHON.md](docs/review-rules/PYTHON.md)
- REPO-01 Identity is complete, canonical and proven: [docs/review-rules/REPO.md](docs/review-rules/REPO.md)
- REPO-02 A change detector sees every write channel: [docs/review-rules/REPO.md](docs/review-rules/REPO.md)
- REPO-03 Release bookkeeping for this marketplace: [docs/review-rules/REPO.md](docs/review-rules/REPO.md)
<!-- crew-standards-export end -->
