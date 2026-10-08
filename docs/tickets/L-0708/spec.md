# L-0708: kimi_probe treats an empty /tmp/.git as a repository          status: spec   risk: medium
Written against origin/main `7cb44221` (crew 1.1.4, 2026-10-07). Direction: `direction.md` (option 1, approved).

## Intent
`kimi_probe._inside_a_repository` asks git, not the file system, whether the temp dir is inside a repository.
A `.git` that git itself rejects (an empty directory, a directory with no `HEAD`) no longer refuses the probe,
so the empty `/tmp/.git` mount point Codex's workspace-write sandbox leaves stops blocking every Kimi run.
A real repository above the temp dir is still refused, and every answer git gives that is not the specific
"not a git repository" (git missing, timeout, "dubious ownership", any other exit or message) stays
could-not-tell and refuses, as today. `probe`'s refusal message and state (`unknown`) are unchanged.

## Exclusions
- No change to `probe`'s other states, the read-only flags, `kimi_env`, the stream parser or `review_run.py`.
- No new sabotage entry in this PR: `plugin/crew/tests/sabotage_kimi.py` is in `HARNESS`
  (`scripts/check-tooling-pr.py:79`). The must-allow mutation (revert to "any `.git` is a repository") goes
  in a tooling PR right after this one, on the next free L- id (tooling-PR rule: split, do not ask). The
  existing must-block mutation `sabotage_kimi.py:742-746` (deletes `if _inside_a_repository(base):`) must
  still apply; keep that line byte-identical so its anchor matches.
- No change to Codex host config (already applied on the Linux host; not a repo concern).
- No change to `review_run.py`'s tree fingerprint `.git` handling (different question: it fingerprints, it
  does not refuse).

## Evidence
- Guard: `plugin/crew/hooks/scripts/kimi_probe.py:382-397` walks from `os.path.realpath(tempfile.gettempdir())`
  upward and returns True on any `os.lstat(<dir>/.git)` success, True on any other `OSError`.
- Refusal: `kimi_probe.py:544-549`, `probe` returns `unknown` "the temporary directory ... is inside a
  repository; set TMPDIR outside it" before making the scratch dir.
- Cause: bpftrace on the Linux host caught bwrap `--tmpfs /tmp/.git --remount-ro /tmp/.git` from
  `codex exec -s workspace-write` (TSS sessions). Inside such a sandbox `ls -ld /tmp/.git` shows
  `dr-xr-xr-x 2 root root 40 ... /tmp/.git`; with `[sandbox_workspace_write] exclude_slash_tmp = true` it
  does not exist (measured 2026-10-07, codex-cli 0.160.0).
- Impact, measured 2026-10-07 on the main checkout at `7cb44221`: `TMPDIR=<dir holding an empty .git>
  pytest test_review_run_kimi.py test_kimi_probe.py` = 82 failed (63 + 19), 144 passed, 1 skipped; the
  same with a clean `TMPDIR` = 226 passed, 1 skipped.
- Git's answer for that layout: `git rev-parse --git-dir` in a dir under an empty `.git` exits 128 with
  `fatal: not a git repository (or any parent up to mount point /)`.
- Existing test that models a repository as an empty `.git`: `plugin/crew/tests/test_kimi_probe.py:480-494`
  `test_probe_refuses_a_scratch_directory_inside_a_repository` (`(repo / ".git").mkdir(...)`). Under the new
  rule it must build a real repository (`git init`) instead, or it becomes the must-allow case by accident.
- Sabotage anchor: `plugin/crew/tests/sabotage_kimi.py:742-746` names that test.
- Verify rule: `.crew/verify.json:531-548` maps `kimi_probe.py` and its tests; reach local.
- Docs describing the refusal: `.crew/codemap/crew.md:1941-1942`; `CHANGELOG.md:4086-4088` (historic entry).

