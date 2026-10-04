# L-0678: `crew_memory.py migrate` and `restore` - convert existing native memories, previewed and opt-in, and undo it          status: spec   risk: med
Split from T-0084 (slice 3 of 4). Needs T-0084's first slice and L-0677 (`save`) on main. Checked against origin/main `155fe6d8` on 2026-10-04; `crew_memory.py` line numbers are re-read at plan time.

## Intent
`crew_memory.py migrate` previews, and with `--apply` performs, the conversion of every full-text memory in one native memory directory into a vault note plus a pointer, using L-0677's `save` for each file. `crew_memory.py restore` turns one pointer back into full text from its note. Both are opt-in, dry run by default, and neither can leave a dangling pointer or lose a memory's text.

## Design
- **`migrate --memory-dir <dir> --tag <tag> [--tag ...] [--only <file name> ...] [--type <type>] [--project <name>] [--note-dir <vault-relative folder>] [--root <repo>] [--apply] [--json]`.**
  - Lists every `*.md` in the directory except `MEMORY.md`, sorted by name. `--only` narrows to the named files; a name not in the directory is a usage error.
  - Each file is classified with the first slice's parser, then planned with L-0677's `save` planning function (title from `name:`, note at `<note-dir or memories/<project>>/<title>.md`).
  - Preview row: `<action>  <file>  -> <vault>/<note>` or `<action>  <file>  (<reason>)`. Actions: `convert`, `append` (a note with this `memory_id` already exists), `skip: already a pointer`, `skip: <pointer state>` for a pointer that does not resolve, `refuse: <reason>` for anything `save` would refuse (collision, no `name:`, bad note path, ASCII required).
  - Two files that would write the same note path are both `refuse: duplicate note path`.
  - With no writable vault the run prints one line, `nothing to migrate: <reason>`, lists no conversion, and exits 0 for `no vault configured`, 1 otherwise.
  - Dry run exit: 1 when at least one `convert` or `append` is pending or any row is `refuse`, else 0.
  - `--apply`: runs `save`'s apply for each `convert` and `append` row, one file at a time, in name order. A file whose apply fails is reported with `save`'s `kept-full-text` reason and the loop continues. Exit 0 only when no row failed or was refused.
  - A closing count per action, and the reminder that `MEMORY.md` was not edited.
- **`restore --file <memory file> [--root <repo>] [--apply] [--json]`.**
  - The file must be a pointer that `resolve`s; any other state is printed and exits 1 with nothing written (`full-text` exits 0: nothing to do).
  - The restored body is the note's text after its frontmatter, LF-only. The native frontmatter is kept byte-for-byte.
  - Dry run prints the first line and the line count of the body it would write. `--apply` writes through a temp file and `os.replace`, then re-reads the file and confirms it classifies as `full-text`.
  - The vault note is never edited or deleted.
- No state file and no migration log are written; the preview is recomputed from disk each run, which is what makes a re-run a no-op.
- **Skill.** The `crew-memory` section gains "Converting existing memories": run `migrate` with no `--apply`, show the user the table, convert only on their yes, and how to `restore`.

## Exclusions
- No new write path into the vault or the native memory: every write goes through L-0677's `save` functions, or `restore`'s single native-file replace.
- No automatic run: no hook, no SessionStart call, no call from `/crew:init`, `/crew:migrate` or `/crew:upgrade`. (`/crew:migrate` is the 0.20-to-1.0 config move and is not touched.)
- No discovery of memory directories: `--memory-dir` is given by the caller. No "all projects" mode.
- No edit, rename or delete of `MEMORY.md` or of any memory file other than the body replace.
- No delete or edit of a vault note by `restore`. No bulk `restore`.
- No config key. No change under `plugin/obsidian-vault/`.
- No sabotage entry and no edit to `plugin/crew/tests/sabotage*.py` (harness; L-0679).
- No machine name, account name or absolute vault path in any tracked file.

## Evidence
All read at origin/main `155fe6d8` on 2026-10-04.
- The parent direction, `.work/tickets/T-0084/direction.md`: "Migration of existing native memories is opt-in and previewed."
- plugin/obsidian-vault/hooks/scripts/vault_import.py:180 `plan_import` and :227 `apply_actions`: the plan-then-apply shape, per-file statuses and "a re-run is a no-op" behaviour this follows; :321-327 the dry-run exit rule (1 while writes are pending).
- plugin/crew/commands/migrate.md exists and means the 0.20-to-1.0 layout move (`git show origin/main:plugin/crew/commands/migrate.md`, description line), so this subcommand is documented under `crew-memory`, never as `/crew:migrate`.
- A native memory directory on this host holds one `MEMORY.md` and one file per fact (32 files beside the index on 2026-10-04), each with a `name:` line in its frontmatter.
- plugin/crew/tests/crew_fixtures.py:973 `resolve_pwsh`.
- scripts/check-tooling-pr.py:58-87: none of this slice's paths are harness.

