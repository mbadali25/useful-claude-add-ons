---
description: Pick up a ticket and work it end to end
argument-hint: <ticket id, e.g. T-0042, PROJ-123 or SDP-40219>
allowed-tools: Read, Edit, Write, Bash, Grep, Glob, Agent
---

Work ticket $1.

When the ticket is complete and verified, and `notify.provider` is not `none`,
send one line - this is the `done` event:
`bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/notify.sh done "$1 complete"`
Only after the checks pass. "Done" that means "I stopped typing" is the reason
nobody trusts a notification channel.

1. Read the ticket. Files mode: `.work/tickets/$1.md`. Jira, ServiceDesk Plus
   and Obsidian Kanban mode: `.work/cache/$1.md`, and if it is missing run
   `/crew:jira-sync $1`, `/crew:sdp-sync $1` or `/crew:obsidian-sync $1` first.
   Do NOT read INDEX.md or any other ticket.

   Then record where this ticket starts, once:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/scope_base.py --root . --record $1
   ```

   It writes HEAD to `.crew/.scope-base` keyed by the ticket, keeps an
   existing record for the same ticket (a re-run after `/clear` must not move
   the base to wherever HEAD has reached by then), and is machine-local like
   the gate's own marker. The scope evidence at step 5 diffs from this
   commit, not from what the gate last verified.
2. If Scope is unclear or "Done when" is not observable, stop and ask me.
3. Use the `crew:explorer` subagent to locate the code. Do not grep yourself.
3b. **If the ticket is a defect rather than a feature, run `/crew:debug` before
    you plan.** A defect is a ticket describing something that is broken,
    wrong, flaky, slow, or behaving other than it used to: a bug report, a
    failing or intermittent test, a regression, a stack trace, an incident, "it
    worked last week". A feature is a ticket describing something that does not
    exist yet. When it is genuinely both — a feature whose absence is showing
    up as a defect — treat it as a defect and debug first.

    `/crew:debug` ends with a cause and its evidence, and cannot edit the tree:
    its tool grant has no `Write` and no `Edit`. Feed its report into the plan
    at step 4, so the plan fixes the cause rather than the symptom, and carry
    its root-cause line into the brief you hand the developer at step 5.

    **Do not skip this because the fix looks obvious.** The ticket that most
    looks like it needs no diagnosis is the one where the obvious fix addresses
    the place the error surfaced rather than where the bad value came from, and
    that fix passes its test, ships, and brings the defect back under a
    different symptom. If you skip it deliberately, say so in the turn and say
    why — a diagnosis skipped and a diagnosis that found nothing are
    indistinguishable in a plan that mentions neither.

4. Plan mode. Show me the plan before editing.
4b. **Emit the goal line.** After the plan is agreed and before you edit
    anything, print a ready-to-paste `/goal` line. You cannot set it yourself —
    `/goal` is a built-in the user types, and crew has no way to invoke it — so
    print it and say plainly that pasting it is optional and what it buys.

    Three clauses, each from an artifact this repo already has:

    ```
    /goal <the ticket's "Done when", as one measurable end state>; proven by
    <the .crew/verify.json commands the ticket's paths map to> and <the
    specific new test this ticket adds>; no tracked file outside <the ticket's
    declared paths>, except TODO.md and .crew/ and .work/, is modified — the turn prints the
    changed-file list to show it, and anything found outside is appended to TODO.md with its reason,
    not fixed
    ```

    **The carve-out is load-bearing, not tidiness.** `TODO.md` is tracked. A
    constraint reading "no tracked file outside <paths> is modified" next to
    an instruction to append findings to `TODO.md` tells the turn to do what
    the same sentence forbids, so a correctly deferred finding reads to the
    evaluator as a scope violation and the only way to satisfy the goal is to
    stop deferring. Crew bookkeeping is excluded for the same reason
    `scope_report.py` excludes it: a ticket edit is the process working. Keep
    the two exclusion lists saying the same thing.

    **Why the third clause needs the second half.** The goal evaluator reads
    only what the turn surfaced in the conversation — it runs no commands and
    opens no files. So "no tracked file outside these paths is modified" is
    checkable only if the turn PRINTS the evidence. A turn that stays silent
    and a turn that stayed inside its paths look identical to the evaluator,
    and it returns Met for both. That is the failure this repo names over and
    over: an unknown collapsing into the safe-looking value.

    **Name the specific test, not only the mapped command.** `.crew/verify.json`
    rules are coarse globs — in this repository a single rule covers
    `plugin/**` and `skills/**` — so nearly every change maps to the same
    top-level checker. True, and not discriminating. The ticket's own new test
    is what makes the middle clause mean this change rather than any change.

    Skip this step and say why if the ticket has no observable "Done when";
    step 2 should already have stopped you.

5. Implement the smallest change that satisfies Done. Who types is not assumed:
   read the effective dev table first with
   `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_config.py --root . --models`
   and dispatch whatever `dev.roles.developer` names, else `dev.provider`.
   `claude` means the `crew:developer` subagent; `codex` or `copilot` means that
   CLI writes the change. The brief names the branch the work is on and says
   whether it is this ticket's own. The developer may commit on the ticket's
   own branch and nowhere else — never a shared branch, never `git stash`.
   So a brief asking for a commit on the default branch contradicts
   `developer.md`, and the developer is right to refuse it. In Obsidian Kanban mode,
   set `status: in-progress` in `.work/cache/$1.md` and run
   `/crew:obsidian-sync $1 --push` first — that command reads the status from
   the cache and moves the card, and a board nobody moves is a board nobody
   trusts.

   **Record the dispatch the moment it returns**, with the provider and model
   that actually ran:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_state.py --root . \
     --record-dispatch dev --role developer --provider <provider> --model <model>
   ```

   Record what RAN, never the pin. If the pinned model was gone and
   `dev.fallback` fired, the fallback is the value that goes in — a record naming
   the pin after the fallback ran makes step 9 bar a family that did not write
   this diff and clear the one that did, which is worse than no record at all.
   Omit `--model` only for `claude`, an in-session subagent with no model flag.
   Re-record on every later implementation pass, including the one that fixes
   review findings: the last dispatch is the one that produced the diff being
   reviewed. Unrecorded is not neutral — `/crew:review` then reads `dev` out of
   the config, which describes the *next* run rather than this one, and has to
   say so in its verdict.

   **End the implementation turn by printing the changed-file list,
   verbatim, including when it is empty:**

   ```bash
   # The ticket's START, recorded at step 1 -- NOT the base verify-gate.sh
   # derives from `.crew/.verify-verified-at`. The gate's base answers "what
   # has not been verified yet" and advances on every clean pass; this one
   # answers "what has this ticket changed" and does not move until the
   # ticket closes. One marker used to answer both, and a commit verified on
   # one turn had left the evidence by the next while still on the branch.
   # A missing or stale record falls back to the merge-base with the default
   # branch, which shows MORE, never less -- and never the verified marker.
   BASE=$(python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/scope_base.py --root . --base $1)
   git diff --name-only "$BASE"; git ls-files --others --exclude-standard
   ```

   **Not `git status --porcelain`.** Porcelain compares against the index, so
   a developer who commits on the ticket's own branch mid-ticket — which
   `developer.md` permits, and only there — vanishes from it while still
   having changed the tree. Diffing from the ticket's start keeps that commit
   in the evidence for the whole ticket. Porcelain also shows
   files that were already dirty before the ticket started, which on this
   repository includes `graphify-out/`, rewritten in the background by a
   post-commit hook. Both failures point the same way: the constraint reads
   satisfied when it is not.** Then name any path in it that is
   outside the ticket's declared scope, and say what you did about it — which
   under the scope clause means filed to `TODO.md`, not fixed. An empty result
   is printed as an empty result, not omitted: a turn that shows nothing and a
   turn that touched nothing are the same to every later reader, and only one
   of them is a claim anybody checked.

6. Verify. If `.crew/verify.json` exists, run the checks your changed paths map
   to (the Stop hook enforces this anyway; running it yourself is faster feedback).
   Otherwise `./_verify/smoke.sh`. On failure, fix and rerun. Never proceed past
   a red gate. If a changed path maps to no rule, add one before finishing.
7. If the change touches auth, input, SQL, secrets, or IaC -> `crew:security`.
   If it touches a migration, schema, or a big-table query and the `dba` role is
   enabled in `.crew/config.json` -> `crew:dba`.
8. If this ticket made a new endpoint externally reachable — a route, an
   Ingress, an API Gateway/API Management resource, an OpenAPI path — declare
   it now, the only way a candidate becomes an authoritative fact:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_state.py --root . \
     --declare-endpoint "<url or host>" --location <path:line> --ticket $1
   ```

   Name a URL or a bare host, not a free-text description (BLOCK 3) — the scan
   artifact later has to prove it covered THIS target by literally containing
   what you write here, and prose has nothing in it to search for.

   Do this even if `endpointUnscanned` never fired — that trigger only sees a
   candidate while its diff line is still uncommitted against HEAD; a ticket
   that merges without declaring the endpoint it just created loses the scan
   obligation entirely, silently, the moment the diff lands.
9. `/crew:review`.
10. If this added behaviour with no coverage, add a check: `crew:smoke-author` for
    API and data paths, `crew:browser-tester` for UI, CSS, or user flows. Those
    agents write the `.crew/verify.json` rule as part of writing the check and
    prove it fires — confirm both happened. A check nobody mapped never runs, and
    it reads as coverage while it does not.
    If the change touched migrations, schema, or procedures, the rule must cover
    fresh apply, rollback apply, and a round trip.
11. If this ticket involved an operational procedure that will be repeated, is
    destructive, or lived only in someone's head, run `/crew:runbook
    --from-ticket $1`. Build it from the commands actually run, not from memory.
12. Run `/crew:docs` — decide which documents this change should touch, per the
    `crew-docs` trigger table. "None" is the common and correct answer. If this
    is a Terraform module, run `terraform-docs .` rather than editing inside the
    `BEGIN_TF_DOCS` markers, which would be overwritten.
13. Update ticket status and a one-line Result. Files mode: edit the ticket and
    its INDEX line. Jira mode: `/crew:jira-sync $1 --push`. ServiceDesk Plus mode:
    `/crew:sdp-sync $1 --push` - which writes one note and transitions the
    request, and does not close it unless `sdp.closeOnDone` says to. Obsidian
    Kanban mode: set `status: done` in `.work/cache/$1.md`, then
    `/crew:obsidian-sync $1 --push` - which moves the card to the done lane and
    appends one note to the ticket note in the vault - and then edit the INDEX
    line too, the way files mode does. Obsidian mode keeps an INDEX because its
    keys are `T-####`, which the session brief can read.

14. Delete `.work/HANDOFF.md` if it exists. A stale handoff gets injected into
    every later session as though it were current, and that session has no way
    to know it is reading history.


Every role you dispatch carries a scope clause, but **not the same one, and do
not enforce it as though they did.** The clause follows the role's tools and
its output contract:

- **Roles that can write** (`developer`, `smoke-author`) file the finding to
  `TODO.md` themselves and end their report with
  `## Deferred — and where it went`, present even when empty.
- **Read-only roles** (`dba`, `qa-reviewer`) hold no `Write` or `Edit`, on
  purpose. They report the finding and **you** file it. Telling them to write
  `TODO.md` asks them to do it by shell redirection — which works, which is
  why it is the worse failure.
- **`qa-reviewer` has no Deferred section at all.** Its contract is defect
  lines or exactly `CLEAN`, and a prose heading breaks both. An unrelated
  defect from a reviewer is a `NIT` finding, not a deferral.

Reject a *writer's* report that omits the section; never expect one from
`qa-reviewer`. A uniform rule is what produced the contradiction this
replaced: one clause pasted into four roles whose contracts differ.

Stop there. I open the PR.
