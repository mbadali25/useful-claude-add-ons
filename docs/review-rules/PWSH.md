<!-- crew-standards-export digest=df6052ac0825389b086b6ca038d9f2c0e191ea1a5407dee8f55424f8dff3a8e6 crew=1.2.86 -->
# Review rules: set PWSH

Applies to: files matching `**/*.ps1`, `**/*.psm1`, `**/*.psd1`.
Generated from crew's standards by `crew_standards.py export --write`; do not edit by hand. Check a change against every standard here whose scope matches the files it touches.

## PWSH-16 An external program is resolved to an Application that is proven to run, never to whatever name lookup returns first

**Rule.** Refines GEN-01 (an unknown must not collapse into the safe-looking value). To find
an external program (`python`, `bash`, `git`, `pwsh`), take candidates only of command type
Application: `Get-Command <name> -All -CommandType Application`, or `Get-Command -All` with
each result's `CommandType` checked before its path is used. Never use a bare
`(Get-Command <name>).Source`: a profile `function` or `alias` of the same name comes earlier
in PowerShell's command precedence, wins the lookup, and has no `.Source`. Location alone
never makes a candidate believed. A documented exclusion of a launcher that runs in the wrong
environment is allowed, for example Windows' `System32\bash.exe`, the WSL launcher, which
proves it is bash but runs outside the Windows tool environment a hook needs. Every remaining
candidate is executed before it is trusted,
under a bound (a per-candidate timeout that kills the whole process tree, and an overall
deadline the caller sets; in a hook, that deadline sits inside the hook's timeout). It is accepted only on proof the real program alone can
give: its process exit code plus a structured answer, for example a JSON object carrying its
version and executable path. On real Windows, a candidate without a launchable extension is
skipped before it is started. An `.exe` or `.com` file can be started directly, but a `.cmd`
or `.bat` file runs only through `cmd.exe /c`, so it is never passed straight to
`Process.Start`. When every
candidate is rejected, return nothing and refuse by name. Never fall back to the bare name,
which `&` re-resolves through the same lookup to the shim that was just rejected.

**Self-check.**
1. Does every lookup of an external program keep only Application results (with
   `-CommandType Application`, or by checking each result's `CommandType`)? Pass: yes, with
   no bare `(Get-Command x).Source` left in the diff.
2. Is every candidate executed and proven (exit code plus a structured answer) before it is
   trusted? Is any exclusion by location a documented wrong-environment launcher, not a guess?
   Pass: yes to both, with a test that puts a broken candidate ahead of a working same-named
   one.
3. Is each probe bounded (a timeout that kills the process tree, and an overall deadline the
   caller sets, inside the hook's timeout when the caller is a hook)? Pass: yes, with a test
   using a candidate that hangs.
4. When every candidate is rejected, does the caller get an empty result and refuse by name,
   never a bare name that `&` would re-resolve? Pass: yes, with a test that runs the real
   script on an all-rejected PATH.
5. Was a profile `function` of the same name tried? Pass: the resolver still finds the real
   program or refuses by name.
   Example starting grep, not the definition: `Get-Command|\.Source|-CommandType|Process\.Start|Resolve-`.

