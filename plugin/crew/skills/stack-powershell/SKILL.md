---
name: stack-powershell
description: |
  Windows PowerShell 5.1 and PowerShell 7 pitfalls, checks and verify.json wiring - encoding
  defaults, TLS, module compatibility, and security hardening. Use when the repo has *.ps1 or
  *.psm1 files, or the user asks to write or review a PowerShell script, decide between 5.1
  and 7 for a target host, or asks why a generated file is UTF-16 or why Install-Module fails.
---

# Stack: PowerShell (5.1 and 7)

## When this applies

Any repo with `*.ps1`/`*.psm1`. **5.1 is present by construction; 7 is a deployment.**
Windows Server ships 5.1 and cannot remove it; `pwsh` exists only where someone installed it.
Establish which edition the *target host* actually has before writing - a script for a
scheduled task, a GPO startup script, or an installer's custom action calls `powershell.exe`
(5.1) unless something explicitly changed it to `pwsh.exe`.

## 5.1-only cases (hard blocks on 7, not preferences)

- **`ADSync`** (Azure AD Connect / Entra Connect) - Framework-only, no supported 7 build.
- Modules with no .NET Standard build, older vendor modules, COM-heavy automation.
- Anything that must run before 7 is installed - bootstrap, imaging, an Intune script.
- `powershell.exe` invoked by something you do not control (a years-old scheduled task, an
  SSM document, a GPO script) - it calls 5.1 regardless of what the code prefers.

## Pitfalls that cost time - 5.1

- **`>`/`Out-File` write UTF-16LE; `Set-Content`'s default is the ANSI codepage.** Neither is
  UTF-8. Set `-Encoding UTF8` explicitly - and know 5.1's `UTF8` means *with a BOM*, which
  breaks a shebang or a `.service` unit. BOM-less UTF-8 needs
  `[IO.File]::WriteAllText($path, $text, (New-Object Text.UTF8Encoding($false)))`.
- **`Install-Module` fails on TLS** - 5.1 defaults to TLS 1.0/1.1 and the PowerShell Gallery
  requires 1.2. Every install path starts with
  `[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12`.
- **`ConvertTo-Json` truncates at depth 2 with no warning.** Always pass `-Depth`.
- **The language is 2016** - no ternary, no `??`, no `&&`/`||`, no `-Parallel`. Code lifted
  from a 7 example is a parse error, and a parse error in 5.1 stops the *whole file* loading.
- **`$PSVersionTable.PSVersion.Major -eq 5` is the only honest version check** - `$host.Version`
  is the host's, not the engine's.

## Pitfalls that cost time - 7

- **`-UseWindowsPowerShell` is a proxy, not a port.** It runs the module in a background 5.1
  process; what returns is deserialized - a property bag with no methods. `.Save()`/`.Delete()`
  on the result fails at runtime, not parse time.
- **`ConvertTo-Json` still defaults to `-Depth 2`** - not a 5.1 bug that got fixed, the same
  default (7 at least warns on truncation).
- **`ForEach-Object -Parallel`**: each runspace is a fresh session - variables need `$using:`,
  and `$ErrorActionPreference` does not flow in; an error inside `-Parallel` will not stop the
  outer loop unless made to.
- **UTF-8 without a BOM is the default here** - a script moved from 5.1 starts writing files a
  5.1-side consumer may not expect; check what reads the output before treating it as a pure win.

## Security hardening (both editions)

Execution policy documented, no plaintext creds (use SecretManagement/Key Vault/DPAPI),
module/script-block logging enabled, remoting restricted to JEA or a constrained endpoint,
least-privilege service accounts. No `Write-Host` of a secret; sanitise error output.

## Verification

Report what actually ran: a `-NoProfile -Command` syntax parse, PSScriptAnalyzer with the
repo's settings and its exit code, `-WhatIf` output for every mutating step. State
`$PSVersionTable` and whether the target host actually has `pwsh` before claiming a 7 result.

