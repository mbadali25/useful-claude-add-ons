# T-0083 direction          status: direction   risk: med
## Ask
Filed 2026-09-27 ~23:20 CDT by owner decision ("yes please", to "file option 1 as a crew ticket"). The owner asked whether Claude's native memory recall could try Obsidian first. Native memory has no recall call to intercept (MEMORY.md loads at session start; a memory file is read with the ordinary Read tool), but crew's UserPromptSubmit hook already searches the vault on every prompt and injects `<vault-recall>` before Claude sees it - so Obsidian is already first. The defect is relevance: through the whole 2026-09-27 crew session the injected hits were archived session notes from other projects with no bearing on the crew work being discussed.

Evidence (origin/main):
- `plugin/crew/hooks/scripts/crew_context.py:578` `recall_items` calls `crew_recall.recall(query, cfg, ...)` with the raw prompt as the query.
- `plugin/crew/hooks/scripts/crew_recall.py:218` `recall` shells out to the obsidian-vault CLI (`recall --query ... --vaults ... --max-chars ... --json`); `:209` orders snippets only by vault priority, then the CLI's own rank. Nothing passes the current repo/project, and nothing prefers durable notes over session logs.
- The vault's own contract (the vault's CLAUDE.md): durable claims live in `wiki/concepts/<org>/<project>/` and `wiki/decisions/`; `wiki/sessions/archive/YYYY-MM/` is excluded from Obsidian search on purpose (`.obsidian/app.json` userIgnoreFilters). The CLI evidently does not honour that exclusion.

Direction to settle at brainstorm (may span crew and the obsidian-vault plugin's CLI):
- Pass the current repo's project identity (repo name, or the vault's `project:` key) and prefer notes whose `project:` matches.
- Rank `wiki/concepts/` and `wiki/decisions/` above `wiki/sessions/`, and exclude `wiki/sessions/archive/` (the vault already excludes it from Obsidian search).
- Return nothing rather than something unrelated: a relevance floor, so an empty recall is an honest "no hit", not an off-topic hit.
- Tests: a crew prompt in this repo recalls the crew concept note over an archived session note of another project; an archive-only match yields no injection; the project filter never hides a concept note with no project. Sabotage per rule.
- Option 2 (native memory files as one-line pointers into the vault) is its own ticket, T-0084, built into crew at the owner's request.
## Options
none yet - to be settled at /crew:brainstorm.
## Approval
Status `direction`.

