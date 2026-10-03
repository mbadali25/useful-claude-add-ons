# T-0050 global defaults for every crew setting, and rebuildable config          status: direction   risk: high   priority: high

## Problem
The owner's crew settings live in untracked local files. Today `autopilot.mode`, `approval`, `questions` and `deploy` were set in this repo's `.crew/config.json` only. A re-clone, a new machine or a new worktree loses them: T-0029 lane-init has to copy the file in, and the file had to be backed up by hand. The machine-global `~/.claude/crew/config.json` exists (`/crew:config` walks it), but many keys are repo-only by design (the `autopilot` block among them), so the owner cannot set a personal default once for every repo. The templates (`plugin/crew/templates/config.template.json`, `global.template.json`) rebuild crew's DEFAULTS, not the owner's chosen values.

## Owner request (2026-09-26)
"Just like the previous setting, there needs to be a global config for crew and also configuration templates to rebuild in case something gets lost or needs to be regenerated."

## Recommendation
- Global layer for the owner's defaults: the `autopilot` block (mode, maxPhases, approval, questions, deploy, and later ship and maxLanes) becomes settable in `~/.claude/crew/config.json`. A repo value overrides it. Permission-widening keys stay safe: a global `approval: self` or `deploy: nonprod` applies only where the repo does not set a stricter value, and a repo `human` / `none` always wins (the same ratchet idea as guards). The owner confirms the ratchet direction per key at spec.
- Rebuild: `/crew:config --rebuild [--repo | --global]` regenerates a lost or corrupt config from the template plus the owner's saved profile, dry-run first, then `--apply`. The profile is a copy of the owner's non-default values, kept at `~/.claude/crew/profile.json` and optionally in the Obsidian vault, so it survives a re-clone and syncs to the other machines.
- Automatic backup: every crew write to either config first saves a timestamped copy under `~/.claude/crew/backups/` (keep the last N), and `/crew:config --restore <stamp>` puts one back.
- `/crew:config --show` marks each value with its layer (default, global, repo) so it is clear where a setting came from.

## Open questions (resolve at spec)
- Which keys may be set globally: the `autopilot` block only, or every key except repo-identity ones (tracker board paths, environments)? Recommendation: `autopilot`, `scope.allowCliApproval`, `resume`, provider and model choices; not environments or tracker paths.
- Should the profile also live in the vault (synced across the three machines) or only in `~/.claude/crew/`? Recommendation: both, with the vault copy as the one that syncs.

## Depends on
T-0010 (the approval and questions keys; its spec made them repo-only, which this reverses for defaults). Coordinates with T-0048 (the generated settings reference shows the layer column).

## Owner decision 2026-09-30 - catch up with main by MERGE, never rebase
Owner Matthew Badali, 2026-09-30, verbatim choice "Merge main in (Recommended)", after "rebase alot fo these before merge we did 4-5 prs outside of here that merged to main". origin/main has moved (it was a61a6f38 when this note was written: T-0088 #262, the QA fixes #263-#267, crew 1.0.69).
- Before your NEXT Review round and again right before Land: `git fetch origin && git merge origin/main` (a merge commit; mechanical conflicts only - a behavioural conflict is a STOP to the owner). Never `git rebase`, never force-push, never squash.
- After each merge: version one patch past origin/main's, refresh the artifacts until fresh and committed, re-run the suites serially under heavy-run, and state the merged origin/main sha in the phase evidence.
- A review receipt that went stale ONLY because of such a merge follows the existing merge-only rule; anything else needs a new round.

## Owner decision 2026-09-30 - run the suites in parallel (pytest-xdist installed, capped at 4)
Owner Matthew Badali, 2026-09-30, verbatim choice "Install + cap at -n 4 (Recommended)". pytest-xdist 3.8.0 is now installed (apt python3-pytest-xdist); /root/crew-tmp/heavy-run exports PYTEST_XDIST_AUTO_NUM_WORKERS=4, so `-n auto` means 4 workers inside the wrapper.
- Full crew suite, always through heavy-run: `python3 -m pytest plugin/crew/tests/ -q -n 4 -m "not wallclock"`, then `python3 -m pytest plugin/crew/tests/ -q -m wallclock` serially (both must pass). This is main's own .crew/verify.json rule with the worker count pinned. Other pytest suites: same shape.
- pylint as CI runs it: `python3 -m pylint -j 4 $(git ls-files "*.py")`.
- Quote the new timing in the evidence (the serial full suite took ~700-900s here; #263 measured ~230s at -n 4).
- A test that passes serially and fails only under -n 4 is a real finding (shared-state race, as #267's d3cf73c3), not something to paper over: report it, never skip it.
