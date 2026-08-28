---
description: Diagnose and offer to repair the vault's git/sync posture, gardener freshness, and REST bridge
allowed-tools: Read, Write, Edit, Bash, PowerShell
---

Diagnose the configured vault. Read `~/.claude/obsidian/config.json` for
`vaultPath`; if absent, run the detection `/obsidian:init` uses and say the
vault is unconfigured once you have found or failed to find one.

Check every one of these. Report all of them, even the healthy ones - a doctor
that only speaks when something is wrong gets ignored during the run where
something actually is.

## 1. REST bridge

Probe `127.0.0.1:27123` the way `bridge_status.py` does at session start. If
down, say exactly why (not running vs. wrong port vs. rejected key) and what to
do about it - do not just say "unreachable."

## 2. Git-configured, but not a git repo

If `<vault>/.obsidian/plugins/obsidian-git/data.json` has `autoSaveInterval` or
`autoPushInterval` above 0, but `<vault>/.git` does not exist: the plugin is
firing into the void on a timer, silently, forever. Offer to fix it, and ask
which:
  - `git init` a repo here (optionally with a remote you provide), so the
    interval actually does something, or
  - turn both intervals to 0 in `data.json`, so a vault that is Sync-only stops
    paying for a plugin doing nothing.
Never silently pick one - this changes whether the vault has version history.

## 3. CLAUDE.md says something the filesystem does not

Read `<vault>/CLAUDE.md`'s statement about git/sync (if it has one) against
what `git -C <vault> rev-parse --is-inside-work-tree` and `git -C <vault>
remote -v` actually say. A mismatch here is not cosmetic: a vault's own
CLAUDE.md is what every future session trusts without checking, so a false
claim propagates. Show the drift, propose the corrected paragraph, and write it
only after confirmation - never overwrite a note the user did not ask you to
touch.

## 4. Gardener staleness

If `<vault>/.claude/logs/` (or wherever this vault's gardener writes logs, per
its own setup) has a newest entry older than 2 days AND
`<vault>/inbox/pending-reflect.md` has unchecked entries: say how many are
queued and how stale, and offer to run the `obsidian:gardener` agent now rather
than waiting for the next scheduled run.

## 5. Empty structural folders

If the vault declares `wiki/maps/` or similar map-of-content folders in its own
layout but they are empty, say so - it usually means `/obsidian:map` was never
run rather than that no map is needed, and is worth a line in the report even
though it blocks nothing.

## Report format

One line per check: OK / WARN / FAIL, plus the fix offered where applicable.
Do not apply any fix without the specific confirmation named above - this
command diagnoses; it does not act unasked.