## Unknowns
- Whether one tag set for a whole batch is acceptable, or each memory needs its own tags. Default taken: one set per run, and `--only` lets a caller run several batches with different tags. Owner may ask for a per-file mapping; that would be a follow-up.
- Titles that are not valid file names on Windows (`:`, `?`, a trailing dot). Resolved at plan time: such a row is `refuse: title is not a portable file name`, tested with a table of names; the caller converts that file alone with `save --title`.
- A note edited by hand in Obsidian after conversion restores with the edited text. Accepted: the note is the source of truth once a pointer exists.
- The next free crew patch version is set at implement time.

## Size
About 150 added production lines in `plugin/crew/hooks/scripts/crew_memory.py` (migrate about 100, restore about 50). No new parser, no new guard: it composes the first slice's classifier and L-0677's writer. Under the 300-line rule. No harness path.

## Touch
- `plugin/crew/hooks/scripts/crew_memory.py`
- `plugin/crew/tests/test_crew_memory_migrate.py` - new
- `plugin/crew/skills/crew-memory/SKILL.md`
- `plugin/crew/README.md` - section 14
- `plugin/PLUGINS.md` - the crew-memory row and the crew version cell
- `docs/guides/crew/src/memory-and-obsidian.md`
- `docs/guides/crew/**` - the HTML, DOCX and PDF rebuilt by the guide build script
- `.crew/codemap/crew.md`
- `.crew/verify.json` - add the new test file to the crew_memory rule
- `CHANGELOG.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`

Not in Touch, stated: `plugin/crew/CONFIG.md` (no setting); `plugin/crew/commands/migrate.md` (a different feature); `docs/diagrams/` (no box or edge changes).

## Acceptance checks
Commands run from the repo root; pytest goes through the heavy-run wrapper on a memory-bound host. New tests are in `plugin/crew/tests/test_crew_memory_migrate.py`, all under `tmp_path`.
- [ ] The files pass: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_memory.py plugin/crew/tests/test_crew_memory_save.py plugin/crew/tests/test_crew_memory_migrate.py -q`
- [ ] Preview writes nothing (`-k test_migrate_preview_writes_nothing`): the fixture tree's hashes are unchanged; rows are sorted; `MEMORY.md` is not a row; exit 1 with conversions pending.
- [ ] Each action appears for the right file (`-k test_migrate_preview_actions`): one fixture directory holding a full-text file, a resolving pointer, a dangling pointer, a malformed pointer, a file with no `name:`, two files with the same `name:`, and a file whose note collides with a foreign note.
- [ ] Apply converts exactly the previewed rows (`-k test_migrate_apply_matches_the_preview`): every `convert` row is now a pointer that resolves; every `skip` and `refuse` row is byte-identical; `MEMORY.md` is byte-identical.
- [ ] One failure does not stop or undo the rest (`-k test_migrate_continues_past_a_failed_file`): the note write for the second of three files raises; files one and three are converted, file two is byte-identical, exit 1.
- [ ] No vault (`-k test_migrate_without_a_vault_changes_nothing`): no config gives `nothing to migrate` and exit 0; an unavailable primary gives exit 1; the memory directory is byte-identical in both.
- [ ] Re-run is a no-op (`-k test_migrate_twice_is_a_no_op`): a second `--apply` writes nothing and exits 0.
- [ ] `--only` (`-k test_migrate_only_limits_the_run` and `-k test_migrate_only_unknown_name_exits_2`).
- [ ] Portable titles (`-k test_migrate_refuses_unportable_titles`, parametrized over `:`, `?`, `*`, `<`, `|`, a trailing dot, a trailing space, a reserved device name).
- [ ] `restore` round trip (`-k test_restore_round_trips_the_body`): save then restore gives a body equal to the original with LF endings; frontmatter bytes are unchanged; the vault note is byte-identical before and after.
- [ ] `restore` refusals (`-k test_restore_refuses_what_does_not_resolve`, parametrized over `note-missing`, `vault-unavailable`, `vault-unknown`, `malformed`): the native file is byte-identical, exit 1. `full-text` exits 0 and writes nothing.
- [ ] `restore` dry run writes nothing (`-k test_restore_dry_run_writes_nothing`).
- [ ] Both shells (`-k test_migrate_from_bash_and_pwsh`): the preview table is byte-identical from bash and from the resolved pwsh; an absent shell is skipped and named.
- [ ] `(cd plugin/crew && python3 hooks/scripts/_test/validate-prompts.py)` passes.
- [ ] Lint: pylint 10.00 on the changed Python files; ruff reports no new finding against the merge base.
- [ ] `python3 scripts/check-tooling-pr.py` exits 0.
- [ ] Docs: skill, README section 14 and the guide chapter describe `migrate`, its action list, `restore`, and that nothing runs without `--apply`; guide outputs rebuilt (`python3 docs/guides/crew/src/build.py`); `.crew/codemap/crew.md` updated; crew bumped to the next free patch with a CHANGELOG entry; after the commit `python3 scripts/check-marketplace.py` passes.

## Dependencies
Must land first:
- T-0084 (spec, first slice): classifier and `resolve`.
- L-0677 (direction): `save`'s plan and apply functions.

Blocks: L-0679, for the mutations that target `migrate` and `restore`.
Related: T-0083 (direction), T-0048 (spec), T-0046 (in-progress), as in the parent spec.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
