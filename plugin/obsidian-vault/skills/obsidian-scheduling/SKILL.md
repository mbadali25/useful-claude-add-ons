---
name: obsidian-scheduling
description: How to schedule the obsidian-vault:gardener and obsidian-vault:reflector agents to run unattended on Windows and Linux. Use when the user wants nightly gardening, a recurring reflection pass, or asks why the gardener only ran when they typed /obsidian-vault:garden.
---

# Scheduling the gardener and reflector

**This plugin never schedules anything itself.** No hook here installs a
recurring task - a plugin silently registering a scheduled task on someone's
machine is the kind of thing that should require the user's own action, using
their own OS's own scheduler, which they can see and remove without needing to
know this plugin exists. This skill is the reference for doing that by hand,
or scripting it once with informed consent.

## What actually runs

A headless Claude Code call:

```
claude -p "<the gardener's own steps, or: run the obsidian-vault:gardener agent>" \
  --dangerously-skip-permissions --max-turns 80
```

`--dangerously-skip-permissions` is what makes an unattended run possible at
all - there is no one present to click "allow". Scope this deliberately: run
it as a user whose only local capability is this vault, or accept that the
gardener can act with the full permissions of whoever's account runs it. Say
this to the user before setting it up; do not bury it in a script comment.

Cap turns and run frequency - this is maintenance, not an open-ended agent.
Once nightly is normally enough; twice is rarely useful.

## Windows: Task Scheduler

```powershell
$action = New-ScheduledTaskAction -Execute (Get-Command claude).Source `
    -Argument '-p "run the obsidian-vault:gardener agent now" --dangerously-skip-permissions --max-turns 80' `
    -WorkingDirectory '<vault path>'
$trigger = New-ScheduledTaskTrigger -Daily -At '02:23'
Register-ScheduledTask -TaskName 'Obsidian Gardener' -Action $action -Trigger $trigger `
    -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2))
```

`-StartWhenAvailable` catches a run missed because the machine was asleep at
02:23. Verify with `Start-ScheduledTask 'Obsidian Gardener'` and read the log
the gardener writes for itself, rather than trusting Task Scheduler's own
success/failure flag - a run that "succeeded" by exiting 0 after doing nothing
useful looks identical to Task Scheduler.

## Linux / macOS: cron or a systemd user timer

cron, simplest:

```
23 2 * * * cd '<vault path>' && claude -p "run the obsidian-vault:gardener agent now" \
  --dangerously-skip-permissions --max-turns 80 >> <vault path>/.claude/gardener.log 2>&1
```

systemd user timer, if the machine runs systemd and the user wants restart-on-
failure semantics cron does not give:

```ini
# ~/.config/systemd/user/obsidian-gardener.service
[Unit]
Description=Obsidian vault gardener

[Service]
Type=oneshot
WorkingDirectory=%h/vault-path
ExecStart=claude -p "run the obsidian-vault:gardener agent now" --dangerously-skip-permissions --max-turns 80
```

```ini
# ~/.config/systemd/user/obsidian-gardener.timer
[Timer]
OnCalendar=*-*-* 02:23:00
Persistent=true

[Install]
WantedBy=timers.target
```

`Persistent=true` is the cron `StartWhenAvailable` equivalent - a run missed
while the machine was off fires once it is back. Enable with
`systemctl --user enable --now obsidian-gardener.timer`.

## Run it on exactly one machine

If the vault syncs across machines (Obsidian Sync, or a synced folder), two
scheduled gardeners on two machines distill the same `inbox/pending-reflect.md`
queue independently and produce duplicate concepts. Pick one machine for the
schedule; the others can still run `/obsidian-vault:garden` on demand without
conflict, since an on-demand run processes whatever is left in the queue at
that moment rather than racing a concurrent one.

## Verify a schedule is actually working

Do not assume a registered task runs correctly. Check:
1. The task/timer exists and is enabled (`Get-ScheduledTask` /
   `systemctl --user list-timers`).
2. It has actually fired at least once (`Get-ScheduledTaskInfo` /
   `journalctl --user -u obsidian-gardener`).
3. The gardener's own log shows a real pass, not just a process that started
   and exited immediately from a config error.
