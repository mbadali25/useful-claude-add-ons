---
description: Diagnose and offer to repair the vault's git/sync posture, gardener freshness, and REST bridge
allowed-tools: Read, Write, Edit, Bash, PowerShell
---

Diagnose **every** configured vault. Read `~/.claude/obsidian/config.json` for
`vaults` (or the legacy `vaultPath`, treated as one vault named `memory`); if
absent, run the detection `/obsidian-vault:init` uses and say the vault is
unconfigured once you have found or failed to find one.

Checks 1 run once per vault. Checks 2-5 run once per vault that has the
matching feature configured for it (a second vault with no gardener wired up
simply has nothing to check there). Report all of them, even the healthy ones
- a doctor that only speaks when something is wrong gets ignored during the
run where something actually is.

## 1. REST bridge, per vault

For each configured vault, probe `127.0.0.1:<that vault's port>` (and
port+1 for the HTTPS side) the way `bridge_status.py` does at session start.
If down, say exactly why (not running vs. wrong port vs. rejected key) and
what to do about it - do not just say "unreachable." Name the vault in every
line; "the bridge is down" is not useful once there is more than one.

## 2. Git-configured, but not a git repo

Run this per vault. If `<vault>/.obsidian/plugins/obsidian-git/data.json` has `autoSaveInterval` or
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
queued and how stale, and offer to run the `obsidian-vault:gardener` agent now rather
than waiting for the next scheduled run.

## 5. Empty structural folders

If the vault declares `wiki/maps/` or similar map-of-content folders in its own
layout but they are empty, say so - it usually means `/obsidian-vault:map` was never
run rather than that no map is needed, and is worth a line in the report even
though it blocks nothing.

Checks 3 and 4 (CLAUDE.md drift, gardener staleness) apply to the default
vault - the capture hook and gardener are wired to it, not to every vault. A
second vault with no `inbox/pending-reflect.md` at all simply has nothing to
be stale.

## 6. Companion plugins - report only, never install

Doctor never installs anything; it only says what is missing and points at
`/obsidian-vault:init`'s Companions step to fix it. Check once, not per vault:
- `obsidian@obsidian-skills` present via `claude plugin list`? If not, and its
  marketplace (`kepano/obsidian-skills`) is reachable via `claude plugin
  marketplace list`, report it missing with the one-sentence reason it is
  complementary (infrastructure here vs. workflow skills there), not a
  duplicate. If the marketplace itself is unreachable, say that instead of
  "missing."
- `graphify --version` resolves? If not and any configured vault has
  `"layout": "org/repo"` (i.e. a codegraphs vault exists), report it missing -
  `/obsidian-vault:graph` cannot run without it.
- `crew@useful-claude-add-ons` installed, only worth checking when a vault
  holds ticket boards or code-graph output? Report missing in one line if so;
  say nothing about it for a memory-only vault.

## Report format

Group by vault, then one line per check: OK / WARN / FAIL, plus the fix
offered where applicable. Do not apply any fix without the specific
confirmation named above - this command diagnoses; it does not act unasked.