## Owner decision 2026-09-30 - catch up with main by MERGE, never rebase
the owner, 2026-09-30, verbatim choice "Merge main in (Recommended)", after "rebase alot fo these before merge we did 4-5 prs outside of here that merged to main". origin/main has moved (it was a61a6f38 when this note was written: T-0088 #262, the QA fixes #263-#267, crew 1.0.69).
- Before your NEXT Review round and again right before Land: `git fetch origin && git merge origin/main` (a merge commit; mechanical conflicts only - a behavioural conflict is a STOP to the owner). Never `git rebase`, never force-push, never squash.
- After each merge: version one patch past origin/main's, refresh the artifacts until fresh and committed, re-run the suites serially under heavy-run, and state the merged origin/main sha in the phase evidence.
- A review receipt that went stale ONLY because of such a merge follows the existing merge-only rule; anything else needs a new round.

## Owner decision 2026-09-30 - run the suites in parallel (pytest-xdist installed, capped at 4)
the owner, 2026-09-30, verbatim choice "Install + cap at -n 4 (Recommended)". pytest-xdist 3.8.0 is now installed (apt python3-pytest-xdist); <local-tmp>/heavy-run exports PYTEST_XDIST_AUTO_NUM_WORKERS=4, so `-n auto` means 4 workers inside the wrapper.
- Full crew suite, always through heavy-run: `python3 -m pytest plugin/crew/tests/ -q -n 4 -m "not wallclock"`, then `python3 -m pytest plugin/crew/tests/ -q -m wallclock` serially (both must pass). This is main's own .crew/verify.json rule with the worker count pinned. Other pytest suites: same shape.
- pylint as CI runs it: `python3 -m pylint -j 4 $(git ls-files "*.py")`.
- Quote the new timing in the evidence (the serial full suite took ~700-900s here; #263 measured ~230s at -n 4).
- A test that passes serially and fails only under -n 4 is a real finding (shared-state race, as #267's d3cf73c3), not something to paper over: report it, never skip it.

## Direction check 2026-10-04
Checked against origin/main `155fe6d8` (crew 1.0.322, obsidian-vault 0.4.16). Owner go 2026-10-04 for Brainstorm and Spec only; the owner was not available, so each open choice below takes the recommended option and is repeated under "Open questions for the owner" in spec.md.

Still true (the problem is real, nothing merged fixes it):
- `git log origin/main -i --grep=recall` finds one commit, the 1.0.25 lifecycle redesign (`6c497a14`). Nothing since has touched ranking.
- plugin/crew/hooks/scripts/crew_context.py:604-606 `recall_items` still passes the raw prompt and no project. plugin/crew/hooks/scripts/crew_recall.py:244-245 builds `recall --query --vaults --max-chars --json` and nothing else; :209 still orders by vault priority, then the CLI's rank.
- plugin/obsidian-vault/hooks/scripts/vault_recall.py:110-115 `iter_notes` walks every `.md` outside `SKIP_DIRS` (:40), so `wiki/sessions/archive/` is read like any other folder. :135 keeps every note with `score > 0`, so one common word in a body line is a hit. :50-56 `terms_of` keeps every word of two or more characters, stop words included, and the first 12 of them. :139 sorts by score and path only. Nothing reads `project:` or the folder a note is in.

What changed since the ticket was filed:
- The CLI path. The direction says crew calls `scripts/vault_ops.py`; on origin/main the file is plugin/obsidian-vault/hooks/scripts/vault_ops.py and the recall code is its own module, vault_recall.py (231 lines). crew finds either location (crew_recall.py:44).
- The cause is in the CLI, not in crew. crew's own module says so: "crew does not search vaults itself" (crew_recall.py:4). So the ranking fix belongs to obsidian-vault, and crew's part is only to say which project it is in.
- The tooling-PR rule (T-0087, merged) now applies: `plugin/crew/tests/sabotage*.py` is harness (scripts/check-tooling-pr.py:78), so a crew sabotage mutation cannot ride in the same PR as the crew_recall.py change.
- The vault contract shipped with the plugin names `project` as a concept key (plugin/obsidian-vault/templates/concept.md:15) but gives sessions and decisions no project key, and it does not mention an archive folder. The archive folder and the per-project concept folders are conventions of the owner's vault.

Options considered:
1. **Recommended: fix ranking in the obsidian-vault CLI, then have crew pass the project.** Three slices. Slice 1 (this ticket): the CLI skips excluded folders, drops stop words, applies a relevance floor, ranks concept and decision notes above session notes, and accepts `--project`. It helps every caller at once and needs no crew change. Slice 2 (L-0675): crew passes `--project` and falls back cleanly on an older CLI. Slice 3 (L-0676): the crew sabotage mutations for slice 2, as a tooling-only PR.
2. Filter in crew after the CLI answers. Rejected: crew sees only the snippets that fit the budget, so it cannot promote a concept note the CLI already cut, and it would be a second search engine in the plugin whose docstring says it has none.
3. Semantic or embedding search. Rejected for this ticket: a new dependency and an index to keep fresh, against a hook with a 4 second budget (crew_recall.py:39). The plain-text scorer is enough once it stops reading the archive and stops counting stop words.

Choices taken (each is the recommended default, listed again in spec.md):
- Another project's notes are ranked last, not dropped. A concept filed under one project is often general knowledge.
- Excluded folders are `wiki/sessions/archive/` plus the plain path entries of the vault's own `.obsidian/app.json` `userIgnoreFilters`. What the owner hid from Obsidian search is hidden from recall. `--include-excluded` reads them anyway.
- The floor counts distinct matched terms after stop words are removed: 1 for a query of one or two terms, 2 for three to five, 3 for six or more. `--min-terms` overrides it.
- Project identity in crew is `memory.recall.projects` when set, else the main checkout's directory name.
- obsidian-vault takes a minor bump (0.5.0), because default results change for every caller.

Note for publishing: the "Ask" section above names two other projects by their short names. Replace them with "other projects" before this file is published.
