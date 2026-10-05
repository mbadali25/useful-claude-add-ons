# Cloud handoff: L-0538

**Angular 2+ development standards set (T-0086 slice; set `NG`, AngularJS 1.x out of scope)**

Handed to a cloud session on 2026-10-05 by owner instruction (orchestrated spec run). Do not pick up locally.

- **Role:** child of T-0086 (per-language standards), slice 8 of 8 (Python landed as #282).
- **INDEX status:** spec (direction and spec approved for hand-off 2026-10-05; plan to be written by the implementing session)
- **Branch:** `L-0538-build`, new from origin/main `a555ff37`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0538/direction.md`, `spec.md`, `HANDOFF.md`, `research-angular.md` (copy of T-0086's
  machine-local Angular research), `changesets-angular.txt` (the change-set count, taken on the owner's host)
- **Size:** 0 production lines. About 60 lines of new standards Markdown, 45 in `stack-angular`, 30 test lines, doc rows.
- **Harness:** no. `plugin/crew/tests/sabotage*.py` is HARNESS, so the NG sabotage entries are a separate tooling-only follow-up.
- **Risk:** medium (every Angular app change in every repo gains a self-check row).

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0085 | merged (#269) | The loader, gate and self-check this set plugs into. |
| T-0086 | merged (#282) | The Python slice: the pattern, the parametrised stack-set tests, the change-set definition. |
| L-0532..L-0537 | not started | Sibling slices. Independent content, but they edit the same SKILL.md paragraph, README paragraph, PLUGINS.md row and BUDGETS.md claim; land one at a time through the merge train. |
| L-0539 | not merged | Only matters if sabotage entries ride along; they do not here. |

This ticket blocks the NG sabotage follow-up (to be minted by the coordinator).

## Read before writing code

- **The prefix is `NG`, not `ANGULAR`.** `crew_standards.py:82-84` accepts 2-6 capital letters; `ANGULAR` is 7. Keep the
  research numbers (`ANGULAR-07` -> `NG-07`). Do not touch the loader.
- **One rule ships: NG-07.** The count is in `changesets-angular.txt`. It was taken from the private repos
  `solomon/aws-shared-infrastructure` and `solomon/aws-managed-services`, which this session cannot open. Treat the file
  as the record; do not invent change sets. NG-07's text is `research-angular.md:355-396`.
- **Follow `references/python.md` and `stack-python/SKILL.md` exactly** for the header paragraph (what a change set is),
  the Change sets line, Earned by citation shape and the Candidate section. Cite `aws-shared-infrastructure@<sha>` with
  the quoted message, never a `/repos/` path or a vault note (two tests forbid them).
- NG-07 has no Angular doc for its first half. Ship no Source, or only the route-guards "server-side" sentence, fetched raw
  and string-matched whole.
- `stack-angular`'s AngularJS section is not edited.
- No plan.md is published. Write the plan first.

## Open questions for the owner (recommended option taken)

- Prefix `NG` instead of widening the loader to fit `ANGULAR` (default taken; PowerShell and Terraform will face the same).
- Whether `f774865` "(I2)" counts as a reviewed change set (default: yes, as Important #2). If rejected and AMS PR #480 is
  rejected too, NG-07 falls to two and the slice ships candidates only, no set file.
- ANGULAR-18 stays an Angular candidate rather than moving to the Node.js slice (default taken).

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline,
doc updates for `plugin/crew` changes, BUDGETS.md re-measure), run `python3 scripts/check-marketplace.py` after the commit,
state "Docs: guides/ADR/diagrams none - they name no set" in the PR body, and remove `docs/tickets/L-0538/` in the final PR
unless the owner wants it kept.
