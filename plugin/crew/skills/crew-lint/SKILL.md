---
name: crew-lint
description: Configure and run linters and formatters for PowerShell, PHP, Python, Terraform, and JavaScript, and wire them into the verification gate. Use when the user says set up linting, add a linter, format this code, run PSScriptAnalyzer, ruff, phpstan, or tflint, or asks why style keeps drifting.
---

# Linting

Linters belong in `.crew/verify.json` under `always` or a path rule — not in an
agent's head. A linter an agent remembers to run is a linter that gets skipped
on the turn it mattered.

## Per language

### Python
```bash
pip install ruff mypy
ruff check .            # lint
ruff format --check .   # formatting, replaces black
mypy src/               # types, only if the codebase is annotated
```
`ruff` covers what flake8, isort, pyupgrade and several plugins used to, in one
fast binary. Add `mypy` only where annotations already exist — turning it on over
an unannotated legacy codebase produces thousands of findings nobody will read,
which teaches the team to ignore the whole gate.

### PowerShell
```powershell
Install-Module -Name PSScriptAnalyzer -Scope CurrentUser
Invoke-ScriptAnalyzer -Path . -Recurse -Severity Error,Warning
```
Fail the gate on `Error` only at first. `Warning` on legacy scripts is usually a
few hundred findings; promote it once the error count is zero.

Settings live in `PSScriptAnalyzerSettings.psd1` at the repo root. Suppress
per-rule there rather than sprinkling `[Diagnostics.CodeAnalysis.SuppressMessage]`
through the code.

### PHP
```bash
composer require --dev phpstan/phpstan squizlabs/php_codesniffer
php -l <file>                      # syntax only, but catches parse errors fast
vendor/bin/phpstan analyse --level=1
vendor/bin/phpcs --standard=PSR12 src/
```
Start phpstan at `--level=1` on legacy code and raise it one level at a time,
each raise as its own ticket. Starting at level 8 produces an unreadable wall and
the gate gets disabled within a week.

`php -l` across changed files is cheap enough to run on every gate.

### Terraform
```bash
terraform fmt -recursive -check
terraform validate
tflint
```
See the `crew-terraform` skill — `tflint` needs `tflint --init` once, and there
is a rule you must keep disabled if terraform-docs reads its header from a
`/** */` block.

### JavaScript / TypeScript / AngularJS
```bash
npx eslint .
npx prettier --check .
```
For AngularJS 1.x, the useful rules are the deprecated-pattern ones; most modern
ESLint presets assume ES modules and will produce noise on string-annotated DI.
Configure deliberately or the output is worthless.

## Wiring into the gate

```json
{
  "rules": [
    { "paths": ["**/*.py"],  "run": ["ruff check .", "ruff format --check ."], "why": "style and common bugs" },
    { "paths": ["**/*.ps1", "**/*.psm1"], "run": ["pwsh -c \"Invoke-ScriptAnalyzer -Path . -Recurse -Severity Error\""], "why": "PowerShell errors only" },
    { "paths": ["**/*.php"], "run": ["vendor/bin/phpstan analyse --level=1", "vendor/bin/phpcs --standard=PSR12 src/"], "why": "types and PSR-12" },
    { "paths": ["**/*.tf", "**/*.tfvars"],
      "run": ["terraform fmt -recursive -check", "terraform validate", "tflint", "terraform-docs ."],
      "why": "syntax, lint, and README stays honest" }
  ]
}
```

Path-scoped, not `always`. A Python change should not wait on `terraform init`.

## Two rules that keep a gate alive

**Format automatically, lint blockingly.** Run the formatter in write mode and
commit the result; run the linter in check mode and fail on it. Arguing with a
formatter in a review is wasted time, and a formatter that only complains is
pure friction.

**Baseline legacy debt, do not fix it in the same change.** Every tool here has
a way to freeze existing findings — `ruff`'s per-file ignores, phpstan's
`--generate-baseline`, PSScriptAnalyzer's settings file. Baseline on day one so
the gate is green, then burn the baseline down as its own tickets. A gate that
starts red never becomes a gate; it becomes something people pass with `--force`.
