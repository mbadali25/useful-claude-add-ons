# Terraform — Example Project

Hand-written content lives ABOVE the markers and is never touched by
terraform-docs. Put prerequisites, common commands, CI/CD notes and
deployment caveats here.

## Prerequisites

- [asdf](https://asdf-vm.com/) with the terraform, terraform-docs and tflint plugins
- Credentials for the `svc-terraform` service account

```bash
asdf install   # installs the versions pinned in .tool-versions
```

## Common Commands

```bash
terraform validate
tflint

# Regenerate the generated block below from main.tf header + footer.md
terraform-docs .
```

---

<!-- BEGIN_TF_DOCS -->
<!-- END_TF_DOCS -->
