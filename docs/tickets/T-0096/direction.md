# T-0096 shell and PowerShell config readers inherit the main checkout's repo config in a linked worktree

status: direction (written 2026-10-04 from the INDEX row; no direction.md existed before)

## Problem
T-0088 (merged, crew 1.0.69) made every **Python** reader of `.crew/config.json` and `.crew/crew.json` open `crew_common.repo_config_file(root, name)`. In a linked git worktree with no crew config of its own, that resolves to the main checkout's `.crew/`. T-0088 excluded the shell and PowerShell readers and its docs name the gap. In a lane worktree those hooks still read only the worktree's own file, which does not exist (`.crew/*` is gitignored), so they behave as if the repo had no config while the Python half of the same hook reads the owner's settings.

## Direction check 2026-10-04
Checked against origin/main `155fe6d8` (crew 1.0.322).

**Still true.** Nothing on main routes a shell or PowerShell reader: `git grep -n "repo_config" origin/main -- 'plugin/crew/hooks/scripts/*.sh' 'plugin/crew/hooks/scripts/*.ps1'` prints nothing, and README.md:1027-1029, CONFIG.md:147-148 and troubleshooting.md:234-236 still carry the "not yet covered" note. Two tests pin the gap for this ticket by name: `test_worktree_config.py:220-223` (the `review_gate.py` allowlist entry) and `test_review_gate.py:158-170` (`test_a_lane_follows_its_own_gate_not_the_main_checkouts_stand_down`).

**What changed since T-0088 wrote its list of nine files.** The list is short. Read at origin/main, the unrouted readers are in 19 files, not 9:
- bash: `_common.sh:341`, `verify-gate.sh:164` and `:993`, `notify.sh:8` and `:21`, `handoff-read.sh:44` and `:48`, `handoff-write.sh:12`, `:61`, `:81`, `:87`, `context-watch.sh:174`, `:250`, `:313`, `scope-guard.sh:27`, `completion-audit.sh:25`, `cloud-guard.sh:37`.
- PowerShell: `verify-gate.ps1:405`, `:510-511`, `:1363-1364`, `promote-gate.ps1:151`, `scope-guard.ps1:224`, `completion-audit.ps1:223`, `cloud-guard.ps1:199`, `auto-clear.ps1:146`, `notify.ps1:292` and `:302`, `handoff-read.ps1:227-228`, `handoff-write.ps1:297`, `:356`, `:378`, `:386`, `context-watch.ps1:140` and `:150`.
- Python, pinned on purpose: `review_gate.py:126` reads the worktree's own file so that it agrees with `verify-gate.sh:164`. The two must move together.

**Flavour and layer disagreements this causes today, in a lane with no config of its own:**
- `auto-clear.sh` takes its decision from `crew_autocycle.py` (routed, `:154`), `auto-clear.ps1:146` reads the own file. The two flavours of one hook can disagree.
- `crew_incident.py:433` reads the inherited `emergency.standDown`; `_common.sh:341` and the two inline `Test-CrewIncidentActive` copies read the own file.
- The no-python fallbacks of three guards read the own file, and "absent" is their proof of off: `scope-guard.sh:26-30`, `completion-audit.sh:24-28` (`_scope_provably_off`) and `cloud-guard.sh:35-45` (`_cloud_guard_armed`), with their PowerShell twins. In a lane whose main checkout says `scope.mode: block` or `cloudGuard: block`, a session with no usable python is let through. With python present the Python guard blocks. That is a fail-open, and it is the part of this ticket that is a defect and not only a missing feature.

## Options
1. **(Recommended, taken) One pure-shell resolver per flavour, parity-tested against `crew_common.repo_config_dir`, landed in three slices.** bash gets one function in `_common.sh`. PowerShell gets one function body copied into each script that needs it, because the PowerShell hooks have no shared file (a dot-sourced function is invisible to `scripts/check-powershell.ps1`'s static call check: `promote-gate.ps1:144-147`, `verify-gate.ps1:398-399`); a test asserts the copies are identical, as `test_completion_audit.py:615-616` does for `_scope_provably_off`. Same rules as the Python resolver: own files win whole, never merged, `unknown` inherits nothing and is never read as "absent".
2. Ask Python for the path (`python -c "import crew_common ..."`) from each shell reader. Rejected: the readers that matter most are the no-python fallbacks, which by definition cannot ask Python, and it adds an interpreter start to every hook on Windows.
3. Have the SessionStart heal copy the main checkout's config into the lane. Rejected by T-0088 already: a copy goes stale and then shadows the owner's file (`crew_common.shadowed_main_config`).
4. Close as won't-fix and keep the documented gap. Rejected: the guard fallbacks fail open in a lane.

## Why three slices
`scripts/check-tooling-pr.py:58-87` (`HARNESS`) lists `verify-gate.sh`, `verify-gate.ps1`, `scope-guard.sh`, `scope-guard.ps1`, `completion-audit.sh`, `completion-audit.ps1` and `review_*.py`. A PR that changes any of them may carry no other production file. `_common.sh`, the cloud guard, the promote gate, auto-clear and the notify, handoff and context hooks are not in that list. So the harness readers land alone, after the resolver. The non-harness readers are split in two to stay well under 300 production lines each (the PowerShell copies are about 28 lines per script).

- **T-0096 (this ticket, slice 0):** the resolver in both flavours, and the guard-class readers outside the harness: `_common.sh` (incident stand-down), `cloud-guard.sh`/`.ps1`, `promote-gate.ps1`, `auto-clear.ps1`.
- **L-0680:** the session hooks: `notify`, `handoff-read`, `handoff-write`, `context-watch`, both flavours.
- **L-0681 (tooling PR, lands alone):** `verify-gate.sh`/`.ps1`, `scope-guard.sh`/`.ps1`, `completion-audit.sh`/`.ps1`, `review_gate.py`.

L-0680 and L-0681 each need slice 0 and do not need each other.

## Open questions for the owner
Each has a default taken, so nothing here blocks.
1. **`unknown` in a no-python guard fallback.** Default: when `.git` is a file and git cannot name the main checkout, `_scope_provably_off` is false (block) and `_cloud_guard_armed` is true (refuse). The alternative is to treat it as the own file being absent, which is what main does today and is the fail-open. The cost of the default: a lane with a broken git **and** no python blocks until one of them works.
2. **The `.crew/` directory gates stay as they are.** `context-watch.sh:160`, `auto-clear.sh:87` and their twins exit when the worktree has no `.crew/` directory at all (a recorded owner decision in those files). Default: unchanged, so a lane with no `.crew/` directory still gets no context warnings even when the main checkout has a config. In this repository lanes always have `.crew/` (the code map is tracked). The alternative, treating an inheriting lane as initialised, would make those hooks create `.crew/` in a lane as a side effect.
3. **Three PRs, three version bumps.** Default: yes, forced for L-0681 by the tooling-PR rule. Slice 0 and L-0680 could be one PR of roughly 290 production lines if the owner prefers fewer PRs.
4. **`handoffPath` stays relative to the worktree.** An inherited `context.handoffPath` of `.work/HANDOFF.md` names the lane's own file, not the main checkout's. Default: yes, the same as the Python readers.

## Recommendation
Option 1, three slices, slice 0 first.
