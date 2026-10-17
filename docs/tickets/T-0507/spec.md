# T-0507 refresh the code maps, diagrams, rules and graph left stale on main          status: spec   risk: low
## Refreshed 2026-10-04
First spec for this ticket (there was only a seed direction). Written against origin/main `155fe6d8` (crew 1.0.322); see direction.md "Direction check 2026-10-04". Docs and generated artifacts only. No plan.md exists.

Decisions taken without the owner (listed again under Open questions):
- Scope is everything the freshness reader reports stale on origin/main at build time, not the seed's fixed list. Today that is 8 maps and 19 diagram files.
- T-0501 and T-0504 are not waited for.

## Intent
After this ticket lands, the freshness reader reports no code map behind, no code map unresolvable and no diagram behind on main, the `.claude/rules/` files match the maps, and the code graph is built at the branch head. Every `path:line` in a refreshed map and every node and edge in a refreshed diagram was re-read against the code at the new anchor, not just re-stamped. Nothing the artifacts describe is changed.

## Exclusions
- No edit under `plugin/`, `scripts/`, `skills/`, `mcp-servers/` or `.github/`. A claim found wrong is corrected in the map or diagram. A code defect found on the way is named in the PR body for a later ticket, not fixed.
- No version bump and no `CHANGELOG.md` entry. No registered plugin's content changes.
- No edit to `CHANGELOG.md`, `TODO.md`, `README.md`, `AGENTS.md`, `CLAUDE.md` or `.crew/verify.json`. The maps cite them, so an edit after the new anchor stales the maps again.
- No restructuring of the maps: no pruning of old re-anchor notes, no moving of citations between maps, no new subsystem file.
- No diagram is renamed, moved or split into new files (that is L-0548). A diagram that fails the readability check after its redraw is reported, not reorganised.
- No re-anchor of an artifact that reads current (`skills-itsm`, `skills-security-ops`, `architecture`, `data-flow`, `data-flow-search`, `process`, `process-bitbucket-svg*`, the current part files). Leave them byte-identical.
- No commit of anything under `docs/diagrams/out/`, `.crew/codemap.v1.bak/` or `.crew/config.json` (all ignored; `crew_upgrade.py --force` and `render.sh` write them).
- No squash or rebase at Land. The new anchors are branch commits and only survive a merge commit.

## Evidence
Read at origin/main `155fe6d8` on 2026-10-04.
- plugin/crew/hooks/scripts/crew_freshness.py:63 `_ANCHOR_RE` (the line must end after the sha). :127 `_DIAGRAM_ANCHOR_RE`. :213 `_CITED_PATH_RE` (a cited path must start with a letter, digit or underscore, so `.crew/...` and `.claude/...` citations are not read; `docs/...` ones are). :224 `_DIAGRAM_ANCHORS_RE`. :229 `_moved_since` diffs `<sha>..HEAD` on exactly the cited paths, with no refresh-artifact exclusion. :374 `read_knowledge`. :472 `read_diagrams`.
- plugin/crew/hooks/scripts/crew_refresh_check.py:1-140 (docstring): the ticket-scoped check drops refresh-artifact paths from the changed set, so on a refresh-only branch it has nothing to measure. This ticket's acceptance therefore uses `crew_freshness` directly.
- Measured stale set (reproduction of the two readers with git plumbing, `<anchor>..origin/main`):
  - maps: `crew` (anchor `42effe14`, 98 cited paths changed), `install-scripts` (97), `localgpu` (97), `marketplace-registration` (99), `mcp-servers` (96), `obsidian-vault` (96), `repo-docs` (101), `verification-harness` (98), the last seven anchored `0620587f`. 95 changed paths are common to all eight; 35 of those are under `plugin/crew/tests`, 19 under `plugin/crew/hooks`, 14 under `plugin/crew/skills`, 8 under `plugin/crew/commands`.
  - maps current: `skills-itsm` (`5be137d8`), `skills-security-ops` (`22399a9c`).
  - diagrams stale, with the Anchors paths that moved:
    - `data-flow-crew-config` (`0620587f`): `plugin/crew/CONFIG.md`, `crew_autocycle.py`, `crew_config.py`, `crew_context.py`, `crew_state.py`
    - `data-flow-crew-config-autoclear`, `-menu`, `-ratchet`, `-read`, `-shell-route`, `-split`, `-two-files`, `-write` (`452b30cc`): `crew_config.py` in each; also `crew_autocycle.py`, `crew_state.py`, `crew_context.py`, `plugin/crew/CONFIG.md` in some
    - `process-crew-brief` (`a54ca704`): `crew-context.sh`; `process-crew-brief-crew-context`: `crew-context.sh`, `crew_context.py`, `crew_state.py`
    - `process-crew-lifecycle` (`42effe14`): `commands/implement.md`, `commands/review.md`
    - `process-crew-lifecycle-approve` (`f808e5f0`): `crew_ticket.py`; `-done`: `completion_audit.py`, `crew_ticket.py`; `-implement`: `commands/implement.md`, `crew_ticket.py`; `-review`: `commands/review.md`
    - `process-qa-audit`, `process-qa-gates` (`c5fd58de`): `.crew/verify.json`, `.github/workflows/marketplace.yml`; `process-qa-ladder`: `.crew/verify.json`
  - diagrams current: `architecture`, `data-flow`, `data-flow-search`, `process`, the 7 `process-bitbucket-svg*`, `data-flow-crew-config-no-python`, `process-crew-brief-handoff-read`, `-platform-sync`, `-status`, `process-crew-lifecycle-brainstorm`, `-spec-plan`.
