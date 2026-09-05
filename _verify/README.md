# `_verify/` — the check harness

This repo is a Claude Code **marketplace**. There is no service to curl and no
environment to deploy to, so "smoke" here means *the registration invariants hold
and every executable artifact still parses* — the class of breakage that is
invisible in this working tree and real on someone else's machine.

Neither script reimplements `scripts/check-marketplace.py`. They import it and
call the same functions its `main()` does. Two homes for the same logic is how the
copies drift.

## Layout

| Script | Covers | Budget | Run it when |
|---|---|---|---|
| `smoke.sh` | 10 checks: registration, skill manifests, plugin-version agreement, catalog rows, install-script menu parity, hook command quoting, every `.ps1` parsing (**tracked and untracked**), the audit's `label()`/`canon()` contract | **14s** (cap 90s) | every change; this is the Stop-gate default |
| `run-all.sh` | everything in smoke **plus** the version-drift walk, the full install-script menu contract, and localgpu's 87 engine tests | ~6 min | before pushing; before a promotion |
| `run-all.sh --with-hooks` | additionally forces crew's blocking-guard suite, which **hangs** here | +240s to hang | only when debugging that hang |
| `cases/` | fixtures. Empty — every check builds its own throwaway state | — | — |

`smoke.sh` deliberately omits the version-drift check. It walks 58 revisions of
`marketplace.json` and runs a `git diff` per entry — ~163s on its own, against a
90s budget. It is not optional, it is just too slow to gate every edit, so it
lives in `run-all.sh`. A budget that gets blown is a suite that gets skipped.

## Sabotage status

A check nobody has broken on purpose is a check nobody knows works. Each row: the
defect reintroduced, and whether the suite went red.

| Check | Sabotage | Went red | Last verified |
|---|---|---|---|
| registration | removed `localgpu` from `marketplace.json` while the directory remained | yes | 2026-09-05 |
| skill manifests | set `skills/cloudflare/SKILL.md` frontmatter `name:` to `wrong-name-here` | yes | 2026-09-05 |
| plugin manifests | set `plugin/localgpu/.claude-plugin/plugin.json` to `9.9.9` | yes | 2026-09-05 |
| catalogs | deleted the `localgpu` row from `plugin/README.md` | yes | 2026-09-05 |
| menu parity (top level) | renamed `$script:Catalog` key `repo-plugins` → `repo-pluginsX` | yes | 2026-09-05 |
| menu parity (sub-catalog) | renamed `$script:PluginCatalog` key `localgpu` → `localgpu-TYPO` | yes | 2026-09-05 |
| hook commands | dropped `; exit $LASTEXITCODE` from a PowerShell hook | yes | 2026-09-05 |
| hook commands | single-quoted `${CLAUDE_PLUGIN_ROOT}` in a PowerShell hook | yes | 2026-09-05 |
| powershell | appended `Invoke-TotallyMadeUpCmdlet` to the **untracked** `plugin/localgpu/bootstrap.ps1` | yes — **only after a fix**, see below | 2026-09-05 |
| crew-setup round-trip | reverted `canon()`'s `commands*` wildcard | yes | 2026-09-05 |
| ruff (`**/*.py`) | added an unused `import xml.etree.ElementTree` (F401 — not in the ignore list) | yes | 2026-09-05 |
| mcp-servers (`npm test`) | changed one assertion in `packages/core/test/jwt.test.ts` from `DeviceManagementManagedDevices.Read.All` to `SABOTAGE.Wrong.Role` | yes | 2026-09-05 |
| versions (check 10) | set `pyproject.toml` back to `0.1.0` against `0.1.2` in both manifests | yes | 2026-09-05 |
| localgpu CLI (check 9) | planted a second install root with a venv; then removed the persisted PATH entry | yes | 2026-09-05 |

### One sabotage that was wrong, not a hole

Renaming a `Name =` display string in `install-prerequisites.ps1` left menu parity
green. That is correct: `check_menu_parity` compares `MENU_KEYS` against `$script:Catalog`
**keys**, and display text is not part of the contract. Re-aimed at the actual keys, both
levels went red. Worth recording because a sabotage that misses looks identical to a
coverage hole in the output.

### The one that mattered

The `powershell` sabotage **passed** on its first run — the check was vacuous for
exactly the file it claimed to cover. Two compounding reasons:

1. `check-powershell.ps1`'s CI mode enumerates via `git ls-files`, so an
   uncommitted `.ps1` is invisible to it. `plugin/localgpu/bootstrap.ps1` had
   already cleared a green gate that never opened it.
2. The obvious fix — pass every file to `-Path` — is *also* vacuous, because the
   script declares `param([string]$Path)`. One string. Passing a list binds the
   first path and silently drops the rest.

`smoke.sh` now runs CI mode once, then one invocation per untracked file. The
sabotage goes red. **The underlying script still has both limitations** — anything
else calling it inherits them.

### `mcp-servers` — the failure propagates through the exit code, not the visible tail

The sabotage changed one assertion in `packages/core/test/jwt.test.ts` — the
expected role claim from `DeviceManagementManagedDevices.Read.All` to
`SABOTAGE.Wrong.Role` — and ran `npm --prefix mcp-servers test`. This is a
workspace script that runs each package's `node --test` in turn; `packages/core`
fails early, but the last package printed (`mcp-o365-user`, 6/6 passing) is what
lands in the visible output tail. Reading only that tail would misreport the run
as green. The command's own exit code is non-zero regardless of what printed
last, which is what any caller — `_verify/README.md`'s own precondition note,
`run-all.sh`, or a human running it by hand — needs to check, not the tail.
Restored immediately after confirming red; `git diff` on `mcp-servers/` is clean.

## Known gaps

`.work/SMOKE-GAPS.md` is the full list. The one worth knowing here: crew's
blocking-guard regression suite hangs on Windows + Git Bash, so nothing currently
proves `guard.sh` still blocks on the platform this repo is developed on. It is
quarantined rather than absent, because a hanging check stalls every run instead
of failing one.

## Preconditions

`npm --prefix mcp-servers test` needs `npm --prefix mcp-servers install` run once. Without
it the rule fails with `'tsc' is not recognized` — which reads as a broken check rather
than a missing dependency. It was in exactly that state when the rule was written.

## Why check 10 exists

`check-marketplace.py` enforces `plugin.json == marketplace.json` and knows nothing about
`pyproject.toml`. A plugin that also ships a Python package therefore carries a THIRD
version that nothing compared - and `localgpu` drifted to `0.1.0` against `0.1.2` in both
manifests within a day of being created. `localgpu --version` would have reported one
number while `claude plugin update` decided on another: the same class of failure as a
missed bump, correct locally and wrong on the installed machine. The check is generic over
`plugin/*/pyproject.toml`, so the next plugin to grow one is covered without an edit.
