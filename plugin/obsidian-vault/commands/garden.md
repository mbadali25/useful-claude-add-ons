---
description: Run the gardener now - distill queued sessions into concepts and daily notes
allowed-tools: Agent
---

Dispatch the `obsidian-vault:gardener` subagent to process
`<vault>/inbox/pending-reflect.md` now, instead of waiting for its next
scheduled run. Pass it no arguments beyond "run now" - the agent reads its own
queue and vault config. Report what it produced when it returns.
