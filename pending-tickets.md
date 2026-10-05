# Pending tickets

Work found while building L-0618 (crew QA standards), waiting for a ticket ID. The owner's ticket
agent creates each ticket and writes its ID in the **Ticket** column; the implementing session works
from this file and updates **Status** as work lands.

Status values: `needs ticket`, `ready`, `in progress`, `in review (PR #n)`, `blocked: <why>`,
`done (PR #n)`, `owner action`.

Last updated: 2026-10-05 (feature rush 1.2.0 section). Previously 2026-10-03. Tracks L-0618's follow-ups, this session's PRs (#337, #372, #374, #375) and the handed-over PRs #350-#373. Other open PRs (#376, #377, #378, #379, #380 and #274-#349 outside that range) belong to other sessions and appear here only where they block or are blocked by a tracked PR.

## Feature rush 1.2.0 (PRs #324-#508, cloud session `crew-rush-2`, started 2026-10-05)

Owner instruction 2026-10-05. Every PR in #324-#508 is grouped by dependency and files touched, built
or ported into a group branch `rush/<group>` that targets `release/1.2.0` (cut from main `e84a8bfe`).
`release/1.2.0` lands on main as one PR after the other session's 1.1.0 (#512). The two harness
lanes land alone (owner rule T-0087); the last one sets crew **1.2.0**. Each group PR
merges only on a Codex review (`gpt-6-sol`, high reasoning) with 0 BLOCK and 0 FIX, plus green CI.
New tickets minted by this rush start at **C-0020**; the owner's local session creates them from the
"New tickets" table below and writes the real ID back.

### Groups (10, owner 2026-10-05)

| # | Group | Branch | PRs | Placeholder crew | Status |
|---|---|---|---|---|---|
| 0 | G0 coord + wave (prerequisites, lands first) | `rush/g0-coord-wave` | T-0030 (`T-0030-coord`), T-0029 (`T-0029-wave`), feature halves; harness halves go to H1/H2 | 1.1.9 | building |
| 1 | G1 ports: tracker, gitignore, graph, migrate | `rush/g1-ports` | #478, #464, #376, #346, #367, #370 | 1.1.1 | building |
| 2 | G1b ports: reference, hygiene, help, archive, CI | `rush/g1b-ports` | #345, #349, #359, #341, #324 | 1.1.6 | building |
| 3 | G2 autopilot ports | `rush/g2-autopilot` | #354, #395, #342, #358, #369, #363, #365, #366 | 1.1.2 | building |
| 4 | G3 contracts / ticket state | `rush/g3-contracts` | #408, #412, #410, #409, #411 | 1.1.3 | building |
| 5 | G3b bridge / recall / config / graph | `rush/g3b-bridge` | #434, #437, #442, #425, #414, #447, #455 | 1.1.7 | building |
| 6 | G4 deploy / promote-gate | `rush/g4-deploy` | #336 (feature half), #467, #428, #432, #436, #439, #445, #471, #473, #488, #452 | 1.1.4 | building |
| 7 | G5 platform / CI / docs | `rush/g5-platform` | #441, #458, #468, #476, #474, #480, #454, #465, #477 | 1.1.5 | building |
| 7b | G7 development standards sets | `rush/g7-standards` | L-0519, then L-0532, L-0533, L-0534, L-0535, L-0536, L-0537, L-0538 | next free | waiting on PRs |
| 8 | G6 autopilot builds, sleep, goals | `rush/g6-autopilot-builds` | #485, #486, #397, #426, #443, #449, #446, #453, #483, #444, #431, #435, then L-0541 (no PR yet), #459, #463, #469 | next free | after G2 lands (T-0012) |
| 7c | G8 late tooling and tracker | `rush/g8-late` | L-0517, L-0511, L-0530 | next free | waiting on PRs |
| 9 | H1 harness ports (to main, alone) | `rush/h1-harness` | #418, #461, #422, #333, #340, #331, #343, #402, #406, #490 | 1.1.8 | building |
| 9b | H3 review-harness tickets (to main, alone) | `rush/h3-review` | L-0527, L-0528, L-0518, L-0514, T-0033 | next free | waiting on PRs |
| 10 | H2 harness sabotage entries (to main, alone, last) | `rush/h2-sabotage` | #472, #413, #415, #417, #419, #423, #424, #429, #430, #438, #440, #448, #457, #460, #466, #470, #482, #484, #487, harness half of #336 | **1.2.0** | after release lands |
| - | Last | | #479 (T-0507 code-map refresh) | | regenerated at the end |

Groups 1-8 target `release/1.2.0`; 9 and 10 target `main`, each alone.

Versions: no bump when a source PR folds into its group; each merge into `release/1.2.0` takes the
next free 1.1.x in landing order; `release/1.2.0` -> main takes the next 1.1.x; H2, the last merge,
sets 1.2.0. The drift check dates a version from its first commit, so every re-merge re-bumps.

### Added by the owner mid-rush (2026-10-05, PRs being opened)

Placed by what each ticket says it touches; re-placed when its PR shows the real file list. Owner 2026-10-05: add groups as needed, so the late arrivals get their own groups (G7, G8, H3) instead of joining groups already mid-build.

| Ticket | Title (short) | Lane | Why |
|---|---|---|---|
| L-0527 | Kimi review launch in the review harness (tooling half of T-0028) | H3 | review harness |
| L-0528 | `review_run.py` EXIT_UNVERIFIED and EXIT_PROBE_LIMITED both 5 | H3 | `review_*.py` is HARNESS |
| L-0518 | T-0085 round-4 findings in crew-standards / review_run self-check gate | H3 | review_run |
| L-0514 | INCOMPLETE review rounds retry automatically after a tool-failure refund | H3 | review loop |
| T-0033 | version-only re-bump does not stale a review receipt | H3 | review receipt hash |
| L-0525 | sabotage suite: 13 vacuous entries, 1 unproven, cloud-guard r1 OOM | H2 | sabotage suite |
| L-0519 | reconcile crew-standards with crew-qa-standards | G7 | lands first in G7: the language sets below build on one reconciled source |
| L-0532 | SQL standards set (MySQL/MariaDB, MSSQL, PostgreSQL), T-0086 slice | G7 | `crew-standards/references/` + index |
| L-0533 | PHP standards set, T-0086 slice | G7 | same files |
| L-0534 | PowerShell standards set, T-0086 slice | G7 | same files |
| L-0535 | .NET standards set, T-0086 slice | G7 | same files |
| L-0536 | Terraform standards set, T-0086 slice | G7 | same files |
| L-0537 | Node.js standards set, T-0086 slice | G7 | same files |
| L-0538 | Angular 2+ standards set (AngularJS 1.x out of scope, owner 2026-09-28), T-0086 slice | G7 | same files |
| L-0530 | crew_tracker maps merged/approved/new/land-blocked to lanes | G8 | `crew_tracker.py`, with #464 T-0071 |
| L-0517 | heavy-run logs each lane's slot wait | G8 | gate-runner / heavy-run tooling |
| L-0511 | version bump and artifact refresh happen once at land | G8 | release bookkeeping; H1 if it touches HARNESS |
| L-0515 | dependency-aware lane scheduling (folded into L-0520) | G6 | autopilot lanes; L-0520 is on main |

### Blocked inside the rush

| PRs | Blocked by | Note |
|---|---|---|
| L-0541 | its direction/spec is only in the owner's local ticket folder | owner 2026-10-05: ready to build. Owner's local session: publish `docs/tickets/L-0541/` to branch `L-0541-build` (as the other handoffs). If it is not there when G6 reaches it, the builder drafts a spec from T-0012's split and T-0056's dependency rows, has Codex review the spec, then builds |
| #408 T-0031, #410 L-0633, #412 L-0634, #434 T-0032, #437 L-0636, #442 L-0637; H2: #415 L-0635, #448 L-0638 | **T-0030** (`crew_coord.py`) | Pushed 2026-10-05 as `T-0030-coord`; ported in G0. The blocked PRs un-skip once G0 lands in `release/1.2.0` |
| #410 L-0633, #412 L-0634, #442 L-0637, #443 T-0067 (G6); H2: #415, #448 | **T-0029** (`crew_wave.py`, the autopilot wave) | Pushed 2026-10-05 as `T-0029-wave`; ported in G0, after T-0030. Same un-skip rule |
| #445 L-0648 | L-0564 (ordering only) | promote-gate review follow-ups in the same files; not a hard blocker, whichever lands second merges main |
| #490 L-0690 | L-0609 (constraint only) | wallclock flake in `test_ps1_python_probe.py`: new tests must not assert an upper time bound. Not a hard blocker |
| #391 | n/a | the landing session's notes branch; not touched by this rush |

### New tickets (C-0020 onward)

| ID | Title | From | Blocked by | Status |
|---|---|---|---|---|
| _filled as group reports arrive_ | | | | |

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
| #350 | T-0061 | merged with main, verified; in review. Merge after #378 (harness half, 1.0.181) | #378 | 1.0.184 |
| #351 | T-0066 | part 1 merged with main, verified; in review | | 1.0.185 |
| #355 | T-0013 | merged with main, verified; in review | | 1.0.186 |
| #360 | T-0048 | merged with main, verified; in review | | 1.0.200 |
| #368 | T-0063 | merged with main, verified; in review. Guide DOCX/PDF need a LibreOffice rebuild | | 1.0.201 |
| #371 | T-0100 | merged with main, verified; harness PR, no split needed (tooling-pr OK). Contains #378; merge after it | #378 | 1.0.202 |
| #337 | L-0618 | in review | | 1.0.204 |
| #375 | row 4 | in review | | 1.0.205 |
| #372 | L-0562 | in review | | 1.0.203 |
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
| T-0013 (#355) | `sabotage_resume_typing.py` registered in `sabotage.py` | needs ticket |
| T-0063 (#368) | Its 16 sabotage mutations registered in `sabotage.py` | needs ticket |

**Re-bumps:** merging `main` always needs a new crew version set after the merge (the drift check dates a version from the first commit that declared it). 1.0.180 -> 1.0.199 (#372), 1.0.183 -> 1.0.200 (#360), 1.0.182 -> 1.0.201 (#368), 1.0.166 -> 1.0.202 (#371). Then main took #334 (1.0.163), so the front of the merge order re-merged again: #372 -> 1.0.203, #337 -> 1.0.204, #375 -> 1.0.205. Next free: 1.0.206.

**Policy:** when `main` moves, only the PRs at the front of the merge order are re-merged and re-bumped; the rest are re-merged when they reach the front, so version numbers and CI runs are not burned on every landing.

**Not started anywhere (no branch, nothing on `main`):** T-0016, T-0037 and T-0049. Together they block
#356, #363, #364, #365 and #366. Owner's ticket agent: confirm that each ticket exists and is ready to
build, or create it.

## Dependency map (2026-10-03)

Merge left to right; nothing in a chain merges before the item to its left. Checked against each
PR's handoff note and against `main`'s history.

**Hard dependencies (the wrong order breaks something):**

| Chain | Why |
|---|---|
| #378 (T-0061 harness) -> #350 (T-0061 feature) | #350's docs describe exit codes and `activate`, which exist only once #378 lands |
| #378 -> #371 (T-0100) | #371 already contains #378's commits |
| #379 (T-0019) -> #354 (T-0012) | T-0012 uses T-0019's ticket mint |
| #379 + T-0037 -> #364 (T-0052) -> #365 (T-0058) | T-0058 also needs #354. T-0037 has no branch or PR yet |
| #353 (T-0011) + T-0037 + #364 -> #366 (T-0059) | T-0059 ships slices through T-0011's ship policy |
| #362 (T-0051) + T-0049 -> #363 (T-0060) | T-0060 is part 2 of the notify rebuild. T-0049 has no branch or PR yet |
| T-0016 -> #356 (T-0017) | T-0016 has no branch or PR yet |
| #344 (T-0035) -> #345 (T-0036) | T-0036 uses T-0035's diagram generator |

**Soft dependencies (the same files or behaviour, no breakage):**

| Pair | Overlap | Order |
|---|---|---|
| #337 (L-0618) and #370 (T-0038) | #337 adds step 5c to `/crew:upgrade`; T-0038 makes that command a stub | #337 first. T-0038 carries step 5c into `/crew:migrate` |
| #375 (diagrams) and #344 (T-0035) | Both generate `docs/diagrams/README.md` | #375 first. T-0035 builds on its checker (owner decision pending) |
| #372 + #337, then row 7 | G1 should point at `--stamp-reach` | Row 7 after both land |

**No open dependency (already on `main`):**

| PR | Depended on | On `main` as |
|---|---|---|
| #339 L-0563 | L-0516 | #298 |
| #340 L-0526 | L-0520 | #287 |
| #347 T-0047, #369 T-0044 | T-0005 | #241 |
| #352, #357, #358, #359 | T-0004, T-0008, T-0018, T-0021, T-0023, T-0024, T-0042 | all merged |
| #351, #355, #360, #368, #361 | T-0006 or none | merged, or none |

#338, #341, #342, #343, #346, #348, #349, #376, #377, #336, #333, #331, #324, #275 and #274 name no
dependency in their handoff notes (headers checked, not their full specs).

**Unblock first:** T-0016, T-0037 and T-0049 have no branch and together block five PRs; T-0019 (#379)
blocks three more.

## Owner decisions (2026-10-03)

| # | Question | Decision |
|---|---|---|
| 1 | Merge order for the open PRs | #374, then #373, #372, #337, #375 (as decided; #373 has since merged). Superseded 2026-10-03 by the owner's review-gated merge approval: #372, #337, #375, #378, #350, #371, #351, #355, #360, #368, then #374 last. Each crew PR is re-merged with `main` and re-bumped when it reaches the front |
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