- All eight stale maps cite `docs/diagrams/data-flow-crew-config.mmd`; `crew` and `repo-docs` also cite `docs/diagrams/process-crew-lifecycle.mmd`; `repo-docs` cites `docs/diagrams/architecture.mmd`. None cites a file under `graphify-out/`, `docs/qa/` or `docs/handoff/cloud/` other than `docs/handoff/cloud/T-0503.md`.
- Map sizes (lines / `path:line` citations): crew 3703 / 3112, verification-harness 2352 / 1433, localgpu 1874 / 693, repo-docs 1732 / 961, install-scripts 1622 / 875, marketplace-registration 1532 / 848, obsidian-vault 1323 / 485, mcp-servers 711 / 357.
- .crew/codemap/INDEX.md:297-305 the File / Anchor / Last pass / Covers table, one row per map, carrying each anchor.
- plugin/crew/commands/onboard.md:206-252 `--refresh <subsystem>`: `crew_upgrade.py --root <repo> --derived <file> --force`, which overwrites `.crew/codemap/UPGRADE.md`, creates `.crew/codemap.v1.bak/` if absent and rewrites `.crew/config.json`. :170-182 step 6: `crew_instructions.py rules --root .`.
- plugin/crew/commands/diagram.md:18-25 render (`render.sh docs/diagrams`), check (`diagram_check.py docs/diagrams/out`), page (`diagram_doc.py --dir docs/diagrams --write`). :30-32 `refresh` updates only diagrams whose anchors moved.
- plugin/crew/skills/crew-qa-standards/scripts/qa_doc.py:1-19 `qa_doc.py --write` generates the three `process-qa-*.mmd` plus `docs/qa/README.md` and `docs/qa/qa-process.html`; it refuses a file without its GENERATED marker.
- .gitignore:355 `docs/diagrams/out/` is ignored; tracked under `docs/diagrams/` are the `.mmd` files, `README.md` and `index.html`. .gitignore:356-366 only `graph.json` and `GRAPH_REPORT.md` are tracked under `graphify-out/`.
- graphify-out/graph.json `built_at_commit` is `197f38c5`; graphify-out/GRAPH_REPORT.md Summary reads `23840 nodes · 50994 edges`.
- .crew/verify.json rule for `.claude/rules/**` and `.crew/codemap/**`: `python3 plugin/crew/hooks/scripts/crew_instructions.py rules --root . --check` (a sync check, it passes on a stale map). `graphify-out/**` and `.crew/**` are deliberately unchecked. The `docs` rule runs `scripts/check-marketplace.py`, `scripts/_test/self-claims.py` and `scripts/sync-updates.py --check`.
- scripts/check-tooling-pr.py:58-87 `HARNESS`: none of this ticket's paths is in it. :99-118 `ALONGSIDE` lists `.claude/rules/**`, `docs/**`, `.crew/codemap/**`, `graphify-out/**`.
- docs/handoff/cloud/T-0507.md "Cleanup (required)" and docs/handoff/cloud/README.md:3-7: the ticket's PR deletes its handoff file and its README row (row 7).
- Anchor commits `0620587f` and `42effe14` are lane merge commits that reached main through a merge-commit PR, which is why they still resolve.

