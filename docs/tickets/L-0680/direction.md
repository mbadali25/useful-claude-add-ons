# L-0680: the session hooks (notify, handoff-read, handoff-write, context-watch) inherit the main checkout's repo config in a linked worktree

Split from T-0096 on 2026-10-04. Filed as L-0680.

## Problem
In a linked git worktree with no crew config of its own, four hooks in both flavours stop at "is there a `.crew/config.json` here" and do nothing, although the Python readers (T-0088) and, after T-0096, the guard-class shell readers use the main checkout's config. In a lane that means: no notifications (`notify.sh:8`, `notify.ps1:292`), no handoff note printed at SessionStart when `memory.inject` is off (`handoff-read.sh:44`, `handoff-read.ps1:227`), no transcript copy or handoff skeleton at PreCompact (`handoff-write.sh:61`, `handoff-write.ps1:356`), and no context warnings (`context-watch.sh:174`, `context-watch.ps1:140`). Lines are at origin/main `155fe6d8`.

## Direction
Route every read of `.crew/config.json` and `.crew/crew.json` in those eight scripts through the resolver T-0096 adds: `crew_repo_config_dir` / `crew_repo_config_file` in `_common.sh`, and a verbatim copy of `Get-CrewRepoConfigDir` in each PowerShell script. Own files win whole, never merged, `unknown` inherits nothing. Everything these hooks **write** (transcripts, markers, the handoff note) stays in the worktree.

None of the eight scripts is a review/gate harness path (scripts/check-tooling-pr.py:58-87), so this is a feature PR.

## Options
1. **(Recommended, taken)** Route the reads and the "config exists" gates; leave the `.crew/` directory gates alone.
2. Also treat an inheriting lane with no `.crew/` directory as initialised. Rejected as the default: it makes a Stop hook create `.crew/` in a lane, against the recorded owner decision in `context-watch.sh:155-160`.

## Open questions for the owner
1. A lane now sends notifications with the main checkout's `notify` settings, so several lanes ping the same channel. Default: yes, that is what inheriting means; a lane that should be quiet writes its own config.
2. An inherited relative `context.handoffPath` names a file in the lane, not in the main checkout. Default: yes, the same as the Python readers.
3. The `.crew/` directory gate (option 2). Default: unchanged.
