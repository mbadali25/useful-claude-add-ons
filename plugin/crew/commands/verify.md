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
to a smoke-harness ticket (`/crew:brainstorm`) — a map pointing at checks that cannot fail is worse than
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

The Stop gate runs ONLY `local` rules. `network`/`host` rules run under
`--all` and the merge gate, never unattended on Stop. Declaring
`"reach": "local"` runs the rule on Stop with NO inspection at all — that is
the human saying so, and the gate takes the word for it.

**An UNDECLARED rule is not quietly assumed local, and the bar for "assumed
local" is narrower than it looks.** The scanner (`verify_record.scan_reach`)
STOPS MODELLING SHELL (Codex round 6) — five rounds of "read one layer
deeper into the shell syntax" each found a new shape that defeated the last
one, so it no longer tries to parse shell at all:
- **any shell metacharacter present, anywhere, defers unconditionally** — the
  set below, plus a newline or a tab. No exception, not even a `2>&1` or a
  trailing comment. Notice: `shell syntax in an undeclared rule: declare
  "reach": "local" (or network/host)`.

  ```text
  ( ) $ ; & | < > " ' \ { } * ? [ ] ~ # !
  ```

  ...and U+0060, the backtick, which is deliberately NOT printed above.

  **Never write a literal backtick anywhere in this file.** Claude Code pairs
  SINGLE backticks when it scans a command file — it does not honour the
  double-backtick form, and it does not exempt fenced blocks. So one unpaired
  backtick leaves the whole file's spans off by one, and the prose between two
  of them is handed to bash before the command runs.

  This line did exactly that, twice. First as an inline span, where the
  fragment beginning `, a newline, or a tab` became a command and
  `/crew:verify` died with `/bin/bash: line 1: ,: command not found`. Then
  again after the list was moved into this fenced block, which looked like the
  fix and was not: a fence is three backticks, the literal one inside the list
  paired with one of them, and the file was left with an odd count — 251 — and
  an unterminated span. The rule that actually holds is parity, not container.
  `check_command_backtick_spans` enforces it.
- only once nothing on that list is present does whitespace-only splitting
  become safe. A reach verb (`ssm`, `ssh`, `curl`, `aws`, `az`, `gh`,
  `psql`, `mysql`) anywhere — notice: `remote verb <v>`.
- otherwise, if the first token is a recognised interpreter (`bash`/`sh`/
  `dash`/`zsh`/`pwsh`/`powershell`/`python`/`python3`/`py`/`node`/`ruby`/
  `perl`): `-n` is parse-only ONLY as the exact second token with EXACTLY
  one token after it (`bash -n a.sh` local; `bash a.sh -n` and
  `bash -n a.sh b.sh` are NOT); `-m` as the second token is always local
  (a module name, never a file — `python3 -m pytest x -q` is local);
  `-c`/`-Command`/`-File` as the second token always defer; any other
  token from the second position on that resolves to an existing repo
  file defers too.
- otherwise: any token at all resolving to an existing repo file defers.
- none of the above: runs undeclared.

This is deliberately conservative and, on purpose, no longer tries to be
precise about WHY a command might be safe — `verify_record.py`'s module
docstring has the full history of why "model shell more completely" turned
out not to be a fixable bug. Declare `"reach": "local"` on the rule; that is
the fix, not a smarter scanner.

`default`/`always` entries in `.crew/verify.json` get the SAME
classification on Stop — they have no `"reach"` field of their own, so a
deferred command named there is excluded from the fallback exactly like an
undeclared rule would be, never silently reintroduced through it.

`--price` refuses to time a verb-, syntax-, or wrapper-classified rule
outright, in both directions, same as the gate. The
`verifyReachUndeclared` trigger in `crew_state.py` separately flags any rule
with no `reach` at all — see `CONFIG.md` §18 for the full classification.

## Environment pinning

Every rule the gate runs gets `ENV`, `AWS_PROFILE`, `AWS_DEFAULT_PROFILE`, `AWS_DEFAULT_REGION`,
`AWS_REGION`, `AZURE_SUBSCRIPTION_ID`, `ARM_SUBSCRIPTION_ID`, `KUBECONFIG`,
`TF_WORKSPACE` and `TF_VAR_environment` unset, unless the rule declares
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
