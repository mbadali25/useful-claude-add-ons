# T-0084 crew memory pointers, slice 1: the pointer format and a per-host resolver (read-only)          status: spec   risk: med
## Written 2026-10-04
First spec for this ticket; there was no earlier spec.md or plan.md. Checked against origin/main `155fe6d8` (crew 1.0.322). The direction (direction.md, "Direction check 2026-10-04") is larger than one ticket, so this spec is narrowed to the first slice. The rest is in `children/1` (writer), `children/2` (migration and restore) and `children/3` (sabotage entries, tooling-only). Nothing here writes to a vault or to a native memory file.

## Intent
A native Claude Code memory file can hold one pointer line, `vault: <name> | note: <vault-relative path>`, in place of its body. This ticket adds `plugin/crew/hooks/scripts/crew_memory.py` with that format's one parser and two read-only subcommands: `resolve` maps a pointer to the note's real path on this host, and `check` reports the state of every memory file in a directory. Every way a pointer can fail to resolve is a named state with a non-zero exit, never a guess and never a silent pass.

## Design
- **File shape.** A native memory file is a YAML frontmatter block followed by a body. The frontmatter is never parsed as YAML and never rewritten: it is split off by the first two `---` lines and kept as bytes. A file with no frontmatter is body only.
- **Pointer grammar.** The body, with trailing blank lines ignored, is exactly one line: `vault: <name> | note: <path>`.
  - `<name>`: `[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}`.
  - `<path>`: vault-relative, forward slashes only, ends `.md`, no empty segment, no `.` or `..` segment, no leading `/`, no backslash, no drive prefix (`X:`), no control character, no leading or trailing space in a segment.
- **Classification of a body**, in this order:
  1. matches the grammar: `pointer`;
  2. is one line starting `vault:` that does not match: `malformed` (its own state; it is never read as full text and never resolved);
  3. anything else, including empty: `full-text`.
- **Vault name to path, on this host.**
  1. `vaults.<name>.path` in the machine's Obsidian config, the file `crew_recall.obsidian_config_path()` returns (it honours `CREW_OBSIDIAN_CONFIG`). An entry with `role: ignore` is not resolved.
  2. Only for the name `memory` and only when step 1 has no such entry: the crew config's `memory.vaultPath` (through `crew_config.resolve_config`), then the Obsidian config's legacy top-level `vaultPath`. `memory` is the name `obsidian_common.writer_vault` gives the legacy single vault.
  3. The path must be an existing directory. No other vault is ever substituted.
- **Note path.** Joined under the vault with `os.path.join` on the split segments, so it is right on Windows and POSIX. Every existing component between the vault and the note must not be a symlink, and the note's real path must stay under the vault's real path; otherwise `outside-vault`.
- **States** (`resolve`, and one per row in `check`):

  | state | meaning | exit |
  |---|---|---|
  | `resolved` | pointer, vault found, note exists | 0 |
  | `full-text` | not a pointer; nothing to resolve | 0 |
  | `malformed` | a `vault:` line that fails the grammar | 1 |
  | `no-vault-config` | no Obsidian config and no `memory.vaultPath` | 1 |
  | `vault-unknown` | this host's config has no vault of that name (or it is `ignore`) | 1 |
  | `vault-unavailable` | the configured path is not a directory (not mounted, not synced) | 1 |
  | `note-missing` | the vault is there, the note is not | 1 |
  | `outside-vault` | a symlink component, or the real path leaves the vault | 1 |
  | `unreadable` | the memory file cannot be read or is not UTF-8 | 1 |

  A config file that exists but does not parse is `no-vault-config` with the reason `config unreadable: <path>`; it is not treated as "no vaults".
- **CLI.**
  - `crew_memory.py resolve --file <memory file> [--root <repo>] [--json]` prints `state: <state>` and, for `resolved`, `path: <absolute note path>`; other states print `reason: <text>`. `--root` is where the crew config is read from (default: the current directory).
  - `crew_memory.py check --memory-dir <dir> [--root <repo>] [--json]` lists every `*.md` in the directory except `MEMORY.md`, one row each (`<state>  <file>  <vault>/<note or reason>`), sorted by file name, then a count per state. Exit 0 when every row is `resolved` or `full-text`, else 1.
  - Exit 2: usage error, or `--file` / `--memory-dir` missing on disk.
