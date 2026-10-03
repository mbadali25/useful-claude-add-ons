# T-0047 direction          status: ready   risk: high

## Ask
Owner (Matthew Badali, 2026-09-26), when landing T-0005: accept review round 8, land, and carry its
open findings in a follow-up ticket. On 2026-09-27 the owner asked for this ticket to go through the
workflow: "can you add more of the back log items to a workflow brainstorm -> spec -> approve ->
implement -> review -> fix -> gate -> land".

Round 8 is Codex, review dir `/repos/personal/uca-t0005/.work/review/T-0005-env-terraform--LKKlDl/`
(`out.txt`), at head `4e0abc8f`. The findings below still stand on `origin/main` `502cb137`. Since
`4e0abc8f`, `plugin/crew/hooks/scripts/crew_guards.py` has not changed, and the only change to
`plugin/crew/hooks/scripts/cloud_guard.py` is three version strings (1.0.41 -> 1.0.42). No finding
was re-run against `502cb137`. That is the spec's first Evidence item.

- BLOCK `cloud_guard.py:1394`: `xargs -rn 1 -Iplan terraform plan < verbs.txt` is allowed. The `-I`
  replace string turns a read-only word into `destroy`.
- BLOCK `cloud_guard.py:1122`: `parallel --timeout 60 terraform destroy ::: -auto-approve` and
  `parallel --delay 1 tofu workspace delete ::: production` are allowed. The guard reads the option
  value as the executable.
- BLOCK `crew_guards.py:1824`: PowerShell `Invoke-Expression -Command:"terraform destroy
  -auto-approve"` is allowed. The guard drops arguments bound with a colon.
- BLOCK `crew_guards.py:1787`: the PowerShell trigger never strips the listed wrappers, so
  `env terraform destroy${x} -auto-approve` is allowed. The `sudo` and `timeout` forms are too.
- FIX (over-block) `crew_guards.py:1553`: `terragrunt --non-interactive plan -out="p.tfplan"` and
  its run-all form are refused. The boolean option swallows the subcommand.
- FIX (over-block) `crew_guards.py:1795`: PowerShell string expressions such as
  `Write-Output ("terraform" + " destroy")` and `$message = "terraform", "destroy"` are refused.
- FIX (over-block) `crew_guards.py:1525`: `terraform workspace select "staging"` with a quoted name
  is refused, while the unquoted name is allowed.
- NIT `plugin/crew/CONFIG.md:1375`: the literal-word paragraph still says quoted commit messages and
  redirected plans are refused. They are allowed.
- Carried from `.work/HANDOFF.md` (2026-09-26 late): sabotage entry "cloud guard r5: a `pwsh -c`
  payload made at run time read" (`plugin/crew/tests/sabotage_cloud.py:909`,
  `[r5-pwsh-substituted-payload]`) stays GREEN on T-0005 `5c05c869`, so no test kills that mutant.
- Carried from T-0005: when T-0005 removed its unknown-wrapper fallback, some wrappers were left
  unjudged: `strace`, `aws-vault exec`, `unbuffer`, `systemd-run`, `git bisect run`, `rg --pre` and
  `docker run`. CONFIG.md:1515-1525 lists them under "What the guard does not catch".

## Recommendation
**Option 1: fix each direct-use spelling within T-0005's scope rule, and decide the wrapper list one
wrapper at a time.** This ticket does not add disguise detection.

- The four BLOCKs are direct spellings of commands the guard already says it catches: listed
  wrappers, `eval`'s PowerShell analogue, and `xargs`. Close each one with its own must-block case.
  - `parallel` and `xargs` get a complete table of options that take a value.
  - `xargs -I`/`-i`/`--replace` refuses when the replace string appears in a terraform subcommand
    or option position. The guard cannot know what will be substituted there.
  - PowerShell's colon binding (`-Command:<v>`) is read the way PowerShell reads it.
  - The PowerShell trigger strips the same listed wrappers as the Bash trigger, and shares one
    wrapper table with it.
- The three over-blocks each get a must-allow case, and a must-block case for the neighbouring
  spelling. Examples: `terragrunt --non-interactive destroy` must still block. So must
  `terraform workspace select -or-create "prod"` and a PowerShell `& ("terraform") destroy`.
- Make the GREEN r5 sabotage entry go RED. Either add a case that kills the mutant, or show that the
  branch it mutates is unreachable and delete the branch and its entry together. The spec decides
  which, from evidence.
- Unlisted wrappers, decided one at a time. List a wrapper only when its grammar is small and fully
  known. An options table that is missing one entry is exactly the `parallel` bug.
  - **List `aws-vault exec <profile> [--] cmd`.** It is the common way to run terraform under AWS
    credentials, and its option set is small.
  - **List `unbuffer [-p] cmd`.** Its grammar is trivial.
  - **Leave the rest documented, not caught:** `strace` and `systemd-run` (large valued option
    sets), `git bisect run` and `rg --pre` (programs that run another), and `docker run` (the
    container's entrypoint). The boundary for these stays T-0044's credentials.
- Fix CONFIG.md's literal-word paragraph. Update every other document that states the caught and
  not-caught lists, per the repo's crew docs rule.
- Tests come first. Every fix gets a sabotage entry that goes RED, plus a check of the neighbouring
  case, as the project CLAUDE.md requires after `vault_guard.py`'s seven rounds. Windows (PowerShell
  twin) verification goes to win-repo-2, as it did for T-0005.

Why: this closes every accepted finding in the terms the guard's own documentation already uses,
and adds no new class of detection that would need its own review series.

## Options
1. **Direct-use fixes plus a per-wrapper list decision (recommended).** Tradeoff: the list of
   wrappers the guard does not catch stays non-empty by design. Each listed wrapper is a table to
   keep complete.
2. **Bring back an unknown-wrapper fallback.** The guard would refuse any command in which
   `terraform`/`tofu`/`terragrunt` appears as an argument word after a head it does not know. It
   catches `strace`, `systemd-run` and the rest at once. But T-0005 removed this because it
   over-blocked (quoted commit messages, `echo`, `grep terraform`). It also contradicts the
   direct-use scope the owner accepted on 2026-09-26, and it would reopen the over-block findings
   this ticket is closing.
3. **Document only and defer to T-0044.** Cheapest. But four BLOCKs would stay open on spellings
   CONFIG.md says are caught, so the document would be false. And the three over-blocks would keep
   refusing ordinary read-only work unattended.

## Open questions
The recommendation answers each of these. The spec may overturn an answer only with evidence.

- Should the list also add `strace`, `systemd-run` or `nice`/`ionice`-style wrappers? Answer: no,
  apart from wrappers already listed. Revisit a wrapper only if someone shows it is used to run
  terraform in practice.
- Overlap with T-0009, which another agent is building, stacked on T-0005. Its spec also touches
  `plugin/crew/hooks/scripts/cloud_guard.py` and `crew_guards.py`. The overlap is textual, not a
  dependency. Whichever ticket lands second merges the other, and a behavioural conflict is a stop.
  The spec records this under Unknowns.

## Depends on
T-0005, merged to `origin/main` (`4ed4b763`, crew 1.0.42).

## Approval
Direction approved under the owner's standing authorization (2026-09-26, "no longer ask me for
approvals"), recorded 2026-09-27 by the brainstorm phase of the owner's backlog workflow.

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
