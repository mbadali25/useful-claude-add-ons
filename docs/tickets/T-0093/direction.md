# T-0093 direction          status: direction   risk: low
## Ask
Owner, 2026-09-28 ~06:15 CDT, chose "Accept, file the NIT (Recommended)" for T-0091's round-2 NIT.
## Facts
T-0091 round 2 (Claude reviewer; Codex out until Oct 3), verbatim NIT: "CLAUDE.md:205|The paragraph says the `build_gallery.py:206` re-run of `index_html()` differs from its first run "only [in] the thumbnail `os.path.isfile` at `:85`". That is not the only difference. The second call goes through `samples()` ... `resolve_brand.list_themes()` ... `_brand()` ... re-read the theme and density JSON ... `load_overlay` then `_load_overlay_file` raises `OverlayInvalid` (`skills/doc-builder/scripts/resolve_brand.py:483-487`, `:514-522`). So a theme file that is edited or removed while the PNGs render raises inside the `with` opened at `:204`, after `index.html` has already been truncated." Worked out by reading, not run.
## Options
1. **Reword the CLAUDE.md sentence to state the condition (recommended)** - one-line doc fix after T-0091 lands.
2. Also fix build_gallery.py to compute the HTML before opening the file (the immune construction) - a doc-builder change with its own version bump; better as its own ticket if wanted.
## Recommendation
Option 1 via /crew:fix once T-0091 is on main.
## Open questions
none.
## Approval
Status `direction`.

## Owner decision 2026-09-30 - catch up with main by MERGE, never rebase
the owner, 2026-09-30, verbatim choice "Merge main in (Recommended)", after "rebase alot fo these before merge we did 4-5 prs outside of here that merged to main". origin/main has moved (it was a61a6f38 when this note was written: T-0088 #262, the QA fixes #263-#267, crew 1.0.69).
- Before your NEXT Review round and again right before Land: `git fetch origin && git merge origin/main` (a merge commit; mechanical conflicts only - a behavioural conflict is a STOP to the owner). Never `git rebase`, never force-push, never squash.
- After each merge: version one patch past origin/main's, refresh the artifacts until fresh and committed, re-run the suites serially under heavy-run, and state the merged origin/main sha in the phase evidence.
- A review receipt that went stale ONLY because of such a merge follows the existing merge-only rule; anything else needs a new round.

## Owner decision 2026-09-30 - run the suites in parallel (pytest-xdist installed, capped at 4)
the owner, 2026-09-30, verbatim choice "Install + cap at -n 4 (Recommended)". pytest-xdist 3.8.0 is now installed (apt python3-pytest-xdist); <local-tmp>/heavy-run exports PYTEST_XDIST_AUTO_NUM_WORKERS=4, so `-n auto` means 4 workers inside the wrapper.
- Full crew suite, always through heavy-run: `python3 -m pytest plugin/crew/tests/ -q -n 4 -m "not wallclock"`, then `python3 -m pytest plugin/crew/tests/ -q -m wallclock` serially (both must pass). This is main's own .crew/verify.json rule with the worker count pinned. Other pytest suites: same shape.
- pylint as CI runs it: `python3 -m pylint -j 4 $(git ls-files "*.py")`.
- Quote the new timing in the evidence (the serial full suite took ~700-900s here; #263 measured ~230s at -n 4).
- A test that passes serially and fails only under -n 4 is a real finding (shared-state race, as #267's d3cf73c3), not something to paper over: report it, never skip it.

## Direction check 2026-10-04
Checked against origin/main `155fe6d8`. Verdict: still real, still a docs-only fix, option 1 stands with two corrections.

Still true:
- The sentence is still on main, unchanged: "only the thumbnail `os.path.isfile` at `:85` differs" (`git grep -n "only the thumbnail" origin/main` prints one line). No commit on origin/main names T-0093.
- `skills/doc-builder/scripts/build_gallery.py` is unchanged since `bc6a3a09`: `:128` first `index_html()` call, `:204` the `open(..., "w")`, `:206` the second call inside the `with`. Option 2 (compute before open) has not been done by anyone.

What changed:
- **The paragraph moved.** Commit `199defe8` (2026-09-30) moved it verbatim from `CLAUDE.md` to `docs/claude-md-evidence.md` ("From Landmines"); the sentence is at `docs/claude-md-evidence.md:142-143`. `CLAUDE.md:129-132` now carries only the rule and a pointer. The fix edits the evidence file, not `CLAUDE.md`. The ticket title still says CLAUDE.md.
- **The NIT's condition is narrower than it reads.** The NIT was worked out by reading. Run on 2026-10-04 in a throwaway copy of origin/main's `skills/doc-builder/` (first `expected_files()`, then change a file, then `index_html()` again):
  - any theme file other than `professional.json` made unparsable or removed: **no raise**. `list_themes()` skips an unparsable file with a warning (`resolve_brand.py:490-502`), so its card is dropped from the index.
  - `professional.json` (the theme `COMPACT_SAMPLE` names, `build_gallery.py:48`) or the `compact` density file made unparsable: `OverlayInvalid`. Either one removed: `OverlayNotFound`.
  - a theme file edited to valid JSON with wrong value types (a number where a colour string goes, a list at the top level): `AttributeError` / `TypeError`.
  - the write as `main()` does it at `:204-206` with `professional.json` missing: `index.html` went from 10988 bytes to 0.
  So the reworded sentence must not say "a theme file changes" flatly, and must not name `OverlayInvalid` as the only exception.
- The paragraph's count sentence ("Six more were read one by one and none has a raise reachable between the open and the write") is also wrong for this site and has to change with it: five have none, the sixth has one under a stated condition.

Recommended option (taken, owner not available): option 1, reword the evidence paragraph to state the measured condition. Option 2 (make `build_gallery.py` compute the HTML before opening) stays out: it is a doc-builder content change with a version bump and is not needed to make the document true. If the owner wants it, it is its own ticket.

Path: `/crew:fix` is still the right weight (one file, no code). The 2026-09-30 owner notes above (merge, never rebase; xdist) still apply; only the docs rule of `.crew/verify.json` matches this change.

## Open questions for the owner
- Should option 2 (fix `build_gallery.py` so the site leaves the list) be filed as its own ticket? Default taken: no; the document states the condition instead.
- Should the INDEX title be corrected to name `docs/claude-md-evidence.md`? Default taken: left alone; the spec title carries the right path.