- Standard library only. The module writes nothing. Output is LF-only; paths in `--json` are the host's own, the pointer's `note` is echoed as written.
- **Skill.** `plugin/crew/skills/crew-memory/SKILL.md` gains a short section, "Native memories as vault pointers": the pointer line, that a session meeting one runs `resolve` and reads the printed path, the state table, and that a non-`resolved` state is reported to the user rather than worked around. It states that writing pointers arrives with a later crew version.

## Exclusions
- No write of any kind: no vault note, no native memory file, no `MEMORY.md` edit. The writer is L-0677; migration and restore are L-0678.
- No hook, no `hooks.json` change, no SessionStart or prompt injection, no change to `crew_context.py` or `crew_recall.py`.
- No new config key, so no edit to `crew_config.py`, `plugin/crew/CONFIG.md` or crew-setup's template.
- No derivation of the harness's `~/.claude/projects/<project>/` folder name. The caller passes the path.
- No call into the `obsidian-vault` plugin and no import from it; no change under `plugin/obsidian-vault/`.
- No wikilink form of the pointer. One format, the `vault: | note:` line.
- No `OBSIDIAN_VAULT_PATH` handling (see Unknowns).
- No sabotage entry and no edit to any `plugin/crew/tests/sabotage*.py` (harness; L-0679).
- Nothing of T-0083 (recall relevance).
- No machine name, account name or absolute vault path in any tracked file; examples use `<name>` and relative paths.

## Evidence
All read at origin/main `155fe6d8` on 2026-10-04.
- Nothing implements this: `git grep -n -E "crew_memory|vault: .* \| note:" origin/main -- plugin scripts skills` prints nothing.
- plugin/crew/skills/crew-memory/SKILL.md:1-70 is the whole skill: vault layout, the INDEX-only rule, anchors. No native-memory procedure, no script.
- plugin/crew/hooks/scripts/crew_recall.py:48 `obsidian_config_path` (honours `CREW_OBSIDIAN_CONFIG`, else `~/.claude/obsidian/config.json`); :55 `_read_json` (`utf-8-sig`, returns None on error); :111 `vault_order` reads `vaults.<name>.role` and never returns an `ignore` vault; :28 "Read-only: this module writes nothing anywhere".
- plugin/crew/hooks/scripts/crew_config.py:810 `resolve_config(root)`; :303 the template's `"memory": {"mode": "repo", "vaultPath": None, "inject": True, ...`.
- plugin/crew/CONFIG.md:723 `memory.vaultPath` (global-settable, `null`); :806 `obsidian.vaultPath` falls back to it; :828 `memory.recall.vaults`.
- plugin/crew/hooks/scripts/crew_tracker.py:172-174 the `memory.vaultPath` fallback; the vault-path checks in `_vault_paths` (from :988: `os.path.isabs or ntpath.isabs`, the `..` segment check on both separators).
- plugin/obsidian-vault/hooks/scripts/obsidian_common.py:332 `writer_vault`: the legacy single vault is named `memory`; an unavailable primary is reported, never replaced.
- plugin/obsidian-vault/hooks/scripts/vault_import.py:157 `contained`: the symlink-component and realpath containment rule this resolver restates (crew does not import it).
- Native memory file shape, read on this host: `---`, `name:`, `description:`, `metadata:` (nested `node_type`, `type`, `originSessionId`, `modified`), `---`, blank line, prose body. `MEMORY.md` is one `- [Title](file.md) — summary` line per file.
- Tests that already cover the neighbouring module: plugin/crew/tests/test_crew_context.py and plugin/crew/tests/test_crew_context_wrappers.py reference `crew_recall`. plugin/crew/tests/crew_fixtures.py:973 `resolve_pwsh`.
- .crew/verify.json: no rule names `crew_recall.py` or a memory script; `**/*.py` reaches pylint and ruff only, and `plugin/crew/skills/**` reaches `hooks/scripts/_test/validate-prompts.py`. A new rule is needed for the new script and its test.
- Docs that describe crew memory: plugin/crew/README.md:1798 (section 14, "Optional: Obsidian for memory"); plugin/PLUGINS.md:208 (`crew-memory` row); docs/guides/crew/src/memory-and-obsidian.md (sections at :34-:296; built with `memory-recall-proof.md` per docs/guides/crew/src/build.py:71); .crew/codemap/crew.md:1559 (the `crew_recall.py` dependency line).
- Harness: scripts/check-tooling-pr.py:58-87 `HARNESS` includes `plugin/crew/tests/sabotage*.py`. None of this slice's paths are in it.
- plugin/crew/.claude-plugin/plugin.json:3 `"version": "1.0.322"`.

