# T-0055 CI enforces crew doc updates: narrative docs touched, or "Docs: none - <reason>" declared          status: spec   risk: med
## Refreshed 2026-10-04
Written against origin/main `155fe6d8`. No earlier spec.md or plan.md existed. What differs from direction.md's option 1, and why (details in direction.md "Direction check 2026-10-04"):
- This ticket is part (a) only, docs-touched-or-declared. Part (b), built guides fresh, is L-0657 (`children/1/`), blocked on T-0048.
- The check is its own script beside `scripts/check-tooling-pr.py`, not a function in `check-marketplace.py`.
- Files every crew PR changes mechanically (version, changelog, budgets, code map, diagrams) do not count as docs touched. Measured: counting them would pass 31 of 31 recent crew PRs.
- The rule's paragraph is missing from `CLAUDE.md` on origin/main. This ticket commits it.
- No Stop-gate rule for the check itself; it runs in CI and in `gate-runner.py`.
## Intent
A pull request that changes crew code must also change at least one narrative crew document, or say why not with a `Docs: none - <reason>` line. CI fails the PR otherwise, so the owner's rule holds when no human reads the PR. The check forces a decision; it does not judge whether the prose is right, which stays with review.
## Design
One new script, `scripts/check-crew-docs.py`, shaped like `scripts/check-tooling-pr.py`.

- **Changed paths.** The branch's own changes: `git diff --name-status -z origin/main...HEAD` (both sides of a rename) plus everything `git status --porcelain` reports. Same rules as `check-tooling-pr.py:126-155`; share the code by importing or copying, the implementer's choice, but do not edit `check-tooling-pr.py` (it is harness).
- **CODE (what triggers the check).** A changed path under `plugin/crew/` that matches none of: `plugin/crew/**/*.md`, `plugin/crew/tests/**`, `plugin/crew/**/_test/**`, `plugin/crew/evals/**`, `plugin/crew/.claude-plugin/plugin.json`. Matching uses `crew_ticket.path_matches`.
- **DOCS (what satisfies it).** A changed path matching any of: `plugin/crew/README.md`, `plugin/crew/CONFIG.md`, `plugin/crew/commands/*.md`, `plugin/crew/agents/*.md`, `plugin/crew/skills/*/SKILL.md`, `plugin/crew/docs/**`, `docs/guides/crew/src/*.md`.
- **Never counted, either way:** `plugin/PLUGINS.md`, `CHANGELOG.md`, `plugin/crew/BUDGETS.md`, `.crew/codemap/**`, `docs/diagrams/**`, `graphify-out/**`, the built guides under `docs/guides/crew/`. They still have to be updated under the CLAUDE.md rule; the check just cannot tell a real edit from a refresh.
- **Declaration.** A line `Docs: none - <reason>`, read from two places:
  - a commit trailer on any commit in `origin/main..HEAD` (`git log --format=%(trailers:key=Docs,valueonly)`);
  - the PR body, when `--pr-body-file <path>` is given, or when `GITHUB_EVENT_NAME` is `pull_request` and the JSON at `GITHUB_EVENT_PATH` has `pull_request.body`. In the body the line must start a line (leading spaces allowed).
  - The separator is a hyphen, en dash or em dash. The reason is valid when, stripped, it is not empty and does not start with `<` (the unfilled `<why>` / `<reason>` placeholder). `Docs: none` alone is not a declaration.
- **Verdict, in this order.**
  1. `origin/main` is not a ref, or a git call fails: exit 77, `TOOL MISSING ... DID NOT RUN` on stderr. Never 0.
  2. No CODE path changed: exit 0, `crew-docs: no crew code changed`.
  3. A DOCS path changed: exit 0, naming the count.
  4. A valid declaration exists: exit 0, printing where it came from (trailer or PR body) and the reason verbatim.
  5. The PR body should have been readable (the event is `pull_request`, or `--pr-body-file` was given) but the file is missing or not valid JSON/text: exit 77, saying the body could not be read. An unreadable body is not "no declaration".
  6. Otherwise exit 1: the CODE paths, one per line, the DOCS globs, and both ways to declare. An invalid declaration (empty or placeholder reason) is named as such.
- **CI.** Two steps in `marketplace.yml`'s `check` job, after "Windows shard fan-in suite": `python3 scripts/_test/crew-docs.py`, then `python3 scripts/check-crew-docs.py`. No workflow trigger changes. On a push to main the diff is empty and the check passes; the PR run was the gate.
- **gate-runner.** Both commands join `TABLE` in `scripts/gate-runner.py` with their `ci=` pairs, so `--check-ci` stays green. Locally the checker sees trailers only.

