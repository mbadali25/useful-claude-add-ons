# vault-automation — a self-feeding Claude/Obsidian memory pipeline

Installs the automation layer that makes an Obsidian vault **learn, grow, and
document on its own** from Claude Code sessions:

```
work happens → capture (hooks, zero effort) → distill (nightly gardener) → recall (any session)
                                                     ↓
                        concepts + daily notes + canvases + dashboard, with provenance
```

| Piece | What it does |
|---|---|
| **Capture hooks** | Claude Code `SessionEnd` + `PreCompact` hooks append every session (id, cwd, transcript path) to `inbox/pending-reflect.md`. Costs nothing, can't break a session. |
| **Nightly gardener** | Scheduled task (`Claude Vault Gardener`, default 02:23, catches missed runs) runs headless Claude in the vault: distills up to 5 queued sessions into `wiki/concepts` pages **with populated `sources:`** and `wiki/daily` digests, updates canvases on structural change, runs a provenance pass that promotes well-attested concepts, then commits (and pushes, if a remote exists). |
| **Dashboard** | `HOME.md` Dataview views: active projects, stale concepts, unsourced concepts, daily notes, reflection queue. Maintains itself. |
| **Obsidian plugins** | Dataview, Obsidian Git, Excalidraw, Omnisearch, Kanban — installed file-level and pre-enabled. |
| **Optional git layer** | `-UseGit` / `-GitRemote` adds version history via git + obsidian-git 15-min auto-commit. |

## Sync vs git — read this first

**Obsidian Sync and git are complementary, not competing.** If the vault is on
Obsidian Sync, that is already your backup and multi-device sync — you do NOT
need git, and the gardener detects a git-less vault and skips all git steps.
The git layer adds *version history and rollback* on top. If you enable git on
multiple machines that also share Obsidian Sync, expect merge noise — pick ONE
machine for the git remote, or skip git entirely.

**Run the gardener on exactly one machine.** Two gardeners distilling the same
queue produce duplicate concepts.

## Prerequisites

- Windows 10/11, PowerShell 5.1+
- Claude Code CLI installed and authenticated (`claude.exe` on PATH or `~/.local/bin`)
- Python 3 on PATH
- An existing Obsidian vault (see [`../claude-obsidian-setup/`](../claude-obsidian-setup/) to create one)
- Recommended: the `recall` / `reflect` / `canvas` skills in `~/.claude/skills/` — the gardener leans on their conventions (the installer warns if missing)

## Run it

Dry-run by default — nothing changes until `-Apply`:

```powershell
# Preview against the default vault (C:\repos\claude-memories)
.\setup-vault-automation.ps1

# Obsidian-Sync-only vault (no git)
.\setup-vault-automation.ps1 -Apply

# With the git history layer + private remote
.\setup-vault-automation.ps1 -Apply -UseGit -GitRemote git@github.com:you/claude-memories.git

# Different vault, different gardener time
.\setup-vault-automation.ps1 -Apply -VaultPath D:\vaults\memories -GardenerTime '03:41'
```

Re-run safe: content files already present (HOME.md, inbox, plugins, hook entries) are skipped; the capture/gardener scripts and the scheduled task are refreshed in place. The self-test writes no queue entries.

## After -Apply

1. Reload Obsidian (`Ctrl+R`); if a Restricted-mode banner appears, turn it off — plugins are pre-installed and pre-enabled
2. Test end-to-end: finish any Claude session (queues an entry), then `Start-ScheduledTask 'Claude Vault Gardener'` and read the newest log in `<vault>\.claude\gardener-logs\`
3. Open `HOME.md` — the dashboard views populate as the gardener works

## What gets written where

| Path | File |
|---|---|
| `~/.claude/hooks/vault-capture.py` | Capture script (vault path baked in) |
| `~/.claude/settings.json` | `SessionEnd` + `PreCompact` hook entries (merged, existing hooks preserved, JSON validated) |
| `<vault>/.claude/gardener.ps1` | Gardener (vault + claude paths baked in) |
| `<vault>/HOME.md`, `<vault>/inbox/pending-reflect.md` | Dashboard + queue (skipped if present) |
| `<vault>/.obsidian/plugins/*`, `community-plugins.json` | Plugins (merged) |
| Task Scheduler | `Claude Vault Gardener` (run-when-logged-on, StartWhenAvailable, 2h limit) |

## Uninstall

```powershell
Unregister-ScheduledTask 'Claude Vault Gardener' -Confirm:$false
# Remove the two vault-capture entries from ~/.claude/settings.json hooks
# Delete ~/.claude/hooks/vault-capture.py and <vault>/.claude/gardener.ps1
```

## Costs & safety notes

- The gardener runs `claude -p` with `--dangerously-skip-permissions` scoped to a
  local maintenance job in your own vault; cap is 80 turns / 2 hours. Review
  `gardener-template.ps1` before applying if that concerns you.
- Distilling a heavy session costs real tokens. The 5-sessions-per-night cap and
  the "be economical" prompt keep it bounded.
- The capture hook and gardener never write credentials into notes (explicitly
  instructed; also keep secrets out of session transcripts where possible).