## Unknowns
- The stale set at build time. Main moves; the list above is a snapshot. Resolved at implement: run the acceptance snippet on the fresh branch first and work from its output. An artifact that became current is left alone; one that became stale is added.
- Whether `crew_upgrade.py --force` leaves a new tracked file on a clean cloud checkout (no `.crew/config.json` there). Resolved at implement: `git status --short` after the first map; anything outside Touch is not committed.
- Whether `mmdc` and `graphify` are installed in the cloud session. If `mmdc` is missing, the diagram check did not run: the PR says NOT VERIFIED for the readability check and the diagrams are still re-read and re-anchored. If `graphify` is missing, the graph step is not done, the PR says so, and the ticket is not closed.
- Whether a redrawn diagram still passes `diagram_check.py` (15 boxes, no crossings). A FAIL that needs a new part file is outside this ticket: report it and leave that diagram's old anchor.
- Whether `qa_doc.py --write` changes `docs/qa/README.md` content beyond the diagrams. Accepted: it is generated output and is committed as written.
- A merge to main between the last re-measure and Land can stale the maps again. Accepted as risk; the Land step re-runs the snippet and repeats the affected part once.

## Size and split
- Production lines added: 0. No parser, guard or state machine. No path in `HARNESS`. No split.
- One PR, three commits, in this order (the order is the fixpoint, see direction.md):
  1. Diagrams: the stale `.mmd` files re-derived and re-anchored, `qa_doc.py --write` for the `process-qa-*` set, `docs/diagrams/README.md` and `index.html` regenerated, and the cloud handoff cleanup.
  2. Maps and rules: each stale map re-checked and anchored to commit 1's sha (or a later branch commit), `INDEX.md` rows updated, `.claude/rules/` regenerated.
  3. Graph: `graphify update .` on a quiescent tree, both tracked files.

## Touch
- `.crew/codemap/crew.md`
- `.crew/codemap/install-scripts.md`
- `.crew/codemap/localgpu.md`
- `.crew/codemap/marketplace-registration.md`
- `.crew/codemap/mcp-servers.md`
- `.crew/codemap/obsidian-vault.md`
- `.crew/codemap/repo-docs.md`
- `.crew/codemap/verification-harness.md`
- `.crew/codemap/INDEX.md` - the anchor and last-pass cells of the refreshed rows
- `.crew/codemap/UPGRADE.md` - overwritten by the refresh command
- `.claude/rules/*.md` - regenerated, never hand-edited
- `docs/diagrams/data-flow-crew-config*.mmd`
- `docs/diagrams/process-crew-brief*.mmd`
- `docs/diagrams/process-crew-lifecycle*.mmd`
- `docs/diagrams/process-qa-*.mmd`
- `docs/diagrams/README.md`
- `docs/diagrams/index.html`
- `docs/qa/README.md` - only as qa_doc.py writes it
- `docs/qa/qa-process.html` - only as qa_doc.py writes it
- `graphify-out/graph.json`
- `graphify-out/GRAPH_REPORT.md`
- `docs/handoff/cloud/T-0507.md` - deleted
- `docs/handoff/cloud/README.md` - row 7 removed

Not in Touch, stated: everything under `plugin/`, `scripts/`, `skills/`; the version files; `CHANGELOG.md`; `plugin/crew/BUDGETS.md`. The repo rule "a `plugin/crew/` change updates every doc" does not apply: no `plugin/crew/` file changes. The PR body says `Docs: none - refresh artifacts only, no behaviour change`.

## Acceptance checks
Commands run from the repo root on the build branch. None needs pytest.
- [ ] Before any edit, the stale set is recorded in the PR body from this snippet's output (the "before" measurement):
  ```
  python3 - <<'PY'
  import sys
  sys.dont_write_bytecode = True
  sys.path.insert(0, "plugin/crew/hooks/scripts")
  import crew_freshness as f
  k = f.read_knowledge(".", {})
  d = f.read_diagrams(".", {})
  print("maps behind:", k["behind"], "unresolvable:", k["unresolvable"])
  print("diagrams behind:", d["behind"], "missing:", d["missing"])
  print("graph current:", k["graph"].get("current"), "built at:", k["graph"].get("builtAt"))
  sys.exit(1 if (k["behind"] or k["unresolvable"] or d["behind"] or d["missing"]
                 or k["graph"].get("current") is not True) else 0)
  PY
  ```
