# L-0677: `crew_memory.py save` - write the vault note, then turn the native memory into a pointer          status: spec   risk: med
Split from T-0084 (slice 2 of 4). Needs T-0084's first slice (the pointer format and `resolve`) on main. Checked against origin/main `155fe6d8` on 2026-10-04; line numbers in `crew_memory.py` do not exist yet and are re-read at plan time.

## Intent
`crew_memory.py save` takes a native memory file that holds its full text, writes or updates one note in the host's writable vault under the vault's six-key frontmatter contract, confirms the note is on disk, and only then replaces the native file's body with the pointer line. When no vault is writable, or anything is refused, the native file keeps its full text byte-for-byte and the reason is printed. A dangling pointer is never written.

## Design
- **CLI.** `crew_memory.py save --file <memory file> --tag <tag> [--tag ...] [--title <title>] [--note <vault-relative path>] [--type <type>] [--project <name>] [--root <repo>] [--apply] [--json]`.
  - Dry run by default: prints the plan (vault name, note path, `create` or `append`, the pointer line) and writes nothing, not even a directory. Exit 1 while a write is pending, as `obsidian-vault`'s `import` does.
  - `--title` defaults to the frontmatter `name:` value of the memory file, read by a single-line match (`^name:\s*(.+)$` inside the frontmatter, surrounding quotes stripped); with no such line and no `--title`, usage error.
  - `--note` defaults to `memories/<project>/<title>.md`; `--project` defaults to the repository directory name of `--root`. `--note` goes through the first slice's path grammar; a path that fails it is refused.
  - `--type` defaults to `concept` and must be one of `concept`, `decision`, `source`, `meta`, `project-index`.
  - At least one `--tag`; each matches `[a-z0-9][a-z0-9/_-]*`.
- **Writable vault.** From the machine's Obsidian config: with roles in use, the single `role: primary` entry (zero or several is a refusal); without roles, the entry with `default: true`, else the first. Without an Obsidian config, the name `memory` at the crew config's `memory.vaultPath`. The path must be a directory containing `.obsidian/`. An unavailable vault is a refusal; no other vault is used instead. This is the rule in `obsidian_common.writer_vault`, restated in crew (crew does not import the other plugin).
- **Note text**, computed in full before any file is opened:
  - frontmatter keys in this order: `type`, `title` (JSON-quoted, byte-identical to the note's file name stem), `created`, `updated` (both today, `YYYY-MM-DD`, UTC), `status: seed`, `tags` (one `  - tag` line each), `project`, `memory_id` (the native file's stem, JSON-quoted);
  - body: the native memory's body, line endings normalised to LF, with no absolute path added by crew.
- **Create or append.**
  - Note absent: exclusive create (`open(..., "x", newline="\n")`) after `os.makedirs`; containment is checked before and after `makedirs`.
  - Note present with the same `memory_id`: append `\n## Update <today>\n\n<body>\n`, and replace the `updated:` line. `created:` is untouched. Written through a temp file in the same directory and `os.replace`. If the body to append is already the note's last passage, nothing is written (`unchanged`).
  - Note present with another `memory_id`, or none: refused as `collision`; nothing is written.
- **ASCII-only vaults.** When the Obsidian config has `guard.asciiOnly: true` and the title, tags or body hold a non-ASCII character, refuse as `ascii-required`. Crew does not transliterate.
- **Pointer write.** After the note write, read the note back and run the first slice's `resolve` logic on the pointer about to be written; only on `resolved` is the native file rewritten: frontmatter bytes unchanged, body = the pointer line plus one `\n`. Temp file in the same directory, then `os.replace`.
- **A file that is already a pointer** is not rewritten: `resolved` prints `already a pointer` and exits 0; any other state prints that state and exits 1.
- **Outcome states and exits.**

  | state | native file | exit |
  |---|---|---|
  | `pointer-written` | body replaced | 0 |
  | `already-pointer` | untouched | 0 |
  | `kept-full-text: no vault configured` | untouched | 0 |
  | `kept-full-text: <vault unavailable / no primary / several primaries / not a vault>` | untouched | 1 |
  | `kept-full-text: collision`, `ascii-required`, `outside-vault`, `bad-note-path` | untouched | 1 |
  | `kept-full-text: note not readable after write` | untouched | 1 |
  | `malformed`, `unreadable` (from the first slice) | untouched | 1 |

  Every `kept-full-text` line names the reason. `no vault configured` exits 0 because it is the normal state on a machine without Obsidian.
