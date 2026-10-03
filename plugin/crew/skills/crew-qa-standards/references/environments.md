# Environment and gate standard

What a repo's QA environments, verify gate and deploy path must do so a green check means
something. Each item names the defect that earned it (`docs/review/09-qa-standards-crew.md`,
section 1, from two production repositories, ticket L-0618) and how to check and apply it.
`qa_audit.py` checks the items marked **[audited]** through `qa_audit_env.py`; the rest need a
reader. Read only the item you are applying.

The audit never deploys, never reads a secret value and never calls a remote host. An item that
needs the target to answer is a reader's item below, not an audited one.

## Gate rules that can fail

### G1 — Every rule declares `reach` and `seconds` [audited]

A rule with no `reach` is classified on Stop (CONFIG.md §19): a command with shell syntax, a
remote verb or a wrapper script is deferred, recorded as skipped while the verified-at marker
advances to HEAD, so the gate runs nothing and reads green (D10, both repositories). A plain local
command still runs undeclared.

- **Check.** `.crew/verify.json`: every rule has `reach` and a numeric `seconds`. The evidence
  separates the rules the Stop gate skips (by `verify_record.scan_reach`, the gate's own
  classifier) from the ones that run undeclared.
- **Apply.** Declare `reach` on each rule by hand (CONFIG.md §19); L-0562's
  `/crew:verify --stamp-reach` will do it once it lands. Then time each rule in the gate's own
  profile-less shell, not a login shell. A rule that mutates state gets `requiresCleanTree` or
  `reach: "host"`.

### G2 — No fire-and-forget commands [audited]

A command that dispatches and exits 0 proves the dispatch, not the result (D2).

- **Check.** Over every map command: `curl` without `-f`; `gh workflow run` without
  `gh run watch --exit-status`; a remote `send-command` without a wait-and-read; `|| true`,
  `| Out-Null`; a pipe into `tee`/`head`/`tail`/`grep -v` without `pipefail`.
  `| grep -q <expected>` is allowed: it fails when the body is wrong.
- **Apply.** Wait for the run and read its result, then exit with its status.

### G3 — `_verify` scripts: explicit env, strict flags, zero checks fails [audited]

The `_verify/` template shipped since crew 0.2.0 carries bugs both repositories fixed by hand (D1).

- **Check.** `ENV="${ENV:-...}"` (an inherited `ENV=prd` targets production); `*) shift ;;`
  (unknown flags dropped, so `--ci` makes live calls); `${READONLY:+...}` (true on `"0"`);
  `if "$@" >/dev/null 2>&1` (FAIL with no reason); `check()` defined but never called (0/0 exits 0).
- **Apply.** Refuse without `--env`; refuse unknown flags; assert the remote host before acting;
  count what was examined and FAIL on zero; a required check that SKIPs fails.

### G4 — Generated directories are ignored [audited]

An unignored build directory floods the changed-file list, overflows argv and reads as "verify.json
could not be parsed" (D6).

- **Check.** `git check-ignore` on each generated directory present. Tracked ones are reported as a
  decision to confirm, not a gap.

### G5 — `.gitignore` carries crew's `.crew/*` block [audited]

Without it the promotion approval marker is trackable, creating it dirties the tree, and the
promote gate refuses on the file it asked for (D9).

- **Check.** `.crew/*`, `.crew/.approved-*` and `.work/` are lines; `.crew/` (which kills every
  `!.crew/...` negation) is not.

### Reader items

- **Failing control per rule** (standard 20): the mutation, the red output and the date, recorded
  before a setup phase is marked done.
- **A runner never PASSes an aborted run** (23): exit code first, artifact second, partial result
  files rejected.
- **Two tiers** (29): affected checks on fix rounds, the full suite once on the final candidate.
- **Fires on unrelated changes** (28): a rule whose triggers run it on PRs that never touch what it
  proves; `/crew:verify --price` history.

## Environments

### E1 — Non-production data provenance [audited]

QA restored from production carried production API tokens and kept receiving production writes (D4).

- **Check.** Each non-production environment declares `dataProvenance`: `seeded`,
  `restored-from-prod` (with a `scrub` command) or `shared-with-prod` (with `acceptedBy`).

```json
"qa": { "dataProvenance": "restored-from-prod", "scrub": ["./scripts/scrub-qa.sh"] }
```

### E2 — Every rung's rollback is rehearsed [audited]

Rollback was declared only for production, and the first rehearsal showed the command did not work (D3).

