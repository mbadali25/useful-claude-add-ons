---
description: Build or refresh the verification map from evidence
argument-hint: "[--refresh] [--price]"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent
---

Build `.crew/verify.json` — the map from changed paths to the checks they require.

1. **Look for `_verify/` first**, then the repo's other conventions — `qa/`,
   `spec/`, `_test*/`. If `_verify/` exists, read its `README.md` and the scripts
   in it, and map every one of them into a rule. If **none** of them exists,
   create `_verify/` from
   `${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/templates/_verify/` — `README.md`,
   `smoke.sh`, `run-all.sh`, and a `cases/` directory — then fill in that
   README's layout and status tables with what this repo actually needs. Do not
   leave the template's commented-out examples as the whole file: either write
   real checks or say plainly that the directory is a scaffold with none in it
   yet. If a convention does exist, read it and ask me what runs it and
   when. It will not be discovered for you, and it is usually the most valuable
   thing in the repo for this purpose.
2. Inventory what exists: test directories, test scripts in `package.json` /
   `*.csproj` / `Makefile` / `composer.json`, CI workflow steps, `e2e/` specs.
   Read the CI config carefully — it is the closest thing to an existing map.
3. Find what actually changes:
   `git log --format= --name-only -300 | sort | uniq -c | sort -rn | head -30`
4. Pair hot paths with the checks that cover them.
5. **Verify each pairing.** Break the code deliberately, run the mapped check,
   confirm red, revert. An unverified mapping is a guess written in JSON.
   Report any pairing that stayed green — that is a coverage hole worth knowing.
6. Time each check. Anything over ~3 minutes belongs in CI, not the local gate.
7. Write the map with a `why` on every rule and `"unmapped": "fail"`.
8. Report: rules created, paths left unmapped, and every pairing that failed
   step 4.

If the repo has no meaningful tests, do not fabricate a map. Say so, and hand off
to `crew:smoke-author` — a map pointing at checks that cannot fail is worse than
no map, because the gate turns green and everyone relaxes.

**Running the whole map, unbudgeted.** The Stop gate spends a budget
(`verify.stopBudgetSeconds`, default 60) cheapest-first and DEFERS what does
not fit, printing `deferred to /crew:verify: <cmd> (<n>s)` for each one. Those
were not checked.

**`seconds` prices the RULE, and is charged ONCE.** A rule runs whole or
defers whole, however many commands its `run` holds -- so a rule with
`"seconds": 40` and three commands costs 40 against the budget, not 120. This
sentence exists because the unit was left unstated when the budget was
introduced ("run matched rules in ascending seconds"), and the first
implementation read it per command and split rules in half.

**A command named by more than one source carries the STRONGEST obligation of
any of them.** `always` is unconditional; a rule with no `seconds` is
unconditional-until-priced; only a rule that states `seconds` is deferrable.
Naming a command in `always` and also in a 90s rule therefore RUNS it -- the
merge resolves toward running, never toward deferring.

**The obligation attaches to the RULE, so `run` order is never disturbed and
nothing is charged twice.** A rule is unconditional when it states no cost or
when any command it names is unconditional, and it then runs WHOLE, in its own
`run` order, charged its `seconds` once. Two consequences worth knowing when
you write a map:

* `run: ["prepare", "check"]` keeps `prepare` first even when `check` is in
  `always`. Where a command runs is part of what the rule means; being
  mandatory only decides whether it can be deferred.
* putting one command of a rule in `always` makes the WHOLE rule
  unconditional, because half a rule is not something anyone can say ran. If
  you want just one check unconditional, give it a rule of its own.

To run everything with no budget:

    bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/verify-gate.sh --all

(or `-All` on the PowerShell flavour). Give every rule a measured `seconds`
when you write the map -- step 6 already times them. A rule with no `seconds`
is UNKNOWN cost, not free: it always runs and the gate says its cost is
unstated, which is the honest default but a poor one to leave in place.

