# terraform-lsp

Terraform code intelligence for Claude Code, through HashiCorp's
[`terraform-ls`](https://github.com/hashicorp/terraform-ls). The plugin registers
one LSP server and nothing else: no hooks, no commands, no agents, no skills.

## Install

```
/plugin install terraform-lsp --marketplace mbadali25/useful-claude-add-ons
```

or, from a shell:

```bash
claude plugin marketplace add mbadali25/useful-claude-add-ons
claude plugin install terraform-lsp@useful-claude-add-ons --scope user
```

**The plugin does not install the language server.** Claude Code starts whatever
`terraform-ls` it finds on `PATH`, so install that separately:

| Platform | Command |
|---|---|
| macOS / Linux with Homebrew | `brew install hashicorp/tap/terraform-ls` |
| Windows | `winget install -e --id Hashicorp.TerraformLanguageServer` |
| Anything else | Download a release from <https://releases.hashicorp.com/terraform-ls/>, check it against the `SHA256SUMS` file published beside it, and put the binary on `PATH` |

`scripts/install-prerequisites.sh` / `.ps1` do both halves from the **LSP
plugins** menu row. Without Homebrew (or `winget` on Windows) they stop and
print the manual route rather than download an unverified binary.

## What it registers

```json
"lspServers": {
  "terraform": {
    "command": "terraform-ls",
    "args": ["serve"],
    "extensionToLanguage": { ".tf": "terraform", ".tfvars": "terraform-vars" }
  }
}
```

The block lives in `.claude-plugin/plugin.json`, not in a separate `.lsp.json`,
because `claude plugin validate` checks an inline block and does not read
`.lsp.json` at all: a malformed inline block fails this repository's gate, a
malformed `.lsp.json` passes it.

- `serve` is terraform-ls's stdio subcommand. Run bare, it prints usage and exits.
- `terraform` and `terraform-vars` are the language IDs terraform-ls's own
  usage guide requires for `*.tf` and `*.tfvars`.
- `.tf.json` and `.tfvars.json` are deliberately not mapped. The same guide
  tells clients not to send them.
- Stacks, deployment, search and policy files (`*.tfcomponent.hcl`,
  `*.tfdeploy.hcl`, `*.tfquery.hcl`, `*.policy.hcl`) are not mapped either.
  Claude Code keys a server on a file's final extension, and `.hcl` alone would
  also claim Packer, Nomad and Terragrunt files this server cannot read.

## What to expect

terraform-ls answers from the files alone, but provider-aware answers
(attribute completion, hover on a resource argument) need the provider schemas,
which it reads from an initialised working directory. Run `terraform init` in
the module first. The server never runs `init`, `plan` or `apply` itself, and
this plugin passes it no credentials.

## Verified, and not

Verified on Linux with terraform-ls 0.39.0: the server started from the exact
command above, answered an LSP `initialize` request over stdio with 17
capabilities, and shut down cleanly.

Not verified: a Claude Code session using the server against a real Terraform
module, anything on Windows or macOS, and any terraform-ls version other than
0.39.0.
