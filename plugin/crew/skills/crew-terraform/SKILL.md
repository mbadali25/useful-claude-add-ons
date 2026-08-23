---
name: crew-terraform
description: Set up and run terraform-docs and tflint for a Terraform module, including the header comment block, footer.md, and README injection. Use when the user says set up terraform-docs, generate module docs, add tflint, lint terraform, or asks why the Terraform README keeps changing or reverting.
---

# Terraform docs and lint

## The trap to understand first

`terraform-docs` writes into the README **between the markers**:

```
<!-- BEGIN_TF_DOCS -->
...generated...
<!-- END_TF_DOCS -->
```

Anything an agent or a human edits inside that block is destroyed on the next
run. This is the single most common way Terraform documentation work gets
silently thrown away.

So the rule is absolute: **never edit inside the markers.** To change generated
content, change its source:

| To change | Edit |
|---|---|
| The narrative header | The `/** */` block at the top of `main.tf` |
| Support/contact section | `footer.md` |
| Variable descriptions | The `description` on each `variable` block |
| Output descriptions | The `description` on each `output` block |
| Section order or wording | `content:` in `.terraform-docs.yml` |

Prose that is genuinely hand-written lives **above** `BEGIN_TF_DOCS`, in the
normal part of the README. That is where "How it works", "Deploying", and
"Decisions worth knowing" belong.

## Setup

```bash
cp ${CLAUDE_PLUGIN_ROOT}/skills/crew-terraform/templates/terraform-docs.yml .terraform-docs.yml
cp ${CLAUDE_PLUGIN_ROOT}/skills/crew-terraform/templates/tflint.hcl        .tflint.hcl
cp ${CLAUDE_PLUGIN_ROOT}/skills/crew-terraform/templates/footer.md         footer.md
```

Fill in `footer.md` (owner, email, date). Then ensure the README has the marker
pair somewhere sensible — usually under a `## Module Reference` heading — because
`mode: inject` needs them to exist before the first run.

The header comes from a `/** */` block that must be the **first thing** in
`main.tf`. Inside it, every line starts with `* `. Markdown works, including
Mermaid fences, tables, and links — which makes that block the right home for the
data-flow diagram and the account inventory table.

Requires `terraform-docs >= 0.16.0`: `footer-from` and `.Module` in `content` do
not exist in earlier releases, and the failure is a confusing template error
rather than a version message.

## Running

```bash
terraform-docs .          # reads .terraform-docs.yml, injects into README.md
tflint --init             # once, to install the terraform ruleset plugin
tflint
terraform fmt -recursive -check
terraform validate
```

Wire them into `.crew/verify.json` so a `.tf` change runs them automatically:

```json
{ "paths": ["**/*.tf", "**/*.tfvars"],
  "run": ["terraform fmt -recursive -check", "terraform validate", "tflint",
          "terraform-docs markdown table . --output-file README.md --output-check"],
  "agents": ["dba"],
  "why": "fmt and validate catch syntax; tflint catches deprecated and undocumented; the `--output-check` form FAILS on a stale README instead of rewriting it. The writing form mutates the tree mid-gate, which makes README.md a changed file on the next run and trips `unmapped: fail` in a loop" }
```

Putting `terraform-docs` in the gate matters more than it looks: it means a
variable added without a `description` shows up as a failing check, so
undocumented inputs become visible rather than accumulating.

**Use `--output-check` in the gate, never the writing form.** `terraform-docs .`
rewrites `README.md`. Inside the `Stop` gate that mutates the working tree, which
makes `README.md` a changed file on the next run, which has no rule, which trips
`unmapped: fail` - and the gate now blocks on a file it edited itself. The
`--output-check` form exits non-zero when the README is stale and writes nothing.
Run the writing form by hand or from `/crew:docs`.

## The tflint rules worth knowing

The template enables the recommended preset plus documented-variables,
documented-outputs, naming-convention, unused-declarations, and
deprecated-index.

It **disables `terraform_comment_syntax` deliberately.** That rule wants `#`
comments, but terraform-docs reads its header from the `/** */` block, so leaving
the rule on flags the very thing the docs pipeline depends on. Keep the comment
in the config explaining why, or someone will "fix" it in six months.

`tflint --init` must run once per machine and once in CI before `tflint` works.
A missing plugin fails with an unhelpful message.

## Security scanning

tflint is a linter, not a security scanner. For IaC security, add `trivy config .`
or `checkov -d .` and route findings through `crew:security` rather than treating
them as lint. Keep them out of the fast local gate if they are slow — the pull
request is the right place for a two-minute scan.

## Multi-module repos

Set `recursive.enabled: true` and `recursive.path: modules` in
`.terraform-docs.yml` when the repo has `modules/*` submodules, and give each
submodule its own README with the marker pair. Otherwise the root run silently
documents only the root.
