# T-0102 Linux tools on a Windows system, and SSM's limits: one marketplace reference skill

Written 2026-10-04 from the ticket's INDEX row. The direction drafted in the Windows-side session on 2026-09-28 was never copied to this box: `.work/tickets/T-0102/` did not exist, and the offload branch holds no file for it. This file rebuilds the direction from the row and checks it against origin/main `155fe6d8`.

## The ask
Owner request, 2026-09-28: write down how to use Linux tools on a Windows system, and what AWS Systems Manager (SSM) will and will not carry, so that no oversized payload is silently truncated on its way through SSM.

## The problem
- A session on Windows keeps relearning the same facts: which shell a command lands in, why a path is rewritten, why `python3` or `pwsh` is not found, why a script grows CRLF line endings. This repo records them as landmines in its own CLAUDE.md, but that file helps this repo only. Nothing installable carries them to another repo or machine.
- SSM Run Command returns only the first 24,000 characters of stdout and the first 8,000 of stderr through the API. The cut is silent: the call succeeds and the status is `Success`. A caller that parses the returned text acts on a partial answer. The same holds in the other direction for a large script or file pushed through a command parameter.

## Options
1. **One marketplace reference skill (recommended).** `skills/windows-ssm/` with a short SKILL.md, `references/windows-tools.md`, `references/ssm-limits.md` (every number cited to an AWS documentation page) and one small offline helper that reads a `get-command-invocation` result and exits non-zero when the output is, or may be, cut. This is the option the INDEX row names.
2. Two skills, one per subject. Rejected: the two subjects meet in practice (the usual case is a Windows node driven through SSM from a Windows or Linux workstation), each registration costs seven files, and one skill with two reference files loads only the half a task needs.
3. Put the text into crew (`crew-setup/platform.md`, `stack-powershell`). Rejected: it would reach only crew users, it grows crew's markdown budget, and every crew change carries the full crew document set.
4. Documentation only, no helper. Kept as the fallback. The owner's phrase is "no oversized payloads truncated", and prose alone cannot make a truncated result fail. The helper is the part that fails loudly.

## Recommendation
Option 1. The helper stays small and offline: it makes no AWS call, holds no credentials and reads one JSON document. It reports three outcomes, complete, truncated and could-not-tell, and only the first exits 0.

## Direction check 2026-10-04
Checked against origin/main `155fe6d8`.

Still true:
- No skill covers either subject. `git ls-tree --name-only origin/main skills/` lists 35 skill directories and none is about Windows shells or SSM. `git log origin/main -i --grep='ssm\|windows-tools'` finds no commit that adds such a skill.
- SSM appears on main only in passing: as a reach verb in crew's verify map (`plugin/crew/CONFIG.md:1456`, `:2453`, `plugin/crew/commands/verify.md:179`) and as one clause in `plugin/crew/skills/stack-powershell/SKILL.md:26`. Nothing states a limit.
- The Windows shell facts live in the repo CLAUDE.md "Landmines" section and in crew's setup skill (`plugin/crew/skills/crew-setup/SKILL.md:51-55`, `phases.md:76-86`). They are written for crew's own setup, not as a general reference.
- The AWS numbers were re-read on 2026-10-04 from the AWS API reference and the service quotas page (see spec.md, Evidence).

Changed since the row was written:
- T-0040 merged (PR #290, crew 1.0.98) and added crew's shell routes (`auto`, `wsl`, `powershell`, `gitbash`). The new skill must describe choosing a shell in general terms and point to crew's route setting, not restate or contradict it.
- The marketplace holds 35 skills (it was 34 when the row was written; `mailgun` landed as L-0561). The count this ticket moves is 35 to 36.

Recommended option: unchanged, option 1.

## Open questions for the owner
Each has a default already taken in spec.md.
1. Skill name. Default: `windows-ssm`. Alternatives: `windows-linux-tools`, `ssm-limits`.
2. Is the helper in or out? The row calls it optional. Default: in, as an offline checker of about 110 lines with its own tests. Alternative: ship the two reference files first and file the helper as a follow-up.
3. Output exactly at the limit (24,000 characters of stdout) cannot be told apart from cut output. Default: treat it as truncated and exit non-zero, because an unknown must not read as the safe value.
4. Default-on in the install menu, like every other skill here. Default: yes. It registers no hook.
