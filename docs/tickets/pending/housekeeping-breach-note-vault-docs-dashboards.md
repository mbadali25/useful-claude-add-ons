# Housekeeping: #679 breach note, vault entries, Configuration Guide refresh, stale dashboards

Priority: unassigned (owner to set).
Status: needs ticket (no T-/L-/C- id yet). Recorded 2026-11-17 from the owner's open-item list. Small items, grouped; split if the owner wants them tracked apart.

## Items

1. #679 breach note. VERIFIED: #679 (L-0888, the verify gate runs a repo's verify map only for a trusted repo, slice 1) is MERGED (head `401a41c5e`, 31 checks pass or skipped). What "the breach" is was not given; the note itself is not written. UNKNOWN: its content and where it goes (the PR, a ticket, the vault).
2. Vault entries L-0951 and L-0954 need updating (owner's request). Not read here: the vault was not opened and what changed is not stated.
3. Configuration Guide refresh after the key PRs merge. Keys: `guards.enabled` (#775, open), `guards.git.allow` (#769, open, VERIFIED title "crew 1.3.82", DIRTY), `verify.stopBudgetSeconds` (#780, open). Two artifacts: the published Claude Docs doc titled "Configuration Guide" and the guide built from `docs/guides/crew/src/` (`build.py`, `config_reference.py`). The repo rule (CLAUDE.md "keep the Configuration Guide current") makes this part of each PR; the PR bodies of #775 and #780 say the published doc was NOT updated from there. Do it after each merge, not before.
4. Retire stale dashboards (artifact ids as given by the owner, not opened here): Crew Fix Plan Status `RcVgoESU3rqZD6mZdoXDud`, Crew Changes Dashboard `6uoJMBdkTmBzD2nxSXt3Yr`, Crew Status Dashboard `P9iKsfrr4txKb8CNhyYEDx`. The old Fixes Boards `Fjx9TpixPjebuH2eos8ftX` and `WoyESjd8997L9cRnY8SwZY` are for the owner to delete through `/artifacts`; an agent does not delete them.
5. Keep the three maintained dashboards current, following `REFRESH.md` in `abs-claude-development` (not read).

## Recommended next step

Do items 1 and 2 once their content is supplied. Do item 3 per PR at merge time. For item 4, confirm each id is stale (read it) before the owner or an agent retires it. Item 5 is recurring.

## Acceptance criteria

- Item 1: a breach note exists, says what happened and what was changed, and is linked from #679.
- Item 2: L-0951 and L-0954 reflect current state.
- Item 3: after each of #775, #769, #780 merges, both the built guide (`build.py --check` and `config_reference.py --check` clean) and the published doc list the key with its default and allowed values.
- Item 4: the three named dashboards are retired; the two old boards are deleted by the owner.
- Item 5: each maintained dashboard shows data newer than the last merge.

## Owner questions

1. What was the #679 breach, and where should the note live?
2. What must L-0951 and L-0954 say?
3. Is the order of dashboard retirement important (any still linked from somewhere)?

## Out of scope

Merging the key PRs; deleting the two old boards (owner action via `/artifacts`).

## Related

#679, #769, #775, #780; `docs/guides/crew/src/`, `plugin/crew/CONFIG.md`.