The paragraph to add to `CLAUDE.md`, after the registration paragraph in "Scope discipline" (`:29`), then extended with one sentence naming the check and the trailer:

> **A change to `plugin/crew/` updates every document that describes it, in the same PR.** Owner rule, 2026-09-26. Docs are part of the ticket, not something noticed nearby, so they go in the spec's Touch list; otherwise the scope guard blocks the doc edits at implement time. The set to check: `plugin/crew/README.md`, `plugin/crew/CONFIG.md`, the command and skill files that describe the behaviour, `plugin/PLUGINS.md`'s row, `docs/guides/crew/src/*.md` plus the rebuilt HTML, DOCX and PDF (`docs/guides/crew/src/build.py`), the crew, configuration and autopilot guides once T-0048 and T-0054 land, `.crew/codemap/`, and `docs/diagrams/`. In this repo that overrides `commands/implement.md` step 6's "none is common and correct" for crew itself. A crew change with no doc impact says so in its PR body, with the reason (`Docs: none - <why>`), never silently.

The added sentence says: `scripts/check-crew-docs.py` fails a PR that changes crew code and neither touches a narrative doc nor carries the line, and the line also works as a commit trailer, which is the only form a local run can see.
## Exclusions
- No guide freshness check, no `build.py --check`, no `markdown` install in CI. That is L-0657.
- No file under `plugin/crew/` changes, so no crew version bump and no crew doc update. No `/crew:implement`, `/crew:docs` or `/crew:done` change to write the declaration for the author.
- No edit to any review/gate harness path (`HARNESS` in `scripts/check-tooling-pr.py:58-87`): not `check-tooling-pr.py`, not `plugin/crew/tests/sabotage*.py`, not `crew_ticket.py` (imported, not edited).
- No Stop-gate rule that runs `check-crew-docs.py`. The `.crew/verify.json` rule added here runs the suite only, on a change to the checker or its suite.
- No change to `marketplace.yml`'s `on:` triggers or permissions. No `gh` or API call from the check; it reads the event file GitHub already wrote.
- No hook. Nothing here runs inside a Claude session.
- No attempt to judge doc content, to tell a code map prose edit from a re-anchor, or to check plugins other than crew.
- No comment posted on the PR (direction option 2).
- No edit to the local uncommitted `CLAUDE.md` in any other checkout; the paragraph is added on the ticket branch from the text above.
## Evidence
All read at origin/main `155fe6d8` on 2026-10-04.
- Nothing implements this: `git grep -n -i "Docs: none" origin/main -- scripts .github plugin/crew/commands plugin/crew/hooks` prints nothing. `git log origin/main --grep=T-0055` prints nothing.
- The rule on main: .crew/standards.md:118-119 ("a `plugin/crew/` change updates every document CLAUDE.md "Scope discipline" lists, or says `Docs: none - <why>` in its PR body"). CLAUDE.md:24-29 is "Scope discipline" up to the end of the registration paragraph; :31 starts the claim-marker rule. The doc-rule paragraph is absent: `git log origin/main -S"updates every document" -- CLAUDE.md` prints nothing.
- Measured: `git log origin/main --first-parent --merges -n 60`, each diffed against its first parent. 31 merges change crew code as defined above. All 31 change `plugin/PLUGINS.md` and `CHANGELOG.md`. 4 change no narrative doc: 1d43e9fe (#380), 03d6b788 (#328), e2bc4fa8 (#317), 8d84786d (#302); none of those PR bodies has a `Docs:` line. A re-anchor alone changes all nine code maps (2a2d6e07: 9 files, 8 `anchor:` lines plus re-anchor notes).
- The model: scripts/check-tooling-pr.py:56 `EXIT_MISSING = 77`; :126-155 `changed_paths`; :158-164 `declared_seams` reads trailers from `origin/main..HEAD`; :167-168 `_matches` over `crew_ticket.path_matches`; :171-182 `check`; :204-212 `main` prints exit 77 on stderr. :52-54 the `sys.path` insert for `crew_ticket`.
- plugin/crew/hooks/scripts/crew_ticket.py:415 `path_matches(path, glob)`; `*` stays inside one segment, a `**` segment spans zero or more.
- .github/workflows/marketplace.yml:6-10 triggers (`push` to main, `pull_request`, `workflow_dispatch`); :24-29 checkout with `fetch-depth: 0`; :39-40 installs pyyaml only; :85-86 "Windows shard fan-in suite", the step the new ones follow.
- scripts/gate-runner.py:68-75 `--check-ci` fails on a workflow `run:` command in neither the table nor `EXCLUDED_CI`; :138-139 `_py_suite` (default workflow `marketplace.yml`); :148 `TABLE`; :188 the `check-tooling-pr` step, the shape for a non-suite checker; :107 `EXIT_SKIP = 77`.
- .crew/verify.json:446-473 the harness rule, the shape for a rule that maps a checker and its suite.
- The suite model: scripts/_test/tooling-pr.py:30 `load_checker`, :56 `repo(tmp, origin=True)` builds a throwaway repo with an `origin/main` ref, one `case_*` function per case.
- Crew tree shape: `plugin/crew/commands/` 36 files, `plugin/crew/agents/` 4, `plugin/crew/docs/` 3, 49 `.md` files directly under `plugin/crew/skills/*/`, `plugin/crew/tests/` 346, `plugin/crew/evals/` 31.
## Unknowns
- Whether `origin/main` resolves in the `pull_request` checkout of `marketplace.yml`. `fetch-depth: 0` fetches all branches, and `verify-gate.yml:47-49` relies on the same for a push. Resolved at implement: the ticket's own PR run shows the step's first output line; exit 77 there is a red step, never a silent pass.
- Whether `HEAD` on the PR merge ref gives the PR's own diff. Expected yes: the merge base of `origin/main` and `refs/pull/N/merge` is the base tip. Resolved by a suite case that builds that commit shape.
- Whether `gate-runner.py`'s suite (`scripts/_test/gate-runner.py`) pins the step count or names. Resolved at implement by running it; it is in Touch.
- A `Docs: none` trailer on an early commit covers later commits that do need docs. Accepted as risk: the reason is printed in the CI log and the reviewer holds the PR to it, as with `Tooling-seam:`.
- A PR-body declaration added after the run is not seen until the next push. Accepted as risk and documented; owner question 2 in direction.md.
- Whether any code map documents `scripts/`' checkers closely enough to need a line. Resolved at implement: `git grep -l check-tooling-pr origin/main -- .crew/codemap .claude/rules` lists the maps to read.
## Size and split
- Estimate: about 190 added production lines. `scripts/check-crew-docs.py` about 170 with its docstring, `scripts/gate-runner.py` about 6, `marketplace.yml` about 14. Under the 300-line rule.
- One guard, no parser beyond one line pattern, no state machine.
- No harness path is touched, so the tooling-PR rule does not apply; `python3 scripts/check-tooling-pr.py` prints `tooling-pr: no harness path changed`.
- Split anyway, by dependency: L-0657 (guides fresh in CI) cannot start until T-0048 lands.
## Touch
- `scripts/check-crew-docs.py` - new
- `scripts/_test/crew-docs.py` - new
- `.github/workflows/marketplace.yml`
- `scripts/gate-runner.py`
- `scripts/_test/gate-runner.py` - only if it pins the table
- `.crew/verify.json`
- `CLAUDE.md`
- `.crew/standards.md`
- `docs/claude-md-evidence.md` - the measurement behind the new paragraph
- `CHANGELOG.md`
- `.crew/codemap/**` - a line where a map lists the repo checkers, plus refresh
- `.claude/rules/**` - regenerated from the code maps
- `graphify-out/**` - refresh artifact

Not in Touch, stated: anything under `plugin/crew/` (no crew change, so `Docs: none` does not arise for this PR and no version moves); `plugin/PLUGINS.md` and `.claude-plugin/marketplace.json` (no plugin content changes); `scripts/check-tooling-pr.py` and `plugin/crew/tests/sabotage*.py` (harness).
## Acceptance checks
Commands run from the repo root. The suite builds throwaway git repos under a temp directory and touches no real config.
- [ ] `python3 scripts/_test/crew-docs.py` exits 0 and prints one line per case. Must-fail cases (checker exits 1):
  - a crew hook script changed, nothing else
  - a crew hook script plus only `plugin/PLUGINS.md`, `CHANGELOG.md`, `plugin/crew/BUDGETS.md`, a code map and a diagram
  - a crew hook script, uncommitted (untracked), nothing else
  - a crew skill script (`plugin/crew/skills/*/scripts/*`) plus a skill reference `.md` that is not `SKILL.md`
  - a trailer `Docs: none` with no reason
  - a trailer `Docs: none - <why>`
  - a PR body with `Docs: none -` and only spaces after it
  - a PR body where the line is inside a sentence, not at the start of a line
  - a declaration trailer that exists only on a commit merged in from main
- [ ] Must-pass cases (checker exits 0) in the same suite:
  - no crew path changed
  - only crew tests, evals and `plugin.json` changed
  - only `plugin/crew/commands/x.md` changed
  - a hook script plus `plugin/crew/README.md`
  - a hook script plus `docs/guides/crew/src/quickstart.md`
  - a hook script renamed, plus a `SKILL.md` edit
  - a hook script plus a trailer `Docs: none - internal rename, no behaviour change`
  - a hook script plus the same line in `--pr-body-file`, with a hyphen, an en dash and an em dash
  - a hook script plus the line in a `GITHUB_EVENT_PATH` JSON with `GITHUB_EVENT_NAME=pull_request`
  - the PR merge-ref shape: HEAD is a merge of main and a branch that changed a hook script and README
  - main merged into the branch, where main's side changed crew code and the branch did not
- [ ] Could-not-tell cases exit 77 and print on stderr: no `origin/main` ref; `GITHUB_EVENT_NAME=pull_request` with a `GITHUB_EVENT_PATH` that is missing; one that is not JSON. With a DOCS path changed, the unreadable-body cases exit 0 instead (the body was not needed).
- [ ] Exit-1 output names every CODE path, lists the DOCS globs and shows both declaration forms. Exit-0-by-declaration output prints the reason verbatim and its source.
- [ ] Mutation cases inside the suite, each patching the loaded checker and asserting a named case flips: (a) `plugin/PLUGINS.md` added to DOCS; (b) the empty-reason test removed; (c) the placeholder test removed; (d) the missing-ref branch returns 0; (e) trailers read from `HEAD` instead of `origin/main..HEAD`; (f) `git status` paths dropped; (g) an unreadable body treated as an empty body. The suite fails if any mutation leaves every case unchanged.
- [ ] `python3 scripts/check-crew-docs.py` on this ticket's own branch prints `crew-docs: no crew code changed` and exits 0.
- [ ] `.github/workflows/marketplace.yml` runs both commands; `python3 scripts/gate-runner.py --check-ci` exits 0 and `python3 scripts/_test/gate-runner.py` passes.
- [ ] `.crew/verify.json` has a rule with paths `scripts/check-crew-docs.py` and `scripts/_test/crew-docs.py` that runs `python3 scripts/_test/crew-docs.py`, with a measured `seconds` and a `why`. No rule runs `check-crew-docs.py` itself.
- [ ] `CLAUDE.md` "Scope discipline" carries the paragraph above plus the sentence naming the check and the trailer. `.crew/standards.md:118-119` says "in its PR body or a `Docs:` commit trailer". `docs/claude-md-evidence.md` records the 31 / 4 measurement and how to re-measure it.
- [ ] `python3 scripts/check-tooling-pr.py` prints `tooling-pr: no harness path changed`. `python3 scripts/check-marketplace.py` passes after the commit. `ruff check scripts/check-crew-docs.py scripts/_test/crew-docs.py` and pylint on both are clean.
- [ ] The ticket's PR shows the new CI step green, and its log's first line is not `TOOL MISSING`.
## Dependencies
Must land first:
- T-0087 (merged): `scripts/check-tooling-pr.py`, the model this copies, and the tooling-PRs-land-alone rule this spec stays clear of.

Not required for this slice:
- T-0048 (spec): needed by L-0657 only. The original INDEX note "depends on T-0048 for freshness" now applies to the child.

Related, no order forced:
- T-0046 (in-progress): BUDGETS.md claim numbers. This spec treats `plugin/crew/BUDGETS.md` as never counted, which holds either way.
- T-0054 (ready): the autopilot guide. Its source lands under `docs/guides/crew/src/*.md`, already in DOCS.

Blocks:
- L-0657 (guides fresh in CI): reuses this ticket's CI step position and `CLAUDE.md` paragraph.
- T-0011 (approved; autopilot ship policy): merges on green checks. Not a hard block, but the doc rule is unenforced for autopilot merges until this lands.

## Split
- L-0657 (child 1 of T-0055, filed 2026-10-04): CI fails when a built crew guide is stale

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
