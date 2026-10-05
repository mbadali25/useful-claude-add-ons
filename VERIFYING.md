# Verifying a change

How to prove a change in this repository works, for people and for any AI agent (Claude Code, Codex,
or anything else that can run a shell). Every command runs from the repository root.

`AGENTS.md`'s "How to verify a change" has the deeper detail on the pytest sets and the CI jobs;
`CLAUDE.md` has the rules these commands enforce. This page is the map.

## Which layers do I need?

| You are about to... | Run layers |
|---|---|
| have committed anything | 1, 2, then the rules layer 3 maps your paths to |
| ask for review, or land | 1-3, with layer 3 as `--all` (or a CI receipt, layer 7) |
| push a lane branch | 1-5 |
| promote | 1-5, then `/crew:promote` |

## The minimum, for every change

```bash
git commit ...                          # first: the version-drift check compares COMMITS
python3 scripts/check-marketplace.py    # layer 1; exit 0 = pass
bash _verify/smoke.sh                   # layer 2; exit 0 = safe to merge
```

A plugin change with no `version` bump fails layer 1 after you commit, and that failure is real:
`claude plugin update` compares versions, so an unbumped change never reaches anyone who already
installed the plugin. `AGENTS.md` lists the full local sequence, which adds
`scripts/_test/self-claims.py`, the `crew` default pytest set and pylint.

## The layers

| # | Layer | Command | When | Cost |
|---|---|---|---|---|
| 1 | Marketplace gate | `python3 scripts/check-marketplace.py` | every commit, after committing | seconds |
| 2 | Smoke | `bash _verify/smoke.sh` | every change | about 15 s, capped at 90 s |
| 3 | Verify gate | `bash plugin/crew/hooks/scripts/verify-gate.sh --all < /dev/null` | before review or landing | 17-20 min for the whole map |
| 4 | Local CI suite | `python3 scripts/gate-runner.py` | before pushing a lane | the longest local run; `--list` shows the steps |
| 5 | Regression | `bash _verify/run-all.sh` | before pushing; before a promotion | minutes |
| 6 | CI | `.github/workflows/` | every pull request, and every push to `main` | runs on GitHub |
| 7 | CI receipt | `python3 plugin/crew/hooks/scripts/ci_receipt.py check --root .` | to reuse a CI gate run for HEAD | needs `gh` |

Layer 4 runs what CI runs on a pull request; layer 5 is `_verify/`'s own deeper suite (smoke's
registration checks plus the version-drift walk and the full install-script contracts). They
overlap; neither replaces the other.

### 1-2. Marketplace gate and smoke

Both are fast enough to run on every change. `_verify/README.md` lists what smoke covers and the
sabotage that proved each check can fail.

### 3. The verify gate

`.crew/verify.json` maps path globs to the commands a change to those paths requires. Each rule has
`paths`, `run`, a measured `seconds`, a `reach` (`local`, `network` or `host`) and a `why`.

| How it runs | What it checks |
|---|---|
| Automatically at the end of every Claude Code turn, with the `crew` plugin enabled | only the rules your changed paths match, within a 60 s budget |
| `/crew:verify --all` inside Claude Code | the whole map, no budget |
| `bash plugin/crew/hooks/scripts/verify-gate.sh --all < /dev/null` anywhere else | the same |
| `plugin/crew/hooks/scripts/verify-gate.ps1 -All` | the same, on native Windows PowerShell |

- Exit 2 means the work is not done.
- `NOT VERIFIED ON THIS TREE` or `deferred` is not a pass, even with exit 0.
- Run it by hand with `--all`. Without it, the gate behaves as the Stop hook does: it runs the
  cheapest matched rules first, defers whatever does not fit the 60 s budget, and skips `network`
  and `host` rules.
- **An agent must run `--all` in the background.** It takes longer than a foreground tool call is
  allowed to, and on a shared box with a 6G memory cap it can be killed. Read its output when it
  ends, or use a CI receipt (layer 7) instead.

### 4. The local CI suite

`python3 scripts/gate-runner.py --list` prints what it would run; without `--list` it runs it and
writes one status file (the path is printed). States are PASS, FAIL, SKIP (exit 77 or a missing
tool, which is NOT VERIFIED) and COULD-NOT-TELL. `--check-ci` reports whether its table still
matches `.github/workflows/`.

### 5. Regression

`bash _verify/run-all.sh`: the same registration checks as smoke, plus the checks too slow for it.
`claude plugin validate --strict` runs in smoke only.

### 6-7. CI and receipts

- A pull request starts one workflow, `.github/workflows/ci.yml`. Its first job routes the PR's
  changed files (`scripts/ci-route.py`); the marketplace and instruction-budget workflows always
  run, and the crew, shell, MCP and pylint workflows run only when their files changed. `CI gate`,
  the one required check, fails unless every routed workflow ran and passed. An unknown path, a
  failed diff or any `.github/` change runs everything. Pushes to `main` and the nightly schedule
  run every workflow in full. The `crew` suite is `.github/workflows/pytest-crew.yml`.
- A push to an `L-*`, `T-*` or `W-*` branch also runs the whole verify gate on the self-hosted
  runners (`.github/workflows/verify-gate.yml`) and uploads a receipt. That job runs only in this
  repository and only while the repo variable `CREW_RUNNER` is `self-hosted`.
- `ci_receipt.py check` accepts a receipt only when it matches HEAD's commit, tree and `verify.json`
  exactly, and never for a branch that changed the gate or the receipt code itself (it would vouch
  for itself).
- `/crew:review` and `/crew:done` accept a receipt in place of a local `--all`.

## Test suites, directly

| Set | Command |
|---|---|
| `crew` default set | `python3 -m pytest plugin/crew/tests/ -q` |
| `crew` per-shell matrix | `python3 -m pytest plugin/crew/tests -m slow` |
| `crew` wall-clock tests, serially (no `-n`) | `python3 -m pytest plugin/crew/tests -m wallclock` |
| Mutation (sabotage) suite | `python3 plugin/crew/tests/sabotage.py` |
| Marketplace checker suites | `python3 scripts/_test/<name>.py` |

The sabotage suite edits real source files in place and restores them. Run it on a clean tree with
nothing else running.

## What no automated layer runs

| Gap | What to do |
|---|---|
| `scripts/_test/drift-detection.sh` drives the real `claude` CLI | run it by hand before pushing a change to the plugin update path |
| README install URLs are pinned to a commit | after merging a change to `scripts/install-prerequisites.sh` or `scripts/install-prerequisites.ps1`, re-pin both to the new SHA |
| `.ps1` test cases skip where `pwsh` is not installed, and some run only on native Windows | say which were skipped; CI's Windows jobs run them |
| A live review round, a real `/crew:promote` | not reproducible in CI; say they did not run |

## Reporting a result

- Quote a failure verbatim. Never summarise a stack trace.
- Name what ran and what did not. A SKIP, a deferred rule and a skipped test are not passes.
- Attach the ref: which commit, and whether the tree was clean.

<!-- Every repository path named in this file must exist: scripts/check-marketplace.py
     (check_verifying_doc) fails otherwise. -->