## Unknowns
- `OBSIDIAN_VAULT_PATH`. `obsidian-vault` lets it relocate the default vault. Not honoured here: accepted as risk for this slice, and stated in the skill section. Revisit in L-0677, where the writer must agree with the resolver.
- Whether Claude Code keeps a memory whose body is one line. Nothing in the harness is known to validate body length. Resolved in L-0677 by a manual check on a real session before the writer ships; this slice writes no pointer.
- The frontmatter of a native memory is harness-owned and may change shape. Resolved by never parsing it: the split is on the `---` lines only, and a test uses a frontmatter with nested keys and one with none.
- Case-insensitive file systems: a pointer written on Linux may differ in case from the file on Windows and still open. Accepted: `resolved` means the path opens on this host.
- The next free crew patch version is set at implement time.

## Size and split
- This slice: about 180 added production lines, all in `plugin/crew/hooks/scripts/crew_memory.py`. One parser (the pointer line), no guard, no write.
- The whole direction is about 560 production lines with a parser, a fail-closed writer and a migration, so it is split: L-0677 `save` (about 230 lines), L-0678 `migrate` and `restore` (about 150 lines), L-0679 sabotage entries (0 production lines; tooling-only PR because `sabotage*.py` is harness).
- This slice touches no harness path, so it is an ordinary feature PR.

## Touch
- `plugin/crew/hooks/scripts/crew_memory.py` - new
- `plugin/crew/tests/test_crew_memory.py` - new
- `plugin/crew/skills/crew-memory/SKILL.md`
- `plugin/crew/README.md` - section 14
- `plugin/PLUGINS.md` - the crew-memory row and the crew version cell
- `docs/guides/crew/src/memory-and-obsidian.md`
- `docs/guides/crew/**` - the HTML, DOCX and PDF rebuilt by the guide build script
- `.crew/codemap/crew.md`
- `.crew/verify.json` - one new rule for the script and its test
- `CHANGELOG.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`

Not in Touch, stated: `plugin/crew/CONFIG.md` (no setting added); `docs/diagrams/` (no box or edge changes; a regenerated anchor is a refresh artifact); `graphify-out/` (refresh artifact); `plugin/crew/hooks/hooks.json` (no hook).

## Acceptance checks
Commands run from the repo root. On a memory-bound host each pytest command goes through the repo's heavy-run wrapper. All new tests are in `plugin/crew/tests/test_crew_memory.py`; fixtures are built under `tmp_path` with `HOME`, `CREW_OBSIDIAN_CONFIG` and the crew config pointed at the fixture, and no real vault or real memory directory is read.
- [ ] The whole file passes: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_memory.py -q`
- [ ] Grammar, must-accept (`-k test_pointer_grammar_accepts`, parametrized): a plain pointer; a name with a space, dot and dash; a nested note path; a non-ASCII note name; trailing blank lines after the pointer; CRLF line endings in the file.
- [ ] Grammar, must-refuse as `malformed` (`-k test_pointer_grammar_refuses`, parametrized), each case exit 1 and never `resolved`:
  - an absolute POSIX path (`/x/y.md`)
  - a drive path (`C:/x/y.md`) and a backslash path
  - a `..` segment and a `.` segment
  - an empty segment (`a//b.md`)
  - a path not ending `.md`
  - an empty or over-long vault name
  - a control character in the name or the path
  - a second `|` field
