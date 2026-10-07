# Harness standard

What a repo's test-and-lint harness must do so QA is fast, cheap and honest. Each rule carries
the evidence that earned it (measured in this marketplace, crew 1.0.62-1.0.64, 2026-09-29) and
how to check and apply it. `qa_audit.py` checks the rules marked **[audited]**; the rest need a
reader.

## H1 — Measure before you optimise

Time each stage before changing it, and write the number down where the harness reads it
(`seconds` on each `.crew/verify.json` rule). Re-time rather than trust a recorded figure.

- **Evidence.** The crew suite ran 923s serially while holding one core at ~33%: it was
  waiting on subprocesses, not computing. That one observation predicted the 3.3x that
  parallelism then delivered. Without it, "make the tests faster" gets you rewrites.
- **Check.** Run the suite once serially with `--durations=40` and note CPU time vs wall time.
  CPU far below wall means wait-bound, so parallelism pays. CPU near wall means the tests
  themselves are slow, so profile before anything else.

## H2 — Parallelise a wait-bound test runner [audited]

| Stack | How |
|---|---|
| Python | `pytest-xdist`, `-n auto`, in CI and the local full-suite rule; fall back to serial when `xdist` does not import |
| PHP | `paratest` in place of `phpunit` |
| .NET | `dotnet test` runs assemblies in parallel; xUnit parallelises collections by default |
| Java | JUnit 5 `junit.jupiter.execution.parallel.enabled=true`; Gradle `maxParallelForks`; Maven `-T 1C` |

- **Evidence.** 923s → 281s at `-n 4`, same 6393 passed.
- **Not for small suites.** Worker start-up costs more than a small suite runs for: 137 tests
  took 0.57s serially and 0.9s under `-n 4`; 31 took 0.45s and 1.97s. The audit treats a
  serial suite under 200 test functions as correct. That's a heuristic from those two
  measurements, so re-measure yours.
- **Apply.** Run the whole suite under the parallel runner once **before** enabling it in CI.
  Any test that fails only in parallel is an isolation bug (H4) or a wall-clock test (H3), and
  both have their own fix. None of them is a reason to skip the test.

## H3 — Wall-clock-bounded tests run serially [audited]

A test asserting elapsed time against a **real** bound (a hook timeout, a probe deadline) gets
a marker and runs after the parallel pass, on its own. Never loosen the bound: it is the real
limit the test protects.

- Python: register `wallclock` in `conftest.py`; run `-n auto -m "not wallclock"`, then
  `-m wallclock`. JUnit 5: `@Isolated` or `@Execution(SAME_THREAD)`. xUnit: a collection with
  `DisableParallelization = true`.
- **Evidence.** Under `-n auto` in CI, `ps1=10.25s` against a 10s bound on 2 of 6 jobs. Serially,
  all 12 such items passed.
- **Not a fixed sleep.** A test that sleeps a fixed time and then checks a condition is not a
  wall-clock test: poll the condition until a deadline well under the thing's natural lifetime,
  and return the last value so a real survivor still fails. Evidence (L-0516): a 0.5 s sleep
  before a survivor check failed in CI with one survivor; a pidfile read as soon as it existed
  saw it empty in 389 of 500 tight reads.

## H4 — Fixtures never inherit the developer's or runner's global state [audited]

A fixture repository or process must not read the real global config. Pin, per test:

