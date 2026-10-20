<!-- Moved verbatim from plugin/crew/README.md (17. Linting, Terraform docs, and repo conventions) by L-0726; the README keeps an index entry. -->

## 17. Linting, Terraform docs, and repo conventions

### Your `_verify` directories

**These are not discovered automatically.** Nothing in crew knows what a
`_verify/` directory is, and a check nobody runs reads like coverage to the next
person — which is worse than having none.

Phase 5 now searches for `_verify/`, `qa/`, `spec/`, `_test*/` and similar, and
when it finds one it **asks you** rather than guessing: what runs it, which
changes should trigger it, does it need credentials. Then it gets a rule of its
own, with the directory named in `why` so the mapping outlives the person who
explained it:

```json
{ "paths": ["src/loaders/**"],
  "run": ["bash _verify/run.sh loaders"],
  "why": "_verify/ holds the team's hand-written QA checks for loader changes" }
```

The implementing session checks for these before writing anything, so it wires into
what exists instead of building a parallel suite that will drift out of
agreement with it.

### The verify gate on CI: a receipt for HEAD

This repository's `.github/workflows/verify-gate.yml` runs `verify-gate.sh --all`
on a pushed lane branch (`L-*`, `T-*`, `W-*`) on the self-hosted runner pool, only
while the repo variable `CREW_RUNNER` is `self-hosted`, and uploads a receipt
built by `hooks/scripts/ci_receipt.py build`. The receipt binds the verdict
(`review_gate.gate_state` asked on the runner, not the job's exit code) to the
head sha, its tree, the `.crew/verify.json` blob and a digest of the gate
implementation.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/ci_receipt.py check --root .
```

prints `CI_RECEIPT <STATE> head=<sha> <reason>` and exits 0 VERIFIED, 1
UNVERIFIED, 3 UNKNOWN (could not tell: `gh`, the network or the artifact
unreadable) or 4 NO_GATE. VERIFIED needs the newest run for HEAD to have
succeeded, that attempt's one artifact to match HEAD, its tree and map exactly,
a clean local tree, and no change on this branch to the gate implementation or
the producer. When HEAD's sha has no run at all, as on the merge commit a PR
lands on `main` (the workflow never runs there), the newest run of a parent
whose tree is exactly HEAD's (the PR head) is judged the same way and the
receipt must bind HEAD's tree, map and gate digest; a merge that changes the
producer is refused (L-0753). `/crew:review`, `crew_train.py check-land` and `/crew:done` accept
a VERIFIED receipt where the local gate is UNVERIFIED or UNKNOWN; any other
receipt answer leaves the local verdict standing. The Stop hook does not consult
it: that would put network calls in a hook that runs every turn. It is where a
rule priced over `verify.stopBudgetSeconds` on its own runs: Stop defers such a
rule every turn and names it `NOT VERIFIED ... deferred to CI` (L-0710), so its
only evidence is this receipt or a local `/crew:verify --all`.

`/crew:done` check 2 makes this receipt the precondition for whatever Stop did
not check (L-0710): a rule deferred to CI (`chronic`), a `skipped` or
`unverified` rule, a turn where `0 rules ran`, or no record at all. Check 2
passes on `CI_RECEIPT VERIFIED` (exit 0), on `NO_GATE` (exit 4), or on a record
with nothing outstanding (`verify   no rules recorded`: a clean pass empties it)
together with `GATE VERIFIED` from `review_gate.gate_state` (marker at HEAD and
the working tree's fingerprint unchanged since that pass; the marker alone
survives an uncommitted edit). Anything else refuses the close. The workflow is
not a required check on `main`; making it one is a branch-protection setting.

The receipt's per-command list is informative only. A command reads PASS, FAIL,
SKIP or UNKNOWN; UNKNOWN is a `COULD NOT TELL` line, or a command named failed,
skipped or could-not-tell with no elapsed line after it (L-0673). `log_complete` is
false unless the gate's total line comes after its last per-rule line, and with a
non-zero gate exit the job summary calls the list partial.

### Linters

Path-scoped rules in `verify.json`, per the `crew-lint` skill: `ruff` for Python,
`PSScriptAnalyzer` for PowerShell, `phpstan` + `phpcs` for PHP, `fmt`/`validate`/
`tflint` for Terraform, `eslint`/`prettier` for JS.

Two rules that keep a gate alive:

**Format automatically, lint blockingly.** Formatter in write mode, committed;
linter in check mode, failing. Arguing with a formatter in review is wasted time.

**Baseline the legacy debt on day one.** `phpstan --generate-baseline`, ruff
per-file ignores, a PSScriptAnalyzer settings file. A gate that starts red never
becomes a gate — it becomes something people pass with `--force`. Burn the
baseline down as its own tickets.

Start phpstan at level 1 and PSScriptAnalyzer at `Error` only. Level 8 on legacy
PHP produces a wall nobody reads.

### terraform-docs and tflint

Templates ship for `.terraform-docs.yml`, `.tflint.hcl`, and `footer.md`.

The critical rule: **never edit inside `<!-- BEGIN_TF_DOCS -->`.** That block is
regenerated, so edits there are destroyed silently on the next run. To change it,
change the source — the `/** */` header at the top of `main.tf`, `footer.md`, or
the `description` on each variable and output. Hand-written prose lives *above*
the marker.

Put `terraform-docs markdown table . --output-file README.md --output-check` in the gate - the `--output-check` form, which fails on a stale
README rather than rewriting it mid-gate and tripping `unmapped: fail` on its own
edit. That way a variable added without a
`description` shows up as a README diff in the pull request, so undocumented
inputs become visible instead of accumulating quietly.

One tflint note worth keeping: the template disables `terraform_comment_syntax`
**deliberately**, because that rule flags the `/** */` block terraform-docs reads
its header from. The config carries a comment explaining why — leave it there, or
someone will "fix" it in six months and break the docs pipeline.

`tflint --init` must run once per machine and once in CI. A missing plugin fails
unhelpfully.

Requires terraform-docs >= 0.16.0; `footer-from` and `.Module` in `content` do
not exist earlier, and the failure is a template error rather than a version
message.