With `--sync`: run
`bash ${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/scripts/map-audit.sh` and reconcile.

- A check on disk with no rule: ask me what it covers, then add the rule and
  prove it fires. Do not guess the paths — a wrong mapping is worse than none,
  because it produces false confidence in the pull request.
- A rule pointing at a file that no longer exists: that check has been silently
  passing as a failure or silently skipped. Tell me which, then fix or remove it.

Report the counts before and after.

With `--refresh`: keep existing rules, add rules for paths that have appeared
since the recorded anchor, and flag rules whose target files no longer exist.

## The per-rule record replaces the single marker

Stop used to keep exactly one baseline (`.crew/.verify-verified-at`) and one
fingerprint (`.crew/.verify-gate.fingerprint`), both written ONLY when every
matched rule ran clean. A rule priced over the Stop budget on its own — this
repo's own `rules[8]` at 185s against a 60s default — was deferred on EVERY
Stop, so neither ever advanced again: the baseline froze, and every OTHER
rule re-matched and re-ran from that same old commit, forever.

`.crew/.verify-gate.record.json` (machine-local, never tracked) now carries
per-rule status alongside the two markers. A rule that is PERMANENTLY over
budget on its own — chronic, not a fluke of this turn's ordering — no longer
blocks the baseline; it is named in the record instead, and reported EVERY
turn ("NOT VERIFIED ON THIS TREE") until it actually runs clean, which only
`--all` can do. A rule that fits alone but lost to this turn's contention
(acute) still blocks the baseline exactly as before — that case is genuinely
unverified for THIS commit, not permanently unverifiable.

## `--price` (operator only, never from Stop)

    bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/verify-gate.sh --price [path] [--force]
    pwsh ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/verify-gate.ps1 -Price [-PriceTarget path] [-PriceForce]

Times every rule in a verify.json-shaped map with no budget and writes
`seconds` (ceil, min 1) for the ones that have none. Defaults to
`.crew/verify.json`; pass a path to price a different file. Never overwrites
an existing `seconds` unless `--force`/`-PriceForce` is given, and never
writes 0 — a rule that ran in under a second still costs 1.

**`.crew/verify.json` in this repo is TRACKED**, so `--price` against it
dirties a committed file. It is never reachable from the Stop hook and is
never invoked automatically by this command either — run it by hand, review
the diff, and commit the pricing separately.

## reach: `local` | `network` | `host`

The Stop gate runs ONLY `local` rules (the default, when a rule's command
matches no reach verb). `network`/`host` rules run under `--all` and the
merge gate, never unattended on Stop. Declare `"reach"` on any rule whose
command leaves this machine.

An UNDECLARED rule is not quietly assumed local: if its command contains a
reach verb (`ssm`, `ssh`, `curl `, `aws `, `az `, `gh `, `psql`, `mysql`), the
Stop gate defers it and names it — "undeclared reach, looks like it leaves
this machine" — rather than running it unattended. Declare `reach` (or
`"reach": "local"` if it genuinely never leaves the machine) to silence the
notice. `--price` refuses to time such a rule outright, in both directions.

## Environment pinning

Every rule the gate runs gets `ENV`, `AWS_PROFILE`, `AWS_DEFAULT_REGION`,
`KUBECONFIG` and `TF_WORKSPACE` unset, unless the rule declares
`"env": {"VAR": "value"}` — in which case exactly those values are set
instead. The gate prints what it pinned for every command. A rule whose
target is chosen by whatever the calling shell happened to have set cannot be
reasoned about.

## Exit 77 is SKIP

Following `_verify/smoke.sh` and GNU automake's convention, a command exiting
77 means "skipped, environment absent" — not a pass, not a fail. The gate
reports it (`SKIP (rc 77, environment absent)`), never fails the turn on it,
and never records it as verified: it is listed with the deferred/chronic
rules until it actually runs and exits 0.
