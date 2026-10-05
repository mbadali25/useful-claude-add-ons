---
set: PWSH
applies-to: ["**/*.ps1", "**/*.psm1", "**/*.psd1"]
---

# PowerShell development standards (PWSH)

Build-time standards for Windows PowerShell 5.1 and PowerShell 7, applied when any changed file
matches `**/*.ps1`, `**/*.psm1` or `**/*.psd1` (L-0534, T-0086 slice 4). The set is `PWSH`
because the loader takes set names of two to six capitals. Each standard refines the GEN
standard its Rule names and supplies the PowerShell mechanics. A standard ships here only when
findings from at least three distinct reviewed change sets earn it, counted as `python.md`'s
lead paragraph counts them: a crew review, or a fix commit whose own message or CHANGELOG entry
records that a review found the defect. Commits of one review series or one PR count once.
`crew-0.19.69`, `crew-0.19.92` and `crew-1.0.23` are crew versions in this repository: a
security review of the 0.19.63 scope layer (commit `fe8187e9`), the PowerShell-security-
hardening review of `role-write-guard.ps1` inside PR #200 (squash `621d50dc`), and BLOCK B2 of
the native-Windows PowerShell review from win-repo-2 that the 1.0.23 CHANGELOG entry records
(fix `9e57868d`, regression test `735c225d`). Public third-party change sets do not count (owner, 2026-10-05). The owner's
research numbering is kept: PWSH-16 here is that rule's command-resolution half, as the spec
names it. Its `Set-StrictMode` half has no change set and stays a candidate. The research text
itself was not available to this build, so the mapping rests on the spec's description. Every
other rule is a candidate in the `stack-powershell` skill's `references/candidates.md`.
Official documentation is kept as **Source**, quoted from learn.microsoft.com at
`view=powershell-7.5` and re-read from the raw page on 2026-10-05; it is not a change set. A
self-check's grep is an example starting grep, not the definition.

## PWSH-16 An external program is resolved to an Application that is proven to run, never to whatever name lookup returns first

**Rule.** Refines GEN-01 (an unknown must not collapse into the safe-looking value). To find
an external program (`python`, `bash`, `git`, `pwsh`), take only
`Get-Command <name> -CommandType Application`. Never take a bare
`(Get-Command <name>).Source`, which a profile `function` or `alias` of the same name wins
because it comes earlier in PowerShell's command precedence. Reject the `WindowsApps` App
Execution Alias stub and extensionless PATH shims. Take the first acceptable match per name,
as bash's `command -v` does, and move to the next name on rejection: never walk `-All` past a
rejected stub to a same-named program further down PATH. Prove the candidate before trusting
it: run it and check both its output (for example `sys.executable`) and `$LASTEXITCODE`. When
every candidate is rejected, return nothing and refuse by name. Never fall back to the bare
name, which `&` re-resolves through the same lookup to the shim that was just rejected.

**Why.** Hooks run without `-NoProfile`, so a profile function shadows the real program and
leaves `.Source` empty. The Store's alias stub is a real Application that resolves and runs
an installer prompt. Either way a blocking hook silently allowed, reported a tool missing on
a machine that has it, or hung. 4 findings across 3 change sets: a python resolver that took
the first `Get-Command` result with no Application filter (crew-0.19.69); a resolver that
never executed a candidate to prove it, and one that walked `-All` past a WindowsApps stub to
a same-named python (crew-0.19.92); a bash resolver that returned the bare name `bash` on
total rejection, so `&` re-resolved it to the rejected shim and hung (crew-1.0.23).

**Change sets.** 3: crew-0.19.69, crew-0.19.92, crew-1.0.23

**Applies when.** Any `Get-Command`, `Get-Command -All`, `.Source`, `.Path`, `& $exe`, or a
resolver function (`Resolve-*`) that chooses an interpreter or tool to launch; any `.ps1`
that runs an external program by a bare name from a hook or other unattended path.

**Self-check.**
1. Does every lookup of an external program filter on `-CommandType Application`? Pass: yes,
   with no bare `(Get-Command x).Source` left in the diff.
2. Is the WindowsApps alias stub (and an extensionless shim) rejected, and does rejection
   move to the next name rather than further down PATH for the same name? Pass: yes, with a
   test that puts a stub ahead of a same-named real program.
3. Is the chosen candidate executed and its output and `$LASTEXITCODE` checked before it is
   trusted? Pass: yes.
4. When every candidate is rejected, does the caller get an empty result and refuse by name,
   never a bare name that `&` would re-resolve? Pass: yes, with a test that runs the real
   script on an all-rejected PATH.
5. Was a profile `function` of the same name tried? Pass: the resolver still finds the real
   program or refuses by name.
   Example starting grep, not the definition: `Get-Command|\.Source|-CommandType|WindowsApps|Resolve-`.

**Earned by.**
- crew-0.19.69 security review of the 0.19.63 scope layer, commit `fe8187e9`, "crew 0.19.69: the
  gate resolves python the way it already resolved bash": "The interpreter for the scope report
  was `(Get-Command python3, python | Select-Object -First 1).Source` -- four lines away from
  `Resolve-CrewBash` in the SAME file, which filters on `CommandType -eq 'Application'` and
  excludes the WindowsApps App Execution Alias for exactly these reasons." (CHANGELOG entry
  "`crew` 0.19.69")
- crew-0.19.92 PowerShell-security-hardening review of `role-write-guard.ps1` (PR #200,
  squash `621d50dc`), FIX: "`Resolve-CrewPython` never executed a candidate to prove it was a
  real interpreter (role-write-guard.sh's own resolver does), and `Get-Command $name -All`
  walked past a WindowsApps stub to a SAME-NAMED real python further down PATH, while bash's
  `command -v` takes only the first match per name" (CHANGELOG entry "`crew` 0.19.92")
- crew-1.0.23 native-Windows PowerShell review from win-repo-2, BLOCK B2, fix commit
  `9e57868d`: "**B2: `verify-gate.ps1`'s `Resolve-CrewBash` refuses instead of re-invoking a
  rejected bare `bash` shim**" (CHANGELOG entry "`crew` 1.0.23"); the commit: "Resolve-CrewBash's
  PATH fallback returned the bare string 'bash' when every candidate was rejected by the
  native-extension gate (or none found), and `& $bashExe` re-resolves that bare name through
  PowerShell's own PATH lookup -- landing back on the exact rejected shim and hanging."

**Source.**
- https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_command_precedence?view=powershell-7.5:
  "If you specify the path to a command, PowerShell runs the command at the location specified
  by the path." "If you don't specify a path, PowerShell uses the following precedence order
  when it runs commands." "Therefore, if you type help, PowerShell first looks for an alias
  named help, then a function named help, and finally a cmdlet named help." "You can use
  Get-Command to determine which command is chosen first." "The All parameter of the
  Get-Command cmdlet gets all commands with the specified name, even if they're hidden or
  replaced."
