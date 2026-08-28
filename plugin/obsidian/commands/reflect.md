---
description: Ask the vault what it knows about a topic, and what contradicts
argument-hint: <topic>
allowed-tools: Agent
---

Dispatch the `obsidian:reflector` subagent on: $ARGUMENTS.

Pass the topic through unchanged. Report its findings, including any
contradiction it surfaces between notes - a contradiction is the useful
output here, not a bug in the vault.
