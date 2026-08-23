---
description: Guided phased setup for this repo — resumable, one phase at a time
argument-hint: [--status | --phase N]
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent, Skill
---

Run the guided setup for this repository.

Follow `${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/phases.md` exactly. It defines all
eight phases, the status file format, and the rules about stopping between phases.

Arguments: $ARGUMENTS
- `--status` — print the phase table from `.crew/STATUS.md` and stop
- `--phase N` — run that phase only, warning about incomplete prerequisites
- no argument — resume at the first phase not marked `done`

After each phase, if `notify.provider` is configured, send one line:
`bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/notify.sh phase "Phase N <state>"`