- `MEMORY.md` is not edited: its line already carries the summary and links the file by name, and the file name does not change.
- The date comes from one function that tests replace; nothing else reads the clock.
- **Skill.** The `crew-memory` section added by the first slice gains the save procedure: write the memory as usual, read the vault's own `CLAUDE.md` for the folder and tag vocabulary, run `save` without `--apply`, read the plan, run it with `--apply`, and report a `kept-full-text` line to the user verbatim.

## Exclusions
- No batch conversion of existing memories and no pointer-to-full-text restore: L-0678.
- No hook, no `hooks.json` change, no automatic conversion when a memory is written, no SessionStart injection.
- No new config key; no edit to `crew_config.py`, `plugin/crew/CONFIG.md` or crew-setup's template.
- No edit to `MEMORY.md`. No rename or delete of a native memory file.
- No overwrite of an existing note body, ever; no write to a `recall` or `ignore` vault; no write outside the vault.
- No call into or import from `plugin/obsidian-vault/`, and no change there. No REST bridge or MCP call: the write is to the file system.
- No git commit in the vault.
- No sabotage entry and no edit to `plugin/crew/tests/sabotage*.py` (harness; L-0679).
- No machine name, account name or absolute vault path in any tracked file.

## Evidence
All read at origin/main `155fe6d8` on 2026-10-04.
- plugin/obsidian-vault/hooks/scripts/obsidian_common.py:332 `writer_vault`: the primary-only rule, the "not available ... no other vault is used instead" refusal, the legacy name `memory`.
- plugin/obsidian-vault/hooks/scripts/vault_import.py:157 `contained`; :239-247 `makedirs`, the second containment check, then `open(dest, "x", encoding="utf-8", newline="\n")`; :26-29 "full text is computed before anything is opened".
- plugin/obsidian-vault/skills/obsidian-memory-contract/SKILL.md:22-43 the six keys (`title` byte-identical to the file name, quoted; `tags` one per line); :38 the type list; :100-102 a correction is a visible passage; :162-167 `guard.asciiOnly`.
- plugin/obsidian-vault/hooks/scripts/vault_guard.py:156 `check_note` and :301 `asciiOnly`: the guard is a PreToolUse hook on the Write tool, so a script write does not pass through it and must conform on its own.
- plugin/crew/hooks/scripts/crew_tracker.py:449 `_atomic_update` (temp file, re-read, `os.replace`): the in-crew precedent for an atomic vault write; :988 onward, the `.obsidian/` check that makes a directory a vault.
- plugin/crew/hooks/scripts/crew_recall.py:48 `obsidian_config_path`.
- Repo rule, CLAUDE.md "Landmines": compute the full text before opening for write; `newline="\n"` on every write.
- Native memory file shape, read on this host: frontmatter `name`, `description`, `metadata`, then a prose body.
- scripts/check-tooling-pr.py:58-87: none of this slice's paths are harness.

## Unknowns
- Whether Claude Code keeps or rewrites a memory file whose body is one line, and whether a later memory update by the harness overwrites the pointer with full text. Resolved before review: one manual run on a real session, result recorded in the PR body. If the harness rewrites it, `check` (first slice) shows the file as `full-text` again and `save` can be re-run; that is stated in the skill.
- `OBSIDIAN_VAULT_PATH`: `obsidian-vault` lets it relocate the primary vault. Default taken: the writer and the resolver both ignore it, so they always agree. Owner may reverse it; both must change together.
- Default folder `memories/<project>/` and default `type: concept` are owner questions 3 and 4 in the parent direction.
- Obsidian Sync conflicts when two hosts save the same memory before syncing: accepted as risk; the second writer sees `collision` or appends an update.
- The next free crew patch version is set at implement time.

## Size
About 230 added production lines in `plugin/crew/hooks/scripts/crew_memory.py`. One fail-closed write sequence; no new parser (the `name:` line match is one regular expression). Under the 300-line rule. No harness path.

## Touch
- `plugin/crew/hooks/scripts/crew_memory.py`
- `plugin/crew/tests/test_crew_memory_save.py` - new
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

