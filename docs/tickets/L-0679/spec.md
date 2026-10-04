# L-0679: sabotage entries for `crew_memory.py` (tooling-only PR)          status: spec   risk: low
Split from T-0084 (slice 4 of 4). Needs T-0084's first slice, L-0677 and L-0678 on main. Checked against origin/main `155fe6d8` on 2026-10-04. The exact anchor strings are taken from `crew_memory.py` as merged, at plan time.

## Intent
Each fail-closed rule in `crew_memory.py` gets a sabotage mutation that removes it and names the test that must go red. The entries live in `plugin/crew/tests/sabotage_context.py` and run through the existing `plugin/crew/tests/sabotage.py` runner. This PR changes only the harness and what may ride along with it.

## Design
- A new tuple `MEMORY_MUTATIONS` in `sabotage_context.py`, in the module's existing five-field shape (label, file, exact anchor text, replacement text, test id), added into `CONTEXT_MUTATIONS` so `sabotage.py` needs no edit.
- A new constant `MEMORY = os.path.join(SCRIPTS, "crew_memory.py")` beside `RECALL`.
- The mutations, one per rule. Each replacement is the same length class as its anchor where practical, and never size-preserving with a same-second restore (the stale-`.pyc` trap).

  | # | mutation | must turn red |
  |---|---|---|
  | a | the path grammar accepts a leading `/` | `test_crew_memory.py::test_pointer_grammar_refuses` |
  | b | the path grammar accepts a drive prefix or a backslash | same test, its drive and backslash cases |
  | c | the `..` segment check is dropped | same test, its `..` case |
  | d | a `vault:` line that fails the grammar classifies as `full-text` | `test_crew_memory.py::test_pointer_grammar_refuses` (state assertion) |
  | e | an unavailable named vault falls through to another configured vault | `test_crew_memory.py::test_unavailable_vault_is_not_substituted` |
  | f | an unparseable config reads as "no vaults" | `test_crew_memory.py::test_unparseable_config_is_not_no_vaults` |
  | g | the symlink-component check is dropped | `test_crew_memory.py::test_symlinked_component_is_outside_vault` |
  | h | `save` writes the pointer before the note | `test_crew_memory_save.py`, the note-write `OSError` case |
  | i | `save` skips the read-back before writing the pointer | `test_crew_memory_save.py`, the read-back case |
  | j | `save` opens an existing note for write (`"x"` becomes `"w"`) | `test_crew_memory_save.py`, the `collision` case |
  | k | `save` ignores `memory_id` when a note exists | same `collision` case, foreign-note variant |
  | l | the writer takes a `recall` vault when the primary is unavailable | `test_crew_memory_save.py`, the unavailable-primary case |
  | m | `save` drops `newline="\n"` on the note write | `test_crew_memory_save.py::test_outputs_are_lf_only` (red on Windows; on POSIX it reads STILL GREEN and is listed as platform-skipped, never as passed) |
  | n | `migrate --apply` stops at the first failed file | `test_crew_memory_migrate.py::test_migrate_continues_past_a_failed_file` |
  | o | `migrate` converts a row the preview refused | `test_crew_memory_migrate.py::test_migrate_apply_matches_the_preview` |
  | p | `restore` proceeds on a pointer that does not resolve | `test_crew_memory_migrate.py::test_restore_refuses_what_does_not_resolve` |

- A presence test, `plugin/crew/tests/test_crew_memory_sabotage_anchors.py::test_every_memory_sabotage_anchor_is_present_exactly_once`, reads `crew_memory.py` and asserts each anchor occurs exactly once, so a later edit that moves an anchor fails a fast test instead of silently skipping a mutation.
- Where a mutation survives (the named test stays green), the fix is a stronger test. A test file under `plugin/crew/tests/` may ride along; a change to `crew_memory.py` may not, and goes back to a feature PR.

## Exclusions
- No change to `plugin/crew/hooks/scripts/crew_memory.py` or any other production file, prompt or skill. This is the harness-lands-alone rule.
- No edit to `plugin/crew/tests/sabotage.py` (3400 of 3400 lines).
- No new sabotage module unless `sabotage.py` has room by then (direction, option 2).
- No change to the sabotage runner's behaviour, timeouts or restore logic; nothing of T-0080 or L-0608.
- No version bump of crew unless the gate asks for one: a tests-only change under `plugin/crew/` still counts as plugin content for `check-marketplace.py`'s drift check, so the bump and CHANGELOG entry are in Touch.