## verify.json rules to propose (5.1 and 7 checked separately)

```json
{
  "paths": ["**/*.ps1", "**/*.psm1"],
  "run": [
    "sh -c 'PW=\"\"; for c in pwsh pwsh.exe \"/c/Program Files/PowerShell/7/pwsh\"; do if command -v \"$c\" >/dev/null 2>&1 || [ -x \"$c\" ]; then PW=\"$c\"; break; fi; done; if [ -z \"$PW\" ]; then echo \"TOOL MISSING: pwsh (PowerShell 7) is on no known PATH, so the 7-targeted analysis DID NOT RUN. Install PowerShell 7 to check locally.\" >&2; exit 77; fi; \"$PW\" -NoProfile -Command \"if (-not (Get-Module -ListAvailable -Name PSScriptAnalyzer)) { [Console]::Error.WriteLine(\\\"TOOL MISSING: PSScriptAnalyzer module is not installed for pwsh, so the 7-targeted analysis DID NOT RUN. Install-Module PSScriptAnalyzer to check locally.\\\"); exit 77 }; \\$r = Invoke-ScriptAnalyzer -Path . -Recurse -Severity Error -Settings @{Rules=@{PSUseCompatibleSyntax=@{Enabled=\\$true;TargetVersions=@(\\\"7.0\\\")}}}; if (\\$r) { \\$r | Format-Table -AutoSize; exit 1 }\"'",
    "sh -c 'PW=\"\"; for c in powershell.exe powershell \"/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe\"; do if command -v \"$c\" >/dev/null 2>&1 || [ -x \"$c\" ]; then PW=\"$c\"; break; fi; done; if [ -z \"$PW\" ]; then echo \"TOOL MISSING: Windows PowerShell 5.1 is on no known PATH (Linux/macOS host), so the 5.1-targeted analysis DID NOT RUN.\" >&2; exit 77; fi; \"$PW\" -NoProfile -Command \"if (-not (Get-Module -ListAvailable -Name PSScriptAnalyzer)) { [Console]::Error.WriteLine(\\\"TOOL MISSING: PSScriptAnalyzer module is not installed for Windows PowerShell 5.1, so the 5.1-targeted analysis DID NOT RUN. Install-Module PSScriptAnalyzer to check locally.\\\"); exit 77 }; \\$r = Invoke-ScriptAnalyzer -Path . -Recurse -Severity Error -Settings @{Rules=@{PSUseCompatibleSyntax=@{Enabled=\\$true;TargetVersions=@(\\\"5.1\\\")}}}; if (\\$r) { \\$r | Format-Table -AutoSize; exit 1 }\"'"
  ],
  "agents": ["powershell-security-hardening"],
  "reach": "local",
  "why": "5.1 and 7 accept different syntax - one green run does not prove the other edition parses"
}
```

Both stages fail closed at three points, not one: no `pwsh`/`powershell.exe` on PATH exits 77 before
PowerShell ever starts; a resolved host missing the `PSScriptAnalyzer` module exits 77 from inside
`-Command` before analysis runs (`Get-Module -ListAvailable` first - Invoke-ScriptAnalyzer on a
missing module is an ordinary error, not this repo's tool-missing convention); only then does
`Invoke-ScriptAnalyzer` run, capture its result, and `exit 1` if it found anything - the cmdlet
itself never sets the process exit code, so a findings-only run that skipped this three-way split
would print violations and still report PASS. One `-Settings` argument per invocation: passing the
bundled `PSGallery` preset alongside a second `-Settings` hashtable is a duplicate-parameter error
that PowerShell rejects before any file is analysed.

Copies the exit-77 tool-missing pattern already used for `.ps1` files in this repo's own
`.crew/verify.json` (the `pwsh`-resolution rule). Nothing in this repo writes rules into
`verify.json` on a skill's behalf (see `crew-verification`) - add by hand.

## LSP

None decided for this stack.
