---
description: Run the gardener now - distill queued sessions into concepts and daily notes
allowed-tools: Agent, Bash
---

Run one bounded gardener pass now instead of waiting for the schedule.

1. Show what is queued:
   `python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" queue --max 5`
2. Dispatch the `obsidian-vault:gardener` subagent. It takes at most 5 items,
   and acknowledges each one with `vault_ops.py ack --id <id> --wrote <path>`
   only after the note it wrote exists - an item it could not finish stays
   queued.

For an unattended-style run that enforces the bounds in code rather than in
the agent's instructions, use `vault_ops.py garden-run --force-host` instead
(`--force-host` because an attended run need not be on the designated gardener
host). For a large backlog, `vault_ops.py drain` shows the batch plan; add
`--apply --batches N` once the user agrees. Report what came back.
