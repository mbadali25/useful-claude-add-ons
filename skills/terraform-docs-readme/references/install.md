# Installing terraform-docs

**Never install without asking first.** Present the options for the user's platform,
let them pick, then run the one command they chose. Do not fall back to a second
method if the first fails — report the failure and ask.

terraform-docs is a single static Go binary. Every method below just puts that one
file on PATH.

## Pick a version before installing

The repo's `.tool-versions` is the source of truth. Read the pinned version first:

```
terraform-docs 0.20.0
```

If the pin is older than the minimum the config requires (0.16.0 for `footer-from`
or `.Module` in `content`), **stop and raise it with the user** rather than installing
a newer binary that silently disagrees with the pin. Bumping the pin is a repo change
and needs their sign-off.

## asdf — preferred when the repo has a .tool-versions

Keeps every developer and the pipeline on the same version, and installs terraform
and tflint from the same file.

```bash
asdf plugin add terraform-docs
asdf install                 # installs exactly what .tool-versions pins
terraform-docs --version
```

To change the pin: `asdf set terraform-docs 0.20.0` (older asdf: `asdf local ...`),
then commit `.tool-versions`.

## Windows

```powershell
# winget (Microsoft-native, no admin needed for user scope)
winget install --id Terraform-docs.Terraform-docs --exact

# Chocolatey (needs an elevated shell)
choco install terraform-docs -y
```

Pin an exact version with `--version` (winget) or `--version 0.20.0` (choco).

Manual, if both package managers are blocked by policy — download the
`windows-amd64.zip` from the releases page, extract `terraform-docs.exe`, and put it
somewhere already on PATH. Open a new terminal afterwards; PATH is read at shell start.

For WSL, use the Linux instructions inside the WSL distro. A Windows binary is not
visible as `terraform-docs` to a Linux shell in any reliable way.

## Linux

```bash
# Homebrew (Linuxbrew), if present
brew install terraform-docs

# Direct download — works anywhere, no package manager needed
curl -sSLo tfdocs.tar.gz https://terraform-docs.io/dl/v0.20.0/terraform-docs-v0.20.0-linux-amd64.tar.gz
tar -xzf tfdocs.tar.gz terraform-docs
chmod +x terraform-docs
sudo mv terraform-docs /usr/local/bin/    # or ~/.local/bin for a user install
rm tfdocs.tar.gz
```

Substitute `darwin-amd64` / `darwin-arm64` / `linux-arm64` as needed. `brew install
terraform-docs` also covers macOS.

There is no `apt` or `yum` package in the distro repositories. If the user asks for
one, the direct download above is the honest answer.

## Python

terraform-docs is **not** published on PyPI — `pip install terraform-docs` will not
get it. If someone expects a Python route, they almost certainly mean pre-commit,
which is a Python tool that fetches the terraform-docs binary itself:

```bash
pip install pre-commit
```

with a `.pre-commit-config.yaml` entry:

```yaml
repos:
  - repo: https://github.com/terraform-docs/terraform-docs
    rev: v0.20.0
    hooks:
      - id: terraform-docs-go
        args: ["--config", ".terraform-docs.yml"]
```

That is a separate change to the repo, so raise it as its own suggestion rather than
installing it as a side effect of a docs regeneration.

## Go

```bash
go install github.com/terraform-docs/terraform-docs@v0.20.0
```

Lands in `$(go env GOPATH)/bin`, which is often not on PATH. Only reach for this if
the user already has a Go toolchain.

## Docker

Useful when nothing can be installed on the host. Mount the module read-write, since
inject mode edits README.md in place:

```bash
docker run --rm -v "$PWD:/terraform-docs" -u "$(id -u)" \
  quay.io/terraform-docs/terraform-docs:0.20.0 markdown /terraform-docs
```

The `-u $(id -u)` matters — without it the rewritten README.md is owned by root.

## After installing

Re-run the preflight to confirm the version satisfies both the pin and the config:

```bash
python3 "$SKILL_DIR/scripts/tfdocs_preflight.py" .
```
