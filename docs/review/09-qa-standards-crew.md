---
title: QA standards for crew - what two production repos taught us about QA environments, verify gates, review and CI
date: 2026-10-03
status: direction for L-0618, owner decisions recorded 2026-10-03 (section 6); input to a follow-up implementation session
---

# QA standards for crew

Crew sets up verify gates, review harnesses, promotion ladders and test environments in other
repositories. This document collects what went wrong when it did that in two production repositories
that have used crew for about six weeks, and turns it into standards crew should template, check and
audit. It is the public summary of ticket **L-0618**.

The two repositories are called **repo A** (a PHP web platform with a development and a production
rung, deployed by CodeDeploy) and **repo B** (a .NET platform with development, QA and production
rungs, deployed by GitHub Actions). Both are private. This summary leaves out hostnames, account
names, ticket numbers and any detail of their live security posture; the full evidence is kept
privately. Where a crew file is cited, the path is at `origin/main` (crew 1.0.154).

Evidence: answers from each repository's lead session to a six-question survey, read-only sweeps of
both repositories' history, crew's own setup code, and the crew review-rounds analysis in
`08-qa-rounds-analysis.md`. Nothing was executed against either repository; claims marked *reported*
come from those sessions and were not reproduced.

## 1. What crew builds wrong today

Ten recurring defects. Each names the crew template, phase or rule a fix would change.

**D10. A Stop gate that runs nothing.** Crew 1.0 runs a rule on Stop only when it declares `reach`;
a rule without it is recorded as skipped (`verify-gate.sh:803`). Nothing migrated maps written before
`reach` existed. In repo A every rule lacks `reach`, so every Stop records 13 skips while the
verified-at marker advances to HEAD with no command run (checked). Repo B hit the same defect and fixed
it by hand; declaring `reach` then exposed rules timed under a login shell that fail in the gate's
profile-less shell, browser proofs mislabelled `network` so they never ran, and a destructive rule
armed by the declaration. At least two more crew-managed repositories have the same map shape.
Fix half exists as **L-0562** (`/crew:verify --stamp-reach`); the audit that finds affected repos does
not.

**D1. The `_verify/` templates carry the bugs both repos later fixed by hand.**
`skills/crew-setup/templates/_verify/{smoke,run-all}.sh` have not changed since crew 0.2.0:

| Template line | Defect |
|---|---|
| `ENV="${ENV:-dev}"` | Reads an inherited `ENV` and defaults to dev. An `ENV=prd` left in a shell targets production with no flag. |
| `*) shift ;;` | Silently drops unknown flags, so `--ci` on a script without a CI mode makes live remote calls. |
| `${READONLY:+ (read-only)}` | Expands on the string `"0"`, so every run is labelled read-only, including write runs. Repo A fixed this locally; the template still has it. |
| every check commented out, `[ "$FAIL" -eq 0 ] \|\| exit 1` | Zero checks exits 0 ("0/0 passed"). SKIPs never fail. |
| `if "$@" >/dev/null 2>&1` | Swallows the failure reason; one run printed PASS over 14 warning lines. |
| README contract: "`--env`, defaulting to the local/development environment" | The written contract requires the default both repos now forbid. |

No hostname guard, no `--ci` mode, no count of what was examined.

**D2. Checks that cannot fail are accepted at setup.** The skill says every check ships a failing
control (`crew-verification` §1); nothing enforces it, and Phase 8's environment commands get no such
rule at all.
- Environment `verify` commands written as a remote command dispatch that queues and exits 0 without
  waiting for or reading the result.
- Deploy commands that dispatch a workflow and exit 0, so a "non-zero exit is a stop" gate proves the
  dispatch, not the deploy. The first generated dispatch omitted required inputs and failed on every
  run; the deploy ref is `$(git rev-parse HEAD)`, so it deploys whatever happens to be checked out.
- A deploy step piping a copy tool's exit code away left production hundreds of commits behind through
  green deploys.
- Test rules that reported PASS on a test run that never ran (mangled paths), a smoke check that called
  `exit` and ended the run rc 0 with no verdict, a runner that accepts a partial results file and
  ignores the exit code.
- Verifiers looping over an unset variable (OK over zero files), a fingerprint that agreed with itself,
  an inventory satisfied by commented-out code, a check matching a docblock.
- Crew's own recurring-findings list counts about 154 of 539 BLOCK/FIX findings as tests that cannot
  fail. In repo B, missing or vacuous failing controls were the top round-forcing cause across 60 PRs.

**D3. The environment model does not fit how the repos deploy.**
- In repo B, merging is the deploy: all three environments declare the same merge command, so
  `promote-gate` (which matches by command) cannot tell which environment is being promoted. The
  target is the PR's base branch, which the schema has no key for.
