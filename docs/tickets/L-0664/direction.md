# L-0664: promote-gate.ps1 treats a workflow dispatch of a declared deploy workflow as that deploy
Split from T-0062. risk: high

## Problem
After T-0062, `promote-gate.sh` reads a workflow dispatch in either spelling and gates it. `promote-gate.ps1` still matches by text containment only (`plugin/crew/hooks/scripts/promote-gate.ps1:90` and the working-map loop at `:117-135`, origin/main `155fe6d8`), so on the PowerShell tool `gh api ... /actions/workflows/<wf>/dispatches` of a declared deploy workflow runs with no check. Hooks branch on the tool, so this is a live gap on any host with the PowerShell tool, not a Windows-only one.

## Recommendation
Port the call, not the reader. `promote-gate.ps1` is native PowerShell today and runs no python. It gains the inline `Resolve-CrewPython` every other crew `.ps1` carries and calls T-0062's `_promote_dispatch.py` with `shell=powershell`, so there is still one reader. Python that cannot be resolved is "could not tell": it blocks when the command names `gh` together with `workflow` or `dispatches` and the map declares a dispatch deploy, and changes nothing otherwise.

## Options considered
1. (Taken) Call the shared helper.
2. A native PowerShell reader. Rejected: a second parser.
3. Leave PowerShell containment-only. Rejected: the same bypass on the other tool.

## Approval
Owner go 2026-10-04 for the T-0062 hand-off; open questions take the recommendation.
