---
name: stack-terraform
description: |
  Terraform-specific pitfalls, checks and verify.json wiring - state, plan replacements,
  count/for_each re-indexing, module interfaces. Use when the repo has *.tf files, a change
  touches a backend block or provider version, or the user asks to write, refactor or review
  HCL, run `terraform plan`, or explain a "forces replacement" line.
---

# Stack: Terraform

## When this applies

Any repo with `*.tf`/`*.tfvars` files. Read the backend block, provider version constraints
and `.terraform.lock.hcl` before writing a line - they say which state you are about to move
and which provider API you are writing against. `terraform apply`, `destroy`, `import`,
`state mv/rm` and `taint` are never something an agent runs unattended; a human runs those
knowing which account is targeted.

## Pitfalls that cost time

- **Read the plan for replacements, not the count.** `# forces replacement` on a database,
  a stateful volume or an ENI is the finding - "3 to add, 1 to change, 1 to destroy" hides
  which one. Quote the replacement lines verbatim.
- **`count` re-indexes everything after the change; `for_each` does not.** `count` addresses
  each instance by a numeric index (`resource.name[2]`), so removing the middle element of a
  `count` list shifts every index after it - Terraform sees that as destroying and recreating
  each shifted resource, not just the one removed. `for_each` addresses instances by the map
  key or set value itself, so removing one element leaves every other instance's address
  untouched - there is no "unkeyed `for_each`" to re-index. Converting `count` to `for_each`
  over stable keys is still a state operation (the resource addresses change shape), not a
  plain edit.
- **State is the product.** A local backend means the state lives on one laptop; a remote
  backend without locking lets two applies corrupt it. State holds secrets in plaintext, so
  a state file written anywhere readable is a finding regardless of what the code does.
- **An unpinned provider upgrades under you between plans**; `~>` on a major version still
  lets a minor version change behaviour. The lock file belongs in the commit.
- **Secrets do not belong in variables with defaults, committed `.tfvars`, or outputs** -
  `sensitive = true` hides a value from CLI output, not from the state.
- **`depends_on` added to fix a race usually hides a missing reference.** Implicit
  dependencies through attribute references are what let Terraform parallelise correctly.
- **A module interface is an API.** Renaming a variable breaks every caller; adding a
  required variable breaks them at plan time. Say which callers were checked.

## Verification

Run `terraform fmt -check`, `terraform validate`, and `terraform plan` where credentials and
a backend are reachable - report exit codes, never the summary line. If plan could not run
(no credentials, no backend access), say so and say which claims are therefore unverified: a
validated-but-unplanned change is a syntax result, not a behaviour result.

## verify.json rule to propose

Add this rule to the target repo's `.crew/verify.json` (see the `crew-verification` skill for
the file's shape) rather than inventing a separate mechanism - nothing in this repo writes
rules into `verify.json` on a skill's behalf, so state the JSON here and let the session add
it:

```json
{
  "paths": ["**/*.tf", "**/*.tfvars", "**/*.tf.json", "**/*.tfvars.json"],
  "run": [
    "sh -c 'command -v terraform >/dev/null 2>&1 || { echo \"TOOL MISSING: terraform is not on PATH, so fmt/validate DID NOT RUN. This is a missing tool, not a passing or failing check. Install Terraform to check locally.\" >&2; exit 77; }; terraform fmt -check -recursive && terraform validate'",
    "sh -c 'command -v tflint >/dev/null 2>&1 || { echo \"TOOL MISSING: tflint is not on PATH, so the lint pass DID NOT RUN. Install tflint (and run tflint --init once) to check locally.\" >&2; exit 77; }; tflint --recursive'"
  ],
  "reach": "local",
  "why": "fmt/validate/tflint catch drift and syntax before a human ever runs plan"
}
```

A missing tool exits **77**, the code `verify-gate.sh` and every existing probe in this
repo's own `.crew/verify.json` (e.g. the `pwsh`/`ruff` rules) already treat as UNVERIFIED,
never PASS - copy that shape rather than a bare `command -v` check that silently exits 0.
`paths` includes the JSON variants of both file types - `*.tf.json` and `*.tfvars.json` are
valid Terraform/tfvars syntax and a change there should trigger the same rule. Bare `tflint`
only lints the current directory's module; `--recursive` walks nested root modules too (verify
the flag is still current for the installed tflint version - it has been stable since tflint
0.42).

## LSP

No official Terraform LSP plugin is decided for crew 1.0 (unlike C#/Python/TypeScript/Angular
below). If the editor wants one, HashiCorp's `terraform-ls` is the community option; install
it yourself rather than expecting crew to wire it.