- The promotion record is hard to satisfy as specified: a literal `pass` cell, and a tracked log whose
  write moves HEAD (*reported*).
- Rollback was declared only for production, and the first rehearsal showed the runbook command did
  not work.
- Repo A has no QA rung by decision; setup still treats `development -> qa -> production` as a fixed
  order.
- A green run whose path-gated deploy job was skipped ships nothing. `promote.md` says "check the job,
  not the run" in prose; no template checks it.
- Deployed identity is never read back. Repo B's production held an old build through three green
  deploys; both repos now read a build id or file digest from the target.

**D4. Non-production environments share production's data, credentials and identities.** Setup asks
nothing about this, and both repos got it wrong for weeks: a non-production environment holding live
third-party payment and shipping credentials; QA test-account ids that exist as real production
customers; a QA environment restored from production that carries production API tokens and keeps
receiving production writes after the restore; a host-only untracked config file that overrides
tracked config, so the repository does not say what QA runs; one build's fallback that made QA write
to another system's production; QA and production sharing one egress identity. Crew's credentials
guidance records *where* secrets live, not *which environment a credential reaches* or *whether it is
live*.

**D5. Local gate and CI disagree, and nobody checks which jobs ran.** A manual CI run that only lints
read as "the merged tree passes"; a test suite that runs out of memory locally passes in CI; renaming a
CI job deadlocks PRs on a required check that never reports; the main branch was less protected than
the development branch; one repo runs none of its local `_verify` checks in CI at all. Crew ships no CI
template for a target repo: `verify-gate.yml` and `ci_receipt.py` are hard-wired to this repository,
and setup has no CI phase. H7 ("CI runs what the docs say") is audited for Ruff only.

**D6. Gates that are slow or fire on the wrong changes.** A 372 KB verify map; one rule starting an
89-minute sabotage run on 18 of 35 PRs, none of which touched what it proves; full smoke (15-43 min)
every review round; a tracked generated directory overflowing argv and reading as "verify.json could
not be parsed".

**D7. Exit codes, SKIPs and missing tools collapse into pass or fail.** Exit 77 read as FAIL at the
crew gate and SKIP in the repo's smoke; "10/10 passed" hid 9 skips from a browser library installed
under the wrong interpreter. Crew holds the principle (H8, "a missing tool is its own result"); the
templates do not apply it.

**D8. A review non-run reads as a clean pass.** Codex and Copilot exit 0 on usage-limit and budget
refusals; a harness that checks only the exit code counts that as BLOCK=0 FIX=0, and it nearly merged
ungated. A null reasoning-effort setting produced a silent no-findings run; an open stdin hung a review
for 100 minutes; a verdict gate read CLEAN past an earlier BLOCK; an oversized release diff could not
be reviewed at all; reviewer model and effort lived in untracked per-machine config and drifted (one
run used effort `none`). Crew's `review_limit.py` covers Codex's limit wording only. These are
review-harness changes and must land in their own tooling PRs.

**D9. Setup state that cannot be audited later.** A repo that never received crew's `.crew/*` ignore
block, so the promotion approval marker could not be untracked and the promote gate could not pass; an
in-flight deploy marker nothing clears; a map audit blind to tree-local verifier directories (71
verifier files mapped nowhere, reporting "orphaned: 0"); verifier scripts deployable into a served
directory; holds and stop rules kept only in CLAUDE.md prose ("a convention is not a control");
`STATUS.md` marking phases done against definitions that later changed; an upgrade that stamped codemap
anchors current without re-reading the prose; repositories whose setup started and never finished,
with nothing to report it.

## 2. The standards

Each is tagged **template** (crew writes it that way at setup), **check** (a deterministic audit item
that can fail) or **prose** (guidance only, the last resort).

### QA environment isolation
1. Every environment declares its data provenance: `seeded`, `restored-from-prod` with the scrub step
   named, or `shared-with-prod`. Restored without a scrub command is a GAP. *(check)*
2. Every host-reaching script refuses without an explicit `--env`, never reads an inherited `ENV`,
   refuses unknown flags, and asserts the remote hostname or account before acting. *(template + check)*
3. An environment marker (`APP_ENV` or equivalent) is read back from the target before any write; a
   per-environment egress or identity marker where partners see one address. *(template; prose for infra)*
4. Production smoke is read-mostly: writes only under an explicit `--confirm-prod`, with a test-data
   prefix and a cleanup ledger. *(template)*
5. Verifier scripts never ship into a served directory, or carry a CLI-only guard. *(check)*

### Credentials
6. A credential inventory at setup in `.crew/secrets.md` (names, never values) with two new columns:
   which environments it reaches, and whether it is a live third-party credential (payments, labels,
   email, SMS). A non-production environment holding a live one is a GAP that needs an owner acceptance
   line. *(template + check)*
