# L-0640: next.md - waiting-on, next, reason, revisit and superseded-by, read into the ticket view          status: spec   risk: med
Split from T-0037 (2026-10-04). Feature PR; lands after L-0639.
## Intent
A ticket folder may hold `next.md` with five optional `key: value` lines: `waiting-on`, `next`, `reason`, `revisit`, `superseded-by`. `crew_ticket_state.read_next` parses it and `view` carries the fields, a `revisit_due` flag and any problems, so L-0550's stops and L-0551's owner list can quote who a ticket waits on and what to do next. A malformed or missing value is reported, never read as "nothing asked".
## Exclusions
- No writer. Nothing in crew creates or edits `next.md` in this ticket, and no command text tells an agent to.
- No `HARNESS` path: no `crew_ticket.py`, no `sabotage*.py` (mutations are L-0641). `python3 scripts/check-tooling-pr.py` must print `tooling-pr: no harness path changed`.
- `next.md` is not part of the contract: `crew_ticket.validate`, the approval digest and the scope guard never read it.
- No autopilot stop, no `/crew:status` change (L-0550, L-0551).
- No new status values and no change to `dependency_state`.
- Read-only: `read_next` and `view` write nothing.
## Evidence
At origin/main `155fe6d8` unless marked.
- `git grep -n "next\.md" origin/main -- plugin/crew/hooks/scripts` returns nothing: there is no reader to extend.
- What stales an approval: `plugin/crew/hooks/scripts/crew_ticket.py:64-75` (only the header status value is normalised), which is why these fields cannot live in spec.md.
- Ticket id shape for `waiting-on` and `superseded-by`: `_TICKET_RE` at `crew_ticket.py:175`, checked by `check_ticket` (`:193-197`).
- `.work/tickets/<id>/` is resolved by `crew_ticket.ticket_dir` (used at `plugin/crew/hooks/scripts/crew_autopilot.py:411`).
- From L-0639 (not on main until it lands): `plugin/crew/hooks/scripts/crew_ticket_state.py` with `view(top, ticket, today)` returning a dict with `problems`, and `plugin/crew/tests/test_ticket_state.py`.
## Unknowns
- Grammar, decided: UTF-8, one `key: value` per line, key case-insensitive, blank lines and lines starting `#` skipped. Unknown keys are ignored (must-allow). A known key given twice is a problem and the value is unset. A file that cannot be read or decoded is a problem, and every field is unset, which callers must treat as "cannot tell".
- Values, decided: `waiting-on` is `owner`, `agent`, `external` or a ticket id; anything else is a problem. `revisit` is `YYYY-MM-DD`; anything else is a problem and `revisit_due` is `None` (not False). `superseded-by` is a ticket id. `next` and `reason` are free text, one line, clipped to 200 characters for display.
- `revisit_due`: True when `revisit <= today`, False when later, None when absent or unparsable. `today` is a parameter (a `datetime.date`), defaulting to the local date, so tests are deterministic.
- A gating status of `needs-owner` with no `next:` adds the problem "needs-owner: cannot tell what is asked (no next: in next.md)". A `superseded` gate with no `superseded-by:` adds a matching problem. Each has a must-block test.
- Symlinked `next.md` pointing outside the ticket folder: read is refused with a problem (resolve by a test using `os.path.realpath`). Accepted as low risk since the file is local state.
- Version: one patch above origin/main's at land time.
## Touch
- `plugin/crew/hooks/scripts/crew_ticket_state.py`
- `plugin/crew/tests/test_ticket_state.py`
- `plugin/crew/README.md`
- `plugin/crew/BUDGETS.md`
- `docs/guides/crew/**` - guide sources and the rebuilt HTML, DOCX and PDF
- `docs/diagrams/**`
- `.crew/verify.json`
- `.crew/codemap/**`
- `.claude/rules/**`
- `graphify-out/**`
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
## Acceptance checks
- [ ] Must-block in `test_ticket_state.py`: `test_needs_owner_without_next_says_cannot_tell`, `test_superseded_without_successor_is_reported`, `test_bad_waiting_on_is_reported` (`waiting-on: someone`), `test_bad_revisit_date_is_listed` (`revisit_due is None`, problem present), `test_duplicate_key_is_reported`, `test_unreadable_next_md_is_reported` (invalid UTF-8 bytes), `test_next_md_symlink_out_of_the_folder_is_refused`.
- [ ] Must-allow: `test_next_md_fields_are_read` (all five keys, an unknown key ignored), `test_no_next_md_has_no_problems` (a ticket with no gating status), `test_hold_revisit_in_the_future_is_not_due`, `test_hold_revisit_today_is_due`, `test_waiting_on_a_ticket_id`.
- [ ] `test_view_is_read_only` (from L-0639) still passes with a `next.md` present. Command for all three checks: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_ticket_state.py -q` (the verify rule L-0639 adds; its `seconds` is re-measured if the run time changes).
- [ ] Docs: README's Ticket statuses section gains a `next.md` paragraph: the five keys, allowed values, that it is not hashed and not validated by `/crew:approve`, and that nothing writes it automatically. The crew guide source that describes the ticket folder lists `next.md`, and `python3 docs/guides/crew/src/build.py` is re-run. `python3 plugin/crew/hooks/scripts/crew_refresh_check.py --root . --ticket <id>` prints every line `fresh`.
- [ ] `python3 scripts/check-tooling-pr.py` prints `tooling-pr: no harness path changed`; `python3 scripts/check-marketplace.py` passes after the one-patch crew bump in the three version files and a CHANGELOG entry; `python3 scripts/gate-runner.py` is green, with the suites that ran named in the PR body.
## Dependencies
- L-0639 (must be merged first): the module and `view`.
- T-0037 (ready; transitively): status tuples.
Blocks: L-0641, L-0550 (hold reason/revisit, needs-owner `next:`, `superseded-by`), L-0551 (owner list actions).
## Size
About 75 added production lines in `crew_ticket_state.py`: `read_next` 45, the `view` join and `revisit_due` 20, constants 10. One new parser.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
