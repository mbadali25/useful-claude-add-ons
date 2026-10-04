# L-0677 plan: `crew_memory.py save`

Written by the implementing session, 2026-10-04, on `L-0677-build` after merging origin/main
`86d96fa1` (crew 1.0.328) and origin/T-0084-build `5080f05c` (crew 1.0.398, the read side).
Contract: `spec.md` here. Version: crew 1.0.405 (coordinator placeholder), set in the last commit.

## Unknown 6, checked before code (spec "Unknowns", first bullet)

Checked with the real `claude` CLI (2.1.289) in this container, on a scratch project whose memory
directory held `MEMORY.md` plus one memory whose body was the single pointer line:

1. A new `-p` session with auto-memory on (`autoMemoryEnabled: true`; it is off by default in this
   container) listed the index line; the file stayed byte-identical (sha256 before = after).
2. A second session saved a different memory and read the pointer memory verbatim: the pointer
   file stayed byte-identical; `MEMORY.md` gained the new line.
3. A third session asked to update the pointer memory itself rewrote its frontmatter (name slug,
   `originSessionId`, `modified`, a blank line) and kept the pointer body.

So the harness keeps a one-line body. The code still fails safe: anything `save` cannot confirm
leaves the native file byte-identical, and a body the harness later rewrites to full text is shown
as `full-text` by `check` and can be saved again (stated in the skill).

## Steps (each test-first: write the test, see it red, implement, see it green)

1. **Tests file** `plugin/crew/tests/test_crew_memory_save.py`, reusing `test_crew_memory.Host`'s
   shape (HOME, USERPROFILE, CREW_OBSIDIAN_CONFIG, crew root under tmp_path; a fixed `today`).
2. **Writable vault** `writer_vault(root)`: roles -> the single `primary` (none / several refused);
   no roles -> `default: true`, else the first; no `vaults` block -> the name `memory` through
   T-0084's `vault_path` (crew `memory.vaultPath`, then the legacy `vaultPath`). The chosen name
   is resolved through `vault_path` too, so writer and resolver agree. Must hold `.obsidian/`.
   Nothing configured -> `kept-full-text: no vault configured`, exit 0.
3. **Plan** `plan_save(...)`: read the native file once (bytes), classify with T-0084's
   `classify`; pointer -> `already-pointer` (resolved) or its state; full text -> title (from
   `name:`), note path (`memories/<project>/<title>.md` through `_path_problem`), type, tags,
   ASCII rule, containment walk (no symlink component), existing note -> `create` / `append` /
   `unchanged` / `collision`. The full note text is computed here, before anything is opened for
   write.
4. **Apply** `apply_save(plan)`: note first. Create = temp file in the note's directory, then
   `os.link` to the final name (exclusive, atomic), temp removed; append = re-read, confirm
   unchanged since the plan, temp + `os.replace`. Containment re-checked after `makedirs`. Then
   read-back: the note's bytes equal what was written AND `resolve_pointer` returns `resolved`.
   Only then the pointer: frontmatter bytes kept, body = pointer + `\n`, native re-read and
   compared with the planned bytes, temp in the same directory, `os.replace`; the temp is removed
   on any failure. Never `open(path, "w")` on a real path; every write `newline="\n"` / bytes.
5. **CLI** `save` with the spec's flags, dry run by default (exit 1 while a write is pending),
   `--apply`, `--json`; usage errors exit 2.
6. **Failure-ordering tests**: note write raises -> native byte-identical, no note; read-back
   fails -> native byte-identical; pointer temp write / `os.replace` raises -> note exists,
   native byte-identical, no temp left.
7. **Docs**: `crew-memory` skill save procedure, README section 14, the memory guide (+ rebuilt
   outputs), codemap section, CHANGELOG, verify.json rule gains the new test file, BUDGETS.
8. **Version** last commit: crew 1.0.405 everywhere stated. Delete `docs/tickets/L-0677/` in the
   final content commit.

## Open questions (recommended option taken, as in HANDOFF.md)

1 crew writes the note itself; 2 `memories/<project>/<title>.md`; 3 `type: concept`; 4 an existing
note of the same memory gets a dated `## Update` passage; 5 `OBSIDIAN_VAULT_PATH` ignored by both
writer and resolver; 6 checked above.

## Readings of the spec

- `title` must equal the note's file-name stem, so the frontmatter `title` is the stem of the
  note path (an explicit `--note` wins over `--title`); a title holding `/` is `bad-note-path`.
- The spec's exclusive create is kept, and made crash-safe: temp file + `os.link` rather than
  writing into an `open(dest, "x")` handle, which would leave a partial note on a crash.
- A malformed `guard` block in the Obsidian config is refused ("config unreadable"), never read as
  `asciiOnly: false`.