7. Test identities are proven non-production and populated: the QA account's id does not exist in
   production, and it can see the population under test (an empty population is a stop). *(check, or a
   recorded manual step)*
8. Host-only overrides (untracked files that override tracked config) are named in the environment's
   entry in `.crew/verify.json`. *(template)*
9. Unattended runs hold scoped, read-only credentials (**T-0044**). *(referenced)*

### Checks after a deploy
10. Check the job, not the run: given a run id, assert the deploy job executed and succeeded. Shipped as
    a helper an environment's `verify` can name; **T-0045** owns dispatch-and-watch. *(template)*
11. Read the deployed identity back (build id, version or file digest) and compare it with the SHA
    being promoted. *(template)*
12. A health check reads the body, not only the status. *(template)*
13. UI repos smoke the real site in a browser per role and viewport, capturing console and network
    errors and diffing a control inventory before and after. *(template via webtest)*
14. Authorization deny paths are proven with a real non-admin user on the target. *(template + prose)*
15. Alerting reaches a person: a declared alarm's subscription reads confirmed. *(check)*
16. The same SHA goes up the ladder: promotion compares the SHA, production needs a dry run first, main
    fast-forwards to the release SHA, and a deploy ref is never `$(git rev-parse HEAD)` of whatever is
    checked out. *(check, partly in `promote-gate`)*
17. Deploy workflows fail loudly: a lint for swallowed exit codes (`| Out-Null`, `|| true`, copy tools
    without exit mapping, pipes into `grep`), secrets used without an emptiness check, missing
    per-environment concurrency groups. *(check)*
18. Every rung's rollback is rehearsed, and "last verified: never" keeps blocking. *(check)*

### Gate rules that can fail
19. No map is written, and no map passes audit, while a rule lacks `reach` or a `seconds` timed in the
    gate's own shell; a rule that mutates state carries `requiresCleanTree` or is classed `host`.
    *(template + check + fix via L-0562)*
20. Every rule and every environment command has a recorded failing control (the mutation, the red
    output, the date) before its setup phase can be marked done. *(check)*
21. Zero examined is a FAIL: every runner counts what it checked; a required check that SKIPs fails.
    *(template + check)*
22. Fire-and-forget commands are refused as checks: a remote dispatch without a wait-and-read, a
    workflow dispatch without a watch, `curl` without `-f`, a pipe whose exit is `grep`'s.
    *(check over `verify.json`)*
23. A runner never PASSes an aborted run: exit code first, artifact second, partial result files
    rejected. *(template; gate twin is **T-0082**)*
24. Baselines move in the PR that legitimately changes them. *(prose + CI template)*

### CI parity
25. A CI template per stack that runs the same `_verify/` entry points as the local gate, on push and
    pull request alike, with a parity check that every `verify.json` command family appears in CI or is
    declared local-only. *(template + check)*
26. Required-check names are recorded and a rename is flagged; branch protection is exported at setup so
    drift is detectable. *(check)*
27. Runtime parity facts are recorded: memory limit, tool versions, restore step, shared resources that
    need a lock. *(prose + check)*

### Gate speed
28. Triggers derive from real dependencies; a rule that fires on changes that never break it is flagged
    from history (`/crew:verify --price` gains a "fires on unrelated PRs" report). *(check)*
29. Two tiers: affected checks on fix rounds, the full suite once on the final candidate. *(template)*
30. Generated directories are ignored at setup and checked with `git check-ignore`. *(check)*

### Receipts
31. A structured promotion receipt per gate: command, exit, target echoed, deployed identity read back,
    SKIP count. *(template)*
32. A machine-read hold: a `holds` entry in `verify.json` (environment, reason, until, by) that
    `promote-gate` refuses on. *(check)*
33. Review receipts only from a substantive run: the verdict file exists, is newer than the run start,
    names model and effort, carries no limit text; an empty run is a FAIL; each with a failing control.
    *(harness, separate PR)*
34. Reviewer model, effort and versions live in a tracked file, not per-machine config. *(harness or
    config schema)*

## 3. Audit and fix for existing repositories

Extend `skills/crew-qa-standards/qa_audit.py`, which already answers PASS, GAP, N/A or UNKNOWN per
item, with environment (`E*`) and gate (`G*`) items mapped to the standards above.

- `/crew:init --audit` reports; `/crew:init --audit --fix` applies one confirmed fix per GAP, each shown
  as a diff and run through the repo's own gate.
- It reads `.crew/verify.json`, `_verify/` and any tree-local verifier directories, CI workflow files,
  `.gitignore`, `.crew/secrets.md` and `.crew/STATUS.md`. It never deploys, never reads a secret value
  and never calls a remote host; items that need the target come back UNKNOWN with the command to run
  by hand.