## Unknowns
- U1: how Kimi Code 2.1.1 finds the project root for instructions (AGENTS.md etc.). If it stops at any
  `.git` entry, an empty `/tmp/.git` would make `/tmp` its root, and the question becomes "could `/tmp` hold
  instructions" - then use direction option 3 (skip a git-rejected `.git` and keep walking) and say so in the
  PR. Resolve by reading the CLI's source or a run with a marker AGENTS.md; record the finding.
- U2: the exact git messages to match as "not a repository" across git versions and locales. Force
  `LC_ALL=C`, match only the `not a git repository` substring with exit 128, and treat every other 128 (e.g.
  `detected dubious ownership`) as could-not-tell.
- U3: git missing from PATH on a host where Kimi is installed (Windows Git Bash case). That is could-not-tell
  (refuse), with a reason that names it, never "allowed".
- U4: environment leakage. `GIT_DIR`, `GIT_WORK_TREE`, `GIT_CEILING_DIRECTORIES`,
  `GIT_DISCOVERY_ACROSS_FILESYSTEM` would change git's answer; run git with every `GIT_*` variable removed.

## Touch
- `plugin/crew/hooks/scripts/kimi_probe.py` - `_inside_a_repository` asks `git rev-parse --git-dir`
  (cwd = the resolved temp dir, `GIT_*` scrubbed, `LC_ALL=C`, bounded timeout, stdin closed); three outcomes:
  repository, not-a-repository, could-not-tell; only not-a-repository allows. Docstring updated.
- `plugin/crew/tests/test_kimi_probe.py` - the existing refusal test builds a real repository; new tests below.
- `plugin/crew/tests/test_review_run_kimi.py` - only if a fixture there builds an empty `.git` as a repo
  (check; likely untouched).
- `CHANGELOG.md`, `plugin/crew/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` - version bump
  and entry.
- `.crew/codemap/crew.md` - the `_inside_a_repository` sentence and line anchors.
- `docs/guides/crew/src/troubleshooting.md` plus the rebuilt HTML/DOCX/PDF - only if a Kimi
  "inside a repository" entry is added; otherwise the PR body says `Docs: none beyond CHANGELOG and codemap -
  no user doc describes the temp-dir refusal` (checked: README, CONFIG, crew-providers SKILL.md,
  alternative-providers.md, guides).
- Refresh artifacts (graphify-out, diagrams) as the landing requires.

## Acceptance checks
1. must-block: a real repository (`git init` with a commit, and once with no commit) above `TMPDIR` -> `probe`
   is `unknown` "inside a repository", the runner is never called, no scratch dir is made.
2. must-block: a linked worktree (`.git` file with `gitdir:`) above `TMPDIR` -> refused.
3. must-allow: an empty `.git` directory above `TMPDIR` (no `HEAD`) -> the probe proceeds to the runner.
4. must-allow: a read-only empty `.git` (mode 0555, the bwrap shape) -> proceeds.
5. could-not-tell fails closed: git not on PATH; git timing out; git exiting 128 with a message other than
   "not a git repository" (simulate "dubious ownership"); git exiting with any other code -> `unknown`, runner
   never called. Each reason names what happened.
6. A `GIT_DIR` pointing at a real repository in the caller's env does not change the answer for an empty
   `.git` (env scrubbed).
7. With `TMPDIR` under an empty `.git`, the full Kimi suite (`test_kimi_probe.py`, `test_review_run_kimi.py`,
   `test_kimi_stream.py`, `test_kimi_docs.py`) passes - the 82 failures are gone.
8. Sabotage, run by hand in this PR and registered in the follow-up tooling PR: reverting the guard to "any
   `.git`" turns check 3 red; deleting the refusal (`sabotage_kimi.py:742` existing entry) turns check 1 red;
   mapping could-not-tell to allowed turns check 5 red.
9. `python3 scripts/check-marketplace.py` passes after the commit; verify.json's Kimi rule passes.
