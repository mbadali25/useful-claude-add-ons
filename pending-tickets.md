# Pending tickets

Work found while building L-0618 (crew QA standards), waiting for a ticket ID. The owner's ticket
agent creates each ticket and writes its ID in the **Ticket** column; the implementing session works
from this file and updates **Status** as work lands.

Status values: `needs ticket`, `ready`, `in progress`, `in review (PR #n)`, `blocked: <why>`,
`done (PR #n)`, `owner action`.

Last updated: 2026-10-03 (PRs #350-#373 added).

## Summary

| # | Ticket | Title | Status | Blocked by |
|---|---|---|---|---|
| 1 | L-0618 | QA standards: environment and gate audit, `qaAuditStale`, QA-process docs | in review (PR #337) | |
| 2 | L-0562 | `/crew:verify --stamp-reach` | in review (PR #372) | |
| 3 | _new_ | Run `_verify/smoke.sh` in CI; a missing `pwsh` is a SKIP | done (PR #373) | |
| 4 | _new_ | Crew diagram readability standard, and this repo's diagrams made readable | in review (PR #375) | |
| 5 | L-0618 | Slice b: correct-by-default `_verify` templates, `--audit --fix`, GitHub Actions CI template, `holds` | needs ticket | #1 |
| 6 | L-0618 | Slice c: sabotage entries for every new check (harness: its own tooling PR) | needs ticket | #1, #2, #4 |
| 7 | _new_ | G1 points at `--stamp-reach` once both have merged | needs ticket | #1, #2 |
| 8 | _new_ | `qa_doc.py` follows the diagram standard (`%% Purpose:` lines, readability check) | needs ticket | #1, #4 |
| 9 | _new_ | Refresh the crew code map after #337 (`TRIGGERS` gains `qaAuditStale`) | needs ticket | #1 |
| 10 | _new_ | Apply the diagram standard to the other diagram-producing skills | needs ticket | #4 |
| 11 | owner | Tell the two production repositories' sessions about D10 and the audit | owner action | #1, #2 merged |

## PRs #350-#373 (handed over from another cloud session, 2026-10-03)

Crew versions are allocated here so parallel PRs do not collide. A PR re-bumps above `main` when
it merges if its number has been passed.

| PR | Ticket | State | Blocked by | Crew version |
|---|---|---|---|---|
| #350 | T-0061 | built; merging main and verifying (harness half is #378, 1.0.181) | | 1.0.184 |
| #351 | T-0066 | part 1 merged with main, verified; in review | | 1.0.185 |
| #355 | T-0013 | built; merging main and verifying | | 1.0.186 |
| #360 | T-0048 | merged with main, verified; in review | | 1.0.200 |
| #368 | T-0063 | built; merging main and verifying | | 1.0.201 |
| #371 | T-0100 | built; harness files, may need a tooling-PR split | | 1.0.202 |
| #337 | L-0618 | in review | | 1.0.187 |
| #375 | row 4 | in review | | 1.0.188 |
| #372 | L-0562 | in review; re-bumped after main's #327 | | 1.0.199 |
| #352 | T-0069 | ready to build | | 1.0.189 |
| #357 | T-0020 | ready to build | | 1.0.190 |
| #358 | T-0022 | ready to build | | 1.0.191 |
| #359 | T-0025 | ready to build | | 1.0.192 |
| #361 | T-0050 | ready to build | | 1.0.193 |
| #369 | T-0044 | ready to build | | 1.0.194 |
| #370 | T-0038 | ready to build; carries #337's `/crew:upgrade` step 5c into `/crew:migrate` | | 1.0.195 |
| #353 | T-0011 | real code on a base 1,855 commits old; port to main | | 1.0.196 |
| #362 | T-0051 | unverified WIP on an old base; port and verify | | 1.0.197 |
| #367 | T-0064 | real code on an old base; port to main | | 1.0.198 |
| #354 | T-0012 | blocked | T-0019 (#379) | |
| #356 | T-0017 | blocked | T-0016 (not started) | |
| #363 | T-0060 | blocked | T-0051 (#362), T-0049 (not started) | |
| #364 | T-0052 | blocked | T-0019 (#379), T-0037 (not started) | |
| #365 | T-0058 | blocked | T-0052, T-0012, T-0019 | |
| #366 | T-0059 | blocked | T-0011 (#353), T-0037, T-0052 | |

**Harness-only follow-ups (each lands alone, per `CLAUDE.md` T-0087):**

| For | Work | Status |
|---|---|---|
| T-0066 (#351) part 2 | The scope guard refuses a commit carrying a `git.forbiddenTrailers` trailer: `scope_guard.py`, `test_scope_guard_trailers.py` (must-block/must-allow), `sabotage_trailers.py` + `sabotage.py` entry, the scope-guard doc rows | needs ticket |
| T-0048 (#360) | `sabotage_keys.py` (ten mutations, shown red by hand) registered in `sabotage.py` | needs ticket |

**Re-bumps:** merging `main` always needs a new crew version set after the merge (the drift check dates a version from the first commit that declared it). 1.0.180 -> 1.0.199 (#372), 1.0.183 -> 1.0.200 (#360), 1.0.182 -> 1.0.201 (#368), 1.0.166 -> 1.0.202 (#371). Next free: 1.0.203.

**Not started anywhere (no branch, nothing on `main`):** T-0016, T-0037 and T-0049. Together they block
#356, #363, #364, #365 and #366. Owner's ticket agent: confirm that each ticket exists and is ready to
build, or create it.

## Owner decisions (2026-10-03)

| # | Question | Decision |
|---|---|---|
| 1 | Merge order for the open PRs | #374, then #373, #372, #337, #375. Each crew PR is re-bumped and merged with `main` after the one before it lands |
| 2 | Box limit per diagram | 15 (`diagram_check.MAX_NODES`) |
| 3 | Should `render.sh` fail on a readability FAIL? | No. The check is its own step; `/crew:diagram` treats a FAIL as not done |
| 4 | Diagram standard for other skills (row 10) | Each skill references the crew-diagrams rules and runs `diagram_check.py` only where crew is installed; no hard dependency on crew |
| 5 | A visual of graphify's graph | No. It is a 1,000+ node graph with no readable single picture; the code map is the human view |

## Details

### 1. L-0618: QA standards (slices 0 + a)

PR #337. Report-only audit items G1-G5 and E1-E7 in `crew-qa-standards`, the `qaAuditStale` session
trigger, `--stamp`, `--all-repos`, `qa_doc.py` (Markdown + HTML + diagrams), `/crew:init --audit`,
`/crew:upgrade` step 5c. Follows the owner decisions in `docs/review/09-qa-standards-crew.md` §6.

### 2. L-0562: `/crew:verify --stamp-reach`

PR #372. Declares `reach` on undeclared rules from the Stop gate's own classifier; `--apply` never
changes what Stop runs; a deferred rule runs only on `--set N=...`. Also corrects `verify.md`'s
`reach` citation (CONFIG.md §19, not §18) and adds a correction note to D10 in the review doc.

### 3. `_verify/smoke.sh` in CI

PR #373. Found by the QA audit (item E7). Two smoke checks ran nowhere in CI: the crew-setup
`canon()` round-trip and version agreement including `pyproject.toml`.

### 4. Crew diagram readability standard

PR #375 (branch `crew-diagram-standard`). Owner request: every diagram crew draws is readable (no crossing
lines, nothing drawn through a box, labels clear, at most 15 boxes), embedded in a Markdown page with
an HTML twin, and kept in standard locations.

- `crew-diagrams/scripts/diagram_check.py`: measures the rendered SVG. FAIL on any crossing, line
  through a box, label overlap, or more than 15 boxes. Non-flowcharts are NOT CHECKED, never PASS.
- `crew-diagrams/scripts/diagram_doc.py`: writes `docs/diagrams/README.md` and `index.html`, every
  diagram embedded beside its `%% Purpose:`, anchors and readability verdict.
- `crew-diagrams` SKILL.md and `/crew:diagram`: render, check (a FAIL is not done), then the page.
- This repo's five failing diagrams split into readable parts; wordy boxes shortened, detail kept in
  `%% Note` lines shown as a "Box details" table. All 33 pass.

**Acceptance:** every `docs/diagrams/*.mmd` here renders to a PASS; the page is generated; tests
cover each checker guard with a sabotage that turns them red.

### 5. L-0618 slice b

Corrected `_verify/{smoke,run-all}.sh` templates (explicit `--env`, unknown flags refused, `--ci`,
hostname guard, zero checks fails); `qa_audit.py --audit --fix` (one confirmed fix per GAP, shown as a
diff, through the repo's gate); a GitHub Actions CI template (owner decision 5: Bitbucket later);
Phase 8 asks data provenance, credential reach and host overrides; check-the-job and
deployed-identity helpers; `holds` read by `promote-gate`.

### 6. L-0618 slice c (tooling PR)

`plugin/crew/tests/sabotage*.py` entries for: `qa_audit_env.py` (G1-G5, E1-E7), `qa_doc.py`'s
no-back-edge guard, `verify_reach.py`, `diagram_check.py` and `diagram_doc.py`. Each was
sabotage-tested by hand when it landed; this makes those mutations permanent. Harness paths:
lands alone, per `CLAUDE.md`.

### 7. G1 points at `--stamp-reach`

After #337 and #372 have both merged: `qa_audit_env.py`'s G1 evidence and
`references/environments.md` say "declare by hand until L-0562 lands". Point them at
`/crew:verify --stamp-reach` instead. One-line change plus its test.

### 8. `qa_doc.py` follows the diagram standard

After #337 and #4: `qa_doc.py`'s `.mmd` files gain `%% Purpose:` lines, and it reports
`diagram_check.py`'s verdict for its diagrams when they are rendered.

### 9. Crew code map refresh

`.crew/codemap/crew.md` says `TRIGGERS` is a 15-entry tuple; #337 adds `qaAuditStale` (16). Refresh
with `/crew:onboard --refresh crew`, never by hand: `.claude/rules/crew.md` is generated from it.

### 10. Diagram standard for the other skills

`skills/mermaid-svg-bitbucket`, `skills/repo-docs` and `skills/terraform-docs-readme` also produce
Mermaid. Owner decision 4: each references the crew-diagrams rules and runs `diagram_check.py` only
where crew is installed, with no hard dependency on crew.

### 11. Owner action: tell the production repositories

The two repositories in the review (repo A, repo B) may have a Stop gate that runs nothing today
(D10). Message to send to each session, once #337 and #372 have merged:

> **crew L-0618: please check your Stop gate.** Crew's Stop gate skips any rule in
> `.crew/verify.json` whose command it cannot classify as local (shell syntax, a remote command, a
> wrapper script) and has no `reach` setting, yet still records the commit as verified.
> 1. Update crew, then run `/crew:init --audit`.
> 2. If check **G1** says rules are SKIPPED on every Stop, run `/crew:verify --stamp-reach`, then
>    decide each listed rule with `--set N=local|network|host`.
> 3. Fix the other gaps under your own tickets; a setup phase with an open gap stays `partial`.
>    Keep the audit output as your acceptance evidence.
