# scripts

anchor: useful-claude-add-ons@875c9c6f
verified: 2026-09-05

## Does

The repo's own gates. They stop a plugin or skill edit from silently going
stale on other people's machines, and stop Windows-only PowerShell from
shipping broken to the one platform CI cannot exercise. Dense for their size:
260 graph nodes across 7 files.

## Entry points

- `scripts/check-marketplace.py:377` — `main()`, the CI gate. Returns 1 when
  `problems` is non-empty, after printing the count.
- `scripts/check-marketplace.py:298` — `check_versions()`, the one
  non-bookkeeping rule (see Landmines).
- `scripts/check-marketplace.py:280` — `version_set_at()`, walks
  `marketplace.json`'s git history.
- `scripts/check-marketplace.py:122` — `check_skill_manifests()`.
- `scripts/sync-updates.py:53` — `write()`, referenced from `skills/`.
- `scripts/check-powershell.ps1` — resolves every `Verb-Noun` call in every
  tracked `.ps1`, not just the installer.

## Owns data

- `.claude-plugin/marketplace.json` — read and validated, never written.
- The `<!-- BEGIN ... -->` mirror blocks in `README.md`, `skills/README.md`,
  `plugin/README.md` — written by `sync-updates.py`.

## Calls out to

- `git` — `version_set_at` shells out for history; degrades gracefully.
- Nothing else. No network, no package manager.

## Landmines

- **`check_versions` is the rule that protects other people's machines**
  (`scripts/check-marketplace.py:298`). It finds the commit where a plugin's
  *declared* version was last set and fails if that plugin's files changed
  since — because `claude plugin update` compares version strings, not
  contents. A missed bump makes the CLI report "already at the latest version"
  and copy nothing. Nothing about the repo looks wrong; the bug exists only on
  machines that already installed it.
- **It skips gracefully outside a git checkout or with no history**
  (`:305`, `:309`). That is deliberate, not a false pass — but it does mean a
  shallow clone cannot answer this check, which is why CI sets
  `fetch-depth: 0`.
- **`check-powershell.ps1` is not a parse check.** A mis-named function call
  parses cleanly and dies only at call time, on Windows. It covers every
  tracked `.ps1` — including crew's hook scripts, which run unguarded from a
  hook on someone else's machine where a thrown exception is invisible.
- **`sync-updates.py --check` has three exit codes, not two**
  (`scripts/sync-updates.py:24`): 0 current, 1 stale block, 2 structural
  problem it refuses to paper over. Treating it as a boolean loses the
  distinction between "regenerate this" and "a human must look".
- **`REQUIRED_FIELDS` is exactly four** (`:33`): `name`, `source`,
  `description`, `version`.

## Unverified

- Which specific check cross-validates the two install scripts as a matched
  pair (menu keys, order, default flags). The requirement is stated in
  `CLAUDE.md`; the enforcing function was not identified. File known, line
  unverified.
- `scripts/_test/drift-detection.sh` and `scripts/_test/menu-groups.sh` were
  not opened, so their sabotage coverage is unconfirmed.
- `check_skill_manifests()` (`:122`) exists and sits between
  `check_registration` and `check_plugin_manifests`; its body was not read, so
  which frontmatter fields it cross-checks is unknown.
