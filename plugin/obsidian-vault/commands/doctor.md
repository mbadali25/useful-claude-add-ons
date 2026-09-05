---
description: Diagnose every configured vault - REST bridge, port collisions, git posture, gardener freshness - and report, without changing anything
argument-hint: [vault-name]
allowed-tools: Read, Bash, PowerShell, Grep, Glob
---

Diagnose every configured vault and report. **This command is read-only by
design.** It has no `Write` and no `Edit`, so it cannot repair what it finds
even if you ask it to mid-run. Everything that acts lives in
`/obsidian-vault:repair` and `/obsidian-vault:install`; hand off to those by
name instead of typing a fix here.

## 1. Run the diagnosis

```
python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" diagnose
```

Add `--vault <name>` for one vault when $1 names one. Add `--json` when you
want to reason over the result rather than quote it; `diagnose` is read-only,
so `--json` is available there. If `python` is not on PATH, try `python3` then
`py`, and say which one worked - Git Bash on Windows ships without `python3`.

**Read the exit code before you read the output.**

| Exit | Means |
|---|---|
| 0 | Every vault **you asked about** is healthy. Say so per vault and move on. |
| 1 | Problems found. This is a successful run, not a crash - report the findings. |
| 2 | Usage error. You passed a flag the script does not take. Fix the invocation; do not report a vault problem. |

The exit code is scoped to the selection, and so are the labels. A `--vault`
run still prints every port collision on the machine, because a collision the
selected vault is not part of is often the thing that explains its symptoms -
but one it is not part of is printed `[ELSEWHERE]`, names the vaults it does
belong to, and does not move the exit code. Only `[FAIL]` counts. Do not report
an `[ELSEWHERE]` line as a failure of what was asked; report it as a real
problem belonging to the vaults it names, which is worth raising and is fixed by
scoping to one of them or running unscoped. The `--json` output carries the same
distinction as `in_scope` on each collision.

Report every vault, including the healthy ones. A doctor that only speaks when
something is wrong gets ignored during the run where something actually is.

## 2. Explain the verdicts

The script decides; you translate. Three verdicts need more than their one-line
message.

**Port collision.** Two vaults declaring the same port is one cause with three
symptoms, and each symptom on its own points somewhere wrong:

- HTTP never listens for the losing vault.
- HTTPS answers, but with the *other* vault's API key.
- The bridge serves the *other* vault's files.

Only one plugin instance wins the bind. The loser fails to start its server at
all, which takes its HTTP listener down with it - so "HTTP is dead" and "HTTPS
returns a stranger's notes" are the same fault, not two. Say that plainly, then
point at `/obsidian-vault:repair fix-ports`.

Do not diagnose this from the symptom. Diagnose it from the declarations:
`diagnose` compares `port` and `insecurePort` across **every** vault's
`.obsidian/plugins/obsidian-local-rest-api/data.json`, including vaults absent
from `~/.claude/obsidian/config.json`. A vault this plugin has never been told
about still binds ports.

**Stale plugin instance.** The Local REST API plugin reads its `data.json` only
at load. A vault whose file was edited since its Obsidian window opened
disagrees with disk on both the port and the API key, and every probe of it
reports something that is true of neither. The fix is a window reload, not
another edit: `/obsidian-vault:repair reload`.

**Cert rejected.** `curl -k` against the HTTPS port succeeds where Claude Code's
Node MCP client rejects the same self-signed certificate. A hand-run `curl -k`
that works therefore proves the vault is up - it does not prove the MCP server
will connect. Never conclude from a green `curl -k` that the bridge is healthy,
and never repoint an MCP server at the HTTPS port to chase one.

## 3. Checks the script does not make

These need judgement or a file the script does not read. Run them yourself, per
vault, and report only - do not offer to apply any of them, because this command
cannot.

**Git configured, but not a git repo.** If
`<vault>/.obsidian/plugins/obsidian-git/data.json` has `autoSaveInterval` or
`autoPushInterval` above 0 but `<vault>/.git` does not exist, the plugin is
firing into the void on a timer, silently, forever. Report it with both possible
resolutions named - `git init` the vault, or set both intervals to 0 - and let
the user pick. This changes whether the vault has version history, so it is
never a default.

**CLAUDE.md says something the filesystem does not.** Compare `<vault>/CLAUDE.md`'s
statement about git and sync against `git -C <vault> rev-parse
--is-inside-work-tree` and `git -C <vault> remote -v`. A vault's own CLAUDE.md is
what every future session trusts without checking, so a false claim propagates.
Show the drift and the corrected paragraph; the user applies it.

**Gardener staleness.** If the default vault's gardener log directory
(`<vault>/.claude/logs/`, or wherever that vault's setup writes) has a newest
entry older than 2 days *and* `<vault>/inbox/pending-reflect.md` has unchecked
entries, say how many are queued and how stale, and point at
`/obsidian-vault:garden`.

**Empty structural folders.** A vault declaring `wiki/maps/` or similar
map-of-content folders with nothing in them usually means `/obsidian-vault:map`
was never run. Worth a line even though it blocks nothing.

The last two apply to the default vault only. The capture hook and the gardener
are wired to it, not to every vault; a second vault with no
`inbox/pending-reflect.md` has nothing to be stale.

## 4. Companion plugins - report only

Check once, not per vault, and never install:

- `obsidian@obsidian-skills` present in `claude plugin list`? If not, and
  `kepano/obsidian-skills` is reachable in `claude plugin marketplace list`,
  report it missing with the reason it is complementary - infrastructure here,
  workflow skills there. If the marketplace list itself fails, say unreachable
  rather than missing.
- `graphify --version` resolves? Report it missing only when a configured vault
  has `"layout": "org/repo"`, since `/obsidian-vault:graph` is what needs it.
- `crew@useful-claude-add-ons` installed? One line, and only when a vault holds
  ticket boards or code-graph output. Say nothing for a memory-only vault.

`/obsidian-vault:init`'s Companions step installs these.

## Report format

Group by vault, one line per check: OK / WARN / FAIL, and for every FAIL the
command that fixes it. End with the single next command to run - usually
`/obsidian-vault:repair`, or `/obsidian-vault:install <vault>` for a vault with
no REST API plugin at all.
