# T-0054 direction          status: ready   risk: low

## Ask
Owner (the owner, 2026-09-26): "When writing the guide for the documentation on using Autopilot,
please include all these examples of how to use it in there." Then: "I'll need a full crew autopilot
guide and also a configuration guide. Those should be separate documents in general."

## Decision
Three documents, not two:
- a full crew guide (T-0048);
- a configuration guide (T-0048's second document);
- and this one, a full **autopilot guide**, as its own document in `docs/guides/crew/`, built by
  `docs/guides/crew/src/build.py` as HTML, DOCX and PDF like the others.

T-0048's crew guide keeps a short autopilot section that links here.

## Content
Task-first: how to arm it, how to hand it work, what it stops for, and how to read its output. Every
example the owner asked for goes in, each as the exact command or the real output plus what it
means. The running list is the memory note `autopilot-guide-examples` (moved here from T-0048's
acceptance check):
- arming (`mode: plan`, `maxPhases`, `crew_autopilot.py settings`);
- the "armed, first phase is spec" output (seen in another repository; shown with a neutral ticket id), and why it is not a stop;
- approvals, including why an edit stales one, and `goal:<slug>`;
- the `human|self|risk` policies;
- the subcommands: `status`, `assign`, `goal`, `focus`, `wave` and `split`;
- resuming after `/clear`;
- Telegram pings;
- shipping as a PR, a merge or PR slices;
- sleep mode (T-0053).

## Options
1. **Write it once most autopilot tickets have landed, with a section per landed feature
   (recommended).** Today only T-0004 is on main; a guide written now would be mostly "arrives with
   T-00xx". Start it as soon as T-0010, T-0018 and T-0019 land, and have each later autopilot ticket
   add its section and example when it lands.
2. Write it now against the specs, marking everything not yet landed. Faster to exist, but it
   describes behaviour that review rounds are still changing.

## Recommendation
Option 1. A grep test lists each example's key phrase and fails, naming any example the built guide
lacks. That turns "include all the examples" into a check, not a promise.

## Depends on
T-0048 (build pipeline, and the crew guide section that links here), T-0010, T-0018, T-0019. Later
sections: T-0011, T-0012, T-0020, T-0029, T-0051, T-0052, T-0053.

## Approval
Direction approved under the owner's standing authorization (2026-09-26).

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
Checked against origin/main `155fe6d8` (crew 1.0.322). Owner not available; every default below is the recommended option, and each is listed under "Open questions for the owner".

**Still true**
- The guide does not exist. `docs/guides/crew/src/` has no autopilot source and `build.py`'s `GUIDES` table has five entries (`docs/guides/crew/src/build.py:68-74`). `git log origin/main --grep T-0054` prints nothing. Verdict: not obsolete.
- The only autopilot documentation is reference prose: `plugin/crew/README.md:855-919`, `plugin/crew/CONFIG.md:2591` (section 20) and `plugin/crew/commands/autopilot.md`. The guide sources mention autopilot only in passing (`docs/guides/crew/src/daily-workflow-scope.md:53-56`, `docs/guides/crew/src/troubleshooting.md:247-250`). None of it is task-first and none shows the owner's examples.
- Option 1 (a section per landed feature, the rest named by ticket) is still the right shape.

**What changed since 2026-09-26**
- Option 1's start condition is met. T-0010 (PR #261), T-0018 and T-0019 (PR #379, merge `d67098ad`) are all on origin/main. INDEX still reads T-0019 as `in-progress`; the merge commit is the evidence.
- More is landed than the direction assumed, so more of the guide can show real behaviour: the subcommand router and `status` (T-0018), the approval and questions policies (T-0010), `crew_ticket.py assign` and `mint` (T-0019), `autopilot.deploy` and `deploy-allowed` (T-0072), group approval (T-0024), plain-text `continue` (T-0023), handoff resume (T-0006), and the final-round auto-accept (L-0510).
- Still not landed, so the guide names the ticket and shows no invented output: the `/crew:autopilot assign` route (L-0611), `goal` (T-0012, L-0541, T-0056), `focus` (T-0020), `wave` (T-0029), `split` (T-0052, T-0058, T-0059), ship by PR or merge (T-0011), Telegram pings (T-0051), sleep mode (T-0053), plain-text phrases for every autopilot command (T-0057), self-typed resume (T-0013).
- T-0048 has not landed (INDEX: `spec`; no `guide.md`, no `build.py --check` on main). The direction listed it as a dependency for the build pipeline. That pipeline is already on main: `build.py` builds any entry in `GUIDES`. So T-0048 is no longer a blocker.
- One example in the list quoted a real ticket key from another repository. This repository is public, so the guide shows that output with a neutral id (`ABC-510`). The line above was reworded to match.

**Recommended option (taken)**
Option 1, now: write the guide against origin/main, one section per landed feature, with a "What is coming" table that names the ticket for everything else. Three defaults go with it:
1. **Do not wait for T-0048.** Add one `autopilot` entry to `GUIDES` and build. T-0048's crew guide adds its link to this document when it lands (it already has that acceptance check). Alternative: wait for T-0048, which leaves the owner without the guide for as long as that ticket takes.
2. **The example check is a static list.** `scripts/_test/autopilot-guide.py` holds one row per owner example: its key phrases if landed, its ticket id if coming. It fails naming any row the source or the built HTML lacks. It does not import crew code. Keeping the guide in step as later tickets land is the repo's doc rule and T-0055's job. Alternative: make the test read `crew_autopilot.AVAILABLE` and `ARRIVES`, so a landing ticket turns it red until the guide moves that row. That is stricter, but it reddens about ten in-flight tickets whose Touch does not list the guide.
3. **No file under `plugin/crew/` changes**, so no version bump. A pointer from the plugin's README would be a dead link on installed copies (`docs/` does not ship with the plugin) and would cost a bump. Alternative: add a one-line pointer and bump crew.

## Open questions for the owner
- Q1. Land before T-0048 (default taken), or wait for it?
- Q2. Static example list (default taken), or couple the test to the router's `AVAILABLE`/`ARRIVES` tables?
- Q3. No pointer from `plugin/crew/README.md` (default taken), or a one-line pointer with a crew version bump?
- Q4. Unlanded examples (the goal walkthrough, sleep mode, Telegram, ship, split) appear as one "What is coming" row each, with the ticket id and one sentence, and no sample output (default taken). The alternative is to print the intended output from the specs, marked "not yet", which review rounds may still change.
- Q5. The neutral id `ABC-510` replaces the other repository's real ticket key in the "armed, first phase is spec" example (default taken).
