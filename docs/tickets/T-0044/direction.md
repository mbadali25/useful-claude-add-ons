# T-0044 direction          status: ready   risk: high

Approved 2026-09-27 under the owner's standing authorization (2026-09-26, "no longer ask me for
approvals"), inside the owner's request of 2026-09-27 to move backlog items through
brainstorm -> spec -> approve -> implement -> review -> fix -> gate -> land. This approves the
direction only; the spec and plan still go through `/crew:approve`.

## Recommendation
Option A: an unattended run is **started** holding short-lived credentials for an owner-named
read-only role, with the machine's own credential stores unreadable to it, and crew refuses to start
unattended cloud work whenever it cannot establish all of that. AWS first, because it is the only
cloud configured here.

Why: T-0005's guard reads command lines, so a renamed binary, `python -c` or a script file walks past
it (T-0005 spec, Exclusions; owner decision 2026-09-26). The only thing that holds whatever the command
line says is what the process can authenticate as. Choosing a profile (Option B) is not enough on
this machine: `~/.aws/config` has an `sso-session` (`<sso-session>`) whose cached token in
`~/.aws/sso/cache` can mint `AdministratorAccess` for the `<admin-profile>` profile. Any process that can
read that cache can write its own config and assume the admin role, whatever `AWS_PROFILE` says. So
the boundary is two things together: the credentials handed to the run, and the stores the run
cannot read.

Shape, not a plan:
- **Who starts it.** Credentials are set where crew starts an unattended process (the autopilot
  launch, a workflow lane, the auto-resume child), in that child's environment. A hook cannot change
  the environment of the session that is already running.
- **What it gets.** Temporary credentials exported for the read-only profile
  (`aws configure export-credentials`), `AWS_CONFIG_FILE` and `AWS_SHARED_CREDENTIALS_FILE` pointed at a
  minimal file crew generates, and no static keys inherited.
- **What it cannot read.** The machine's credential stores (`~/.aws/credentials`, `~/.aws/sso/cache`,
  and `~/.azure` / `~/.terraform.d/credentials.tfrc.json` where they exist) are denied to Bash and to
  the file tools through Claude Code's sandbox and permission deny rules.
- **Who names the role.** The owner names it in the machine-layer config only. A cloned repo must not
  be able to choose credentials on someone else's machine, the same rule `resume.auto` and
  `context.autoClear` follow. A write-capable profile is allowed only per `environments.nonProd` name.
- **How crew checks.** Before the run starts, `aws sts get-caller-identity` has to return the named
  role. "Could not tell" (no role named, sandbox unavailable, the probe failed, or it returned a
  different identity) is its own value and it refuses. It never falls back to the ambient
  credentials.
- **What crew never does.** It never stores, copies or logs a credential. It picks one and checks it.

## Ask
From the T-0005 review, round 6, and the owner decision of 2026-09-26: "unattended runs hold
read-only cloud credentials (the boundary T-0005 cannot be; depends on T-0005)". T-0005's guard only
catches terraform written directly. The boundary that holds whatever the command line says is the
credentials the process holds.

## Options
- **A. Short-lived read-only credentials plus sealed credential stores, refused when unverifiable**
  (recommended). This is a real boundary against disguise. It costs a launcher change on each
  unattended entry point, a sandbox/deny-rule dependency, and a pre-run STS probe. Read-only
  investigation (plans, `describe`, logs) keeps working unattended.
- **B. Profile selection only.** Set `AWS_PROFILE` to the read-only profile and strip static keys. It
  is cheap and it catches accidents, but it is **not a boundary**: the SSO cache can still mint admin
  for any script (see above). It is worth keeping as the first layer inside A, never on its own.
- **C. Refuse all unattended cloud work unless the owner names a profile for the run, with no
  switching.** This is the simplest and the strictest. It stops every read-only investigation that
  autopilot can do now, and it still leaves the ambient SSO token readable once a profile is named.
  So the named profile is not a boundary either unless A's sealing is added.
- **D. A separate OS user or container for unattended runs.** This is the strongest isolation. It
  means a new install step, runs as a different identity from the owner's root sessions, and moves
  file ownership. It is out of scope here; record it as the upgrade path if A's sandbox layer turns
  out to have gaps.

Out of scope, by YAGNI: Azure and TFC/HCP providers. Neither `az` nor a TFC token exists on this
machine. The spec should leave a provider seam, not implement them. T-0047's direct-use guard gaps
are also out of scope; they stay in T-0047.

## Open questions
- Does the owner's SSO assignment include a read-only permission set (for example `ReadOnlyAccess` or
  `ViewOnlyAccess`)? The profile `anew` names no role. If there is no such set, the first unattended
  cloud run refuses until the owner adds one. The spec records this under Unknowns and does not
  guess it.
- Does Claude Code's sandbox deny-read cover every Bash child, including interpreters and scripts,
  and do the permission deny rules cover the Read, Grep and Glob tools on the same paths? The
  spec's Evidence has to measure this. If either gap is real, A falls back to D for that path.
- Is it acceptable for the pre-run STS probe to make a network call to AWS? It is read-only and
  free, but it is still a network call.

## Depends on
T-0005 (merged to origin/main, 502cb137): the environment layer, `environments.nonProd`, and the
`unattended()` detection in `plugin/crew/hooks/scripts/cloud_guard.py`.

## Owner decision 2026-09-30 - catch up with main by MERGE, never rebase
Owner Matthew Badali, 2026-09-30, verbatim choice "Merge main in (Recommended)", after "rebase alot fo these before merge we did 4-5 prs outside of here that merged to main". origin/main has moved (it was a61a6f38 when this note was written: T-0088 #262, the QA fixes #263-#267, crew 1.0.69).
- Before your NEXT Review round and again right before Land: `git fetch origin && git merge origin/main` (a merge commit; mechanical conflicts only - a behavioural conflict is a STOP to the owner). Never `git rebase`, never force-push, never squash.
- After each merge: version one patch past origin/main's, refresh the artifacts until fresh and committed, re-run the suites serially under heavy-run, and state the merged origin/main sha in the phase evidence.
- A review receipt that went stale ONLY because of such a merge follows the existing merge-only rule; anything else needs a new round.

## Owner decision 2026-09-30 - run the suites in parallel (pytest-xdist installed, capped at 4)
Owner Matthew Badali, 2026-09-30, verbatim choice "Install + cap at -n 4 (Recommended)". pytest-xdist 3.8.0 is now installed (apt python3-pytest-xdist); /root/crew-tmp/heavy-run exports PYTEST_XDIST_AUTO_NUM_WORKERS=4, so `-n auto` means 4 workers inside the wrapper.
- Full crew suite, always through heavy-run: `python3 -m pytest plugin/crew/tests/ -q -n 4 -m "not wallclock"`, then `python3 -m pytest plugin/crew/tests/ -q -m wallclock` serially (both must pass). This is main's own .crew/verify.json rule with the worker count pinned. Other pytest suites: same shape.
- pylint as CI runs it: `python3 -m pylint -j 4 $(git ls-files "*.py")`.
- Quote the new timing in the evidence (the serial full suite took ~700-900s here; #263 measured ~230s at -n 4).
- A test that passes serially and fails only under -n 4 is a real finding (shared-state race, as #267's d3cf73c3), not something to paper over: report it, never skip it.
