# L-0680 plan: the session hooks inherit the main checkout's repo config in a linked worktree

Written 2026-10-04 by the implementing session, against `L-0680-build` after merging origin/main
`86d96fa1` and origin/T-0096-build `dfe113ab` (merge `21b77ead`). Spec: `spec.md`; direction:
`direction.md`. The resolver contract is T-0096's as merged on this branch:
`crew_repo_config_dir [root]` sets `CREW_CFG_DIR` and `CREW_CFG_SOURCE` (own, main, unknown) in
`plugin/crew/hooks/scripts/_common.sh`; `Get-CrewRepoConfigDir $Root` returns `@{ Dir; Source }`,
one body copied into each `.ps1` that needs it.

## Decisions (open questions: the recommended option taken)

1. A lane notifies with the main checkout's `notify` block (direction Q1). Documented in README.
2. An inherited relative `context.handoffPath` resolves against the lane (Q2): the path string is
   read from the resolved file; every file operation keeps the lane as its cwd.
3. The `.crew/` directory gates stay (Q3, option 1): context-watch still needs a `.crew/`
   directory in the lane before it measures anything.
4. Separate PR from T-0096 (Q4), stacked on #398.
5. `unknown` inherits nothing: the resolver points at the own `.crew/`, so each hook behaves as
   it does with no config there (no read, no write). These four hooks are not guards; none of
   them gets less guarded by this, and nothing a guard reads changes.
6. `notify.ps1` is run in-process by `context-watch.ps1` with `&`, which gives it its own script
   scope: its copy of `Get-CrewRepoConfigDir` shadows the caller's for that call only, and the
   two bodies are byte-identical anyway (held by the copies test). Safe to redefine.
7. Messages that name `.crew/config.json` as the place to set a value name the resolved file
   when it is inherited (its absolute path in the main checkout) and keep today's text when own.

## Steps (test-first: each test written and seen red before the code)

1. Tests in `plugin/crew/tests/test_worktree_config_shell.py`, both flavours (pwsh run here):
   notify (main's provider used once; lane's own config without `notify` sends nothing; the
   provider is a local HTTP stub reached through `teams` + `urlEnv`), handoff-read (inherited
   `handoffPath` + `memory.inject: false` prints the lane's note, never main's), handoff-write
   (inherited `keepTranscripts: 2` over three PreCompacts leaves two files in the lane, main's
   `.crew/` unchanged), context-watch (inherited `enabled: false`, sh, ps1 and sh-no-python;
   inherited `warnAt` warns once and names main's file), unknown (`.git` naming a missing
   directory: all four hooks as with no config), the copies test widened to seven scripts, and
   a static test that no executable line in the eight scripts names `.crew/config.json` or
   `.crew/crew.json` outside an explicit allowlist with counts.
2. bash: each of the four `.sh` hooks calls `crew_repo_config_dir .` after its `cd` and reads
   `$CREW_CFG_DIR/config.json` (and `crew.json` in handoff-write), passing the path to python as
   an argument. context-watch's no-python awk pass reads the same file.
3. PowerShell: copy `Get-CrewRepoConfigDir` verbatim into the four `.ps1` hooks; route each gate
   and read through it with `-LiteralPath`.
4. Hand sabotage: revert one routed gate per hook to the literal path; the matching lane test
   goes red; restore. Recorded in the PR body.
5. Docs: README, CONFIG.md, troubleshooting guide (src + rebuilt html/docx/pdf) drop the session
   hooks from the "not yet covered" list (L-0681 has not landed, so the list stays with the
   harness readers); README gains the notify/handoffPath sentence. CHANGELOG entry; code map
   section; diagrams (`data-flow-crew-config-read.mmd` RES note,
   `process-crew-brief-handoff-read.mmd`) and the generated page; rules regenerated;
   `.crew/verify.json` T-0096 rule gains the eight scripts, re-priced.
6. No harness path is touched (`scripts/check-tooling-pr.py` must report none). Ticket folder
   removed in the final content commit. Version commit last: crew 1.0.404.
