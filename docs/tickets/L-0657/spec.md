# L-0657: CI fails when a built crew guide is stale          status: spec   risk: low
Split from T-0055 on 2026-10-04. Checked against origin/main `155fe6d8`. **Blocked on T-0048**: re-read `build.py --check` and `config_reference.py --check` on main once it merges, before planning.
## Intent
CI fails a pull request whose committed crew guide HTML, or generated configuration reference, does not match its sources. It uses the `--check` commands T-0048 adds, so a stale guide cannot merge on green checks.
## Exclusions
- No change to `build.py`, `config_reference.py` or any guide source or output. If a `--check` command is wrong, that is a T-0048 fix.
- No DOCX or PDF comparison (not byte-reproducible).
- No `markdown` install in the pylint job; `.pylintrc:59-64` keeps it out on purpose.
- No new workflow, no trigger change, no file under `plugin/crew/`, no harness path.
- Nothing from T-0055's docs-touched check.
## Evidence
At origin/main `155fe6d8`:
- docs/guides/crew/src/build.py:52 `import markdown`; :245-262 `main` has `--guide`, `--brand`, `--theme`, `--html-only` and no `--check`.
- .github/workflows/marketplace.yml:39-40 installs `pip pyyaml`; :91-92 "UPDATE.md mirrors are current" is the existing generated-file `--check` step this follows.
- scripts/gate-runner.py:160-161 the `sync-updates` step, the table shape for a `--check` command; :246-248 `EXCLUDED_CI` covers `python -m pip install *` for `marketplace.yml`.
- T-0048's spec (not on main): `build.py --check` exits 0 fresh, 1 naming the stale guide, 2 when `markdown` is missing; `config_reference.py --check` exits 1 naming the file.
## Unknowns
- The final names and exit codes of T-0048's commands. Resolved by reading main after T-0048 merges.
- Whether the HTML is byte-stable across `markdown` versions and across the CI runner and the build host. Resolved at implement: run the step on the ticket's PR; if it differs with nothing stale, pin the version, and if it still differs, stop and report (do not loosen the comparison here).
- Whether `build.py --check` needs `skills/doc-builder/scripts` dependencies beyond `markdown` in CI. Resolved by the first CI run; add only what the import error names.
## Size and split
About 15 added production lines (`marketplace.yml` about 10, `scripts/gate-runner.py` about 5). No parser, guard or state machine. No split.
## Touch
- `.github/workflows/marketplace.yml`
- `scripts/gate-runner.py`
- `scripts/_test/gate-runner.py` - only if it pins the table
- `CLAUDE.md` - one clause in the doc-rule paragraph: stale built guides fail CI
- `CHANGELOG.md`
- `.crew/codemap/**` - refresh
- `graphify-out/**` - refresh artifact
## Acceptance checks
- [ ] `marketplace.yml` installs `markdown` (pinned) in the existing install step or one beside it, and runs `python3 docs/guides/crew/src/build.py --check` and `python3 docs/guides/crew/src/config_reference.py --check` as named steps.
- [ ] Both commands are in `scripts/gate-runner.py`'s `TABLE` with their `ci=` pairs and `needs` naming `markdown` so a host without it reports SKIP, not PASS. `python3 scripts/gate-runner.py --check-ci` exits 0.
- [ ] Must-fail, shown once in the PR description with the CI run link: a commit that edits one line of `docs/guides/crew/src/quickstart.md` without rebuilding turns the step red, naming the guide. The commit is then reverted or the guide rebuilt.
- [ ] Must-pass: the PR's final run is green with no guide changed.
- [ ] With `markdown` uninstalled, `python3 docs/guides/crew/src/build.py --check` exits 2, not 0 (T-0048's behaviour, re-confirmed here because the CI step depends on it).
- [ ] `python3 scripts/check-tooling-pr.py` prints `tooling-pr: no harness path changed`; `python3 scripts/check-marketplace.py` passes after the commit.
## Dependencies
Must land first:
- T-0048 (spec): provides both `--check` commands.
- T-0055 (ready; the parent slice): adds the CI steps and the `CLAUDE.md` paragraph this child extends.

Blocks: nothing.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
