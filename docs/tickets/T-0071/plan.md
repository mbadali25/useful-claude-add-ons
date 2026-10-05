# T-0071 plan          status: planned   risk: high

Written by the implementing session (feature rush 1.2.0, group g1-ports) against
`release/1.2.0` after T-0081 (#478) was merged into the branch. Every anchor the spec names
was re-checked there: `normal_url`, `_local_path`, `repo_id`, `_CHECKED`, `_BOX`,
`_checkbox`, `_NOTE_REPO_ID`, `_card_owner`, `_foreign`, `_obsidian_move` all still hold the
spec's quoted text; only their line numbers moved (T-0081 added the vault walk above them).

## Steps (test-first: each test is run red before its fix)

1. Tests in `plugin/crew/tests/test_crew_tracker.py`, one section `T-0071` at the end:
   `test_origins_differing_only_in_case_are_two_repos`, `test_repo_id_folds_only_scheme_and_host`,
   `test_a_lowercased_old_note_is_refused_with_the_fix`, `test_file_url_authority_is_not_path_text`,
   `test_file_url_drive_prefix_by_platform`, `test_overlapping_moves_leave_board_and_index_agreeing`,
   `test_board_is_not_moved_when_index_cannot_be_read_at_write_time`, `test_note_repo_id_quote_*`,
   `test_checkbox_without_a_space_is_repaired`. `test_repo_id_normalises_the_origin_url` and
   `test_note_records_repo_id_without_credentials` move to the case-preserving ids.
   `plugin/crew/tests/test_lifecycle_commands.py` gains `test_fix_mints_through_mcp_under_jira_and_sdp`.
2. Fix 1: `normal_url` folds the scheme and the host (with port) only; scp-style folds the host.
   `_foreign` gains the old-note clause when the note's id equals this repo's id case-folded.
3. Fix 2: a pure `_file_url_path(url, windows)` behind `_local_path`.
4. Fix 3: `_obsidian_move`'s `edit` re-reads INDEX (`_files_read`) and binds `key` to the lane
   for the status INDEX holds; unreadable or unknown -> `could not tell where INDEX has ...`.
5. Fix 4: `_NOTE_REPO_ID` strips only a matched pair of quotes; `_card_owner` keeps its 3-tuple.
6. Fix 6: `_BOX` and `_CHECKED` need a space, tab or line end after the marker; `_checkbox`
   repairs a glued marker.
7. Fix 5: `commands/fix.md` step 1 resolves the tracker kind first and creates through MCP
   under Jira and ServiceDesk Plus.
8. Docs: README 13c, the guide's "Whose card it is" and troubleshooting, the code map,
   CHANGELOG (flagged breaking for notes written with a mixed-case origin), guide rebuild.

Every sabotage anchor (`test_every_tracker_sabotage_anchor_is_present_exactly_once`) stays
byte-identical; `sabotage_tracker.py` and `crew_ticket.py` are not edited. New mutations are
L-0669.