| Leak | Pin | Evidence |
|---|---|---|
| Commit/tag signing | `commit.gpgsign=false`, `tag.gpgsign=false` | 83 ms vs 7 ms a commit; a gpg pinentry can stall the suite |
| Background git maintenance | `maintenance.auto=false`, `gc.auto=0` | git 2.55 detaches `maintenance run --auto`; a "writes nothing" test saw `.git/objects/maintenance.lock` vanish mid-snapshot |
| Machine-global tool config | point the path at a file that does not exist | crew's `~/.claude/crew/config.json` |
| Ambient env (`CLAUDE_PROJECT_DIR`, `HOME`) | `monkeypatch.delenv` / explicit `env=` | green in CI, red on the maintainer's machine |
| Shared tool cache raced by concurrent children (pwsh's startup profile) | a per-test `XDG_CACHE_HOME` | concurrent pwsh crashed at start-up (-6 "Stack overflow.", -11 SIGSEGV), about 1 `-m slow -n 12` run in 20-50; with the profile unwritable, 150/150 clean |

- **Apply.** Pin through `GIT_CONFIG_COUNT` / `GIT_CONFIG_KEY_n` / `GIT_CONFIG_VALUE_n`,
  **appended after** whatever count the runner already carries. Cloud containers export their
  own entries, and overwriting from slot 0 drops them silently. Each pin gets a test that goes
  red with the pin removed.

## H5 — Deep linters run in parallel, with an explicit job count [audited]

`pylint -j "$(python -c 'import os; print(os.cpu_count() or 1)')"`, not `-j 0`. Psalm:
`--threads`. PHPStan parallelises by default.

- **Evidence.** 148s → 34s at `-j 4`, identical findings. `-j 0` gave **no** speedup, because
  pylint's own detection read a 4-CPU container as 1 CPU.
- **Precondition.** `duplicate-code` is the one pylint check `-j` changes; confirm it is
  disabled, or accept the difference.

## H6 — A fast linter and a deep linter, both pinned, both in CI [audited]

- Name the rule set explicitly (Ruff: `select = [...]`). A default set changes on upgrade:
  Ruff 0.16 widened its defaults, and `ruff check .` went from 0 to 1493 findings on untouched code.
- Pin versions in CI (`ruff~=0.16.0`, `pylint~=4.0`), so CI and a dev machine agree.
- Baseline existing findings (PHPStan baseline, `.editorconfig` severities) so the gate starts
  green. A gate that starts red gets an exception, then gets ignored.
- Do not replace an inference linter (pylint, PHPStan, SpotBugs) with a style linter (Ruff,
  php-cs-fixer) and call it equivalent. The inference checks (`no-member`, `not-callable`,
  `arguments-differ`) have no style-linter counterpart.

## H7 — CI runs what the docs say it runs [audited: Ruff]

Check every "CI runs X" statement against the workflow files, not against memory.

- **Evidence.** `verify.json` told readers "CI still runs" Ruff. No workflow did, and nine
  findings had landed in shipped scripts unseen.

## H8 — A missing tool is its own result

A check whose tool is absent exits **77** and says `TOOL MISSING`. It is never a pass and never
a fail. The environment then installs the tool: a cloud environment's setup script, or the
repo's install script.

Code-level standard: GEN-01 (crew-standards), of which this is the missing-tool case.

- **Evidence.** Without `pwsh`, `smoke.sh` read 10 passed / 1 failed. With it installed, 11/0.
  A missing `pwsh` also meant the verify gate could never record a clean pass, so every review
  needed an override.

- **Apply: the setup script.** Every tool a gate rule calls is installed by the environment's
  setup script (for a Claude Code cloud environment: environment settings → Setup script;
  new sessions run it). For this marketplace:

  ```bash
  curl -sSfLo /tmp/msprod.deb https://packages.microsoft.com/config/ubuntu/24.04/packages-microsoft-prod.deb
  dpkg -i /tmp/msprod.deb && apt-get update -qq && apt-get install -y -qq powershell
  pip install -q 'pytest~=8.0' pytest-xdist pyyaml 'pylint~=4.0' 'ruff~=0.16.0'
  ```

  Derive the list from the gate, not from memory: `crew-setup`'s `resolve-tools.sh` reports
  every command a `verify.json` rule calls that is MISSING.

## H9 — A selective local gate, a complete CI gate

Locally, run what the changed paths require: a path → suite map with measured `seconds`, a
budget, and `unmapped: fail`. Heavy suites go to CI or `--all`. A rule that is permanently over
budget never runs locally. Say so, and make sure CI runs it.

## H10 — A gate that compares commits runs after committing

A check that reads history (version drift, "changed since X was set") passes on uncommitted
edits. Commit, run it, then push.

- **Evidence.** crew 1.0.62 passed `check-marketplace.py` locally and failed CI's `check`.
- **Bump in the same commit as the change.** A versioned artifact's bump rides the commit that
  changes its contents. A later fix commit to the same artifact needs its own bump. On #263,
  two CI fixes moved crew twice (1.0.62 → 1.0.64), and each stacked PR had to move with it.
  That's correct, but it's churn: land fixes before stacking more work on a PR.

## H11 — "Not this PR's" needs a reproduction on the base commit

Before calling a CI failure unrelated, reproduce it on the base commit in the same environment.
"Flake" is not a root cause: every intermittent failure found this way had one (H3, H4).
