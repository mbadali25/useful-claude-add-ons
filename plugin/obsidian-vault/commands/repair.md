---
description: Repair a vault's REST bridge - resolve port collisions, reload stale Obsidian windows, re-register MCP servers - showing the plan before applying it
argument-hint: [fix-ports | reload | register | all] [vault-name]
allowed-tools: Read, Bash, PowerShell
---

Repair what `/obsidian-vault:doctor` found. This is the acting counterpart to
that command: doctor reports, repair writes.

Every operation is performed by
`${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py`. Do not hand-edit a
`data.json`, a `config.json`, or an MCP registration to fix any of this. The
script is dry-run by default and writes only with `--apply`, which is what makes
"show the plan, then ask" possible at all.

If `python` is not on PATH, try `python3` then `py`, and say which one worked.
Git Bash on Windows ships without `python3`.

## Exit codes

0 healthy or applied, 1 problems found, 2 usage error. Exit 1 from a dry run is
the normal case - it means there is something to fix, not that the script broke.
Exit 2 means the invocation was wrong; fix the flags rather than reporting a
vault fault.

## The loop, for every operation

1. **Run it without `--apply`.** That is the plan.
2. **Show the plan verbatim.** Name the vault, the file, and the value that
   would change.
3. **Ask.** Nothing below runs with `--apply` until the user says so, for that
   operation, on that vault. Not a batched yes for all three.
4. **Run it with `--apply`.**
5. **Re-run `diagnose`** and report the new verdict. Do not report success
   because the command exited 0 - report it because the diagnosis changed.

## Operations

Pick from $1, or run all three in the order below when $1 is empty or `all`.
`--vault <name>` scopes to one vault; `--all` covers every **configured** vault.
Default to the vault named in $2, and to `--all` only when the user asked for
every vault.

`fix-ports` has no `--all`, so its unscoped form is its default - and it edits a
vault's own `data.json`, which is a heavier write than the MCP config. It moves
only configured vaults. When the vault that should move is one config has never
named, that step is **refused by name** rather than worked around: moving the
other vault instead would hide a real conflict and relocate a vault that was not
at fault. The output says which vault has to `add-vault` before the collision
can be fixed.

`--vault X` is scoped the same way, and for the same reason. If ending the
collision means moving a vault other than X, that step is refused and names the
vault - being in your config is consent to be managed by this plugin, not
consent to be edited by a command you pointed somewhere else. The unscoped run
is what actually fixes it, and it still keeps the port with whichever vault holds
the bind. Say which vault would have to move before re-running unscoped.

A configured vault that discovery cannot find - deleted, renamed, or on a drive
that is not mounted - is named with its path and keeps the exit code non-zero.
An empty selection that exits 0 would report success for work nobody did.

`--all` deliberately stops at the config. `scan` and `diagnose` see every vault
on the machine, including ones config has never heard of, because a vault
nobody configured can still be the one causing a port collision. Acting on one
is different: naming a vault with `--vault` is consent, and sharing a disk is
not. Anything skipped for that reason is named in the output, so it is visible
rather than quietly dropped - `add-vault` is how it opts in.

### `fix-ports`

```
python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" fix-ports [--vault <name>]
python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" fix-ports [--vault <name>] --apply
```

This is the one that fixes the failure that looks like three failures. Two
vaults declaring the same port means one wins the bind and the other's plugin
fails to start its server at all - so its HTTP listener is gone, its HTTPS port
answers with the other vault's API key, and it serves the other vault's files.
One cause, three symptoms.

The comparison that finds it is `port` and `insecurePort` across **every**
vault's `.obsidian/plugins/obsidian-local-rest-api/data.json`, including vaults
that `~/.claude/obsidian/config.json` has never heard of. Do not reach for
`enableInsecureServer` here. A vault can have that flag already `true` and still
be dark, because the collision kills the whole server before either listener
starts.

Show the before and after port for each vault in the plan. A port change is a
change to what an already-registered MCP server points at, so `register` has to
follow it.

`--apply` writes `data.json` and stops there. It does **not** reload, and it
says which vaults are still running on their old port and old key. A user who
approved an edit to a file on disk did not approve having their editor restarted
under them, so the reload is asked for separately, below. There is a `--reload`
flag that folds the two together - pass it only once you already hold that
second yes, never to save a round trip.

A vault claiming the same port for both protocols has **two** things to move.
Expect two lines in the plan for it, and do not treat the second as a duplicate:
moving one and leaving the other is a repair that reports success while the
collision survives.

### `reload`

```
python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" reload [--vault <name> | --all]
```

The plugin reads `data.json` only at load. A vault whose file changed since its
window opened disagrees with disk on both the port and the API key until it
reloads. Run this after every `fix-ports` that applied anything.

`reload` has no dry-run form - there is no `--apply` to withhold. Ask before
running it anyway: it reloads a live Obsidian window, and a reload is disruptive
to whoever is typing in it. Say which vault's window you are about to reload and
wait for the yes.

Closing an Obsidian window is not quitting it - it minimizes to the tray, and a
tray-resident instance is still the stale one. If a reload does not take, say so
and ask for a real quit and relaunch rather than reloading again.

### `register`

```
python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" register [--vault <name> | --all]
python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" register [--vault <name> | --all] --apply
```

Registers one MCP server per vault, named `obsidian-<vault-name>`, against that
vault's HTTP port and current API key. Run it after any port change and after
any key rotation - "key rejected, and it used to work" is always this.

One server per vault, never one server for two. The bridge is per-port and per
vault instance; a single server config could not speak for both if you wanted it
to.

## Two things that will mislead you here

**`curl -k` proves less than it looks like it does.** It succeeds against the
HTTPS port where Claude Code's Node MCP client rejects the same self-signed
certificate. A green `curl -k` means the vault is serving; it does not mean the
MCP server will connect. Never repoint an MCP server at the HTTPS port because
`curl -k` reached it.

**`port` means different things in different files.** In a vault's
`data.json`, `port` is the HTTPS port and `insecurePort` is the HTTP one. In
`~/.claude/obsidian/config.json`, `port` is the HTTP port. They are not offset
by one and no arithmetic relates them - read each file's own value.

## When repair is the wrong command

A vault with no Local REST API plugin installed at all has nothing to fix.
`register` cannot invent an API key and `fix-ports` has no `data.json` to
compare. Send that vault to `/obsidian-vault:install`.

## Report

Per vault: what the plan said, what was applied, what the follow-up `diagnose`
returned. Name anything you deliberately did not apply and why the user declined
it.
