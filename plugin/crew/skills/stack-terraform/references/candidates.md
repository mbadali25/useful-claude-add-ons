# Terraform candidate standards (not gated)

No gated Terraform standards set ships yet (L-0536). Nothing in this file is loaded by
`crew_standards.py` or asked in the pre-review self-check. It is guidance, kept with its
evidence. A rule is promoted once three distinct reviewed change sets earn it, into
`crew-standards/references/terraform.md` with `applies-to: ["**/*.tf", "**/*.tftest.hcl"]`.
The set id is **`TF`** (owner, 2026-10-05): the loader accepts set names of 2 to 6
capitals, so the spec's `TERRAFORM` would be refused. A promoted rule keeps its research
number, so TERRAFORM-03 ships as `TF-03`.

**Why nothing ships.** The bar and the counting rule are `python.md`'s: a change set is a
crew review, or a fix commit whose own message or CHANGELOG entry records that a review
found the defect. There is no file-type condition. A plan failure, an apply failure, a
Terraform Cloud run, a tool alert or the author's own fix is not one. The spec's re-count
over the owner's private repositories put no rule above 2: -05 1, -06 1, -09 1, -10 1,
-11 2, -12 2, -14 1, -16 1, -17 1, and 0 for the rest. The owner decided on 2026-10-05
that public third-party change sets do not count. The rules below come from a public pass
on 2026-10-05, and its change sets are recorded as leads, each counted 0. The private PR
review threads that might lift -11 or -12 were not reachable.

**How the public pass read its evidence.** Commit messages came from GitHub commit
search. Diffs were not read. Every Source sentence was string-matched against the raw
HashiCorp page on 2026-10-05. TERRAFORM-03 and TERRAFORM-12 are research ids that the
spec names by content. Mapping them to the public rules below is inferred. TERRAFORM-P1
is a label from the public pass, not a research id. The research text for TERRAFORM-01
to -19 was not available, so the other ids are not written here.

## Candidate standards (not gated)

### TERRAFORM-03 No literal account IDs or ARNs: derive them (research id inferred)

0 counted. 4 public change sets, not counted. 0 in the spec's private re-count.

Do not hard-code account IDs, account-scoped ARNs, repository names or region strings in
`.tf`. Use `data.aws_caller_identity`, `data.aws_region` and `data.aws_partition`,
resource attribute references, or variables. A literal ties the module to one account,
breaks in a second environment, and publishes identifiers. Settled position: the
stricter form applies to new code. An existing literal-ARN fix in a private repository is
not reopened.

Public change sets (message text only):
- `vantagexai-cb90d0fe` (paupaf3/vantagexai@cb90d0fe): a full code review replaced a
  hard-coded AWS account ID with `data.aws_caller_identity`.
- `devnavi-19a63b78` (hwchany0ung/DevNavi@19a63b78): "Terraform code review findings (pass
  2)". The SSM ARN is now scoped through `data.aws_caller_identity`, and a hard-coded
  repository name became a variable.
- `awsportfolio-898eb71b` (Daichi-Kubota/aws-infra-portfolio@898eb71b): "QA review fixes -
  hardcoded IDs".
- `databuilder-83c5a850` (jmg887/databuilder@83c5a850): a PR review minor finding. A
  secrets ARN now uses the caller identity's account id and `var.region`.

Rejected leads: two where it could not be determined whether the review found the
account-id defect, and one that kept the literal deliberately.

Source: https://developer.hashicorp.com/terraform/language/data-sources: "You can instruct
Terraform to fetch data from a range of data sources, including APIs, external Terraform
workspaces, and function outputs." "Data sources fetch data from the provider, but do not
create or modify resources." No HashiCorp page that was fetched says "do not hard-code
ARNs", and the style guide has no such line.

Public verdict: admitted on public stand-ins (4). That does not count under the owner's
decision.

### TERRAFORM-P1 Secrets never surface as outputs, and sensitive inputs are `sensitive = true`

0 counted. 2 public change sets, not counted.

A secret is never an `output`. A variable or output that must carry one is marked
`sensitive = true`, knowing that this hides it from CLI output, not from state. This
extends the secrets pitfall in `SKILL.md`.

Public change sets (message text only):
- `traefik-cab21c3d` (traefik-workshops/traefik-demo-resources@cab21c3d): a follow-up from a
  v4 review marks a password variable `sensitive = true`.
- `vigilant-27e69baa` (iamharryliu/vigilant-broccoli@27e69baa): "A security review flagged
  that ... tokens were exposed as Terraform outputs".

Source: https://developer.hashicorp.com/terraform/language/values/outputs: "If you are
outputting sensitive data such as a password or API key, use the sensitive argument to
prevent Terraform from displaying the value in CLI output:"
https://developer.hashicorp.com/terraform/language/state/sensitive-data: "If you are
developing with Terraform locally, Terraform stores your state in a plaintext file, which
includes any secret values you defined in your configuration."

Public verdict: candidate (2).

### TERRAFORM-12 CloudWatch log groups are encrypted with a customer-managed KMS key (research id inferred)

0 counted. 0 public change sets. 2 in the spec's private re-count.

Settled position, flagged: "CMK always" is the lane's draft. Only one private
repository's evidence supports it, and no public review-recorded change set was found.
The one public lead is a Checkov alert, which is a tool finding and is not counted.

## Settled questions

- **`for_each` in `import` blocks needs Terraform 1.7.0.** Confirmed in the raw
  `v1.7/CHANGELOG.md`, section "1.7.0 (January 17, 2024)": "`import`: `for_each` can now
  be used to expand the `import` block to handle multiple resource instances". The spec
  puts `import` blocks themselves at 1.5 or later; this build did not re-check that.
- **CMK for log groups:** see TERRAFORM-12. It stays a candidate, and the flag stands.
- **TERRAFORM-03 and the existing literal-ARN fix:** the stricter form is for new code.
