# T-0502 direction - crew-setup _verify diagrams case as root

Status: seed (not yet approved).

## Report (verbatim, from another repository's session (crew 1.0.59, bitbucket and obsidian-vault plugins), follow-up report relayed cross-session 2026-09-29 ~06:40 CDT; the reporter's line numbers are at crew 1.0.59 - re-verify against origin/main)
16. _verify/cases/diagrams-parse.sh (created during crew setup) reports every diagram as "does not render" when run as root, because mmdc's Chromium refuses to start without --no-sandbox ("Running as root without --no-sandbox is not supported"). The failure message hides the real cause; with a puppeteer config {"args":["--no-sandbox"]} all 14 render. If the template comes from crew, it should pass a puppeteer config when EUID=0 and surface mmdc's stderr.
Note (orchestrator): plugin/crew/skills/crew-diagrams/scripts/render.sh:89-91 already writes a --no-sandbox puppeteer config; Brainstorm must first establish whether diagrams-parse.sh is a crew template (crew-setup templates/_verify/) or repo-owned.

## Notes
- Siblings from this follow-up: T-0500 (13), T-0501 (14), T-0106 gains item 15, T-0502 (16), T-0503 (18-20). Item 17 (Codex usage limit -> Claude fallback) is T-0088, landing now.
- Every claim is the reporter's; Brainstorm verifies each against the code before designing.

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
Checked against origin/main `155fe6d8` (crew 1.0.322). Owner not available; the recommended option below was taken as the default.

**Is `diagrams-parse.sh` a crew template? No.** crew ships three files under `plugin/crew/skills/crew-setup/templates/_verify/` (`README.md`, `run-all.sh`, `smoke.sh`) and no `cases/` file. `git grep -n "diagrams-parse" origin/main` and `git grep -n -i "does not render" origin/main -- plugin/crew` both print nothing. The file in the report was written by the setup session in that repository (`phases.md:307-309`: "an empty `cases/`. Then fill it, in this session"). So the message "does not render" and the bare `mmdc` call are repo-owned text, and crew cannot patch that file.

**What is still true on main (the crew-side causes).**
- Nothing in crew tells a session how to write a diagram check. The only place that says a direct `mmdc` call lacks `--no-sandbox` is a troubleshooting row (`plugin/crew/README.md:3100`); the setup phase, the `_verify` template README and `/crew:verify` do not mention it. A session filling `cases/` writes a bare `mmdc` call, which fails as root and in most containers.
- The shipped runners hide every failing check's output. `templates/_verify/smoke.sh:26-28` and `templates/_verify/run-all.sh:31-33` run the check with `>/dev/null 2>&1` and print only `FAIL <name>: <command>`. Even a case that prints mmdc's stderr is silenced when it runs through either runner. This part is crew's own code and affects every check, not only diagrams.
- The shipped runners have no SKIP for exit 77, while crew's gate does (`commands/verify.md`, "Exit 77 is SKIP"). A case that skips for a missing tool reads as FAIL through `run-all.sh`.

**What changed since the report.** Nothing fixed this. `git log origin/main --grep="T-0502"` has no implementation commit; only the hand-off note `docs/handoff/cloud/T-0502.md` (PR #276). `render.sh` already does the right thing and has moved: the puppeteer config is now at `plugin/crew/skills/crew-diagrams/scripts/render.sh:92-94` (the seed said `:89-91`), and it prints mmdc's last five lines on a failure (`:159-160`).

**Options.**
1. (Recommended, taken) Ship a ready diagram case and stop the runners hiding output. Add a self-contained template case `templates/cases/diagrams-render.sh` that passes the same puppeteer config as `render.sh`, prints mmdc's own error lines on a failure and exits 77 when `mmdc` is absent. Change the two template runners to print the last lines of a failing check's output and to report exit 77 as SKIP. Point the setup phase, `/crew:verify`, the template README and the crew-diagrams skill at the case. About 100 production lines, one PR.
2. Guidance only: a paragraph in the setup phase and the crew-diagrams skill. Cheapest, but the runners still hide the cause, and the next session still writes the case by hand.
3. Make the case call `render.sh` from the plugin. Rejected: a repo's `_verify/` scripts run in CI and from the gate without `CLAUDE_PLUGIN_ROOT`, so the case must not depend on the plugin being installed.

**Decision taken inside option 1: `--no-sandbox` always, not only when EUID is 0.** The report asked for it "when EUID=0". `render.sh` passes it unconditionally, because non-root containers without user namespaces fail the same way. One behaviour in both scripts is simpler to explain and to test (bash cannot fake EUID, and this host's sessions run as root, so a root-only branch would have an untested other half). The diagrams rendered are the repo's own sources.

**Out of reach.** Repos that already ran setup keep their own case file and their copied runners; templates are copied once. The docs added here tell them what to change by hand.

## Open questions for the owner
1. `--no-sandbox` always (taken, matches `render.sh`) or only when EUID is 0 (the report's wording)?
2. Runner output on a failing check: the last 5 lines of the check's combined output are printed (taken). A check that echoes a secret would now show it in the gate log. Accept, or print only stderr?
3. Exit 77 in the template runners: reported as SKIP and not counted as a failure (taken, matches the gate). The alternative is to keep 77 as FAIL in `smoke.sh` so a smoke run can never be green on skips alone.
