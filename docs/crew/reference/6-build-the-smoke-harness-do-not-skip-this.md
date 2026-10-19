<!-- Moved verbatim from plugin/crew/README.md (6. Build the smoke harness (do not skip this)) by L-0726; the README keeps an index entry. -->

## 6. Build the smoke harness (do not skip this)

Checks live in **`_verify/`**. Setup looks for it first, along with `qa/`, `spec/` and `_test*/`; if the repo already has one of those it is adopted rather than duplicated. If none exists, `/crew:init` creates `_verify/` from the bundled template:

```
_verify/
  README.md       # what each check covers, and when it was last sabotage-tested
  smoke.sh        # fast and shallow: does it respond
  run-all.sh      # the regression suite: does everything else still work
  cases/          # one file per concern, called by the two runners
```

`_verify/README.md` is part of the deliverable. Its layout table says what each script covers and its status table records when each check last proved it could fail. `/crew:verify` cross-checks that README against `.crew/verify.json` and reports drift in either direction — a script with no rule never runs, and a rule pointing at a script the README does not list is a check nobody knows about.

A repo that already has a working `scripts/smoke.sh` keeps it. The gate checks `_verify/smoke.sh` first and falls back, so there is no reason to migrate a harness that works.

Both template runners print the last 5 lines of a failing check's output under its `FAIL` line, and report exit 77 (a tool or environment the check needs is absent) as `SKIP`, not a failure (T-0502). A repo with Mermaid sources also gets the ready case `_verify/cases/diagrams-render.sh` (from `skills/crew-setup/templates/cases/`): it renders every `.mmd` with the `--no-sandbox` puppeteer config, so it works as root in CI containers, prints mmdc's own error lines on a failed render, and exits 77 without `mmdc`. A bare `mmdc` call in a case fails as root with "Running as root without --no-sandbox is not supported". Repos set up before this keep their runners and cases; to pick it up, copy the case, and replace each runner's counter line (`PASS=0; FAIL=0`, now with `SKIP=0`), its `check()` / `run()` function, the `CUR_OUT` / `cleanup` / `trap` lines above it and its final count line with the template's - `check()` alone fails under `set -u` on the first exit 77, because the old `smoke.sh` has no `SKIP` counter.

At this point `_verify/smoke.sh` exists but contains no checks, so the gate passes vacuously. The crew has no safety net.

```
/crew:init --phase 3
```

The session fills `_verify/` itself; crew 1.0 ships no writing agents.

Do nothing else in this repository until that script runs green from a clean checkout.

This is not process ceremony. Agents working on untested legacy code produce confident, plausible, broken changes faster than you can review them. The gate is what converts speed into progress rather than into a slow-motion outage.

What good looks like:

- Five to nine checks, under ninety seconds total
- **Characterization, not aspiration** — capture what the application does *today*, bugs included. A test encoding current behavior is an asset. One encoding intended behavior is a wish.
- Contract level: does it boot, reject an anonymous request, accept an authenticated one, read, write, and round-trip through the database
- Deterministic: no wall clock, no randomness, no dependence on data that happens to exist
- Exit 0 or 1, one line per check, `SMOKE: n/m passed` at the end

Anything that cannot be tested without touching production does not get tested. It gets written into `.work/SMOKE-GAPS.md` so the gap is visible rather than assumed away.

Once it is green, the `Stop` hook takes over: if code changed and smoke fails, the turn cannot be reported as complete.
