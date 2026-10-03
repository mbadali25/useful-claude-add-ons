# T-0036 direction - crew documents API calls and end-to-end flows

Status: direction APPROVED by the owner 2026-09-26 ("approve 1-3").

## Ask (owner, Matthew Badali, 2026-09-26, verbatim)
"Another ticket would be for the crew documenting API calls and flows as well (order sync, auth ,etc)"

## Facts (origin/main 3c1f94a9)
- `/crew:reference` (`plugin/crew/commands/reference.md`) already has `--api`, `--features` and
  `--audit`. `--api` writes `docs/reference/api.md` from the routes a repo EXPOSES, with a
  `path:line` anchor on every entry and `undocumented - needs a human` where the handler cannot be
  found. Its rule: enumerate from code, never from existing docs.
- Nothing documents what a repo CALLS: outbound integrations (a partner API, a payment or shipping
  provider, a cloud SDK), or a FLOW that spans several calls and systems, such as order sync between
  two apps or a login/token-refresh sequence.
- The endpoint ledger (`.crew/endpoints.json`, `crew_endpoints.py`) records hosts a ticket's tests or
  scans touch. It is a safety ledger, not documentation, but it is a ready list of outbound hosts.
- `crew-diagrams` already supports `sequenceDiagram` ("a request through the system over time",
  `plugin/crew/skills/crew-diagrams/SKILL.md:74`) and requires every edge to be labelled (`:89`).
- T-0035 (direction) proposes how diagrams are organised and embedded in READMEs. A flow document here
  is the natural first user of that mechanism.

## Recommendation (to be confirmed)
Extend `/crew:reference` rather than adding a new command:
1. **`--integrations`: every outbound API call.** Written to `docs/reference/integrations.md`, grouped by
   external system. Each entry records:
   - the endpoint and method;
   - the auth scheme, naming WHERE the credential comes from (env var, secret name, config key),
     never its value;
   - the request and response shape, as far as the code shows it;
   - retries, timeouts, rate limits and error handling;
   - every call site, with `path:line`.

   The endpoint ledger's hosts are a cross-check: a host in the ledger with no entry is a gap, and it
   is reported.
2. **`--flows <name>`: named end-to-end flows** (order sync, auth/login, token refresh, a webhook's
   round trip...). Each flow gets `docs/reference/flows/<name>.md` containing:
   - a labelled `sequenceDiagram` placed per T-0035's layout (e.g. `docs/diagrams/process/<name>.mmd`)
     and embedded here;
   - a step table where each step says who calls whom, with what, anchored `path:line`, and what
     happens on failure;
   - the data each step carries, and where state is stored between steps;
   - a "Failure and retry" section and a "What is not covered" section, stated rather than silent.
   `--flows` with no name proposes the candidate flows it finds, recommendation first, and waits for the
   owner to pick, because naming a flow is a judgement.
3. **Kept current:** the new docs carry anchors, so T-0008's refresh check judges them like codemaps and
   diagrams, and `/crew:implement` step 6 refreshes the ones a ticket's changes reach.
4. **Safe by construction:** auth flows and credential sources route to `crew:security` for review.
   Any string that looks like a secret stops the write. Hostnames and account ids follow the repo's
   existing redaction rules.
5. **Readable by agents and people:** plain markdown tables plus embedded Mermaid (T-0035's mechanism),
   and a one-line summary on top of every flow.

## Open questions
- Depends on T-0035 for the diagram layout and the embed generator. Proposal: T-0036 can land its
  markdown first and adopt the embeds when T-0035 lands.
- Which repos first? This repo has few outbound calls; the value is in consumer repos (e.g. SRL/TSS
  order sync). The crew feature is built and tested here with fixtures.
- Should `--audit` also check `integrations.md` against the code, reporting calls missing from the
  doc and doc entries with no call? Proposal: yes.

## Added 2026-09-26 (owner, verbatim): automatic in crew's routines
"for T-0035 /36 this should be a part of the crew routines automatically when running"
So this is not only a command someone remembers to run. It runs as part of crew's normal flow:
- `/crew:implement` step 6 (the docs + refresh step, before review) runs it for the paths a ticket changed:
  T-0035 regenerates diagram embeds and runs the readability lint on any diagram the change reaches;
  T-0036 updates the integration and flow docs whose anchors the change reaches, and proposes a new
  flow doc when a change adds an outbound call or a new multi-step flow.
- `/crew:done` check 4 (via `crew_refresh_check.py`) refuses when a reached diagram or reference doc is
  stale, the same way it already refuses stale codemaps - so skipping it cannot pass the gate.
- `/crew:onboard` (first run and `--refresh`) builds them for a repo that has none yet.
- Autopilot (T-0004/T-0022 docs phase) runs the same step unattended; anything needing judgement (naming a
  new flow, splitting an oversized diagram) becomes a needs-owner question, not a silent guess.

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

## Split 2026-09-30 (owner 2026-09-30 "Triage pass now")

Owner decision 2026-09-30 ~11:30: oldest tickets first, 1-2 deliverables per ticket, extras split into new tickets.

Kept in T-0036: `--integrations` with crew_reference.py lint (plan Step 1), the secret refusal and CLI (Step 3), the reference kind in the refresh check (Step 4), the docs/reference allowance (Step 5), and Steps 6-9 for those.

Moved:
- L-0549: `--flows [<name>]`, plan Step 2 (flow-doc lint) and the flows parts of Steps 3, 7 and 8.

spec.md and plan.md are APPROVED and were not edited. Before implement, they need a successor amendment narrowed to the kept scope, and a re-approval.
