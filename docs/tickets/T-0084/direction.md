# T-0084 direction          status: direction   risk: med
## Ask
Filed 2026-09-27 ~23:25 CDT by owner decision: "ensure #2 will work on any system so have it built into crew". #2 was the second of three options offered for Obsidian-first recall: make Claude Code's native memory files one-line pointers into the vault, with the substance living in the vault note, so anything native memory recalls leads to Obsidian by design. The owner wants it built into crew and portable, not a convention one machine follows.

Constraints known now:
- Native auto-memory lives at `~/.claude/projects/<project>/memory/` (MEMORY.md index + one file per fact). Claude writes it with the ordinary Write tool; there is no recall call to intercept (see T-0083).
- The vault is on several hosts at different paths (a Windows drive path on two machines, a POSIX path on a Linux laptop), synced by Obsidian Sync. A pointer must therefore name the vault and a vault-relative note path (or a wikilink), never an absolute path, and resolve on every host from crew's own vault config.
- Crew already has a vault config (`obsidian.vaultPath` / `memory.vaultPath`), the vault guard's frontmatter contract, and the `crew-memory` skill; recall runs through `crew_recall.py` and the obsidian-vault CLI.
- It must degrade honestly: no vault configured, vault missing on this host, or the note not found -> the native memory keeps its full text (never a dangling pointer), and the degradation is stated, not silent.
- Windows (PowerShell and Git Bash), Linux and macOS alike: branch on the tool, not the OS; `newline="\n"`; no absolute POSIX paths in anything written to the vault.

Direction to settle at brainstorm: a crew-owned memory writer (skill procedure plus a small script) that, when a memory is saved, writes or updates the vault note per the vault's contract (type, title = filename, tags from the existing vocabulary, `project:`), and writes the native memory file as frontmatter plus a one-line pointer `vault: <name> | note: <vault-relative path>` with the one-sentence summary kept inline so MEMORY.md stays useful when the vault is unreachable. A resolver maps the pointer to the note on any host. Migration of existing native memories is opt-in and previewed. Tests on both shells; sabotage for the dangling-pointer and absolute-path cases.
Related: T-0083 (recall relevance) - together they make recall Obsidian-first.
## Options
none yet - to be settled at /crew:brainstorm.
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
Checked against origin/main `155fe6d8` (crew 1.0.322). The owner was not available; where the brainstorm would have asked, the recommended option was taken and the question is listed at the end.

Still true:
- Nothing on main implements this. `git grep -n -i -E "auto-memory|native memor|projects/.*memory" origin/main -- plugin scripts docs/guides/crew/src` finds only a review golden and a test regex; there is no `crew_memory.py`, and `git log origin/main -i --grep=memory` shows no commit for it.
- `plugin/crew/skills/crew-memory/SKILL.md` (70 lines) is still vault-layout prose with no procedure for a native memory and no script.
- Native memory is still written with the ordinary Write tool into `~/.claude/projects/<project>/memory/`: one `MEMORY.md` index plus one file per fact, each file a YAML frontmatter block (`name`, `description`, `metadata`) and a prose body. There is still no recall call to intercept.
- The vault is resolved per host by name: `~/.claude/obsidian/config.json` holds `vaults.<name>.path` and `role`, and crew already reads that file (`plugin/crew/hooks/scripts/crew_recall.py:48`, `:111`). `memory.vaultPath` in the crew config is the older single-vault key (`plugin/crew/CONFIG.md:723`).

Changed since the ticket was filed (2026-09-27):
- `obsidian-vault` now has a writer rule worth copying: one role-`primary` vault, read from the raw config so an unmounted primary is reported and never replaced by a recall vault (`plugin/obsidian-vault/hooks/scripts/obsidian_common.py:332`). The crew writer follows the same rule.
- T-0077 (merged) gave `crew_tracker.py` pinned, atomic vault writes (`_atomic_update`, `crew_tracker.py:449`). That is the in-crew precedent for crew writing into a vault directly.
- T-0087 (merged) made the review/gate harness land alone. `plugin/crew/tests/sabotage*.py` is harness (`scripts/check-tooling-pr.py:58-87`), so the sabotage entries this direction asks for cannot ride in the feature PR.
- `plugin/crew/tests/sabotage.py` is at the pylint module limit (3400 of 3400 lines, `.pylintrc:140`), so a new `sabotage_memory.py` import does not fit; the entries go into an existing module.
- T-0083 (recall relevance) is still at `direction`. The two tickets do not share code; neither blocks the other.
- One line of the Ask above was reworded on 2026-10-04 to remove machine names and absolute vault paths, because this file is published. Its meaning is unchanged.

Options considered:
1. **Recommended, taken: a crew-owned script, `plugin/crew/hooks/scripts/crew_memory.py`, driven by the `crew-memory` skill's procedure. No hook.** It owns the pointer format, the per-host resolver, the writer and the migration. It reads the vault location from the machine's Obsidian config (the file `crew_recall.py` already reads), with crew's `memory.vaultPath` as the single-vault fallback. It works without the `obsidian-vault` plugin installed, which is what "built into crew, on any system" asks for.
2. A `remember` subcommand in `obsidian-vault`'s CLI, called from crew as `crew_recall.py` calls `recall`. Keeps one vault writer, but the feature then needs a second plugin installed and the owner asked for it in crew. Rejected.
3. A PostToolUse hook that rewrites a native memory the moment Claude writes it. No reliance on the session following a skill, but it is a new hook that rewrites user files: the repo rule makes that a stop-and-ask, default OFF, with its own must-block and must-allow suite. Left as an open question, not built here.

Decisions taken with option 1:
- Pointer line, exactly: `vault: <name> | note: <vault-relative path with forward slashes>`. It is the whole body of the native memory file. The frontmatter stays byte-for-byte, so `description:` still carries the one-sentence summary and `MEMORY.md` stays useful with no vault.
- The vault note is written first and read back; only then is the native body replaced. Any failure before that leaves the native file byte-identical with its full text. A dangling pointer is never written.
- No new config key. Whether a pointer is written depends only on whether a writable vault resolves on this host.
- The native memory directory is passed in (`--file`, `--memory-dir`); crew does not derive the harness's project folder name.
- Dry run by default, `--apply` to write, as `obsidian-vault`'s CLI does.

Split (about 560 production lines in all, over the 300-line rule, and more than one parser or fail-closed state):
- T-0084 (this ticket, first slice): the pointer format, `resolve` and `check`. Read-only.
- L-0677: `save`, the writer.
- L-0678: `migrate` (previewed, opt-in) and `restore`.
- L-0679: the sabotage entries, as a tooling-only PR.

## Open questions for the owner
1. Crew writes the vault note itself (taken), or delegates to an `obsidian-vault` CLI subcommand?
2. No hook and no SessionStart nudge in this ticket (taken): the session uses the writer because the `crew-memory` skill says to. Is a default-OFF PostToolUse hook, or a one-line SessionStart reminder, wanted as a follow-up?
3. Default note folder when the caller passes no `--note`: `memories/<project>/<title>.md` (taken). The vault's own `CLAUDE.md` still wins; the skill tells the session to pass `--note` where the vault names a folder.
4. Default note `type:` is `concept` with the tag passed by the caller (taken), or `meta` as `obsidian-vault`'s `templates/memory.md` ships?
5. Updating a note that already exists for the same memory appends a dated `## Update YYYY-MM-DD` passage (taken, per the vault contract's "a correction is a visible passage"), or replaces the body?