- Fix may touch repo files only: the template arg loop, `--ci` and the hostname guard, the ignore block,
  a fire-and-forget `verify` rewritten to wait and read, a `holds` key, the inventory columns. It never
  edits `~/.claude`, never changes branch protection (it prints the `/crew:gate` command), and never
  records a failing control without running it.
- Setup phases use the same audit as their "Done when", so a new repo and an old one are judged by one
  definition.
- `--audit --all-repos <root>` prints one line per crew checkout: phase reached, GAP count, D10 yes/no.
- **Acceptance:** run by each repository's own session, the audit must find the known defects in repo A
  and repo B listed in section 1. A clean result on either today is wrong; those known GAPs are the
  audit's failing controls.

## 4. Proposed slicing

The tooling-PR rule applies: `verify-gate.*`, `review_*.py`, `commands/review.md`,
`agents/reviewer.md`, `crew_ticket.py` and every `plugin/crew/tests/sabotage*.py` are harness and land
alone. `promote-gate.*`, `ci_receipt.py`, `qa_audit.py`, the setup skills, templates and phases are not.

| Slice | Content |
|---|---|
| 0 (optional, recommended) | D10: the `reach` audit item plus L-0562's helper, ahead of everything, because a Stop gate that runs nothing is live today |
| a | Setup audit: E/G items, `/crew:init --audit`, fleet view, `verify.json` command lint, deploy-workflow lint, tree-local verifier discovery. Report-only |
| b | Correct-by-default templates and phases: D1 fixes, `--ci`, hostname guard, zero-examined FAIL; Phase 8 asks provenance, credential reach and host overrides; check-the-job and deployed-identity helpers; `holds` and an environment `target` key; promote-gate reads holds and clears its marker; a CI template per stack; `--audit --fix` |
| c | Tooling PR with slice b's sabotage entries, after b |
| d | Review-validity tooling PR (D8), coordinated with the QA-rounds stream in `08-qa-rounds-analysis.md` |

Alternatives considered: templates before the audit (new repos benefit sooner, existing ones wait and
the templates have no checker); one feature PR plus one tooling PR (fewest PRs, but size predicts
review rounds: 2.19 rounds under 150 production lines, 4.85 at 600-1500); guidance only (fails the
"audit and fix" ask).

Overlaps: **T-0045** (promote watches runs), **T-0062** / **L-0564** (promote-gate), **L-0562**
(`--stamp-reach`), **T-0082** (killed rule is FAILED), **T-0044** (read-only credentials), **T-0500**
(re-offer changed phases), **T-0039** (gitignore block), **T-0104** (webtest multi-module), **T-0101**
(review receipts block).

## 5. Open questions for the owner

Answered by the owner on 2026-10-03; the decisions are in section 6.

1. Ship D10 as slice 0 now, and tell the affected repositories' sessions?
2. Approve the slicing above, or another option?
3. Should an audit GAP block a setup phase from being marked done (it could be `partial` with the GAP
   recorded), while never adding a hook?
4. A non-production environment holding live third-party credentials: a GAP with a recorded owner
   acceptance, or a hard refusal?
5. CI template for GitHub Actions only first, or Bitbucket Pipelines as well?
6. Do the two repositories' own sessions run the audit as the acceptance evidence and land their fixes
   under their own tickets?
7. Does the review-validity work (D8) belong here or in the QA-rounds stream?

## 6. Owner decisions (2026-10-03)

The owner's private companion page for this review, which names the two repositories, was updated with the same decisions on 2026-10-03.

| # | Question | Decision |
|---|---|---|
| 1 | Ship D10 as slice 0 now? | **Yes.** D10 lands first as slice 0, and the two repositories' sessions are told the Stop gate there may run nothing today. |
| 2 | Slicing | **As proposed in section 4, without slice d:** 0, then a (audit, report-only), b (correct-by-default templates and phases), c (slice b's sabotage tooling PR). Slice d moves out under question 7. |
| 3 | Does an audit GAP block a setup phase? | **No hard block.** A phase with an open GAP is marked `partial` with the GAP recorded, never `done`, and the audit never adds a hook. |
| 4 | Live third-party credentials outside production | **A GAP that needs a recorded owner acceptance**, not a hard refusal. |
| 5 | CI template | **GitHub Actions first.** Bitbucket Pipelines follows in a later slice. |
| 6 | Who fixes the two repositories? | **Each repository's own session** runs the audit as the acceptance evidence and lands its fixes under its own tickets. |
| 7 | Where does review validity (D8) live? | **In the QA-rounds stream** (`08-qa-rounds-analysis.md`), not here. D8 is review-harness work (`review_*.py`), which that stream already owns; keeping it in L-0618 would put two streams on the same harness files, which land alone. |
