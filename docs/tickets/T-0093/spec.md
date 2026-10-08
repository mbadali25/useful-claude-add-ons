# T-0093 docs/claude-md-evidence.md truncation paragraph: state when the build_gallery.py:206 re-run can raise          status: spec   risk: low
## Refreshed 2026-10-04
First spec for this ticket (there was none). Written against origin/main `155fe6d8`; see direction.md "Direction check 2026-10-04". Two things differ from the 2026-09-28 direction, both because origin/main contradicts it:
- The paragraph is in `docs/claude-md-evidence.md` now (moved verbatim by `199defe8`), not in `CLAUDE.md`.
- The condition was run, not read, and it is narrower than the review NIT said: most theme-file changes do not raise. The measured cases are under Evidence.
There is no plan.md. `/crew:fix` is the intended path, so none is needed.
## Intent
Make the truncation paragraph in `docs/claude-md-evidence.md` true about `skills/doc-builder/scripts/build_gallery.py:206`. Today it says the second `index_html()` call differs from the first only in a thumbnail `os.path.isfile`, and counts the site among six with no raise reachable between the open and the write. The second call re-reads the brand, theme and density files from disk, so it can raise inside the `with` opened at `:204` and leave `index.html` at zero bytes. The paragraph must state that condition as measured, and correct the count sentence that depends on it.
## Exclusions
- No change to `skills/doc-builder/scripts/build_gallery.py` or any other code. Computing the HTML before the open is direction option 2 and is not this ticket.
- No change to `CLAUDE.md`. Its rule at `:129-132` and its pointer to the evidence file stay as they are.
- No re-run of the whole AST scan and no change to the paragraph's other counts (57 sites, 48 in tests, nine that ship) or to the text about the other eight sites. They are stated as facts about `f54af3fa` and stay so.
- No version bump: `docs/claude-md-evidence.md` belongs to no plugin or skill. No CHANGELOG entry (T-0091, the same kind of change, had none).
- No new checker, test or marker for the evidence file.
- Do not rewrap or re-flow lines of the paragraph that the rewording does not change.
## Evidence
All read at origin/main `155fe6d8` on 2026-10-04.
- docs/claude-md-evidence.md:95 heading "From Landmines". :110 the truncation bullet starts. :129-131 "Six more were read one by one and none has a raise reachable between the open and the write". :140-143 the build_gallery clause, ending "only the thumbnail `os.path.isfile` at `:85` differs). That is reading, not execution." :144 "The ninth is the one to re-check first". :156-157 "Re-run it rather than trusting these counts".
- docs/claude-md-evidence.md:3-9 the file's own header: moved verbatim on 2026-09-30, `CLAUDE.md` is the rule and this file is the record, every `path:line` is a fact about the commit it was written at.
- CLAUDE.md:129-132 the rule, ending "The per-site audit, and the one live site to re-check first, are in the evidence file."
- skills/doc-builder/scripts/build_gallery.py:48 `COMPACT_SAMPLE = ("professional-compact", "professional", "compact")`. :51-52 `_brand` calls `resolve_brand.resolve`. :55-62 `samples()` calls `resolve_brand.list_themes()` at :57 and :59. :79-82 `index_html()` calls `samples()` and `_brand(theme, density)` per card. :85 the thumbnail `os.path.isfile`. :124-128 `expected_files()`, first `index_html()` call at :128, reached from `main` at :167. :150-152 the Chromium render, `timeout=120` per sample, which is the window between the two calls. :197-202 the render loop. :204-206 `open(..., "w")` then `fh.write(index_html())`.
- skills/doc-builder/scripts/resolve_brand.py:466 `OverlayNotFound`. :479 `OverlayInvalid`. :483-487 `_load_overlay_file` raises `OverlayInvalid` on `OSError` or `ValueError`. :490-502 `_listable` skips an unparsable overlay with a warning and does not raise. :505-507 `list_themes`. :514-522 `load_overlay` raises `OverlayNotFound` at :520-521 and loads at :522. :525-547 `resolve`, calling `load_overlay` at :541. No cache: each call re-reads the files.
- skills/doc-builder/assets/themes/gallery/index.html is tracked, so `git checkout --` repairs it.
- Run, not read, 2026-10-04, in a throwaway copy of origin/main's `skills/doc-builder/` (first `expected_files()`, then change one file, then `index_html()` again):
  - a theme file other than `professional.json` made unparsable, or removed: no raise; the card is dropped and a warning printed.
  - `professional.json` made unparsable: `OverlayInvalid`. Removed: `OverlayNotFound`.
  - the `compact` density file made unparsable: `OverlayInvalid`. Removed: `OverlayNotFound`.
  - a theme file rewritten as valid JSON with wrong value types: `AttributeError`; as a top-level list: `TypeError`.
  - the write exactly as `:204-206` does it, with `professional.json` missing: `OverlayNotFound`, and `index.html` went from 10988 bytes to 0.
