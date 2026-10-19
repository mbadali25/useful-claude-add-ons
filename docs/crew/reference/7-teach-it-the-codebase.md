<!-- Moved verbatim from plugin/crew/README.md (7. Teach it the codebase) by L-0726; the README keeps an index entry. -->

## 7. Teach it the codebase

```
/crew:onboard
```

This is the expensive one-time cost you are willing to pay. It spawns one `explorer` per subsystem in parallel, capped at six per run, and only their summaries reach your context.

The output is `.crew/codemap/<subsystem>.md`, each under sixty lines, each carrying:

```
anchor: repo@a1b2c3d
verified: 2026-08-22
```

**Anchors are the entire point.** Every claim names the file it came from, so any note can be re-verified:

```bash
git diff --name-only <anchor-sha>..HEAD -- <paths>
```

If the anchor files moved, re-verify that section before relying on it. A map without anchors rots silently and keeps being trusted, which is strictly worse than having no map — a stale note is confidently wrong in exactly the way a fresh search never is, and it arrives with the authority of something you wrote down deliberately.

**Code always wins over notes.** When they disagree, the note is wrong. Fix the note; do not reason from it.

Only `.crew/codemap/INDEX.md` loads by default. Everything else is read by path, one file at a time.

Re-map a single area after major surgery with `/crew:onboard --refresh <subsystem>`. Do not re-run the whole thing on a schedule — that is the cost you were avoiding.

**`.gitignore` kept right for the languages in the repo (T-0039).** `/crew:init` Phase 1, `/crew:onboard` and `/crew:onboard --refresh` run `crew_gitignore.py apply --root .`; `/crew:implement` step 6 runs `check`, and `/crew:status` shows one `gitignore` line. Languages come from the files git lists (never an ignored `node_modules/`), the patterns from a table vendored from github/gitignore (CC0-1.0, `NOTICE.md`), and "already covered" is measured with `git check-ignore` against the working tree's ignore files only - a machine-global excludes file does not travel with a clone, so it never counts. Missing patterns are added without asking (owner decision) inside one `# crew:gitignore:managed` block at the top of `.gitignore`, so every human rule below it wins; crew never edits a human line, never touches the `.crew` policy block, and never drops an entry from its own block. It never untracks: a tracked file a new pattern matches is named, and a tracked secret-shaped file (`*.pem`, `.env`, ...) is a `needs-owner` line, exit 3. The `.env.*` row re-includes the usual templates (`.env.example`, `.sample`, `.template`, `.dist`, `.defaults`). Known limit: a committed test-fixture key or certificate (`*.pem`, `*.key` under `tests/`) is still reported `needs-owner`; there is no acknowledgement mechanism, so the owner decides. A directory pattern that would defeat a human `!` re-include is a `conflict`, not added. `# crew:gitignore:off` in `.gitignore` makes it report-only; inside a ticket whose Touch lacks `.gitignore` it refuses (exit 5), because an ignore line could hide the ticket's own files from the completion audit. Exits: 0 current, 1 pending, 3 owner, 4 unknown (including an unreadable file or any unexpected error - never 1), 5 refused.