## Evidence
All read at origin/main `155fe6d8` on 2026-10-04.
- scripts/check-tooling-pr.py:58-87 `HARNESS` lists `plugin/crew/tests/sabotage*.py`; :99-118 `ALONGSIDE` lets `plugin/crew/tests/**`, the version files, `CHANGELOG.md`, `plugin/crew/BUDGETS.md`, `docs/**`, `.crew/codemap/**` and `.crew/verify.json` ride along.
- plugin/crew/tests/sabotage.py is 3400 lines; `.pylintrc:140` `max-module-lines=3400`. sabotage.py:70 `from sabotage_context import CONTEXT_MUTATIONS`; :3064 folds it into `MUTATIONS`.
- plugin/crew/tests/sabotage_context.py (203 lines): :11-13 `SCRIPTS`, `CONTEXT`, `RECALL`; its docstring says it is kept apart because `sabotage.py` sits at the module limit; the tuple shape is (label, file, anchor, replacement, test id); the comment at the first tuple records that a `.ps1` mutation on a host without pwsh reads STILL GREEN.
- Repo CLAUDE.md, "Stop and ask": a guard that can block needs must-block and must-allow cases, sabotage-tested. `crew_memory.py` is not a hook, but its refusals protect user files, and the parent direction asks for sabotage by name.
- Memory note on this host's past incident: a size-preserving mutation restored in the same second defeats `.pyc` invalidation; check the `.pyc` timestamp before blaming another writer.
- L-0608 (in-progress) is making platform-skipped mutations fail closed; mutation m follows whatever shape it lands.

## Unknowns
- The anchor strings: they do not exist until the three feature slices merge. Resolved at plan time from the merged file.
- Whether L-0608 lands first and changes how a platform-skipped mutation is declared. Resolved by re-reading `sabotage.py` and L-0608's state at plan time.
- The full sabotage run is heavy on a memory-bound host. Resolved by running only this module's entries through the runner's selection option if it has one at that time, and the whole run in CI; say in the PR body which was run where.

## Size
0 production lines. About 90 lines in `sabotage_context.py` and about 30 in the anchor test. One PR, tooling-only.

## Touch
- `plugin/crew/tests/sabotage_context.py`
- `plugin/crew/tests/test_crew_memory_sabotage_anchors.py` - new
- `plugin/crew/tests/test_crew_memory.py` - only to strengthen a test a mutation survived
- `plugin/crew/tests/test_crew_memory_save.py` - same
- `plugin/crew/tests/test_crew_memory_migrate.py` - same
- `.crew/verify.json` - add sabotage_context.py and the anchor test to the crew_memory rule's paths and run
- `.crew/codemap/verification-harness.md`
- `CHANGELOG.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `plugin/PLUGINS.md` - the crew version cell
- `.claude-plugin/marketplace.json`

Docs: none beyond the code map and CHANGELOG - no behaviour a user sees changes.

## Acceptance checks
Commands run from the repo root; heavy runs go through the heavy-run wrapper on a memory-bound host.
- [ ] Every anchor is present exactly once: `python3 -m pytest plugin/crew/tests/test_crew_memory_sabotage_anchors.py -q`
- [ ] Each of the mutations a to p goes RED on its named test through the runner: `python3 plugin/crew/tests/sabotage.py`. Mutation m on a POSIX host is reported as platform-skipped, by name, and not counted as red.
- [ ] After the run every mutated file is byte-identical to its committed copy: `git status --porcelain plugin/crew/hooks/scripts/` prints nothing.
- [ ] The existing context mutations still go red (same run), and `python3 -m pytest plugin/crew/tests/test_sabotage_harness.py -q` passes.
- [ ] The three memory test files still pass: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_memory.py plugin/crew/tests/test_crew_memory_save.py plugin/crew/tests/test_crew_memory_migrate.py -q`
- [ ] Tooling-only: `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK`, and `git diff --name-only origin/main...HEAD -- plugin/crew/hooks plugin/crew/skills plugin/crew/commands` prints nothing.
- [ ] `sabotage.py` is untouched: `git diff --stat origin/main...HEAD -- plugin/crew/tests/sabotage.py` prints nothing.
- [ ] Lint: pylint 10.00 on the changed files; ruff reports no new finding against the merge base.
- [ ] `.crew/codemap/verification-harness.md` lists the memory mutations; crew is bumped to the next free patch with a CHANGELOG entry; after the commit `python3 scripts/check-marketplace.py` passes.

## Dependencies
Must land first:
- T-0084 (spec, first slice): mutations a to g.
- L-0677 (direction): mutations h to m.
- L-0678 (direction): mutations n to p.
- T-0087 (merged): the tooling-PRs-land-alone rule and `check-tooling-pr.py`.

Related, re-check before planning: L-0608 (in-progress; platform-skipped mutations fail closed), T-0080 (direction; sabotage harness memory bound).
Blocks: nothing.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
