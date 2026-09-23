---
name: obsidian-scheduling
description: How to schedule the obsidian-vault gardener to run unattended, daily, on one designated host - generated cron, systemd-timer and Task Scheduler units, bounded runs, and draining a backlog. Use when the user wants nightly gardening, asks why the gardener only ran when they typed /obsidian-vault:garden, or has a large pending-reflect backlog.
---

# Scheduling the gardener

**This plugin never installs a scheduled task itself.** `vault_ops.py schedule`
generates the unit and prints the exact commands; the user runs them, with
their own OS's scheduler, where they can see and remove it without knowing this
plugin exists.

## What runs: one bounded pass

```
python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" garden-run
```

The bounds are enforced in code, not asked of a model:

- **At most 5 items per run**, oldest first. `--max` can lower it, never raise it.
- **At most 10 minutes per run.** Each item's processor gets only the time left;
  nothing starts once it is spent.
- **Acknowledge only after a successful write.** The processor (by default
  `claude -p` limited to Read/Write/Edit/Grep/Glob in the vault) must exit 0
  and print `GARDENER-WROTE: <path>` for each note; the item is acknowledged
  only if every such file exists inside the vault and is non-empty. Anything
  else leaves it queued for the next run.
- **One designated host.** `garden-run` refuses on any host other than config
  `gardener.host`. Two schedules on two machines syncing one vault would
  distil the same sessions twice.
- **One run at a time** (`inbox/.garden.lock`, treated as stale after 15 minutes).
- **Only owned files committed**, and only with `--commit`: the notes this run
  wrote plus its own `inbox/reflected.<host>.md`, via `git commit -- <paths>`.
  Leave `--commit` off when something else (Obsidian Git) owns commits.
- A queued session whose transcript is not on this host is left queued as
  "unresolved here" and does not use up a slot.

Log: `~/.claude/obsidian/gardener.log`, one line per item acknowledged or left queued.

## Generate the unit

Run on the host that should garden, and designate it in the same step:

```
python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" schedule --os cron --designate
python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" schedule --os cron --designate --apply
```

`--apply` writes only `gardener.host` into `~/.claude/obsidian/config.json`.
The unit itself is printed, never installed. `--os` is one of:

| `--os` | Output | Install command it prints |
|---|---|---|
| `cron` | one crontab line, daily at `--time` (default 02:23) | `( crontab -l ...; echo "<line>" ) \| crontab -` |
| `systemd` | `obsidian-gardener.service` + `.timer` (`Persistent=true`) for `~/.config/systemd/user/` | `systemctl --user daemon-reload` and `systemctl --user enable --now obsidian-gardener.timer` |
| `windows` | `Register-ScheduledTask` block, `-StartWhenAvailable`, 15-minute limit | the PowerShell block itself |

Pick cron where there is no systemd user bus - for example a root shell or a
container, where `systemctl --user` fails with "Failed to connect to bus".

The unit embeds the plugin's versioned install path, so **re-run `schedule`
after a plugin update**, or the scheduled command points at a directory the
update removed.

## Drain a backlog

```
python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" drain
python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" drain --apply --batches 4
```

The dry run prints the backlog, how many items this host can read, the number
of 5-item batches, and the first batch. `--apply` runs up to `--batches`
bounded passes back to back and stops early when a pass acknowledges nothing.
A 95-item backlog is 19 batches; run a few, read the notes they wrote, then
continue.

## Unattended permissions

The default processor is `claude -p ... --permission-mode acceptEdits
--allowedTools Read,Write,Edit,Grep,Glob`, run with the vault as its working
directory and the transcript's folder added with `--add-dir`. It has no Bash,
so it cannot commit, push or edit the queue; the runner does those. Say this
to the user before scheduling it: the job edits notes in the vault with
nobody present.

## Verify a schedule is actually working

1. The task/timer exists (`crontab -l`, `systemctl --user list-timers`,
   `Get-ScheduledTask 'Obsidian Gardener'`).
2. It has fired (`journalctl --user -u obsidian-gardener`, `Get-ScheduledTaskInfo`).
3. `gardener.log` shows items acknowledged - not just a process that started
   and exited on "not the designated gardener host".