Not in Touch, stated: `plugin/crew/CONFIG.md` (no setting); `docs/diagrams/` (no box or edge changes); `plugin/crew/hooks/hooks.json` (no hook).

## Acceptance checks
Commands run from the repo root; pytest goes through the heavy-run wrapper on a memory-bound host. New tests are in `plugin/crew/tests/test_crew_memory_save.py`, with every path under `tmp_path` and `HOME`, `CREW_OBSIDIAN_CONFIG` and the crew config pointed at the fixture.
- [ ] The file passes: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_memory.py plugin/crew/tests/test_crew_memory_save.py -q`
- [ ] Dry run writes nothing (`-k test_save_dry_run_writes_nothing`): a hash of every file and directory under the fixture is unchanged, the plan names the vault, the note and the pointer line, exit 1.
- [ ] Happy path (`-k test_save_apply_writes_note_then_pointer`): the note exists with the six keys, `project` and `memory_id`; `title` equals the file name stem; the native file's frontmatter bytes are unchanged; its body is exactly the pointer line; `resolve` on it returns `resolved` and the note's path.
- [ ] The pointer holds no absolute path (`-k test_pointer_and_note_hold_no_absolute_path`): neither the native file nor the note contains the fixture's vault root or home path.
- [ ] LF only (`-k test_outputs_are_lf_only`): no `\r` in the note or the native file, including when the input memory was CRLF.
- [ ] Must keep full text, one test each, each asserting the native file is byte-identical, the reason is printed, and the exit code is as in the state table:
  - no Obsidian config and no `memory.vaultPath` (exit 0)
  - primary vault path not on disk, with a `recall` vault present (the recall vault gains no file)
  - two `primary` vaults; no `primary` among vaults with roles
  - a directory with no `.obsidian/`
  - an existing note with a different `memory_id`, and one with none (`collision`; the existing note is byte-identical)
  - `--note` with a `..` segment, an absolute path, a backslash
  - a symlinked directory inside the vault on the note path (`outside-vault`; skipped with a reason where symlinks cannot be made)
  - `guard.asciiOnly: true` with a non-ASCII body
  - the note write raising `OSError` (monkeypatched): no pointer is written
  - the read-back failing (monkeypatched `resolve` to `note-missing`): no pointer is written
- [ ] Append (`-k test_save_again_appends_a_dated_update`): a second memory file with the same stem and a new body appends `## Update <date>`, keeps `created:`, bumps `updated:`, and keeps the first body.
- [ ] Idempotent (`-k test_save_on_a_pointer_is_a_no_op` and `-k test_same_body_twice_is_unchanged`): both leave every file byte-identical.
- [ ] A pointer that does not resolve is reported, not rewritten (`-k test_save_on_a_dangling_pointer_reports_its_state`).
- [ ] Usage (`-k test_save_usage_errors_exit_2`): no `--tag`; a tag with a space; an unknown `--type`; no `name:` and no `--title`.
- [ ] Both shells (`-k test_save_from_bash_and_pwsh`): `save --apply` through bash and through the resolved pwsh, on a vault path containing a space, produce byte-identical notes and native files. An absent shell is skipped and named.
- [ ] `(cd plugin/crew && python3 hooks/scripts/_test/validate-prompts.py)` passes with the skill's save procedure in place.
- [ ] Lint: pylint 10.00 on the two changed Python files; ruff reports no new finding against the merge base.
- [ ] `python3 scripts/check-tooling-pr.py` exits 0.
- [ ] Manual, recorded in the PR body: one real `save --apply` on a scratch memory in a real session, then a new session lists the memory and `resolve` returns the note.
- [ ] Docs: skill, README section 14 and the guide chapter describe `save`, the state table and every `kept-full-text` reason; guide outputs rebuilt (`python3 docs/guides/crew/src/build.py`); `.crew/codemap/crew.md` updated; crew bumped to the next free patch with a CHANGELOG entry; after the commit `python3 scripts/check-marketplace.py` passes.

## Dependencies
Must land first:
- T-0084 (spec, first slice): the pointer grammar, `resolve`, the test module and the verify rule this child extends.
- T-0021 (merged), T-0077 (merged): vault handling and the atomic-write precedent in crew.

Blocks: L-0678 (migration calls `save`'s plan and apply functions); L-0679 (its mutations target this code).
Related: T-0083 (direction), T-0048 (spec), T-0046 (in-progress), as in the parent spec.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