- [ ] After the last commit, with a clean tree, the same snippet exits 0: `maps behind: []`, `unresolvable: []`, `diagrams behind: []`, `missing: []`, `graph current: True`. If the graph commit itself leaves `graph current` false (the graph is tracked, so its commit moves HEAD), state the value printed and that `git diff --name-only <builtAt>..HEAD` lists only `graphify-out/` paths.
- [ ] Every refreshed map has an `anchor:` line that is the whole line (`grep -nE '^anchor: \S+@[0-9a-f]{7,40}$' .crew/codemap/<name>.md` prints one line) and names a commit on this branch (`git merge-base --is-ancestor <sha> HEAD` exits 0).
- [ ] For each refreshed map, `git diff --name-only <new anchor>..HEAD -- <paths the map cites>` prints nothing.
- [ ] For each refreshed map, the PR body gives the count of `path:line` citations re-read in files that changed since the old anchor, the count corrected, and any claim left unverified by name. A map with citations corrected: 0 and changed files: more than 0 says which files were re-read.
- [ ] `python3 plugin/crew/hooks/scripts/crew_instructions.py rules --root . --check` exits 0 (`.crew/verify.json` rule for `.claude/rules/**`).
- [ ] Each refreshed diagram's first line names the new anchor, its `%% Anchors:` paths all exist (`git cat-file -e HEAD:<path>` for each), and it carries a `%% Purpose:` line.
- [ ] `bash plugin/crew/skills/crew-diagrams/scripts/render.sh docs/diagrams` then `python3 plugin/crew/skills/crew-diagrams/scripts/diagram_check.py docs/diagrams/out` passes for every refreshed diagram, or the PR body says NOT VERIFIED with the reason (`mmdc` missing) or names the diagram that fails.
- [ ] `python3 plugin/crew/skills/crew-diagrams/scripts/diagram_doc.py --dir docs/diagrams --write` leaves no diff after the diagram commit (the page is in sync with the sources).
- [ ] `python3 plugin/crew/skills/crew-qa-standards/scripts/qa_doc.py --write` exits 0 and leaves no diff after the diagram commit.
- [ ] Graph counts agree: the `nodes` and `links` lengths in `graphify-out/graph.json` equal the numbers in `GRAPH_REPORT.md`'s `## Summary`, and the commit subject states them. The graph was built with `graphify update .` after `~/.cache/graphify-rebuild.log` stopped growing.
- [ ] `git diff --name-only origin/main...HEAD` lists only paths in Touch; in particular nothing under `plugin/`, `scripts/` or `skills/`, and not `CHANGELOG.md`.
- [ ] Artifacts that read current before the work are byte-identical: `git diff --stat origin/main...HEAD -- .crew/codemap/skills-itsm.md .crew/codemap/skills-security-ops.md docs/diagrams/architecture.mmd docs/diagrams/data-flow.mmd docs/diagrams/data-flow-search.mmd docs/diagrams/process.mmd 'docs/diagrams/process-bitbucket-svg*.mmd'` prints nothing.
- [ ] `docs/handoff/cloud/T-0507.md` is gone and `git grep -n "T-0507" -- docs/handoff/cloud/README.md` prints nothing.
- [ ] `python3 scripts/check-marketplace.py` exits 0 after the commits (it is run committed; its version-drift check compares commits) and reports no version drift, confirming no bump was needed. `python3 scripts/check-tooling-pr.py` does not refuse the branch.
- [ ] No new test is added: the change has no code. The standing checks above are the `.crew/verify.json` rules for `.claude/rules/**`, `.crew/codemap/**` and `docs/**`.
- [ ] Not verified by this ticket, and said so in the PR body: `scripts/_test/drift-detection.sh` (skipped by default, not relevant to a refresh).

## Dependencies
Must land before this one:
- None is a hard blocker.

Context and soft dependencies (state from INDEX, 2026-10-04):
- T-0503 - merged. Its waiver created this ticket.
- T-0008 - merged. The refresh check and the freshness reader this ticket is measured by.
- T-0094 - merged. Admits refresh artifacts without Touch for an approved ticket. Its tooling half L-0540 is `direction`; not needed, because Touch here names every path.
- T-0015 - merged. The previous whole-repo refresh; same procedure.
- T-0501 - done in INDEX, not on origin/main `155fe6d8`. Changes how `crew_instructions.py rules` treats maps whose anchors need a re-check. Soft: if it lands first, the rules step may warn until the maps are refreshed, which is this ticket's order anyway.
- T-0504 - done in INDEX, not on origin/main `155fe6d8`. Touches the same crew map. Soft: whichever lands second re-runs the measurement.

This ticket blocks nothing. It overlaps:
- L-0631 - direction. Refresh the crew map after #337; covered by the crew map refresh here.
- L-0548 - direction. Moves the diagrams into kind directories and re-anchors the maps; if it lands first, the diagram paths in Touch change and this spec needs a refresh.
- L-0511 - direction. Would move refreshes to Land; does not change this ticket.

## Open questions for the owner
- Scope widened from the seed's 7 maps and 3 diagrams to everything stale on origin/main at build time (8 maps, 19 diagram files today). Default taken: widened.
- T-0501 and T-0504 are not waited for. Default taken: proceed, re-measure before Land.
- Close L-0631 as covered when this lands? Default: say so in the PR body; the owner closes the row.
- The non-crew maps stale on every crew merge because their re-anchor notes cite crew paths. Default: not fixed here; named in the PR body as a follow-up.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
