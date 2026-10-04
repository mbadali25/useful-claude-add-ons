# T-0108 direction - gizmoduck headless/CI (plugin/gizmoduck/bootstrap.sh, scanners/zap.py, nikto, nuclei defaults)

Status: seed (not yet approved; the Brainstorm phase settles it under the owner's standing authority).

## Ask
the owner, 2026-09-29 ~05:15 CDT, verbatim: "@<another-session> reporting gizmo duck plugin issues please take that, and address them at the same time as this , put them in a workflow brainstorm -> spec -> approve -> implement -> fix -> gate -> land"

## Report (verbatim, from a session in another repository (crew 1.0.59, gizmoduck 0.5.3), found 2026-09-28/29, relayed cross-session 2026-09-29 ~05:10 CDT; its line numbers are the reporter's at crew 1.0.59 / gizmoduck 0.5.3 - re-verify against origin/main)
9. bootstrap.sh needs apt/sudo (:35-202); no guidance for CI/containers; ZAP adapter deliberately avoids Docker (scanners/zap.py:3-8).
10. ZAP/nikto look up Windows LOCALAPPDATA first (override GIZMODUCK_ZAP_HOME / GIZMODUCK_NIKTO_PL).
11. No default exclusion of nuclei dos/intrusive/fuzz tags and no default rate limit - only via --extra.

## Notes
- Every claim above is the reporter's; Brainstorm verifies each against the code before designing.
- Siblings from the same report: T-0104 (items 1-5), T-0105 (6), T-0106 (7), T-0107 (8, 12), T-0108 (9-11).

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
Checked against origin/main `155fe6d8` (gizmoduck 0.5.6, crew 1.0.322). The owner was not available; where the brainstorm would have asked, the recommended option is taken and the question is listed in spec.md under "Open questions for the owner".

### Is the problem still real
Yes, all three items. Nothing merged since the report touches them: `git log origin/main -- plugin/gizmoduck` since 0.5.3 holds only T-0107 (#273, the `routine` subcommand, 0.5.5) and L-0599 (#315, a pylint disable, 0.5.6). `git grep -n -i "etags\|exclude-tags\|GIZMODUCK_HOME\|rate-limit\|EUID\|--prefix" origin/main -- plugin/gizmoduck` returns nothing.

T-0107 raised the stakes: `gizmoduck.py routine` is now the documented path for scheduled and headless runs (`plugin/gizmoduck/README.md:95-97`), so a CI job is exactly the caller that meets these three gaps.

### Each claim, verified
- **Item 9, true.** `plugin/gizmoduck/bootstrap.sh` calls `sudo` unconditionally at `:34-35`, `:64-71`, `:91`, `:95`, `:101-107`, `:114`, `:141-149`, `:158-167`, `:176`, `:197-202`. A container running as root with no `sudo` binary fails every one of those steps. Everything lands in `/opt` and `/usr/local/bin`. The script ends on a `cat` (`:256-268`), so it exits 0 even when `FAILED` is not empty (`:246-251`): a CI step cannot tell a partial install from a full one. The README's install section is two lines (`plugin/gizmoduck/README.md:23-28`) with nothing about CI or containers. The no-Docker stance is real and deliberate (`plugin/gizmoduck/scripts/scanners/zap.py:3-8`, `bootstrap.sh:179-183`); it rules out Docker-in-Docker from the adapter, not running gizmoduck inside a container.
- **Item 10, partly true, and the real defect is different from the one reported.** Neither adapter looks at `LOCALAPPDATA` first. ZAP: a `zap.bat`/`zap.sh` on PATH (`zap.py:57-58`, `:102-104`), then `GIZMODUCK_ZAP_HOME`, then `LOCALAPPDATA` (`:70-77`). Nikto: a `nikto` on PATH (`nikto.py:112-114`), then `GIZMODUCK_NIKTO_PL`, then `LOCALAPPDATA` (`:89-95`). What is actually wrong:
  1. The explicit override loses to whatever is on PATH. An operator who sets `GIZMODUCK_ZAP_HOME` to pin a ZAP gets the PATH one instead, silently.
  2. `GIZMODUCK_ZAP_HOME` is searched for a `zap-*.jar` only (`zap.py:87-92`), never for the `zap.sh` in the same directory.
  3. On Linux there is no tool home at all: seven adapters resolve through `base.which` = `shutil.which` (`scanners/base.py:37-38`), so a tool is found only if it is on PATH. A no-sudo install has nowhere to put things that gizmoduck will find.
  4. Nikto's and testssl's candidates are built at import time (`nikto.py:89-95`, `testssl.py:64-70`), so an override set after import is ignored.
  5. None of `GIZMODUCK_ZAP_HOME`, `GIZMODUCK_NIKTO_PL`, `GIZMODUCK_TESTSSL_SH`, `GIZMODUCK_MSYS2_BIN` is documented in the README, the skill or a command file (grep: no hits outside the code and one test).
- **Item 11, true.** `cmd_scan` builds `-jsonl -silent -nc`, the target, `-severity`, then `--extra` split on whitespace (`plugin/gizmoduck/scripts/gizmoduck.py:151-160`). The routine adapter builds the same argv a second time (`scanners/nuclei.py:121-128`). Neither adds a tag exclusion or a rate limit, so Nuclei's own default rate (150 requests per second) applies, and templates tagged `intrusive` run. In a routine manifest, `options.extra` reaches Nuclei unchecked and the cell is recorded as a bare `ran` (`routine.py:309-312`, `nuclei.py:63`), unlike nmap and ZAP, whose mode is always named (`routine.py:278-281`).

### Options
1. **Recommended: fix all three, as three small PRs.** Safe Nuclei defaults first (it changes what traffic a scan sends, so it is the one with a safety consequence), then one tool-home lookup rule for every adapter, then a no-sudo mode for `bootstrap.sh` that installs into that tool home. Each is under 300 production lines and none touches the review or gate harness. The second and third are written as L-0684 and L-0685.
2. Docs only: document the env overrides and tell CI users to bake the tools into their image by hand. Cheap, but leaves the unsafe Nuclei default and the PATH-beats-override defect in place.
3. A container image published by this repo. Rejected: it contradicts the standing no-Docker decision for the operator machine, adds a registry and a release process, and nothing in the report asks for it.

### Defaults taken without the owner (each is an open question in spec.md)
- Default rate limit 50 requests per second (Nuclei's own default is 150).
- Default excluded tags `dos,intrusive,fuzz`, exactly the three the report names.
- Opting out is a named switch (`--intrusive`, manifest `nuclei_intrusive: true`), not a hidden `--extra`; in a routine run the mode is recorded as `ran(safe)` or `ran(safe+intrusive)`.
- `nuclei_intrusive` does not additionally need `--confirm-active`, matching `zap_active` and `nmap_vuln`.
- The default change ships as gizmoduck 0.6.0 (a behaviour change), not 0.5.7.

### Split
T-0108 keeps item 11. L-0684 is item 10. L-0685 is item 9 and depends on L-0684. Estimated production lines: 95 + 100 + 150 = 345, over the 300-line rule as one ticket.