- [ ] `full-text` (`-k test_full_text_bodies`): a prose body; a prose body whose second line is a valid pointer; an empty body; a file with no frontmatter. Exit 0, no path printed.
- [ ] `resolve` happy path (`-k test_resolve_prints_the_real_note_path`): the printed path equals the fixture note's real path, for a vault named in the Obsidian config and for the name `memory` resolved from `memory.vaultPath`.
- [ ] The same pointer resolves under two different vault roots (`-k test_same_pointer_resolves_on_two_hosts`): two fixture configs give one name two paths; the memory file is byte-identical in both runs.
- [ ] One test per degraded state, each asserting the state name, a non-empty reason and exit 1: `-k test_state_no_vault_config`, `test_state_vault_unknown`, `test_state_vault_ignored_is_unknown`, `test_state_vault_unavailable`, `test_state_note_missing`, `test_state_unreadable`, `test_unparseable_config_is_not_no_vaults`.
- [ ] An unavailable named vault is never replaced by another configured vault that holds a note at the same relative path (`-k test_unavailable_vault_is_not_substituted`).
- [ ] Containment (`-k test_symlinked_component_is_outside_vault`, skipped with a printed reason where the platform cannot create a symlink): a note path that passes through a symlink inside the vault reads `outside-vault`.
- [ ] `check` (`-k test_check_lists_every_file_and_counts_states`): `MEMORY.md` is not listed; rows are sorted; exit 1 when any row is degraded and 0 when all are `resolved` or `full-text`; `--json` parses and carries the same rows.
- [ ] Read-only (`-k test_resolve_and_check_write_nothing`): a hash of every file under the fixture home, vault and memory directory is unchanged after `resolve` and `check`.
- [ ] Both shells (`-k test_cli_from_bash_and_pwsh`): `resolve` is invoked through bash and through the resolved pwsh on a memory path containing a space; both print the same `state:` line. Where a shell is absent the test is skipped and says which.
- [ ] Usage (`-k test_usage_errors_exit_2`): no subcommand, a missing `--file`, a `--memory-dir` that does not exist.
- [ ] The skill parses and the prompt checks pass: `(cd plugin/crew && python3 hooks/scripts/_test/validate-prompts.py)`
- [ ] `.crew/verify.json` has a rule whose paths are `plugin/crew/hooks/scripts/crew_memory.py` and `plugin/crew/tests/test_crew_memory.py` and whose run is the first command above: `python3 -c "import json;d=json.load(open('.crew/verify.json'));assert any('plugin/crew/hooks/scripts/crew_memory.py' in r.get('paths',[]) for r in d['rules'])"`
- [ ] Lint: `python3 -m pylint plugin/crew/hooks/scripts/crew_memory.py plugin/crew/tests/test_crew_memory.py` scores 10.00, and ruff reports no new finding against the merge base.
- [ ] No harness path in the PR: `python3 scripts/check-tooling-pr.py` exits 0.
- [ ] Docs: the skill section, README section 14 and the guide's memory chapter describe the pointer line, `resolve`, `check` and the state table, and say that writing pointers is not in this version; the guide outputs are rebuilt (`python3 docs/guides/crew/src/build.py`); `.crew/codemap/crew.md` names `crew_memory.py` and what it reads. Crew is bumped to the next free patch in `plugin.json`, `marketplace.json` and `plugin/PLUGINS.md`, with a CHANGELOG entry, and after the commit `python3 scripts/check-marketplace.py` passes.
- [ ] No private detail in the diff: `git diff origin/main...HEAD | grep -n -i -E "^\+.*(/home/|/root/|[A-Z]:\\\\repos)"` prints nothing.

## Dependencies
Must land first:
- none open. Listed for state: T-0021 (merged) put vault handling and the `memory.vaultPath` fallback in crew; T-0077 (merged) is the vault-write precedent the later slices follow; T-0087 (merged) is the harness-lands-alone rule that shapes the split.

Related, no order forced:
- T-0083 (direction): recall relevance. With this ticket it makes recall Obsidian-first; no shared file.
- T-0048 (spec) and T-0054 (ready): the full crew guide. If T-0048 lands first, the guide text moves to wherever it puts the memory chapter.
- T-0046 (in-progress): BUDGETS.md bookkeeping. Until it lands, the BUDGETS.md count edit is in Touch above.
- T-0081 (direction): per-component identity checks in `crew_tracker`'s vault walk. Same idea as the containment rule here, different module.

Blocks:
- L-0677 (writer), L-0678 (migration and restore), L-0679 (sabotage entries). Each needs this slice's format and resolver on main.

## Split
- L-0677 (child 1 of T-0084, filed 2026-10-04): crew_memory.py save - write the vault note, then turn the native memory into a pointer
- L-0678 (child 2 of T-0084, filed 2026-10-04): crew_memory.py migrate and restore - convert existing native memories, previewed and opt-in, and undo it
- L-0679 (child 3 of T-0084, filed 2026-10-04): sabotage entries for crew_memory.py (tooling-only PR)

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