- **Check.** Every environment has `rollback`; a runbook path carries `last verified: YYYY-MM-DD`
  within 90 days (the promote gate's ceiling); `"none"` carries a `rollbackReason`.

### E3 — Deploy the promoted SHA [audited]

`ref=$(git rev-parse HEAD)` deploys whatever is checked out, not what was proven (D2).

- **Check.** No environment `deploy` command or deploy workflow derives its ref from
  `git rev-parse HEAD`. Pass the SHA being promoted explicitly.

### E4 — Deploy workflows fail loudly [audited]

A copy step piping its exit code away left production hundreds of commits behind through green
deploys (D2).

- **Check.** In deploy workflows: no `|| true`, `| Out-Null` or `continue-on-error: true`;
  `robocopy` maps its exit codes (8+ fail); GitHub workflows set a `concurrency:` group.

### E5 — Credential inventory says where each credential reaches [audited]

Non-production held live payment and shipping credentials for weeks (D4).

- **Check.** `.crew/secrets.md` (names, never values) has a reaches column and a live column. A
  live credential reaching a non-production environment needs an owner acceptance.
- **Columns** are found by whole header words: reaches (`reach`, `reaches`, `environment(s)`,
  `env(s)`), `live`, and accepted (`accept`, `accepted`, `acceptance`). A "Delivered" column is not
  `live`.
- **Live** is `yes`, `y`, `true` or `live`, or `no`, `n` or `false`; a note in parentheses after it is
  ignored. Anything else (`?`, `TBD`, blank) is unknown, and an unknown row that may reach a
  non-production environment makes E5 UNKNOWN, naming the row. Only a reach that is production
  alone settles the row whatever `live` says.
- **Reaches** splits on `,`, `;` and `/`. Each part counts by the environment names in it: the
  declared `environments` keys, the production names (`prod`, `production`, `prd`, `live`) and the
  usual non-production ones (`dev`, `development`, `local`, `ci`, `test`, `testing`, `qa`, `uat`,
  `stage`, `staging`, `preprod`, `sandbox`, `demo`, `preview`). `production only` is production. A
  live credential whose reach is blank, or has a part naming none of these, is UNKNOWN.
- **Accepted** must be affirmative: a date (`2026-10-01`), `accepted`, `yes`, or a name. Blank,
  `-`, `?`, and a cell starting with `no`, `not`, `pending`, `TBD`, `todo`, `none`, `n/a`,
  `unknown`, `rejected`, `declined`, `awaiting` or `waiting` is not an acceptance, so a live
  non-production credential with one is a GAP.

| Name | Reaches | Live | Accepted |
|---|---|---|---|
| `STRIPE_KEY` | production | yes | |
| `STRIPE_TEST_KEY` | development, qa | no | |

### E6 — No verifier inside a served directory [audited]

A verifier script under the web root is a public endpoint (D9).

- **Check.** Nothing verifier-shaped (`verify*`, `smoke*`, `qa_check*`, `_verify/`) under
  `public/`, `public_html/`, `wwwroot/`, `htdocs/`, `www/` or `web/`.

### E7 — CI runs the gate's `_verify` entry points [audited]

One repository ran none of its local `_verify` checks in CI (D5).

- **Check.** Every `_verify/` script the map runs appears in a CI file, or its rule says
  `"localOnly": true` (a decision, recorded).

### Reader items

- **Read the deployed identity back** (11): build id or file digest from the target, compared with
  the promoted SHA. Production held an old build through three green deploys.
- **Check the job, not the run** (10): a path-gated deploy job that was skipped ships nothing.
- **Health reads the body** (12); **alerting reaches a person** (15); **deny paths with a real
  non-admin user** (14); **browser smoke per role and viewport** (13, `/crew:webtest`).
- **Test identities are not production customers** (7) and **host-only overrides are named** (8).
- **Required-check names and branch protection are recorded** (26); **runtime parity** (27).
- **Review receipts and reviewer config** (33, 34, D8) belong to the QA-rounds stream
  (`docs/review/08-qa-rounds-analysis.md`), not this standard: owner decision 7.

## Applying

Run the audit and fix one GAP at a time through the repo's gate. A setup phase with a GAP still
open is `partial` in `.crew/STATUS.md`, with the GAP named, never `done` (owner decision 3). A live
third-party credential outside production is a GAP until the inventory records an owner acceptance
(decision 4). Then stamp:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/crew-qa-standards/scripts/qa_audit.py --root . --stamp
python3 ${CLAUDE_PLUGIN_ROOT}/skills/crew-qa-standards/scripts/qa_doc.py --root . --write
```
