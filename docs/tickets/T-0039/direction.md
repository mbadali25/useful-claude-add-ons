# T-0039 direction - crew keeps a repo's .gitignore right for the languages actually in it

Status: direction APPROVED by the owner 2026-09-26 (answer to the open question: "appy automatically").

## Ask (owner, Matthew Badali, 2026-09-26, verbatim)
"another ticket for the crew when it sets up repos for work please make sure a proper .gitignore exists and
scan code base and ensure it has the proper ignores for the languages in the repo, it should be periodically
checked and updated as well"

## Facts (origin/main 3c1f94a9)
- Setup today appends ONE fixed block: `plugin/crew/skills/crew-setup/SKILL.md:355-395` ("3c. Gitignore
  secrets before any exist") adds `.env*`, the `.crew/*` policy with its closed un-ignore list, and `.work/`.
  `/crew:init` adds `playwright/.auth/` for webtest (`plugin/crew/commands/init.md:40-43`). Nothing looks at
  the languages or build tools in the repo.
- `scripts/check-marketplace.py::check_crew_ignore_policy` asserts the `.crew` un-ignore list matches in this
  repo, the shipped template and the docs, so any new logic must not rewrite that block.
- Evidence of the gap on 2026-09-26: the Obsidian vault's `.gitignore` had been replaced by an uncommitted
  version that dropped `.claude/mining/`, `.superpowers/` and `__pycache__/`, and sessions run inside it
  left `.crew/` and `.thumbgate/` untracked - nothing noticed until a manual check.
- `crew_state.py`, `crew_guards.py` and `review_patch.py` already read `.gitignore`; `git check-ignore -v`
  is the authoritative test of what an ignore file does.

## Recommendation (to be confirmed)
1. **Detect** languages and tools from evidence in the tree (file extensions, and manifests such as
   `package.json`, `pyproject.toml`/`requirements*.txt`, `*.csproj`/`*.sln`, `go.mod`, `Cargo.toml`, `*.tf`,
   `pom.xml`/`build.gradle`, `composer.json`), plus OS and editor noise (`.DS_Store`, `Thumbs.db`,
   `.idea/`, `.vscode/` except shared settings).
2. **Recommend** ignore patterns from a curated table kept in crew, e.g. `__pycache__/`, `.venv/`,
   `node_modules/`, `bin/` + `obj/`, `.terraform/` but not `.terraform.lock.hcl`, `target/`, `vendor/`
   where the ecosystem expects it. Each pattern carries its reason. Sourced from well-known templates
   (github/gitignore), vendored with provenance, never fetched at runtime.
3. **Never lose anything, never hide tracked work.**
   - Crew only ADDS inside one marker-delimited block (`# crew:gitignore:managed ... # end`). It never
     edits or removes lines a human wrote, and never touches the `.crew` policy block.
   - Before adding a pattern it checks `git ls-files -ci --exclude-standard` style evidence. A pattern
     that would match an already-tracked file is reported, not added, because ignoring a tracked file
     does nothing and hides a decision.
   - Secrets patterns (`.env*`, `*.pem`, `*.key`, credential files) are always recommended. A secret
     already tracked is a stop that goes to the owner, not an ignore line.
4. **When:** at `/crew:init` and `/crew:onboard` (first run), and periodically, meaning `/crew:onboard
   --refresh` and the T-0008 refresh step whenever a ticket adds a new language or manifest. A read-only
   `crew_gitignore.py --check` prints what is missing, redundant or dangerous, and `/crew:status` shows a
   one-line summary.
5. **Preview then apply:** the change is shown as a diff, and only the managed block is written, atomically.

## Open questions
- Apply automatically in the refresh step, or only propose (needs-owner)? Recommendation: auto-add inside the
  managed block for build-output and cache patterns, and propose (never auto-apply) anything touching
  secrets or tracked files.
- Also check the vault and other non-code repos crew touches? Recommendation: only repos with a crew config.
- Relation to T-0037: a proposal that needs the owner becomes a `needs-owner` item once T-0037 lands.

## Decided (owner, 2026-09-26: "appy automatically")
- Everything additive is applied automatically, inside the managed block and without asking: build output,
  caches, OS/editor noise, and secrets patterns (`.env*`, `*.pem`, `*.key`, credential files). Adding an
  ignore line never deletes, untracks or rewrites anything.
- Still never automatic, because they are not additive: untracking an already-tracked file (`git rm
  --cached`), and anything about a secret that is ALREADY committed. That needs rotation and a history
  decision, so it is reported to the owner (a `needs-owner` item once T-0037 lands). A pattern that
  matches tracked files is still added, but the report names those files so the ignore does not look like
  it took effect.

## Owner decision 2026-09-30 - catch up with main by MERGE, never rebase
Owner Matthew Badali, 2026-09-30, verbatim choice "Merge main in (Recommended)", after "rebase alot fo these before merge we did 4-5 prs outside of here that merged to main". origin/main has moved (it was a61a6f38 when this note was written: T-0088 #262, the QA fixes #263-#267, crew 1.0.69).
- Before your NEXT Review round and again right before Land: `git fetch origin && git merge origin/main` (a merge commit; mechanical conflicts only - a behavioural conflict is a STOP to the owner). Never `git rebase`, never force-push, never squash.
- After each merge: version one patch past origin/main's, refresh the artifacts until fresh and committed, re-run the suites serially under heavy-run, and state the merged origin/main sha in the phase evidence.
- A review receipt that went stale ONLY because of such a merge follows the existing merge-only rule; anything else needs a new round.

## Owner decision 2026-09-30 - run the suites in parallel (pytest-xdist installed, capped at 4)
Owner Matthew Badali, 2026-09-30, verbatim choice "Install + cap at -n 4 (Recommended)". pytest-xdist 3.8.0 is now installed (apt python3-pytest-xdist); /root/crew-tmp/heavy-run exports PYTEST_XDIST_AUTO_NUM_WORKERS=4, so `-n auto` means 4 workers inside the wrapper.
- Full crew suite, always through heavy-run: `python3 -m pytest plugin/crew/tests/ -q -n 4 -m "not wallclock"`, then `python3 -m pytest plugin/crew/tests/ -q -m wallclock` serially (both must pass). This is main's own .crew/verify.json rule with the worker count pinned. Other pytest suites: same shape.
- pylint as CI runs it: `python3 -m pylint -j 4 $(git ls-files "*.py")`.
- Quote the new timing in the evidence (the serial full suite took ~700-900s here; #263 measured ~230s at -n 4).
- A test that passes serially and fails only under -n 4 is a real finding (shared-state race, as #267's d3cf73c3), not something to paper over: report it, never skip it.
