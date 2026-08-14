# claude-obsidian setup

Two installers that bring a **Windows (WSL)** machine and a **Linux** machine to
the same [claude-obsidian](https://github.com/AgriciDaniel/claude-obsidian)
standard: a source-cited Obsidian knowledge vault driven from Claude Code.

| Platform | Script |
|---|---|
| Windows 10/11 + WSL | [`setup-claude-obsidian.ps1`](setup-claude-obsidian.ps1) |
| Linux (native) | [`setup-claude-obsidian.sh`](setup-claude-obsidian.sh) |

> Only setting up one machine and happy with the defaults? The repo bootstrap
> covers this as **menu item 19** — see
> [Quick Install](../README.md#quick-install). These scripts are the
> deeper, vault-aware version: they also create and verify the vault.

## Quick start

Both are **dry-run by default**. Nothing changes until you pass `-Apply` /
`--apply`.

```powershell
# Windows - preview, then apply (elevated for the Obsidian install)
.\setup-claude-obsidian.ps1
.\setup-claude-obsidian.ps1 -Apply

# Somewhere other than C:\repos
.\setup-claude-obsidian.ps1 -Apply -RepoRoot D:\work
```

```bash
# Linux - preview, then apply
bash setup-claude-obsidian.sh
bash setup-claude-obsidian.sh --apply

# Somewhere other than ~/repos
bash setup-claude-obsidian.sh --apply --repo-root /srv/work
```

## Paths

Everything hangs off **one root**, so a single switch relocates the whole setup.

| | Windows default | Linux default |
|---|---|---|
| Root | `C:\repos` | `~/repos` |
| Vault | `C:\repos\Claude` | `~/repos/Claude` |
| Product checkout | `C:\repos\claude-obsidian` | `~/repos/claude-obsidian` |

Change the root with `-RepoRoot` / `--repo-root`. Override either half on its own
with `-VaultPath` / `--vault` and `-ProductRoot` / `--product`.

## Switches

| Windows | Linux | Effect |
|---|---|---|
| `-Apply` | `--apply` | Actually make changes. Without it, nothing is written. |
| `-RepoRoot` | `--repo-root` | Move the whole setup (default `C:\repos` / `~/repos`). |
| `-VaultPath` | `--vault` | Vault location, independent of the root. |
| `-ProductRoot` | `--product` | Product checkout location. |
| `-SkipPlugins` | `--skip-plugins` | Don't touch marketplaces or plugins. |
| `-SkipObsidian` | `--skip-obsidian` | Don't install the Obsidian desktop app. |
| `-Distro` | — | WSL distro to use (default `Ubuntu-24.04`). |

## Shared standards

1. Dry-run by default; `-Apply` / `--apply` is the only thing that writes.
2. Every check prints `PASS` / `FIX` / `FAIL` against a stable check id.
3. Idempotent — re-running reports `already initialised` and changes nothing.
4. Identical outcome on both platforms: same vault layout, marketplaces,
   plugins, and verification.
5. Non-zero exit if any check is still `FAIL`.
6. Vault creation follows the product's own **preview-then-apply** contract: run
   the plan, read back its `approved_plan_sha256`, and pass that exact hash to
   `--apply`. An unreviewed plan is never applied.

## Python 3.11+ is a hard requirement

The product's floor is Python 3.11. Both scripts version-check it rather than merely
looking for the binary, and neither will proceed to create a vault with an older
interpreter — you get `blocked: python3 3.11+ is required` instead of a failure from deep
inside the core.

An interpreter that is *absent* is installed for you. An interpreter that is *too old* is
**not** upgraded automatically: on a distro like Ubuntu 22.04 (which ships 3.10) that
means adding a third-party repository such as deadsnakes and possibly moving
`update-alternatives`, which is too invasive to do behind one `--apply`. The scripts print
the exact remedy instead. On Windows/WSL the simplest fix is `-Distro Ubuntu-24.04`, which
ships 3.12.

## What gets installed

- Python 3.11+ (installed when absent; see above when merely outdated), git, curl,
  Node.js, Claude Code
- **Obsidian desktop** — Chocolatey (falling back to winget) on Windows;
  flatpak or snap on Linux
- The product checkout, `AgriciDaniel/claude-obsidian`
- Marketplaces and plugins:
  - `AgriciDaniel/claude-obsidian` → `claude-obsidian@agricidaniel-claude-obsidian`
  - [`kepano/obsidian-skills`](https://github.com/kepano/obsidian-skills) →
    `obsidian@obsidian-skills` (Obsidian's own upstream syntax skills:
    Markdown, Bases, JSON Canvas, the Obsidian CLI, and Defuddle)
- An initialised vault: `.claude-obsidian.json`, `.gitignore`, `inbox/`,
  `.raw/`, `wiki/` (index, log, hot cache, overview, provenance ledgers), and
  `.obsidian/` defaults

## Windows-specific landmines these scripts handle

Four things silently break claude-obsidian on Windows. The script detects and
fixes all of them — this is most of why it exists.

**1. Native Windows cannot write to a vault.**
Mutation safety is bound to POSIX directory descriptors and `fcntl.flock`.
Native Python has no `fcntl`, so the core refuses writes with
`UNSUPPORTED_PLATFORM`. Reads and dry-runs work natively; writes go through WSL,
which is why the script creates the vault from inside WSL.

**2. `python3` resolves to a Microsoft Store stub.**
Windows ships no `python3.exe`, so the name hits the App Execution Alias, which
prints an install advert instead of running Python. That breaks the plugin's
`SessionStart` / `Stop` hooks and every documented `python3 …` command. Fix: a
hard link `python3.exe → python.exe` in the Python install directory, which must
precede `%LOCALAPPDATA%\Microsoft\WindowsApps` on `PATH`.

**3. `/mnt/c` mounts without `metadata`.**
DrvFs then rejects `chmod` with `EPERM`, and every transaction apply dies with
`CORRUPT_RUNTIME_STATE: cannot write confined bundle copy`. This **cannot** be
fixed by remounting live; it needs `/etc/wsl.conf`:

```ini
[automount]
options = "metadata,uid=1000,gid=1000"
```

followed by a full `wsl --shutdown`. The script backs the file up to
`/etc/wsl.conf.bak-claude-obsidian` first.

**4. Git identity does not cross the WSL boundary.**
`checkpoint` runs inside WSL, where Windows' `git config --global` is invisible,
so it fails with `GIT_FAILED: Author identity unknown`. Fix: set identity
**repo-locally** in the vault, which both environments read from `.git/config`.

## Operating notes

- **Run WSL from PowerShell, not Git Bash.** Git Bash rewrites `/mnt/...`
  arguments and silently mangles the command.
- **Approval hashes bind to the environment that produced them.** Do the
  reviewing dry-run where the apply will run, or it fails `PLAN_CHANGED` by
  design.
- **Checkpoint immediately after each operation.** If anything touches those
  paths afterwards the checkpoint refuses — `TRANSACTION_DRIFT` when content
  changed, `COMMITTED_MODE_MISMATCH` when permissions did. Obsidian
  re-serialises `.base` files it opens, so a running Obsidian will trigger this.
- **Keep `.vault-meta/` out of git and out of sync.** It holds transaction
  journals and recovery state that can contain note text and absolute local
  paths. The generated `.gitignore` already excludes it.

## Cross-platform vaults

The vault's internal structure is fully relative and portable —
`.claude-obsidian.json` stores `"vault": "."`, and the source ledger uses
vault-relative locators. The absolute location is irrelevant, so Windows and
Linux need the same structure *inside* the vault but not the same path. That is
why the root is a single switch.

Two hazards when one vault is shared across both:

- **Case sensitivity.** Linux is case-sensitive, Windows is not. The transaction
  engine rejects case-colliding paths outright, but don't hand-create pages that
  differ only in case.
- **`.obsidian/*.json` is portable and syncs**, so the Templates and Daily-notes
  folder settings carry between machines. `workspace.json` is correctly ignored
  as per-machine UI state.

## After the script

Four steps stay manual, because the product deliberately refuses to write
arbitrary `.obsidian` config — its non-wiki allowlist is only `app.json`,
`appearance.json`, `graph.json`, `snippets/vault-colors.css`, and
`.claude-obsidian.json`:

- Settings → Templates → *Template folder location* = `wiki/templates`
- Settings → Daily notes → *New file location* = `wiki/daily`, format
  `YYYY-MM-DD`
- Settings → General → enable *Command line interface* — optional. The CLI ships
  with Obsidian; do **not** `npm install obsidian-cli`, which is the legacy
  third-party tool the product refuses to invoke.
- Open the vault in Obsidian via the vault picker

Then start a Claude session in the vault and run `/claude-obsidian:wiki`.