- .crew/verify.json:96-103 the docs rule: `docs/**` runs `python3 scripts/check-marketplace.py`, `python3 scripts/_test/self-claims.py` and `python3 scripts/sync-updates.py --check`.
- Nothing under `scripts/`, `.github/` or the crew tests reads `docs/claude-md-evidence.md` (`git grep -l claude-md-evidence origin/main -- scripts .github plugin/crew/tests plugin/crew/hooks` prints nothing). `docs/**` is not in `HARNESS` (scripts/check-tooling-pr.py:58-87), so the tooling-PR rule does not apply.
- No commit on origin/main mentions T-0093 (`git log origin/main --oneline --grep=T-0093` prints nothing).
## Unknowns
- Line numbers may have moved by implement time. Resolve by re-reading `build_gallery.py` and `resolve_brand.py` at the branch head and writing the numbers found there; the acceptance checks compare against the head, not against this spec.
- Whether a brand-pack change between the calls (the neutral pack `_brand` resolves at `build_gallery.py:52`) can also raise was not run. Accepted: the new text names the theme and density cases that were run and says the list is what was measured, not a complete one.
- A change that lands between `list_themes()` and `load_overlay` inside one `index_html()` call (a far narrower window) was not run. Accepted as risk; the wording "between the two calls" does not claim otherwise.
## Size and split
- Production lines added: 0. One documentation file changes, by roughly 10 lines.
- No parser, guard or state machine. No `HARNESS` path. No split.
## Touch
- `docs/claude-md-evidence.md` - the truncation bullet under "From Landmines" only

Not in Touch, stated: `CLAUDE.md` (the rule is unchanged); `skills/doc-builder/**` (no code change); every `plugin/crew/` document (this is not a crew change, so the crew docs rule does not apply; PR body carries `Docs: none - not a plugin/crew change`); `.claude-plugin/marketplace.json` and `CHANGELOG.md` (no version bump). Refresh artifacts (`graphify-out/`) follow the standing rule and need no Touch line.
## Required content
The reworded text, in the paragraph's existing voice and wrap width, must say all of the following. Wording is the implementer's; the facts are fixed.
1. Of the six sites, five have no raise reachable between the open and the write; `build_gallery.py:206` has one under a condition.
2. The second `index_html()` call re-reads the theme and density files from disk, after the Chromium renders, so the thumbnail check at `:85` is not the only difference.
3. The condition, as measured: the call raises when the `professional` theme or the `compact` density file (the pair `COMPACT_SAMPLE` names) is unparsable (`OverlayInvalid`) or gone (`OverlayNotFound`) by then, or when any theme file has become valid JSON of the wrong shape. Any other theme file made unparsable or removed does not raise; `list_themes()` skips it.
4. The consequence: the raise is inside the `with` opened at `:204`, so `index.html` is left at zero bytes. This one was run in a throwaway copy, not only read.
5. The existing sentence "That is reading, not execution." must stay true: either keep it scoped to the other five sites or reword it so it does not cover the build_gallery case.
6. `routine.py:508` stays named as the one to re-check first.
## Acceptance checks
- [ ] The false claim is gone: `git grep -n "only the thumbnail" -- docs/claude-md-evidence.md` prints nothing.
- [ ] The count sentence no longer says all six are safe: `git grep -n "Six more were read one by one and none has" -- docs/claude-md-evidence.md` prints nothing.
- [ ] Both exceptions and the skip are named: `git grep -n "OverlayInvalid" -- docs/claude-md-evidence.md` and `git grep -n "OverlayNotFound" -- docs/claude-md-evidence.md` each print at least one line, and `git grep -n -E "COMPACT_SAMPLE|professional" -- docs/claude-md-evidence.md` prints at least one line inside the truncation bullet.
- [ ] Every `build_gallery.py` and `resolve_brand.py` line number the new text cites matches the branch head: for each cited `:N`, `git show HEAD:skills/doc-builder/scripts/<file> | sed -n 'Np'` shows the thing named. Paste the output in the PR body.
- [ ] The condition is reproduced at the branch head before the text is written (run the states): in a throwaway copy made with `git archive HEAD skills/doc-builder | tar -x -C <tmpdir>`, call `build_gallery.expected_files()`, remove `assets/themes/professional.json`, then run the `:204-206` write; it raises `OverlayNotFound` and `index.html` is 0 bytes. Paste the output in the PR body. Never run it in the checkout.
- [ ] Only the one file changed: `git diff --name-only origin/main...HEAD` prints `docs/claude-md-evidence.md` and, at most, refresh artifacts under `graphify-out/`.
- [ ] Nothing outside the truncation bullet changed: `git diff origin/main...HEAD -- docs/claude-md-evidence.md` shows hunks only between the line starting ``- **`open(p, "w")` truncates`` and the line starting ``- **`pathlib.write_text` converts``.
- [ ] `CLAUDE.md` is untouched: `git diff --stat origin/main...HEAD -- CLAUDE.md` prints nothing.
- [ ] The docs rule of `.crew/verify.json` passes: `python3 scripts/check-marketplace.py`, `python3 scripts/_test/self-claims.py` and `python3 scripts/sync-updates.py --check` each exit 0 (commit first; the version-drift check compares commits).
- [ ] New test: none, stated. This is a prose correction in a file no checker reads, and the Exclusions rule out adding one. The reproduction above is the evidence.
## Dependencies
Must land first:
- T-0091 (done; merged 2026-09-28 as PR #252): wrote the paragraph and the sentence this ticket corrects. This ticket is its round-2 NIT.
- The move of the paragraph to `docs/claude-md-evidence.md` (commit `199defe8`, on main, no ticket id): decides which file is edited.

Blocks: nothing. No ticket in INDEX names T-0093 as a dependency.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
