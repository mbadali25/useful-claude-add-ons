# L-0708 direction - kimi_probe treats an empty /tmp/.git as a repository

Status: approved 2026-10-07 (lead session subagent, owner's standing self-approve authority).
Filed 2026-10-07 on the owner's request. Reserved in `.work/HANDOFF.md` as L-0708.

## Problem

`kimi_probe._inside_a_repository` (`plugin/crew/hooks/scripts/kimi_probe.py:382`, origin/main
`7cb44221`, crew 1.1.4) says "inside a repository" when any directory from the temp dir up holds a
`.git` entry of any kind, and `probe` then refuses (`unknown`, `:544-549`). Codex's workspace-write
sandbox leaves exactly such an entry: bpftrace caught bwrap running
`--tmpfs /tmp/.git --remount-ro /tmp/.git` for `codex exec -s workspace-write` (TSS sessions), and
the mount point is an empty `/tmp/.git` directory. While it exists every Kimi probe, and so every
Kimi review, is refused, and 82 tests fail (63 in `test_review_run_kimi.py`, 19 in
`test_kimi_probe.py`; reproduced 2026-10-07 with `TMPDIR` under a directory holding an empty
`.git`: 82 failed / 144 passed, against 226 passed without it).

## Options

1. **Ask git (recommended).** Run `git rev-parse --git-dir` (scrubbed `GIT_*` env, bounded) in the
   temp dir. Exit 0 = repository (refuse). The specific "not a git repository" answer = not a
   repository (allow). Anything else - git missing, timeout, "dubious ownership", any other exit
   or message - is could-not-tell and refuses, as today. Git is the authority on what a
   repository is, so worktree `.git` files, `gitdir:` links and bare-ish layouts are judged the
   way git judges them.
2. **Shape check in Python.** Count a `.git` as a repository only when it is a directory holding
   `HEAD`, or a file starting `gitdir:`. No subprocess, but it re-implements git's discovery and
   will drift from it (`commondir`, `GIT_DIR`, ceiling and filesystem-boundary rules).
3. **Hybrid.** Keep the walk; on finding a `.git`, ask git about that directory; a `.git` git
   rejects is skipped and the walk continues upward. Most precise, most code.

Recommendation: option 1, falling back to option 3's "continue the walk" only if the spec's
Unknown U1 shows Kimi's own project discovery stops at any `.git`.

## Owner rules that apply

- This loosens a guard, so the fix needs a committed must-block and must-allow regression suite,
  sabotage-tested (CLAUDE.md "Adding a hook" rule, applied to guards).
- An unknown result must not collapse into "allowed" (CLAUDE.md Lessons).
- `sabotage_kimi.py` is in `HARNESS` (`scripts/check-tooling-pr.py:79`): new mutation entries go
  in a separate tooling PR after the feature PR (tooling-PR rule: split, do not ask).

## Host mitigation already applied

`/root/.codex/config.toml` on the Linux host now has `[sandbox_workspace_write]
exclude_slash_tmp = true`. Verified 2026-10-07: `codex exec -s workspace-write` running
`ls -ld /tmp/.git` reports no such file with the setting, and `dr-xr-xr-x ... /tmp/.git` with
`-c sandbox_workspace_write.exclude_slash_tmp=false`. Other hosts and other users' Codex configs
are not mitigated, so the code fix is still needed.
