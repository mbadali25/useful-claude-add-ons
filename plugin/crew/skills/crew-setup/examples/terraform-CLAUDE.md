<!-- Worked example: a Terraform module with Python Lambdas.
     The five rules people usually try to write into CLAUDE.md are split here
     between this file (judgment) and .crew/verify.json (mechanism). -->

# thd-processors

**Stack:** Terraform 1.7 + Python 3.13 Lambdas   **Runs:** TFC workspace, no local apply
**Platform:** wsl2/Ubuntu   **Shell:** bash
**Talks to:** S3 (anew-aws-datastore), SQL Server THDSalvage, SES, EventBridge

## Commands
| fmt/lint | `terraform fmt -recursive && tflint` |
| validate | `terraform validate` |
| docs | `terraform-docs .` (gate uses `--output-check`) |
| verify | `bash _verify/smoke.sh` |
| regression | `bash _verify/run-all.sh` |
| python | `ruff check . && ruff format --check .` |

## Where things are
- module root: `main.tf` (the `/** */` header is the README source — see below)
- business logic: `sql/procedures/` — NOT the Lambdas, which are orchestration only
- DO NOT TOUCH: inside `<!-- BEGIN_TF_DOCS -->` in README.md. Generated.
  Change `main.tf`'s header block, `footer.md`, or a variable `description`.

## Terraform rules
- Never `terraform apply` or `destroy`. Plan only; show me the plan.
- No deprecated syntax. If tflint flags it, fix it rather than disabling the rule.
- Provider versions: pinned in `versions.tf`. Bumping one is its own ticket with
  its own plan review — never a side effect of another change.
- Every `variable` and `output` needs a `description`. An undocumented one shows
  up as a README diff, which is the point.

## Scope discipline
- Fix the ticket, not what you notice nearby. Findings go in `.work/FINDINGS.md`.
- If a change grows past ~10 files, stop and confirm the approach.
- No new provider or module without asking.

## Stop and ask
- The change touches IAM, the security group, or the archive-delete deny
- A migration or `stg` table shape changes
- You are about to work around a failing check rather than fix it

## Promotion: development -> qa -> production
- That order, no skipping. Same plan artifact through all three - a re-plan
  between qa and prod is a different change, and qa proved nothing about it.
- `/crew:promote <env>` after every deploy: **smoke** (Lambda invokes, one CSV
  lands in stg), **regression** (full `_verify/` suite), **verify** (CloudWatch
  error alarms + the SES error mailbox, after a 10 minute soak).
- A clean TFC apply is the weakest evidence available. It proves Terraform
  converged, not that the pipeline moves data.
- Rollback runbook verified inside 90 days, or production does not deploy.
- A failed gate stops the promotion. Re-run the whole sequence, never resume.

## Reporting
- Errors verbatim. Say what you did not verify.

## Memory
`.crew/codemap/INDEX.md`, `docs/runbooks/INDEX.md`. Index first, then one file.
