# L-0753 plan - checks 4 and 5 judge the ticket's own diff; check 5 finds the entry wherever it sits; check 2 accepts a same-tree PR-head receipt

Spec: `spec.md`. Base `origin/main` `a7fb104b0` (crew 1.2.16). No HARNESS path is edited: `ci_receipt.py`,
`crew_refresh_check.py` and `crew_docs_check.py` are feature code, and tests and docs are ALONGSIDE. The
sabotage entries are HARNESS, so they wait for the follow-up tooling PR (standing split rule).

## Steps

### Step 1 - failing tests (TDD red)
Files: `plugin/crew/tests/test_done_own_changes.py`, `plugin/crew/tests/test_ci_receipt.py`
Test: a fixture world with a ticket branch, main and another PR, with three states: pre-land (main merged in), landed
(close branch at the merge), and later (a second release on main). Acceptance 1-7 against
`crew_docs_check.ticket_docs` and `crew_refresh_check.ticket_freshness`. Acceptance 8-9 against `ci_receipt.check`
with the fake fetcher. On main these are red for 1 (landed and later), 3, 5, 6 (landed) and 8.
Risk: low - tmp_path repos only.

### Step 2 - own_changes in crew_refresh_check
Files: `plugin/crew/hooks/scripts/crew_refresh_check.py`
Test: step 1's refresh cases green; whole `test_refresh_check.py` green.
Risk: high - `own_changes(top, base, ticket)` returns `{"paths", "old", "new", "note", "narrowed"}`.
Before landing: `merged_main.resolve`, then `completion_audit.changed_paths(top, base, merged)`, with old =
merged commit (or base) and new = None (working tree). After landing (merged commit == HEAD): read the
receipt head, binary-search the ref's first-parent line in base..ref for the first commit containing it, require
2+ parents, and set paths = since-base ∩ (diff-tree M^1 M ∪ changed_paths(top, HEAD)), old = M^1, new = M.
Every failure falls back to the full since-base set, with `note` saying could not tell. `ticket_freshness` uses
it and appends the note to its reason.

### Step 3 - crew_docs_check uses it; CHANGELOG range and sections
Files: `plugin/crew/hooks/scripts/crew_docs_check.py`, `plugin/crew/tests/test_docs_check.py`
Test: step 1's docs cases green; whole `test_docs_check.py` green (the MISSING reason text is adjusted where pinned).
Risk: med - `_changelog_rows` reads old/new from the own range; the version comes from the range end's marketplace.json;
the accepted sections are `[Unreleased]` or `## [V]`; `_names_version` also accepts the bare `name V`.

### Step 4 - ci_receipt same-tree parent
Files: `plugin/crew/hooks/scripts/ci_receipt.py`
Test: step 1's receipt cases green; whole `test_ci_receipt.py` green.
Risk: high - only when no run exists for HEAD. The subject is a parent with an equal tree. The merge's producer diff
is refused. The artifact, receipt `head` and the re-read are bound to the subject; tree, map and impl to HEAD.

### Step 5 - sabotage by hand
Files: `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/hooks/scripts/crew_docs_check.py`, `plugin/crew/hooks/scripts/ci_receipt.py` (mutated, then restored byte-identical; each mutation and its red test go in the ticket notes for the tooling PR)
Test: each of spec check 10's six mutations applied, named test seen red, restored, `git diff` clean.
Risk: low.

### Step 6 - docs, diagram, code map
Files: `plugin/crew/commands/done.md`, `plugin/crew/commands/docs.md`, `plugin/crew/README.md`, `docs/guides/crew/src/troubleshooting.md`, `docs/guides/crew/src/daily-workflow.md`, `docs/guides/crew/crew-troubleshooting.html`, `docs/guides/crew/crew-troubleshooting.docx`, `docs/guides/crew/crew-troubleshooting.pdf`, `docs/guides/crew/crew-daily-workflow.html`, `docs/guides/crew/crew-daily-workflow.docx`, `docs/guides/crew/crew-daily-workflow.pdf`, `docs/diagrams/process-crew-lifecycle-done.mmd`, `docs/diagrams/README.md`, `docs/diagrams/index.html`, `.crew/codemap/crew.md`, `.crew/codemap/verification-harness.md`, `.claude/rules/crew.md`, `CHANGELOG.md`, `README.md`
Test: `docs/guides/crew/src/build.py` + `--check`; `scripts/check-crew-docs.py`; crew_refresh_check for L-0753 fresh.
Risk: low.

### Step 7 - gates, review, version commit last
Files: `plugin/crew/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `plugin/PLUGINS.md`, `plugin/crew/BUDGETS.md`
Test: `python3 scripts/check-marketplace.py`, `python3 scripts/check-tooling-pr.py`, affected suites via heavy-run;
`/crew:review` Codex, one round (two on a BLOCK).
Risk: low - placeholder version 1.2.20; the lead assigns at merge.
