# T-0040 direction - on Windows, crew runs shell-heavy work in WSL2 when it is available

Status: direction APPROVED by the owner 2026-09-26 ("Approve as proposed": detect WSL2, route heavy jobs, hooks unchanged, offer (never force) an in-WSL clone, recommend install, explicit fallback).

## Ask (owner, Matthew Badali, 2026-09-26, verbatim)
"can you also make another rule on windows machines for crew configuration , if windows systems has WSL
installed or can have WSL installed run ti since the native linux commands are faster in WSL vs git bash in
windows which is notiously slower - make a tikcet"

## Facts
- Measured, not guessed (vault concept "Git Bash's per-fork cost makes WSL2 the correct shell for database and
  text work", project anew, two independent sessions on `dadeush-legion`, 2026-09-22):
  50 trivial forks 27.7-35.5s in Git Bash vs 0.19-0.20s in WSL2; 20 subshell+pipe round trips 20.4s vs 0.28s;
  200 small writes 4.43s on /mnt/c vs 0.062s on ext4. **/mnt/c is ~71x slower than WSL's own ext4 for
  small writes** - so WSL is only fast when the repo lives INSIDE the WSL filesystem.
- crew already knows the platform: `crew-setup/SKILL.md:45-53` routes Windows/WSL to `platform.md` (repo
  location under WSL "an order of magnitude in test runtime", `localhost` not reaching the Windows host
  from WSL2, CRLF breaking scripts), and config has `"platform": { "os", "wsl", "shell", "windowsHostIp" }`
  (`crew-setup/SKILL.md:153`). Nothing chooses WSL for work.
- Constraints (CLAUDE.md landmines): a bare hook `command` runs in Git Bash on Windows; "branch on the tool,
  not the OS" (a `Bash` tool call is bash syntax even on Windows); Git Bash ships without `python3`.
- Installing WSL needs admin rights and usually a reboot (`wsl --install`), so it cannot be done silently.

## Recommendation (to be confirmed)
1. **Detect** on Windows at `/crew:init`/`/crew:config`: is WSL2 installed (`wsl.exe --status`, a default
   distro), which distro, python3/git inside it, and where the repo lives. Record it in `platform.wsl`.
2. **If installed:** set `platform.shell: wsl` and route crew's shell-heavy work through it - test suites,
   sabotage, graphify, bulk text/git operations - via `wsl.exe -d <distro> -e bash -lc '...'`, with a
   path translator (`wslpath`). Hooks stay as they are (they must answer fast and exist on every machine);
   this is about crew's own long-running jobs, not every command.
3. **Repo location matters more than the shell:** if the repo is on /mnt/c, say plainly that WSL will be
   slower for file-heavy work there, and offer (never force) a clone inside WSL's ext4 (`~/repos/...`) with
   the Windows side reaching it through `\\wsl$\`. Measure before recommending: a 50-fork and 200-write probe
   on this machine, reported with the numbers.
4. **If WSL can be installed but is not:** recommend it with the measured reason and the exact command
   (`wsl --install -d Ubuntu`, admin, reboot), as a `needs-owner` item (T-0037). Never install it unasked.
5. **Fallback is explicit:** WSL missing, broken, or its distro lacking python3 -> Git Bash/pwsh as today, and
   `/crew:status` says which shell crew is using and why, so a silent fallback cannot hide a slow machine.
6. **Tests:** fixture-driven detection (installed / not installed / broken / repo on /mnt/c), the path
   translator (drive letters, spaces, UNC), and a must-allow that nothing changes on Linux/macOS.
   Real-WSL checks are measured by win-repo-2 on native Windows.

## Open questions
- Which jobs route to WSL by default? Recommendation: test suites, sabotage, graphify and refresh; leave
  interactive/one-off commands alone.
- Should crew offer to move an existing /mnt/c repo into WSL? Recommendation: offer with measurements, the
  owner decides; never move automatically (it changes paths other tools and sessions use).
- Windows hosts in play: dadeush-lenovo, dadeush-desktop, dadeush-legion (win-repo-2's machine). Measure on each.

## Amendment (owner, 2026-09-28 ~00:30 CDT) - PowerShell is a first-class route
Owner, verbatim: "one thing to add if its Windows there should be a Option for WSL and powershell , since
powershell is native to windows".

Effect on the approved spec/plan (plan aacd11aa9ea4 approval is VOID until re-planned):
- On Windows the route choice is three-way, not WSL-vs-"native": `wsl` | `powershell` | `gitbash`, plus
  `auto`. PowerShell (pwsh 7, else Windows PowerShell 5.1) is Windows' native shell and must be selectable
  in its own right, not folded into "native" as an alias for Git Bash.
- Settle at re-spec:
  - Mode names and whether `native` survives as an alias (and which shell it maps to).
  - What `auto` picks when WSL is unusable: PowerShell or Git Bash (owner's framing suggests PowerShell).
  - How a job reaches PowerShell: crew's verify-map commands and suites are bash syntax today, so a
    `powershell` route needs a per-job PowerShell form (or a stated refusal/fallback for jobs that have
    none) - never a bash string handed to pwsh. "Branch on the tool, not the OS" still holds.
  - pwsh resolution by absolute path (CLAUDE.md landmine: pwsh is not on Git Bash's PATH here).
  - `/crew:status` shell line names which of the three is in use and why.
- Unchanged: hooks untouched, gate/record writers not routed, WSL never installed, repo never moved.
Next: /crew:spec T-0040 (revise), then /crew:plan, then approval.
