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
an external program (`python`, `bash`, `git`, `pwsh`), take candidates only from
`Get-Command <name> -All -CommandType Application`. Never use a bare
`(Get-Command <name>).Source`: a profile `function` or `alias` of the same name comes earlier
in PowerShell's command precedence, wins the lookup, and has no `.Source`. Where a candidate
lives never decides whether it is believed. Every candidate is executed before it is trusted,
under a bound (a per-candidate timeout that kills the whole process tree, and an overall
deadline inside the hook's timeout). It is accepted only on proof the real program alone can
give: its process exit code plus a structured answer, for example a JSON object carrying its
version and executable path. On real Windows, a candidate that `CreateProcess` cannot launch
(no `.exe`, `.com`, `.cmd` or `.bat` extension) is skipped before it is started. When every
candidate is rejected, return nothing and refuse by name. Never fall back to the bare name,
which `&` re-resolves through the same lookup to the shim that was just rejected.

**Why.** Hooks run without `-NoProfile`, so a profile function can shadow the real program.
A candidate that is never executed can be a stub, a shim or the wrong interpreter. A bare-name
fallback re-runs the rejected candidate. Each way, a blocking hook silently allowed, reported a
tool missing on a machine that has it, or hung. 3 findings across 3 change sets: a python
resolver that took the first `Get-Command` result with no Application filter, so a profile
function won with an empty `.Source` (crew-0.19.69); a resolver that never executed a
candidate to prove it (crew-0.19.92); a bash resolver that returned the bare name `bash` on
total rejection, so `&` re-resolved it to the rejected shim and hung (crew-1.0.23). Those
reviews also asked for WindowsApps aliases to be rejected by path and for only the first match
per name to be taken. The 1.0.5 Windows burn-in reversed both: a working alias is accepted,
and a broken one falls through to a same-named program further down PATH. So this rule asks
for proof, not location (`plugin/crew/tests/test_ps1_python_probe.py`).

**Change sets.** 3: crew-0.19.69, crew-0.19.92, crew-1.0.23

**Applies when.** Any `Get-Command`, `.Source`, `.Path`, `& $exe` or `Process.Start`, or a
resolver function (`Resolve-*`) that chooses an interpreter or tool to launch, and any `.ps1`
that runs an external program by a bare name from a hook or other unattended path.

**Self-check.**
1. Does every lookup of an external program filter on `-CommandType Application`? Pass: yes,
   with no bare `(Get-Command x).Source` left in the diff.
2. Is every candidate executed and proven (exit code plus a structured answer) before it is
   trusted, rather than accepted or rejected by where it lives? Pass: yes, with a test that
   puts a broken candidate ahead of a working same-named one.
3. Is each probe bounded (a timeout that kills the process tree, and an overall deadline inside
   the hook's timeout)? Pass: yes, with a test using a candidate that hangs.
4. When every candidate is rejected, does the caller get an empty result and refuse by name,
   never a bare name that `&` would re-resolve? Pass: yes, with a test that runs the real
   script on an all-rejected PATH.
5. Was a profile `function` of the same name tried? Pass: the resolver still finds the real
   program or refuses by name.
   Example starting grep, not the definition: `Get-Command|\.Source|-CommandType|Process\.Start|Resolve-`.

**Earned by.**
- crew-0.19.69 security review of the 0.19.63 scope layer, commit `fe8187e9`, "crew 0.19.69: the
  gate resolves python the way it already resolved bash": "The interpreter for the scope report
  was `(Get-Command python3, python | Select-Object -First 1).Source`" and "a `function python
  { }` in a user profile is loaded and returned AHEAD of any python.exe with an empty
  `.Source`, which then failed the truth test and made the gate report "no python" on a machine
  that has python" (CHANGELOG entry "`crew` 0.19.69")
- crew-0.19.92 PowerShell-security-hardening review of `role-write-guard.ps1` (PR #200,
  squash `621d50dc`), FIX: "`Resolve-CrewPython` never executed a candidate to prove it was a
  real interpreter (role-write-guard.sh's own resolver does)" (CHANGELOG entry "`crew` 0.19.92")
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
